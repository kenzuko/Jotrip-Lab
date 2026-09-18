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
  layer:"wind",
  step:0,
  selected:"duong_dong",
  showLabels:true,
  riskOverlay:true,
  actualOverlay:false,
  data:null,
  weatherRaw:null,
  marineRaw:null,
  weatherAt:0,
  marineAt:0,
  radarMeta:null,
  radarAt:0,
  radarLayers:[],
  radarIndex:0,
  radarTimer:null,
  overlayRisk:null,
  overlayActual:null,
  overlayLabels:null,
  particles:[],
  particleRows:null,
  particleKind:null,
  particleRAF:null,
  loading:false
};

const $=id=>document.getElementById(id);
const num=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?null:Number(v);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const fmt=(v,d=1)=>{v=num(v);return v===null?"-":Number(v.toFixed(d)).toString()};
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const localStamp=iso=>{
  const d=new Date(iso||"");
  return Number.isFinite(d.getTime())?d.toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit",hour12:false}):"-";
};
const ageMin=iso=>{
  const t=Date.parse(iso||"");
  return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):Infinity;
};
const ageText=iso=>{
  const m=ageMin(iso);
  if(!Number.isFinite(m))return "không rõ";
  if(m<2)return "vừa cập nhật";
  if(m<60)return Math.round(m)+" phút";
  return (m/60).toFixed(1)+" giờ";
};

async function getJSON(url){
  const sep=url.includes("?")?"&":"?";
  const r=await fetch(url+sep+"t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  return r.json();
}
async function getFirst(urls){
  let last;
  for(const u of urls){try{return await getJSON(u)}catch(e){last=e}}
  throw last||new Error("unavailable");
}

function makeGrid(){
  const out=[],lat0=9.78,lat1=10.54,lon0=103.70,lon1=104.24,rows=10,cols=9;
  for(let i=0;i<rows;i++){
    for(let j=0;j<cols;j++){
      out.push({
        lat:+(lat0+(lat1-lat0)*i/(rows-1)).toFixed(4),
        lon:+(lon0+(lon1-lon0)*j/(cols-1)).toFixed(4)
      });
    }
  }
  return out;
}
const GRID=makeGrid();

function initMap(){
  state.map=L.map("map",{zoomControl:false,attributionControl:true,minZoom:8,maxZoom:13,preferCanvas:true}).setView([10.17,103.97],10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",{
    subdomains:"abcd",maxZoom:19,attribution:"&copy; OpenStreetMap &copy; CARTO"
  }).addTo(state.map);
  state.overlayRisk=L.layerGroup().addTo(state.map);
  state.overlayActual=L.layerGroup().addTo(state.map);
  state.overlayLabels=L.layerGroup().addTo(state.map);
  state.map.on("moveend zoomend",()=>{renderFieldOnly();resetParticles()});
  state.map.on("click",onMapClick);
}

function snapshotTime(){return state.data?.generated_at||state.data?.local_generated_at||null}
function localNowTime(){return state.data?.local_generated_at||state.data?.generated_at||null}
function point(id=state.selected){return state.data?.points?.[id]||{}}
function pointIds(){return (state.data?.island_watch_order||Object.keys(POINTS)).filter(id=>POINTS[id]&&state.data?.points?.[id])}

function nearestEnsRow(p,lead){
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
  const l=p.local||{},m=p.model||{},n=p.nowcast||{},rows=(p.ensemble?.rows||[]).slice(0,2);
  const conv=num(n.convective_score??l.convection_score),gust=num(m.gust_kmh),rain=num(m.rain_3h_mm),wave=num(l.wave_hs_m??m.wave_hs_m);
  let wp=0,rp=0,level=0,reasons=[];
  rows.forEach(r=>{wp=Math.max(wp,num(r.wind?.prob)||0);rp=Math.max(rp,num(r.rain?.prob)||0)});
  if(conv!==null&&conv>=75){level=Math.max(level,2);reasons.push("đối lưu cao")}
  else if(conv!==null&&conv>=60){level=Math.max(level,1);reasons.push("đối lưu tăng")}
  if(gust!==null&&gust>=39){level=3;reasons.push("gió giật mạnh")}
  else if(gust!==null&&gust>=29){level=Math.max(level,2);reasons.push("gió giật tăng")}
  if(rain!==null&&rain>=25){level=3;reasons.push("mưa 3 giờ lớn")}
  else if(rain!==null&&rain>=10){level=Math.max(level,2);reasons.push("mưa tăng")}
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
  const wp=num(row.wind?.prob)||0,rp=num(row.rain?.prob)||0,w95=num(row.wind?.q95),r90=num(row.rain?.q90);
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
  return state.step?futureRisk(nearestEnsRow(p,state.step)):currentRisk(p);
}
function riskClass(v){return v>=3?"alert":v>=1?"watch":"ok"}
function riskLabel(v){return v>=3?"CAO":v>=2?"THEO DÕI":v>=1?"LƯU Ý":"ỔN"}

