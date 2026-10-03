import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The caller's own company — its domain, and whether that domain is proved.
 *
 * What `/settings` is built on. Nothing else served these two facts, which is
 * part of why the screen three other screens point at did not exist (F3).
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/companies/current',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}
