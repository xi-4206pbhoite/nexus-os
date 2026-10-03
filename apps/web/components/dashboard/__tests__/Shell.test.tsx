import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Shell } from '@/components/dashboard/Shell'

/**
 * The shell's honesty rules, which are the reason it exists (I10).
 *
 * A dashboard's job before it has data is to be clear that it has no data. The
 * failure it guards against is not a crash — it is a page that looks like a
 * verdict on somebody's business when it is a statement about ours.
 */

const EMPTY = {
  score: null,
  score_denominator: 3,
  capabilities_delivered: 0,
  capabilities_total: 24,
  assistant_reserved: true,
}

describe('Shell', () => {
  it('renders no score at all rather than a zero', () => {
    render(<Shell shell={EMPTY} company="Acme" />)

    // The word that must not appear. A greyed-out "0" is still read as a
    // score, and no caption undoes a number somebody has already seen.
    expect(screen.queryByText('0', { exact: true })).not.toBeInTheDocument()
    expect(screen.getByText(/no department has enough behind it/i)).toBeInTheDocument()
  })

  it('shows the denominator beside a real score', () => {
    render(<Shell shell={{ ...EMPTY, score: 72 }} company="Acme" />)

    expect(screen.getByText('72')).toBeInTheDocument()
    expect(screen.getByText(/across 3 departments/i)).toBeInTheDocument()
  })

  it('says "1 department" rather than "1 departments"', () => {
    render(<Shell shell={{ ...EMPTY, score: 60, score_denominator: 1 }} company="Acme" />)
    expect(screen.getByText(/across 1 department$/i)).toBeInTheDocument()
  })

  it('reports completeness as a pair, not a percentage', () => {
    render(<Shell shell={EMPTY} company="Acme" />)

    // "0 of 24" is a sentence somebody can argue with. "0%" is not — it hides
    // the denominator, which is the part that makes the claim checkable.
    expect(screen.getByText(/0 of 24/)).toBeInTheDocument()
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument()
  })

  it('reserves the assistant panel and says what it will do', () => {
    render(<Shell shell={EMPTY} company="Acme" />)

    // Q67. A blank region where a feature is coming reads as a bug; a fake one
    // reads as a lie. Named, with an honest "not built".
    expect(screen.getByText(/ask this director/i)).toBeInTheDocument()
    expect(screen.getByText(/It is not built/i)).toBeInTheDocument()
  })

  it('omits the panel when it is not reserved', () => {
    render(<Shell shell={{ ...EMPTY, assistant_reserved: false }} company="Acme" />)
    expect(screen.queryByText(/ask this director/i)).not.toBeInTheDocument()
  })
})
