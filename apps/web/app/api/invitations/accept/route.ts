import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Accepts an invitation.
 *
 * Only the token is forwarded. There is deliberately no role, department or
 * workspace field to forward — doc 06 §2.2 calls a self-declared role privilege
 * escalation via dropdown, and the way to not have that dropdown is to have
 * nowhere to put its value.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/invitations/accept',
    method: 'POST',
    body: { token: body.token },
    unavailable: 'Cannot reach the setup service right now.',
  })
}
