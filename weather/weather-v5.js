(function(){
"use strict";

const URLS={
  ecmwf:["./spatial-ecmwf.json","/weather/spatial-ecmwf.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/spatial-ecmwf.json"],
  icon:["./spatial-icon.json","/weather/spatial-icon.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/spatial-icon.json"],
  marine:["./spatial-marine.json","/weather/spatial-marine.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/spatial-marine.json"],
  gefs:["./data/weather-ensemble/spatial.json","/data/weather-ensemble/spatial.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-ensemble/spatial.json"],
  nowcast:["./data/weather-nowcast/latest.json","/data/weather-nowcast/latest.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-nowcast/latest.json"],
  critical:["./data/critical.json","/weather/critical.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/gh-pages/weather/data/critical.json"],
  forecast:["./jotrip-forecast.json","/weather/jotrip-forecast.json","https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/gh-pages/weather/jotrip-forecast.json"]
};

const POINTS={
  duong_dong:{lat:10.2172,lon:103.9593,name:"Dương Đông",region:"central_west"},
  cua_can:{lat:10.292693,lon:103.914799,name:"Cửa Cạn",region:"north_northwest"},
  ganh_dau:{lat:10.37077,lon:103.84472,name:"Gành Dầu",region:"north_northwest"},
  bai_thom:{lat:10.411765,lon:104.031055,name:"Bãi Thơm",region:"east_northeast"},
  ham_ninh:{lat:10.18062,lon:104.04463,name:"Hàm Ninh",region:"east_northeast"},
  bai_sao:{lat:10.0572576,lon:104.0363948,name:"Bãi Sao",region:"south_southeast"},
  an_thoi:{lat:9.905,lon:104.005,name:"Biển An Thới",region:"south_southeast"}
};

const state={
  map:null,
  ecmwf:null,
  icon:null,
  marine:null,
  gefs:null,
  nowcast:null,
  critical:null,
  forecast:null,
  layer:"wind",
  frameIndex:0,
  selected:{lat:10.2172,lon:103.9593,anchor:"duong_dong"},
  ensemble:false,
  risk:true,
  actual:false,
  riskLayer:null,
  actualLayer:null,
  radarLayers:[],
  radarMeta:null,
  radarIndex:0,
  timer:null,
  particles:[],
  particleRows:null,
  particleRAF:null,
  cloudTween:0,
  currentRows:null,
  currentFrame:null,
  loading:false
};

const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));

async function fetchJSON(url){
  const sep=url.includes("?")?"&":"?";
  const r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status+" "+url);
  return r.json();
}
async function fetchFirst(urls){
  let last=null;
  for(const u of urls){
    try{return await fetchJSON(u)}catch(e){last=e}
  }
  throw last||new Error("No source");
}
async function optional(urls){
  try{return await fetchFirst(urls)}catch(e){console.warn("[V5 optional]",e);return null}
}

function parseTime(s){
  if(!s)return NaN;
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s)?s:s+"Z");
}
function localStamp(s,withDate=true){
  const d=new Date(s||"");
  if(!Number.isFinite(d.getTime()))return "-";
  return d.toLocaleString("vi-VN",{
    timeZone:"Asia/Ho_Chi_Minh",
    day:withDate?"2-digit":undefined,
    month:withDate?"2-digit":undefined,
    hour:"2-digit",minute:"2-digit",hour12:false
  });
}
function dayLabel(s){
  const d=new Date(s||"");
  if(!Number.isFinite(d.getTime()))return "-";
  return d.toLocaleDateString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",weekday:"short",day:"2-digit",month:"2-digit"});
}
function ageText(s){
  const t=Date.parse(s||"");
  if(!Number.isFinite(t))return "không rõ";
  const m=Math.max(0,(Date.now()-t)/60000);
  if(m<2)return "vừa cập nhật";
  if(m<60)return Math.round(m)+" phút";
  return (m/60).toFixed(1)+" giờ";
}
function distance2(a,b,c,d){return (a-c)*(a-c)+(b-d)*(b-d)}

function initMap(){
  state.map=L.map("map",{zoomControl:false,attributionControl:true,minZoom:8,maxZoom:13,preferCanvas:true}).setView([10.17,103.98],10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png?key=cb1_3q98_1_d8112ce70cc7ec9b9276b0a0",{
    subdomains:"abcd",
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>'
  }).addTo(state.map);
  state.riskLayer=L.layerGroup().addTo(state.map);
  state.actualLayer=L.layerGroup().addTo(state.map);
  state.map.on("moveend zoomend",()=>{renderField();resetParticles();renderUncertainty()});
  state.map.on("click",onMapClick);
}

function ecmwfFrames(){return state.ecmwf?.spatial?.frames||[]}
function gefsFrames(){return state.gefs?.spatial?.frames||[]}
function cloudFrames(){return state.nowcast?.spatial?.frames||[]}
function marineCurrentRows(){return state.marine?.current?.cells||[]}
function marineWaveRows(){return state.marine?.wave?.cells||[]}
function iconRows(){return state.icon?.spatial?.cells||[]}
function baseFrames(){return ecmwfFrames().length?ecmwfFrames():gefsFrames()}

function nearestFrame(frames,targetTime){
  if(!frames?.length)return null;
  let best=frames[0],dist=Infinity;
  frames.forEach(f=>{
    const t=parseTime(f.valid_time||f.sampled_time),d=Math.abs(t-targetTime);
    if(Number.isFinite(t)&&d<dist){dist=d;best=f}
  });
  return best;
}
function nearestRow(rows,lat,lon){
  if(!rows?.length)return null;
  let best=null,dist=Infinity;
  rows.forEach(r=>{
    const d=distance2(r.lat,r.lon,lat,lon);
    if(d<dist){dist=d;best=r}
  });
  return best;
}
function nearestAnchor(lat,lon){
  let best="duong_dong",dist=Infinity;
  Object.entries(POINTS).forEach(([id,p])=>{
    const d=distance2(p.lat,p.lon,lat,lon);
    if(d<dist){dist=d;best=id}
  });
  return best;
}

