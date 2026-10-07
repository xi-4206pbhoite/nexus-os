import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OnboardingEntry } from '@/components/onboarding/OnboardingEntry'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany, fetchDepartments } from '@/lib/settings-client'

/**
 * `OnboardingEntry`'s whole job is resuming at the right beat — company
 * details first, then Areas of Interest (`AreasStage`, its own tile screen) if
 * no department has ever been chosen, then the conversation (ADR 0071 amends
 * ADR 0069 to move department selection ahead of the chat). `CompanyStage`'s
 * own tests cover its internals; `AreasStage`'s own tests cover its internals
 * too — these tests are about routing between the three, not about what each
 * stage does once it is showing. `ConversationalOnboarding` is stubbed for
 * that reason: its own boot sequence against the agent client is covered by
 * `ConversationalOnboarding.test.tsx`.
 */

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchCompany: vi.fn(), fetchDepartments: vi.fn() }
})

vi.mock('@/components/onboarding/ConversationalOnboarding', () => ({
  ConversationalOnboarding: () => <div>the conversation</div>,
}))

const NO_DEPARTMENT_RUNNING = {
  departments: [
    { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
    { value: 'marketing', label: 'Marketing', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  ],
  may_administer: true,
}

const MARKETING_RUNNING = {
  departments: [
    { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
    { value: 'marketing', label: 'Marketing', running: true, capabilities: 2, answered: 0, unanswered: 2 },
  ],
  may_administer: true,
}

const COMPANY = {
  workspace_id: 'w1',
  name: 'Acme',
  domain: 'acme.om',
  website_url: 'https://acme.om',
  domain_verified: false,
  role: 'admin' as const,
  may_administer: true,
}

beforeEach(() => {
  vi.mocked(fetchCompany).mockReset()
  vi.mocked(fetchDepartments).mockReset()
})

describe('OnboardingEntry resume', () => {
  it('resumes at company details when no workspace has been created yet', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('no workspace selected', 403))

    render(<OnboardingEntry />)

    expect(await screen.findByText(/let.s start with your company/i)).toBeInTheDocument()
  })

  it('shows the Areas of Interest tile screen once a workspace exists but no department is running yet', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(COMPANY)
    vi.mocked(fetchDepartments).mockResolvedValue(NO_DEPARTMENT_RUNNING)

    render(<OnboardingEntry />)

    expect(
      await screen.findByText(/which parts of the business should nexus pay attention to/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('the conversation')).not.toBeInTheDocument()
  })

  it('goes straight to the conversation once a department is already running', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(COMPANY)
    vi.mocked(fetchDepartments).mockResolvedValue(MARKETING_RUNNING)

    render(<OnboardingEntry />)

    expect(await screen.findByText('the conversation')).toBeInTheDocument()
  })

  it('shows a retryable error on a real failure, rather than guessing which beat to show', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('database unavailable', 500))

    render(<OnboardingEntry />)

    expect(await screen.findByText(/could not reach the account service/i)).toBeInTheDocument()
  })
})
