'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, login } from '@/lib/auth-client'

type State = { status: 'idle' } | { status: 'submitting' } | { status: 'error'; message: string }

export function LoginForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return

    setState({ status: 'submitting' })
    try {
      await login(email.trim(), password)
      // Replace rather than push: the sign-in page should not sit in history
      // behind an authenticated page, where Back would show a stale form.
      router.replace('/account')
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the sign-in service. Is the API running?'
      setState({ status: 'error', message })
      // Clear only the password. Retyping an email you already got right is
      // pure friction, and the failure says nothing about which field was wrong.
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
        disabled={busy}
      />

      <Field
        label="Password"
        type="password"
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
        disabled={busy}
        revealable
      />

      <Button
        type="submit"
        size="lg"
        disabled={busy || email.trim() === '' || password === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {busy ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  )
}
