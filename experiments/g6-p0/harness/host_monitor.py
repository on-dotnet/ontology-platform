"""G6 归属适配：复用只读宿主检查，不修改公共脚本或系统能源策略。"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
TASK = "G6-P0-PARSER-PREP-001"


def main():
    spec = importlib.util.spec_from_file_location("host_continuity", ROOT / "scripts/maintenance/host_continuity.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    original_inspect, original_save = host.inspect, host.save

    def inspect():
        row = original_inspect()
        row["taskId"] = TASK
        return row

    def save(path, row, append=False):
        row["taskId"] = TASK
        original_save(path, row, append)

    host.inspect, host.save = inspect, save
    target = host.output_path(str(ROOT / "artifacts/g6-p0/host.jsonl"))
    print(json.dumps({"taskId": TASK, "mode": "bounded-readonly", "seconds": 28800}), flush=True)
    result = host.monitor(target, 28800, 15)
    result["taskId"] = TASK
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
