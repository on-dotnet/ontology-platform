import { test as base, expect, type ConsoleMessage } from '@playwright/test';

export { expect };

export const STORAGE_STATE = 'test-results/.auth/admin.json';
export const SIGNED_OUT = { cookies: [], origins: [] };

/** Seeded by global-setup.ts; the tests pick the second one so that choosing it is a real switch. */
export const SEEDED_ONTOLOGIES = [
  { key: 'e2e-smoke-a', name: 'E2E 冒烟本体 A' },
  { key: 'e2e-smoke-b', name: 'E2E 冒烟本体 B' },
] as const;

export function credentials(): { username: string; password: string } {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) throw new Error('E2E_USERNAME and E2E_PASSWORD must be set (see e2e/e2e.env)');
  return { username, password };
}

// A signed-out page asks /api/auth/me first and gets 401; the browser logs that as a failed load.
function expectedWhileSignedOut(message: ConsoleMessage): boolean {
  return message.text().includes('status of 401') && message.location().url.endsWith('/api/auth/me');
}

/** Every test fails if the page logged a console error or threw, apart from the expected 401 above. */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' && !expectedWhileSignedOut(message)) {
          errors.push(`${message.text()} (${message.location().url})`);
        }
      });
      page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
      await use(errors);
      expect(errors, 'console errors').toEqual([]);
    },
    { auto: true },
  ],
});
