#!/bin/sh
# Runs lint, typecheck and unit tests at the same time (they only read the sources), then prints
# each step's output in that order and a single summary line.
# Every step runs even if another one fails; the exit code is non-zero if any step failed.

report=/tmp/vitest-report.json
logs=$(mktemp -d)

start() {
  name=$1
  shift
  ("$@" >"$logs/$name.log" 2>&1; echo $? >"$logs/$name.status") &
}

start lint pnpm run lint
start typecheck pnpm run typecheck
start vitest pnpm exec vitest run --reporter=default --reporter=json --outputFile.json="$report"
wait

results=""
status=0
for name in lint typecheck vitest; do
  echo "==> $name"
  cat "$logs/$name.log"
  if [ "$(cat "$logs/$name.status" 2>/dev/null)" = 0 ]; then
    results="$results $name=ok"
  else
    results="$results $name=fail"
    status=1
  fi
done

tests=$(node scripts/vitest-summary.mjs "$report")
echo "test-web summary:$results ($tests)"
exit $status
