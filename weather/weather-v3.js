(function(){
"use strict";

var DATA_URLS=[
  "/Jotrip-Lab/weather/data/critical.json",
  "./data/critical.json",
  "https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/gh-pages/weather/data/critical.json"
];

var POINTS={
  duong_dong:{lat:10.2172,lon:103.9593,label:"Dương Đông"},
  cua_can:{lat:10.292693,lon:103.914799,label:"Cửa Cạn"},
  ganh_dau:{lat:10.37077,lon:103.84472,label:"Gành Dầu"},
  bai_thom:{lat:10.411765,lon:104.031055,label:"Bãi Thơm"},
  ham_ninh:{lat:10.18062,lon:104.04463,label:"Hàm Ninh"},
  bai_sao:{lat:10.0572576,lon:104.0363948,label:"Bãi Sao"},
  an_thoi:{lat:9.905,lon:104.005,label:"Biển An Thới"}
};

var state={
  data:null,
  map:null,
  fieldLayer:null,
  markerLayer:null,
  actualLayer:null,
  selected:"duong_dong",
  mode:"jotrip",
  layer:"risk",
  source:null,
  step:0,
  loading:false
};

var SOURCE_MAPS={
  radar:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1",
  wind:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
  rain:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=rain&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C",
  waves:"https://embed.windy.com/embed2.html?lat=10.20&lon=104.00&detailLat=10.20&detailLon=104.00&width=1000&height=650&zoom=8&level=surface&overlay=waves&product=ecmwfWaves&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C"
};
var JMA_BASE="https://www.data.jma.go.jp/mscweb/data/himawari/img/ha1/";

var $=function(id){return document.getElementById(id)};
var num=function(v){
  if(v===null||v===undefined||v===""||Number.isNaN(Number(v)))return null;
  return Number(v);
};
var clamp=function(v,a,b){return Math.max(a,Math.min(b,v))};
var fmt=function(v,d){
  v=num(v);
  if(v===null)return "-";
  return Number(v.toFixed(d===undefined?1:d)).toString();
};
var esc=function(v){
  return String(v===undefined||v===null?"":v).replace(/[&<>'"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c];
  });
};

function getPoint(id){
  return state.data&&state.data.points&&state.data.points[id]?state.data.points[id]:{};
}
function pointIds(){
  var ids=state.data&&Array.isArray(state.data.island_watch_order)?state.data.island_watch_order.slice():Object.keys(POINTS);
  return ids.filter(function(id){return POINTS[id]&&state.data&&state.data.points&&state.data.points[id]});
}
function ageMinutes(iso){
  var t=Date.parse(iso||"");
  if(!Number.isFinite(t))return Infinity;
  return Math.max(0,(Date.now()-t)/60000);
}
function ageText(iso){
  var m=ageMinutes(iso);
  if(!Number.isFinite(m))return "không rõ";
  if(m<2)return "vừa cập nhật";
  if(m<60)return Math.round(m)+" phút trước";
  return (m/60).toFixed(1)+" giờ trước";
}
function localTime(iso){
  var d=new Date(iso||"");
  if(!Number.isFinite(d.getTime()))return "-";
  return d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
}
function dataTimestamp(){
  return state.data?(state.data.local_generated_at||state.data.generated_at):null;
}

async function fetchJSON(url){
  var sep=url.indexOf("?")>=0?"&":"?";
  var res=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});
  if(!res.ok)throw new Error("HTTP "+res.status);
  return res.json();
}
async function fetchFirst(urls){
  var last=null;
  for(var i=0;i<urls.length;i++){
    try{return await fetchJSON(urls[i])}catch(e){last=e}
  }
  throw last||new Error("No data source");
}

function ensembleRow(p,lead){
  var rows=p&&p.ensemble&&Array.isArray(p.ensemble.rows)?p.ensemble.rows:[];
  if(!rows.length)return null;
  var best=null,dist=Infinity;
  rows.forEach(function(r){
    var l=num(r.lead_hours);
    if(l===null)return;
    var d=Math.abs(l-lead);
    if(d<dist){dist=d;best=r}
  });
  return best;
}

