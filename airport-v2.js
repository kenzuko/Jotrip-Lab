(() => {
  const baseFetchLive=fetchLivePayload;
  const baseFetchSnapshot=fetchSnapshotPayload;
  const baseRenderSummary=renderSummary;
  const baseRenderAnalytics=renderAnalytics;
  const TZ='Asia/Ho_Chi_Minh';
  state.boardDateOffset=0;

  function todayVN(){return new Intl.DateTimeFormat('en-CA',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
  function addDays(day,n){const d=new Date(`${day}T12:00:00+07:00`);d.setUTCDate(d.getUTCDate()+n);return new Intl.DateTimeFormat('en-CA',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).format(d)}
  function selectedDate(){return addDays(todayVN(),state.boardDateOffset||0)}
  function labelForOffset(o){return o===-1?'Hôm qua':o===1?'Ngày mai':'Hôm nay'}

  fetchLivePayload=async function(){
    if(!LIVE_API_URL)throw new Error('Live API chưa cấu hình');
    const u=new URL(LIVE_API_URL);u.searchParams.set('date',selectedDate());u.searchParams.set('t',String(Date.now()));
    const res=await fetch(u,{cache:'no-store',headers:{accept:'application/json'}});
    if(!res.ok)throw new Error(`JoTrip Live API HTTP ${res.status}`);
    const payload=await res.json();
    if(!payload?.latest?.records||!payload?.health)throw new Error('JoTrip Live API trả dữ liệu không hợp lệ');
    return payload;
  };
  fetchSnapshotPayload=async function(){if((state.boardDateOffset||0)!==0)throw new Error('Không dùng snapshot hôm nay cho bảng ngày khác');return baseFetchSnapshot()};

  function buildDaySwitch(){
    const strip=document.querySelector('.source-strip');if(!strip||document.querySelector('.board-day-switch'))return;
    const nav=document.createElement('div');nav.className='board-day-switch';nav.setAttribute('aria-label','Chọn ngày bảng bay');
    [[-1,'HÔM QUA'],[0,'HÔM NAY'],[1,'NGÀY MAI']].forEach(([offset,label])=>{const b=document.createElement('button');b.type='button';b.dataset.offset=offset;b.textContent=label;if(offset===0)b.classList.add('active');b.onclick=()=>{state.boardDateOffset=Number(offset);state.limit=8;state.filter='all';document.querySelectorAll('#filterChips button').forEach(x=>x.classList.toggle('active',x.dataset.filter==='all'));nav.querySelectorAll('button').forEach(x=>x.classList.toggle('active',Number(x.dataset.offset)===state.boardDateOffset));applyDayMode();load()};nav.appendChild(b)});
    strip.after(nav);
    const cards=document.querySelectorAll('.card.live-only');if(cards[1])cards[1].classList.add('next-relative');
    const sides=document.querySelectorAll('.side-card.live-only');sides.forEach(x=>x.classList.add('next-relative'));
  }

  function applyDayMode(){
    const o=state.boardDateOffset||0,notToday=o!==0;document.body.classList.toggle('board-not-today',notToday);
    const hero=document.querySelector('.hero h2');if(hero)hero.textContent=`${labelForOffset(o)} tại Phú Quốc`;
    const boardTitle=document.querySelector('.card.live-only .card-head h3');if(boardTitle)boardTitle.textContent=`Chuyến bay ${labelForOffset(o).toLowerCase()}`;
    const pill=document.querySelector('.live-pill');if(pill){pill.innerHTML=notToday?'BOARD':'<i></i> LIVE'}
    if(notToday){const ops=document.querySelector('#opsState');if(ops){ops.className='ops-state';ops.textContent=o<0?'BẢNG HÔM QUA':'LỊCH NGÀY MAI'}}
  }

  renderSummary=function(){baseRenderSummary();applyDayMode();const o=state.boardDateOffset||0;if(o!==0){const u=document.querySelector('#updatedAt');if(u)u.textContent=`Bảng ${state.latest?.source_date||selectedDate()} · lấy từ Sun Airport lúc ${new Date(state.latest?.collected_at_vn).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',timeZone:TZ})}`}};

  function performanceRows(records){
    const m=new Map();for(const r of records||[]){if(!r.actual_time||!Number.isFinite(Number(r.actual_delay_minutes)))continue;const name=airlineFor(r)||r.airline_code||'Khác';if(!m.has(name))m.set(name,{name,scored:0,on:0,late:0,delaySum:0});const x=m.get(name),d=Number(r.actual_delay_minutes);x.scored++;if(d<=15)x.on++;else x.late++;x.delaySum+=Math.max(0,d)}
    return [...m.values()].map(x=>({...x,otp:x.scored?x.on*100/x.scored:0,latePct:x.scored?x.late*100/x.scored:0,avg:x.scored?x.delaySum/x.scored:0})).sort((a,b)=>b.scored-a.scored||b.otp-a.otp);
  }
  function renderAirlinePerformance(){
    const host=document.querySelector('.analytics-only.card');if(!host)return;let block=document.querySelector('#airlinePerformanceBlock');if(!block){block=document.createElement('div');block.id='airlinePerformanceBlock';block.className='analytics-block';host.appendChild(block)}
    const rows=performanceRows(state.latest?.records||[]);const title=`Hiệu suất hãng bay · OTP15 · ${labelForOffset(state.boardDateOffset||0)}`;
    if(!rows.length){block.innerHTML=`<h4>${title}</h4><p class="analytics-note">Chưa đủ chuyến có giờ thực tế để tính. OTP15 chỉ chấm chuyến có actual time từ Sun Airport.</p>`;return}
    block.innerHTML=`<h4>${title}</h4><div class="airline-performance"><table class="airline-table"><thead><tr><th>Hãng</th><th>Mẫu</th><th>Đúng giờ</th><th>Trễ &gt;15'</th><th>Trễ TB</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${escapeHtml(x.name)}</td><td>${x.scored}</td><td class="${x.otp>=80?'otp-good':'otp-watch'}">${x.otp.toFixed(0)}%</td><td>${x.latePct.toFixed(0)}%</td><td>${x.avg.toFixed(0)} phút</td></tr>`).join('')}</tbody></table></div><p class="analytics-note">OTP15 = giờ thực tế không muộn quá 15 phút so với giờ lịch. Chuyến chưa có actual time không được chấm.</p>`;
  }
  renderAnalytics=function(){baseRenderAnalytics();renderAirlinePerformance()};

  renderNextArrivals=function(){
    if((state.boardDateOffset||0)!==0)return;
    const a=(state.latest?.records||[]).filter(r=>r.direction==='arrival'&&!isPastRecord(r)).sort((x,y)=>(mins(scheduledTime(x))??9999)-(mins(scheduledTime(y))??9999)).slice(0,5);
    $('#nextArrivalsList').innerHTML=a.length?a.map(r=>{const info=timingInfo(r),status=displayStatusLabel(r),air=airlineFor(r);return `<div class="arrival-item"><div class="arrival-time">${escapeHtml(info.scheduled||'--:--')}</div><div class="arrival-main"><strong>${escapeHtml(r.operating_flight_number)} · ${escapeHtml(stationLabel(r.station))}</strong><span class="arrival-airline">${escapeHtml(air)}</span>${isDelayed(r)&&info.expected?`<span class="arrival-estimate">Dự kiến ${escapeHtml(info.expected)}</span>`:''}</div><span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span></div>`}).join(''):'<div class="empty-state">Chưa có chuyến đến tiếp theo trong dữ liệu.</div>';
  };

  buildDaySwitch();applyDayMode();
})();
