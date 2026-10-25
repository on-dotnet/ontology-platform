#!/usr/bin/env python3
"""Suspend only this checkout's two API processes to prove local alert firing/recovery."""
import datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
# 默认保留历史入口；后续收口显式选择新证据目录，不覆盖历史事实。
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-WAVE2/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)

ALERT = '平台心跳停止'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RECORDS = []


def snapshot(phase):
    with OPENER.open('http://localhost:19095/api/v1/rules', timeout=10) as response:
        data = json.load(response)
    rules = [r for g in data['data']['groups'] for r in g['rules'] if r.get('name') == ALERT]
    if len(rules) != 1:
        raise ValueError('Expected exactly one configured heartbeat alert')
    value = {'atUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': phase,
             'state': rules[0]['state'], 'rule': rules[0]}
    RECORDS.append(value)
    print(json.dumps({k: value[k] for k in ['atUtc', 'phase', 'state']}, ensure_ascii=False), flush=True)
    return value['state']


def main():
    binary = ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api'
    pattern = '^' + re.escape(str(binary)) + r'(\s|$)'
    found = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True, check=True)
    targets = [int(p) for p in found.stdout.split()]
    if len(targets) != 2 or os.name == 'nt':
        raise ValueError('Requires exactly two explicit local API processes on Unix')
    # 首次请求触发正式遥测源注册；匿名拒绝仍为真实API请求。
    for port in [15100, 15101]:
        try:
            OPENER.open(f'http://localhost:{port}/api/v1/platform/me', timeout=10).close()
        except urllib.error.HTTPError as response:
            if response.code != 401:
                raise
    for _ in range(8):
        if snapshot('baseline') == 'inactive':
            break
        time.sleep(5)
    else:
        raise ValueError('Alert is not initially healthy')
    fired = False
    recovered = False
    try:
        for pid in targets:
            os.kill(pid, signal.SIGSTOP)
        RECORDS.append({'phase': 'fault', 'method': 'SIGSTOP', 'target': 'exact two APIs in this checkout', 'processCount': 2})
        for _ in range(10):
            time.sleep(10)
            if snapshot('suspended') == 'firing':
                fired = True
                break
    finally:
        for pid in targets:
            os.kill(pid, signal.SIGCONT)
        RECORDS.append({'phase': 'restore', 'method': 'SIGCONT', 'processCount': 2})
    for _ in range(12):
        time.sleep(5)
        if snapshot('restored') == 'inactive':
            recovered = True
            break
    result = {'status': 'PASS' if fired and recovered else 'FAIL', 'fired': fired, 'recovered': recovered,
              'notification': 'local Prometheus rule/alert state only; no external recipients', 'records': RECORDS}
    out = EVIDENCE / 'alert-drill.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return 0 if fired and recovered else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print('FAIL: alert drill; category=' + type(failure).__name__ + '; details suppressed')
        raise SystemExit(1)
