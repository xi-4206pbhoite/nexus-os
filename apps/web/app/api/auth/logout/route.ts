import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  // No body. The session comes from the cookie and the CSRF token from the
  // header, both forwarded by the proxy.
  return proxyToApi(request, {
    path: '/auth/logout',
    method: 'POST',
    unavailable: 'Sign-out is unavailable right now.',
  })
}
