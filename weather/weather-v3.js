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
  map:null,data:null,mode:"jotrip",layer:"risk",step:0,selected:"duong_dong",showLabels:true,
  markerLayer:null,valueLayer:null,actualLayer:null,
  sourceWeather:null,sourceMarine:null,sourceRadar:null,
  sourceWeatherAt:0,sourceMarineAt:0,sourceRadarAt:0,
  radarLayers:[],radarIndex:0,radarTimer:null,
  particleRows:null,particleKind:null,particles:[],particleRAF:null,
  activeFieldRows:null,activePalette:"risk",fieldOpacity:.64,loading:false
};
const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));

function parseUTC(s){if(!s)return NaN;return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s)?s:s+"Z")}
function localStamp(iso){const d=new Date(iso||"");return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit",hour12:false}):"-"}
function ageMin(iso){const t=Date.parse(iso||"");return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):Infinity}
function ageText(iso){const m=ageMin(iso);if(!Number.isFinite(m))return "không rõ";if(m<2)return "vừa cập nhật";if(m<60)return Math.round(m)+" phút";return (m/60).toFixed(1)+" giờ"}
function snapshotTime(){return state.data?.generated_at||state.data?.local_generated_at||null}
function localNowTime(){return state.data?.local_generated_at||state.data?.generated_at||null}

async function getJSON(url){const sep=url.includes("?")?"&":"?";const r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}
async function firstJSON(urls){let last;for(const u of urls){try{return await getJSON(u)}catch(e){last=e}}throw last||new Error("unavailable")}

function pointIds(){return (state.data?.island_watch_order||Object.keys(POINTS)).filter(id=>POINTS[id]&&state.data?.points?.[id])}
function point(id=state.selected){return state.data?.points?.[id]||{}}
function ensRow(p,lead){const rows=p?.ensemble?.rows||[];let best=null,d=Infinity;rows.forEach(r=>{const x=num(r.lead_hours);if(x===null)return;const dd=Math.abs(x-lead);if(dd<d){d=dd;best=r}});return best}

function currentRisk(p){
  const l=p.local||{},m=p.model||{},n=p.nowcast||{},rows=(p.ensemble?.rows||[]).slice(0,2);
  const conv=num(n.convective_score??l.convection_score),gust=num(m.gust_kmh),rain=num(m.rain_3h_mm),wave=num(l.wave_hs_m??m.wave_hs_m);
  let wp=0,rp=0,level=0,reasons=[];
  rows.forEach(r=>{wp=Math.max(wp,num(r.wind?.prob)||0);rp=Math.max(rp,num(r.rain?.prob)||0)});
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}else if(conv!==null&&conv>=60){level=Math.max(level,1);reasons.push("đối lưu tăng")}
  if(gust!==null&&gust>=39){level=3;reasons.push("gió giật mạnh")}else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật tăng")}
  if(rain!==null&&rain>=25){level=3;reasons.push("mưa 3 giờ lớn")}else if(rain!==null&&rain>=10){level=Math.max(level,2);reasons.push("mưa tăng")}
  if(wave!==null&&wave>=2){level=3;reasons.push("sóng nền cao")}else if(wave!==null&&wave>=1.5){level=Math.max(level,2);reasons.push("sóng tăng")}
  if(wp>=.25){level=Math.max(level,2);reasons.push("ensemble còn kịch bản gió mạnh")}else if(wp>=.10)level=Math.max(level,1);
  if(rp>=.50){level=Math.max(level,2);reasons.push("ensemble nghiêng về mưa")}else if(rp>=.25)level=Math.max(level,1);
  return {level,reasons};
}
function futureRisk(r){
  if(!r)return {level:0,reasons:["chưa đủ dữ liệu"]};
  const wp=num(r.wind?.prob)||0,rp=num(r.rain?.prob)||0,w95=num(r.wind?.q95),r90=num(r.rain?.q90);
  let level=0,reasons=[];
  if(wp>=.45||(w95!==null&&w95>=39)){level=3;reasons.push("gió mạnh")}else if(wp>=.20||(w95!==null&&w95>=30)){level=Math.max(level,2);reasons.push("gió cần theo dõi")}else if(wp>=.08)level=Math.max(level,1);
  if(rp>=.65||(r90!==null&&r90>=20)){level=3;reasons.push("mưa cao")}else if(rp>=.35||(r90!==null&&r90>=8)){level=Math.max(level,2);reasons.push("mưa tăng")}else if(rp>=.15)level=Math.max(level,1);
  return {level,reasons};
}
function riskAt(id){return state.step?futureRisk(ensRow(point(id),state.step)):currentRisk(point(id))}
function riskClass(v){return v>=3?"alert":v>=1?"watch":"ok"}
function riskLabel(v){return v>=3?"CAO":v>=2?"THEO DÕI":v>=1?"LƯU Ý":"ỔN"}

