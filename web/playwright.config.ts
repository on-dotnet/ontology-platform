import { defineConfig, devices } from '@playwright/test';

// End-to-end smoke tests, run by `./dev.ps1 e2e` inside the e2e image against a throwaway stack.
// E2E_BASE_URL points at that stack's web container; see e2e/e2e.env for the test account.
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  globalSetup: './e2e/global-setup.ts',
  forbidOnly: true,
  retries: 0,
  // One worker: the tests share the seeded ontologies, and the suite is small.
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results/artifacts',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    locale: 'zh-CN',
    storageState: 'test-results/.auth/admin.json',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
