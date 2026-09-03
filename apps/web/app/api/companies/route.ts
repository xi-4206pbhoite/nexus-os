import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Registers a company.
 *
 * Named fields, not a spread — the same rule the register proxy states. Note
 * `confirm_separate_company` in particular: it is the deliberate override for
 * "a company already holds this domain", and forwarding it by accident from an
 * arbitrary body would turn a confirmation into a default.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/companies',
    method: 'POST',
    body: {
      name: body.name,
      website_url: body.website_url,
      country: body.country,
      reporting_currency: body.reporting_currency,
      headcount_band: body.headcount_band,
      confirm_separate_company: body.confirm_separate_company === true,
    },
    unavailable: 'Cannot reach the account service right now.',
  })
}
