import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The onboarding catalogue, with whatever of it the caller may see.
 *
 * The API decides that — which questions are writable, which stored answers are
 * readable at the caller's scope, and whether the workspace roster is included
 * at all. This route forwards the cookie and nothing more.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/questions',
    method: 'GET',
    unavailable: 'Cannot reach the setup service right now.',
  })
}
