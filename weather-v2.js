(()=>{
"use strict";

const CRITICAL="/weather/critical.json";
const FULL="/weather/dashboard-data.json";
const TIDE="/weather/tide.json";
const AQI=["/data/weather-aqi/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-aqi/latest.json","/weather/air-quality.json"];
const ENSEMBLE=["/data/weather-ensemble/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-ensemble/latest.json"];
const NOWCAST=["/data/weather-nowcast/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-nowcast/latest.json","/weather/nowcast.json"];
const WINDY={
  radar:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1",
  wind:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
  rain:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=rain&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C"
};
const JMA="https://www.data.jma.go.jp/mscweb/data/himawari/img/ha1/";

const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const defer=(fn,ms=600)=>{"requestIdleCallback" in window?requestIdleCallback(()=>fn(),{timeout:ms+900}):setTimeout(fn,ms)};

let critical=null;
let current="duong_dong";
let horizon=72;
let full=null;
let fullAQI=null;
let fullTide=null;
let fullNowcast=null;
let fullEnsemble=null;
let mapStarted=false;
let mapLayer="radar";

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
  return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}):"-";
}
function hourLabel(iso){
  const d=new Date(iso);
  return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{weekday:"short",hour:"2-digit",minute:"2-digit",hour12:false}):"-";
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
  el.textContent=label||String(k||"-").replace("_NOW","").replaceAll("_"," ");
}
function setMetric(id,v,d){const el=$(id);if(el)el.textContent=num(v)===null?"-":fmt(v,d)}
function point(){return critical?.points?.[current]||{}}
function localPoint(){return point().local||{}}
function modelPoint(){return point().model||{}}

