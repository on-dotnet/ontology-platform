#!/usr/bin/env python3
"""Run the genuine full G2 browser chain using exact project Node and a private synthetic runtime."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    parser.add_argument('--m1', action='store_true')
    parser.add_argument('--m2', action='store_true')
    parser.add_argument('--m2-api-only', action='store_true')
    args = parser.parse_args()
    runtime = Path(args.runtime_file).resolve()
    if not runtime.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Only this checkout private synthetic runtime is accepted')
    tools = json.loads(subprocess.check_output(['pwsh', '-NoProfile', '-File', 'scripts/bootstrap-web-tools.ps1'], cwd=ROOT, text=True))
    command = [tools['nodePath'], 'scripts/acceptance/g2-live-browser.mjs', str(runtime), '--full']
    if args.m2_api_only:
        command = [tools['nodePath'], 'scripts/acceptance/g2-live-browser.mjs', str(runtime), '--m2-api-only']
    if args.m1 or args.m2:
        command.append('--m1')
    if args.m2:
        command.append('--m2')
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
