#!/usr/bin/env python3
"""Hold a real BFF cookie in memory while Master replaces the AppHost/API processes."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time

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
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / '.tools/security').resolve()) or (os.name != 'nt' and path.stat().st_mode & 0o077):
        raise ValueError('Expected this run private configuration')
    runtime = json.loads(path.read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    driver = OIDC.ProtocolDriver('http://localhost:15100', 'http://localhost:15101', realm['authority'])
    cookie = driver.login(realm['identities']['wave2-viewer-a'])
    before, _ = driver.json_request(driver.first, '/api/v1/platform/me', 200, 'before-process-restart')
    twin, _ = driver.json_request(driver.second, '/api/v1/platform/me', 200, 'before-twin')
    if twin != before:
        raise AssertionError('Initial identity mismatch')
    print('READY_FOR_RESTART: real cookie remains only in this process memory; press Enter after controlled restart.', flush=True)
    input()
    for origin in [driver.first, driver.second]:
        for _ in range(60):
            try:
                status, _, _ = driver.request(origin + '/api/v1/platform/me')
                if status == 200:
                    break
            except OSError:
                pass
            time.sleep(2)
        else:
            raise TimeoutError('API did not accept existing cookie after restart')
        after, _ = driver.json_request(origin, '/api/v1/platform/me', 200, 'same-cookie-after-process-restart')
        driver.check('same-identity-after-process-restart', after == before)
    driver.logout_and_replay(cookie)
    out = EVIDENCE / 'api-process-restart.json'
    out.write_text(json.dumps({'status': 'PASS', 'scope': 'same in-memory real cookie across new AppHost and two API process IDs with persisted shared certificate/keyring and PostgreSQL', 'checks': driver.records}, ensure_ascii=False, indent=2) + '\n')
    print('PASS: same authenticated identity on both new API processes; logout/replay denied.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    args = parser.parse_args()
    try:
        main(args.runtime_file)
    except Exception as failure:
        print('FAIL: process restart cookie check; category=' + type(failure).__name__ + '; details suppressed', flush=True)
        raise SystemExit(1)