async function loadWeather(force=false){
  if(state.weatherRaw&&!force&&Date.now()-state.weatherAt<10*60*1000)return;
  const lats=GRID.map(x=>x.lat).join(","),lons=GRID.map(x=>x.lon).join(",");
  const url="https://api.open-meteo.com/v1/forecast?latitude="+encodeURIComponent(lats)+"&longitude="+encodeURIComponent(lons)+"&hourly=precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kmh&timezone=UTC&forecast_hours=30";
  const raw=await getJSON(url),arr=Array.isArray(raw)?raw:[raw];
  state.weatherRaw=GRID.map((g,i)=>({...g,hourly:arr[i]?.hourly||{},gridLat:num(arr[i]?.latitude),gridLon:num(arr[i]?.longitude)}));
  state.weatherAt=Date.now();
}
async function loadMarine(force=false){
  if(state.marineRaw&&!force&&Date.now()-state.marineAt<15*60*1000)return;
  const lats=GRID.map(x=>x.lat).join(","),lons=GRID.map(x=>x.lon).join(",");
  const url="https://marine-api.open-meteo.com/v1/marine?latitude="+encodeURIComponent(lats)+"&longitude="+encodeURIComponent(lons)+"&hourly=wave_height,wave_direction,wave_period&cell_selection=sea&timezone=UTC&forecast_hours=30";
  const raw=await getJSON(url),arr=Array.isArray(raw)?raw:[raw];
  state.marineRaw=GRID.map((g,i)=>({...g,hourly:arr[i]?.hourly||{},gridLat:num(arr[i]?.latitude),gridLon:num(arr[i]?.longitude)}));
  state.marineAt=Date.now();
}
async function loadRadar(force=false){
  if(state.radarMeta&&!force&&Date.now()-state.radarAt<5*60*1000)return;
  const raw=await getJSON("https://api.rainviewer.com/public/weather-maps.json");
  const frames=(raw?.radar?.past||[]).slice(-8);
  if(!frames.length)throw new Error("Radar unavailable");
  state.radarMeta={host:raw.host,frames};
  state.radarAt=Date.now();
}
function parseTimeUTC(s){
  if(!s)return NaN;
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s)?s:s+"Z");
}
function hourlyAt(raw,step,marine=false){
  const h=raw?.hourly||{},times=h.time||[];
  if(!times.length)return null;
  const target=Date.now()+step*3600000;
  let idx=0,dist=Infinity;
  times.forEach((t,i)=>{
    const tt=parseTimeUTC(t),d=Math.abs(tt-target);
    if(Number.isFinite(tt)&&d<dist){dist=d;idx=i}
  });
  return {
    lat:raw.lat,lon:raw.lon,gridLat:raw.gridLat,gridLon:raw.gridLon,time:times[idx],
    precip:num(h.precipitation?.[idx]),
    wind:num(h.wind_speed_10m?.[idx]),
    dir:num(h.wind_direction_10m?.[idx]??h.wave_direction?.[idx]),
    gust:num(h.wind_gusts_10m?.[idx]),
    wave:num(h.wave_height?.[idx]),
    period:num(h.wave_period?.[idx]),
    marine
  };
}
function weatherRows(step=state.step){return (state.weatherRaw||[]).map(x=>hourlyAt(x,step,false)).filter(Boolean)}
function marineRows(step=state.step){return (state.marineRaw||[]).map(x=>hourlyAt(x,step,true)).filter(Boolean)}

