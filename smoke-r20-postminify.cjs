'use strict';
const fs=require('fs');
const {chromium}=require('C:/Users/Public/OpenPQ/living-kyoto-reference-proof-20261010/kyoto-higashiyama/node_modules/playwright');
const {createServer}=require('./server.cjs');
(async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));let b;const errors=[];
 try{
  b=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--no-sandbox','--enable-unsafe-swiftshader']});
  const p=await b.newPage({viewport:{width:844,height:390}});
  p.on('pageerror',e=>errors.push(e.message));
  p.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
  await p.goto('http://127.0.0.1:'+server.address().port+'/',{waitUntil:'domcontentloaded'});
  await p.waitForFunction(()=>window.R20?.state()?.ready,{timeout:60000});
  await p.keyboard.down('w');await p.waitForTimeout(900);await p.keyboard.up('w');
  await p.mouse.move(510,220);await p.mouse.down();await p.mouse.move(340,220,{steps:6});await p.mouse.up();
  await p.waitForTimeout(350);
  const s=await p.evaluate(()=>window.R20.state());
  const result={result:'',checks:{loaded:s.ready&&s.webgl&&s.asset,moved:s.walkedDistance>.05,looked:s.input.lookEvents>0,stopped:!s.moving,noErrors:errors.length===0},state:{x:s.x,z:s.z,yawDeg:s.yawDeg,walkedDistance:s.walkedDistance,disocclusion:s.disocclusion},errors,visual:'HOLD'};
  result.result=Object.values(result.checks).every(Boolean)?'PASS_MINIFIED_TECHNICAL_ONLY':'FAIL';
  fs.writeFileSync('R20_MINIFIED_POSTBUILD_SMOKE.json',JSON.stringify(result,null,2));
  console.log('R20_MINIFIED_SMOKE',JSON.stringify(result));
  if(result.result==='FAIL')process.exitCode=2;
 }catch(e){console.error('POSTBUILD_SMOKE_FATAL',e.stack);process.exitCode=2;}
 finally{if(b)await b.close();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=2});