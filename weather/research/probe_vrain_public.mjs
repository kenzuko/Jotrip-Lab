import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const tx = [];
page.on('response', async res => {
  const req = res.request();
  const u = res.url();
  if (!/vrain\.vn/i.test(u)) return;
  if (!['xhr','fetch','document'].includes(req.resourceType())) return;
  const h = await res.allHeaders().catch(()=>({}));
  const ct = h['content-type'] || '';
  let body='';
  if (/json|text|html|javascript/i.test(ct)) body = await res.text().catch(()=> '');
  tx.push({url:u,status:res.status(),method:req.method(),resource_type:req.resourceType(),content_type:ct,post_data:req.postData()||'',body_length:body.length,body_preview:body.slice(0,8000)});
});
let error=null;
try {
  await page.goto('https://vrain.vn/', {waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForTimeout(10000);
} catch(e) { error=String(e); }
const dom = await page.evaluate(() => ({
  title: document.title,
  text: (document.body?.innerText||'').slice(0,10000),
  links: [...document.querySelectorAll('a')].map(a=>({text:(a.innerText||'').trim(),href:a.href})).filter(x=>x.text||x.href).slice(0,200),
  inputs: [...document.querySelectorAll('input')].map(i=>({name:i.name,id:i.id,placeholder:i.placeholder,type:i.type})).slice(0,100),
})).catch(e=>({error:String(e)}));
const out={generated_at:new Date().toISOString(),note:'Public browser only. No request headers/cookies/tokens are recorded.',navigation_error:error,final_url:page.url(),dom,transactions:tx};
await browser.close();
await fs.mkdir('weather/research/ground-truth-probe',{recursive:true});
await fs.writeFile('weather/research/ground-truth-probe/vrain-public.json',JSON.stringify(out,null,2)+'\n');
console.log(JSON.stringify({generated_at:out.generated_at,final_url:out.final_url,transaction_count:tx.length,title:dom.title,text_preview:(dom.text||'').slice(0,1000)},null,2));
