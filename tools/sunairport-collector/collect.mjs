import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  buildSummary,
  detectRollover,
  normalizeRecords,
  runQualityChecks
} from './normalize.mjs';

const url = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const tz = 'Asia/Ho_Chi_Minh';
const repoRoot = path.resolve(process.cwd(), '../..');
const outRoot = path.join(repoRoot, 'data', 'sunairport');
const artifactRoot = path.join(repoRoot, '.artifacts', 'sunairport');
const clean = (value = '') => String(value).replace(/\s+/g, ' ').trim();

const knownStatuses = [
  'ĐÃ HẠ CÁNH', 'ĐÃ CẤT CÁNH', 'ĐÚNG GIỜ', 'TRỄ', 'HỦY', 'HOÃN',
  'ĐANG LÀM THỦ TỤC', 'QUẦY THỦ TỤC ĐÃ ĐÓNG', 'LÀM THỦ TỤC LÚC',
  'BÃI ĐỖ', 'BOARDING', 'DELAYED', 'CANCELLED', 'RESCHEDULED'
];

function stampVN() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return {
    day: `${values.year}-${values.month}-${values.day}`,
    hhmm: `${values.hour}${values.minute}`,
    iso: `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}:${values.second}+07:00`
  };
}

function flightNo(token) {
  const value = token.replace(/\s+/g, '').toUpperCase();
  if (!/^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$/.test(value)) return null;
  const prefix = value.match(/^[A-Z0-9]{2,3}/)?.[0] || '';
  return /[A-Z]/.test(prefix) ? value : null;
}

function parseText(text, direction) {
  const lines = text.split(/\n+/).map(clean).filter(Boolean);
  const records = [];
  for (let index = 0; index < lines.length; index += 1) {
    const hits = lines[index].toUpperCase().match(/\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/g) || [];
    for (const hit of hits) {
      const number = flightNo(hit);
      if (!number) continue;
      const context = clean(lines.slice(Math.max(0, index - 3), Math.min(lines.length, index + 5)).join(' | '));
      const times = [...new Set(context.match(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g) || [])];
      const upperContext = context.toUpperCase();
      const status = knownStatuses.find(candidate => upperContext.includes(candidate)) || '';
      records.push({ direction, flight_number: number, times, context, status });
    }
  }
  const unique = new Map();
  for (const record of records) {
    const key = `${record.direction}|${record.flight_number}|${record.times[0] || ''}|${record.context}`;
    if (!unique.has(key)) unique.set(key, record);
  }
  return [...unique.values()];
}

async function selectBoard(page, label) {
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
        return;
      }
    } catch {}
  }
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    return null;
  }
}

