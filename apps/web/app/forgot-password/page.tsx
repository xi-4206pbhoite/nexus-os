import type { Metadata } from 'next'
import Link from 'next/link'
import { AuthShell } from '@/components/auth/AuthShell'
import { ForgotPasswordForm } from '@/components/auth/ForgotPasswordForm'

export const metadata: Metadata = {
  title: 'Reset your password',
  robots: { index: false, follow: false },
}

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      title="Reset your password"
      intro="Tell us the address you signed up with and we will send a link to set a new password."
      footer={
        <p>
          Remembered it?{' '}
          <Link
            href="/login"
            className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
          >
            Sign in
          </Link>
          .
        </p>
      }
    >
      <ForgotPasswordForm />
    </AuthShell>
  )
}
