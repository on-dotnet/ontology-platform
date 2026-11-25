// Proves the accessibility and hooks rules still report: a clean `eslint .` cannot tell a passing
// codebase from a plugin that silently stopped working on an ESLint version it does not declare.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

import { ESLint } from 'eslint';

// Containers set CI=true, which makes typescript-eslint type-check the file on disk instead of the
// snippet passed in below.
process.env.TSESTREE_SINGLE_RUN = 'false';

const violations = `
import { useState } from 'react';

export function Violations({ flag }: { flag: boolean }) {
  if (flag) useState(0);
  return (
    <div onClick={() => undefined}>
      <img src="a.png" />
    </div>
  );
}
`;
const expected = [
  'jsx-a11y/alt-text',
  'jsx-a11y/click-events-have-key-events',
  'react-hooks/rules-of-hooks',
];

const eslint = new ESLint({ cwd: fileURLToPath(new URL('..', import.meta.url)) });
// Type-aware rules only accept files that a tsconfig includes, so the snippet borrows a real path.
const [result] = await eslint.lintText(violations, { filePath: 'src/main.tsx' });
const fatal = result.messages.find((m) => m.fatal);
assert.ok(!fatal, `could not lint the snippet, check the borrowed path: ${fatal?.message}`);
const errors = new Set(result.messages.filter((m) => m.severity === 2).map((m) => m.ruleId));
const missing = expected.filter((rule) => !errors.has(rule));
assert.equal(
  missing.length,
  0,
  `rules that no longer report: ${missing.join(', ')}\n${JSON.stringify(result.messages, null, 2)}`,
);
console.log(`lint self-check ok: ${expected.join(', ')}`);
