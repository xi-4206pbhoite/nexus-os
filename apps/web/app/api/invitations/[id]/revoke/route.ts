import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Withdraws an invitation.
 *
 * The id is checked against a uuid shape before it reaches the upstream path.
 * It is the only value in this app that is interpolated into an API URL, and an
 * unchecked segment there would let a caller append their own path — reaching
 * an endpoint this route was never meant to expose.
 */
export async function POST(request: Request, { params }: { params: { id: string } }) {
  if (!UUID.test(params.id)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/invitations/${params.id}/revoke`,
    method: 'POST',
    unavailable: 'Cannot reach the setup service right now.',
  })
}
