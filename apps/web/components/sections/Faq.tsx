'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { faq } from '@/lib/content'

function Item({
  q,
  a,
  open,
  onToggle,
  index,
}: {
  q: string
  a: string
  open: boolean
  onToggle: () => void
  index: number
}) {
  return (
    <div className="border-b border-bone-200">
      <h3>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={`faq-panel-${index}`}
          className="group flex w-full items-start justify-between gap-6 py-6 text-left"
        >
          <span
            className={`font-display text-lg transition-colors duration-300 sm:text-xl ${
              open ? 'text-ink-800' : 'text-ink-700 group-hover:text-ink-900'
            }`}
          >
            {q}
          </span>
          <span
            className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-all duration-400 ease-out-expo ${
              open
                ? 'rotate-45 border-ink-800 bg-ink-800 text-bone-50'
                : 'border-bone-300 text-ink-500 group-hover:border-steel-400 group-hover:text-steel-600'
            }`}
          >
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true">
              <path
                d="M8 2.5v11M2.5 8h11"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </span>
        </button>
      </h3>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={`faq-panel-${index}`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <p className="max-w-2xl text-pretty pb-7 leading-relaxed text-ink-500">{a}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

export function Faq() {
  const [open, setOpen] = useState<number | null>(0)

  return (
    <section id="faq" className="relative scroll-mt-24 py-section">
      <div className="shell">
        <div className="grid gap-12 lg:grid-cols-[0.75fr_1.25fr] lg:gap-20">
          <div>
            <SectionHeading eyebrow={faq.eyebrow} headline={faq.headline} />
          </div>

          <RevealGroup stagger={0.05} className="lg:pt-2">
            {faq.items.map((item, i) => (
              <RevealItem key={item.q}>
                <Item
                  q={item.q}
                  a={item.a}
                  index={i}
                  open={open === i}
                  onToggle={() => setOpen(open === i ? null : i)}
                />
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </div>
    </section>
  )
}
