import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Re-run the claim's check.
 *
 * The claim id comes from the path and is forwarded as-is. It is not a secret
 * and not a capability: the API re-loads the claim scoped to the caller, so an
 * id belonging to somebody else resolves to nothing there rather than being
 * filtered here.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ claimId: string }> },
) {
  const { claimId } = await params
  return proxyToApi(request, {
    path: `/domains/${encodeURIComponent(claimId)}/check`,
    method: 'POST',
    unavailable: 'Cannot reach the account service right now.',
  })
}
