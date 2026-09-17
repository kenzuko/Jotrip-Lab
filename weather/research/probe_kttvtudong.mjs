import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const targets = [
  { key: 'phu_quoc_60018', url: 'https://kttvtudong.net/kttv/detail/view?sid=33' },
  { key: 'rach_gia_089907', url: 'https://kttvtudong.net/kttv/detail/view?sid=464' },
  { key: 'rain_control_DM6100', url: 'https://kttvtudong.net/kttv/detail/view?sid=482' },
];

const outDir = 'weather/research/ground-truth-probe';
await fs.mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const collected = {
  generated_at: new Date().toISOString(),
  purpose: 'Public-browser diagnostic only. Discover public numeric observation transport without bypassing authentication.',
  targets: {},
};

for (const target of targets) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const requests = [];
  const responses = [];

  page.on('request', req => {
    const type = req.resourceType();
    if (['xhr', 'fetch', 'document'].includes(type)) {
      requests.push({
        url: req.url(),
        method: req.method(),
        resource_type: type,
        post_data: (req.postData() || '').slice(0, 4000),
      });
    }
  });

  page.on('response', async res => {
    const req = res.request();
    const type = req.resourceType();
    if (!['xhr', 'fetch', 'document'].includes(type)) return;
    const headers = await res.allHeaders().catch(() => ({}));
    const contentType = headers['content-type'] || '';
    const item = {
      url: res.url(),
      status: res.status(),
      method: req.method(),
      resource_type: type,
      content_type: contentType,
    };
    if (/json|text|javascript|xml|csv|html/i.test(contentType)) {
      try {
        const body = await res.text();
        item.body_preview = body.slice(0, 12000);
        item.body_length = body.length;
      } catch {}
    }
    responses.push(item);
  });

  let navigation_error = null;
  try {
    await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(7000);
  } catch (err) {
    navigation_error = String(err);
  }

  const dom = await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('input')].map((el, index) => ({
      index,
      type: el.type,
      name: el.name,
      id: el.id,
      value: el.value,
      placeholder: el.placeholder,
      className: el.className,
    }));
    const forms = [...document.querySelectorAll('form')].map((form, index) => ({
      index,
      action: form.action,
      method: form.method,
      id: form.id,
      className: form.className,
      text: (form.innerText || '').trim().slice(0, 1500),
      controls: [...form.querySelectorAll('input,button,select')].map(el => ({
        tag: el.tagName,
        type: el.type || null,
        name: el.name || null,
        id: el.id || null,
        value: el.value || null,
        text: (el.innerText || '').trim().slice(0, 300),
      })),
    }));
    const scripts = [...document.scripts].map(s => ({ src: s.src, inline_preview: s.src ? '' : (s.textContent || '').slice(0, 6000) }));
    const links = [...document.querySelectorAll('a')]
      .map(a => ({ text: (a.innerText || '').trim(), href: a.href }))
      .filter(x => /6h|12h|24h|36h|48h|60h|72h|240h|360h|480h|600h|720h|excel|xuất|bao cao|report/i.test(`${x.text} ${x.href}`));
    const table_text = [...document.querySelectorAll('table')].map(t => (t.innerText || '').trim().slice(0, 12000));
    return { title: document.title, inputs, forms, scripts, links, table_text };
  }).catch(err => ({ evaluation_error: String(err) }));

  // Probe the public export control if it can be identified. Do not attempt login or protected routes.
  const exportProbe = { attempted: false, result: null };
  try {
    const button = page.getByRole('button', { name: /xuất báo cáo/i }).first();
    if (await button.count()) {
      exportProbe.attempted = true;
      const form = button.locator('xpath=ancestor::form[1]');
      if (await form.count()) {
        const dateInputs = form.locator('input');
        const n = await dateInputs.count();
        const today = new Date();
        const yesterday = new Date(today.getTime() - 86400000);
        const fmt = d => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()}`;
        if (n >= 2) {
          await dateInputs.nth(0).fill(fmt(yesterday)).catch(() => {});
          await dateInputs.nth(1).fill(fmt(today)).catch(() => {});
        }
        const before = page.url();
        const downloadPromise = page.waitForEvent('download', { timeout: 12000 }).catch(() => null);
        await button.click().catch(() => {});
        await page.waitForTimeout(4000);
        const download = await downloadPromise;
        exportProbe.result = {
          before_url: before,
          after_url: page.url(),
          download: download ? {
            suggested_filename: download.suggestedFilename(),
            url: download.url(),
          } : null,
        };
      }
    }
  } catch (err) {
    exportProbe.result = { error: String(err) };
  }

  collected.targets[target.key] = {
    url: target.url,
    navigation_error,
    final_url: page.url(),
    dom,
    requests,
    responses,
    export_probe: exportProbe,
  };

  await context.close();
}

await browser.close();
await fs.writeFile(path.join(outDir, 'latest.json'), JSON.stringify(collected, null, 2) + '\n');
console.log(JSON.stringify({ status: 'OK', output: path.join(outDir, 'latest.json'), generated_at: collected.generated_at }));
