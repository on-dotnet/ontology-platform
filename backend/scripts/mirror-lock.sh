#!/bin/sh
# Point the image's copy of uv.lock at a PyPI mirror before `uv sync --frozen`.
# Mirrors serve the same files under the same paths, so the locked hashes still verify them.
# No-op unless PYPI_FILES_MIRROR is set; the repository's uv.lock keeps the official URLs.
# Usage: mirror-lock.sh [lock file, default uv.lock]
set -eu
lock="${1:-uv.lock}"
[ -n "${PYPI_FILES_MIRROR:-}" ] || exit 0

files="${PYPI_FILES_MIRROR%/}/"
index="${PIP_INDEX_URL:-https://pypi.org/simple}"
index="${index%/}"
case "$files$index" in
    *'&'* | *'#'* | *'\'* | *'|'*)
        echo "mirror-lock: mirror URLs must not contain &, #, \\ or |" >&2
        exit 1
        ;;
esac

sed -i \
    -e "s#https://files.pythonhosted.org/#${files}#g" \
    -e "s#registry = \"https://pypi.org/simple\"#registry = \"${index}\"#g" \
    "$lock"
if grep -q 'files\.pythonhosted\.org' "$lock"; then
    echo "mirror-lock: $lock still references files.pythonhosted.org" >&2
    exit 1
fi
echo "mirror-lock: downloads redirected to ${files}"
