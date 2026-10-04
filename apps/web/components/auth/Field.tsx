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
  type = 'text',
  value,
  onChange,
  autoComplete,
  hint,
  error,
  disabled,
  placeholder,
  revealable,
  options,
  required,
}: {
  label: string
  /**
   * Defaults to `text`. Widened from `'email' | 'password'` in P5 for the
   * company-registration form — a company name is not a credential, and
   * duplicating this component to say so would have meant two places to fix the
   * `aria-describedby` reasoning below.
   */
  type?: 'email' | 'password' | 'text' | 'url' | 'tel'
  value: string
  onChange: (value: string) => void
  /** Optional: only credential fields have a meaningful autofill token. */
  autoComplete?: string
  hint?: string
  error?: string
  disabled?: boolean
  placeholder?: string
  revealable?: boolean
  /**
   * Whether the field must be filled.
   *
   * **Nothing carried this until a browser run went looking**, so every form in
   * the product — register, register the company, sign in — validated only on
   * the server. Two things were missing rather than one: the browser did no
   * constraint check, and a screen reader announced an optional field where the
   * form would refuse without it.
   *
   * `required` sets both, because `aria-required` and the native attribute are
   * not interchangeable: the attribute is what a screen reader reads, and
   * `aria-required` says the same thing to assistive technology. **Neither
   * blocks a submit here** (F-24) — every form that uses `Field` also sets
   * `noValidate`, which turns off the browser's own constraint validation
   * entirely, `required` included. That is deliberate: `noValidate` is what
   * lets a form show its own styled, announced error instead of the browser's
   * native bubble — but it means `required` is decorative unless the form's
   * own `onSubmit` checks the field itself. Every consumer of `Field` does
   * that validation in its `onSubmit`, the same pattern `LoginForm` uses.
   *
   * Optional fields say so in their **label** — "Phone (optional)" — which is
   * the existing convention here, so this is the inverse of it and not a second
   * way of saying the same thing.
   */
  required?: boolean
  /**
   * Render a `<select>` over these instead of a text input.
   *
   * Here rather than in a second component so that the label, the hint, the
   * `role="alert"` error and the `aria-describedby` reasoning below have one
   * implementation. A `SelectField` copy would be a second place for the
   * describedby bug this component's comment documents.
   *
   * `placeholder` becomes the empty first option, which is how a `<select>`
   * expresses "nothing chosen" — an optional field has to be able to stay
   * unanswered, and a select with no empty option silently answers it with
   * whatever happens to be first.
   */
  options?: { value: string; label: string }[]
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
      <label htmlFor={id} className="app-label">
        {label}
      </label>

      <div className="relative mt-1.5">
        {options ? (
          <select
            id={id}
            required={required}
            aria-required={required || undefined}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedById}
            // `app-field`'s own `select` rule draws the chevron (an
            // `appearance-none` background image) at its own height and font
            // on every platform, which next to these inputs reads as a
            // different form otherwise. No `pr-20` branch — `revealable` is a
            // password affordance and cannot apply here.
            className={`app-field h-12 ${value ? 'text-cloud-900' : 'text-cloud-400'} ${
              error ? 'border-clay-500 focus:border-clay-500 focus:ring-clay-200' : ''
            }`}
          >
            <option value="">{placeholder ?? 'Select…'}</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={inputType}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            autoComplete={autoComplete}
            disabled={disabled}
            required={required}
            aria-required={required || undefined}
            placeholder={placeholder}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedById}
            className={`app-field h-12 ${
              error ? 'border-clay-500 focus:border-clay-500 focus:ring-clay-200' : ''
            } ${revealable ? 'pr-20' : ''}`}
          />
        )}

        {revealable ? (
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            className="absolute inset-y-0 right-2 my-auto h-8 rounded-lg px-2.5 font-mono text-2xs uppercase tracking-[0.1em] text-cloud-500 transition-colors hover:bg-cloud-100 hover:text-cloud-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
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
        <p id={describedById} role="alert" className="app-hint mt-1.5 text-clay-600">
          {error}
        </p>
      ) : hint ? (
        <p id={describedById} className="app-hint mt-1.5">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
