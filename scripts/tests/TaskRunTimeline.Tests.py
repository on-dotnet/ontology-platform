"""Exercise real timeline records and subprocess exits without collecting command arguments."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'scripts/maintenance/task_run_timeline.py'


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.is_file(), 'Timeline implementation is required')
        spec = importlib.util.spec_from_file_location('timeline', PATH)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def row(self, step='a', start=0, end=10, dependencies=None, fingerprint='a'*64):
        return dict(schemaVersion=1, taskId='G3-M3-001', runId='fixture', stepId=step,
                    taskType='TEST', inputFingerprint=fingerprint,
                    startedAtUtc=f'2026-10-28T00:00:{start:02d}+00:00',
                    endedAtUtc=f'2026-10-28T00:00:{end:02d}+00:00', durationMs=(end-start)*1000,
                    outcome='PASS', errorCategory=None, dependsOn=dependencies or [],
                    concurrencyGroup='fixture', attempt=1, exitCode=0, commandLabel=step)

    def test_parallel_wall_time_is_not_cumulative_runtime(self):
        rows = [self.row('a', 0, 10), self.row('b', 0, 10), self.row('c', 10, 15, ['a', 'b'])]
        result = self.m.summarize(rows)
        self.assertEqual(result['wallClockMs'], 15000)
        self.assertEqual(result['cumulativeTaskMs'], 25000)
        self.assertEqual(result['overlapMs'], 10000)
        self.assertEqual(result['observableCriticalPathMs'], 15000)
        self.assertEqual(result['agentActiveTime'], 'UNKNOWN')

    def test_missing_extra_invalid_fields_are_refused(self):
        for key in self.row():
            value = self.row(); del value[key]
            with self.assertRaises(ValueError, msg=key): self.m.validate([value])
        value = self.row(); value['chatContent'] = 'not-collected'
        with self.assertRaises(ValueError): self.m.validate([value])
        for key, item in [('outcome', 'GREEN'), ('durationMs', -1), ('exitCode', 17), ('attempt', 0),
                          ('inputFingerprint', 'unknown'), ('startedAtUtc', '2026-10-28T00:00:00+08:00')]:
            value = self.row(); value[key] = item
            with self.assertRaises(ValueError, msg=key): self.m.validate([value])

    def test_dag_and_duplicate_identity_are_refused(self):
        for rows in [[self.row(), self.row()], [self.row(dependencies=['unknown'])],
                     [self.row(dependencies=['a'])],
                     [self.row('a', 0, 10), self.row('b', 5, 15, ['a'])]]:
            with self.assertRaises(ValueError): self.m.validate(rows)
        self.m.validate([self.row('a'), {**self.row('a'), 'runId': 'other', 'attempt': 2}])

    def test_attempts_and_rechecks_are_derived(self):
        rows = [self.row(), {**self.row('b', 10, 15), 'attempt': 2, 'commandLabel': 'a'}]
        self.assertEqual(self.m.summarize(rows)['recheckCount'], 1)
        rows[1]['attempt'] = 1
        with self.assertRaises(ValueError): self.m.validate(rows)

    def test_real_command_exit_and_only_label_are_recorded(self):
        with tempfile.TemporaryDirectory(prefix='m3-timeline-', dir=Path(tempfile.gettempdir()).resolve()) as directory:
            target = Path(directory)/'timeline.jsonl'
            sentinel = 'SYNTHETIC_ARGUMENT_MUST_NOT_BE_LOGGED'
            for step, code in [('ok', 0), ('failure', 17)]:
                result = subprocess.run([sys.executable, str(PATH), 'run', '--path', str(target),
                    '--task-id', 'G3-M3-001', '--run-id', 'fixture', '--step-id', step,
                    '--task-type', 'TEST', '--input-fingerprint', 'a'*64, '--command-label', 'synthetic-test',
                    '--', sys.executable, '-c', f'import sys; sys.exit({code})', sentinel], capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
            raw = target.read_text()
            self.assertNotIn(sentinel, raw)
            rows = [json.loads(line) for line in raw.splitlines()]
            self.assertEqual([r['exitCode'] for r in rows], [0, 17])
            self.assertEqual([r['outcome'] for r in rows], ['PASS', 'FAIL'])
            self.assertEqual(rows[1]['attempt'], 2)
            self.m.validate(rows)

    def test_nonzero_and_unknown_outcomes_cannot_be_success(self):
        fail = {**self.row(), 'outcome': 'FAIL', 'exitCode': 3, 'errorCategory': 'COMMAND_FAILED'}
        self.m.validate([fail])
        for row in [{**fail, 'exitCode': 0}, {**self.row(), 'exitCode': None},
                    {**self.row(), 'outcome': 'NOT_RUN', 'exitCode': None}]:
            with self.assertRaises(ValueError): self.m.validate([row])

    def test_simultaneous_commands_assign_attempt_under_writer_lock(self):
        with tempfile.TemporaryDirectory(prefix='m3-timeline-', dir=Path(tempfile.gettempdir()).resolve()) as directory:
            target = Path(directory)/'timeline.jsonl'
            commands = [[sys.executable, str(PATH), 'run', '--path', str(target),
                '--task-id', 'G3-M3-001', '--run-id', 'parallel', '--step-id', f'parallel-{index}',
                '--task-type', 'TEST', '--input-fingerprint', 'a'*64, '--command-label', 'parallel-test',
                '--', sys.executable, '-c', 'import time; time.sleep(.3)'] for index in range(4)]
            children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for command in commands]
            for child in children:
                _, error = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, error.decode())
            rows = self.m.read(target)
            self.assertEqual([row['attempt'] for row in rows], [1, 2, 3, 4])
            self.assertEqual(len(rows), 4)
            self.assertGreater(self.m.summarize(rows)['overlapMs'], 0)

    def test_ci_wrapper_records_real_failure_without_token_or_arguments(self):
        with tempfile.TemporaryDirectory(prefix='m3-timeline-', dir=Path(tempfile.gettempdir()).resolve()) as directory:
            environment={**os.environ,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'2','GITHUB_JOB':'engineering',
                         'TASK_TIMELINE_INPUT':'a'*64,'SYNTHETIC_PRIVATE_TOKEN':'NEVER_COLLECT_TOKEN'}
            result=subprocess.run([sys.executable,str(PATH),'ci','--step-id','failure','--task-type','TEST',
                '--',sys.executable,'-c','import sys; sys.exit(19)'],cwd=directory,env=environment,capture_output=True,text=True)
            self.assertEqual(result.returncode,19,result.stderr)
            target=Path(directory)/'artifacts/task-timeline-engineering.jsonl'
            rows=self.m.read(target)
            self.assertEqual(rows[0]['runId'],'ci-12345-2')
            self.assertEqual(rows[0]['exitCode'],19)
            self.assertNotIn('NEVER_COLLECT_TOKEN',target.read_text())

    def test_symlink_output_does_not_collect_or_replace_external_file(self):
        with tempfile.TemporaryDirectory(prefix='m3-timeline-', dir=Path(tempfile.gettempdir()).resolve()) as directory:
            outside = Path(directory)/'outside'; outside.write_text('retained')
            target = Path(directory)/'linked'; target.symlink_to(outside)
            with self.assertRaises(ValueError): self.m.append(target, self.row())
            self.assertEqual(outside.read_text(), 'retained')


if __name__ == '__main__': unittest.main()
