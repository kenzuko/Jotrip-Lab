(()=>{
"use strict";

const CRITICAL="/weather/critical.json";
const TIDE=["/weather/tide.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/tide.json"];
const AQI=["/data/weather-aqi/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-aqi/latest.json","/weather/air-quality.json"];
const NOWCAST=["/data/weather-nowcast/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-nowcast/latest.json","/weather/nowcast.json"];
const JOTRIP_FORECAST="/weather/jotrip-forecast.json";
const LIVE_REFRESH_MS=10*60*1000;
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
let mapStarted=false;
let mapLayer="radar";
let liveRefreshBusy=false;
let lastLiveRefreshAt=0;

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
  const fresh=clamp(1-ageMinutes(critical.generated_at)/90,0,1);
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
  const windLvl=probabilityLevel(wind?.val);
  const waves=points.map(x=>({name:x.p.name,hs:num(x.p.local?.wave_hs_m??x.p.model?.wave_hs_m)||0})).sort((a,b)=>b.hs-a.hs)[0];
  const windMeta=wind?"P(gió ≥30 km/h) · "+esc(wind.p.name)+" · "+leadMoment(wind.row)+(waves?.hs?" · Hs cao nhất "+fmt(waves.hs,1)+" m":""):"Chưa đủ dữ liệu tổ hợp";
  setHazard("hazardWind",wind?pct(wind.val):"-",windMeta,Math.max(windLvl.score,waves?.hs>=2?3:waves?.hs>=1.5?2:0));

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
  const m=ageMinutes(critical.generated_at);
  const stale=m>60,delayed=m>25;
  $("liveDot").className=stale||delayed?"warn":"ok";
  $("liveLabel").textContent=(stale?"DỮ LIỆU CŨ":delayed?"CẬP NHẬT CHẬM":critical.report_status==="LIVE"?"ĐANG HOẠT ĐỘNG":"SUY GIẢM")+" · "+ageText(critical.generated_at);

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
  $("updatedAt").textContent="Cập nhật "+localTime(critical.generated_at)+" · "+ageText(critical.generated_at);
  if($("scenePoint"))$("scenePoint").textContent=p.name||current;
  if($("sceneTemp"))$("sceneTemp").textContent=t===null?"--":fmt(t,1)+"°";
  if($("sceneUpdated"))$("sceneUpdated").textContent="JoTrip Local Now · "+ageText(critical.generated_at);
  const rain=num(l.rain_rate_mm_h)||0,conv=num(n.convective_score??l.convection_score)||0,wind=num(l.wind_kmh??m.wind_kmh)||0;
  const mood=(conv>=70||rain>=3)?"storm":(conv>=50||rain>=.5||wind>=28)?"watch":"calm";
  document.querySelector(".hero")?.setAttribute("data-mood",mood);
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
  g.forEach(x=>cards.push('<article class="actual-card"><header><b>'+esc(x.name)+'</b><em class="badge actual">ĐO THỰC</em></header><strong>'+fmt(x.accum_mm,1)+' mm</strong><small>Tích lũy'+(num(x.increment_mm)!==null?' · +'+fmt(x.increment_mm,1)+' mm / '+fmt(x.increment_min,0)+' phút':'')+'</small></article>'));
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
  const p=fullNowcast.points?.[current]||{},sig=p.convective_signal||{};
  return {
    status:fullNowcast.status,
    sampled_time:fullNowcast.sampled_time,
    source:fullNowcast.source,
    cloud_top_cold_c:p.regional_cold_cloud_top_temp_c,
    cloud_top_high_m:p.regional_high_cloud_top_height_m,
    cooling_c_per_20m:p.cooling_c_per_20m_proxy,
    convective_score:sig.score,
    convective_level:sig.level,
    lightning:p.lightning_observed||fullNowcast.lightning_observed?.status
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
  root.innerHTML=days.map(({day,rows})=>{
    const temps=rows.map(r=>num(r.temperature_c)).filter(v=>v!==null);
    const winds=rows.map(r=>num(r.wind_kmh)).filter(v=>v!==null);
    const rainProb=Math.max(0,...rows.map(r=>num(r.rain_prob_5)).filter(v=>v!==null));
    const windProb=Math.max(0,...rows.map(r=>num(r.wind_prob_30)).filter(v=>v!==null));
    const state=forecastCardState(windProb,rainProb);
    const bft=beaufort(winds.length?Math.max(...winds):0);
    const conf=worstConfidence(rows.map(r=>r.confidence_band).filter(Boolean));
    const confScore=Math.min(...rows.map(rowConfidence));
    return '<article class="forecast-day '+state.cls+'">'+
      '<header><b>'+esc(day.label)+'</b><span>'+esc(day.date)+'</span></header>'+
      '<strong>'+(temps.length?fmt(Math.min(...temps),0)+'-'+fmt(Math.max(...temps),0)+'°':'-')+'</strong>'+
      '<div><span>Mưa ≥5 mm</span><b>'+pct(rainProb)+'</b></div>'+
      '<div><span>Gió ≥30</span><b>'+pct(windProb)+' · Bft '+bft.force+'</b></div>'+
      '<small>Tin cậy '+confScore+'/100 · '+esc(conf)+'</small>'+
    '</article>';
  }).join("")||'<span class="inline-loader">Chưa đủ dữ liệu để tóm tắt 10 ngày.</span>';
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
      '<td><b>'+fmt(r.wind_kmh,0)+' km/h</b><small>q90 '+fmt(r.wind_q90_kmh,0)+'</small></td>'+
      '<td><b>Bft '+bft.force+'</b><small>'+esc(bft.label)+'</small></td>'+
      '<td><b>'+pct(r.rain_prob_5)+'</b><small>'+forecastBand(r.rain_prob_5)+'</small></td>'+
      '<td><b>'+pct(r.wind_prob_30)+'</b><small>'+forecastBand(r.wind_prob_30)+'</small></td>'+
      '<td><b>'+rowVariability(r)+'/100</b><small>'+variation.label.toLowerCase()+'</small></td>'+
      '<td><b>'+rowConfidence(r)+'/100</b><small>'+esc((r.confidence_band||"-").toLowerCase())+'</small></td>'+
      '<td>'+esc(driverText)+'</td>'+
    '</tr>';
  }).join("");

  const horizon=regionalForecast.horizon_hours||0;
  $("jotripForecastSummary").textContent=(horizon>=240
    ? "D0-D3 mỗi 6 giờ; D4-D10 mỗi 12 giờ. "
    : "Nguồn hiện tại mới đủ "+Math.round(horizon/24)+" ngày. ")+
    (watch?watch+" mốc trong vùng có rủi ro hoặc mức chênh giữa các kịch bản đáng theo dõi. ":"")+
    "Mỗi vùng được tổng hợp từ các điểm đại diện tại Phú Quốc, không lấy riêng Dương Đông làm chuẩn cho cả đảo.";

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
  renderPointTabs();renderStatus();renderHero();renderCurrent();renderActual();renderFeedbackPoint();renderAQI();renderTide();renderMapConvective();
  renderJoTripForecast();renderHealth();
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
  try{fullNowcast=await getFirst(NOWCAST);renderMapConvective();renderCurrent();renderStatus()}catch(e){console.warn("[Weather V2] nowcast",e)}
}
async function loadRegionalForecast(){
  try{
    regionalForecast=await getJSON(JOTRIP_FORECAST);
    const ids=Object.keys(regionalForecast.regions||{});
    if(!ids.includes(currentRegion))currentRegion=ids[0]||currentRegion;
    renderJoTripForecast();renderStatus();
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

function feedback(kind){
  const feedbackPoint=$("feedbackPoint")?.value||current;
  const p=critical?.points?.[feedbackPoint]||point(),l=p.local||{},item={
    schema_version:"1.0",
    id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),
    at:new Date().toISOString(),
    point_id:feedbackPoint,
    category:kind,
    engine:critical?.source_state?.local_engine||"PQ_LOCAL_NOW_V1",
    estimate:{temperature_c:l.temperature_c,wind_kmh:l.wind_kmh,rain_rate_mm_h:l.rain_rate_mm_h,rain_confidence:l.rain_confidence}
  };
  let q=[];try{q=JSON.parse(localStorage.getItem("pq_weather_field_feedback_v1")||"[]")}catch{}
  if(!Array.isArray(q))q=[];q.push(item);q=q.slice(-100);
  try{localStorage.setItem("pq_weather_field_feedback_v1",JSON.stringify(q))}catch{}
  $("feedbackState").textContent="Đã lưu phản hồi trên thiết bị. Cảm ơn bạn.";
}

function shareWeather(){
  const data={title:"JoTrip Weather - Phú Quốc",text:"Theo dõi thời tiết hiện tại, biển, chất lượng không khí và Dự báo JoTrip 10 ngày cho Phú Quốc.",url:location.href};
  if(navigator.share){navigator.share(data).catch(()=>{})}
  else if(navigator.clipboard){navigator.clipboard.writeText(location.href).then(()=>{const b=$("shareWeather");if(b)b.textContent="Đã sao chép link"})}
}
function events(){
  $("pointTabs")?.addEventListener("click",e=>{
    const b=e.target.closest("[data-point]");if(!b)return;
    current=b.dataset.point;renderAll();
  });
  document.querySelectorAll("[data-map]").forEach(b=>b.addEventListener("click",()=>{startMap();setMap(b.dataset.map)}));
  $("forecastRegionTabs")?.addEventListener("click",e=>{
    const b=e.target.closest("[data-region]");if(!b)return;
    currentRegion=b.dataset.region;renderJoTripForecast();
  });
  document.querySelectorAll("[data-feedback]").forEach(b=>b.addEventListener("click",()=>feedback(b.dataset.feedback)));
  $("shareWeather")?.addEventListener("click",shareWeather);
}

function registerWeatherWorker(){
  if(!("serviceWorker" in navigator))return;
  navigator.serviceWorker.register("/weather-sw.js",{scope:"/"}).catch(e=>console.warn("[Weather] service worker",e));
}
async function refreshLive(){
  if(liveRefreshBusy)return;
  liveRefreshBusy=true;
  try{
    const next=await getJSON(CRITICAL);
    critical=next;
    if(!critical?.points?.[current])current=critical.default_point||"duong_dong";
    renderAll();
    lastLiveRefreshAt=Date.now();
    await Promise.allSettled([loadTide(),loadAQI(),loadNowcast(),loadRegionalForecast()]);
  }catch(e){
    console.warn("[Weather V2] live refresh",e);
    renderStatus();
  }finally{
    liveRefreshBusy=false;
  }
}
async function boot(){
  registerWeatherWorker();
  events();
  try{
    critical=await getJSON(CRITICAL);
    current=critical.default_point||"duong_dong";
    lastLiveRefreshAt=Date.now();
    renderAll();
    installMapObserver();
    Promise.allSettled([loadTide(),loadAQI(),loadNowcast(),loadRegionalForecast()]);
    setInterval(()=>{renderStatus();renderHero()},60000);
    setInterval(refreshLive,LIVE_REFRESH_MS);
    document.addEventListener("visibilitychange",()=>{
      if(document.visibilityState==="visible"&&Date.now()-lastLiveRefreshAt>5*60*1000)refreshLive();
    });
  }catch(e){
    $("heroSummary").textContent="Không tải được dữ liệu ban đầu. Bạn thử tải lại trang giúp mình.";
    $("liveLabel").textContent="LỖI DỮ LIỆU";$("liveDot").className="warn";
    console.error(e);
  }
}
boot();
})();