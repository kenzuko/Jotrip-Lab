import fs from 'node:fs/promises';

const src = 'weather/research/ground-truth-probe/latest.json';
const dst = 'weather/research/ground-truth-probe/extracted.json';
const raw = JSON.parse(await fs.readFile(src, 'utf8'));
const out = { generated_at: new Date().toISOString(), source_generated_at: raw.generated_at, targets: {} };

for (const [key, t] of Object.entries(raw.targets || {})) {
  const requests = (t.requests || []).filter(x => /\/kttv\/(report|export)\//.test(x.url || ''));
  const responses = (t.responses || []).filter(x => /\/kttv\/(report|export)\//.test(x.url || ''));
  out.targets[key] = {
    url: t.url,
    requests: requests.map(x => ({ url: x.url, method: x.method, resource_type: x.resource_type, post_data: x.post_data })),
    responses: responses.map(x => ({ url: x.url, status: x.status, method: x.method, resource_type: x.resource_type, content_type: x.content_type, body_length: x.body_length, body_preview: x.body_preview })),
    export_probe: t.export_probe,
  };
}

await fs.writeFile(dst, JSON.stringify(out, null, 2) + '\n');
console.log(JSON.stringify(out, null, 2));
