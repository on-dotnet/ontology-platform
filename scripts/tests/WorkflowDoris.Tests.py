#!/usr/bin/env python3
"""Doris结构入口拒绝缺失真实消费者，不能由接口存在冒充可用。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('doris', ROOT / 'scripts/maintenance/workflow_m2_doris.py')
DORIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DORIS)


class DorisAdmissionTests(unittest.TestCase):
    def test_wrong_task_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'TASK_INVALID'):
            DORIS.structural(ROOT, 'G4-M2-WEB-01')

    def test_empty_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'CONSUMER_MISSING'):
                DORIS.structural(Path(directory), DORIS.TASK)

    def test_current_structure_does_not_claim_product_pass(self):
        result = DORIS.structural(ROOT, DORIS.TASK)
        self.assertEqual('STRUCTURAL_READY', result['status'])
        self.assertEqual('NOT_RUN', result['lifecycle'])
        self.assertEqual('NOT_AUTHORIZED', result['production'])

    def test_production_guard_removal_is_rejected(self):
        result = DORIS.structural(ROOT, DORIS.TASK)
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
                DORIS.structural(root, DORIS.TASK)


class DorisEvidenceTests(unittest.TestCase):
    def test_empty_audit_cannot_claim_pass(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
        from workflow_m2_evidence import doris_audit
        with self.assertRaises((ValueError, KeyError)):
            doris_audit(b'', {'taskId': 'G4-M2-DORIS-01', 'runId': 'doris-123456789abc', 'status': 'PASS', 'skipped': 0, 'tests': 0, 'checks': [], 'cancellations': []})

    def test_unknown_task_cannot_use_doris_product_gate(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
        from workflow_m2_evidence import verify
        with self.assertRaisesRegex(ValueError, 'PRODUCT_TASK_GATE'):
            verify('UNAPPROVED-DORIS', 'backend', '0' * 64)


if __name__ == '__main__':
    unittest.main()
