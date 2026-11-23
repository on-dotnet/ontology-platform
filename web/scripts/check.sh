#!/bin/sh
# Runs lint, typecheck and unit tests in order, then prints a single summary line.
# Every step runs even if an earlier one fails; the exit code is non-zero if any step failed.

results=""
status=0
report=/tmp/vitest-report.json

step() {
  name=$1
  shift
  echo "==> $name"
  if "$@"; then
    results="$results $name=ok"
  else
    results="$results $name=fail"
    status=1
  fi
}

step lint pnpm run lint
step typecheck pnpm run typecheck
step vitest pnpm exec vitest run --reporter=default --reporter=json --outputFile.json="$report"

tests=$(node scripts/vitest-summary.mjs "$report")
echo "test-web summary:$results ($tests)"
exit $status
