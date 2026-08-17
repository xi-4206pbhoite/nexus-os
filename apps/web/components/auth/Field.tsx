'use client'

import { useId, useState } from 'react'

/**
 * A labelled input with its error wired up for screen readers.
 *
 * The error is `role="alert"` and referenced by `aria-describedby`, so it is
 * announced rather than only seen. `aria-invalid` marks the field itself, since
 * colour alone is not a signal everyone receives.
 */
export function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
  hint,
  error,
  disabled,
  placeholder,
  revealable,
}: {
  label: string
  type: 'email' | 'password'
  value: string
  onChange: (value: string) => void
  autoComplete: string
  hint?: string
  error?: string
  disabled?: boolean
  placeholder?: string
  revealable?: boolean
}) {
  const id = useId()
  const [revealed, setRevealed] = useState(false)
  // The error *replaces* the hint below, so only one of these is ever rendered.
  // `aria-describedby` must name that one and no other: an id pointing at an
  // element that does not exist resolves to nothing, and a screen reader
  // announces nothing where the error should be. Listing both looked harmless
  // and silently dropped the error from the accessible description.
  const describedById = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  const inputType = revealable && revealed ? 'text' : type

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-ink-800">
        {label}
      </label>

      <div className="relative mt-1.5">
        <input
          id={id}
          type={inputType}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          disabled={disabled}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedById}
          className={`h-12 w-full rounded-xl border bg-white px-4 text-[0.95rem] text-ink-900 shadow-paper outline-none transition-colors placeholder:text-ink-300 disabled:bg-bone-100 disabled:text-ink-500 ${
            error
              ? 'border-clay-500 focus:border-clay-500 focus:ring-2 focus:ring-clay-200'
              : 'border-ink-200 focus:border-steel-500 focus:ring-2 focus:ring-steel-200'
          } ${revealable ? 'pr-20' : ''}`}
        />

        {revealable ? (
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            className="absolute inset-y-0 right-2 my-auto h-8 rounded-lg px-2.5 font-mono text-2xs uppercase tracking-[0.1em] text-ink-500 transition-colors hover:bg-bone-100 hover:text-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold-500"
            // The label says what will happen, and the state is announced
            // separately — a button reading "Hide" while the value is hidden is
            // the classic version of this bug.
            aria-pressed={revealed}
          >
            {revealed ? 'Hide' : 'Show'}
          </button>
        ) : null}
      </div>

      {error ? (
        <p id={describedById} role="alert" className="mt-1.5 text-sm text-clay-600">
          {error}
        </p>
      ) : hint ? (
        <p id={describedById} className="mt-1.5 text-sm text-ink-500">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
