import { NextResponse } from 'next/server'
import { clientAddress } from '@/lib/client-address'

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
        // The visitor's address, taken from the platform's own header and
        // NEVER from the request the browser sent.
        //
        // This used to forward `request.headers.get('x-forwarded-for')`
        // verbatim. The API trusts this header from this proxy, so anyone could
        // send `X-Forwarded-For: 1.2.3.4`, change it per request, and land in a
        // fresh rate-limit bucket every time — defeating the per-IP limit
        // completely and letting one machine spend the entire daily crawl
        // budget for every visitor.
        //
        // `request.ip` and `x-real-ip` are set by the serving platform and are
        // not settable by the client. If neither is present the header is
        // omitted, and the API falls back to its direct peer — a shared bucket,
        // which is the safe failure.
        ...clientAddress(request),
      },
      body: JSON.stringify({ url: url.trim() }),
      signal: controller.signal,
      cache: 'no-store',
    })
    clearTimeout(timeout)

    const payload = await upstream.json().catch(() => ({ detail: 'Analysis failed.' }))

    // Forward `Retry-After`. Constructing a fresh response drops every upstream
    // header, and dropping this one is not cosmetic: the API measures the wait
    // and the browser is the only thing that can show it, so losing it here is
    // what turned a precise limit into "please try again later" with no idea
    // whether that meant seconds or a day.
    const headers = new Headers()
    const retryAfter = upstream.headers.get('retry-after')
    if (retryAfter) headers.set('Retry-After', retryAfter)

    return NextResponse.json(payload, { status: upstream.status, headers })
  } catch {
    return NextResponse.json(
      { detail: 'The analysis service is unavailable right now.' },
      { status: 503 },
    )
  }
}
