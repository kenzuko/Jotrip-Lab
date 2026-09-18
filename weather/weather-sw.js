const VERSION="weather-lab-2026.09.18.01";
const CACHE=`${VERSION}-static`;
const STATIC=[
  "/Jotrip-Lab/weather/",
  "/Jotrip-Lab/weather/weather-dashboard.css",
  "/Jotrip-Lab/weather/weather-dashboard-base.css",
  "/Jotrip-Lab/weather/weather-dashboard-typography.css",
  "/Jotrip-Lab/weather/weather-dashboard.js?v=20260918-01",
  "/Jotrip-Lab/weather/weather-dashboard-enhancements.js",
  "/Jotrip-Lab/weather/weather-dashboard-legacy.js",
  "/Jotrip-Lab/weather/weather-dashboard-air-quality.js",
  "/Jotrip-Lab/weather/weather-dashboard-tide.js",
  "/Jotrip-Lab/weather/weather-dashboard-local-now.js",
  "/Jotrip-Lab/weather/weather-dashboard-weather-map.js",
  "/Jotrip-Lab/weather/weather-dashboard-history-link.js",
  "/Jotrip-Lab/weather/weather-app-icon.svg",
  "/Jotrip-Lab/weather/weather-manifest.webmanifest"
];

self.addEventListener("install",e=>e.waitUntil(
  caches.open(CACHE)
    .then(async c=>{
      await Promise.allSettled(STATIC.map(async url=>{
        const r=await fetch(url,{cache:"reload"});
        if(r.ok)await c.put(url,r);
      }));
    })
    .then(()=>self.skipWaiting())
));

self.addEventListener("activate",e=>e.waitUntil(
  caches.keys()
    .then(keys=>Promise.all(keys.filter(k=>k.startsWith("weather-lab-")&&k!==CACHE).map(k=>caches.delete(k))))
    .then(()=>self.clients.claim())
));

self.addEventListener("message",e=>{
  if(e.data?.type==="SKIP_WAITING")self.skipWaiting();
});

self.addEventListener("fetch",e=>{
  const r=e.request;
  if(r.method!=="GET")return;
  const u=new URL(r.url);
  if(u.origin!==location.origin)return;

  if(
    u.pathname.endsWith("/Jotrip-Lab/weather/data/dashboard-data.json")||
    u.pathname.endsWith("/Jotrip-Lab/weather/data/air-quality.json")||
    u.pathname.endsWith("/Jotrip-Lab/weather/data/tide.json")||
    u.pathname.endsWith("/Jotrip-Lab/weather/data/nowcast.json")||
    u.pathname.includes("/Jotrip-Lab/weather/data/weather-groundtruth/")
  ){
    e.respondWith(fetch(r,{cache:"no-store"}).catch(()=>caches.match(r)));
    return;
  }

  const isWeatherAsset=
    u.pathname.endsWith("/Jotrip-Lab/weather/")||
    /\/weather-dashboard[^/]*$/.test(u.pathname)||
    u.pathname.endsWith("/Jotrip-Lab/weather/weather-app-icon.svg")||
    u.pathname.endsWith("/Jotrip-Lab/weather/weather-manifest.webmanifest");

  if(!isWeatherAsset)return;

  e.respondWith(
    fetch(r)
      .then(res=>{
        const copy=res.clone();
        caches.open(CACHE).then(c=>c.put(r,copy));
        return res;
      })
      .catch(()=>caches.match(r))
  );
});
