'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { OnboardingShell } from '@/components/onboarding/OnboardingShell'
import { CompanyStage } from '@/components/onboarding/stages/CompanyStage'
import { AreasStage } from '@/components/onboarding/stages/AreasStage'
import { ConversationalOnboarding } from '@/components/onboarding/ConversationalOnboarding'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany, fetchDepartments } from '@/lib/settings-client'

/**
 * Mounted at both `/register-company` and `/onboarding/agent` (ADR 0069 phase 1,
 * amended by ADR 0071).
 *
 * ## Three beats ahead of the chat: company, then areas, then the conversation
 *
 * The conversational engine greets by name, reads the company's website, and —
 * as of this amendment — recommends tools against the departments the founder
 * already chose. All three need to exist before the chat mounts, so this
 * resolves the founder's real position on every load rather than folding any
 * of it into the chat as a turn:
 *
 * 1. **`fetchCompany()` 403/401** — no workspace yet. Render `CompanyStage`
 *    (already tested, already wired to `registerCompany`/`looksLikeWebsite`/
 *    the domain-taken "ask to join" path). Account creation is a form, not a
 *    conversation.
 * 2. **`fetchDepartments()` with no non-`executive` department `running`** —
 *    a workspace exists but Areas of Interest has never been saved. Render
 *    `AreasStage` as its own tile-selection screen, the same component
 *    `StartFlow` used — icon tiles, floor-of-one, `executive` excluded because
 *    Chief of Staff is automatic and never a choice. This used to be an
 *    in-chat quick-reply beat (`DeptPicker`, in `ConversationalOnboarding`);
 *    ADR 0071 moves it ahead of the chat because picking the departments that
 *    decide which directors exist is a bigger decision than a quick-reply
 *    chip, and it is the same decision `ToolsStep`'s recommendations need
 *    answered before the chat ever reaches the tools phase.
 * 3. **Otherwise** — `ConversationalOnboarding` takes over: the website read,
 *    the brief, discovery, documents, tools and the Persona/Company Brain
 *    assembly. It still reads the chosen departments on its own boot (for the
 *    Brain panel and the tools recommendations), but no longer collects them.
 *
 * `CompanyStage`'s `onComplete` re-runs `resolve()` rather than jumping
 * straight to `chat`, so a brand-new workspace lands on `areas` next, exactly
 * as the resolution above would compute on a fresh page load.
 */

type Resume =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'company' }
  | { status: 'areas' }
  | { status: 'chat' }

export function OnboardingEntry() {
  const [resume, setResume] = useState<Resume>({ status: 'loading' })

  useEffect(() => {
    void resolve()
    // Run once on mount — `CompanyStage`'s own `onComplete` re-runs `resolve()`
    // itself, and `AreasStage`'s advances us locally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function resolve() {
    setResume({ status: 'loading' })
    try {
      await fetchCompany()
    } catch (error) {
      if (error instanceof AuthError && (error.status === 403 || error.status === 401)) {
        setResume({ status: 'company' })
        return
      }
      setResume({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
      return
    }

    try {
      const { departments } = await fetchDepartments()
      const hasRunningDepartment = departments.some((d) => d.value !== 'executive' && d.running)
      setResume({ status: hasRunningDepartment ? 'chat' : 'areas' })
    } catch (error) {
      setResume({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
    }
  }

  if (resume.status === 'loading') {
    return (
      <OnboardingShell part={1} eyebrow="loading your progress" stageKey="loading" aura="idle">
        <div aria-hidden className="flex flex-col gap-4">
          <div className="h-8 w-2/3 animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-full animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-5/6 animate-breathe rounded-full bg-bone-200" />
        </div>
      </OnboardingShell>
    )
  }

  if (resume.status === 'error') {
    return (
      <OnboardingShell part={1} eyebrow="something went wrong" stageKey="error" aura="idle">
        <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
          <h3 className="font-medium text-ink-800">Could not reach the account service</h3>
          <p className="mt-2 text-sm text-clay-600">{resume.message}</p>
          <Button variant="danger" size="sm" className="mt-4" onClick={() => void resolve()}>
            Retry
          </Button>
        </div>
      </OnboardingShell>
    )
  }

  if (resume.status === 'company') {
    return (
      <OnboardingShell part={1} eyebrow="a minute, then we start learning" stageKey="company" aura="idle">
        <CompanyStage onComplete={() => void resolve()} />
      </OnboardingShell>
    )
  }

  if (resume.status === 'areas') {
    return (
      <OnboardingShell part={2} eyebrow="Areas of interest" stageKey="areas" aura="idle">
        <AreasStage onComplete={() => setResume({ status: 'chat' })} />
      </OnboardingShell>
    )
  }

  return <ConversationalOnboarding />
}
