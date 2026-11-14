#!/usr/bin/env python3
"""映射任务只消费已锁闭包，缺失真实消费者不得宣称产品可用。"""
import importlib.util
from pathlib import Path
import unittest
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('mapping_environment', ROOT / 'scripts/maintenance/workflow_environment.py')
ENVIRONMENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENVIRONMENT)
TASK = 'G4-M3-MAPPING-001'
sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
import workflow_m3_mapping as MAPPING

WEB_SPEC = importlib.util.spec_from_file_location('mapping_web', ROOT / 'scripts/maintenance/workflow_web_cache.py')
WEB = importlib.util.module_from_spec(WEB_SPEC)
WEB_SPEC.loader.exec_module(WEB)


class MappingEnvironmentTests(unittest.TestCase):
    def test_current_baseline_closure_is_accepted_without_new_packages(self):
        packages, _, _ = ENVIRONMENT.locks(ROOT)
        try:
            actual = ENVIRONMENT.approved_archives(ROOT, TASK, packages)
        except ValueError:
            self.fail('Approved M3 task must accept the exact inherited baseline closure.')
        self.assertEqual(packages, {name: row['contentHash'] for name, row in actual.items()})
        self.assertIn('oracle.manageddataaccess.core/23.26.400', actual)

    def test_unknown_package_cannot_enter_the_mapping_task(self):
        packages, _, _ = ENVIRONMENT.locks(ROOT)
        packages['unapproved/1.0.0'] = 'unapproved'
        with self.assertRaisesRegex(ValueError, 'APPROVED_CURRENT_LOCK_CLOSURE'):
            ENVIRONMENT.approved_archives(ROOT, TASK, packages)

    def test_foreign_task_does_not_inherit_mapping_admission(self):
        packages, _, _ = ENVIRONMENT.locks(ROOT)
        with self.assertRaisesRegex(ValueError, 'APPROVED_CURRENT_LOCK_CLOSURE'):
            ENVIRONMENT.approved_archives(ROOT, 'G4-UNKNOWN-001', packages)


class MappingWebAdmissionTests(unittest.TestCase):
    def test_mapping_reaches_existing_cache_checks(self):
        adapter = Mock()
        adapter.web_marker.side_effect = ValueError('CACHE_CHECK_REACHED')
        home = ROOT / 'artifacts/workflow' / TASK / 'environment/key'
        with self.assertRaisesRegex(ValueError, '^CACHE_CHECK_REACHED$'):
            WEB.prepare(ROOT, home, {}, [], {}, None, None, adapter)
        adapter.web_marker.assert_called_once_with(ROOT, home, {})

    def test_unknown_task_is_rejected_before_cache_access(self):
        adapter = Mock()
        home = ROOT / 'artifacts/workflow/G4-M3-UNKNOWN-001/environment/key'
        with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_BLOCKED: TASK_ID'):
            WEB.prepare(ROOT, home, {}, [], {}, None, None, adapter)
        adapter.web_marker.assert_not_called()


class MappingConsumerTests(unittest.TestCase):
    def test_runtime_requires_registered_real_consumers(self):
        result = MAPPING.structural(ROOT, TASK)
        self.assertEqual('STRUCTURAL_READY', result['status'])
        self.assertEqual('NOT_RUN', result['lifecycle'])
        self.assertIn('worker', result['consumers'])

    def test_foreign_task_or_phase_cannot_borrow_admission(self):
        for task, phase in [('G3', 'runtime'), (TASK, 'M4')]:
            with self.assertRaisesRegex(ValueError, 'MAPPING_TASK_PHASE_INVALID'):
                MAPPING.structural(ROOT, task, phase)

    def test_missing_worker_or_outbox_registration_is_blocked(self):
        from execution_preflight import source_path
        for consumer in ('MappingJobWorker', 'MappingOutboxDispatcher'):
            def changed(root, path):
                original = source_path(root, path)
                if path.endswith('G4Composition.cs'):
                    return Mock(read_text=lambda: original.read_text().replace('builder.Services.AddHostedService<' + consumer + '>();', ''))
                return original
            with patch('execution_preflight.source_path', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'MAPPING_CONSUMER_NOT_REGISTERED'):
                    MAPPING.structural(ROOT, TASK)

    def test_missing_audit_or_endpoint_is_blocked(self):
        from execution_preflight import source_path
        for suffix, old, error in [('TransactionalAuditWriter.cs', '"mapping.activate",', 'MAPPING_AUDIT_NOT_REGISTERED'),
                                   ('G4Endpoints.cs', 'app.MapMappingEndpoints();', 'MAPPING_CONSUMER_NOT_REGISTERED')]:
            def changed(root, path):
                original = source_path(root, path)
                return Mock(read_text=lambda: original.read_text().replace(old, '')) if path.endswith(suffix) else original
            with patch('execution_preflight.source_path', side_effect=changed):
                with self.assertRaisesRegex(ValueError, error):
                    MAPPING.structural(ROOT, TASK)


