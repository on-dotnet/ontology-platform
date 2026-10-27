"""Control-plane tests only; real child exit codes cannot be replaced by fabricated product PASS."""
import contextlib
import importlib.util
import json
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

    def exercise(self, fail_gate=None, prefix='g3-m1-control'):
        spec = importlib.util.spec_from_file_location('m1_orchestrator', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / '.tools/security' / prefix
            private.mkdir(parents=True)
            runtime = private / 'runtime.json'
            runtime.write_text(json.dumps({'volumePrefix': prefix, 'healthKey': 'synthetic-health', 'realmFile': str(private / 'realm.json')}))
            log = root / 'children.jsonl'
            child = root / 'exit-child.py'
            child.write_text('import json,sys\nfrom pathlib import Path\nwith Path(sys.argv[1]).open("a") as f:f.write(json.dumps(sys.argv[2:-1])+"\\n")\nsys.exit(int(sys.argv[-1]))\n')
            original = subprocess.run

            def run(command, **kwargs):
                gate = Path(command[1]).name
                if gate == 'full-g2-e2e.py':
                    self.assertIn('--m1', command, 'M1 checks must run in the existing authenticated harness')
                return original([sys.executable, str(child), str(log), *command, '23' if gate == fail_gate else '0'], cwd=root)

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(module, 'ROOT', root))
                stack.enter_context(patch.object(sys, 'argv', [str(SCRIPT), '--runtime-file', str(runtime)]))
                stack.enter_context(patch.object(module.shared, 'wait_for'))
                stack.enter_context(patch.object(module.shared, 'stop'))
                stack.enter_context(patch.object(module.subprocess, 'check_output', return_value=json.dumps({'nodePath': str(root / 'project-node')})))
                stack.enter_context(patch.object(module.subprocess, 'run', side_effect=run))
                code = module.main()
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return code, [Path(call[1]).name for call in calls]

    def test_all_real_gate_selections_include_m1_and_regressions(self):
        code, calls = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(calls, GATES)

    def test_each_child_failure_stops_later_gates(self):
        for index, gate in enumerate(GATES):
            code, calls = self.exercise(gate)
            self.assertEqual(code, 23, gate)
            self.assertEqual(calls, GATES[:index + 1], gate)

    def test_protected_g2_runtime_is_refused(self):
        with self.assertRaises(SystemExit) as failure:
            self.exercise(prefix='g2-protected')
        self.assertNotEqual(failure.exception.code, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
