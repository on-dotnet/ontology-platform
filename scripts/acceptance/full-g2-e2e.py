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
    parser.add_argument('--m2-ui-only', action='store_true')
    parser.add_argument('--m3', action='store_true')
    parser.add_argument('--m3-api-only', action='store_true')
    parser.add_argument('--m3-ui-only', action='store_true')
    parser.add_argument('--workspace-smoke-only', action='store_true')
    parser.add_argument('--smoke-fault-check', action='store_true')
    args = parser.parse_args()
    modes = [args.m2_api_only, args.m2_ui_only, args.m3_api_only, args.m3_ui_only, args.workspace_smoke_only]
    if sum(modes) > 1 or (any(modes) and (args.m1 or args.m2 or args.m3)):
        parser.error('Select one partial checkpoint or a full milestone chain')
    runtime = Path(args.runtime_file).resolve()
    if not runtime.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Only this checkout private synthetic runtime is accepted')
    tools = json.loads(subprocess.check_output(['pwsh', '-NoProfile', '-File', 'scripts/bootstrap-web-tools.ps1'], cwd=ROOT, text=True))
    command = [tools['nodePath'], 'scripts/acceptance/g2-live-browser.mjs', str(runtime), '--full']
    if any(modes):
        selected = next(flag for flag, enabled in [('--m2-api-only', args.m2_api_only), ('--m2-ui-only', args.m2_ui_only), ('--m3-api-only', args.m3_api_only), ('--m3-ui-only', args.m3_ui_only), ('--workspace-smoke-only', args.workspace_smoke_only)] if enabled)
        command = [tools['nodePath'], 'scripts/acceptance/g2-live-browser.mjs', str(runtime), selected]
    if args.m1 or args.m2 or args.m3:
        command.append('--m1')
    if args.m2 or args.m3:
        command.append('--m2')
    if args.m3:
        command.append('--m3')
    if args.smoke_fault_check:
        command.append('--smoke-fault-check')
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
