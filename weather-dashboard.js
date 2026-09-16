const emptyPoint=name=>({name,status:"UNAVAILABLE",temperature:null,wind:null,gust:null,wave_max:null,wave:null,period:null,rain:null,current:null,caveat:"Không có snapshot live để hiển thị.",hours:[],daily_outlook:[]});
const fallback={snapshot_id:"NO_LIVE_SNAPSHOT",generated_at:new Date().toISOString(),data_mode:"-",completeness:0,confidence:null,report_status:"UNAVAILABLE",decision:"NOT_ISSUED",headline:"Không tải được snapshot live. Kiểm tra dashboard-data.json hoặc lần publish CI gần nhất.",next_review:"sau cycle CI kế tiếp",git_commit_sha:"-",forecast_horizon_hours:72,sources:{ECMWF:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},GEFS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},ICON:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},COPERNICUS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},RADAR_LIGHTNING:{status:"UNRESOLVED",detail:"Chưa tải snapshot"}},gaps:[{name:"Dashboard data",detail:"Fetch /weather/dashboard-data.json thất bại"}],points:{an_thoi:emptyPoint("An Thới"),duong_dong:emptyPoint("Dương Đông"),ganh_dau:emptyPoint("Gành Dầu"),rach_gia:emptyPoint("Rạch Giá")}};
let state=fallback,currentPoint="an_thoi",horizonHours=72;
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>{if(v===null||v===undefined||Number.isNaN(Number(v)))return "-";return Number(Number(v).toFixed(d)).toString()};

const HORIZONS={
  72:{label:"TỪ HIỆN TẠI ĐẾN D+3",note:"D0-D3: mỗi 3 giờ",guide:"D0-D3 hiển thị chi tiết 3 giờ. Hs là trạng thái biển nền; Hmax là biên rủi ro sóng cá thể."},
  120:{label:"TỪ HIỆN TẠI ĐẾN D+5",note:"D0-D3: 3 giờ · D4-D5: 6 giờ",guide:"D0-D3 dùng chi tiết 3 giờ. Từ D+4 giảm xuống khoảng 6 giờ để tránh cảm giác chính xác giả ở forecast xa."},
  168:{label:"TỪ HIỆN TẠI ĐẾN D+7",note:"D0-D3: 3 giờ · D4-D7: 6 giờ",guide:"D0-D3 là vùng vận hành chi tiết. D4-D7 hiển thị 6 giờ và hiện vẫn là ECMWF medium-range control, ensemble consensus đang bổ sung."},
  240:{label:"D+7 CHI TIẾT · D+8-D+10 XU HƯỚNG",note:"D0-D3: 3 giờ · D4-D7: 6 giờ · D8-D10: theo ngày",guide:"Biểu đồ chi tiết dừng ở D+7. D+8-D+10 được gom theo ngày bên dưới để chỉ nhìn xu hướng và biên rủi ro, không dùng để chốt vận hành."}
};

function ensureEnhancedDOM(){
  const headRow=document.querySelector(".forecast-table thead tr");
  if(headRow&&!headRow.querySelector('[data-col="temperature"]')){
    const th=document.createElement("th");th.dataset.col="temperature";th.innerHTML="Nhiệt độ<br><small>°C</small>";
    headRow.insertBefore(th,headRow.children[1]||null);
  }
  if(!document.querySelector(".app-dock")){
    const dock=document.createElement("nav");
    dock.className="app-dock";dock.setAttribute("aria-label","Điều hướng Weather Lab");
    dock.innerHTML=`<button class="active" data-target="control-shell">Tổng quan</button><button data-target="forecast-shell">Dự báo</button><button data-target="forecast-table-panel">Số liệu</button><button data-target="data-health">Nguồn</button>`;
    document.body.appendChild(dock);
    dock.querySelectorAll("button").forEach(btn=>btn.addEventListener("click",()=>{
      const el=document.querySelector("."+btn.dataset.target)||document.getElementById(btn.dataset.target);
      if(el)el.scrollIntoView({behavior:"smooth",block:"start"});
      dock.querySelectorAll("button").forEach(x=>x.classList.toggle("active",x===btn));
    }));
  }
}

