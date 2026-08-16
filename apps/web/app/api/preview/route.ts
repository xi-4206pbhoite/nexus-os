import { NextResponse } from 'next/server'

/**
 * Proxies the Preview audit to the API.
 *
 * Server-side on purpose. The browser never learns the API's address, there is
 * no CORS surface to configure, and — most importantly — the rate limiter sees
 * a request from this server rather than from the visitor's browser, so the
 * per-IP bucket is applied where we control it.
 *
 * Note the API is what enforces every guard here: SSRF validation, the rate
 * limits and the Preview scope all live behind this call. This route adds no
 * checks of its own and must never be mistaken for the place they happen.
 */

export const dynamic = 'force-dynamic'

const API_BASE = process.env.NEXUS_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function POST(request: Request) {
  let url: unknown
  try {
    const body = await request.json()
    url = body?.url
  } catch {
    return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })
  }

  if (typeof url !== 'string' || url.trim().length < 4) {
    return NextResponse.json({ detail: 'Enter a website address.' }, { status: 400 })
  }

  try {
    const controller = new AbortController()
    // Comfortably above the API's own crawl budget, so a timeout here means
    // the API is unreachable rather than the site being slow.
    const timeout = setTimeout(() => controller.abort(), 30_000)

    const upstream = await fetch(`${API_BASE}/preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Pass the visitor's address so the API's per-IP bucket is meaningful.
        // The API only trusts this because this proxy is a known hop.
        'X-Forwarded-For': request.headers.get('x-forwarded-for') ?? '',
      },
      body: JSON.stringify({ url: url.trim() }),
      signal: controller.signal,
      cache: 'no-store',
    })
    clearTimeout(timeout)

    const payload = await upstream.json().catch(() => ({ detail: 'Analysis failed.' }))
    return NextResponse.json(payload, { status: upstream.status })
  } catch {
    return NextResponse.json(
      { detail: 'The analysis service is unavailable right now.' },
      { status: 503 },
    )
  }
}
