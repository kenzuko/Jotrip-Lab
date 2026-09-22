(()=>{
"use strict";

const CRITICAL="/Jotrip-Lab/weather/data/critical.json";
const TIDE=["/Jotrip-Lab/weather/data/tide.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/tide.json"];
const AQI=["/Jotrip-Lab/weather/data/weather-aqi/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-aqi/latest.json","/weather/air-quality.json"];
const NOWCAST=["/Jotrip-Lab/weather/data/weather-nowcast/compact-latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-nowcast/compact-latest.json","/weather/nowcast.json"];
const JOTRIP_FORECAST="/Jotrip-Lab/weather/jotrip-forecast.json";
const LIVE_REFRESH_MS=10*60*1000;
const SLOW_REFRESH_MS=45*60*1000;
const FEEDBACK_ENDPOINT="/feedback";
const FEEDBACK_QUEUE_KEY="pq_weather_feedback_queue_v1";
const FEEDBACK_HISTORY_KEY="pq_weather_field_feedback_v1";
const WINDY={
  radar:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1",
  wind:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
  rain:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=rain&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
  waves:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=waves&product=ecmwfWaves&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C"
};
const JMA="https://www.data.jma.go.jp/mscweb/data/himawari/img/ha1/";

const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const defer=(fn,ms=600)=>setTimeout(()=>{"requestIdleCallback" in window?requestIdleCallback(()=>fn(),{timeout:900}):fn()},ms);

let critical=null;
let current="duong_dong";
let fullAQI=null;
let fullTide=null;
let fullNowcast=null;
let regionalForecast=null;
let currentRegion="central_west";
const POINT_REGION={
  duong_dong:"central_west",
  cua_can:"north_northwest",ganh_dau:"north_northwest",
  bai_thom:"east_northeast",ham_ninh:"east_northeast",
  bai_sao:"south_southeast",an_thoi:"south_southeast"
};
function regionForPoint(id){return POINT_REGION[id]||null}
let mapStarted=false;
let mapLayer="radar";
let liveRefreshBusy=false;
let lastLiveRefreshAt=0;
let lastSlowRefreshAt=0;

async function getJSON(url){
  const sep=url.includes("?")?"&":"?";
  const r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  return r.json();
}
async function getFirst(urls){
  let last;
  for(const u of urls){
    try{return await getJSON(u)}catch(e){last=e}
  }
  throw last||new Error("unavailable");
}
function ageMinutes(iso){
  const t=Date.parse(iso||"");
  return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):Infinity;
}
function latestIso(...values){
  return values.filter(Boolean).map(v=>({v,t:Date.parse(v)})).filter(x=>Number.isFinite(x.t)).sort((a,b)=>b.t-a.t)[0]?.v||null;
}
function liveTimestamp(){
  return latestIso(critical?.generated_at,critical?.local_generated_at);
}
function observationTimestamp(){
  const rain=(critical?.actual?.rain_gauges||[]).map(x=>x?.observed_at);
  return latestIso(critical?.actual?.vvpq?.observed_at,...rain);
}
function ageText(iso){
  const m=ageMinutes(iso);
  if(!Number.isFinite(m))return "không rõ";
  if(m<2)return "vừa cập nhật";
  if(m<60)return Math.round(m)+" phút trước";
  return (m/60).toFixed(1)+" giờ trước";
}
function localTime(iso){
  const d=new Date(iso);
  return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}):"-";
}
function hourLabel(iso){
  const d=new Date(iso);
  return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",weekday:"short",hour:"2-digit",minute:"2-digit",hour12:false}):"-";
}
function badgeClass(k){
  k=String(k||"").toUpperCase();
  if(k==="ACTUAL"||k==="POINT_NUMERIC_READY"||k==="READY")return "actual";
  if(k==="ESTIMATED_NOW")return "estimated";
  if(k==="REMOTE_OBSERVED")return "remote";
  if(k==="MODEL_ONLY")return "model";
  if(k==="LEARNING")return "learning";
  return "deferred";
}
function setBadge(id,k,label){
  const el=$(id);if(!el)return;
  el.className="badge "+badgeClass(k);
  const key=String(k||"").toUpperCase();
  const natural={
    ACTUAL:"ĐO THỰC",ESTIMATED_NOW:"ƯỚC TÍNH",MODEL_ONLY:"MÔ HÌNH",
    REMOTE_OBSERVED:"VỆ TINH",LEARNING:"ĐANG HIỆU CHỈNH",
    READY:"SẴN SÀNG",UNAVAILABLE:"CHƯA CÓ"
  };
  el.textContent=label||natural[key]||String(k||"-").replace("_NOW","").replaceAll("_"," ");
}
function setMetric(id,v,d){const el=$(id);if(el)el.textContent=num(v)===null?"-":fmt(v,d)}
function point(){return critical?.points?.[current]||{}}
function localPoint(){return point().local||{}}
function modelPoint(){return point().model||{}}

