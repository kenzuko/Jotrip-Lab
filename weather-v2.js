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
const defer=(fn,ms=600)=>setTimeout(()=>{"requestIdleCallback" in window?requestIdleCallback(()=>fn(),{timeout:900}):fn()},ms);

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
    (p.next24h||[]).length>=3,
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
  const fresh=clamp(1-ageMinutes(critical.generated_at)/180,0,1);
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
  if(windProb>=0.25){level=Math.max(level,2);reasons.push("ensemble còn đuôi gió mạnh")}
  else if(windProb>=0.10){level=Math.max(level,1)}
  if(rainProb>=0.50){level=Math.max(level,2);reasons.push("ensemble nghiêng về mưa")}
  else if(rainProb>=0.25){level=Math.max(level,1)}
  return {level,reasons};
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
  const stale=m>180,delayed=m>90;
  $("liveDot").className=stale||delayed?"warn":"ok";
  $("liveLabel").textContent=(stale?"DỮ LIỆU CŨ":delayed?"CẬP NHẬT CHẬM":critical.report_status==="LIVE"?"ĐANG HOẠT ĐỘNG":"SUY GIẢM")+" · "+ageText(critical.generated_at);

  const assessment=islandAssessment();
  const coverage=coverageScore();
  const confidence=confidenceScore();
  $("decisionNow").textContent=assessment.label;
  $("completenessNow").textContent=coverage+"% · "+islandIds().length+"/"+islandIds().length+" điểm";
  $("confidenceNow").textContent=(confidence>=80?"CAO":confidence>=60?"KHÁ":"THẤP")+" · "+confidence+"/100";
  $("horizonNow").textContent=num(critical.forecast_horizon_hours)===null?"-":"D+"+Math.round(critical.forecast_horizon_hours/24);
  $("completenessNow").parentElement.title="Tỷ lệ các lớp Local Now, forecast, AQI, triều, Himawari và ensemble đang có dữ liệu trên 7 điểm đảo.";
  $("confidenceNow").parentElement.title="Điểm chất lượng gói dữ liệu hiện tại, không phải xác suất dự báo đúng.";
  const summary=$("islandSummary");
  if(summary){
    if(assessment.attention.length){
      summary.innerHTML="<b>Cần chú ý:</b> "+assessment.attention.map(x=>esc(x.p.name)+" - "+esc(x.risk.reasons.slice(0,2).join(", "))).join(" · ")+"<small>Đánh giá thời tiết tham khảo. Hạn chế/cấm tàu thuyền vẫn theo thông báo chính thức.</small>";
    }else{
      summary.innerHTML="<b>Toàn đảo:</b> chưa thấy lớp dữ liệu hiện có vượt ngưỡng theo dõi chính.<small>Tin cậy dữ liệu không đồng nghĩa dự báo chắc chắn đúng.</small>";
    }
  }
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
    $("aqiQuick").innerHTML='<div class="data-empty"><b>CHỜ CYCLE AQI</b><span>Điểm này chưa có số AQI trong snapshot hiện tại.</span></div>';
    setBadge("aqiSourceBadge","UNAVAILABLE","CHƯA CÓ");
    $("aqiAge").textContent="Không nội suy AQI từ điểm khác để lấp số.";
    return;
  }
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
  if(num(t.height_m)===null&&!t.next_high&&!t.next_low){
    $("tideQuick").innerHTML='<div class="data-empty"><b>CHỜ CYCLE TRIỀU</b><span>Chưa có ô lưới triều hợp lệ cho điểm này trong snapshot hiện tại.</span></div>';
    $("tideAge").textContent="Triều luôn giữ nhãn MODEL, không thay bằng số từ điểm khác.";
    drawTide([]);
    return;
  }
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
  const n=effectiveNowcast(),root=$("nowcastQuick"),preview=$("satellitePreview");
  if(num(n.convective_score)===null&&num(n.cloud_top_cold_c)===null&&num(n.cloud_top_high_m)===null){
    root.innerHTML='<div class="data-empty"><b>CHƯA CÓ DỮ LIỆU HIMAWARI</b><span>Điểm này chưa có cửa sổ quan sát vệ tinh trong chu kỳ hiện tại.</span></div>';
    $("nowcastAge").textContent="Không dùng forecast để thay thế quan sát vệ tinh.";
    if(preview)preview.hidden=true;
    return;
  }
  const cards=[];
  if(num(n.convective_score)!==null)cards.push('<div class="quick-item"><span>Mức đối lưu</span><b>'+fmt(n.convective_score,0)+'/100</b><small>'+esc(viLevel(n.convective_level))+'</small></div>');
  if(num(n.cloud_top_cold_c)!==null)cards.push('<div class="quick-item"><span>Đỉnh mây lạnh nhất</span><b>'+fmt(n.cloud_top_cold_c,1)+'°C</b><small>quan sát hồng ngoại</small></div>');
  if(num(n.cloud_top_high_m)!==null)cards.push('<div class="quick-item"><span>Đỉnh mây cao</span><b>'+fmt(num(n.cloud_top_high_m)/1000,1)+' km</b><small>cửa sổ khu vực</small></div>');
  if(num(n.cooling_c_per_20m)!==null)cards.push('<div class="quick-item"><span>Biến thiên 20 phút</span><b>'+fmt(n.cooling_c_per_20m,1)+'°C</b><small>âm = đỉnh mây lạnh thêm</small></div>');
  if(n.lightning&&String(n.lightning).toUpperCase()!=="NOT_CONNECTED")cards.push('<div class="quick-item"><span>Sét quan sát</span><b class="small-value">'+esc(n.lightning)+'</b><small>nguồn sét trực tiếp</small></div>');
  root.innerHTML=cards.join("");
  $("nowcastAge").textContent="Himawari quan sát "+ageText(n.sampled_time)+" · "+esc(n.source||"JMA Himawari")+". Đây là quan sát vệ tinh, không phải trạm mưa.";
  if(preview){preview.hidden=false;installSatellitePreviewObserver()}
}

