import { chromium } from "playwright";
const base=process.env.WEATHER_V2_URL||"http://127.0.0.1:4173/weather-v2.html";
const sizes=[["iphone390",390,844],["iphone430",430,932],["desktop",1440,1000]];
const browser=await chromium.launch({headless:true});
let failed=false;

for(const [name,width,height] of sizes){
  const page=await browser.newPage({viewport:{width,height}});
  const errors=[],requests=[];
  page.on("request",r=>requests.push(r.url()));
  page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{
    if(m.type()!=="error")return;
    const t=m.text();
    if(/Permissions policy violation/i.test(t))return;
    errors.push(t);
  });

  await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
  await page.waitForFunction(()=>document.querySelector("#heroTemp")?.textContent!=="--",{timeout:10000});
  await page.waitForTimeout(250);

  const initial=[...requests];
  const checks=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
    hero:document.querySelector("#heroTemp")?.textContent,
    actualCards:document.querySelectorAll(".actual-card").length,
    hourly:document.querySelectorAll(".hour-card").length,
    forecastRows:document.querySelectorAll("#forecastRows tr").length,
    aqiItems:document.querySelectorAll("#aqiQuick .quick-item").length,
    tideItems:document.querySelectorAll("#tideQuick .quick-item").length,
    nowcastItems:document.querySelectorAll("#nowcastQuick .quick-item").length,
    sourceCards:document.querySelectorAll("#sourceGrid .source-card").length,
    mapDeferred:!document.querySelector("#mapBox iframe")&&!document.querySelector("#mapBox img"),
    horizonTabs:document.querySelectorAll(".horizon-tabs button").length
  }));

  const heavyInitial=initial.filter(u=>/embed\.windy|dashboard-data\.json|tide\.json|weather-aqi|weather-ensemble|weather-nowcast|himawari\/img/i.test(u));

  await page.waitForTimeout(1800);
  const deferred={
    forecast:requests.some(u=>/dashboard-data\.json/.test(u)),
    tide:requests.some(u=>/tide\.json/.test(u)),
    aqi:requests.some(u=>/weather-aqi|air-quality\.json/.test(u)),
    nowcast:requests.some(u=>/weather-nowcast|nowcast\.json/.test(u))
  };

  let mapLoaded=true;
  if(name==="iphone390"){
    await page.locator(".map-panel").scrollIntoViewIfNeeded();
    await page.waitForSelector("#mapBox iframe",{timeout:8000});
    mapLoaded=await page.locator("#mapBox iframe").evaluate(el=>/windy\.com/.test(el.src));
  }

  await page.screenshot({path:`artifacts/weather-v2-${name}.png`,fullPage:true});

  const ok=
    checks.overflow<=2&&
    !!checks.hero&&
    checks.actualCards>=1&&
    checks.hourly>=1&&
    checks.forecastRows>=1&&
    checks.aqiItems>=3&&
    checks.tideItems>=3&&
    checks.nowcastItems>=4&&
    checks.sourceCards>=1&&
    checks.mapDeferred&&
    checks.horizonTabs===4&&
    heavyInitial.length===0&&
    deferred.forecast&&deferred.tide&&deferred.aqi&&deferred.nowcast&&
    errors.length===0&&
    mapLoaded;

  console.log(name,JSON.stringify({checks,heavyInitial,deferred,errors,initialRequests:initial.length,mapLoaded}));
  if(!ok)failed=true;
  await page.close();
}

await browser.close();
if(failed)process.exit(1);
