(()=>{
"use strict";
const CRITICAL="/Jotrip-Lab/weather/data/critical.json",FULL="/Jotrip-Lab/weather/data/dashboard-data.json",TIDE="/Jotrip-Lab/weather/data/tide.json";
const AQ=["https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-aqi/latest.json","/Jotrip-Lab/weather/data/air-quality.json"];
const ENSEMBLE=["/Jotrip-Lab/weather/data/weather-ensemble/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-ensemble/latest.json"];
const WINDY={
 radar:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1",
 wind:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
 rain:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=rain&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C"
};
const JMA="https://www.data.jma.go.jp/mscweb/data/himawari/img/ha1/";
const $=id=>document.getElementById(id),num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
let critical=null,current="duong_dong",full=null,mapOpened=false,ensemble=null;

async function getJSON(url,opts={}){const sep=url.includes("?")?"&":"?",r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store",...opts});if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}
async function getFirst(urls){let last;for(const u of urls){try{return await getJSON(u)}catch(e){last=e}}throw last||new Error("unavailable")}
function badgeClass(k){k=String(k||"").toUpperCase();return k==="ACTUAL"?"actual":k==="ESTIMATED_NOW"?"estimated":k==="REMOTE_OBSERVED"?"remote":k==="MODEL_ONLY"?"model":"deferred"}
function age(iso){const t=Date.parse(iso||"");if(!Number.isFinite(t))return "-";const m=Math.max(0,(Date.now()-t)/60000);return m<60?Math.round(m)+" phút trước":(m/60).toFixed(1)+" giờ trước"}
function localTime(iso){const d=new Date(iso);return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}):"-"}
function hourLabel(iso){const d=new Date(iso);return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{weekday:"short",hour:"2-digit",minute:"2-digit",hour12:false}):"-"}

function render(){
 if(!critical)return;
 const p=critical.points?.[current]||{},l=p.local||{},m=p.model||{};
 $("placeName").textContent=p.name||current;
 $("heroTemp").textContent=(num(l.temperature_c)??num(m.temperature_c))===null?"--":fmt(num(l.temperature_c)??num(m.temperature_c),1)+"°";
 $("heroTempClass").textContent=l.available?"ESTIMATED":"MODEL";
 $("heroSummary").textContent=summary(p);
 $("updatedAt").textContent="Cập nhật "+localTime(critical.generated_at)+" · "+age(critical.generated_at);
 $("liveDot").className=critical.report_status==="LIVE"?"ok":"warn";
 $("liveLabel").textContent=(critical.report_status==="LIVE"?"LIVE":"DEGRADED")+" · "+age(critical.generated_at);
 setMetric("windNow",l.wind_kmh??m.wind_kmh,1); setBadge("windClass",l.wind_class||"MODEL_ONLY");
 setMetric("rainNow",l.rain_rate_mm_h,2); $("rainConfidence").textContent=num(l.rain_confidence)===null?"-":Math.round(l.rain_confidence*100);setBadge("rainClass",l.available?(l.rain_class||"ESTIMATED_NOW"):"MODEL_ONLY");
 $("convectiveNow").textContent=num(l.convection_score)===null?"-":Math.round(l.convection_score);
 setMetric("waveNow",l.wave_hs_m??m.wave_hs_m,2);setBadge("marineClass",l.marine_class||"MODEL_ONLY");
 renderActual();renderHours(p.next24h||[]);
 document.querySelectorAll(".point-tabs button").forEach(b=>b.classList.toggle("active",b.dataset.point===current));
 if(full&&!$("forecastDetail").hidden)renderForecastDetail();
}
function summary(p){const l=p.local||{},m=p.model||{},bits=[];const rain=num(l.rain_rate_mm_h),conv=num(l.convection_score),wind=num(l.wind_kmh??m.wind_kmh),wave=num(l.wave_hs_m??m.wave_hs_m);
 if(rain!==null)bits.push(rain>=3?"Mưa hiện tại đáng chú ý":rain>.2?"Ước tính có mưa nhẹ hoặc rải rác":"Ước tính mưa hiện tại thấp");
 if(conv!==null&&conv>=70)bits.push("mây đối lưu đang hoạt động");
 if(wind!==null)bits.push("gió khoảng "+fmt(wind,0)+" km/h");
 if(wave!==null)bits.push("Hs nền khoảng "+fmt(wave,1)+" m");
 return bits.length?bits.join(" · ")+".":"Chưa đủ dữ liệu địa phương để tóm tắt.";
}
function setMetric(id,v,d){$(id).textContent=num(v)===null?"-":fmt(v,d)}
function setBadge(id,k){const el=$(id);el.className="badge "+badgeClass(k);el.textContent=String(k||"MODEL_ONLY").replace("_NOW","").replaceAll("_"," ")}

