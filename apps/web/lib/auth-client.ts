import { messageFrom } from '@/lib/api-error'

/**
 * Browser-side auth calls.
 *
 * All of these go to this app's own `/api/auth/*` routes, never to the API
 * directly — see `lib/auth-proxy.ts` for why that matters to the cookie flags.
 */

/** Mirrors the API's `MIN_PASSWORD_LENGTH`. Checked there too; this is only so the form can say so first. */
export const MIN_PASSWORD_LENGTH = 12

export type WorkspaceSummary = {
  workspace_id: string
  name: string
  role: string
}

export type SessionState = {
  user_id: string
  workspaces: WorkspaceSummary[]
  active_workspace_id: string | null
}

/**
 * The CSRF token the API set in a readable cookie at login.
 *
 * Readable on purpose: state-changing requests must echo it in a header, and
 * that is exactly what an attacker on another origin cannot do — they can make
 * the browser *send* the cookie but never read it.
 */
export function csrfToken(): string | null {
  if (typeof document === 'undefined') return null
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name === 'nexus_csrf') return decodeURIComponent(rest.join('='))
  }
  return null
}

/**
 * Whether a session *looks* present, for choosing what to render first.
 *
 * A hint, never a decision. The cookie is client-visible and therefore
 * client-forgeable; every real answer comes from the API. Using this to gate
 * access rather than to pick an initial view would be the mistake.
 */
export function looksSignedIn(): boolean {
  return csrfToken() !== null
}

export class AuthError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function post(path: string, body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    method: 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    // Same origin, so cookies ride along; stated rather than assumed.
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

/**
 * Create an account and land signed in.
 *
 * Returns the same `SessionState` login does, because the API now issues a
 * session at registration — there is no email to verify and no second round trip.
 * A taken address with the wrong password comes back 401 with login's wording, so
 * this call fails exactly as a sign-in would.
 */
export async function register(email: string, password: string): Promise<SessionState> {
  return (await post('/api/auth/register', { email, password })) as SessionState
}

export async function login(email: string, password: string): Promise<SessionState> {
  return (await post('/api/auth/login', { email, password })) as SessionState
}

export async function logout(): Promise<void> {
  await post('/api/auth/logout')
}

/** The current session, or `null` when there is none. */
export async function fetchSession(): Promise<SessionState | null> {
  const response = await fetch('/api/auth/session', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (response.status === 401) return null
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Could not load your account.'), response.status)
  }
  return payload as SessionState
}
