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

/**
 * Generous on purpose. `/health/ready` reaches the database, and since that
 * became a managed Postgres in another region (ADR 0008) a round trip costs
 * ~450ms rather than the sub-millisecond of a loopback socket. The previous 2s
 * budget reported the API as `unreachable` while it was answering correctly —
 * a false negative that is worse than a slow answer, because it points at the
 * wrong component.
 */
const API_TIMEOUT_MS = 6000

type ApiState = 'ok' | 'not_ready' | 'timeout' | 'unreachable'

export async function GET() {
  let api: ApiState = 'unreachable'
  let apiDetail: string | null = null

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  try {
    const res = await fetch(`${API_BASE}/health/ready`, {
      signal: controller.signal,
      cache: 'no-store',
    })
    api = res.ok ? 'ok' : 'not_ready'
    if (!res.ok) apiDetail = `api returned ${res.status}`
  } catch (err) {
    // `timeout` and `unreachable` are separate states for the same reason `api`
    // is separate from `status`: they call for different responses. Nothing
    // listening on the port means the API is down. A timeout against a
    // serverless database that suspends when idle (ADR 0008) usually means the
    // compute is waking up and the next call will succeed — reporting that as
    // `unreachable` sends an operator looking for a dead process.
    if (controller.signal.aborted) {
      api = 'timeout'
      apiDetail = `no response within ${API_TIMEOUT_MS}ms — the database may be waking`
    } else {
      apiDetail = err instanceof Error ? err.message : 'fetch failed'
    }
  } finally {
    clearTimeout(timeout)
  }

  return NextResponse.json(
    { status: 'ok', service: 'nexus-web', api, apiDetail },
    { status: 200, headers: { 'cache-control': 'no-store' } },
  )
}
