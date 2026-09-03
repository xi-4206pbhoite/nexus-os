'use client'

import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'

/**
 * The upload stage — the first `<input type="file">` in the product.
 *
 * Three things this screen has to get right, all of them about honesty rather
 * than mechanics.
 *
 * **Named asks, not a drop zone** (Q35). "Upload some documents" gets nothing.
 * A founder uploads a file when they can picture which file and can see what it
 * buys them, so every ask names a document and what it turns on.
 *
 * **Skipping is first-class** (`doc/09` §6.2). Stage 5 is *not required,
 * strongly guided*, and the screen says so where the decision is made. A stage
 * that guilts you into uploading is one people abandon rather than skip.
 *
 * **Every failure is per-file and visible.** A batch that reports "3 uploaded"
 * when one of them was a scan is the product quietly losing something the
 * customer believes it has. Each file carries its own state and its own reason,
 * and a failed one can be retried without touching the others.
 */

type Ask = { name: string; unlocks: string }
type DepartmentAsks = { department: string; asks: Ask[] }
type Stage = {
  consent: { text: string; version: string }
  departments: DepartmentAsks[]
  max_file_bytes: number
  max_files_at_onboarding: number
  workspace_quota_bytes: number
  bytes_used: number
  files_uploaded: number
}

type Upload = {
  id: string
  file: File
  state: 'queued' | 'uploading' | 'done' | 'failed'
  /** Why it failed, in the API's words. Never ours — the API knows whether it
   *  was a scan, an unreadable type or a limit, and paraphrasing loses that. */
  reason?: string
  chunksHeld?: number
}

const MB = 1024 * 1024

function mb(bytes: number): string {
  return `${Math.round(bytes / MB)} MB`
}