const PALETTES={
  wind:[[0,[70,91,178]],[.18,[57,136,193]],[.38,[61,183,175]],[.58,[76,194,104]],[.76,[222,197,62]],[.9,[232,123,60]],[1,[202,67,89]]],
  rain:[[0,[54,84,170]],[.18,[59,129,197]],[.35,[55,181,204]],[.52,[59,202,131]],[.72,[226,213,66]],[.88,[235,128,59]],[1,[205,67,93]]],
  waves:[[0,[58,80,157]],[.20,[56,120,190]],[.42,[59,171,199]],[.62,[73,199,153]],[.8,[217,190,67]],[1,[202,71,103]]],
  storm:[[0,[63,84,164]],[.35,[79,113,192]],[.58,[135,92,190]],[.78,[224,104,80]],[1,[194,55,92]]]
};
function colorAt(name,t){
  const p=PALETTES[name]||PALETTES.wind;t=clamp(t,0,1);
  for(let i=1;i<p.length;i++){
    if(t<=p[i][0]){
      const a=p[i-1],b=p[i],q=(t-a[0])/Math.max(.001,b[0]-a[0]);
      return a[1].map((v,k)=>Math.round(v+(b[1][k]-v)*q));
    }
  }
  return p[p.length-1][1];
}
function canvasScale(c,scale=.28){
  const r=c.getBoundingClientRect();
  c.width=Math.max(120,Math.round(r.width*scale));
  c.height=Math.max(180,Math.round(r.height*scale));
  c.style.width=r.width+"px";c.style.height=r.height+"px";
  return {sx:c.width/r.width,sy:c.height/r.height,w:r.width,h:r.height};
}
function clearCanvas(id){
  const c=$(id),ctx=c.getContext("2d");
  ctx.clearRect(0,0,c.width,c.height);
}
function drawField(rows,layer){
  const c=$("fieldCanvas"),ctx=c.getContext("2d"),s=canvasScale(c,.28);
  const pts=rows.map(r=>{
    const p=state.map.latLngToContainerPoint([r.lat,r.lon]);
    let raw=0,norm=0;
    if(layer==="wind"){raw=r.wind??0;norm=clamp(raw/45,0,1)}
    if(layer==="rain"){raw=r.precip??0;norm=clamp(raw/10,0,1)}
    if(layer==="waves"){raw=r.wave??0;norm=clamp(raw/2.5,0,1)}
    if(layer==="storm"){raw=r.score??0;norm=clamp(raw/100,0,1)}
    return {x:p.x*s.sx,y:p.y*s.sy,n:norm};
  }).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
  ctx.clearRect(0,0,c.width,c.height);
  if(!pts.length)return;
  const img=ctx.createImageData(c.width,c.height);
  for(let y=0;y<c.height;y++){
    for(let x=0;x<c.width;x++){
      let sw=0,sv=0;
      for(const p of pts){
        const dx=x-p.x,dy=y-p.y,d2=dx*dx+dy*dy+4,w=1/d2;
        sw+=w;sv+=w*p.n;
      }
      const v=sv/sw,rgb=colorAt(layer,v),k=(y*c.width+x)*4;
      img.data[k]=rgb[0];img.data[k+1]=rgb[1];img.data[k+2]=rgb[2];img.data[k+3]=190;
    }
  }
  ctx.putImageData(img,0,0);
}
function drawStormField(){
  if(!state.data)return;
  const rows=pointIds().map(id=>{
    const p=point(id),cfg=POINTS[id];
    return {lat:cfg.lat,lon:cfg.lon,score:num(p.nowcast?.convective_score??p.local?.convection_score)||0};
  });
  drawField(rows,"storm");
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
  const c=$("flowCanvas"),count=innerWidth<700?130:260;
  state.particles=Array.from({length:count},()=>({
    x:Math.random()*c.width,y:Math.random()*c.height,age:Math.random()*90,max:55+Math.random()*100
  }));
}
function projectedVectors(){
  const c=$("flowCanvas"),dpr=Number(c.dataset.dpr)||1;
  return (state.particleRows||[]).map(r=>{
    const p=state.map.latLngToContainerPoint([r.lat,r.lon]);
    return {x:p.x*dpr,y:p.y*dpr,dir:num(r.dir),mag:state.particleKind==="waves"?num(r.wave):num(r.wind)}
  }).filter(v=>v.dir!==null&&v.mag!==null);
}
function startParticles(rows,kind){
  stopParticles();
  if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  state.particleRows=rows;state.particleKind=kind;resetParticles();
  const c=$("flowCanvas"),ctx=c.getContext("2d");
  const tick=()=>{
    if(!state.particleRows)return;
    const vectors=projectedVectors();
    ctx.globalCompositeOperation="destination-out";
    ctx.fillStyle="rgba(0,0,0,.10)";
    ctx.fillRect(0,0,c.width,c.height);
    ctx.globalCompositeOperation="source-over";
    ctx.strokeStyle=kind==="waves"?"rgba(235,250,255,.82)":"rgba(255,255,255,.88)";
    ctx.lineWidth=kind==="waves"?1.45:1.25;
    state.particles.forEach(p=>{
      let n=null,d=Infinity;
      for(const v of vectors){
        const dd=(p.x-v.x)**2+(p.y-v.y)**2;
        if(dd<d){d=dd;n=v}
      }
      if(!n)return;
      const to=(n.dir+180)*Math.PI/180;
      const spd=kind==="waves"?clamp((n.mag||0)*1.4,.45,2.1):clamp((n.mag||0)/7,.7,4.2);
      const len=kind==="waves"?1.8:2.25;
      const nx=p.x+Math.sin(to)*spd*len,ny=p.y-Math.cos(to)*spd*len;
      ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(nx,ny);ctx.stroke();
      p.x=nx;p.y=ny;p.age++;
      if(p.age>p.max||p.x<0||p.y<0||p.x>c.width||p.y>c.height){
        p.x=Math.random()*c.width;p.y=Math.random()*c.height;p.age=0;p.max=55+Math.random()*100;
      }
    });
    state.particleRAF=requestAnimationFrame(tick);
  };
  tick();
}

