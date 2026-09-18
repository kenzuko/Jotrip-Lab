import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const OUT='weather/research/ground-truth-probe/deep-probe';
await fs.mkdir(OUT,{recursive:true});
await fs.mkdir('/tmp/pq-groundtruth',{recursive:true});

const VN_TZ='Asia/Ho_Chi_Minh';
const pad=n=>String(n).padStart(2,'0');
function vnDate(offsetDays=0){
  const now=new Date(Date.now()+offsetDays*86400000);
  const parts=new Intl.DateTimeFormat('en-GB',{timeZone:VN_TZ,day:'2-digit',month:'2-digit',year:'numeric'}).formatToParts(now);
  const o=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  return `${o.day}/${o.month}/${o.year}`;
}
const fd=vnDate(-2), td=vnDate(0);

async function safeText(res,max=20000){
  try { const t=await res.text(); return t.slice(0,max); } catch { return ''; }
}
async function browserTarget(browser,t){
  const ctx=await browser.newContext({acceptDownloads:true});
  const page=await ctx.newPage();
  const out={key:t.key,url:t.url,nav_error:null,scripts:[],inline_routes:[],probes:[],export:null};
  try{
    await page.goto(t.url,{waitUntil:'domcontentloaded',timeout:45000});
    await page.waitForTimeout(2500);
    const dom=await page.evaluate(()=>({
      title:document.title,
      scripts:[...document.scripts].map(s=>({src:s.src,text:s.src?'':(s.textContent||'').slice(0,40000)})),
      body:(document.body?.innerText||'').slice(0,25000)
    }));
    out.title=dom.title;
    out.body_preview=dom.body;
    for(const s of dom.scripts){
      if(s.src) out.scripts.push(s.src);
      else {
        const hits=(s.text.match(/\/(?:kttv|api)\/[^'"\s)]+/g)||[]).slice(0,80);
        if(hits.length) out.inline_routes.push(...hits);
      }
    }
    for(const sdid of (t.sdids||[])){
      for(const hour of ['6','24','72']){
        for(const route of (t.routes||[])){
          const result=await page.evaluate(async ({route,sdid,hour})=>{
            const body=new URLSearchParams({sdid:String(sdid)});
            const res=await fetch(`${route}?hour=${hour}`,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},body,credentials:'include'});
            return {status:res.status,content_type:res.headers.get('content-type')||'',text:(await res.text()).slice(0,25000)};
          },{route,sdid,hour}).catch(e=>({error:String(e)}));
          out.probes.push({sdid,hour,route,...result});
        }
      }
    }
    if(t.sid){
      try{
        const res=await ctx.request.post(`https://kttvtudong.net/kttv/export/excelexport?sid=${t.sid}`,{
          form:{fd,td},
          headers:{'Referer':t.url,'User-Agent':'JoTrip-WeatherLab-Research/2.0'}
        });
        const buf=await res.body();
        const p=`/tmp/pq-groundtruth/${t.key}.xlsx`;
        await fs.writeFile(p,buf);
        out.export={status:res.status(),content_type:res.headers()['content-type']||'',bytes:buf.length,path:p,window:{fd,td},magic:buf.slice(0,8).toString('hex')};
      }catch(e){out.export={error:String(e),window:{fd,td}}}
    }
    const detailJs=out.scripts.find(x=>/kWeb\.KTTVDetail\.js/i.test(x));
    if(detailJs){
      try{
        const res=await ctx.request.get(detailJs);
        const txt=(await res.text()).slice(0,200000);
        out.detail_js={url:detailJs,status:res.status(),length:txt.length,routes:[...new Set(txt.match(/\/(?:kttv|api)\/[^'"\s)]+/g)||[])].slice(0,200),interesting:txt.split('\n').filter(l=>/ajax|post\(|get\(|report|socket|signalr|mqtt|device|value|tbody/i.test(l)).slice(0,220)};
      }catch(e){out.detail_js={url:detailJs,error:String(e)}}
    }
  }catch(e){out.nav_error=String(e)}
  await ctx.close();
  return out;
}

async function listPage(browser,url){
  const ctx=await browser.newContext();
  const p=await ctx.newPage();
  let result={url,error:null};
  try{
    await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
    await p.waitForTimeout(2000);
    result=await p.evaluate(()=>({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,50000),links:[...document.querySelectorAll('a')].map(a=>({text:(a.innerText||'').trim(),href:a.href})).filter(x=>/Phú Quốc|Phu Quoc|An Thới|An Thoi|Cửa Cạn|Cua Can|Gành Dầu|Ganh Dau|Rạch Giá|Rach Gia/i.test(x.text+' '+x.href)).slice(0,300)}));
  }catch(e){result.error=String(e)}
  await ctx.close();
  return result;
}

async function vrainProbe(browser){
  const ctx=await browser.newContext();
  const p=await ctx.newPage();
  const out={};
  try{
    await p.goto('https://vrain.vn/',{waitUntil:'domcontentloaded',timeout:45000});
    await p.waitForTimeout(5000);
    const scripts=await p.evaluate(()=>[...document.scripts].map(s=>s.src).filter(Boolean));
    out.scripts=scripts;
    out.bundle_hits=[];
    for(const src of scripts.filter(x=>/vrain\.vn/i.test(x)).slice(-12)){
      try{
        const res=await ctx.request.get(src);
        const txt=await res.text();
        const hits=[];
        for(const re of [/https:\/\/data\.vrain\.vn[^"'\s)]+/g,/\/api\/[^"'\s)]+/g,/\/public\/[^"'\s)]+/g]){
          for(const m of (txt.match(re)||[])) hits.push(m);
        }
        const keywords=txt.split(/[,;{}]/).filter(x=>/history|archive|sumDepth|current\/all|time_point|station.*stat|public\/current/i.test(x)).slice(0,120);
        if(hits.length||keywords.length) out.bundle_hits.push({src,status:res.status(),hits:[...new Set(hits)].slice(0,250),keywords});
      }catch(e){out.bundle_hits.push({src,error:String(e)})}
    }
    const all=await ctx.request.get('https://data.vrain.vn/public/current/all.json');
    const data=await all.json();
    const rows=Array.isArray(data)?data:Object.values(data||{}).flatMap(v=>Array.isArray(v)?v:[v]);
    out.current={status:all.status(),count:rows.length,phu_quoc:rows.filter(r=>{
      const lt=Number(r?.lt??r?.lat??r?.station?.lat),lg=Number(r?.lg??r?.lng??r?.station?.lng);
      const s=JSON.stringify(r).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
      return (Number.isFinite(lt)&&Number.isFinite(lg)&&lt>=9.8&&lt<=10.55&&lg>=103.65&&lg<=104.25)||/(phu quoc|cua can|an thoi|duong dong|ganh dau|rach vem|ham ninh)/.test(s);
    })};
    out.candidates=[];
    for(const u of [
      'https://data.vrain.vn/public/history/all.json',
      'https://data.vrain.vn/public/archive/all.json',
      'https://data.vrain.vn/public/2026-09-17/all.json',
      'https://data.vrain.vn/public/2026/09/17/all.json'
    ]){
      try{const r=await ctx.request.get(u);out.candidates.push({url:u,status:r.status(),content_type:r.headers()['content-type']||'',preview:(await safeText(r,1200))})}catch(e){out.candidates.push({url:u,error:String(e)})}
    }
    const time=await ctx.request.get('https://vrain.vn/api/public/v1/time');
    out.time={status:time.status(),body:await safeText(time,2000)};
    out.dom=await p.evaluate(()=>({text:(document.body?.innerText||'').slice(0,15000)}));
  }catch(e){out.error=String(e)}
  await ctx.close();
  return out;
}

async function awcProbe(browser){
  const ctx=await browser.newContext();
  try{
    const url='https://aviationweather.gov/api/data/metar?ids=VVPQ&format=json&hours=24';
    const r=await ctx.request.get(url,{headers:{'User-Agent':'JoTrip-WeatherLab-Research/2.0'}});
    return {url,status:r.status(),content_type:r.headers()['content-type']||'',body:await safeText(r,30000)};
  }catch(e){return {error:String(e)}} finally {await ctx.close()}
}

const browser=await chromium.launch({headless:true});
const result={
  generated_at:new Date().toISOString(),
  purpose:'Deep public-source ground-truth probe. No authentication bypass.',
  date_window:{fd,td},
  kttv:{},
  lists:{},
  vrain:null,
  vvpq:null
};
const targets=[
 {key:'phu_quoc_60018',sid:33,url:'https://kttvtudong.net/kttv/detail/view?sid=33',sdids:[57,58],routes:['/kttv/report/tocdogio','/kttv/report/huonggio','/kttv/report/mucnuochaivan']},
 {key:'rach_gia_089907',sid:464,url:'https://kttvtudong.net/kttv/detail/view?sid=464',sdids:[2464],routes:['/kttv/report/tocdogio','/kttv/report/huonggio']},
];
for(const t of targets) result.kttv[t.key]=await browserTarget(browser,t);
for(const [k,u] of Object.entries({
  mua_default:'https://kttvtudong.net/kttv/default/mua',
  mua_detail:'https://kttvtudong.net/kttv/detail/mua',
  khituong_default:'https://kttvtudong.net/kttv/default/khituong'
})) result.lists[k]=await listPage(browser,u);
result.vrain=await vrainProbe(browser);
result.vvpq=await awcProbe(browser);
await browser.close();
await fs.writeFile(`${OUT}/deep-probe.json`,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({
 generated_at:result.generated_at,
 kttv:Object.fromEntries(Object.entries(result.kttv).map(([k,v])=>[k,{nav_error:v.nav_error,probes:v.probes?.map(x=>({route:x.route,sdid:x.sdid,hour:x.hour,status:x.status,preview:(x.text||'').slice(0,180)})),export:v.export,detail_routes:v.detail_js?.routes}])),
 vrain:{current:result.vrain?.current,candidates:result.vrain?.candidates,bundle_hits:result.vrain?.bundle_hits?.map(x=>({src:x.src,hits:x.hits}))},
 vvpq:{status:result.vvpq?.status,preview:(result.vvpq?.body||'').slice(0,500)}
},null,2));