function currentRisk(p){
  var l=p.local||{},m=p.model||{},n=p.nowcast||{};
  var rows=p.ensemble&&Array.isArray(p.ensemble.rows)?p.ensemble.rows:[];
  var conv=num(n.convective_score!==undefined?n.convective_score:l.convection_score);
  var gust=num(m.gust_kmh),rain=num(m.rain_3h_mm),hs=num(l.wave_hs_m!==undefined?l.wave_hs_m:m.wave_hs_m);
  var windProb=0,rainProb=0;
  rows.slice(0,2).forEach(function(r){
    windProb=Math.max(windProb,num(r.wind&&r.wind.prob)||0);
    rainProb=Math.max(rainProb,num(r.rain&&r.rain.prob)||0);
  });
  var level=0,reasons=[];
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}
  else if(conv!==null&&conv>=60){level=Math.max(level,1);reasons.push("đối lưu tăng")}
  if(gust!==null&&gust>=39){level=Math.max(level,3);reasons.push("gió giật mạnh")}
  else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật cần theo dõi")}
  if(rain!==null&&rain>=25){level=Math.max(level,3);reasons.push("mưa tích lũy lớn")}
  else if(rain!==null&&rain>=10){level=Math.max(level,2);reasons.push("mưa tăng")}
  if(hs!==null&&hs>=2){level=Math.max(level,3);reasons.push("sóng nền cao")}
  else if(hs!==null&&hs>=1.5){level=Math.max(level,2);reasons.push("sóng tăng")}
  if(windProb>=.25){level=Math.max(level,2);reasons.push("ensemble còn kịch bản gió mạnh")}
  else if(windProb>=.10){level=Math.max(level,1)}
  if(rainProb>=.50){level=Math.max(level,2);reasons.push("ensemble nghiêng về mưa")}
  else if(rainProb>=.25){level=Math.max(level,1)}
  return {level:level,reasons:reasons};
}

function futureRisk(row){
  if(!row)return {level:0,reasons:["chưa có dữ liệu"]};
  var wp=num(row.wind&&row.wind.prob)||0;
  var rp=num(row.rain&&row.rain.prob)||0;
  var w95=num(row.wind&&row.wind.q95);
  var rq=num(row.rain&&row.rain.q90);
  var level=0,reasons=[];
  if(wp>=.45||w95!==null&&w95>=39){level=Math.max(level,3);reasons.push("gió mạnh")}
  else if(wp>=.20||w95!==null&&w95>=30){level=Math.max(level,2);reasons.push("gió cần theo dõi")}
  else if(wp>=.08){level=Math.max(level,1)}
  if(rp>=.65||rq!==null&&rq>=20){level=Math.max(level,3);reasons.push("mưa cao")}
  else if(rp>=.35||rq!==null&&rq>=8){level=Math.max(level,2);reasons.push("mưa tăng")}
  else if(rp>=.15){level=Math.max(level,1)}
  return {level:level,reasons:reasons};
}

function riskFor(id,step){
  var p=getPoint(id);
  if(step>0)return futureRisk(ensembleRow(p,step));
  return currentRisk(p);
}
function classForLevel(level){
  if(level>=3)return "alert";
  if(level>=1)return "watch";
  return "ok";
}
function colorForLevel(level){
  if(level>=3)return "#ff4d5d";
  if(level>=2)return "#ff9c43";
  if(level>=1)return "#ffc145";
  return "#37d67a";
}

