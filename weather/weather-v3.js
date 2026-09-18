(function(){
"use strict";

const LAB_URLS=[
  "/Jotrip-Lab/weather/data/critical.json",
  "./data/critical.json",
  "https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/gh-pages/weather/data/critical.json"
];

const POINTS={
  duong_dong:{lat:10.2172,lon:103.9593,name:"Dương Đông"},
  cua_can:{lat:10.292693,lon:103.914799,name:"Cửa Cạn"},
  ganh_dau:{lat:10.37077,lon:103.84472,name:"Gành Dầu"},
  bai_thom:{lat:10.411765,lon:104.031055,name:"Bãi Thơm"},
  ham_ninh:{lat:10.18062,lon:104.04463,name:"Hàm Ninh"},
  bai_sao:{lat:10.0572576,lon:104.0363948,name:"Bãi Sao"},
  an_thoi:{lat:9.905,lon:104.005,name:"Biển An Thới"}
};

const state={
  map:null,
  data:null,
  mode:"jotrip",
  layer:"risk",
  step:0,
  selected:"duong_dong",
  showLabels:true,
  field:null,
  radar:null,
  markerLayer:null,
  valueLayer:null,
  actualLayer:null,
  vectorLayer:null,
  sourceWeather:null,
  sourceMarine:null,
  sourceRadar:null,
  sourceWeatherAt:0,
  sourceMarineAt:0,
  sourceRadarAt:0,
  loadingSource:false
};

const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));

function phuQuocTime(iso){
  const d=new Date(iso||"");
  if(!Number.isFinite(d.getTime()))return "-";
  return d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit",hour12:false});
}
function ageMin(iso){
  const t=Date.parse(iso||"");
  return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):Infinity;
}
function ageText(iso){
  const m=ageMin(iso);
  if(!Number.isFinite(m))return "không rõ";
  if(m<2)return "vừa cập nhật";
  if(m<60)return Math.round(m)+" phút";
  return (m/60).toFixed(1)+" giờ";
}
function snapshotTime(){return state.data?.generated_at||state.data?.local_generated_at||null}
function localTime(){return state.data?.local_generated_at||state.data?.generated_at||null}

async function fetchJSON(url){
  const sep=url.includes("?")?"&":"?";
  const r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  return r.json();
}
async function fetchFirst(urls){
  let last;
  for(const u of urls){
    try{return await fetchJSON(u)}catch(e){last=e}
  }
  throw last||new Error("unavailable");
}

function pointIds(){
  const ids=state.data?.island_watch_order||Object.keys(POINTS);
  return ids.filter(id=>POINTS[id]&&state.data?.points?.[id]);
}
function point(id=state.selected){return state.data?.points?.[id]||{}}
function nearestEnsembleRow(p,lead){
  const rows=p?.ensemble?.rows||[];
  let best=null,dist=Infinity;
  rows.forEach(r=>{
    const l=num(r.lead_hours);
    if(l===null)return;
    const d=Math.abs(l-lead);
    if(d<dist){dist=d;best=r}
  });
  return best;
}

function currentRisk(p){
  const l=p.local||{},m=p.model||{},n=p.nowcast||{};
  const rows=(p.ensemble?.rows||[]).slice(0,2);
  const conv=num(n.convective_score??l.convection_score);
  const gust=num(m.gust_kmh);
  const rain3=num(m.rain_3h_mm);
  const wave=num(l.wave_hs_m??m.wave_hs_m);
  let wp=0,rp=0,level=0,reasons=[];
  rows.forEach(r=>{
    wp=Math.max(wp,num(r.wind?.prob)||0);
    rp=Math.max(rp,num(r.rain?.prob)||0);
  });
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}
  else if(conv!==null&&conv>=60){level=Math.max(level,1);reasons.push("đối lưu tăng")}
  if(gust!==null&&gust>=39){level=3;reasons.push("gió giật mạnh")}
  else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật tăng")}
  if(rain3!==null&&rain3>=25){level=3;reasons.push("mưa 3 giờ lớn")}
  else if(rain3!==null&&rain3>=10){level=Math.max(level,2);reasons.push("mưa tăng")}
  if(wave!==null&&wave>=2){level=3;reasons.push("sóng nền cao")}
  else if(wave!==null&&wave>=1.5){level=Math.max(level,2);reasons.push("sóng tăng")}
  if(wp>=.25){level=Math.max(level,2);reasons.push("ensemble còn kịch bản gió mạnh")}
  else if(wp>=.10)level=Math.max(level,1);
  if(rp>=.50){level=Math.max(level,2);reasons.push("ensemble nghiêng về mưa")}
  else if(rp>=.25)level=Math.max(level,1);
  return {level,reasons};
}
function futureRisk(row){
  if(!row)return {level:0,reasons:["chưa đủ dữ liệu"]};
  const wp=num(row.wind?.prob)||0,rp=num(row.rain?.prob)||0;
  const w95=num(row.wind?.q95),r90=num(row.rain?.q90);
  let level=0,reasons=[];
  if(wp>=.45||(w95!==null&&w95>=39)){level=3;reasons.push("gió mạnh")}
  else if(wp>=.20||(w95!==null&&w95>=30)){level=Math.max(level,2);reasons.push("gió cần theo dõi")}
  else if(wp>=.08)level=Math.max(level,1);
  if(rp>=.65||(r90!==null&&r90>=20)){level=3;reasons.push("mưa cao")}
  else if(rp>=.35||(r90!==null&&r90>=8)){level=Math.max(level,2);reasons.push("mưa tăng")}
  else if(rp>=.15)level=Math.max(level,1);
  return {level,reasons};
}
function riskAt(id){
  const p=point(id);
  return state.step?futureRisk(nearestEnsembleRow(p,state.step)):currentRisk(p);
}
function riskClass(level){return level>=3?"alert":level>=1?"watch":"ok"}
function riskLabel(level){return level>=3?"CAO":level>=2?"THEO DÕI":level>=1?"LƯU Ý":"ỔN"}

