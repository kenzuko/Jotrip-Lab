import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const targets = [
  { key: 'phu_quoc_60018', sid: 33, url: 'https://kttvtudong.net/kttv/detail/view?sid=33' },
  { key: 'rach_gia_089907', sid: 464, url: 'https://kttvtudong.net/kttv/detail/view?sid=464' },
  { key: 'rain_control_DM6100', sid: 482, url: 'https://kttvtudong.net/kttv/detail/view?sid=482' },
];

await fs.mkdir('/tmp/gt-exports', { recursive: true });
const browser = await chromium.launch({ headless: true });
const meta = { generated_at: new Date().toISOString(), targets: {} };

for (const t of targets) {
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  try {
    await page.goto(t.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(2000);
    const form = page.locator(`form[action*="/kttv/export/excelexport?sid=${t.sid}"]`).first();
    if (!(await form.count())) throw new Error('export form not found');
    const fd = form.locator('input[name="fd"]');
    const td = form.locator('input[name="td"]');
    if (await fd.count()) await fd.fill('16/09/2026');
    if (await td.count()) await td.fill('17/09/2026');
    const reqs = [];
    page.on('request', r => {
      if (r.url().includes('/kttv/export/excelexport')) reqs.push({ url: r.url(), method: r.method(), post_data: r.postData() || '' });
    });
    const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
    await form.locator('button[type="submit"]').click();
    const dl = await downloadPromise;
    const dest = `/tmp/gt-exports/${t.key}.xlsx`;
    await dl.saveAs(dest);
    const stat = await fs.stat(dest);
    meta.targets[t.key] = { ok: true, sid: t.sid, path: dest, bytes: stat.size, suggested_filename: dl.suggestedFilename(), requests: reqs };
  } catch (e) {
    meta.targets[t.key] = { ok: false, sid: t.sid, error: String(e) };
  }
  await ctx.close();
}
await browser.close();
await fs.writeFile('/tmp/gt-exports/meta.json', JSON.stringify(meta, null, 2));
console.log(JSON.stringify(meta, null, 2));
