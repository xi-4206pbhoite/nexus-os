import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/connections',
    method: 'GET',
    unavailable: 'Connection options are unavailable right now.',
  })
}
