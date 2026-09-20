import { getAirportLivePayload, airportBoardVersion } from '../server/airport-live-core.mjs';

const FALLBACK_BASE = 'https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-sunairport/data/sunairport';
const CACHE_SECONDS = 30;
const STALE_SECONDS = 90;

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
  const boardVersion = latest.board_version || airportBoardVersion(latest.records || []);
  latest.board_version = boardVersion;
  return {
    latest,
    health: {
      ...health,
      module: 'JoTrip Live API - GitHub fallback',
      live_proxy: false,
      source_mode: 'GITHUB_SNAPSHOT_FALLBACK',
      board_version: boardVersion
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
    const isVersion = ['/version', '/api/airport-live/version'].includes(url.pathname);
    if (!isVersion && !['/', '/api/airport-live', '/api/airport-live/'].includes(url.pathname)) {
      return json({ error: 'Not found' }, 404);
    }

    const cache = caches.default;
    const cacheKey = new Request(`${url.origin}/__jotrip_cache/airport-live`, { method: 'GET' });
    let cached = await cache.match(cacheKey);
    let payload = null;
    let cacheState = cached ? 'HIT' : 'MISS';
    let mode = cached?.headers.get('x-jotrip-source') || 'LIVE';

    if (cached) {
      if (!isVersion) {
        const h = new Headers(cached.headers);
        h.set('x-jotrip-cache', 'HIT');
        return new Response(request.method === 'HEAD' ? null : cached.body, { status: cached.status, headers: h });
      }
      payload = await cached.clone().json();
    } else {
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
        'x-jotrip-source': mode,
        'x-jotrip-version': payload?.latest?.board_version || ''
      });
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      cached = response;
    }

    if (isVersion) {
      const versionBody = {
        version: payload?.latest?.board_version || payload?.health?.board_version || null,
        collected_at_vn: payload?.latest?.collected_at_vn || null,
        source_date: payload?.latest?.source_date || null,
        source_mode: payload?.health?.source_mode || payload?.latest?.quality?.source_mode || null,
        qa_passed: payload?.health?.qa_passed === true,
        cache_ttl_seconds: CACHE_SECONDS
      };
      const h = headers({
        'cache-control': 'no-store',
        'x-jotrip-cache': cacheState,
        'x-jotrip-source': mode,
        'x-jotrip-version': versionBody.version || ''
      });
      return new Response(request.method === 'HEAD' ? null : JSON.stringify(versionBody), { status: 200, headers: h });
    }

    const h = new Headers(cached.headers);
    h.set('x-jotrip-cache', cacheState);
    return new Response(request.method === 'HEAD' ? null : cached.body, { status: cached.status, headers: h });
  }
};