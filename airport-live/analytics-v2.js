(()=>{
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
const fold=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toUpperCase();
const liveUrl=()=>String(window.JOTRIP_LIVE_API_URL||'').replace(/\/$/,'');
function airline(r){return r?.airline_name||r?.airline||r?.airline_code||'Chưa rõ hãng'}
function mins(t){if(!t)return null;const m=String(t).match(/(\d{1,2}):(\d{2})/);return m?Number(m[1])*60+Number(m[2]):null}
function diff(a,b){const x=mins(a),y=mins(b);if(x==null||y==null)return null;let d=y-x;if(d<0)d+=1440;return d>=0&&d<=720?d:null}
function delayed(r){
 const u=fold([r?.status_code,r?.status,r?.raw_status].join(' '));
 if(/DELAYED|RESCHEDULED|POSTPONED|TRE|HOAN|DOI GIO/.test(u))return true;
 if(Number(r?.delay_minutes)>0)return true;
 const s=r?.scheduled_time||r?.times?.[0],e=r?.estimated_time;
 return !!(s&&e&&s!==e&&diff(s,e)>0);
}
function cancelled(r){return /CANCELLED|HUY/.test(fold([r?.status_code,r?.status,r?.raw_status].join(' ')))}
function delayMinutes(r){if(Number.isFinite(Number(r?.delay_minutes)))return Math.max(0,Number(r.delay_minutes));const s=r?.scheduled_time||r?.times?.[0],e=r?.estimated_time;return diff(s,e)}
function table(records){
 const map=new Map();
 for(const r of records||[]){const name=airline(r),k=fold(name)||'UNKNOWN';if(!map.has(k))map.set(k,{name,total:0,on:0,late:0,cancel:0,delaySum:0,delayN:0});const a=map.get(k);a.total++;if(cancelled(r)){a.cancel++;continue}if(delayed(r)){a.late++;const d=delayMinutes(r);if(Number.isFinite(d)){a.delaySum+=d;a.delayN++}}else a.on++}
 return [...map.values()].sort((a,b)=>b.total-a.total||b.on-a.on);
}
function render(records){const body=$('#airlinePerformanceBody');if(!body)return;const rows=table(records);body.innerHTML=rows.length?rows.map(a=>{const base=Math.max(1,a.total-a.cancel),onPct=Math.round(a.on*1000/base)/10,latePct=Math.round(a.late*1000/base)/10,avg=a.delayN?Math.round(a.delaySum/a.delayN):0;return `<tr><td><strong>${esc(a.name)}</strong></td><td>${a.total}</td><td>${a.on}</td><td>${a.late}</td><td class="rate-good">${onPct}%</td><td class="rate-watch">${latePct}%</td><td>${avg?avg+' phút':'-'}</td></tr>`}).join(''):'<tr><td colspan="7">Chưa có dữ liệu hãng bay.</td></tr>';const valid=rows.reduce((n,a)=>n+a.on+a.late,0),on=rows.reduce((n,a)=>n+a.on,0),late=rows.reduce((n,a)=>n+a.late,0);$('#airlineOnTimeRate').textContent=valid?Math.round(on*1000/valid)/10+'%':'-';$('#airlineDelayRate').textContent=valid?Math.round(late*1000/valid)/10+'%':'-'}
async function load(){try{const u=liveUrl();if(!u)return;const r=await fetch(`${u}?t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const p=await r.json();render(p?.latest?.records||[])}catch(e){console.warn('Airline analytics unavailable',e)}}
load();setInterval(load,60000);
})();
