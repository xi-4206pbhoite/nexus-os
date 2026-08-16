'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useRef, useState } from 'react'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { pillars } from '@/lib/content'

const tones: Record<
  string,
  { card: string; title: string; body: string; chip: string; rule: string }
> = {
  ink: {
    card: 'bg-ink-800 border-ink-700',
    title: 'text-bone-50',
    body: 'text-slate-300',
    chip: 'border-white/15 bg-white/5 text-bone-200',
    rule: 'bg-white/10',
  },
  gold: {
    card: 'bg-gold-100 border-gold-200',
    title: 'text-ink-800',
    body: 'text-ink-600',
    chip: 'border-gold-300/70 bg-white/60 text-ink-600',
    rule: 'bg-gold-300/60',
  },
  clay: {
    card: 'bg-clay-100 border-clay-200',
    title: 'text-ink-800',
    body: 'text-ink-600',
    chip: 'border-clay-300/60 bg-white/60 text-ink-600',
    rule: 'bg-clay-300/60',
  },
  steel: {
    card: 'bg-white border-bone-300/70',
    title: 'text-ink-800',
    body: 'text-ink-500',
    chip: 'border-bone-300 bg-bone-50 text-ink-600',
    rule: 'bg-bone-300',
  },
  slate: {
    card: 'bg-slate-100 border-slate-200',
    title: 'text-ink-800',
    body: 'text-ink-600',
    chip: 'border-slate-300/70 bg-white/60 text-ink-600',
    rule: 'bg-slate-300',
  },
}

/** A cursor-following highlight — cheap, and it makes a static grid feel alive. */
function Spotlight({ active, tone }: { active: { x: number; y: number } | null; tone: string }) {
  if (!active) return null
  const colour = tone === 'ink' ? 'rgba(239,191,106,0.16)' : 'rgba(9,31,70,0.06)'
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      style={{
        background: `radial-gradient(18rem 18rem at ${active.x}px ${active.y}px, ${colour}, transparent 70%)`,
        opacity: 1,
      }}
    />
  )
}

function PillarCard({
  title,
  promise,
  items,
  tone,
  span,
}: {
  title: string
  promise: string
  items: readonly string[]
  tone: string
  span: string
}) {
  const t = tones[tone] ?? tones.steel
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const reduced = useReducedMotion()

  return (
    <RevealItem className={span === 'lg' ? 'lg:col-span-2' : ''}>
      <motion.div
        ref={ref}
        onMouseMove={(e) => {
          if (reduced) return
          const r = ref.current?.getBoundingClientRect()
          if (r) setPos({ x: e.clientX - r.left, y: e.clientY - r.top })
        }}
        onMouseLeave={() => setPos(null)}
        whileHover={reduced ? undefined : { y: -6 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className={`group relative flex h-full flex-col overflow-hidden rounded-card border p-7 shadow-paper transition-shadow duration-400 hover:shadow-paper-lg ${t.card}`}
      >
        <Spotlight active={pos} tone={tone} />

        <div className="relative z-10 flex h-full flex-col">
          <h3 className={`font-display text-2xl leading-tight ${t.title}`}>{title}</h3>
          <p className={`mt-2.5 text-pretty text-[0.95rem] leading-relaxed ${t.body}`}>{promise}</p>

          <div className={`my-6 h-px w-full ${t.rule}`} />

          <ul className="mt-auto flex flex-wrap gap-2">
            {items.map((item) => (
              <li
                key={item}
                className={`rounded-full border px-3 py-1.5 text-xs transition-transform duration-300 group-hover:-translate-y-0.5 ${t.chip}`}
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      </motion.div>
    </RevealItem>
  )
}

export function Pillars() {
  return (
    <section id="pillars" className="relative scroll-mt-24 bg-bone-50 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={pillars.eyebrow}
          headline={pillars.headline}
          sub={pillars.sub}
          align="center"
        />

        <RevealGroup
          className="mt-16 grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-4"
          stagger={0.06}
        >
          {pillars.list.map((p) => (
            <PillarCard
              key={p.title}
              title={p.title}
              promise={p.promise}
              items={p.items}
              tone={p.tone}
              span={p.span}
            />
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