function renderActual(){
 const a=critical.actual||{},v=a.vvpq||{},g=a.rain_gauges||[],cards=[];
 cards.push('<article class="actual-card"><header><b>VVPQ</b><em class="badge actual">ACTUAL</em></header><strong>'+fmt(v.temperature_c,1)+'°C</strong><small>Gió '+fmt(v.wind_kmh,1)+' km/h · '+age(v.observed_at)+'</small></article>');
 g.forEach(x=>cards.push('<article class="actual-card"><header><b>'+esc(x.name)+'</b><em class="badge actual">ACTUAL</em></header><strong>'+fmt(x.accum_mm,1)+' mm</strong><small>Tích lũy'+(num(x.increment_mm)!==null?' · +'+fmt(x.increment_mm,1)+' mm / '+fmt(x.increment_min,0)+' phút':'')+'</small></article>'));
 $("actualStrip").innerHTML=cards.join("");
 $("actualState").textContent=(critical.source_state?.vvpq==="FRESH"&&critical.source_state?.vrain==="FRESH")?"VVPQ + VRAIN FRESH":"CÓ NGUỒN CHẬM";
}
function renderHours(rows){
 $("hourlyStrip").innerHTML=rows.length?rows.map(r=>'<article class="hour-card"><time>'+hourLabel(r.t)+'</time><strong>'+fmt(r.temp,0)+'°</strong><div class="hour-grid"><span>Gió</span><b>'+fmt(r.wind,0)+'</b><span>Mưa</span><b>'+fmt(r.rain,1)+'</b><span>Hs</span><b>'+fmt(r.wave,1)+'</b></div></article>').join(""):'<div class="lazy-status">Chưa có chuỗi 24 giờ.</div>';
}

async function openForecast(){
 const host=$("forecastDetail");host.hidden=false;host.innerHTML='<div class="lazy-status">Đang tải forecast đầy đủ...</div>';
 try{if(!full)full=await getJSON(FULL);renderForecastDetail()}catch(e){host.innerHTML='<div class="lazy-status">Không tải được forecast chi tiết: '+esc(e.message)+'</div>'}
}
function renderForecastDetail(){
 const host=$("forecastDetail"),p=full?.points?.[current];if(!host||!p)return;
 const now=Date.now(),rows=(p.hours||[]).filter(r=>{const t=Date.parse(r.time_iso);return Number.isFinite(t)&&t>=now&&t<=now+72*3600000}).slice(0,25);
 host.innerHTML='<div class="detail-grid"><article class="detail-card"><span>D0-D3</span><b>'+rows.length+' bước</b></article><article class="detail-card"><span>Gió giật hiện tại</span><b>'+fmt(p.gust,0)+' km/h</b></article><article class="detail-card"><span>Hmax rủi ro</span><b>'+fmt(p.wave_max,1)+' m</b></article></div><div class="table-scroll"><table class="forecast-table"><thead><tr><th>Giờ</th><th>°C</th><th>Gió</th><th>Giật</th><th>Mưa</th><th>Hs</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+localTime(r.time_iso)+'</td><td>'+fmt(r.temperature,0)+'</td><td>'+fmt(r.wind,0)+'</td><td>'+fmt(r.gust,0)+'</td><td>'+fmt(r.rain,1)+'</td><td>'+fmt(r.wave,1)+'</td></tr>').join("")+'</tbody></table></div>';
}

async function openEnsemble(){
 const host=$("ensembleDetail");host.hidden=false;host.innerHTML='<div class="lazy-status">Đang đọc ensemble matrix...</div>';
 try{if(!ensemble)ensemble=await getFirst(ENSEMBLE);renderEnsemble()}catch(e){host.innerHTML='<div class="lazy-status">Ensemble matrix chưa được publish. Hệ thống vẫn giữ trạng thái LEARNING.</div>'}
}
function renderEnsemble(){
 const host=$("ensembleDetail"),rows=ensemble?.points?.[current]||[],first=rows.find(r=>r?.variables?.wind)||rows[0];
 if(!first){host.innerHTML='<div class="lazy-status">Chưa có member matrix cho điểm này.</div>';return}
 const wind=first.variables?.wind?.corrected||{},rain=first.variables?.rain?.corrected||{};
 $("ensembleState").textContent=ensemble.calibration_status||"LEARNING";$("ensembleState").className="badge "+(ensemble.calibration_status==="READY"?"actual":"learning");
 host.innerHTML='<div class="detail-grid"><article class="detail-card"><span>GEFS members</span><b>'+fmt(wind.member_count,0)+'</b></article><article class="detail-card"><span>Gió q50 / q90</span><b>'+fmt(wind.q50,0)+' / '+fmt(wind.q90,0)+'</b></article><article class="detail-card"><span>Mưa q50 / q90</span><b>'+fmt(rain.q50,1)+' / '+fmt(rain.q90,1)+'</b></article></div><div class="lazy-status">Lead +'+fmt(first.lead_hours,0)+'h · '+esc(ensemble.source||"ensemble")+' · '+esc(ensemble.calibration_status||"LEARNING")+'</div>';
}

