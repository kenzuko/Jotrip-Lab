import {makeEndpointDetector} from '/voice-activity.mjs?v=1202';
import {speechBounds,tooShortToRecognize} from '/speech-crop.mjs?v=1202';
import {combinePcmWavs} from '/wav-join.mjs';

const $=id=>document.getElementById(id);
const ui={body:document.body,presence:$('presence'),conversation:$('conversation-view'),
 thread:$('thread'),question:$('question'),status:$('status-label'),mini:$('conversation-state'),
mic:$('composer-mic'),transcript:$('transcript-panel'),transcriptText:$('transcript-edit'),
result:$('result-panel'),resultBody:$('result-body'),send:$('send'),stopAudio:$('stop-audio')};
const qa={events:[],startMicMs:null,eouDelayMs:null,asrMs:null,llmMs:null,ttsMs:null,
 audioStartMs:null,lastError:null};
window.__songQA=qa; // Metadata only. No transcript or raw WAV in QA telemetry.
const clock=()=>performance.now();
const stamp=(type,fields={})=>{qa.events.push({type,at:Math.round(clock()),...fields});if(qa.events.length>60)qa.events.shift()};
const state={view:'welcome',status:'idle',turn:0,history:[],pendingInput:'text',pendingText:'',
 voice:null,openingMic:false,sessionArmed:false,request:null,playSource:null,playAbort:null,audioContext:null,filterChain:null,lastAudio:null,lastAssistant:null,
 lastPermits:[],settings:{readText:false,reduceMotion:false},resultOpen:false};
const labeled={idle:'Sóng đang sẵn sàng',listening:'Sóng đang nghe...',transcribing:'Sóng đang nhận giọng nói...',
 confirming:'Bạn kiểm tra lại điều Sóng vừa nghe',thinking:'Sóng đang suy nghĩ...',buffering:'Sóng đang chuẩn bị giọng...',
 speaking:'Sóng đang trả lời',ready:'Sóng đã sẵn sàng',error:'Chưa kết nối được. Bạn có thể thử lại hoặc nhập chữ.'};
