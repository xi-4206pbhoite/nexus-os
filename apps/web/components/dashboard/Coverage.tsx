'use client'

import type { Coverage as Bands } from '@/lib/dashboard-client'

/**
 * Where the product is, for this company — ADR 0030.
 *
 * This replaces the "Company Health 82/100" the reference mock opened with. A
 * composite over two measured capabilities out of eighty-nine would read as a
 * verdict on the business and is a verdict on one web page, so the region says
 * something narrower and true instead: **who has to move next.**
 *
 * ## Why a bar is honest here and would not have been over sources
 *
 * The three bands partition what a caller can reach, so every capability is in
 * exactly one. Banding by *connected source* would not partition anything —
 * `marketing.seo_gaps` computes today and is still missing `dataforseo`, so it
 * belongs in two bands at once and a stacked bar would assert it belongs in one.
 *
 * ## The third band is the honest headline
 *
 * "Not built yet" is ours, and naming it is what makes the other two mean
 * anything: without it, a founder reads two-of-eighty-nine as a product waiting
 * on them. `planned` tiles already say this one at a time; this says it once, at
 * the top.
 */

/** A band, as a row rather than a chart label — the number is the point and the
 *  sentence beside it is what stops the number being misread. */
function Band({
  count,
  label,
  swatch,
  children,
}: {
  count: number
  label: string
  swatch: string
  children: React.ReactNode
}) {
  return (
    <li className="flex gap-4 border-b border-cloud-200 py-3 last:border-b-0">
      <span aria-hidden className={`mt-2 h-2 w-2 shrink-0 rounded-sm ${swatch}`} />
      <div className="min-w-0">
        <p className="text-[0.95rem] text-cloud-900">
          <span className="font-sans text-lg font-semibold tabular-nums">{count}</span>{' '}
          <span className="font-medium">— {label}</span>
        </p>
        <p className="mt-0.5 max-w-prose text-sm leading-relaxed text-cloud-600">{children}</p>
      </div>
    </li>
  )
}

export function Coverage({ bands }: { bands: Bands }) {
  // Guarded rather than assumed. The API cannot serve a total of zero for a
  // caller who holds a department, but a division by it would render `NaN%`
  // across the bar — and a meter showing nothing is indistinguishable from a
  // meter showing a real zero.
  const width = (count: number) => (bands.total > 0 ? `${(count / bands.total) * 100}%` : '0%')

  return (
    <section aria-labelledby="coverage-heading">
      <h2 id="coverage-heading" className="font-sans text-title font-semibold text-cloud-900">
        Where the product is, for you
      </h2>
      <p className="mt-1 max-w-prose text-sm text-cloud-500">
        {bands.total} capabilities, split by what stands in front of each one.
      </p>

      <div className="app-card mt-4 px-5 py-5">
        <div
          role="img"
          aria-label={`${bands.measuring} measuring, ${bands.reading_back} reading your answers back, ${bands.not_built} not built yet, of ${bands.total}`}
          className="flex h-1.5 overflow-hidden rounded-full bg-cloud-100"
        >
          <span className="bg-brand-500" style={{ width: width(bands.measuring) }} />
          <span className="bg-azure-500" style={{ width: width(bands.reading_back) }} />
        </div>

        <ul className="mt-4">
          <Band count={bands.measuring} label="producing a figure" swatch="bg-brand-500">
            {/* Not "each with its denominator": only a scored audit has one.
                A pipeline (ADR 0033) and a count of your own records (ADR 0034)
                have no denominator to show, and this band counts all three. */}
            Computed in code from what we could measure, each showing its working and
            what it left out.
          </Band>
          <Band count={bands.reading_back} label="reading your answers back" swatch="bg-azure-500">
            Your own words rather than a measurement — which is why they never render as
            a score.
          </Band>
          <Band count={bands.not_built} label="not built yet" swatch="bg-cloud-300">
            Ours to fix, not yours. No calculator exists for these, so no connection you
            make would switch one on.
          </Band>
        </ul>

        <p className="mt-4 max-w-prose border-t border-cloud-200 pt-3 text-sm leading-relaxed text-cloud-600">
          <span className="font-semibold text-cloud-800">There is no company score.</span>{' '}
          Averaging what we hold would produce something that looks like a verdict on the
          business and is a verdict on one web page. It appears when there is enough
          behind it to mean what it would appear to mean.
        </p>
      </div>
    </section>
  )
}
