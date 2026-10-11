export const STATES=Object.freeze({
  IDLE:'idle', LISTENING:'listening', CONFIRM:'confirm_pending',
  THINKING:'thinking', BUFFERING:'buffering', SPEAKING:'speaking',
  BLOCKED:'audio_blocked', READY:'ready', ERROR:'error'
});
const randomId=()=>globalThis.crypto?.randomUUID?.()||('session-'+Math.random().toString(36).slice(2));
const requireText=(s)=>typeof s==='string'&&s.trim().length>0&&s.length<=450;

/** One session, ordered turns; no Cloudflare, model, or credentials are used here.
 * Not a production authentication or billing mechanism.
 */
export class TurnEngine {
  constructor({synthesizer,player,onEvent=()=>{},sessionId=randomId(),requireConfirmation=true}={}){
    if(typeof synthesizer!=='function'||!player?.play||!player?.stop) throw Error('MISSING_ADAPTER');
    this.synthesizer=synthesizer;this.player=player;this.onEvent=onEvent;
    this.sessionId=sessionId;this.requireConfirmation=requireConfirmation;
    this.turnId=0;this.generation=0;this.state=STATES.IDLE;
    this.current=null;this.history=[];this.disposed=false;
  }
  emit(event,fields={}){
    this.onEvent({event,state:this.state,sessionId:this.sessionId,turnId:this.turnId,...fields});
  }
  setState(state,fields={}){this.state=state;this.emit('state',fields)}
  cancel(reason='user'){
    if(this.current){this.current.abort.abort();this.current.status='cancelled';}
    this.generation++;this.player.stop();
    this.current=null;this.setState(STATES.READY,{reason});
  }
  listen(){
    if(this.disposed)throw Error('DISPOSED');
    this.cancel('next_turn');
    this.setState(STATES.LISTENING);
  }
  /** No speculative STT output may be submitted unless the policy permits it.
   * Confirmation is the only accepted default.
   */
  receiveTranscript(text,{confirmed=false,confidence=null,background=false}={}){
    if(this.disposed)throw Error('DISPOSED');
    if(!requireText(text)||background){this.setState(STATES.ERROR,{reason:'INVALID_TRANSCRIPT'});return null}
    this.cancel('new_transcript');
    const abort=new AbortController();
    const turn={id:++this.turnId,generation:++this.generation,abort,text:text.trim(),
      confirmed:false,played:[],allSegments:[],status:'pending',answer:null,created:Date.now()};
    this.current=turn;
    if(this.requireConfirmation&&!confirmed){
      this.setState(STATES.CONFIRM,{reason:'EXPLICIT_CONFIRMATION_REQUIRED'});
      return turn.id;
    }
    if(confirmed){turn.confirmed=true;this.setState(STATES.THINKING);return turn.id;}
    // Even when opt-in is eventually allowed, keep an explicit policy flag.
    turn.confirmed=true;this.setState(STATES.THINKING);return turn.id;
  }
  confirm(turnId,editedText=null){
    const t=this.current;
    if(!t||t.id!==turnId||this.state!==STATES.CONFIRM)return false;
    if(editedText!==null){
      if(!requireText(editedText))return false;
      t.text=editedText.trim();
    }
    t.confirmed=true;this.setState(STATES.THINKING);return true;
  }
  active(t){return !this.disposed&&this.current===t&&t.generation===this.generation&&!t.abort.signal.aborted}
  async run(turnId){
    const turn=this.current;
    if(!turn||turn.id!==turnId||!turn.confirmed||this.state!==STATES.THINKING)return {ok:false,reason:'NOT_CONFIRMED'};
    try{
      const result=await this.synthesizer({turnId,sessionId:this.sessionId,text:turn.text,
        signal:turn.abort.signal,history:this.history.slice(-4)});
      if(!this.active(turn))return {ok:false,reason:'STALE'};
      if(!result||typeof result.answer!=='string'||!Array.isArray(result.segments)
       ||result.segments.length<1||result.segments.length>6
       ||result.segments.some(s=>typeof s.url!=='string'||!s.url.startsWith('https://')))
        throw Error('INVALID_SYNTHESIZER_RESULT');
      turn.answer=result.answer;
      turn.allSegments=result.segments;
      this.setState(STATES.BUFFERING,{segments:result.segments.length});
      for(let index=0;index<result.segments.length;index++){
        if(!this.active(turn))return {ok:false,reason:'STALE'};
        this.setState(STATES.SPEAKING,{segment:index+1});
        const played=await this.player.play(result.segments[index].url,{signal:turn.abort.signal,
          turnId, generation:turn.generation,segment:index+1});
        if(!this.active(turn))return {ok:false,reason:'STALE'};
        if(played!==true){this.setState(STATES.BLOCKED,{segment:index+1,reason:'PLAYBACK_NOT_CONFIRMED'});return {ok:false,reason:'AUDIO_BLOCKED'};}
        turn.played.push(index);
        this.emit('segment_ack',{segment:index+1,playedCount:turn.played.length});
      }
      if(!this.active(turn))return {ok:false,reason:'STALE'};
      // The local player reports completion, not proof of actual audible output.
      this.history.push({role:'user',content:turn.text},{role:'assistant',content:turn.answer});
      this.history=this.history.slice(-8);
      turn.status='played_proxy';this.setState(STATES.READY,{playedCount:turn.played.length});
      return {ok:true,playedCount:turn.played.length,completion:'player_ended_proxy'};
    }catch(error){
      if(!this.active(turn))return {ok:false,reason:'STALE'};
      this.setState(STATES.ERROR,{reason:error?.name==='AbortError'?'CANCELLED':'PIPELINE_ERROR'});
      return {ok:false,reason:'PIPELINE_ERROR'};
    }
  }
  resetAudio(){
    this.player.stop();
    if(this.state===STATES.BLOCKED)this.setState(STATES.READY,{reason:'MANUAL_RECOVERY'});
  }
  dispose(){this.cancel('dispose');this.disposed=true;this.state=STATES.IDLE}
}