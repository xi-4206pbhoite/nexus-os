/**
 * Turning whatever the API returned into a string a person can read.
 *
 * Extracted because the absence of it caused a real crash. `PreviewForm` —
 * since retired with the rest of the pre-signup audit — assigned
 * `payload.detail` straight into a `string` and rendered it. That
 * holds for every error the API raises deliberately — those carry a string —
 * but **FastAPI's own validation errors carry an array of objects**. A URL over
 * the 2048-character limit produced one, React was handed an object as a child,
 * and with no error boundary the whole landing page went white.
 *
 * The lesson is not "add a guard at that call site": it is that `detail` is
 * `unknown` at the boundary and every reader has to treat it that way. This is
 * the one place that does.
 */

/** The first human-readable message in an API error payload, or `fallback`. */
export function messageFrom(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return fallback

  const detail = (payload as { detail: unknown }).detail

  // The normal case: an error the API raised on purpose, written to be shown.
  if (typeof detail === 'string' && detail.trim() !== '') return detail

  // FastAPI request validation: [{ type, loc, msg, input, ctx }, …].
  // The first message is the useful one; the rest repeat it per field.
  if (Array.isArray(detail)) {
    for (const entry of detail) {
      if (entry && typeof entry === 'object') {
        const msg = (entry as { msg?: unknown }).msg
        if (typeof msg === 'string' && msg.trim() !== '') return msg
      }
    }
  }

  return fallback
}
