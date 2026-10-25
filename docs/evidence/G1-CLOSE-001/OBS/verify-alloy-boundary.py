#!/usr/bin/env python3
"""Exercise the approved Alloy binary with OTLP input and capture its real exports."""
import gzip
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[4]
IMAGE = 'grafana/alloy:v1.21.2@sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18'
FROZEN_BASELINE = '1cbfcf3b3807a49003c0054fa618108a4c1a63a0'
MARKER = 'synthetic-alloy-body-status-event-secret-marker'
received = {}


class Sink(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        received[self.path] = body
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-protobuf')
        self.end_headers()

    def log_message(self, *args):
        pass


def attribute(key, value):
    return {'key': key, 'value': {'intValue': str(value)} if isinstance(value, int) else {'stringValue': value}}


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    name = 'g1-close-obs-alloy-' + secrets.token_hex(5)
    host = 'http://host.docker.internal:' + str(server.server_port)
    checks = []
    output = {'image': IMAGE, 'configurationBaselineSha': FROZEN_BASELINE, 'checks': checks, 'status': 'FAIL'}
    target = ROOT / 'docs/evidence/G1-CLOSE-001/OBS/alloy-runtime-baseline.json'
    try:
        args = ['docker', 'run', '--detach', '--name', name, '--publish', '127.0.0.1::4318',
                '--env', 'LOKI_OTLP_ENDPOINT=' + host + '/loki', '--env', 'TEMPO_OTLP_ENDPOINT=' + host + '/tempo',
                '--env', 'PROMETHEUS_OTLP_ENDPOINT=' + host + '/prometheus',
                '--volume', str(ROOT / 'infra/observability/alloy/config.alloy') + ':/etc/alloy/config.alloy:ro',
                IMAGE, 'run', '--disable-reporting', '/etc/alloy/config.alloy']
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        port = subprocess.check_output(['docker', 'port', name, '4318/tcp'], text=True).strip().rsplit(':', 1)[1]
        resource = {'attributes': [attribute('service.name', 'ontology-platform-api'), attribute('deployment.environment.name', 'Development'), attribute('service.version', 'g1-close'), attribute('rogue.resource', MARKER)]}
        trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
        now = time.time_ns()
        logs = {'resourceLogs': [{'resource': resource, 'scopeLogs': [{'scope': {'name': 'OntologyPlatform.Api'}, 'logRecords': [{
            'timeUnixNano': str(now), 'severityNumber': 17, 'body': {'stringValue': MARKER}, 'traceId': trace_id, 'spanId': span_id,
            'attributes': [attribute('EventId', 1003), attribute('EventName', 'PlatformRequestFault'), attribute('Route', '/api/test/{id}'), attribute('ExceptionCategory', 'database_connection'), attribute('Outcome', 'problem_returned'), attribute('Status', 503), attribute('TraceId', trace_id), attribute('rogue.attribute', MARKER), attribute('routeWrongCase', MARKER)]
        }]}]}]}
        spans = {'resourceSpans': [{'resource': resource, 'scopeSpans': [{'scope': {'name': 'OntologyPlatform.Api'}, 'spans': [{
            'traceId': trace_id, 'spanId': span_id, 'name': 'GET /api/test/{id}', 'kind': 2, 'startTimeUnixNano': str(now), 'endTimeUnixNano': str(now + 1000000),
            'attributes': [attribute('platform.exception.category', 'database_connection'), attribute('platform.request.outcome', 'problem_returned'), attribute('platform.response.status', 503), attribute('exception.message', MARKER), attribute('url.query', MARKER)],
            'status': {'code': 2, 'message': MARKER},
            'events': [{'timeUnixNano': str(now), 'name': MARKER, 'attributes': [attribute('exception.message', MARKER), attribute('exception.stacktrace', MARKER), attribute('exception.type', MARKER)]}]
        }]}]}]}
        opener = build_opener(ProxyHandler({}))
        for signal, payload in [('logs', logs), ('traces', spans)]:
            for attempt in range(40):
                try:
                    with opener.open(Request('http://127.0.0.1:' + port + '/v1/' + signal, json.dumps(payload).encode(), {'Content-Type': 'application/json'}), timeout=3) as response:
                        checks.append({'name': signal + '-ingest-http200', 'pass': response.status == 200})
                    break
                except OSError:
                    if attempt == 39:
                        raise
                    time.sleep(.25)
        for attempt in range(80):
            if '/loki/v1/logs' in received and '/tempo/v1/traces' in received:
                break
            time.sleep(.25)
        log_bytes = received.get('/loki/v1/logs', b'')
        span_bytes = received.get('/tempo/v1/traces', b'')
        checks += [
            {'name': 'actual-loki-export-received', 'pass': bool(log_bytes)},
            {'name': 'actual-tempo-export-received', 'pass': bool(span_bytes)},
            {'name': 'body-and-all-sensitive-markers-removed', 'pass': bool(log_bytes and span_bytes) and MARKER.encode() not in log_bytes + span_bytes},
            {'name': 'fault-body-and-exact-case-fields-retained', 'pass': all(value.encode() in log_bytes for value in ['PlatformRequestFault', 'Route', '/api/test/{id}', 'ExceptionCategory', 'database_connection', 'Outcome', 'problem_returned', 'Status', 'TraceId', trace_id])},
            {'name': 'wrong-case-fields-removed', 'pass': b'routeWrongCase' not in log_bytes},
            {'name': 'span-safe-category-retained', 'pass': b'platform.exception.category' in span_bytes and b'database_connection' in span_bytes},
            {'name': 'span-event-normalized', 'pass': b'platform.event' in span_bytes and b'exception.stacktrace' not in span_bytes},
            {'name': 'loki-index-configuration-unchanged-from-frozen-baseline', 'pass': subprocess.run(['git', 'diff', '--exit-code', FROZEN_BASELINE, '--', 'infra/observability/loki/loki.yaml'], cwd=ROOT, stdout=subprocess.DEVNULL).returncode == 0}
        ]
        output['status'] = 'PASS' if all(check['pass'] for check in checks) else 'FAIL'
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output['status'] == 'PASS' else 1
    finally:
        subprocess.run(['docker', 'rm', '--force', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server.shutdown()
        server.server_close()
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
