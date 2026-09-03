'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { QuestionField } from '@/components/onboarding/QuestionField'
import { TeamStep } from '@/components/onboarding/TeamStep'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchCatalogue, saveAnswers, type Catalogue, type Question } from '@/lib/onboarding-client'

/**
 * The onboarding wizard.
 *
 * The order is doc 04 §5's, which is the whole argument of that document: value
 * first, then questions justified by what was shown, connections and documents
 * next, team last. Two of its stages are not this milestone's to build, and the
 * screen says so rather than staging a version of them —
 *
 * - **the audit** (§5 stage 1) is M7. It was once previewed on the landing page
 *   by the same engine; Phase 2 retired that entry point (`doc/11` Q1), so the
 *   audit now exists nowhere until this stage builds it;
 * - **connections** (§5 stage 4) are M10.
 *
 * Skipping straight from the basics to the money questions is *worse* than the
 * intended flow, and pretending otherwise with a mock audit would be worse
 * still: a fabricated score is exactly the failure the product's central claim
 * exists to prevent. So the gap is named where it falls.
 *
 * One rule here is not cosmetic. Brief recipients come after the team step
 * because recipients must be workspace users (doc 06 §4.10) — and the API
 * refuses a non-member regardless of what this component renders.
 */

type Step = {
  id: string
  title: string
  blurb: string
  /** Which catalogue stage this step submits, if any. */
  stage?: Question['stage']
}

const STEPS: Step[] = [
  {
    id: 'basics',
    title: 'The basics',
    blurb: 'Four questions. Everything else waits until there is something to show you.',
    stage: 'pass_1',
  },
  {
    id: 'audit',
    title: 'Your audit',
    blurb: 'What we would normally show you here, and why we are not going to pretend.',
  },
  {
    id: 'context',
    title: 'What we cannot work out for ourselves',
    blurb:
      'Your site tells us what you sell. It does not tell us what you are trying to do, or what a deal is worth.',
    stage: 'pass_2',
  },
  {
    id: 'team',
    title: 'Your team',
    blurb: 'You choose each person’s role. They never choose their own.',
  },
  {
    id: 'brief',
    title: 'The morning brief',
    blurb: 'Who receives it — chosen from the people in your workspace.',
    stage: 'post_invite',
  },
]

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; catalogue: Catalogue }