const PALETTES={
  wind:[[0,[57,58,164]],[.16,[50,91,190]],[.32,[41,151,202]],[.5,[48,193,153]],[.66,[83,198,87]],[.8,[231,205,57]],[.91,[238,132,52]],[1,[203,55,76]]],
  rain:[[0,[39,46,126]],[.12,[45,82,179]],[.28,[38,145,211]],[.45,[35,194,190]],[.62,[55,202,113]],[.78,[232,216,62]],[.9,[237,127,49]],[1,[205,50,82]]],
  waves:[[0,[46,53,143]],[.2,[43,105,186]],[.4,[36,162,203]],[.58,[45,196,164]],[.75,[92,198,93]],[.88,[229,190,59]],[1,[201,66,91]]],
  current:[[0,[39,63,153]],[.18,[36,119,190]],[.38,[31,176,199]],[.58,[43,201,156]],[.76,[89,198,91]],[.9,[231,183,55]],[1,[213,77,65]]],
  storm:[[0,[30,36,94]],[.22,[52,68,160]],[.42,[83,80,188]],[.62,[135,71,183]],[.78,[204,77,132]],[.9,[235,110,62]],[1,[191,48,74]]]
};
function colorAt(name,t){
  const p=PALETTES[name]||PALETTES.wind;t=clamp(t,0,1);
  for(let i=1;i<p.length;i++){
    if(t<=p[i][0]){
      const a=p[i-1],b=p[i],q=(t-a[0])/Math.max(.0001,b[0]-a[0]);
      return a[1].map((v,k)=>Math.round(v+(b[1][k]-v)*q));
    }
  }
  return p[p.length-1][1];
}
function canvasSize(c,scale=.30){
  const r=c.getBoundingClientRect();
  c.width=Math.max(120,Math.round(r.width*scale));
  c.height=Math.max(180,Math.round(r.height*scale));
  c.style.width=r.width+"px";c.style.height=r.height+"px";
  return {sx:c.width/r.width,sy:c.height/r.height};
}
function clearCanvas(id){
  const c=$(id),ctx=c.getContext("2d");
  ctx.clearRect(0,0,c.width,c.height);
}
function fieldNorm(row,layer){
  if(layer==="wind")return clamp((num(row.wind_kmh)??0)/45,0,1);
  if(layer==="rain")return clamp((num(row.rain_mm)??0)/12,0,1);
  if(layer==="waves")return clamp((num(row.wave_hs_m)??0)/2.5,0,1);
  if(layer==="current")return clamp((num(row.speed_kmh)??0)/3.0,0,1);
  return clamp((num(row.convective_score)??0)/100,0,1);
}
function median(values){
  if(!values.length)return 0;
  const a=[...values].sort((x,y)=>x-y),m=Math.floor(a.length/2);
  return a.length%2?a[m]:(a[m-1]+a[m])/2;
}
function spatialSupportRadius(pts){
  if(pts.length<3)return Infinity;
  const nearest=[];
  for(let i=0;i<pts.length;i++){
    let best=Infinity;
    for(let k=0;k<pts.length;k++){
      if(i===k)continue;
      const dx=pts[i].x-pts[k].x,dy=pts[i].y-pts[k].y;
      best=Math.min(best,Math.sqrt(dx*dx+dy*dy));
    }
    if(Number.isFinite(best))nearest.push(best);
  }
  return median(nearest)*.92;
}
function drawIDW(rows,layer,alpha=.76){
  const c=$("fieldCanvas"),ctx=c.getContext("2d"),s=canvasSize(c,.30);
  ctx.clearRect(0,0,c.width,c.height);
  const pts=(rows||[]).map(r=>{
    const p=state.map.latLngToContainerPoint([r.lat,r.lon]);
    return {x:p.x*s.sx,y:p.y*s.sy,n:fieldNorm(r,layer)};
  }).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
  if(!pts.length)return;
  const marine=layer==="waves"||layer==="current";
  const support=marine?spatialSupportRadius(pts):Infinity;
  const support2=support*support;
  const img=ctx.createImageData(c.width,c.height);
  for(let y=0;y<c.height;y++){
    for(let x=0;x<c.width;x++){
      let sw=0,sv=0,near2=Infinity;
      for(const p of pts){
        const dx=x-p.x,dy=y-p.y,d2=dx*dx+dy*dy+3,w=1/d2;
        near2=Math.min(near2,d2);
        sw+=w;sv+=w*p.n;
      }
      if(marine&&near2>support2)continue;
      const v=sv/sw,rgb=colorAt(layer,v),k=(y*c.width+x)*4;
      let localAlpha=alpha;
      if(layer==="rain")localAlpha*=clamp(.08+v*1.6,.08,1);
      if(layer==="storm")localAlpha*=clamp(.18+v*1.15,.18,1);
      img.data[k]=rgb[0];img.data[k+1]=rgb[1];img.data[k+2]=rgb[2];img.data[k+3]=Math.round(255*localAlpha);
    }
  }
  ctx.putImageData(img,0,0);
}

function genericRowsFromGEFS(frame,layer){
  return (frame?.cells||[]).map(c=>{
    if(layer==="wind")return {
      lat:cellLat(c.cell_id),lon:cellLon(c.cell_id),
      wind_kmh:num(c.wind?.q50),
      u10_ms:num(c.wind?.u10_q50_ms),
      v10_ms:num(c.wind?.v10_q50_ms),
      wind_direction_deg:num(c.wind?.direction_q50_deg),
      _ensemble:c.wind
    };
    if(layer==="rain")return {
      lat:cellLat(c.cell_id),lon:cellLon(c.cell_id),
      rain_mm:num(c.rain?.q50),
      _ensemble:c.rain
    };
    return null;
  }).filter(Boolean);
}
function cellLat(id){
  const m=String(id||"").match(/^grid_(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)$/);
  return m?Number(m[1]):0;
}
function cellLon(id){
  const m=String(id||"").match(/^grid_(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)$/);
  return m?Number(m[2]):0;
}

function activeECMWFFrame(){
  const frames=ecmwfFrames();
  if(!frames.length)return null;
  return frames[clamp(state.frameIndex,0,frames.length-1)];
}
function activeBaseFrame(){
  const frames=baseFrames();
  if(!frames.length)return null;
  return frames[clamp(state.frameIndex,0,frames.length-1)];
}
function activeValidTime(){
  if(state.layer==="storm"){
    const f=cloudFrames()[clamp(state.frameIndex,0,Math.max(0,cloudFrames().length-1))];
    return parseTime(f?.sampled_time);
  }
  if(state.layer==="radar"){
    const f=state.radarMeta?.frames?.[state.radarIndex];
    return f?f.time*1000:Date.now();
  }
  if(state.layer==="current")return parseTime(state.marine?.current?.sampled_time);
  return parseTime(activeBaseFrame()?.valid_time);
}
function activeRows(){
  if(state.layer==="storm"){
    const fs=cloudFrames();
    const i=clamp(state.frameIndex,0,Math.max(0,fs.length-1));
    const a=fs[i]?.cells||[];
    if(!a.length||!state.cloudTween||fs.length<2)return a;
    const b=fs[(i+1)%fs.length]?.cells||[];
    if(a.length!==b.length)return a;
    const t=clamp(state.cloudTween/5,0,1);
    return a.map((row,k)=>{
      const next=b[k]||row;
      const mix=(x,y)=>{
        const ax=num(x),by=num(y);
        if(ax===null)return by;
        if(by===null)return ax;
        return ax+(by-ax)*t;
      };
      return {
        ...row,
        cloud_top_cold_c:mix(row.cloud_top_cold_c,next.cloud_top_cold_c),
        cloud_top_median_c:mix(row.cloud_top_median_c,next.cloud_top_median_c),
        cloud_top_high_m:mix(row.cloud_top_high_m,next.cloud_top_high_m),
        cloud_top_median_m:mix(row.cloud_top_median_m,next.cloud_top_median_m),
        cooling_c_per_20m_proxy:mix(row.cooling_c_per_20m_proxy,next.cooling_c_per_20m_proxy),
        convective_score:mix(row.convective_score,next.convective_score),
      };
    });
  }
  if(state.layer==="current")return marineCurrentRows().filter(r=>num(r.speed_kmh)!==null);
  const frame=activeECMWFFrame();
  if(frame?.cells?.length){
    if(state.layer==="waves")return frame.cells.filter(r=>num(r.wave_hs_m)!==null);
    if(state.layer==="rain")return frame.cells.filter(r=>num(r.rain_mm)!==null);
    if(state.layer==="wind")return frame.cells.filter(r=>num(r.wind_kmh)!==null);
    return frame.cells;
  }
  const gf=gefsFrames()[clamp(state.frameIndex,0,Math.max(0,gefsFrames().length-1))];
  return genericRowsFromGEFS(gf,state.layer);
}

