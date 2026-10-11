/** Offline-only resource budget simulator.
 * No IP-as-identity, no production storage, no distributed-atomic guarantee.
 * Use this to prove the CONTRACT before implementing a durable authority.
 */
export class TurnBudget {
 constructor({maxTurns=30,maxConcurrent=1,maxQueue=2,now=()=>Date.now(),ttlMs=60000}={}){
  if(maxTurns<1||maxConcurrent<1||maxQueue<0)throw Error('INVALID_LIMITS');
  Object.assign(this,{maxTurns,maxConcurrent,maxQueue,now,ttlMs});
  this.reservations=new Map();this.active=new Set();this.waiting=[];
 }
 key(session,turn){if(!session||!Number.isInteger(turn)||turn<1)throw Error('INVALID_TURN');return session+':'+turn;}
 reserve({session,turn,ip}){
  const key=this.key(session,turn);const existing=this.reservations.get(key);
  if(existing)return {ok:true,reused:true,id:key,state:existing.state};
  const owned=[...this.reservations.values()].filter(v=>v.session===session&&!v.cancelled);
  if(owned.length>=this.maxTurns)return {ok:false,reason:'TURN_BUDGET_EXHAUSTED'};
  const waitingCount=this.waiting.length;
  if(this.active.size>=this.maxConcurrent&&waitingCount>=this.maxQueue)
   return {ok:false,reason:'CPU_QUEUE_FULL'};
  const r={key,session,turn,state:'reserved',created:this.now(),chunks:new Set(),cancelled:false};
  // ip is deliberately ignored: shared NAT is not a person identity.
  this.reservations.set(key,r);this.waiting.push(key);
  this.dispatch();
  return {ok:true,reused:false,id:key,state:r.state};
 }
 dispatch(){
  while(this.active.size<this.maxConcurrent&&this.waiting.length){
    const k=this.waiting.shift(),r=this.reservations.get(k);
    if(!r||r.cancelled)continue;
    r.state='running';this.active.add(k);
  }
 }
 startChunk(id,chunkId){
  const r=this.reservations.get(id);
  if(!r||r.cancelled||r.state!=='running')return {ok:false,reason:'NOT_ACTIVE'};
  if(!Number.isInteger(chunkId)||chunkId<0||chunkId>=6)return {ok:false,reason:'BAD_CHUNK'};
  if(this.now()-r.created>this.ttlMs)return {ok:false,reason:'RESERVATION_EXPIRED'};
  const reused=r.chunks.has(chunkId);r.chunks.add(chunkId);
  return {ok:true,reused,turnCharge:reused?0:0};
 }
 complete(id){
  const r=this.reservations.get(id);if(!r||r.cancelled)return false;
  r.state='complete';this.active.delete(id);this.dispatch();return true;
 }
 cancel(id){
  const r=this.reservations.get(id);if(!r)return false;
  r.cancelled=true;r.state='cancelled';this.active.delete(id);
  this.waiting=this.waiting.filter(x=>x!==id);this.dispatch();return true;
 }
 status(id){return this.reservations.get(id)?.state||'unknown'}
 snapshot(){return {active:this.active.size,waiting:this.waiting.length,reserved:this.reservations.size}}
}