let satellitePreviewStarted=false;
function startSatellitePreview(){
  if(satellitePreviewStarted)return;satellitePreviewStarted=true;
  const box=$("satellitePreview"),img=$("nowcastImage"),cap=$("nowcastImageCaption");
  if(!box||!img)return;
  const list=mapCandidates();let i=0;
  img.onerror=()=>{i++;if(i<list.length){img.src=list[i]+"?t="+Date.now()}else{box.hidden=true;img.onerror=null}};
  img.onload=()=>{
    box.hidden=false;
    if(cap)cap.textContent="Ảnh Himawari B13 quan sát thực tế gần nhất từ JMA. Màu tối/sáng là bức xạ hồng ngoại, không phải ảnh màu tự nhiên.";
  };
  img.src=list[0]+"?t="+Date.now();
}
function installSatellitePreviewObserver(){
  const target=$("satellitePreview");if(!target||satellitePreviewStarted)return;
  if(!("IntersectionObserver" in window)){defer(startSatellitePreview,1000);return}
  const ob=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){startSatellitePreview();ob.disconnect()}},{rootMargin:"250px 0px"});
  ob.observe(target);
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
  setBadge("ensembleState",e.calibration_status||"LEARNING",viCal(e.calibration_status||"LEARNING"));
  if(!rows.length){
    $("ensembleQuick").innerHTML='<div class="lazy-status">Chưa có đủ ma trận ensemble cho điểm này. Dự báo mô hình phía trên vẫn hoạt động.</div>';
    $("ensembleMeta").textContent=esc(e.source||"NOAA GEFS")+" · "+(e.status==="UNAVAILABLE"?"chưa sẵn sàng":"đang cập nhật");
    return;
  }
  const selected=rows.filter(r=>[6,12,24,48,72].includes(Number(r.lead_hours))).slice(0,5);
  $("ensembleQuick").innerHTML='<table class="ensemble-table"><thead><tr><th>Mốc</th><th>Thành viên</th><th>Gió q50</th><th>Gió q90</th><th>P(gió≥30)</th><th>Mưa q50</th><th>Mưa q90</th><th>P(mưa≥5)</th></tr></thead><tbody>'+
    selected.map(r=>{
      const vars=r.variables||{};
      const w=vars.wind?.corrected||vars.wind?.raw||r.wind||{};
      const rain=vars.rain?.corrected||vars.rain?.raw||r.rain||{};
      const members=r.member_count??w.member_count??r.members;
      return '<tr><td>+'+fmt(r.lead_hours,0)+' giờ</td><td>'+fmt(members,0)+'</td><td>'+ensembleCell(w,"q50",0)+'</td><td>'+ensembleCell(w,"q90",0)+'</td><td>'+pct(w.exceedance_probability??w.prob)+'</td><td>'+ensembleCell(rain,"q50",1)+'</td><td>'+ensembleCell(rain,"q90",1)+'</td><td>'+pct(rain.exceedance_probability??rain.prob)+'</td></tr>';
    }).join("")+'</tbody></table>';
  $("ensembleMeta").textContent=(e.source||"ensemble")+" · chu kỳ "+localTime(e.run_time)+" · hoàn tất "+(num(e.completion_ratio)===null?"-":Math.round(e.completion_ratio*100)+"%")+" · hiệu chỉnh: "+viCal(e.calibration_status||"LEARNING").toLowerCase();
}

function pct(v){v=num(v);return v===null?"-":Math.round(v*100)+"%"}