async function load(){
  ensureEnhancedDOM();
  try{
    const response=await fetch("/weather/dashboard-data.json",{cache:"no-store"});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    state=await response.json();
  }catch(e){console.error("Weather dashboard snapshot load failed",e);state=fallback}
  const available=Number(state.forecast_horizon_hours)||72;
  if(horizonHours>available)horizonHours=72;
  render();
}

function render(){
  const live=state.report_status==="LIVE";
  $("healthDot").className="dot "+(live?"ok":"warn");
  $("cycleText").textContent=(live?"Dữ liệu thời tiết & hải văn thời gian thực":"Dữ liệu chưa live")+" · "+new Date(state.generated_at).toLocaleString("vi-VN",{hour12:false});
  $("dataMode").textContent=state.data_mode;
  $("modeNote").textContent=live?"live snapshot":"chưa có snapshot live";
  $("snapshotAge").textContent=live?age(state.generated_at):"-";
  $("snapshotId").textContent=state.snapshot_id;
  $("completeness").textContent=state.completeness+"%";
  $("confidence").textContent=state.confidence===null||state.confidence===undefined?"-":state.confidence+"/100";
  $("headline").textContent=state.headline;
  $("nextReview").textContent="Lần đọc tiếp: "+state.next_review;
  $("commitSha").textContent="Commit "+state.git_commit_sha;
  renderDecision();renderHorizonAvailability();renderSources();renderGaps();renderPoint();
}

function renderDecision(){
  const raw=String(state.decision||"NOT_ISSUED").toUpperCase();
  const badge=$("decisionBadge");
  badge.textContent=raw==="NOT_ISSUED"?"CHƯA PHÁT QUYẾT ĐỊNH":raw.replaceAll("_"," ");
  badge.className="badge neutral";
  let active=null,icon="i";
  if(raw==="GO"){active="GO";badge.className="badge good";icon="✓"}
  else if(raw.includes("WATCH")){active="WATCH";badge.className="badge watch";icon="!"}
  else if(raw.includes("HOLD")||raw.includes("CANCEL")){active="HOLD";badge.className="badge hold";icon="×"}
  else if(raw.includes("TREND")){active="TREND_ONLY";badge.className="badge trend";icon="↗"}
  $("decisionIcon").textContent=icon;
  document.querySelectorAll(".decision-state").forEach(el=>el.classList.toggle("active",el.dataset.state===active));
}

function age(date){const mins=Math.max(0,Math.round((Date.now()-new Date(date))/60000));return mins<60?mins+" phút":Math.round(mins/60)+" giờ"}
function renderSources(){$("sources").innerHTML=Object.entries(state.sources).map(([name,x])=>`<div class="source"><b>${name}</b><span><i class="state ${x.status==="PASS"?"ok":x.status==="PARTIAL"?"partial":"fail"}">${x.status}</i><br>${x.detail}</span></div>`).join("")}
function renderGaps(){$("gaps").innerHTML=(state.gaps||[]).length?state.gaps.map(x=>`<div class="gap"><b>${x.name}</b><span>${x.detail}</span></div>`).join(""):`<div class="gap"><b>Không có critical gap</b><span>Cycle đủ điều kiện</span></div>`}

function renderHorizonAvailability(){
  const available=Number(state.forecast_horizon_hours)||72;
  document.querySelectorAll(".horizon-tabs button").forEach(b=>{
    const h=Number(b.dataset.horizon);b.disabled=h>available;b.classList.toggle("active",h===horizonHours);
    b.title=b.disabled?`Snapshot hiện tại mới có ${available} giờ`:"";
  });
}

function futureUntil(rows,hours){
  const now=Date.now(),cutoff=now+hours*3600000;
  return rows.filter(r=>{const t=Date.parse(r.time_iso);return Number.isFinite(t)&&t>=now&&t<=cutoff}).sort((a,b)=>Date.parse(a.time_iso)-Date.parse(b.time_iso));
}

