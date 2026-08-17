import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The client's only way to answer "am I signed in?" across a page load.
 *
 * `/auth/me` cannot serve this: it requires an active workspace, which a new
 * account does not have. A 401 here means "no session"; anything else is a real
 * fault worth showing.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/auth/session',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}
