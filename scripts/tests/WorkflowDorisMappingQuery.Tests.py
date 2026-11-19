"""Doris 独立预期的定向反例；这些检查不启动或认证 Doris。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from workflow_doris_mapping_query import fixture_instant, fixture_tables, reference_targets
import workflow_doris_s0_cancel as cancellation
from workflow import select_gates


class DorisReferenceTests(unittest.TestCase):
    def test_changed_shared_runtime_selects_the_consuming_doris_gate(self):
        gate = 'doris-mapping-query-admission'
        for name in ('workflow_execution.py','execution_preflight.py','workflow_m2_build.py','workflow_m4_query_runtime.py',
                     'workflow_doris_fixture.py','canonical_fuseki.py','doris_keep_pg_recovery.py'):
            with self.subTest(name=name):
                self.assertIn(gate, select_gates(['scripts/maintenance/'+name])['affected'])
        keep = select_gates(['docs/evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/r0-review.json'])
        self.assertIn('doris-keep-preservation',keep['affected'])
        self.assertIn(gate,keep['affected'])

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

    def test_first_catalog_gets_both_unique_mow_tables_with_fixed_keys(self):
        definitions = fixture_tables()
        self.assertEqual(len(definitions), 2)
        for ddl, table, identity in zip(definitions, ('dmq_entity', 'dmq_target'), ('entity_id', 'target_id'), strict=True):
            self.assertIn('CREATE TABLE fixture.' + table, ddl)
            self.assertIn('UNIQUE KEY(org_id, site_id, ' + identity + ')', ddl)
            self.assertIn('"enable_unique_key_merge_on_write"="true"', ddl)
            self.assertEqual(ddl.count('DATETIMEV2(6) NOT NULL'), 4)

    def test_missing_or_live_backend_cannot_qualify_cancellation(self):
        self.assertTrue(any(cancellation.activity_counts('0\t1')))
        self.assertFalse(any(cancellation.activity_counts('0\t0')))
        for sample in ('', '0', '0\t', '0\t-1'):
            with self.assertRaisesRegex(ValueError, 'SOURCE_OBSERVATION_INCOMPLETE'):
                cancellation.activity_counts(sample)

    def test_observer_keeps_connection_and_query_identity_separate(self):
        row, = cancellation.rows('Id\tUser\tQueryId\tInfo\n60\tfixture_reader\tfe-be\tSELECT 1;')
        self.assertEqual((row['Id'], row['QueryId'], row['User']), ('60', 'fe-be', 'fixture_reader'))
        self.assertEqual(cancellation.rows(''), [])

    def test_last_microsecond_is_preserved(self):
        self.assertEqual(fixture_instant('2026-11-17 12:00:00.123459'), '2026-11-17T12:00:00.123459Z')
        for invalid in ('2026-11-17 12:00:00.12345', '2026-11-17 12:00:00.1234590'):
            with self.assertRaises(ValueError):
                fixture_instant(invalid)


if __name__ == '__main__':
    unittest.main()