function jotripMetric(id){
  const p=point(id),l=p.local||{},m=p.model||{},n=p.nowcast||{},r=state.step?ensRow(p,state.step):null;
  if(state.layer==="risk"){const x=riskAt(id);return {value:x.level,norm:x.level/3,label:riskLabel(x.level),level:x.level}}
  if(state.layer==="rain"){const v=(state.step?num(r?.rain?.q50):num(l.rain_rate_mm_h))??0;return {value:v,norm:clamp(v/12,0,1),label:fmt(v,state.step?1:2)+(state.step?" mm":" mm/h"),level:v>=10?3:v>=3?2:v>=.3?1:0}}
  if(state.layer==="wind"){const v=(state.step?num(r?.wind?.q50):num(l.wind_kmh??m.wind_kmh))??0;return {value:v,norm:clamp(v/45,0,1),label:fmt(v,0)+" km/h",level:v>=39?3:v>=29?2:v>=20?1:0}}
  if(state.layer==="storm"){const v=num(n.convective_score??l.convection_score)??0;return {value:v,norm:clamp(v/100,0,1),label:fmt(v,0)+"/100",level:v>=75?3:v>=60?2:v>=40?1:0}}
  const v=num(l.wave_hs_m??m.wave_hs_m)??0;return {value:v,norm:clamp(v/2.2,0,1),label:fmt(v,1)+" m",level:v>=2?3:v>=1.5?2:v>=1?1:0};
}

function makeGrid(){
  const a=[],lat0=9.82,lat1=10.50,lon0=103.76,lon1=104.20,rows=9,cols=8;
  for(let i=0;i<rows;i++)for(let j=0;j<cols;j++)a.push({lat:lat0+(lat1-lat0)*i/(rows-1),lon:lon0+(lon1-lon0)*j/(cols-1)});
  return a;
}
const GRID=makeGrid();

async function loadWeather(force=false){
  if(state.sourceWeather&&!force&&Date.now()-state.sourceWeatherAt<10*60*1000)return;
  const lat=GRID.map(x=>x.lat.toFixed(4)).join(","),lon=GRID.map(x=>x.lon.toFixed(4)).join(",");
  const url="https://api.open-meteo.com/v1/forecast?latitude="+encodeURIComponent(lat)+"&longitude="+encodeURIComponent(lon)+"&hourly=precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kmh&timezone=UTC&forecast_hours=30";
  const raw=await getJSON(url),arr=Array.isArray(raw)?raw:[raw];
  state.sourceWeather=GRID.map((g,i)=>({ ...g, hourly:arr[i]?.hourly||{}, gridLat:num(arr[i]?.latitude),gridLon:num(arr[i]?.longitude)}));
  state.sourceWeatherAt=Date.now();
}
async function loadMarine(force=false){
  if(state.sourceMarine&&!force&&Date.now()-state.sourceMarineAt<15*60*1000)return;
  const lat=GRID.map(x=>x.lat.toFixed(4)).join(","),lon=GRID.map(x=>x.lon.toFixed(4)).join(",");
  const url="https://marine-api.open-meteo.com/v1/marine?latitude="+encodeURIComponent(lat)+"&longitude="+encodeURIComponent(lon)+"&hourly=wave_height,wave_direction,wave_period&cell_selection=sea&timezone=UTC&forecast_hours=30";
  const raw=await getJSON(url),arr=Array.isArray(raw)?raw:[raw];
  state.sourceMarine=GRID.map((g,i)=>({ ...g, hourly:arr[i]?.hourly||{}, gridLat:num(arr[i]?.latitude),gridLon:num(arr[i]?.longitude)}));
  state.sourceMarineAt=Date.now();
}
async function loadRadar(force=false){
  if(state.sourceRadar&&!force&&Date.now()-state.sourceRadarAt<5*60*1000)return;
  const raw=await getJSON("https://api.rainviewer.com/public/weather-maps.json");
  const frames=(raw?.radar?.past||[]).slice(-6);
  if(!frames.length)throw new Error("Radar unavailable");
  state.sourceRadar={host:raw.host,frames};
  state.sourceRadarAt=Date.now();
}
function hourlyRow(raw,step){
  const h=raw?.hourly||{},times=h.time||[];if(!times.length)return null;
  const target=Date.now()+step*3600000;let idx=0,d=Infinity;
  times.forEach((t,i)=>{const tt=parseUTC(t);const dd=Math.abs(tt-target);if(Number.isFinite(tt)&&dd<d){d=dd;idx=i}});
  return {
    lat:raw.lat,lon:raw.lon,gridLat:raw.gridLat,gridLon:raw.gridLon,time:times[idx],
    precip:num(h.precipitation?.[idx]),wind:num(h.wind_speed_10m?.[idx]),dir:num(h.wind_direction_10m?.[idx]??h.wave_direction?.[idx]),gust:num(h.wind_gusts_10m?.[idx]),
    wave:num(h.wave_height?.[idx]),period:num(h.wave_period?.[idx])
  };
}
function weatherRows(){return (state.sourceWeather||[]).map(x=>hourlyRow(x,state.step)).filter(Boolean)}
function marineRows(){return (state.sourceMarine||[]).map(x=>hourlyRow(x,state.step)).filter(Boolean)}

