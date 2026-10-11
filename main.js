import {Application, Asset, Entity, FILLMODE_FILL_WINDOW, RESOLUTION_AUTO} from 'playcanvas';

// LivingPQ R20: isolated playable-input test. All scene geometry originates in
// the R17G SINGLE-photo inferred SOG, not multi-view capture or surveyed terrain.
const $ = id => document.getElementById(id);
const stage = $('splat-stage'), stateText = $('state'), badge=$('gate'),
  meter=$('meters'), status=$('status'), fpsEl=$('fps'),trace=$('trace');
const input={held:new Set(),joyX:0,joyY:0,lookActive:false,lookPointer:null,oldX:0,oldY:0,keys:0,lookEvents:0,movingFrames:0,stoppedFrames:0,touchEvents:0};
const player={x:0,y:0,z:0,yaw:0,pitch:0,distance:0,moving:false,maxDisplacement:0,positionSamples:[{x:0,z:0,t:0}]};
const LIMIT=2.0, SPEED=0.68, LOOK_FACTOR=0.0031;
let app=null,asset=null,cam=null,model=null,device=null,ready=false,error=null,frameCount=0;
let lastFrame=performance.now(), fpsTime=performance.now(),fpsFrames=0,fps=0;
const failures=[];
function recordPoint() {
 const path=player.positionSamples;
 const prev=path[path.length-1];
 if(Math.hypot(prev.x-player.x,prev.z-player.z)>.055) {
   path.push({x:+player.x.toFixed(3),z:+player.z.toFixed(3),t:+(performance.now()/1000).toFixed(2)});
   if(path.length>360)path.shift();
 }
}
function cameraSync(){
 if(!cam)return;
 cam.setPosition(player.x,player.y,player.z);
 // This explicitly uses the player heading, unlike R17G's always-on lookAt().
 cam.setEulerAngles(player.pitch*180/Math.PI, player.yaw*180/Math.PI, 0);
}
function disocclusion(){
 const d=Math.hypot(player.x,player.z), a=Math.abs(player.yaw)*180/Math.PI;
 if(d>=.8||a>=45)return 'SOURCE FAIL ZONE: unseen surfaces likely';
 if(d>.25||a>18)return 'PARALLAX RISK: single-photo missing data';
 return 'SOURCE VIEW CONE ONLY: still NOT a real scan';
}
function drawTrace(){
 const ctx=trace.getContext('2d'),w=trace.width,h=trace.height,scale=26;
 ctx.clearRect(0,0,w,h);
 ctx.fillStyle='#10232cca';ctx.fillRect(0,0,w,h);
 ctx.strokeStyle='#adc7d955';ctx.lineWidth=1;ctx.setLineDash([4,3]);
 ctx.strokeRect(w/2-LIMIT*scale,h/2-LIMIT*scale,2*LIMIT*scale,2*LIMIT*scale);ctx.setLineDash([]);
 ctx.strokeStyle='#ecbd78';ctx.lineWidth=2;ctx.beginPath();
 player.positionSamples.forEach((p,i)=>{const X=w/2+p.x*scale,Y=h/2+p.z*scale;if(!i)ctx.moveTo(X,Y);else ctx.lineTo(X,Y);});ctx.stroke();
 ctx.fillStyle='#95e5d3';ctx.beginPath();ctx.arc(w/2+player.x*scale,h/2+player.z*scale,4,0,Math.PI*2);ctx.fill();
 const a=player.yaw;ctx.strokeStyle='#95e5d3';ctx.lineWidth=2;ctx.beginPath();
 ctx.moveTo(w/2+player.x*scale,h/2+player.z*scale);
 ctx.lineTo(w/2+player.x*scale-Math.sin(a)*16,h/2+player.z*scale-Math.cos(a)*16);ctx.stroke();
}
function renderHUD(){
 const displacement=Math.hypot(player.x,player.z);
 badge.textContent=disocclusion();badge.dataset.state=displacement>=.8||Math.abs(player.yaw)>Math.PI/4?'fail':displacement>.25?'warn':'caution';
 meter.textContent='x '+player.x.toFixed(2)+' m  |  z '+player.z.toFixed(2)+' m  |  yaw '+(player.yaw*180/Math.PI).toFixed(0)+'°';
 stateText.textContent=(player.moving?'MOVING':'STOPPED')+' · '+player.distance.toFixed(2)+' m walked · '+(input.lookEvents)+' look updates';
 fpsEl.textContent=fps?fps+' fps browser sample':'fps collecting';
 drawTrace();
}
function exposeState(){
 return {
  release:'R20_LOCAL_ONLY_NO_DEPLOY',
  ready, error, webgl:!!device, asset:asset?.loaded||false, frameCount,
  input:{keys:input.keys,lookEvents:input.lookEvents,movingFrames:input.movingFrames,stoppedFrames:input.stoppedFrames,touchEvents:input.touchEvents},
  x:player.x,y:player.y,z:player.z,yawDeg:player.yaw*180/Math.PI,pitchDeg:player.pitch*180/Math.PI,
  walkedDistance:player.distance,maxDisplacement:player.maxDisplacement,moving:player.moving,
  samples:player.positionSamples.length,path:player.positionSamples.slice(),
  fpsBrowser:fps, visualGate:'HOLD_SINGLE_IMAGE_DISOCCLUSION_AND_EMBEDDED_PEOPLE',
  disocclusion:disocclusion(),boundsMeters:LIMIT,
  ground:'SEPARATE_FLAT_BOUNDED_NAVIGATION_PROXY_NOT_SURVEYED_COLLISION',
  source:'R17G_SINGLE_PHOTO_INFERRED_GAUSSIAN_SOG_221184_POINTS',
  noAnimatedPeople:true,staticPeopleAreInPhoto:true,realIPhoneFPS:'UNTESTED',
  issues:failures.slice()
 };
}
function reset(){
 player.x=0;player.z=0;player.yaw=0;player.pitch=0;player.distance=0;
 player.maxDisplacement=0;player.moving=false;player.positionSamples=[{x:0,z:0,t:0}];
 input.held.clear();input.joyX=0;input.joyY=0;cameraSync();renderHUD();
}
window.R20={state:exposeState,reset, __testSafePose:(x,z,yaw=0)=>{
 // Only a deterministic QA helper. It is NOT counted as a user-input walk.
 player.x=Math.max(-LIMIT,Math.min(LIMIT,x));
 player.z=Math.max(-LIMIT,Math.min(LIMIT,z));
 player.yaw=yaw;cameraSync();recordPoint();renderHUD();
}};
document.querySelector('#reset').addEventListener('click',reset);
const keymap=new Set(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright']);
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(keymap.has(k)){e.preventDefault();input.held.add(k);input.keys++;}});
window.addEventListener('keyup',e=>input.held.delete(e.key.toLowerCase()));
window.addEventListener('blur',()=>{input.held.clear();input.joyX=0;input.joyY=0;input.lookActive=false;});
stage.addEventListener('pointerdown',e=>{
 if(e.pointerType==='mouse'&&e.button!==0)return;
 input.lookActive=true;input.lookPointer=e.pointerId;input.oldX=e.clientX;input.oldY=e.clientY;
 stage.setPointerCapture(e.pointerId);if(e.pointerType==='touch')input.touchEvents++;
});
stage.addEventListener('pointerup',e=>{if(e.pointerId===input.lookPointer)input.lookActive=false;});
stage.addEventListener('pointercancel',e=>{if(e.pointerId===input.lookPointer)input.lookActive=false;});
stage.addEventListener('pointermove',e=>{
 if(!input.lookActive||e.pointerId!==input.lookPointer)return;
 const dx=e.clientX-input.oldX,dy=e.clientY-input.oldY;
 input.oldX=e.clientX;input.oldY=e.clientY;
 player.yaw-=dx*LOOK_FACTOR;player.pitch=Math.max(-.7,Math.min(.7,player.pitch-dy*LOOK_FACTOR));
 input.lookEvents++;cameraSync();
});
const joy=$('joystick'), knob=$('knob');let activeJoy=null;
function setJoy(e){
 const box=joy.getBoundingClientRect();
 const x=(e.clientX-(box.left+box.width/2))/(box.width*.38), y=(e.clientY-(box.top+box.height/2))/(box.height*.38);
 const len=Math.max(1,Math.hypot(x,y)),fx=x/len,fy=y/len;
 input.joyX=fx;input.joyY=-fy;
 knob.style.transform='translate('+Math.round(fx*33)+'px,'+Math.round(fy*33)+'px)';
}
joy.addEventListener('pointerdown',e=>{activeJoy=e.pointerId;joy.setPointerCapture(e.pointerId);setJoy(e);input.touchEvents++;e.preventDefault();});
joy.addEventListener('pointermove',e=>{if(e.pointerId!==activeJoy)return;setJoy(e);e.preventDefault();});
function joyStop(e){if(e.pointerId!==activeJoy)return;activeJoy=null;input.joyX=0;input.joyY=0;knob.style.transform='translate(0,0)';}
joy.addEventListener('pointerup',joyStop);joy.addEventListener('pointercancel',joyStop);
try{
 app=new Application(stage,{graphicsDeviceOptions:{antialias:false,preserveDrawingBuffer:true,alpha:false}});
 app.setCanvasFillMode(FILLMODE_FILL_WINDOW);app.setCanvasResolution(RESOLUTION_AUTO);app.start();
 device=app.graphicsDevice;app.scene.ambientLight.set(1,1,1);
 asset=new Asset('Apollo R17G single-photo Gaussian','gsplat',{url:'/scene.sog'});
 app.assets.add(asset);
 cam=new Entity('R20_input_camera');cam.addComponent('camera',{clearColor:[.7,.78,.8,1],fov:58,nearClip:.05,farClip:50});app.root.addChild(cam);
 model=new Entity('R17G_readonly_sample');model.addComponent('gsplat',{asset});app.root.addChild(model);
 await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(Error('ASSET_TIMEOUT_35S')),35000);
  asset.once('load',()=>{clearTimeout(timer);resolve();});
  asset.once('error',e=>{clearTimeout(timer);reject(Error(String(e)))});
  app.assets.load(asset);
 });
 ready=true;status.textContent='SOG loaded · player input enabled';cameraSync();renderHUD();
}catch(e){error=String(e);failures.push(error);status.textContent='LOAD ERROR '+error;console.error('R20_INITIALIZATION',e);}
if(app)app.on('update',()=>{
 const now=performance.now(),dt=Math.max(0,Math.min(.06,(now-lastFrame)/1000));lastFrame=now;
 const forward=Number(input.held.has('w')||input.held.has('arrowup'))-Number(input.held.has('s')||input.held.has('arrowdown'))+input.joyY;
 const side=Number(input.held.has('d')||input.held.has('arrowright'))-Number(input.held.has('a')||input.held.has('arrowleft'))+input.joyX;
 const len=Math.hypot(forward,side);
 player.moving=len>.05;
 if(player.moving){
  const f=forward/Math.max(1,len),s=side/Math.max(1,len),speed=SPEED*dt;
  const dx=(-Math.sin(player.yaw)*f+Math.cos(player.yaw)*s)*speed,
        dz=(-Math.cos(player.yaw)*f-Math.sin(player.yaw)*s)*speed;
  const nx=Math.max(-LIMIT,Math.min(LIMIT,player.x+dx)),nz=Math.max(-LIMIT,Math.min(LIMIT,player.z+dz));
  player.distance+=Math.hypot(nx-player.x,nz-player.z);player.x=nx;player.z=nz;
  player.maxDisplacement=Math.max(player.maxDisplacement,Math.hypot(player.x,player.z));
  input.movingFrames++;recordPoint();cameraSync();
 }else input.stoppedFrames++;
 frameCount++;fpsFrames++;
 if(now-fpsTime>=1000){fps=Math.round(fpsFrames*1000/(now-fpsTime));fpsFrames=0;fpsTime=now;}
 if(frameCount%6===0)renderHUD();
});
window.addEventListener('resize',()=>app?.resizeCanvas());cameraSync();renderHUD();
