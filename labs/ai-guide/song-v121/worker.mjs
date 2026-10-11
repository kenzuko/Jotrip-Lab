import {speechText,grant,speak} from './tts-stage.mjs';
import {serveWavWithRanges} from './audio-range.mjs';
import {splitVoice} from './voice-chunks.mjs';
import {looksLikeBackgroundAudio} from './asr-artifact.mjs';
import {judgeAsrTranscript} from './asr-quality.mjs';
// V0.10 offline stage candidate; Workers AI Free only, no paid fallback or tunnel.
const ORIGIN='https://ai.openphuquoc.com'; // Browser origin verified from req.url on either stage or release
const MODEL='@cf/google/gemma-4-26b-a4b-it';
const ACCEPT=new Set(['/guide-legacy','/guide-legacy.html','/song-v1','/song-v1.html','/song-v1.js','/song-v1.css','/song-approved.webp','/song-qa-before-mobile.png','/song-qa-before-desktop.png','/song-qa-after-mobile.png','/song-qa-after-conversation.png','/song-qa-after-result.png','/song-qa-after-desktop.png','/song-qa-after-mobile-dark.png','/song-qa-after-mobile-conversation.png','/song-qa-after-mobile-result.png','/song-qa-after-desktop-result.png','/', '/voice-lab','/voice-lab.html','/v12-audio','/v12-audio.html','/v12-audio.mjs','/assets/v12_proof_chunk_1.wav','/assets/v12_proof_chunk_2.wav','/assets/v12_proof_chunk_3.wav','/assets/v12_adam_speed086_bright_ab.wav','/v12-launch.css','/v12-turn-engine.mjs','/v12-persistent-player.mjs','/voice-ab','/voice-ab.html','/voice-ab.js','/voice-ab.css','/assets/v113_adam_speed100.wav','/assets/v113_adam_speed086.wav','/voice-lab-fix.js','/asr-artifact.mjs','/wav-join.mjs','/v112-ui.css','/v112-conversation.css','/assets/v11_sentence1_step16.wav','/assets/v11_sentence1_step12.wav','/assets/v11_sentence1_step8.wav','/assets/v11_sentence2_step16.wav','/assets/v11_sentence2_step12.wav','/assets/v11_sentence2_step8.wav', '/style.css','/app.js','/voice-activity.mjs','/speech-crop.mjs','/speech-quality.mjs','/api/health','/api/turn','/api/transcribe','/api/speak','/assets/adam-south-test.wav','/assets/openpq-eye.png','/assets/guide-welcome.jpeg','/assets/guide-listening.jpeg','/assets/guide-thinking.jpeg','/assets/guide-pointing.jpeg','/assets/guide-speaking.jpeg','/assets/sunset-town.jpg','/assets/hon-thom.jpg','/assets/dinh-cau.jpg']);
const LANG={'vi-VN':'tiếng Việt có dấu','en-US':'English','ko-KR':'한국어','ru-RU':'русском языке'};
const SYSTEM='Bạn là hướng dẫn viên Open Phu Quoc, thân thiện và hiểu đảo. Trả lời bằng ngôn ngữ khách đang dùng, tối đa 2 câu và khoảng 35-45 từ cho câu hỏi thường. Tự nhiên như đang trò chuyện, câu ngắn dễ nghe thành tiếng, không đọc những thuật ngữ kỹ thuật. Khách yêu cầu giải thích kỹ mới mở rộng. Đừng nhắc lại câu hỏi hay nhồi câu cảnh báo nếu không cần. Trả lời câu hỏi trước rồi chỉ hỏi lại khi thực sự cần. Đừng dùng danh sách, markdown hay quảng cáo. Kiến thức nền chắc chắn: Hòn Thơm và cáp treo ở phía Nam đảo, ga cáp treo xuất phát khu An Thới; Dinh Cậu ở Dương Đông; Vinpearl Safari và VinWonders ở phía Bắc đảo. Nếu không có dữ liệu đã xác minh, không bịa giá vé, giờ mở cửa, giờ chạy cáp treo, biển có an toàn không, thời tiết hôm nay/ngày mai, vé còn hay đường đi chính xác. Không tự nhận đã đặt vé hoặc có dữ liệu live. Khi không rõ địa danh hoặc ý định hãy hỏi lại ngắn gọn. Khi khách đã nói muốn đi một nơi, đừng hỏi lại có muốn đi nơi đó không. Phải trả lời trực tiếp bằng một thông tin đã biết, gợi ý bước đi hữu ích và chỉ hỏi một câu về chi tiết thật sự còn thiếu. Nếu khách hỏi ngày mai có nên đi không thì nói chưa có nguồn thời tiết và vận hành ngày mai để khẳng định; không bịa thời gian, giá, hãng xe hay việc đã kiểm tra nguồn trực tiếp.';
const json=(data,status=200,more={})=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff',...more}});
async function answer(req,env){
 if(req.headers.get('origin')!==new URL(req.url).origin)return json({error:'WRONG_ORIGIN'},403);
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return json({error:'JSON_ONLY'},415);
 const bytes=Number(req.headers.get('content-length')||0);
 if(bytes>4500)return json({error:'BODY_TOO_LARGE'},413);
 let body;try{const text=await req.text();if(text.length>4500)return json({error:'BODY_TOO_LARGE'},413);body=JSON.parse(text)}catch{return json({error:'INVALID_JSON'},400)}
 const locale=body?.locale||'vi-VN',text=String(body?.text||'').trim();
 if(!LANG[locale]||!text||text.length>450)return json({error:'INVALID_INPUT'},400);
 const client=req.headers.get('cf-connecting-ip')||'unknown';
 try{
  const local=await env.AI_PER_CLIENT.limit({key:client});
  if(!local.success)return json({message:'Guide đang giới hạn lượt hỏi miễn phí. Bạn chờ một phút rồi thử lại nhé.'},429);
  const shared=await env.AI_GLOBAL.limit({key:'openpq-ai-guide-free'});
  if(!shared.success)return json({message:'Guide đang nhận nhiều câu hỏi. Bạn thử lại sau một phút nhé.'},429);
 }catch{return json({message:'Chưa thể xác nhận hạn mức an toàn; vui lòng thử lại sau.'},503)}
 const prior=Array.isArray(body?.history)?body.history.slice(-4).filter(x=>(x?.role==='user'||x?.role==='assistant')&&typeof x.content==='string'&&x.content.length<=450).map(x=>({role:x.role,content:x.content})):[];
 const messages=[{role:'system',content:SYSTEM+' Chỉ trả lời bằng '+LANG[locale]+'.'},...prior,{role:'user',content:text}];
 try{
  const v=await env.AI.run(MODEL,{messages,max_completion_tokens:180,chat_template_kwargs:{enable_thinking:false},temperature:0.3,stream:false},{rejectIfBusy:true});
  const response=String(v?.choices?.[0]?.message?.content||v?.response||'').trim();
  if(!response)return json({message:'Guide chưa có câu trả lời. Bạn thử lại nhé.'},503);
  const answerText=response.slice(0,650);
  const ip=req.headers.get('cf-connecting-ip');
  // V12: one verified, per-answer signed audio permit instead of 1-3 requests.
  // VPS synthesizes a single continuous WAV so later turns do not waste client quotas.
  // Keep speechText's sentence-aware cap. The full answer remains visible in text.
  const chunks=locale==='vi-VN'?[speechText(answerText)].filter(Boolean):[];
  const speakSegments=await Promise.all(chunks.map(async text=>({
    text,permit:await grant(env.TTS_SIGN_KEY,text,ip).catch(()=>'')
  })));
  const allowed=speakSegments.filter(part=>part.permit);
  return json({answer:answerText,speakText:allowed[0]?.text||'',speakPermit:allowed[0]?.permit||'',speakSegments:allowed,
    model:'cloudflare-free-gemma-4-26b',verifiedLive:false});
 }catch(e){
  const msg=String(e?.message||e);
  const exhausted=/limit|quota|neuron|429|out of capacity|3040/i.test(msg);
  return json({message:exhausted?'Hôm nay lượt AI miễn phí đang bận hoặc đã hết. Bạn thử lại sau nhé.':'Guide tạm thời chưa trả lời được. Bạn thử lại sau nhé.',code:exhausted?'FREE_LIMIT':'AI_UNAVAILABLE'},503);
 }
}
async function transcribe(req,env){
 if(req.headers.get('origin')!==new URL(req.url).origin)return json({error:'WRONG_ORIGIN'},403);
 if(req.headers.get('content-type')?.split(';')[0]!=='audio/wav')return json({error:'WAV_ONLY'},415);
 const declared=Number(req.headers.get('content-length')||0);
 if(declared>620000)return json({error:'AUDIO_TOO_LONG'},413);
 let audio;try{audio=new Uint8Array(await req.arrayBuffer())}catch{return json({error:'INVALID_AUDIO'},400)}
 if(audio.length<15044||audio.length>620000)return json({error:'INVALID_AUDIO_LENGTH'},413);
 const view=new DataView(audio.buffer,audio.byteOffset,audio.byteLength);
 const fourcc=(at)=>String.fromCharCode(...audio.subarray(at,at+4));
 if(fourcc(0)!=='RIFF'||fourcc(8)!=='WAVE'||fourcc(12)!=='fmt '||view.getUint16(20,true)!==1||view.getUint16(22,true)!==1||view.getUint32(24,true)!==16000||view.getUint16(34,true)!==16||fourcc(36)!=='data')return json({error:'INVALID_WAV_PCM16_16K_MONO'},400);
 const declaredPayload=view.getUint32(40,true);if(declaredPayload+44!==audio.length)return json({error:'INVALID_WAV_LENGTH'},400);
 const locale=req.headers.get('x-guide-locale')||'vi-VN';
 const language=({'vi-VN':'vi','en-US':'en','ko-KR':'ko','ru-RU':'ru'})[locale];
 if(!language)return json({error:'INVALID_LOCALE'},400);
 const key=req.headers.get('cf-connecting-ip')||'unknown';
 try{
  const [user,globalLimit]=await Promise.all([env.ASR_PER_CLIENT.limit({key}),env.ASR_GLOBAL.limit({key:'openpq-ai-guide-asr-free'})]);
  if(!user.success||!globalLimit.success)return json({error:'VOICE_RATE_LIMIT',message:'Bộ nghe đang bận. Bạn chờ một phút và thử lại nhé.'},429);
 }catch{return json({error:'RATE_LIMIT_UNAVAILABLE'},503)}
 const chunks=[];
 for(let at=0;at<audio.length;at+=12000)chunks.push(String.fromCharCode(...audio.subarray(at,at+12000)));
 const payload=btoa(chunks.join(''));
 try{
  const out=await env.AI.run('@cf/openai/whisper-large-v3-turbo',{audio:payload,task:'transcribe',language,vad_filter:true,condition_on_previous_text:false,no_speech_threshold:0.48,hallucination_silence_threshold:1,compression_ratio_threshold:2.2,initial_prompt:language==='vi'&&audio.length>=44+32000*3.5?'Những tên riêng có thể xuất hiện: Phú Quốc, Hòn Thơm, An Thới, Dinh Cậu, Dương Đông, Rạch Vẹm, Bãi Sao, Bãi Khem. Chỉ chép lời đã nghe, không đoán thêm.':undefined});
  const text=String(out?.text||'').trim();
  if(!text)return json({error:'NO_SPEECH',message:'Chưa nghe rõ. Bạn thử nói lại nhé.',text:''},422);
  if(looksLikeBackgroundAudio(text,locale))return json({error:'POSSIBLE_BACKGROUND_AUDIO',
    message:'Micro có thể đã nghe tiếng video hoặc tiếng nền. Bạn nói lại nhé.',text:''},422);
  const plausible=judgeAsrTranscript(text,{durationMs:(audio.length-44)/32,locale});
  if(!plausible.accept)return json({error:'LOW_CONFIDENCE_TRANSCRIPT',message:'Guide nghe được tiếng nhưng bản nhận dạng có vẻ sai. Cậu nói lại thành một câu rõ hơn nhé.',text:''},422);
  const segments=Array.isArray(out?.segments)?out.segments:[];
  if(segments.length&&segments.every(s=>Number(s.no_speech_prob)>.75))return json({
    error:'NO_SPEECH',message:'Tớ chưa nghe rõ tiếng nói. Bạn thử lại nhé.',text:''},422);
  return json({text:text.slice(0,450),source:'cloudflare-free-whisper-large-v3-turbo'});
 }catch(e){
  const msg=String(e?.message||e);
  return json({error:/limit|quota|neuron|429/i.test(msg)?'FREE_LIMIT':'ASR_UNAVAILABLE',message:'Chưa nhận được giọng nói. Vui lòng thử lại.'},503);
 }
}
export default {async fetch(request,env){
 const u=new URL(request.url);
 if(!(u.hostname==='ai.openphuquoc.com')||!ACCEPT.has(u.pathname))return new Response('Not found',{status:404});
 if(!['GET','HEAD','POST'].includes(request.method))return new Response('Method not allowed',{status:405});
 if(u.pathname==='/api/turn'&&request.method==='POST')return answer(request,env);
 if(u.pathname==='/api/transcribe'&&request.method==='POST')return transcribe(request,env);
 if(u.pathname==='/api/speak'&&request.method==='POST')return speak(request,env);

 if(request.method==='POST'){
  if(u.pathname!=='/api/transcribe'||request.headers.get('origin')!==ORIGIN)return json({error:'WRONG_ORIGIN'},403);
  if(Number(request.headers.get('content-length')||0)>405000)return json({error:'BODY_TOO_LARGE'},413);
 }
 if(u.pathname==='/api/health'&&request.method==='GET')return json({ok:true,mode:'VOICE_FIRST_LAB',modelEngine:'cloudflare-workers-ai-free',modelConfigured:Boolean(env.AI),model:'gemma-4-26b-a4b-it',voice:'VIE-NEU-CPU-PRIVATE',ttsConfigured:Boolean(env.TTS_SIGN_KEY&&env.TTS_UPSTREAM_TOKEN&&env.TTS_PRIVATE_ORIGIN),asrConfigured:Boolean(env.AI&&env.ASR_PER_CLIENT&&env.ASR_GLOBAL),liveSourceReady:false,productionApproved:false,paidFallback:false});
 try{
  if(u.pathname.endsWith('.wav')&&['GET','HEAD'].includes(request.method))return await serveWavWithRanges(request,env);
  return await env.ASSETS.fetch(request)
 }catch{return new Response('Static assets unavailable',{status:503})}
}};