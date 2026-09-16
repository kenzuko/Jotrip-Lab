import { getAirportLivePayload } from '../server/airport-live-core.mjs';

const FALLBACK_BASE = 'https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-sunairport/data/sunairport';
const CACHE_SECONDS = 45;
const STALE_SECONDS = 120;

function headers(extra = {}) {
  return {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET, HEAD, OPTIONS',
    'access-control-allow-headers': 'Content-Type',
    'cache-control': 'public, max-age=0, must-revalidate',
    ...extra
  };
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), { status, headers: headers(extra) });
}

async function githubFallback() {
  const stamp = Date.now();
  const [latestRes, healthRes] = await Promise.all([
    fetch(`${FALLBACK_BASE}/latest.json?t=${stamp}`, { cache: 'no-store' }),
    fetch(`${FALLBACK_BASE}/health.json?t=${stamp}`, { cache: 'no-store' })
  ]);
  if (!latestRes.ok || !healthRes.ok) throw new Error(`Fallback unavailable: ${latestRes.status}/${healthRes.status}`);
  const [latest, health] = await Promise.all([latestRes.json(), healthRes.json()]);
  return {
    latest,
    health: {
      ...health,
      module: 'JoTrip Live API - GitHub fallback',
      live_proxy: false,
      source_mode: 'GITHUB_SNAPSHOT_FALLBACK'
    }
  };
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: headers() });
    if (!['GET', 'HEAD'].includes(request.method)) return json({ error: 'Method not allowed' }, 405);

    const url = new URL(request.url);
    if (url.pathname === '/healthz') {
      return json({ ok: true, service: 'JoTrip Airport Live API', provider: 'Cloudflare Workers Free' });
    }
    if (!['/', '/api/airport-live', '/api/airport-live/'].includes(url.pathname)) {
      return json({ error: 'Not found' }, 404);
    }

    const cache = caches.default;
    const cacheKey = new Request(`${url.origin}/__jotrip_cache/airport-live`, { method: 'GET' });
    const cached = await cache.match(cacheKey);
    if (cached) {
      const h = new Headers(cached.headers);
      h.set('x-jotrip-cache', 'HIT');
      return new Response(request.method === 'HEAD' ? null : cached.body, { status: cached.status, headers: h });
    }

    let payload;
    let mode = 'LIVE';
    try {
      payload = await getAirportLivePayload();
    } catch (error) {
      mode = 'FALLBACK';
      payload = await githubFallback();
      payload.health = {
        ...payload.health,
        upstream_error: error?.message || String(error)
      };
    }

    const response = json(payload, 200, {
      'cache-control': `public, max-age=0, s-maxage=${CACHE_SECONDS}, stale-while-revalidate=${STALE_SECONDS}`,
      'x-jotrip-cache': 'MISS',
      'x-jotrip-source': mode
    });
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return new Response(request.method === 'HEAD' ? null : response.body, { status: response.status, headers: response.headers });
  }
};
