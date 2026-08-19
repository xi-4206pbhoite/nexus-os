import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Browser-side calls for workspace setup.
 *
 * Like the auth calls, these go to this app's own `/api/*` routes rather than
 * to the API directly — see `lib/auth-proxy.ts`. The session cookie is
 * `httponly` and `SameSite=Lax`, and both properties only hold while the
 * request is first-party.
 *
 * Nothing here decides anything. `writable`, `can_administer` and the scope on
 * each question are read from the API and used to choose what to *render*; the
 * API refuses the write regardless of what this file believes. A field this
 * code hides is a presentation choice, and never the boundary.
 */

export type Choice = { value: string; label: string }

export type Stage = 'pass_1' | 'pass_2' | 'department' | 'connect' | 'post_invite'

export type AnswerType =
  | 'text'
  | 'long_text'
  | 'single_choice'
  | 'multi_choice'
  | 'ranked'
  | 'money'
  | 'url'
  | 'user_list'

export type Question = {
  key: string
  prompt: string
  stage: Stage
  answer_type: AnswerType
  /** `L1`…`L5`. Where this answer will be stored, shown to the person giving it. */
  scope: string
  department: string | null
  /**
   * Which department's block this question belongs to, or null for company-wide.
   *
   * Not the same as `department`, which is the scope classification. A question can
   * be asked of Sales and still be classified L2 — the pipeline stages are, because
   * they are structural rather than sensitive.
   */
  asked_of: string | null
  required: boolean
  why: string
  options: Choice[]
  free_entry: boolean
  writable: boolean
  value: unknown
}

export type Member = {
  user_id: string
  email: string
  display_name: string | null
  role: string
}

export type Catalogue = {
  questions: Question[]
  can_administer: boolean
  members: Member[]
}

export type Invitation = {
  invitation_id: string
  email: string
  role: string
  departments: string[]
  state: 'pending' | 'accepted' | 'revoked' | 'expired'
  expires_at: string
}

export type IssuedInvitation = Invitation & {
  /** Where to send the invited person. No email is sent yet — see `TeamStep`. */
  accept_path: string
}

export type AcceptResult = {
  outcome: 'accepted' | 'already_a_member'
  workspace_id: string | null
  workspace_name: string | null
  role: string | null
}

async function call(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (init.body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Something went wrong.'), response.status)
  }
  return payload
}

export type Connection = {
  source: string
  label: string
  /** Always false. There is no connector — see the connections endpoint. */
  connected: boolean
  /** How many capabilities this would unlock, counted from the offering data. */
  unlocks: number
  departments: string[]
  detail: string
}

export type Connections = {
  connections: Connection[]
  connected_count: number
}

export async function fetchConnections(): Promise<Connections> {
  return (await call('/api/onboarding/connections')) as Connections
}

export async function fetchCatalogue(): Promise<Catalogue> {
  return (await call('/api/onboarding/questions')) as Catalogue
}

export async function saveAnswers(
  answers: { key: string; value: unknown }[],
): Promise<{ saved: string[] }> {
  return (await call('/api/onboarding/answers', {
    method: 'POST',
    body: JSON.stringify({ answers }),
  })) as { saved: string[] }
}

export type Completion = {
  completed_at: string
  landing_department: string | null
  email_sent: boolean
  email_detail: string
  already_complete: boolean
}

/**
 * Mark setup finished.
 *
 * Idempotent on the server — a second call reports `already_complete` and sends no
 * second notification — so a double-click or a retry after a slow response is safe.
 */
export async function completeSetup(): Promise<Completion> {
  return (await call('/api/onboarding/complete', { method: 'POST' })) as Completion
}

export async function fetchInvitations(): Promise<Invitation[]> {
  const payload = (await call('/api/invitations')) as { invitations: Invitation[] }
  return payload.invitations
}

export async function createInvitation(input: {
  email: string
  role: string
  departments: string[]
}): Promise<IssuedInvitation> {
  return (await call('/api/invitations', {
    method: 'POST',
    body: JSON.stringify(input),
  })) as IssuedInvitation
}

export async function revokeInvitation(id: string): Promise<void> {
  await call(`/api/invitations/${id}/revoke`, { method: 'POST' })
}

export async function acceptInvitation(token: string): Promise<AcceptResult> {
  return (await call('/api/invitations/accept', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })) as AcceptResult
}

/**
 * What the scope on a question means, in words.
 *
 * The product's claim is that a form is not a laundering mechanism — an average
 * deal size typed at signup is a Sales fact, not a company fact. Saying so at
 * the point of capture is the only place that claim is visible to the person it
 * protects.
 */
export function scopeLabel(scope: string, department: string | null): string {
  switch (scope) {
    case 'L1':
      return 'Public — this is outward-facing material'
    case 'L2':
      return 'Everyone in your workspace'
    case 'L3':
      return department
        ? `${department[0].toUpperCase()}${department.slice(1)} only — managers and above`
        : 'One department only'
    default:
      return 'Restricted'
  }
}
