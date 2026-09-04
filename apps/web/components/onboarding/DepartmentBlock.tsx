'use client'

import { useEffect, useState } from 'react'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { Waiting } from '@/components/ui/Waiting'
import { useSlowLabel } from '@/lib/slow'

type BlockQuestion = {
  key: string
  prompt: string
  why: string
  answer_type: string
  consumed_by: string
  answered: boolean
  proposed: boolean
  answer: string | null
}
type Block = {
  department: string
  may_answer: boolean
  binds: boolean
  questions: BlockQuestion[]
}

async function send(department: string, answers: { key: string; value: string }[]) {
  const csrf = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]*)/)?.[1]
  const response = await fetch(`/api/onboarding/departments/${department}/block`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}),
    },
    body: JSON.stringify({ answers }),
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
  return payload as Block
}

/**
 * One department's questions (P7).
 *
 * **The server says whether you may answer and whether it binds**; this renders
 * what it was told rather than deciding. A client that worked it out itself
 * would be reimplementing an authority rule, and the version that matters is
 * the one it gets wrong — a Contributor shown a form that binds, or a Manager
 * shown read-only for their own department.
 *
 * A Contributor sees the same form with different words. Their answers become
 * **proposals** waiting for a manager, and saying so is not a demotion: it is
 * the difference between "your answer was ignored" and "your answer is waiting",
 * and only one of those is true.
 */
export function DepartmentBlock({ department }: { department: string }) {
  const [block, setBlock] = useState<Block | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})

  /** What the server holds, as the starting point for the boxes.
   *
   * An ANSWERED badge beside an empty box is not a resumable form (Q28): the
   * badge was the only evidence an answer existed, saving again overwrote it
   * silently, and correcting one meant remembering it. `edited` holds only what
   * this visit changed, so an untouched question submits exactly what is
   * already stored rather than a copy the render happened to make. */
  const stored = (b: Block): Record<string, string> =>
    Object.fromEntries(b.questions.filter((q) => q.answer !== null).map((q) => [q.key, q.answer!]))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Finding F9: saving a department block measured ~10 s against Neon.
  // The idle label depends on whether this caller's answers bind, so the
  // block has to be loaded before it is known — `block?.binds` rather than
  // `block.binds`, because hooks cannot sit behind the early return below.
  const saveLabel = useSlowLabel(
    busy,
    block?.binds === false ? 'Propose answers' : 'Save answers',
    'Saving…',
    'Still saving…',
  )

  useEffect(() => {
    let live = true
    fetch(`/api/onboarding/departments/${department}/block`, {
      credentials: 'same-origin',
      cache: 'no-store',
    })
      .then(async (r) => {
        if (!r.ok) throw new AuthError('That block is not available.', r.status)
        return (await r.json()) as Block
      })
      .then((b) => live && setBlock(b))
      .catch((e: unknown) =>
        setError(e instanceof AuthError ? e.message : 'Could not load that block.'),
      )
    return () => {
      live = false
    }
  }, [department])

  if (error) {
    return (
      <div role="alert" className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600">
        {error}
      </div>
    )
  }
  if (!block) return <Waiting className="text-ink-500">Loading these questions…</Waiting>

  const outstanding = block.questions.filter((q) => !q.answered).length

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-title font-medium capitalize text-ink-900">
          {block.department.replace('_', ' ')}
        </h1>
        <p className="mt-2 text-ink-600">
          {outstanding === 0
            ? 'Every question here is answered.'
            : `${outstanding} of ${block.questions.length} still to answer. Each one turns something on.`}
        </p>
        {block.may_answer && outstanding > 0 ? (
          <p className="mt-2 text-sm text-ink-500">
            Answer what you know. Leaving one blank is fine — it stays unanswered, and its
            director keeps showing it as the thing that turns that number on.
          </p>
        ) : null}
        {block.may_answer && !block.binds ? (
          <p className="mt-3 rounded-xl border border-gold-300 bg-gold-100 px-4 py-3 text-sm text-ink-800">
            Your answers here are <strong>proposals</strong>. A manager or owner confirms them
            before they become facts for the whole department — because a department fact binds
            everyone in it.
          </p>
        ) : null}
        {!block.may_answer ? (
          <p className="mt-3 rounded-xl border border-ink-100 bg-bone-100 px-4 py-3 text-sm text-ink-600">
            These are read-only for you. A department&rsquo;s questions are answered by its
            manager, or by an owner.
          </p>
        ) : null}
      </div>

      <form
        className="flex flex-col gap-6"
        onSubmit={async (event) => {
          event.preventDefault()
          if (busy || !block.may_answer) return
          // A blank is not an answer, and the API refuses one. Skipping a
          // question means leaving it out of the request entirely — blocks are
          // skippable (doc 11 stage 4), and its director keeps saying so.
          const answers = Object.entries(values)
            .filter(([, v]) => v.trim() !== '')
            .map(([key, value]) => ({ key, value: value.trim() }))
          if (answers.length === 0) return
          setBusy(true)
          try {
            const saved = await send(department, answers)
            setBlock(saved)
            setValues(stored(saved))
          } catch (e) {
            setError(e instanceof AuthError ? e.message : 'Could not save.')
          } finally {
            setBusy(false)
          }
        }}
      >
        {block.questions.map((q) => (
          <div key={q.key} className="flex flex-col gap-2">
            <label htmlFor={q.key} className="font-medium text-ink-900">
              {q.prompt}
              {q.answered ? (
                <span className="ml-2 rounded-full bg-steel-100 px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-steel-700">
                  {q.proposed ? 'proposed' : 'answered'}
                </span>
              ) : null}
            </label>
            {/* `why` comes from the bank, where every question states what it
                changes. Doc 04 §5: a question a founder cannot see the point of
                is a question they resent answering. */}
            <p className="text-sm text-ink-500">{q.why}</p>
            <textarea
              id={q.key}
              rows={2}
              disabled={busy || !block.may_answer}
              value={values[q.key] ?? q.answer ?? ''}
              onChange={(e) => setValues({ ...values, [q.key]: e.target.value })}
              className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 disabled:bg-bone-100 disabled:text-ink-400"
            />
          </div>
        ))}

        {block.may_answer ? (
          <Button type="submit" size="lg" disabled={busy} icon={busy ? undefined : <ArrowRight />}>
            {saveLabel}
          </Button>
        ) : null}
      </form>
    </div>
  )
}
