'use client'

import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal } from '@/components/motion/Reveal'
import { directors } from '@/lib/content'

const accents: Record<string, { bg: string; fg: string; mark: string }> = {
  gold: { bg: 'bg-gold-200', fg: 'text-gold-600', mark: '#EFBF6A' },
  steel: { bg: 'bg-steel-100', fg: 'text-steel-600', mark: '#37729C' },
  clay: { bg: 'bg-clay-100', fg: 'text-clay-500', mark: '#A55D35' },
  ink: { bg: 'bg-ink-100', fg: 'text-ink-700', mark: '#091F46' },
  slate: { bg: 'bg-slate-100', fg: 'text-slate-500', mark: '#7699AE' },
}

/**
 * A paper-cut "portrait" — deliberately abstract. Illustrating an AI director
 * as a human face would overclaim; layered shapes read as a role, not a person.
 */
function DirectorMark({ seed, colour }: { seed: number; colour: string }) {
  const rot = (seed * 37) % 40 - 20
  return (
    <svg viewBox="0 0 64 64" className="h-14 w-14" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="#FFFFFF" />
      <g transform={`rotate(${rot} 32 32)`}>
        <path d="M32 8a24 24 0 0 1 24 24H32z" fill={colour} opacity="0.9" />
        <path d="M32 32h24a24 24 0 0 1-24 24z" fill={colour} opacity="0.45" />
        <path d="M8 32a24 24 0 0 1 24-24v24z" fill={colour} opacity="0.22" />
      </g>
      <circle cx="32" cy="32" r="7" fill="#FFFFFF" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#D8D0C7" strokeWidth="1.5" />
    </svg>
  )
}

function DirectorCard({
  name,
  owns,
  accent,
  index,
}: {
  name: string
  owns: string
  accent: string
  index: number
}) {
  const a = accents[accent] ?? accents.steel
  return (
    <article className="group mx-3 flex h-full w-[19rem] shrink-0 flex-col rounded-card border border-bone-300/70 bg-white p-6 shadow-paper transition-all duration-500 ease-out-expo hover:-translate-y-1.5 hover:shadow-paper-lg">
      <div className={`w-fit rounded-2xl p-2 ${a.bg}`}>
        <DirectorMark seed={index} colour={a.mark} />
      </div>
      <h3 className="mt-5 font-display text-xl text-ink-800">{name}</h3>
      <p className="mt-2 text-pretty text-sm leading-relaxed text-ink-500">{owns}</p>
      <div className="mt-auto pt-5">
        <span className={`font-mono text-2xs uppercase tracking-[0.16em] ${a.fg}`}>
          reads the company brain
        </span>
      </div>
    </article>
  )
}

export function Directors() {
  return (
    <section id="team" className="relative scroll-mt-24 overflow-hidden py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={directors.eyebrow}
          headline={directors.headline}
          sub={directors.sub}
          align="center"
        />
      </div>

      {/* Two identical tracks scroll as one continuous belt. */}
      <Reveal delay={0.1} className="mt-14">
        <div className="mask-fade-x overflow-hidden pause-on-hover">
          <div className="flex w-max motion-safe:animate-marquee">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex" aria-hidden={copy === 1}>
                {directors.list.map((d, i) => (
                  <DirectorCard
                    key={`${copy}-${d.name}`}
                    name={d.name}
                    owns={d.owns}
                    accent={d.accent}
                    index={i}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </Reveal>

      <div className="shell">
        <Reveal delay={0.16}>
          <p className="mx-auto mt-12 max-w-xl text-center text-sm text-ink-400">
            Seven directors, one shared understanding of your business. The Sales Director already
            knows what the Finance Advisor knows.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
