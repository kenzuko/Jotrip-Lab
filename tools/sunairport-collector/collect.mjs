import fs from 'node:fs/promises';
import path from 'node:path';

const API_ROOT = 'https://sunairport.com/phuquoc/cms/api/flights';
const SOURCE_URL = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const tz = 'Asia/Ho_Chi_Minh';
const repoRoot = path.resolve(process.cwd(), '../..');
const workDir = path.join(repoRoot, 'data', 'sunairport', '_working');
const diagDir = path.join(repoRoot, 'artifacts', 'sunairport');

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

async function fetchBoard(type, day) {
  const u = new URL(API_ROOT);
  u.searchParams.set('type', type);
  u.searchParams.set('date', day);
  u.searchParams.set('limit', '100');
  u.searchParams.set('_t', String(Date.now()));

  const response = await fetch(u, {
    headers: {
      accept: 'application/json',
      'user-agent': 'JoTrip-Airport-Live/3.0 (+https://github.com/kenzuko/Jotrip-Lab)'
    },
    cache: 'no-store',
    signal: AbortSignal.timeout(20000)
  });

  if (!response.ok) throw new Error(`Sun Airport API ${type}: HTTP ${response.status}`);
  const body = await response.json();
  if (!body?.success || !Array.isArray(body?.data)) {
    throw new Error(`Sun Airport API ${type}: invalid JSON shape`);
  }

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

  const [arrival, departure] = await Promise.all([
    fetchBoard('A', s.day),
    fetchBoard('D', s.day)
  ]);

  // Preserve the official API rows exactly. This is the source-of-truth input for
  // normalization and the compact daily raw archive. No rendered-page parsing.
  const apiRaw = {
    schema_version: '3.0-api-raw',
    collected_at_vn: s.iso,
    collected_day_vn: s.day,
    collected_hhmm_vn: s.hhmm,
    board_date: s.day,
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url: SOURCE_URL,
      api: API_ROOT,
      acquisition: 'Direct official JSON API via JoTrip AutoSync',
      paid_services_used: false
    },
    arrivals: arrival.data,
    departures: departure.data
  };

  await fs.writeFile(
    path.join(workDir, 'api-raw.json'),
    JSON.stringify(apiRaw, null, 2) + '\n'
  );

  await fs.writeFile(path.join(workDir, 'api-meta.json'), JSON.stringify({
    collected_at_vn: s.iso,
    arrival: { url: arrival.url, rows: arrival.data.length, headers: arrival.headers },
    departure: { url: departure.url, rows: departure.data.length, headers: departure.headers }
  }, null, 2) + '\n');

  console.log(JSON.stringify({
    board_date: s.day,
    arrivals_api: arrival.data.length,
    departures_api: departure.data.length,
    acquisition: 'direct-json',
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
