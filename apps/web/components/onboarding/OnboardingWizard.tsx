'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { ConnectStep } from '@/components/onboarding/ConnectStep'
import { QuestionField } from '@/components/onboarding/QuestionField'
import { TeamStep } from '@/components/onboarding/TeamStep'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  completeSetup,
  fetchCatalogue,
  saveAnswers,
  type Catalogue,
  type Completion,
  type Question,
} from '@/lib/onboarding-client'

/**
 * The onboarding wizard.
 *
 * The order is doc 04 §5's, which is the whole argument of that document: value
 * first, then questions justified by what was shown, connections and documents
 * next, team last.
 *
 * - **the audit** (§5 stage 1) is M7, and is still a named gap here. The free
 *   Preview audit on the landing page is the same engine running on the
 *   outside-in half;
 * - **connections** (§5 stage 4) exist as a step, and connect nothing. M10 is
 *   unbuilt and both its prerequisites are open decisions, so `ConnectStep`
 *   shows what each tool would unlock and states plainly that none is attached.
 *   A Connect button there would be a control that lies.
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

const DEPARTMENTS_KEY = 'departments_run'
/** The one answer that changes which *other* questions exist. */

const STEPS: Step[] = [
  {
    id: 'basics',
    title: 'The basics',
    // Deliberately not a count. It said "Four questions" and went stale the moment
    // the catalogue grew — a number in prose beside a list rendered from data is a
    // claim nothing keeps true.
    blurb: 'Who you are, and enough to run your first audit. Everything else waits.',
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
    id: 'departments',
    title: 'Your departments',
    // The API decides what appears here, not this component. It serves a
    // department's questions only when the company selected that department *and*
    // the caller can reach it (doc 08 §0), so an unselected department is absent
    // rather than a row of disabled inputs implying something was forgotten.
    //
    // Consequence worth knowing: this step is legitimately empty until
    // `departments_run` is answered in the previous step, which is why it renders
    // its own empty state rather than assuming it has fields.
    blurb:
      'Five questions each, and only for the departments you run. These are the ones no crawl and no connector can answer.',
    stage: 'department',
  },
  {
    id: 'connect',
    title: 'Your tools',
    blurb:
      'What each connection is worth, and why none of them is attached yet. Telling you the first part is the only honest half of this step.',
    stage: 'connect',
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
  const [finished, setFinished] = useState<Completion | null>(null)

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
        completion={finished}
        onRevisit={() => {
          setFinished(null)
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

        // Selecting departments changes which questions exist.
        //
        // The catalogue is fetched once on mount, and the server decides the
        // department blocks from the *stored* `departments_run`. So without this,
        // ticking Sales and Operations and pressing continue lands on a departments
        // step reading "nothing to ask here" — the questions only appear after a
        // reload, which nobody does mid-form. Found by walking the flow in a browser;
        // every API-level test passed throughout, because the API was right.
        //
        // Re-fetched only when that answer is in the batch: this is a round trip, and
        // paying it on every step to cover one is the wrong trade.
        if (toSave.some((answer) => answer.key === DEPARTMENTS_KEY)) {
          const refreshed = await fetchCatalogue()
          setState({ status: 'ready', catalogue: refreshed })
        }
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
      // The last step is where setup actually becomes complete. Until this call the
      // wizard only set a local flag, so nothing was recorded, no notification went
      // out, and a reload started the form again.
      //
      // A failure here keeps the user on the last step with the reason, rather than
      // showing a finished screen for something that did not finish. The API refuses
      // with the list of answers still missing, which is exactly what the user needs
      // to see.
      setSaving(true)
      try {
        setFinished(await completeSetup())
      } catch (caught) {
        setSaveError(
          caught instanceof AuthError ? caught.message : 'Could not finish setting up.',
        )
      } finally {
        setSaving(false)
      }
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
      {step.id === 'connect' ? <ConnectStep /> : null}
      {step.id === 'departments' && questions.length === 0 ? <NoDepartments /> : null}

      {questions.length > 0 ? (
        // One column until xl, two beyond it. Full width made a name field span the
        // screen; pairing short questions uses that space instead of stretching one
        // input across it. `QuestionField` decides which of them can share a row —
        // a paragraph, an option list or an ordering takes the whole one.
        //
        // `items-start` matters: without it, grid rows stretch every cell to the
        // tallest in the row, so a select would grow to match a neighbour with two
        // lines of help text under it.
        <div className="grid items-start gap-x-12 rounded-2xl border border-ink-100 bg-white px-6 py-6 shadow-paper xl:grid-cols-2 xl:gap-y-8">
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
/**
 * The departments step with nothing in it.
 *
 * Reachable in two honest ways, and one of them is not an error: a read-only
 * viewer sees no writable questions, and a department manager sees only their own
 * department's block — which may not be among the ones the company selected.
 *
 * Without this the step rendered a header promising "five questions each" followed
 * by empty space and a Continue button, which reads as broken. Never a blank (I10),
 * and that rule applies to a wizard step as much as to a dashboard tile.
 */
function NoDepartments() {
  return (
    <div className="rounded-2xl border border-ink-100 bg-white px-6 py-6 shadow-paper">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-500">
        Nothing to ask here
      </p>
      <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
        These questions follow the departments your company runs. Either none are
        selected yet — go back a step to choose them — or the ones selected belong to
        a department you do not hold, in which case somebody in that department
        answers them rather than you.
      </p>
    </div>
  )
}

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

function Finished({
  completion,
  onRevisit,
}: {
  completion: Completion
  onRevisit: () => void
}) {
  // Resolved from membership by the API, never from the `department` answer — a
  // stated role is a fact about the person and membership is what authorises, so
  // landing on the answer would 404 for anyone whose two disagree.
  const href = completion.landing_department
    ? `/dashboard/${completion.landing_department}`
    : '/dashboard'

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

      {completion.email_detail ? (
        <div className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-3">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            No email sent
          </p>
          {/* Said plainly rather than swallowed: a notification that silently did not
              arrive is the kind of thing people discover a week later. */}
          <p className="mt-2 text-sm leading-relaxed text-ink-700">{completion.email_detail}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-4">
        <Button href={href} size="lg">
          Go to your dashboard
        </Button>
        <Button type="button" onClick={onRevisit} variant="secondary" size="lg">
          Change an answer
        </Button>
      </div>
    </div>
  )
}
