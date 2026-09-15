import crypto from 'node:crypto';

const clean = (value = '') => String(value).replace(/\s+/g, ' ').trim();
const flightTokenRe = /\b[A-Z0-9]{2,3}\s?\d{2,4}[A-Z]?\b/gi;
const timeRe = /^(?:[01]?\d|2[0-3]):[0-5]\d$/;

const domesticStations = new Set([
  'HO CHI MINH', 'HA NOI', 'DA NANG', 'HAI PHONG', 'CAN THO', 'CAM RANH',
  'VINH', 'HUE', 'THANH HOA', 'BUON MA THUOT', 'DA LAT', 'QUY NHON',
  'PLEIKU', 'DONG HOI', 'DIEN BIEN'
]);

// Unknown labels fail QA instead of silently becoming an international station.
// Add a station only after confirming its exact label on the official board.
const knownStations = new Set([
  ...domesticStations,
  'INCHEON', 'BUSAN', 'SEOUL', 'BANGKOK', 'DON MUANG', 'KUALA LUMPUR',
  'SINGAPORE', 'HONG KONG', 'TAIPEI', 'TAICHUNG', 'KUNMING',
  'CHENGDU TIANFU', 'PHNOM PENH', 'ALMATY', 'ASTANA', 'TASHKENT',
  'MOSCOW', 'WARSAW'
]);

const knownStatuses = [
  'ĐÃ HẠ CÁNH', 'ĐÃ CẤT CÁNH', 'ĐÚNG GIỜ', 'TRỄ', 'HỦY', 'HOÃN',
  'ĐANG LÀM THỦ TỤC', 'QUẦY THỦ TỤC ĐÃ ĐÓNG', 'LÀM THỦ TỤC LÚC',
  'HÀNH KHÁCH ĐANG LÊN TÀU BAY', 'ĐỔI GIỜ', 'BÃI ĐỖ', 'BOARDING',
  'DELAYED', 'CANCELLED', 'RESCHEDULED'
];

const activeStatuses = new Set([
  'ĐÚNG GIỜ', 'TRỄ', 'HOÃN', 'ĐANG LÀM THỦ TỤC', 'LÀM THỦ TỤC LÚC',
  'BOARDING', 'DELAYED', 'RESCHEDULED'
]);

export function extractFlightNumbers(value = '') {
  return [...clean(value).toUpperCase().matchAll(flightTokenRe)]
    .map(match => match[0].replace(/\s+/g, ''));
}

function isOnlyFlightNumbers(value) {
  const stripped = clean(value).toUpperCase().replace(flightTokenRe, '').replace(/[\s,;/&-]/g, '');
  return extractFlightNumbers(value).length > 0 && stripped.length === 0;
}

function movementParts(record) {
  const parts = clean(record.context).split('|').map(clean).filter(Boolean);
  const carrierIndex = parts.findIndex(part => part.includes('•'));
  const carrierPart = carrierIndex >= 0 ? parts[carrierIndex] : '';
  const operatingFlight = extractFlightNumbers(carrierPart)[0]
    || clean(record.flight_number).toUpperCase();
  const carrier = carrierPart.includes('•') ? clean(carrierPart.split('•').slice(1).join('•')) : '';
  const statusContext = carrierIndex >= 0 ? parts.slice(Math.max(0, carrierIndex - 4), carrierIndex) : [];
  const status = [...knownStatuses].find(candidate =>
    statusContext.slice().reverse().some(part => part.toUpperCase().includes(candidate))
  ) || clean(record.status).toUpperCase() || 'UNKNOWN';

  let station = '';
  let stationIndex = -1;
  const marketingFlights = [];
  if (carrierIndex >= 0) {
    for (let index = carrierIndex + 1; index < Math.min(parts.length, carrierIndex + 6); index += 1) {
      const candidate = parts[index].toUpperCase();
      if (timeRe.test(candidate)) break;
      if (isOnlyFlightNumbers(candidate)) {
        marketingFlights.push(...extractFlightNumbers(candidate));
        continue;
      }
      if (knownStatuses.some(status => candidate.includes(status))) continue;
      if (/^[\d\s-]+$/.test(candidate)) continue;
      station = candidate;
      stationIndex = index;
      break;
    }
  }

  // Times before the carrier can belong to a status such as
  // "LÀM THỦ TỤC LÚC 15:05". Flight times are the time cells after station.
  const flightTimes = stationIndex >= 0
    ? parts.slice(stationIndex + 1).filter(part => timeRe.test(part))
    : [];
  const resolvedTimes = flightTimes.length ? flightTimes : (record.times || []);
  const scheduledTime = resolvedTimes[0] || '';
  const actualTime = resolvedTimes.length > 1 ? resolvedTimes.at(-1) : null;
  return {
    operatingFlight,
    marketingFlights: [...new Set(marketingFlights.filter(number => number !== operatingFlight))],
    carrier,
    station,
    scheduledTime,
    actualTime,
    status,
    flightTimes: resolvedTimes
  };
}

