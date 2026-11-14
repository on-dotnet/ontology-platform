#!/usr/bin/env python3
"""查询任务只接受批准闭包与真实准入，不借历史TaskId宣称成功。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
import workflow_environment as environment
import workflow_web_cache as web

TASK = 'G4-M4-QUERY-001'


class QueryAdmissionTests(unittest.TestCase):
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