function detailRows(rows){
  const limit=Math.min(horizonHours,168),future=futureUntil(rows,limit);
  if(horizonHours<=72)return future;
  const now=Date.now(),nearCut=now+72*3600000,out=[];let lastFar=null;
  for(const r of future){
    const t=Date.parse(r.time_iso);
    if(t<=nearCut){out.push(r);continue}
    if(lastFar===null||t-lastFar>=5.5*3600000){out.push(r);lastFar=t}
  }
  return out;
}

function renderPoint(){
  const p=state.points[currentPoint]||emptyPoint(currentPoint),rows=detailRows(p.hours||[]),cfg=HORIZONS[horizonHours];
  $("pointName").textContent=p.name;
  const region=currentPoint==="rach_gia"?"RẠCH GIÁ":"PHÚ QUỐC";
  $("pointStatus").textContent=`${region} · ${p.status}`;
  $("heroUpdated").textContent="Cập nhật "+new Date(state.generated_at).toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
  $("heroHeadline").textContent=`Theo dõi gió, sóng, mưa và dòng chảy tại ${p.name}.`;
  const temp=p.temperature??p.temp??null;
  $("temperature").textContent=temp===null||temp===undefined?"—":fmt(temp,1)+"°C";
  $("temperatureMetric").textContent=temp===null||temp===undefined?"—":fmt(temp,1);
  $("temperatureNote").textContent=temp===null||temp===undefined?"chờ snapshot có 2t ECMWF":"ECMWF 2 m";
  for(const [id,key,d] of [["wind","wind",1],["gust","gust",1],["wave","wave",2],["waveMax","wave_max",2],["period","period",2],["rain","rain",2],["current","current",2]])$(id).textContent=fmt(p[key],d);
  $("pointCaveat").textContent=p.caveat||"";
  $("horizonLabel").textContent=cfg.label;$("tableStepNote").textContent=cfg.note;$("chartGuide").textContent=cfg.guide;
  document.body.dataset.point=currentPoint;
  renderTable(rows);drawChart(rows);renderOutlook(p);
}

function renderTable(rows){
  $("forecastRows").innerHTML=rows.length?rows.map(r=>`<tr><td>${r.time}</td><td>${fmt(r.temperature,1)}</td><td>${fmt(r.wind,1)}</td><td>${fmt(r.gust,1)}</td><td>${fmt(r.rain,2)}</td><td>${fmt(r.wave,2)}</td><td>${fmt(r.wave_max,2)}</td><td>${fmt(r.period,1)}</td></tr>`).join(""):`<tr><td colspan="8" style="text-align:center;color:#82929c">Chưa có bước dự báo trong khoảng đang chọn</td></tr>`;
  $("forecastCards").innerHTML=rows.length?rows.map(r=>`<article class="forecast-card"><time>${r.time}</time><div class="forecast-card-grid"><div><span>Nhiệt độ</span><b>${fmt(r.temperature,1)} <small>°C</small></b></div><div><span>Gió nền</span><b>${fmt(r.wind,1)} <small>km/h</small></b></div><div><span>Gió giật</span><b>${fmt(r.gust,1)} <small>km/h</small></b></div><div><span>Mưa kỳ</span><b>${fmt(r.rain,2)} <small>mm</small></b></div><div class="wave-cell"><span>Sóng Hs</span><b>${fmt(r.wave,2)} <small>m</small></b></div><div class="risk-cell"><span>Hmax rủi ro</span><b>${fmt(r.wave_max,2)} <small>m</small></b></div><div><span>Chu kỳ</span><b>${fmt(r.period,1)} <small>giây</small></b></div></div></article>`).join(""):`<div class="empty" style="display:grid">Chưa có bước dự báo trong khoảng đang chọn.</div>`;
}