export function normalizeRecords(rawRecords = [], sourceDate = '') {
  const movements = new Map();
  for (const raw of rawRecords) {
    const parsed = movementParts(raw);
    const key = [raw.direction, parsed.operatingFlight, parsed.scheduledTime, parsed.station].join('|');
    const normalized = {
      movement_id: crypto.createHash('sha256').update(`${sourceDate}|${key}`).digest('hex').slice(0, 20),
      direction: raw.direction,
      operating_flight_number: parsed.operatingFlight,
      marketing_flight_numbers: parsed.marketingFlights,
      carrier: parsed.carrier,
      scheduled_time: parsed.scheduledTime,
      actual_time: parsed.actualTime,
      times: parsed.flightTimes,
      station: parsed.station,
      market: parsed.station
        ? (domesticStations.has(parsed.station) ? 'domestic' : 'international')
        : 'unknown',
      status: parsed.status,
      context: clean(raw.context)
    };

    if (!movements.has(key)) {
      movements.set(key, normalized);
      continue;
    }
    const existing = movements.get(key);
    existing.marketing_flight_numbers = [...new Set([
      ...existing.marketing_flight_numbers,
      ...normalized.marketing_flight_numbers,
      ...extractFlightNumbers(raw.flight_number).filter(number => number !== parsed.operatingFlight)
    ])];
  }
  return [...movements.values()];
}

function countBy(records, keyFn) {
  const counts = {};
  for (const record of records) {
    const key = keyFn(record);
    if (!key) continue;
    counts[key] = (counts[key] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

function hourBank(records) {
  return countBy(records, record => {
    const hour = Number((record.actual_time || record.scheduled_time || '').slice(0, 2));
    if (!Number.isInteger(hour)) return '';
    if (hour < 6) return '00:00-05:59';
    if (hour < 9) return '06:00-08:59';
    if (hour < 12) return '09:00-11:59';
    if (hour < 15) return '12:00-14:59';
    if (hour < 18) return '15:00-17:59';
    if (hour < 21) return '18:00-20:59';
    return '21:00-23:59';
  });
}

export function buildSummary(records) {
  const arrivals = records.filter(record => record.direction === 'arrival');
  const departures = records.filter(record => record.direction === 'departure');
  const marketCounts = items => ({
    domestic: items.filter(record => record.market === 'domestic').length,
    international: items.filter(record => record.market === 'international').length,
    unknown: items.filter(record => record.market === 'unknown').length
  });
  return {
    counts: { arrivals: arrivals.length, departures: departures.length, total: records.length },
    summary: {
      arrivals_market: marketCounts(arrivals),
      departures_market: marketCounts(departures),
      arrivals_by_station: countBy(arrivals, record => record.station),
      departures_by_station: countBy(departures, record => record.station),
      arrivals_by_status: countBy(arrivals, record => record.status),
      departures_by_status: countBy(departures, record => record.status),
      arrivals_by_time_bank: hourBank(arrivals),
      departures_by_time_bank: hourBank(departures)
    }
  };
}

export function runQualityChecks(records) {
  const errors = [];
  const warnings = [];
  const ids = new Set();
  const arrivals = records.filter(record => record.direction === 'arrival');
  const departures = records.filter(record => record.direction === 'departure');
  if (arrivals.length < 5) errors.push(`TOO_FEW_ARRIVALS:${arrivals.length}`);
  if (departures.length < 5) errors.push(`TOO_FEW_DEPARTURES:${departures.length}`);

  for (const record of records) {
    if (!record.station) errors.push(`MISSING_STATION:${record.movement_id}`);
    else if (isOnlyFlightNumbers(record.station)) errors.push(`FLIGHT_NUMBER_AS_STATION:${record.station}`);
    else if (!knownStations.has(record.station)) errors.push(`UNKNOWN_STATION:${record.station}`);
    if (!record.operating_flight_number) errors.push(`MISSING_OPERATING_FLIGHT:${record.movement_id}`);
    if (!record.scheduled_time) warnings.push(`MISSING_SCHEDULED_TIME:${record.operating_flight_number}`);
    if (record.status === 'UNKNOWN') warnings.push(`UNKNOWN_STATUS:${record.operating_flight_number}`);
    if (ids.has(record.movement_id)) errors.push(`DUPLICATE_MOVEMENT:${record.movement_id}`);
    ids.add(record.movement_id);
  }
  return {
    passed: errors.length === 0,
    errors: [...new Set(errors)],
    warnings: [...new Set(warnings)],
    rules_checked: 8,
    records_checked: records.length
  };
}

export function detectRollover(records, previousSnapshot, sourceDate) {
  if (previousSnapshot?.source_date === sourceDate) return { detected: true, reason: 'CURRENT_DATE_ALREADY_PRESENT' };
  const activeCount = records.filter(record => activeStatuses.has(record.status)).length;
  if (activeCount >= 5) return { detected: true, reason: `ACTIVE_D0_STATUSES:${activeCount}` };
  return { detected: false, reason: `NO_D0_EVIDENCE_ACTIVE_STATUSES:${activeCount}` };
}
