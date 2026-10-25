#!/usr/bin/env python3
"""Exercise the approved Alloy binary with OTLP input and capture its real exports."""
import argparse
import gzip
import os
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
native_received = []
alloy_endpoint = None


class Sink(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        if self.path == '/native/v1/logs':
            native_received.append(body)
            opener = build_opener(ProxyHandler({}))
            with opener.open(Request(alloy_endpoint + '/v1/logs', body, {'Content-Type': 'application/x-protobuf'}), timeout=5) as response:
                assert response.status == 200
        else:
            received.setdefault(self.path, []).append(body)
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-protobuf')
        self.end_headers()

    def log_message(self, *args):
        pass


def attribute(key, value):
    return {'key': key, 'value': {'intValue': str(value)} if isinstance(value, int) else {'stringValue': value}}


def wire_fields(data):
    """Read bounded protobuf fields according to the official logs.proto wire schema."""
    offset = 0

    def varint():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('Invalid test protobuf varint')

    while offset < len(data):
        tag = varint()
        wire = tag & 7
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            length = varint() if wire == 2 else 8 if wire == 1 else 4
            assert offset + length <= len(data)
            value = data[offset:offset + length]
            offset += length
        else:
            raise ValueError('Unsupported test protobuf wire type')
        yield tag >> 3, value


def subfields(data, number):
    return [value for field, value in wire_fields(data) if field == number]


def decode_logs(payloads):
    """Decode real LogRecord event_name/body/attributes, retaining only test-safe views."""
    records = []
    for payload in payloads:
        for resource in subfields(payload, 1):
            for scope in subfields(resource, 2):
                for record in subfields(scope, 2):
                    attributes = {}
                    for attribute_bytes in subfields(record, 6):
                        key = subfields(attribute_bytes, 1)[0].decode()
                        any_value = subfields(attribute_bytes, 2)[0]
                        strings = subfields(any_value, 1)
                        integers = subfields(any_value, 3)
                        attributes[key] = strings[0].decode() if strings else integers[0] if integers else None
                    event_names = subfields(record, 12)
                    bodies = subfields(record, 5)
                    body_strings = subfields(bodies[0], 1) if bodies else []
                    records.append({'eventName': event_names[0].decode() if event_names else '', 'body': body_strings[0].decode() if body_strings else '', 'attributes': attributes})
    return records


def main():
    global alloy_endpoint
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", default="docs/evidence/G1-CLOSE-001/OBS/alloy-event-identity.json")
    options = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    name = 'g1-close-obs-alloy-' + secrets.token_hex(5)
    host = 'http://host.docker.internal:' + str(server.server_port)
    checks = []
    output = {'image': IMAGE, 'configurationBaselineSha': FROZEN_BASELINE, 'checks': checks, 'status': 'FAIL'}
    target = ROOT / options.output_json
    try:
        args = ['docker', 'run', '--detach', '--name', name, '--publish', '127.0.0.1::4318',
                '--env', 'LOKI_OTLP_ENDPOINT=' + host + '/loki', '--env', 'TEMPO_OTLP_ENDPOINT=' + host + '/tempo',
                '--env', 'PROMETHEUS_OTLP_ENDPOINT=' + host + '/prometheus',
                '--volume', str(ROOT / 'infra/observability/alloy/config.alloy') + ':/etc/alloy/config.alloy:ro',
                IMAGE, 'run', '--disable-reporting', '/etc/alloy/config.alloy']
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        port = subprocess.check_output(['docker', 'port', name, '4318/tcp'], text=True).strip().rsplit(':', 1)[1]
        alloy_endpoint = 'http://127.0.0.1:' + port
        for attempt in range(40):
            try:
                with build_opener(ProxyHandler({})).open(Request(alloy_endpoint + '/v1/logs', b'{}', {'Content-Type': 'application/json'}), timeout=3):
                    break
            except OSError:
                time.sleep(.25)
        env = os.environ.copy()
        env['G1_OBS_NATIVE_LOG_RELAY'] = 'http://127.0.0.1:' + str(server.server_port) + '/native'
        result = subprocess.run(['dotnet', 'test', '--project', 'backend/tests/OntologyPlatform.SecurityTests', '--no-restore', '--filter', 'FullyQualifiedName~NativeOtlpExportContainsControlledFaultAndNoOriginalException'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output['nativeTest'] = {'exitCode': result.returncode, 'output': result.stdout}
        for attempt in range(80):
            if any(record['eventName'] == 'PlatformRequestFault' for record in decode_logs(received.get('/loki/v1/logs', []))):
                break
            time.sleep(.25)
        raw_faults = [record for record in decode_logs(native_received) if record['eventName'] == 'PlatformRequestFault']
        exported_faults = [record for record in decode_logs(received.get('/loki/v1/logs', [])) if record['eventName'] == 'PlatformRequestFault']
        output['nativeSchemaObserved'] = [{'eventName': record['eventName'], 'attributeKeys': sorted(record['attributes'])} for record in raw_faults]
        output['safeExportedFaultIdentity'] = [{'eventName': record['eventName'], 'body': record['body'], 'EventName': record['attributes'].get('EventName'), 'EventId': record['attributes'].get('EventId')} for record in exported_faults]
        checks += [
            {'name': 'real-native-exporter-test-passed', 'pass': result.returncode == 0},
            {'name': 'native-schema-is-top-level-event-name-without-legacy-event-attributes', 'pass': len(raw_faults) == 2 and all('EventName' not in record['attributes'] and 'EventId' not in record['attributes'] and 'logrecord.event.id' not in record['attributes'] for record in raw_faults)},
            {'name': 'native-fault-through-alloy-retains-fixed-body-name-and-id', 'pass': len(exported_faults) == 2 and all(record['body'] == 'PlatformRequestFault' and record['attributes'].get('EventName') == 'PlatformRequestFault' and record['attributes'].get('EventId') == 1003 for record in exported_faults)},
            {'name': 'native-fault-fields-remain-correlated', 'pass': len(exported_faults) == 2 and all(record['attributes'].get('Route') == '/api/obs-export/{kind}' and record['attributes'].get('ExceptionCategory') == 'unexpected_failure' and record['attributes'].get('Status') == 500 and len(record['attributes'].get('TraceId', '')) == 32 for record in exported_faults)},
            {'name': 'native-alloy-export-has-no-sensitive-marker', 'pass': bool(exported_faults) and b'synthetic-obs-secret-password-token-marker' not in b''.join(received.get('/loki/v1/logs', []))},
        ]
        received.clear()
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
        log_bytes = b''.join(received.get('/loki/v1/logs', []))
        span_bytes = b''.join(received.get('/tempo/v1/traces', []))
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
