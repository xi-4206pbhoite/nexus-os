import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Spends the reset token and sets the new password.
 *
 * Named fields, not a spread. The API's model takes `token` and `password`, and
 * forwarding whatever arrived would let a caller reach fields this form never
 * offers — the same rule the register proxy states.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/auth/password-reset/confirm',
    method: 'POST',
    body: { token: body.token, password: body.password },
    unavailable: 'Cannot reach the account service right now.',
  })
}