function islandIds(){
  return (critical?.island_watch_order||[]).filter(id=>critical?.points?.[id]);
}
function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function viLevel(v){
  return ({LOW:"THẤP",WATCH:"THEO DÕI",ELEVATED:"TĂNG",HIGH:"CAO"}[String(v||"").toUpperCase()]||String(v||""));
}
function viCal(v){
  return String(v||"").toUpperCase()==="LEARNING"?"ĐANG HIỆU CHỈNH":String(v||"").replaceAll("_"," ");
}
function sourceReady(v){
  const x=String(v||"").toUpperCase();
  return ["FRESH","READY","POINT_NUMERIC_READY","MEMBER_MATRIX_READY","PASS","LIVE"].includes(x);
}
function pointLayerCoverage(p){
  const l=p.local||{},a=p.aqi||{},t=p.tide||{},n=p.nowcast||{},e=p.ensemble||{};
  return [
    [l.temperature_c,l.wind_kmh,l.rain_rate_mm_h].every(v=>num(v)!==null),
    num(l.wave_hs_m??p.model?.wave_hs_m)!==null,
    num(a.aqi_us)!==null,
    num(t.height_m)!==null,
    num(n.convective_score)!==null,
    (e.rows||[]).length>=3
  ];
}
function coverageScore(){
  const ids=islandIds();if(!ids.length)return 0;
  let ok=0,total=0;
  ids.forEach(id=>pointLayerCoverage(critical.points[id]).forEach(v=>{total++;if(v)ok++}));
  return total?Math.round(100*ok/total):0;
}
function confidenceScore(){
  const ids=islandIds();if(!ids.length)return 0;
  const coverage=coverageScore()/100;
  const confs=ids.map(id=>num(critical.points[id]?.local?.rain_confidence)).filter(v=>v!==null);
  const local=confs.length?confs.reduce((a,b)=>a+b,0)/confs.length:0.35;
  const fresh=clamp(1-ageMinutes(liveTimestamp())/90,0,1);
  const ens=ids.map(id=>num(critical.points[id]?.ensemble?.completion_ratio)).filter(v=>v!==null);
  const ensemble=ens.length?ens.reduce((a,b)=>a+b,0)/ens.length:0;
  const g=critical.actual?.rain_gauges||[];
  const actual=(sourceReady(critical.source_state?.vvpq)?0.45:0)+(g.filter(x=>x.qc==="PASS"||num(x.accum_mm)!==null).length>=3?0.55:0);
  let score=100*(0.25*coverage+0.30*local+0.15*fresh+0.15*ensemble+0.15*actual);
  const learning=ids.some(id=>String(critical.points[id]?.ensemble?.calibration_status||"").toUpperCase()==="LEARNING");
  if(learning)score*=0.88;
  return Math.round(clamp(score,0,100));
}
function pointRisk(p){
  const m=p.model||{},n=p.nowcast||{},rows=p.ensemble?.rows||[];
  const conv=num(n.convective_score),gust=num(m.gust_kmh),rain=num(m.rain_3h_mm),hs=num(m.wave_hs_m);
  const windProb=Math.max(0,...rows.map(x=>num(x.wind?.prob)).filter(v=>v!==null));
  const rainProb=Math.max(0,...rows.map(x=>num(x.rain?.prob)).filter(v=>v!==null));
  let level=0,reasons=[];
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}
  else if(conv!==null&&conv>=60){level=Math.max(level,1);reasons.push("đối lưu tăng")}
  if(gust!==null&&gust>=39){level=Math.max(level,3);reasons.push("gió giật mạnh")}
  else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật cần theo dõi")}
  if(rain!==null&&rain>=25){level=Math.max(level,3);reasons.push("mưa 3 giờ lớn")}
  else if(rain!==null&&rain>=10){level=Math.max(level,2);reasons.push("mưa 3 giờ tăng")}
  if(hs!==null&&hs>=2){level=Math.max(level,3);reasons.push("sóng nền cao")}
  else if(hs!==null&&hs>=1.5){level=Math.max(level,2);reasons.push("sóng tăng")}
  if(windProb>=0.25){level=Math.max(level,2);reasons.push("vẫn còn kịch bản gió mạnh")}
  else if(windProb>=0.10){level=Math.max(level,1)}
  if(rainProb>=0.50){level=Math.max(level,2);reasons.push("nhiều kịch bản cùng nghiêng về mưa")}
  else if(rainProb>=0.25){level=Math.max(level,1)}
  return {level,reasons};
}
function beaufort(kmh){
  const v=Math.max(0,num(kmh)||0);
  const limits=[1,6,12,20,29,39,50,62,75,89,103,118];
  const names=["Lặng gió","Rất nhẹ","Nhẹ","Gió yếu","Vừa","Khá mạnh","Mạnh","Gió lớn","Gió rất lớn","Bão","Bão mạnh","Bão rất mạnh","Cuồng phong"];
  let force=12;
  for(let i=0;i<limits.length;i++){if(v<limits[i]){force=i;break}}
  return {force,label:names[force]};
}
function probabilityLevel(v){
  v=num(v);
  if(v===null)return {label:"CHƯA RÕ",score:0};
  if(v>=0.60)return {label:"CAO",score:3};
  if(v>=0.30)return {label:"VỪA",score:2};
  if(v>=0.12)return {label:"THẤP - VỪA",score:1};
  return {label:"THẤP",score:0};
}
function variationLevel(w,r){
  const ws=num(w?.spread)||0,rs=num(r?.spread)||0;
  const raw=Math.max(ws/20,rs/10);
  const index=Math.round(clamp(raw*100,0,100));
  if(index>=70)return {label:"CAO",score:3,index};
  if(index>=40)return {label:"VỪA",score:2,index};
  if(index>=20)return {label:"NHẸ",score:1,index};
  return {label:"ỔN ĐỊNH",score:0,index};
}
function pct(v){
  v=num(v);return v===null?"-":Math.round(clamp(v,0,1)*100)+"%";
}
function rowVariability(r){
  const direct=num(r?.variability_score);
  if(direct!==null)return Math.round(clamp(direct,0,100));
  return variationLevel({spread:r?.wind_spread},{spread:r?.rain_spread}).index;
}
function rowConfidence(r){
  const direct=num(r?.confidence_score);
  if(direct!==null)return Math.round(clamp(direct,0,100));
  const completion=clamp(num(regionalForecast?.ensemble_completion_ratio)??0,0,1);
  const lead=Math.max(0,num(r?.lead_hours)||0);
  const leadPenalty=lead<=72?0:Math.min(35,35*(lead-72)/(240-72));
  const learning=String(regionalForecast?.calibration_status||"").toUpperCase()==="LEARNING"?8:0;
  return Math.round(clamp(100*completion-leadPenalty-learning,35,95));
}
function leadMoment(row){
  return row?.valid_time?localTime(row.valid_time):("+"+fmt(row?.lead_hours,0)+" giờ");
}
function setHazard(id,label,meta,level){
  const b=$(id),m=$(id+"Meta");if(!b||!m)return;
  b.textContent=label;m.textContent=meta;
  const card=b.closest("article");
  if(card)card.dataset.level=String(level||0);
}
function renderHazardBoard(){
  const points=islandIds().map(id=>({id,p:critical.points[id]}));
  const future=[];
  points.forEach(x=>(x.p.ensemble?.rows||[]).forEach(r=>future.push({id:x.id,p:x.p,row:r})));

  const rain=future.map(x=>({...x,val:num(x.row.rain?.prob)||0})).sort((a,b)=>b.val-a.val)[0];
  const rainLvl=probabilityLevel(rain?.val);
  setHazard("hazardRain",rain?pct(rain.val):"-",rain?"P(mưa ≥5 mm / 6h) · "+esc(rain.p.name)+" · "+leadMoment(rain.row):"Chưa đủ dữ liệu tổ hợp",rainLvl.score);

  const storms=points.map(x=>({
    ...x,
    score:num(x.p.nowcast?.convective_score)||0,
    cooling:num(x.p.nowcast?.cooling_c_per_20m)
  })).sort((a,b)=>b.score-a.score);
  const storm=storms[0];
  let stormLevel=0;
  if(storm?.score>=75)stormLevel=3;
  else if(storm?.score>=60)stormLevel=2;
  else if(storm?.score>=40)stormLevel=1;
  setHazard("hazardStorm",storm?fmt(storm.score,0)+"/100":"-",storm?"Chỉ số đối lưu · "+esc(storm.p.name)+(storm.cooling!==null?" · Δ20p "+fmt(storm.cooling,1)+"°C":"")+" · không phải xác suất dông":"Chưa có Himawari",stormLevel);

  const wind=future.map(x=>({...x,val:num(x.row.wind?.prob)||0})).sort((a,b)=>b.val-a.val)[0];
  const regionalWindRows=Object.values(regionalForecast?.regions||{}).flatMap(region=>
    (region.rows||[]).map(row=>({region:region.name||"Phú Quốc",row}))
  );
  const nearWindRows=regionalWindRows.filter(x=>{
    const lead=num(x.row.lead_hours);
    return lead!==null&&lead>=0&&lead<=24;
  });
  const windHeadline=(nearWindRows.length?nearWindRows:regionalWindRows)
    .sort((a,b)=>(num(b.row.wind_kmh)??-1)-(num(a.row.wind_kmh)??-1))[0];
  const windP50=num(windHeadline?.row?.wind_kmh);
  const windP10=num(windHeadline?.row?.wind_q10_kmh);
  const windP90=num(windHeadline?.row?.wind_q90_kmh);
  const windThresholdProb=num(windHeadline?.row?.wind_prob_30)??num(wind?.val);
  const windLvl=probabilityLevel(windThresholdProb);
  const waves=points.map(x=>({name:x.p.name,hs:num(x.p.local?.wave_hs_m??x.p.model?.wave_hs_m)||0})).sort((a,b)=>b.hs-a.hs)[0];
  const rangeText=windP10!==null&&windP90!==null
    ? "P10-P90 "+fmt(windP10,1)+"-"+fmt(windP90,1)+" km/h"
    : (windP90!==null?"P50-P90 "+fmt(windP50,1)+"-"+fmt(windP90,1)+" km/h":"Chưa đủ range");
  const windMeta=windHeadline
    ? rangeText+" · xác suất ≥30 km/h "+pct(windThresholdProb)+" · "+esc(windHeadline.region)+" · "+leadMoment(windHeadline.row)+(waves?.hs?" · Hs cao nhất "+fmt(waves.hs,1)+" m":"")
    : "Đang chờ dự báo ensemble theo vùng";
  setHazard("hazardWind",windP50!==null?fmt(windP50,1)+" km/h":"-",windMeta,Math.max(windLvl.score,waves?.hs>=2?3:waves?.hs>=1.5?2:0));

  const vol=future.map(x=>({...x,v:variationLevel(x.row.wind,x.row.rain)})).sort((a,b)=>b.v.index-a.v.index)[0];
  setHazard("hazardVolatility",vol?vol.v.index+"/100":"-",vol?"Biến động ensemble · "+esc(vol.p.name)+" · mạnh nhất "+leadMoment(vol.row)+" · không phải xác suất":"Chưa đủ dữ liệu",vol?.v.score||0);
}

function islandAssessment(){
  const rows=islandIds().map(id=>({id,p:critical.points[id],risk:pointRisk(critical.points[id])}));
  rows.sort((a,b)=>b.risk.level-a.risk.level);
  const worst=rows[0]?.risk.level||0;
  const label=worst>=3?"NÊN ĐIỀU CHỈNH":worst>=2?"THEO DÕI SÁT":worst>=1?"CÓ ĐIỂM CẦN LƯU Ý":"TƯƠNG ĐỐI ỔN";
  const attention=rows.filter(x=>x.risk.level>=2).slice(0,4);
  return {label,attention,rows};
}
function renderPointTabs(){
  const nav=$("pointTabs");if(!nav||!critical)return;
  const ids=[...islandIds()];
  if(critical.points?.rach_gia)ids.push("rach_gia");
  nav.innerHTML=ids.map(id=>{
    const off=id==="rach_gia";
    return '<button class="'+(id===current?'active ':'')+(off?'off-island':'')+'" data-point="'+esc(id)+'">'+esc(critical.points[id]?.name||id)+(off?' · đối chiếu':'')+'</button>';
  }).join("");
}

function renderStatus(){
  if(!critical)return;
  const m=ageMinutes(liveTimestamp());
  const stale=m>60,delayed=m>25;
  $("liveDot").className=stale||delayed?"warn":"ok";
  $("liveLabel").textContent=(stale?"DỮ LIỆU CŨ":delayed?"CẬP NHẬT CHẬM":critical.report_status==="LIVE"?"ĐANG HOẠT ĐỘNG":"SUY GIẢM")+" · "+ageText(liveTimestamp());

  const assessment=islandAssessment();
  const coverage=coverageScore();
  const confidence=confidenceScore();
  $("decisionNow").textContent=assessment.label;
  $("completenessNow").textContent=coverage+"% · "+islandIds().length+"/"+islandIds().length+" điểm";
  $("confidenceNow").textContent=confidence+"/100 · "+(confidence>=80?"cao":confidence>=60?"khá":"thận trọng");
  const fallbackLead=Math.max(0,...islandIds().flatMap(id=>(critical.points[id]?.ensemble?.rows||[]).map(r=>Number(r.lead_hours)||0)));
  const maxLead=Number(regionalForecast?.horizon_hours||fallbackLead||0);
  $("horizonNow").textContent=maxLead?(maxLead>=240?"10 NGÀY":maxLead+" giờ"):"CHƯA CÓ";
  $("completenessNow").parentElement.title="Tỷ lệ các lớp phân tích hiện tại, dự báo JoTrip, AQI, triều, Himawari và dự báo tổ hợp đang có dữ liệu trên 7 điểm đảo.";
  $("confidenceNow").parentElement.title="Mức tin cậy của toàn bộ dữ liệu đang dùng, không phải xác suất dự báo chắc chắn đúng.";
  const summary=$("islandSummary");
  if(summary){
    if(assessment.attention.length){
      summary.innerHTML="<b>Cần chú ý:</b> "+assessment.attention.map(x=>esc(x.p.name)+" - "+esc(x.risk.reasons.slice(0,2).join(", "))).join(" · ")+"<small>Đánh giá thời tiết tham khảo. Hạn chế/cấm tàu thuyền vẫn theo thông báo chính thức.</small>";
    }else{
      summary.innerHTML="<b>Toàn đảo:</b> chưa thấy lớp dữ liệu hiện có vượt ngưỡng theo dõi chính.<small>Tin cậy dữ liệu không đồng nghĩa dự báo chắc chắn đúng.</small>";
    }
  }
  renderHazardBoard();
  $("dataMode").textContent=critical.data_mode==="B"?"ƯU TIÊN RỦI RO":(critical.data_mode||"-");
}

