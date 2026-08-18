'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import {
  createInvitation,
  fetchInvitations,
  revokeInvitation,
  type Invitation,
  type IssuedInvitation,
} from '@/lib/onboarding-client'

/**
 * Team, last (doc 04 §5, stage 6) — and before the brief-recipients question,
 * because recipients must be workspace users (doc 06 §4.10).
 *
 * The role is chosen here, by the inviter. Doc 06 §2.2: *"Every subsequent
 * user's role is set by the inviter, never self-declared at acceptance.
 * Self-declared role is privilege escalation via dropdown."* The dropdown is on
 * this screen, which is the only screen it may be on.
 */

const ROLES = [
  { value: 'executive', label: 'Executive', hint: 'Every department, and the executive surface.' },
  {
    value: 'department_manager',
    label: 'Department manager',
    hint: 'One department, including its totals.',
  },
  {
    value: 'contributor',
    label: 'Contributor',
    hint: 'One department, without department-wide figures or other people’s records.',
  },
  { value: 'viewer', label: 'Viewer', hint: 'Company-wide material only. No department data.' },
] as const

/** Mirrors `DEPARTMENT_BY_ROLE` — these two roles pick a department, the rest do not. */
const NEEDS_DEPARTMENT = new Set(['department_manager', 'contributor'])

const DEPARTMENTS = [
  'marketing',
  'sales',
  'finance',
  'operations',
  'hr',
  'strategy',
  'executive',
] as const

const STATE_STYLES: Record<Invitation['state'], string> = {
  pending: 'bg-gold-100 text-clay-600',
  accepted: 'bg-bone-200 text-ink-600',
  revoked: 'bg-clay-100 text-clay-600',
  expired: 'bg-clay-100 text-clay-600',
}

export function TeamStep() {
  const [invitations, setInvitations] = useState<Invitation[] | null>(null)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<string>('contributor')
  const [department, setDepartment] = useState<string>('sales')
  const [issued, setIssued] = useState<IssuedInvitation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetchInvitations()
      .then((found) => live && setInvitations(found))
      .catch(() => live && setInvitations([]))
    return () => {
      live = false
    }
  }, [])

  async function invite(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return

    setBusy(true)
    setError(null)
    try {
      const result = await createInvitation({
        email: email.trim(),
        role,
        // The API derives the department for roles that do not choose one, and
        // refuses a department sent for a role that has none — so sending an
        // empty list is the honest thing rather than a convenience.
        departments: NEEDS_DEPARTMENT.has(role) ? [department] : [],
      })
      setIssued(result)
      setEmail('')
      setInvitations(await fetchInvitations())
    } catch (caught) {
      setError(
        caught instanceof AuthError ? caught.message : 'Could not create that invitation.',
      )
    }
    setBusy(false)
  }

  async function withdraw(id: string) {
    try {
      await revokeInvitation(id)
      if (issued?.invitation_id === id) setIssued(null)
      setInvitations(await fetchInvitations())
    } catch (caught) {
      setError(caught instanceof AuthError ? caught.message : 'Could not withdraw that invitation.')
    }
  }

  const chosen = ROLES.find((r) => r.value === role)

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={invite} noValidate className="flex flex-col gap-5">
        {error ? (
          <div
            role="alert"
            className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
          >
            {error}
          </div>
        ) : null}

        <div>
          <label htmlFor="invite-email" className="block text-sm font-medium text-ink-800">
            Their work email
          </label>
          <input
            id="invite-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={busy}
            placeholder="colleague@yourcompany.example"
            className="mt-1.5 h-12 w-full rounded-xl border border-ink-200 bg-white px-4 text-[0.95rem] text-ink-900 shadow-paper outline-none transition-colors placeholder:text-ink-300 focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
          />
          <p className="mt-1.5 text-sm text-ink-500">
            They accept while signed in with this address, and no other.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="invite-role" className="block text-sm font-medium text-ink-800">
              Their role
            </label>
            <select
              id="invite-role"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              disabled={busy}
              className="mt-1.5 h-12 w-full rounded-xl border border-ink-200 bg-white px-4 text-[0.95rem] text-ink-900 shadow-paper outline-none focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
            >
              {ROLES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {chosen ? <p className="mt-1.5 text-sm text-ink-500">{chosen.hint}</p> : null}
          </div>

          {NEEDS_DEPARTMENT.has(role) ? (
            <div>
              <label htmlFor="invite-department" className="block text-sm font-medium text-ink-800">
                Their department
              </label>
              <select
                id="invite-department"
                value={department}
                onChange={(event) => setDepartment(event.target.value)}
                disabled={busy}
                className="mt-1.5 h-12 w-full rounded-xl border border-ink-200 bg-white px-4 text-[0.95rem] text-ink-900 shadow-paper outline-none focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
              >
                {DEPARTMENTS.map((value) => (
                  <option key={value} value={value}>
                    {value === 'hr' ? 'HR / People' : value[0].toUpperCase() + value.slice(1)}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-sm text-ink-500">
                This is what they can see. It is not a label.
              </p>
            </div>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={busy || email.trim() === ''}
          className="h-12 w-fit rounded-full bg-ink-800 px-6 text-sm font-medium text-bone-50 shadow-paper transition-all hover:bg-ink-700 disabled:opacity-50"
        >
          {busy ? 'Creating the invitation…' : 'Create invitation'}
        </button>
      </form>

      {issued ? (
        <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            Send this to them yourself
          </p>
          <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
            <span className="font-medium">No email is sent yet.</span> Delivery is not
            wired up anywhere in the product, so the link below is the invitation.
            It only works for <span className="font-medium">{issued.email}</span>,
            signed in with that address.
          </p>
          <code className="mt-3 block break-all rounded-lg border border-ink-200 bg-white px-3 py-2 font-mono text-[0.8rem] text-ink-800">
            {typeof window === 'undefined' ? issued.accept_path : window.location.origin + issued.accept_path}
          </code>
        </div>
      ) : null}

      <section>
        <h3 className="font-display text-lg font-medium text-ink-900">Invitations</h3>

        {invitations === null ? (
          <p className="mt-3 font-mono text-sm text-ink-500">Loading…</p>
        ) : invitations.length === 0 ? (
          <p className="mt-3 text-[0.95rem] text-ink-600">
            Nobody has been invited yet. You can skip this and come back — it is the
            step most likely to be done later anyway.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {invitations.map((invitation) => (
              <li
                key={invitation.invitation_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-100 bg-white px-4 py-3 shadow-paper"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink-900">{invitation.email}</p>
                  <p className="mt-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
                    {invitation.role.replace('_', ' ')}
                    {invitation.departments.length > 0
                      ? ` · ${invitation.departments.join(', ')}`
                      : ''}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-full px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] ${STATE_STYLES[invitation.state]}`}
                  >
                    {invitation.state}
                  </span>
                  {invitation.state === 'pending' ? (
                    <button
                      type="button"
                      onClick={() => withdraw(invitation.invitation_id)}
                      className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
                    >
                      Withdraw
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
