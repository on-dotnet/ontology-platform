"""查询受控回环开发栈并直接捕获安全证据；不启动、停止或重启服务。"""
import argparse
import base64
import datetime
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/G1-WAVE2/OBS'
INSTANCES = {'platform-api-1', 'platform-api-2'}
SERVICE = '{service_name="ontology-platform-api"}'
RESOURCE_LABELS = {'service_name', 'service_version', 'deployment_environment_name'}
METRIC_LABELS = RESOURCE_LABELS | {'__name__', 'job', 'instance', 'method', 'route', 'status_class',
                                 'http_request_method', 'http_route', 'http_response_status_code', 'le',
                                 'otel_scope_name', 'otel_scope_version', 'otel_scope_schema_url'}
SECRET_KEY = re.compile(r'^(password|client_secret|access_token|id_token|refresh_token|authorization|cookie|set-cookie)$', re.I)
SECRET_VALUE = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)')


def local_origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1'}
            or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        raise ValueError('Only credential-free HTTP loopback origins are allowed')
    return value.rstrip('/')


def safe_payload(value):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if SECRET_KEY.match(key) else safe_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_payload(item) for item in value]
    if isinstance(value, str):
        value = SECRET_VALUE.sub('[REDACTED]', value)
        grafana_password = os.environ.get('WAVE2_GRAFANA_PASSWORD')
        if grafana_password:
            value = value.replace(grafana_password, '[REDACTED]')
            encoded = base64.b64encode(('platform-dev-admin:' + grafana_password).encode()).decode()
            value = value.replace(encoded, '[REDACTED]')
        return value
    return value


def instance_totals(rows):
    totals = {}
    for row in rows:
        name = row['metric'].get('instance')
        if name not in INSTANCES:
            raise ValueError('Unexpected or missing metric instance')
        number = float(row['value'][1])
        if not math.isfinite(number) or number < 0:
            raise ValueError('Counter sample is not a finite nonnegative value')
        totals[name] = totals.get(name, 0) + number
    if set(totals) != INSTANCES:
        raise ValueError('Both controlled instances must have actual samples')
    return totals


def check_labels(rows, loki=False):
    allowed = RESOURCE_LABELS if loki else METRIC_LABELS
    if not rows:
        raise ValueError('No real series returned')
    for row in rows:
        if set(row) - allowed:
            raise ValueError('Unexpected index labels: ' + ','.join(sorted(set(row) - allowed)))
        if not loki and 'instance' in row and row['instance'] not in INSTANCES:
            raise ValueError('Unexpected metric instance dimension')
        for key in ('route', 'http_route'):
            if key in row and (len(row[key]) > 100 or re.search(r'[?=]|[a-f0-9]{24,}', row[key])):
                raise ValueError('Route is not a bounded route template')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Capture:
    def __init__(self, output, grafana):
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.grafana = grafana
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.sequence = 0
        self.results = []

    def save(self, name, value):
        (self.output / (name + '.json')).write_text(json.dumps(safe_payload(value), ensure_ascii=False, indent=2) + '\n')

    def request(self, name, origin, path, query=None, payload=None, headers=None):
        origin = local_origin(origin)
        address = origin + path + ('?' + urllib.parse.urlencode(query, doseq=True) if query else '')
        actual_headers = {'Accept': 'application/json'} | (headers or {})
        if origin == self.grafana and os.environ.get('WAVE2_GRAFANA_PASSWORD'):
            encoded = base64.b64encode(('platform-dev-admin:' + os.environ['WAVE2_GRAFANA_PASSWORD']).encode()).decode()
            actual_headers['Authorization'] = 'Basic ' + encoded
        body = None if payload is None else json.dumps(payload).encode()
        if body is not None:
            actual_headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(address, data=body, headers=actual_headers)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self.sequence += 1
            self.save(f'{self.sequence:03d}-{name}', {'atUtc': started, 'method': request.get_method(), 'url': address,
                      'httpStatus': None, 'errorType': type(error).__name__})
            raise ValueError(name + ': transport unavailable') from None
        with response:
            status = response.code
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError(name + ': response exceeds evidence limit')
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                value = {'nonJsonBodyOmitted': True, 'byteCount': len(raw)}
            selected_headers = {key: response.headers[key] for key in ('Content-Type', 'X-Trace-Id', 'X-Audit-Id', 'X-Correlation-Id') if key in response.headers}
        self.sequence += 1
        self.save(f'{self.sequence:03d}-{name}', {'atUtc': started, 'method': request.get_method(), 'url': address,
                  'httpStatus': status, 'responseHeaders': selected_headers, 'response': value})
        return status, value, selected_headers

    def stage(self, name, action):
        try:
            detail = action()
            result = {'check': name, 'status': 'PASS', 'detail': detail}
        except (ValueError, KeyError, TypeError, IndexError) as error:
            result = {'check': name, 'status': 'FAIL', 'error': str(error)}
        self.results.append(result)
        print(json.dumps(safe_payload(result), ensure_ascii=False), flush=True)


