'use client'

import { useEffect, useState } from 'react'
import { StageRail } from '@/components/onboarding/StageRail'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { departmentLabel } from '@/lib/onboarding-client'
import { Waiting } from '@/components/ui/Waiting'

type Question = {
  key: string
  prompt: string
  why: string
  required: boolean
  assumption_when_unsure: string | null
  /** What is already stored, so returning to the step shows it rather than an
   *  empty form that would overwrite it. Absent against an older API. */
  answer?: string | null
  is_assumption?: boolean
}
type DepartmentOption = { value: string; label?: string; selected: boolean }
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
 *
 * **Nothing here is the boundary.** The two rules this file now enforces —
 * every question answered or explicitly skipped (F2), and at least one
 * department (F1) — are enforced in `app/routes/spine.py` as well, and that is
 * the copy that counts. Disabling a button is how a person is told what is
 * expected; it is never how it is required.
 */
export function OnboardingFlow() {
  const [spine, setSpine] = useState<Spine | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [answers, setAnswers] = useState<Record<string, { value: string; unsure: boolean }>>({})
  const [departments, setDepartments] = useState<string[]>([])
  /** A completed stage the founder has stepped back into, or `null` for
   *  wherever the server says they are. Only ever a *view*: the server still
   *  owns the progress, and every Continue posts to the same endpoint it
   *  always did. */
  const [revisiting, setRevisiting] = useState<string | null>(null)

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
        // Seeded from what is stored. An assumption is seeded as its ticked
        // checkbox rather than as text in the box, because that is what the
        // founder actually chose — and it leaves them one click from replacing
        // it with something they know.
        setAnswers(
          Object.fromEntries(
            s.company_questions
              .filter((q) => q.answer != null)
              .map((q) => [
                q.key,
                q.is_assumption
                  ? { value: '', unsure: true }
                  : { value: q.answer as string, unsure: false },
              ]),
          ),
        )
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
  if (!spine) return <Waiting className="text-ink-500">Loading your progress…</Waiting>

  const { stage } = spine
  // What to render. Normally the server's cursor; a completed stage the founder
  // stepped back into otherwise. `revisiting` is dropped the moment the server
  // hands back new progress, so this never drifts from it for long.
  const showing = revisiting ?? stage.current
  const revisit = (target: string) => {
    setRevisiting(target === stage.current ? null : target)
    setError(null)
  }

  if (stage.finished && revisiting === null) {
    return (
      <div className="flex flex-col gap-6">
        <StageRail
          stages={stage.stages}
          current={stage.current}
          completed={stage.completed}
          labels={LABELS}
          onRevisit={revisit}
        />
        <p className="text-ink-700">
          Setup is done. What NEXUS knows about your company is being assembled from your
          answers and your website.
        </p>
        <WayOut />
      </div>
    )
  }

  // F2's client half. A question counts as answered when it has text *or* the
  // founder ticked the box that names what will be assumed instead — the same
  // rule `resolve_answer` applies, said here first so Continue explains itself
  // rather than failing.
  const unanswered = spine.company_questions.filter((q) => {
    const state = answers[q.key]
    return !state?.unsure && !(state?.value ?? '').trim()
  })

  return (
    <div className="flex flex-col gap-2">
      <StageRail
        stages={stage.stages}
        current={showing}
        completed={stage.completed}
        labels={LABELS}
        onRevisit={revisit}
      />

      {/* Finding F13. The pills were inert, so a founder past a step had no way
          back to correct an answer — which, with F2, meant blank answers were
          unreachable once submitted. Stepping back is a view: the server keeps
          the progress, and saving here re-posts the same stage it always did. */}
      {revisiting !== null ? (
        <p className="mb-4 text-sm text-ink-600">
          You have stepped back to a finished step. Saving updates your answers and returns
          you to{' '}
          <button
            type="button"
            className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2"
            onClick={() => setRevisiting(null)}
          >
            {LABELS[stage.current] ?? stage.current}
          </button>
          .
        </p>
      ) : null}

      {showing === 'company' ? (
        <form
          className="flex flex-col gap-6"
          onSubmit={async (event) => {
            event.preventDefault()
            if (busy || unanswered.length > 0) return
            setBusy(true)
            setError(null)
            try {
              const next = (await post('/api/onboarding/company', {
                answers: spine.company_questions.map((q) => ({
                  key: q.key,
                  value: answers[q.key]?.value ?? null,
                  unsure: answers[q.key]?.unsure ?? false,
                })),
              })) as Stage
              setSpine({ ...spine, stage: next })
              setRevisiting(null)
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

          {/* Finding F2. Five blank boxes used to save, tick the stage
              complete, and store five assumptions the founder had never read —
              because a blank and "not sure yet" were treated as the same
              thing. They are not: one is agreement to a stated assumption, the
              other is an empty form. */}
          {unanswered.length > 0 ? (
            <p className="text-sm text-ink-600">
              {unanswered.length} still to go. Answer each one, or tick{' '}
              <em>Not sure yet</em> to record the assumption it names instead.
            </p>
          ) : null}

          <Button
            type="submit"
            size="lg"
            disabled={busy || unanswered.length > 0}
            icon={busy ? undefined : <ArrowRight />}
          >
            {busy ? 'Saving…' : 'Continue'}
          </Button>
        </form>
      ) : null}

      {showing === 'departments' ? (
        <form
          className="flex flex-col gap-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (busy || departments.length === 0) return
            setBusy(true)
            setError(null)
            try {
              const next = (await post('/api/onboarding/departments', { departments })) as Stage
              setSpine({ ...spine, stage: next })
              setRevisiting(null)
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
                {/* Served by the API, not title-cased here. `capitalize` on the
                    raw key rendered the People department as "Hr" — finding
                    F13, and the same department the dashboard nav had already
                    special-cased into a third spelling. */}
                <span>{d.label ?? departmentLabel(d.value)}</span>
              </label>
            ))}
          </div>

          {/* Finding F1. Continuing with nothing ticked used to be accepted and
              marked complete, and then every one of the seven directors
              appeared anyway — the exact opposite of the promise two paragraphs
              above. The API refuses zero now; this says so before the trip. */}
          {departments.length === 0 ? (
            <p className="text-sm text-ink-600">
              Choose at least one. With none chosen there is nothing for the Chief of Staff
              to read.
            </p>
          ) : null}

          <Button
            type="submit"
            size="lg"
            disabled={busy || departments.length === 0}
            icon={busy ? undefined : <ArrowRight />}
          >
            {busy ? 'Saving…' : 'Continue'}
          </Button>
        </form>
      ) : null}

      {showing === 'review' ? (
        /* Finding F4. This step explained that review is a later phase and then
           offered nothing — the only clickable thing on the page was the logo,
           and a first-run founder had no reason to guess that the dashboard
           they had just been set up for was at a URL nobody had shown them.
           The honesty about being unbuilt was right and stays; what was missing
           was a way out of it. */
        <div className="flex flex-col gap-6">
          <p className="text-ink-700">
            The review gate is Phase 13. Your answers are saved and your departments are
            chosen — there is nothing to review here yet, and a screen pretending otherwise
            would be the mock data this product refuses to ship.
          </p>
          <WayOut />
        </div>
      ) : null}
    </div>
  )
}

/**
 * Where to go from a step that has nothing left to do.
 *
 * Three destinations, because the three things a founder has just earned are
 * their dashboard, the questions that turn each director on, and the documents
 * the brain reads. The last two had no link from anywhere in the flow (F10) and
 * were reachable only by typing a URL.
 */
function WayOut() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button href="/dashboard" size="lg">
        Go to your dashboard
      </Button>
      <Button href="/onboarding/documents" variant="secondary">
        Add documents
      </Button>
      <Button href="/settings" variant="secondary">
        Settings
      </Button>
    </div>
  )
}
