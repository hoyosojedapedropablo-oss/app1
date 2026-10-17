// Protocol adapter: Cobalt's POST /get_pot -> BgUtils' JSON HTTP API.
// No browser login, account cookies, token logging, or public listener mapping.
import http from 'node:http';

let cached = null, expires = 0, pending = null;
const provider = process.env.POT_PROVIDER_URL || 'http://pot-provider:4416';

export function normalize(payload, now = Date.now()) {
  if (typeof payload?.poToken !== 'string' || payload.poToken.length < 100 || payload.poToken.length > 10000 ||
      typeof payload?.contentBinding !== 'string' || !payload.contentBinding || payload.contentBinding.length > 4096) {
    throw Error('POT_INVALID');
  }
  const expiry = Date.parse(payload.expiresAt);
  if (!Number.isFinite(expiry) || expiry <= now) throw Error('POT_EXPIRED');
  return {value: {potoken: payload.poToken, visitor_data: payload.contentBinding, updated: now},
          expires: Math.min(expiry, now + 240000)};
}

async function session() {
  if (cached && expires > Date.now()) return cached;
  if (pending) return pending;
  pending = (async () => {
    const response = await fetch(provider + '/get_pot', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
      signal: AbortSignal.timeout(45000)
    });
    if (!response.ok) throw Error('POT_UNAVAILABLE');
    // Do not relay provider errors or credentials to Cobalt or the browser.
    const result = normalize(await response.json());
    cached = result.value; expires = result.expires;
    return cached;
  })().finally(() => { pending = null; });
  return pending;
}

export function createServer() {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Cache-Control', 'no-store');
    if (req.headers.origin || req.headers['sec-fetch-site'] === 'cross-site') {
      res.writeHead(403).end('{"error":"ORIGIN_DENIED"}'); return;
    }
    if (req.url === '/health' && req.method === 'GET') {
      res.end(JSON.stringify({reachable: true, attestation_ready: !!cached && expires > Date.now()})); return;
    }
    if (req.url !== '/get_pot' || req.method !== 'POST') {
      res.writeHead(404).end('{"error":"NOT_FOUND"}'); return;
    }
    try { res.end(JSON.stringify(await session())); }
    catch { res.writeHead(503).end('{"error":"POT_UNAVAILABLE"}'); }
  });
}

if (process.argv[1] && import.meta.url === new URL('file://' + process.argv[1]).href) {
  createServer().listen(8080, '0.0.0.0');
}
