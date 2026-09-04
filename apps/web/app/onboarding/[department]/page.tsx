import type { Metadata } from 'next'
import { DepartmentBlock } from '@/components/onboarding/DepartmentBlock'
import { SetupShell } from '@/components/onboarding/SetupShell'

export const metadata: Metadata = {
  title: 'Department questions',
  robots: { index: false, follow: false },
}

/**
 * One department's block, reached from its director (Q27).
 *
 * A separate page rather than a stage in the main flow: the founder answers
 * their own department during onboarding and **defers the rest**, so the others
 * are returned to later, one at a time, from the dashboard that needs them.
 *
 * Wrapped in `SetupShell` since finding F10 — this had no header, no navigation
 * and nothing linking back to the director whose page sent the founder here.
 */
export default async function DepartmentBlockPage({
  params,
}: {
  params: Promise<{ department: string }>
}) {
  const { department } = await params
  return (
    <SetupShell eyebrow="Department questions">
      <DepartmentBlock department={department} />
    </SetupShell>
  )
}
