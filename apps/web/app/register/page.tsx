import type { Metadata } from 'next'
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
      intro="One account per person. Your workspace is created as you sign up, named from your email domain — you can rename it, and verify the domain later."
    >
      <RegisterForm />
    </AuthShell>
  )
}
