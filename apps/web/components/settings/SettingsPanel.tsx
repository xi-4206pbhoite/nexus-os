'use client'

import { useCallback, useEffect, useState } from 'react'
import { DomainVerificationCard } from '@/components/settings/DomainVerificationCard'
import { InvitePeople } from '@/components/settings/InvitePeople'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchState, type SpineState } from '@/lib/onboarding-client'
import { fetchCompany, type CurrentCompany } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Settings: the domain, and the people.
 *
 * Finding F3. `/register-company` said twice that proving the domain "happens
 * in Settings"; the invitation refusal said "Settings has the DNS record to
 * add"; and there was no `/settings` route, no import of the verification card
 * that had already been written, and no screen anywhere that sent an
 * invitation. The gate was real and correctly enforced server-side, which is
 * what made the missing screen expensive rather than cosmetic: the entire
 * multi-user half of the product was unreachable from a browser.
 *
 * Two fetches rather than one. The company answers what the domain is and
 * whether it is proved; the onboarding state answers which departments this
 * company runs, which is the list the invite form assigns from. Neither is
 * derivable from the other, and inventing a combined endpoint for one screen
 * would put a view's shape into the API.
 */

type State =
  | { status: 'loading' }
  | { status: 'ready'; company: CurrentCompany; spine: SpineState | null }
  | { status: 'error'; message: string; code: number }

export function SettingsPanel() {
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    const company = await fetchCompany()
    // The department list is a nicety on this screen, not its subject. If it
    // will not load, the domain card and the invite form are still the whole
    // point of being here, so this failure is absorbed rather than raised.
    const spine = await fetchState().catch(() => null)
    return { company, spine }
  }, [])

  useEffect(() => {
    let live = true
    load()
      .then(({ company, spine }) => live && setState({ status: 'ready', company, spine }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the account service. Is the API running?',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })
    return () => {
      live = false
    }
  }, [load])

  if (state.status === 'loading') {
    return <Waiting>Loading your settings…</Waiting>
  }

  if (state.status === 'error') {
    // 401 and 403 both mean "not signed in, or not in a company yet", and both
    // want somewhere to go rather than a sentence to read (finding F7).
    const signedOut = state.code === 401 || state.code === 403
    return (
      <div className="flex max-w-prose flex-col gap-5">
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {signedOut ? 'You need to be signed in, in a company, to open settings.' : state.message}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button href={signedOut ? '/login?next=/settings' : '/account'}>
            {signedOut ? 'Sign in' : 'Your account'}
          </Button>
        </div>
      </div>
    )
  }

  const { company, spine } = state
  const running = (spine?.departments ?? [])
    .filter((d) => d.selected)
    .map((d) => ({ value: d.value, label: d.label ?? d.value }))

  return (
    <div className="flex flex-col gap-8">
      <dl className="overflow-hidden rounded-2xl border border-ink-100 bg-white px-5 py-4">
        <dt className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">Company</dt>
        <dd className="mt-1 text-ink-900">
          {company.name}{' '}
          <span className="text-ink-500">
            — {company.domain}
            {company.domain_verified ? ' · verified' : ' · not yet verified'}
          </span>
        </dd>
      </dl>

      <DomainVerificationCard
        domain={company.domain}
        verified={company.domain_verified}
        mayAdminister={company.may_administer}
        // Re-read rather than assumed. The card knows its own check passed; the
        // fact that unlocks the invite form is the workspace's, and the
        // workspace is what the API will consult when the invitation is sent.
        onVerified={() => {
          void load()
            .then(({ company: fresh, spine: freshSpine }) =>
              setState({ status: 'ready', company: fresh, spine: freshSpine }),
            )
            .catch(() => undefined)
        }}
      />

      <InvitePeople
        verified={company.domain_verified}
        mayAdminister={company.may_administer}
        departments={running}
      />
    </div>
  )
}