class MappingEvidenceIdentityTests(unittest.TestCase):
    def test_old_success_receipt_cannot_borrow_current_input_summary(self):
        from workflow_execution import encoded, sha
        command = ['dotnet', 'actual-tests.dll']
        receipt = dict(stage='wire', inputFingerprint='old-input', cwd=str(ROOT), commandSummary=dict(sha256=sha(encoded(command))), classification='SUCCESS', exitCode=0)
        with self.assertRaisesRegex(ValueError, 'MAPPING_COMMAND_IDENTITY'):
            MAPPING.demand_command_identity(receipt, 'wire', 'current-input', command, ROOT)
        MAPPING.demand_command_identity(receipt, 'wire', 'old-input', command, ROOT)

    def test_different_test_command_stage_or_worktree_is_rejected(self):
        from workflow_execution import encoded, sha
        command = ['dotnet', 'actual-tests.dll']
        receipt = dict(stage='wire', inputFingerprint='input', cwd=str(ROOT), commandSummary=dict(sha256=sha(encoded(command))))
        for stage, argv, cwd in [('semantics', command, ROOT), ('wire', ['dotnet', 'other.dll'], ROOT), ('wire', command, ROOT.parent)]:
            with self.assertRaisesRegex(ValueError, 'MAPPING_COMMAND_IDENTITY'):
                MAPPING.demand_command_identity(receipt, stage, 'input', argv, cwd)

    def test_new_disk_build_cannot_attest_old_service_process(self):
        startup = dict(inputKey='old-source', outputKey='old-output', receiptSha256='old-build')
        current = dict(inputKey='new-source', outputKey='new-output', receiptSha256='new-build')
        with self.assertRaisesRegex(ValueError, 'MAPPING_PROCESS_BUILD_DRIFT'):
            MAPPING.demand_process_build(startup, current)
        MAPPING.demand_process_build(current, current)

    def test_omitted_revocation_takeover_or_rotation_cannot_pass(self):
        for mode in ('worker', 'permissions', 'authority', 'rotation', 'visual'):
            with self.assertRaisesRegex(ValueError, 'MAPPING_BROWSER_REQUIRED_COVERAGE'):
                MAPPING.demand_browser_coverage(mode, [dict(name='ordinary_success', status='PASS')])

    def test_old_parser_or_substituted_actual_manifest_is_rejected(self):
        import tempfile
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            reader = root / 'reader'
            reader.mkdir()
            assembly = reader / 'OntologyPlatform.Contracts.dll'
            assembly.write_bytes(b'current-strict-parser')
            manifest = root / 'actual-v2-manifest.json'
            manifest.write_bytes(b'actual-history')
            binaries = {assembly.name: hashlib.sha256(assembly.read_bytes()).hexdigest()}
            expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
            MAPPING.demand_compatibility_reader(reader, binaries, expected)
            assembly.write_bytes(b'old-loose-parser')
            with self.assertRaisesRegex(ValueError, 'MAPPING_COMPATIBILITY_READER_DRIFT'):
                MAPPING.demand_compatibility_reader(reader, binaries, expected)
            assembly.write_bytes(b'current-strict-parser')
            manifest.write_bytes(b'substituted-history')
            with self.assertRaisesRegex(ValueError, 'MAPPING_COMPATIBILITY_READER_DRIFT'):
                MAPPING.demand_compatibility_reader(reader, binaries, expected)

    def test_unknown_gate_cannot_claim_qualification(self):
        with self.assertRaisesRegex(ValueError, 'MAPPING_GATE_INPUT_INVALID'):
            MAPPING.qualify('mapping-impl-01', 'm4', 'fake')


if __name__ == '__main__':
    unittest.main()
