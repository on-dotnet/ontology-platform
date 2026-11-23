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

echo "==> mypy"
mypy

echo "==> pytest"
log="$(mktemp)"
pytest -q | tee "$log"

echo "check.sh: ruff ok, format ok, mypy ok, pytest ok ($(tail -n 1 "$log"))"
