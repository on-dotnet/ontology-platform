// Prints a short test count summary from a Vitest JSON report: `node vitest-summary.mjs <report.json>`.
import { readFileSync } from 'node:fs';

const file = process.argv[2];
try {
  const report = JSON.parse(readFileSync(file, 'utf8'));
  const files = report.testResults?.length ?? 0;
  console.log(
    `tests: ${report.numPassedTests} passed, ${report.numFailedTests} failed, ` +
      `${report.numPendingTests + report.numTodoTests} skipped, ${report.numTotalTests} total; files: ${files}`,
  );
} catch {
  console.log('tests: no report');
}