export function DocumentUpload({ onDone }: { onDone?: () => void }) {
  const [stage, setStage] = useState<Stage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [consented, setConsented] = useState(false)
  const [uploads, setUploads] = useState<Upload[]>([])
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let live = true
    fetch('/api/documents/asks', { credentials: 'same-origin', cache: 'no-store' })
      .then(async (r) => {
        const body = (await r.json()) as Stage & { detail?: string }
        if (!r.ok) throw new AuthError(body.detail ?? 'Could not load this step.', r.status)
        if (live) setStage(body)
      })
      .catch((caught: unknown) => {
        if (live) setError(caught instanceof AuthError ? caught.message : 'Could not load this step.')
      })
    return () => {
      live = false
    }
  }, [])

  if (error) return <p className="text-ink-600">{error}</p>
  if (!stage) return <p className="font-mono text-sm text-ink-500">Loading…</p>

  const done = uploads.filter((u) => u.state === 'done').length
  const remaining = stage.max_files_at_onboarding - stage.files_uploaded - done

  /**
   * The refusal, predicted from the same numbers the server enforces.
   *
   * Predicting is not enforcing — the server checks again, and it is the one
   * that decides. This exists so a founder is told a 30 MB file is too big
   * before waiting for it to upload, not so the limit lives in two places.
   */
  const refuse = (file: File, already: number): string | null => {
    if (file.size === 0) return 'This file is empty.'
    if (file.size > stage.max_file_bytes)
      return `Over ${mb(stage.max_file_bytes)}. Split it and upload the parts.`
    if (already >= remaining)
      return `That is more than the ${stage.max_files_at_onboarding} files onboarding takes.`
    if (stage.bytes_used + file.size > stage.workspace_quota_bytes)
      return `This workspace holds ${mb(stage.workspace_quota_bytes)} and is full.`
    return null
  }

  async function send(upload: Upload) {
    setUploads((all) => all.map((u) => (u.id === upload.id ? { ...u, state: 'uploading' } : u)))

    const body = new FormData()
    body.append('file', upload.file)
    body.append('consent', 'true')
    const csrf = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]*)/)?.[1]

    try {
      const response = await fetch('/api/documents', {
        method: 'POST',
        headers: csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {},
        body,
        credentials: 'same-origin',
        cache: 'no-store',
      })
      const payload = (await response.json()) as {
        detail?: string
        status?: string
        /** Empty when the upload succeeded. Never empty when it did not. */
        message?: string
        chunks_held_for_review?: number
      }

      setUploads((all) =>
        all.map((u) =>
          u.id !== upload.id
            ? u
            : !response.ok
              ? { ...u, state: 'failed', reason: payload.detail ?? 'Upload failed.' }
              : payload.status === 'indexed'
                ? { ...u, state: 'done', chunksHeld: payload.chunks_held_for_review }
                : // A 201 that did not index is still a failure *to the founder*
                  // — the file is stored and unreadable, and saying "uploaded"
                  // would be the product losing something it claims to hold.
                  { ...u, state: 'failed', reason: payload.message || 'Could not be read.' },
        ),
      )
    } catch {
      setUploads((all) =>
        all.map((u) =>
          u.id === upload.id ? { ...u, state: 'failed', reason: 'Upload failed. Try again.' } : u,
        ),
      )
    }
  }

  function choose(files: FileList | null) {
    if (!files) return
    const queued: Upload[] = []
    Array.from(files).forEach((file, index) => {
      const reason = refuse(file, uploads.filter((u) => u.state !== 'failed').length + index)
      queued.push({
        id: `${file.name}-${file.size}-${index}-${queued.length}`,
        file,
        state: reason ? 'failed' : 'queued',
        reason: reason ?? undefined,
      })
    })
    setUploads((all) => [...all, ...queued])
    queued.filter((u) => u.state === 'queued').forEach((u) => void send(u))
    if (input.current) input.current.value = ''
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="font-display text-title font-medium text-ink-900">
          Give NEXUS something to read
        </h1>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Nothing here is required. Every document you add makes an answer come from your
          business instead of from a general assumption — and you can add them later just as
          easily.
        </p>
        <p className="mt-2 text-sm text-ink-500">
          PDF, Word, PowerPoint, Excel, CSV and text. Up to {mb(stage.max_file_bytes)} each.{' '}
          Scans and photographs of documents cannot be read at all.
        </p>
      </div>

      {stage.departments.map((group) => (
        <section key={group.department}>
          <h2 className="font-mono text-2xs uppercase tracking-[0.12em] text-steel-700">
            {group.department === 'hr' ? 'People' : group.department}
          </h2>
          <ul className="mt-3 grid gap-3 sm:grid-cols-3">
            {group.asks.map((ask) => (
              <li
                key={ask.name}
                className="rounded-2xl border border-ink-100 bg-white px-4 py-3"
              >
                <p className="font-medium text-ink-900">{ask.name}</p>
                <p className="mt-1 text-sm text-ink-500">{ask.unlocks}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <div className="rounded-2xl border border-ink-100 bg-bone-100 px-5 py-5">
        <label className="flex items-start gap-3 text-[0.95rem] leading-relaxed text-ink-800">
          <input
            type="checkbox"
            checked={consented}
            onChange={(e) => setConsented(e.target.checked)}
            className="mt-1"
          />
          <span>
            {stage.consent.text}
            {/* The version is shown, not hidden in the request. "They consented"
                is only defensible if we can say to what, and the screen has to
                show the same words the document row records. */}
            <span className="mt-1 block font-mono text-2xs text-ink-400">
              {stage.consent.version}
            </span>
          </span>
        </label>

        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.docx,.pptx,.xlsx,.xlsm,.csv,.txt,.md"
          disabled={!consented}
          onChange={(e) => choose(e.target.files)}
          className="mt-4 block w-full text-sm text-ink-700 file:mr-4 file:rounded-full file:border-0 file:bg-ink-800 file:px-4 file:py-2 file:text-bone-50 disabled:cursor-not-allowed disabled:opacity-50"
        />
        {!consented ? (
          <p className="mt-2 text-sm text-ink-500">
            Confirm the statement above to choose files.
          </p>
        ) : null}
      </div>

      {uploads.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {uploads.map((upload) => (
            <li
              key={upload.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-100 bg-white px-4 py-3"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-ink-900">
                  {upload.file.name}
                </span>
                {upload.reason ? (
                  <span className="mt-0.5 block text-sm text-clay-600">{upload.reason}</span>
                ) : upload.state === 'done' && upload.chunksHeld ? (
                  <span className="mt-0.5 block text-sm text-ink-500">
                    Indexed. {upload.chunksHeld} section{upload.chunksHeld === 1 ? '' : 's'} are
                    yours only until reviewed.
                  </span>
                ) : null}
              </span>
              {upload.state === 'uploading' ? (
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-400">
                  uploading…
                </span>
              ) : upload.state === 'done' ? (
                <span className="rounded-full bg-steel-100 px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-steel-700">
                  indexed
                </span>
              ) : upload.state === 'failed' ? (
                <button
                  type="button"
                  onClick={() => void send({ ...upload, reason: undefined })}
                  className="rounded-full border border-ink-200 px-3 py-1 font-mono text-2xs uppercase tracking-[0.08em] text-ink-600 hover:border-ink-300"
                >
                  Retry
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={onDone}>{done > 0 ? 'Continue' : 'Skip for now'}</Button>
        {done > 0 ? (
          <span className="text-sm text-ink-500">
            {done} indexed · {remaining} more you can add now
          </span>
        ) : null}
      </div>
    </div>
  )
}
