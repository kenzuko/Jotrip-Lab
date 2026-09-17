import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const targets = [
  { key: 'phu_quoc_60018', sid: 33, url: 'https://kttvtudong.net/kttv/detail/view?sid=33' },
  { key: 'rach_gia_089907', sid: 464, url: 'https://kttvtudong.net/kttv/detail/view?sid=464' },
  { key: 'rain_control_DM6100', sid: 482, url: 'https://kttvtudong.net/kttv/detail/view?sid=482' },
];

const outDir = 'weather/research/ground-truth-probe';
await fs.mkdir(outDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const report = {
  generated_at: new Date().toISOString(),
  scope: 'Public pages only; no auth bypass; cookies/headers are not persisted.',
  targets: {},
};

for (const target of targets) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const transactions = [];

  page.on('response', async res => {
    const req = res.request();
    const u = new URL(res.url());
    if (u.hostname !== 'kttvtudong.net' && u.hostname !== 'www.kttvtudong.net') return;
    if (!/\/kttv\/(report|detail|export)\//.test(u.pathname) && !/\/kttv\/detail\/view/.test(u.pathname)) return;
    const headers = await res.allHeaders().catch(() => ({}));
    const contentType = headers['content-type'] || '';
    let body = '';
    if (/json|text|csv|html|javascript|xml/i.test(contentType)) {
      body = await res.text().catch(() => '');
    }
    transactions.push({
      url: res.url(),
      status: res.status(),
      method: req.method(),
      resource_type: req.resourceType(),
      post_data: req.postData() || '',
      content_type: contentType,
      body_length: body.length,
      body_preview: body.slice(0, 10000),
    });
  });

  let navigation_error = null;
  try {
    await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(9000);
  } catch (err) {
    navigation_error = String(err);
  }

  const discovered = await page.evaluate(() => {
    const inline = [...document.scripts].filter(s => !s.src).map(s => s.textContent || '').join('\n');
    const postCalls = [];
    const re = /\$\.post\(\s*['\"]([^'\"]+)['\"]\s*,\s*\{([^}]*)\}/g;
    let m;
    while ((m = re.exec(inline)) !== null) {
      const sd = /['\"]?sdid['\"]?\s*:\s*(\d+)/.exec(m[2]);
      postCalls.push({ endpoint: m[1], args_preview: m[2].trim(), sdid: sd ? Number(sd[1]) : null });
    }
    const uniq = [...new Map(postCalls.map(x => [`${x.endpoint}|${x.sdid}`, x])).values()];
    const forms = [...document.forms].map(f => ({
      action: f.action,
      method: f.method,
      controls: [...f.querySelectorAll('input,button')].map(el => ({
        tag: el.tagName,
        type: el.type || null,
        name: el.name || null,
        id: el.id || null,
        placeholder: el.placeholder || null,
        text: (el.innerText || '').trim(),
      })),
    }));
    const headers = [...document.querySelectorAll('table th')].map(x => (x.innerText || '').trim()).filter(Boolean);
    const vvClasses = [...new Set([...inline.matchAll(/vv(\d+)/g)].map(m => Number(m[1])))];
    return { post_calls: uniq, forms, table_headers: headers, variable_ids: vvClasses };
  }).catch(err => ({ error: String(err), post_calls: [], forms: [], table_headers: [], variable_ids: [] }));

  // Replay only POST routes that the public page itself disclosed, preserving the browser's public session.
  const directProbes = [];
  for (const call of discovered.post_calls || []) {
    if (!call.endpoint.startsWith('/kttv/report/') || !call.sdid) continue;
    try {
      const r = await page.evaluate(async ({ endpoint, sdid }) => {
        const body = new URLSearchParams({ sdid: String(sdid) });
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' },
          body,
          credentials: 'same-origin',
        });
        const text = await res.text();
        return { endpoint, sdid, status: res.status, content_type: res.headers.get('content-type'), body_length: text.length, body_preview: text.slice(0, 12000) };
      }, { endpoint: call.endpoint, sdid: call.sdid });
      directProbes.push(r);
    } catch (err) {
      directProbes.push({ endpoint: call.endpoint, sdid: call.sdid, error: String(err) });
    }
  }

  // Exercise the exact public Excel form for the previous day -> today and record only download metadata.
  const exportProbe = { attempted: false };
  try {
    const form = page.locator(`form[action*="/kttv/export/excelexport?sid=${target.sid}"]`).first();
    if (await form.count()) {
      exportProbe.attempted = true;
      const inputs = form.locator('input');
      const n = await inputs.count();
      const today = new Date();
      const yesterday = new Date(today.getTime() - 86400000);
      const fmt = d => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()}`;
      if (n >= 2) {
        await inputs.nth(0).fill(fmt(yesterday)).catch(() => {});
        await inputs.nth(1).fill(fmt(today)).catch(() => {});
      }
      const dlPromise = page.waitForEvent('download', { timeout: 15000 }).catch(() => null);
      await form.locator('button[type="submit"]').click().catch(() => {});
      const dl = await dlPromise;
      exportProbe.download = dl ? { suggested_filename: dl.suggestedFilename(), url: dl.url() } : null;
    }
  } catch (err) {
    exportProbe.error = String(err);
  }

  report.targets[target.key] = {
    sid: target.sid,
    navigation_error,
    final_url: page.url(),
    discovered,
    transactions,
    direct_probes: directProbes,
    export_probe: exportProbe,
  };
  await context.close();
}

await browser.close();
await fs.writeFile(`${outDir}/summary.json`, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: 'OK', output: `${outDir}/summary.json`, generated_at: report.generated_at }));
