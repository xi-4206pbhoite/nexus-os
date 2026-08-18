import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { DirectorPage } from '@/components/dashboard/DirectorPage'

export const metadata: Metadata = {
  title: 'Dashboard',
  robots: { index: false, follow: false },
}

/** The seven department keys, mirroring `Department` in `app/domain/scopes.py`. */
const DEPARTMENTS = [
  'marketing',
  'sales',
  'finance',
  'operations',
  'hr',
  'strategy',
  'executive',
] as const

export function generateStaticParams() {
  return DEPARTMENTS.map((department) => ({ department }))
}

/**
 * One director's page.
 *
 * The department in the URL is checked against the known seven here, which
 * decides only whether a *page* exists. Whether this caller may see it is
 * decided by the API — a department they do not hold answers 404 there, and the
 * page renders that rather than assuming its own check was enough.
 */
export default function DepartmentDashboardPage({
  params,
}: {
  params: { department: string }
}) {
  if (!DEPARTMENTS.includes(params.department as (typeof DEPARTMENTS)[number])) {
    notFound()
  }

  return <DirectorPage department={params.department} />
}
