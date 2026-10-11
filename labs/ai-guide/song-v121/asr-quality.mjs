// ASR sanity checks, not a substitute for understanding speech.
// Explicitly rejects impossible-length transcripts from short recordings.
export function judgeAsrTranscript(raw,{durationMs=0,locale='vi-VN'}={}){
 const text=String(raw||'').trim().replace(/\s+/gu,' ');
 if(!text)return {accept:false,reason:'EMPTY'};
 if(text.length>450)return {accept:false,reason:'TOO_LONG'};
 const words=text.split(/\s+/u).filter(Boolean).length;
 if(locale==='vi-VN'){
   if(durationMs>0&&durationMs<1050&&words>=11)return {accept:false,reason:'HALLUCINATED_LONG_TEXT'};
   if(durationMs>=1050&&durationMs<1700&&words>=15)return {accept:false,reason:'HALLUCINATED_LONG_TEXT'};
   if(durationMs>=1700&&durationMs<2600&&words>=22)return {accept:false,reason:'HALLUCINATED_LONG_TEXT'};
 }
 return {accept:true,reason:'OK',words};
}