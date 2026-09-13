import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const url = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const tz = 'Asia/Ho_Chi_Minh';
const repoRoot = path.resolve(process.cwd(), '../..');
const outRoot = path.join(repoRoot, 'data', 'sunairport');

const clean = (s='') => String(s).replace(/\s+/g, ' ').trim();

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
  const arrivals = parseText(arrivalText, 'arrival');
  const departures = parseText(departureText, 'departure');
  const records = [...arrivals, ...departures];

  const output = {
    schema_version: '1.0',
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
  console.log(JSON.stringify(output.counts));
} finally {
  if (browser) await browser.close();
}
