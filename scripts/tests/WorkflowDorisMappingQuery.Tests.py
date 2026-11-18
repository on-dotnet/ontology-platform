"""Doris 独立预期的定向反例；这些检查不启动或认证 Doris。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from workflow_doris_mapping_query import fixture_instant, reference_targets


class DorisReferenceTests(unittest.TestCase):
    def test_scoped_decimal_join_excludes_null_touching_and_other_scopes(self):
        entity = ('org-demo', 'site-a', '1.00', 10, 20)
        targets = [('T1', 'org-demo', 'site-a', '1.000', 10, 20),
                   ('T2', 'org-demo', 'site-a', '1.000', 19, 21),
                   ('T3', 'org-demo', 'site-a', '1.010', 10, 20),
                   ('T4', 'org-demo', 'site-a', None, 10, 20),
                   ('T5', 'org-demo', 'site-a', '1.000', 20, 21),
                   ('T6', 'org-demo', 'site-b', '1.000', 10, 20),
                   ('T7', 'other', 'site-a', '1.000', 10, 20)]
        self.assertEqual(reference_targets(entity, targets), ['T1', 'T2'])

    def test_last_microsecond_is_preserved(self):
        self.assertEqual(fixture_instant('2026-11-17 12:00:00.123459'), '2026-11-17T12:00:00.123459Z')
        for invalid in ('2026-11-17 12:00:00.12345', '2026-11-17 12:00:00.1234590'):
            with self.assertRaises(ValueError):
                fixture_instant(invalid)


if __name__ == '__main__':
    unittest.main()
