import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The BFF proxy, tested where Playwright cannot reach.
 *
 * This layer exists so the browser never holds an API token and never talks to
 * the API directly. Everything it does is a *security* behaviour rather than a
 * visible one, which means the journey passes whether or not it is right: a
 * proxy that forwarded the wrong cookies, or collapsed two `Set-Cookie` headers
 * into one, would still render every page.
 *
 * So these assert the things that fail silently.
 */

const upstream = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.stubGlobal('fetch', upstream)
  upstream.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
})

function apiResponse(body: unknown, init: { status?: number; cookies?: string[] } = {}): Response {
  const headers = new Headers()
  for (const cookie of init.cookies ?? []) headers.append('set-cookie', cookie)
  return {
    status: init.status ?? 200,
    headers: {
      ...headers,
      getSetCookie: () => init.cookies ?? [],
    } as unknown as Headers,
    json: async () => body,
  } as Response
}

function request(headers: Record<string, string> = {}): Request {
  return new Request('http://localhost:3001/api/whatever', {
    method: 'POST',
    headers,
  })
}

async function proxy() {
  return (await import('@/lib/auth-proxy')).proxyToApi
}

describe('proxyToApi', () => {
  it('forwards the session cookie, so the API can identify the caller', async () => {
    upstream.mockResolvedValue(apiResponse({ ok: true }))
    await (await proxy())(request({ cookie: 'nexus_session=abc' }), {
      path: '/auth/session',
      method: 'GET',
      unavailable: 'down',
    })

    expect(upstream.mock.calls[0][1].headers.get('Cookie')).toBe('nexus_session=abc')
  })

  it('forwards the CSRF header, which is the whole point of having one', async () => {
    upstream.mockResolvedValue(apiResponse({ ok: true }))
    await (await proxy())(request({ 'x-csrf-token': 'a-token' }), {
      path: '/companies',
      method: 'POST',
      body: { name: 'X' },
      unavailable: 'down',
    })

    expect(upstream.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('a-token')
  })

  it('returns both Set-Cookie headers, not one comma-joined string', async () => {
    // Login sets two cookies. `headers.get('set-cookie')` collapses them into a
    // single comma-joined value that no browser can parse back into two — and
    // splitting on commas is not a fix, because a cookie value may contain one.
    // The symptom is a login that appears to work and has no CSRF cookie.
    upstream.mockResolvedValue(
      apiResponse(
        { user_id: 'u' },
        { cookies: ['nexus_session=a; Path=/; HttpOnly', 'nexus_csrf=b; Path=/'] },
      ),
    )

    const response = await (await proxy())(request(), {
      path: '/auth/login',
      method: 'POST',
      body: {},
      unavailable: 'down',
    })

    const cookies = response.headers.getSetCookie()
    expect(cookies).toHaveLength(2)
    expect(cookies[0]).toContain('nexus_session=a')
    expect(cookies[1]).toContain('nexus_csrf=b')
  })

  it('passes the API status through rather than flattening it', async () => {
    // A 404 that becomes a 500 turns "no dashboard here for you" into "the
    // product is broken", and the UI branches on exactly that distinction.
    upstream.mockResolvedValue(apiResponse({ detail: 'Not found' }, { status: 404 }))

    const response = await (await proxy())(request(), {
      path: '/dashboards/hr',
      method: 'GET',
      unavailable: 'down',
    })

    expect(response.status).toBe(404)
  })

  it('never caches a response', async () => {
    // Every one of these carries workspace data. A cached dashboard is one
    // customer's numbers served to whoever asks next.
    upstream.mockResolvedValue(apiResponse({ ok: true }))

    const response = await (await proxy())(request(), {
      path: '/dashboards',
      method: 'GET',
      unavailable: 'down',
    })

    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it('turns an unreachable API into 503 with the caller\'s own message', async () => {
    // Not a 500. The API being down is not the same as the API failing, and the
    // UI says something different for each.
    upstream.mockRejectedValue(new Error('ECONNREFUSED'))

    const response = await (await proxy())(request(), {
      path: '/dashboards',
      method: 'GET',
      unavailable: 'Cannot reach the dashboard service right now.',
    })

    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({
      detail: 'Cannot reach the dashboard service right now.',
    })
  })

  it('gives a 204 no body, because a body on a 204 is a protocol error', async () => {
    upstream.mockResolvedValue(apiResponse(null, { status: 204 }))

    const response = await (await proxy())(request(), {
      path: '/auth/logout',
      method: 'POST',
      unavailable: 'down',
    })

    expect(response.status).toBe(204)
    expect(await response.text()).toBe('')
  })
})