async function writeJson(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

const stamp = stampVN();
await fs.mkdir(outRoot, { recursive: true });
await fs.mkdir(artifactRoot, { recursive: true });

const healthPath = path.join(outRoot, 'health.json');
const artifactHealthPath = path.join(artifactRoot, 'health.json');
const latestPath = path.join(outRoot, 'latest.json');
const previousSnapshot = await readJson(latestPath);
const previousHealth = await readJson(healthPath);
const startedAt = new Date().toISOString();
const health = {
  health_schema_version: '1.0',
  source: 'sunairport',
  source_date: stamp.day,
  state: 'STARTED',
  requested_at: startedAt,
  started_at: startedAt,
  completed_at: null,
  source_last_updated: null,
  scheduler_triggered: true,
  job_started: true,
  collector_completed: false,
  parser_passed: false,
  normalization_passed: false,
  qa_passed: false,
  commit_succeeded: null,
  records_parsed: 0,
  retry_number: Number(process.env.GITHUB_RUN_ATTEMPT || 1),
  workflow_run_id: process.env.GITHUB_RUN_ID || null,
  fallback_used: false,
  final_evidence_status: 'NOT_READY',
  last_successful_run: previousHealth?.state === 'REPORT_READY'
    ? previousHealth.completed_at
    : previousHealth?.last_successful_run || previousSnapshot?.collected_at_vn || null,
  schema_version: '2.0',
  parser_version: '2.0.0',
  normalization_version: '2.0.0',
  configuration_version: '2.0.0',
  errors: [],
  warnings: []
};

async function persistHealth() {
  health.completed_at = new Date().toISOString();
  await writeJson(healthPath, health);
  await writeJson(artifactHealthPath, health);
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ locale: 'vi-VN', timezoneId: tz });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);

  await selectBoard(page, 'Bay đến');
  const arrivalText = await page.locator('body').innerText();
  await fs.writeFile(path.join(artifactRoot, 'arrival.html'), await page.content());
  await fs.writeFile(path.join(artifactRoot, 'arrival.txt'), arrivalText);
  await page.screenshot({ path: path.join(artifactRoot, 'arrival.png'), fullPage: true });

  await selectBoard(page, 'Bay đi');
  const departureText = await page.locator('body').innerText();
  await fs.writeFile(path.join(artifactRoot, 'departure.html'), await page.content());
  await fs.writeFile(path.join(artifactRoot, 'departure.txt'), departureText);
  await page.screenshot({ path: path.join(artifactRoot, 'departure.png'), fullPage: true });

  health.collector_completed = true;
  const rawRecords = [
    ...parseText(arrivalText, 'arrival'),
    ...parseText(departureText, 'departure')
  ];
  health.parser_passed = rawRecords.length >= 10;
  health.records_parsed = rawRecords.length;
  await writeJson(path.join(artifactRoot, 'raw-records.json'), rawRecords);

  const records = normalizeRecords(rawRecords, stamp.day);
  health.normalization_passed = true;
  const qa = runQualityChecks(records);
  health.qa_passed = qa.passed;
  health.errors.push(...qa.errors);
  health.warnings.push(...qa.warnings);

  const rollover = detectRollover(records, previousSnapshot, stamp.day);
  const aggregates = buildSummary(records);
  const output = {
    schema_version: '2.0',
    parser_version: '2.0.0',
    normalization_version: '2.0.0',
    configuration_version: '2.0.0',
    source_date: stamp.day,
    collected_at_vn: stamp.iso,
    report_state: qa.passed && rollover.detected ? 'REPORT_READY' : 'NOT_READY',
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url,
      acquisition: 'Playwright on GitHub Actions',
      paid_services_used: false
    },
    source_last_updated: clean(arrivalText.match(/Lần cuối cập nhật[^\n]*/i)?.[0] || ''),
    rollover,
    normalization: {
      same_row_codeshares_collapsed: true,
      method: 'direction + operating carrier flight + scheduled time + station'
    },
    ...aggregates,
    quality: qa,
    records
  };
  health.source_last_updated = output.source_last_updated;
  await writeJson(path.join(artifactRoot, 'candidate.json'), output);

  if (!rollover.detected) {
    health.state = 'PAGE_NOT_ROLLED';
    health.final_evidence_status = 'NOT_YET_ROLLED_OVER';
    await persistHealth();
    console.log(JSON.stringify({ state: health.state, rollover, counts: aggregates.counts }));
  } else if (!qa.passed) {
    health.state = 'QA_FAILED';
    health.final_evidence_status = 'NOT_READY';
    await persistHealth();
    throw new Error(`Sun Airport QA failed: ${qa.errors.join(', ')}`);
  } else {
    health.state = 'REPORT_READY';
    health.final_evidence_status = 'DIRECT_NORMALIZED_QA_PASSED';
    health.last_successful_run = new Date().toISOString();
    const dayPath = path.join(outRoot, stamp.day, `${stamp.hhmm}.json`);
    await writeJson(dayPath, output);
    await writeJson(latestPath, output);
    await persistHealth();
    console.log(JSON.stringify({ state: health.state, counts: aggregates.counts, quality: qa }));
  }
} catch (error) {
  if (!['QA_FAILED', 'PAGE_NOT_ROLLED'].includes(health.state)) {
    health.state = health.collector_completed ? 'PARSE_OR_NORMALIZE_FAILED' : 'COLLECTOR_FAILED';
    health.final_evidence_status = 'NOT_READY';
    health.errors.push(error instanceof Error ? error.message : String(error));
    await persistHealth();
  }
  throw error;
} finally {
  if (browser) await browser.close();
}
