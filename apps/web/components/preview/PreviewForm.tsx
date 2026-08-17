'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
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

/** Whole seconds until `at`, or 0. */
function secondsUntil(at: number) {
  return Math.max(0, Math.ceil((at - Date.now()) / 1000))
}

function formatWait(seconds: number) {
  if (seconds >= 3600) {
    const hours = Math.ceil(seconds / 3600)
    return `${hours} hour${hours === 1 ? '' : 's'}`
  }
  if (seconds >= 60) {
    const minutes = Math.ceil(seconds / 60)
    return `${minutes} minute${minutes === 1 ? '' : 's'}`
  }
  return `${seconds}s`
}

/**
 * Counts down to a timestamp, re-rendering once a second and stopping at zero.
 * The interval only exists while a wait is outstanding.
 */
function useCountdown(until: number | null) {
  const [remaining, setRemaining] = useState(() => (until ? secondsUntil(until) : 0))

  useEffect(() => {
    if (until === null) {
      setRemaining(0)
      return
    }
    setRemaining(secondsUntil(until))
    const id = setInterval(() => {
      const next = secondsUntil(until)
      setRemaining(next)
      if (next === 0) clearInterval(id)
    }, 1000)
    return () => clearInterval(id)
  }, [until])

  return remaining
}

export function PreviewForm() {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })
  // When the rate limiter says to come back. Held as a timestamp rather than a
  // duration so a re-render cannot restart the wait.
  const [retryAt, setRetryAt] = useState<number | null>(null)
  const waiting = useCountdown(retryAt)

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
        // 429 carries a measured wait. Honour it: the button stays disabled
        // until it elapses, so the visitor is told when to come back instead of
        // being invited to retry into the same wall.
        if (response.status === 429) {
          const header = Number(response.headers.get('retry-after'))
          const seconds = Number.isFinite(header) && header > 0 ? header : 60
          setRetryAt(Date.now() + seconds * 1000)
        }
        setState({
          status: 'error',
          // The API's message is written to be safe to show: it never confirms
          // internal network shape to whoever supplied the URL.
          message: payload?.detail ?? 'That address could not be analysed.',
        })
        return
      }
      setRetryAt(null)
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
          disabled={running || waiting > 0 || url.trim().length < 4}
          className="group inline-flex h-14 shrink-0 items-center justify-center gap-2 rounded-full bg-ink-800 px-7 text-[0.975rem] font-medium text-bone-50 shadow-paper transition-all duration-300 ease-out-expo hover:-translate-y-0.5 hover:bg-ink-700 hover:shadow-lift disabled:pointer-events-none disabled:opacity-50"
        >
          {running
            ? 'Analysing…'
            : waiting > 0
              ? `Try again in ${formatWait(waiting)}`
              : 'Analyse my business'}
          {!running && waiting === 0 && (
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