function renderField(){
  if(state.layer==="radar"){clearCanvas("fieldCanvas");clearCanvas("uncertaintyCanvas");return}
  const rows=activeRows();
  state.currentRows=rows;
  state.currentFrame=state.layer==="storm"
    ?cloudFrames()[clamp(state.frameIndex,0,Math.max(0,cloudFrames().length-1))]
    :state.layer==="current"
      ?state.marine?.current||null
      :activeECMWFFrame();
  drawIDW(rows,state.layer,state.layer==="storm"?.76:state.layer==="rain"?.82:.88);
}

function drawUncertaintyField(rows,layer){
  const c=$("uncertaintyCanvas"),ctx=c.getContext("2d"),s=canvasSize(c,.24);
  ctx.clearRect(0,0,c.width,c.height);
  if(!rows?.length)return;
  const pts=rows.map(r=>{
    const p=state.map.latLngToContainerPoint([r.lat,r.lon]);
    return {x:p.x*s.sx,y:p.y*s.sy,n:clamp(r.u,0,1)};
  }).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
  if(!pts.length)return;
  const img=ctx.createImageData(c.width,c.height);
  for(let y=0;y<c.height;y++){
    for(let x=0;x<c.width;x++){
      let sw=0,sv=0;
      for(const p of pts){
        const dx=x-p.x,dy=y-p.y,d2=dx*dx+dy*dy+4,w=1/d2;
        sw+=w;sv+=w*p.n;
      }
      const v=sv/sw;
      if(v<.08)continue;
      const k=(y*c.width+x)*4;
      img.data[k]=117;img.data[k+1]=67;img.data[k+2]=170;img.data[k+3]=Math.round(145*clamp((v-.05)/.95,0,1));
    }
  }
  ctx.putImageData(img,0,0);
}
function renderUncertainty(){
  clearCanvas("uncertaintyCanvas");
  if(!state.ensemble||!state.gefs||!["wind","rain"].includes(state.layer))return;
  const t=activeValidTime();
  const frame=nearestFrame(gefsFrames(),Number.isFinite(t)?t:Date.now());
  if(!frame)return;
  const rows=(frame.cells||[]).map(c=>{
    const dist=state.layer==="wind"?c.wind:c.rain;
    const prob=num(dist?.prob)??0;
    const spread=num(dist?.spread)??0;
    const spreadNorm=state.layer==="wind"?clamp(spread/20,0,1):clamp(spread/10,0,1);
    return {lat:cellLat(c.cell_id),lon:cellLon(c.cell_id),u:Math.max(prob,spreadNorm*.55)};
  });
  drawUncertaintyField(rows,state.layer);
}

function fitFlow(){
  const c=$("flowCanvas"),r=c.getBoundingClientRect(),dpr=Math.min(1.4,devicePixelRatio||1);
  c.width=Math.round(r.width*dpr);c.height=Math.round(r.height*dpr);c.dataset.dpr=dpr;
}
function stopParticles(){
  if(state.particleRAF)cancelAnimationFrame(state.particleRAF);
  state.particleRAF=null;state.particleRows=null;state.particles=[];
  clearCanvas("flowCanvas");
}
function resetParticles(){
  if(!state.particleRows)return;
  fitFlow();
  const c=$("flowCanvas"),count=innerWidth<700?280:520;
  state.particles=Array.from({length:count},()=>({
    x:Math.random()*c.width,y:Math.random()*c.height,age:Math.random()*110,max:85+Math.random()*150
  }));
}
function vectorRows(rows,kind){
  if(kind==="current"){
    return (rows||[]).filter(r=>num(r.u_ms)!==null&&num(r.v_ms)!==null).map(r=>({
      ...r,u:num(r.u_ms),v:num(r.v_ms),mag:(num(r.speed_kmh)??0)/3.6
    }));
  }
  if(kind==="waves"){
    return (rows||[]).filter(r=>num(r.wave_direction_deg)!==null&&num(r.wave_hs_m)!==null).map(r=>{
      const to=(num(r.wave_direction_deg)+180)*Math.PI/180;
      const mag=num(r.wave_hs_m)||0;
      return {...r,u:Math.sin(to)*mag,v:Math.cos(to)*mag,mag};
    });
  }
  return (rows||[]).filter(r=>num(r.u10_ms)!==null&&num(r.v10_ms)!==null).map(r=>({
    ...r,u:num(r.u10_ms),v:num(r.v10_ms),mag:Math.hypot(num(r.u10_ms),num(r.v10_ms))
  }));
}
function interpolatedVectorAt(p,pv){
  if(!pv.length)return null;
  const nearest=[];
  for(const v of pv){
    const dx=p.x-v.x,dy=p.y-v.y,d2=dx*dx+dy*dy+18;
    let inserted=false;
    for(let i=0;i<nearest.length;i++){
      if(d2<nearest[i].d2){nearest.splice(i,0,{v,d2});inserted=true;break}
    }
    if(!inserted)nearest.push({v,d2});
    if(nearest.length>4)nearest.length=4;
  }
  let sw=0,u=0,vv=0,mag=0;
  for(const item of nearest){
    const w=1/item.d2;
    sw+=w;u+=item.v.u*w;vv+=item.v.v*w;mag+=(item.v.mag||0)*w;
  }
  return sw?{u:u/sw,v:vv/sw,mag:mag/sw}:null;
}
function startParticles(rows,kind){
  stopParticles();
  if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  let vectors=vectorRows(rows,kind);
  if(!vectors.length&&kind!=="waves"&&state.gefs){
    const gf=nearestFrame(gefsFrames(),activeValidTime()||Date.now());
    vectors=vectorRows(genericRowsFromGEFS(gf,"wind"),"wind");
  }
  if(!vectors.length)return;
  state.particleRows=vectors;
  fitFlow();resetParticles();
  const c=$("flowCanvas"),ctx=c.getContext("2d");
  const tick=()=>{
    if(!state.particleRows)return;
    ctx.globalCompositeOperation="destination-out";
    ctx.fillStyle="rgba(0,0,0,.052)";
    ctx.fillRect(0,0,c.width,c.height);
    ctx.globalCompositeOperation="source-over";
    ctx.strokeStyle=kind==="waves"?"rgba(240,252,255,.92)":"rgba(255,255,255,.96)";
    ctx.lineWidth=kind==="waves"?1.7:1.55;
    const dpr=Number(c.dataset.dpr)||1;
    const pv=state.particleRows.map(r=>{
      const p=state.map.latLngToContainerPoint([r.lat,r.lon]);
      return {x:p.x*dpr,y:p.y*dpr,u:r.u,v:r.v,mag:r.mag};
    });
    state.particles.forEach(p=>{
      const n=interpolatedVectorAt(p,pv);
      if(!n)return;
      const scale=kind==="waves"
        ?clamp((n.mag||0)*1.7,.55,2.7)
        :clamp((n.mag||0)/3.4,.85,4.8);
      const m=Math.max(.001,Math.hypot(n.u,n.v));
      const dx=(n.u/m)*scale,dy=-(n.v/m)*scale;
      const nx=p.x+dx*2.7,ny=p.y+dy*2.7;
      ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(nx,ny);ctx.stroke();
      p.x=nx;p.y=ny;p.age++;
      if(p.age>p.max||p.x<0||p.y<0||p.x>c.width||p.y>c.height){
        p.x=Math.random()*c.width;p.y=Math.random()*c.height;p.age=0;p.max=85+Math.random()*150;
      }
    });
    state.particleRAF=requestAnimationFrame(tick);
  };
  tick();
}

