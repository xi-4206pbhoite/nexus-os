import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * The company itself, and proving the domain it claims.
 *
 * The invitation calls are deliberately **not** here — they already live in
 * `onboarding-client.ts`, and a second copy is how two callers of one endpoint
 * start disagreeing about its shape. This file holds only what had no home:
 * reading the current company, and the two domain-claim calls that `/settings`
 * is built on.
 */

export type CurrentCompany = {
  workspace_id: string
  name: string
  domain: string
  website_url: string | null
  domain_verified: boolean
  role: string
  may_administer: boolean
}

/** The four ways to prove a domain, as `app/connectors/domain_check.py` names them. */
export type ClaimMethod = 'dns_txt' | 'file' | 'email' | 'manual'

export type DomainClaim = {
  claim_id: string
  domain: string
  method: ClaimMethod
  strength: string
  state: string
  instruction: string
  evidence?: string | null
}

async function request(path: string, init?: { method: 'POST'; body?: unknown }): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (init?.body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    method: init?.method ?? 'GET',
    headers,
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'That did not work.'), response.status)
  }
  return payload
}

export async function fetchCompany(): Promise<CurrentCompany> {
  return (await request('/api/companies/current')) as CurrentCompany
}

export async function startDomainClaim(domain: string, method: ClaimMethod): Promise<DomainClaim> {
  return (await request('/api/domains', {
    method: 'POST',
    body: { domain, method },
  })) as DomainClaim
}

export async function checkDomainClaim(claimId: string): Promise<DomainClaim> {
  return (await request(`/api/domains/${encodeURIComponent(claimId)}/check`, {
    method: 'POST',
  })) as DomainClaim
}
