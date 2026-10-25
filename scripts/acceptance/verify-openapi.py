#!/usr/bin/env python3
"""Compare the actual Kestrel OpenAPI document against the frozen public contract."""
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
# 默认保留历史入口；后续收口显式选择新证据目录，不覆盖历史事实。
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-WAVE2/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)

ERRORS = []


def expect(condition, location):
    if not condition:
        ERRORS.append(location)


def resolve(spec, node):
    if '$ref' in node:
        value = spec
        for part in node['$ref'].removeprefix('#/').split('/'):
            value = value[part]
        return resolve(spec, value)
    return node


def schema(expected_spec, actual_spec, expected, actual, where):
    expected = resolve(expected_spec, expected)
    actual = resolve(actual_spec, actual)
    if 'type' in expected:
        expected_types = expected['type'] if isinstance(expected['type'], list) else [expected['type']]
        actual_types = actual.get('type', [])
        actual_types = actual_types if isinstance(actual_types, list) else [actual_types]
        expect(set(expected_types) == set(actual_types), where + ':type')
    if 'format' in expected:
        expect(expected['format'] == actual.get('format'), where + ':format')
    expect(set(expected.get('required', [])) <= set(actual.get('required', [])), where + ':required')
    for key in ['minimum', 'maximum', 'default', 'enum']:
        if key in expected:
            expect(expected[key] == actual.get(key), where + ':' + key)
    for key, value in expected.get('properties', {}).items():
        if key not in actual.get('properties', {}):
            expect(False, where + ':property-' + key)
        else:
            schema(expected_spec, actual_spec, value, actual['properties'][key], where + '.' + key)
    if 'items' in expected:
        if 'items' not in actual:
            expect(False, where + ':items')
        else:
            schema(expected_spec, actual_spec, expected['items'], actual['items'], where + '[]')


def compare(expected, actual):
    expect(actual.get('openapi', '').startswith('3.1'), 'OpenAPI3.1')
    for path, methods in expected['paths'].items():
        for method, wanted in methods.items():
            found = actual.get('paths', {}).get(path, {}).get(method)
            where = method.upper() + ' ' + path
            if found is None:
                expect(False, where + ':missing')
                continue
            expect(wanted.get('operationId') == found.get('operationId'), where + ':operationId')
            expect(wanted.get('security', []) == found.get('security', []), where + ':security')
            for status, response in wanted['responses'].items():
                if status not in found['responses']:
                    expect(False, where + ':status-' + status)
                    continue
                for media, content in response.get('content', {}).items():
                    produced = found['responses'][status].get('content', {}).get(media)
                    if produced is None:
                        expect(False, where + ':media-' + status + '-' + media)
                    else:
                        schema(expected, actual, content['schema'], produced['schema'], where + ':' + status)
            for parameter in wanted.get('parameters', []):
                matches = [p for p in found.get('parameters', []) if p.get('name') == parameter['name'] and p.get('in') == parameter['in']]
                if len(matches) != 1:
                    expect(False, where + ':parameter-' + parameter['name'])
                else:
                    expect(parameter.get('required', False) == matches[0].get('required', False), where + ':parameter-required')
                    schema(expected, actual, parameter['schema'], matches[0]['schema'], where + ':parameter-' + parameter['name'])
            if 'requestBody' in wanted:
                body = found.get('requestBody', {})
                expect(wanted['requestBody'].get('required', False) == body.get('required', False), where + ':requestBody-required')
                for media, content in wanted['requestBody']['content'].items():
                    produced = body.get('content', {}).get(media)
                    if produced is None:
                        expect(False, where + ':requestBody-' + media)
                    else:
                        schema(expected, actual, content['schema'], produced['schema'], where + ':requestBody')
    for name, wanted in expected['components']['schemas'].items():
        found = actual.get('components', {}).get('schemas', {}).get(name)
        if found is None:
            expect(False, 'schema:' + name)
        else:
            schema(expected, actual, wanted, found, 'schema:' + name)
    expect(expected['components']['securitySchemes']['session'] == {k: actual.get('components', {}).get('securitySchemes', {}).get('session', {}).get(k) for k in ['type', 'in', 'name']}, 'session-security-scheme')
    return ERRORS


def main():
    expected = json.loads((ROOT / 'docs/contracts/g1-platform.openapi.json').read_text())
    if len(sys.argv) > 1:
        actual = json.loads(Path(sys.argv[1]).read_text())
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://localhost:15100/openapi/v1.json', timeout=10) as response:
            actual = json.load(response)
    errors = compare(expected, actual)
    target = EVIDENCE
    (target / 'openapi-runtime-final.json').write_text(json.dumps(actual, ensure_ascii=False, indent=2) + '\n')
    (target / 'openapi-contract-check.json').write_text(json.dumps({'status': 'FAIL' if errors else 'PASS', 'command': 'python3 scripts/acceptance/verify-openapi.py', 'checked': ['paths', 'response-status-and-media', 'all-public-DTO-fields-types-required', 'error-schema', 'stable-operationIds', 'session-security', 'parameters-bounds', 'native-CSRF-form'], 'errors': errors}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'errors': errors}, ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
