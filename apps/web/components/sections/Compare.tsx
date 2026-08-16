'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { IconCheck, IconMinus } from '@/components/art/Icons'
import { compare } from '@/lib/content'

export function Compare() {
  return (
    <section id="compare" className="relative scroll-mt-24 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={compare.eyebrow}
          headline={compare.headline}
          align="center"
        />

        <div className="mx-auto mt-14 max-w-4xl">
          {/* Column headers */}
          <Reveal>
            <div className="grid grid-cols-[1fr] gap-3 sm:grid-cols-[1.1fr_1fr_1fr]">
              <div className="hidden sm:block" />
              <div className="hidden rounded-t-2xl border border-b-0 border-bone-300/70 bg-bone-50 px-5 py-3.5 text-center sm:block">
                <span className="font-mono text-2xs uppercase tracking-[0.16em] text-ink-400">
                  {compare.themLabel}
                </span>
              </div>
              <div className="hidden rounded-t-2xl border border-b-0 border-ink-700 bg-ink-800 px-5 py-3.5 text-center sm:block">
                <span className="font-mono text-2xs uppercase tracking-[0.16em] text-gold-400">
                  {compare.usLabel}
                </span>
              </div>
            </div>
          </Reveal>

          <RevealGroup stagger={0.06}>
            {compare.rows.map((r, i) => {
              const last = i === compare.rows.length - 1
              return (
                <RevealItem key={r.dimension}>
                  <motion.div
                    className="grid grid-cols-1 gap-3 sm:grid-cols-[1.1fr_1fr_1fr]"
                    whileHover={{ x: 3 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="flex items-center pt-5 sm:pt-0">
                      <span className="font-display text-lg text-ink-800">{r.dimension}</span>
                    </div>

                    <div
                      className={`flex items-start gap-2.5 border-x border-b border-bone-300/70 bg-bone-50/60 px-5 py-4 ${
                        last ? 'rounded-b-2xl' : ''
                      } border-t sm:border-t-0`}
                    >
                      <IconMinus className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
                      <span className="text-sm leading-relaxed text-ink-500">{r.them}</span>
                    </div>

                    <div
                      className={`flex items-start gap-2.5 border-x border-b border-ink-700 bg-ink-800 px-5 py-4 ${
                        last ? 'rounded-b-2xl' : ''
                      } border-t sm:border-t-0`}
                    >
                      <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-gold-400" />
                      <span className="text-sm leading-relaxed text-bone-100">{r.us}</span>
                    </div>
                  </motion.div>
                </RevealItem>
              )
            })}
          </RevealGroup>
        </div>
      </div>
    </section>
  )
}
