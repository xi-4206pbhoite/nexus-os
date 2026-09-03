import type { Metadata } from 'next'
import { AuthShell } from '@/components/auth/AuthShell'
import { RegisterCompanyForm } from '@/components/auth/RegisterCompanyForm'

export const metadata: Metadata = {
  title: 'Create your company',
  robots: { index: false, follow: false },
}

export default function RegisterCompanyPage() {
  return (
    <AuthShell
      title="Create your company"
      intro="One step. NEXUS starts reading your website straight away — proving you own the domain comes later, in Settings."
    >
      <RegisterCompanyForm />
    </AuthShell>
  )
}
