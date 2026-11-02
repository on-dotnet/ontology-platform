#!/usr/bin/env python3
"""本任务宿主观测薄适配；复用原实现，不修改系统能源策略。"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M1-MAIN-INTEGRATION-001'


def main():
    """仅允许本任务新证据目录和有界监测，拒绝旧任务身份。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'monitor'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=7200)
    parser.add_argument('--interval', type=int, default=10)
    args = parser.parse_args()
    target = args.output.absolute()
    boundary = ROOT / 'artifacts/g4-m1-main-integration-001'
    if '..' in target.parts or target == boundary or not target.is_relative_to(boundary) or any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('TASK_OUTPUT_BOUNDARY')
    if not 1 <= args.seconds <= 14400 or not 1 <= args.interval <= 60 or target.exists():
        raise ValueError('BOUND_OR_EXISTING_OUTPUT')
    summary = target.with_suffix('.summary.json')
    if args.mode == 'monitor' and (summary.exists() or summary.is_symlink() or summary == target):
        raise ValueError('EXISTING_OR_UNSAFE_SUMMARY')
    source = ROOT / 'scripts/maintenance/host_continuity.py'
    spec = importlib.util.spec_from_file_location('approved_host_monitor', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == 'preflight':
        result = module.inspect(task_id=TASK)
        module.save(target, result)
    else:
        result = module.monitor(target, args.seconds, args.interval, TASK)
    print(json.dumps(result, ensure_ascii=False))
    if result.get('assurance') == 'BLOCKED_HOST_SLEEP_ASSURANCE' or result.get('policyContinuouslyReady') is False:
        return 2
    if args.mode == 'monitor' and (result['sleep']['status'] == 'NOT_VERIFIED' or result['sleep']['confirmedSleepMs'] != 0):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
