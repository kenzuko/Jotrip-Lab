import { chromium } from "playwright";
const base=process.env.WEATHER_V2_URL||"http://127.0.0.1:4173/weather-v2.html";
const sizes=[["iphone390",390,844],["iphone430",430,932],["desktop",1440,1000]];
const browser=await chromium.launch({headless:true});
let failed=false;
for(const [name,width,height] of sizes){
  const page=await browser.newPage({viewport:{width,height}}),errors=[],requests=[];
  page.on("request",r=>requests.push(r.url()));
  page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{if(m.type()!=="error")return;const t=m.text();if(/Permissions policy violation/i.test(t))return;errors.push(t)});
  await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
  await page.waitForFunction(()=>document.querySelector("#heroTemp")?.textContent!=="--",{timeout:10000});
  await page.waitForTimeout(200);
  const initial=[...requests];
  const checks=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
    hero:document.querySelector("#heroTemp")?.textContent,
    actualCards:document.querySelectorAll(".actual-card").length,
    hourly:document.querySelectorAll(".hour-card").length,
    mapHidden:document.querySelector("#mapArea")?.hidden,
    forecastHidden:document.querySelector("#forecastDetail")?.hidden
  }));
  const heavyInitial=initial.filter(u=>/embed\.windy|dashboard-data\.json|tide\.json|weather-aqi|weather-ensemble|himawari\/img/i.test(u));
  let forecastLoaded=false,mapLoaded=false;
  if(name==="iphone390"){
    await page.click("#openForecast");
    await page.waitForSelector("#forecastDetail .forecast-table",{timeout:10000});
    forecastLoaded=requests.some(u=>/dashboard-data\.json/.test(u));
    await page.click("#openMap");
    await page.waitForSelector("#mapBox iframe",{timeout:5000});
    mapLoaded=await page.locator("#mapBox iframe").evaluate(el=>/windy\.com/.test(el.src));
  }
  await page.screenshot({path:`artifacts/weather-v2-${name}.png`,fullPage:true});
  const ok=checks.overflow<=2&&checks.hero&&checks.actualCards>=1&&checks.hourly>=1&&checks.mapHidden&&checks.forecastHidden&&heavyInitial.length===0&&errors.length===0&&(name!=="iphone390"||(forecastLoaded&&mapLoaded));
  console.log(name,JSON.stringify({checks,heavyInitial,errors,initialRequests:initial.length,forecastLoaded,mapLoaded}));
  if(!ok)failed=true;
  await page.close();
}
await browser.close();
if(failed)process.exit(1);
