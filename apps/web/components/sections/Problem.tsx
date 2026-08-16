'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem, Reveal } from '@/components/motion/Reveal'
import { problemIcons } from '@/components/art/Icons'
import { problem } from '@/lib/content'

export function Problem() {
  return (
    <section id="problem" className="relative py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={problem.eyebrow}
          headline={problem.headline}
          sub={problem.sub}
        />

        <RevealGroup className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" stagger={0.07}>
          {problem.options.map((o) => {
            const Icon = problemIcons[o.icon as keyof typeof problemIcons]
            return (
              <RevealItem key={o.option}>
                <motion.article
                  whileHover={{ y: -5 }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  className="group h-full rounded-card border border-bone-300/70 bg-white p-6 shadow-paper transition-shadow duration-300 hover:shadow-paper-lg"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-bone-100 text-ink-600 transition-colors duration-300 group-hover:bg-ink-800 group-hover:text-bone-50">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-5 text-lg font-medium text-ink-800">{o.option}</h3>
                  <p className="mt-2 text-pretty text-[0.95rem] leading-relaxed text-ink-500">
                    {o.why}
                  </p>
                  {/* A struck-through rule: this option is crossed off. */}
                  <div className="mt-5 h-px w-full origin-left scale-x-0 bg-clay-400/50 transition-transform duration-500 ease-out-expo group-hover:scale-x-100" />
                </motion.article>
              </RevealItem>
            )
          })}

          {/* The pivot, occupying the sixth cell of the grid. */}
          <RevealItem>
            <div className="flex h-full flex-col justify-center rounded-card bg-ink-800 p-7 shadow-paper-lg">
              <p className="text-[0.95rem] leading-relaxed text-slate-300">
                {problem.punchline.before}{' '}
                <span className="text-bone-200">{problem.punchline.quiet}</span>
              </p>
              <div className="my-4 h-px w-full bg-white/10" />
              <p className="font-display text-2xl leading-tight text-bone-50">
                {problem.punchline.after}{' '}
                <span className="text-gold-400">{problem.punchline.loud}</span>
              </p>
              <p className="mt-3 text-sm text-slate-400">{problem.punchline.tail}</p>
            </div>
          </RevealItem>
        </RevealGroup>

        <Reveal delay={0.1}>
          <div className="mt-10 hairline" />
        </Reveal>
      </div>
    </section>
  )
}
