'use client'

import Link from 'next/link'
import type { ComponentProps, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'onDark'
type Size = 'md' | 'lg'

const base =
  'group relative inline-flex items-center justify-center gap-2 rounded-full font-medium ' +
  'transition-all duration-300 ease-out-expo will-change-transform ' +
  'active:translate-y-px disabled:pointer-events-none disabled:opacity-50'

const variants: Record<Variant, string> = {
  primary:
    'bg-ink-800 text-bone-50 shadow-paper hover:bg-ink-700 hover:shadow-lift hover:-translate-y-0.5',
  secondary:
    'border border-ink-200 bg-white text-ink-800 shadow-paper hover:border-ink-300 hover:bg-bone-50 hover:-translate-y-0.5 hover:shadow-paper-lg',
  ghost: 'text-ink-700 hover:bg-bone-100',
  onDark:
    'bg-gold-400 text-ink-900 shadow-paper hover:bg-gold-300 hover:-translate-y-0.5 hover:shadow-paper-lg',
}

const sizes: Record<Size, string> = {
  md: 'h-11 px-5 text-sm',
  lg: 'h-14 px-7 text-[0.975rem]',
}

type Props = {
  children: ReactNode
  href?: string
  variant?: Variant
  size?: Size
  className?: string
  icon?: ReactNode
} & Omit<ComponentProps<'button'>, 'ref'>

export function Button({
  children,
  href,
  variant = 'primary',
  size = 'md',
  className = '',
  icon,
  ...rest
}: Props) {
  const cls = `${base} ${variants[variant]} ${sizes[size]} ${className}`

  const inner = (
    <>
      <span className="relative z-10">{children}</span>
      {icon ? (
        <span className="relative z-10 transition-transform duration-300 ease-out-expo group-hover:translate-x-0.5">
          {icon}
        </span>
      ) : null}
    </>
  )

  if (href) {
    return (
      <Link href={href} className={cls}>
        {inner}
      </Link>
    )
  }

  return (
    <button className={cls} {...rest}>
      {inner}
    </button>
  )
}

export function ArrowRight({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={`h-4 w-4 ${className}`}
    >
      <path
        d="M2.5 8h11m0 0L9 3.5M13.5 8 9 12.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
