'use client'

import { useId, useState } from 'react'
import { ScopeTag } from '@/components/onboarding/ScopeTag'
import type { Member, Question } from '@/lib/onboarding-client'

/**
 * One onboarding question, rendered from its declared answer type.
 *
 * The catalogue is the source of truth for what a question is — its type, its
 * options, its scope, whether this caller may write it — so this component
 * switches on data rather than carrying a hand-written form per question. A
 * question added to `app/domain/onboarding.py` appears here without an edit.
 *
 * `writable: false` renders read-only rather than hidden. A question whose
 * answer you can see but not change is a real state, and hiding it would make
 * the screen disagree with what the API will actually do.
 */

const inputClass =
  'w-full rounded-xl border border-ink-200 bg-white px-4 text-[0.95rem] text-ink-900 ' +
  'shadow-paper outline-none transition-colors placeholder:text-ink-300 ' +
  'focus:border-steel-500 focus:ring-2 focus:ring-steel-200 ' +
  'disabled:bg-bone-100 disabled:text-ink-500'

/**
 * Whether a question needs the whole row when the form is two columns wide.
 *
 * Half a row is right for a short answer and wrong for an answer that is a
 * paragraph, a list of options, or an ordering. Cramming those into a column
 * produces a textarea you cannot read a sentence in and checkbox lists that wrap
 * every second item — which is worse than the single wide column this replaced.
 *
 * Decided on the answer type rather than per question, so a new question inherits
 * the right behaviour from what it asks for rather than needing a layout note.
 */
export function spansFullWidth(question: Question): boolean {
  return (
    question.answer_type === 'long_text' ||
    question.answer_type === 'multi_choice' ||
    question.answer_type === 'ranked' ||
    question.answer_type === 'user_list'
  )
}