function summary(p){
  const l=p.local||{},m=p.model||{},bits=[];
  const rain=num(l.rain_rate_mm_h),conv=num((p.nowcast||{}).convective_score??l.convection_score),wind=num(l.wind_kmh??m.wind_kmh),wave=num(l.wave_hs_m??m.wave_hs_m);
  if(rain!==null)bits.push(rain>=3?"Ước tính mưa hiện tại đáng chú ý":rain>.2?"Ước tính có mưa nhẹ hoặc rải rác":"Ước tính mưa hiện tại thấp");
  if(conv!==null&&conv>=70)bits.push("mây đối lưu đang hoạt động");
  if(wind!==null)bits.push("gió khoảng "+fmt(wind,0)+" km/h");
  if(wave!==null)bits.push("Hs nền khoảng "+fmt(wave,1)+" m");
  return bits.length?bits.join(" · ")+".":"Chưa đủ dữ liệu địa phương để tóm tắt.";
}

function renderHero(){
  const p=point(),l=p.local||{},m=p.model||{},n=p.nowcast||{};
  $("placeName").textContent=p.name||current;
  const t=num(l.temperature_c)??num(m.temperature_c);
  $("heroTemp").textContent=t===null?"--":fmt(t,1)+"°";
  $("heroTempClass").textContent=l.available?"ƯỚC TÍNH":"MÔ HÌNH";
  $("heroSummary").textContent=summary(p);
  $("updatedAt").textContent="Hệ thống "+localTime(liveTimestamp())+" · quan trắc gần nhất "+ageText(observationTimestamp());
  if($("scenePoint"))$("scenePoint").textContent=p.name||current;
  if($("sceneTemp"))$("sceneTemp").textContent=t===null?"--":fmt(t,1)+"°";
  if($("sceneUpdated"))$("sceneUpdated").textContent="JoTrip Local Now · "+ageText(liveTimestamp());
  const rain=num(l.rain_rate_mm_h)||0,conv=num(n.convective_score??l.convection_score)||0,wind=num(l.wind_kmh??m.wind_kmh)||0;
  const mood=(conv>=70||rain>=3)?"storm":(conv>=50||rain>=.5||wind>=28)?"watch":"calm";
  document.querySelector(".hero")?.setAttribute("data-mood",mood);
}


function weatherGlyph(kind){
  const common='viewBox="0 0 48 48" aria-hidden="true" focusable="false"';
  if(kind==="storm")return '<svg '+common+'><path d="M14 30h21a8 8 0 0 0 0-16 12 12 0 0 0-22-2A7 7 0 0 0 14 30Z"/><path d="M25 31l-4 7h5l-3 6"/></svg>';
  if(kind==="moon")return '<svg '+common+'><path d="M33 34A15 15 0 0 1 18 9a16 16 0 1 0 15 25Z"/></svg>';
  if(kind==="sun")return '<svg '+common+'><circle cx="24" cy="24" r="8"/><path d="M24 5v6M24 37v6M5 24h6M37 24h6M10.6 10.6l4.3 4.3M33.1 33.1l4.3 4.3M37.4 10.6l-4.3 4.3M14.9 33.1l-4.3 4.3"/></svg>';
  if(kind==="rain")return '<svg '+common+'><path d="M15 31h19a8 8 0 0 0 1-15.9A12 12 0 0 0 12 18.5 6.5 6.5 0 0 0 15 31Z"/><path d="M17 36l-2 5M25 36l-2 5M33 36l-2 5"/></svg>';
  if(kind==="wind")return '<svg '+common+'><path d="M7 17h23c5 0 5-7 0-7-3 0-4 2-4 4M7 24h31c5 0 5 7 0 7-3 0-4-2-4-4M7 31h17"/></svg>';
  if(kind==="wave")return '<svg '+common+'><path d="M5 20c5 0 5-5 10-5s5 5 10 5 5-5 10-5 5 5 8 5M5 29c5 0 5-5 10-5s5 5 10 5 5-5 10-5 5 5 8 5M8 37h32"/></svg>';
  return '<svg '+common+'><path d="M14 32h21a8 8 0 0 0 0-16 12 12 0 0 0-22-2A7 7 0 0 0 14 32Z"/></svg>';
}
function setDecisionTile(prefix,kind,title,text,tone){
  const tile=$(prefix+"DecisionTile"),icon=$(prefix+"DecisionIcon"),head=$(prefix+"DecisionTitle"),copy=$(prefix+"DecisionText");
  if(tile)tile.dataset.tone=tone||"neutral";
  if(icon)icon.innerHTML=weatherGlyph(kind);
  if(head)head.textContent=title;
  if(copy)copy.textContent=text;
}
function phuQuocClock(iso){
  const d=new Date(iso);
  return Number.isFinite(d.getTime())?d.toLocaleTimeString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit",hour12:false}):"-";
}
function todaySlotState(row){
  const rain=num(row?.rain)||0,wind=num(row?.wind)||0,gust=num(row?.gust)||0;
  if(rain>=10||gust>=39||wind>=32)return {cls:"avoid",label:"Nên né khung này"};
  if(rain>=3||gust>=30||wind>=24)return {cls:"watch",label:"Cần để ý"};
  return {cls:"good",label:"Khá thuận lợi"};
}
function todaySlotKind(row){
  const rain=num(row?.rain)||0,gust=num(row?.gust)||0;
  const d=new Date(row?.t||"");
  const hour=Number.isFinite(d.getTime())?Number(d.toLocaleString("en-US",{timeZone:"Asia/Ho_Chi_Minh",hour:"numeric",hour12:false})):12;
  if(rain>=8||gust>=39)return "storm";
  if(rain>=1)return "rain";
  if(rain>=0.2)return "cloud";
  if(hour>=18||hour<6)return "moon";
  return "sun";
}
function renderTodayTimeline(){
  const root=$("todayTimeline"),summary=$("todayTimelineSummary"),place=$("todayTimelinePlace");
  if(!root||!summary)return;
  const p=point(),rows=(p.today||[]).filter(r=>r&&r.t);
  if(place)place.textContent=(p.name||"Điểm đang chọn")+" · mốc 3 giờ";
  if(!rows.length){
    root.innerHTML='<div class="today-empty"><b>Chưa còn mốc dự báo nào trong hôm nay</b><span>Xem phần 10 ngày bên dưới cho ngày mai và các ngày tiếp theo.</span></div>';
    summary.textContent="Hôm nay đã gần hết hoặc chu kỳ hiện tại chưa có thêm mốc phù hợp.";
    return;
  }
  let worst=null,good=0;
  root.innerHTML=rows.map(r=>{
    const state=todaySlotState(r),kind=todaySlotKind(r);
    if(state.cls==="good")good++;
    if(!worst||({good:0,watch:1,avoid:2}[state.cls]>{good:0,watch:1,avoid:2}[worst.state.cls]))worst={r,state};
    const rain=num(r.rain),wind=num(r.wind),gust=num(r.gust);
    return '<article class="today-slot '+state.cls+'">'+
      '<time>'+esc(phuQuocClock(r.t))+'</time>'+
      '<div class="today-icon">'+weatherGlyph(kind)+'</div>'+
      '<strong>'+(num(r.temp)===null?'-':fmt(r.temp,0)+'°')+'</strong>'+
      '<b>'+state.label+'</b>'+
      '<span>'+(rain===null?'Mưa -':'Mưa '+fmt(rain,1)+' mm / 3h')+'</span>'+
      '<span>'+(wind===null?'Gió -':'Gió '+fmt(wind,0)+' km/h')+(gust!==null?' · giật '+fmt(gust,0):'')+'</span>'+
    '</article>';
  }).join("");
  if(worst?.state.cls==="avoid"){
    summary.textContent="Có khung giờ nên né: khoảng "+phuQuocClock(worst.r.t)+". Nếu có kế hoạch ngoài trời, nên chọn mốc thuận lợi hơn ở timeline.";
  }else if(worst?.state.cls==="watch"){
    summary.textContent=(good?"Vẫn còn "+good+" mốc khá thuận lợi. ":"")+"Có thời điểm mưa hoặc gió tăng - xem các ô màu vàng trước khi sắp lịch.";
  }else{
    summary.textContent="Các mốc còn lại hôm nay nhìn chung khá thuận lợi cho hoạt động ngoài trời.";
  }
}

