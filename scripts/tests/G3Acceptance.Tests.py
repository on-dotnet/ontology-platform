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


class RealBrowserEntryTests(unittest.TestCase):
    """Exercise the real downstream argparse and command construction, not a child-name mock."""

    def invoke(self, flag):
        script = SCRIPT.with_name('full-g2-e2e.py')
        spec = importlib.util.spec_from_file_location('real_browser_entry', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        runtime = module.ROOT / '.tools/security/g3-m3-parser-test/runtime.json'
        with patch.object(sys, 'argv', [str(script), '--runtime-file', str(runtime), flag]), \
                patch.object(module.subprocess, 'check_output', return_value=json.dumps({'nodePath': '/project/node'})), \
                patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as child:
            self.assertEqual(module.main(), 0)
            return child.call_args.args[0]

    def test_three_m3_modes_reach_real_browser_flags(self):
        for flag in ['--m3', '--m3-api-only', '--m3-ui-only']:
            with self.subTest(flag=flag):
                command = self.invoke(flag)
                self.assertIn(flag, command)
                self.assertEqual('--full' in command, flag == '--m3')
                if flag == '--m3':
                    self.assertIn('--m1', command)
                    self.assertIn('--m2', command)

    def test_precise_m4_modes_reach_real_browser_flags(self):
        for flag in ['--m4', '--m4-api-only', '--m4-ui-only', '--m4-diff-only', '--m4-impact-only']:
            command = self.invoke(flag)
            self.assertIn(flag, command)
            self.assertEqual('--full' in command, flag == '--m4')
            if flag == '--m4':
                for prior in ['--m1', '--m2', '--m3']: self.assertIn(prior, command)

    def test_m5_full_dispatch_includes_m1_to_m4_and_partial_is_precise(self):
        full=self.invoke('--m5')
        for flag in ['--full','--m1','--m2','--m3','--m4','--m5']:self.assertIn(flag,full)
        for flag in ['--m5-api-only','--m5-ui-only']:
            value=self.invoke(flag)
            self.assertIn(flag,value)
            self.assertNotIn('--full',value)

    def test_existing_m2_and_unknown_flag(self):
        for flag in ['--m2', '--m2-api-only', '--m2-ui-only']:
            self.assertIn(flag, self.invoke(flag))
        with self.assertRaises(SystemExit) as result:
            self.invoke('--m6')
        self.assertEqual(result.exception.code, 2)

    def test_real_smoke_fault_checkpoint_is_forwarded(self):
        self.assertIn('--workspace-smoke-only', self.invoke('--workspace-smoke-only'))
        self.assertIn('--smoke-fault-check', self.invoke('--smoke-fault-check'))

    def test_actual_node_writer_preserves_detailed_smoke_receipt(self):
        result = subprocess.run(['node', '--test', str(SCRIPT.parents[1] / 'tests/G3BrowserReport.Tests.mjs')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class M1OrchestrationTests(unittest.TestCase):
    """Keep gate selection/order/failure propagation real, isolate external services only."""

    def exercise(self, fail_gate=None, prefix='g3-m1-control', launch_failure=False, milestone=None, api_only=False, ui_only=False, smoke_fault=False, workspace_smoke=False, diff_only=False, impact_only=False, retry_unchanged=False, record_failure=False, child_failure_code=23):
        spec = importlib.util.spec_from_file_location('m1_orchestrator', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
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
                    selected = '--m4-impact-only' if impact_only else '--m4-diff-only' if diff_only else '--workspace-smoke-only' if workspace_smoke else '--' + (milestone or 'M2').lower() + ('-api-only' if api_only else '-ui-only') if api_only or ui_only else '--m1'
                    self.assertIn(selected, command, 'Selected checks must run in the existing authenticated harness')
                    if milestone == 'M2' and not workspace_smoke: self.assertIn('--m2-api-only' if api_only else '--m2-ui-only' if ui_only else '--m2', command, 'M2 checks must execute in the real authenticated harness')
                    if milestone == 'M3' and not workspace_smoke: self.assertIn('--m3-api-only' if api_only else '--m3-ui-only' if ui_only else '--m3', command, 'M3 checks must execute in the real authenticated harness')
                    if milestone == 'M4' and not workspace_smoke: self.assertIn('--m4-impact-only' if impact_only else '--m4-diff-only' if diff_only else '--m4-api-only' if api_only else '--m4-ui-only' if ui_only else '--m4', command)
                    if smoke_fault: self.assertIn('--smoke-fault-check', command)
                    # Parse the exact upstream argument combination with the real downstream entry.
                    entry_spec = importlib.util.spec_from_file_location('downstream_browser', SCRIPT.with_name(gate))
                    entry = importlib.util.module_from_spec(entry_spec)
                    entry_spec.loader.exec_module(entry)
                    with patch.object(entry, 'ROOT', root), patch.object(sys, 'argv', command[1:]), \
                            patch.object(entry.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                        self.assertEqual(entry.main(), 0)
                if gate == fail_gate and launch_failure:
                    return original([str(root / 'actual-missing-gate-executable')], cwd=root)
                return original([sys.executable, str(child), str(log), *command, str(child_failure_code) if gate == fail_gate else '0'], cwd=root)

            def output(command, **kwargs):
                return '1' * 40 if command[0] == 'git' else json.dumps({'nodePath': str(root / 'project-node')})

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]))
                stack.enter_context(patch.object(module, 'ROOT', root))
                stack.enter_context(patch.object(sys, 'argv', [str(SCRIPT), '--runtime-file', str(runtime)] + (['--milestone', milestone] if milestone else []) + (['--api-only'] if api_only else []) + (['--ui-only'] if ui_only else []) + (['--smoke-fault-check'] if smoke_fault else []) + (['--workspace-smoke-only'] if workspace_smoke else []) + (['--diff-only'] if diff_only else []) + (['--impact-only'] if impact_only else [])))
                if record_failure:
                    stack.enter_context(patch.object(module.preflight.FailureState, 'record', side_effect=OSError('synthetic_receipt_write_failure')))
                stack.enter_context(patch.object(module, 'gate_fingerprint', return_value='a'*64))
                stack.enter_context(patch.object(module.shared, 'wait_for'))
                stack.enter_context(patch.object(module.shared, 'stop'))
                stack.enter_context(patch.dict(os.environ, {'PLATFORM_EVIDENCE_DIR': 'docs/evidence/' + task + '/runtime'}))
                stack.enter_context(patch.object(module.subprocess, 'check_output', side_effect=output))
                stack.enter_context(patch.object(module.subprocess, 'run', side_effect=run))
                try:
                    code = module.main()
                    if retry_unchanged:
                        self.assertEqual(module.main(), 2, '同输入失败必须在子进程前阻断')
                except OSError:
                    if not launch_failure and not record_failure:
                        raise
                    code = 1
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            manifests = list(stale.parent.rglob('acceptance.json'))
            proof = json.loads(manifests[0].read_text()) if len(manifests) == 1 else None
            timelines = list(stale.parent.rglob('task-run-timeline.jsonl'))
            if proof is not None: proof['_testObservedTimeline'] = [json.loads(line) for path in timelines for line in path.read_text().splitlines()]
            return code, [Path(call[1]).name for call in calls], proof, evidence_seen, stale.read_text()

    def test_owned_e0_workspace_smoke_runs_only_fast_gate_and_preserves_fault_flag(self):
        code,calls,proof,*_=self.exercise(prefix='g3-m3-smoke-control',milestone='M3',workspace_smoke=True,smoke_fault=True)
        self.assertEqual(code,0)
        self.assertEqual(calls,['full-g2-e2e.py'])
        self.assertEqual(proof['scope'],'WORKSPACE_SMOKE_ONLY')
        self.assertEqual(len(proof['_testObservedTimeline']),1)

    def test_real_child_gates_automatically_record_timeline_and_failure_exit(self):
        for failed in [None, 'g3-compatibility.py']:
            code,calls,proof,*_=self.exercise(prefix='g3-m3-timing-control',milestone='M3',fail_gate=failed)
            rows=proof['_testObservedTimeline']
            self.assertEqual(len(rows),len(calls))
            self.assertGreater(len(rows),0)
            self.assertEqual([row['commandLabel'] for row in rows],calls)
            self.assertEqual(rows[-1]['exitCode'],23 if failed else 0)
            self.assertEqual(rows[-1]['outcome'],'FAIL' if failed else 'PASS')
            for index,row in enumerate(rows):
                self.assertEqual(row['dependsOn'],[] if index==0 else [rows[index-1]['stepId']])
                self.assertEqual(row['taskId'],'G3-M3-001')
                self.assertGreaterEqual(row['durationMs'],0)
                self.assertNotIn('runtime.json',json.dumps(row))

    def test_m3_full_chain_runs_smoke_fault_through_actual_parsers(self):
        code,calls,proof,*_=self.exercise(prefix='g3-m3-fault-control',milestone='M3',smoke_fault=True)
        self.assertEqual(code,0)
        self.assertEqual(calls,GATES)
        self.assertEqual(proof['scope'],'FULL')

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

    def test_second_m2_integration_selects_only_real_ui_checkpoint(self):
        code,calls,proof,_,_=self.exercise(prefix='g3-m2-control',milestone='M2',ui_only=True)
        self.assertEqual(code,0)
        self.assertEqual(calls,['full-g2-e2e.py'])
        self.assertEqual(proof['scope'],'UI_ONLY')

    def test_m3_selects_own_runtime_and_real_gates(self):
        code,calls,proof,selected,_=self.exercise(prefix='g3-m3-control',milestone='M3')
        self.assertEqual(code,0)
        self.assertEqual(calls,GATES)
        self.assertEqual(proof['milestone'],'M3')
        self.assertTrue(all('G3-M3-001/runtime/' in item for item in selected))

    def test_m3_partial_modes_parse_the_exact_upstream_command(self):
        for mode in ('api_only', 'ui_only'):
            with self.subTest(mode=mode):
                code, calls, proof, *_ = self.exercise(prefix='g3-m3-control', milestone='M3', **{mode: True})
                self.assertEqual(code, 0)
                self.assertEqual(calls, ['full-g2-e2e.py'])
                self.assertEqual(proof['scope'], 'API_ONLY' if mode == 'api_only' else 'UI_ONLY')

    def test_m4_own_runtime_checkpoints_and_failure_propagation(self):
        for mode in ({}, {'api_only': True}, {'ui_only': True}, {'diff_only': True}, {'impact_only': True}, {'workspace_smoke': True, 'smoke_fault': True}):
            code, calls, proof, selected, _ = self.exercise(prefix='g3-m4-control', milestone='M4', **mode)
            self.assertEqual(code, 0)
            self.assertEqual(calls, GATES if not mode else GATES[:1])
            self.assertTrue(all('G3-M4-001/runtime/' in item for item in selected))
        code, calls, proof, *_ = self.exercise(prefix='g3-m4-control', milestone='M4', fail_gate=GATES[0])
        self.assertEqual(code, 23)
        self.assertEqual(calls, GATES[:1])
        self.assertEqual(proof['status'], 'FAIL')
        self.assertTrue(all(item['status'] == 'NOT_RUN' for item in proof['gates'][1:]))

    def test_receipt_write_failure_keeps_actual_child_zero_or_failure(self):
        for fail_gate, expected in [(None,0),(GATES[0],17)]:
            code,calls,proof,*_=self.exercise(prefix='g3-m5-control',milestone='M5',fail_gate=fail_gate,record_failure=True,child_failure_code=17)
            self.assertEqual(code,1)
            self.assertEqual(calls,GATES[:1])
            row=proof['_testObservedTimeline'][0]
            self.assertEqual(row['exitCode'],expected)
            self.assertEqual(row['outcome'],'PASS' if expected==0 else 'FAIL')
            self.assertEqual(row['errorCategory'],None if expected==0 else 'COMMAND_FAILED')

    def test_unchanged_expensive_failure_is_blocked_before_second_child(self):
        code,calls,proof,*_=self.exercise(prefix='g3-m5-control',milestone='M5',fail_gate=GATES[0],retry_unchanged=True)
        self.assertEqual(code,23)
        self.assertEqual(calls,GATES[:1])

    def test_m5_all_and_checkpoints_keep_old_gates_and_schema2_exits(self):
        for mode in ({}, {'api_only':True}, {'ui_only':True}, {'workspace_smoke':True}):
            code,calls,proof,selected,_=self.exercise(prefix='g3-m5-control',milestone='M5',**mode)
            self.assertEqual(code,0)
            self.assertEqual(calls,GATES if not mode else GATES[:1])
            self.assertTrue(all('G3-M5-001/runtime/' in value for value in selected))
            self.assertTrue(all(row['schemaVersion']==2 and row['exitCode']==0 and row['timingStatus']=='VALID' for row in proof['_testObservedTimeline']))

    def test_wrong_runtime_and_future_milestones_are_refused(self):
        for prefix,milestone in [('g3-m1-control','M2'),('g3-m2-control','M3'),('g3-m3-control','M4'),('g3-m4-control','M5'),('g3-m6-control','M6')]:
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
