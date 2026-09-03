import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Ask to join the company that already holds a domain. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/join-requests',
    method: 'POST',
    body: { website_url: body.website_url, message: body.message ?? null },
    unavailable: 'Cannot reach the account service right now.',
  })
}

/** The pending queue, for an Owner or Executive. */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/join-requests',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}
