import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Saves a wizard step.
 *
 * `answers` is forwarded and nothing else. Spreading the body would let a
 * caller invent fields — and the one field that must never exist on an answer
 * is a scope, since the classification has to come from the catalogue rather
 * than from the same request as the data (doc 06 §2.5).
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/onboarding/answers',
    method: 'POST',
    body: { answers: body.answers },
    unavailable: 'Cannot reach the setup service right now.',
  })
}
