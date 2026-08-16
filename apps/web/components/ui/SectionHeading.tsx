import type { ReactNode } from 'react'
import { Reveal } from '@/components/motion/Reveal'

export function SectionHeading({
  eyebrow,
  headline,
  sub,
  align = 'left',
  tone = 'light',
  className = '',
  children,
}: {
  eyebrow?: string
  headline: ReactNode
  sub?: ReactNode
  align?: 'left' | 'center'
  tone?: 'light' | 'dark'
  className?: string
  children?: ReactNode
}) {
  const isCenter = align === 'center'
  const isDark = tone === 'dark'

  return (
    <div
      className={`${isCenter ? 'mx-auto max-w-prose text-center' : 'max-w-3xl'} ${className}`}
    >
      {eyebrow ? (
        <Reveal>
          <div
            className={`flex items-center gap-3 ${isCenter ? 'justify-center' : ''}`}
          >
            <span
              className={`h-px w-8 ${isDark ? 'bg-gold-400/60' : 'bg-gold-500/70'}`}
              aria-hidden="true"
            />
            <span className={`eyebrow ${isDark ? 'text-gold-300' : ''}`}>{eyebrow}</span>
          </div>
        </Reveal>
      ) : null}

      <Reveal delay={0.06}>
        <h2
          className={`mt-5 text-headline text-balance ${isDark ? 'text-bone-50' : 'text-ink-800'}`}
        >
          {headline}
        </h2>
      </Reveal>

      {sub ? (
        <Reveal delay={0.12}>
          <p
            className={`mt-5 text-pretty text-lg leading-relaxed ${
              isDark ? 'text-slate-300' : 'text-ink-500'
            }`}
          >
            {sub}
          </p>
        </Reveal>
      ) : null}

      {children}
    </div>
  )
}