function layerMetric(id){
  var p=getPoint(id),l=p.local||{},m=p.model||{},n=p.nowcast||{};
  var row=state.step>0?ensembleRow(p,state.step):null;
  if(state.layer==="risk"){
    var rr=riskFor(id,state.step);
    return {value:rr.level,label:rr.level>=3?"CAO":rr.level>=2?"THEO DÕI":rr.level>=1?"LƯU Ý":"ỔN",level:rr.level};
  }
  if(state.layer==="rain"){
    var rain=state.step>0?num(row&&row.rain&&row.rain.q50):num(l.rain_rate_mm_h);
    rain=rain===null?0:rain;
    var rlevel=rain>=10?3:rain>=3?2:rain>=.3?1:0;
    return {value:rain,label:fmt(rain,state.step>0?1:2)+(state.step>0?" mm":" mm/h"),level:rlevel};
  }
  if(state.layer==="wind"){
    var wind=state.step>0?num(row&&row.wind&&row.wind.q50):num(l.wind_kmh!==undefined?l.wind_kmh:m.wind_kmh);
    wind=wind===null?0:wind;
    var wlevel=wind>=39?3:wind>=29?2:wind>=20?1:0;
    return {value:wind,label:fmt(wind,0)+" km/h",level:wlevel};
  }
  if(state.layer==="waves"){
    var wave=num(l.wave_hs_m!==undefined?l.wave_hs_m:m.wave_hs_m);
    wave=wave===null?0:wave;
    var hlevel=wave>=2?3:wave>=1.5?2:wave>=1?1:0;
    return {value:wave,label:fmt(wave,1)+" m",level:hlevel};
  }
  var conv=num(n.convective_score!==undefined?n.convective_score:l.convection_score);
  conv=conv===null?0:conv;
  var clevel=conv>=75?3:conv>=60?2:conv>=40?1:0;
  return {value:conv,label:fmt(conv,0)+"/100",level:clevel};
}

function layerRadius(metric){
  if(state.layer==="risk")return 6500+metric.level*2800;
  if(state.layer==="rain")return 5500+clamp(metric.value,0,15)*420;
  if(state.layer==="wind")return 6200+clamp(metric.value,0,45)*110;
  if(state.layer==="waves")return 6200+clamp(metric.value,0,2.5)*2600;
  return 6000+clamp(metric.value,0,100)*55;
}

function layerNote(){
  if(state.step>0&&state.layer==="storm")return "Storm chưa có trajectory phút-giờ trong payload hiện tại. Lớp này đang giữ nowcast Himawari gần nhất.";
  if(state.step>0&&state.layer==="waves")return "Sóng ensemble chưa có trong payload thời gian này. Lớp đang giữ trạng thái biển hiện tại.";
  var notes={
    risk:"Risk là lớp đánh giá JoTrip từ Local Now, model và ensemble. Vùng màu chỉ để định hướng, không phải độ phân giải thật của mô hình.",
    rain:state.step>0?"Mưa tương lai hiển thị trung vị ensemble tại mốc gần nhất.":"Mưa hiện tại dùng Estimated Now tại các điểm Weather Lab.",
    wind:state.step>0?"Gió tương lai hiển thị trung vị ensemble tại mốc gần nhất.":"Gió hiện tại ưu tiên Local Now rồi mới tới model.",
    waves:"Sóng Hs là biển nền từ model tại ô lưới biển hợp lệ gần nhất.",
    storm:"Đối lưu là tín hiệu Himawari/nowcast, không phải xác suất có sét."
  };
  return notes[state.layer]||notes.risk;
}

function initMap(){
  if(!window.L)return;
  state.map=L.map("situationMap",{zoomControl:false,attributionControl:true,minZoom:9,maxZoom:13}).setView([10.17,103.97],10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",{
    maxZoom:19,
    subdomains:"abcd",
    attribution:'&copy; OpenStreetMap &copy; CARTO'
  }).addTo(state.map);
  L.control.zoom({position:"bottomright"}).addTo(state.map);
  state.fieldLayer=L.layerGroup().addTo(state.map);
  state.markerLayer=L.layerGroup().addTo(state.map);
  state.actualLayer=L.layerGroup().addTo(state.map);
}