function jotripMetric(id){
  const p=point(id),l=p.local||{},m=p.model||{},n=p.nowcast||{};
  const row=state.step?nearestEnsembleRow(p,state.step):null;
  if(state.layer==="risk"){
    const r=riskAt(id);
    return {value:r.level,label:riskLabel(r.level),norm:Math.max(.05,r.level/3),level:r.level};
  }
  if(state.layer==="rain"){
    const v=state.step?num(row?.rain?.q50):num(l.rain_rate_mm_h);
    const vv=v??0;
    return {value:vv,label:fmt(vv,state.step?1:2)+(state.step?" mm":" mm/h"),norm:clamp(vv/12,0,1),level:vv>=10?3:vv>=3?2:vv>=.3?1:0};
  }
  if(state.layer==="wind"){
    const v=state.step?num(row?.wind?.q50):num(l.wind_kmh??m.wind_kmh);
    const vv=v??0;
    return {value:vv,label:fmt(vv,0)+" km/h",norm:clamp(vv/42,0,1),level:vv>=39?3:vv>=29?2:vv>=20?1:0};
  }
  if(state.layer==="waves"){
    const v=num(l.wave_hs_m??m.wave_hs_m);
    const vv=v??0;
    return {value:vv,label:fmt(vv,1)+" m",norm:clamp(vv/2.2,0,1),level:vv>=2?3:vv>=1.5?2:vv>=1?1:0};
  }
  const v=num(n.convective_score??l.convection_score);
  const vv=v??0;
  return {value:vv,label:fmt(vv,0)+"/100",norm:clamp(vv/100,0,1),level:vv>=75?3:vv>=60?2:vv>=40?1:0};
}

function makeGrid(){
  const out=[];
  const lat0=9.84,lat1=10.48,lon0=103.78,lon1=104.18;
  const rows=8,cols=7;
  for(let i=0;i<rows;i++){
    const lat=lat0+(lat1-lat0)*i/(rows-1);
    for(let j=0;j<cols;j++){
      const lon=lon0+(lon1-lon0)*j/(cols-1);
      out.push({lat:+lat.toFixed(4),lon:+lon.toFixed(4)});
    }
  }
  return out;
}
const GRID=makeGrid();

async function loadSourceWeather(force=false){
  if(state.sourceWeather&&!force&&Date.now()-state.sourceWeatherAt<10*60*1000)return state.sourceWeather;
  const lats=GRID.map(x=>x.lat).join(",");
  const lons=GRID.map(x=>x.lon).join(",");
  const url="https://api.open-meteo.com/v1/forecast?latitude="+encodeURIComponent(lats)+"&longitude="+encodeURIComponent(lons)+"&current=precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kmh&timezone=Asia%2FBangkok&forecast_days=1";
  const raw=await fetchJSON(url);
  const arr=Array.isArray(raw)?raw:[raw];
  state.sourceWeather=GRID.map((g,i)=>{
    const x=arr[i]||{},c=x.current||{};
    return {...g,precip:num(c.precipitation),wind:num(c.wind_speed_10m),dir:num(c.wind_direction_10m),gust:num(c.wind_gusts_10m),time:c.time||null,gridLat:num(x.latitude),gridLon:num(x.longitude)};
  });
  state.sourceWeatherAt=Date.now();
  return state.sourceWeather;
}

async function loadSourceMarine(force=false){
  if(state.sourceMarine&&!force&&Date.now()-state.sourceMarineAt<15*60*1000)return state.sourceMarine;
  const lats=GRID.map(x=>x.lat).join(",");
  const lons=GRID.map(x=>x.lon).join(",");
  const url="https://marine-api.open-meteo.com/v1/marine?latitude="+encodeURIComponent(lats)+"&longitude="+encodeURIComponent(lons)+"&current=wave_height,wave_direction,wave_period&cell_selection=sea&timezone=Asia%2FBangkok&forecast_days=1";
  const raw=await fetchJSON(url);
  const arr=Array.isArray(raw)?raw:[raw];
  state.sourceMarine=GRID.map((g,i)=>{
    const x=arr[i]||{},c=x.current||{};
    return {...g,wave:num(c.wave_height),dir:num(c.wave_direction),period:num(c.wave_period),time:c.time||null,gridLat:num(x.latitude),gridLon:num(x.longitude)};
  });
  state.sourceMarineAt=Date.now();
  return state.sourceMarine;
}

