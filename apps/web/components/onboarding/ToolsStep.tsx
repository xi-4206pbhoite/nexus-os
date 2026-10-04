'use client'

import { useEffect, useMemo, useState } from 'react'

import { type Tool, type ToolCatalogue, readTools } from '@/lib/agent-onboarding-client'

/**
 * The tools step: which systems this company runs on. The last thing before
 * the Persona and the Company Brain are assembled.
 *
 * **It says "declare", not "connect", because that is what it does.** No OAuth
 * flow exists yet, and `connectable` comes back false for every tool — so the
 * screen asks which systems they use and says plainly that connecting comes
 * later. The alternative was a row of Connect buttons that open nothing, which
 * is the one thing this product cannot afford to ship: the whole claim is that
 * it never states what it cannot support.
 *
 * That does not make the step decorative. What is recorded here is grounding
 * the Brain is built *with* — "deals are in Pipedrive, invoices in Xero" is a
 * fact only this person has — and every declared-but-unconnected tool becomes a
 * named gap with a named unlock, which is a different thing from an empty tile.
 *
 * **It is a screen now, not a card at the end of a transcript.** It used to
 * render under the whole interview, so the one place in onboarding asking for a
 * decision opened with several hundred words of the reader's own history. On
 * its own surface it can do what it is for: show the stack, show what each
 * choice changes, and let somebody scan it.
 *
 * **Selecting is configuring, and the panel is what makes that true.** Ticking
 * a box used to be a write into the dark. The count and the unlock list beside
 * the catalogue update as choices are made, so the screen answers "what does
 * this get me" while the choice is still being made rather than three screens
 * later — and every line in it is a capability the registry already declares,
 * never a finding and never a figure.
 *
 * **Nothing is filtered out.** The catalogue arrives ordered by the departments
 * this company runs, and every tool is still on it: a company with no formal
 * finance function may well run Stripe, and hiding it would be the product
 * deciding it knows their stack better than they do.
 *
 * **The CRMs are grouped, not made exclusive.** Four of them are alternatives
 * to each other, so they are presented under one heading rather than as four
 * unrelated choices — but more than one can be ticked, because a company
 * mid-migration really does run two, and a radio group would force them to lie.
 */
