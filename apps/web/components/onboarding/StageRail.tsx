'use client'

/**
 * Where you are, and what you have already finished.
 *
 * The rail exists because the flow is resumable (Q28) and resumability is
 * useless if it is invisible: a founder who returns needs to see that the work
 * they did last time survived, or they will redo it.
 *
 * A completed stage is shown as completed even when it is not the current one —
 * that is the whole message. `aria-current="step"` marks the live one so a
 * screen reader gets the same information the styling carries.
 *
 * **A completed stage is clickable.** Finding F13: every pill was an inert
 * `<li>`, so once past a step there was no way back to correct an answer.
 * Combined with F2 that was the one with teeth — a founder who had submitted
 * blank answers could not reach them again. Only *completed* stages are
 * offered, and only backwards: the current stage is where you already are, and
 * a stage you have not reached is not a shortcut, since the server decides the
 * order and would put you straight back.
 */
export function StageRail({
  stages,
  current,
  completed,
  labels,
  onRevisit,
}: {
  stages: string[]
  current: string
  completed: string[]
  labels: Record<string, string>
  /** Called with a completed stage the person wants to return to. Omit it and
   *  the rail stays exactly as inert as it was. */
  onRevisit?: (stage: string) => void
}) {
  return (
    <ol className="mb-8 flex flex-wrap gap-2" aria-label="Onboarding progress">
      {stages.map((stage) => {
        const done = completed.includes(stage)
        const here = stage === current
        const revisitable = done && !here && onRevisit !== undefined

        const className = [
          'rounded-full px-3 py-1 font-mono text-2xs uppercase tracking-[0.1em]',
          here
            ? 'bg-ink-900 text-bone-50'
            : done
              ? 'bg-steel-100 text-steel-700'
              : 'bg-bone-200 text-ink-400',
          revisitable
            ? 'cursor-pointer underline decoration-steel-300 underline-offset-2 hover:bg-steel-200'
            : '',
        ].join(' ')

        const body = `${done && !here ? '✓ ' : ''}${labels[stage] ?? stage}`

        return (
          <li key={stage} aria-current={here ? 'step' : undefined}>
            {revisitable ? (
              <button type="button" className={className} onClick={() => onRevisit(stage)}>
                {body}
                <span className="sr-only"> — go back to this step</span>
              </button>
            ) : (
              <span className={className}>{body}</span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
