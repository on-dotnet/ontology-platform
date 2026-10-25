#!/usr/bin/env python3
"""Exercise committed audit-read facts and a bounded INSERT fault through real LGTM.

This runner uses only this checkout's explicitly supplied synthetic runtime.
It never exports cookies, identity rows, raw SQL output or private configuration.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-CLOSE-001/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)
SPEC = importlib.util.spec_from_file_location('closeout_oidc', ROOT / 'infra/security/verify-oidc.py')
OIDC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OIDC)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CHECKS = []


def check(name, condition):
    CHECKS.append({'check': name, 'status': 'PASS' if condition else 'FAIL'})
    print(name + ': ' + CHECKS[-1]['status'], flush=True)
    if not condition:
        raise AssertionError('Closeout acceptance failed')


def fetch(origin, path):
    with OPENER.open(origin + path, timeout=10) as response:
        return json.load(response)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main(runtime_path):
    path = Path(runtime_path).resolve()
    if not path.is_relative_to((ROOT / '.tools/security').resolve()) or (os.name != 'nt' and path.stat().st_mode & 0o077):
        raise ValueError('Expected this checkout private runtime')
    runtime = json.loads(path.read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    driver = OIDC.ProtocolDriver('http://localhost:15100', 'http://localhost:15101', realm['authority'])
    cookie = driver.login(realm['identities']['wave2-auditor-a'])
    identity, _ = driver.json_request(driver.first, '/api/v1/platform/me', 200, 'real-auditor-identity')
    subject = identity['subjectId']
    if not re.fullmatch(r'[a-fA-F0-9-]{16,64}', subject):
        raise ValueError('Expected synthetic Keycloak UUID')
    containers = subprocess.check_output(['docker', 'ps', '--filter', 'volume=' + runtime['volumePrefix'] + '-postgres-data', '--format', '{{.Names}}'], text=True).split()
    if len(containers) != 1:
        raise ValueError('Expected this runtime dedicated PostgreSQL')
    database = containers[0]
    env = os.environ.copy()
    env['PGPASSWORD'] = runtime['postgresPassword']

    def sql(statement):
        result = subprocess.run(['docker', 'exec', '--env', 'PGPASSWORD', database, 'psql', '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'governance', '-c', statement], env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Dedicated PostgreSQL operation failed; details suppressed')
        return result.stdout.strip()

    count_query = 'SELECT count(*) FROM governance.audit_records WHERE "Actor"=\'' + subject + '\' AND "Action"=\'platform.audit.read\''
    before = int(sql(count_query))
    rows, headers = driver.json_request(driver.first, '/api/v1/platform/audit?limit=100', 200, 'real-audit-read-success')
    own_id = headers.get('X-Audit-Id')
    trace = headers['X-Trace-Id']
    check('success-read-commits-exactly-one-fact', bool(own_id) and int(sql(count_query)) == before + 1)
    check('success-response-excludes-own-event', all(row['id'] != own_id for row in rows))
    check('complete-real-single-site-scope', all(row['scopeSiteIds'] == ['site-a'] and row['organizationId'] == 'org-demo' for row in rows))
    check('success-valid-trace', bool(re.fullmatch('[a-f0-9]{32}', trace)) and trace != '0' * 32)
    persisted = sql('SELECT count(*) FROM governance.audit_records WHERE "Id"=\'' + own_id + '\' AND "TraceId"=\'' + trace + '\' AND "ScopeSiteIds"=ARRAY[\'site-a\']::text[]')
    check('returned-audit-id-is-real-persisted-scope-and-trace', persisted == '1')
    function = 'closeout_fail_' + secrets.token_hex(6)
    marker = 'synthetic-closeout-confidential-marker'
    installed = False
    try:
        sql('CREATE FUNCTION governance.' + function + '() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW."Actor"=\'' + subject + '\' AND NEW."Action"=\'platform.audit.read\' THEN RAISE EXCEPTION \'' + marker + '\'; END IF; RETURN NEW; END $$; CREATE TRIGGER ' + function + ' BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.' + function + '();')
        installed = True
        body, failed_headers = driver.json_request(driver.first, '/api/v1/platform/audit?limit=100', 503, 'audit-insert-fails-closed')
        fault_trace = failed_headers['X-Trace-Id']
        check('insert-failure-no-success-audit-id', not failed_headers.get('X-Audit-Id'))
        check('insert-failure-no-new-success-fact', int(sql(count_query)) == before + 1)
        check('insert-failure-safe-problem', body['code'] == 'dependency_unavailable' and marker not in json.dumps(body))
    finally:
        if installed:
            sql('DROP TRIGGER ' + function + ' ON governance.audit_records; DROP FUNCTION governance.' + function + '();')
    recovered, _ = driver.json_request(driver.first, '/api/v1/platform/audit?limit=100', 200, 'audit-write-restored')
    check('same-cookie-recovers-and-previous-fact-visible', any(row['id'] == own_id for row in recovered) and int(sql(count_query)) == before + 2)
    query = urllib.parse.urlencode({'query': '{service_name="ontology-platform-api"} | trace_id="' + fault_trace + '"', 'limit': 100, 'since': '10m'})
    logs = None
    tempo = None
    for _ in range(30):
        try:
            logs = fetch('http://localhost:13100', '/loki/api/v1/query_range?' + query)
            tempo = fetch('http://localhost:13200', '/api/traces/' + fault_trace)
            if 'PlatformRequestFault' in json.dumps(logs) and any(value.get('key') == 'platform.exception.category' for value in walk(tempo)):
                break
        except (OSError, ValueError):
            pass
        time.sleep(2)
    else:
        raise TimeoutError('Actual Loki/Tempo correlation not ready')
    log_text = json.dumps(logs, ensure_ascii=False)
    tempo_text = json.dumps(tempo, ensure_ascii=False)
    fault_streams = [row for row in logs['data']['result'] if row['stream'].get('EventName') == 'PlatformRequestFault' and str(row['stream'].get('EventId')) == '1003' and any(value[1] == 'PlatformRequestFault' for value in row['values'])]
    check('real-loki-fixed-event-and-fields', bool(fault_streams) and all(row['stream'].get('ExceptionCategory') == 'database_write' and row['stream'].get('Outcome') == 'problem_returned' for row in fault_streams))
    check('real-loki-fixed-route-status-trace', all(row['stream'].get('Route') == '/api/v1/platform/audit' and str(row['stream'].get('Status')) == '503' and row['stream'].get('TraceId') == fault_trace for row in fault_streams))
    series = fetch('http://localhost:13100', '/loki/api/v1/series?' + urllib.parse.urlencode({'match[]': '{service_name="ontology-platform-api"}', 'start': str(time.time_ns() - 600_000_000_000)}))
    check('real-loki-only-three-index-labels', bool(series.get('data')) and all(set(stream) == {'service_name', 'deployment_environment_name', 'service_version'} for stream in series['data']))
    (EVIDENCE / 'closeout-loki-series.json').write_text(json.dumps(series, ensure_ascii=False, indent=2) + '\n')
    spans = [value for value in walk(tempo) if 'spanId' in value and 'name' in value]
    check('real-tempo-error-span', any(value.get('status', {}).get('code') in (2, 'STATUS_CODE_ERROR') for value in spans))
    check('real-tempo-classification-and-outcome', 'database_write' in tempo_text and 'problem_returned' in tempo_text)
    check('real-tempo-no-raw-error-description', all(not value.get('status', {}).get('message') for value in spans))
    forbidden = [marker, cookie.value, runtime['postgresPassword'], runtime['grafanaPassword'], realm['clientSecret']]
    check('actual-loki-tempo-no-injected-or-runtime-secrets', all(value not in log_text + tempo_text for value in forbidden))
    (EVIDENCE / 'closeout-loki.json').write_text(json.dumps(logs, ensure_ascii=False, indent=2) + '\n')
    (EVIDENCE / 'closeout-tempo.json').write_text(json.dumps(tempo, ensure_ascii=False, indent=2) + '\n')
    driver.logout_and_replay(cookie)
    result = {'status': 'PASS', 'traceId': fault_trace, 'successTraceId': trace, 'checks': CHECKS, 'identityProtocol': driver.records,
              'fault': 'temporary trigger rejects only this synthetic auditor audit-read INSERT; restored in finally', 'scope': 'actual local PostgreSQL/Keycloak/API/Alloy/Loki/Tempo, no production debug endpoint'}
    (EVIDENCE / 'closeout-observability.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('PASS: actual committed audit-read and controlled database_write event linked to Tempo; traceId=' + fault_trace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    args = parser.parse_args()
    try:
        main(args.runtime_file)
    except Exception as failure:
        (EVIDENCE / 'closeout-observability-failure.json').write_text(json.dumps({'status': 'FAIL', 'category': type(failure).__name__, 'checks': CHECKS}, ensure_ascii=False, indent=2) + '\n')
        print('FAIL: closeout runtime acceptance; category=' + type(failure).__name__ + '; details suppressed')
        raise SystemExit(1)
