'use strict';
// Playwright drives *real keyboard and mouse inputs* into R20 WebGL.
// Video is browser-encoded, never a pre-scripted camera animation.
// The real player remains free to stop and turn; QA just simulates a human session.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('C:/Users/Public/OpenPQ/living-kyoto-reference-proof-20261010/kyoto-higashiyama/node_modules/playwright');
const {createServer}=require('./server.cjs');
const out=__dirname;
const stages=[],screens=[],errors=[];
const safe=s=>s.replace(/[^a-z0-9_-]/gi,'');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port+'/';
 let browser,context,page,fatal=null,videoPath=null;
 try{
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
   args:['--no-sandbox','--enable-unsafe-swiftshader','--disable-extensions','--disable-background-networking']});
  context=await browser.newContext({viewport:{width:844,height:390},deviceScaleFactor:1,
   recordVideo:{dir:out,size:{width:844,height:390}}});
  page=await context.newPage();
  page.on('pageerror',e=>errors.push('PAGE:'+e.message));
  page.on('console',e=>{if(e.type()==='error')errors.push('CONSOLE:'+e.text())});
  page.on('response',e=>{if(e.status()>=400)errors.push('HTTP:'+e.status()+' '+e.url())});
  page.on('request',e=>{if(!e.url().startsWith(url)&&!e.url().startsWith('blob:'))errors.push('EXTERNAL:'+e.url())});
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>window.R20?.state()?.ready,{timeout:90000});
  const video=page.video();let n=0;
  async function snapshot(name){
   const state=await page.evaluate(()=>window.R20.state());
   const img=path.join(out,'R20_'+safe(name)+'.png');
   const bytes=await page.screenshot({path:img,timeout:40000});
   const hash=crypto.createHash('sha256').update(bytes).digest('hex');
   stages.push({stage:name,atSec:+(Date.now()-start)/1000,state:{x:state.x,z:state.z,yawDeg:state.yawDeg,
     walkedDistance:state.walkedDistance,disocclusion:state.disocclusion,moving:state.moving,
     movingFrames:state.input.movingFrames,stoppedFrames:state.input.stoppedFrames,keys:state.input.keys,
     lookEvents:state.input.lookEvents,fpsBrowser:state.fpsBrowser}});
   screens.push({stage:name,file:path.basename(img),bytes:bytes.length,sha256:hash});
   console.log('R20_STAGE',name,'x',state.x.toFixed(2),'z',state.z.toFixed(2),'yaw',state.yawDeg.toFixed(1));
  }
  const start=Date.now();
  await wait(2200);await snapshot('00_front');
  await page.keyboard.down('w');await wait(3400);await page.keyboard.up('w');
  await wait(1600);await snapshot('01_walk_stop');
  await page.mouse.move(560,210);await page.mouse.down();
  for(let i=1;i<=16;i++){await page.mouse.move(560-i*18,210+i*.7);await wait(55);}
  await page.mouse.up();await wait(500);await snapshot('02_turn');
  await page.keyboard.down('d');await wait(3300);await page.keyboard.up('d');
  await wait(1600);await snapshot('03_lateral_stop');
  await page.keyboard.down('s');await wait(2700);await page.keyboard.up('s');
  await wait(1400);await snapshot('04_backstep');
  await page.mouse.move(660,250);await page.mouse.down();
  for(let i=1;i<=20;i++){await page.mouse.move(660-i*23,250);await wait(45);}
  await page.mouse.up();
  await wait(1800);await snapshot('05_lookback_stop');
  const final=await page.evaluate(()=>window.R20.state());
  const elapsed=(Date.now()-start)/1000;
  await page.close();await context.close();
  videoPath=path.join(out,'R20_REAL_INPUT_WEBGL_'+Math.round(elapsed)+'S.webm');
  await video.saveAs(videoPath);
  await browser.close();browser=null;
  const checks={
   actualWebGLAndSOG:final.ready&&final.webgl&&final.asset&&!final.error,
   hasMovementInput:final.input.keys>=3&&final.input.movingFrames>0&&final.walkedDistance>.5,
   hasPointerLook:final.input.lookEvents>=20&&Math.abs(final.yawDeg)>=20,
   stoppedFrames:final.input.stoppedFrames>0&&!final.moving,
   stress1m:final.maxDisplacement>=1,
   boundedProxy:Math.abs(final.x)<=2.001&&Math.abs(final.z)<=2.001,
   noConsoleOrNetworkErrors:errors.length===0,
   realWebM:fs.existsSync(videoPath)&&fs.statSync(videoPath).size>20000,
   threeDistinctViews:screens.length>=3
  };
  const tech=Object.values(checks).every(Boolean);
  const qa={
   status:tech?'TECHNICAL_INPUT_PASS__VISUAL_FAIL_HOLD':'TECHNICAL_INCOMPLETE__VISUAL_FAIL_HOLD',
   video:{file:path.basename(videoPath),bytes:fs.statSync(videoPath).size,durationSec:elapsed,meaning:'browser-recorded real mouse/keyboard action; not a manually animated orbit; headless Windows Edge, NOT iPhone'},
   checks,stages,screens,errors,final,
   visual:'FAIL/HOLD: single-source geometry tearing/holes at large displacements, people in source remain baked in; NOT 10x10m photogrammetry',
   mobile:'UNTESTED on actual iPhone landscape, FPS on Edge does not prove iPhone >=30fps',
   provenance:'Vivu Vietnam Apollo photo Wikimedia Commons CC BY-SA 4.0; Depth Anything V2 Small Apache-2.0; PlayCanvas MIT; inherited R17G SOG',
   master:'NO_DEPLOY_NO_MERGE_NO_CLOUDFLARE_NO_GITHUB_ACTIONS_NO_PROD'};
  fs.writeFileSync(path.join(out,'R20_REAL_INPUT_QA.json'),JSON.stringify(qa,null,2));
  console.log('R20_FINAL',qa.status,'timeSec',elapsed.toFixed(1),'videoBytes',qa.video.bytes,'checks',checks);
  if(!tech)process.exitCode=2;
 }catch(e){
  fatal=e.stack||String(e);console.error('R20_QA_FATAL',fatal);
  fs.writeFileSync(path.join(out,'R20_REAL_INPUT_QA_ERROR.json'),JSON.stringify({fatal,errors,stages,screens,claim:'NOT_VERIFIED'},null,2));
  process.exitCode=2;
 }finally{
  try{if(context)await context.close()}catch{}
  try{if(browser)await browser.close()}catch{}
  await new Promise(r=>server.close(r));
 }
})().catch(e=>{console.error(e.stack);process.exitCode=2});