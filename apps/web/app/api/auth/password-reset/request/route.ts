import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Asks for a reset link.
 *
 * The API answers identically whether or not the address has an account, and
 * this route must not undo that. It adds no branch of its own — no "we found
 * you", no different status — because a difference introduced at this hop is
 * just as complete an enumeration oracle as one in the API.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/auth/password-reset/request',
    method: 'POST',
    body: { email: body.email },
    unavailable: 'Cannot reach the account service right now.',
  })
}