async function loadRadar(force=false){
  if(state.sourceRadar&&!force&&Date.now()-state.sourceRadarAt<5*60*1000)return state.sourceRadar;
  const raw=await fetchJSON("https://api.rainviewer.com/public/weather-maps.json");
  const past=raw?.radar?.past||[];
  if(!past.length)throw new Error("Radar unavailable");
  state.sourceRadar={host:raw.host,frame:past[past.length-1]};
  state.sourceRadarAt=Date.now();
  return state.sourceRadar;
}

function initMap(){
  state.map=L.map("map",{zoomControl:false,attributionControl:true,minZoom:8,maxZoom:13,preferCanvas:true}).setView([10.17,103.98],10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",{
    maxZoom:19,
    subdomains:"abcd",
    attribution:"&copy; OpenStreetMap &copy; CARTO"
  }).addTo(state.map);
  L.control.zoom({position:"bottomright"}).addTo(state.map);
  state.markerLayer=L.layerGroup().addTo(state.map);
  state.valueLayer=L.layerGroup().addTo(state.map);
  state.actualLayer=L.layerGroup().addTo(state.map);
  state.vectorLayer=L.layerGroup().addTo(state.map);
  state.map.on("click",onMapClick);
}

function clearDynamic(){
  if(state.field){state.map.removeLayer(state.field);state.field=null}
  if(state.radar){state.map.removeLayer(state.radar);state.radar=null}
  state.markerLayer.clearLayers();
  state.valueLayer.clearLayers();
  state.actualLayer.clearLayers();
  state.vectorLayer.clearLayers();
  clearFlowCanvas();
}
function heatLayer(points,options={}){
  if(!L.heatLayer)return null;
  return L.heatLayer(points,{
    radius:options.radius||44,
    blur:options.blur||38,
    minOpacity:options.minOpacity??.22,
    maxZoom:12,
    gradient:options.gradient||{0.15:"#67d48b",0.38:"#e6d94c",0.63:"#f09c3d",1:"#e94e61"}
  });
}

function addAnchorMarker(id,metric){
  const cfg=POINTS[id],selected=id===state.selected;
  const icon=L.divIcon({
    className:"",
    html:'<div class="anchor-dot '+riskClass(metric.level)+'"></div>',
    iconSize:[13,13],iconAnchor:[6,6]
  });
  const mk=L.marker([cfg.lat,cfg.lon],{icon,zIndexOffset:selected?800:300});
  mk.on("click",e=>{L.DomEvent.stopPropagation(e);selectAnchor(id)});
  mk.addTo(state.markerLayer);

  if(state.showLabels){
    const label=L.divIcon({
      className:"",
      html:'<div class="anchor-label '+(selected?"selected":"")+'"><strong>'+esc(cfg.name)+'</strong> · '+esc(metric.label)+'</div>',
      iconSize:[130,23],iconAnchor:[65,-8]
    });
    const lm=L.marker([cfg.lat,cfg.lon],{icon:label,interactive:true,zIndexOffset:selected?700:200});
    lm.on("click",e=>{L.DomEvent.stopPropagation(e);selectAnchor(id)});
    lm.addTo(state.valueLayer);
  }
}

function renderJotrip(){
  clearDynamic();
  const heat=[];
  pointIds().forEach(id=>{
    const m=jotripMetric(id),cfg=POINTS[id];
    heat.push([cfg.lat,cfg.lon,Math.max(.08,m.norm)]);
    addAnchorMarker(id,m);
  });
  state.field=heatLayer(heat,{
    radius:state.layer==="storm"?60:52,
    blur:44,
    minOpacity:.20,
    gradient:state.layer==="rain"
      ?{0.10:"#d8f1ff",0.28:"#5ebcf3",0.52:"#3ecb97",0.72:"#f0dc48",1:"#e95758"}
      :state.layer==="wind"
      ?{0.12:"#b9ecf4",0.34:"#58c8df",0.62:"#f0cb4c",.82:"#ef8a42",1:"#e94e61"}
      :state.layer==="waves"
      ?{0.12:"#d8f4f8",.34:"#55b8df",.60:"#2d82c5",.80:"#e1a54b",1:"#e95a61"}
      :{0.12:"#68d48b",.40:"#f2c846",.68:"#ed8c3c",1:"#e94e61"}
  });
  if(state.field)state.field.addTo(state.map);

  const names={risk:"JoTrip Risk",rain:"JoTrip Rain",wind:"JoTrip Wind",waves:"JoTrip Waves",storm:"Himawari Storm"};
  $("layerTitle").textContent=names[state.layer]||"JoTrip";
  $("layerSource").textContent=state.layer==="storm"?"Himawari observed proxy":"Weather Lab";
  $("layerUpdated").textContent="Cập nhật "+phuQuocTime(localTime());
  $("attributionNote").textContent=state.layer==="storm"
    ?"Himawari proxy là tín hiệu mây đối lưu quan sát từ vệ tinh, không phải quan trắc sét."
    :"JoTrip field là lớp trực quan từ các anchor Weather Lab, không phải độ phân giải gốc của model.";
  renderHeadline();
  renderProbeAnchor();
}

