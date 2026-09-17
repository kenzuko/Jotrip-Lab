import fs from 'node:fs/promises';

const url='https://data.vrain.vn/public/current/all.json';
const res=await fetch(url,{headers:{'User-Agent':'JoTrip-WeatherLab-Research/1.0'}});
if(!res.ok) throw new Error(`HTTP ${res.status}`);
const data=await res.json();

const norm=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();
const getCoord=o=>({lat:Number(o?.lat ?? o?.station?.lat),lng:Number(o?.lng ?? o?.station?.lng)});
const textOf=o=>norm(JSON.stringify(o));
const rows=Array.isArray(data)?data:Object.values(data||{}).flatMap(v=>Array.isArray(v)?v:[v]);
const matched=[];
for(const r of rows){
  const txt=textOf(r);
  const {lat,lng}=getCoord(r);
  const nameHit=['cua can','an thoi','phu quoc','duong dong','ganh dau','rach vem','ham ninh'].some(k=>txt.includes(k));
  const box=Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=9.8&&lat<=10.55&&lng>=103.65&&lng<=104.25;
  if(nameHit||box) matched.push(r);
}
const out={
  fetched_at:new Date().toISOString(),
  source:url,
  http_status:res.status,
  total_top_level_rows:rows.length,
  match_count:matched.length,
  note:'Public feed used by vrain.vn landing. Filter is name/address plus broad Phu Quoc bounding box.',
  matches:matched
};
await fs.mkdir('weather/research/ground-truth-probe',{recursive:true});
await fs.writeFile('weather/research/ground-truth-probe/vrain-phuquoc.json',JSON.stringify(out,null,2)+'\n');
console.log(JSON.stringify(out,null,2));
