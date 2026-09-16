(() => {
  const endpoint = () => String(window.JOTRIP_LIVE_API_URL || '').trim();
  const nativeFetch = window.fetch.bind(window);
  let cachedPayload = null;
  let cachedAt = 0;
  let inFlight = null;
  const CACHE_MS = 20 * 1000;

  function isAirportSnapshotRequest(input) {
    const u = typeof input === 'string' ? input : input?.url || '';
    if (!u.includes('raw.githubusercontent.com/kenzuko/Jotrip-Lab/data-sunairport/data/sunairport/')) return null;
    if (/\/latest\.json(?:\?|$)/.test(u)) return 'latest';
    if (/\/health\.json(?:\?|$)/.test(u)) return 'health';
    return null;
  }

  async function livePayload() {
    const url = endpoint();
    if (!url) throw new Error('LIVE_API_NOT_CONFIGURED');
    if (cachedPayload && Date.now() - cachedAt < CACHE_MS) return cachedPayload;
    if (inFlight) return inFlight;

    inFlight = nativeFetch(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`, {
      cache: 'no-store',
      headers: { accept: 'application/json' }
    }).then(async response => {
      if (!response.ok) throw new Error(`LIVE_API_HTTP_${response.status}`);
      const body = await response.json();
      if (!body?.latest || !body?.health) throw new Error('LIVE_API_INVALID_SHAPE');
      cachedPayload = body;
      cachedAt = Date.now();
      window.__JOTRIP_LIVE_TRANSPORT__ = {
        mode: 'live-api',
        endpoint: url,
        fetchedAt: new Date().toISOString()
      };
      return body;
    }).finally(() => { inFlight = null; });

    return inFlight;
  }

  window.fetch = async function jotripAirportFetch(input, init) {
    const kind = isAirportSnapshotRequest(input);
    if (!kind || !endpoint()) return nativeFetch(input, init);

    try {
      const payload = await livePayload();
      return new Response(JSON.stringify(payload[kind]), {
        status: 200,
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-JoTrip-Transport': 'live-api'
        }
      });
    } catch (error) {
      console.warn('[JoTrip Airport Live] Live API unavailable, falling back to GitHub snapshot:', error);
      window.__JOTRIP_LIVE_TRANSPORT__ = {
        mode: 'github-snapshot-fallback',
        endpoint: endpoint(),
        error: error?.message || String(error),
        fetchedAt: new Date().toISOString()
      };
      return nativeFetch(input, init);
    }
  };
})();
