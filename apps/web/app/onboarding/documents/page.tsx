import { DocumentUpload } from '@/components/onboarding/DocumentUpload'

export const metadata = { title: 'Documents · NEXUS OS' }

/**
 * Stage 5, on its own page.
 *
 * Separate from the department blocks for the same reason those are separate
 * from the main flow (Q27): a founder returns to uploading over days as they
 * find the files, and a stage that only exists inside a wizard is a stage you
 * can only do once.
 */
export default function DocumentsPage() {
  return (
    <main className="min-h-screen bg-bone-50">
      <div className="mx-auto max-w-4xl px-6 py-12 sm:px-10">
        <DocumentUpload />
      </div>
    </main>
  )
}
