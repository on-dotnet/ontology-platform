#!/usr/bin/env python3
"""Capture an actual authenticated .NET/YARP/Next SSR trace without exporting cookies."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

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
    runtime = json.loads(Path(path).read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    driver = OIDC.ProtocolDriver('http://localhost:15100', 'http://localhost:15101', realm['authority'])
    cookie = driver.login(realm['identities']['wave2-viewer-a'])
    status, headers, body = driver.request(driver.first + '/')
    driver.check('real-yarp-next-ssr', status == 200 and headers.get_content_type() == 'text/html'
                 and '平台资源'.encode() in body and b'Ontology' in body, status)
    driver.check('no-browser-auth-token-fields', not any(value in body for value in [b'access_token', b'clientSecret', b'refresh_token']))
    trace = headers['X-Trace-Id']
    driver.logout_and_replay(cookie)
    result = {'status': 'PASS', 'traceId': trace, 'checks': driver.records,
              'scope': 'real .NET BFF/YARP HTTP client/Next SSR; full Next OTel export is not claimed'}
    (EVIDENCE / 'proxy-correlation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('PASS: actual authenticated YARP/Next SSR; traceId=' + trace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    try:
        main(parser.parse_args().runtime_file)
    except Exception as failure:
        print('FAIL: proxy correlation; category=' + type(failure).__name__ + '; details suppressed')
        raise SystemExit(1)
