import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/invitations',
    method: 'GET',
    unavailable: 'Cannot reach the setup service right now.',
  })
}

/**
 * Creates an invitation.
 *
 * The role travels from the inviter's form to the API, which is the whole point
 * of doc 06 §2.2 — it is set here and copied at acceptance, never supplied by
 * the person accepting. Whether this caller may grant it is decided by the API.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/invitations',
    method: 'POST',
    body: { email: body.email, role: body.role, departments: body.departments },
    unavailable: 'Cannot reach the setup service right now.',
  })
}
