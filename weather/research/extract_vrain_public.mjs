import fs from 'node:fs/promises';
const src='weather/research/ground-truth-probe/vrain-public.json';
const dst='weather/research/ground-truth-probe/vrain-calls.json';
const raw=JSON.parse(await fs.readFile(src,'utf8'));
const tx=(raw.transactions||[]).filter(x=>x.resource_type!=='document');
const out={generated_at:new Date().toISOString(),source_generated_at:raw.generated_at,final_url:raw.final_url,calls:tx.map(x=>({url:x.url,status:x.status,method:x.method,resource_type:x.resource_type,content_type:x.content_type,post_data:x.post_data,body_length:x.body_length,body_preview:x.body_preview}))};
await fs.writeFile(dst,JSON.stringify(out,null,2)+'\n');
console.log(JSON.stringify(out,null,2));