function renderActualLayer(){
  if(!state.actualLayer||!state.data)return;
  state.actualLayer.clearLayers();
  if(state.mode!=="actual")return;

  var actual=state.data.actual||{};
  var v=actual.vvpq||{};
  if(v.status){
    var metarIcon=L.divIcon({className:"",html:'<div class="actual-observation metar"></div>',iconSize:[18,18],iconAnchor:[9,9]});
    var metar=L.marker([10.169,103.995],{icon:metarIcon,zIndexOffset:1400});
    metar.bindTooltip("VVPQ · "+(v.temperature_c!==undefined?fmt(v.temperature_c,1)+"°C":"")+" · "+(v.wind_kmh!==undefined?fmt(v.wind_kmh,0)+" km/h":""),{direction:"top",opacity:.98});
    metar.addTo(state.actualLayer);
    var ml=L.divIcon({className:"",html:'<div class="actual-label">VVPQ · METAR</div>',iconSize:[98,22],iconAnchor:[49,-11]});
    L.marker([10.169,103.995],{icon:ml,interactive:false,zIndexOffset:1300}).addTo(state.actualLayer);
  }

  (actual.rain_gauges||[]).forEach(function(g){
    if(num(g.lat)===null||num(g.lon)===null)return;
    var icon=L.divIcon({className:"",html:'<div class="actual-observation rain"></div>',iconSize:[18,18],iconAnchor:[9,9]});
    var mk=L.marker([Number(g.lat),Number(g.lon)],{icon:icon,zIndexOffset:1300});
    var rainText=g.rain_observed===true?"ĐANG MƯA":g.rain_observed===false?"KHÔNG MƯA":"TRẠNG THÁI CHƯA ĐỦ";
    var amount=num(g.rain_intensity_mm_h)!==null?fmt(g.rain_intensity_mm_h,1)+" mm/h":num(g.accum_mm)!==null?fmt(g.accum_mm,1)+" mm tích lũy":"-";
    mk.bindTooltip((g.name||"VRain")+" · "+rainText+" · "+amount,{direction:"top",opacity:.98});
    mk.addTo(state.actualLayer);
    var lb=L.divIcon({className:"",html:'<div class="actual-label">'+esc(g.name||"VRain")+'</div>',iconSize:[100,22],iconAnchor:[50,-11]});
    L.marker([Number(g.lat),Number(g.lon)],{icon:lb,interactive:false,zIndexOffset:1200}).addTo(state.actualLayer);
  });
}

function himawariCandidates(){
  var now=new Date(),base=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate(),now.getUTCHours(),Math.floor(now.getUTCMinutes()/10)*10);
  return Array.from({length:12},function(_,i){
    var d=new Date(base-(i+2)*600000);
    var hh=String(d.getUTCHours()).padStart(2,"0"),mm=String(d.getUTCMinutes()).padStart(2,"0");
    return JMA_BASE+"ha1_b13_"+hh+mm+".jpg";
  });
}

function renderSourceLayer(){
  var box=$("sourceLayerFrame");
  if(!box)return;
  if(state.mode!=="source"){
    box.className="source-layer-frame";
    box.setAttribute("aria-hidden","true");
    box.innerHTML="";
    return;
  }
  box.className="source-layer-frame active";
  box.setAttribute("aria-hidden","false");
  if(state.source==="himawari"){
    box.innerHTML='<img id="v3Himawari" alt="JMA Himawari B13 infrared">';
    var img=$("v3Himawari"),list=himawariCandidates(),i=0;
    img.onerror=function(){
      i++;
      if(i<list.length)img.src=list[i]+"?t="+Date.now();
      else box.innerHTML='<div class="source-fallback"><div><b>Himawari chưa tải được</b><span>JoTrip Risk và Actual vẫn hoạt động bình thường.</span></div></div>';
    };
    img.src=list[0]+"?t="+Date.now();
    return;
  }
  var src=SOURCE_MAPS[state.source];
  if(src){
    box.innerHTML='<iframe title="Weather source map" loading="eager" referrerpolicy="strict-origin-when-cross-origin" allow="geolocation"></iframe>';
    box.firstChild.src=src;
  }else{
    box.innerHTML='<div class="source-fallback"><div><b>Source layer chưa sẵn sàng</b><span>Chọn Radar, Himawari, Wind, Rain hoặc Waves.</span></div></div>';
  }
}

