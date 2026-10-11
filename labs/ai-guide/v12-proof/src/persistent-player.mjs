/** Browser-only audio proof. A single persistent media element owns all turns.
 * Every playback completion is a browser proxy, never proof a human heard sound.
 * No autoplay bypasses or microphone access.
 */
export class PersistentMediaPlayer {
 constructor({audio,onEvent=()=>{},timeoutMs=30000}={}){
  if(!audio||typeof audio.play!=='function'||typeof audio.pause!=='function')throw Error('AUDIO_REQUIRED');
  this.audio=audio;this.onEvent=onEvent;this.timeoutMs=timeoutMs;
  this.serial=0;this.active=null;
  audio.preload='auto';audio.controls=false;audio.preservesPitch=true;
 }
 stop(){
  this.serial++;
  const pending=this.active;this.active=null;
  try{this.audio.pause()}catch{}
  if(pending)pending.settle(false,'CANCELLED');
 }
 async play(url,{signal,turnId,segment,generation}={}){
  if(signal?.aborted)return false;
  this.stop();
  const token=this.serial;
  const audio=this.audio;
  return new Promise(resolve=>{
    let done=false;
    const emit=(event,detail)=>this.onEvent({event,turnId,segment,generation,detail});
    const cleanup=()=>{
      clearTimeout(timer);
      signal?.removeEventListener('abort',aborted);
      audio.removeEventListener('playing',playing);
      audio.removeEventListener('ended',ended);
      audio.removeEventListener('error',errored);
      audio.removeEventListener('stalled',stalled);
    };
    const settle=(ok,reason)=>{
      if(done)return;
      done=true;cleanup();
      if(this.active?.token===token)this.active=null;
      if(!ok&&this.serial===token){try{audio.pause()}catch{}}
      emit(ok?'sink_ended':'sink_not_completed',reason);
      resolve(ok);
    };
    const playing=()=>{if(this.serial===token)emit('sink_playing','browser_event')};
    const ended=()=>{if(this.serial===token)settle(true,'ended_event')};
    const errored=()=>settle(false,'media_error_'+(audio.error?.code||'unknown'));
    const stalled=()=>emit('sink_stalled','network');
    const aborted=()=>settle(false,'ABORT');
    const timer=setTimeout(()=>settle(false,'PLAYBACK_TIMEOUT'),this.timeoutMs);
    this.active={token,settle};
    audio.addEventListener('playing',playing);
    audio.addEventListener('ended',ended);
    audio.addEventListener('error',errored);
    audio.addEventListener('stalled',stalled);
    signal?.addEventListener('abort',aborted,{once:true});
    try{
      audio.src=url;audio.playbackRate=1;audio.preservesPitch=true;
      emit('play_requested','user_gesture_required_by_browser');
      const result=audio.play();
      Promise.resolve(result).then(()=>{if(this.serial===token)emit('play_promise_resolved','not_audible_proof')})
        .catch(e=>settle(false,'play_rejected_'+(e?.name||'unknown')));
    }catch(e){settle(false,'play_exception_'+(e?.name||'unknown'))}
  });
 }
 dispose(){this.stop();try{this.audio.removeAttribute('src')}catch{}}
}