function clearRadar(){
  if(state.radarTimer){clearInterval(state.radarTimer);state.radarTimer=null}
  state.radarLayers.forEach(l=>{try{state.map.removeLayer(l)}catch{}});
  state.radarLayers=[];state.radarIndex=0;
}
function clearBase(){
  clearRadar();stopParticles();clearCanvas("fieldCanvas");
}
function showRadarFrame(i){
  const frames=state.radarMeta?.frames||[];
  if(!frames.length)return;
  i=clamp(i,0,frames.length-1);state.radarIndex=i;
  state.radarLayers.forEach((l,k)=>l.setOpacity(k===i?.78:0));
  $("timelineSlider").value=i;
  const iso=new Date(frames[i].time*1000).toISOString();
  $("timelineNow").textContent=localStamp(iso).split(" ")[0];
  $("currentSecondary").textContent="Radar "+localStamp(iso);
}
function startRadar(){
  if(state.radarTimer)clearInterval(state.radarTimer);
  $("timelinePlay").textContent="❚❚";
  state.radarTimer=setInterval(()=>showRadarFrame((state.radarIndex+1)%(state.radarMeta?.frames?.length||1)),780);
}
function togglePlay(){
  if(state.layer==="radar"){
    if(state.radarTimer){clearInterval(state.radarTimer);state.radarTimer=null;$("timelinePlay").textContent="▶"}else startRadar();
    return;
  }
  if(state._forecastTimer){
    clearInterval(state._forecastTimer);state._forecastTimer=null;$("timelinePlay").textContent="▶";
  }else{
    $("timelinePlay").textContent="❚❚";
    state._forecastTimer=setInterval(()=>{
      state.step=state.step>=18?0:state.step+1;
      $("timelineSlider").value=state.step;
      renderBaseLayer();
    },700);
  }
}

function nearestRow(rows,lat,lon){
  let best=null,d=Infinity;
  (rows||[]).forEach(r=>{
    const x=(r.lat-lat)**2+(r.lon-lon)**2;
    if(x<d){d=x;best=r}
  });
  return best;
}
function selectedCoord(){
  const p=POINTS[state.selected]||POINTS.duong_dong;
  return [p.lat,p.lon];
}