function actualLabelClass(v){return v===true?"ĐANG MƯA":v===false?"KHÔNG MƯA":"CHƯA ĐỦ CỬA SỔ"}
function renderActual(){
  clearDynamic();
  const actual=state.data?.actual||{};
  const v=actual.vvpq||{};
  if(v.status){
    const icon=L.divIcon({className:"",html:'<div class="actual-pin metar"></div>',iconSize:[17,17],iconAnchor:[8,8]});
    const mk=L.marker([10.169,103.995],{icon,zIndexOffset:800}).addTo(state.actualLayer);
    mk.bindTooltip("VVPQ · "+fmt(v.temperature_c,1)+"°C · gió "+fmt(v.wind_kmh,0)+" km/h",{direction:"top"});
    if(state.showLabels){
      const lb=L.divIcon({className:"",html:'<div class="actual-text">VVPQ · '+fmt(v.wind_kmh,0)+' km/h</div>',iconSize:[100,22],iconAnchor:[50,-10]});
      L.marker([10.169,103.995],{icon:lb,interactive:false,zIndexOffset:700}).addTo(state.actualLayer);
    }
  }
  (actual.rain_gauges||[]).forEach(g=>{
    const lat=num(g.lat),lon=num(g.lon);if(lat===null||lon===null)return;
    const icon=L.divIcon({className:"",html:'<div class="actual-pin rain"></div>',iconSize:[17,17],iconAnchor:[8,8]});
    const mk=L.marker([lat,lon],{icon,zIndexOffset:760}).addTo(state.actualLayer);
    const amount=num(g.rain_intensity_mm_h)!==null?fmt(g.rain_intensity_mm_h,1)+" mm/h":num(g.accum_mm)!==null?fmt(g.accum_mm,1)+" mm tích lũy":"-";
    mk.bindTooltip((g.name||"VRain")+" · "+actualLabelClass(g.rain_observed)+" · "+amount,{direction:"top"});
    if(state.showLabels){
      const lb=L.divIcon({className:"",html:'<div class="actual-text">'+esc(g.name||"VRain")+' · '+esc(amount)+'</div>',iconSize:[130,22],iconAnchor:[65,-10]});
      L.marker([lat,lon],{icon:lb,interactive:false,zIndexOffset:700}).addTo(state.actualLayer);
    }
  });
  $("layerTitle").textContent="Actual";
  $("layerSource").textContent="METAR + VRain";
  $("layerUpdated").textContent="Quan trắc có timestamp riêng";
  $("attributionNote").textContent="Actual chỉ gồm số đo thật. Không nội suy thành trường liên tục.";
  $("headline").textContent="Quan trắc thực tế trên đảo";
  $("headlineSub").textContent="VVPQ + "+((actual.rain_gauges||[]).length)+" trạm mưa VRain. Chạm marker để xem giá trị.";
  renderProbeActual();
}

function sourceNormalize(layer,v){
  if(v===null)return 0;
  if(layer==="rain")return clamp(v/10,0,1);
  if(layer==="wind")return clamp(v/45,0,1);
  if(layer==="waves")return clamp(v/2.5,0,1);
  return clamp(v,0,1);
}
function sourceGradient(layer){
  if(layer==="rain")return {0.10:"#d9f3ff",.24:"#64bef3",.45:"#46d09c",.68:"#f1df50",.84:"#ef9644",1:"#e9515c"};
  if(layer==="wind")return {0.10:"#d1f1f5",.30:"#60c9dc",.54:"#4aa1d5",.73:"#f0cb4b",.88:"#ee8b40",1:"#e95361"};
  return {0.10:"#e1f6f9",.30:"#70c5e1",.55:"#438ecb",.72:"#775fc0",.87:"#eea248",1:"#e95661"};
}
function addSourceValues(rows,layer){
  if(!state.showLabels)return;
  rows.forEach((r,i)=>{
    if(i%7!==0)return;
    let txt="-";
    if(layer==="rain")txt=fmt(r.precip,1)+" mm";
    if(layer==="wind")txt=fmt(r.wind,0)+" km/h";
    if(layer==="waves")txt=fmt(r.wave,1)+" m";
    const icon=L.divIcon({className:"",html:'<div class="source-value">'+txt+'</div>',iconSize:[68,20],iconAnchor:[34,10]});
    L.marker([r.lat,r.lon],{icon,interactive:false,zIndexOffset:80}).addTo(state.valueLayer);
  });
}
function addDirectionVectors(rows,kind){
  rows.forEach((r,i)=>{
    if(i%5!==0)return;
    const d=num(r.dir);if(d===null)return;
    let val=kind==="wind"?num(r.wind):num(r.wave);
    if(val===null)return;
    const arrow=kind==="wind"?"↑":"⇧";
    const icon=L.divIcon({
      className:"",
      html:'<div style="transform:rotate('+d+'deg);font-size:'+(kind==="wind"?16:14)+'px;color:'+(kind==="wind"?"#167fa4":"#3a6db5")+';text-shadow:0 1px 3px white;font-weight:900">'+arrow+'</div>',
      iconSize:[20,20],iconAnchor:[10,10]
    });
    L.marker([r.lat,r.lon],{icon,interactive:false,zIndexOffset:90}).addTo(state.vectorLayer);
  });
}