function renderDecisionGlance(){
  const p=point(),l=p.local||{},m=p.marine||{},n=effectiveNowcast();
  const temp=num(l.temperature_c??m.temperature_c);
  const rain=num(l.rain_rate_mm_h);
  const conv=num(n.convective_score??l.convection_score);
  const wind=num(l.wind_kmh??m.wind_kmh);
  const wave=num(l.wave_hs_m??m.wave_hs_m);
  const place=$("decisionPlaceNote");if(place)place.textContent=(p.name||"Điểm đang chọn")+" · ưu tiên thông tin dễ hiểu";

  let skyKind="sun",skyTone="good",skyText="Trời tương đối ổn định tại điểm đang chọn.";
  if((rain||0)>=1){skyKind="rain";skyTone=(rain||0)>=5?"warn":"watch";skyText="Đang có mưa - xem radar trước khi di chuyển xa."}
  else if((conv||0)>=70){skyKind="cloud";skyTone="watch";skyText="Mây đối lưu đang hoạt động - thời tiết có thể đổi nhanh."}
  else if((conv||0)>=45){skyKind="cloud";skyTone="neutral";skyText="Có mây phát triển quanh khu vực, vẫn nên để ý Quick Alert."}
  setDecisionTile("sky",skyKind,temp===null?"Chưa rõ":fmt(temp,1)+"°C",skyText,skyTone);

  if(rain===null)setDecisionTile("rain","cloud","Chưa rõ","Chưa có số mưa đủ mới tại điểm này.","neutral");
  else if(rain<0.1)setDecisionTile("rain","cloud","Chưa thấy mưa đáng kể","Có thể tiếp tục kế hoạch, vẫn để ý Quick Alert.","good");
  else if(rain<1)setDecisionTile("rain","rain","Mưa rất nhẹ","Mang áo mưa mỏng nếu đi xa.","neutral");
  else if(rain<5)setDecisionTile("rain","rain","Đang có mưa","Nên xem radar trước khi di chuyển.","watch");
  else setDecisionTile("rain","rain","Mưa khá mạnh","Ưu tiên chỗ trú và kiểm tra radar trước khi đi tiếp.","warn");

  if(wind===null)setDecisionTile("wind","wind","Chưa rõ","Chưa có số gió đủ mới tại điểm này.","neutral");
  else if(wind<12)setDecisionTile("wind","wind","Gió nhẹ · "+fmt(wind,0)+" km/h","Đi lại và hoạt động ngoài trời nhìn chung dễ chịu.","good");
  else if(wind<20)setDecisionTile("wind","wind","Có gió · "+fmt(wind,0)+" km/h","Ngoài trời vẫn ổn, hoạt động biển nên xem thêm gió giật.","neutral");
  else if(wind<30)setDecisionTile("wind","wind","Gió khá mạnh · "+fmt(wind,0)+" km/h","Đi biển/cano nên xem thêm gió giật và cảnh báo.","watch");
  else setDecisionTile("wind","wind","Gió mạnh · "+fmt(wind,0)+" km/h","Cần kiểm tra cảnh báo trước các hoạt động ngoài trời và trên biển.","warn");

  if(wave===null)setDecisionTile("sea","wave","Chưa rõ","Chưa có trạng thái sóng đủ mới tại điểm này.","neutral");
  else if(wave<0.5)setDecisionTile("sea","wave","Biển khá êm · "+fmt(wave,1)+" m","Sóng nền thấp tại điểm mô hình gần nhất.","good");
  else if(wave<1)setDecisionTile("sea","wave","Sóng thấp · "+fmt(wave,1)+" m","Đi biển nên xem thêm gió giật và Hmax nếu cần.","neutral");
  else if(wave<1.5)setDecisionTile("sea","wave","Có sóng · "+fmt(wave,1)+" m","Hoạt động cano/biển nên xem kỹ cảnh báo ngắn hạn.","watch");
  else setDecisionTile("sea","wave","Sóng cao · "+fmt(wave,1)+" m","Cần thận trọng với hoạt động trên biển.","warn");
}

function renderCurrent(){
  const l=localPoint(),m=modelPoint(),n=point().nowcast||{};
  setMetric("windNow",l.wind_kmh??m.wind_kmh,1);setBadge("windClass",l.wind_class||"MODEL_ONLY");
  setMetric("gustNow",m.gust_kmh,1);
  setMetric("rainNow",l.rain_rate_mm_h,2);
  $("rainConfidence").textContent=num(l.rain_confidence)===null?"-":Math.round(l.rain_confidence*100);
  setBadge("rainClass",l.available?(l.rain_class||"ESTIMATED_NOW"):"MODEL_ONLY");
  $("convectiveNow").textContent=num(n.convective_score??l.convection_score)===null?"-":Math.round(num(n.convective_score??l.convection_score));
  setMetric("waveNow",l.wave_hs_m??m.wave_hs_m,2);setBadge("marineClass",l.marine_class||"MODEL_ONLY");
  setMetric("hmaxNow",m.wave_hmax_m,2);
  setMetric("periodNow",m.period_s,1);
  setMetric("currentNow",m.current_kmh,2);
}

function renderActual(){
  const a=critical.actual||{},v=a.vvpq||{},g=a.rain_gauges||[],cards=[];
  cards.push('<article class="actual-card"><header><b>VVPQ</b><em class="badge actual">ĐO THỰC</em></header><strong>'+fmt(v.temperature_c,1)+'°C</strong><small>Gió '+fmt(v.wind_kmh,1)+' km/h · '+(v.weather?esc(v.weather)+' · ':'')+ageText(v.observed_at)+'</small></article>');
  g.forEach(x=>{
    const win=num(x.increment_min),inc=num(x.increment_mm),rate=num(x.rain_intensity_mm_h),acc=num(x.accum_mm);
    let observed="CHƯA CÓ DỮ LIỆU HIỆN TẠI";
    let detail="Không đủ dữ liệu mới để xác định trạng thái mưa.";

    if(x.rain_observed===true){
      observed="CÓ MƯA";
      detail="Lượng mưa "+fmt(inc,2)+" mm / "+fmt(win,0)+" phút";
      if(rate!==null)detail+=" · cường độ "+fmt(rate,2)+" mm/h";
    }else if(x.rain_observed===false){
      observed="KHÔNG MƯA";
      detail="Không ghi nhận thêm lượng mưa trong "+fmt(win,0)+" phút gần nhất.";
    }else if(acc===0){
      observed="KHÔNG MƯA";
      detail="VRain hiện ghi 0 mm trong kỳ quan trắc.";
    }else if(acc!==null&&acc>0){
      observed="ĐÃ CÓ MƯA TRONG KỲ";
      detail="Tổng kỳ "+fmt(acc,1)+" mm · chưa đủ hai mẫu gần nhau để kết luận đang mưa ngay lúc này.";
    }

    if(acc!==null&&x.rain_observed!==true&&!(acc>0&&x.rain_observed===null))detail+=" · tổng kỳ "+fmt(acc,1)+" mm";
    cards.push('<article class="actual-card rain-actual"><header><b>'+esc(x.name)+'</b><em class="badge actual">ĐO THỰC</em></header><strong>'+observed+'</strong><small>'+detail+'</small></article>');
  });
  $("actualStrip").innerHTML=cards.join("");
  $("actualState").textContent=(critical.source_state?.vvpq==="FRESH"&&critical.source_state?.vrain==="FRESH")?"VVPQ + VRain vừa cập nhật":"Có nguồn cập nhật chậm";
}

function renderFeedbackPoint(){
  const sel=$("feedbackPoint");if(!sel)return;
  const ids=(critical.island_watch_order||[]).filter(id=>critical.points?.[id]);
  const prev=sel.value;
  sel.innerHTML=ids.map(id=>'<option value="'+esc(id)+'">'+esc(critical.points[id]?.name||id)+'</option>').join("");
  const desired=ids.includes(current)?current:(ids.includes(prev)?prev:"duong_dong");
  sel.value=desired;
}

function aqiLabel(cat){
  const map={GOOD:"Tốt",MODERATE:"Trung bình",UNHEALTHY_FOR_SENSITIVE_GROUPS:"Không tốt cho nhóm nhạy cảm",UNHEALTHY:"Không tốt",VERY_UNHEALTHY:"Rất không tốt",HAZARDOUS:"Nguy hại"};
  return map[cat]||cat||"Chưa xác định";
}
function effectiveAQI(){
  const compact=point().aqi||{};
  if(!fullAQI)return compact;
  const p=fullAQI.points?.[current]||{};
  return {
    status:fullAQI.status,
    sampled_time:p.sampled_time||fullAQI.sampled_time,
    aqi_us:p.aqi_us,
    category:p.category,
    aqi_source:p.aqi_source,
    source_city:p.source_city||p.iqair_city,
    pm25_ugm3:p.pm25_ugm3,
    pm10_ugm3:p.pm10_ugm3,
    model_aqi_us:p.model_aqi_us,
    divergence:p.source_divergence_aqi
  };
}
function renderAQI(){
  const a=effectiveAQI();
  if(num(a.aqi_us)===null&&num(a.pm25_ugm3)===null&&num(a.pm10_ugm3)===null){
    $("aqiQuick").innerHTML='<div class="data-empty"><b>ĐANG CHỜ DỮ LIỆU AQI</b><span>Điểm này chưa có số AQI trong bản dữ liệu hiện tại.</span></div>';
    setBadge("aqiSourceBadge","UNAVAILABLE","CHƯA CÓ");
    $("aqiAge").textContent="Không nội suy AQI từ điểm khác để lấp số.";
    return;
  }
  $("aqiQuick").innerHTML=
    '<div class="quick-item"><span>US AQI</span><b>'+fmt(a.aqi_us,0)+'</b><small>'+esc(aqiLabel(a.category))+'</small></div>'+
    '<div class="quick-item"><span>PM2.5</span><b>'+fmt(a.pm25_ugm3,1)+'</b><small>µg/m³ · CAMS tham chiếu</small></div>'+
    '<div class="quick-item"><span>PM10</span><b>'+fmt(a.pm10_ugm3,1)+'</b><small>µg/m³ · CAMS tham chiếu</small></div>'+
    '<div class="quick-item"><span>AQI CAMS</span><b>'+fmt(a.model_aqi_us,0)+'</b><small>mô hình tham chiếu</small></div>'+
    '<div class="quick-item"><span>Chênh lệch AQI</span><b>'+fmt(a.divergence,0)+'</b><small>IQAir - CAMS</small></div>'+
    '<div class="quick-item"><span>Điểm tham chiếu</span><b class="small-value">'+esc(a.source_city||"-")+'</b><small>'+esc(a.aqi_source||"-")+'</small></div>';
  setBadge("aqiSourceBadge",a.aqi_source==="IQAIR_COMMUNITY_REALTIME"?"ACTUAL":"MODEL_ONLY",a.aqi_source==="IQAIR_COMMUNITY_REALTIME"?"IQAIR TRỰC TIẾP":"CAMS");
  $("aqiAge").textContent="AQI cập nhật "+ageText(a.sampled_time)+". 0-50: tốt · 51-100: trung bình · trên 100: bắt đầu đáng lưu ý. Khi chưa có phép đo PM2.5/PM10 phù hợp, hệ thống dùng CAMS làm nguồn tham chiếu.";
}

