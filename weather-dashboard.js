const fallback={snapshot_id:"NO_LIVE_SNAPSHOT",generated_at:new Date().toISOString(),data_mode:"-",completeness:0,confidence:null,report_status:"UNAVAILABLE",decision:"NOT_ISSUED",headline:"Không tải được snapshot live. Kiểm tra dashboard-data.json hoặc lần publish CI gần nhất.",next_review:"sau cycle CI kế tiếp",git_commit_sha:"-",sources:{ECMWF:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},GEFS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},ICON:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},COPERNICUS:{status:"UNRESOLVED",detail:"Chưa tải snapshot"},RADAR_LIGHTNING:{status:"UNRESOLVED",detail:"Chưa tải snapshot"}},gaps:[{name:"Dashboard data",detail:"Fetch /weather/dashboard-data.json thất bại"}],points:{an_thoi:{name:"An Thới",status:"UNAVAILABLE",wind:null,gust:null,wave_max:null,wave:null,period:null,rain:null,current:null,caveat:"Không có snapshot live để hiển thị.",hours:[]},duong_dong:{name:"Dương Đông",status:"UNAVAILABLE",wind:null,gust:null,wave_max:null,wave:null,period:null,rain:null,current:null,caveat:"Không có snapshot live để hiển thị.",hours:[]},ganh_dau:{name:"Gành Dầu",status:"UNAVAILABLE",wind:null,gust:null,wave_max:null,wave:null,period:null,rain:null,current:null,caveat:"Không có snapshot live để hiển thị.",hours:[]}}};
let state=fallback,currentPoint="an_thoi";
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>{if(v===null||v===undefined||Number.isNaN(Number(v)))return "-";const n=Number(v);return Number(n.toFixed(d)).toString()};
const futureRows=rows=>rows.filter(r=>{const t=Date.parse(r.time_iso);return !Number.isFinite(t)||t>=Date.now()});

async function load(){try{const response=await fetch("/weather/dashboard-data.json",{cache:"no-store"});if(!response.ok)throw new Error(`HTTP ${response.status}`);state=await response.json()}catch(e){console.error("Weather dashboard snapshot load failed",e);state=fallback}render();}
function render(){const live=state.report_status==="LIVE";$("healthDot").className="dot "+(live?"ok":"warn");$("cycleText").textContent=(live?"LIVE":"DỮ LIỆU CHƯA LIVE")+" · "+new Date(state.generated_at).toLocaleString("vi-VN");$("dataMode").textContent=state.data_mode;$("modeNote").textContent=live?"live snapshot":"chưa có snapshot live";$("snapshotAge").textContent=live?age(state.generated_at):"-";$("snapshotId").textContent=state.snapshot_id;$("completeness").textContent=state.completeness+"%";$("confidence").textContent=state.confidence===null||state.confidence===undefined?"-":state.confidence+"/100";$("headline").textContent=state.headline;$("nextReview").textContent="Lần đọc tiếp: "+state.next_review;$("decisionBadge").textContent=state.decision.replaceAll("_"," ");$("decisionBadge").className="badge "+(state.decision==="GO"?"good":state.decision.includes("WATCH")?"watch":"neutral");$("commitSha").textContent="Commit "+state.git_commit_sha;renderSources();renderGaps();renderPoint();}
function age(date){const mins=Math.max(0,Math.round((Date.now()-new Date(date))/60000));return mins<60?mins+" phút":Math.round(mins/60)+" giờ"}
function renderSources(){$("sources").innerHTML=Object.entries(state.sources).map(([name,x])=>`<div class="source"><b>${name}</b><span><i class="state ${x.status==="PASS"?"ok":x.status==="PARTIAL"?"partial":"fail"}">${x.status}</i><br>${x.detail}</span></div>`).join("")}
function renderGaps(){$("gaps").innerHTML=state.gaps.length?state.gaps.map(x=>`<div class="gap"><b>${x.name}</b><span>${x.detail}</span></div>`).join(""):`<div class="gap"><b>Không có critical gap</b><span>Cycle đủ điều kiện</span></div>`}
function renderPoint(){const p=state.points[currentPoint],rows=futureRows(p.hours||[]);$("pointName").textContent=p.name;$("pointStatus").textContent=p.status;for(const [id,key,d] of [["wind","wind",1],["gust","gust",1],["waveMax","wave_max",2],["wave","wave",2],["period","period",2],["rain","rain",2],["current","current",2]])$(id).textContent=fmt(p[key],d);$("pointCaveat").textContent=p.caveat||"";renderTable(rows);drawChart(rows)}

