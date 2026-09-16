import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const url = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const tz = 'Asia/Ho_Chi_Minh';
const repoRoot = path.resolve(process.cwd(), '../..');
const workDir = path.join(repoRoot, 'data', 'sunairport', '_working');
const diagDir = path.join(repoRoot, 'artifacts', 'sunairport');
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

function parseBoardDate(text='') {
  const m = text.match(/\b(\d{1,2})\s*(?:thg|tháng)\s*(\d{1,2})\s*,?\s*(\d{4})\b/i);
  if (!m) return null;
  const dd = String(Number(m[1])).padStart(2, '0');
  const mm = String(Number(m[2])).padStart(2, '0');
  return `${m[3]}-${mm}-${dd}`;
}

function flightNo(token) {
  const x = token.replace(/\s+/g, '').toUpperCase();
  if (!/^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$/.test(x)) return null;
  const prefix = x.match(/^[A-Z0-9]{2,3}/)?.[0] || '';
  return /[A-Z]/.test(prefix) ? x : null;
}

function flightHits(line='') {
  const hits = String(line).toUpperCase().match(/\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/g) || [];
  return [...new Set(hits.map(flightNo).filter(Boolean))];
}

function parseText(text, direction) {
  const lines = text.split(/\n+/).map(clean).filter(Boolean);
  const flightLineIndexes = [];
  for (let i = 0; i < lines.length; i++) {
    if (flightHits(lines[i]).length) flightLineIndexes.push(i);
  }

  const records = [];
  for (let n = 0; n < flightLineIndexes.length; n++) {
    const i = flightLineIndexes[n];
    const next = flightLineIndexes[n + 1] ?? lines.length;
    let rowLines = lines.slice(i, next);

    // Sun Airport renders the next row ordinal immediately before the next flight line.
    // Drop that ordinal so status/time extraction belongs only to this physical flight row.
    if (rowLines.length > 1 && /^\d{1,3}$/.test(rowLines[rowLines.length - 1])) rowLines = rowLines.slice(0, -1);

    const numbers = flightHits(lines[i]);
    const context = clean(rowLines.join(' | '));
    const times = [...new Set(rowLines.flatMap(line => line.match(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g) || []))];
    for (const number of numbers) records.push({ direction, flight_number: number, times, context });
  }
  return records;
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
let page;
try {
  await fs.mkdir(workDir, { recursive: true });
  await fs.mkdir(diagDir, { recursive: true });
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ locale: 'vi-VN', timezoneId: tz });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);

  const bodyText = await page.locator('body').innerText();
  const boardDate = parseBoardDate(bodyText);
  const arrivalText = await boardText(page, 'Bay đến');
  const departureText = await boardText(page, 'Bay đi');

  const raw = {
    schema_version: '2.2-raw',
    collected_at_vn: s.iso,
    collected_day_vn: s.day,
    collected_hhmm_vn: s.hhmm,
    board_date: boardDate,
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url,
      acquisition: 'Playwright on GitHub Actions',
      paid_services_used: false
    },
    page_last_updated: clean(arrivalText.match(/Lần cuối cập nhật[^\n]*/i)?.[0] || ''),
    arrivals_raw: parseText(arrivalText, 'arrival'),
    departures_raw: parseText(departureText, 'departure')
  };

  await fs.writeFile(path.join(workDir, 'raw.json'), JSON.stringify(raw, null, 2) + '\n');
  console.log(JSON.stringify({ board_date: boardDate, arrivals_raw: raw.arrivals_raw.length, departures_raw: raw.departures_raw.length }));
} catch (error) {
  const errorInfo = {
    collected_at_vn: s.iso,
    stage: 'COLLECT',
    name: error?.name || 'Error',
    message: error?.message || String(error)
  };
  await fs.mkdir(diagDir, { recursive: true });
  await fs.writeFile(path.join(diagDir, 'error.json'), JSON.stringify(errorInfo, null, 2) + '\n');
  if (page) {
    try { await page.screenshot({ path: path.join(diagDir, 'page.png'), fullPage: true }); } catch {}
    try { await fs.writeFile(path.join(diagDir, 'page.html'), await page.content()); } catch {}
  }
  throw error;
} finally {
  if (browser) await browser.close();
}
