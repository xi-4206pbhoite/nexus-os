import type { Metadata } from 'next'
import { DepartmentBlock } from '@/components/onboarding/DepartmentBlock'

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
 */
export default async function DepartmentBlockPage({
  params,
}: {
  params: Promise<{ department: string }>
}) {
  const { department } = await params
  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <DepartmentBlock department={department} />
    </main>
  )
}
