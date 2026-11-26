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

/** An API answer a test expects to be an error; the browser logs it as a failed load anyway. */
export interface ExpectedFailedLoad {
  status: number;
  path: RegExp;
}

/** A signed-out page asks who is signed in first. */
export const SIGNED_OUT_CHECK: ExpectedFailedLoad = { status: 401, path: /^\/api\/auth\/me$/ };

// The text is Chromium's own (English in the e2e image, whatever the page locale).
function isExpectedFailedLoad(message: ConsoleMessage, expected: readonly ExpectedFailedLoad[]): boolean {
  const url = message.location().url;
  if (!url) return false;
  const path = new URL(url).pathname;
  return expected.some(({ status, path: pattern }) => message.text().includes(`status of ${status} `) && pattern.test(path));
}

/**
 * Every test fails if the page logged a console error or threw. A test lists the error answers
 * it expects in `expectedFailedLoads`; nothing else is let through.
 */
export const test = base.extend<{ expectedFailedLoads: ExpectedFailedLoad[]; consoleErrors: string[] }>({
  expectedFailedLoads: [[], { option: true }],
  consoleErrors: [
    async ({ page, expectedFailedLoads }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' && !isExpectedFailedLoad(message, expectedFailedLoads)) {
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
