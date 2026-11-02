#!/usr/bin/env python3
"""本任务宿主适配；只读系统状态，仅输出本树artifacts，不改变共享CLI。"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = "G4-M1-POSTREVIEW-001"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("host", ROOT / "scripts/maintenance/host_continuity.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def destination(value):
    """复用共享路径守卫后限缩本任务子目录，拒绝覆写及链接。"""
    target = Path(value).absolute()
    if not target.is_relative_to(ROOT / "artifacts/g4-m1-postreview-001"):
        raise ValueError("OUTSIDE_TASK_OUTPUT")
    if target.exists() or target.with_suffix(".summary.json").exists():
        raise ValueError("REFUSE_OVERWRITE")
    return host.output_path(str(target))


def verdict(value):
    """保持原宿主失败含义，不将未知状态转成成功。"""
    if value.get("assurance") == "BLOCKED_HOST_SLEEP_ASSURANCE" or value.get("status") == "NOT_VERIFIED":
        return 2
    if "policyContinuouslyReady" in value and (not value["policyContinuouslyReady"] or value["sleep"]["status"] == "NOT_VERIFIED" or value["sleep"]["confirmedSleepMs"] != 0):
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["preflight", "monitor"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--seconds", type=int, default=7200)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 7200:
        raise ValueError("TIME_BUDGET")
    target = destination(args.output)
    if args.mode == "preflight":
        result = host.inspect(task_id=TASK)
        host.save(target, result)
    else:
        result = host.monitor(target, args.seconds, 10, TASK)
    print(json.dumps(result, ensure_ascii=False))
    return verdict(result)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(type(error).__name__, file=sys.stderr)
        sys.exit(2)
