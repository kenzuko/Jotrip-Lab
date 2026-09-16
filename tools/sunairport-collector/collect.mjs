import fs from 'node:fs/promises';
import path from 'node:path';

const API_ROOT = 'https://sunairport.com/phuquoc/cms/api/flights';
const SOURCE_URL = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
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
    hm: `${m.hour}:${m.minute}`,
    iso: `${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}:${m.second}+07:00`
  };
}

function hhmm(value) {
  const digits = clean(value).match(/^(\d{2})(\d{2})/);
  if (!digits) return null;
  const h = Number(digits[1]), m = Number(digits[2]);
  return h <= 23 && m <= 59 ? `${digits[1]}:${digits[2]}` : null;
}

function flightNos(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value ?? '');
  const hits = String(text).toUpperCase().match(/\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/g) || [];
  return [...new Set(hits.map(x => x.replace(/\s+/g, '')).filter(x => /[A-Z]/.test(x.slice(0,3))))];
}

function rowStatus(item, scheduled, estimated) {
  const direct = clean(item.notesVn || item.notesEn || item.status || item.remarks || '');
  if (direct) return direct;
  return estimated && scheduled && estimated !== scheduled ? 'ĐỔI GIỜ' : '';
}

function toRaw(item, direction) {
  const flight = clean(item.flightNo).toUpperCase();
  const scheduled = hhmm(item.scheduledTime);
  const estimated = hhmm(item.estimatedTime);
  const times = [...new Set([scheduled, estimated && estimated !== scheduled ? estimated : null].filter(Boolean))];
  const status = rowStatus(item, scheduled, estimated);
  const station = clean(item.cityName);
  const airline = clean(item.airlineName || item.airline);
  const meta = [clean(item.belt), clean(item.parkingBay), clean(item.gate)].filter(Boolean);
  const context = clean([
    `${flight} • ${airline}`,
    station,
    ...times,
    ...meta,
    status
  ].filter(Boolean).join(' | '));
  const aliases = flightNos(item.codeShare).filter(x => x !== flight);
  return [flight, ...aliases].filter(Boolean).map(number => ({
    direction,
    flight_number: number,
    times,
    context
  }));
}

async function fetchBoard(type, day) {
  const u = new URL(API_ROOT);
  u.searchParams.set('type', type);
  u.searchParams.set('date', day);
  u.searchParams.set('limit', '100');
  u.searchParams.set('_t', String(Date.now()));
  const response = await fetch(u, {
    headers: {
      'accept': 'application/json',
      'user-agent': 'JoTrip-Airport-Live/2.3 (+https://github.com/kenzuko/Jotrip-Lab)',
      'origin': 'https://kenzuko.github.io'
    },
    cache: 'no-store',
    signal: AbortSignal.timeout(20000)
  });
  if (!response.ok) throw new Error(`Sun Airport API ${type}: HTTP ${response.status}`);
  const body = await response.json();
  if (!body?.success || !Array.isArray(body?.data)) throw new Error(`Sun Airport API ${type}: invalid JSON shape`);
  return {
    url: u.toString(),
    data: body.data,
    headers: {
      cache_control: response.headers.get('cache-control'),
      content_type: response.headers.get('content-type'),
      access_control_allow_origin: response.headers.get('access-control-allow-origin'),
      rate_limit: response.headers.get('x-ratelimit-limit'),
      rate_remaining: response.headers.get('x-ratelimit-remaining')
    }
  };
}

const s = stampVN();
try {
  await fs.mkdir(workDir, { recursive: true });
  await fs.mkdir(diagDir, { recursive: true });
  const [arrival, departure] = await Promise.all([fetchBoard('A', s.day), fetchBoard('D', s.day)]);

  const arrivalsRaw = arrival.data.flatMap(x => toRaw(x, 'arrival'));
  const departuresRaw = departure.data.flatMap(x => toRaw(x, 'departure'));

  const raw = {
    schema_version: '2.3-raw',
    collected_at_vn: s.iso,
    collected_day_vn: s.day,
    collected_hhmm_vn: s.hhmm,
    board_date: s.day,
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url: SOURCE_URL,
      api: API_ROOT,
      acquisition: 'Direct official JSON API on GitHub Actions',
      paid_services_used: false
    },
    page_last_updated: `Official API fetched ${s.hm}`,
    arrivals_raw: arrivalsRaw,
    departures_raw: departuresRaw
  };

  await fs.writeFile(path.join(workDir, 'raw.json'), JSON.stringify(raw, null, 2) + '\n');
  await fs.writeFile(path.join(workDir, 'api-meta.json'), JSON.stringify({
    collected_at_vn: s.iso,
    arrival: { url: arrival.url, rows: arrival.data.length, headers: arrival.headers },
    departure: { url: departure.url, rows: departure.data.length, headers: departure.headers }
  }, null, 2) + '\n');

  console.log(JSON.stringify({
    board_date: s.day,
    arrivals_api: arrival.data.length,
    departures_api: departure.data.length,
    arrivals_raw: arrivalsRaw.length,
    departures_raw: departuresRaw.length,
    cors: arrival.headers.access_control_allow_origin || null
  }));
} catch (error) {
  const errorInfo = {
    collected_at_vn: s.iso,
    stage: 'COLLECT',
    name: error?.name || 'Error',
    message: error?.message || String(error)
  };
  await fs.mkdir(diagDir, { recursive: true });
  await fs.writeFile(path.join(diagDir, 'error.json'), JSON.stringify(errorInfo, null, 2) + '\n');
  throw error;
}
