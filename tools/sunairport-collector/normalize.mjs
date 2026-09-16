import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const root = path.join(repoRoot, 'data', 'sunairport');
const apiRawPath = path.join(root, '_working', 'api-raw.json');
const latestPath = path.join(root, 'latest.json');
const healthPath = path.join(root, 'health.json');
const clean = (s='') => String(s ?? '').replace(/\s+/g, ' ').trim();

const domesticStations = new Set([
  'HO CHI MINH','HA NOI','DA NANG','HAI PHONG','CAN THO','CAM RANH',
  'VINH','HUE','THANH HOA','BUON MA THUOT','DA LAT','QUY NHON',
  'PLEIKU','DONG HOI','DIEN BIEN'
]);

const trackedRawFields = [
  'flightNo','airline','airlineName','flightDate','route','cityName','country','arrDep',
  'status','acType','aircraft','scheduledTime','estimatedTime','actualTime',
  'boardingStart','boardingFinish','codeShare','parkingBay','terminal','ckRow','belt','gate',
  'remarks','synced_at','notesVn','notesEn'
];

function hhmm(value) {
  const m = clean(value).match(/^(\d{2})(\d{2})/);
  if (!m) return null;
  const h = Number(m[1]), min = Number(m[2]);
  return h <= 23 && min <= 59 ? `${m[1]}:${m[2]}` : null;
}

function timeMinutes(t) {
  const m = String(t || '').match(/^(\d{1,2}):(\d{2})$/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

function signedDiffMinutes(from, to) {
  const a = timeMinutes(from), b = timeMinutes(to);
  if (a == null || b == null) return null;
  let d = b - a;
  if (d > 720) d -= 1440;
  if (d < -720) d += 1440;
  return d;
}

function flightNos(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value ?? '');
  const hits = String(text).toUpperCase().match(/\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/g) || [];
  return [...new Set(hits.map(x => x.replace(/\s+/g, '')).filter(x => /[A-Z]/.test(x.slice(0,3))))];
}

function rawStatus(item) {
  return clean(item.notesVn || item.notesEn || item.status || item.remarks || '');
}

function checkinTime(text) {
  const m = String(text || '').match(/LÀM THỦ TỤC LÚC\s*(\d{1,2}:\d{2})/i);
  return m ? m[1].padStart(5, '0') : null;
}

function normalizedStatus(item, scheduled, estimated) {
  const raw = rawStatus(item);
  const u = raw.toUpperCase();
  if (/QUẦY THỦ TỤC ĐÃ ĐÓNG/.test(u)) return { status: 'QUẦY THỦ TỤC ĐÃ ĐÓNG', code: 'CHECKIN_CLOSED' };
  if (/ĐANG LÀM THỦ TỤC/.test(u)) return { status: 'ĐANG LÀM THỦ TỤC', code: 'CHECKIN_OPEN' };
  if (/LÀM THỦ TỤC LÚC/.test(u)) return { status: 'LÀM THỦ TỤC LÚC', code: 'CHECKIN_SCHEDULED' };
  if (/ĐÃ HẠ CÁNH|ARRIVED/.test(u)) return { status: 'ĐÃ HẠ CÁNH', code: 'ARRIVED' };
  if (/ĐÃ CẤT CÁNH|DEPARTED/.test(u)) return { status: 'ĐÃ CẤT CÁNH', code: 'DEPARTED' };
  if (/HỦY|CANCELLED|CANCELED/.test(u)) return { status: 'HỦY', code: 'CANCELLED' };
  if (/HOÃN/.test(u)) return { status: 'HOÃN', code: 'POSTPONED' };
  if (/TRỄ|DELAYED/.test(u)) return { status: 'TRỄ', code: 'DELAYED' };
  if (/ĐỔI GIỜ|RESCHEDULED/.test(u)) return { status: 'TRỄ', code: 'RESCHEDULED' };
  if (/BOARDING/.test(u)) return { status: 'BOARDING', code: 'BOARDING' };
  if (/BÃI ĐỖ/.test(u)) return { status: 'BÃI ĐỖ', code: 'ON_BLOCK' };
  if (/ĐÚNG GIỜ|ON TIME/.test(u)) return { status: 'ĐÚNG GIỜ', code: 'ON_TIME' };
  if (scheduled && estimated && scheduled !== estimated) return { status: 'TRỄ', code: 'RESCHEDULED' };
  return { status: raw || '', code: raw ? 'SOURCE_OTHER' : 'UNKNOWN' };
}

function marketFor(item) {
  const country = clean(item.country).toUpperCase();
  if (country) return country === 'VN' ? 'domestic' : 'international';
  const station = clean(item.cityName).toUpperCase();
  return station ? (domesticStations.has(station) ? 'domestic' : 'international') : 'unknown';
}

function normalizeItem(item, direction) {
  const scheduled = hhmm(item.scheduledTime);
  const estimatedRaw = hhmm(item.estimatedTime);
  const estimated = estimatedRaw && estimatedRaw !== scheduled ? estimatedRaw : null;
  const actual = hhmm(item.actualTime);
  const st = normalizedStatus(item, scheduled, estimatedRaw);
  const flight = clean(item.flightNo).toUpperCase();
  const aliases = flightNos(item.codeShare).filter(x => x !== flight);
  const sourceStatus = rawStatus(item);
  const station = clean(item.cityName);
  const estimatedDelay = estimated ? signedDiffMinutes(scheduled, estimated) : null;
  const actualDelay = actual ? signedDiffMinutes(scheduled, actual) : null;

  return {
    source_id: item.id ?? null,
    direction,
    operating_flight_number: flight,
    marketing_flight_numbers: aliases,
    station,
    country: clean(item.country) || null,
    route: clean(item.route) || null,
    market: marketFor(item),
    airline_code: clean(item.airline) || null,
    airline_name: clean(item.airlineName) || null,
    aircraft_type: clean(item.acType) || null,
    aircraft: clean(item.aircraft) || null,
    scheduled_time: scheduled,
    estimated_time: estimated,
    actual_time: actual,
    delay_minutes: estimatedDelay != null && estimatedDelay > 0 ? estimatedDelay : null,
    estimated_delay_minutes: estimatedDelay,
    actual_delay_minutes: actualDelay,
    checkin_time: checkinTime(sourceStatus),
    boarding_start: hhmm(item.boardingStart),
    boarding_finish: hhmm(item.boardingFinish),
    gate: clean(item.gate) || null,
    belt: clean(item.belt) || null,
    parking_bay: clean(item.parkingBay) || null,
    terminal: clean(item.terminal) || null,
    checkin_row: clean(item.ckRow) || null,
    status: st.status,
    status_code: st.code,
    raw_status: sourceStatus,
    source_synced_at: clean(item.synced_at) || null,
    timing_source: 'SUN_AIRPORT_OFFICIAL_API'
  };
}

function countBy(items, fn) {
  const out = {};
  for (const x of items) {
    const k = fn(x);
    if (!k) continue;
    out[k] = (out[k] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(out).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0])));
}