function renderTable(rows){
  $("forecastRows").innerHTML=rows.length?rows.map(r=>`<tr><td>${r.time}</td><td>${fmt(r.wind,1)}</td><td>${fmt(r.gust,1)}</td><td>${fmt(r.rain,2)}</td><td>${fmt(r.wave_max,2)}</td><td>${fmt(r.wave,2)}</td><td>${fmt(r.period,1)}</td></tr>`).join(""):`<tr><td colspan="7" style="text-align:center;color:#8da8ae">Chưa có bước dự báo tương lai trong snapshot hiện tại</td></tr>`;
  $("forecastCards").innerHTML=rows.length?rows.map(r=>`<article class="forecast-card"><time>${r.time}</time><div class="forecast-card-grid"><div><span>Gió nền</span><b>${fmt(r.wind,1)} <small>km/h</small></b></div><div><span>Gió giật</span><b>${fmt(r.gust,1)} <small>km/h</small></b></div><div><span>Mưa 3 giờ</span><b>${fmt(r.rain,2)} <small>mm</small></b></div><div class="risk-cell"><span>Hmax rủi ro</span><b>${fmt(r.wave_max,2)} <small>m</small></b></div><div><span>Sóng Hs</span><b>${fmt(r.wave,2)} <small>m</small></b></div><div><span>Chu kỳ</span><b>${fmt(r.period,1)} <small>giây</small></b></div></div></article>`).join(""):`<div class="empty" style="display:grid">Chưa có bước dự báo tương lai trong snapshot hiện tại.</div>`;
}

function niceMax(value,kind){
  const v=Math.max(0,Number(value)||0);
  if(kind==="wave")return Math.max(.1,Math.ceil(v*10)/10);
  if(kind==="rain")return Math.max(.1,Math.ceil(v*10)/10);
  return Math.max(5,Math.ceil(v/5)*5);
}
function shortTime(text){return String(text||"").replace(":00","h")}
function drawChart(rows){
  const c=$("forecastChart"),empty=$("chartEmpty");
  if(!rows.length){c.style.display="none";empty.style.display="grid";return}
  c.style.display="block";empty.style.display="none";
  const ctx=c.getContext("2d"),dpr=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;
  c.width=Math.max(1,w*dpr);c.height=Math.max(1,h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const left=w<500?47:58,right=12,top=8,bottom=30,gap=12;
  const usable=h-top-bottom-gap*2,panelH=usable/3;
  const panels=[
    {label:"Gió / Giật",unit:"km/h",kind:"wind",series:[{key:"wind",color:"#2fc5b4"},{key:"gust",color:"#ff8b73"}]},
    {label:"Hmax / Hs",unit:"m",kind:"wave",series:[{key:"wave_max",color:"#c28cff"},{key:"wave",color:"#63aef4"}]},
    {label:"Mưa 3h",unit:"mm",kind:"rain",series:[{key:"rain",color:"#fcbc12"}]}
  ];
  ctx.font=w<500?"10px system-ui":"11px system-ui";ctx.textBaseline="middle";
  panels.forEach((p,pi)=>{
    const y0=top+pi*(panelH+gap),y1=y0+panelH;
    const vals=p.series.flatMap(s=>rows.map(r=>Number(r[s.key])).filter(Number.isFinite));
    const max=niceMax(Math.max(...vals,0),p.kind),mid=max/2;
    ctx.fillStyle="#8da8ae";ctx.textAlign="left";ctx.fillText(p.label,2,y0+10);ctx.font=w<500?"9px system-ui":"10px system-ui";ctx.fillText(p.unit,2,y0+24);ctx.font=w<500?"10px system-ui":"11px system-ui";
    for(const [frac,label] of [[0,max],[.5,mid],[1,0]]){
      const y=y0+frac*panelH;ctx.strokeStyle="#25414b";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillStyle="#8da8ae";ctx.textAlign="right";ctx.fillText(fmt(label,p.kind==="wind"?0:1),left-6,y);
    }
    p.series.forEach(s=>{
      const points=rows.map((r,i)=>({i,v:Number(r[s.key])})).filter(x=>Number.isFinite(x.v));
      if(!points.length)return;
      ctx.strokeStyle=s.color;ctx.lineWidth=s.key==="wave_max"?2.8:2.2;ctx.beginPath();
      points.forEach((pt,j)=>{const x=left+(w-left-right)*pt.i/Math.max(1,rows.length-1),y=y1-panelH*Math.min(max,Math.max(0,pt.v))/max;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
    });
  });
  const every=w<500?8:4;
  ctx.textAlign="center";ctx.textBaseline="top";ctx.fillStyle="#8da8ae";ctx.font=w<500?"9px system-ui":"10px system-ui";
  rows.forEach((r,i)=>{if(i%every!==0&&i!==rows.length-1)return;const x=left+(w-left-right)*i/Math.max(1,rows.length-1);ctx.strokeStyle="#25414b";ctx.beginPath();ctx.moveTo(x,h-bottom+1);ctx.lineTo(x,h-bottom+5);ctx.stroke();ctx.fillText(shortTime(r.time),x,h-bottom+7)});
}

document.querySelectorAll(".point-tabs button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".point-tabs button").forEach(x=>x.classList.remove("active"));b.classList.add("active");currentPoint=b.dataset.point;renderPoint()}));
addEventListener("resize",()=>drawChart(futureRows(state.points[currentPoint].hours||[])));
load();