function clearRadar(){
  if(state.radarLayers.length){
    state.radarLayers.forEach(l=>{try{state.map.removeLayer(l)}catch{}});
    state.radarLayers=[];
  }
  state.radarMeta=null;state.radarIndex=0;
}
async function loadRadar(){
  if(state.radarMeta)return;
  const raw=await fetchJSON("https://api.rainviewer.com/public/weather-maps.json");
  const frames=(raw?.radar?.past||[]).slice(-8);
  if(!frames.length)throw new Error("Radar unavailable");
  state.radarMeta={host:raw.host,frames};
  state.radarLayers=frames.map((f,i)=>L.tileLayer(raw.host+f.path+"/256/{z}/{x}/{y}/2/1_0.png",{
    opacity:i===frames.length-1?.78:0,maxNativeZoom:7,maxZoom:13,zIndex:550,
    attribution:'Radar by <a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>'
  }).addTo(state.map));
  state.radarIndex=frames.length-1;
}
function showRadar(i){
  const fs=state.radarMeta?.frames||[];if(!fs.length)return;
  i=clamp(i,0,fs.length-1);state.radarIndex=i;
  state.radarLayers.forEach((l,k)=>l.setOpacity(k===i?.78:0));
  $("timeLabel").textContent=localStamp(new Date(fs[i].time*1000).toISOString(),false);
}
function playRadar(){
  stopTimer();
  $("playBtn").textContent="❚❚";
  state.timer=setInterval(()=>showRadar((state.radarIndex+1)%(state.radarMeta?.frames?.length||1)),800);
}

function renderRisk(){
  state.riskLayer.clearLayers();
  if(!state.risk||!state.critical)return;
  const ids=(state.critical.island_watch_order||Object.keys(POINTS))
    .filter(id=>POINTS[id]&&state.critical.points?.[id]);
  const ranked=ids.map(id=>({id,r:riskAt(id)})).sort((a,b)=>b.r.level-a.r.level);
  const worst=ranked[0]?.id||null;
  const zoom=state.map?.getZoom?.()||10;
  ids.forEach(id=>{
    const cfg=POINTS[id],r=riskAt(id);
    const icon=L.divIcon({className:"",html:'<div class="risk-dot '+riskClass(r.level)+'"></div>',iconSize:[10,10],iconAnchor:[5,5]});
    const m=L.marker([cfg.lat,cfg.lon],{icon,zIndexOffset:900}).addTo(state.riskLayer);
    m.on("click",()=>showAnchorProbe(id));
    const selected=id===state.selected.anchor;
    const severe=id===worst&&r.level>=3;
    const zoomed=zoom>=12&&r.level>=2;
    if(selected||severe||zoomed){
      const li=L.divIcon({className:"",html:'<div class="risk-label">'+esc(cfg.name)+' · '+riskLabel(r.level)+'</div>',iconSize:[118,20],iconAnchor:[59,-9]});
      L.marker([cfg.lat,cfg.lon],{icon:li,interactive:false,zIndexOffset:850}).addTo(state.riskLayer);
    }
  });
}
function renderActual(){
  state.actualLayer.clearLayers();
  if(!state.actual||!state.critical)return;
  const a=state.critical.actual||{},v=a.vvpq||{};
  if(v.status){
    const ic=L.divIcon({className:"",html:'<div class="actual-pin metar"></div>',iconSize:[15,15],iconAnchor:[7,7]});
    const m=L.marker([10.169,103.995],{icon:ic,zIndexOffset:1000}).addTo(state.actualLayer);
    m.on("click",()=>showActualProbe("VVPQ",v));
    const li=L.divIcon({className:"",html:'<div class="actual-label">VVPQ · '+fmt(v.wind_kmh,0)+' km/h</div>',iconSize:[100,20],iconAnchor:[50,-9]});
    L.marker([10.169,103.995],{icon:li,interactive:false,zIndexOffset:950}).addTo(state.actualLayer);
  }
  (a.rain_gauges||[]).forEach(g=>{
    if(num(g.lat)===null||num(g.lon)===null)return;
    const ic=L.divIcon({className:"",html:'<div class="actual-pin rain"></div>',iconSize:[15,15],iconAnchor:[7,7]});
    const m=L.marker([g.lat,g.lon],{icon:ic,zIndexOffset:1000}).addTo(state.actualLayer);
    m.on("click",()=>showActualProbe(g.name||"VRain",g));
    const val=num(g.rain_intensity_mm_h)!==null?fmt(g.rain_intensity_mm_h,1)+" mm/h":fmt(g.accum_mm,1)+" mm";
    const li=L.divIcon({className:"",html:'<div class="actual-label">'+esc(g.name||"VRain")+' · '+val+'</div>',iconSize:[120,20],iconAnchor:[60,-9]});
    L.marker([g.lat,g.lon],{icon:li,interactive:false,zIndexOffset:950}).addTo(state.actualLayer);
  });
}