async function renderSource(layer){
  clearDynamic();
  setSourceLoading(true);
  try{
    if(layer==="radar"){
      const rv=await loadRadar();
      const url=rv.host+rv.frame.path+"/256/{z}/{x}/{y}/2/1_0.png";
      state.radar=L.tileLayer(url,{
        opacity:.72,maxNativeZoom:7,maxZoom:13,zIndex:500,
        attribution:'Weather radar by <a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>'
      }).addTo(state.map);
      $("layerTitle").textContent="Radar";
      $("layerSource").textContent="RainViewer";
      $("layerUpdated").textContent="Frame "+phuQuocTime(new Date(rv.frame.time*1000).toISOString());
      $("attributionNote").innerHTML='Radar trực tiếp · Weather data by RainViewer · không cần API key.';
      $("headline").textContent="Radar mưa quanh Phú Quốc";
      $("headlineSub").textContent="Ảnh radar nguồn phủ trực tiếp lên bản đồ. Đây không phải JoTrip Risk.";
      renderProbeSource(null,"radar");
      return;
    }

    if(layer==="satellite"){
      const rows=pointIds().map(id=>{
        const p=point(id),n=p.nowcast||{},cfg=POINTS[id];
        const score=num(n.convective_score??p.local?.convection_score)||0;
        return {id,lat:cfg.lat,lon:cfg.lon,score,cold:num(n.cloud_top_cold_c),cool:num(n.cooling_c_per_20m)};
      });
      const heat=rows.map(r=>[r.lat,r.lon,clamp(r.score/100,0,1)]);
      state.field=heatLayer(heat,{radius:64,blur:48,minOpacity:.25,gradient:{.15:"#d8eef8",.38:"#6c91d4",.60:"#9563c6",.78:"#ed7f4e",1:"#e94e61"}});
      if(state.field)state.field.addTo(state.map);
      rows.forEach(r=>{
        if(!state.showLabels)return;
        const icon=L.divIcon({className:"",html:'<div class="source-value">'+fmt(r.score,0)+'/100</div>',iconSize:[64,20],iconAnchor:[32,10]});
        L.marker([r.lat,r.lon],{icon,interactive:false}).addTo(state.valueLayer);
      });
      $("layerTitle").textContent="Himawari";
      $("layerSource").textContent="JMA Himawari-9 observed";
      $("layerUpdated").textContent="Nowcast "+phuQuocTime(state.data?.points?.duong_dong?.nowcast?.sampled_time);
      $("attributionNote").textContent="Trường màu là trực quan hóa proxy đối lưu từ cửa sổ Himawari quanh các anchor, không phải ảnh pixel vệ tinh gốc.";
      $("headline").textContent="Mây đối lưu quan sát quanh đảo";
      const max=Math.max(0,...rows.map(r=>r.score));
      $("headlineSub").textContent="Chỉ số proxy cao nhất "+Math.round(max)+"/100. Không đồng nghĩa xác suất có sét.";
      renderProbeSource(rows[0],"satellite");
      return;
    }

    if(layer==="rain"||layer==="wind"){
      const rows=await loadSourceWeather();
      const vals=rows.map(r=>layer==="rain"?r.precip:r.wind).filter(v=>v!==null);
      const heat=rows.map(r=>[r.lat,r.lon,Math.max(.03,sourceNormalize(layer,layer==="rain"?r.precip:r.wind))]);
      state.field=heatLayer(heat,{radius:52,blur:42,minOpacity:.18,gradient:sourceGradient(layer)});
      if(state.field)state.field.addTo(state.map);
      addSourceValues(rows,layer);
      if(layer==="wind")addDirectionVectors(rows,"wind");
      $("layerTitle").textContent=layer==="rain"?"Rain grid":"Wind grid";
      $("layerSource").textContent="Open-Meteo · best match";
      $("layerUpdated").textContent="Grid nguồn · "+(rows[0]?.time||"-");
      $("attributionNote").textContent="Source grid độc lập để đối chiếu · Open-Meteo CC BY 4.0 · không cần API key.";
      if(layer==="rain"){
        $("headline").textContent="Trường mưa mô hình quanh Phú Quốc";
        $("headlineSub").textContent="Grid nguồn độc lập · cực đại hiện tại "+fmt(Math.max(0,...vals),1)+" mm.";
      }else{
        $("headline").textContent="Trường gió quanh Phú Quốc";
        $("headlineSub").textContent="Grid nguồn độc lập · tốc độ cao nhất "+fmt(Math.max(0,...vals),0)+" km/h. Mũi tên thể hiện hướng gió.";
      }
      renderProbeSource(nearestGridRow(rows,10.2172,103.9593),layer);
      return;
    }

    if(layer==="waves"){
      const rows=await loadSourceMarine();
      const vals=rows.map(r=>r.wave).filter(v=>v!==null);
      const heat=rows.map(r=>[r.lat,r.lon,Math.max(.03,sourceNormalize("waves",r.wave))]);
      state.field=heatLayer(heat,{radius:54,blur:43,minOpacity:.18,gradient:sourceGradient("waves")});
      if(state.field)state.field.addTo(state.map);
      addSourceValues(rows,"waves");
      addDirectionVectors(rows,"waves");
      $("layerTitle").textContent="Wave grid";
      $("layerSource").textContent="Open-Meteo Marine";
      $("layerUpdated").textContent="Grid biển · "+(rows.find(r=>r.time)?.time||"-");
      $("attributionNote").textContent="Wave source grid · Open-Meteo Marine CC BY 4.0 · không dùng cho dẫn đường hàng hải.";
      $("headline").textContent="Trạng thái sóng quanh Phú Quốc";
      $("headlineSub").textContent="Hs nguồn độc lập · cao nhất trong vùng "+fmt(Math.max(0,...vals),1)+" m. Mũi tên là hướng sóng.";
      renderProbeSource(nearestGridRow(rows,9.98,104.00),"waves");
    }
  }catch(e){
    console.warn("[V3.2 source]",e);
    $("headline").textContent="Lớp nguồn tạm thời chưa tải được";
    $("headlineSub").textContent="JoTrip Weather Lab vẫn hoạt động. Thử lại lớp này sau ít phút.";
    $("layerUpdated").textContent="SOURCE ERROR";
  }finally{
    setSourceLoading(false);
  }
}

