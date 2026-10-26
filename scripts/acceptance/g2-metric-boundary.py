#!/usr/bin/env python3
"""Prove finite G2 metric labels at the actual pinned Alloy/Prometheus boundary.

Only Python stdlib and pre-existing approved digest-pinned images are used. Input
is synthetic OTLP, not product Meter E2E. No existing runtime/volumes are read.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OBS = ROOT / 'docs/evidence/G2-THIN-SLICE-001/OBS'
# Independently transcribed from product emitters; deliberately not parsed from config.
FINITE = {
    'capability': ['describe_ontology', 'resolve_entity', 'traverse_relationships'],
    'status': ['Found', 'Empty', 'Partial', 'Unavailable', 'Unauthorized', 'Ambiguous', 'allowed', 'failure'],
    'operation': ['AnalyzeAsync', 'ValidateAsync', 'ApplyEditAsync', 'DeployAsync', 'VerifyAsync', 'ReadPublishedAsync', 'ReadVerifiedPublishedAsync', 'publish', 'rollback', 'outbox'],
    'outcome': ['completed', 'failed'],
    'phase': ['lease', 'verify', 'consume', 'commit', 'prepare_or_commit'],
}
MARKER = 'SYNTHETIC-G2-CONFIDENTIAL-MARKER'
PRIVATE_KEYS = ['prompt', 'body', 'user.id', 'subject', 'site', 'siteId', 'releaseId', 'traceId', 'requestId', 'authorization', 'db.statement']
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def value(item):
    """Encode the actual OTLP AnyValue wire-JSON shape without an SDK."""
    if isinstance(item, bool):
        return {'boolValue': item}
    if isinstance(item, int):
        return {'intValue': str(item)}
    if isinstance(item, list):
        return {'arrayValue': {'values': [value(child) for child in item]}}
    if isinstance(item, dict):
        return {'kvlistValue': {'values': attributes(item)}}
    return {'stringValue': item}


def attributes(items):
    return [{'key': key, 'value': value(item)} for key, item in items.items()]


def fixture():
    """Each case has its own metric identity, preventing dropped-label coalescence."""
    cases = []
    for key, allowed in FINITE.items():
        for item in allowed:
            cases.append((f'finite-{key}-{item}', {key: item}, {key: item}, 'finite'))
        # Includes exact-case mismatch, arbitrary body, empty and each non-string type.
        for label, item in [('unknown', 'unknown'), ('body', MARKER), ('empty', ''), ('case', allowed[0].upper()), ('integer', 7), ('boolean', True), ('array', [allowed[0]]), ('map', {'text': MARKER})]:
            cases.append((f'invalid-{key}-{label}', {key: item}, {}, 'negative'))
    # Real product instrument names/shapes, still synthetic input (not product E2E).
    product = [
        ('ontology.semantic.duration', {'operation': 'AnalyzeAsync', 'outcome': 'completed'}, 'histogram'),
        ('publishing.operations', {'operation': 'publish', 'status': 'allowed', 'phase': 'commit'}, 'sum'),
        ('semantic.query.count', {'capability': 'resolve_entity', 'status': 'Found'}, 'sum'),
        ('agents.run.count', {'capability': 'traverse_relationships', 'outcome': 'completed'}, 'sum'),
    ]
    now = str(time.time_ns())
    metrics = []
    expected = []
    private = {key: MARKER for key in PRIVATE_KEYS}
    for index, (label, supplied, wanted, group) in enumerate(cases):
        name = f'g2.boundary.case{index:03d}'
        metrics.append({'name': name, 'gauge': {'dataPoints': [{'attributes': attributes(private | supplied), 'timeUnixNano': now, 'asInt': '1'}]}})
        expected.append({'case': label, 'name': name.replace('.', '_'), 'labels': wanted, 'group': group})
    for name, labels, kind in product:
        point = {'attributes': attributes(private | labels), 'timeUnixNano': now, 'startTimeUnixNano': str(int(now) - 1_000_000_000)}
        if kind == 'histogram':
            point |= {'count': '1', 'sum': 2.0, 'bucketCounts': ['1', '0'], 'explicitBounds': [5.0]}
            data = {'histogram': {'dataPoints': [point], 'aggregationTemporality': 2}}
            expected_name = name.replace('.', '_') + '_count'
        else:
            point['asInt'] = '1'
            data = {'sum': {'dataPoints': [point], 'aggregationTemporality': 2, 'isMonotonic': True}}
            expected_name = name.replace('.', '_') + '_total'
        metrics.append({'name': name} | data)
        expected.append({'case': 'product-shape-' + name, 'name': expected_name, 'labels': labels, 'group': 'product-shape'})
    http = {'http.request.method': 'GET', 'http.route': '/api/v1/platform/health', 'http.response.status_code': 200, 'method': 'GET', 'route': '/api/v1/platform/health', 'status_class': '2xx'}
    metrics.append({'name': 'g2.boundary.http', 'sum': {'dataPoints': [{'attributes': attributes(private | http), 'timeUnixNano': now, 'startTimeUnixNano': str(int(now) - 1_000_000_000), 'asInt': '1'}], 'aggregationTemporality': 2, 'isMonotonic': True}})
    expected.append({'case': 'g1-http-and-instance-a', 'name': 'g2_boundary_http_total', 'labels': {key.replace('.', '_'): str(item) for key, item in http.items()}, 'group': 'g1', 'instance': 'boundary-instance-a'})
    resources = []
    for instance, stream in [('boundary-instance-a', metrics), ('boundary-instance-b', [metrics[-1]])]:
        resource = {'service.name': 'g2-boundary-fixture', 'service.version': 'synthetic', 'deployment.environment.name': 'Development', 'service.instance.id': instance} | private
        resources.append({'resource': {'attributes': attributes(resource)}, 'scopeMetrics': [{'scope': {'name': 'G2.Boundary.Synthetic'}, 'metrics': stream}]})
    expected.append({'case': 'g1-http-and-instance-b', 'name': 'g2_boundary_http_total', 'labels': {key.replace('.', '_'): str(item) for key, item in http.items()}, 'group': 'g1', 'instance': 'boundary-instance-b'})
    return {'resourceMetrics': resources}, expected


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=5) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def main(args):
    config = args.config.resolve()
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to(OBS.resolve()):
        raise ValueError('Evidence must stay inside the assigned OBS path')
    if args.input and not args.input.resolve().is_relative_to(OBS.resolve()):
        raise ValueError('Replay input must stay inside the synthetic OBS evidence path')
    evidence.mkdir(parents=True, exist_ok=True)
    commands = []
    result = {'status': 'FAIL', 'scope': 'Synthetic OTLP -> real pinned Alloy -> real pinned Prometheus; product Meter E2E NOT_RUN here', 'configSha256': hashlib.sha256(config.read_bytes()).hexdigest(), 'checks': [], 'commands': commands}
    prefix = 'g2-metric-' + secrets.token_hex(6)
    network = prefix + '-network'
    created = []
    network_created = False

    def run(label, argv, required=True):
        try:
            process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else (error.stdout or '')
            stderr = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else (error.stderr or '')
            process = subprocess.CompletedProcess(argv, 124, stdout, stderr + '\nTimed out after 60 seconds')
        commands.append({'label': label, 'argv': argv, 'exitCode': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr})
        if required and process.returncode:
            raise RuntimeError(label + ' failed')
        return process

    def check(label, condition, group):
        result['checks'].append({'check': label, 'status': 'PASS' if condition else 'FAIL', 'group': group})

    def port(name, target):
        binding = run(name + '-port', ['docker', 'port', name, str(target)]).stdout.strip()
        if not re.fullmatch(r'127\.0\.0\.1:\d+', binding):
            raise ValueError('Expected one random loopback port')
        return 'http://' + binding

    def ready(origin, path):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with OPENER.open(origin + path, timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(0.25)
        raise TimeoutError('New fixture readiness timed out')

    try:
        resources = json.loads((ROOT / 'infra/observability/resources.json').read_text())['resources']
        images = {item['name']: item['image'] + ':' + item['tag'] + '@' + item['indexDigest'] for item in resources if item['name'] in ('alloy', 'prometheus')}
        result['images'] = images
        run('docker-version', ['docker', 'version', '--format', '{{.Server.Version}}'])
        for name, image in images.items():
            run(name + '-image', ['docker', 'image', 'inspect', image, '--format', '{{json .RepoDigests}} {{.Architecture}}'])
        env = ['-e', 'LOKI_OTLP_ENDPOINT=http://127.0.0.1:9/otlp', '-e', 'TEMPO_OTLP_ENDPOINT=http://127.0.0.1:9', '-e', 'PROMETHEUS_OTLP_ENDPOINT=http://prometheus:9090/api/v1/otlp']
        bounded = ['--memory=256m', '--cpus=1', '--pids-limit=128']
        mount = ['--mount', 'type=bind,src=' + str(config) + ',dst=/etc/alloy/config.alloy,readonly']
        validator = prefix + '-validate'
        created.append(validator)
        run('alloy-validate', ['docker', 'run', '--pull=never', '--rm', '--name', validator, '--network=none'] + bounded + mount + env + [images['alloy'], 'validate', '/etc/alloy/config.alloy'])
        created.remove(validator)
        # Fixture-local Prometheus config avoids all existing targets and private state.
        with tempfile.TemporaryDirectory(prefix=prefix + '-') as directory:
            prometheus_config = Path(directory) / 'prometheus.yaml'
            prometheus_config.write_text('global:\n  scrape_interval: 1m\nscrape_configs: []\notlp:\n  promote_resource_attributes: [service.name, service.version, deployment.environment.name]\n  keep_identifying_resource_attributes: false\n')
            run('network-create', ['docker', 'network', 'create', network])
            network_created = True
            prometheus = prefix + '-prometheus'
            created.append(prometheus)
            run('prometheus-start', ['docker', 'run', '-d', '--pull=never', '--name', prometheus, '--network', network, '--network-alias', 'prometheus', '-p', '127.0.0.1::9090', '--read-only', '--tmpfs', '/prometheus:rw,size=96m,uid=65534,gid=65534', '--mount', 'type=bind,src=' + str(prometheus_config) + ',dst=/etc/prometheus/prometheus.yaml,readonly'] + bounded + [images['prometheus'], '--config.file=/etc/prometheus/prometheus.yaml', '--storage.tsdb.path=/prometheus', '--storage.tsdb.retention.time=15m', '--web.enable-otlp-receiver'])
            prom_origin = port(prometheus, 9090)
            ready(prom_origin, '/-/ready')
            alloy = prefix + '-alloy'
            created.append(alloy)
            run('alloy-start', ['docker', 'run', '-d', '--pull=never', '--name', alloy, '--network', network, '-p', '127.0.0.1::4318', '-p', '127.0.0.1::12345', '--read-only', '--tmpfs', '/var/lib/alloy:rw,size=32m'] + bounded + mount + env + [images['alloy'], 'run', '--server.http.listen-addr=0.0.0.0:12345', '--storage.path=/var/lib/alloy/data', '--disable-reporting', '/etc/alloy/config.alloy'])
            alloy_origin = port(alloy, 4318)
            ready(port(alloy, 12345), '/-/ready')
            payload, expected = fixture()
            if args.input:
                payload = json.loads(args.input.read_text())
            result['inputSha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            result['inputDatapoints'] = len(expected)
            (evidence / 'input.synthetic-otlp.json').write_text(json.dumps(payload, indent=2) + '\n')
            result['otlpResponse'] = request(alloy_origin + '/v1/metrics', payload)
            selector = '{__name__=~"g2_boundary_.*|ontology_semantic_duration.*|publishing_operations.*|semantic_query_count.*|agents_run_count.*"}'
            endpoint = prom_origin + '/api/v1/query?' + urllib.parse.urlencode({'query': selector})
            observed = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                observed = request(endpoint)
                rows = observed.get('data', {}).get('result', [])
                if len(rows) >= len(expected):
                    break
                time.sleep(0.5)
            else:
                raise TimeoutError('Actual Prometheus datapoints did not arrive')
            (evidence / 'prometheus-output.json').write_text(json.dumps(observed, indent=2) + '\n')
            for item in expected:
                matching = [row['metric'] for row in rows if row['metric'].get('__name__') == item['name'] and row['metric'].get('instance') == item.get('instance', 'boundary-instance-a')]
                actual = matching[0] if len(matching) == 1 else {}
                # Require exact finite-label set; unknown values cannot hide behind presence-only tests.
                labels = {key: actual[key] for key in FINITE if key in actual}
                wanted = {key: str(value) for key, value in item['labels'].items()}
                good = len(matching) == 1 and labels == {key: wanted[key] for key in FINITE if key in wanted} and all(actual.get(key) == value for key, value in wanted.items())
                check(item['case'], good, item['group'])
            all_series = request(prom_origin + '/api/v1/series?' + urllib.parse.urlencode({'match[]': '{__name__=~".+"}'}))
            (evidence / 'prometheus-series.json').write_text(json.dumps(all_series, indent=2) + '\n')
            series = all_series.get('data', [])
            output_text = json.dumps(observed) + json.dumps(all_series)
            check('private-marker-never-exits', MARKER not in output_text, 'privacy')
            denied = {key.replace('.', '_') for key in PRIVATE_KEYS}
            check('private-keys-never-exit-series', all(not denied.intersection(row) for row in series), 'privacy')
            allowed_labels = {'__name__', 'job', 'instance', 'service_name', 'service_version', 'deployment_environment_name', 'otel_scope_name', 'otel_scope_version', 'le'} | set(FINITE) | {'http_request_method', 'http_route', 'http_response_status_code', 'method', 'route', 'status_class'}
            check('series-labels-only-known-finite-or-existing-g1', all(set(row) <= allowed_labels for row in series), 'privacy')
            result['outputSeries'] = len(series)
            result['queriedSeries'] = len(rows)
            result['status'] = 'PASS' if all(item['status'] == 'PASS' for item in result['checks']) else 'FAIL'
            for group in ['finite', 'negative', 'product-shape', 'g1', 'privacy']:
                checks = [item for item in result['checks'] if item['group'] == group]
                result.setdefault('counts', {})[group] = {'total': len(checks), 'passed': sum(item['status'] == 'PASS' for item in checks)}
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        for container in reversed(created):
            run(container + '-logs', ['docker', 'logs', '--tail=100', container], required=False)
            run(container + '-cleanup', ['docker', 'rm', '-f', '-v', container], required=False)
        if network_created:
            run('network-cleanup', ['docker', 'network', 'rm', network], required=False)
        # Inspect only our random names; no broad runtime listing/cleanup.
        remaining = run('cleanup-check', ['docker', 'ps', '-a', '--filter', 'name=' + prefix, '--format', '{{.Names}}'], required=False)
        result['cleanup'] = {'ownContainersRemaining': remaining.stdout.split(), 'checkedPrefix': prefix, 'onlyOwnNewResources': True}
        if remaining.returncode or remaining.stdout.strip() or any(command['exitCode'] for command in commands if command['label'].endswith('-cleanup')):
            result['status'] = 'FAIL'
        result['recordedAtUtc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result.get(key) for key in ['status', 'inputDatapoints', 'queriedSeries', 'counts', 'configSha256', 'error', 'cleanup']}, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'infra/observability/alloy/config.alloy')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--input', type=Path, help='Replay the exact prior synthetic payload for RED/GREEN comparison')
    raise SystemExit(main(parser.parse_args()))
