(() => {
  "use strict";

  const cfg = window.JOTRIP_OPS_CONFIG || {readOnly:true,sources:{}};
  const $ = (id) => document.getElementById(id);
  const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
  const params = new URLSearchParams(location.search);
  const demoMode = params.get(cfg.demoQueryParam || "demo") === "1";

  const state = {
    weather:null, aqi:null, tide:null, flights:null,
    ferries:null, tours:null, bookings:null, customers:null,
    partners:null, staff:null, tasks:null, alerts:null, shifts:null,
    flightDir:"arrival",
    sourceResults:{},
    selectedDate:null,
    derivedAlerts:[]
  };

  const VN_TZ = cfg.timezone || "Asia/Ho_Chi_Minh";

  function setLogo(){
    if(window.JOTRIP_LOGO_DATA) $("brandLogo").src = window.JOTRIP_LOGO_DATA;
  }

  function viDate(date=new Date()){
    return new Intl.DateTimeFormat("vi-VN",{
      timeZone:VN_TZ,weekday:"short",day:"2-digit",month:"2-digit",year:"numeric"
    }).format(date);
  }
  function viTime(date=new Date()){
    return new Intl.DateTimeFormat("vi-VN",{
      timeZone:VN_TZ,hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false
    }).format(date);
  }
  function dateKeyVN(date=new Date()){
    const parts = new Intl.DateTimeFormat("en-CA",{timeZone:VN_TZ,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(date);
    const get=t=>parts.find(x=>x.type===t)?.value;
    return `${get("year")}-${get("month")}-${get("day")}`;
  }
  function startClock(){
    const tick=()=>{$("topClock").textContent=`${viDate()}  ${viTime()} (GMT+7)`};
    tick(); setInterval(tick,1000);
  }

  function fixText(v){
    if(v===null || v===undefined) return "";
    const s=String(v);
    if(!/[ÃÂÄÆáºá»]/.test(s)) return s;
    try{
      const bytes=Uint8Array.from([...s].map(ch=>ch.charCodeAt(0)&255));
      const decoded=new TextDecoder("utf-8",{fatal:false}).decode(bytes);
      return decoded.includes("�")?s:decoded;
    }catch{return s}
  }
  const n=(v,d=0)=>{
    const x=Number(v);
    if(!Number.isFinite(x)) return "--";
    return x.toLocaleString("vi-VN",{minimumFractionDigits:d,maximumFractionDigits:d});
  };
  const arr=(payload)=>{
    if(Array.isArray(payload)) return payload;
    if(Array.isArray(payload?.data)) return payload.data;
    if(Array.isArray(payload?.items)) return payload.items;
    if(Array.isArray(payload?.records)) return payload.records;
    if(Array.isArray(payload?.results)) return payload.results;
    return [];
  };
  const bool=(v)=>v===true||v===1||String(v).toLowerCase()==="true";

  async function safeGet(name,url){
    if(!url){
      state.sourceResults[name]={status:"UNCONFIGURED",url:null,at:new Date().toISOString()};
      return null;
    }
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(),cfg.fetchTimeoutMs||10000);
    try{
      const r=await fetch(url,{method:"GET",cache:"no-store",credentials:"same-origin",signal:ctrl.signal});
      if(!r.ok) throw new Error(`HTTP ${r.status}`);
      const data=await r.json();
      state.sourceResults[name]={status:"LIVE",url,at:new Date().toISOString()};
      return data;
    }catch(error){
      console.warn(`[ops] GET ${name} failed`,error);
      state.sourceResults[name]={status:"FAILED",url,error:String(error),at:new Date().toISOString()};
      return null;
    }finally{clearTimeout(timer)}
  }

  function noWritesGuard(){
    const originalFetch=window.fetch.bind(window);
    window.fetch=(input,init={})=>{
      const method=String(init.method||"GET").toUpperCase();
      if(!["GET","HEAD"].includes(method)){
        console.error("[JoTrip READ ONLY] blocked network write",method,input);
        showToast("Đã chặn thao tác ghi vào backend cũ.");
        return Promise.reject(new Error("JoTrip Operations dashboard is read-only"));
      }
      return originalFetch(input,init);
    };
  }

  function demoData(){
    const today=dateKeyVN();
    return {
      tours:[
        {time:"07:00",code:"JT-ISL-001",name:"3 đảo (Mây Rút - Gầm Ghì - Hòn Thơm)",guests:18,staff:"Minh / Hằng",vehicle:"Cano 01",readiness:100,status:"Đang chạy",problem:""},
        {time:"08:30",code:"JT-PRV-012",name:"Private Island Day",guests:8,staff:"Tùng / Quân",vehicle:"Cano riêng",readiness:80,status:"Sắp chạy",problem:"Thiếu xác nhận xe"},
        {time:"09:00",code:"JT-CITY-021",name:"City & Sunset Town",guests:24,staff:"Lan / Phương",vehicle:"Xe 07",readiness:100,status:"Đang chạy",problem:""},
        {time:"13:00",code:"JT-FISH-005",name:"Câu cá lớn (chiều)",guests:6,staff:"Nam / Ken",vehicle:"Cano 02",readiness:60,status:"Sắp chạy",problem:"Theo dõi điều kiện biển"},
        {time:"14:00",code:"JT-ISL-018",name:"3 đảo Nam",guests:20,staff:"Huy / Thảo",vehicle:"Cano 04",readiness:100,status:"Sắp chạy",problem:""},
        {time:"15:30",code:"JT-FOOD-009",name:"Nhà thùng & tiêu",guests:12,staff:"Anh / Mai",vehicle:"Xe 13",readiness:100,status:"Sắp chạy",problem:""}
      ],
      ferries:[
        {time:"08:00",operator:"PQ Express",route:"Rạch Giá → Phú Quốc",status:"Đúng giờ"},
        {time:"10:30",operator:"Superdong",route:"Hà Tiên → Phú Quốc",status:"Đúng giờ"},
        {time:"13:00",operator:"PQ Express",route:"Phú Quốc → Rạch Giá",status:"Đúng giờ"},
        {time:"15:30",operator:"Superdong",route:"Hà Tiên → Phú Quốc",status:"Theo lịch"}
      ],
      tasks:[
        {level:"danger",title:"Tour JT-PRV-012 thiếu xác nhận xe",detail:"Khởi hành 08:30. Điều hành cần xác nhận nhà xe.",time:"2 giờ trước"},
        {level:"warn",title:"Cano 02 cần xác nhận trước tour câu cá",detail:"JT-FISH-005 khởi hành 13:00.",time:"1 giờ trước"}
      ],
      activities:[
        {name:"Ngọc Hà",text:"cập nhật trạng thái tour JT-ISL-001",time:"5 phút trước"},
        {name:"Minh Quân",text:"thêm booking BKG-DEMO-015",time:"12 phút trước"},
        {name:"Hệ thống",text:"cập nhật dữ liệu chuyến bay",time:"18 phút trước"}
      ],
      shifts:{current:"Ca sáng",time:"06:00 - 14:00",members:["Ken","Mai","Quân"],next:"Ca chiều",nextTime:"14:00 - 22:00"},
      date:today
    };
  }

  async function loadAll(){
    const S=cfg.sources||{};
    const fixedEntries=[
      ["weather",S.weather],["aqi",S.airQuality],["tide",S.tide],["flights",S.flights]
    ];
    const optionalEntries=[
      ["ferries",S.ferries],["tours",S.tours],["bookings",S.bookings],["customers",S.customers],
      ["partners",S.partners],["staff",S.staff],["tasks",S.tasks],["alerts",S.alerts],["shifts",S.shifts]
    ];

    const fixed=await Promise.all(fixedEntries.map(([name,url])=>safeGet(name,url)));
    fixedEntries.forEach(([name],i)=>state[name]=fixed[i]);

    const optional=await Promise.all(optionalEntries.map(([name,url])=>safeGet(name,url)));
    optionalEntries.forEach(([name],i)=>state[name]=optional[i]);

    if(demoMode){
      const d=demoData();
      if(!state.tours) state.tours=d.tours;
      if(!state.ferries) state.ferries=d.ferries;
      if(!state.tasks) state.tasks=d.tasks;
      state.demoActivities=d.activities;
      if(!state.shifts) state.shifts=d.shifts;
      $("buildMode").textContent="DEMO UI + LIVE WEATHER/FLIGHT";
      $("pageSubtitle").textContent="Chế độ demo UI: dữ liệu nội bộ minh họa, weather/flight vẫn đọc nguồn hiện có.";
      document.body.classList.add("demo-mode");
    }

    renderAll();
  }

  function renderAll(){
    renderHeader();
    renderWeather();
    renderAirQuality();
    renderTide();
    renderFlights();
    renderFerries();
    renderTours();
    deriveAlerts();
    renderAlerts();
    renderTimeline();
    renderActivity();
    renderSourceHealth();
    renderShifts();
    renderGaps();
    updateGlobalKPIs();
  }

  function renderHeader(){
    const generated=state.weather?.generated_at || state.flights?.collected_at_vn || null;
    $("lastUpdated").textContent=generated?ageLabel(generated):"--";
    const dd=state.weather?.points?.duong_dong;
    $("miniTemp").textContent=dd?.temperature!=null?`${n(dd.temperature,0)}°C`:"--°C";
    const active=["weather","aqi","tide","flights"];
    const failed=active.filter(x=>state.sourceResults[x]?.status==="FAILED").length;
    const live=active.filter(x=>state.sourceResults[x]?.status==="LIVE").length;
    $("systemHealth").textContent=failed?`${live}/${active.length} nguồn lõi đang đọc`:`${live}/${active.length} nguồn lõi ổn định`;
    $("sourceDelay").textContent=failed?`${failed} nguồn lỗi`:"Không có lỗi GET";
    $("sourceDelayPill").querySelector(".dot").className=`dot ${failed?"bad":"ok"}`;
  }

  function ageLabel(iso){
    const t=Date.parse(iso); if(!Number.isFinite(t)) return "--";
    const m=Math.max(0,Math.round((Date.now()-t)/60000));
    if(m<1)return"vừa xong"; if(m<60)return`${m} phút trước`;
    const h=Math.round(m/60); if(h<48)return`${h} giờ trước`;
    return new Intl.DateTimeFormat("vi-VN",{timeZone:VN_TZ,day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(t));
  }

  function pointDecision(p){
    const issued=String(state.weather?.decision||"").toUpperCase();
    if(["GO","WATCH","MODIFY","CANCEL","HOLD"].some(x=>issued.includes(x))){
      if(issued.includes("CANCEL")||issued.includes("HOLD")) return {label:"HOLD",cls:"modify"};
      if(issued.includes("WATCH")) return {label:"WATCH",cls:"watch"};
      if(issued.includes("MODIFY")) return {label:"MODIFY",cls:"modify"};
      if(issued==="GO") return {label:"GO",cls:"go"};
    }
    if(String(p?.status||"").includes("LIVE")) return {label:"LIVE DATA",cls:"go"};
    return {label:"CHƯA PHÁT QĐ",cls:""};
  }

  function renderWeather(){
    const w=state.weather;
    if(!w){
      $("weatherPointCards").innerHTML=`<div class="empty-state slim" style="grid-column:1/-1"><b>Không tải được JoTrip Lab snapshot</b><p>Không thay bằng forecast tiêu dùng hoặc báo chí.</p></div>`;
      $("weatherMeta").textContent="LAB DATA PLANE DEGRADED";
      $("weatherMode").textContent="MODE C";
      $("weatherCompleteness").textContent="Numerical layer unavailable";
      return;
    }
    $("weatherMeta").textContent=`Cập nhật ${ageLabel(w.generated_at)} • ${w.snapshot_id||""}`;
    $("weatherMode").textContent=`MODE ${w.data_mode||"--"}`;
    $("weatherCompleteness").textContent=`Completeness ${n(w.completeness,0)}%`;
    const keys=["duong_dong","an_thoi","ganh_dau"];
    $("weatherPointCards").innerHTML=keys.map(k=>{
      const p=w.points?.[k]||{};
      const decision=pointDecision(p);
      return `<div class="weather-point">
        <h3>${fixText(p.name)||k}</h3>
        <div class="temp-line"><span class="weather-symbol">${Number(p.rain)>0.3?"🌦️":"☀️"}</span><span class="temp">${n(p.temperature,1)}°C</span></div>
        <div class="weather-stats">
          <div><span>Gió nền</span><b>${n(p.wind,1)} km/h</b></div>
          <div><span>Gió giật</span><b>${n(p.gust,1)} km/h</b></div>
          <div><span>Sóng Hs</span><b>${n(p.wave,2)} m</b></div>
          <div><span>Chu kỳ</span><b>${n(p.period,1)} s</b></div>
          <div><span>Mưa kỳ</span><b>${n(p.rain,2)} mm</b></div>
          <div><span>Dòng</span><b>${n(p.current,2)} km/h</b></div>
        </div>
        <div class="point-state ${decision.cls}">${decision.label}</div>
      </div>`;
    }).join("");
  }

  function aqiCategoryVi(cat){
    return ({
      GOOD:"Tốt",MODERATE:"Trung bình",UNHEALTHY_FOR_SENSITIVE_GROUPS:"Không tốt cho nhóm nhạy cảm",
      UNHEALTHY:"Không tốt",VERY_UNHEALTHY:"Rất không tốt",HAZARDOUS:"Nguy hại"
    })[String(cat||"").toUpperCase()] || fixText(cat)||"--";
  }
  function renderAirQuality(){
    const q=state.aqi;
    const dd=q?.points?.duong_dong;
    $("aqiValue").textContent=dd?.aqi_us!=null?`AQI ${n(dd.aqi_us)}`:"--";
    $("aqiNote").textContent=dd?`${aqiCategoryVi(dd.category)} • CAMS model`:"Không có dữ liệu";
    const keys=["duong_dong","an_thoi","ganh_dau","rach_gia"];
    $("aqiCards").innerHTML=q?keys.filter(k=>q.points?.[k]).map(k=>{
      const p=q.points[k];
      const name=({duong_dong:"Dương Đông",an_thoi:"An Thới",ganh_dau:"Gành Dầu",rach_gia:"Rạch Giá"})[k];
      return `<div class="mini-card"><h3>${name}</h3><strong>AQI ${n(p.aqi_us)}</strong><p>${aqiCategoryVi(p.category)} • ${p.dominant_pollutant||""}</p><div class="mini-stats"><span>PM2.5 <b>${n(p.pm25_ugm3,1)}</b></span><span>PM10 <b>${n(p.pm10_ugm3,1)}</b></span></div></div>`;
    }).join(""):`<div class="empty-state slim" style="grid-column:1/-1"><b>Không có AQI</b></div>`;
  }

  function renderTide(){
    const t=state.tide;
    const dd=t?.points?.duong_dong;
    $("tideValue").textContent=dd?.current_height_m!=null?`${n(dd.current_height_m,2)} m`:"--";
    $("tideNote").textContent=dd?`${dd.trend==="FALLING"?"Đang xuống":"Đang lên"} • đổi nước ${dd.next_turn?.time||"--"}`:"Không có dữ liệu";
    const keys=["duong_dong","an_thoi","ganh_dau"];
    $("tideCards").innerHTML=t?keys.filter(k=>t.points?.[k]).map(k=>{
      const p=t.points[k];
      return `<div class="mini-card"><h3>${fixText(p.name)}</h3><strong>${n(p.current_height_m,2)} m</strong><p>${p.trend==="FALLING"?"Triều đang xuống":"Triều đang lên"} • MSL model</p><div class="mini-stats"><span>Đổi nước <b>${p.next_turn?.time||"--"}</b></span><span>Biên 24h <b>${n(p.range_24h_m,2)} m</b></span></div></div>`;
    }).join(""):`<div class="empty-state slim" style="grid-column:1/-1"><b>Không có dữ liệu triều</b></div>`;
  }

  function statusClass(status){
    const s=fixText(status).toUpperCase();
    if(/HỦY|HUY|TRỄ|TRE|CHẬM|CHAM|DELAY/.test(s))return"bad";
    if(/ĐÚNG GIỜ|DUNG GIO|ĐÃ HẠ CÁNH|DA HA CANH|BÃI ĐỖ|BAI DO|ĐANG BAY|DANG BAY/.test(s))return"good";
    return"warn";
  }

  function renderFlights(){
    const f=state.flights;
    const records=arr(f).map(x=>({...x,
      carrier:fixText(x.carrier),status:fixText(x.status),station:fixText(x.station)
    }));
    if(!f){
      $("flightRows").innerHTML=`<tr><td colspan="5"><div class="empty-inline">Không tải được Sun Airport snapshot.</div></td></tr>`;
      $("flightMeta").textContent="Nguồn không khả dụng";
      return;
    }
    const arrivals=records.filter(x=>x.direction==="arrival");
    const departures=records.filter(x=>x.direction==="departure");
    $("arrivalCount").textContent=arrivals.length;
    $("departureCount").textContent=departures.length;
    $("kpiFlights").textContent=n(records.length);
    $("kpiFlightMeta").textContent=`Đến ${arrivals.length} • Đi ${departures.length}`;
    $("flightMeta").textContent=`${fixText(f.source?.name||"Sun Airport")} • ${ageLabel(f.collected_at_vn)}`;

    const delayed=records.filter(x=>statusClass(x.status)==="bad").length;
    $("navFlightBadge").classList.toggle("hidden",!delayed);
    $("navFlightBadge").textContent=delayed;

    const dir=state.flightDir;
    const list=(dir==="arrival"?arrivals:departures).slice().sort((a,b)=>String(a.scheduled_time).localeCompare(String(b.scheduled_time)));
    const nowHHMM=new Intl.DateTimeFormat("en-GB",{timeZone:VN_TZ,hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date());
    let near=list.filter(x=>String(x.scheduled_time)>=nowHHMM).slice(0,7);
    if(near.length<5) near=list.slice(-7);
    $("flightRows").innerHTML=near.length?near.map(x=>`<tr>
      <td><b>${x.scheduled_time||"--"}</b></td><td>${shortCarrier(x.carrier)}</td><td><b>${x.operating_flight_number||"--"}</b></td>
      <td>${x.station||"--"} ${dir==="arrival"?"→ PQ":"← PQ"}</td>
      <td><span class="status-text ${statusClass(x.status)}">${x.status||"Chưa rõ"}</span></td>
    </tr>`).join(""):`<tr><td colspan="5"><div class="empty-inline">Không có chuyến trong snapshot.</div></td></tr>`;
  }
  function shortCarrier(v){
    const s=String(v||"");
    return s.replace("VIETNAM AIRLINES","Vietnam Airlines").replace("VIETJET AIR","Vietjet Air").replace("BAMBOO AIRWAYS","Bamboo Airways").replace("SUN PHUQUOC AIRWAYS","Sun PhuQuoc");
  }

  function renderFerries(){
    const rows=arr(state.ferries);
    if(!rows.length){
      $("kpiFerries").textContent="--";
      $("kpiFerryMeta").textContent="Chưa kết nối GET";
      $("ferrySourceState").className="source-state neutral";
      $("ferrySourceState").textContent=demoMode?"DEMO":"CHƯA KẾT NỐI";
      return;
    }
    $("kpiFerries").textContent=n(rows.length);
    $("kpiFerryMeta").textContent=demoMode?"Dữ liệu demo UI":"GET read-only";
    $("ferrySourceState").className=`source-state ${demoMode?"stale":"live"}`;
    $("ferrySourceState").textContent=demoMode?"DEMO":"READ ONLY";
    $("ferryBody").className="";
    $("ferryBody").innerHTML=`<div class="table-wrap compact"><table><thead><tr><th>Giờ</th><th>Hãng</th><th>Tuyến</th><th>Trạng thái</th></tr></thead><tbody>${rows.slice(0,8).map(x=>`<tr><td><b>${x.time||x.scheduled_time||"--"}</b></td><td>${fixText(x.operator||x.carrier||x.company||"--")}</td><td>${fixText(x.route||x.station||"--")}</td><td><span class="status-text ${statusClass(x.status)}">${fixText(x.status||"Chưa rõ")}</span></td></tr>`).join("")}</tbody></table></div>`;
  }

  function normalizeTour(x){
    return {
      time:x.time||x.start_time||x.departure_time||"--",
      code:x.code||x.tour_code||x.id||"--",
      name:fixText(x.name||x.route_name||x.itinerary||x.title||"--"),
      guests:Number(x.guests??x.guest_count??x.pax??0)||0,
      staff:fixText(x.staff||x.guide_host||x.guide||x.host||"--"),
      vehicle:fixText(x.vehicle||x.transport||x.boat||"--"),
      readiness:Number(x.readiness??x.readiness_percent??x.ready_percent),
      status:fixText(x.status||"--"),
      problem:fixText(x.problem||x.issue||x.alert||"")
    }
  }

  function renderTours(){
    const rows=arr(state.tours).map(normalizeTour);
    if(!rows.length){
      $("tourSourceState").textContent="CHƯA KẾT NỐI";
      $("kpiTours").textContent="--";$("kpiGuests").textContent="--";
      $("kpiTourMeta").textContent="Chưa kết nối GET";$("kpiGuestMeta").textContent="Chưa kết nối GET";
      return;
    }
    $("tourSourceState").className=`source-state ${demoMode?"stale":"live"}`;
    $("tourSourceState").textContent=demoMode?"DEMO UI":"READ ONLY";
    const active=rows.filter(x=>!/xong|hoàn thành|cancel|hủy/i.test(x.status));
    const guests=rows.reduce((s,x)=>s+x.guests,0);
    $("kpiTours").textContent=n(active.length); $("kpiGuests").textContent=n(guests);
    $("kpiTourMeta").textContent=`${rows.length} tour trong dữ liệu`;
    $("kpiGuestMeta").textContent=`${rows.length} đoàn/tour`;
    $("tourRows").innerHTML=rows.map(x=>{
      const r=Number.isFinite(x.readiness)?x.readiness:null;
      const cls=r===null?"watch":r>=90?"good":r>=70?"watch":"bad";
      const problemCls=/thiếu|xấu|ảnh hưởng|chưa/i.test(x.problem)?"bad":x.problem?"warn":"";
      return `<tr data-tour-search="${(x.code+" "+x.name+" "+x.staff).toLowerCase()}">
        <td>${x.time}</td><td><b>${x.code}</b></td><td>${x.name}</td><td>${x.guests||"--"}</td><td>${x.staff}</td><td>${x.vehicle}</td>
        <td><span class="readiness ${cls}">${r===null?"--":r+"%"}</span></td><td>${x.status}</td><td><span class="problem ${problemCls}">${x.problem||"--"}</span></td>
      </tr>`;
    }).join("");
  }

  function deriveAlerts(){
    const out=[];
    const f=arr(state.flights).map(x=>({...x,status:fixText(x.status),station:fixText(x.station)}));
    f.filter(x=>statusClass(x.status)==="bad").slice(0,3).forEach(x=>{
      out.push({level:"danger",title:`Chuyến bay ${x.operating_flight_number||""} ${x.status||""}`,detail:`${x.direction==="arrival"?x.station+" → PQ":"PQ → "+x.station} • ${x.scheduled_time||"--"} • kiểm tra tác động tour/đón tiễn trước khi thay đổi vận hành.`,time:"live",tag:"Chuyến bay"})
    });
    const tasks=arr(state.tasks);
    tasks.forEach(x=>out.push({
      level:x.level||x.severity||"warn",
      title:fixText(x.title||x.name||"Việc cần xử lý"),
      detail:fixText(x.detail||x.description||""),
      time:fixText(x.time||x.updated_at||""),
      tag:fixText(x.tag||"Điều hành")
    }));
    const internalAlerts=arr(state.alerts);
    internalAlerts.forEach(x=>out.push({
      level:x.level||x.severity||"warn",title:fixText(x.title||"Cảnh báo"),detail:fixText(x.detail||x.description||""),time:fixText(x.time||""),tag:fixText(x.tag||"")
    }));
    state.derivedAlerts=out;
  }

  function renderAlerts(){
    const rows=state.derivedAlerts;
    $("alertCount").textContent=rows.length?`(${rows.length})`:"";
    $("kpiUrgent").textContent=rows.length?n(rows.length):"0";
    $("kpiUrgentMeta").textContent=rows.length?`${rows.filter(x=>x.level==="danger").length} mức khẩn/cần kiểm tra`:"Không có exception live từ nguồn đã nối";
    $("navTaskBadge").classList.toggle("hidden",!rows.length);
    $("navTaskBadge").textContent=rows.length;
    $("bellBadge").classList.toggle("hidden",!rows.length);
    $("bellBadge").textContent=rows.length;
    if(!rows.length){
      $("alertsList").innerHTML=`<div class="empty-state slim"><b>Không có cảnh báo live từ các nguồn đã nối</b><p>Khoảng trống dữ liệu không tự động bị biến thành rủi ro.</p></div>`;
      return;
    }
    $("alertsList").innerHTML=rows.slice(0,6).map((x,i)=>`<div class="alert-item">
      <span class="alert-num ${x.level==="danger"?"":"warn"}">${i+1}</span>
      <div><b>${x.title}</b><p>${x.detail}</p>${x.tag?`<small>${x.tag}</small>`:""}</div><time class="alert-time">${x.time||""}</time>
    </div>`).join("");
  }

  function pctForTime(time){
    const m=String(time||"").match(/(\d{1,2}):(\d{2})/); if(!m)return null;
    const minutes=Number(m[1])*60+Number(m[2]);
    const start=6*60,end=22*60;
    return Math.max(0,Math.min(100,(minutes-start)/(end-start)*100));
  }
  function renderTimeline(){
    const f=arr(state.flights).map(x=>({...x,status:fixText(x.status),station:fixText(x.station)}));
    const flights=f.filter(x=>{const p=pctForTime(x.scheduled_time);return p!==null&&p>=0&&p<=100}).slice(0,12);
    $("tlFlights").innerHTML=flights.map((x,i)=>{
      const left=pctForTime(x.scheduled_time);
      const cls=statusClass(x.status)==="bad"?"bad":"flight";
      return `<span class="tl-block ${cls}" title="${x.operating_flight_number} ${x.station} ${x.status}" style="left:${left}%;width:7%;transform:translateX(-10%)">${x.operating_flight_number}</span>`;
    }).join("") || `<span class="timeline-empty">Không có chuyến trong khung giờ</span>`;

    const tours=arr(state.tours).map(normalizeTour);
    $("tlTours").innerHTML=tours.map(x=>{
      const left=pctForTime(x.time);if(left===null)return"";
      return `<span class="tl-block" style="left:${left}%;width:12%;transform:translateX(-4%)">${x.code}</span>`;
    }).join("") || `<span class="timeline-empty">Chờ GET tours</span>`;

    const ferries=arr(state.ferries);
    $("tlFerries").innerHTML=ferries.map(x=>{
      const left=pctForTime(x.time||x.scheduled_time);if(left===null)return"";
      return `<span class="tl-block flight" style="left:${left}%;width:11%;transform:translateX(-4%)">${fixText(x.operator||x.carrier||"Tàu")}</span>`;
    }).join("") || `<span class="timeline-empty">Chờ GET tàu/phà</span>`;

    const alerts=state.derivedAlerts.slice(0,4);
    $("tlAlerts").innerHTML=alerts.map((x,i)=>`<span class="tl-block ${x.level==="danger"?"bad":"warn"}" style="left:${8+i*18}%;width:15%">${x.tag||"Cảnh báo"}</span>`).join("") || `<span class="timeline-empty">Không có exception live</span>`;
  }

  function renderActivity(){
    const rows=state.demoActivities||[];
    if(!rows.length)return;
    $("activityList").innerHTML=rows.map((x,i)=>`<div class="activity-item"><div class="avatar">${initials(x.name)}</div><div><b>${x.name}</b><small>${x.text}</small></div><time>${x.time}</time></div>`).join("");
  }
  function initials(name){return String(name||"").split(/\s+/).slice(-2).map(x=>x[0]||"").join("").toUpperCase()||"JT"}

  function renderSourceHealth(){
    const rows=[];
    const w=state.weather;
    if(w?.sources){
      Object.entries(w.sources).forEach(([name,x])=>{
        rows.push({name,quality:x.status,detail:fixText(x.detail),freshness:ageLabel(w.generated_at),state:x.status==="PASS"?"live":x.status==="PARTIAL"?"stale":"bad"})
      });
    }
    rows.push({
      name:"AQI / CAMS",quality:state.aqi?.status||state.sourceResults.aqi?.status||"FAILED",
      detail:state.aqi?.source||"CAMS",freshness:state.aqi?.sampled_time?ageLabel(state.aqi.sampled_time):"--",
      state:state.aqi?"live":"bad"
    });
    rows.push({
      name:"Triều / Copernicus",quality:state.tide?.status||state.sourceResults.tide?.status||"FAILED",
      detail:state.tide?.source||"Copernicus",freshness:state.tide?.generated_at?ageLabel(state.tide.generated_at):"--",
      state:state.tide?"live":"bad"
    });
    rows.push({
      name:"Sun Airport",quality:state.flights?.report_state||state.sourceResults.flights?.status||"FAILED",
      detail:state.flights?.source?.name||"PQ Airport",freshness:state.flights?.collected_at_vn?ageLabel(state.flights.collected_at_vn):"--",
      state:state.flights?"live":"bad"
    });
    ["tours","ferries","tasks"].forEach(name=>{
      const sr=state.sourceResults[name];
      rows.push({name:`Internal GET / ${name}`,quality:sr?.status||"UNCONFIGURED",detail:sr?.url||"Chưa có endpoint cụ thể",freshness:"--",state:sr?.status==="LIVE"?"live":sr?.status==="FAILED"?"bad":"stale"});
    });
    $("sourceHealthRows").innerHTML=rows.map(x=>`<div class="source-row"><div><b>${x.name}</b><small>${x.detail}</small></div><span class="freshness">${x.freshness}</span><span class="source-state ${x.state}">${x.quality}</span></div>`).join("");
    const core=["weather","aqi","tide","flights"];
    const live=core.filter(x=>state.sourceResults[x]?.status==="LIVE").length;
    $("coverageState").className=`source-state ${live===core.length?"live":"stale"}`;
    $("coverageState").textContent=`${live}/${core.length} NGUỒN LÕI`;
  }

  function renderShifts(){
    const s=state.shifts;
    if(!s)return;
    $("shiftBody").className="";
    $("shiftBody").innerHTML=`<div style="padding:11px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div class="mini-card"><h3>Ca hiện tại</h3><strong style="font-size:13px">${fixText(s.current||s.name||"Ca hiện tại")}</strong><p>${fixText(s.time||"")}</p></div>
      <div class="mini-card"><h3>Ca tiếp theo</h3><strong style="font-size:13px">${fixText(s.next||"Chưa có")}</strong><p>${fixText(s.nextTime||"")}</p></div>
    </div>`;
  }

  function renderGaps(){
    const gaps=state.weather?.gaps||[];
    $("gapList").innerHTML=gaps.length?gaps.slice(0,6).map(x=>`<div class="gap-item"><b>${fixText(x.name)}</b><p>${fixText(x.detail)}</p></div>`).join(""):`<div class="empty-state slim"><b>Không có critical gap được công bố</b></div>`;
  }

  function updateGlobalKPIs(){
    if(!state.flights){$("kpiFlights").textContent="--";$("kpiFlightMeta").textContent="Nguồn lỗi/không có"}
    const failures=["weather","aqi","tide","flights"].filter(x=>state.sourceResults[x]?.status==="FAILED").length;
    $("navSourceBadge").classList.toggle("hidden",!failures);
    $("navSourceBadge").textContent=failures?`${failures} LỖI`:"";
  }

  function wireUI(){
    $("sidebarToggle")?.addEventListener("click",()=>document.body.classList.toggle("sidebar-collapsed"));
    $$(".scope-tabs button").forEach(btn=>btn.addEventListener("click",()=>{
      $$(".scope-tabs button").forEach(x=>x.classList.toggle("active",x===btn));
      const target=({flight:"flights",ferry:"ferries",tour:"tours",task:"tasks",weather:"weather"})[btn.dataset.scope];
      if(target) $(target)?.scrollIntoView({behavior:"smooth",block:"start"});
    }));
    $$(".segmented [data-flight-dir]").forEach(btn=>btn.addEventListener("click",()=>{
      state.flightDir=btn.dataset.flightDir;
      $$(".segmented [data-flight-dir]").forEach(x=>x.classList.toggle("active",x===btn));
      renderFlights();
    }));
    $("globalSearch").addEventListener("input",e=>{
      const q=e.target.value.trim().toLowerCase();
      if(!q){$$("[data-tour-search]").forEach(tr=>tr.hidden=false);return}
      $$("[data-tour-search]").forEach(tr=>tr.hidden=!tr.dataset.tourSearch.includes(q));
    });
    $("tourSearch").addEventListener("input",e=>{
      const q=e.target.value.trim().toLowerCase();
      $$("[data-tour-search]").forEach(tr=>tr.hidden=q&&!tr.dataset.tourSearch.includes(q));
    });
    document.addEventListener("keydown",e=>{
      if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();$("globalSearch").focus()}
    });
    $("quickButton")?.addEventListener("click",()=>$("quickDialog").showModal());
    $("mobileMore")?.addEventListener("click",()=>$("quickDialog").showModal());
    $$("#quickDialog [data-action]").forEach(btn=>btn.addEventListener("click",()=>showToast("UI đã sẵn sàng. Chưa ghi vào backend cũ.")));
    $$(".nav-item").forEach(a=>a.addEventListener("click",()=>{
      $$(".nav-item").forEach(x=>x.classList.toggle("active",x===a));
    }));
    $$(".mobile-nav a").forEach(a=>a.addEventListener("click",()=>{
      $$(".mobile-nav a").forEach(x=>x.classList.toggle("active",x===a));
    }));

    const today=dateKeyVN();
    state.selectedDate=today;$("dayPicker").value=today;
    $("todayButton").addEventListener("click",()=>{$("dayPicker").value=today;state.selectedDate=today;showToast("Đang hiển thị snapshot live hôm nay.")});
    $("dayPicker").addEventListener("change",e=>{
      if(e.target.value!==today){
        showToast("Lịch sử cần snapshot index riêng. V1 giữ dữ liệu live, không giả lập ngày cũ.");
        setTimeout(()=>{e.target.value=today},250);
      }
    });
    $("prevDay").addEventListener("click",()=>showToast("Chưa bật lịch sử cho Operations V1."));
    $("nextDay").addEventListener("click",()=>showToast("Chưa bật dữ liệu tương lai cho Operations V1."));
  }

  let toastTimer;
  function showToast(msg){
    const el=$("toast");el.textContent=msg;el.classList.add("show");
    clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove("show"),2600);
  }

  async function init(){
    setLogo();
    startClock();
    noWritesGuard();
    wireUI();
    await loadAll();
  }
  init();
})();