function nearestEnsembleRow(p,lead){
  const rows=p?.ensemble?.rows||[];let best=null,d=Infinity;
  rows.forEach(r=>{const l=num(r.lead_hours);if(l===null)return;const dd=Math.abs(l-lead);if(dd<d){d=dd;best=r}});
  return best;
}
function currentRisk(p){
  const l=p.local||{},m=p.model||{},n=p.nowcast||{},rows=(p.ensemble?.rows||[]).slice(0,2);
  let level=0,reasons=[],wp=0,rp=0;
  rows.forEach(r=>{wp=Math.max(wp,num(r.wind?.prob)||0);rp=Math.max(rp,num(r.rain?.prob)||0)});
  const conv=num(n.convective_score??l.convection_score),gust=num(m.gust_kmh),rain=num(m.rain_3h_mm),wave=num(l.wave_hs_m??m.wave_hs_m);
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}else if(conv!==null&&conv>=60)level=Math.max(level,1);
  if(gust!==null&&gust>=39){level=3;reasons.push("gió giật mạnh")}else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật tăng")}
  if(rain!==null&&rain>=25){level=3;reasons.push("mưa 3 giờ lớn")}else if(rain!==null&&rain>=10){level=Math.max(level,2);reasons.push("mưa tăng")}
  if(wave!==null&&wave>=2){level=3;reasons.push("sóng nền cao")}else if(wave!==null&&wave>=1.5){level=Math.max(level,2);reasons.push("sóng tăng")}
  if(wp>=.25){level=Math.max(level,2);reasons.push("ensemble gió phân tán")}else if(wp>=.10)level=Math.max(level,1);
  if(rp>=.5){level=Math.max(level,2);reasons.push("ensemble nghiêng về mưa")}else if(rp>=.25)level=Math.max(level,1);
  return {level,reasons};
}
function futureRisk(row){
  if(!row)return {level:0,reasons:[]};
  const wp=num(row.wind?.prob)||0,rp=num(row.rain?.prob)||0,w95=num(row.wind?.q95),r90=num(row.rain?.q90);
  let level=0,reasons=[];
  if(wp>=.45||(w95!==null&&w95>=39)){level=3;reasons.push("gió mạnh")}else if(wp>=.20||(w95!==null&&w95>=30)){level=Math.max(level,2);reasons.push("gió cần theo dõi")}else if(wp>=.08)level=Math.max(level,1);
  if(rp>=.65||(r90!==null&&r90>=20)){level=3;reasons.push("mưa cao")}else if(rp>=.35||(r90!==null&&r90>=8)){level=Math.max(level,2);reasons.push("mưa tăng")}else if(rp>=.15)level=Math.max(level,1);
  return {level,reasons};
}
function regionalRiskAt(id,lead){
  if(!state.forecast)return {level:0,reasons:["D4-D10 trend only"]};
  const regionId=POINTS[id]?.region||"central_west";
  const rows=state.forecast.regions?.[regionId]?.rows||[];
  let best=null,d=Infinity;
  rows.forEach(r=>{const dd=Math.abs((num(r.lead_hours)||0)-lead);if(dd<d){d=dd;best=r}});
  if(!best)return {level:0,reasons:["D4-D10 trend only"]};
  const wp=num(best.wind_prob_30)||0,rp=num(best.rain_prob_5)||0;
  const w90=num(best.wind_q90_kmh),r90=num(best.rain_q90_mm),vari=num(best.variability_score)||0;
  let level=0,reasons=[];
  if(wp>=.45||(w90!==null&&w90>=39)){level=3;reasons.push("ensemble gió mạnh")}
  else if(wp>=.20||(w90!==null&&w90>=30)){level=Math.max(level,2);reasons.push("ensemble gió cần theo dõi")}
  else if(wp>=.08)level=Math.max(level,1);
  if(rp>=.65||(r90!==null&&r90>=20)){level=3;reasons.push("ensemble mưa cao")}
  else if(rp>=.35||(r90!==null&&r90>=8)){level=Math.max(level,2);reasons.push("ensemble mưa tăng")}
  else if(rp>=.15)level=Math.max(level,1);
  if(vari>=70){level=Math.max(level,2);reasons.push("độ phân tán cao")}
  return {level,reasons,confidence:num(best.confidence_score),variability:vari};
}
function riskAt(id){
  const p=state.critical?.points?.[id]||{};
  const lead=currentLeadHours();
  if(lead>72)return regionalRiskAt(id,lead);
  return lead>0?futureRisk(nearestEnsembleRow(p,lead)):currentRisk(p);
}
function riskClass(v){return v>=3?"alert":v>=1?"watch":"ok"}
function riskLabel(v){return v>=3?"CAO":v>=2?"THEO DÕI":v>=1?"LƯU Ý":"ỔN"}

function currentLeadHours(){
  if(state.layer==="storm"||state.layer==="radar"||state.layer==="current")return 0;
  const f=activeBaseFrame();
  if(f&&num(f.lead_hours)!==null)return num(f.lead_hours);
  const t=activeValidTime();return Number.isFinite(t)?Math.max(0,Math.round((t-Date.now())/3600000)):0;
}
function regionalForecastRow(){
  if(!state.forecast)return null;
  const anchor=state.selected.anchor||nearestAnchor(state.selected.lat,state.selected.lon);
  const regionId=POINTS[anchor]?.region||"central_west";
  const rows=state.forecast.regions?.[regionId]?.rows||[];
  const lead=currentLeadHours();
  let best=null,d=Infinity;
  rows.forEach(r=>{const dd=Math.abs((num(r.lead_hours)||0)-lead);if(dd<d){d=dd;best=r}});
  return best;
}
function updateConfidence(){
  if(state.layer==="current"){
    $("confidenceLabel").textContent="Copernicus near-now";
    $("trendLabel").textContent="SURFACE CURRENT";
    return;
  }
  if(state.layer==="storm"){
    $("confidenceLabel").textContent="Observed satellite";
    $("trendLabel").textContent="HIMAWARI";
    return;
  }
  if(state.layer==="radar"){
    $("confidenceLabel").textContent="Observed radar";
    $("trendLabel").textContent="RADAR";
    return;
  }
  const row=regionalForecastRow();
  const lead=currentLeadHours();
  $("confidenceLabel").textContent=row?"Confidence "+fmt(row.confidence_score,0)+"/100":"Confidence --";
  $("trendLabel").textContent=lead>72?"D"+Math.round(lead/24)+" · TREND":"+"+Math.round(lead)+"H";
}

function renderScale(){
  const cfg={
    wind:{g:"linear-gradient(90deg,#3f53ab,#3580c5,#36b3ba,#41c370,#dcc541,#e87d3d,#ca4259)",l:["0","10","20","30","40+"]},
    rain:{g:"linear-gradient(90deg,#3652a4,#367cc5,#34afcf,#39c984,#dfd444,#ec823d,#cd425d)",l:["0","1","3","8","15+"]},
    waves:{g:"linear-gradient(90deg,#374c99,#3474bd,#36a7c8,#45c59b,#d8bd44,#ca4767)",l:["0",".5","1","1.5","2+"]},
    current:{g:"linear-gradient(90deg,#3058a1,#2a89be,#28b8bc,#43c991,#e1c242,#dc5c48)",l:["0",".5","1","2","3+"]},
    storm:{g:"linear-gradient(90deg,#374991,#4268b8,#6d5cbe,#b04daa,#e56950,#be345b)",l:["0","25","50","75","100"]},
    radar:{g:"linear-gradient(90deg,#4559ad,#39a2c9,#4bc77d,#e5d64a,#e57b3d,#cb455c)",l:["Light","","","","Heavy"]}
  }[state.layer];
  $("scaleGradient").style.background=cfg.g;
  $("scaleLabels").innerHTML=cfg.l.map(x=>"<span>"+x+"</span>").join("");
}