function renderOutlook(p){
  const panel=$("longRangePanel");
  if(horizonHours!==240){panel.hidden=true;return}
  panel.hidden=false;
  const rows=(p.daily_outlook||[]).filter(x=>x.day_offset>=8&&x.day_offset<=10);
  $("outlookCards").innerHTML=rows.length?rows.map(x=>`<article class="outlook-card"><div class="outlook-head"><b>D+${x.day_offset}</b><time>${x.date}</time><span>Xu hướng</span></div><div class="outlook-grid"><div><small>Gió max</small><b>${fmt(x.wind_max,1)} <em>km/h</em></b></div><div><small>Giật max</small><b>${fmt(x.gust_max,1)} <em>km/h</em></b></div><div class="wave-cell"><small>Hs max</small><b>${fmt(x.hs_max,2)} <em>m</em></b></div><div class="risk-cell"><small>Hmax rủi ro</small><b>${fmt(x.hmax_max,2)} <em>m</em></b></div><div><small>Mưa tổng</small><b>${fmt(x.rain_total,1)} <em>mm</em></b></div><div><small>Độ tin cậy</small><b class="unscored">Chưa chấm</b></div></div></article>`).join(""):`<div class="outlook-empty">Snapshot này chưa có đủ D+8-D+10. Chờ cycle D10 publish kế tiếp.</div>`;
}

