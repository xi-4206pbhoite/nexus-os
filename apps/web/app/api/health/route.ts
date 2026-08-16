import { NextResponse } from 'next/server'

/**
 * Web liveness, plus a reachability probe for the API.
 *
 * Deliberately reports the API as a separate field rather than folding it into
 * one boolean: "the web app is down" and "the web app is up but cannot reach the
 * API" need different responses, and a single `ok` hides which one happened.
 */

export const dynamic = 'force-dynamic'
export const revalidate = 0

const API_BASE = process.env.NEXUS_API_BASE_URL ?? 'http://127.0.0.1:8000'

type ApiState = 'ok' | 'not_ready' | 'unreachable'

export async function GET() {
  let api: ApiState = 'unreachable'
  let apiDetail: string | null = null

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 2000)
    const res = await fetch(`${API_BASE}/health/ready`, {
      signal: controller.signal,
      cache: 'no-store',
    })
    clearTimeout(timeout)
    api = res.ok ? 'ok' : 'not_ready'
    if (!res.ok) apiDetail = `api returned ${res.status}`
  } catch (err) {
    apiDetail = err instanceof Error ? err.message : 'fetch failed'
  }

  return NextResponse.json(
    { status: 'ok', service: 'nexus-web', api, apiDetail },
    { status: 200, headers: { 'cache-control': 'no-store' } },
  )
}