function setSourceLoading(on){
  state.loadingSource=on;
  $("layerUpdated").textContent=on?"Đang tải field...":$("layerUpdated").textContent;
}

function nearestGridRow(rows,lat,lon){
  if(!rows?.length)return null;
  let best=null,dist=Infinity;
  rows.forEach(r=>{
    const d=(r.lat-lat)*(r.lat-lat)+(r.lon-lon)*(r.lon-lon);
    if(d<dist){dist=d;best=r}
  });
  return best;
}

function onMapClick(e){
  if(state.mode!=="source")return;
  if(state.layer==="radar")return renderProbeSource({lat:e.latlng.lat,lon:e.latlng.lng},"radar");
  let rows=null;
  if(state.layer==="rain"||state.layer==="wind")rows=state.sourceWeather;
  if(state.layer==="waves")rows=state.sourceMarine;
  if(state.layer==="satellite"){
    rows=pointIds().map(id=>({id,lat:POINTS[id].lat,lon:POINTS[id].lon,score:num(point(id).nowcast?.convective_score),cold:num(point(id).nowcast?.cloud_top_cold_c),cool:num(point(id).nowcast?.cooling_c_per_20m)}));
  }
  if(rows)renderProbeSource(nearestGridRow(rows,e.latlng.lat,e.latlng.lng),state.layer);
}

