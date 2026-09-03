import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Three named documents per department this company runs (Q35). */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/documents/asks',
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}
