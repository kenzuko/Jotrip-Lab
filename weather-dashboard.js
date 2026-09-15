const emptyPoint=name=>({name,status:"UNAVAILABLE",wind:null,gust:null,wave_max:null,wave:null,period:null,rain:null,current:null,caveat:"Không có snapshot live để hiển thị.",hours:[],daily_outlook:[]});
const fallback={snapshot_id:"NO_LIVE_SNAPSHOT",generated_at:new Date().toISOString(),data_mode:"-",completeness:0,confidence:null,report_status:"UNAVAILABLE",decision:"NOT_ISSUED",headline:"Không tải được snapshot live. Kiểm tra dashboard-data.json hoặc lần publish CI gần nhất.",next_review:"sau cycle CI kế tiếp",git_commit_sha:"-",forecast_horizon_hours:72,sources:{ECMWF:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},GEFS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},ICON:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},COPERNICUS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},RADAR_LIGHTNING:{status:"UNRESOLVED",detail:"Chưa tải snapshot"}},gaps:[{name:"Dashboard data",detail:"Fetch /weather/dashboard-data.json thất bại"}],points:{an_thoi:emptyPoint("An Thới"),duong_dong:emptyPoint("Dương Đông"),ganh_dau:emptyPoint("Gành Dầu")}};
let state=fallback,currentPoint="an_thoi",horizonHours=72;
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>{if(v===null||v===undefined||Number.isNaN(Number(v)))return "-";return Number(Number(v).toFixed(d)).toString()};

const HORIZONS={
  72:{label:"TỪ HIỆN TẠI ĐẾN D+3",note:"D0-D3: mỗi 3 giờ",guide:"D0-D3 hiển thị chi tiết 3 giờ. Hs là trạng thái biển nền; Hmax là biên rủi ro sóng cá thể."},
  120:{label:"TỪ HIỆN TẠI ĐẾN D+5",note:"D0-D3: 3 giờ · D4-D5: 6 giờ",guide:"D0-D3 dùng chi tiết 3 giờ. Từ D+4 giảm xuống khoảng 6 giờ để tránh cảm giác chính xác giả ở forecast xa."},
  168:{label:"TỪ HIỆN TẠI ĐẾN D+7",note:"D0-D3: 3 giờ · D4-D7: 6 giờ",guide:"D0-D3 là vùng vận hành chi tiết. D4-D7 hiển thị 6 giờ và hiện vẫn là ECMWF medium-range control, ensemble consensus đang bổ sung."},
  240:{label:"D+7 CHI TIẾT · D+8-D+10 XU HƯỚNG",note:"D0-D3: 3 giờ · D4-D7: 6 giờ · D8-D10: theo ngày",guide:"Biểu đồ chi tiết dừng ở D+7. D+8-D+10 được gom theo ngày bên dưới để chỉ nhìn xu hướng và biên rủi ro, không dùng để chốt vận hành."}
};

async function load(){
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
  $("cycleText").textContent=(live?"LIVE":"DỮ LIỆU CHƯA LIVE")+" · "+new Date(state.generated_at).toLocaleString("vi-VN");
  $("dataMode").textContent=state.data_mode;
  $("modeNote").textContent=live?"live snapshot":"chưa có snapshot live";
  $("snapshotAge").textContent=live?age(state.generated_at):"-";
  $("snapshotId").textContent=state.snapshot_id;
  $("completeness").textContent=state.completeness+"%";
  $("confidence").textContent=state.confidence===null||state.confidence===undefined?"-":state.confidence+"/100";
  $("headline").textContent=state.headline;
  $("nextReview").textContent="Lần đọc tiếp: "+state.next_review;
  $("decisionBadge").textContent=state.decision.replaceAll("_"," ");
  $("decisionBadge").className="badge "+(state.decision==="GO"?"good":state.decision.includes("WATCH")?"watch":"neutral");
  $("commitSha").textContent="Commit "+state.git_commit_sha;
  renderHorizonAvailability();renderSources();renderGaps();renderPoint();
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
  $("pointStatus").textContent=p.status;
  for(const [id,key,d] of [["wind","wind",1],["gust","gust",1],["wave","wave",2],["waveMax","wave_max",2],["period","period",2],["rain","rain",2],["current","current",2]])$(id).textContent=fmt(p[key],d);
  $("pointCaveat").textContent=p.caveat||"";
  $("horizonLabel").textContent=cfg.label;$("tableStepNote").textContent=cfg.note;$("chartGuide").textContent=cfg.guide;
  renderTable(rows);drawChart(rows);renderOutlook(p);
}

function renderTable(rows){
  $("forecastRows").innerHTML=rows.length?rows.map(r=>`<tr><td>${r.time}</td><td>${fmt(r.wind,1)}</td><td>${fmt(r.gust,1)}</td><td>${fmt(r.rain,2)}</td><td>${fmt(r.wave,2)}</td><td>${fmt(r.wave_max,2)}</td><td>${fmt(r.period,1)}</td></tr>`).join(""):`<tr><td colspan="7" style="text-align:center;color:#8da8ae">Chưa có bước dự báo trong khoảng đang chọn</td></tr>`;
  $("forecastCards").innerHTML=rows.length?rows.map(r=>`<article class="forecast-card"><time>${r.time}</time><div class="forecast-card-grid"><div><span>Gió nền</span><b>${fmt(r.wind,1)} <small>km/h</small></b></div><div><span>Gió giật</span><b>${fmt(r.gust,1)} <small>km/h</small></b></div><div class="wave-cell"><span>Sóng Hs</span><b>${fmt(r.wave,2)} <small>m</small></b></div><div class="risk-cell"><span>Hmax rủi ro</span><b>${fmt(r.wave_max,2)} <small>m</small></b></div><div><span>Mưa kỳ</span><b>${fmt(r.rain,2)} <small>mm</small></b></div><div><span>Chu kỳ</span><b>${fmt(r.period,1)} <small>giây</small></b></div></div></article>`).join(""):`<div class="empty" style="display:grid">Chưa có bước dự báo trong khoảng đang chọn.</div>`;
}