function setStatus(status,info){
 state.status=status;ui.body.dataset.state=status;
 ui.status.textContent=info||labeled[status]||labeled.idle;
 ui.mini.textContent=ui.status.textContent;ui.mic.setAttribute('aria-label',status==='listening'?'Dừng ghi âm':'Bắt đầu nói bằng micro');
 ui.stopAudio.hidden=status!=='speaking'&&status!=='buffering';
 $('end-voice-session').hidden=!state.sessionArmed;
 stamp('state',{state:status});
}
function showView(view){
 state.view=view;ui.body.dataset.view=view;ui.presence.hidden=view!=='welcome';
 ui.conversation.hidden=view==='welcome';
 if(view==='conversation'){requestAnimationFrame(()=>{if(!ui.thread.querySelector('.message'))return;
  ui.thread.lastElementChild?.scrollIntoView({block:'nearest',behavior:'smooth'});});}
}
function clearTranscript(){ui.transcript.hidden=true;state.pendingText='';}
function disarmVoiceSession(reason='user'){
 state.sessionArmed=false;closeVoice();$('end-voice-session').hidden=true;
 stamp('voice_session_end',{reason});
}
function rearmVoiceAfterSpeech(turn){
 if(!state.sessionArmed||turn!==state.turn||document.hidden||state.openingMic||state.voice)return;
 stamp('voice_session_rearm');
 setTimeout(()=>{
  if(state.sessionArmed&&turn===state.turn&&!document.hidden&&!state.voice)
   void beginVoice();
 },280);
}
function buttonText(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',fn);return b;}
function addMessage(role,text){
 const intro=ui.thread.querySelector('.thread-intro');if(intro)intro.hidden=true;
 const m=document.createElement('article');m.className='message '+role;if(role==='assistant')state.lastAssistant=m;
 if(role==='user'){m.textContent=text;}
 else{
  const heading=document.createElement('div');heading.className='assistant-heading';
  const symbol=document.createElement('span');symbol.className='tiny-wave';symbol.textContent='〰';
  heading.append(symbol,document.createTextNode(' Sóng · by OpenPQ AI'));
  const p=document.createElement('p');p.className='assistant-content';p.textContent=text;
  const meta=document.createElement('div');meta.className='message-meta';
  meta.textContent='Thông tin tham khảo · chưa xác minh vận hành trực tiếp.';
  const actions=document.createElement('div');actions.className='message-actions';
  actions.append(buttonText('Hỏi tiếp',()=>ui.question.focus()));
  if(state.lastAudio)actions.append(buttonText('Nghe lại',()=>playCached(true)));
  m.append(heading,p,meta,actions);
 }
 ui.thread.append(m);
 requestAnimationFrame(()=>{if(!ui.thread.hidden) m.scrollIntoView({block:'nearest',behavior:'smooth'});});
 return m;
}
function newImageResult(url,title,caption,creditUrl,credit){
 const card=document.createElement('div');card.className='visual-card';
 const img=document.createElement('img');img.src=url;img.alt=caption;img.loading='lazy';
 const content=document.createElement('div');content.className='visual-card-body';
 const h=document.createElement('h2');h.textContent=title;
 const p=document.createElement('p');p.textContent='Ảnh thực tế minh họa địa điểm. Không phải dữ liệu vận hành theo thời gian thực.';
 const small=document.createElement('small');small.append('Nguồn ảnh: ');
 const link=document.createElement('a');link.textContent=credit;link.href=creditUrl;link.target='_blank';link.rel='noopener noreferrer';
 small.append(link);content.append(h,p,small);card.append(img,content);return card;
}
const scenes=[
 {pattern:/hòn\s*thơm|cáp\s*treo/i,image:'/assets/hon-thom.jpg',title:'Hòn Thơm',
 credit:'Wikimedia Commons · Vivu Vietnam · CC BY-SA 4.0',url:'https://commons.wikimedia.org/wiki/File:Hon_Thom_Cable_Car_aerial_view_Phu_Quoc_Island_Vietnam.jpg'},
 {pattern:/dinh\s*cậu/i,image:'/assets/dinh-cau.jpg',title:'Dinh Cậu',
 credit:'Wikimedia Commons · trungydang · CC BY 3.0',url:'https://commons.wikimedia.org/wiki/File:Dinh_C%E1%BA%ADu,_D%C6%B0%C6%A1ng_%C4%90%C3%B4ng,_Ph%C3%BA_Qu%E1%BB%91c,_Kien_giang_-_panoramio.jpg'},
 {pattern:/sunset\s*town|thị\s*trấn\s*hoàng\s*hôn/i,image:'/assets/sunset-town.jpg',title:'Sunset Town',
 credit:'Wikimedia Commons · Vivu Vietnam · CC BY-SA 4.0',url:'https://commons.wikimedia.org/wiki/File:Sunset-town-phu-quoc-2.jpg'}
];
function showContext(query){
 const scene=scenes.find(x=>x.pattern.test(query));
 ui.resultBody.replaceChildren();ui.result.hidden=true;ui.conversation.dataset.hasResult='false';
 if(scene){
  ui.resultBody.append(newImageResult(scene.image,scene.title,scene.title+' Phú Quốc, ảnh tư liệu thực tế',scene.url,scene.credit));
  ui.result.hidden=false;ui.conversation.dataset.hasResult='true';$('result-kind').textContent='ẢNH ĐỊA ĐIỂM · NGUỒN RÕ RÀNG';
  if(window.matchMedia('(max-width:1099px)').matches)requestAnimationFrame(()=>ui.result.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}));return;
 }
 if(/thời\s*tiết|trời\s*có\s*mưa|sóng\s*biển|dự\s*báo\s*(?:mưa|gió|biển)|gió\s*biển/i.test(query)){
  const card=document.createElement('div');card.className='truth-card';
  const title=document.createElement('strong');title.textContent='Chưa có dữ liệu quan trắc đã xác minh';
  const p=document.createElement('p');p.textContent='Bản demo Sóng chưa kết nối luồng Weather chính thức. Không có căn cứ để hiển thị dự báo theo giờ hoặc nhãn an toàn.';
  card.append(title,p);ui.resultBody.append(card);
  ui.result.hidden=false;ui.conversation.dataset.hasResult='true';$('result-kind').textContent='TRẠNG THÁI DỮ LIỆU';
  if(window.matchMedia('(max-width:1099px)').matches)requestAnimationFrame(()=>ui.result.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}));
 }
}
function captureError(e,phase){qa.lastError=phase+':'+(e?.name||'error');stamp('error',{phase,name:e?.name||'Error'})}
async function copyDiagnostics(){
 const payload={product:'OpenPQ AI Song',version:'V12.1-voice',time:new Date().toISOString(),
 browser:navigator.userAgent.slice(0,200),metrics:{micStartMs:qa.startMicMs,endOfUtteranceMs:qa.eouDelayMs,
 asrMs:qa.asrMs,llmVisibleMs:qa.llmMs,ttsReadyMs:qa.ttsMs,firstAudioEventMs:qa.audioStartMs},
 lastError:qa.lastError,events:qa.events.slice(-25)};
 try{await navigator.clipboard.writeText(JSON.stringify(payload,null,2));$('qa-note').textContent='Đã sao chép số đo, không bao gồm nội dung hội thoại.';}
 catch{$('qa-note').textContent='Safari chưa cho sao chép tự động. Bạn có thể chụp màn hình trạng thái.';}
}
function cancelRequest(){state.request?.abort();state.request=null;}
function closeVoice(){
 const v=state.voice;state.voice=null;
 if(!v)return;
 v.done=true;clearTimeout(v.timer);
 try{v.processor?.disconnect();v.source?.disconnect();v.sink?.disconnect()}catch{}
 v.stream?.getTracks().forEach(t=>t.stop());
 v.context?.close?.().catch(()=>{});
}
function stopAudio(){
 state.playAbort?.abort();state.playAbort=null;
 if(state.playSource){try{state.playSource.stop()}catch{};state.playSource=null;}
 ui.stopAudio.hidden=true;
}
function userGestureAudio(){
 try{
  const C=window.AudioContext||window.webkitAudioContext;
  if(!C)return;
  if(!state.audioContext){
   const ctx=new C();
   const hp=ctx.createBiquadFilter();hp.type='highpass';hp.frequency.value=95;hp.Q.value=.707;
   const shelf=ctx.createBiquadFilter();shelf.type='highshelf';shelf.frequency.value=2850;shelf.gain.value=2.3;
   const gain=ctx.createGain();gain.gain.value=.84;
   hp.connect(shelf);shelf.connect(gain);gain.connect(ctx.destination);
   state.audioContext=ctx;state.filterChain=hp;
  }
  if(state.audioContext.state!=='running')state.audioContext.resume().catch(()=>{});
 }catch(e){captureError(e,'audio_unlock')}
}
async function playCached(fromTap=false){
 if(!state.lastAudio){setStatus('ready','Chưa có tiếng để nghe lại. Nội dung chữ vẫn có ở trên.');return false;}
 if(fromTap)userGestureAudio();
 const ctx=state.audioContext;
 if(!ctx){setStatus('ready','Giọng chưa hoạt động trên thiết bị này. Bạn xem phần chữ nhé.');return false;}
 if(ctx.state!=='running'){
  try{await ctx.resume()}catch{}
 }
 if(ctx.state!=='running'){setStatus('ready','Safari chưa cho phép phát tiếng. Bạn chạm Nghe lại khi sẵn sàng.');return false;}
 stopAudio();const controller=new AbortController();state.playAbort=controller;
 try{
  const decoded=await ctx.decodeAudioData(state.lastAudio.slice(0));
  if(controller.signal.aborted)return false;
  const src=ctx.createBufferSource();src.buffer=decoded;src.playbackRate.value=1;
  src.connect(state.filterChain);state.playSource=src;
  setStatus('speaking','Sóng đang trả lời bằng giọng nam miền Nam (lọc sáng nhẹ)...');
  qa.audioStartMs=qa.audioStartMs??Math.round(clock());stamp('audio_start');
  const heard=await new Promise(resolve=>{
   let ended=false;const settle=ok=>{if(ended)return;ended=true;
    clearTimeout(timer);controller.signal.removeEventListener('abort',aborted);
    if(state.playSource===src)state.playSource=null;resolve(ok);};
   const aborted=()=>{try{src.stop()}catch{}settle(false)};
   const timer=setTimeout(()=>{try{src.stop()}catch{}settle(false)},Math.max(3000,decoded.duration*1000+1800));
   controller.signal.addEventListener('abort',aborted,{once:true});
   src.onended=()=>settle(!controller.signal.aborted);
   try{src.start()}catch{settle(false)}
  });
  if(state.playAbort===controller)state.playAbort=null;
  if(heard){setStatus('ready','Sóng đã phát xong theo trình duyệt. Bạn có thể hỏi tiếp.');stamp('audio_end');}
  else{setStatus('ready','Tiếng đã bị ngắt. Câu trả lời bằng chữ vẫn còn.');stamp('audio_interrupted');}
  return heard;
 }catch(e){captureError(e,'playback');setStatus('ready','Chưa phát được tiếng trên Safari. Bạn có thể đọc câu trả lời hoặc hỏi tiếp.');return false}
}
async function synthAndSpeak(payload,turn){
 const parts=(Array.isArray(payload.speakSegments)?payload.speakSegments:[]).filter(x=>x?.text&&x?.permit).slice(0,3);
 if(!parts.length){disarmVoiceSession('tts_not_ready');setStatus('ready','Giọng Sóng chưa sẵn sàng. Bạn vẫn xem được câu trả lời bằng chữ.');return}
 const controller=new AbortController();state.playAbort=controller;const t0=clock(),wavs=[];
 setStatus('buffering','Đang chuẩn bị giọng Sóng... Câu trả lời bằng chữ đã có.');
 for(const part of parts){
  if(turn!==state.turn||controller.signal.aborted)return;
  try{
   const timer=setTimeout(()=>controller.abort(),28000);
   const res=await fetch('/api/speak',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},
    body:JSON.stringify({text:part.text,permit:part.permit,locale:'vi-VN'}),signal:controller.signal}).finally(()=>clearTimeout(timer));
   if(!res.ok)throw new Error('TTS_HTTP_'+res.status);
   if(!/^audio\/wav/i.test(res.headers.get('content-type')||''))throw new Error('TTS_NOT_WAV');
   const buf=await res.arrayBuffer();if(buf.byteLength<44||buf.byteLength>2000000)throw new Error('INVALID_AUDIO');
   wavs.push(buf);
  }catch(e){captureError(e,'tts');break}
 }
 if(turn!==state.turn||controller.signal.aborted)return;
 if(!wavs.length){disarmVoiceSession('tts_unavailable');setStatus('ready','Giọng đang bận hoặc hết lượt miễn phí. Phiên nghe đã tạm dừng; chạm micro để tiếp tục.');return}
 try{
  state.lastAudio=wavs.length===1?wavs[0]:combinePcmWavs(wavs);
  if(state.lastAssistant){const row=state.lastAssistant.querySelector('.message-actions');if(row&&!row.querySelector('[data-replay]')){const replay=buttonText('Nghe lại',()=>playCached(true));replay.dataset.replay='true';row.append(replay);}}
  qa.ttsMs=Math.round(clock()-t0);stamp('tts_ready',{ms:qa.ttsMs,parts:wavs.length,expected:parts.length});
  if(wavs.length!==parts.length){disarmVoiceSession('tts_partial');setStatus('ready','Chỉ chuẩn bị được một phần giọng. Bạn có thể nghe thử, nội dung chữ vẫn đầy đủ.');return}
  const heard=await playCached(false);
  if(heard&&state.sessionArmed)rearmVoiceAfterSpeech(turn);
  else if(!heard&&state.sessionArmed)disarmVoiceSession('playback_interrupted');
 }catch(e){captureError(e,'wav_join');disarmVoiceSession('audio_error');setStatus('ready','Giọng Sóng bị gián đoạn. Câu trả lời bằng chữ vẫn đầy đủ.')}
}
async function sendQuestion(raw,origin='text'){
 const text=String(raw||'').trim().slice(0,450);if(!text)return;
 closeVoice();clearTranscript();stopAudio();cancelRequest();
 showView('conversation');
 state.lastAudio=null;state.pendingInput=origin;ui.question.value='';ui.question.style.height='auto';
 addMessage('user',text);
 if(origin==='text'&&state.sessionArmed)disarmVoiceSession('user_switched_to_text');
 const turn=++state.turn,ctrl=new AbortController();state.request=ctrl;const t0=clock();
 setStatus('thinking','Sóng đang suy nghĩ...');
 const timer=setTimeout(()=>ctrl.abort(),30000);
 try{
  const res=await fetch('/api/turn',{method:'POST',credentials:'same-origin',signal:ctrl.signal,
   headers:{'content-type':'application/json'},body:JSON.stringify({text,locale:'vi-VN',history:state.history.slice(-4)})});
  const out=await res.json().catch(()=>({}));
  if(turn!==state.turn)return;
  if(!res.ok)throw Error(out.message||'Hiện lượt AI miễn phí đang bận. Bạn thử lại sau nhé.');
  if(typeof out.answer!=='string'||!out.answer.trim())throw Error('Sóng chưa có câu trả lời rõ ràng.');
  qa.llmMs=Math.round(clock()-t0);stamp('llm_visible',{ms:qa.llmMs});
  addMessage('assistant',out.answer);
  state.history=[...state.history,{role:'user',content:text},{role:'assistant',content:out.answer}].slice(-4);
  showContext(text);
  setStatus('ready','Sóng đã trả lời bằng chữ.');
  const speakWanted=origin==='voice'||state.settings.readText;
  if(speakWanted)void synthAndSpeak(out,turn);
  else if(state.sessionArmed)rearmVoiceAfterSpeech(turn);
 }catch(e){
  if(turn!==state.turn)return;captureError(e,'turn');disarmVoiceSession('llm_failure');
  const msg=e.name==='AbortError'?'Sóng đợi hơi lâu. Bạn thử lại nhé.':
    (e?.message||'Chưa kết nối được. Bạn có thể thử lại hoặc nhập chữ.');
  addMessage('assistant',msg);setStatus('error',msg);
 }finally{clearTimeout(timer);if(state.request===ctrl)state.request=null}
}
function wav16k(buffers,rate,bounds){
 const count=buffers.reduce((n,b)=>n+b.length,0);if(!count||count>rate*18)throw Error('INVALID_DURATION');
 const samples=new Float32Array(count);let at=0;for(const b of buffers){samples.set(b,at);at+=b.length}
 const crop=bounds||{start:0,end:count},source=samples.subarray(crop.start,crop.end);
 if(!source.length)throw Error('EMPTY_AUDIO');
 const length=Math.round(source.length*16000/rate);
 const out=new ArrayBuffer(44+length*2),v=new DataView(out);
 const tag=(at,s)=>{for(let i=0;i<s.length;i++)v.setUint8(at+i,s.charCodeAt(i))};
 tag(0,'RIFF');v.setUint32(4,36+length*2,true);tag(8,'WAVE');tag(12,'fmt ');
 v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
 v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
 tag(36,'data');v.setUint32(40,length*2,true);
 for(let i=0;i<length;i++){
  const x=i*rate/16000,j=Math.floor(x),fr=x-j;
  const value=(source[Math.min(j,source.length-1)]||0)*(1-fr)+(source[Math.min(j+1,source.length-1)]||0)*fr;
  v.setInt16(44+2*i,Math.round(Math.max(-1,Math.min(1,value))*32767),true);
 }
 return new Blob([out],{type:'audio/wav'});
}
async function endRecording(reason='MANUAL'){
 const v=state.voice;if(!v||v.done)return;
 v.done=true;state.voice=null;clearTimeout(v.timer);
 try{v.processor.disconnect();v.source.disconnect();v.sink.disconnect();v.stream.getTracks().forEach(t=>t.stop());await v.context.close()}catch{}
 stamp('endpoint',{reason,speechMs:Math.round(v.detector.speechMs)});
 qa.eouDelayMs=reason==='SILENCE_AFTER_SPEECH'?1600:null;
 if(!v.detector.heardSpeech||v.samples/v.rate<.45){disarmVoiceSession('no_speech');setStatus('ready','Sóng chưa nghe rõ tiếng. Bạn thử lại nhé.');return}
 if(tooShortToRecognize(v.detector.speechMs)){disarmVoiceSession('short_speech');setStatus('ready','Âm quá ngắn, Sóng khó nhận đúng chữ cái. Bạn thử nói cả câu nhé.');return}
 const start=clock();setStatus('transcribing','Sóng đang nhận giọng nói...');
 const ctrl=new AbortController();state.request=ctrl;const timer=setTimeout(()=>ctrl.abort(),14500);
 try{
  const b=wav16k(v.buffers,v.rate,speechBounds(v.detector,v.samples,v.rate));
  const res=await fetch('/api/transcribe',{method:'POST',credentials:'same-origin',signal:ctrl.signal,
    headers:{'content-type':'audio/wav','x-guide-locale':'vi-VN'},body:b});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.message||'Chưa nghe rõ, bạn thử lại nhé.');
  if(typeof data.text!=='string'||!data.text.trim())throw Error('Sóng chưa nhận ra lời nói.');
  qa.asrMs=Math.round(clock()-start);stamp('asr_ready',{ms:qa.asrMs});
  state.pendingText=data.text;ui.transcriptText.value=data.text;
  ui.transcript.hidden=false;showView('conversation');
  setStatus('confirming','Bạn kiểm tra nhanh lời Sóng đã nghe trước khi gửi.');
  ui.transcriptText.focus();
 }catch(e){captureError(e,'asr');disarmVoiceSession('asr_failure');setStatus('error',e.name==='AbortError'?'Nhận giọng nói quá lâu. Bạn thử lại nhé.':(e.message||'Chưa dùng được giọng nói. Bạn có thể nhập chữ.'))}
 finally{clearTimeout(timer);if(state.request===ctrl)state.request=null}
}
async function beginVoice(){
 if(state.voice){await endRecording('MANUAL');return}
 if(state.openingMic)return;
 state.openingMic=true;clearTranscript();stopAudio();cancelRequest();
 userGestureAudio();showView('conversation');
 if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext&&!window.webkitAudioContext){
  state.sessionArmed=false;state.openingMic=false;setStatus('error','Chưa dùng được giọng nói trên thiết bị này. Bạn có thể nhập chữ.');ui.question.focus();return;
 }
 const start=clock(),C=window.AudioContext||window.webkitAudioContext;
 let openingStream=null;
 try{
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
  openingStream=stream;
  const ctx=new C();if(ctx.state==='suspended')await ctx.resume();
  const source=ctx.createMediaStreamSource(stream),processor=ctx.createScriptProcessor(4096,1,1),sink=ctx.createGain();
  sink.gain.value=0;
  const v={stream,context:ctx,source,processor,sink,buffers:[],samples:0,rate:ctx.sampleRate,done:false,
    detector:makeEndpointDetector({sampleRate:ctx.sampleRate,minSpeechMs:220}),timer:null};
  state.voice=v;
  processor.onaudioprocess=e=>{
   if(state.voice!==v||v.done)return;
   const buf=new Float32Array(e.inputBuffer.getChannelData(0));
   if(v.samples+buf.length>v.rate*17.3)return;
   v.buffers.push(buf);v.samples+=buf.length;
   const event=v.detector.feed(buf);ui.mic.style.setProperty('--level',String(event.level||0));
   if(event.done)queueMicrotask(()=>{if(state.voice===v)void endRecording(event.reason)});
  };
  source.connect(processor);processor.connect(sink);sink.connect(ctx.destination);
  v.timer=setTimeout(()=>{if(state.voice===v)void endRecording('MAX_DURATION')},16900);
  qa.startMicMs=Math.round(clock()-start);stamp('mic_active',{ms:qa.startMicMs});
  setStatus('listening','Sóng đang nghe... Chạm micro lần nữa để kết thúc.');
  openingStream=null;
 }catch(e){
  state.sessionArmed=false;captureError(e,'get_user_media');openingStream?.getTracks()?.forEach(t=>t.stop());closeVoice();
  setStatus('error',e?.name==='NotAllowedError'?'Micro chưa được cấp quyền. Bạn vẫn có thể nhập chữ.':'Chưa dùng được giọng nói trên thiết bị này. Bạn có thể nhập chữ.');
  ui.question.focus();
 }finally{state.openingMic=false}
}
$('voice-start').addEventListener('click',()=>{state.sessionArmed=true;stamp('voice_session_start');void beginVoice()});
ui.mic.addEventListener('click',()=>{
 if(state.voice)void endRecording('MANUAL');else {state.sessionArmed=true;stamp('voice_session_start');void beginVoice();}
});
$('composer').addEventListener('submit',e=>{e.preventDefault();if(state.settings.readText)userGestureAudio();void sendQuestion(ui.question.value,'text')});
ui.question.addEventListener('input',()=>{
 ui.question.style.height='auto';ui.question.style.height=Math.min(ui.question.scrollHeight,106)+'px';
});
ui.question.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('composer').requestSubmit()}});
document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{ui.question.value=b.dataset.prompt;void sendQuestion(b.dataset.prompt,'text')}));
document.querySelector('[data-nearme]').addEventListener('click',()=>{
 ui.question.value='Tớ đang ở khu vực ';showView('conversation');
 setStatus('ready','Chưa kết nối vị trí tự động. Bạn nhập khu vực hoặc khách sạn để Sóng gợi ý nhé.');
 ui.question.focus();
});
$('transcript-confirm').addEventListener('click',()=>{
 const t=ui.transcriptText.value.trim();if(!t){setStatus('ready','Bạn sửa lại câu cần hỏi nhé.');return}
 userGestureAudio();void sendQuestion(t,'voice');
});
$('transcript-repeat').addEventListener('click',beginVoice);
$('transcript-close').addEventListener('click',()=>{disarmVoiceSession('cancel_confirmation');clearTranscript();setStatus('ready')});
$('stop-audio').addEventListener('click',()=>{disarmVoiceSession('stop_audio');stopAudio();setStatus('ready','Đã dừng tiếng. Nội dung chữ vẫn còn.')});
$('back-welcome').addEventListener('click',()=>{disarmVoiceSession('back_home');stopAudio();showView('welcome');setStatus('ready')});
$('close-result').addEventListener('click',()=>{ui.result.hidden=true;ui.conversation.dataset.hasResult='false';ui.resultOpen=false});
$('end-voice-session').addEventListener('click',()=>{
 disarmVoiceSession('user_stop');stopAudio();clearTranscript();setStatus('ready','Đã dừng phiên giọng nói. Bạn có thể hỏi bằng chữ.');
});
const dialog=$('settings-dialog'),settingsBtn=$('settings');
function settings(open){dialog.hidden=!open;settingsBtn.setAttribute('aria-expanded',String(open));if(open)$('dark-setting').focus();else settingsBtn.focus()}
settingsBtn.addEventListener('click',()=>settings(dialog.hidden));
$('close-settings').addEventListener('click',()=>settings(false));
$('settings-done').addEventListener('click',()=>settings(false));
$('qa-copy').addEventListener('click',copyDiagnostics);
dialog.addEventListener('click',e=>{if(e.target===dialog)settings(false)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dialog.hidden)settings(false)});
$('dark-setting').addEventListener('change',e=>{document.body.dataset.theme=e.target.checked?'dark':'light';document.querySelector('meta[name="theme-color"]').content=e.target.checked?'#062F3A':'#F6F3EA'});
$('autoplay-setting').addEventListener('change',e=>{state.settings.readText=e.target.checked;if(e.target.checked)userGestureAudio()});
$('motion-setting').addEventListener('change',e=>{state.settings.reduceMotion=e.target.checked;document.body.dataset.motion=e.target.checked?'reduced':'normal'});
document.addEventListener('visibilitychange',()=>{
 if(document.hidden){
  if(state.sessionArmed){state.sessionArmed=false;$('end-voice-session').hidden=true;stamp('voice_session_paused',{reason:'background'});}
  if(state.voice){closeVoice();setStatus('ready','Đã dừng nghe khi rời Safari. Chạm micro để tiếp tục.')}
  if(state.playSource){stopAudio();setStatus('ready','Safari đã ngắt tiếng khi chuyển ứng dụng. Chạm Nghe lại nếu cần.')}
 }
});
if(window.visualViewport){const adjust=()=>{
 const viewport=window.visualViewport;
 const lift=Math.max(0,window.innerHeight-viewport.height-viewport.offsetTop);
 document.documentElement.style.setProperty('--keyboard-lift',Math.round(lift)+'px');
 };window.visualViewport.addEventListener('resize',adjust);window.visualViewport.addEventListener('scroll',adjust);adjust();}
setStatus('idle');showView('welcome');