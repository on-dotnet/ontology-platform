#!/usr/bin/env python3
"""查询任务只接受批准闭包与真实准入，不借历史TaskId宣称成功。"""
import sys
import json
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
import workflow_environment as environment
import workflow_web_cache as web
import workflow
import workflow_m4_query as query

TASK = 'G4-M4-QUERY-001'


class QueryAdmissionTests(unittest.TestCase):
    def test_persistence_database_cannot_target_live_or_foreign_database(self):
        self.assertEqual('m4_query_test_0123456789ab', query.test_database_name('0123456789ab'))
        for value in ('query', '', 'a' * 11, '0123456789ab;DROP DATABASE query', 'ABCDEF012345'):
            with self.assertRaisesRegex(ValueError, 'QUERY_TEST_DATABASE_ID_INVALID'):
                query.test_database_name(value)

    def test_partial_database_creation_has_explicit_keep_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'artifacts/workflow' / TASK / query.RUN
            output.mkdir(parents=True)
            labels = json.dumps({'ontology.task-id': TASK, 'ontology.run-id': query.RUN}).encode()
            inspected = SimpleNamespace(returncode=0, stdout=b'', receipt={'commandId': 'inspection'})
            with patch.object(query, 'ROOT', root), patch('subprocess.check_output', return_value=labels), patch('workflow_execution.run', side_effect=[inspected, OSError('injected')]):
                with self.assertRaises(OSError):
                    query.test_database_control('exact-owned-container', '0123456789ab', True)
            record = json.loads((output / 'm4_query_test_0123456789ab-create.json').read_text())
            self.assertEqual('KEEP_UNVERIFIED', record['status'])
            self.assertEqual('m4_query_test_0123456789ab', record['database'])
            self.assertIn('task_marker', record['releaseCondition'])

    def test_container_cleanup_timeout_records_database_keep(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'artifacts/workflow' / TASK / query.RUN
            output.mkdir(parents=True)
            project = 'ontology-g4-m4-query-impl-01'
            (output / 'platform-resources.json').write_text(json.dumps(dict(taskId=TASK, runId=query.RUN, status='HEALTHY', project=project, resources=[{'id': 'owned-pg'}])))
            private = root / '.tools/security/g4-m4-query-001' / query.RUN / 'platform-pg'
            private.mkdir(parents=True)
            (private / 'password').write_text('synthetic-test-only')
            labels = {'ontology.task-id': TASK, 'ontology.run-id': query.RUN}
            container = dict(Config={'Labels': labels}, State={'Health': {'Status': 'healthy'}})
            image = dict(Id='sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55', Architecture='arm64')
            name = project + '-persistence-test-0123456789ab'
            absent = SimpleNamespace(returncode=1, stderr=('No such container: '+name).encode())
            completed = SimpleNamespace(returncode=0, stdout=b'', receipt={'commandId': 'test'})
            with patch.object(query, 'ROOT', root), patch.object(query, 'prepared'), patch.object(query, 'runtime_query_inventory', return_value=[]), patch.object(query, 'test_database_control'), patch('uuid.uuid4', return_value=SimpleNamespace(hex='0123456789ab')), patch('subprocess.check_output', side_effect=[json.dumps([container]).encode(), json.dumps([image]).encode()]), patch('subprocess.run', side_effect=[absent, subprocess.TimeoutExpired('inspect', 10)]), patch('workflow_execution.run', return_value=completed):
                with self.assertRaises(subprocess.TimeoutExpired):
                    query.persistence_test()
            record = json.loads((output / 'm4_query_test_0123456789ab-keep.json').read_text())
            self.assertEqual('KEEP_UNVERIFIED', record['status'])
            self.assertEqual(name, record['containerName'])
            self.assertIn('exact_test_container_absent', record['releaseCondition'])
            self.assertFalse((private / 'test-0123456789ab.env').exists())

    def test_public_m4_originals_have_exact_policy_gate(self):
        current = workflow.select_gates(['docs/evidence/G4-M4-QUERY-001/query-impl-01/stdout.txt.raw.json'])
        self.assertEqual('PLANNED', current['status'])
        self.assertIn('policy', current['affected'])
        self.assertEqual('BLOCKED', workflow.select_gates(['docs/evidence/G4-M4-UNKNOWN/raw.json'])['status'])

    def test_exact_baseline_archives_are_accepted(self):
        packages, _, _ = environment.locks(ROOT)
        actual = environment.approved_archives(ROOT, TASK, packages)
        self.assertEqual(packages, {key: row['contentHash'] for key, row in actual.items()})

    def test_unapproved_package_and_task_are_rejected(self):
        packages, _, _ = environment.locks(ROOT)
        with self.assertRaisesRegex(ValueError, 'APPROVED_CURRENT_LOCK_CLOSURE'):
            environment.approved_archives(ROOT, 'G4-M4-UNKNOWN', packages)
        with self.assertRaisesRegex(ValueError, 'APPROVED_CURRENT_LOCK_CLOSURE'):
            environment.approved_archives(ROOT, TASK, dict(packages, unapproved='fake'))

    def test_web_task_reaches_content_verification(self):
        adapter = Mock()
        adapter.web_marker.side_effect = ValueError('CONTENT_VERIFICATION_REACHED')
        with self.assertRaisesRegex(ValueError, '^CONTENT_VERIFICATION_REACHED$'):
            web.prepare(ROOT, ROOT / 'artifacts/workflow' / TASK / 'environment/key', {}, [], {}, None, None, adapter)
        adapter.web_marker.assert_called_once()

    def test_unknown_web_task_is_rejected_before_cache(self):
        adapter = Mock()
        with self.assertRaisesRegex(ValueError, 'TASK_ID'):
            web.prepare(ROOT, ROOT / 'artifacts/workflow/G4-M4-UNKNOWN/environment/key', {}, [], {}, None, None, adapter)
        adapter.web_marker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
