#!/usr/bin/env python3
"""Verify only this run's seven containers retain identity, audit and telemetry.

Cookies and random passwords remain in memory; evidence contains safe checks only.
The test restarts explicit names captured from the dedicated AppHost, never prunes.
"""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
# 默认保留历史入口；后续收口显式选择新证据目录，不覆盖历史事实。
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-WAVE2/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)

SPEC = importlib.util.spec_from_file_location('oidc', ROOT / 'infra/security/verify-oidc.py')
OIDC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OIDC)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), OIDC.NoRedirect())
CHECKS = []


def check(name, condition, detail=None):
    CHECKS.append({'check': name, 'status': 'PASS' if condition else 'FAIL', 'detail': detail})
    print(name + ': ' + CHECKS[-1]['status'], flush=True)
    if not condition:
        raise AssertionError('Persistence check failed')


def request(origin, path, headers=None, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    operation = urllib.request.Request(origin + path, data=body, headers=(headers or {}) | {'Content-Type': 'application/json'})
    try:
        response = OPENER.open(operation, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            value = None
        return response.status, value


def available(runtime):
    for origin, path in [('http://localhost:13100', '/ready'), ('http://localhost:13200', '/ready'),
                         ('http://localhost:19095', '/-/ready'), ('http://localhost:15330', '/api/health'),
                         ('http://localhost:18080', '/realms/master/.well-known/openid-configuration')]:
        if request(origin, path)[0] != 200:
            return False
    # 两个API各自持有数据库池；七容器重启后的流量恢复必须逐实例等待真实三表查询。
    return all(request(origin, '/health/ready', {'X-Health-Key': runtime['healthKey']})[0] == 200
               for origin in ['http://localhost:15100', 'http://localhost:15101'])


def main(runtime_path):
    runtime = json.loads(Path(runtime_path).read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    viewer = OIDC.ProtocolDriver('http://localhost:15100', 'http://localhost:15101', realm['authority'])
    cookie = viewer.login(realm['identities']['wave2-viewer-a'])
    before, _ = viewer.json_request(viewer.first, '/api/v1/platform/me', 200, 'before-identity')
    resource, headers = viewer.json_request(viewer.first, '/api/v1/platform/resources?siteId=site-a', 200, 'before-resource')
    audit_id = resource['auditId']
    trace = headers['X-Trace-Id']
    auditor = OIDC.ProtocolDriver(viewer.first, viewer.second, realm['authority'])
    auditor.login(realm['identities']['wave2-auditor-a'])
    audit, _ = auditor.json_request(auditor.first, '/api/v1/platform/audit?limit=100', 200, 'before-audit')
    check('before-pg-audit-visible', any(row['id'] == audit_id for row in audit), {'auditId': audit_id, 'traceId': trace})
    auth = {'Authorization': 'Basic ' + base64.b64encode(('platform-dev-admin:' + runtime['grafanaPassword']).encode()).decode()}
    marker = 'wave2-persistence-' + os.urandom(5).hex()
    status, annotation = request('http://localhost:15330', '/api/annotations', auth,
                                 {'text': 'Wave2 合成持久化验收', 'tags': [marker]})
    check('before-grafana-state-created', status == 200 and isinstance(annotation.get('id'), int))
    annotation_id = annotation['id']
    prom_time = str(time.time() - 10)
    metric_query = urllib.parse.urlencode({'query': 'sum(platform_requests_total{service_name="ontology-platform-api"})', 'time': prom_time})
    status, prom = request('http://localhost:19095', '/api/v1/query?' + metric_query)
    old_metrics = prom['data']['result']
    check('before-prometheus-history', status == 200 and len(old_metrics) == 1)
    for _ in range(12):
        if request('http://localhost:13200', '/api/traces/' + trace)[0] == 200:
            break
        time.sleep(3)
    else:
        raise ValueError('Trace must exist before restart')
    bindings = json.loads((EVIDENCE / 'container-bindings.json').read_text())
    names = [row['container'] for row in bindings]
    check('bounded-container-set', len(names) == 7 and {name.split('-')[0] for name in names} == {'postgres', 'keycloak', 'alloy', 'loki', 'tempo', 'prometheus', 'grafana'})
    # PostgreSQL卷前缀再次验证，拒绝把历史或其他项目容器作为本轮fixture。
    postgres = next(name for name in names if name.startswith('postgres-'))
    mounts = json.loads(subprocess.check_output(['docker', 'inspect', '--format', '{{json .Mounts}}', postgres], text=True))
    check('dedicated-volume-guard', any(m.get('Name') == runtime['volumePrefix'] + '-postgres-data' for m in mounts))
    restarted = subprocess.run(['docker', 'restart', *names], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    check('seven-container-restart', restarted.returncode == 0, {'count': 7, 'names': names, 'volumes': 'preserved'})
    for _ in range(45):
        try:
            if available(runtime):
                break
        except (OSError, ValueError):
            pass
        time.sleep(3)
    else:
        raise TimeoutError('Stack recovery incomplete')
    for origin in [viewer.first, viewer.second]:
        after, _ = viewer.json_request(origin, '/api/v1/platform/me', 200, 'after-cookie-identity')
        check('same-cookie-after-pg-kc-restart-' + origin.rsplit(':', 1)[1], after == before)
    after_audit, _ = auditor.json_request(auditor.first, '/api/v1/platform/audit?limit=100', 200, 'after-audit')
    check('pg-audit-record-survives', any(row['id'] == audit_id and row['traceId'] == trace for row in after_audit))
    status, _ = request('http://localhost:13200', '/api/traces/' + trace)
    check('tempo-trace-survives', status == 200, {'traceId': trace})
    log_query = urllib.parse.urlencode({'query': '{service_name="ontology-platform-api"} | trace_id="' + trace + '"', 'limit': 100, 'start': str(int((time.time() - 900) * 1e9))})
    status, logs = request('http://localhost:13100', '/loki/api/v1/query_range?' + log_query)
    check('loki-same-trace-survives', status == 200 and any(row.get('values') for row in logs['data']['result']))
    status, prom = request('http://localhost:19095', '/api/v1/query?' + metric_query)
    check('prometheus-historical-sample-survives', status == 200 and prom['data']['result'] == old_metrics)
    status, annotations = request('http://localhost:15330', '/api/annotations?' + urllib.parse.urlencode({'tags': marker}), auth)
    check('grafana-state-survives', status == 200 and any(row['id'] == annotation_id for row in annotations))
    fresh = OIDC.ProtocolDriver(viewer.first, viewer.second, realm['authority'])
    fresh_cookie = fresh.login(realm['identities']['wave2-viewer-b'])
    me, _ = fresh.json_request(fresh.first, '/api/v1/platform/me', 200, 'fresh-identity-after-restart')
    check('keycloak-realm-user-login-survives', me['scopes'][0]['siteId'] == 'site-b')
    fresh.logout_and_replay(fresh_cookie)
    viewer.logout_and_replay(cookie)
    (EVIDENCE / 'persistence.json').write_text(json.dumps({'status': 'PASS', 'scope': 'seven explicit development containers; API process restart is separately checked', 'checks': CHECKS}, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(main(args.runtime_file))
    except Exception as failure:
        (EVIDENCE / 'persistence-failure.json').write_text(json.dumps({'status': 'PARTIAL', 'category': type(failure).__name__, 'checks': CHECKS}, ensure_ascii=False, indent=2) + '\n')
        print('PARTIAL: persistence; category=' + type(failure).__name__ + '; details suppressed')
        raise SystemExit(1)
