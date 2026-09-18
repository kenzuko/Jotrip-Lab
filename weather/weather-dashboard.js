(()=>{
  const V="20260918-01";
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
    style("/Jotrip-Lab/weather/weather-dashboard-typography.css");

    try{
      await load("/Jotrip-Lab/weather/weather-dashboard-enhancements.js");
      await load("/Jotrip-Lab/weather/weather-dashboard-legacy.js");
      await window.WeatherLabEnhancements?.afterLegacy?.();
    }catch(err){
      fatal(err);
      return;
    }

    await optional("/Jotrip-Lab/weather/weather-dashboard-air-quality.js","chất lượng không khí",()=>window.WeatherLabAirQuality?.install?.());
    await optional("/Jotrip-Lab/weather/weather-dashboard-tide.js","thủy triều",()=>window.WeatherLabTide?.install?.());
    await optional("/Jotrip-Lab/weather/weather-dashboard-local-now.js","PQ Local Now",()=>window.PQLocalNow?.install?.());
    await optional("/Jotrip-Lab/weather/weather-dashboard-weather-map.js","bản đồ thời tiết",()=>window.PQWeatherMap?.install?.());

    // OpenStreetMap/Leaflet đã tắt. Không tải tile, Leaflet hoặc mô-đun bản đồ.
    // Mô-đun polish động cũng tạm ngưng để ưu tiên tải trang ổn định;
    // các nhãn tiếng Việt sẽ được giữ ở lớp giao diện cốt lõi thay vì observer runtime.

    await optional("/Jotrip-Lab/weather/weather-dashboard-history-link.js","lịch sử và đối chiếu",()=>window.WeatherLabHistoryLink?.install?.());
  }

  boot();
})();
