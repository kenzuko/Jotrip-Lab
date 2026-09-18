import { chromium } from "playwright";

const base=process.env.WEATHER_UI_URL||"http://127.0.0.1:4173/weather.html";
const historyBase=new URL('/weather-history.html',base).href;
const sizes=[["iphone390",390,844],["iphone430",430,932],["tablet",768,1024],["desktop",1440,1100]];
const liveCritical=await fetch("https://kenzuko.github.io/Jotrip-Lab/weather/data/critical.json").then(r=>{if(!r.ok)throw new Error("critical "+r.status);return r.text()});
const liveForecast=await fetch("https://kenzuko.github.io/Jotrip-Lab/weather/jotrip-forecast.json").then(r=>{if(!r.ok)throw new Error("forecast "+r.status);return r.text()});
const liveTide=await fetch("https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/feat/weather-lab-data-engine-v1/weather/tide.json").then(r=>{if(!r.ok)throw new Error("tide "+r.status);return r.text()});
const liveAQI=await fetch("https://kenzuko.github.io/Jotrip-Lab/weather/data/weather-aqi/latest.json").then(r=>r.ok?r.text():"{}");
const liveNowcast=await fetch("https://kenzuko.github.io/Jotrip-Lab/weather/data/weather-nowcast/latest.json").then(r=>r.ok?r.text():"{}");
const browser=await chromium.launch({headless:true});
let failed=false;

function inside(r,w){
  return !!(r&&r.left>=-1&&r.right<=w+1);
}

for(const [name,width,height] of sizes){
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:"block"});
  const page=await context.newPage(),errors=[];
  await page.route("**/weather/critical.json*",route=>route.fulfill({status:200,contentType:"application/json",body:liveCritical}));
  await page.route("**/weather/jotrip-forecast.json*",route=>route.fulfill({status:200,contentType:"application/json",body:liveForecast}));
  await page.route("**/weather/tide.json*",route=>route.fulfill({status:200,contentType:"application/json",body:liveTide}));
  await page.route("**/data/weather-aqi/latest.json*",route=>route.fulfill({status:200,contentType:"application/json",body:liveAQI}));
  await page.route("**/data/weather-nowcast/latest.json*",route=>route.fulfill({status:200,contentType:"application/json",body:liveNowcast}));
  page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{
    if(m.type()!=="error")return;
    const t=m.text();
    if(/Permissions policy violation: Geolocation access has been blocked/i.test(t))return;
    if(/Failed to load resource.*commons.wikimedia.org/i.test(t))return;
    errors.push(t);
  });

  await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
  await page.waitForSelector(".weather-scene-hero",{timeout:10000});
  await page.waitForSelector("#pointTabs button",{timeout:10000});
  await page.waitForSelector("#actualStrip .actual-card",{timeout:10000});
  await page.waitForSelector("#aqiQuick .quick-item",{timeout:10000});
  await page.waitForSelector("#tideQuick .quick-item",{timeout:10000});
  await page.waitForSelector("#forecastRegionTabs button",{timeout:10000});
  await page.waitForSelector("#forecastDayRibbon .forecast-day",{timeout:10000});
  await page.waitForTimeout(500);

  const checks=await page.evaluate(()=>{
    const W=document.documentElement.clientWidth;
    const rect=s=>document.querySelector(s)?.getBoundingClientRect();
    const txt=s=>document.querySelector(s)?.textContent?.trim()||"";
    return {
      overflow:document.documentElement.scrollWidth-W,
      heroInside:!!rect(".weather-scene-hero")&&rect(".weather-scene-hero").left>=-1&&rect(".weather-scene-hero").right<=W+1,
      heroImage:!!document.querySelector(".weather-scene-hero img"),
      place:txt("#placeName"),
      temp:txt("#heroTemp"),
      statusInside:!!rect(".status-strip")&&rect(".status-strip").left>=-1&&rect(".status-strip").right<=W+1,
      pointTabs:document.querySelectorAll("#pointTabs button").length,
      metrics:document.querySelectorAll(".now-grid .metric-card").length,
      actualCards:document.querySelectorAll("#actualStrip .actual-card").length,
      aqiItems:document.querySelectorAll("#aqiQuick .quick-item").length,
      tideItems:document.querySelectorAll("#tideQuick .quick-item").length,
      tideSpark:!!document.querySelector("#tideSpark"),
      feedback:document.querySelectorAll("[data-feedback]").length,
      command:!!document.querySelector(".command-center"),
      mapBox:!!document.querySelector("#mapBox"),
      hazards:document.querySelectorAll("#hazardBoard article").length,
      regions:document.querySelectorAll("#forecastRegionTabs button").length,
      days:document.querySelectorAll("#forecastDayRibbon .forecast-day").length,
      forecastRows:document.querySelectorAll("#jotripForecastRows tr").length,
      historyLink:!!document.querySelector('a[href="/weather-history.html"]'),
      fatal:/Không tải được dữ liệu ban đầu/i.test(document.body.innerText)
    };
  });

  await page.screenshot({path:`artifacts/weather-ui-${name}.png`,fullPage:true});
  const ok=checks.overflow<=2&&checks.heroInside&&checks.heroImage&&checks.place&&checks.temp&&checks.statusInside&&
    checks.pointTabs>=8&&checks.metrics===8&&checks.actualCards>=1&&checks.aqiItems>=4&&checks.tideItems>=4&&
    checks.tideSpark&&checks.feedback===6&&checks.command&&checks.mapBox&&checks.hazards===4&&
    checks.regions===4&&checks.days>=7&&checks.forecastRows>=1&&checks.historyLink&&!checks.fatal&&errors.length===0;
  console.log(name,JSON.stringify(checks),errors);
  if(!ok)failed=true;
  await page.close();
  await context.close();
}