export function ToolsStep({
  onContinue,
  disabled,
}: {
  /** The ids to declare, and whether the person chose to skip the step. */
  onContinue: (providers: string[], skipped: boolean) => void
  disabled: boolean
}) {
  const [catalogue, setCatalogue] = useState<ToolCatalogue | null>(null)
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const loaded = await readTools()
        if (!live) return
        setCatalogue(loaded)
        // Seeded from the server so that returning to this step — a refresh, a
        // second tab, a resumed journey — shows what was declared last time
        // rather than an empty form that would silently clear it on continue.
        setPicked(new Set(loaded.declared))
      } catch (cause) {
        if (!live) return
        setError(cause instanceof Error ? cause.message : 'Could not load the tool list.')
      }
    })()
    return () => {
      live = false
    }
  }, [])

  /**
   * The catalogue in the order it arrived, split into department blocks with
   * the four CRMs collapsed into one.
   *
   * Grouped here rather than server-side because it is a layout decision: the
   * wire carries `department` and `kind` per tool, which is the data, and how
   * many headings that becomes is a question about this screen.
   */
  const groups = useMemo(() => {
    const out: { key: string; label: string; note: string | null; tools: Tool[] }[] = []
    for (const tool of catalogue?.tools ?? []) {
      const key = tool.kind === 'crm' ? 'crm' : tool.department
      const existing = out.find((group) => group.key === key)
      if (existing) {
        existing.tools.push(tool)
        continue
      }
      out.push({
        key,
        label: tool.kind === 'crm' ? 'Your CRM' : tool.department_label,
        note: tool.kind === 'crm' ? 'Whichever you use — more than one is fine.' : null,
        tools: [tool],
      })
    }
    return out
  }, [catalogue])

  const chosen = picked ?? new Set<string>()

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev ?? [])
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  /**
   * What the current selection turns on, deduplicated.
   *
   * Two tools can unlock the same capability — two CRMs both feed the pipeline
   * — and listing it twice would read as two things being gained. Order follows
   * the catalogue so the list does not reshuffle as boxes are ticked.
   */
  const unlocks = useMemo(() => {
    const seen = new Set<string>()
    for (const tool of catalogue?.tools ?? []) {
      // `picked`, not `chosen`. `chosen` substitutes a fresh empty Set while the
      // catalogue is still loading, so depending on it would rebuild this on
      // every render — and the list it produces is rendered in order, so a
      // needless rebuild is a needless reshuffle.
      // `tool.unlocks`, never `tool.records`. This list is what ticking these
      // boxes turns on, so a tool nothing reads yet must not appear in it —
      // that is the whole point of the split, and the type enforces it.
      if (picked?.has(tool.id) && tool.unlocks) seen.add(tool.unlocks)
    }
    return Array.from(seen)
  }, [catalogue, picked])

  const nothingConnects =
    catalogue !== null && catalogue.tools.every((tool) => !tool.connectable)

  return (
    <div className="flex flex-col gap-5">
      <div className="app-card animate-rise p-5">
        <h2 className="font-sans text-lg font-semibold text-cloud-900">Which systems do you run on?</h2>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-cloud-600">
          Knowing where your numbers live changes how your workspace answers, even before it can
          read them. Tick what you use — and if you use none of these, that is a real answer too.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_17rem] lg:items-start">
        <div className="flex flex-col gap-5">
          {groups.map((group, index) => (
            <fieldset
              key={group.key}
              className="app-card animate-rise p-4"
              style={{ animationDelay: `${60 + index * 60}ms` }}
            >
              <legend className="px-1 font-mono text-[11px] uppercase tracking-[0.18em] text-cloud-400">
                {group.label}
              </legend>
              {group.note && <p className="mt-1 text-xs text-cloud-400">{group.note}</p>}

              {/* A grid of cards rather than a divided list. The rows were
                  indistinguishable from the document asks two screens earlier,
                  which are a list of things to read; these are things to
                  choose, and a choice should look like one. */}
              <ul className="mt-2.5 grid gap-2 sm:grid-cols-2">
                {group.tools.map((tool) => {
                  const on = chosen.has(tool.id)
                  return (
                    <li key={tool.id}>
                      {/* The checkbox stays a checkbox. It is styled as a card
                          and it is still an `input` with the tool's name as its
                          accessible name, so it keeps its role, its keyboard
                          behaviour and its announcement — a `div` with
                          `onClick` would have looked identical and been
                          unreachable without a mouse. */}
                      <label
                        className={`flex h-full cursor-pointer items-start gap-3 rounded-xl border p-3 transition-all duration-200 ${
                          disabled ? 'cursor-not-allowed opacity-50' : ''
                        } ${
                          on
                            ? 'border-brand-400 bg-brand-100 shadow-e1'
                            : 'border-cloud-200 bg-white hover:border-brand-300 hover:shadow-e1'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={disabled}
                          onChange={() => toggle(tool.id)}
                          className="mt-0.5 h-4 w-4 shrink-0 accent-brand-600"
                        />
                        <span className="min-w-0">
                          <span
                            className={`block text-sm font-medium transition-colors ${
                              on ? 'text-brand-700' : 'text-cloud-900'
                            }`}
                          >
                            {tool.name}
                          </span>
                          {/* A capability, never a finding — or, for a tool no
                              capability reads yet, what recording it does
                              instead. Exactly one is set, so this never renders
                              empty. */}
                          <span className="mt-0.5 block text-xs leading-snug text-cloud-400">
                            {tool.unlocks ?? tool.records}
                          </span>
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
            </fieldset>
          ))}

          {error && (
            <p role="alert" className="text-xs text-clay-600">
              {error}
            </p>
          )}
        </div>

        {/* What the choice adds up to, beside the choice. Sticky on a wide
            screen so it stays in view while the catalogue scrolls; in normal
            flow below it on a narrow one, where a sticky panel would eat the
            viewport. */}
        <aside className="app-sunken animate-rise p-4 lg:sticky lg:top-6">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-cloud-400">
            Your stack
          </p>
          <p className="mt-2 font-sans text-2xl font-semibold text-cloud-900" aria-live="polite">
            {chosen.size}
            <span className="ml-1.5 text-sm font-normal text-cloud-400">
              {chosen.size === 1 ? 'system' : 'systems'}
            </span>
          </p>

          {unlocks.length > 0 ? (
            <>
              <p className="mt-3 text-xs font-medium text-cloud-600">What that turns on</p>
              <ul className="mt-1.5 flex flex-col gap-1.5">
                {unlocks.map((unlock) => (
                  <li key={unlock} className="flex items-start gap-2 text-xs text-cloud-500">
                    <span
                      aria-hidden
                      className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400"
                    />
                    {unlock}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            // Never a zero and never a blank: the empty state is a sentence
            // that says what happens next, not an absence the reader has to
            // interpret. Skipping is a first-class choice here (`doc/09` §6.2).
            <p className="mt-3 text-xs leading-relaxed text-cloud-400">
              Nothing ticked yet. You can skip this entirely — your workspace will name the
              figures it cannot see rather than guessing at them.
            </p>
          )}

          {/* The honest sentence, and the reason this screen has checkboxes
              rather than Connect buttons. Rendered from `connectable` so it
              disappears on its own the day a real flow lands, rather than
              staying on screen after it stops being true. */}
          {nothingConnects && (
            <p className="mt-4 border-l-2 border-brand-400 pl-2 text-[11px] leading-snug text-cloud-400">
              Ticking a box records that you use it — it does not connect it. Signing in to these
              comes after setup, and until then your workspace will say which figures it cannot
              see yet instead of guessing at them.
            </p>
          )}
        </aside>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          // Held until the catalogue lands. Continuing before it does would
          // post an empty declaration and — because the write replaces rather
          // than appends — clear anything already on record.
          disabled={disabled || picked === null}
          onClick={() => onContinue(Array.from(chosen), chosen.size === 0)}
          className="app-btn rounded-full px-6 py-2.5 transition-transform hover:scale-[1.02] disabled:hover:scale-100"
        >
          {chosen.size > 0
            ? `Continue with ${chosen.size} ${chosen.size === 1 ? 'system' : 'systems'}`
            : 'I use none of these'}
        </button>
        {chosen.size > 0 && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onContinue([], true)}
            className="text-sm text-cloud-400 underline decoration-cloud-200 underline-offset-4 hover:text-cloud-600 disabled:opacity-50"
          >
            Skip this
          </button>
        )}
      </div>
    </div>
  )
}