function renderHealth(){
  const src=critical.sources||{};
  const stLabel=st=>({PASS:"Sẵn sàng",PARTIAL:"Một phần",FAIL:"Chưa sẵn sàng",UNRESOLVED:"Chưa kết nối"}[st]||st.replaceAll("_"," ").toLowerCase());
  $("sourceGrid").innerHTML=Object.entries(src).map(([k,v])=>{
    const st=String(v.status||"UNRESOLVED").toUpperCase();
    const cls=st==="PASS"?"pass":st==="PARTIAL"?"partial":"fail";
    return '<article class="source-card"><header><b>'+esc(k)+'</b><span class="source-state '+cls+'">'+esc(stLabel(st))+'</span></header><p>'+esc(v.detail||"")+'</p></article>';
  }).join("")||'<div class="lazy-status">Chưa có thông tin tình trạng nguồn.</div>';
  $("gapGrid").innerHTML=(critical.gaps||[]).length?(critical.gaps||[]).map(g=>'<div class="gap-card"><b>'+esc(g.name||"Phần còn thiếu")+'</b><span>'+esc(g.detail||"")+'</span></div>').join(""):'<div class="gap-card"><b>Không có khoảng trống nghiêm trọng</b><span>Chu kỳ hiện tại chưa ghi nhận lớp dữ liệu bắt buộc bị thiếu.</span></div>';
  $("cycleGrid").innerHTML=Object.entries(critical.source_cycles||{}).map(([k,v])=>'<span class="cycle-chip">'+esc(k)+' · '+localTime(v)+'</span>').join("");
  const headline=String(critical.headline||"").includes("Live D0-D10")?"Dữ liệu D0-D10 đã cập nhật. D4-D10 dùng để theo dõi xu hướng, không tự phát quyết định vận hành.":(critical.headline||"-");
  const next=String(critical.next_review||"").includes("watch cycle")?"Hệ thống tự kiểm tra chu kỳ mô hình mới mỗi 30 phút.":(critical.next_review||"-");
  $("auditGrid").innerHTML=
    '<div class="audit-item"><span>Mã ảnh chụp dữ liệu</span><b>'+esc(critical.snapshot_id||"-")+'</b></div>'+
    '<div class="audit-item"><span>Mã phiên bản</span><b>'+esc(critical.git_commit_sha||"-")+'</b></div>'+
    '<div class="audit-item wide"><span>Tóm tắt hệ thống</span><b>'+esc(headline)+'</b></div>'+
    '<div class="audit-item wide"><span>Lần kiểm tra tiếp</span><b>'+esc(next)+'</b></div>';
}

function renderAll(){
  if(!critical)return;
  renderPointTabs();renderStatus();renderHero();renderCurrent();renderActual();renderFeedbackPoint();renderAQI();renderTide();renderNowcast();
  renderHours(point().next24h||[]);renderForecastTable();renderEnsemble();renderHealth();
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
  $("mapState").textContent="ĐANG TẢI";$("mapState").className="badge deferred";
  if(type==="himawari"){
    box.innerHTML='<img id="himawariImg" alt="JMA Himawari B13 infrared">';
    const img=$("himawariImg"),list=mapCandidates();let i=0;
    img.onerror=()=>{i++;if(i<list.length)img.src=list[i]+"?t="+Date.now();else{note.textContent="Không tải được frame Himawari trực tiếp lúc này.";$("mapState").textContent="KHÔNG TẢI ĐƯỢC"}};
    img.onload=()=>{note.textContent="JMA Himawari B13 · ảnh quan sát vệ tinh gần nhất tải thành công.";$("mapState").textContent="SẴN SÀNG";$("mapState").className="badge remote"};
    img.src=list[0]+"?t="+Date.now();
    return;
  }
  box.innerHTML='<iframe title="Weather map" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';
  const frame=box.firstChild;
  frame.onload=()=>{$("mapState").textContent="SẴN SÀNG";$("mapState").className="badge remote"};
  frame.src=WINDY[type]||WINDY.radar;
  note.textContent=type==="radar"?"Radar dùng để nhìn vùng mưa theo không gian; số liệu tại điểm vẫn lấy từ pipeline riêng.":type==="wind"?"Windy/ECMWF giúp nhìn cấu trúc gió trên khu vực.":"Mưa dự báo giúp nhìn cấu trúc không gian; mưa đo thực tế vẫn ưu tiên VRain.";
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
  const data={title:"JoTrip Weather - Phú Quốc",text:"Theo dõi thời tiết, biển, AQI và ensemble riêng cho Phú Quốc.",url:location.href};
  if(navigator.share){navigator.share(data).catch(()=>{})}
  else if(navigator.clipboard){navigator.clipboard.writeText(location.href).then(()=>{const b=$("shareWeather");if(b)b.textContent="Đã sao chép link"})}
}
function events(){
  $("pointTabs")?.addEventListener("click",e=>{
    const b=e.target.closest("[data-point]");if(!b)return;
    current=b.dataset.point;renderAll();
  });
  document.querySelectorAll(".horizon-tabs button").forEach(b=>b.addEventListener("click",()=>{horizon=Number(b.dataset.horizon);renderForecastTable()}));
  document.querySelectorAll("[data-map]").forEach(b=>b.addEventListener("click",()=>{startMap();setMap(b.dataset.map)}));
  document.querySelectorAll("[data-feedback]").forEach(b=>b.addEventListener("click",()=>feedback(b.dataset.feedback)));
  $("shareWeather")?.addEventListener("click",shareWeather);
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
    if(critical.source_state?.ensemble&&critical.source_state.ensemble!=="UNAVAILABLE")defer(loadEnsemble,1350);
  }catch(e){
    $("heroSummary").textContent="Không tải được payload nhanh. Hãy thử tải lại trang.";
    $("liveLabel").textContent="LỖI DỮ LIỆU";$("liveDot").className="warn";
    console.error(e);
  }
}
boot();
})();