import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';

const args = process.argv.slice(2);
const outIndex = args.indexOf('--out');
const outputDir = path.resolve(outIndex >= 0 ? args[outIndex + 1] : 'phu-quoc-pixel/.asset-audit');
const repoRoot = process.cwd();

const sources = [
  'preview/asset-map.js',
  'preview/asset-bg.js',
  'preview/asset-rides.js',
  'preview/asset-props.js'
];

function threeByteLE(buffer, offset) {
  return buffer[offset] | (buffer[offset + 1] << 8) | (buffer[offset + 2] << 16);
}

function imageDimensions(buffer, mime) {
  if (mime === 'image/png' && buffer.length >= 24) {
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }

  if (mime === 'image/webp' && buffer.length >= 30 && buffer.toString('ascii', 0, 4) === 'RIFF' && buffer.toString('ascii', 8, 12) === 'WEBP') {
    let offset = 12;
    while (offset + 8 <= buffer.length) {
      const chunk = buffer.toString('ascii', offset, offset + 4);
      const chunkSize = buffer.readUInt32LE(offset + 4);
      const data = offset + 8;

      if (chunk === 'VP8X' && data + 10 <= buffer.length) {
        return {
          width: threeByteLE(buffer, data + 4) + 1,
          height: threeByteLE(buffer, data + 7) + 1
        };
      }

      if (chunk === 'VP8 ' && data + 10 <= buffer.length && buffer[data + 3] === 0x9d && buffer[data + 4] === 0x01 && buffer[data + 5] === 0x2a) {
        return {
          width: buffer.readUInt16LE(data + 6) & 0x3fff,
          height: buffer.readUInt16LE(data + 8) & 0x3fff
        };
      }

      if (chunk === 'VP8L' && data + 5 <= buffer.length && buffer[data] === 0x2f) {
        const bits = buffer.readUInt32LE(data + 1);
        return {
          width: (bits & 0x3fff) + 1,
          height: ((bits >>> 14) & 0x3fff) + 1
        };
      }

      offset = data + chunkSize + (chunkSize % 2);
    }
  }

  return { width: null, height: null };
}

function extensionForMime(mime) {
  const map = {
    'image/webp': 'webp',
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/svg+xml': 'svg'
  };
  return map[mime] ?? 'bin';
}

await mkdir(outputDir, { recursive: true });

const sharedAssets = {};
const context = vm.createContext({
  A: sharedAssets,
  window: { A: sharedAssets }
});

for (const source of sources) {
  const code = await readFile(path.join(repoRoot, source), 'utf8');
  vm.runInContext(code, context, { filename: source, timeout: 1000 });
}

const manifest = [];
for (const [key, value] of Object.entries(sharedAssets).sort(([a], [b]) => a.localeCompare(b))) {
  if (typeof value !== 'string') continue;
  const match = value.match(/^data:([^;]+);base64,(.+)$/s);
  if (!match) continue;

  const mime = match[1];
  const bytes = Buffer.from(match[2], 'base64');
  const ext = extensionForMime(mime);
  const filename = `${key}.${ext}`;
  const outputPath = path.join(outputDir, filename);
  await writeFile(outputPath, bytes);

  const dimensions = imageDimensions(bytes, mime);
  manifest.push({
    key,
    sourceFiles: sources,
    filename,
    mime,
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    width: dimensions.width,
    height: dimensions.height,
    approved: null,
    note: 'Extracted losslessly from current prototype wrapper for audit only.'
  });
}

await writeFile(
  path.join(outputDir, 'manifest.json'),
  JSON.stringify({ generatedAt: new Date().toISOString(), count: manifest.length, assets: manifest }, null, 2) + '\n',
  'utf8'
);

console.log(`Extracted ${manifest.length} prototype assets to ${outputDir}`);
for (const asset of manifest) {
  console.log(`${asset.key}\t${asset.width ?? '?'}x${asset.height ?? '?'}\t${asset.bytes} bytes\t${asset.filename}`);
}
