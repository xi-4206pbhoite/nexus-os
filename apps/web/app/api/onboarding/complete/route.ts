import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Mark setup complete.
 *
 * No body: the API decides everything from the session. A request that carried a
 * workspace id would be a request that could complete somebody else's setup, and the
 * proxy forwards whatever it is given — so the safe version is to give it nothing.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/complete',
    method: 'POST',
    unavailable: 'Could not finish setting up right now.',
  })
}
