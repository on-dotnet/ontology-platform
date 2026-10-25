#!/usr/bin/env python3
"""Fail the dedicated PostgreSQL dependency and verify safe 503, liveness and recovery."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

STAGE = 'initialization'
DRIVER = None
ROOT = Path(__file__).resolve().parents[2]
# 默认保留历史入口；后续收口显式选择新证据目录，不覆盖历史事实。
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-WAVE2/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)

SPEC = importlib.util.spec_from_file_location('oidc', ROOT / 'infra/security/verify-oidc.py')
OIDC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OIDC)


def main(path):
    global STAGE, DRIVER
    runtime = json.loads(Path(path).read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    driver = OIDC.ProtocolDriver('http://localhost:15100', 'http://localhost:15101', realm['authority'])
    DRIVER = driver
    # 真实数据库断连可等待默认30秒命令超时，客户端留足75秒且不替换任何响应。
    original_open = driver.opener.open
    driver.opener.open = lambda operation, timeout=20: original_open(operation, timeout=75)
    STAGE = 'real-login'
    print('Fault stage: ' + STAGE, flush=True)
    cookie = driver.login(realm['identities']['wave2-viewer-a'])
    driver.json_request(driver.first, '/api/v1/platform/me', 200, 'healthy-before-dependency-fault')
    driver.json_request(driver.second, '/api/v1/platform/me', 200, 'healthy-twin-before-dependency-fault')
    found = subprocess.check_output(['docker', 'ps', '--filter', 'volume=' + runtime['volumePrefix'] + '-postgres-data', '--format', '{{.ID}}'], text=True).split()
    if len(found) != 1:
        raise ValueError('Expected exactly this run dedicated PostgreSQL')
    target = found[0]
    trace = None
    try:
        STAGE = 'stop-dedicated-db'
        print('Fault stage: ' + STAGE, flush=True)
        subprocess.run(['docker', 'stop', '--time', '10', target], check=True, stdout=subprocess.DEVNULL)
        STAGE = 'authenticated-dependency-request'
        print('Fault stage: ' + STAGE, flush=True)
        problem, headers = driver.json_request(driver.first, '/api/v1/platform/me', 503, 'database-unavailable-is-503')
        trace = headers['X-Trace-Id']
        driver.check('dependency-error-safe-code', problem['code'] == 'dependency_unavailable')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for endpoint, expected in [('live', 200), ('ready', 503)]:
            STAGE = 'health-' + endpoint
            print('Fault stage: ' + STAGE, flush=True)
            request = urllib.request.Request(driver.first + '/health/' + endpoint, headers={'X-Health-Key': runtime['healthKey']})
            try:
                response = opener.open(request, timeout=75)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                driver.check('dependency-fault-health-' + endpoint, response.status == expected, response.status)
    finally:
        subprocess.run(['docker', 'start', target], check=True, stdout=subprocess.DEVNULL)
    STAGE = 'database-recovered'
    print('Fault stage: ' + STAGE, flush=True)
    # 双实例各有独立Npgsql池；PG重启后第二实例首次查询也可能先清理旧断连。
    recovery = []
    for origin in [driver.first, driver.second]:
        for _ in range(30):
            try:
                status = driver.request(origin + '/api/v1/platform/me')[0]
                recovery.append({'instance': origin.rsplit(':', 1)[1], 'httpStatus': status})
                if status == 200:
                    break
            except OSError:
                recovery.append({'instance': origin.rsplit(':', 1)[1], 'httpStatus': None})
            time.sleep(2)
        else:
            raise TimeoutError('Dedicated PostgreSQL recovery failed on an API instance')
        driver.json_request(origin, '/api/v1/platform/me', 200, 'same-cookie-after-dependency-recovery-' + origin.rsplit(':', 1)[1])
    STAGE = 'logout-after-recovery'
    print('Fault stage: ' + STAGE, flush=True)
    driver.logout_and_replay(cookie)
    result = {'status': 'PASS', 'traceId': trace, 'scope': 'one explicit dedicated PostgreSQL stop/start; no other volume touched', 'checks': driver.records, 'recoveryObservations': recovery}
    (EVIDENCE / 'dependency-fault.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('PASS: dependency503, independent live200/ready503 and same-cookie recovery; error TraceId=' + trace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    args = parser.parse_args()
    try:
        main(args.runtime_file)
    except Exception as failure:
        (EVIDENCE / 'dependency-fault-failure.json').write_text(json.dumps({'status': 'FAIL', 'stage': STAGE, 'category': type(failure).__name__, 'currentCheck': DRIVER.current_check if DRIVER else None, 'checks': DRIVER.records if DRIVER else []}, ensure_ascii=False, indent=2) + '\n')
        print('FAIL: dependency fault; stage=' + STAGE + '; category=' + type(failure).__name__ + '; details suppressed')
        raise SystemExit(1)