function initMap(){
  state.map=L.map("map",{zoomControl:false,attributionControl:true,minZoom:8,maxZoom:13,preferCanvas:true}).setView([10.17,103.98],10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",{maxZoom:19,subdomains:"abcd",attribution:"&copy; OpenStreetMap &copy; CARTO"}).addTo(state.map);
  L.control.zoom({position:"bottomright"}).addTo(state.map);
  state.markerLayer=L.layerGroup().addTo(state.map);state.valueLayer=L.layerGroup().addTo(state.map);state.actualLayer=L.layerGroup().addTo(state.map);
  state.map.on("moveend zoomend",()=>{redrawField();resetParticles()});
  state.map.on("click",e=>{
    if(state.mode!=="source"||state.layer==="radar")return;
    const rows=state.layer==="waves"?marineRows():weatherRows();
    renderProbeSource(nearestRow(rows,e.latlng.lat,e.latlng.lng),state.layer);
  });
}
function clearRadar(){
  if(state.radarTimer){clearInterval(state.radarTimer);state.radarTimer=null}
  state.radarLayers.forEach(l=>{try{state.map.removeLayer(l)}catch{}});state.radarLayers=[];state.radarIndex=0;
  $("playRadar").classList.add("hidden");
}
function clearDynamic(){
  clearRadar();stopParticles();state.markerLayer.clearLayers();state.valueLayer.clearLayers();state.actualLayer.clearLayers();
  state.activeFieldRows=null;clearCanvas("fieldCanvas");clearCanvas("flowCanvas");
}
function clearCanvas(id){const c=$(id),ctx=c.getContext("2d");ctx.clearRect(0,0,c.width,c.height)}

const PALETTES={
  risk:[[0,[64,198,122]],[.42,[242,191,65]],[.72,[238,137,56]],[1,[229,76,91]]],
  rain:[[0,[194,236,248]],[.25,[83,181,232]],[.48,[67,205,153]],[.70,[241,219,76]],[1,[230,77,91]]],
  wind:[[0,[205,241,244]],[.28,[86,194,216]],[.55,[65,137,205]],[.76,[241,197,70]],[1,[231,83,95]]],
  waves:[[0,[218,244,248]],[.3,[96,191,220]],[.58,[62,127,192]],[.8,[116,87,190]],[1,[231,86,97]]],
  storm:[[0,[215,237,246]],[.35,[104,137,206]],[.62,[145,91,194]],[.82,[237,123,74]],[1,[230,73,91]]]
};
function colorAt(palette,t){
  const p=PALETTES[palette]||PALETTES.risk;t=clamp(t,0,1);
  for(let i=1;i<p.length;i++){if(t<=p[i][0]){const a=p[i-1],b=p[i],q=(t-a[0])/Math.max(.001,b[0]-a[0]);return a[1].map((v,k)=>Math.round(v+(b[1][k]-v)*q))}}
  return p[p.length-1][1];
}
function setCanvasSize(c,scale=.32){
  const r=c.getBoundingClientRect();c.width=Math.max(120,Math.round(r.width*scale));c.height=Math.max(180,Math.round(r.height*scale));return {w:r.width,h:r.height,sx:c.width/r.width,sy:c.height/r.height};
}
function drawField(rows,palette,opacity=.62,coverage=360){
  state.activeFieldRows=rows;state.activePalette=palette;state.fieldOpacity=opacity;
  const c=$("fieldCanvas"),ctx=c.getContext("2d"),sz=setCanvasSize(c,.34),img=ctx.createImageData(c.width,c.height);
  const pts=rows.map(r=>{const p=state.map.latLngToContainerPoint([r.lat,r.lon]);return {x:p.x*sz.sx,y:p.y*sz.sy,n:clamp(r.norm??0,0,1)}}).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
  if(!pts.length){ctx.clearRect(0,0,c.width,c.height);return}
  const maxD=coverage*Math.max(sz.sx,sz.sy);
  for(let y=0;y<c.height;y+=2){
    for(let x=0;x<c.width;x+=2){
      let sw=0,sv=0,near=Infinity;
      for(const p of pts){const dx=x-p.x,dy=y-p.y,d2=dx*dx+dy*dy+5;near=Math.min(near,Math.sqrt(d2));const w=1/d2;sw+=w;sv+=w*p.n}
      if(near>maxD)continue;
      const v=sv/sw,rgb=colorAt(palette,v),fade=clamp(1-near/maxD,0,1),a=Math.round(255*opacity*(.35+.65*fade));
      for(let yy=0;yy<2;yy++)for(let xx=0;xx<2;xx++){const px=x+xx,py=y+yy;if(px>=c.width||py>=c.height)continue;const k=(py*c.width+px)*4;img.data[k]=rgb[0];img.data[k+1]=rgb[1];img.data[k+2]=rgb[2];img.data[k+3]=a}
    }
  }
  ctx.putImageData(img,0,0);
}
function redrawField(){if(state.activeFieldRows)drawField(state.activeFieldRows,state.activePalette,state.fieldOpacity,state.mode==="jotrip"?300:420)}

function addAnchor(id,m){
  const cfg=POINTS[id],selected=id===state.selected;
  const icon=L.divIcon({className:"",html:'<div class="anchor-dot '+riskClass(m.level)+'"></div>',iconSize:[12,12],iconAnchor:[6,6]});
  const mk=L.marker([cfg.lat,cfg.lon],{icon,zIndexOffset:selected?800:300}).addTo(state.markerLayer);
  mk.on("click",()=>selectAnchor(id));
  if(state.showLabels){
    const li=L.divIcon({className:"",html:'<div class="anchor-label '+(selected?"selected":"")+'">'+esc(cfg.name)+' · '+esc(m.label)+'</div>',iconSize:[130,22],iconAnchor:[65,-9]});
    const lm=L.marker([cfg.lat,cfg.lon],{icon:li,zIndexOffset:selected?700:200}).addTo(state.valueLayer);lm.on("click",()=>selectAnchor(id));
  }
}
function renderJotrip(){
  clearDynamic();
  const rows=[];
  pointIds().forEach(id=>{const m=jotripMetric(id),cfg=POINTS[id];rows.push({lat:cfg.lat,lon:cfg.lon,norm:state.layer==="risk"?(m.level===0?.08:m.norm):m.norm});addAnchor(id,m)});
  drawField(rows,state.layer,.60,310);
  const title={risk:"JoTrip Risk",storm:"Storm proxy",rain:"JoTrip Rain",wind:"JoTrip Wind",waves:"JoTrip Waves"}[state.layer]||"JoTrip";
  $("layerTitle").textContent=title;$("layerSource").textContent=state.layer==="storm"?"Himawari + Lab":"Weather Lab";$("layerUpdated").textContent="Cập nhật "+localStamp(localNowTime());
  $("attributionNote").textContent="JoTrip field là lớp trực quan từ anchor Weather Lab, không phải độ phân giải gốc của model.";
  renderHeadline();renderProbeAnchor();configureForecastTimeline();
}

function renderActual(){
  clearDynamic();
  const a=state.data?.actual||{},v=a.vvpq||{},g=a.rain_gauges||[];
  if(v.status){
    const ic=L.divIcon({className:"",html:'<div class="actual-pin metar"></div>',iconSize:[16,16],iconAnchor:[8,8]});const m=L.marker([10.169,103.995],{icon:ic}).addTo(state.actualLayer);
    m.bindTooltip("VVPQ · "+fmt(v.temperature_c,1)+"°C · "+fmt(v.wind_kmh,0)+" km/h");
    if(state.showLabels){const li=L.divIcon({className:"",html:'<div class="actual-text">VVPQ · '+fmt(v.wind_kmh,0)+' km/h</div>',iconSize:[105,22],iconAnchor:[52,-9]});L.marker([10.169,103.995],{icon:li,interactive:false}).addTo(state.actualLayer)}
  }
  g.forEach(x=>{if(num(x.lat)===null||num(x.lon)===null)return;const ic=L.divIcon({className:"",html:'<div class="actual-pin rain"></div>',iconSize:[16,16],iconAnchor:[8,8]});const m=L.marker([x.lat,x.lon],{icon:ic}).addTo(state.actualLayer);const amount=num(x.rain_intensity_mm_h)!==null?fmt(x.rain_intensity_mm_h,1)+" mm/h":fmt(x.accum_mm,1)+" mm tích lũy";m.bindTooltip((x.name||"VRain")+" · "+amount);if(state.showLabels){const li=L.divIcon({className:"",html:'<div class="actual-text">'+esc(x.name||"VRain")+' · '+esc(amount)+'</div>',iconSize:[135,22],iconAnchor:[67,-9]});L.marker([x.lat,x.lon],{icon:li,interactive:false}).addTo(state.actualLayer)}});
  $("headline").textContent="Quan trắc thực tế trên đảo";$("headlineSub").textContent="VVPQ + "+g.length+" trạm mưa VRain. Không nội suy Actual.";
  $("layerTitle").textContent="Actual";$("layerSource").textContent="METAR + VRain";$("layerUpdated").textContent="Timestamp theo từng trạm";$("attributionNote").textContent="Actual chỉ là số đo thật, không tô thành trường liên tục.";
  renderProbeActual();configureForecastTimeline(true);
}

function rowsForSource(layer){
  if(layer==="rain"||layer==="wind")return weatherRows();
  if(layer==="waves")return marineRows();
  return [];
}
function normSource(layer,r){if(layer==="rain")return clamp((r.precip??0)/10,0,1);if(layer==="wind")return clamp((r.wind??0)/45,0,1);return clamp((r.wave??0)/2.5,0,1)}
function addSourceLabels(rows,layer){
  if(!state.showLabels)return;
  rows.forEach((r,i)=>{if(i%9!==0)return;let txt=layer==="rain"?fmt(r.precip,1)+" mm":layer==="wind"?fmt(r.wind,0)+" km/h":fmt(r.wave,1)+" m";const li=L.divIcon({className:"",html:'<div class="source-value">'+txt+'</div>',iconSize:[68,20],iconAnchor:[34,10]});L.marker([r.lat,r.lon],{icon:li,interactive:false}).addTo(state.valueLayer)});
}
async function renderSource(layer){
  clearDynamic();$("headline").textContent="Đang tải trường dữ liệu...";$("headlineSub").textContent="Không cần API key.";
  try{
    if(layer==="radar")return await renderRadar();
    if(layer==="rain"||layer==="wind"){await loadWeather();const rows=weatherRows();const field=rows.map(r=>({...r,norm:normSource(layer,r)}));drawField(field,layer,.64,430);addSourceLabels(rows,layer);if(layer==="wind")startParticles(rows,"wind");renderSourceHeadline(rows,layer);renderProbeSource(nearestRow(rows,10.2172,103.9593),layer)}
    if(layer==="waves"){await loadMarine();const rows=marineRows(),field=rows.map(r=>({...r,norm:normSource(layer,r)}));drawField(field,"waves",.64,430);addSourceLabels(rows,layer);startParticles(rows,"waves");renderSourceHeadline(rows,layer);renderProbeSource(nearestRow(rows,9.98,104.00),layer)}
    $("layerTitle").textContent=layer==="rain"?"Rain field":layer==="wind"?"Wind field":"Wave field";$("layerSource").textContent=layer==="waves"?"Open-Meteo Marine":"Open-Meteo";$("layerUpdated").textContent=(rowsForSource(layer)[0]?.time||"-")+" UTC";
    $("attributionNote").textContent="Source field độc lập để đối chiếu · Open-Meteo CC BY 4.0 · không cần API key.";
    configureForecastTimeline();
  }catch(e){console.warn("[V3.3 source]",e);$("headline").textContent="Lớp nguồn chưa tải được";$("headlineSub").textContent="JoTrip Weather Lab vẫn hoạt động. Thử lại lớp này sau.";renderProbeSource(null,layer)}
}
function renderSourceHeadline(rows,layer){
  const vals=rows.map(r=>layer==="rain"?r.precip:layer==="wind"?r.wind:r.wave).filter(v=>v!==null);
  const max=vals.length?Math.max(...vals):null;
  $("headline").textContent=layer==="rain"?"Mưa đang tập trung ở đâu?":layer==="wind"?"Gió đang chạy qua đảo thế nào?":"Sóng quanh Phú Quốc";
  $("headlineSub").textContent=layer==="rain"?"Mưa cao nhất trong grid "+fmt(max,1)+" mm tại mốc đang xem.":layer==="wind"?"Gió cao nhất "+fmt(max,0)+" km/h · particle thể hiện hướng chuyển động.":"Hs cao nhất "+fmt(max,1)+" m · particle thể hiện hướng sóng.";
}
async function renderRadar(){
  await loadRadar();const frames=state.sourceRadar.frames,host=state.sourceRadar.host;
  state.radarLayers=frames.map((f,i)=>L.tileLayer(host+f.path+"/256/{z}/{x}/{y}/2/1_0.png",{opacity:i===frames.length-1?.73:0,maxNativeZoom:7,maxZoom:13,zIndex:550,attribution:'Weather radar by <a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>'}).addTo(state.map));
  state.radarIndex=frames.length-1;showRadarFrame(state.radarIndex);
  $("headline").textContent="Radar mưa đang chuyển động";$("headlineSub").textContent="Chuỗi "+frames.length+" frame gần nhất. Nhấn ▶ hoặc kéo timeline.";
  $("layerTitle").textContent="Radar animation";$("layerSource").textContent="RainViewer";$("attributionNote").textContent="Radar nguồn trực tiếp · không phải JoTrip Risk · không cần API key.";
  configureRadarTimeline();startRadarAnimation();renderProbeSource(null,"radar");
}
function showRadarFrame(i){
  const frames=state.sourceRadar?.frames||[];if(!frames.length)return;i=clamp(i,0,frames.length-1);state.radarIndex=i;
  state.radarLayers.forEach((l,k)=>l.setOpacity(k===i?.73:0));
  const f=frames[i];$("layerUpdated").textContent=localStamp(new Date(f.time*1000).toISOString());$("timeLabel").textContent=localStamp(new Date(f.time*1000).toISOString()).split(" ")[0];
  $("timeSlider").value=i;
}
function startRadarAnimation(){if(state.radarTimer)clearInterval(state.radarTimer);$("playRadar").textContent="❚❚";state.radarTimer=setInterval(()=>showRadarFrame((state.radarIndex+1)%(state.sourceRadar?.frames?.length||1)),850)}
function toggleRadar(){if(state.mode!=="source"||state.layer!=="radar")return;if(state.radarTimer){clearInterval(state.radarTimer);state.radarTimer=null;$("playRadar").textContent="▶"}else startRadarAnimation()}

function nearestRow(rows,lat,lon){let best=null,d=Infinity;(rows||[]).forEach(r=>{const x=(r.lat-lat)**2+(r.lon-lon)**2;if(x<d){d=x;best=r}});return best}

function startParticles(rows,kind){
  stopParticles();if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  state.particleRows=rows;state.particleKind=kind;resetParticles();animateParticles();
}
function resetParticles(){
  if(!state.particleRows)return;fitFlow();
  const c=$("flowCanvas"),count=innerWidth<700?75:150;state.particles=Array.from({length:count},()=>({x:Math.random()*c.width,y:Math.random()*c.height,age:Math.random()*70,max:50+Math.random()*80}));
}
function fitFlow(){const c=$("flowCanvas"),r=c.getBoundingClientRect(),dpr=Math.min(1.35,devicePixelRatio||1);c.width=Math.round(r.width*dpr);c.height=Math.round(r.height*dpr);c.dataset.dpr=dpr}
function projectedVectors(){
  const c=$("flowCanvas"),dpr=Number(c.dataset.dpr)||1;
  return (state.particleRows||[]).map(r=>{const p=state.map.latLngToContainerPoint([r.lat,r.lon]);return {x:p.x*dpr,y:p.y*dpr,dir:num(r.dir),mag:state.particleKind==="wind"?num(r.wind):num(r.wave)}}).filter(v=>v.dir!==null&&v.mag!==null)
}
function animateParticles(){
  const c=$("flowCanvas"),ctx=c.getContext("2d"),vec=projectedVectors();if(!vec.length)return;
  const frame=()=>{
    if(!state.particleRows)return;
    ctx.globalCompositeOperation="destination-out";ctx.fillStyle="rgba(0,0,0,.14)";ctx.fillRect(0,0,c.width,c.height);ctx.globalCompositeOperation="source-over";ctx.lineWidth=state.particleKind==="wind"?1.15:1.35;
    ctx.strokeStyle=state.particleKind==="wind"?"rgba(255,255,255,.78)":"rgba(230,247,255,.82)";
    const vectors=projectedVectors();
    state.particles.forEach(p=>{
      let n=null,d=Infinity;for(const v of vectors){const dd=(p.x-v.x)**2+(p.y-v.y)**2;if(dd<d){d=dd;n=v}}
      if(!n)return;const to=(n.dir+180)*Math.PI/180,spd=state.particleKind==="wind"?clamp(n.mag/9,.55,3.2):clamp(n.mag*1.3,.35,1.9);const nx=p.x+Math.sin(to)*spd,ny=p.y-Math.cos(to)*spd;
      ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(nx,ny);ctx.stroke();p.x=nx;p.y=ny;p.age++;
      if(p.age>p.max||p.x<0||p.y<0||p.x>c.width||p.y>c.height){p.x=Math.random()*c.width;p.y=Math.random()*c.height;p.age=0;p.max=50+Math.random()*80}
    });
    state.particleRAF=requestAnimationFrame(frame);
  };frame();
}
function stopParticles(){if(state.particleRAF)cancelAnimationFrame(state.particleRAF);state.particleRAF=null;state.particleRows=null;state.particles=[];clearCanvas("flowCanvas")}

function renderHeadline(){
  const rows=pointIds().map(id=>({id,r:riskAt(id)})).sort((a,b)=>b.r.level-a.r.level),worst=rows[0],attention=rows.filter(x=>x.r.level>=2);
  $("headline").textContent=worst?.r.level>=3?"Có vùng nguy cơ cao":worst?.r.level>=2?"Có vùng cần theo dõi sát":worst?.r.level>=1?"Có tín hiệu cần lưu ý":"Nhìn chung ổn";
  $("headlineSub").textContent=attention.length?attention.slice(0,3).map(x=>(POINTS[x.id]?.name||x.id)+" · "+(x.r.reasons[0]||"theo dõi")).join(" | "):"Chưa thấy anchor Weather Lab vượt ngưỡng theo dõi chính.";
}
function renderQuickAlert(){
  const root=$("quickAlert"),now=pointIds().map(id=>({id,score:num(point(id).nowcast?.convective_score)||0})).sort((a,b)=>b.score-a.score)[0];
  let future=[];pointIds().forEach(id=>[6,12].forEach(lead=>{const r=ensRow(point(id),lead);if(r)future.push({id,lead,risk:futureRisk(r)})}));future.sort((a,b)=>b.risk.level-a.risk.level||a.lead-b.lead);
  root.className="quick-alert neutral";$("alertTitle").textContent="Chưa thấy tín hiệu vượt ngưỡng chính";$("alertText").textContent="Weather Lab vẫn theo dõi nowcast và ensemble.";$("alertWhen").textContent="12H";
  if(now&&now.score>=75){root.className="quick-alert alert";$("alertTitle").textContent="Đối lưu đang hoạt động mạnh";$("alertText").textContent=(POINTS[now.id]?.name||now.id)+" · proxy "+fmt(now.score,0)+"/100.";$("alertWhen").textContent="NOW"}
  else if(future[0]?.risk.level>=2){const f=future[0];root.className="quick-alert "+(f.risk.level>=3?"alert":"watch");$("alertTitle").textContent=f.risk.level>=3?"Có tín hiệu bất lợi":"Có tín hiệu cần theo dõi";$("alertText").textContent=(POINTS[f.id]?.name||f.id)+" · "+f.risk.reasons.slice(0,2).join(", ");$("alertWhen").textContent="+"+f.lead+"H"}
}
function renderFresh(){const t=snapshotTime(),m=ageMin(t),el=$("liveState").parentElement;el.className="freshness "+(m>75?"warn":"live");$("liveState").textContent=(m>75?"CẬP NHẬT CHẬM":"LIVE")+" · "+ageText(t)}

function renderProbeAnchor(){
  const p=point(),l=p.local||{},m=p.model||{},n=p.nowcast||{},r=riskAt(state.selected);showProbe();
  $("probeEyebrow").textContent="JOTRIP · ĐIỂM ĐANG CHỌN";$("probeName").textContent=POINTS[state.selected]?.name||p.name||state.selected;const chip=$("probeRisk");chip.className="risk-chip "+riskClass(r.level);chip.textContent=riskLabel(r.level);
  $("probeMetrics").innerHTML=[["Mưa",fmt(l.rain_rate_mm_h,2)+" mm/h"],["Gió",fmt(l.wind_kmh??m.wind_kmh,0)+" km/h"],["Giật",fmt(m.gust_kmh,0)+" km/h"],["Sóng",fmt(l.wave_hs_m??m.wave_hs_m,1)+" m"]].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b></article>').join("");
  $("probeClass").textContent="Đối lưu "+fmt(n.convective_score??l.convection_score,0)+"/100";$("probeTime").textContent="Local Now · "+ageText(localNowTime());
}
function renderProbeActual(){
  const a=state.data?.actual||{},v=a.vvpq||{},g=a.rain_gauges||[];showProbe();$("probeEyebrow").textContent="ACTUAL · QUAN TRẮC";$("probeName").textContent="Phú Quốc";$("probeRisk").className="risk-chip ok";$("probeRisk").textContent="MEASURED";
  $("probeMetrics").innerHTML=[["VVPQ gió",fmt(v.wind_kmh,0)+" km/h"],["Nhiệt",fmt(v.temperature_c,1)+"°C"],["Trạm mưa",String(g.length)],["Mưa mới",g.some(x=>x.rain_observed===true)?"CÓ":g.every(x=>x.rain_observed===false)?"KHÔNG":"CHƯA RÕ"]].map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b></article>').join("");
  $("probeClass").textContent="Không nội suy Actual";$("probeTime").textContent=v.observed_at?localStamp(v.observed_at):"-";
}
function renderProbeSource(r,layer){
  showProbe();$("probeEyebrow").textContent="SOURCE · GRID GẦN NHẤT";$("probeName").textContent=layer==="radar"?"Radar":layer==="rain"?"Rain grid":layer==="wind"?"Wind grid":"Wave grid";$("probeRisk").className="risk-chip";$("probeRisk").textContent="SOURCE";
  if(layer==="radar"){$("probeMetrics").innerHTML='<article><span>Radar</span><b>Animated</b></article><article><span>Frames</span><b>'+String(state.sourceRadar?.frames?.length||0)+'</b></article>';$("probeClass").textContent="RainViewer tile";$("probeTime").textContent="-";return}
  const data=layer==="waves"?[["Hs",fmt(r?.wave,1)+" m"],["Hướng",fmt(r?.dir,0)+"°"],["Chu kỳ",fmt(r?.period,1)+" s"],["Mốc",r?.time||"-"]]:[["Mưa",fmt(r?.precip,1)+" mm"],["Gió",fmt(r?.wind,0)+" km/h"],["Giật",fmt(r?.gust,0)+" km/h"],["Hướng",fmt(r?.dir,0)+"°"]];
  $("probeMetrics").innerHTML=data.map(x=>'<article><span>'+x[0]+'</span><b>'+x[1]+'</b></article>').join("");$("probeClass").textContent=layer==="waves"?"Open-Meteo Marine":"Open-Meteo";$("probeTime").textContent=r?.time||"-";
}
function showProbe(){$("probeCard").classList.remove("hidden")}

function configureForecastTimeline(disabled=false){
  clearRadar();const s=$("timeSlider");s.min=0;s.max=18;s.step=6;s.value=state.step;$("timeLabel").textContent=state.step===0?"NOW":"+"+state.step+"H";$("timeEnd").textContent="+18H";$("playRadar").classList.add("hidden");s.disabled=disabled;
}
function configureRadarTimeline(){
  const n=state.sourceRadar?.frames?.length||1,s=$("timeSlider");s.min=0;s.max=n-1;s.step=1;s.value=state.radarIndex;$("timeEnd").textContent="NOW";$("playRadar").classList.remove("hidden");s.disabled=false;
}
function onSlider(v){
  if(state.mode==="source"&&state.layer==="radar"){showRadarFrame(Number(v));return}
  state.step=Number(v)||0;$("timeLabel").textContent=state.step===0?"NOW":"+"+state.step+"H";
  if(state.mode==="jotrip")renderJotrip();else if(state.mode==="source")renderSource(state.layer);
}
function setMode(mode,layer){
  state.mode=mode;state.layer=layer;document.querySelectorAll(".layer-btn").forEach(b=>b.classList.toggle("active",b.dataset.mode===mode&&b.dataset.layer===layer));
  if(mode==="jotrip")renderJotrip();else if(mode==="actual")renderActual();else renderSource(layer);
}
function selectAnchor(id){state.selected=id;if(state.mode==="jotrip")renderJotrip();if(innerWidth>900)state.map.panTo([POINTS[id].lat,POINTS[id].lon],{animate:true,duration:.35})}
function toggleLabels(){state.showLabels=!state.showLabels;$("toggleLabelsBtn").classList.toggle("active",state.showLabels);if(state.mode==="jotrip")renderJotrip();else if(state.mode==="actual")renderActual();else if(state.mode==="source"&&state.layer!=="radar")renderSource(state.layer)}

async function loadLab(){
  if(state.loading)return;state.loading=true;
  try{state.data=await firstJSON(LAB_URLS);if(!state.data?.points?.[state.selected])state.selected=state.data.default_point||"duong_dong";renderFresh();renderQuickAlert();setMode(state.mode,state.layer)}
  catch(e){console.error("[Weather V3.3]",e);$("headline").textContent="Weather Lab chưa tải được";$("headlineSub").textContent="Các lớp source vẫn có thể thử lại.";$("liveState").textContent="LAB ERROR";$("liveState").parentElement.className="freshness warn"}
  finally{state.loading=false}
}
function events(){
  document.querySelectorAll(".layer-btn").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.mode,b.dataset.layer)));
  $("timeSlider").addEventListener("input",e=>onSlider(e.target.value));$("playRadar").addEventListener("click",toggleRadar);
  $("recenterBtn").addEventListener("click",()=>state.map.setView([10.17,103.98],10,{animate:true}));$("toggleLabelsBtn").addEventListener("click",toggleLabels);
  $("probeClose").addEventListener("click",()=>$("probeCard").classList.add("hidden"));$("probeToggle").addEventListener("click",()=>$("probeCard").classList.toggle("compact"));
  addEventListener("resize",()=>{redrawField();resetParticles()},{passive:true});
}
function start(){initMap();events();loadLab();setInterval(loadLab,10*60*1000)}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start();
})();