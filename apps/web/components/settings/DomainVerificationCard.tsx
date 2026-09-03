'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'

type Claim = { claim_id: string; domain: string; instruction: string; state: string }
type State =
  | { status: 'idle' }
  | { status: 'working' }
  | { status: 'claimed'; claim: Claim }
  | { status: 'verified' }
  | { status: 'error'; message: string }

async function post(path: string, body?: unknown): Promise<unknown> {
  const csrf = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]*)/)?.[1]
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}),
    },
    body: JSON.stringify(body ?? {}),
    credentials: 'same-origin',
    cache: 'no-store',
  })
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
  if (!response.ok) {
    throw new AuthError(
      typeof payload?.detail === 'string' ? payload.detail : 'That did not work.',
      response.status,
    )
  }
  return payload
}

/**
 * Proving the domain — after registration, not before it.
 *
 * D19 moved this here. It used to stand between a signed-up user and the whole
 * product: no workspace existed without a verified domain, so every scoped
 * endpoint answered 403 until somebody published a DNS record.
 *
 * **The card says what verification unlocks.** A step with no stated purpose
 * reads as bureaucracy, and the honest answer — that it is what stops somebody
 * else registering your domain and inviting your colleagues — is also the most
 * persuasive one.
 */
export function DomainVerificationCard({
  domain,
  verified,
}: {
  domain: string
  verified: boolean
}) {
  const [state, setState] = useState<State>(verified ? { status: 'verified' } : { status: 'idle' })

  if (state.status === 'verified') {
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg font-medium text-ink-900">Domain verified</h2>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-700">
          <strong>{domain}</strong> is proved yours. You can invite colleagues and connect tools.
        </p>
      </section>
    )
  }

  return (
    <section className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
      <h2 className="font-display text-lg font-medium text-ink-900">Verify {domain}</h2>
      <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
        Everything works without this except the two things that reach beyond you:{' '}
        <strong>inviting colleagues</strong> and <strong>connecting tools</strong>. Proving the
        domain is what stops somebody else registering it and inviting your team.
      </p>

      {state.status === 'error' ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      {state.status === 'claimed' ? (
        <div className="mt-4 flex flex-col gap-3">
          <p className="text-[0.95rem] text-ink-800">{state.claim.instruction}</p>
          <Button
            type="button"
            className="w-fit"
            onClick={async () => {
              const claim = state.claim
              setState({ status: 'working' })
              try {
                const checked = (await post(`/api/domains/${claim.claim_id}/check`)) as Claim
                // A check that has not found the record yet is not a failure —
                // DNS propagates on its own schedule, and telling somebody their
                // record is wrong when it is merely young sends them to edit a
                // correct record.
                setState(
                  checked.state === 'verified'
                    ? { status: 'verified' }
                    : {
                        status: 'error',
                        message:
                          'Not visible yet. DNS can take a few minutes to propagate — try again shortly.',
                      },
                )
              } catch (error) {
                setState({
                  status: 'error',
                  message: error instanceof AuthError ? error.message : 'Could not check.',
                })
              }
            }}
          >
            Check now
          </Button>
        </div>
      ) : (
        <div className="mt-4">
          <Button
            type="button"
            disabled={state.status === 'working'}
            onClick={async () => {
              setState({ status: 'working' })
              try {
                const claim = (await post('/api/domains', {
                  domain,
                  method: 'dns_txt',
                })) as Claim
                setState({ status: 'claimed', claim })
              } catch (error) {
                setState({
                  status: 'error',
                  message:
                    error instanceof AuthError ? error.message : 'Could not start verification.',
                })
              }
            }}
          >
            {state.status === 'working' ? 'Working…' : 'Start verification'}
          </Button>
        </div>
      )}
    </section>
  )
}
