import { messageFrom } from '@/lib/api-error'
import { AuthError } from '@/lib/auth-client'

/**
 * The seven director pages.
 *
 * Every field here is read from the API and rendered. Nothing is computed in the
 * browser, and there is deliberately no place to put a value: an `Offering` has
 * a name, what it will show, its state and its unlock — and no number. The
 * figures arrive in a later milestone from `calculators/`, which is pure.
 */

/**
 * Doc 05 §0's states, plus `planned`.
 *
 * `locked` means "connect something and this works". `planned` means the widget
 * does not exist yet. Collapsing them would turn a placeholder into a promise,
 * so the two are distinct all the way from `app/domain/dashboards.py` to here.
 */
export type WidgetState =
  | 'live'
  | 'partial'
  | 'locked'
  | 'warming'
  | 'self_reported'
  | 'planned'

export type Offering = {
  /** Doc 05's own numbering — `3.4` is the Growth Plan. */
  id: string
  name: string
  shows: string
  state: WidgetState
  /** What this needs, in words. Empty only when nothing is missing. */
  unlock: string
  needs: string[]
  phase: number
  note: string
}

export type DirectorSummary = {
  department: string
  title: string
  remit: string
  scoreable: boolean
  path: string
  offering_count: number
  /**
   * Q27. How many of this department's questions are still unanswered.
   *
   * Optional because a client built against an older API gets `undefined`
   * rather than a wrong zero — and zero would read as "nothing to do", which is
   * the one thing it must not say when the truth is unknown.
   */
  unanswered_questions?: number
}

export type Dashboards = {
  directors: DirectorSummary[]
  /** Where to send this person. `null` when they hold no department. */
  shell?: {
    score: number | null
    score_denominator: number
    capabilities_delivered: number
    capabilities_total: number
    assistant_reserved: boolean
  }
  /** Optional so a client built against an older API gets `undefined` rather
   *  than a wrong zero — the same reason `unanswered_questions` is optional. */

  landing: string | null
  delivered_count: number
}

export type Director = {
  department: string
  title: string
  remit: string
  scoreable: boolean
  path: string
  offerings: Offering[]
}

async function get(path: string): Promise<unknown> {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store' })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Could not load that dashboard.'), response.status)
  }
  return payload
}

export async function fetchDashboards(): Promise<Dashboards> {
  return (await get('/api/dashboards')) as Dashboards
}

export async function fetchDirector(department: string): Promise<Director> {
  return (await get(`/api/dashboards/${encodeURIComponent(department)}`)) as Director
}

export const STATE_LABEL: Record<WidgetState, string> = {
  live: 'Live',
  partial: 'Partial',
  locked: 'Locked',
  warming: 'Warming',
  self_reported: 'Entered by you',
  planned: 'Not built yet',
}