function updateReadout(){
  if(state.layer==="radar"){
    $("readoutSource").textContent="RADAR · OBSERVED SOURCE";
    $("readoutValue").textContent="RADAR";$("readoutUnit").textContent="";
    $("readoutPlace").textContent="Phú Quốc";
    $("readoutMeta").textContent=state.radarMeta?"Chuỗi frame gần hiện tại":"Đang tải radar...";
    return;
  }
  const row=nearestRow(state.currentRows,state.selected.lat,state.selected.lon);
  $("readoutPlace").textContent=POINTS[state.selected.anchor]?.name||"Điểm chọn";
  if(state.layer==="wind"){
    $("readoutSource").textContent=activeECMWFFrame()?"ECMWF · MOST LIKELY":"GEFS · P50";
    $("readoutValue").textContent=fmt(row?.wind_kmh,0);$("readoutUnit").textContent="km/h";
    $("readoutMeta").textContent="Gió · "+(row?.gust_kmh!=null?"giật "+fmt(row.gust_kmh,0)+" km/h":"ensemble vector");
  }else if(state.layer==="rain"){
    $("readoutSource").textContent=activeECMWFFrame()?"ECMWF · MOST LIKELY":"GEFS · P50";
    $("readoutValue").textContent=fmt(row?.rain_mm,1);$("readoutUnit").textContent="mm";
    $("readoutMeta").textContent="Mưa trong bước thời gian đang chọn";
  }else if(state.layer==="waves"){
    $("readoutSource").textContent="ECMWF WAVE · MOST LIKELY";
    $("readoutValue").textContent=fmt(row?.wave_hs_m,1);$("readoutUnit").textContent="m Hs";
    $("readoutMeta").textContent="Chu kỳ "+fmt(row?.wave_period_s,1)+" s";
  }else if(state.layer==="current"){
    $("readoutSource").textContent="COPERNICUS · SURFACE CURRENT";
    $("readoutValue").textContent=fmt(row?.speed_kmh,2);$("readoutUnit").textContent="km/h";
    $("readoutMeta").textContent="Hướng tới "+fmt(row?.direction_toward_deg,0)+"° · near-now";
  }else{
    $("readoutSource").textContent="HIMAWARI-9 · OBSERVED";
    $("readoutValue").textContent=fmt(row?.convective_score,0);$("readoutUnit").textContent="/100";
    $("readoutMeta").textContent="Proxy đối lưu · không phải quan trắc sét";
  }
}

function configureTimeline(){
  stopTimer();
  const slider=$("timeSlider");
  $("playBtn").disabled=false;
  slider.disabled=false;
  if(state.layer==="current"){
    slider.min=0;slider.max=0;slider.step=1;slider.value=0;slider.disabled=true;
    $("playBtn").disabled=true;
    $("timelineTicks").innerHTML='<span>NEAR-NOW</span>';
    $("timeLabel").textContent=state.marine?.current?.sampled_time?localStamp(state.marine.current.sampled_time,false):"NOW";
  }else if(state.layer==="storm"){
    const fs=cloudFrames();slider.min=0;slider.max=Math.max(0,fs.length-1);slider.step=1;state.frameIndex=clamp(state.frameIndex,0,Math.max(0,fs.length-1));slider.value=state.frameIndex;
    $("timelineTicks").innerHTML=fs.map(f=>"<span>"+localStamp(f.sampled_time,false)+"</span>").join("");
    $("timeLabel").textContent=fs[state.frameIndex]?localStamp(fs[state.frameIndex].sampled_time,false):"NOW";
  }else if(state.layer==="radar"){
    const fs=state.radarMeta?.frames||[];slider.min=0;slider.max=Math.max(0,fs.length-1);slider.step=1;slider.value=state.radarIndex;
    $("timelineTicks").innerHTML=fs.length?'<span>-60m</span><span>-40m</span><span>-20m</span><span>NOW</span>':"";
    $("timeLabel").textContent="NOW";
  }else{
    const fs=baseFrames();
    slider.min=0;slider.max=Math.max(0,fs.length-1);slider.step=1;state.frameIndex=clamp(state.frameIndex,0,Math.max(0,fs.length-1));slider.value=state.frameIndex;
    const idxs=[0,Math.floor((fs.length-1)*.25),Math.floor((fs.length-1)*.5),Math.floor((fs.length-1)*.75),fs.length-1].filter((v,i,a)=>a.indexOf(v)===i);
    $("timelineTicks").innerHTML=idxs.map(i=>"<span>"+(fs[i]?dayLabel(fs[i].valid_time):"-")+"</span>").join("");
    const f=fs[state.frameIndex];$("timeLabel").textContent=f?localStamp(f.valid_time):"NOW";
  }
  updateConfidence();
}
function selectNearestNowFrame(){
  const fs=baseFrames();if(!fs.length){state.frameIndex=0;return}
  let best=0,d=Infinity;
  fs.forEach((f,i)=>{const dd=Math.abs(parseTime(f.valid_time)-Date.now());if(dd<d){d=dd;best=i}});
  state.frameIndex=best;
}

function stopTimer(){
  if(state.timer){clearInterval(state.timer);state.timer=null}
  state.cloudTween=0;
  $("playBtn").textContent="▶";
}
function togglePlay(){
  if(state.timer){stopTimer();return}
  $("playBtn").textContent="❚❚";
  if(state.layer==="radar"){
    state.timer=setInterval(()=>{showRadar((state.radarIndex+1)%(state.radarMeta?.frames?.length||1));$("timeSlider").value=state.radarIndex},800);
  }else if(state.layer==="storm"){
    const max=Number($("timeSlider").max)||0;
    state.cloudTween=0;
    state.timer=setInterval(()=>{
      state.cloudTween++;
      if(state.cloudTween>5){
        state.cloudTween=0;
        state.frameIndex=state.frameIndex>=max?0:state.frameIndex+1;
        $("timeSlider").value=state.frameIndex;
        const f=cloudFrames()[state.frameIndex];
        $("timeLabel").textContent=f?localStamp(f.sampled_time):"NOW";
      }
      renderField();
      updateReadout();
    },150);
  }else{
    const max=Number($("timeSlider").max)||0;
    state.timer=setInterval(()=>{
      state.frameIndex=state.frameIndex>=max?0:state.frameIndex+1;
      $("timeSlider").value=state.frameIndex;
      renderAll(false);
    },650);
  }
}