function renderProbeAnchor(){
  const p=point(),l=p.local||{},m=p.model||{},n=p.nowcast||{},r=riskAt(state.selected);
  $("probeCard").classList.remove("hidden");
  $("probeEyebrow").textContent="JOTRIP · ĐIỂM ĐANG CHỌN";
  $("probeName").textContent=POINTS[state.selected]?.name||p.name||state.selected;
  const chip=$("probeRisk");
  chip.className="risk-chip "+riskClass(r.level);
  chip.textContent=riskLabel(r.level);
  $("probeMetrics").innerHTML=[
    ["Mưa",fmt(l.rain_rate_mm_h,2)+" mm/h",l.rain_class||"ESTIMATED_NOW"],
    ["Gió",fmt(l.wind_kmh??m.wind_kmh,0)+" km/h",l.wind_class||"ESTIMATED_NOW"],
    ["Giật",fmt(m.gust_kmh,0)+" km/h","MODEL"],
    ["Sóng Hs",fmt(l.wave_hs_m??m.wave_hs_m,1)+" m",l.marine_class||"MODEL_ONLY"]
  ].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+esc(String(x[2]).replaceAll("_"," "))+'</small></article>').join("");
  $("probeClass").textContent="Đối lưu "+fmt(n.convective_score??l.convection_score,0)+"/100";
  $("probeTime").textContent="Local Now · "+ageText(localTime());
}
function renderProbeActual(){
  const actual=state.data?.actual||{},v=actual.vvpq||{},g=actual.rain_gauges||[];
  $("probeCard").classList.remove("hidden");
  $("probeEyebrow").textContent="ACTUAL · QUAN TRẮC";
  $("probeName").textContent="Phú Quốc";
  $("probeRisk").className="risk-chip ok";
  $("probeRisk").textContent="MEASURED";
  $("probeMetrics").innerHTML=[
    ["VVPQ gió",fmt(v.wind_kmh,0)+" km/h","METAR"],
    ["VVPQ nhiệt",fmt(v.temperature_c,1)+"°C","METAR"],
    ["Trạm mưa",String(g.length),"VRAIN"],
    ["Mưa mới",g.some(x=>x.rain_observed===true)?"CÓ":g.every(x=>x.rain_observed===false)?"KHÔNG":"CHƯA RÕ","OBSERVED"]
  ].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></article>').join("");
  $("probeClass").textContent="Không nội suy Actual";
  $("probeTime").textContent=v.observed_at?"VVPQ "+phuQuocTime(v.observed_at):"-";
}
function renderProbeSource(r,layer){
  $("probeCard").classList.remove("hidden");
  $("probeEyebrow").textContent="SOURCE · ĐIỂM GẦN NHẤT";
  $("probeName").textContent=layer==="radar"?"Radar probe":layer==="satellite"?(r?.id?POINTS[r.id]?.name:"Himawari"):"Grid source";
  $("probeRisk").className="risk-chip";
  $("probeRisk").textContent="SOURCE";
  if(layer==="radar"){
    $("probeMetrics").innerHTML='<article><span>Radar</span><b>Tile live</b><small>RainViewer</small></article><article><span>Điểm</span><b>'+fmt(r?.lat,2)+', '+fmt(r?.lon,2)+'</b><small>Không suy dBZ từ màu tile</small></article>';
    $("probeClass").textContent="Spatial radar";
    $("probeTime").textContent=state.sourceRadar?.frame?.time?phuQuocTime(new Date(state.sourceRadar.frame.time*1000).toISOString()):"-";
    return;
  }
  if(layer==="satellite"){
    $("probeMetrics").innerHTML=[
      ["Đối lưu",fmt(r?.score,0)+"/100","HIMAWARI"],
      ["Đỉnh mây",r?.cold===null?"-":fmt(r?.cold,1)+"°C","OBSERVED"],
      ["Δ20p",r?.cool===null?"-":fmt(r?.cool,1)+"°C","PROXY"],
      ["Vị trí",r?.id?POINTS[r.id]?.name:"-","ANCHOR"]
    ].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></article>').join("");
    $("probeClass").textContent="Observed satellite proxy";
    $("probeTime").textContent=state.data?.points?.duong_dong?.nowcast?.sampled_time?phuQuocTime(state.data.points.duong_dong.nowcast.sampled_time):"-";
    return;
  }
  if(layer==="rain"||layer==="wind"){
    $("probeMetrics").innerHTML=[
      ["Mưa",fmt(r?.precip,1)+" mm","MODEL GRID"],
      ["Gió",fmt(r?.wind,0)+" km/h","MODEL GRID"],
      ["Giật",fmt(r?.gust,0)+" km/h","MODEL GRID"],
      ["Hướng",r?.dir===null?"-":fmt(r?.dir,0)+"°","MODEL GRID"]
    ].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></article>').join("");
    $("probeClass").textContent="Open-Meteo best match";
    $("probeTime").textContent=r?.time||"-";
    return;
  }
  $("probeMetrics").innerHTML=[
    ["Hs",fmt(r?.wave,1)+" m","MARINE GRID"],
    ["Hướng",r?.dir===null?"-":fmt(r?.dir,0)+"°","MARINE GRID"],
    ["Chu kỳ",fmt(r?.period,1)+" s","MARINE GRID"],
    ["Ô lưới",r?fmt(r.gridLat??r.lat,2)+', '+fmt(r.gridLon??r.lon,2):"-","SEA CELL"]
  ].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></article>').join("");
  $("probeClass").textContent="Open-Meteo Marine";
  $("probeTime").textContent=r?.time||"-";
}

function selectAnchor(id){
  if(!POINTS[id])return;
  state.selected=id;
  if(state.mode==="jotrip")renderJotrip();
  if(innerWidth>900)state.map.panTo([POINTS[id].lat,POINTS[id].lon],{animate:true,duration:.35});
}

function renderHeadline(){
  const rows=pointIds().map(id=>({id,r:riskAt(id)})).sort((a,b)=>b.r.level-a.r.level);
  const worst=rows[0],attention=rows.filter(x=>x.r.level>=2);
  let title="Nhìn chung ổn";
  if(worst?.r.level>=3)title="Có vùng nguy cơ cao";
  else if(worst?.r.level>=2)title="Có vùng cần theo dõi sát";
  else if(worst?.r.level>=1)title="Có tín hiệu cần lưu ý";
  $("headline").textContent=title;
  if(attention.length){
    $("headlineSub").textContent=attention.slice(0,3).map(x=>(POINTS[x.id]?.name||x.id)+" · "+(x.r.reasons[0]||"theo dõi")).join(" | ");
  }else{
    $("headlineSub").textContent="Chưa thấy anchor Weather Lab vượt ngưỡng theo dõi chính ở mốc đang xem.";
  }
}

