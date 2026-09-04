import type { Metadata } from 'next'
import { DocumentUpload } from '@/components/onboarding/DocumentUpload'
import { SetupShell } from '@/components/onboarding/SetupShell'

/* `title` alone, not "Documents · NEXUS OS". The root layout's metadata carries
   a `%s · NEXUS OS` template, so spelling the suffix here rendered it twice —
   finding F13. */
export const metadata: Metadata = {
  title: 'Documents',
  robots: { index: false, follow: false },
}

/**
 * Stage 5, on its own page.
 *
 * Separate from the department blocks for the same reason those are separate
 * from the main flow (Q27): a founder returns to uploading over days as they
 * find the files, and a stage that only exists inside a wizard is a stage you
 * can only do once.
 *
 * Wrapped in `SetupShell` since finding F10 — this rendered as bare content on
 * an empty background, with no header, no navigation and no way onward but the
 * browser's Back button.
 */
export default function DocumentsPage() {
  return (
    <SetupShell eyebrow="Documents" width="max-w-4xl">
      <DocumentUpload />
    </SetupShell>
  )
}