function renderMap(){
  if(!state.map||!state.data)return;
  state.fieldLayer.clearLayers();
  state.markerLayer.clearLayers();
  renderSourceLayer();
  renderActualLayer();
  if(state.mode!=="jotrip"){
    $("layerNote").textContent=state.mode==="actual"?"Actual chỉ hiển thị trạm/nguồn đo thật có timestamp. Không nội suy thành trường liên tục.":"Đây là lớp nguồn tham chiếu như V2. JoTrip Risk không trộn vào dữ liệu nguồn.";
    $("windFlow").classList.add("hidden");
    return;
  }

  pointIds().forEach(function(id){
    var cfg=POINTS[id],metric=layerMetric(id),color=colorForLevel(metric.level);
    var circle=L.circle([cfg.lat,cfg.lon],{
      radius:layerRadius(metric),
      stroke:true,
      color:color,
      weight:id===state.selected?2:1,
      opacity:id===state.selected?.82:.45,
      fill:true,
      fillColor:color,
      fillOpacity:id===state.selected?.24:.14,
      className:"field-circle"
    });
    circle.on("click",function(){selectPoint(id)});
    circle.bindTooltip(cfg.label+" · "+metric.label,{sticky:true,direction:"top",opacity:.96});
    circle.addTo(state.fieldLayer);

    var risk=riskFor(id,state.step);
    var dotClass=classForLevel(risk.level);
    var icon=L.divIcon({
      className:"",
      html:'<div class="weather-dot '+dotClass+'"></div>',
      iconSize:[12,12],
      iconAnchor:[6,6]
    });
    var marker=L.marker([cfg.lat,cfg.lon],{icon:icon,zIndexOffset:id===state.selected?1000:0});
    marker.on("click",function(){selectPoint(id)});
    marker.addTo(state.markerLayer);

    var label=L.divIcon({
      className:"",
      html:'<div class="weather-label '+(id===state.selected?"selected":"")+'">'+esc(cfg.label)+'</div>',
      iconSize:[110,20],
      iconAnchor:[55,-8]
    });
    var labelMarker=L.marker([cfg.lat,cfg.lon],{icon:label,interactive:true,zIndexOffset:id===state.selected?900:0});
    labelMarker.on("click",function(){selectPoint(id)});
    labelMarker.addTo(state.markerLayer);
  });

  $("layerNote").textContent=layerNote();
  $("windFlow").classList.toggle("hidden",state.layer!=="wind"&&state.layer!=="risk");
}

function selectedPoint(){
  return getPoint(state.selected);
}

function confidenceFor(p){
  var local=num(p.local&&p.local.rain_confidence);
  var ens=num(p.ensemble&&p.ensemble.completion_ratio);
  if(local===null&&ens===null)return null;
  if(local===null)return Math.round(ens*100);
  if(ens===null)return Math.round(local*100);
  return Math.round((local*.55+ens*.45)*100);
}
function classLabel(v){
  var s=String(v||"").toUpperCase();
  var map={ACTUAL:"ĐO THỰC",ESTIMATED_NOW:"ƯỚC TÍNH",MODEL_ONLY:"MÔ HÌNH",REMOTE_OBSERVED:"VỆ TINH"};
  return map[s]||s.replaceAll("_"," ")||"-";
}

function renderDetail(){
  var p=selectedPoint(),l=p.local||{},m=p.model||{},n=p.nowcast||{};
  var risk=riskFor(state.selected,state.step);
  $("pointName").textContent=(POINTS[state.selected]&&POINTS[state.selected].label)||p.name||state.selected;
  $("timelineTitle").textContent=$("pointName").textContent;
  var pill=$("pointRisk");
  pill.className="risk-pill "+classForLevel(risk.level);
  pill.textContent=risk.level>=3?"NGUY CƠ CAO":risk.level>=2?"THEO DÕI":risk.level>=1?"LƯU Ý":"ỔN";

  var rain=num(l.rain_rate_mm_h);
  var wind=num(l.wind_kmh!==undefined?l.wind_kmh:m.wind_kmh);
  var gust=num(m.gust_kmh);
  var wave=num(l.wave_hs_m!==undefined?l.wave_hs_m:m.wave_hs_m);
  $("rainNow").textContent=rain===null?"-":fmt(rain,2)+" mm/h";
  $("windNow").textContent=wind===null?"-":fmt(wind,0)+" km/h";
  $("gustNow").textContent=gust===null?"-":fmt(gust,0)+" km/h";
  $("waveNow").textContent=wave===null?"-":fmt(wave,1)+" m";
  $("rainClass").textContent=classLabel(l.rain_class||"ESTIMATED_NOW");
  $("windClass").textContent=classLabel(l.wind_class||(l.available?"ESTIMATED_NOW":"MODEL_ONLY"));
  $("waveClass").textContent=classLabel(l.marine_class||"MODEL_ONLY");

  var conv=num(n.convective_score!==undefined?n.convective_score:l.convection_score);
  $("convectiveNow").textContent=conv===null?"-":fmt(conv,0)+"/100";
  $("convectiveMeta").textContent=(n.source||"Himawari")+" · "+classLabel("REMOTE_OBSERVED");

  var conf=confidenceFor(p);
  $("confidenceNow").textContent=conf===null?"-":conf+"/100";
  $("updatedAt").textContent="Cập nhật "+localTime(dataTimestamp())+" · "+ageText(dataTimestamp());
}