function effectiveTide(){
  const compact=point().tide||{};
  if(!fullTide)return compact;
  const p=fullTide.points?.[current]||{};
  return {
    status:p.status||fullTide.status,
    generated_at:fullTide.generated_at,
    height_m:p.current_height_m,
    current_time:p.current_time,
    trend:p.trend,
    range_24h_m:p.range_24h_m,
    next_high:p.next_high?{type:p.next_high.type,time:p.next_high.time_iso,height_m:p.next_high.height_m}:null,
    next_low:p.next_low?{type:p.next_low.type,time:p.next_low.time_iso,height_m:p.next_low.height_m}:null,
    next_turn:p.next_turn?{type:p.next_turn.type,time:p.next_turn.time_iso,height_m:p.next_turn.height_m}:null,
    source:fullTide.source,
    series:p.series||[]
  };
}
function tideTrend(v){return v==="RISING"?"Đang lên":v==="FALLING"?"Đang xuống":v==="TURNING"?"Đang đổi nước":"-"}
function renderTide(){
  const t=effectiveTide();
  if(num(t.height_m)===null&&!t.next_high&&!t.next_low){
    $("tideQuick").innerHTML='<div class="data-empty"><b>ĐANG CHỜ DỮ LIỆU TRIỀU</b><span>Chưa có dữ liệu triều phù hợp cho khu vực này trong lần cập nhật hiện tại.</span></div>';
    $("tideAge").textContent="Triều luôn giữ nhãn MÔ HÌNH, không thay bằng số từ điểm khác.";
    drawTide([]);
    return;
  }
  $("tideQuick").innerHTML=
    '<div class="quick-item"><span>Mực triều</span><b>'+fmt(t.height_m,2)+' m</b><small>'+esc(tideTrend(t.trend))+'</small></div>'+
    '<div class="quick-item"><span>Triều cao kế</span><b>'+localTime(t.next_high?.time)+'</b><small>'+fmt(t.next_high?.height_m,2)+' m</small></div>'+
    '<div class="quick-item"><span>Triều thấp kế</span><b>'+localTime(t.next_low?.time)+'</b><small>'+fmt(t.next_low?.height_m,2)+' m</small></div>'+
    '<div class="quick-item"><span>Đổi nước</span><b>'+localTime(t.next_turn?.time)+'</b><small>'+esc(t.next_turn?.type||"-")+'</small></div>'+
    '<div class="quick-item"><span>Biên độ 24h</span><b>'+fmt(t.range_24h_m,2)+' m</b><small>cao nhất - thấp nhất</small></div>'+
    '<div class="quick-item"><span>Nguồn</span><b class="small-value">'+esc(t.source||"FES2014")+'</b><small>không phải trạm triều</small></div>';
  $("tideAge").textContent="Triều mô hình cập nhật "+ageText(t.generated_at||t.current_time)+". Không dùng thay mực nước hải đồ cảng.";
  drawTide(t.series||[]);
}
function drawTide(series){
  const svg=$("tideSpark");if(!svg)return;
  if(!series||series.length<2){svg.innerHTML='<text x="300" y="65" text-anchor="middle" fill="#8b9ba5" font-size="10">Chuỗi triều 24h đang tải nền...</text>';return}
  const now=Date.now(),rows=series.filter(r=>{const tt=Date.parse(r.time_iso);return Number.isFinite(tt)&&tt>=now-3600000&&tt<=now+24*3600000});
  const vals=rows.map(r=>num(r.height_m)).filter(v=>v!==null);
  if(vals.length<2){svg.innerHTML='<text x="300" y="65" text-anchor="middle" fill="#8b9ba5" font-size="10">Không đủ chuỗi triều</text>';return}
  const min=Math.min(...vals),max=Math.max(...vals),span=Math.max(.05,max-min);
  const pts=rows.map((r,i)=>{const x=15+i*(570/Math.max(1,rows.length-1)),y=105-(num(r.height_m)-min)/span*85;return x.toFixed(1)+","+y.toFixed(1)}).join(" ");
  svg.innerHTML='<line x1="15" y1="105" x2="585" y2="105" class="tide-base-v2"/><polyline points="'+pts+'" class="tide-line-v2"/>';
}

function effectiveNowcast(){
  const c=point().nowcast||{};
  if(!fullNowcast)return c;
  const p=fullNowcast.points?.[current]||{};
  if(String(fullNowcast.schema_version||"").includes("compact")){
    return {
      status:fullNowcast.status,
      sampled_time:fullNowcast.sampled_time,
      source:fullNowcast.source,
      cloud_top_cold_c:p.cold_cloud_top_temp_c,
      cloud_top_high_m:p.high_cloud_top_height_m,
      cooling_c_per_20m:p.cooling_c_per_20m_proxy,
      convective_score:p.score,
      convective_level:p.level,
      lightning:p.lightning_observed||fullNowcast.lightning_observed?.status,
      cloud_motion:p.cloud_motion||null
    };
  }
  const sig=p.convective_signal||{};
  return {
    status:fullNowcast.status,
    sampled_time:fullNowcast.sampled_time,
    source:fullNowcast.source,
    cloud_top_cold_c:p.regional_cold_cloud_top_temp_c,
    cloud_top_high_m:p.regional_high_cloud_top_height_m,
    cooling_c_per_20m:p.cooling_c_per_20m_proxy,
    convective_score:sig.score,
    convective_level:sig.level,
    lightning:p.lightning_observed||fullNowcast.lightning_observed?.status,
    cloud_motion:p.cloud_motion||null
  };
}
function renderMapConvective(){
  const n=effectiveNowcast();
  const score=$("mapConvectiveScore"),cloud=$("mapCloudTop"),cool=$("mapCooling");
  if(score)score.textContent=num(n.convective_score)===null?"-":fmt(n.convective_score,0)+"/100";
  if(cloud)cloud.textContent=num(n.cloud_top_cold_c)===null?"-":fmt(n.cloud_top_cold_c,1)+"°C";
  if(cool)cool.textContent=num(n.cooling_c_per_20m)===null?"-":fmt(n.cooling_c_per_20m,1)+"°C";
}

function ensembleData(){
  return point().ensemble||{};
}
function forecastBand(prob){
  prob=num(prob);
  if(prob===null)return "chưa đủ dữ liệu";
  if(prob>=0.50)return "cao";
  if(prob>=0.25)return "vừa";
  if(prob>=0.10)return "thấp đến vừa";
  return "thấp";
}
function forecastCardState(windProb,rainProb){
  windProb=num(windProb)||0;rainProb=num(rainProb)||0;
  if(windProb>=0.25||rainProb>=0.50)return {label:"CẦN THEO DÕI",cls:"watch"};
  if(windProb>=0.10||rainProb>=0.25)return {label:"CÓ DAO ĐỘNG",cls:"variable"};
  return {label:"KHÁ ỔN ĐỊNH",cls:"stable"};
}
function regionRows(){
  return regionalForecast?.regions?.[currentRegion]?.rows||[];
}
function regionMeta(){
  return regionalForecast?.regions?.[currentRegion]||null;
}
function renderForecastRegionTabs(){
  const nav=$("forecastRegionTabs");if(!nav)return;
  const regions=regionalForecast?.regions||{};
  nav.innerHTML=Object.entries(regions).map(([id,r])=>
    '<button class="'+(id===currentRegion?'active':'')+'" data-region="'+esc(id)+'">'+esc(r.name||id)+'</button>'
  ).join("")||'<span class="inline-loader">Đang chờ dữ liệu vùng...</span>';
}
function phuQuocDay(iso){
  const d=new Date(iso);
  if(!Number.isFinite(d.getTime()))return null;
  const parts=new Intl.DateTimeFormat("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",year:"numeric",month:"2-digit",day:"2-digit",weekday:"short"}).formatToParts(d);
  const get=t=>parts.find(x=>x.type===t)?.value||"";
  return {key:get("year")+"-"+get("month")+"-"+get("day"),label:get("weekday"),date:get("day")+"/"+get("month")};
}
function worstConfidence(values){
  const rank={"THẬN TRỌNG":3,"TRUNG BÌNH":2,"KHÁ":1};
  return values.sort((a,b)=>(rank[b]||0)-(rank[a]||0))[0]||"-";
}
function renderForecastDayRibbon(rows){
  const root=$("forecastDayRibbon");if(!root)return;
  const groups=new Map();
  rows.forEach(r=>{
    const day=phuQuocDay(r.valid_time);if(!day)return;
    if(!groups.has(day.key))groups.set(day.key,{day,rows:[]});
    groups.get(day.key).rows.push(r);
  });
  const days=[...groups.values()].slice(0,10);
  root.innerHTML=days.map(({day,rows},index)=>{
    const temps=rows.map(r=>num(r.temperature_c)).filter(v=>v!==null);
    const winds=rows.map(r=>num(r.wind_kmh)).filter(v=>v!==null);
    const rainProb=Math.max(0,...rows.map(r=>num(r.rain_prob_5)).filter(v=>v!==null));
    const windProb=Math.max(0,...rows.map(r=>num(r.wind_prob_30)).filter(v=>v!==null));
    const windMax=winds.length?Math.max(...winds):null;
    const state=forecastCardState(windProb,rainProb);
    let kind="sun",rainText="Ít tín hiệu mưa",summary="Khá ổn để lên kế hoạch.";
    if(rainProb>=.65){kind="rain";rainText="Dễ có mưa";summary="Nên chừa phương án linh hoạt vì có tín hiệu mưa đáng kể."}
    else if(rainProb>=.40){kind="rain";rainText="Có mưa từng lúc";summary="Có thể có mưa trong ngày, nên xem lại gần giờ đi."}
    else if(rainProb>=.20){kind="cloud";rainText="Có thể có mưa";summary="Nhìn chung vẫn có khoảng thời gian thuận lợi."}
    if(windProb>=.35&&rainProb<.40){kind="wind";summary="Gió có thể tăng - hoạt động biển nên kiểm tra lại gần ngày."}
    if(windProb>=.35&&rainProb>=.40){kind="storm";summary="Mưa và gió cùng có tín hiệu tăng - lịch ngoài trời nên linh hoạt."}
    const windText=windMax===null?"Gió chưa rõ":windMax>=30?"Gió mạnh":windMax>=22?"Gió tăng":windMax>=14?"Có gió":"Gió nhẹ";
    const trend=index>=4;
    return '<article class="forecast-day '+state.cls+'">'+
      '<header><div><b>'+esc(day.label)+'</b><span>'+esc(day.date)+'</span></div><em>'+(trend?'Xu hướng':'Chi tiết hơn')+'</em></header>'+
      '<div class="forecast-day-visual">'+weatherGlyph(kind)+'</div>'+
      '<strong>'+(temps.length?fmt(Math.min(...temps),0)+'-'+fmt(Math.max(...temps),0)+'°':'-')+'</strong>'+
      '<p>'+esc(summary)+'</p>'+
      '<div class="forecast-day-facts"><span>'+esc(rainText)+'</span><span>'+esc(windText)+(windMax===null?'':' · '+fmt(windMax,0)+' km/h')+'</span></div>'+
      (trend?'<small>Xem lại gần ngày đi để quyết định chính xác hơn.</small>':'<small>3 ngày đầu có nhiều mốc thời gian hơn.</small>')+
    '</article>';
  }).join("")||'<span class="inline-loader">Chưa đủ dữ liệu để tóm tắt 10 ngày.</span>';
}