function niceMax(value,kind){const v=Math.max(0,Number(value)||0);if(kind==="wave"||kind==="rain")return Math.max(.1,Math.ceil(v*10)/10);return Math.max(5,Math.ceil(v/5)*5)}
function roundRect(ctx,x,y,w,h,r){const rr=Math.min(r,w/2,h/2);ctx.beginPath();ctx.moveTo(x+rr,y);ctx.arcTo(x+w,y,x+w,y+h,rr);ctx.arcTo(x+w,y+h,x,y+h,rr);ctx.arcTo(x,y+h,x,y,rr);ctx.arcTo(x,y,x+w,y,rr);ctx.closePath()}
function shortLabel(row){const s=String(row.time||"");const m=s.match(/(\d{2}\/\d{2})\s+(\d{2}):/);return m?`${m[1]}\n${m[2]}h`:s}
function finiteValues(rows,key){return rows.map(r=>Number(r[key])).filter(Number.isFinite)}
function drawLine(ctx,rows,key,color,x,y,w,h,max,fill=false,dashed=false){
  const pts=rows.map((r,i)=>({i,v:Number(r[key])})).filter(p=>Number.isFinite(p.v));if(!pts.length)return;
  const xy=pts.map(p=>({x:x+w*p.i/Math.max(1,rows.length-1),y:y+h-h*Math.min(max,Math.max(0,p.v))/max}));
  if(fill){const grad=ctx.createLinearGradient(0,y,0,y+h);grad.addColorStop(0,color+"28");grad.addColorStop(1,color+"00");ctx.beginPath();ctx.moveTo(xy[0].x,y+h);xy.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.lineTo(p.x,p.y));ctx.lineTo(xy[xy.length-1].x,y+h);ctx.closePath();ctx.fillStyle=grad;ctx.fill()}
  ctx.save();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineJoin="round";ctx.lineCap="round";if(dashed)ctx.setLineDash([4,3]);ctx.beginPath();xy.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.stroke();ctx.restore();
}
function drawBars(ctx,rows,key,color,x,y,w,h,max){
  const bw=Math.max(2,Math.min(8,w/Math.max(rows.length,1)*.58));rows.forEach((r,i)=>{const v=Number(r[key]);if(!Number.isFinite(v))return;const bh=h*Math.min(max,Math.max(0,v))/max;const xx=x+w*i/Math.max(1,rows.length-1)-bw/2;ctx.fillStyle=color;roundRect(ctx,xx,y+h-bh,bw,Math.max(1,bh),Math.min(3,bw/2));ctx.fill()})
}
function drawChart(rows){
  const c=$("forecastChart"),empty=$("chartEmpty");
  if(!rows.length){c.style.display="none";empty.style.display="grid";return}
  c.style.display="block";empty.style.display="none";
  const ctx=c.getContext("2d"),dpr=devicePixelRatio||1,w=Math.max(300,c.clientWidth),h=Math.max(210,c.clientHeight);
  c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const gap=w<520?6:10,pad=w<520?6:8,panelW=(w-gap*2)/3,panelH=h-2;
  const configs=[
    {title:"Gió & Gió giật",unit:"km/h",kind:"wind",series:[{key:"wind",color:"#168bd0",name:"Gió"},{key:"gust",color:"#f59a23",name:"Giật",dash:true}]},
    {title:"Sóng",unit:"m",kind:"wave",series:[{key:"wave",color:"#2e9bdc",name:"Hs"},{key:"wave_max",color:"#9c66e8",name:"Hmax",dash:true}]},
    {title:"Mưa",unit:"mm",kind:"rain",series:[{key:"rain",color:"#67b7e5",name:"Mưa",bar:true}]}
  ];
  configs.forEach((cfg,pi)=>{
    const px=pi*(panelW+gap),py=1;
    ctx.fillStyle="#ffffff";ctx.strokeStyle="#dfeaf1";ctx.lineWidth=1;roundRect(ctx,px,py,panelW,panelH,14);ctx.fill();ctx.stroke();
    const left=px+pad+24,right=px+panelW-pad-5,top=py+55,bottom=py+panelH-28,cw=Math.max(20,right-left),ch=Math.max(30,bottom-top);
    ctx.fillStyle="#193b55";ctx.font=`700 ${w<520?9:11}px system-ui`;ctx.textAlign="left";ctx.textBaseline="alphabetic";ctx.fillText(cfg.title,px+pad,py+18);
    ctx.font=`600 ${w<520?7:9}px system-ui`;let lx=px+pad;
    cfg.series.forEach(s=>{ctx.fillStyle=s.color;ctx.beginPath();ctx.arc(lx+3,py+32,3,0,Math.PI*2);ctx.fill();ctx.fillStyle="#6d8190";ctx.fillText(s.name,lx+9,py+35);lx+=w<520?34:48});
    const vals=cfg.series.flatMap(s=>finiteValues(rows,s.key)),max=niceMax(Math.max(...vals,0),cfg.kind);
    [0,.5,1].forEach(fr=>{const yy=top+ch*fr;ctx.strokeStyle="#e8f0f5";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();const label=max*(1-fr);ctx.fillStyle="#8a9aa7";ctx.font=`${w<520?6.5:8}px system-ui`;ctx.textAlign="right";ctx.fillText(fmt(label,cfg.kind==="wind"?0:1),left-4,yy+2)});
    if(cfg.kind==="rain")drawBars(ctx,rows,"rain","#67b7e5",left,top,cw,ch,max);else cfg.series.forEach((s,si)=>drawLine(ctx,rows,s.key,s.color,left,top,cw,ch,max,si===0,s.dash));
    const ticks=[0,Math.floor((rows.length-1)/2),rows.length-1];ctx.font=`${w<520?6.5:8}px system-ui`;ctx.fillStyle="#81939f";ctx.textAlign="center";ticks.forEach(i=>{const x=left+cw*i/Math.max(1,rows.length-1);const parts=shortLabel(rows[i]||{}).split("\n");ctx.fillText(parts[0]||"",x,bottom+12);if(parts[1])ctx.fillText(parts[1],x,bottom+21)});
    ctx.fillStyle="#8b9aa4";ctx.textAlign="right";ctx.font=`600 ${w<520?6.5:8}px system-ui`;ctx.fillText(cfg.unit,px+panelW-pad,py+18);
  });
}

document.querySelectorAll(".point-tabs button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".point-tabs button").forEach(x=>x.classList.remove("active"));b.classList.add("active");currentPoint=b.dataset.point;renderPoint()}));
document.querySelectorAll(".horizon-tabs button").forEach(b=>b.addEventListener("click",()=>{if(b.disabled)return;horizonHours=Number(b.dataset.horizon);renderHorizonAvailability();renderPoint()}));
addEventListener("resize",()=>drawChart(detailRows((state.points[currentPoint]||emptyPoint(currentPoint)).hours||[])));
load();
