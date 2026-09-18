const VERSION="weather-intelligence-2026.09.18.02";
const CACHE=`${VERSION}-static`;
const STATIC=[
  "/Jotrip-Lab/weather/",
  "/Jotrip-Lab/weather/weather-v2.css?v=20260918-16",
  "/Jotrip-Lab/weather/weather-v2.js?v=20260918-16",
  "/Jotrip-Lab/weather/weather-brand.svg",
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
    .then(keys=>Promise.all(keys.filter(k=>k.startsWith("weather-")&&k!==CACHE).map(k=>caches.delete(k))))
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

  const liveData=
    u.pathname.endsWith("/weather/data/critical.json")||
    u.pathname.endsWith("/Jotrip-Lab/weather/jotrip-forecast.json")||
    u.pathname.includes("/weather/data/weather-groundtruth/")||
    u.pathname.includes("/weather/data/weather-aqi/")||
    u.pathname.includes("/weather/data/weather-nowcast/")||
    u.pathname.includes("/weather/data/weather-ensemble/")||
    u.pathname.endsWith("/weather/data/tide.json");

  if(liveData){
    e.respondWith(fetch(r,{cache:"no-store"}).catch(()=>caches.match(r)));
    return;
  }

  const isWeatherAsset=
    u.pathname.endsWith("/weather/")||
    u.pathname.endsWith("/weather/weather.html")||
    u.pathname.endsWith("/weather/v2.html")||
    u.pathname.endsWith("/weather/weather-v2.css")||
    u.pathname.endsWith("/weather/weather-v2.js")||
    u.pathname.endsWith("/weather/weather-brand.svg")||
    u.pathname.endsWith("/weather/weather-app-icon.svg")||
    u.pathname.endsWith("/weather/weather-manifest.webmanifest");

  if(!isWeatherAsset)return;

  e.respondWith(
    fetch(r,{cache:"no-store"})
      .then(res=>{
        const copy=res.clone();
        caches.open(CACHE).then(c=>c.put(r,copy));
        return res;
      })
      .catch(()=>caches.match(r))
  );
});
