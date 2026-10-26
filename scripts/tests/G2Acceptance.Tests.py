"""Control-plane regressions only: child/I/O substitutions never certify product behavior."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ACCEPTANCE = Path(__file__).resolve().parents[1] / 'acceptance'
GATES = ['full-g2-e2e.py', 'g1-regression.py', 'g2-observability.py',
         'g2-trace-browser.mjs', 'g2-readiness-fault.py', 'performance-baseline.py']


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ACCEPTANCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OrchestrationTests(unittest.TestCase):
    """Run real orchestration with isolated, real-exit-code child substitutes."""

    def exercise(self, fail_gate=None, start=False, bootstrap=False, prepare=False):
        module = load('g2-acceptance-runtime')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / '.tools/security'
            private.mkdir(parents=True)
            runtime_file = private / 'control-plane.json'
            realm = private / 'realm.json'
            if not bootstrap:
                realm.write_text('{}')
            runtime_file.write_text(json.dumps({'volumePrefix': 'g2-control-only', 'healthKey': 'synthetic-health', 'realmFile': str(realm)}))
            log = root / 'children.jsonl'
            child = root / 'child.py'
            child.write_text('import json,sys\nfrom pathlib import Path\nwith Path(sys.argv[1]).open("a") as output:\n output.write(json.dumps(sys.argv[2:])+"\\n")\nsys.exit(int(sys.argv[-1]))\n')
            real_run = subprocess.run
            real_popen = subprocess.Popen
            launches = []
            stopped = []
            bootstrap_calls = []

            def run(command, **kwargs):
                # Substitute only external programs. The orchestrator's selection/order/return stay real.
                gate = Path(command[1]).name
                code = 23 if gate == fail_gate else 0
                result = real_run([sys.executable, str(child), str(log), *command, str(code)], cwd=root)
                if kwargs.get('check'):
                    result.check_returncode()
                return result

            def tools(command, **kwargs):
                if command == [sys.executable, 'scripts/acceptance/g2-runtime.py', 'prepare']:
                    return str(runtime_file.relative_to(root)) + '\n'
                self.assertEqual(command, ['pwsh', '-NoProfile', '-File', 'scripts/bootstrap-web-tools.ps1'])
                bootstrap_calls.append(command)
                return json.dumps({'nodePath': str(root / 'approved-project-node')})

            def launch(command, **kwargs):
                if command[1] == str(child):
                    return real_popen(command, **kwargs)
                token = object()
                launches.append((command[2], token))
                return token

            argv = ['g2-acceptance-runtime.py', '--runtime-file', str(runtime_file)]
            if prepare:
                argv = ['g2-acceptance-runtime.py']
            if start:
                argv.append('--start-runtime')
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(module, 'ROOT', root))
                stack.enter_context(patch.object(sys, 'argv', argv))
                stack.enter_context(patch.object(module, 'wait_for'))
                stack.enter_context(patch.object(module, 'stop', side_effect=stopped.append))
                stack.enter_context(patch.object(module.subprocess, 'run', side_effect=run))
                stack.enter_context(patch.object(module.subprocess, 'check_output', side_effect=tools))
                stack.enter_context(patch.object(module.subprocess, 'Popen', side_effect=launch))
                stack.enter_context(patch.object(module.OPENER, 'open', side_effect=module.urllib.error.URLError('control-plane no listener')))
                code = module.main()
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return code, calls, bootstrap_calls, launches, stopped, root

    def test_all_six_required_gates_run_with_exact_project_node(self):
        code, calls, tools, _, _, root = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual([Path(call[1]).name for call in calls], GATES)
        self.assertEqual(len(tools), 1)
        self.assertEqual(calls[3][0], str(root / 'approved-project-node'))
        self.assertTrue(all('--runtime-file' in calls[index] for index in [0, 1, 2, 4]))
        self.assertEqual(calls[3][2], calls[0][3])
        self.assertIn('--runtime-only', calls[1])
        self.assertIn('--from-observed-run', calls[5])

    def test_each_child_failure_propagates_and_stops_later_gates(self):
        for index, gate in enumerate(GATES):
            with self.subTest(gate=gate):
                code, calls, _, _, _, _ = self.exercise(fail_gate=gate)
                self.assertEqual(code, 23)
                self.assertEqual([Path(call[1]).name for call in calls], GATES[:index + 1])

    def test_owned_full_launcher_survives_until_failure_and_is_stopped(self):
        code, _, _, launches, stopped, _ = self.exercise(fail_gate='g2-trace-browser.mjs', start=True)
        self.assertEqual(code, 23)
        self.assertEqual([mode for mode, _ in launches], ['full'])
        self.assertEqual(stopped, [launches[0][1]])

    def test_core_bootstrap_then_full_launcher_cleanup_is_preserved(self):
        code, calls, _, launches, stopped, _ = self.exercise(start=True, bootstrap=True, prepare=True)
        self.assertEqual(code, 0)
        self.assertEqual([mode for mode, _ in launches], ['core', 'full'])
        self.assertEqual(stopped, [launches[0][1], launches[1][1]])
        self.assertEqual(calls[0][2], 'bootstrap')
        self.assertEqual([Path(call[1]).name for call in calls[1:]], GATES)


class ObservabilityStatusTests(unittest.TestCase):
    """Exercise actual checks/reporting with synthetic telemetry I/O; no LGTM product claim."""

    def exercise(self, fault=None):
        module = load('g2-observability')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / '.tools/security'
            private.mkdir(parents=True)
            evidence = root / 'evidence'
            evidence.mkdir()
            runtime_file = private / 'control-plane.json'
            realm_file = private / 'realm.json'
            secrets = {key: 'synthetic-private-' + key for key in ['postgresPassword', 'keycloakPassword', 'grafanaPassword', 'certificatePassword', 'healthKey', 'rustfsAccessKey', 'rustfsSecretKey']}
            runtime_file.write_text(json.dumps({**secrets, 'realmFile': str(realm_file)}))
            realm_file.write_text(json.dumps({'clientSecret': 'synthetic-private-client'}))
            traces = [str(index) * 32 for index in range(1, 6)]
            (evidence / 'full-chain-identifiers.json').write_text(json.dumps({'traces': traces, 'ids': {'run': 'synthetic-run'}}))
            report_path = evidence / 'g2-observability.json'
            report_path.write_text('{"status":"PASS","stale":true}\n')
            real_write = Path.write_text
            real_replace = Path.replace
            failed = False

            def fetch(origin, path, parameters=None):
                if fault == 'fetch' and parameters and parameters.get('match[]') == 'agents_run_count_total':
                    raise OSError('synthetic-private-fetch-detail')
                if path == '/api/search':
                    return {'traces': [{'traceID': '6' * 32}]}
                if path.startswith('/api/traces/'):
                    spans = [{'spanId': 'synthetic-span', 'name': 'execution.run', 'attributes': [{'key': 'execution.creation_trace_id', 'value': {'stringValue': traces[2]}}]}, {'spanId': 'synthetic-gateway-span', 'name': 'semantic.query'}]
                    return {'batches': [{'scopeSpans': [{'spans': spans}]}]}
                if path == '/loki/api/v1/query_range':
                    return {'data': {'result': [{'stream': {'service_name': 'ontology-platform-api'}, 'values': [['1', secrets['healthKey'] if fault == 'privacy' else 'safe synthetic log']]}]}}
                if path == '/loki/api/v1/series':
                    return {'data': [{'service_name': 'ontology-platform-api', 'service_version': 'G2-THIN-SLICE-001', 'deployment_environment_name': 'Development'}]}
                if path == '/api/v1/series':
                    return {'status': 'success', 'data': [{'__name__': parameters['match[]'], 'operation': 'publish', 'status': 'Found'}]}
                raise AssertionError('unexpected substituted fetch')

            def write(path, text, *args, **kwargs):
                nonlocal failed
                raw_fault = fault == 'raw-write' and path.name.startswith('trace-')
                report_fault = fault == 'report-write' and '"status": "PASS"' in text
                initial_fault = fault in ['initial-write', 'persistent-write']
                if (not failed or fault == 'persistent-write') and (raw_fault or report_fault or initial_fault):
                    failed = True
                    raise OSError('synthetic-private-persistence-detail')
                return real_write(path, text, *args, **kwargs)

            def replace(path, target):
                nonlocal failed
                if fault == 'report-replace' and not failed and '"status": "PASS"' in path.read_text():
                    failed = True
                    raise OSError('synthetic-private-replace-detail')
                return real_replace(path, target)

            output = io.StringIO()
            caught = None
            with patch.object(module, 'ROOT', root), patch.object(module, 'EVIDENCE', evidence), patch.object(module, 'fetch', side_effect=fetch), patch.object(sys, 'argv', ['g2-observability.py', '--runtime-file', str(runtime_file)]), patch.object(Path, 'write_text', new=write), patch.object(Path, 'replace', new=replace), contextlib.redirect_stdout(output):
                try:
                    code = module.main()
                except Exception as failure:
                    caught = failure
                    code = 1
            report = json.loads(report_path.read_text()) if report_path.exists() else None
            exported = {path.name: path.read_text() for path in evidence.iterdir()}
            return code, caught, report, exported, output.getvalue()

    def test_complete_synthetic_io_path_is_the_only_pass(self):
        code, caught, report, exported, _ = self.exercise()
        self.assertEqual(code, 0)
        self.assertIsNone(caught)
        self.assertEqual(report['status'], 'PASS')
        self.assertIn('metric-agents_run_count_total.json', exported)

    def test_fetch_failure_cannot_leave_stale_pass(self):
        self.assert_failure('fetch')

    def test_raw_export_failure_after_all_assertions_cannot_report_pass(self):
        self.assert_failure('raw-write')

    def test_success_report_persistence_failure_cannot_leave_pass(self):
        self.assert_failure('report-write')

    def test_initial_report_persistence_failure_cannot_leave_stale_pass(self):
        self.assert_failure('initial-write')

    def test_atomic_success_report_replacement_failure_retains_fail(self):
        self.assert_failure('report-replace')

    def test_persistent_report_write_failure_removes_stale_pass(self):
        self.assert_failure('persistent-write')

    def test_privacy_failure_prevents_all_raw_exports(self):
        code, _, report, exported, output = self.exercise('privacy')
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(set(exported), {'full-chain-identifiers.json', 'g2-observability.json'})
        self.assertNotIn('synthetic-private-', ''.join(exported.values()) + output)

    def assert_failure(self, fault):
        code, caught, report, exported, output = self.exercise(fault)
        self.assertEqual(code, 1)
        self.assertIsInstance(caught, OSError)
        self.assertTrue(report is None or report['status'] == 'FAIL', report)
        self.assertNotIn('"status": "PASS"', output)
        self.assertNotIn('synthetic-private-', ''.join(exported.values()) + output)


if __name__ == '__main__':
    print('CONTROL_PLANE_ONLY: substituted processes and telemetry I/O; real product NOT_RUN', flush=True)
    unittest.main(verbosity=2)
