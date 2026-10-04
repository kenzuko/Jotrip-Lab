import {mkdir,writeFile} from 'node:fs/promises';
const account='1a64a0a081ea758f72be8254030bdf11',token=process.env.CLOUDFLARE_API_TOKEN?.trim();
const report={read_only:true,repository:process.env.GITHUB_REPOSITORY,code_sha:process.env.GITHUB_SHA,at:new Date().toISOString(),credential_present:Boolean(token),account_id:account,permissions_changed:false,reads:[]};
if(token)for(const path of ['/workers/scripts','/r2/buckets','/r2/buckets/openpq-intelligence-canonical']){
 const row={path};report.reads.push(row);
 try{const r=await fetch('https://api.cloudflare.com/client/v4/accounts/'+account+path,{headers:{authorization:'Bearer '+token},redirect:'error',signal:AbortSignal.timeout(15000)});const d=await r.json();row.http_status=r.status;row.success=r.ok&&d.success===true;row.error_codes=(d.errors??[]).map(x=>x.code).filter(x=>Number.isSafeInteger(x));
 if(row.success&&path==='/r2/buckets')row.buckets=(d.result?.buckets??[]).map(x=>({name:x.name,jurisdiction:x.jurisdiction??'default'}));
 if(row.success&&path==='/r2/buckets/openpq-intelligence-canonical')row.bucket={name:d.result?.name,jurisdiction:d.result?.jurisdiction??'default'};
 }catch{row.error='READ_UNAVAILABLE';}
}
await mkdir('.core2-r2-capability',{recursive:true});await writeFile('.core2-r2-capability/CAPABILITY.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));