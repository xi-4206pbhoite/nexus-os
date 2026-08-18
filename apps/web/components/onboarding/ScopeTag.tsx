import { scopeLabel } from '@/lib/onboarding-client'

/**
 * Where this answer will be stored, shown beside the question that asks for it.
 *
 * Doc 06 §2.5 requires onboarding answers to be tagged at capture, because a
 * form is not a laundering mechanism: an average deal size typed at signup is a
 * Sales fact, not a company fact. This is that classification made visible to
 * the person it protects, at the moment they decide whether to type it.
 *
 * It is a label on a decision the API has already made — the scope arrives with
 * the question and is never sent back with the answer.
 */
export function ScopeTag({ scope, department }: { scope: string; department: string | null }) {
  const restricted = scope === 'L3'

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] ${
        restricted ? 'bg-clay-100 text-clay-600' : 'bg-bone-200 text-ink-600'
      }`}
    >
      <span aria-hidden="true" className="font-semibold">
        {scope}
      </span>
      <span className="normal-case tracking-normal">{scopeLabel(scope, department)}</span>
    </span>
  )
}
