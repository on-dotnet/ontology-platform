"""Check changed handwritten TSX lines without rewriting source or installing a formatter."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='d6aab6b47e63c9d5deadfa480f6659c62c5ed138')
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()
    result = subprocess.run(['git', 'diff', '--name-only', '--diff-filter=ACMR', args.base, '--', 'apps/web/src'],
                            cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Readability base is unavailable; refusing an empty success')
    checked = 0
    failures = []
    for name in result.stdout.splitlines():
        if not name.endswith('.tsx'):
            continue
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Unexpected changed source path')
        checked += 1
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if len(line) > args.limit:
                failures.append(f'{name}:{number}: {len(line)} characters')
    for failure in failures:
        print('FAIL: ' + failure)
    print(f'Changed TSX readability: {checked} files, {len(failures)} violations, limit={args.limit}; component quality requires independent review.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