export function OnboardingWizard() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [index, setIndex] = useState(0)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)

  useEffect(() => {
    let live = true
    fetchCatalogue()
      .then((catalogue) => {
        if (!live) return
        // Seed the form with what is already stored, so revisiting the wizard
        // shows the answers rather than a blank form that would overwrite them.
        const stored: Record<string, unknown> = {}
        for (const question of catalogue.questions) {
          if (question.value !== null && question.value !== undefined) {
            stored[question.key] = question.value
          }
        }
        setDraft(stored)
        setState({ status: 'ready', catalogue })
      })
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the setup service. Is the API running?',
        })
      })
    return () => {
      live = false
    }
  }, [])

  const step = STEPS[index]

  const questions = useMemo(() => {
    if (state.status !== 'ready' || !step.stage) return []
    return state.catalogue.questions.filter((q) => q.stage === step.stage)
  }, [state, step])

  if (state.status === 'loading') {
    return <p className="font-mono text-sm text-ink-500">Loading your setup…</p>
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

  const { catalogue } = state

  if (finished) {
    return (
      <Finished
        onRevisit={() => {
          setFinished(false)
          setIndex(0)
        }}
      />
    )
  }

  const missing = questions.filter(
    (q) => q.required && q.writable && isEmpty(draft[q.key]),
  )

  async function advance() {
    setSaveError(null)

    const toSave = questions
      .filter((q) => q.writable && !isEmpty(draft[q.key]))
      .map((q) => ({ key: q.key, value: draft[q.key] }))

    if (toSave.length > 0) {
      setSaving(true)
      try {
        await saveAnswers(toSave)
      } catch (caught) {
        setSaveError(
          caught instanceof AuthError ? caught.message : 'Could not save those answers.',
        )
        setSaving(false)
        return
      }
      setSaving(false)
    }

    if (index === STEPS.length - 1) {
      setFinished(true)
      return
    }
    setIndex(index + 1)
  }

  return (
    <div className="flex flex-col gap-8">
      <Progress index={index} />

      {!catalogue.can_administer ? (
        <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-4">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            Read-only
          </p>
          <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
            Workspace setup is run by an owner or an executive. You can see what has
            been answered, at your own scope — some answers belong to a department and
            will simply not be here.
          </p>
        </div>
      ) : null}

      <header>
        <h2 className="font-display text-title font-medium text-ink-900">{step.title}</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {step.blurb}
        </p>
      </header>

      {step.id === 'audit' ? <AuditGap /> : null}
      {step.id === 'team' ? <TeamStep /> : null}

      {questions.length > 0 ? (
        <div className="rounded-2xl border border-ink-100 bg-white px-6 py-6 shadow-paper">
          {questions.map((question) => (
            <QuestionField
              key={question.key}
              question={question}
              value={draft[question.key]}
              onChange={(value) => setDraft((prev) => ({ ...prev, [question.key]: value }))}
              members={catalogue.members}
              disabled={saving}
            />
          ))}
        </div>
      ) : null}

      {saveError ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {saveError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-4">
        <Button
          type="button"
          onClick={advance}
          disabled={saving || missing.length > 0}
          size="lg"
        >
          {saving
            ? 'Saving…'
            : index === STEPS.length - 1
              ? 'Finish setup'
              : 'Save and continue'}
        </Button>

        {index > 0 ? (
          <button
            type="button"
            onClick={() => setIndex(index - 1)}
            disabled={saving}
            className="text-sm font-medium text-ink-600 underline decoration-ink-200 underline-offset-2 hover:text-ink-900"
          >
            Back
          </button>
        ) : null}

        {missing.length > 0 ? (
          <p className="text-sm text-clay-600">
            Still needed: {missing.map((q) => q.prompt).join(', ')}
          </p>
        ) : null}
      </div>
    </div>
  )
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

function Progress({ index }: { index: number }) {
  return (
    <ol className="flex flex-wrap gap-2">
      {STEPS.map((step, position) => (
        <li
          key={step.id}
          aria-current={position === index ? 'step' : undefined}
          className={`rounded-full px-3 py-1.5 font-mono text-2xs uppercase tracking-[0.1em] ${
            position === index
              ? 'bg-ink-800 text-bone-50'
              : position < index
                ? 'bg-bone-200 text-ink-600'
                : 'border border-ink-100 text-ink-400'
          }`}
        >
          {step.title}
        </li>
      ))}
    </ol>
  )
}

/**
 * The honest version of doc 04 §5 stage 1.
 *
 * Doc 04's central finding is that the audit is the only moment that earns the
 * right to ask for the rest. It is not built inside a workspace yet, and a
 * placeholder scoreboard here would be a fabricated number on the screen — the
 * one thing the product sells on never doing.
 */
function AuditGap() {
  return (
    <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
        Not built yet — and why you are seeing this instead
      </p>
      <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
        This is where your audit belongs: brand, SEO, customer experience and AI
        readiness, scored from your own site, with the departments that need connected
        data shown as locked rather than as zeroes. It is a later milestone, and we are
        not going to put a placeholder score here — a made-up number is the one thing
        this product is built not to do.
      </p>
      <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
        The same engine already runs on the landing page and needs no account.{' '}
        <Link
          href="/#top"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Run it on your site
        </Link>
        , then come back — the questions after this one will make more sense with it in
        front of you.
      </p>
    </div>
  )
}

function Finished({ onRevisit }: { onRevisit: () => void }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-ink-100 bg-white px-6 py-6 shadow-paper">
        <h2 className="font-display text-title font-medium text-ink-900">
          That is everything we can use yet
        </h2>
        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Your answers are stored with their scope attached — the deal size as a Sales
          fact, the marketing budget as a Finance one — so they are visible to the
          people those departments include and to nobody else. Nothing you typed
          changed what you or anyone else can see; that comes from the workspace.
        </p>
        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Your department&rsquo;s dashboard is next. It is a placeholder: every offering on
          it is real and says what it needs, and none of them is built yet. That is
          stated on each tile rather than dressed up as an empty widget.
        </p>
      </div>

      <div className="flex flex-wrap gap-4">
        <Button href="/dashboard" size="lg">
          Go to your dashboard
        </Button>
        <Button type="button" onClick={onRevisit} variant="secondary" size="lg">
          Change an answer
        </Button>
      </div>
    </div>
  )
}
