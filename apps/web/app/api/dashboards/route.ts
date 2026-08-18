import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The directors this caller may open, and where to land them.
 *
 * The filtering happens in the API. This route forwards the cookie; it does not
 * know which departments the caller holds and must never be given the job of
 * deciding, because a list trimmed here would still be reachable by URL.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/dashboards',
    method: 'GET',
    unavailable: 'Cannot reach the dashboard service right now.',
  })
}
