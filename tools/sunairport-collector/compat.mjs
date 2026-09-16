import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const latestPath = path.join(repoRoot, 'data', 'sunairport', 'latest.json');

const data = JSON.parse(await fs.readFile(latestPath, 'utf8'));
for (const r of data.records || []) {
  const times = [r.scheduled_time, r.estimated_time].filter(Boolean);
  r.times = [...new Set(times)];
  const airline = r.airline_name || r.airline_code || '';
  r.context = [
    `${r.operating_flight_number || ''}${airline ? ` • ${airline}` : ''}`,
    r.station,
    r.scheduled_time,
    r.estimated_time,
    r.raw_status || r.status
  ].filter(Boolean).join(' | ');
}
await fs.writeFile(latestPath, JSON.stringify(data, null, 2) + '\n');
console.log(JSON.stringify({ compatibility_records: data.records?.length || 0 }));