function renderOutlook(p){
  const panel=$("longRangePanel");
  if(horizonHours!==240){panel.hidden=true;return}
  panel.hidden=false;
  const rows=(p.daily_outlook||[]).filter(x=>x.day_offset>=8&&x.day_offset<=10);
  $("outlookCards").innerHTML=rows.length?rows.map(x=>`<article class="outlook-card"><div class="outlook-head"><b>D+${x.day_offset}</b><time>${x.date}</time><span>Xu hướng</span></div><div class="outlook-grid"><div><small>Gió max</small><b>${fmt(x.wind_max,1)} <em>km/h</em></b></div><div><small>Giật max</small><b>${fmt(x.gust_max,1)} <em>km/h</em></b></div><div class="wave-cell"><small>Hs max</small><b>${fmt(x.hs_max,2)} <em>m</em></b></div><div class="risk-cell"><small>Hmax rủi ro</small><b>${fmt(x.hmax_max,2)} <em>m</em></b></div><div><small>Mưa tổng</small><b>${fmt(x.rain_total,1)} <em>mm</em></b></div><div><small>Độ tin cậy</small><b class="unscored">Chưa chấm</b></div></div></article>`).join(""):`<div class="outlook-empty">Snapshot này chưa có đủ D+8-D+10. Chờ cycle D10 publish kế tiếp.</div>`;
}

function niceMax(value,kind){const v=Math.max(0,Number(value)||0);if(kind==="wave"||kind==="rain")return Math.max(.1,Math.ceil(v*10)/10);return Math.max(5,Math.ceil(v/5)*5)}
function shortTime(text){return String(text||"").replace(":00","h")}
function drawChart(rows){
  const c=$("forecastChart"),empty=$("chartEmpty");
  if(!rows.length){c.style.display="none";empty.style.display="grid";return}
  c.style.display="block";empty.style.display="none";
  const ctx=c.getContext("2d"),dpr=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;
  c.width=Math.max(1,w*dpr);c.height=Math.max(1,h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const left=w<500?47:58,right=12,top=8,bottom=30,gap=12,usable=h-top-bottom-gap*2,panelH=usable/3;
  const panels=[
    {label:"Gió / Giật",unit:"km/h",kind:"wind",series:[{key:"wind",color:"#2fc5b4"},{key:"gust",color:"#ff8b73"}]},
    {label:"Hs / Hmax rủi ro",unit:"m",kind:"wave",series:[{key:"wave",color:"#63aef4"},{key:"wave_max",color:"#c28cff"}]},
    {label:"Mưa/kỳ",unit:"mm",kind:"rain",series:[{key:"rain",color:"#fcbc12"}]}
  ];
  ctx.font=w<500?"10px system-ui":"11px system-ui";ctx.textBaseline="middle";
  panels.forEach((p,pi)=>{
    const y0=top+pi*(panelH+gap),y1=y0+panelH,vals=p.series.flatMap(s=>rows.map(r=>Number(r[s.key])).filter(Number.isFinite)),max=niceMax(Math.max(...vals,0),p.kind),mid=max/2;
    ctx.fillStyle="#8da8ae";ctx.textAlign="left";ctx.fillText(p.label,2,y0+10);ctx.font=w<500?"9px system-ui":"10px system-ui";ctx.fillText(p.unit,2,y0+24);ctx.font=w<500?"10px system-ui":"11px system-ui";
    for(const [frac,label] of [[0,max],[.5,mid],[1,0]]){const y=y0+frac*panelH;ctx.strokeStyle="#25414b";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillStyle="#8da8ae";ctx.textAlign="right";ctx.fillText(fmt(label,p.kind==="wind"?0:1),left-6,y)}
    p.series.forEach(s=>{const points=rows.map((r,i)=>({i,v:Number(r[s.key])})).filter(x=>Number.isFinite(x.v));if(!points.length)return;ctx.strokeStyle=s.color;ctx.lineWidth=s.key==="wave_max"?2.8:2.2;ctx.beginPath();points.forEach((pt,j)=>{const x=left+(w-left-right)*pt.i/Math.max(1,rows.length-1),y=y1-panelH*Math.min(max,Math.max(0,pt.v))/max;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()});
  });
  const every=w<500?Math.max(4,Math.ceil(rows.length/5)):Math.max(3,Math.ceil(rows.length/8));ctx.textAlign="center";ctx.textBaseline="top";ctx.fillStyle="#8da8ae";ctx.font=w<500?"9px system-ui":"10px system-ui";
  rows.forEach((r,i)=>{if(i%every!==0&&i!==rows.length-1)return;const x=left+(w-left-right)*i/Math.max(1,rows.length-1);ctx.strokeStyle="#25414b";ctx.beginPath();ctx.moveTo(x,h-bottom+1);ctx.lineTo(x,h-bottom+5);ctx.stroke();ctx.fillText(shortTime(r.time),x,h-bottom+7)});
}

document.querySelectorAll(".point-tabs button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".point-tabs button").forEach(x=>x.classList.remove("active"));b.classList.add("active");currentPoint=b.dataset.point;renderPoint()}));
document.querySelectorAll(".horizon-tabs button").forEach(b=>b.addEventListener("click",()=>{if(b.disabled)return;horizonHours=Number(b.dataset.horizon);renderHorizonAvailability();renderPoint()}));
addEventListener("resize",()=>drawChart(detailRows((state.points[currentPoint]||emptyPoint(currentPoint)).hours||[])));
load();