function renderQuickAlert(){
  const root=$("quickAlert");
  const now=pointIds().map(id=>({id,score:num(point(id).nowcast?.convective_score)||0})).sort((a,b)=>b.score-a.score)[0];
  let future=[];
  pointIds().forEach(id=>{
    [6,12].forEach(lead=>{
      const row=nearestEnsembleRow(point(id),lead);
      if(row)future.push({id,lead,row,r:futureRisk(row)});
    })
  });
  future.sort((a,b)=>b.r.level-a.r.level||a.lead-b.lead);
  root.className="quick-alert neutral";
  $("alertTitle").textContent="Chưa thấy tín hiệu vượt ngưỡng chính";
  $("alertText").textContent="Weather Lab vẫn theo dõi nowcast và ensemble.";
  $("alertWhen").textContent="12H";
  if(now&&now.score>=75){
    root.className="quick-alert alert";
    $("alertTitle").textContent="Đối lưu đang hoạt động mạnh";
    $("alertText").textContent=(POINTS[now.id]?.name||now.id)+" · proxy "+fmt(now.score,0)+"/100.";
    $("alertWhen").textContent="NOW";
  }else if(future[0]?.r.level>=2){
    const f=future[0];
    root.className="quick-alert "+(f.r.level>=3?"alert":"watch");
    $("alertTitle").textContent=f.r.level>=3?"Có tín hiệu bất lợi":"Có tín hiệu cần theo dõi";
    $("alertText").textContent=(POINTS[f.id]?.name||f.id)+" · "+f.r.reasons.slice(0,2).join(", ");
    $("alertWhen").textContent="+"+f.lead+"H";
  }
}

function renderFreshness(){
  const iso=snapshotTime(),age=ageMin(iso),el=$("liveState").parentElement;
  el.className="freshness "+(age>75?"warn":"live");
  $("liveState").textContent=(age>75?"SNAPSHOT CHẬM":"SNAPSHOT LIVE")+" · "+ageText(iso);
}

function setMode(mode,layer){
  state.mode=mode;
  state.layer=layer;
  document.querySelectorAll(".layer-btn").forEach(b=>{
    b.classList.toggle("active",b.dataset.mode===mode&&b.dataset.layer===layer);
  });
  document.querySelectorAll("[data-step]").forEach(b=>b.disabled=mode!=="jotrip");
  if(mode==="jotrip")renderJotrip();
  else if(mode==="actual")renderActual();
  else renderSource(layer);
}

function setStep(step){
  state.step=Number(step)||0;
  document.querySelectorAll("[data-step]").forEach(b=>b.classList.toggle("active",Number(b.dataset.step)===state.step));
  if(state.mode==="jotrip")renderJotrip();
}
function toggleLabels(){
  state.showLabels=!state.showLabels;
  $("toggleLabelsBtn").classList.toggle("active",state.showLabels);
  if(state.mode==="jotrip")renderJotrip();
  else if(state.mode==="actual")renderActual();
  else renderSource(state.layer);
}

function clearFlowCanvas(){
  const c=$("flowCanvas");
  const ctx=c.getContext("2d");
  ctx.clearRect(0,0,c.width,c.height);
}
function fitCanvas(){
  const c=$("flowCanvas"),r=c.getBoundingClientRect(),dpr=Math.min(2,devicePixelRatio||1);
  c.width=Math.max(1,Math.round(r.width*dpr));
  c.height=Math.max(1,Math.round(r.height*dpr));
  c.style.width=r.width+"px";c.style.height=r.height+"px";
}
function drawWindParticles(){
  fitCanvas();
  clearFlowCanvas();
}

async function loadLab(){
  try{
    state.data=await fetchFirst(LAB_URLS);
    if(!state.data?.points?.[state.selected])state.selected=state.data.default_point||pointIds()[0]||"duong_dong";
    renderFreshness();
    renderQuickAlert();
    setMode(state.mode,state.layer);
  }catch(e){
    console.error("[Weather V3.2]",e);
    $("headline").textContent="Weather Lab chưa tải được";
    $("headlineSub").textContent="Bản đồ nguồn vẫn có thể hoạt động. Thử tải lại sau.";
    $("liveState").textContent="LAB ERROR";
    $("liveState").parentElement.className="freshness warn";
  }
}

function events(){
  document.querySelectorAll(".layer-btn").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.mode,b.dataset.layer)));
  document.querySelectorAll("[data-step]").forEach(b=>b.addEventListener("click",()=>setStep(b.dataset.step)));
  $("recenterBtn").addEventListener("click",()=>state.map.setView([10.17,103.98],10,{animate:true}));
  $("toggleLabelsBtn").addEventListener("click",toggleLabels);
  $("probeClose").addEventListener("click",()=>$("probeCard").classList.add("hidden"));
  addEventListener("resize",fitCanvas,{passive:true});
}

function start(){
  initMap();
  events();
  fitCanvas();
  loadLab();
  setInterval(loadLab,10*60*1000);
}

if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);
else start();

})();