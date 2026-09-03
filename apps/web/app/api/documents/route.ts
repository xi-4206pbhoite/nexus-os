import { proxyToApi, proxyUpload } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** What this caller has uploaded. The API scopes it to them, not the workspace. */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/documents',
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}

/**
 * The upload itself, forwarded as multipart.
 *
 * No validation here beyond forwarding. The size and count limits live in the
 * API, and a second copy in this proxy would be a second opinion that can
 * disagree with the first — the client already predicts the refusal from the
 * same numbers, and predicting is not enforcing.
 */
export async function POST(request: Request) {
  return proxyUpload(request, {
    path: '/documents',
    unavailable: 'Cannot reach the document service right now.',
  })
}
