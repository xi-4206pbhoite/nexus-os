import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * One department's question block.
 *
 * The department comes from the path and is forwarded as-is. It is not a
 * capability: the API decides whether this caller may answer it, and returns
 * `may_answer` either way — so a department name somebody guesses gets them a
 * read-only block at most, never a write.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ department: string }> },
) {
  const { department } = await params
  return proxyToApi(request, {
    path: `/onboarding/departments/${encodeURIComponent(department)}/block`,
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ department: string }> },
) {
  const { department } = await params
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  const answers = Array.isArray(body.answers) ? body.answers : []
  return proxyToApi(request, {
    path: `/onboarding/departments/${encodeURIComponent(department)}/block`,
    method: 'POST',
    body: { answers: answers.map((a: Record<string, unknown>) => ({ key: a.key, value: a.value })) },
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
