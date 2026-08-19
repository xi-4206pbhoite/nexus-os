'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, MIN_PASSWORD_LENGTH, register } from '@/lib/auth-client'

type State = { status: 'idle' } | { status: 'submitting' } | { status: 'error'; message: string }

export function RegisterForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  const tooShort = password !== '' && password.length < MIN_PASSWORD_LENGTH

  // There is no interstitial any more. Registration returns a session, so the
  // only honest next screen is the flow itself.
  //
  // What used to be here was a "Check your email" panel plus a second panel
  // admitting no email is sent — two screens of explanation standing between the
  // user and a product they had just signed up for. Both are now false: the API
  // signs them in.
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || tooShort) return

    setState({ status: 'submitting' })
    try {
      await register(email.trim(), password)
      // Replace rather than push: the sign-up form should not sit in history
      // behind an authenticated page.
      router.replace('/onboarding')
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the account service. Is the API running?'
      setState({ status: 'error', message })
      // Only the password. A 401 here means the address is already registered
      // under a different one, and retyping a correct email is pure friction.
      setPassword('')
    }
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
        hint="Use an address on your company's domain — your workspace is named from it, and it is how you will verify the domain later."
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
