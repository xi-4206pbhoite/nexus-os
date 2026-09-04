'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import {
  AuthError,
  DomainTakenError,
  registerCompany,
  requestToJoin,
  type JoinOffer,
} from '@/lib/auth-client'
import { useSlowLabel } from '@/lib/slow'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }
  | { status: 'taken'; offer: JoinOffer }
  | { status: 'requested' }

/**
 * Register a company. One step — verification comes later, in Settings.
 *
 * That ordering is D19, and it is the whole reason this screen exists: until
 * P5 a signed-up user had to publish a DNS record before they could see
 * anything at all, so the product's front door was a systems administration
 * task.
 *
 * **The website URL is mandatory** (`doc/11` Q13). It is the first fact NEXUS
 * holds and the input the research run is queued against, so a company without
 * one is a company the product cannot begin to learn.
 */
export function RegisterCompanyForm() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [country, setCountry] = useState('OM')
  const [currency, setCurrency] = useState('OMR')
  const [headcount, setHeadcount] = useState('1-10')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  // Finding F9: company creation measured ~8 s against Neon behind one
  // static word, which reads as a hang on the very first thing a founder does.
  const createLabel = useSlowLabel(busy, 'Create company', 'Creating…', 'Still creating…')

  async function submit(confirmSeparateCompany: boolean) {
    setState({ status: 'submitting' })
    try {
      await registerCompany(
        {
          name: name.trim(),
          website_url: websiteUrl.trim(),
          country,
          reporting_currency: currency,
          headcount_band: headcount,
        },
        { confirmSeparateCompany },
      )
      router.replace('/onboarding')
    } catch (error) {
      // The domain is already held by a company that has proved it. Not an
      // error to apologise for — it is usually the right answer arriving early,
      // because a colleague got here first.
      if (error instanceof DomainTakenError) {
        setState({ status: 'taken', offer: error.offer })
        return
      }
      setState({
        status: 'error',
        message:
          error instanceof AuthError
            ? error.message
            : 'Could not reach the account service. Try again in a moment.',
      })
    }
  }

  if (state.status === 'requested') {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-ink-700">
          Your request is with that company&rsquo;s administrators. You will be able to sign in
          once somebody approves it.
        </p>
      </div>
    )
  }

  if (state.status === 'taken') {
    return (
      <div className="flex flex-col gap-6">
        <div
          role="status"
          className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-3 text-sm text-ink-800"
        >
          {state.offer.detail}
        </div>
        <div className="flex flex-col gap-3">
          <Button
            type="button"
            size="lg"
            icon={<ArrowRight />}
            onClick={async () => {
              try {
                await requestToJoin(websiteUrl.trim())
                setState({ status: 'requested' })
              } catch (error) {
                setState({
                  status: 'error',
                  message:
                    error instanceof AuthError ? error.message : 'Could not send that request.',
                })
              }
            }}
          >
            Ask to join them
          </Button>
          {/* The escape hatch, and it stays a hatch. Two genuinely different
              businesses can share a domain — an agency and its trading arm —
              so this is possible and must be chosen, never defaulted. */}
          <Button
            type="button"
            size="lg"
            variant="secondary"
            onClick={() => void submit(true)}
          >
            This is a different company on the same domain
          </Button>
        </div>
      </div>
    )
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (!busy) void submit(false)
      }}
      noValidate
      className="flex flex-col gap-5"
    >
      {state.status === 'error' ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      <Field label="Company name" value={name} onChange={setName} disabled={busy} />
      <Field
        label="Website"
        value={websiteUrl}
        onChange={setWebsiteUrl}
        disabled={busy}
        placeholder="yourcompany.om"
        hint="Where NEXUS starts learning about you. You can add more URLs later."
      />
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Country" value={country} onChange={setCountry} disabled={busy} />
        <Field
          label="Reporting currency"
          value={currency}
          onChange={setCurrency}
          disabled={busy}
        />
      </div>
      <Field label="Headcount" value={headcount} onChange={setHeadcount} disabled={busy} />

      {/* "In Settings" is now a link, because there is now a Settings
          (finding F3). This sentence, its twin on the page's intro and the
          API's own invitation refusal all named a screen that did not exist. */}
      <p className="text-sm text-ink-500">
        You can start straight away. Proving you own the domain happens in{' '}
        <Link
          href="/settings"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Settings
        </Link>
        , and is what unlocks inviting colleagues and connecting tools.
      </p>

      <Button
        type="submit"
        size="lg"
        disabled={busy || name.trim() === '' || websiteUrl.trim() === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {createLabel}
      </Button>
    </form>
  )
}
