"""G6任务自有廉价前置门禁：只检查输入、路径和合同，不执行网络或产品入口。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
BASE = "d1a61daffe844475b07705797e3ad325cc3f2945"
TASK = "G6-P0-PARSER-PREP-001"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).splitlines()


def validate_manifest(raw):
    if hashlib.sha256(raw).hexdigest() != "c1f7248a3e7254d325c63a4d3c1e9a0f9e2396eb2486c0cf65bcb350714d2e13":
        raise ValueError("MANIFEST_HASH_MISMATCH")
    return json.loads(raw)


def discover_count(path):
    loader = unittest.TestLoader()
    suite = loader.discover(str(path), "test_*.py")
    def failed(item):
        if isinstance(item, unittest.TestSuite): return any(failed(child) for child in item)
        return isinstance(item, unittest.loader._FailedTest)
    if loader.errors or failed(suite): raise ValueError("TEST_IMPORT_FAILED")
    count = suite.countTestCases()
    if count == 0: raise ValueError("ZERO_TESTS")
    return count


def main():
    archive = ROOT / "docs/evidence" / TASK / "input"
    manifest = validate_manifest((archive / "MANIFEST.json").read_bytes())
    count = 0
    for row in manifest["files"]:
        name = row["path"]
        if name.startswith("fixtures/"):
            raw = (ROOT / "experiments/g6-p0" / name).read_bytes()
        else:
            wrapped = json.loads((archive / Path(name).with_suffix(".source.json")).read_text())
            raw = wrapped["utf8Text"].encode("utf-8")
        if len(raw) != row["size_bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("INPUT_HASH_MISMATCH")
        count += 1
    paths = set(git("diff", "--name-only", BASE)) | set(git("ls-files", "--others", "--exclude-standard"))
    allowed = ("experiments/g6-p0/", "docs/evidence/" + TASK + "/")
    if any(p != "docs/tasks/" + TASK + ".md" and not p.startswith(allowed) for p in paths):
        raise ValueError("OWNED_PATH_VIOLATION")
    counts = {}
    for name in ("tests", "harness"):
        counts[name] = discover_count(ROOT / "experiments/g6-p0" / name)
    print(json.dumps({"taskId": TASK, "status": "PREFLIGHT_ONLY", "inputMembers": count,
        "testCounts": counts, "head": git("rev-parse", "HEAD")[0],
        "publicContractsChanged": False, "diAuditConsumers": "NOT_APPLICABLE_NO_PRODUCT_CHANGES",
        "runtime": "NOT_RUN", "ci": "NOT_RUN"}))


if __name__ == "__main__":
    main()
