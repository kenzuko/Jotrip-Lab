import { getAirportLivePayload } from '../server/airport-live-core.mjs';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'public, max-age=0, s-maxage=30, stale-while-revalidate=30');

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'METHOD_NOT_ALLOWED' });

  try {
    const payload = await getAirportLivePayload();
    return res.status(payload.health.qa_passed ? 200 : 503).json({ ok: payload.health.qa_passed, ...payload });
  } catch (error) {
    return res.status(502).json({
      ok: false,
      error: 'UPSTREAM_UNAVAILABLE',
      message: error?.message || String(error),
      generated_at: new Date().toISOString()
    });
  }
}
