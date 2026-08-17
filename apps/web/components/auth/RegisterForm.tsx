'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, MIN_PASSWORD_LENGTH, register } from '@/lib/auth-client'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'submitted' }
  | { status: 'error'; message: string }

export function RegisterForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  const tooShort = password !== '' && password.length < MIN_PASSWORD_LENGTH

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || tooShort) return

    setState({ status: 'submitting' })
    try {
      await register(email.trim(), password)
      setState({ status: 'submitted' })
      setPassword('')
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the account service. Is the API running?'
      setState({ status: 'error', message })
    }
  }

  // The API answers identically whether or not the address was already taken —
  // a distinct "already registered" reply would confirm which addresses hold
  // accounts here. So this screen cannot say "account created", because it does
  // not know that, and must not imply it.
  if (state.status === 'submitted') {
    return (
      <div className="flex flex-col gap-5">
        <div className="rounded-xl border border-steel-300 bg-steel-100 px-4 py-4">
          <p className="font-display text-lg text-ink-900">Check your email</p>
          <p className="mt-2 text-sm leading-relaxed text-ink-700">
            If <span className="font-medium">{email.trim()}</span> is not already
            registered, an account now exists for it. We deliberately give the same
            answer either way, so this page cannot be used to discover who has an
            account here.
          </p>
        </div>

        <div className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-4">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            Not yet built
          </p>
          <p className="mt-2 text-sm leading-relaxed text-ink-700">
            <span className="font-medium">No email is actually sent yet.</span> Delivery
            is not wired up, so there is nothing to click. You can sign in with the
            password you just chose — email verification is not required to do so.
          </p>
        </div>

        <Button href="/login" size="lg" icon={<ArrowRight />} className="w-full">
          Continue to sign in
        </Button>
      </div>
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

      <p className="text-sm text-ink-500">
        Already have an account?{' '}
        <Link
          href="/login"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Sign in
        </Link>
        .
      </p>
    </form>
  )
}
