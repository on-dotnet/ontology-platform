"""Control-plane tests only; real child exit codes cannot be replaced by fabricated product PASS."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'acceptance/g3-acceptance-runtime.py'
GATES = ['full-g2-e2e.py', 'g3-compatibility.py', 'g1-regression.py', 'g2-observability.py',
         'g2-trace-browser.mjs', 'g2-readiness-fault.py', 'performance-baseline.py']


class M1OrchestrationTests(unittest.TestCase):
    """Keep gate selection/order/failure propagation real, isolate external services only."""

    def exercise(self, fail_gate=None, prefix='g3-m1-control', launch_failure=False, milestone=None, api_only=False):
        spec = importlib.util.spec_from_file_location('m1_orchestrator', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / '.tools/security' / prefix
            private.mkdir(parents=True)
            runtime = private / 'runtime.json'
            runtime.write_text(json.dumps({'volumePrefix': prefix, 'healthKey': 'synthetic-health', 'realmFile': str(private / 'realm.json')}))
            task = 'G3-' + (milestone or 'M1') + '-001'
            stale = root / ('docs/evidence/' + task + '/runtime/m1-browser.json')
            stale.parent.mkdir(parents=True)
            stale.write_text('{"status":"PASS","runId":"old-run"}\n')
            log = root / 'children.jsonl'
            child = root / 'exit-child.py'
            child.write_text('import json,sys\nfrom pathlib import Path\nwith Path(sys.argv[1]).open("a") as f:f.write(json.dumps(sys.argv[2:-1])+"\\n")\nsys.exit(int(sys.argv[-1]))\n')
            original = subprocess.run
            evidence_seen = []

            def run(command, **kwargs):
                evidence_seen.append(os.environ.get('PLATFORM_EVIDENCE_DIR'))
                gate = Path(command[1]).name
                if gate == 'full-g2-e2e.py':
                    self.assertIn('--m2-api-only' if api_only else '--m1', command, 'Selected checks must run in the existing authenticated harness')
                    if milestone == 'M2': self.assertIn('--m2-api-only' if api_only else '--m2', command, 'M2 checks must execute in the real authenticated harness')
                if gate == fail_gate and launch_failure:
                    return original([str(root / 'actual-missing-gate-executable')], cwd=root)
                return original([sys.executable, str(child), str(log), *command, '23' if gate == fail_gate else '0'], cwd=root)

            def output(command, **kwargs):
                return '1' * 40 if command[0] == 'git' else json.dumps({'nodePath': str(root / 'project-node')})

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]))
                stack.enter_context(patch.object(module, 'ROOT', root))
                stack.enter_context(patch.object(sys, 'argv', [str(SCRIPT), '--runtime-file', str(runtime)] + (['--milestone', milestone] if milestone else []) + (['--api-only'] if api_only else [])))
                stack.enter_context(patch.object(module.shared, 'wait_for'))
                stack.enter_context(patch.object(module.shared, 'stop'))
                stack.enter_context(patch.dict(os.environ, {'PLATFORM_EVIDENCE_DIR': 'docs/evidence/' + task + '/runtime'}))
                stack.enter_context(patch.object(module.subprocess, 'check_output', side_effect=output))
                stack.enter_context(patch.object(module.subprocess, 'run', side_effect=run))
                try:
                    code = module.main()
                except OSError:
                    if not launch_failure:
                        raise
                    code = 1
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            manifests = list(stale.parent.rglob('acceptance.json'))
            proof = json.loads(manifests[0].read_text()) if len(manifests) == 1 else None
            return code, [Path(call[1]).name for call in calls], proof, evidence_seen, stale.read_text()

    def test_all_real_gate_selections_include_m1_and_regressions(self):
        code, calls, *_ = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(calls, GATES)

    def test_each_child_failure_stops_later_gates(self):
        for index, gate in enumerate(GATES):
            code, calls, *_ = self.exercise(gate)
            self.assertEqual(code, 23, gate)
            self.assertEqual(calls, GATES[:index + 1], gate)

    def test_m2_selects_its_own_runtime_evidence_and_authenticated_checks(self):
        code,calls,proof,selected,_=self.exercise(prefix='g3-m2-control',milestone='M2')
        self.assertEqual(code,0)
        self.assertEqual(calls,GATES)
        self.assertEqual(proof['status'],'PASS')
        self.assertTrue(all('G3-M2-001/runtime/' in item for item in selected))

    def test_first_m2_integration_selects_real_api_only_without_claiming_full_gates(self):
        code,calls,proof,_,_=self.exercise(prefix='g3-m2-control',milestone='M2',api_only=True)
        self.assertEqual(code,0)
        self.assertEqual(calls,['full-g2-e2e.py'])
        self.assertEqual(proof['scope'],'API_ONLY')
        self.assertEqual(len(proof['gates']),1)

    def test_m2_cannot_reuse_m1_runtime_or_enable_m3(self):
        for prefix,milestone in [('g3-m1-control','M2'),('g3-m3-control','M3')]:
            with self.assertRaises(SystemExit):self.exercise(prefix=prefix,milestone=milestone)

    def test_protected_g2_runtime_is_refused(self):
        with self.assertRaises(SystemExit) as failure:
            self.exercise(prefix='g2-protected')
        self.assertNotEqual(failure.exception.code, 0)

    def test_failed_attempt_cannot_consume_or_certify_stale_pass(self):
        code, calls, proof, selected, old = self.exercise('full-g2-e2e.py')
        self.assertEqual(code, 23)
        self.assertEqual(calls, GATES[:1])
        self.assertIsNotNone(proof, 'Every attempt needs its own actual completion manifest')
        self.assertEqual(proof['status'], 'FAIL')
        self.assertEqual(proof['sourceHead'], '1' * 40)
        self.assertEqual(proof['gates'][0]['status'], 'FAIL')
        self.assertTrue(all(row['status'] == 'NOT_RUN' for row in proof['gates'][1:]))
        self.assertTrue(proof['runId'])
        self.assertEqual(len(set(selected)), 1)
        self.assertNotEqual(selected[0], 'docs/evidence/G3-M1-001/runtime')
        self.assertIn(proof['runId'], selected[0])
        self.assertEqual(json.loads(old), {'status': 'PASS', 'runId': 'old-run'})

    def test_actual_process_start_failure_marks_current_failed_and_later_not_run(self):
        code, calls, proof, *_ = self.exercise('full-g2-e2e.py', launch_failure=True)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertEqual(proof['status'], 'FAIL')
        self.assertEqual(proof['gates'][0]['status'], 'FAIL')
        self.assertIsNone(proof['gates'][0]['exitCode'])
        self.assertEqual(proof['gates'][0]['failureCategory'], 'FileNotFoundError')
        self.assertTrue(all(item['status'] == 'NOT_RUN' for item in proof['gates'][1:]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