function renderQuickAlert(){
  const root=$("quickAlert"),title=$("quickAlertTitle"),text=$("quickAlertText"),time=$("quickAlertTime");
  if(!root||!title||!text||!time)return;

  const nowSignals=islandIds().map(id=>{
    const p=critical?.points?.[id]||{},live=fullNowcast?.points?.[id]||{};
    const score=num(live.score??live.convective_signal?.score??p.nowcast?.convective_score??p.local?.convection_score)||0;
    return {name:p.name||id,score};
  }).sort((a,b)=>b.score-a.score);
  const strongestNow=nowSignals[0];

  const candidates=[];
  Object.values(regionalForecast?.regions||{}).forEach(region=>{
    (region.rows||[]).forEach(row=>{
      const lead=num(row.lead_hours);
      if(lead===null||lead<0||lead>12)return;
      const rain=num(row.rain_prob_5)||0;
      const wind=num(row.wind_prob_30)||0;
      const variability=rowVariability(row)/100;
      const hazard=Math.max(rain,wind);
      if(rain>=.25||wind>=.15||variability>=.45)candidates.push({region:region.name||"Phú Quốc",row,rain,wind,variability,hazard});
    });
  });
  candidates.sort((a,b)=>(a.row.lead_hours-b.row.lead_hours)||(b.hazard-a.hazard)||(b.variability-a.variability));

  let cls="neutral",headline="Chưa thấy tín hiệu thời tiết đáng ngại trong 12 giờ tới";
  let detail="Bạn vẫn nên nhìn Quick Alert lại trước khi đi xa hoặc ra biển.";
  let when="12 GIỜ";

  if(strongestNow&&strongestNow.score>=70){
    cls="alert";
    headline="Mây đối lưu đang mạnh ở "+strongestNow.name;
    detail="Nên xem radar trước khi đi xa hoặc ra biển. Đây là tín hiệu vệ tinh, chưa phải xác nhận mưa tại chỗ.";
    when="0-3 GIỜ";
  }else if(candidates.length){
    const x=candidates[0],drivers=[];
    const rainHaz=x.rain>=.25,windHaz=x.wind>=.15;
    if(rainHaz)drivers.push(x.rain>=.50?"khả năng mưa đáng kể cao":"có khả năng mưa");
    if(windHaz)drivers.push(x.wind>=.25?"có khả năng gió mạnh":"gió có thể tăng");
    if(!rainHaz&&!windHaz&&x.variability>=.45)drivers.push("dự báo còn dao động");
    cls=(x.rain>=.50||x.wind>=.25)?"alert":"watch";
    headline=cls==="alert"?"Thời tiết có thể xấu đi trong vài giờ tới":"Thời tiết có thể thay đổi trong vài giờ tới";
    detail=x.region+" · "+drivers.join(" · ")+" · khoảng "+leadMoment(x.row)+".";
    when="+"+fmt(x.row.lead_hours,0)+" GIỜ";
  }else if(strongestNow&&strongestNow.score>=50){
    cls="watch";
    headline="Mây đối lưu đang phát triển ở "+strongestNow.name;
    detail="Chưa đủ để nâng cảnh báo, nhưng nên kiểm tra radar nếu chuẩn bị đi xa.";
    when="0-3 GIỜ";
  }

  root.className="quick-alert "+cls;
  const icon=$("quickAlertIcon");if(icon)icon.innerHTML=weatherGlyph(cls==="alert"?"rain":cls==="watch"?"cloud":"sun");
  const radar=$("quickAlertRadar");if(radar)radar.hidden=cls==="neutral";
  title.textContent=headline;
  text.textContent=detail;
  time.textContent=when;
}

function renderJoTripForecast(){
  const title=$("jotripForecastTitle");
  const body=$("jotripForecastRows");
  const meta=regionMeta();
  const rows=regionRows();
  const cal=regionalForecast?.calibration_status||point().ensemble?.calibration_status||"LEARNING";
  setBadge("ensembleState",cal,viCal(cal));

  if(title)title.textContent=(regionalForecast?.horizon_hours>=240?"10 ngày tới":"Dự báo hiện có")+" - "+(meta?.name||"theo vùng");

  if(!regionalForecast||!meta){
    if(body)body.innerHTML='<tr><td colspan="9"><span class="inline-loader">Đang tải dự báo JoTrip theo vùng...</span></td></tr>';
    $("jotripForecastSummary").textContent="Dự báo 10 ngày được tải sau để phần thời tiết hiện tại luôn mở nhanh.";
    $("ensembleMeta").textContent="Đang chờ sản phẩm dự báo vùng.";
    return;
  }

  renderForecastRegionTabs();
  renderForecastDayRibbon(rows);
  const metaBox=$("forecastRegionMeta");
  if(metaBox)metaBox.innerHTML='<b>'+esc(meta.name)+'</b><span>Điểm đại diện: '+esc((meta.points||[]).join(" · "))+'</span>';

  if(!rows.length){
    body.innerHTML='<tr><td colspan="9"><div class="data-empty"><b>CHƯA ĐỦ DỮ LIỆU 10 NGÀY</b><span>Vùng này chưa có đủ dữ liệu dự báo tổ hợp để công bố.</span></div></td></tr>';
    $("jotripForecastSummary").textContent="JoTrip không lấy dự báo nguyên bản của một mô hình để lấp vào khi dữ liệu tổng hợp chưa đủ.";
    $("ensembleMeta").textContent="Dự báo JoTrip chưa sẵn sàng.";
    const ribbon=$("forecastDayRibbon");if(ribbon)ribbon.innerHTML='<span class="inline-loader">Chưa đủ dữ liệu để tóm tắt 10 ngày.</span>';
    return;
  }

  let watch=0;
  const detailOpen=!!$("forecastTechnical")?.open;
  if(detailOpen&&body){
    body.innerHTML=rows.map(r=>{
    const state=forecastCardState(r.wind_prob_30,r.rain_prob_5);
    const variation=variationLevel({spread:r.wind_spread},{spread:r.rain_spread});
    if(state.cls==="watch"||variation.score>=3)watch++;
    const bft=beaufort(r.wind_kmh);
    const driver=[r.risk_driver?.rain,r.risk_driver?.wind].filter(Boolean);
    const driverText=[...new Set(driver)].join(" / ")||"-";
    return '<tr class="'+state.cls+'">'+
      '<td><b>'+esc(r.valid_time?localTime(r.valid_time):("+"+fmt(r.lead_hours,0)+" giờ"))+'</b><small>+'+fmt(r.lead_hours,0)+' giờ</small></td>'+
      '<td>'+fmt(r.temperature_c,1)+'°C</td>'+
      '<td><b>'+fmt(r.wind_kmh,1)+' km/h</b><small>'+(num(r.wind_q10_kmh)!==null?'P10-P90 '+fmt(r.wind_q10_kmh,1)+'-'+fmt(r.wind_q90_kmh,1)+' km/h':'P90 '+fmt(r.wind_q90_kmh,1)+' km/h')+'</small></td>'+
      '<td><b>Bft '+bft.force+'</b><small>'+esc(bft.label)+'</small></td>'+
      '<td><b>'+pct(r.rain_prob_5)+'</b><small>'+forecastBand(r.rain_prob_5)+'</small></td>'+
      '<td><b>'+pct(r.wind_prob_30)+'</b><small>≥30 km/h · '+forecastBand(r.wind_prob_30)+'</small></td>'+
      '<td><b>'+rowVariability(r)+'/100</b><small>'+variation.label.toLowerCase()+'</small></td>'+
      '<td><b>'+rowConfidence(r)+'/100</b><small>'+esc((r.confidence_band||"-").toLowerCase())+'</small></td>'+
      '<td>'+esc(driverText)+'</td>'+
    '</tr>';
  }).join("");
  }else{
    rows.forEach(r=>{const state=forecastCardState(r.wind_prob_30,r.rain_prob_5),variation=variationLevel({spread:r.wind_spread},{spread:r.rain_spread});if(state.cls==="watch"||variation.score>=3)watch++});
    if(body)body.innerHTML='<tr><td colspan="9"><span class="inline-loader">Mở “Xem bảng dự báo chi tiết” để tải phần kỹ thuật.</span></td></tr>';
  }

  const horizon=regionalForecast.horizon_hours||0;
  $("jotripForecastSummary").textContent=(horizon>=240
    ? "Ba ngày đầu dùng nhiều mốc hơn để bạn chọn thời gian. Từ ngày 4 đến ngày 10 chỉ nên xem như xu hướng. "
    : "Dữ liệu hiện có khoảng "+Math.round(horizon/24)+" ngày. ")+
    (watch?"Có một số thời điểm mưa hoặc gió cần để ý - xem từng ngày bên dưới. ":"")+
    "Chọn khu vực bạn sẽ ở để xem đúng phần đảo, thay vì lấy Dương Đông làm chuẩn cho toàn Phú Quốc.";

  $("ensembleMeta").textContent="Dự báo JoTrip theo vùng · dữ liệu đầy đủ "+
    (num(regionalForecast.ensemble_completion_ratio)===null?"-":Math.round(regionalForecast.ensemble_completion_ratio*100)+"%")+
    " · "+viCal(regionalForecast.calibration_status||"LEARNING").toLowerCase()+
    " · càng xa ngày càng giảm độ tin cậy.";
}

