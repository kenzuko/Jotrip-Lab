import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker from './worker.mjs';
import {speechText} from './tts-stage.mjs';
const origin='https://ai.openphuquoc.com',ip='198.51.100.99';
let calls=0,limitCalls=0;
const env={
 AI:{run:async(model,opts)=>{calls++;return {response:'Hòn Thơm nằm ở phía Nam đảo Phú Quốc. Bạn có thể đi cáp treo từ khu vực An Thới. Mình chưa có dữ liệu thời tiết hoặc vận hành hôm nay đã xác minh để khẳng định giờ đi.'};}},
 AI_PER_CLIENT:{limit:async()=>{limitCalls++;return {success:true}}},
 AI_GLOBAL:{limit:async()=>({success:true})},
 TTS_SIGN_KEY:'B'.repeat(45),
 ASSETS:{fetch:async()=>new Response('static', {status:200})}
};
async function ask(text){
 const req=new Request(origin+'/api/turn',{method:'POST',headers:{'origin':origin,'content-type':'application/json','cf-connecting-ip':ip},body:JSON.stringify({text,locale:'vi-VN'})});
 const res=await worker.fetch(req,env);assert.equal(res.status,200);return res.json()
}
test('each AI response uses exactly one signed continuous TTS segment',async()=>{
 const a=await ask('Hòn Thơm là gì?');
 assert.ok(a.answer.includes('Hòn Thơm'));
 assert.equal(a.speakSegments.length,1);
 assert.ok(a.speakSegments[0].text.length>0);
 assert.ok(a.speakSegments[0].text.length<=280);
 assert.ok(a.speakSegments[0].permit.length>40);
 assert.equal(a.speakText,a.speakSegments[0].text);
 assert.equal(a.speakPermit,a.speakSegments[0].permit);
 const b=await ask('Hòn Thơm đi cáp treo được không?');
 assert.equal(b.speakSegments.length,1);
 assert.notEqual(b.speakSegments[0].permit,a.speakSegments[0].permit);
 assert.equal(calls,2);
 console.log('TWO_TURNS_CONSUME_2_SIGNED_TTS_REQUESTS');
});
test('voice truncation is sentence-aware while full answer remains visible',()=>{
 const answer='Câu đầu đủ ý. '+'Đoạn sau chi tiết. '.repeat(34);
 const spoken=speechText(answer);
 assert.ok(spoken.length<=280&&spoken.endsWith('.'));
 assert.ok(answer.length>spoken.length);
});
test('do not modify core assets/bindings, proof preserves owner UX',()=>{
 const html=fs.readFileSync('./public/index.html','utf8');
 const js=fs.readFileSync('./public/song-v1.js','utf8');
 assert.ok(html.includes('Chào bạn, mình là Sóng.'));
 assert.ok(html.includes('by OpenPQ AI'));
 assert.ok(html.includes('song-approved.webp'));
 assert.ok(html.includes('song-v1.js?v=1211'));
 assert.ok(js.includes('sessionArmed=true'));
 assert.ok(js.includes('rearmVoiceAfterSpeech'));
 assert.ok(js.includes('qa-copy'));
 assert.ok(js.includes('highshelf'));
 assert.ok(js.includes('speechBounds'));
 assert.ok(js.includes('transcript-confirm'));
});
console.log('V121_CONTINUOUS_VOICE_OFFLINE_TESTS_COMPLETE');