export function QuestionField({
  question,
  value,
  onChange,
  members,
  disabled,
}: {
  question: Question
  value: unknown
  onChange: (value: unknown) => void
  members: Member[]
  disabled?: boolean
}) {
  const id = useId()
  const readOnly = disabled || !question.writable

  return (
    <div
      className={[
        // Below xl this is a list: a rule between each question, and the first one
        // sits flush against the card's own padding.
        'border-t border-ink-100 py-6 first:border-t-0 first:pt-0',
        // At xl the parent becomes two columns, and the rules have to go. `first:`
        // matches one element, so in a grid the top-*right* question would keep a
        // border its neighbour had lost — a stray line across half the card. The
        // grid's own `gap-y` does the separating instead.
        'xl:border-t-0 xl:py-0 xl:first:pt-0',
        spansFullWidth(question) ? 'xl:col-span-2' : '',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <label htmlFor={id} className="text-[0.95rem] font-medium text-ink-900">
          {question.prompt}
          {question.required ? (
            <span className="ml-1.5 font-mono text-2xs uppercase tracking-[0.1em] text-clay-500">
              required
            </span>
          ) : null}
        </label>
        <ScopeTag scope={question.scope} department={question.department} />
      </div>

      {question.why ? (
        <p id={`${id}-why`} className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-500">
          {question.why}
        </p>
      ) : null}

      <div className="mt-3">
        <Control
          id={id}
          describedBy={question.why ? `${id}-why` : undefined}
          question={question}
          value={value}
          onChange={onChange}
          members={members}
          disabled={readOnly}
        />
      </div>

      {!question.writable ? (
        <p className="mt-2 text-sm text-ink-500">
          Read-only — changing this is available to owners and executives.
        </p>
      ) : null}
    </div>
  )
}

function Control({
  id,
  describedBy,
  question,
  value,
  onChange,
  members,
  disabled,
}: {
  id: string
  describedBy?: string
  question: Question
  value: unknown
  onChange: (value: unknown) => void
  members: Member[]
  disabled: boolean
}) {
  const asText = typeof value === 'string' ? value : ''
  const asList = Array.isArray(value) ? (value as string[]) : []

  switch (question.answer_type) {
    case 'long_text':
      return (
        <textarea
          id={id}
          aria-describedby={describedBy}
          value={asText}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          rows={4}
          className={`${inputClass} py-3`}
        />
      )

    case 'url':
      return (
        <input
          id={id}
          type="url"
          inputMode="url"
          aria-describedby={describedBy}
          value={asText}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          placeholder="yourcompany.example"
          className={`${inputClass} h-12`}
        />
      )

    case 'money':
      return (
        <input
          id={id}
          type="number"
          min={0}
          step="any"
          inputMode="decimal"
          aria-describedby={describedBy}
          value={typeof value === 'number' ? value : ''}
          // An empty box is "not answered", which is different from zero — so it
          // becomes undefined and is left out of the submission entirely rather
          // than stored as 0. A stored zero would be a number the product would
          // later compute with.
          onChange={(event) =>
            onChange(event.target.value === '' ? undefined : Number(event.target.value))
          }
          disabled={disabled}
          className={`${inputClass} h-12`}
        />
      )

    case 'single_choice':
      return (
        <select
          id={id}
          aria-describedby={describedBy}
          value={asText}
          onChange={(event) => onChange(event.target.value || undefined)}
          disabled={disabled}
          className={`${inputClass} h-12`}
        >
          <option value="">Choose…</option>
          {question.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )

    case 'user_list':
      return (
        <MemberPicker
          describedBy={describedBy}
          members={members}
          chosen={asList}
          onChange={onChange}
          disabled={disabled}
        />
      )

    case 'multi_choice':
    case 'ranked':
      if (!question.free_entry) {
        return (
          <fieldset aria-describedby={describedBy} disabled={disabled} className="flex flex-col gap-2">
            {question.options.map((option) => (
              <label key={option.value} className="flex items-center gap-2.5 text-[0.95rem] text-ink-800">
                <input
                  type="checkbox"
                  checked={asList.includes(option.value)}
                  onChange={(event) =>
                    onChange(
                      event.target.checked
                        ? [...asList, option.value]
                        : asList.filter((v) => v !== option.value),
                    )
                  }
                  className="h-4 w-4 rounded border-ink-300 text-steel-600 focus:ring-steel-200"
                />
                {option.label}
              </label>
            ))}
          </fieldset>
        )
      }
      return (
        <EntryList
          id={id}
          describedBy={describedBy}
          entries={asList}
          onChange={onChange}
          disabled={disabled}
          ordered={question.answer_type === 'ranked'}
        />
      )

    default:
      return (
        <input
          id={id}
          type="text"
          aria-describedby={describedBy}
          value={asText}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className={`${inputClass} h-12`}
        />
      )
  }
}

/**
 * A list the person types themselves, in the order they mean it.
 *
 * Used for goals, challenges and brand terms — the questions whose answers are
 * the customer's own words. Offering a menu there would put our vocabulary in
 * their mouth and then store the result as their stated intent.
 */
function EntryList({
  id,
  describedBy,
  entries,
  onChange,
  disabled,
  ordered,
}: {
  id: string
  describedBy?: string
  entries: string[]
  onChange: (value: string[]) => void
  disabled: boolean
  ordered: boolean
}) {
  const [draft, setDraft] = useState('')

  function add() {
    const entry = draft.trim()
    if (!entry || entries.includes(entry)) {
      setDraft('')
      return
    }
    onChange([...entries, entry])
    setDraft('')
  }

  function move(index: number, by: number) {
    const next = [...entries]
    const target = index + by
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  return (
    <div>
      <div className="flex gap-2">
        <input
          id={id}
          type="text"
          aria-describedby={describedBy}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter adds an entry; it must not submit the step, or the first
            // thing typed would save a half-finished list.
            if (event.key === 'Enter') {
              event.preventDefault()
              add()
            }
          }}
          disabled={disabled}
          placeholder="Type and press Enter"
          className={`${inputClass} h-12`}
        />
        <button
          type="button"
          onClick={add}
          disabled={disabled || draft.trim() === ''}
          className="h-12 shrink-0 rounded-xl border border-ink-200 bg-white px-4 text-sm font-medium text-ink-800 transition-colors hover:bg-bone-50 disabled:opacity-50"
        >
          Add
        </button>
      </div>

      {entries.length > 0 ? (
        <ol className="mt-3 flex flex-col gap-2">
          {entries.map((entry, index) => (
            <li
              key={entry}
              className="flex items-center gap-2 rounded-xl border border-ink-100 bg-white px-3 py-2 text-[0.95rem] text-ink-800 shadow-paper"
            >
              {ordered ? (
                <span className="w-5 shrink-0 font-mono text-2xs text-ink-400">{index + 1}</span>
              ) : null}
              <span className="flex-1 break-words">{entry}</span>
              {ordered ? (
                <>
                  <IconButton
                    label={`Move ${entry} up`}
                    onClick={() => move(index, -1)}
                    disabled={disabled || index === 0}
                  >
                    ↑
                  </IconButton>
                  <IconButton
                    label={`Move ${entry} down`}
                    onClick={() => move(index, 1)}
                    disabled={disabled || index === entries.length - 1}
                  >
                    ↓
                  </IconButton>
                </>
              ) : null}
              <IconButton
                label={`Remove ${entry}`}
                onClick={() => onChange(entries.filter((e) => e !== entry))}
                disabled={disabled}
              >
                ×
              </IconButton>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="h-7 w-7 shrink-0 rounded-lg text-ink-500 transition-colors hover:bg-bone-100 hover:text-ink-800 disabled:opacity-30"
    >
      {children}
    </button>
  )
}

/**
 * Recipients, chosen from the workspace and from nowhere else.
 *
 * Doc 06 §4.10: the morning brief is a cross-department composite that leaves
 * the product and cannot be recalled, so recipients must be workspace users
 * rather than typed addresses. There is deliberately no free-text box here —
 * and the API refuses a non-member regardless, because a missing box is a
 * presentation choice.
 */
function MemberPicker({
  describedBy,
  members,
  chosen,
  onChange,
  disabled,
}: {
  describedBy?: string
  members: Member[]
  chosen: string[]
  onChange: (value: string[]) => void
  disabled: boolean
}) {
  if (members.length === 0) {
    return (
      <p className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-3 text-sm text-ink-700">
        There is nobody to choose yet. Invite your team first — that is why this
        question comes after the team step and not before it.
      </p>
    )
  }

  return (
    <fieldset aria-describedby={describedBy} disabled={disabled} className="flex flex-col gap-2">
      {members.map((member) => (
        <label
          key={member.user_id}
          className="flex items-center gap-2.5 rounded-xl border border-ink-100 bg-white px-3 py-2.5 text-[0.95rem] text-ink-800 shadow-paper"
        >
          <input
            type="checkbox"
            checked={chosen.includes(member.user_id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...chosen, member.user_id]
                  : chosen.filter((id) => id !== member.user_id),
              )
            }
            className="h-4 w-4 rounded border-ink-300 text-steel-600 focus:ring-steel-200"
          />
          <span className="flex-1">{member.display_name || member.email}</span>
          <span className="rounded-full bg-bone-200 px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-ink-600">
            {member.role}
          </span>
        </label>
      ))}
    </fieldset>
  )
}
