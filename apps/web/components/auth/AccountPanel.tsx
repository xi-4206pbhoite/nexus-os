'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError, fetchSession, logout, type SessionState } from '@/lib/auth-client'

/**
 * What a signed-in person can currently see.
 *
 * Which is: their account, and an honest account of why there is nothing else
 * yet. A workspace requires a verified domain, so a new account has none — and
 * the rest of the product is scoped to a workspace. Rendering an empty dashboard
 * would imply the data is missing; naming the gate explains it.
 */

type State =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'ready'; session: SessionState }
  | { status: 'error'; message: string }

export function AccountPanel() {
  const router = useRouter()
  const [state, setState] = useState<State>({ status: 'loading' })
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    let live = true
    fetchSession()
      .then((session) => {
        if (!live) return
        setState(session ? { status: 'ready', session } : { status: 'anonymous' })
      })
      .catch((error: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            error instanceof AuthError
              ? error.message
              : 'Could not reach the account service. Is the API running?',
        })
      })
    return () => {
      live = false
    }
  }, [])

  async function onSignOut() {
    setSigningOut(true)
    try {
      await logout()
    } catch {
      // Sign-out is best-effort from here. The button must never trap someone on
      // this page, so a failed call still returns them to a signed-out view —
      // the session cookie is cleared by the API, and if the call never landed
      // the session simply expires on its own.
    }
    router.replace('/login')
  }

  if (state.status === 'loading') {
    return <p className="font-mono text-sm text-ink-500">Loading your account…</p>
  }

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
      >
        {state.message}
      </div>
    )
  }

  if (state.status === 'anonymous') {
    return (
      <div className="flex flex-col gap-5">
        <p className="text-[0.95rem] text-ink-700">
          You are not signed in. Your session may have expired — they last 12 hours.
        </p>
        <Button href="/login" size="lg" className="w-fit">
          Sign in
        </Button>
      </div>
    )
  }

  const { session } = state
  // One company per account (`doc/11` §3.2), so this is a single row rather
  // than a list, and there is no switcher — `POST /auth/workspace` was deleted
  // in P3 because there is never a second workspace to switch to.
  //
  // `session.workspaces` stays an array. The schema is many-to-many by choice
  // (see `app/domain/membership.py`), so the wire format that carries zero or
  // one entry today can carry more if doc 06 §2.1's agency case is revived.
  const company = session.workspaces[0] ?? null

  return (
    <div className="flex flex-col gap-8">
      {/* ── Identity ── */}
      <dl className="grid gap-px overflow-hidden rounded-2xl border border-ink-100 bg-ink-100 sm:grid-cols-2">
        <div className="bg-white px-5 py-4">
          <dt className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
            Signed in as
          </dt>
          <dd className="mt-1 break-all font-mono text-sm text-ink-800">{session.user_id}</dd>
        </div>
        <div className="bg-white px-5 py-4">
          <dt className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
            Company
          </dt>
          <dd className="mt-1 font-mono text-sm text-ink-800">
            {session.active_workspace_id ?? 'None'}
          </dd>
        </div>
      </dl>

      {/* ── Workspaces ── */}
      <section>
        <h2 className="font-display text-lg font-medium text-ink-900">Your company</h2>

        {company ? (
          <>
            <div className="mt-3 flex items-center justify-between gap-4 rounded-xl border border-ink-100 bg-white px-4 py-3 shadow-paper">
              <span className="font-medium text-ink-900">{company.name}</span>
              <span className="rounded-full bg-bone-200 px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] text-ink-600">
                {company.role}
              </span>
            </div>

            <div className="mt-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
              <p className="font-display text-lg text-ink-900">Set up your workspace</p>
              <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-700">
                Tell NEXUS about your business, and invite the people who work in it.
                Each answer is stored at its own scope — the deal size as a Sales fact,
                the marketing budget as a Finance one — and the wizard shows you which
                before you type it.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button href="/dashboard">Go to your dashboard</Button>
                <Button href="/onboarding" variant="secondary">
                  Workspace setup
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="mt-3 rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
            <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
              Nothing here yet — and why
            </p>
            <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
              A workspace only exists once someone has <strong>proved they control the
              domain</strong>. Nobody can create one for a domain they do not own — not
              even by typing it — which is the same rule that stops a competitor claiming
              yours.
            </p>
            <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-700">
              Claiming a domain needs a DNS TXT record or a file published on the site.
              That flow has no screen yet, so it currently runs through the API:{' '}
              <code className="rounded border border-ink-200 bg-white px-1.5 py-0.5 font-mono text-[0.8rem] text-ink-800">
                POST /domains
              </code>
              .
            </p>
          </div>
        )}
      </section>

      {/* ── What is not built ── */}
      <section>
        <h2 className="font-display text-lg font-medium text-ink-900">
          What is not built yet
        </h2>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-600">
          The seven directors have pages, and every widget on them says what it will show
          and what it needs — but <strong>none of them is built</strong>, so none carries a
          number. The Company Brain and the morning brief that would fill them are later
          milestones, and the scoped retrieval layer they depend on comes first, because
          adding permissions after the features is how these products leak.
        </p>
        <p className="mt-3 text-[0.95rem] text-ink-600">
          There was a free audit here that needed no account. Phase 2 retired it: it
          crawled any address a visitor typed, which meant anyone could be handed an
          analysis of a company they do not own. The same engine now runs inside
          onboarding, on the domain you have proved you control.
        </p>
      </section>

      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={onSignOut}
          disabled={signingOut}
          className="w-fit"
        >
          {signingOut ? 'Signing out…' : 'Sign out'}
        </Button>
      </div>
    </div>
  )
}
