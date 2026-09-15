import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const root = path.join(repoRoot, 'data', 'sunairport');
const workPath = path.join(root, '_working', 'raw.json');
const latestPath = path.join(root, 'latest.json');
const healthPath = path.join(root, 'health.json');
const clean = (s='') => String(s).replace(/\s+/g, ' ').trim();
const flightRe = /^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$/i;
const timeRe = /^\d{1,2}:\d{2}$/;

const domesticStations = new Set([
  'HO CHI MINH','HA NOI','DA NANG','HAI PHONG','CAN THO','CAM RANH',
  'VINH','HUE','THANH HOA','BUON MA THUOT','DA LAT','QUY NHON',
  'PLEIKU','DONG HOI','DIEN BIEN'
]);

const raw = JSON.parse(await fs.readFile(workPath, 'utf8'));
const allRaw = [...(raw.arrivals_raw || []), ...(raw.departures_raw || [])];

function physicalKey(r) {
  const t = r.times?.[r.times.length - 1] || r.times?.[0] || '';
  return `${r.direction}|${t}|${r.context}`;
}

const groups = new Map();
for (const r of allRaw) {
  const key = physicalKey(r);
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push(r);
}

function extractStation(context, flightNumbers) {
  const parts = String(context || '').split('|').map(clean).filter(Boolean);
  let start = 0;
  for (let i = 0; i < parts.length; i++) {
    if (flightNumbers.some(f => parts[i].toUpperCase().includes(f))) start = Math.max(start, i + 1);
  }
  for (let i = start; i < Math.min(parts.length, start + 5); i++) {
    const c = clean(parts[i]);
    if (!c || flightRe.test(c) || timeRe.test(c)) continue;
    if (/^(ĐÚNG GIỜ|TRỄ|HỦY|HOÃN|ĐÃ HẠ CÁNH|ĐÃ CẤT CÁNH|ĐANG LÀM THỦ TỤC|QUẦY THỦ TỤC ĐÃ ĐÓNG|LÀM THỦ TỤC LÚC|BÃI ĐỖ)$/i.test(c)) continue;
    return c;
  }
  return '';
}

function extractStatus(context) {
  const u = String(context || '').toUpperCase();
  const known = [
    'ĐÃ HẠ CÁNH','ĐÃ CẤT CÁNH','ĐÚNG GIỜ','TRỄ','HỦY','HOÃN',
    'ĐANG LÀM THỦ TỤC','QUẦY THỦ TỤC ĐÃ ĐÓNG','LÀM THỦ TỤC LÚC',
    'BÃI ĐỖ','BOARDING','DELAYED','CANCELLED','RESCHEDULED'
  ];
  return known.find(x => u.includes(x)) || '';
}

const records = [...groups.values()].map(group => {
  const first = group[0];
  const flightNumbers = [...new Set(group.map(r => String(r.flight_number || '').toUpperCase()).filter(Boolean))];
  const station = extractStation(first.context, flightNumbers);
  return {
    direction: first.direction,
    operating_flight_number: flightNumbers[0] || '',
    marketing_flight_numbers: flightNumbers.slice(1),
    times: first.times || [],
    station,
    market: station ? (domesticStations.has(station.toUpperCase()) ? 'domestic' : 'international') : 'unknown',
    status: extractStatus(first.context),
    context: first.context
  };
});

const arrivals = records.filter(r => r.direction === 'arrival');
const departures = records.filter(r => r.direction === 'departure');
const countBy = (items, fn) => {
  const out = {};
  for (const x of items) {
    const k = fn(x);
    if (!k) continue;
    out[k] = (out[k] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(out).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0])));
};
const bank = items => countBy(items, r => {
  const t = r.times?.[r.times.length - 1] || r.times?.[0] || '';
  const h = Number(t.slice(0,2));
  if (!Number.isInteger(h)) return '';
  if (h < 6) return '00:00-05:59';
  if (h < 9) return '06:00-08:59';
  if (h < 12) return '09:00-11:59';
  if (h < 15) return '12:00-14:59';
  if (h < 18) return '15:00-17:59';
  if (h < 21) return '18:00-20:59';
  return '21:00-23:59';
});
const marketCounts = items => ({
  domestic: items.filter(r => r.market === 'domestic').length,
  international: items.filter(r => r.market === 'international').length,
  unknown: items.filter(r => r.market === 'unknown').length
});

const usable = arrivals.length >= 5 && departures.length >= 5;
let state = 'QA_FAILED';
if (usable && raw.board_date && raw.board_date === raw.collected_day_vn) state = 'REPORT_READY';
else if (usable && raw.board_date && raw.board_date !== raw.collected_day_vn) state = 'WAITING_FOR_D0';
else if (usable && !raw.board_date) state = 'QA_FAILED';

const output = {
  schema_version: '2.1',
  parser_version: 'sunairport-physical-v2.1',
  normalization_version: 'codeshare-row-v2.1',
  report_state: state,
  collected_at_vn: raw.collected_at_vn,
  source_date: raw.board_date,
  source: raw.source,
  page_last_updated: raw.page_last_updated,
  counts: { arrivals: arrivals.length, departures: departures.length, total: records.length },
  summary: {
    arrivals_market: marketCounts(arrivals),
    departures_market: marketCounts(departures),
    arrivals_by_station: countBy(arrivals, r => r.station),
    departures_by_station: countBy(departures, r => r.station),
    arrivals_by_status: countBy(arrivals, r => r.status),
    departures_by_status: countBy(departures, r => r.status),
    arrivals_by_time_bank: bank(arrivals),
    departures_by_time_bank: bank(departures)
  },
  quality: {
    usable,
    board_date_matches_collection_date: raw.board_date === raw.collected_day_vn,
    physical_movement_dedup: true,
    codeshare_method: 'same rendered row + direction + scheduled time'
  },
  records
};

await fs.mkdir(root, { recursive: true });
const hhmm = raw.collected_hhmm_vn || raw.collected_at_vn?.slice(11,16).replace(':','') || 'unknown';
if (state === 'REPORT_READY') {
  const dayDir = path.join(root, raw.board_date);
  await fs.mkdir(dayDir, { recursive: true });
  const json = JSON.stringify(output, null, 2) + '\n';
  await fs.writeFile(path.join(dayDir, `${hhmm}.json`), json);
  await fs.writeFile(latestPath, json);
} else {
  const candidateDir = path.join(root, 'candidate', raw.collected_day_vn || 'unknown');
  await fs.mkdir(candidateDir, { recursive: true });
  await fs.writeFile(path.join(candidateDir, `${hhmm}.json`), JSON.stringify(output, null, 2) + '\n');
}

let previousLatest = null;
try { previousLatest = JSON.parse(await fs.readFile(latestPath, 'utf8')); } catch {}
const health = {
  module: 'Sun Airport flights',
  state,
  scheduler_triggered: true,
  job_started: true,
  collector_completed: true,
  parser_passed: true,
  normalization_passed: true,
  qa_passed: state === 'REPORT_READY',
  commit_succeeded: null,
  collected_at_vn: raw.collected_at_vn,
  source_date: raw.board_date,
  retry_count: Number(process.env.SUNAIRPORT_RETRY_COUNT || 0),
  last_successful_run: state === 'REPORT_READY' ? raw.collected_at_vn : previousLatest?.collected_at_vn || null,
  fallback_used: false,
  run_id: process.env.GITHUB_RUN_ID || null,
  evidence_class: 'DIRECT'
};
await fs.writeFile(healthPath, JSON.stringify(health, null, 2) + '\n');
console.log(JSON.stringify({ state, counts: output.counts, source_date: raw.board_date }));