async function renderBaseLayer(){
  clearBase();
  updateTimelineMode();
  try{
    if(state.layer==="wind"){
      await loadWeather();
      const rows=weatherRows();
      drawField(rows,"wind");
      startParticles(rows,"wind");
      renderCurrentFromRow(nearestRow(rows,...selectedCoord()),"wind");
      renderOutlook("wind");
      setSource("Wind","Open-Meteo","Grid gió + particle");
    }else if(state.layer==="rain"){
      await loadWeather();
      const rows=weatherRows();
      drawField(rows,"rain");
      startParticles(rows,"wind");
      renderCurrentFromRow(nearestRow(rows,...selectedCoord()),"rain");
      renderOutlook("rain");
      setSource("Rain","Open-Meteo","Mưa + chuyển động theo gió");
    }else if(state.layer==="waves"){
      await loadMarine();
      const rows=marineRows();
      drawField(rows,"waves");
      startParticles(rows,"waves");
      renderCurrentFromRow(nearestRow(rows,...selectedCoord()),"waves");
      renderOutlook("waves");
      setSource("Waves","Open-Meteo Marine","Hs + hướng sóng");
    }else if(state.layer==="storm"){
      drawStormField();
      await loadWeather();
      startParticles(weatherRows(),"wind");
      renderStormCurrent();
      renderOutlook("storm");
      setSource("Storm","Himawari + JoTrip","Proxy đối lưu quan sát");
    }else if(state.layer==="radar"){
      await loadRadar();
      const {host,frames}=state.radarMeta;
      state.radarLayers=frames.map((f,i)=>L.tileLayer(host+f.path+"/256/{z}/{x}/{y}/2/1_0.png",{
        opacity:i===frames.length-1?.78:0,maxNativeZoom:7,maxZoom:13,zIndex:550,
        attribution:'Weather radar by <a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>'
      }).addTo(state.map));
      state.radarIndex=frames.length-1;showRadarFrame(state.radarIndex);startRadar();
      $("currentPrimary").textContent="RADAR";
      $("currentSecondary").textContent="Ảnh radar gần nhất";
      $("miniOutlook").innerHTML="";
      setSource("Radar","RainViewer","Animated radar frames");
    }
    renderScale();
    renderOverlays();
  }catch(e){
    console.warn("[V4]",e);
    $("currentPrimary").textContent="--";
    $("currentSecondary").textContent="Lớp dữ liệu đang lỗi";
  }
}

function setSource(title,source,note){
  $("sourceNote").textContent=source+" · "+note;
}
function renderCurrentFromRow(r,layer){
  $("currentPlace").textContent=POINTS[state.selected]?.name||"Phú Quốc";
  if(layer==="wind"){
    $("currentPrimary").textContent=fmt(r?.wind,0)+" km/h";
    $("currentSecondary").textContent="Gió · giật "+fmt(r?.gust,0)+" km/h";
  }else if(layer==="rain"){
    $("currentPrimary").textContent=fmt(r?.precip,1)+" mm";
    $("currentSecondary").textContent="Mưa theo giờ · gió "+fmt(r?.wind,0)+" km/h";
  }else{
    $("currentPrimary").textContent=fmt(r?.wave,1)+" m";
    $("currentSecondary").textContent="Hs · chu kỳ "+fmt(r?.period,1)+" s";
  }
}
function renderStormCurrent(){
  const p=point(),score=num(p.nowcast?.convective_score??p.local?.convection_score);
  $("currentPlace").textContent=POINTS[state.selected]?.name||"Phú Quốc";
  $("currentPrimary").textContent=score===null?"-":fmt(score,0)+"/100";
  $("currentSecondary").textContent="Proxy đối lưu Himawari";
}
function renderOutlook(layer){
  const leads=[6,12,18];
  $("miniOutlook").innerHTML=leads.map(lead=>{
    if(layer==="wind"||layer==="rain"){
      const row=nearestRow(weatherRows(lead),...selectedCoord());
      const value=layer==="wind"?fmt(row?.wind,0)+" km/h":fmt(row?.precip,1)+" mm";
      return '<div class="outlook-item"><span>+'+lead+'H</span><b>'+value+'</b><small>'+esc(row?.time||"")+'</small></div>';
    }
    if(layer==="waves"){
      const row=nearestRow(marineRows(lead),...selectedCoord());
      return '<div class="outlook-item"><span>+'+lead+'H</span><b>'+fmt(row?.wave,1)+' m</b><small>'+esc(row?.time||"")+'</small></div>';
    }
    const r=riskAt(state.selected),txt=riskLabel(r.level);
    return '<div class="outlook-item"><span>+'+lead+'H</span><b>'+txt+'</b><small>JoTrip</small></div>';
  }).join("");
}