async function selectLayer(layer){
  state.layer=layer;
  document.querySelectorAll(".layer").forEach(b=>b.classList.toggle("active",b.dataset.layer===layer));
  clearRadar();stopParticles();stopTimer();
  if(layer==="radar"){
    try{
      await loadRadar();
      configureTimeline();
      showRadar(state.radarIndex);
      togglePlay();
    }catch(e){console.warn(e)}
  }else{
    if(layer==="current")state.frameIndex=0;
    else if(layer!=="storm")selectNearestNowFrame();
    else state.frameIndex=Math.max(0,cloudFrames().length-1);
    configureTimeline();
  }
  renderAll();
  if(layer==="storm"&&cloudFrames().length>1)togglePlay();
}

function renderAll(redrawTimeline=true){
  renderField();
  renderUncertainty();
  stopParticles();
  if(state.layer==="wind"||state.layer==="rain")startParticles(activeRows(),"wind");
  if(state.layer==="waves")startParticles(activeRows(),"waves");
  if(state.layer==="current")startParticles(activeRows(),"current");
  if(state.layer==="storm"){
    const ef=nearestFrame(ecmwfFrames(),activeValidTime()||Date.now());
    if(ef)startParticles(ef.cells||[],"wind");
    else{
      const gf=nearestFrame(gefsFrames(),activeValidTime()||Date.now());
      if(gf)startParticles(genericRowsFromGEFS(gf,"wind"),"wind");
    }
  }
  renderRisk();renderActual();renderScale();updateReadout();updateModelBadge();updateConfidence();
  if(redrawTimeline&&state.layer!=="radar")configureTimeline();
}

function updateModelBadge(){
  if(state.layer==="storm"){
    $("modelName").textContent="HIMAWARI";$("modelRun").textContent=state.nowcast?.sampled_time?localStamp(state.nowcast.sampled_time):"-";return;
  }
  if(state.layer==="radar"){
    $("modelName").textContent="RADAR";$("modelRun").textContent="RainViewer";return;
  }
  if(state.layer==="current"){
    $("modelName").textContent="COPERNICUS";
    $("modelRun").textContent=state.marine?.current?.sampled_time?localStamp(state.marine.current.sampled_time):"-";
    return;
  }
  if(activeECMWFFrame()){
    $("modelName").textContent="ECMWF";$("modelRun").textContent=state.ecmwf?.run_time?localStamp(state.ecmwf.run_time):"-";
  }else{
    $("modelName").textContent="GEFS P50";$("modelRun").textContent=state.gefs?.run_time?localStamp(state.gefs.run_time):"-";
  }
}

function showProbe(title,source,items,extra){
  $("probe").classList.remove("hidden");$("probeTitle").textContent=title;$("probeSource").textContent=source;
  $("probeGrid").innerHTML=items.map(x=>'<div class="probe-item"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b></div>').join("");
  $("probeExtra").textContent=extra||"";
}
function ensembleAt(lat,lon){
  if(!state.gefs)return null;
  const f=nearestFrame(gefsFrames(),activeValidTime()||Date.now());
  if(!f)return null;
  let best=null,d=Infinity;
  (f.cells||[]).forEach(c=>{
    const la=cellLat(c.cell_id),lo=cellLon(c.cell_id),dd=distance2(la,lo,lat,lon);
    if(dd<d){d=dd;best=c}
  });
  return best;
}
function showMapProbe(lat,lon){
  const row=nearestRow(state.currentRows,lat,lon);
  const ens=ensembleAt(lat,lon);
  const anchor=nearestAnchor(lat,lon),p=state.critical?.points?.[anchor]||{},l=p.local||{},m=p.model||{},t=p.tide||{},aq=p.aqi||{};
  const items=[];
  if(state.layer==="wind"){
    const icon=nearestRow(iconRows(),lat,lon);
    const ecmwfWind=num(row?.wind_kmh),iconWind=num(icon?.wind_kmh);
    const delta=ecmwfWind!==null&&iconWind!==null?Math.abs(ecmwfWind-iconWind):null;
    items.push(
      ["ECMWF",fmt(ecmwfWind,0)+" km/h"],
      ["ICON",fmt(iconWind,0)+" km/h"],
      ["Δ model",delta===null?"-":fmt(delta,0)+" km/h"],
      ["GEFS p50",fmt(ens?.wind?.q50,0)+" km/h"],
      ["GEFS p90",fmt(ens?.wind?.q90,0)+" km/h"],
      ["GEFS p95",fmt(ens?.wind?.q95,0)+" km/h"],
      ["P ≥30",ens?.wind?.prob==null?"-":Math.round(ens.wind.prob*100)+"%"],
      ["Spread",fmt(ens?.wind?.spread,1)+" km/h"]
    );
  }
  else if(state.layer==="rain")items.push(
    ["ECMWF",fmt(row?.rain_mm,1)+" mm"],
    ["GEFS p50",fmt(ens?.rain?.q50,1)+" mm"],
    ["GEFS p90",fmt(ens?.rain?.q90,1)+" mm"],
    ["GEFS p95",fmt(ens?.rain?.q95,1)+" mm"],
    ["P ≥5",ens?.rain?.prob==null?"-":Math.round(ens.rain.prob*100)+"%"],
    ["Spread",fmt(ens?.rain?.spread,1)+" mm"]
  );
  else if(state.layer==="waves")items.push(["Hs",fmt(row?.wave_hs_m,1)+" m"],["Hướng",fmt(row?.wave_direction_deg,0)+"°"],["Chu kỳ",fmt(row?.wave_period_s,1)+" s"],["Hmax anchor",fmt(m.wave_hmax_m,1)+" m"]);
  else if(state.layer==="current")items.push(["Dòng",fmt(row?.speed_kmh,2)+" km/h"],["Hướng tới",fmt(row?.direction_toward_deg,0)+"°"],["U",fmt(row?.u_ms,3)+" m/s"],["V",fmt(row?.v_ms,3)+" m/s"]);
  else items.push(["Đối lưu",fmt(row?.convective_score,0)+"/100"],["Đỉnh mây",fmt(row?.cloud_top_cold_c,1)+"°C"],["Độ cao",fmt(row?.cloud_top_high_m,0)+" m"],["Δ20p",fmt(row?.cooling_c_per_20m_proxy,1)+"°C"]);
  const regional=regionalForecastRow();
  const extra=(POINTS[anchor]?.name||anchor)+
    " · Local Now gió "+fmt(l.wind_kmh,0)+" km/h"+
    " · Hmax "+fmt(m.wave_hmax_m,1)+" m"+
    " · dòng "+fmt(m.current_kmh,2)+" km/h"+
    " · triều "+fmt(t.height_m,2)+" m"+
    " · AQI "+fmt(aq.aqi_us,0)+
    (regional?" · confidence "+fmt(regional.confidence_score,0)+"/100 · variability "+fmt(regional.variability_score,0)+"/100":"");
  showProbe("Điểm trên bản đồ",state.layer==="storm"?"HIMAWARI":"SPATIAL + ENSEMBLE",items,extra);
}
function showAnchorProbe(id){
  const p=state.critical?.points?.[id]||{},l=p.local||{},m=p.model||{},t=p.tide||{},aq=p.aqi||{},r=riskAt(id);
  state.selected={lat:POINTS[id].lat,lon:POINTS[id].lon,anchor:id};updateReadout();updateConfidence();
  showProbe(POINTS[id].name,"OPERATIONAL ANCHOR",[
    ["Risk",riskLabel(r.level)],["Local wind",fmt(l.wind_kmh,0)+" km/h"],["Rain",fmt(l.rain_rate_mm_h,2)+" mm/h"],["Hs",fmt(l.wave_hs_m??m.wave_hs_m,1)+" m"],
    ["Hmax",fmt(m.wave_hmax_m,1)+" m"],["Current",fmt(m.current_kmh,2)+" km/h"],["Tide",fmt(t.height_m,2)+" m"],["AQI",fmt(aq.aqi_us,0)]
  ],r.reasons.join(" · ")||"Không có cảnh báo nổi bật.");
}
function showActualProbe(name,g){
  const items=[];
  if(g.wind_kmh!==undefined)items.push(["Gió",fmt(g.wind_kmh,0)+" km/h"]);
  if(g.temperature_c!==undefined)items.push(["Nhiệt",fmt(g.temperature_c,1)+"°C"]);
  if(g.accum_mm!==undefined)items.push(["Tích lũy",fmt(g.accum_mm,1)+" mm"]);
  if(g.rain_intensity_mm_h!==undefined&&g.rain_intensity_mm_h!==null)items.push(["Cường độ",fmt(g.rain_intensity_mm_h,1)+" mm/h"]);
  showProbe(name,"ACTUAL",items,g.observed_at?localStamp(g.observed_at):"");
}

