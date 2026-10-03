import type { Metadata } from 'next'
import { Suspense } from 'react'
import { AuthShell } from '@/components/auth/AuthShell'
import { ResetPasswordForm } from '@/components/auth/ResetPasswordForm'

export const metadata: Metadata = {
  title: 'Set a new password',
  robots: { index: false, follow: false },
}

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Set a new password"
      intro="Choose something you have not used elsewhere. This link works once."
    >
      {/* See the note in `/verify-email`: `useSearchParams` needs this. */}
      <Suspense fallback={<p className="text-ink-500">Loading…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  )
}
