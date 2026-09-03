import { defineConfig, devices } from '@playwright/test'

/**
 * The browser journey, run against a real deployment.
 *
 * `doc/12` P9 asks for this **before** the Dockerfiles, so that "it works
 * deployed" means something specific rather than "the container started". The
 * journey is the whole flow P5–P8 built: land, sign up, verify, register the
 * company, five questions, departments, answer your own block, upload a
 * document, reach the dashboard.
 *
 * `baseURL` comes from the environment so the same spec runs against the dev
 * server locally and against the composed stack in CI. A spec that only knows
 * how to reach `localhost:3001` proves nothing about a deployment.
 *
 * **No `webServer` block.** Starting the app from here would prove the app
 * starts *the way Playwright starts it*, which is not how it is deployed. The
 * stack is brought up by whatever is under test — `docker compose` in CI, the
 * dev server locally — and this only drives a browser at it.
 */
export default defineConfig({
  testDir: './e2e',
  // The journey has real network and a real database behind it; the default
  // 30s expects a local unit test.
  timeout: 120_000,
  expect: { timeout: 20_000 },
  // Serial. The journey registers a company, and one-company-per-founder means
  // two of them racing is a test failing for a reason the product is right about.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: process.env.NEXUS_E2E_BASE_URL ?? 'http://localhost:3001',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
