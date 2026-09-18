import { chromium } from "playwright";
const base=process.env.WEATHER_V2_URL||"http://127.0.0.1:4173/weather.html";
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
    forecastRegionTabs:document.querySelectorAll("#forecastRegionTabs [data-region]").length,
    hazardCards:document.querySelectorAll("#hazardBoard article").length,
    mapTabs:document.querySelectorAll(".map-tabs [data-map]").length,
    feedbackBeforeActual:(document.querySelector(".field-strip")?.compareDocumentPosition(document.querySelector("#actualStrip"))&Node.DOCUMENT_POSITION_FOLLOWING)!==0,
    standaloneNowcastRemoved:!document.querySelector(".nowcast-panel"),
    mapConvective:!!document.querySelector("#mapConvective"),
    rawForecastRemoved:!document.querySelector(".forecast-panel")&&!document.querySelector(".ensemble-panel"),
    rawForecastTableRemoved:!document.querySelector("#forecastRows")&&!document.querySelector(".horizon-tabs"),
    aqiItems:document.querySelectorAll("#aqiQuick .quick-item").length,
    tideItems:document.querySelectorAll("#tideQuick .quick-item").length,
    aqiEmpty:!!document.querySelector("#aqiQuick .data-empty"),
    tideEmpty:!!document.querySelector("#tideQuick .data-empty"),
    sourceCards:document.querySelectorAll("#sourceGrid .source-card").length,
    mapDeferred:!document.querySelector("#mapBox iframe")&&!document.querySelector("#mapBox img"),
    jotripForecastPanel:!!document.querySelector(".jotrip-forecast-panel"),
    pointTabs:document.querySelectorAll("#pointTabs [data-point]").length,
    islandWatchRemoved:!document.querySelector(".island-watch-panel"),
    islandSummary:!!document.querySelector("#islandSummary"),
    numberGuide:!!document.querySelector(".number-guide"),
    aboutPanel:!!document.querySelector(".about-panel"),
    commandCenter:!!document.querySelector(".command-center"),
    photoHero:!!document.querySelector(".weather-scene-hero"),
    tideSeries:!!document.querySelector("#tideSpark polyline"),
    situationGap:(()=>{const a=document.querySelector(".command-center .island-summary")?.getBoundingClientRect(),b=document.querySelector("#hazardBoard")?.getBoundingClientRect();return a&&b?Math.round(b.top-a.bottom):9999})(),
    situationHeight:Math.round(document.querySelector(".situation-rail")?.getBoundingClientRect().height||0),
    compactFeedback:!!document.querySelector(".field-strip")&&!document.querySelector(".feedback-panel"),
    mapBeforeForecast:(document.querySelector(".map-panel")?.compareDocumentPosition(document.querySelector(".jotrip-forecast-panel"))&Node.DOCUMENT_POSITION_FOLLOWING)!==0,
    innerOverflow:[...document.querySelectorAll(".panel")].flatMap(panel=>{
      const pr=panel.getBoundingClientRect();
      return [...panel.querySelectorAll("*")].filter(el=>{
        if(el.tagName==="OPTION"||el.hidden||el.closest("[hidden]")||getComputedStyle(el).display==="none")return false;
        if(el.closest(".table-scroll,.forecast-table-shell,.ensemble-table-shell,.actual-strip,.hourly-strip,.point-tabs"))return false;
        const r=el.getBoundingClientRect();
        return r.right>pr.right+3||r.left<pr.left-3;
      }).slice(0,4).map(el=>el.className||el.tagName);
    }).slice(0,12)
  }));

  const heavyInitial=initial.filter(u=>/embed\.windy|dashboard-data\.json|weather-aqi|weather-ensemble|weather-nowcast|himawari\/img/i.test(u));
  const tideStartedEarly=initial.some(u=>/tide\.json/.test(u));
  const rawForecastRequests=initial.filter(u=>/dashboard-data\.json/.test(u));

  await page.waitForTimeout(1800);
  const deferred={
    tide:requests.some(u=>/tide\.json/.test(u)),
    aqi:requests.some(u=>/weather-aqi|air-quality\.json/.test(u)),
    nowcast:requests.some(u=>/weather-nowcast|nowcast\.json/.test(u)),
    regionalForecast:requests.some(u=>/jotrip-forecast\.json/.test(u))
  };
  const lateChecks=await page.evaluate(()=>({
    forecastRegionTabs:document.querySelectorAll("#forecastRegionTabs [data-region]").length,
    jotripForecastRows:document.querySelectorAll("#jotripForecastRows tr").length,
    beaufortCells:[...document.querySelectorAll("#jotripForecastRows td")].filter(td=>/Bft\s+\d/.test(td.textContent||"")).length,
    regionalTitle:document.querySelector("#jotripForecastTitle")?.textContent||"",
    forecastRibbon:document.querySelectorAll("#forecastDayRibbon .forecast-day").length
  }));
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
    lateChecks.jotripForecastRows>=12&&
    lateChecks.beaufortCells>=12&&
    lateChecks.forecastRegionTabs===4&&
    checks.hazardCards===4&&
    checks.mapTabs>=5&&
    checks.feedbackBeforeActual&&
    checks.standaloneNowcastRemoved&&
    checks.mapConvective&&
    checks.jotripForecastPanel&&
    checks.rawForecastRemoved&&
    checks.rawForecastTableRemoved&&
    (checks.aqiItems>=3||checks.aqiEmpty)&&
    (checks.tideItems>=3||checks.tideEmpty)&&

    checks.sourceCards>=1&&
    checks.mapDeferred&&
    checks.pointTabs>=8&&
    checks.islandWatchRemoved&&
    checks.islandSummary&&
    checks.numberGuide&&
    checks.aboutPanel&&
    checks.commandCenter&&
    checks.photoHero&&
    checks.tideSeries&&
    (width>760||(checks.situationGap>=0&&checks.situationGap<=24&&checks.situationHeight<760))&&
    lateChecks.forecastRibbon>=7&&
    checks.compactFeedback&&
    checks.mapBeforeForecast&&
    checks.innerOverflow.length===0&&
    heavyInitial.length===0&&
    tideStartedEarly&&deferred.tide&&deferred.aqi&&deferred.nowcast&&deferred.regionalForecast&&
    noRawForecastFetch&&rawForecastRequests.length===0&&
    errors.length===0&&
    mapLoaded;

  console.log(name,JSON.stringify({checks,lateChecks,heavyInitial,tideStartedEarly,deferred,noRawForecastFetch,errors,initialRequests:initial.length,mapLoaded}));
  if(!ok)failed=true;
  await page.close();
}

await browser.close();
if(failed)process.exit(1);
