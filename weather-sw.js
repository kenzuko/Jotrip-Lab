const VERSION="weather-lab-2026.09.16.10";
const CACHE=`${VERSION}-static`;
const STATIC=[
  "/weather.html",
  "/weather-dashboard.css",
  "/weather-dashboard-base.css",
  "/weather-dashboard-typography.css",
  "/weather-dashboard.js?v=20260916-16",
  "/weather-dashboard-enhancements.js",
  "/weather-dashboard-legacy.js",
  "/weather-dashboard-air-quality.js",
  "/weather-dashboard-tide.js",
  "/weather-dashboard-observation-status.js",
  "/weather-dashboard-history-link.js",
  "/weather-app-icon.svg",
  "/weather-manifest.webmanifest"
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
    u.pathname.endsWith("/weather/dashboard-data.json")||
    u.pathname.endsWith("/weather/air-quality.json")||
    u.pathname.endsWith("/weather/tide.json")||
    u.pathname.endsWith("/weather/nowcast.json")
  ){
    e.respondWith(fetch(r,{cache:"no-store"}).catch(()=>caches.match(r)));
    return;
  }

  const isWeatherAsset=
    u.pathname.endsWith("/weather.html")||
    /\/weather-dashboard[^/]*$/.test(u.pathname)||
    u.pathname.endsWith("/weather-app-icon.svg")||
    u.pathname.endsWith("/weather-manifest.webmanifest");

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
