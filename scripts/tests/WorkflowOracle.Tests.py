#!/usr/bin/env python3
"""Oracle结构入口拒绝缺失真实消费者，不能由接口存在冒充可用。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('oracle', ROOT / 'scripts/maintenance/workflow_m2_oracle.py')
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)


class OracleAdmissionTests(unittest.TestCase):
    def test_wrong_task_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'TASK_INVALID'):
            ORACLE.structural(ROOT, 'G4-M2-WEB-01')

    def test_empty_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'CONSUMER_MISSING'):
                ORACLE.structural(Path(directory), ORACLE.TASK)

    def test_current_structure_does_not_claim_product_pass(self):
        result = ORACLE.structural(ROOT, ORACLE.TASK)
        self.assertEqual('STRUCTURAL_READY', result['status'])
        self.assertEqual('NOT_RUN', result['lifecycle'])
        self.assertEqual('NOT_AUTHORIZED', result['production'])

    def test_production_guard_removal_is_rejected(self):
        result = ORACLE.structural(ROOT, ORACLE.TASK)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for relative in result['consumers'].values():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                text = (ROOT / relative).read_text()
                if relative.endswith('G4Composition.cs'):
                    text = text.replace('!builder.Environment.IsDevelopment()', 'false')
                path.write_text(text)
            with self.assertRaisesRegex(ValueError, 'GUARD_MISSING'):
                ORACLE.structural(root, ORACLE.TASK)


class OracleControlTests(unittest.TestCase):
    def test_foreign_runtime_and_unregistered_command_are_rejected_before_docker(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
        from workflow_oracle_fixture import load_source, control
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'runtime.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'RUNTIME_BOUNDARY'):
                load_source(path)
        with self.assertRaisesRegex(ValueError, 'CONTROL_MODE'):
            control('unused', 'arbitrary-sql')


class OraclePlatformBoundaryTests(unittest.TestCase):
    def test_platform_control_rejects_foreign_runtime_before_docker(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
        from workflow_oracle_platform import control
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'platform.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'PLATFORM_BOUNDARY'):
                control(path, 'audit-on')



class OracleFrozenMetadataTests(unittest.TestCase):
    def test_exact_original_and_changed_variants(self):
        import subprocess
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT / 'scripts/tests/OracleFrozenMetadata.Tests.ps1')], capture_output=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr.decode())



if __name__ == '__main__':
    unittest.main()
