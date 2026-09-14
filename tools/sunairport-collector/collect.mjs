import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const url = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const tz = 'Asia/Ho_Chi_Minh';
const repoRoot = path.resolve(process.cwd(), '../..');
const outRoot = path.join(repoRoot, 'data', 'sunairport');

const clean = (s='') => String(s).replace(/\s+/g, ' ').trim();

const domesticStations = new Set([
  'HO CHI MINH', 'HA NOI', 'DA NANG', 'HAI PHONG', 'CAN THO', 'CAM RANH',
  'VINH', 'HUE', 'THANH HOA', 'BUON MA THUOT', 'DA LAT', 'QUY NHON',
  'PLEIKU', 'DONG HOI', 'DIEN BIEN'
]);

function stampVN() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(new Date());
  const m = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return {
    day: `${m.year}-${m.month}-${m.day}`,
    hhmm: `${m.hour}${m.minute}`,
    iso: `${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}:${m.second}+07:00`
  };
}

function flightNo(token) {
  const x = token.replace(/\s+/g, '').toUpperCase();
  if (!/^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$/.test(x)) return null;
  const prefix = x.match(/^[A-Z0-9]{2,3}/)?.[0] || '';
  return /[A-Z]/.test(prefix) ? x : null;
}

function parseText(text, direction) {
  const lines = text.split(/\n+/).map(clean).filter(Boolean);
  const records = [];
  for (let i = 0; i < lines.length; i++) {
    const hits = lines[i].toUpperCase().match(/\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/g) || [];
    for (const hit of hits) {
      const number = flightNo(hit);
      if (!number) continue;
      const context = clean(lines.slice(Math.max(0, i - 3), Math.min(lines.length, i + 5)).join(' | '));
      const times = [...new Set(context.match(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g) || [])];
      records.push({ direction, flight_number: number, times, context });
    }
  }
  const unique = new Map();
  for (const r of records) {
    const key = `${r.direction}|${r.flight_number}|${r.times[0] || ''}`;
    if (!unique.has(key)) unique.set(key, r);
  }
  return [...unique.values()];
}

function enrichRecord(record) {
  const parts = record.context.split('|').map(clean).filter(Boolean);
  const flightIndex = parts.findIndex(p => p.toUpperCase().includes(record.flight_number));
  const station = flightIndex >= 0 ? clean(parts[flightIndex + 1] || '') : '';
  const before = flightIndex >= 0 ? parts.slice(Math.max(0, flightIndex - 3), flightIndex).join(' | ').toUpperCase() : '';

  let status = '';
  const knownStatuses = [
    'ĐÃ HẠ CÁNH', 'ĐÃ CẤT CÁNH', 'ĐÚNG GIỜ', 'TRỄ', 'HỦY', 'HOÃN',
    'ĐANG LÀM THỦ TỤC', 'QUẦY THỦ TỤC ĐÃ ĐÓNG', 'LÀM THỦ TỤC LÚC',
    'BÃI ĐỖ', 'BOARDING', 'DELAYED', 'CANCELLED', 'RESCHEDULED'
  ];
  for (const candidate of knownStatuses) {
    if (before.includes(candidate)) {
      status = candidate;
      break;
    }
  }

  return {
    ...record,
    station,
    market: station ? (domesticStations.has(station.toUpperCase()) ? 'domestic' : 'international') : 'unknown',
    status
  };
}

function countBy(records, keyFn) {
  const out = {};
  for (const r of records) {
    const key = keyFn(r);
    if (!key) continue;
    out[key] = (out[key] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(out).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

function hourBank(records) {
  return countBy(records, r => {
    const t = r.times?.[r.times.length - 1] || r.times?.[0] || '';
    const h = Number(t.slice(0, 2));
    if (!Number.isInteger(h)) return '';
    if (h < 6) return '00:00-05:59';
    if (h < 9) return '06:00-08:59';
    if (h < 12) return '09:00-11:59';
    if (h < 15) return '12:00-14:59';
    if (h < 18) return '15:00-17:59';
    if (h < 21) return '18:00-20:59';
    return '21:00-23:59';
  });
}

async function boardText(page, label) {
  const candidates = [
    page.getByRole('button', { name: label, exact: true }),
    page.getByRole('tab', { name: label, exact: true }),
    page.getByText(label, { exact: true })
  ];
  for (const locator of candidates) {
    try {
      if (await locator.count()) {
        await locator.first().click({ timeout: 5000 });
        await page.waitForTimeout(2500);
        break;
      }
    } catch {}
  }
  return await page.locator('body').innerText();
}

const s = stampVN();
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ locale: 'vi-VN', timezoneId: tz });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);

  const arrivalText = await boardText(page, 'Bay đến');
  const departureText = await boardText(page, 'Bay đi');
  const arrivals = parseText(arrivalText, 'arrival').map(enrichRecord);
  const departures = parseText(departureText, 'departure').map(enrichRecord);
  const records = [...arrivals, ...departures];

  const marketCounts = records => ({
    domestic: records.filter(r => r.market === 'domestic').length,
    international: records.filter(r => r.market === 'international').length,
    unknown: records.filter(r => r.market === 'unknown').length
  });

  const output = {
    schema_version: '1.1',
    collected_at_vn: s.iso,
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url,
      acquisition: 'Playwright on GitHub Actions',
      paid_services_used: false
    },
    page_last_updated: clean(arrivalText.match(/Lần cuối cập nhật[^\n]*/i)?.[0] || ''),
    counts: {
      arrivals: arrivals.length,
      departures: departures.length,
      total: records.length
    },
    summary: {
      arrivals_market: marketCounts(arrivals),
      departures_market: marketCounts(departures),
      arrivals_by_station: countBy(arrivals, r => r.station),
      departures_by_station: countBy(departures, r => r.station),
      arrivals_by_status: countBy(arrivals, r => r.status),
      departures_by_status: countBy(departures, r => r.status),
      arrivals_by_time_bank: hourBank(arrivals),
      departures_by_time_bank: hourBank(departures)
    },
    quality: {
      usable: arrivals.length >= 5 && departures.length >= 5,
      note: arrivals.length >= 5 && departures.length >= 5
        ? 'Parsed from the rendered official flight board.'
        : 'Too few rows parsed - do not treat as a complete operational count.'
    },
    records
  };

  const dayDir = path.join(outRoot, s.day);
  await fs.mkdir(dayDir, { recursive: true });
  const json = JSON.stringify(output, null, 2) + '\n';
  await fs.writeFile(path.join(dayDir, `${s.hhmm}.json`), json);
  await fs.writeFile(path.join(outRoot, 'latest.json'), json);
  console.log(JSON.stringify({ counts: output.counts, summary: output.summary }));
} finally {
  if (browser) await browser.close();
}
