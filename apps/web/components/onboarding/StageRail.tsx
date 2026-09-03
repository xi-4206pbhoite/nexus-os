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
 */
export function StageRail({
  stages,
  current,
  completed,
  labels,
}: {
  stages: string[]
  current: string
  completed: string[]
  labels: Record<string, string>
}) {
  return (
    <ol className="mb-8 flex flex-wrap gap-2" aria-label="Onboarding progress">
      {stages.map((stage) => {
        const done = completed.includes(stage)
        const here = stage === current
        return (
          <li
            key={stage}
            aria-current={here ? 'step' : undefined}
            className={[
              'rounded-full px-3 py-1 font-mono text-2xs uppercase tracking-[0.1em]',
              here
                ? 'bg-ink-900 text-bone-50'
                : done
                  ? 'bg-steel-100 text-steel-700'
                  : 'bg-bone-200 text-ink-400',
            ].join(' ')}
          >
            {done && !here ? '✓ ' : ''}
            {labels[stage] ?? stage}
          </li>
        )
      })}
    </ol>
  )
}
