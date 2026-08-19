'use client'

import { useEffect, useState } from 'react'
import { type Connection, fetchConnections } from '@/lib/onboarding-client'

/**
 * Doc 04 §5 stage 4, with no connector behind it.
 *
 * The tempting version of this screen is a grid of provider logos with Connect
 * buttons. There is nothing for them to do — M10 is unbuilt and both of its
 * prerequisites are open decisions (D3 Google credentials, D10 which CRM) — so a
 * button here would be a control that lies, and a "Connected" pill would be the
 * fabricated-capability failure the product exists to avoid.
 *
 * What is honest, and is what this renders: each tool, how many capabilities it
 * would actually unlock, which directors those sit under, and that none of it is
 * attached. The counts come from the API, which derives them from the same offering
 * data the director pages render — so this screen and a locked tile cannot disagree
 * about what a connection is worth.
 *
 * The multi-select that records which tools the company *has* is an ordinary
 * catalogue question (`tools_available`) rendered by the wizard above this. It
 * stores intent and connects nothing, and its own `why` says so.
 */
export function ConnectStep() {
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'error'; message: string }
    | { status: 'ready'; connections: Connection[] }
  >({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchConnections()
      .then((payload) => {
        if (!cancelled) setState({ status: 'ready', connections: payload.connections })
      })
      .catch(() => {
        // Named, never silent. A step that fails to load its own content and shows
        // nothing is indistinguishable from a step with nothing in it.
        if (!cancelled)
          setState({
            status: 'error',
            message: 'Could not load the connection options. The rest of setup still works.',
          })
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-500">Loading…</p>
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

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-4">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          Nothing connects yet
        </p>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
          There is no connector built, so there is no button here that would do
          anything. Telling you what each one is worth is the part we can do honestly
          — the counts below are the real capabilities each tool unlocks, read from
          the same specification the dashboards use.
        </p>
      </div>

      <ul className="grid gap-3 sm:grid-cols-2">
        {state.connections.map((tool) => (
          <li
            key={tool.source}
            className="rounded-2xl border border-ink-100 bg-white px-5 py-4 shadow-paper"
          >
            <div className="flex items-baseline justify-between gap-3">
              <p className="font-display text-[1.05rem] text-ink-900">{tool.label}</p>
              <span className="shrink-0 rounded-full bg-ink-50 px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.1em] text-ink-500">
                Not connected
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-ink-700">
              Would unlock <span className="font-medium">{tool.unlocks}</span>{' '}
              {tool.unlocks === 1 ? 'capability' : 'capabilities'}
              {tool.departments.length > 0 ? <> in {tool.departments.join(', ')}</> : null}.
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}