function bank(items) {
  return countBy(items, r => {
    const t = r.estimated_time || r.scheduled_time || '';
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

function marketCounts(items) {
  return {
    domestic: items.filter(r => r.market === 'domestic').length,
    international: items.filter(r => r.market === 'international').length,
    unknown: items.filter(r => r.market === 'unknown').length
  };
}

function rawKey(direction, row) {
  if (row?.id != null) return `${direction}|id:${row.id}`;
  return `${direction}|${clean(row?.flightNo).toUpperCase()}|${clean(row?.scheduledTime)}|${clean(row?.cityName).toUpperCase()}`;
}

function compactRaw(row) {
  const out = {};
  for (const field of trackedRawFields) out[field] = row?.[field] ?? null;
  return out;
}

function rawDiff(previous, current) {
  const changes = {};
  for (const field of trackedRawFields) {
    const a = previous?.[field] ?? null;
    const b = current?.[field] ?? null;
    if (JSON.stringify(a) !== JSON.stringify(b)) changes[field] = { from: a, to: b };
  }
  return changes;
}

async function readJson(file) {
  try { return JSON.parse(await fs.readFile(file, 'utf8')); } catch { return null; }
}

const apiRaw = JSON.parse(await fs.readFile(apiRawPath, 'utf8'));
const arrivals = (apiRaw.arrivals || []).map(x => normalizeItem(x, 'arrival'));
const departures = (apiRaw.departures || []).map(x => normalizeItem(x, 'departure'));
const records = [...arrivals, ...departures];

const usable = arrivals.length >= 5 && departures.length >= 5;
const state = usable && apiRaw.board_date === apiRaw.collected_day_vn ? 'REPORT_READY' : 'QA_FAILED';

const output = {
  schema_version: '3.0',
  parser_version: 'sunairport-api-v3.0',
  normalization_version: 'jotrip-airport-v3.0',
  report_state: state,
  collected_at_vn: apiRaw.collected_at_vn,
  source_date: apiRaw.board_date,
  source: apiRaw.source,
  page_last_updated: `Official API fetched ${apiRaw.collected_at_vn?.slice(11,16) || ''}`,
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
    board_date_matches_collection_date: apiRaw.board_date === apiRaw.collected_day_vn,
    source_mode: 'OFFICIAL_JSON_API',
    archive_mode: 'DAILY_RAW_PLUS_CHANGE_EVENTS',
    full_snapshot_history: false
  },
  records
};

await fs.mkdir(root, { recursive: true });
let previousLatest = await readJson(latestPath);

if (state === 'REPORT_READY') {
  const rawDir = path.join(root, 'raw');
  const historyDir = path.join(root, 'history', apiRaw.board_date);
  const rawDayPath = path.join(rawDir, `${apiRaw.board_date}.json`);
  const eventsPath = path.join(historyDir, 'events.jsonl');

  await fs.mkdir(rawDir, { recursive: true });
  await fs.mkdir(historyDir, { recursive: true });

  const previousRaw = await readJson(rawDayPath);
  const previousMap = new Map();
  for (const row of previousRaw?.arrivals || []) previousMap.set(rawKey('arrival', row), row);
  for (const row of previousRaw?.departures || []) previousMap.set(rawKey('departure', row), row);

  const events = [];
  const processRows = (direction, rows) => {
    for (const row of rows) {
      const key = rawKey(direction, row);
      const before = previousMap.get(key);
      if (!before) {
        events.push({
          at: apiRaw.collected_at_vn,
          type: 'FIRST_SEEN',
          key,
          direction,
          flight_number: clean(row.flightNo).toUpperCase(),
          current: compactRaw(row)
        });
        continue;
      }
      const changes = rawDiff(before, row);
      if (Object.keys(changes).length) {
        events.push({
          at: apiRaw.collected_at_vn,
          type: 'CHANGED',
          key,
          direction,
          flight_number: clean(row.flightNo).toUpperCase(),
          changes,
          current: compactRaw(row)
        });
      }
    }
  };

  processRows('arrival', apiRaw.arrivals || []);
  processRows('departure', apiRaw.departures || []);

  if (events.length) {
    await fs.appendFile(eventsPath, events.map(x => JSON.stringify(x)).join('\n') + '\n');
  }

  const dailyRaw = {
    schema_version: '1.0-daily-raw',
    date: apiRaw.board_date,
    collected_at_vn: apiRaw.collected_at_vn,
    source: apiRaw.source,
    arrivals: apiRaw.arrivals || [],
    departures: apiRaw.departures || []
  };

  await fs.writeFile(rawDayPath, JSON.stringify(dailyRaw, null, 2) + '\n');
  await fs.writeFile(latestPath, JSON.stringify(output, null, 2) + '\n');

  // Keep only compact persistent products. The exact current source rows now live
  // in raw/YYYY-MM-DD.json, so the working copy is unnecessary after QA.
  await fs.rm(apiRawPath, { force: true });
  await fs.rm(path.join(root, '_working', 'raw.json'), { force: true });

  console.log(JSON.stringify({
    state,
    counts: output.counts,
    source_date: apiRaw.board_date,
    history_events_written: events.length,
    archive: `raw/${apiRaw.board_date}.json`
  }));
} else {
  const candidateDir = path.join(root, 'candidate', apiRaw.collected_day_vn || 'unknown');
  await fs.mkdir(candidateDir, { recursive: true });
  await fs.writeFile(
    path.join(candidateDir, 'latest.json'),
    JSON.stringify(output, null, 2) + '\n'
  );
}

const health = {
  module: 'JoTrip AutoSync - Sun Airport flights',
  state,
  scheduler_triggered: true,
  job_started: true,
  collector_completed: true,
  parser_passed: true,
  normalization_passed: true,
  qa_passed: state === 'REPORT_READY',
  commit_succeeded: null,
  collected_at_vn: apiRaw.collected_at_vn,
  source_date: apiRaw.board_date,
  retry_count: Number(process.env.SUNAIRPORT_RETRY_COUNT || 0),
  last_successful_run: state === 'REPORT_READY' ? apiRaw.collected_at_vn : previousLatest?.collected_at_vn || null,
  fallback_used: false,
  run_id: process.env.GITHUB_RUN_ID || null,
  evidence_class: 'DIRECT',
  source_mode: 'OFFICIAL_JSON_API',
  archive_mode: 'DAILY_RAW_PLUS_CHANGE_EVENTS'
};
await fs.writeFile(healthPath, JSON.stringify(health, null, 2) + '\n');
