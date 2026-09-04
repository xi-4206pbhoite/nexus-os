'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, MIN_PASSWORD_LENGTH, login, register } from '@/lib/auth-client'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  // Registered, and now signing in on the same page rather than sending the
  // founder to `/login` to start again.
  | { status: 'ready'; message?: string }
  | { status: 'signing-in' }
  | { status: 'error'; message: string }

export function RegisterForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  const signingIn = state.status === 'signing-in'
  const tooShort = password !== '' && password.length < MIN_PASSWORD_LENGTH

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || tooShort) return

    setState({ status: 'submitting' })
    try {
      await register(email.trim(), password)
      setState({ status: 'ready' })
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the account service. Is the API running?'
      setState({ status: 'error', message })
    }
  }

  async function onSignIn(event: React.FormEvent) {
    event.preventDefault()
    if (signingIn) return

    setState({ status: 'signing-in' })
    try {
      await login(email.trim(), password)
      // Replace rather than push: the sign-up page must not sit in history
      // behind an authenticated page, where Back would show a stale form.
      router.replace('/account')
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the sign-in service. Is the API running?'
      setState({ status: 'ready', message })
      setPassword('')
    }
  }

  // **Signing in here rather than auto-issuing a session on register.**
  //
  // The API answers identically whether or not the address was already taken,
  // because a distinct "already registered" reply confirms which addresses hold
  // accounts here. Handing back a session on registration would leak the same
  // fact through a side door: a new address would land in the app and a taken
  // one would not, which is the oracle again with extra steps.
  //
  // So this screen cannot say "account created" — it does not know that. What it
  // can do is the thing the founder actually wants, which is to get on with it
  // without a round trip through the inbox.
  if (state.status === 'ready' || signingIn) {
    return (
      <form onSubmit={onSignIn} noValidate className="flex flex-col gap-5">
        {state.status === 'ready' && state.message ? (
          <div
            role="alert"
            className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
          >
            {state.message}
          </div>
        ) : null}

        <div className="rounded-xl border border-steel-300 bg-steel-100 px-4 py-4">
          <p className="font-display text-lg text-ink-900">Sign in to continue</p>
          <p className="mt-2 text-sm leading-relaxed text-ink-700">
            If <span className="font-medium">{email.trim()}</span> was not already
            registered, an account now exists for it. We give the same answer either
            way, so this page cannot be used to discover who has an account here.
          </p>
        </div>

        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          disabled={signingIn}
          revealable
          // Not "the password you just chose". For an address that already had
          // an account, `/register` discards what was typed — deliberately, so
          // the endpoint cannot be used to discover who has an account — and
          // that person's password is the one they set the first time.
          hint="The one you just chose, or your existing password if this address already had an account."
        />

        <Button
          type="submit"
          size="lg"
          disabled={signingIn || password === ''}
          icon={signingIn ? undefined : <ArrowRight />}
          className="mt-1 w-full"
        >
          {signingIn ? 'Signing you in…' : 'Sign in'}
        </Button>

        {/* Finding F6. This said "we have emailed you a confirmation link",
            which is untrue for an address that already had an account — a
            known address is deliberately sent no second verification email, by
            the same anti-enumeration rule the panel above states. Phrased to
            be true either way, without saying which way it went. */}
        <p className="text-sm leading-relaxed text-ink-500">
          If the account is new, a confirmation link is on its way to{' '}
          <span className="font-medium">{email.trim()}</span>. You do not need it to carry
          on — it proves the address is yours, which is what lets you claim your company
          domain by email later.
        </p>
      </form>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.status === 'error' ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      <Field
        label="Work email"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="email"
        placeholder="you@yourcompany.om"
        hint="Use an address on your company's domain — it is how you will claim the domain later."
        disabled={busy}
      />

      <Field
        label="Password"
        type="password"
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        disabled={busy}
        revealable
        hint={`At least ${MIN_PASSWORD_LENGTH} characters. A passphrase beats a short complicated one.`}
        error={tooShort ? `${MIN_PASSWORD_LENGTH - password.length} more characters needed.` : undefined}
      />

      <Button
        type="submit"
        size="lg"
        disabled={busy || tooShort || email.trim() === '' || password === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {busy ? 'Creating your account…' : 'Create account'}
      </Button>

      {/* No "Already have an account?" link here — finding F13. `AuthShell`
          renders one in its footer for every auth page, and this put a second
          copy a few pixels above it. */}
    </form>
  )
}
