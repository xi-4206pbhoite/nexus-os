import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The five company answers.
 *
 * `unsure` is forwarded per answer and is not a nicety: it is what turns a blank
 * into a *stated assumption* rather than a null, which is the distinction the
 * whole stage exists to preserve.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  const answers = Array.isArray(body.answers) ? body.answers : []
  return proxyToApi(request, {
    path: '/onboarding/company',
    method: 'POST',
    body: {
      answers: answers.map((a: Record<string, unknown>) => ({
        key: a.key,
        value: a.value ?? null,
        unsure: a.unsure === true,
      })),
    },
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
