'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchDashboards, type Dashboards } from '@/lib/dashboard-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Sends a person to their own director.
 *
 * Which one is decided by the API from their **membership**, not from the
 * department they typed during setup. The wizard's answer is a stated fact about
 * a person; the membership is what authorises, and landing someone on a page
 * their scope refuses would produce a 404 immediately after finishing setup.
 *
 * `replace` rather than `push`: this route is a redirect, and leaving it in the
 * history means Back lands here and bounces the person forward again.
 */

type State =
  | { status: 'loading' }
  | { status: 'nowhere'; dashboards: Dashboards }
  | { status: 'error'; message: string }

export function DashboardLanding() {
  const router = useRouter()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    fetchDashboards()
      .then((dashboards) => {
        if (!live) return
        if (dashboards.landing) {
          router.replace(dashboards.landing)
          return
        }
        setState({ status: 'nowhere', dashboards })
      })
      .catch((caught: unknown) => {
        if (!live) return
        // Finding F7. A signed-out visitor used to get the API's own
        // `"Not authenticated"` rendered verbatim in a box with nothing
        // clickable in it. The refusal was right; leaving somebody on a dead
        // page was not, and session expiry is the ordinary way into this state.
        if (caught instanceof AuthError && (caught.status === 401 || caught.status === 403)) {
          router.replace('/login?next=/dashboard')
          return
        }
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the dashboard service. Is the API running?',
        })
      })
    return () => {
      live = false
    }
  }, [router])

  if (state.status === 'loading') {
    return <Waiting>Finding your dashboard…</Waiting>
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

  // No department, so no director. A Viewer is the ordinary case: doc 06 §2.3
  // gives them company-wide material and no L3 at all, and inventing a landing
  // page for them would mean putting them in a department nobody assigned.
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          No department dashboard for you
        </p>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
          Each director&rsquo;s page belongs to a department, and your account is not in
          one. That is the normal state for a viewer — you can see company-wide material
          and nothing that belongs to a single department.
        </p>
        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
          If you expected a dashboard, an owner sets which department an account is in
          when they invite it.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button href="/account" size="lg">
          Your account
        </Button>
        <Link
          href="/onboarding"
          className="self-center text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Workspace setup
        </Link>
      </div>
    </div>
  )
}
