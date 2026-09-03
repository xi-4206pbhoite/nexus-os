import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** The selected departments. Chief of Staff is never sent — it is automatic. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/onboarding/departments',
    method: 'POST',
    body: { departments: Array.isArray(body.departments) ? body.departments : [] },
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
