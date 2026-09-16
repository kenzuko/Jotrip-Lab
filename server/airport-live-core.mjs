const API_ROOT = 'https://sunairport.com/phuquoc/cms/api/flights';
const SOURCE_URL = 'https://sunairport.com/phuquoc/vi/chuyen-bay';
const TZ = 'Asia/Ho_Chi_Minh';

const domesticStations = new Set([
  'HO CHI MINH','HA NOI','DA NANG','HAI PHONG','CAN THO','CAM RANH',
  'VINH','HUE','THANH HOA','BUON MA THUOT','DA LAT','QUY NHON',
  'PLEIKU','DONG HOI','DIEN BIEN'
]);

const clean = (s='') => String(s ?? '').replace(/\s+/g, ' ').trim();

function stampVN(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(date);
  const m = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return {
    day: `${m.year}-${m.month}-${m.day}`,
    iso: `${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}:${m.second}+07:00`
  };
}

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
  const estimatedDelay = estimated ? signedDiffMinutes(scheduled, estimated) : null;
  const actualDelay = actual ? signedDiffMinutes(scheduled, actual) : null;

  return {
    source_id: item.id ?? null,
    direction,
    operating_flight_number: flight,
    marketing_flight_numbers: aliases,
    station: clean(item.cityName),
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

async function fetchBoard(type, day) {
  const u = new URL(API_ROOT);
  u.searchParams.set('type', type);
  u.searchParams.set('date', day);
  u.searchParams.set('limit', '100');
  u.searchParams.set('_t', String(Date.now()));

  const response = await fetch(u, {
    headers: {
      accept: 'application/json',
      'user-agent': 'JoTrip-Airport-Live/4.0 (+https://github.com/kenzuko/Jotrip-Lab)'
    },
    cache: 'no-store',
    signal: AbortSignal.timeout(10000)
  });

  if (!response.ok) throw new Error(`Sun Airport API ${type}: HTTP ${response.status}`);
  const body = await response.json();
  if (!body?.success || !Array.isArray(body?.data)) throw new Error(`Sun Airport API ${type}: invalid JSON shape`);
  return body.data;
}

export async function getAirportLivePayload() {
  const startedAt = Date.now();
  const stamp = stampVN();
  const [arrivalRows, departureRows] = await Promise.all([
    fetchBoard('A', stamp.day),
    fetchBoard('D', stamp.day)
  ]);

  const arrivals = arrivalRows.map(x => normalizeItem(x, 'arrival'));
  const departures = departureRows.map(x => normalizeItem(x, 'departure'));
  const records = [...arrivals, ...departures];
  const usable = arrivals.length >= 5 && departures.length >= 5;
  const latest = {
    schema_version: '4.0-live',
    parser_version: 'sunairport-api-v4.0-live',
    normalization_version: 'jotrip-airport-v3.0-compatible',
    report_state: usable ? 'REPORT_READY' : 'QA_FAILED',
    collected_at_vn: stamp.iso,
    source_date: stamp.day,
    source: {
      name: 'Sun Airport - Phu Quoc International Airport',
      url: SOURCE_URL,
      api: API_ROOT,
      acquisition: 'Direct official JSON API via JoTrip Live API',
      paid_services_used: false
    },
    page_last_updated: `Official API fetched ${stamp.iso.slice(11,16)}`,
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
      board_date_matches_collection_date: true,
      source_mode: 'OFFICIAL_JSON_API_LIVE_PROXY',
      archive_mode: 'SEPARATE_AUTOSYNC',
      full_snapshot_history: false
    },
    records
  };

  const health = {
    module: 'JoTrip Live API - Sun Airport flights',
    state: usable ? 'REPORT_READY' : 'QA_FAILED',
    live_proxy: true,
    collector_completed: true,
    parser_passed: true,
    normalization_passed: true,
    qa_passed: usable,
    collected_at_vn: stamp.iso,
    source_date: stamp.day,
    source_mode: 'OFFICIAL_JSON_API_LIVE_PROXY',
    latency_ms: Date.now() - startedAt
  };

  return { latest, health };
}
