import test from 'node:test';
import assert from 'node:assert/strict';
import {TurnEngine,STATES} from '../src/turn-engine.mjs';
import {TurnBudget} from '../src/turn-budget.mjs';
import {PersistentMediaPlayer} from '../src/persistent-player.mjs';
const URL='https://ai.openphuquoc.com/assets/v113_adam_speed086.wav';
function rig({confirmation=true,segments=3,blockedAt=-1}={}){
 const trace=[];let calls=0;
 const player={stop(){trace.push('stop')},async play(u){
    calls++;return calls!==blockedAt;
 }};
 const synth=async({text})=>({answer:'Guide: '+text,segments:Array.from({length:segments},()=>({url:URL}))});
 const engine=new TurnEngine({synthesizer:synth,player,requireConfirmation:confirmation,
 onEvent:e=>trace.push(e)});
 return {engine,trace,get plays(){return calls}};
}
test('confirmation remains mandatory by default',async()=>{
 const {engine,r}=({engine:rig().engine});
 const id=engine.receiveTranscript('Đi Hòn Thơm?');
 assert.equal(engine.state,STATES.CONFIRM);
 assert.deepEqual(await engine.run(id),{ok:false,reason:'NOT_CONFIRMED'});
 assert.equal(engine.history.length,0);
 assert.equal(engine.confirm(id),true);
 assert.equal((await engine.run(id)).ok,true);
 assert.equal(engine.history.length,2);
});
test('10 consecutive three-chunk conversations never go silent in proof',async()=>{
 const r=rig();
 for(let i=1;i<=10;i++){
  const id=r.engine.receiveTranscript('Câu hỏi '+i);
  assert.equal(r.engine.confirm(id),true);
  const out=await r.engine.run(id);
  assert.deepEqual(out,{ok:true,playedCount:3,completion:'player_ended_proxy'});
  assert.equal(r.engine.state,STATES.READY);
 }
 assert.equal(r.plays,30);
 assert.equal(r.engine.history.length,8);
 assert.equal(r.trace.filter(x=>x.event==='segment_ack').length,30);
});
test('second turn playback blocked is never marked spoken',async()=>{
 const r=rig({segments:2,blockedAt:3});
 let id=r.engine.receiveTranscript('one');r.engine.confirm(id);assert.equal((await r.engine.run(id)).ok,true);
 id=r.engine.receiveTranscript('two');r.engine.confirm(id);
 const result=await r.engine.run(id);
 assert.equal(result.reason,'AUDIO_BLOCKED');
 assert.equal(r.engine.state,STATES.BLOCKED);
 assert.equal(r.engine.history.some(x=>x.content==='Guide: two'),false);
 r.engine.resetAudio();assert.equal(r.engine.state,STATES.READY);
});
test('old generation cannot commit history when next turn starts',async()=>{
 let resolve;
 const synth=()=>new Promise(r=>{resolve=r});
 const player={stop(){},async play(){return true}};
 const engine=new TurnEngine({synthesizer:synth,player});
 const one=engine.receiveTranscript('old');engine.confirm(one);
 const oldPending=engine.run(one);
 const two=engine.receiveTranscript('new');engine.confirm(two);
 resolve({answer:'stale',segments:[{url:URL}]});
 assert.deepEqual(await oldPending,{ok:false,reason:'STALE'});
 assert.equal(engine.history.length,0);
 assert.equal(engine.turnId,two);
});
test('stale cancellation during segment playback never commits old turn',async()=>{
 let release;
 const player={stop(){},async play(){return new Promise(r=>{release=r})}};
 const engine=new TurnEngine({synthesizer:async()=>({answer:'old answer',segments:[{url:URL}]}),player});
 const one=engine.receiveTranscript('old');engine.confirm(one);
 const pending=engine.run(one);
 await Promise.resolve();await Promise.resolve();
 engine.receiveTranscript('new');
 if(release)release(true);
 assert.equal((await pending).ok,false);
 assert.equal(engine.history.length,0);
});
test('unconfirmed/invalid/low-confidence audio is not sent automatically',async()=>{
 const r=rig();
 assert.equal(r.engine.receiveTranscript(' ',{confirmed:false}),null);
 assert.equal(r.engine.receiveTranscript('noise',{background:true}),null);
 const id=r.engine.receiveTranscript('Rạch Vẹm?',{confidence:0.2});
 assert.equal(r.engine.state,STATES.CONFIRM);
 assert.equal((await r.engine.run(id)).reason,'NOT_CONFIRMED');
 assert.equal(r.plays,0);
});
test('budget charges per turn not per chunk, regardless of hotel IP',()=>{
 const b=new TurnBudget({maxTurns:10,maxConcurrent:1,maxQueue:3});
 const first=b.reserve({session:'guest-A',turn:1,ip:'same-hotel-ip'});
 assert.equal(first.ok,true);
 assert.equal(first.state,'running');
 for(let i=0;i<3;i++)assert.deepEqual(b.startChunk(first.id,i),{ok:true,reused:false,turnCharge:0});
 assert.equal(b.reserve({session:'guest-A',turn:1,ip:'same-hotel-ip'}).reused,true);
 assert.equal(b.startChunk(first.id,0).reused,true);
 const second=b.reserve({session:'guest-A',turn:2,ip:'same-hotel-ip'});
 assert.equal(second.ok,true);assert.equal(b.status(second.id),'reserved');
 const other=b.reserve({session:'guest-B',turn:1,ip:'same-hotel-ip'});
 assert.equal(other.ok,true);
 b.complete(first.id);
 assert.equal(b.status(second.id),'running');
 b.complete(second.id);
 assert.equal(b.status(other.id),'running');
});
test('queue capacity and cancellation fail fast',()=>{
 const b=new TurnBudget({maxConcurrent:1,maxQueue:1});
 const a=b.reserve({session:'A',turn:1});
 const c=b.reserve({session:'C',turn:1});
 const fail=b.reserve({session:'D',turn:1});
 assert.deepEqual(fail,{ok:false,reason:'CPU_QUEUE_FULL'});
 b.cancel(a.id);
 assert.equal(b.status(c.id),'running');assert.equal(b.snapshot().active,1);
});
test('reservation expiry and idempotence, no automatic token bypass',()=>{
 let t=0;
 const b=new TurnBudget({now:()=>t,ttlMs:100});
 const a=b.reserve({session:'A',turn:1});
 t=101;
 assert.equal(b.startChunk(a.id,0).reason,'RESERVATION_EXPIRED');
 assert.equal(b.reserve({session:'A',turn:1}).reused,true);
});
test('player persists element; never claims success on play rejection',async()=>{
 let paused=0,playCount=0;
 const events=new Map();
 const a={src:'',pause(){paused++},play(){playCount++;return Promise.reject(Object.assign(Error('blocked'),{name:'NotAllowedError'}))},
 addEventListener(k,fn){events.set(k,fn)},removeEventListener(k){events.delete(k)}};
 const p=new PersistentMediaPlayer({audio:a});
 const ok=await p.play(URL,{turnId:1,segment:1});
 assert.equal(ok,false);assert.equal(playCount,1);assert.equal(p.active,null);
 p.stop();assert.ok(paused>=2);
});
test('player completes ONLY on ended event, not successful play()',async()=>{
 const handlers=new Map();
 const a={pause(){},play(){return Promise.resolve()},addEventListener(k,fn){handlers.set(k,fn)},
 removeEventListener(k){handlers.delete(k)}};
 const p=new PersistentMediaPlayer({audio:a,timeoutMs:1000});
 const result=p.play(URL,{turnId:1});
 await Promise.resolve();await Promise.resolve();
 assert.ok(p.active,'still waiting for ended');
 handlers.get('ended')();
 assert.equal(await result,true);
});
console.log('V12_PROOF_TESTS_COMPLETE');