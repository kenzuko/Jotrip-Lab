import { getAirportLivePayload } from '../../server/airport-live-core.mjs';

const headers = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Cache-Control': 'public, max-age=0, s-maxage=30, stale-while-revalidate=30',
  'Content-Type': 'application/json; charset=utf-8'
};

export async function handler(event) {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 204, headers, body: '' };
  if (event.httpMethod !== 'GET') {
    return { statusCode: 405, headers, body: JSON.stringify({ ok: false, error: 'METHOD_NOT_ALLOWED' }) };
  }

  try {
    const payload = await getAirportLivePayload();
    return {
      statusCode: payload.health.qa_passed ? 200 : 503,
      headers,
      body: JSON.stringify({ ok: payload.health.qa_passed, ...payload })
    };
  } catch (error) {
    return {
      statusCode: 502,
      headers,
      body: JSON.stringify({
        ok: false,
        error: 'UPSTREAM_UNAVAILABLE',
        message: error?.message || String(error),
        generated_at: new Date().toISOString()
      })
    };
  }
}
