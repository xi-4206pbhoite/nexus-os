'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { ArrowRight } from '@/components/ui/Button'
import { PreviewResult, type PreviewAudit } from '@/components/preview/PreviewResult'

/**
 * The landing page's primary action (doc 06 §1): "Analyse my business — enter
 * your website." The URL is captured before registration and becomes the first
 * fact NEXUS holds.
 *
 * What comes back is deliberately a *reduced* audit. Everything with
 * intelligence value about a third party — the competitor list above all — sits
 * behind domain verification, because anyone can type a competitor's URL.
 */

type State =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; audit: PreviewAudit }
  | { status: 'error'; message: string }

export function PreviewForm() {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (url.trim().length < 4) return

    setState({ status: 'running' })
    try {
      const response = await fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      const payload = await response.json()

      if (!response.ok) {
        setState({
          status: 'error',
          // The API's message is written to be safe to show: it never confirms
          // internal network shape to whoever supplied the URL.
          message: payload?.detail ?? 'That address could not be analysed.',
        })
        return
      }
      setState({ status: 'done', audit: payload as PreviewAudit })
    } catch {
      setState({ status: 'error', message: 'Something went wrong. Please try again.' })
    }
  }

  const running = state.status === 'running'

  return (
    <div className="w-full">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="preview-url" className="sr-only">
          Your website address
        </label>
        <div className="relative flex-1">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 font-mono text-2xs text-ink-400"
          >
            https://
          </span>
          <input
            id="preview-url"
            type="text"
            inputMode="url"
            autoComplete="url"
            placeholder="your-company.om"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={running}
            className="h-14 w-full rounded-full border border-bone-300 bg-white pl-[4.75rem] pr-5 text-[0.975rem] text-ink-800 shadow-paper transition-colors placeholder:text-ink-300 focus:border-steel-400 disabled:opacity-60"
          />
        </div>
        <button
          type="submit"
          disabled={running || url.trim().length < 4}
          className="group inline-flex h-14 shrink-0 items-center justify-center gap-2 rounded-full bg-ink-800 px-7 text-[0.975rem] font-medium text-bone-50 shadow-paper transition-all duration-300 ease-out-expo hover:-translate-y-0.5 hover:bg-ink-700 hover:shadow-lift disabled:pointer-events-none disabled:opacity-50"
        >
          {running ? 'Analysing…' : 'Analyse my business'}
          {!running && (
            <ArrowRight className="transition-transform duration-300 group-hover:translate-x-0.5" />
          )}
        </button>
      </form>

      <AnimatePresence mode="wait">
        {running && (
          <motion.p
            key="running"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mt-4 flex items-center gap-2 text-sm text-ink-500"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-gold-400 opacity-75 motion-safe:animate-pulse-ring" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-gold-500" />
            </span>
            Reading your site. This takes a few seconds.
          </motion.p>
        )}

        {state.status === 'error' && (
          <motion.p
            key="error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            role="alert"
            className="mt-4 rounded-xl border border-clay-300 bg-clay-100/60 px-4 py-3 text-sm text-ink-700"
          >
            {state.message}
          </motion.p>
        )}
      </AnimatePresence>

      {state.status === 'done' && <PreviewResult audit={state.audit} />}
    </div>
  )
}