function renderScale(){
  const g=$("scaleGradient"),l=$("scaleLabels");
  const cfg={
    wind:{gradient:"linear-gradient(90deg,#465bb2,#39a5ca,#3db7ae,#4cc268,#dec53e,#e87b3c,#ca4359)",labels:["0","10","20","30","40+"]},
    rain:{gradient:"linear-gradient(90deg,#3654aa,#3b81c5,#37b5cc,#3bca83,#e2d542,#eb803b,#cd435d)",labels:["0","1","3","8","15+"]},
    waves:{gradient:"linear-gradient(90deg,#3a509d,#3878be,#3babca,#49c799,#d9be43,#ca4767)",labels:["0",".5","1","1.5","2+"]},
    storm:{gradient:"linear-gradient(90deg,#3f54a4,#4f71c0,#875cbe,#df6850,#c2375c)",labels:["0","40","60","75","100"]},
    radar:{gradient:"linear-gradient(90deg,#4b5eaf,#39a8ca,#50c97e,#ead948,#e6783c,#d0475c)",labels:["Light","","","","Heavy"]}
  }[state.layer];
  g.style.background=cfg.gradient;
  l.innerHTML=cfg.labels.map(x=>"<span>"+x+"</span>").join("");
}
function updateTimelineMode(){
  const s=$("timelineSlider");
  if(state.layer==="radar"){
    const n=state.radarMeta?.frames?.length||8;
    s.min=0;s.max=Math.max(0,n-1);s.step=1;s.value=state.radarIndex;
    $("timelineEnd").textContent="NOW";
    $("dateRow").innerHTML="";
  }else{
    s.min=0;s.max=18;s.step=1;s.value=state.step;
    $("timelineNow").textContent=state.step===0?"NOW":"+"+state.step+"H";
    $("timelineEnd").textContent="+18H";
    $("dateRow").innerHTML='<span>NOW</span><span>+6H</span><span>+12H</span><span>+18H</span>';
  }
}

function renderRiskOverlay(){
  state.overlayRisk.clearLayers();
  if(!state.riskOverlay||!state.data)return;
  pointIds().forEach(id=>{
    const cfg=POINTS[id],r=riskAt(id);
    const icon=L.divIcon({className:"",html:'<div class="risk-dot '+riskClass(r.level)+'"></div>',iconSize:[12,12],iconAnchor:[6,6]});
    const m=L.marker([cfg.lat,cfg.lon],{icon,zIndexOffset:900}).addTo(state.overlayRisk);
    m.on("click",()=>showRiskProbe(id));
    if(state.showLabels&&r.level>=1){
      const li=L.divIcon({className:"",html:'<div class="risk-label">'+esc(cfg.name)+' · '+riskLabel(r.level)+'</div>',iconSize:[118,20],iconAnchor:[59,-9]});
      L.marker([cfg.lat,cfg.lon],{icon:li,interactive:false,zIndexOffset:800}).addTo(state.overlayRisk);
    }
  });
}
function renderActualOverlay(){
  state.overlayActual.clearLayers();
  if(!state.actualOverlay||!state.data)return;
  const a=state.data.actual||{},v=a.vvpq||{};
  if(v.status){
    const ic=L.divIcon({className:"",html:'<div class="actual-pin metar"></div>',iconSize:[15,15],iconAnchor:[7,7]});
    const m=L.marker([10.169,103.995],{icon:ic,zIndexOffset:1000}).addTo(state.overlayActual);
    m.on("click",()=>showActualProbe("VVPQ",v));
    if(state.showLabels){
      const li=L.divIcon({className:"",html:'<div class="actual-label">VVPQ · '+fmt(v.wind_kmh,0)+' km/h</div>',iconSize:[98,20],iconAnchor:[49,-9]});
      L.marker([10.169,103.995],{icon:li,interactive:false,zIndexOffset:950}).addTo(state.overlayActual);
    }
  }
  (a.rain_gauges||[]).forEach(g=>{
    if(num(g.lat)===null||num(g.lon)===null)return;
    const ic=L.divIcon({className:"",html:'<div class="actual-pin rain"></div>',iconSize:[15,15],iconAnchor:[7,7]});
    const m=L.marker([g.lat,g.lon],{icon:ic,zIndexOffset:1000}).addTo(state.overlayActual);
    m.on("click",()=>showActualProbe(g.name||"VRain",g));
    if(state.showLabels){
      const val=num(g.rain_intensity_mm_h)!==null?fmt(g.rain_intensity_mm_h,1)+" mm/h":fmt(g.accum_mm,1)+" mm";
      const li=L.divIcon({className:"",html:'<div class="actual-label">'+esc(g.name||"VRain")+' · '+val+'</div>',iconSize:[118,20],iconAnchor:[59,-9]});
      L.marker([g.lat,g.lon],{icon:li,interactive:false,zIndexOffset:950}).addTo(state.overlayActual);
    }
  });
}
function renderOverlays(){renderRiskOverlay();renderActualOverlay()}

