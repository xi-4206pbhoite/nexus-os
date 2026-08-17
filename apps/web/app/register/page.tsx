import type { Metadata } from 'next'
import Link from 'next/link'
import { AuthShell } from '@/components/auth/AuthShell'
import { RegisterForm } from '@/components/auth/RegisterForm'

export const metadata: Metadata = {
  title: 'Create your account',
  robots: { index: false, follow: false },
}

export default function RegisterPage() {
  return (
    <AuthShell
      title="Create your account"
      intro="One account per person. You will claim your company's domain next, and that is what creates the workspace."
      footer={
        <p>
          Want to see what it finds first?{' '}
          <Link
            href="/#top"
            className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
          >
            Run a free audit
          </Link>{' '}
          — no account needed.
        </p>
      }
    >
      <RegisterForm />
    </AuthShell>
  )
}