function onMapClick(e){
  state.selected={lat:e.latlng.lat,lon:e.latlng.lng,anchor:nearestAnchor(e.latlng.lat,e.latlng.lng)};
  updateReadout();updateConfidence();
  if(state.layer==="radar")showProbe("Radar","RAINVIEWER",[["Vị trí",fmt(e.latlng.lat,2)+", "+fmt(e.latlng.lng,2)],["Frame",localStamp(new Date((state.radarMeta?.frames?.[state.radarIndex]?.time||0)*1000).toISOString())]],"Không suy cường độ dBZ từ màu tile.");
  else showMapProbe(e.latlng.lat,e.latlng.lng);
}

function renderAlert(){
  const root=$("alertBar");
  if(!state.critical){$("alertTitle").textContent="Weather Lab chưa tải";return}
  const ids=state.critical.island_watch_order||Object.keys(POINTS);
  const rows=ids.filter(id=>state.critical.points?.[id]).map(id=>({id,r:riskAt(id)})).sort((a,b)=>b.r.level-a.r.level);
  const w=rows[0];
  root.className="alert-bar neutral";$("alertTitle").textContent="Chưa thấy tín hiệu vượt ngưỡng chính";$("alertTime").textContent=currentLeadHours()>0?"+"+Math.round(currentLeadHours())+"H":"LIVE";
  if(w?.r.level>=2){
    root.className="alert-bar "+(w.r.level>=3?"alert":"watch");
    $("alertTitle").textContent=(POINTS[w.id]?.name||w.id)+" · "+(w.r.reasons[0]||"cần theo dõi");
  }
}

function setStatus(){
  const missing=[];
  if(!state.ecmwf)missing.push("ECMWF");
  if(!state.gefs)missing.push("GEFS");
  if(!state.nowcast)missing.push("Himawari");
  const el=$("dataStatus").parentElement;
  if(!missing.length){el.className="status-pill live";$("dataStatus").textContent="V5 LIVE"}
  else{el.className="status-pill warn";$("dataStatus").textContent="THIẾU "+missing.join("/")}
}
function sourceFreshness(){
  const parts=[];
  if(state.ecmwf?.generated_at)parts.push("ECMWF "+ageText(state.ecmwf.generated_at));
  if(state.icon?.generated_at)parts.push("ICON spatial");
  if(state.gefs?.generated_at)parts.push("GEFS "+ageText(state.gefs.generated_at));
  if(state.nowcast?.sampled_time)parts.push("Himawari "+ageText(state.nowcast.sampled_time));
  if(state.marine?.generated_at)parts.push("Marine "+ageText(state.marine.generated_at));
  return parts.join(" · ");
}

async function loadAll(){
  if(state.loading)return;state.loading=true;
  const [ecmwf,icon,marine,gefs,nowcast,critical,forecast]=await Promise.all([
    optional(URLS.ecmwf),optional(URLS.icon),optional(URLS.marine),optional(URLS.gefs),optional(URLS.nowcast),optional(URLS.critical),optional(URLS.forecast)
  ]);
  state.ecmwf=ecmwf;state.icon=icon;state.marine=marine;state.gefs=gefs;state.nowcast=nowcast;state.critical=critical;state.forecast=forecast;
  setStatus();
  if(state.ecmwf)selectNearestNowFrame();
  renderAlert();
  renderRisk();renderActual();
  renderAll();
  $("readoutMeta").title=sourceFreshness();
  state.loading=false;
}

function bind(){
  document.querySelectorAll(".layer").forEach(b=>b.addEventListener("click",()=>selectLayer(b.dataset.layer)));
  $("ensembleBtn").addEventListener("click",()=>{state.ensemble=!state.ensemble;$("ensembleBtn").classList.toggle("active",state.ensemble);renderUncertainty()});
  $("riskBtn").addEventListener("click",()=>{state.risk=!state.risk;$("riskBtn").classList.toggle("active",state.risk);renderRisk()});
  $("actualBtn").addEventListener("click",()=>{state.actual=!state.actual;$("actualBtn").classList.toggle("active",state.actual);renderActual()});
  $("recenterBtn").addEventListener("click",()=>state.map.setView([10.17,103.98],10,{animate:true}));
  $("probeClose").addEventListener("click",()=>$("probe").classList.add("hidden"));
  $("playBtn").addEventListener("click",togglePlay);
  $("timeSlider").addEventListener("input",e=>{
    stopTimer();
    if(state.layer==="radar"){showRadar(Number(e.target.value));state.radarIndex=Number(e.target.value);return}
    state.frameIndex=Number(e.target.value);
    renderAll(false);
    const f=state.layer==="storm"?cloudFrames()[state.frameIndex]:activeECMWFFrame();
    $("timeLabel").textContent=f?localStamp(f.valid_time||f.sampled_time):"NOW";
    renderAlert();
  });
  addEventListener("resize",()=>{renderField();renderUncertainty();resetParticles()},{passive:true});
}

async function start(){
  initMap();bind();await loadAll();
  setInterval(async()=>{
    const [nowcast,marine,critical,forecast]=await Promise.all([optional(URLS.nowcast),optional(URLS.marine),optional(URLS.critical),optional(URLS.forecast)]);
    if(nowcast)state.nowcast=nowcast;if(marine)state.marine=marine;if(critical)state.critical=critical;if(forecast)state.forecast=forecast;
    setStatus();renderAlert();renderRisk();renderActual();
    if(state.layer==="storm")renderAll(false);
  },10*60*1000);
}

if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start();
})();