function showProbe(title,source,rows,meta){
  $("probe").classList.remove("hidden");
  $("probeName").textContent=title;
  $("probeSource").textContent=source;
  $("probeRows").innerHTML=rows.map(x=>'<div class="probe-row"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b></div>').join("");
  $("probeMeta").textContent=meta||"";
}
function showRiskProbe(id){
  const r=riskAt(id),p=point(id),l=p.local||{},m=p.model||{};
  state.selected=id;
  showProbe(POINTS[id]?.name||id,"JOTRIP RISK",[
    ["Mức",riskLabel(r.level)],
    ["Mưa",fmt(l.rain_rate_mm_h,2)+" mm/h"],
    ["Gió",fmt(l.wind_kmh??m.wind_kmh,0)+" km/h"],
    ["Sóng",fmt(l.wave_hs_m??m.wave_hs_m,1)+" m"]
  ],r.reasons.slice(0,2).join(" · "));
  renderBaseLayer();
}
function showActualProbe(name,g){
  const rows=[];
  if(g.wind_kmh!==undefined)rows.push(["Gió",fmt(g.wind_kmh,0)+" km/h"]);
  if(g.temperature_c!==undefined)rows.push(["Nhiệt",fmt(g.temperature_c,1)+"°C"]);
  if(g.accum_mm!==undefined)rows.push(["Tích lũy",fmt(g.accum_mm,1)+" mm"]);
  if(g.rain_intensity_mm_h!==undefined&&g.rain_intensity_mm_h!==null)rows.push(["Cường độ",fmt(g.rain_intensity_mm_h,1)+" mm/h"]);
  showProbe(name,"ACTUAL",rows,g.observed_at?localStamp(g.observed_at):"");
}
function onMapClick(e){
  if(state.layer==="radar"){
    showProbe("Radar","RAINVIEWER",[["Vị trí",fmt(e.latlng.lat,2)+", "+fmt(e.latlng.lng,2)],["Frame","Animated"]],"Không suy dBZ từ màu tile.");
    return;
  }
  if(state.layer==="storm"){
    let best=null,d=Infinity;
    pointIds().forEach(id=>{
      const c=POINTS[id],dd=(c.lat-e.latlng.lat)**2+(c.lon-e.latlng.lng)**2;
      if(dd<d){d=dd;best=id}
    });
    const p=point(best),n=p.nowcast||{};
    showProbe(POINTS[best]?.name||best,"HIMAWARI",[
      ["Đối lưu",fmt(n.convective_score,0)+"/100"],
      ["Đỉnh mây",fmt(n.cloud_top_cold_c,1)+"°C"],
      ["Δ20p",fmt(n.cooling_c_per_20m,1)+"°C"],
      ["Nguồn","Himawari"]
    ],n.sampled_time?localStamp(n.sampled_time):"");
    return;
  }
  const rows=state.layer==="waves"?marineRows():weatherRows();
  const r=nearestRow(rows,e.latlng.lat,e.latlng.lng);
  if(!r)return;
  if(state.layer==="wind")showProbe("Grid gần nhất","OPEN-METEO",[
    ["Gió",fmt(r.wind,0)+" km/h"],["Giật",fmt(r.gust,0)+" km/h"],["Hướng",fmt(r.dir,0)+"°"],["Mưa",fmt(r.precip,1)+" mm"]
  ],r.time||"");
  else if(state.layer==="rain")showProbe("Grid gần nhất","OPEN-METEO",[
    ["Mưa",fmt(r.precip,1)+" mm"],["Gió",fmt(r.wind,0)+" km/h"],["Giật",fmt(r.gust,0)+" km/h"],["Hướng",fmt(r.dir,0)+"°"]
  ],r.time||"");
  else showProbe("Grid gần nhất","OPEN-METEO MARINE",[
    ["Hs",fmt(r.wave,1)+" m"],["Hướng",fmt(r.dir,0)+"°"],["Chu kỳ",fmt(r.period,1)+" s"],["Ô lưới",fmt(r.gridLat??r.lat,2)+", "+fmt(r.gridLon??r.lon,2)]
  ],r.time||"");
}

