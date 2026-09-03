import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

/**
 * Vitest for components and BFF route handlers — the two layers Playwright is
 * the wrong tool for.
 *
 * Playwright proves the journey works end to end; it is slow, needs a server
 * and a database, and tells you almost nothing about *why* something broke. A
 * component that renders "3 uploaded" when one file was a scan should fail in
 * milliseconds, next to the component, not thirty seconds into a browser run.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    // Playwright's specs live in e2e/ and are driven by `playwright test`.
    // Without this Vitest collects them, and they fail on an import it has
    // never heard of rather than on anything real.
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
  },
})