function timelineRows(p){
  var arr=[{lead:0,risk:currentRisk(p)}];
  [6,12,18].forEach(function(lead){
    var row=ensembleRow(p,lead);
    arr.push({lead:lead,risk:futureRisk(row),row:row});
  });
  return arr;
}
function renderTimeline(){
  var p=selectedPoint();
  var rows=timelineRows(p);
  $("hazardTimeline").innerHTML=rows.map(function(x){
    var cls=classForLevel(x.risk.level);
    var label=x.lead===0?"NOW":"+"+x.lead+"H";
    var note=x.risk.level>=3?"CAO":x.risk.level>=2?"WATCH":x.risk.level>=1?"LƯU Ý":"ỔN";
    return '<div class="hazard-step '+cls+'"><i></i><b>'+label+'</b><small>'+note+'</small></div>';
  }).join("");
}

function renderIslandSummary(){
  var rows=pointIds().map(function(id){
    var r=riskFor(id,state.step);
    return {id:id,r:r};
  }).sort(function(a,b){return b.r.level-a.r.level});
  var worst=rows[0]||{r:{level:0,reasons:[]},id:state.selected};
  var high=rows.filter(function(x){return x.r.level>=2});
  var title="Nhìn chung ổn";
  if(worst.r.level>=3)title="Có vùng nguy cơ cao cần chú ý";
  else if(worst.r.level>=2)title="Có vùng cần theo dõi sát";
  else if(worst.r.level>=1)title="Có tín hiệu nhẹ cần lưu ý";
  $("islandHeadline").textContent=title;
  if(high.length){
    $("islandSub").textContent=high.slice(0,3).map(function(x){
      var name=POINTS[x.id]?POINTS[x.id].label:x.id;
      return name+(x.r.reasons.length?" · "+x.r.reasons.slice(0,2).join(", "):"");
    }).join("  |  ");
  }else{
    $("islandSub").textContent="Chưa thấy điểm Weather Lab vượt ngưỡng theo dõi chính ở mốc đang xem.";
  }
}

function renderQuickAlert(){
  var now=pointIds().map(function(id){
    var p=getPoint(id),conv=num(p.nowcast&&p.nowcast.convective_score)||0;
    return {id:id,conv:conv};
  }).sort(function(a,b){return b.conv-a.conv})[0];

  var future=[];
  pointIds().forEach(function(id){
    var p=getPoint(id);
    [6,12].forEach(function(lead){
      var row=ensembleRow(p,lead);
      if(!row)return;
      var risk=futureRisk(row);
      future.push({id:id,lead:lead,row:row,risk:risk});
    });
  });
  future.sort(function(a,b){
    if(b.risk.level!==a.risk.level)return b.risk.level-a.risk.level;
    return a.lead-b.lead;
  });

  var root=$("quickAlert"),title=$("alertTitle"),text=$("alertText"),when=$("alertWhen");
  root.className="quick-alert neutral";
  title.textContent="Chưa thấy nhiễu động nổi bật trong 12 giờ tới";
  text.textContent="Hệ thống vẫn theo dõi nowcast và độ phân tán ensemble.";
  when.textContent="12H";

  if(now&&now.conv>=75){
    root.className="quick-alert alert";
    title.textContent="Đối lưu đang hoạt động mạnh";
    text.textContent=(POINTS[now.id]?POINTS[now.id].label:now.id)+" · chỉ số đối lưu "+fmt(now.conv,0)+"/100. Ưu tiên radar, Himawari và quan trắc thực địa.";
    when.textContent="NOW";
    return;
  }
  var f=future[0];
  if(f&&f.risk.level>=2){
    root.className="quick-alert "+(f.risk.level>=3?"alert":"watch");
    title.textContent=f.risk.level>=3?"Có tín hiệu thời tiết bất lợi":"Có tín hiệu cần theo dõi";
    var rp=num(f.row.rain&&f.row.rain.prob),wp=num(f.row.wind&&f.row.wind.prob);
    var bits=[];
    if(rp!==null)bits.push("mưa "+Math.round(rp*100)+"%");
    if(wp!==null)bits.push("gió ≥30 "+Math.round(wp*100)+"%");
    text.textContent=(POINTS[f.id]?POINTS[f.id].label:f.id)+" · "+bits.join(" · ")+".";
    when.textContent="+"+f.lead+"H";
  }else if(now&&now.conv>=55){
    root.className="quick-alert watch";
    title.textContent="Đối lưu có tín hiệu phát triển";
    text.textContent=(POINTS[now.id]?POINTS[now.id].label:now.id)+" · chỉ số "+fmt(now.conv,0)+"/100, chưa đủ để nâng cảnh báo.";
    when.textContent="NOW";
  }
}

