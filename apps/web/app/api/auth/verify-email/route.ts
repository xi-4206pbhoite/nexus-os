import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Consumes the token from a verification email.
 *
 * A POST, not a GET, even though it is reached by clicking a link. The page at
 * `/verify-email` reads the token from the query string and calls this — so the
 * token is spent by an action the page takes, not by anything that fetches the
 * URL. Mail scanners, link previewers and prefetchers all issue GETs, and a
 * single-use token consumed by one of those is burned before the recipient ever
 * clicks.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/auth/verify-email',
    method: 'POST',
    body: { token: body.token },
    unavailable: 'Cannot reach the account service right now.',
  })
}
