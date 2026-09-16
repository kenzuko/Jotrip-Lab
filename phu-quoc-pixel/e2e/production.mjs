import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';

const url = process.env.PREVIEW_URL;
const executablePath = process.env.CHROME_BIN;
if (!url || !executablePath) throw new Error('PREVIEW_URL and CHROME_BIN are required');

const out = process.env.E2E_OUT || '/tmp/pixel-e2e';
await fs.mkdir(out, { recursive: true });

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu']
});

const page = await browser.newPage({ viewport: { width: 430, height: 932 } });
const runtimeErrors = [];
const badResponses = [];

page.on('pageerror', (error) => runtimeErrors.push(`pageerror: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`);
});
page.on('response', (response) => {
  if (response.status() >= 400) badResponses.push(`${response.status()} ${response.url()}`);
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 30_000 });
await page.locator('canvas').waitFor({ state: 'visible', timeout: 10_000 });
await page.screenshot({ path: `${out}/01-landing.png` });

async function clickLogical(x, y) {
  const canvas = page.locator('canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('Canvas bounding box unavailable');
  await page.mouse.click(box.x + (x / 540) * box.width, box.y + (y / 960) * box.height);
}

await clickLogical(270, 662); // ENTER THE ISLAND
await page.waitForTimeout(250);
await page.screenshot({ path: `${out}/02-airport.png` });

await clickLogical(270, 670); // LET'S GO
await page.waitForTimeout(250);
await page.screenshot({ path: `${out}/03-character.png` });

await clickLogical(155, 235); // TRAVELER
await clickLogical(270, 790); // OPEN THE MAP
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/04-map.png` });

await clickLogical(202, 496); // SUNSET TOWN pin on migrated island map
await page.waitForTimeout(700);
await page.screenshot({ path: `${out}/05-no-brakes-tutorial.png` });

await clickLogical(270, 610); // START RIDE
await page.waitForTimeout(900);
await page.screenshot({ path: `${out}/06-no-brakes-running.png` });

// Deliberately do not jump. The first two training obstacles must rescue the
// player, while the first non-training collision should end the run.
await page.waitForTimeout(11_000);
await page.screenshot({ path: `${out}/07-no-brakes-result.png` });

const progress = await page.evaluate(() => {
  const raw = window.localStorage.getItem('pqpi:v1:progress');
  return raw ? JSON.parse(raw) : null;
});

if (!progress) throw new Error('ProgressStore did not persist after a completed run');
const best = progress.bestScores?.['no-brakes'] ?? 0;
if (best < 2) throw new Error(`Expected training run best score >= 2, got ${best}`);

await clickLogical(270, 655); // BACK TO MAP
await page.waitForTimeout(450);
await page.screenshot({ path: `${out}/08-return-map.png` });

if (badResponses.length) {
  throw new Error(`HTTP failures during journey:\n${badResponses.join('\n')}`);
}
if (runtimeErrors.length) {
  throw new Error(`Runtime errors during journey:\n${runtimeErrors.join('\n')}`);
}

await fs.writeFile(
  `${out}/journey.json`,
  JSON.stringify({ url, bestScore: best, totalJo: progress.totalJo ?? 0, runtimeErrors, badResponses }, null, 2) + '\n'
);

await browser.close();
console.log(`Pixel production E2E passed with best score ${best}`);