def successful(status, value):
    if status != 200 or value.get('status') != 'success':
        raise ValueError('Backend did not return a successful query')
    return value['data']['result']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', choices=['health', 'query', 'integration'], default='integration')
    parser.add_argument('--api-origin', action='append')
    parser.add_argument('--trace-id', action='append', default=[])
    parser.add_argument('--grafana-origin', default='http://localhost:15330')
    parser.add_argument('--wait-seconds', type=int, default=45)
    parser.add_argument('--out', type=Path, default=EVIDENCE / 'runtime' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args = parser.parse_args()
    args.out = args.out.resolve()
    if not args.out.is_relative_to(EVIDENCE) or args.out.exists():
        parser.error('Output must be a new directory inside OBS evidence; previous runs are never overwritten')
    if not 0 <= args.wait_seconds <= 60:
        parser.error('wait-seconds must be within 0..60')
    apis = [local_origin(item) for item in (args.api_origin or ['http://localhost:15100', 'http://localhost:15101'])]
    grafana = local_origin(args.grafana_origin)
    cap = Capture(args.out, grafana)
    loki, tempo, prom = 'http://localhost:13100', 'http://localhost:13200', 'http://localhost:19095'
    traces = list(args.trace_id)
    if any(not re.fullmatch('[a-f0-9]{32}', item) for item in traces):
        parser.error('trace-id must contain exactly 32 lowercase hex characters')
    start = int((time.time() - 900) * 1e9)
    for name, origin, path in [('loki', loki, '/ready'), ('tempo', tempo, '/ready'),
                               ('prometheus', prom, '/-/ready'), ('grafana', grafana, '/api/health')]:
        def health(name=name, origin=origin, path=path):
            status, _, _ = cap.request(name + '-health', origin, path)
            if status != 200:
                raise ValueError(name + ' is not ready')
            return {'httpStatus': status}
        cap.stage(name + '-ready', health)
    if args.capture == 'integration':
        for index, origin in enumerate(apis, 1):
            def trigger(origin=origin, index=index):
                parent = '00-' + secrets.token_hex(16) + '-' + secrets.token_hex(8) + '-01'
                status, value, headers = cap.request('api-' + str(index), origin, '/api/v1/platform/me', headers={'traceparent': parent})
                trace = headers.get('X-Trace-Id', '')
                if status != 401 or value.get('code') != 'unauthenticated' or not re.fullmatch('[a-f0-9]{32}', trace):
                    raise ValueError('Anonymous request must return actual 401 ProblemDetails with TraceId')
                traces.append(trace)
                return {'httpStatus': status, 'traceId': trace, 'audit': 'NOT_RUN: anonymous me has no resource audit'}
            cap.stage('api-' + str(index) + '-actual-request', trigger)
        if args.wait_seconds:
            print('Waiting for configured OTLP export/batch interval', flush=True)
            time.sleep(args.wait_seconds)
    if args.capture in {'query', 'integration'}:
        for trace in traces:
            def logs(trace=trace):
                status, value, _ = cap.request('loki-' + trace, loki, '/loki/api/v1/query_range',
                    {'query': SERVICE + ' | trace_id="' + trace + '"', 'start': str(start), 'limit': '100'})
                rows = successful(status, value)
                if not any(row.get('values') for row in rows):
                    raise ValueError('No logs returned for actual API TraceId')
                return {'traceId': trace, 'streams': len(rows)}
            cap.stage('loki-same-trace-' + trace, logs)
            def spans(trace=trace):
                status, value, _ = cap.request('tempo-' + trace, tempo, '/api/traces/' + trace)
                # Tempo protobuf JSON encodes trace IDs in base64, while some API versions use hex.
                encoded = base64.b64encode(bytes.fromhex(trace)).decode()
                serialized = json.dumps(value)
                if status != 200 or not (trace in serialized or encoded in serialized):
                    raise ValueError('Tempo did not return spans for the same TraceId')
                return {'traceId': trace}
            cap.stage('tempo-same-trace-' + trace, spans)
        if not traces:
            cap.results.append({'check': 'api-log-trace-link', 'status': 'NOT_RUN', 'reason': 'No trace IDs supplied/generated'})
        def loki_indices():
            status, value, _ = cap.request('loki-index-series', loki, '/loki/api/v1/series', {'match[]': SERVICE, 'start': str(start)})
            if status != 200 or value.get('status') != 'success':
                raise ValueError('Loki index series API failed')
            check_labels(value['data'], loki=True)
            return {'streamCount': len(value['data']), 'indexLabels': sorted({key for row in value['data'] for key in row})}
        cap.stage('loki-index-low-cardinality', loki_indices)
        def series():
            status, value, _ = cap.request('prometheus-series', prom, '/api/v1/series', {'match[]': SERVICE, 'start': str(start // 1_000_000_000)})
            if status != 200 or value.get('status') != 'success':
                raise ValueError('Series API failed')
            check_labels(value['data'])
            return {'seriesCount': len(value['data']), 'labelNames': sorted({key for row in value['data'] for key in row})}
        cap.stage('prometheus-low-cardinality', series)
        def counters():
            sample_time = str(time.time() - 1)
            status, value, _ = cap.request('prometheus-counter-instances', prom, '/api/v1/query', {'query': 'platform_requests_total' + SERVICE, 'time': sample_time})
            totals = instance_totals(successful(status, value))
            status, value, _ = cap.request('prometheus-counter-sum', prom, '/api/v1/query', {'query': 'sum(platform_requests_total' + SERVICE + ')', 'time': sample_time})
            rows = successful(status, value)
            if len(rows) != 1 or not math.isclose(float(rows[0]['value'][1]), sum(totals.values()), rel_tol=1e-9):
                raise ValueError('Explicit aggregation differs from independent samples at the same timestamp')
            return {'instanceTotals': totals, 'sum': float(rows[0]['value'][1]), 'sampleTime': sample_time}
        cap.stage('prometheus-two-instances-then-sum', counters)
        def alerts():
            status, value, _ = cap.request('prometheus-alerts', prom, '/api/v1/alerts')
            if status != 200 or value.get('status') != 'success':
                raise ValueError('Alert API failed')
            return {'alerts': value['data']['alerts'], 'faultInjection': 'NOT_RUN: Master owns lifecycle'}
        cap.stage('prometheus-alert-snapshot', alerts)
        if os.environ.get('WAVE2_GRAFANA_PASSWORD'):
            def dashboards():
                discovered = []
                for uid in ['platform-overview', 'platform-api', 'platform-dependencies', 'platform-errors']:
                    status, value, _ = cap.request('grafana-dashboard-' + uid, grafana, '/api/dashboards/uid/' + uid)
                    dashboard = value.get('dashboard', {})
                    if status != 200 or not value.get('meta', {}).get('provisioned') or not re.search('[\u4e00-\u9fff]', dashboard.get('title', '')):
                        raise ValueError('Chinese dashboard provisioning is not verified: ' + uid)
                    discovered.append({'uid': uid, 'title': dashboard['title']})
                for uid in ['platform-prometheus', 'platform-loki', 'platform-tempo']:
                    status, value, _ = cap.request('grafana-datasource-' + uid, grafana, '/api/datasources/uid/' + uid + '/health')
                    if status != 200 or value.get('status') != 'OK':
                        raise ValueError('Grafana datasource health failed: ' + uid)
                now = int(time.time() * 1000)
                status, value, _ = cap.request('grafana-live-data', grafana, '/api/ds/query', payload={
                    'from': str(now - 900_000), 'to': str(now), 'queries': [{'refId': 'A', 'datasource': {'uid': 'platform-prometheus', 'type': 'prometheus'},
                    'expr': 'sum by (instance) (platform_requests_total' + SERVICE + ')', 'instant': True, 'range': False, 'intervalMs': 10000, 'maxDataPoints': 300}]})
                frames = value.get('results', {}).get('A', {}).get('frames', [])
                if status != 200 or not any(frame.get('data', {}).get('values') for frame in frames):
                    raise ValueError('Grafana returned no actual data frames')
                return {'dashboards': discovered, 'liveFrames': len(frames), 'screenshot': 'NOT_RUN: requires safe browser capture'}
            cap.stage('grafana-chinese-provisioning-and-live-data', dashboards)
        else:
            cap.results.append({'check': 'grafana-authenticated-provisioning', 'status': 'NOT_RUN', 'reason': 'Master must inject process-only WAVE2_GRAFANA_PASSWORD'})
    summary = {'atUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'capture': args.capture,
               'traceIds': traces, 'checks': cap.results, 'screenshots': 'NOT_RUN', 'persistence': 'NOT_RUN',
               'status': 'PARTIAL' if any(row['status'] != 'PASS' for row in cap.results) else 'PASS_SELECTED_QUERIES'}
    cap.save('summary', summary)
    print(json.dumps({'output': str(args.out), 'status': summary['status']}, ensure_ascii=False))
    return 1 if any(row['status'] == 'FAIL' for row in cap.results) else 2 if summary['status'] == 'PARTIAL' else 0


if __name__ == '__main__':
    sys.exit(main())
