'use client'

import { useEffect, useState } from 'react'
import { StageRail } from '@/components/onboarding/StageRail'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'

type Question = {
  key: string
  prompt: string
  why: string
  required: boolean
  assumption_when_unsure: string | null
}
type DepartmentOption = { value: string; selected: boolean }
type Stage = { current: string; completed: string[]; stages: string[]; finished: boolean }
type Spine = {
  stage: Stage
  company_questions: Question[]
  departments: DepartmentOption[]
  recommended: { min: number; max: number }
}

const LABELS: Record<string, string> = {
  company: 'Your company',
  departments: 'Departments',
  review: 'Review',
}

async function post(path: string, body: unknown): Promise<unknown> {
  const csrf = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]*)/)?.[1]
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}),
    },
    body: JSON.stringify(body),
    credentials: 'same-origin',
    cache: 'no-store',
  })
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
  if (!response.ok) {
    throw new AuthError(
      typeof payload?.detail === 'string' ? payload.detail : 'That did not save.',
      response.status,
    )
  }
  return payload
}

/**
 * The resumable multi-stage flow. Replaces the single-page wizard.
 *
 * **The server decides which stage you are on.** The client asks rather than
 * remembering — otherwise a stale tab, a Back button and a second device each
 * hold their own opinion and the last writer wins. There is one answer and the
 * database has it.
 *
 * **Answers are held per stage and only sent on Continue.** Back therefore does
 * not lose anything typed, which was the wizard's worst behaviour: it re-fetched
 * and discarded. Nothing is autosaved mid-keystroke either — a half-typed goal
 * stored as a fact is worse than one not stored at all.
 */
export function OnboardingFlow() {
  const [spine, setSpine] = useState<Spine | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [answers, setAnswers] = useState<Record<string, { value: string; unsure: boolean }>>({})
  const [departments, setDepartments] = useState<string[]>([])

  useEffect(() => {
    let live = true
    fetch('/api/onboarding/state', { credentials: 'same-origin', cache: 'no-store' })
      .then(async (r) => {
        if (r.status === 401 || r.status === 403) throw new AuthError('Sign in first.', r.status)
        return (await r.json()) as Spine
      })
      .then((s) => {
        if (!live) return
        setSpine(s)
        setDepartments(s.departments.filter((d) => d.selected).map((d) => d.value))
      })
      .catch((e: unknown) =>
        setError(e instanceof AuthError ? e.message : 'Could not load your progress.'),
      )
    return () => {
      live = false
    }
  }, [])

  if (error) {
    return (
      <div role="alert" className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600">
        {error}
      </div>
    )
  }
  if (!spine) return <p className="text-ink-500">Loading your progress…</p>

  const { stage } = spine

  if (stage.finished) {
    return (
      <div className="flex flex-col gap-4">
        <StageRail stages={stage.stages} current={stage.current} completed={stage.completed} labels={LABELS} />
        <p className="text-ink-700">
          Setup is done. What NEXUS knows about your company is being assembled from your
          answers and your website.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <StageRail stages={stage.stages} current={stage.current} completed={stage.completed} labels={LABELS} />

      {stage.current === 'company' ? (
        <form
          className="flex flex-col gap-6"
          onSubmit={async (event) => {
            event.preventDefault()
            if (busy) return
            setBusy(true)
            try {
              const next = (await post('/api/onboarding/company', {
                answers: spine.company_questions.map((q) => ({
                  key: q.key,
                  value: answers[q.key]?.value ?? null,
                  unsure: answers[q.key]?.unsure ?? false,
                })),
              })) as Stage
              setSpine({ ...spine, stage: next })
            } catch (e) {
              setError(e instanceof AuthError ? e.message : 'Could not save.')
            } finally {
              setBusy(false)
            }
          }}
        >
          {spine.company_questions.map((q) => {
            const state = answers[q.key] ?? { value: '', unsure: false }
            return (
              <div key={q.key} className="flex flex-col gap-2">
                <label htmlFor={q.key} className="font-medium text-ink-900">
                  {q.prompt}
                </label>
                <p className="text-sm text-ink-500">{q.why}</p>
                <textarea
                  id={q.key}
                  rows={2}
                  value={state.value}
                  disabled={state.unsure || busy}
                  onChange={(e) =>
                    setAnswers({ ...answers, [q.key]: { ...state, value: e.target.value } })
                  }
                  className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 disabled:bg-bone-100 disabled:text-ink-400"
                />
                {q.assumption_when_unsure ? (
                  <label className="flex items-start gap-2 text-sm text-ink-600">
                    <input
                      type="checkbox"
                      checked={state.unsure}
                      disabled={busy}
                      onChange={(e) =>
                        setAnswers({ ...answers, [q.key]: { ...state, unsure: e.target.checked } })
                      }
                      className="mt-1"
                    />
                    {/* The assumption is shown, not hidden. A founder who ticks
                        this is agreeing to something specific, and they can only
                        agree to it if they can read it. */}
                    <span>
                      Not sure yet — <em>{q.assumption_when_unsure}</em>
                    </span>
                  </label>
                ) : null}
              </div>
            )
          })}
          <Button type="submit" size="lg" disabled={busy} icon={busy ? undefined : <ArrowRight />}>
            {busy ? 'Saving…' : 'Continue'}
          </Button>
        </form>
      ) : null}

      {stage.current === 'departments' ? (
        <form
          className="flex flex-col gap-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (busy) return
            setBusy(true)
            try {
              const next = (await post('/api/onboarding/departments', { departments })) as Stage
              setSpine({ ...spine, stage: next })
            } catch (e) {
              setError(e instanceof AuthError ? e.message : 'Could not save.')
            } finally {
              setBusy(false)
            }
          }}
        >
          <p className="text-ink-700">
            Which functions does your company run? Each one you choose gets a director and a
            dashboard; the ones you leave out do not appear at all.
          </p>
          <p className="text-sm text-ink-500">
            Most companies pick {spine.recommended.min} to {spine.recommended.max}. Pick as
            many or as few as are true — the Chief of Staff is always included, because it
            reads the others.
          </p>
          <div className="flex flex-col gap-2">
            {spine.departments.map((d) => (
              <label key={d.value} className="flex items-center gap-2 text-ink-800">
                <input
                  type="checkbox"
                  checked={departments.includes(d.value)}
                  disabled={busy}
                  onChange={(e) =>
                    setDepartments(
                      e.target.checked
                        ? [...departments, d.value]
                        : departments.filter((x) => x !== d.value),
                    )
                  }
                />
                <span className="capitalize">{d.value.replace('_', ' ')}</span>
              </label>
            ))}
          </div>
          <Button type="submit" size="lg" disabled={busy} icon={busy ? undefined : <ArrowRight />}>
            {busy ? 'Saving…' : 'Continue'}
          </Button>
        </form>
      ) : null}

      {stage.current === 'review' ? (
        <p className="text-ink-700">
          The review gate is Phase 13. Your answers are saved and your departments are
          chosen — there is nothing to review here yet, and a screen pretending otherwise
          would be the mock data this product refuses to ship.
        </p>
      ) : null}
    </div>
  )
}