function openMap(){
 const host=$("mapArea");host.hidden=false;
 if(!mapOpened){host.innerHTML='<div class="map-tabs"><button class="active" data-map="radar">Radar</button><button data-map="wind">Gió</button><button data-map="rain">Mưa forecast</button><button data-map="himawari">Himawari IR</button></div><div id="mapBox" class="map-box"></div><div id="mapNote" class="map-note"></div>';host.querySelectorAll("[data-map]").forEach(b=>b.onclick=()=>setMap(b.dataset.map));mapOpened=true;setMap("radar")}
 host.scrollIntoView({behavior:"smooth",block:"nearest"});
}
function setMap(type){
 document.querySelectorAll("[data-map]").forEach(b=>b.classList.toggle("active",b.dataset.map===type));const box=$("mapBox"),note=$("mapNote");if(!box)return;
 if(type==="himawari"){box.innerHTML='<img id="himawariImg" alt="JMA Himawari infrared">';note.textContent="Đang tìm frame Himawari B13 gần nhất...";loadHimawari();return}
 box.innerHTML='<iframe title="Weather map" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';box.firstChild.src=WINDY[type]||WINDY.radar;note.textContent=type==="radar"?"Radar chỉ là lớp quan sát trực quan, không phải ground truth số.":type==="wind"?"Windy/ECMWF để nhìn cấu trúc gió không gian.":"Mưa forecast để nhìn cấu trúc dự báo, không thay VRain actual.";
}
function loadHimawari(){
 const img=$("himawariImg");if(!img)return;const now=new Date(),base=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate(),now.getUTCHours(),Math.floor(now.getUTCMinutes()/10)*10),list=Array.from({length:12},(_,i)=>{const d=new Date(base-(i+2)*600000),hh=String(d.getUTCHours()).padStart(2,"0"),mm=String(d.getUTCMinutes()).padStart(2,"0");return JMA+"ha1_b13_"+hh+mm+".jpg"});let i=0;
 img.onerror=()=>{i++;if(i<list.length)img.src=list[i]+"?t="+Date.now();else $("mapNote").textContent="Không tải được Himawari trực tiếp lúc này."};
 img.onload=()=>{$("mapNote").textContent="JMA Himawari B13 · remote observed · frame gần nhất tải thành công.";};img.src=list[0]+"?t="+Date.now();
}

async function openExtra(kind){
 const host=$("extraDetail");host.hidden=false;host.innerHTML='<div class="lazy-status">Đang tải...</div>';
 if(kind==="tide"){try{const t=await getJSON(TIDE),p=t.points?.[current]||{};host.innerHTML='<div class="detail-grid"><article class="detail-card"><span>Mực triều model</span><b>'+fmt(p.current_height_m,2)+' m</b></article><article class="detail-card"><span>Xu hướng</span><b>'+esc(p.trend||"-")+'</b></article><article class="detail-card"><span>Biên độ 24h</span><b>'+fmt(p.range_24h_m,2)+' m</b></article></div>'}catch(e){host.innerHTML='<div class="lazy-status">Không tải được dữ liệu triều.</div>'}}
 if(kind==="aqi"){try{const a=await getFirst(AQ),p=a.points?.[current]||{};host.innerHTML='<div class="detail-grid"><article class="detail-card"><span>US AQI</span><b>'+fmt(p.aqi_us,0)+'</b></article><article class="detail-card"><span>PM2.5</span><b>'+fmt(p.pm25_ugm3,1)+'</b></article><article class="detail-card"><span>PM10</span><b>'+fmt(p.pm10_ugm3,1)+'</b></article></div>'}catch(e){host.innerHTML='<div class="lazy-status">Không tải được AQI.</div>'}}
}
function feedback(kind){
 const p=critical?.points?.[current]||{},l=p.local||{},item={id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),at:new Date().toISOString(),point_id:current,category:kind,engine:critical?.source_state?.local_engine||"PQ_LOCAL_NOW_V1",estimate:{temperature_c:l.temperature_c,wind_kmh:l.wind_kmh,rain_rate_mm_h:l.rain_rate_mm_h,rain_confidence:l.rain_confidence}};
 let q=[];try{q=JSON.parse(localStorage.getItem("pq_weather_field_feedback_v1")||"[]")}catch{}if(!Array.isArray(q))q=[];q.push(item);q=q.slice(-100);try{localStorage.setItem("pq_weather_field_feedback_v1",JSON.stringify(q))}catch{}$("feedbackState").textContent="Đã lưu phản hồi trên thiết bị. Cảm ơn bạn.";
}
async function boot(){
 document.querySelectorAll(".point-tabs button").forEach(b=>b.onclick=()=>{current=b.dataset.point;render()});
 $("openForecast").onclick=openForecast;$("openEnsemble").onclick=openEnsemble;$("openMap").onclick=openMap;
 document.querySelectorAll("[data-extra]").forEach(b=>b.onclick=()=>openExtra(b.dataset.extra));document.querySelectorAll("[data-feedback]").forEach(b=>b.onclick=()=>feedback(b.dataset.feedback));
 try{critical=await getJSON(CRITICAL);current=critical.default_point||"duong_dong";render()}catch(e){$("heroSummary").textContent="Không tải được dữ liệu nhanh. Hãy thử tải lại trang."; $("liveLabel").textContent="DATA ERROR";$("liveDot").className="warn"}
}
boot();
})();