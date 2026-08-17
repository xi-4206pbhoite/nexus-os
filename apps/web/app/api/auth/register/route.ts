import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  // Fields are named, not spread. Spreading would forward anything the caller
  // invented, and the register model accepts `display_name` — a request could
  // otherwise set fields this form never offers.
  return proxyToApi(request, {
    path: '/auth/register',
    method: 'POST',
    body: { email: body.email, password: body.password },
    unavailable: 'Accounts are unavailable right now.',
  })
}
