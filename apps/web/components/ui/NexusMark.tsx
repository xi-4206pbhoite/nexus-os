/**
 * The product wordmark (ADR 0066).
 *
 * A bold "X" built from two crossing strokes, with the upper-right arm carried
 * in the brand's blue (`azure`) and the rest in ink — then the word NEXUS in a
 * heavy geometric sans. This is the signed-in app's mark: onboarding, the
 * dashboard, auth and the error pages. The marketing site keeps the cut-paper
 * `Logo`, so the landing page is untouched.
 *
 * Colours come from Tailwind `stroke-*` / `text-*` utilities rather than literal
 * hex, so the mark stays inside the token system. `tone="dark"` inverts the ink
 * to white for use on the dark nav rail; the blue arm is constant in both.
 */
export function NexusMark({
  className = '',
  tone = 'light',
  showWord = true,
}: {
  className?: string
  tone?: 'light' | 'dark'
  showWord?: boolean
}) {
  const inkStroke = tone === 'dark' ? 'stroke-white' : 'stroke-cloud-900'
  const inkText = tone === 'dark' ? 'text-white' : 'text-cloud-900'

  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg
        viewBox="0 0 48 48"
        className="h-7 w-7 shrink-0"
        fill="none"
        strokeWidth={7}
        strokeLinecap="round"
        aria-hidden="true"
      >
        {/* Top-left → bottom-right diagonal, in ink. */}
        <line x1="11" y1="11" x2="37" y2="37" className={inkStroke} />
        {/* Bottom-left → centre, in ink. */}
        <line x1="11" y1="37" x2="24" y2="24" className={inkStroke} />
        {/* Centre → top-right, the blue accent arm. */}
        <line x1="24" y1="24" x2="37" y2="11" className="stroke-azure-500" />
      </svg>
      {showWord && (
        <span
          className={`font-sans text-[1.3rem] font-extrabold tracking-tight ${inkText}`}
        >
          NEXUS
        </span>
      )}
    </span>
  )
}