function renderStatus(){
  if(!critical)return;
  const m=ageMinutes(critical.generated_at);
  const stale=m>180,delayed=m>90;
  $("liveDot").className=stale||delayed?"warn":"ok";
  $("liveLabel").textContent=(stale?"STALE":delayed?"DELAYED":critical.report_status==="LIVE"?"LIVE":"DEGRADED")+" · "+ageText(critical.generated_at);
  $("decisionNow").textContent=String(critical.decision||"NOT_ISSUED").replaceAll("_"," ");
  $("completenessNow").textContent=num(critical.completeness)===null?"-":fmt(critical.completeness,0)+"%";
  $("confidenceNow").textContent=num(critical.confidence)===null?"-":fmt(critical.confidence,0)+"/100";
  $("horizonNow").textContent=num(critical.forecast_horizon_hours)===null?"-":"D+"+Math.round(critical.forecast_horizon_hours/24);
  $("dataMode").textContent=critical.data_mode||"-";
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
  const p=point(),l=p.local||{},m=p.model||{};
  $("placeName").textContent=p.name||current;
  const t=num(l.temperature_c)??num(m.temperature_c);
  $("heroTemp").textContent=t===null?"--":fmt(t,1)+"°";
  $("heroTempClass").textContent=l.available?"ESTIMATED":"MODEL";
  $("heroSummary").textContent=summary(p);
  $("updatedAt").textContent="Cập nhật "+localTime(critical.generated_at)+" · "+ageText(critical.generated_at);
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
  cards.push('<article class="actual-card"><header><b>VVPQ</b><em class="badge actual">ACTUAL</em></header><strong>'+fmt(v.temperature_c,1)+'°C</strong><small>Gió '+fmt(v.wind_kmh,1)+' km/h · '+(v.weather?esc(v.weather)+' · ':'')+ageText(v.observed_at)+'</small></article>');
  g.forEach(x=>cards.push('<article class="actual-card"><header><b>'+esc(x.name)+'</b><em class="badge actual">ACTUAL</em></header><strong>'+fmt(x.accum_mm,1)+' mm</strong><small>Tích lũy'+(num(x.increment_mm)!==null?' · +'+fmt(x.increment_mm,1)+' mm / '+fmt(x.increment_min,0)+' phút':'')+'</small></article>'));
  $("actualStrip").innerHTML=cards.join("");
  $("actualState").textContent=(critical.source_state?.vvpq==="FRESH"&&critical.source_state?.vrain==="FRESH")?"VVPQ + VRAIN FRESH":"CÓ NGUỒN CHẬM";
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
  $("aqiQuick").innerHTML=
    '<div class="quick-item"><span>US AQI</span><b>'+fmt(a.aqi_us,0)+'</b><small>'+esc(aqiLabel(a.category))+'</small></div>'+
    '<div class="quick-item"><span>PM2.5</span><b>'+fmt(a.pm25_ugm3,1)+'</b><small>µg/m³ · CAMS reference</small></div>'+
    '<div class="quick-item"><span>PM10</span><b>'+fmt(a.pm10_ugm3,1)+'</b><small>µg/m³ · CAMS reference</small></div>'+
    '<div class="quick-item"><span>AQI CAMS</span><b>'+fmt(a.model_aqi_us,0)+'</b><small>model reference</small></div>'+
    '<div class="quick-item"><span>Lệch nguồn</span><b>'+fmt(a.divergence,0)+'</b><small>IQAir - CAMS</small></div>'+
    '<div class="quick-item"><span>Điểm nguồn</span><b class="small-value">'+esc(a.source_city||"-")+'</b><small>'+esc(a.aqi_source||"-")+'</small></div>';
  setBadge("aqiSourceBadge",a.aqi_source==="IQAIR_COMMUNITY_REALTIME"?"ACTUAL":"MODEL_ONLY",a.aqi_source==="IQAIR_COMMUNITY_REALTIME"?"IQAIR LIVE":"CAMS");
  $("aqiAge").textContent="AQI cập nhật "+ageText(a.sampled_time)+". PM2.5/PM10 hiện là CAMS model trừ khi có feed observed riêng.";
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
  $("tideQuick").innerHTML=
    '<div class="quick-item"><span>Mực triều</span><b>'+fmt(t.height_m,2)+' m</b><small>'+esc(tideTrend(t.trend))+'</small></div>'+
    '<div class="quick-item"><span>Triều cao kế</span><b>'+localTime(t.next_high?.time)+'</b><small>'+fmt(t.next_high?.height_m,2)+' m</small></div>'+
    '<div class="quick-item"><span>Triều thấp kế</span><b>'+localTime(t.next_low?.time)+'</b><small>'+fmt(t.next_low?.height_m,2)+' m</small></div>'+
    '<div class="quick-item"><span>Đổi nước</span><b>'+localTime(t.next_turn?.time)+'</b><small>'+esc(t.next_turn?.type||"-")+'</small></div>'+
    '<div class="quick-item"><span>Biên độ 24h</span><b>'+fmt(t.range_24h_m,2)+' m</b><small>max - min model</small></div>'+
    '<div class="quick-item"><span>Nguồn</span><b class="small-value">'+esc(t.source||"FES2014")+'</b><small>không phải trạm triều</small></div>';
  $("tideAge").textContent="Triều model cập nhật "+ageText(t.generated_at||t.current_time)+". Không dùng như mực nước hải đồ cảng.";
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
function renderNowcast(){
  const n=effectiveNowcast();
  $("nowcastQuick").innerHTML=
    '<div class="quick-item"><span>Đối lưu</span><b>'+fmt(n.convective_score,0)+'/100</b><small>'+esc(n.convective_level||"-")+'</small></div>'+
    '<div class="quick-item"><span>Cloud-top lạnh</span><b>'+fmt(n.cloud_top_cold_c,1)+'°C</b><small>Himawari remote observed</small></div>'+
    '<div class="quick-item"><span>Cloud-top cao</span><b>'+fmt(num(n.cloud_top_high_m)/1000,1)+' km</b><small>p95 local window</small></div>'+
    '<div class="quick-item"><span>Cooling 20 phút</span><b>'+fmt(n.cooling_c_per_20m,1)+'°C</b><small>proxy growth/decay</small></div>'+
    '<div class="quick-item"><span>Sét trực tiếp</span><b class="small-value">'+esc(n.lightning||"NOT_CONNECTED")+'</b><small>không suy proxy thành lightning</small></div>'+
    '<div class="quick-item"><span>Nguồn</span><b class="small-value">'+esc(n.source||"HIMAWARI")+'</b><small>remote observed</small></div>';
  $("nowcastAge").textContent="Himawari sampled "+ageText(n.sampled_time)+". Đây là quan trắc vệ tinh, không phải rain gauge.";
}

function renderHours(rows){
  $("hourlyStrip").innerHTML=rows.length?rows.map(r=>
    '<article class="hour-card"><time>'+hourLabel(r.t)+'</time><strong>'+fmt(r.temp,0)+'°</strong><div class="hour-grid"><span>Gió</span><b>'+fmt(r.wind,0)+'</b><span>Giật</span><b>'+fmt(r.gust,0)+'</b><span>Mưa</span><b>'+fmt(r.rain,1)+'</b><span>Hs</span><b>'+fmt(r.wave,1)+'</b></div></article>'
  ).join(""):'<div class="lazy-status">Chưa có chuỗi 24 giờ.</div>';
}

function compactForecastRows(){
  return (point().next24h||[]).map(r=>({
    time_iso:r.t,temperature:r.temp,wind:r.wind,gust:r.gust,rain:r.rain,wave:r.wave,wave_max:r.hmax,period:r.period
  }));
}
function futureRows(rows,hours){
  const now=Date.now(),cut=now+hours*3600000;
  return (rows||[]).filter(r=>{const t=Date.parse(r.time_iso);return Number.isFinite(t)&&t>=now&&t<=cut}).sort((a,b)=>Date.parse(a.time_iso)-Date.parse(b.time_iso));
}
function detailRows(){
  if(!full)return compactForecastRows();
  const p=full.points?.[current]||{},limit=Math.min(horizon,168),rows=futureRows(p.hours||[],limit);
  if(horizon<=72)return rows;
  const near=Date.now()+72*3600000,out=[];let lastFar=0;
  for(const r of rows){
    const t=Date.parse(r.time_iso);
    if(t<=near){out.push(r);continue}
    if(!lastFar||t-lastFar>=5.5*3600000){out.push(r);lastFar=t}
  }
  return out;
}
function renderForecastTable(){
  const rows=detailRows();
  $("forecastRows").innerHTML=rows.length?rows.map(r=>
    '<tr><td>'+localTime(r.time_iso)+'</td><td>'+fmt(r.temperature,1)+'</td><td>'+fmt(r.wind,1)+'</td><td>'+fmt(r.gust,1)+'</td><td>'+fmt(r.rain,2)+'</td><td>'+fmt(r.wave,2)+'</td><td>'+fmt(r.wave_max,2)+'</td><td>'+fmt(r.period,1)+'</td></tr>'
  ).join(""):'<tr><td colspan="8">Chưa có dữ liệu forecast.</td></tr>';
  const available=full?Number(full.forecast_horizon_hours||72):24;
  document.querySelectorAll(".horizon-tabs button").forEach(b=>{const h=Number(b.dataset.horizon);b.disabled=!full&&h>72;b.classList.toggle("active",h===horizon);b.title=h>available?"Snapshot hiện tại chưa đủ horizon":""});
  renderOutlook();
}
function renderOutlook(){
  const root=$("outlookCards");
  if(horizon!==240){root.innerHTML="";return}
  const rows=(full?.points?.[current]?.daily_outlook||point().outlook||[]).filter(x=>{
    const d=Number(x.day_offset??x.d);return d>=8&&d<=10;
  });
  root.innerHTML=rows.length?rows.map(x=>{
    const d=x.day_offset??x.d;
    return '<article class="outlook-card"><header><b>D+'+d+'</b><time>'+esc(x.date||"-")+'</time></header><div class="outlook-card-grid"><div><span>Gió max</span><b>'+fmt(x.wind_max,0)+' km/h</b></div><div><span>Giật max</span><b>'+fmt(x.gust_max,0)+' km/h</b></div><div><span>Hs max</span><b>'+fmt(x.hs_max,1)+' m</b></div><div><span>Hmax</span><b>'+fmt(x.hmax_max,1)+' m</b></div><div><span>Mưa tổng</span><b>'+fmt(x.rain_total,1)+' mm</b></div></div></article>';
  }).join(""):'<div class="lazy-status">D+8-D+10 chưa có daily outlook.</div>';
}

function ensembleData(){
  if(fullEnsemble)return {
    status:fullEnsemble.status,
    source:fullEnsemble.source,
    run_time:fullEnsemble.run_time,
    completion_ratio:fullEnsemble.completion_ratio,
    calibration_status:fullEnsemble.calibration_status,
    rows:fullEnsemble.points?.[current]||[]
  };
  return point().ensemble||{};
}
function ensembleCell(v,key,d=1){return fmt(v?.[key],d)}
function renderEnsemble(){
  const e=ensembleData(),rows=e.rows||[];
  setBadge("ensembleState",e.calibration_status||"LEARNING",e.calibration_status||"LEARNING");
  if(!rows.length){
    $("ensembleQuick").innerHTML='<div class="lazy-status">Ensemble matrix đang xây. Forecast deterministic phía trên vẫn hoạt động bình thường.</div>';
    $("ensembleMeta").textContent=esc(e.source||"NOAA GEFS / multi-model pipeline")+" · "+esc(e.status||"UNAVAILABLE");
    return;
  }
  const selected=rows.filter(r=>[6,12,24,48,72].includes(Number(r.lead_hours))).slice(0,5);
  $("ensembleQuick").innerHTML='<table class="ensemble-table"><thead><tr><th>Lead</th><th>Members</th><th>Gió q50</th><th>Gió q90</th><th>P(gió≥30)</th><th>Mưa q50</th><th>Mưa q90</th><th>P(mưa≥5)</th></tr></thead><tbody>'+
    selected.map(r=>{
      const vars=r.variables||{};
      const w=vars.wind?.corrected||vars.wind?.raw||r.wind||{};
      const rain=vars.rain?.corrected||vars.rain?.raw||r.rain||{};
      const members=r.member_count??w.member_count??r.members;
      return '<tr><td>+'+fmt(r.lead_hours,0)+'h</td><td>'+fmt(members,0)+'</td><td>'+ensembleCell(w,"q50",0)+'</td><td>'+ensembleCell(w,"q90",0)+'</td><td>'+pct(w.exceedance_probability??w.prob)+'</td><td>'+ensembleCell(rain,"q50",1)+'</td><td>'+ensembleCell(rain,"q90",1)+'</td><td>'+pct(rain.exceedance_probability??rain.prob)+'</td></tr>';
    }).join("")+'</tbody></table>';
  $("ensembleMeta").textContent=(e.source||"ensemble")+" · run "+localTime(e.run_time)+" · completion "+(num(e.completion_ratio)===null?"-":Math.round(e.completion_ratio*100)+"%")+" · calibration "+(e.calibration_status||"LEARNING");
}
function pct(v){v=num(v);return v===null?"-":Math.round(v*100)+"%"}

function renderHealth(){
  const src=critical.sources||{};
  $("sourceGrid").innerHTML=Object.entries(src).map(([k,v])=>{
    const st=String(v.status||"UNRESOLVED").toUpperCase();
    const cls=st==="PASS"?"pass":st==="PARTIAL"?"partial":"fail";
    return '<article class="source-card"><header><b>'+esc(k)+'</b><span class="source-state '+cls+'">'+esc(st)+'</span></header><p>'+esc(v.detail||"")+'</p></article>';
  }).join("")||'<div class="lazy-status">Chưa có source health.</div>';
  $("gapGrid").innerHTML=(critical.gaps||[]).length?(critical.gaps||[]).map(g=>'<div class="gap-card"><b>'+esc(g.name||"Data gap")+'</b><span>'+esc(g.detail||"")+'</span></div>').join(""):'<div class="gap-card"><b>Không có critical gap</b><span>Cycle hiện tại không khai báo khoảng trống nghiêm trọng.</span></div>';
  $("cycleGrid").innerHTML=Object.entries(critical.source_cycles||{}).map(([k,v])=>'<span class="cycle-chip">'+esc(k)+' · '+localTime(v)+'</span>').join("");
}

function renderAll(){
  if(!critical)return;
  renderStatus();renderHero();renderCurrent();renderActual();renderAQI();renderTide();renderNowcast();
  renderHours(point().next24h||[]);renderForecastTable();renderEnsemble();renderHealth();
  document.querySelectorAll(".point-tabs button").forEach(b=>b.classList.toggle("active",b.dataset.point===current));
}

async function loadFullForecast(){
  try{full=await getJSON(FULL);renderForecastTable()}catch(e){console.warn("[Weather V2] full forecast",e)}
}
async function loadAQI(){
  try{fullAQI=await getFirst(AQI);renderAQI()}catch(e){console.warn("[Weather V2] AQI",e)}
}
async function loadTide(){
  try{fullTide=await getJSON(TIDE);renderTide()}catch(e){console.warn("[Weather V2] tide",e)}
}
async function loadNowcast(){
  try{fullNowcast=await getFirst(NOWCAST);renderNowcast();renderCurrent()}catch(e){console.warn("[Weather V2] nowcast",e)}
}
async function loadEnsemble(){
  try{fullEnsemble=await getFirst(ENSEMBLE);renderEnsemble()}catch(e){console.warn("[Weather V2] ensemble",e)}
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
  $("mapState").textContent="LOADING";$("mapState").className="badge deferred";
  if(type==="himawari"){
    box.innerHTML='<img id="himawariImg" alt="JMA Himawari B13 infrared">';
    const img=$("himawariImg"),list=mapCandidates();let i=0;
    img.onerror=()=>{i++;if(i<list.length)img.src=list[i]+"?t="+Date.now();else{note.textContent="Không tải được frame Himawari trực tiếp lúc này.";$("mapState").textContent="DEGRADED"}};
    img.onload=()=>{note.textContent="JMA Himawari B13 · remote observed · frame gần nhất tải thành công.";$("mapState").textContent="READY";$("mapState").className="badge remote"};
    img.src=list[0]+"?t="+Date.now();
    return;
  }
  box.innerHTML='<iframe title="Weather map" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';
  const frame=box.firstChild;
  frame.onload=()=>{$("mapState").textContent="READY";$("mapState").className="badge remote"};
  frame.src=WINDY[type]||WINDY.radar;
  note.textContent=type==="radar"?"Radar/map là lớp trực quan độc lập, không phải ground truth số.":type==="wind"?"Windy/ECMWF để nhìn cấu trúc gió không gian.":"Mưa forecast để nhìn cấu trúc dự báo, không thay VRain actual.";
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
  const p=point(),l=p.local||{},item={
    schema_version:"1.0",
    id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),
    at:new Date().toISOString(),
    point_id:current,
    category:kind,
    engine:critical?.source_state?.local_engine||"PQ_LOCAL_NOW_V1",
    estimate:{temperature_c:l.temperature_c,wind_kmh:l.wind_kmh,rain_rate_mm_h:l.rain_rate_mm_h,rain_confidence:l.rain_confidence}
  };
  let q=[];try{q=JSON.parse(localStorage.getItem("pq_weather_field_feedback_v1")||"[]")}catch{}
  if(!Array.isArray(q))q=[];q.push(item);q=q.slice(-100);
  try{localStorage.setItem("pq_weather_field_feedback_v1",JSON.stringify(q))}catch{}
  $("feedbackState").textContent="Đã lưu phản hồi trên thiết bị. Cảm ơn bạn.";
}

function events(){
  document.querySelectorAll(".point-tabs button").forEach(b=>b.addEventListener("click",()=>{current=b.dataset.point;renderAll()}));
  document.querySelectorAll(".horizon-tabs button").forEach(b=>b.addEventListener("click",()=>{horizon=Number(b.dataset.horizon);renderForecastTable()}));
  document.querySelectorAll("[data-map]").forEach(b=>b.addEventListener("click",()=>{startMap();setMap(b.dataset.map)}));
  document.querySelectorAll("[data-feedback]").forEach(b=>b.addEventListener("click",()=>feedback(b.dataset.feedback)));
}

async function boot(){
  events();
  try{
    critical=await getJSON(CRITICAL);
    current=critical.default_point||"duong_dong";
    renderAll();
    installMapObserver();
    defer(loadFullForecast,650);
    defer(loadAQI,850);
    defer(loadTide,1000);
    defer(loadNowcast,1150);
    defer(loadEnsemble,1350);
  }catch(e){
    $("heroSummary").textContent="Không tải được payload nhanh. Hãy thử tải lại trang.";
    $("liveLabel").textContent="DATA ERROR";$("liveDot").className="warn";
    console.error(e);
  }
}
boot();
})();