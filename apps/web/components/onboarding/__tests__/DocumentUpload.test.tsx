import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentUpload } from '@/components/onboarding/DocumentUpload'

/**
 * The upload states, asserted where they are cheap to assert.
 *
 * `doc/12` P9 asks for "component tests per upload state: idle, uploading,
 * parsed, failed, over-limit". Playwright proves the journey works; it is slow,
 * needs a server and a database, and tells you almost nothing about *why*
 * something broke. A component that says "uploaded" about a file the API could
 * not read should fail in milliseconds, next to the component.
 *
 * The state that matters most is **parsed-but-unreadable**: the API returns
 * 201 for a scan, because the file is stored and is still the customer's file.
 * If this component reads 201 as success, the product tells a founder it has a
 * document it cannot read — the exact failure the whole phase is built against.
 */

const STAGE = {
  consent: { text: 'I warrant that this workspace has the right to use this document.', version: '2026-08-18.v1' },
  departments: [
    { department: 'finance', asks: [{ name: "This year's budget", unlocks: 'Comparing plan to actual.' }] },
  ],
  max_file_bytes: 25 * 1024 * 1024,
  max_files_at_onboarding: 20,
  workspace_quota_bytes: 500 * 1024 * 1024,
  bytes_used: 0,
  files_uploaded: 0,
}

function respond(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => body } as Response
}

async function ready() {
  render(<DocumentUpload />)
  await screen.findByText("This year's budget")
}

function pick(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function consent() {
  const box = document.querySelector('input[type="checkbox"]') as HTMLInputElement
  box.click()
  return box
}

describe('DocumentUpload', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(STAGE)))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('idle: names each ask and what it turns on', async () => {
    await ready()
    expect(screen.getByText("This year's budget")).toBeInTheDocument()
    expect(screen.getByText('Comparing plan to actual.')).toBeInTheDocument()
  })

  it('idle: the primary action offers to skip, because stage 5 is not required', async () => {
    await ready()
    expect(screen.getByText('Skip for now')).toBeInTheDocument()
  })

  it('idle: files cannot be chosen until the warranty is confirmed', async () => {
    await ready()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.disabled).toBe(true)
    consent()
    await waitFor(() => expect(input.disabled).toBe(false))
  })

  it('idle: the consent version is shown, not just sent', async () => {
    await ready()
    expect(screen.getByText('2026-08-18.v1')).toBeInTheDocument()
  })

  it('over-limit: an oversize file is refused without a request', async () => {
    await ready()
    consent()
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length

    const huge = new File(['x'], 'huge.pdf')
    Object.defineProperty(huge, 'size', { value: 30 * 1024 * 1024 })
    pick([huge])

    expect(await screen.findByText(/Over 25 MB/)).toBeInTheDocument()
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(calls)
  })

  it('parsed: an indexed file says so, and says what is still withheld', async () => {
    await ready()
    consent()
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      respond({ status: 'indexed', chunks_held_for_review: 2 }, 201),
    )

    pick([new File(['prices'], 'prices.csv')])

    expect(await screen.findByText('indexed')).toBeInTheDocument()
    expect(await screen.findByText(/2 sections are yours only until reviewed/)).toBeInTheDocument()
  })

  it('failed: a 201 that did not index is a failure, in the API\'s words', async () => {
    await ready()
    consent()
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      respond(
        { status: 'failed', message: 'This looks like a scan. There is no text to read.' },
        201,
      ),
    )

    pick([new File(['scan'], 'scan.pdf')])

    // The word that must NOT appear. A 201 is not success to a founder if the
    // document cannot be read — the file is stored and unreadable, and calling
    // it uploaded is the product losing something it claims to hold.
    expect(await screen.findByText(/This looks like a scan/)).toBeInTheDocument()
    expect(screen.queryByText('indexed')).not.toBeInTheDocument()
  })

  it('failed: a refusal can be retried without disturbing the others', async () => {
    await ready()
    consent()
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(respond({ detail: 'Upload failed.' }, 500))

    pick([new File(['a'], 'a.csv')])

    expect(await screen.findByText('Retry')).toBeInTheDocument()
  })
})
