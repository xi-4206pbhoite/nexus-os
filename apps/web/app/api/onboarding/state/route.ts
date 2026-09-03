import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Everything the flow needs to render itself, in one call.
 *
 * One request rather than three: a stage rail that renders before it knows
 * which stages are done shows the wrong one and then corrects itself, and a
 * founder reads that as the product losing their place.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/state',
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
