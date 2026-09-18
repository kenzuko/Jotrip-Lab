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
    jotripForecastCards:document.querySelectorAll(".jotrip-forecast-card").length,
    rawForecastRemoved:!document.querySelector(".forecast-panel")&&!document.querySelector(".ensemble-panel"),
    rawForecastTableRemoved:!document.querySelector("#forecastRows")&&!document.querySelector(".horizon-tabs"),
    aqiItems:document.querySelectorAll("#aqiQuick .quick-item").length,
    tideItems:document.querySelectorAll("#tideQuick .quick-item").length,
    nowcastItems:document.querySelectorAll("#nowcastQuick .quick-item").length,
    aqiEmpty:!!document.querySelector("#aqiQuick .data-empty"),
    tideEmpty:!!document.querySelector("#tideQuick .data-empty"),
    nowcastEmpty:!!document.querySelector("#nowcastQuick .data-empty"),
    sourceCards:document.querySelectorAll("#sourceGrid .source-card").length,
    mapDeferred:!document.querySelector("#mapBox iframe")&&!document.querySelector("#mapBox img"),
    jotripForecastPanel:!!document.querySelector(".jotrip-forecast-panel"),
    pointTabs:document.querySelectorAll("#pointTabs [data-point]").length,
    islandWatchRemoved:!document.querySelector(".island-watch-panel"),
    islandSummary:!!document.querySelector("#islandSummary"),
    numberGuide:!!document.querySelector(".number-guide"),
    aboutPanel:!!document.querySelector(".about-panel"),
    compactFeedback:!!document.querySelector(".field-strip")&&!document.querySelector(".feedback-panel"),
    mapBeforeForecast:(document.querySelector(".map-panel")?.compareDocumentPosition(document.querySelector(".jotrip-forecast-panel"))&Node.DOCUMENT_POSITION_FOLLOWING)!==0,
    innerOverflow:[...document.querySelectorAll(".panel")].flatMap(panel=>{
      const pr=panel.getBoundingClientRect();
      return [...panel.querySelectorAll("*")].filter(el=>{
        if(el.tagName==="OPTION"||el.hidden||el.closest("[hidden]")||getComputedStyle(el).display==="none")return false;
        if(el.closest(".table-scroll,.ensemble-table-shell,.actual-strip,.hourly-strip,.point-tabs"))return false;
        const r=el.getBoundingClientRect();
        return r.right>pr.right+3||r.left<pr.left-3;
      }).slice(0,4).map(el=>el.className||el.tagName);
    }).slice(0,12)
  }));

  const heavyInitial=initial.filter(u=>/embed\.windy|dashboard-data\.json|tide\.json|weather-aqi|weather-ensemble|weather-nowcast|himawari\/img/i.test(u));
  const rawForecastRequests=initial.filter(u=>/dashboard-data\.json/.test(u));

  await page.waitForTimeout(1800);
  const deferred={
    tide:requests.some(u=>/tide\.json/.test(u)),
    aqi:requests.some(u=>/weather-aqi|air-quality\.json/.test(u)),
    nowcast:requests.some(u=>/weather-nowcast|nowcast\.json/.test(u))
  };
  const noRawForecastFetch=!requests.some(u=>/dashboard-data\.json/.test(u));

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
    checks.jotripForecastCards>=1&&
    checks.jotripForecastPanel&&
    checks.rawForecastRemoved&&
    checks.rawForecastTableRemoved&&
    (checks.aqiItems>=3||checks.aqiEmpty)&&
    (checks.tideItems>=3||checks.tideEmpty)&&
    (checks.nowcastItems>=4||checks.nowcastEmpty)&&
    checks.sourceCards>=1&&
    checks.mapDeferred&&
    checks.pointTabs>=8&&
    checks.islandWatchRemoved&&
    checks.islandSummary&&
    checks.numberGuide&&
    checks.aboutPanel&&
    checks.compactFeedback&&
    checks.mapBeforeForecast&&
    checks.innerOverflow.length===0&&
    heavyInitial.length===0&&
    deferred.tide&&deferred.aqi&&deferred.nowcast&&
    noRawForecastFetch&&rawForecastRequests.length===0&&
    errors.length===0&&
    mapLoaded;

  console.log(name,JSON.stringify({checks,heavyInitial,deferred,noRawForecastFetch,errors,initialRequests:initial.length,mapLoaded}));
  if(!ok)failed=true;
  await page.close();
}

await browser.close();
if(failed)process.exit(1);
