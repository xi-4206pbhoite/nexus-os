import { NextResponse } from 'next/server'

/**
 * Server-side proxy for the auth endpoints.
 *
 * Same reasoning as the Preview proxy: the browser never learns the API's
 * address and there is no CORS surface. For auth it buys something further.
 * The session cookie is `httponly` and `SameSite=Lax`, and both properties only
 * hold if the cookie belongs to the origin the browser is actually talking to.
 * Calling the API directly from the page would make every auth request
 * cross-origin, which means CORS with credentials and `SameSite=None` — and
 * `SameSite=None` is precisely the protection the API deliberately relies on
 * (see `app/auth/csrf.py`). Proxying keeps the cookie first-party.
 *
 * Two directions of forwarding, and both matter:
 *
 * - **Upstream**: the browser's `Cookie` header and its `X-CSRF-Token`. Without
 *   the cookie the API cannot resolve the session; without the header its
 *   double-submit check rejects every state-changing call.
 * - **Downstream**: `Set-Cookie`. Building a fresh response drops all upstream
 *   headers, and dropping this one means login appears to succeed while setting
 *   no session at all.
 *
 * This route adds no checks of its own. Every guard — password verification,
 * session resolution, CSRF, membership visibility — lives in the API, and this
 * file must never be mistaken for the place they happen.
 */

const API_BASE = process.env.NEXUS_API_BASE_URL ?? 'http://127.0.0.1:8000'

/**
 * Comfortably above the slowest auth call, well below a hang.
 *
 * Raised from 15s because registration outgrew it. That call now makes roughly
 * eight round trips — insert the account, authenticate, read memberships, create
 * the tenant/workspace/membership, re-read, issue the session, commit — and
 * measured from a development laptop against Neon in `us-east-2` each one costs
 * ~0.5s, with the *first* statement paying ~1.5-5s of connection setup on top.
 * Total: 8-11s, and occasionally past 15s, at which point this aborted a request
 * the API had already completed.
 *
 * That failure was worse than slow. The account and workspace were created, the
 * browser saw a 503, and only the idempotent re-registration path (ADR 0014) made
 * a retry recover. A timeout that fires while the server succeeds is a lie to the
 * client.
 *
 * **This is local-development latency, not production latency.** Deployed, the API
 * sits beside its database and the same request is a few tens of milliseconds. The
 * number here has to accommodate the development setup, because the alternative is
 * that registration cannot be tested locally at all.
 */
const TIMEOUT_MS = 30_000

/**
 * Headers copied from the browser to the API. An allowlist rather than a
 * pass-through: forwarding whatever arrives would let a caller set
 * `X-Forwarded-For` and speak as another address, which the API trusts from this
 * hop.
 */
function upstreamHeaders(request: Request, json: boolean): Headers {
  const headers = new Headers()
  if (json) headers.set('Content-Type', 'application/json')

  const cookie = request.headers.get('cookie')
  if (cookie) headers.set('Cookie', cookie)

  const csrf = request.headers.get('x-csrf-token')
  if (csrf) headers.set('X-CSRF-Token', csrf)

  return headers
}

/**
 * Copies `Set-Cookie` from the API's response.
 *
 * `getSetCookie()` rather than `get('set-cookie')`: login sets two cookies, and
 * `get` collapses them into one comma-joined string that no browser can parse
 * back into two. Cookie values may legitimately contain commas, so splitting is
 * not a fix.
 */
function forwardCookies(from: Response, to: Headers): void {
  for (const cookie of from.headers.getSetCookie()) {
    to.append('set-cookie', cookie)
  }
}

export type ProxyOptions = {
  /** Path on the API, e.g. `/auth/login`. */
  path: string
  method: 'GET' | 'POST'
  /** Body to send. Omit for GET. */
  body?: unknown
  /** Shown if the API cannot be reached at all. */
  unavailable: string
}

export async function proxyToApi(
  request: Request,
  { path, method, body, unavailable }: ProxyOptions,
): Promise<NextResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const upstream = await fetch(`${API_BASE}${path}`, {
      method,
      headers: upstreamHeaders(request, body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: 'no-store',
      // The API sets the cookies; this fetch must not keep them itself.
      redirect: 'manual',
    })

    const headers = new Headers()
    forwardCookies(upstream, headers)
    headers.set('cache-control', 'no-store')

    // 204 carries no body, and giving it one is a protocol error.
    if (upstream.status === 204) {
      return new NextResponse(null, { status: 204, headers })
    }

    const payload = await upstream.json().catch(() => ({ detail: 'Unexpected response.' }))
    return NextResponse.json(payload, { status: upstream.status, headers })
  } catch {
    return NextResponse.json({ detail: unavailable }, { status: 503 })
  } finally {
    clearTimeout(timeout)
  }
}

/** Reads and lightly shapes a JSON body, without validating it. The API does that. */
export async function readJson(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const body = await request.json()
    return body && typeof body === 'object' ? (body as Record<string, unknown>) : null
  } catch {
    return null
  }
}