function publicSourceName(key){
  const names={
    ECMWF:"ECMWF",
    GEFS:"NOAA GEFS",
    ICON:"ICON",
    COPERNICUS:"Copernicus Marine",
    RADAR_LIGHTNING:"Radar và sét",
    VVPQ:"Quan trắc VVPQ",
    VRAIN:"Mưa đo VRain",
    HIMAWARI:"Himawari",
    AQI:"Chất lượng không khí",
    TRIỀU:"Thủy triều"
  };
  return names[key]||key;
}
function renderHealth(){
  const src=critical.sources||{};
  const stLabel=st=>({PASS:"Sẵn sàng",PARTIAL:"Một phần",FAIL:"Chưa sẵn sàng",UNRESOLVED:"Chưa kết nối"}[st]||st.replaceAll("_"," ").toLowerCase());
  $("sourceGrid").innerHTML=Object.entries(src).map(([k,v])=>{
    const st=String(v.status||"UNRESOLVED").toUpperCase();
    const cls=st==="PASS"?"pass":st==="PARTIAL"?"partial":"fail";
    return '<article class="source-card"><header><b>'+esc(publicSourceName(k))+'</b><span class="source-state '+cls+'">'+esc(stLabel(st))+'</span></header><p>'+esc(v.detail||"")+'</p></article>';
  }).join("")||'<div class="lazy-status">Chưa có thông tin tình trạng nguồn.</div>';
  $("gapGrid").innerHTML=(critical.gaps||[]).length?(critical.gaps||[]).map(g=>'<div class="gap-card"><b>'+esc(g.name||"Phần còn thiếu")+'</b><span>'+esc(g.detail||"")+'</span></div>').join(""):'<div class="gap-card"><b>Không có khoảng trống nghiêm trọng</b><span>Chu kỳ hiện tại chưa ghi nhận lớp dữ liệu bắt buộc bị thiếu.</span></div>';
  $("cycleGrid").innerHTML=Object.entries(critical.source_cycles||{}).map(([k,v])=>'<span class="cycle-chip">'+esc(k)+' · '+localTime(v)+'</span>').join("");
  const headline=String(critical.headline||"").includes("Live D0-D10")?"Các nguồn đầu vào đã cập nhật. Trang chỉ công bố Dự báo JoTrip đã tổng hợp, không hiển thị riêng dự báo nguyên bản của từng mô hình.":(critical.headline||"-");
  const next=String(critical.next_review||"").includes("watch cycle")?"Trang public làm mới dữ liệu khoảng mỗi 10 phút; mô hình nặng cập nhật theo chu kỳ nguồn.":(critical.next_review||"-");
  $("auditGrid").innerHTML=
    '<div class="audit-item"><span>Mã lần cập nhật</span><b>'+esc(critical.snapshot_id||"-")+'</b></div>'+
    '<div class="audit-item"><span>Mã phiên bản</span><b>'+esc(critical.git_commit_sha||"-")+'</b></div>'+
    '<div class="audit-item wide"><span>Tóm tắt hệ thống</span><b>'+esc(headline)+'</b></div>'+
    '<div class="audit-item wide"><span>Lần kiểm tra tiếp</span><b>'+esc(next)+'</b></div>';
}

function renderAll(){
  if(!critical)return;
  renderPointTabs();renderStatus();renderHero();renderDecisionGlance();renderTodayTimeline();renderMapConvective();renderQuickAlert();
  renderJoTripForecast();
  if($("deepWeatherDetails")?.open){
    renderCurrent();renderActual();renderFeedbackPoint();renderAQI();renderTide();
  }
  if($("dataHealthDetails")?.open)renderHealth();
}

async function loadAQI(){
  try{fullAQI=await getFirst(AQI);renderAQI()}catch(e){console.warn("[Weather V2] AQI",e)}
}
async function loadTide(){
  try{fullTide=await getFirst(TIDE);renderTide()}catch(e){
    console.warn("[Weather V2] tide",e);
    const el=$("tideSpark");if(el)el.innerHTML='<text x="300" y="65" text-anchor="middle" fill="#8b9ba5" font-size="10">Chưa tải được chuỗi triều 24h</text>';
  }
}
async function loadNowcast(){
  try{
    fullNowcast=await getFirst(NOWCAST);
    renderMapConvective();renderDecisionGlance();renderStatus();renderQuickAlert();
    if($("deepWeatherDetails")?.open)renderCurrent();
  }catch(e){console.warn("[Weather V2] nowcast",e)}
}
async function loadRegionalForecast(){
  try{
    regionalForecast=await getJSON(JOTRIP_FORECAST);
    const ids=Object.keys(regionalForecast.regions||{});
    if(!ids.includes(currentRegion))currentRegion=ids[0]||currentRegion;
    renderJoTripForecast();renderStatus();renderQuickAlert();
  }catch(e){
    console.warn("[Weather V2] regional forecast",e);
    $("jotripForecastRows").innerHTML='<tr><td colspan="9"><div class="data-empty"><b>CHƯA TẢI ĐƯỢC DỰ BÁO VÙNG</b><span>Phần quan trắc hiện tại vẫn hoạt động bình thường.</span></div></td></tr>';
  }
}

function mapCandidates(){
  const now=new Date(),base=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate(),now.getUTCHours(),Math.floor(now.getUTCMinutes()/10)*10);
  return Array.from({length:12},(_,i)=>{
    const d=new Date(base-(i+2)*600000),hh=String(d.getUTCHours()).padStart(2,"0"),mm=String(d.getUTCMinutes()).padStart(2,"0");
    return JMA+"ha1_b13_"+hh+mm+".jpg";
  });
}
function setMap(type){
  mapLayer=type;
  document.querySelectorAll("[data-map]").forEach(b=>b.classList.toggle("active",b.dataset.map===type));
  if(!mapStarted)return;
  const box=$("mapBox"),note=$("mapNote");
  $("mapState").textContent="ĐANG TẢI";$("mapState").className="badge deferred";
  if(type==="himawari"){
    box.innerHTML='<img id="himawariImg" alt="JMA Himawari B13 infrared">';
    const img=$("himawariImg"),list=mapCandidates();let i=0;
    img.onerror=()=>{i++;if(i<list.length)img.src=list[i]+"?t="+Date.now();else{note.textContent="Không tải được ảnh Himawari trực tiếp lúc này.";$("mapState").textContent="KHÔNG TẢI ĐƯỢC"}};
    img.onload=()=>{note.textContent="Ảnh hồng ngoại Himawari gần nhất từ JMA.";$("mapState").textContent="SẴN SÀNG";$("mapState").className="badge remote"};
    img.src=list[0]+"?t="+Date.now();
    return;
  }
  box.innerHTML='<iframe title="Weather map" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';
  const frame=box.firstChild;
  frame.onload=()=>{$("mapState").textContent="SẴN SÀNG";$("mapState").className=type==="radar"?"badge remote":"badge model"};
  frame.src=WINDY[type]||WINDY.radar;
  const notes={
    radar:"Radar giúp nhìn vùng mưa đang xuất hiện quanh đảo. Lượng mưa tại từng điểm vẫn được kiểm tra bằng các nguồn riêng.",
    wind:"Gió giúp nhìn hướng và vùng gió mạnh yếu quanh Phú Quốc. Đây là lớp tham khảo không gian; Dự báo JoTrip vẫn là dự báo chính của trang.",
    rain:"Mưa dự báo giúp nhìn khu vực có khả năng xuất hiện mưa trong thời gian tới. Lớp này không thay số đo VRain hoặc Dự báo JoTrip.",
    waves:"Sóng giúp nhìn sự khác nhau của trạng thái biển quanh đảo. Đây là lớp tham khảo từ ECMWF Waves."
  };
  note.textContent=notes[type]||notes.radar;
}