const catalog={dates:[{date:'2026-09-16',sample_count:12,material_event_count:5,first_sampled_time:'2026-09-16T00:20:00Z',last_sampled_time:'2026-09-16T05:20:00Z',peak_levels:{an_thoi:'HIGH',duong_dong:'HIGH',ganh_dau:'ELEVATED',rach_gia:'WATCH'},max_scores:{an_thoi:80,duong_dong:90,ganh_dau:65,rach_gia:45}}]};
const pointSummary={sample_count:12,avg_score:62,max_score:80,peak_level:'HIGH',min_cold_cloud_top_temp_c:-72,max_high_cloud_top_height_m:15100,min_cooling_c_per_20m_proxy:-6};
const daily={points:{an_thoi:pointSummary,duong_dong:{...pointSummary,avg_score:70,max_score:90},ganh_dau:{...pointSummary,avg_score:55,max_score:65,peak_level:'ELEVATED'},rach_gia:{...pointSummary,avg_score:38,max_score:45,peak_level:'WATCH'}}};
const events=[{at:'2026-09-16T05:20:00Z',sampled_time:'2026-09-16T05:20:00Z',type:'CHANGED',point:'an_thoi',changes:{score:{from:65,to:80},level:{from:'ELEVATED',to:'HIGH'}},current:{score:80,level:'HIGH'},source:'JMA_HIMAWARI9_VIA_NOAA_OPEN_DATA'}];

for(const [name,width,height] of [["history390",390,844],["historyDesktop",1440,1100]]){
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:"block"});
  const page=await context.newPage(),errors=[];
  page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{if(m.type()!=="error")return;const t=m.text();if(/Permissions policy violation: Geolocation access has been blocked/i.test(t))return;errors.push(t)});
  await page.route('https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-weather/data/weather-nowcast/**',async route=>{
    const u=route.request().url();
    if(u.includes('/catalog.json'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(catalog)});
    if(u.includes('/summary/2026-09-16.json'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(daily)});
    if(u.includes('/history/2026-09-16/events.jsonl'))return route.fulfill({status:200,contentType:'text/plain',body:events.map(x=>JSON.stringify(x)).join('\n')+'\n'});
    return route.fulfill({status:404,body:'not found'});
  });
  await page.goto(historyBase,{waitUntil:"domcontentloaded",timeout:30000});
  await page.waitForTimeout(1500);
  await page.waitForSelector(".archive-row",{timeout:10000});
  await page.waitForSelector(".compare-card",{timeout:10000});
  await page.waitForSelector(".event",{timeout:10000});
  const checks=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
    archiveRows:document.querySelectorAll('.archive-row').length,
    compareCards:document.querySelectorAll('.compare-card').length,
    events:document.querySelectorAll('.event').length,
    search:!!document.querySelector('#historySearch'),
    dateA:!!document.querySelector('#dateA'),
    dateB:!!document.querySelector('#dateB'),
    point:!!document.querySelector('#comparePoint'),
    dataError:document.querySelector('#archiveHealth')?.classList.contains('bad')
  }));
  await page.screenshot({path:`artifacts/weather-ui-${name}.png`,fullPage:true});
  const ok=checks.overflow<=2&&checks.archiveRows>=1&&checks.compareCards===6&&checks.events>=1&&checks.search&&checks.dateA&&checks.dateB&&checks.point&&!checks.dataError&&errors.length===0;
  console.log(name,JSON.stringify(checks),errors);
  if(!ok)failed=true;
  await page.close();
  await context.close();
}

await browser.close();
if(failed)process.exit(1);
