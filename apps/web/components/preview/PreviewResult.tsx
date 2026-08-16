'use client'

import { motion } from 'framer-motion'
import { useState } from 'react'
import { IconCheck, IconMinus } from '@/components/art/Icons'

/**
 * The reduced Preview audit.
 *
 * Two rules from the specification are visible in this component:
 *
 * - **Every score shows its working.** Each category expands to the individual
 *   checks and the evidence behind them, because doc 07 I9 requires any card to
 *   answer "why are you telling me this?".
 * - **Locked is not zero.** Categories with no evidence render as a named
 *   unlock, never as `0` and never as an empty tile (I10). A locked tile is a
 *   call to action, not a failure.
 */

export type PreviewCheck = {
  id: string
  label: string
  passed: boolean
  evidence: string
}

export type PreviewCategory = {
  category: string
  score: number
  max_score: number
  percentage: number
  checks: PreviewCheck[]
}

export type PreviewAudit = {
  preview_id: string
  domain: string
  final_url: string
  overall: number
  scored_categories: number
  categories: PreviewCategory[]
  locked: { category: string; unlock: string }[]
  expires_at: string
}

const LABELS: Record<string, string> = {
  brand: 'Brand',
  technical_seo: 'Technical SEO',
  performance: 'Performance',
  marketing: 'Marketing',
  sales: 'Sales',
  finance: 'Finance',
  operations: 'Operations',
  people: 'People',
  customer_experience: 'Customer experience',
  competitors: 'Competitors',
}

function label(key: string) {
  return LABELS[key] ?? key.replace(/_/g, ' ')
}

function CategoryCard({ category, index }: { category: PreviewCategory; index: number }) {
  const [open, setOpen] = useState(false)
  const failed = category.checks.filter((c) => !c.passed)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.06 * index, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-bone-300/70 bg-white p-5 shadow-paper"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h4 className="font-display text-lg text-ink-800">{label(category.category)}</h4>
        <span className="font-mono text-sm text-ink-600">
          {category.score}
          <span className="text-ink-300">/{category.max_score}</span>
        </span>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-bone-200">
        <motion.span
          initial={{ width: 0 }}
          animate={{ width: `${category.percentage}%` }}
          transition={{ delay: 0.15 + 0.06 * index, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="block h-full rounded-full bg-steel-500"
        />
      </div>

      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mt-3 font-mono text-2xs uppercase tracking-[0.14em] text-ink-400 transition-colors hover:text-ink-700"
      >
        {open ? 'Hide' : 'Show'} the {category.checks.length} checks
        {failed.length > 0 && ` · ${failed.length} to fix`}
      </button>

      {open && (
        <ul className="mt-3 space-y-2 border-t border-bone-200 pt-3">
          {category.checks.map((check) => (
            <li key={check.id} className="flex items-start gap-2.5">
              {check.passed ? (
                <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-steel-500" />
              ) : (
                <IconMinus className="mt-0.5 h-4 w-4 shrink-0 text-clay-500" />
              )}
              <span className="min-w-0">
                <span className="block text-sm text-ink-700">{check.label}</span>
                {/* The evidence, not a recommendation — this is the audit trail. */}
                <span className="mt-0.5 block font-mono text-2xs text-ink-400">
                  {check.evidence}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  )
}

export function PreviewResult({ audit }: { audit: PreviewAudit }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="mt-10 rounded-panel border border-bone-300/70 bg-bone-50 p-6 shadow-paper-lg sm:p-8"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <span className="eyebrow">Preview audit</span>
          <h3 className="mt-1.5 font-display text-2xl text-ink-800">{audit.domain}</h3>
        </div>
        <div className="text-right">
          <span className="font-display text-4xl text-ink-800">{audit.overall}</span>
          <span className="text-sm text-ink-400">/100</span>
          {/* The denominator is always visible: never a whole-business score
              computed from part of the evidence (doc 05 §10). */}
          <p className="mt-1 font-mono text-2xs uppercase tracking-[0.14em] text-ink-400">
            across {audit.scored_categories} scored categories
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {audit.categories.map((category, i) => (
          <CategoryCard key={category.category} category={category} index={i} />
        ))}
      </div>

      <div className="mt-8">
        <h4 className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-400">
          Not scored yet — what each one needs
        </h4>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {audit.locked.map((item) => (
            <div
              key={item.category}
              className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-bone-300 bg-white/60 px-4 py-3"
            >
              <span className="text-sm text-ink-600">{label(item.category)}</span>
              <span className="shrink-0 font-mono text-2xs text-steel-600">{item.unlock}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 max-w-2xl text-xs leading-relaxed text-ink-400">
          This is the reduced audit. Competitor discovery and keyword data are held back until
          you verify you own this domain — anyone can type someone else&rsquo;s address.
        </p>
      </div>
    </motion.section>
  )
}
