import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Start a domain claim. One of the three proxies C3 named as missing. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/domains',
    method: 'POST',
    body: { domain: body.domain, method: body.method },
    unavailable: 'Cannot reach the account service right now.',
  })
}
