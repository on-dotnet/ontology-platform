#!/usr/bin/env bash
# Backend quality gate: lint, formatting, static types, tests. Run from any directory.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> ruff check"
ruff check .

echo "==> ruff format --check"
if ! ruff format --check .; then
    ruff format --diff . || true
    exit 1
fi

# mypy (about 17 s) and pytest share nothing, so mypy runs in the background meanwhile.
mypy_log="$(mktemp)"
mypy >"$mypy_log" 2>&1 &
mypy_pid=$!

# 8 workers measured fastest on the 16-core Docker host (12 and 16 gain nothing) and leave room
# for test-web, the image build and another workspace running at the same time. 0 = one process.
workers="${OP_TEST_WORKERS:-8}"
echo "==> pytest (-n $workers)"
log="$(mktemp)"
pytest_status=0
pytest -q -n "$workers" | tee "$log" || pytest_status=$?

mypy_status=0
wait "$mypy_pid" || mypy_status=$?
echo "==> mypy"
cat "$mypy_log"

if [ "$mypy_status" -ne 0 ] || [ "$pytest_status" -ne 0 ]; then
    echo "check.sh: mypy exit $mypy_status, pytest exit $pytest_status"
    exit 1
fi
echo "check.sh: ruff ok, format ok, mypy ok, pytest ok ($(tail -n 1 "$log"))"
