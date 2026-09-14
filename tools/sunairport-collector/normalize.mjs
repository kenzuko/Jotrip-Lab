import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const latestPath = path.join(repoRoot, 'data', 'sunairport', 'latest.json');
const clean = (s='') => String(s).replace(/\s+/g, ' ').trim();
const flightRe = /^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$/i;

const domesticStations = new Set([
  'HO CHI MINH','HA NOI','DA NANG','HAI PHONG','CAN THO','CAM RANH',
  'VINH','HUE','THANH HOA','BUON MA THUOT','DA LAT','QUY NHON',
  'PLEIKU','DONG HOI','DIEN BIEN'
]);

const raw = JSON.parse(await fs.readFile(latestPath, 'utf8'));
const unique = new Map();
for (const r of raw.records || []) {
  const lastTime = r.times?.[r.times.length - 1] || r.times?.[0] || '';
  const key = `${r.direction}|${lastTime}|${r.context}`;
  if (!unique.has(key)) unique.set(key, r);
}

const records = [...unique.values()].map(r => {
  const parts = String(r.context || '').split('|').map(clean).filter(Boolean);
  const idx = parts.findIndex(p => p.toUpperCase().includes(String(r.flight_number || '').toUpperCase()));
  let station = '';
  if (idx >= 0) {
    for (let i = idx + 1; i < Math.min(parts.length, idx + 4); i++) {
      const c = parts[i];
      if (!c || flightRe.test(c) || /^\d{1,2}:\d{2}$/.test(c)) continue;
      station = c;
      break;
    }
  }
  const market = station ? (domesticStations.has(station.toUpperCase()) ? 'domestic' : 'international') : 'unknown';
  return { ...r, station, market };
});

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

const arrivals = records.filter(r => r.direction === 'arrival');
const departures = records.filter(r => r.direction === 'departure');
const marketCounts = items => ({
  domestic: items.filter(r => r.market === 'domestic').length,
  international: items.filter(r => r.market === 'international').length,
  unknown: items.filter(r => r.market === 'unknown').length
});

raw.schema_version = '1.2';
raw.normalization = {
  same_row_codeshares_collapsed: true,
  method: 'direction + scheduled time + rendered row context'
};
raw.records = records;
raw.counts = { arrivals: arrivals.length, departures: departures.length, total: records.length };
raw.summary = {
  arrivals_market: marketCounts(arrivals),
  departures_market: marketCounts(departures),
  arrivals_by_station: countBy(arrivals, r => r.station),
  departures_by_station: countBy(departures, r => r.station),
  arrivals_by_time_bank: bank(arrivals),
  departures_by_time_bank: bank(departures)
};
raw.quality = {
  usable: arrivals.length >= 5 && departures.length >= 5,
  note: 'Rendered official board normalized so same-row codeshares count as one physical movement.'
};

const iso = raw.collected_at_vn || '';
const day = iso.slice(0,10);
const hhmm = iso.slice(11,16).replace(':','');
const json = JSON.stringify(raw, null, 2) + '\n';
await fs.writeFile(latestPath, json);
if (day && hhmm) {
  await fs.writeFile(path.join(repoRoot, 'data', 'sunairport', day, `${hhmm}.json`), json);
}
console.log(JSON.stringify({ counts: raw.counts, summary: raw.summary }));
