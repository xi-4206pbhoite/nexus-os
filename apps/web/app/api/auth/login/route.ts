import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/auth/login',
    method: 'POST',
    body: { email: body.email, password: body.password },
    unavailable: 'Sign-in is unavailable right now.',
  })
}
