(()=>{
  const V="20260916-15";
  const style=href=>{
    const l=document.createElement("link");
    l.rel="stylesheet";
    l.href=`${href}?v=${V}`;
    l.onerror=()=>console.warn(`Không tải được ${href}`);
    document.head.appendChild(l);
  };
  const load=src=>new Promise((ok,fail)=>{
    const s=document.createElement("script");
    s.src=`${src}?v=${V}`;
    s.async=false;
    s.onload=ok;
    s.onerror=()=>fail(new Error(`Không tải được ${src}`));
    document.head.appendChild(s);
  });
  const warn=(label,err)=>console.warn(`[Weather Lab] Bỏ qua mô-đun ${label}:`,err);
  const optional=async(src,label,install)=>{
    try{
      await load(src);
      await install?.();
    }catch(err){
      warn(label,err);
    }
  };
  const fatal=err=>{
    console.error(err);
    document.body?.insertAdjacentHTML("afterbegin",'<div style="padding:12px;background:#fff1f2;color:#9b3f46">Không tải được dữ liệu cốt lõi của Weather Lab. Hãy tải lại trang sau ít phút.</div>');
  };

  async function boot(){
    style("/weather-dashboard-typography.css");

    try{
      await load("/weather-dashboard-enhancements.js");
      await load("/weather-dashboard-legacy.js");
      await window.WeatherLabEnhancements?.afterLegacy?.();
    }catch(err){
      fatal(err);
      return;
    }

    await optional("/weather-dashboard-air-quality.js","chất lượng không khí",()=>window.WeatherLabAirQuality?.install?.());
    await optional("/weather-dashboard-tide.js","thủy triều",()=>window.WeatherLabTide?.install?.());
    await optional("/weather-dashboard-observation-status.js","trạng thái quan sát",()=>window.WeatherLabObservationStatus?.install?.());
    await optional("/weather-dashboard-polish.js","hoàn thiện giao diện",()=>window.WeatherLabPolish?.install?.());

    // Bản đồ OpenStreetMap/Leaflet tạm tắt. Weather Lab ưu tiên dữ liệu vận hành,
    // tránh phụ thuộc CDN/tile bên ngoài làm chậm hoặc chặn quá trình tải trang.

    await optional("/weather-dashboard-history-link.js","lịch sử và đối chiếu",()=>window.WeatherLabHistoryLink?.install?.());
  }

  boot();
})();
