import { createHash } from 'node:crypto';

const pairs = [
 {name:'Airport',live:'https://airport.openphuquoc.com',stage:'https://openpq-airport-web.pages.dev',paths:['/','/app.js','/live-config.js','/history.html','/fids-board.js']},
 {name:'Weather',live:'https://weather.openphuquoc.com',stage:'https://openpq-weather-web.pages.dev',paths:['/','/weather-live-config.js','/data/critical.json','/data/groundtruth.json','/data/nowcast.json']},
 {name:'Transit',live:'https://transit.openphuquoc.com',stage:'https://openpq-transit-web.pages.dev',paths:['/','/app.js','/data/network.json','/data/health.json']},
 {name:'Dashboard',live:'https://dash.openphuquoc.com',stage:'https://openpq-dash-web.pages.dev',paths:['/','/app.js','/config.js','/login.html']},
 {name:'Charter',live:'https://phuquoccharter.com',stage:'https://openpq-charter-web.pages.dev',paths:['/','/app.js','/cms-copy-runtime.js','/content.js']}
];
const sha = (b)=>createHash('sha256').update(b).digest('hex').slice(0,12);
async function sample(url) {
 try {
  const controller = new AbortController();
  const t=setTimeout(()=>controller.abort(),14000);
  try {
   const r=await fetch(url,{redirect:'follow',signal:controller.signal,headers:{'Cache-Control':'no-cache'}});
   const b=Buffer.from(await r.arrayBuffer());
   return {status:r.status,sha:sha(b),bytes:b.length,type:(r.headers.get('content-type')||'').split(';')[0],noindex:(r.headers.get('x-robots-tag')||'').includes('noindex')};
  }finally{clearTimeout(t)}
 }catch(e){return {error:e.message}}
}
let fatal=0,drift=0;
for(const s of pairs) {
 for(const path of s.paths){
  const [live,stage]=await Promise.all([sample(s.live+path),sample(s.stage+path)]);
  const parity=live.status===200 && stage.status===200 && live.sha===stage.sha;
  if(live.status!==200||stage.status!==200||live.error||stage.error)fatal++;
  if(!parity)drift++;
  console.log(JSON.stringify({site:s.name,path,parity,live,stage}));
 }
}
console.log(JSON.stringify({summary:{fatal,drift,checked:pairs.reduce((n,p)=>n+p.paths.length,0),note:'Content mismatch can indicate a newer live data cycle; inspect individually before cutover'}}));
if(fatal) process.exitCode=1;