function renderLive(){
  var age=ageMinutes(dataTimestamp());
  var el=$("liveState");
  el.className="live-state "+(age>60?"warn":"ok");
  el.innerHTML='<i></i> '+(age>60?"DỮ LIỆU CŨ":"LIVE")+" · "+ageText(dataTimestamp());
}

function renderAll(){
  renderLive();
  renderMap();
  renderDetail();
  renderTimeline();
  renderIslandSummary();
  renderQuickAlert();
}

function selectPoint(id){
  if(!POINTS[id]||!getPoint(id))return;
  state.selected=id;
  renderMap();
  renderDetail();
  renderTimeline();
  if(window.innerWidth>900){
    var c=POINTS[id];
    state.map.panTo([c.lat,c.lon],{animate:true,duration:.4});
  }
}

function setMode(mode,layer,source){
  state.mode=mode||"jotrip";
  if(layer)state.layer=layer;
  state.source=source||null;
  document.querySelectorAll("[data-mode]").forEach(function(btn){
    var active=false;
    if(state.mode==="jotrip")active=btn.getAttribute("data-mode")==="jotrip"&&btn.getAttribute("data-layer")===state.layer;
    if(state.mode==="actual")active=btn.getAttribute("data-mode")==="actual";
    if(state.mode==="source")active=btn.getAttribute("data-mode")==="source"&&btn.getAttribute("data-source")===state.source;
    btn.classList.toggle("active",active);
  });
  renderMap();
}
function setStep(step){
  state.step=Number(step)||0;
  document.querySelectorAll("[data-step]").forEach(function(btn){
    btn.classList.toggle("active",Number(btn.getAttribute("data-step"))===state.step);
  });
  renderMap();
  renderDetail();
  renderIslandSummary();
}

async function loadData(){
  if(state.loading)return;
  state.loading=true;
  try{
    var data=await fetchFirst(DATA_URLS);
    state.data=data;
    var ids=pointIds();
    if(ids.indexOf(state.selected)<0)state.selected=data.default_point&&POINTS[data.default_point]?data.default_point:(ids[0]||"duong_dong");
    renderAll();
  }catch(e){
    console.error("[Weather V3]",e);
    $("islandHeadline").textContent="Chưa tải được dữ liệu live";
    $("islandSub").textContent="Bản đồ vẫn mở được. Weather Lab sẽ thử lại khi bạn tải lại trang.";
    $("liveState").className="live-state warn";
    $("liveState").innerHTML="<i></i> DATA ERROR";
  }finally{
    state.loading=false;
  }
}

function events(){
  document.querySelectorAll("[data-mode]").forEach(function(btn){
    btn.addEventListener("click",function(){
      setMode(btn.getAttribute("data-mode"),btn.getAttribute("data-layer"),btn.getAttribute("data-source"));
    });
  });
  document.querySelectorAll("[data-step]").forEach(function(btn){
    btn.addEventListener("click",function(){setStep(btn.getAttribute("data-step"))});
  });
  $("recenter").addEventListener("click",function(){
    state.map.setView([10.17,103.97],10,{animate:true});
  });
}

function start(){
  initMap();
  events();
  loadData();
  setInterval(loadData,10*60*1000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);
else start();

})();