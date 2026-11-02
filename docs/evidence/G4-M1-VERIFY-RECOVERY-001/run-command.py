"""任务命令安全封装与真实退出记录；不改变被测命令、结果或超时语义。"""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
TASK = 'G4-M1-VERIFY-RECOVERY-001'
EVIDENCE = Path(__file__).parent
ARTIFACTS = ROOT / 'artifacts/g4-m1-verify-recovery-001'


def main():
    """在固定任务树执行显式命令，并无损记录stdout与stderr。"""
    label, budget, *command = sys.argv[1:]
    if not re.fullmatch('[a-z][a-z0-9-]{0,63}', label) or not command:
        raise ValueError('INVALID_COMMAND_LABEL')
    receipt = EVIDENCE / (label + '.raw.json')
    if receipt.exists():
        raise ValueError('REFUSE_RECEIPT_OVERWRITE')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', NO_COLOR='1', TERM='dumb')
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    tick = time.monotonic()
    timeline = ARTIFACTS / 'timeline.jsonl'
    fingerprint = hashlib.sha256(b''.join((ROOT / p).read_bytes() for p in [
        'scripts/verify.ps1', 'scripts/tests/FrozenEvidence.Tests.ps1',
        'docs/evidence/' + TASK + '/host-adapter.py',
        'docs/evidence/' + TASK + '/run-command.py'])).hexdigest()
    wrapped = [sys.executable, '-B', str(ROOT / 'scripts/maintenance/task_run_timeline.py'),
               'run', '--path', str(timeline), '--task-id', TASK, '--run-id', 'verify-recovery',
               '--step-id', label, '--input-fingerprint', fingerprint, '--command-label', label,
               '--task-type', 'TEST', '--', *command]
    status = 'COMPLETED'
    process = subprocess.Popen(wrapped, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = process.communicate(timeout=int(budget))
    except subprocess.TimeoutExpired:
        status = 'TIMEOUT'
        os.killpg(process.pid, signal.SIGTERM)
        try:
            out, err = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            out, err = process.communicate()
    code = process.returncode
    value = dict(taskId=TASK, command=command, wrapper=wrapped, startedAtUtc=started,
                 endedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),
                 elapsedSeconds=round(time.monotonic()-tick, 3), exitCode=code, timingStatus=status,
                 head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                 inputFingerprint=fingerprint)
    for name, data in [('stdout', out), ('stderr', err)]:
        (ARTIFACTS / (label + '.' + name)).write_bytes(data)
        value[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())
    receipt.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: value[key] for key in ['command', 'head', 'exitCode', 'timingStatus', 'elapsedSeconds']}))
    return code if code is not None else 124


if __name__ == '__main__':
    sys.exit(main())
