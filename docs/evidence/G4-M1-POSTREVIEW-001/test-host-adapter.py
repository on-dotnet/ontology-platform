#!/usr/bin/env python3
"""验证本任务宿主适配身份和拒绝路径；夹具仅位于任务artifacts。"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).with_name("host-adapter.py")
spec = importlib.util.spec_from_file_location("adapter", SOURCE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
results = []


def check(name, condition):
    """按实际断言记录结果。"""
    assert condition, name
    results.append(name)


def refused(name, path):
    """危险输出必须抛错，不能写入或自动覆盖。"""
    try:
        adapter.destination(str(path))
    except ValueError:
        results.append(name)
        return
    raise AssertionError(name)


base = ROOT / "artifacts/g4-m1-postreview-001"
with tempfile.TemporaryDirectory(prefix="host-test-", dir=base) as tmp:
    fixture = Path(tmp)
    check("exact-task-identity", adapter.host.inspect(system="Linux", task_id=adapter.TASK)["taskId"] == "G4-M1-POSTREVIEW-001")
    check("blocked-policy-propagates", adapter.verdict({"assurance": "BLOCKED_HOST_SLEEP_ASSURANCE"}) == 2)
    check("unknown-propagates", adapter.verdict({"status": "NOT_VERIFIED"}) == 2)
    check("monitor-sleep-propagates", adapter.verdict({"policyContinuouslyReady": True, "sleep": {"status": "OBSERVED_LOG_WINDOW", "confirmedSleepMs": 1}}) == 2)
    check("ready-does-not-invent-continuity", adapter.verdict({"assurance": "POLICY_READY", "sessionContinuity": "NOT_VERIFIED"}) == 0)
    check("valid-output", adapter.destination(str(fixture / "valid.json")) == fixture / "valid.json")
    refused("outside-task", ROOT / "artifacts/other-task/value.json")
    refused("parent-traversal", fixture / "../escape.json")
    existing = fixture / "existing.json"
    existing.write_text("fixture")
    refused("existing-output", existing)
    summary = fixture / "paired.summary.json"
    summary.write_text("fixture")
    refused("existing-summary", fixture / "paired.json")
    link = fixture / "link"
    link.symlink_to(fixture, target_is_directory=True)
    refused("symlink-parent", link / "new.json")
    rejected = subprocess.run([sys.executable, str(SOURCE), "monitor", "--seconds", "7201", "--output", str(fixture / "too-long.json")], capture_output=True)
    check("bounded-cli-rejection", rejected.returncode == 2 and not (fixture / "too-long.json").exists())
check("fixture-cleaned", not fixture.exists())
print(json.dumps({"status": "PASS", "checks": results, "count": len(results), "sourceSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "fixturePath": str(fixture), "fixtureAfterExists": fixture.exists(), "scope": "HOST_ADAPTER_ONLY_PRODUCT_NOT_RUN"}))