function renderQuickAlert(){
  const root=$("alertPill"),now=pointIds().map(id=>({id,score:num(point(id).nowcast?.convective_score)||0})).sort((a,b)=>b.score-a.score)[0];
  let future=[];
  pointIds().forEach(id=>[6,12].forEach(lead=>{
    const row=nearestEnsRow(point(id),lead);
    if(row)future.push({id,lead,r:futureRisk(row)});
  }));
  future.sort((a,b)=>b.r.level-a.r.level||a.lead-b.lead);
  root.className="alert-pill neutral";$("alertTitle").textContent="Chưa thấy tín hiệu vượt ngưỡng";$("alertWhen").textContent="12H";
  if(now&&now.score>=75){
    root.className="alert-pill alert";$("alertTitle").textContent=(POINTS[now.id]?.name||now.id)+" · đối lưu mạnh";$("alertWhen").textContent="NOW";
  }else if(future[0]?.r.level>=2){
    const f=future[0];root.className="alert-pill "+(f.r.level>=3?"alert":"watch");$("alertTitle").textContent=(POINTS[f.id]?.name||f.id)+" · "+(f.r.reasons[0]||"theo dõi");$("alertWhen").textContent="+"+f.lead+"H";
  }
}
function renderFreshness(){
  const t=snapshotTime(),m=ageMin(t),el=$("liveState").parentElement;
  el.className="live-pill "+(m>75?"warn":"live");
  $("liveState").textContent=(m>75?"CHẬM":"LIVE")+" · "+ageText(t);
}

function renderFieldOnly(){
  if(state.layer==="wind"&&state.weatherRaw)drawField(weatherRows(),"wind");
  if(state.layer==="rain"&&state.weatherRaw)drawField(weatherRows(),"rain");
  if(state.layer==="waves"&&state.marineRaw)drawField(marineRows(),"waves");
  if(state.layer==="storm")drawStormField();
}
function selectLayer(layer){
  state.layer=layer;
  if(state._forecastTimer){clearInterval(state._forecastTimer);state._forecastTimer=null}
  document.querySelectorAll(".layer").forEach(b=>b.classList.toggle("active",b.dataset.layer===layer));
  renderBaseLayer();
}
function setStep(v){
  if(state.layer==="radar"){showRadarFrame(Number(v));return}
  state.step=Number(v)||0;
  $("timelineNow").textContent=state.step===0?"NOW":"+"+state.step+"H";
  renderBaseLayer();
}
function toggleRisk(){
  state.riskOverlay=!state.riskOverlay;
  $("riskOverlayBtn").classList.toggle("active",state.riskOverlay);
  renderRiskOverlay();
}
function toggleActual(){
  state.actualOverlay=!state.actualOverlay;
  $("actualOverlayBtn").classList.toggle("active",state.actualOverlay);
  renderActualOverlay();
}
function toggleLabels(){
  state.showLabels=!state.showLabels;
  $("labelsBtn").classList.toggle("active",state.showLabels);
  renderOverlays();
}
function searchPlace(){
  const q=$("placeSearch").value.trim().toLowerCase();
  if(!q)return;
  const norm=s=>s.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
  const nq=norm(q);
  const hit=Object.entries(POINTS).find(([id,p])=>norm(p.name).includes(nq)||norm(id.replaceAll("_"," ")).includes(nq));
  if(hit){
    state.selected=hit[0];
    state.map.setView([hit[1].lat,hit[1].lon],11,{animate:true});
    renderBaseLayer();
    $("placeSearch").blur();
  }
}

async function loadLab(){
  if(state.loading)return;
  state.loading=true;
  try{
    state.data=await getFirst(LAB_URLS);
    if(!state.data?.points?.[state.selected])state.selected=state.data.default_point||"duong_dong";
    renderFreshness();renderQuickAlert();renderOverlays();
  }catch(e){
    console.warn("[V4 lab]",e);
    $("liveState").textContent="LAB ERROR";$("liveState").parentElement.className="live-pill warn";
  }finally{state.loading=false}
}
async function boot(){
  initMap();
  bindEvents();
  await Promise.allSettled([loadLab(),loadWeather(),loadMarine()]);
  renderBaseLayer();
  setInterval(loadLab,10*60*1000);
}
function bindEvents(){
  document.querySelectorAll(".layer").forEach(b=>b.addEventListener("click",()=>selectLayer(b.dataset.layer)));
  $("timelineSlider").addEventListener("input",e=>setStep(e.target.value));
  $("timelinePlay").addEventListener("click",togglePlay);
  $("recenterBtn").addEventListener("click",()=>state.map.setView([10.17,103.97],10,{animate:true}));
  $("labelsBtn").addEventListener("click",toggleLabels);
  $("riskOverlayBtn").addEventListener("click",toggleRisk);
  $("actualOverlayBtn").addEventListener("click",toggleActual);
  $("probeClose").addEventListener("click",()=>$("probe").classList.add("hidden"));
  $("placeSearch").addEventListener("keydown",e=>{if(e.key==="Enter")searchPlace()});
  addEventListener("resize",()=>{renderFieldOnly();resetParticles()},{passive:true});
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();