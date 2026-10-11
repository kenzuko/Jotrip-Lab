import {TurnEngine} from '../src/turn-engine.mjs';
import {PersistentMediaPlayer} from '../src/persistent-player.mjs';
const $=s=>document.querySelector(s);
const sample='https://ai.openphuquoc.com/assets/v113_adam_speed086.wav';
const status=$('#status'),result=$('#result'),recent=$('#recent'),human=$('#human');
const events=[];
let started=0,completed=0,failed=0,running=false,humanMarks=[];
function log(event){
  const safe={time:new Date().toISOString(),event:event.event||event,
    turnId:event.turnId,segment:event.segment,state:event.state,detail:event.detail};
  events.push(safe);
  if(events.length>200)events.shift();
  const line=document.createElement('li');
  line.textContent=[safe.event,safe.turnId?'lượt '+safe.turnId:'',safe.segment?'đoạn '+safe.segment:'',safe.detail||''].filter(Boolean).join(' · ');
  recent.prepend(line);while(recent.children.length>25)recent.lastChild.remove();
}
const player=new PersistentMediaPlayer({audio:$('#player'),onEvent:log,timeoutMs:25000});
const engine=new TurnEngine({
  synthesizer:async()=>({answer:'Mẫu giọng thực từ OpenPQ VPS',
    segments:[{url:sample},{url:sample},{url:sample}]}),
  player,requireConfirmation:true,onEvent:log
});
function render(){
  result.textContent='Số lượt thử: '+started+' · Hoàn tất qua sự kiện trình duyệt: '+completed+
   ' · Không hoàn tất: '+failed+'\nTrạng thái: '+engine.state+
   '\nLưu ý: trạng thái kỹ thuật không xác nhận tai người đã nghe.';
  result.className=failed?'bad':'good';
}
async function turn(){
 const t=engine.receiveTranscript('Test âm thanh #'+(++started));
 if(!engine.confirm(t))throw Error('CONFIRM_FAILED');
 const response=await engine.run(t);
 if(response.ok)completed++;
 else {failed++;status.textContent='BLOCKED: '+response.reason+' ở lượt '+t}
 render();return response.ok;
}
$('#all').addEventListener('click',async()=>{
 if(running)return;
 running=true;started=completed=failed=0;events.length=0;recent.replaceChildren();
 status.textContent='Đang thử tự động 10 lượt...';
 try{
  for(let n=0;n<10;n++){
   const ok=await turn();
   if(!ok){status.textContent='Đã dừng ở lượt '+started+' vì Safari chưa phát xong.';break}
  }
  if(completed===10)status.textContent='Trình duyệt báo xong 10/10. Cậu hãy xác nhận có nghe đủ tiếng thật không.';
 }catch{failed++;status.textContent='Có lỗi vận hành trình phát, đã dừng thử nghiệm.'}
 finally{running=false;render()}
});
$('#single').addEventListener('click',async()=>{
 if(running)return;running=true;
 try{await turn();status.textContent=engine.state==='ready'?'Trình duyệt báo lượt đã phát xong.':'Lượt chưa hoàn tất.';}
 finally{running=false;render()}
});
$('#stop').addEventListener('click',()=>{
 engine.cancel('user_interruption');running=false;
 status.textContent='Đã ngắt lượt, không ghi nhận hoàn thành.';render();
});
$('#yes').addEventListener('click',()=>{humanMarks.push({tested:started,heard:true});human.textContent='Đã đánh dấu nghe đủ '+completed+'/'+started+' lượt.'});
$('#no').addEventListener('click',()=>{humanMarks.push({tested:started,heard:false});human.textContent='Đã ghi nhận lỗi nghe thực tế, vui lòng sao chép nhật ký.'});
$('#copy').addEventListener('click',async()=>{
 const payload=JSON.stringify({version:'V12-A1-PROOF',started,completed,failed,
  humanMarks,events:events.slice(-50)},null,2);
 try{await navigator.clipboard.writeText(payload);status.textContent='Đã sao chép nhật ký ẩn danh.'}
 catch{status.textContent='Trình duyệt không cho sao chép. Vẫn có thể chụp màn hình.'}
});
render();