function startMap(){
  if(mapStarted)return;
  mapStarted=true;
  setMap(mapLayer);
}
function installMapObserver(){
  const target=document.querySelector(".map-panel");
  if(!target)return;
  if(!("IntersectionObserver" in window)){defer(startMap,1800);return}
  const ob=new IntersectionObserver(entries=>{
    if(entries.some(e=>e.isIntersecting)){startMap();ob.disconnect()}
  },{rootMargin:"350px 0px"});
  ob.observe(target);
}

async function sendFeedbackRemote(item){
  const response=await fetch(FEEDBACK_ENDPOINT,{
    method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify(item),
    cache:"no-store",
    keepalive:true
  });
  if(!response.ok)throw new Error("feedback_http_"+response.status);
  let body={};
  try{body=await response.json()}catch{}
  return body;
}
function readFeedbackQueue(){
  try{
    const q=JSON.parse(localStorage.getItem(FEEDBACK_QUEUE_KEY)||"[]");
    return Array.isArray(q)?q:[];
  }catch{return []}
}
function writeFeedbackQueue(q){
  localStorage.setItem(FEEDBACK_QUEUE_KEY,JSON.stringify((q||[]).slice(-100)));
}
function saveFeedbackHistory(item){
  let h=[];
  try{h=JSON.parse(localStorage.getItem(FEEDBACK_HISTORY_KEY)||"[]")}catch{}
  if(!Array.isArray(h))h=[];
  h.push(item);
  try{localStorage.setItem(FEEDBACK_HISTORY_KEY,JSON.stringify(h.slice(-100)))}catch{}
  return h.length;
}
function queueFeedback(item){
  const q=readFeedbackQueue();
  if(!q.some(x=>x?.id===item.id))q.push(item);
  try{writeFeedbackQueue(q)}catch{}
  return q.length;
}
function dequeueFeedback(id){
  const q=readFeedbackQueue().filter(x=>x?.id!==id);
  try{writeFeedbackQueue(q)}catch{}
  return q.length;
}
function feedbackMessage(message,kind="ok"){
  const state=$("feedbackState"),toast=$("feedbackToast");
  if(state)state.textContent=message;
  if(toast){
    toast.textContent=message;
    toast.classList.remove("error");
    if(kind==="error")toast.classList.add("error");
    toast.classList.add("show");
    clearTimeout(feedbackMessage._timer);
    feedbackMessage._timer=setTimeout(()=>toast.classList.remove("show","error"),2800);
  }
}
async function flushFeedbackQueue(){
  const q=readFeedbackQueue();
  if(!q.length)return {sent:0,pending:0};
  let sent=0;
  for(const item of q){
    try{
      await sendFeedbackRemote(item);
      dequeueFeedback(item.id);
      sent++;
    }catch(e){
      console.warn("[Weather V2] feedback retry",e);
      break;
    }
  }
  return {sent,pending:readFeedbackQueue().length};
}
async function feedback(kind,button){
  const feedbackPoint=$("feedbackPoint")?.value||current;
  const p=critical?.points?.[feedbackPoint]||point(),l=p.local||{};
  const labels={
    MATCH:"Khớp",
    RAIN_MORE:"Mưa nhiều hơn",
    RAIN_LESS:"Mưa ít hơn",
    WIND_MORE:"Gió mạnh hơn",
    WIND_LESS:"Gió yếu hơn",
    THUNDER:"Có dông"
  };
  const item={
    schema_version:"1.2",
    id:(globalThis.crypto&&crypto.randomUUID)?crypto.randomUUID():String(Date.now()),
    observed_at:new Date().toISOString(),
    point_id:feedbackPoint,
    point_name:p.name||feedbackPoint,
    category:kind,
    category_label:labels[kind]||kind,
    evidence_class:"FIELD_FEEDBACK_UNVERIFIED",
    accepted_as_ground_truth:false,
    engine:critical?.source_state?.local_engine||"PQ_LOCAL_NOW_V1",
    snapshot_id:critical?.snapshot_id||null,
    source_cycles:critical?.source_cycles||null,
    estimate:{
      temperature_c:l.temperature_c,
      wind_kmh:l.wind_kmh,
      rain_rate_mm_h:l.rain_rate_mm_h,
      rain_confidence:l.rain_confidence,
      wave_hs_m:p?.marine?.wave_hs_m??null
    }
  };

  saveFeedbackHistory(item);
  const pending=queueFeedback(item);

  document.querySelectorAll("[data-feedback]").forEach(b=>b.classList.toggle("selected",b===button));
  if(button){
    button.setAttribute("aria-pressed","true");
    setTimeout(()=>{button.classList.remove("selected");button.removeAttribute("aria-pressed")},1600);
  }
  if(navigator.vibrate)navigator.vibrate(25);

  feedbackMessage("Đang gửi phản hồi về JoTrip...");
  try{
    await sendFeedbackRemote(item);
    const left=dequeueFeedback(item.id);
    feedbackMessage("Đã gửi về JoTrip · "+(labels[kind]||kind)+" · "+(p.name||feedbackPoint)+(left?" · còn "+left+" phản hồi chờ gửi":""));
    flushFeedbackQueue();
  }catch(e){
    console.warn("[Weather V2] feedback send",e);
    feedbackMessage("Đã lưu trên thiết bị · sẽ tự gửi lại khi có mạng ("+pending+" chờ gửi)");
  }
}
function shareWeather(){
  const data={title:"JoTrip Weather - Phú Quốc",text:"Theo dõi thời tiết hiện tại, biển, chất lượng không khí và Dự báo JoTrip 10 ngày cho Phú Quốc.",url:location.href};
  if(navigator.share){navigator.share(data).catch(()=>{})}
  else if(navigator.clipboard){navigator.clipboard.writeText(location.href).then(()=>{const b=$("shareWeather");if(b)b.textContent="Đã sao chép link"})}
}
function events(){
  $("pointTabs")?.addEventListener("click",e=>{
    const b=e.target.closest("[data-point]");if(!b)return;
    current=b.dataset.point;
    const linkedRegion=regionForPoint(current);if(linkedRegion)currentRegion=linkedRegion;
    renderAll();
  });
  document.querySelectorAll("[data-map]").forEach(b=>b.addEventListener("click",()=>{startMap();setMap(b.dataset.map)}));
  $("forecastRegionTabs")?.addEventListener("click",e=>{
    const b=e.target.closest("[data-region]");if(!b)return;
    currentRegion=b.dataset.region;renderJoTripForecast();
  });
  document.addEventListener("click",e=>{
    const b=e.target.closest("[data-feedback]");
    if(!b)return;
    e.preventDefault();
    feedback(b.dataset.feedback,b);
  });
  $("forecastTechnical")?.addEventListener("toggle",e=>{if(e.currentTarget.open)renderJoTripForecast()});
  $("deepWeatherDetails")?.addEventListener("toggle",e=>{if(e.currentTarget.open)loadDeepData()});
  $("dataHealthDetails")?.addEventListener("toggle",e=>{if(e.currentTarget.open)renderHealth()});
  $("shareWeather")?.addEventListener("click",shareWeather);
}

function registerWeatherWorker(){
  if(!("serviceWorker" in navigator))return;
  navigator.serviceWorker.register("/Jotrip-Lab/weather/weather-sw.js",{scope:"/Jotrip-Lab/weather/"}).catch(e=>console.warn("[Weather] service worker",e));
}
async function refreshLive(){
  if(liveRefreshBusy)return;
  liveRefreshBusy=true;
  try{
    const next=await getJSON(CRITICAL);
    critical=next;
    if(!critical?.points?.[current])current=critical.default_point||"duong_dong";
    lastLiveRefreshAt=Date.now();
    renderAll();
    await loadNowcast();
  }catch(e){
    console.warn("[Weather V2] live refresh",e);
    renderStatus();
    setTimeout(()=>{if(document.visibilityState==="visible")refreshLive()},60000);
  }finally{
    liveRefreshBusy=false;
  }
}
async function loadDeepData(){
  renderCurrent();renderActual();renderFeedbackPoint();renderAQI();renderTide();
  await Promise.allSettled([loadTide(),loadAQI()]);
}
async function refreshSlow(){
  lastSlowRefreshAt=Date.now();
  const jobs=[loadRegionalForecast()];
  if($("deepWeatherDetails")?.open)jobs.push(loadTide(),loadAQI());
  await Promise.allSettled(jobs);
}

async function boot(){
  registerWeatherWorker();
  events();
  try{
    critical=await getJSON(CRITICAL);
    current=critical.default_point||"duong_dong";
    currentRegion=regionForPoint(current)||currentRegion;
    lastLiveRefreshAt=Date.now();
    lastSlowRefreshAt=Date.now();
    renderAll();
    installMapObserver();
    defer(loadNowcast,160);
    defer(loadRegionalForecast,260);
    setInterval(()=>{renderStatus();renderHero();renderDecisionGlance();renderTodayTimeline()},60000);
    setInterval(refreshLive,LIVE_REFRESH_MS);
    setInterval(refreshSlow,SLOW_REFRESH_MS);
    document.addEventListener("visibilitychange",()=>{
      if(document.visibilityState==="visible"&&Date.now()-lastLiveRefreshAt>5*60*1000)refreshLive();
      if(document.visibilityState==="visible"&&Date.now()-lastSlowRefreshAt>30*60*1000)refreshSlow();
    });
    window.addEventListener("online",()=>{
      if(Date.now()-lastLiveRefreshAt>2*60*1000)refreshLive();
      flushFeedbackQueue();
    });
    setTimeout(flushFeedbackQueue,1800);
    setInterval(flushFeedbackQueue,5*60*1000);
  }catch(e){
    $("heroSummary").textContent="Không tải được dữ liệu ban đầu. Bạn thử tải lại trang giúp mình.";
    $("liveLabel").textContent="LỖI DỮ LIỆU";$("liveDot").className="warn";
    console.error(e);
  }
}
boot();
})();