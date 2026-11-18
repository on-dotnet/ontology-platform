"""旧卷恢复入口在接触目标之前拒绝被替换或越界的私有原件。"""
from contextlib import nullcontext
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
import doris_keep_preservation as keep
import doris_keep_drain as drain
import doris_keep_readmit as readmit


class RestoreGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name) / 'synthetic.tar'

    def write(self, extra):
        with tarfile.open(self.archive, 'w') as stream:
            root = tarfile.TarInfo('.')
            root.type = tarfile.DIRTYPE
            stream.addfile(root)
            stream.addfile(extra, io.BytesIO())
        os.chmod(self.archive, 0o600)

    def test_checksum_rejected_before_target_access(self):
        self.write(tarfile.TarInfo('synthetic'))
        with patch.object(keep, 'execute', side_effect=AssertionError('touched target')):
            with self.assertRaisesRegex(ValueError, 'BACKUP_HASH_MISMATCH'):
                keep.restore_empty('unused', self.archive, '0' * 64)

    def test_traversal_absolute_duplicates_and_links_rejected(self):
        entries = [tarfile.TarInfo(name) for name in ('../escape', '/absolute', '.')]
        link = tarfile.TarInfo('alias')
        link.type, link.linkname = tarfile.SYMTYPE, '../../outside'
        for item in [*entries, link]:
            with self.subTest(name=item.name):
                self.write(item)
                with self.assertRaisesRegex(ValueError, 'ARCHIVE_MEMBER'):
                    keep.check_archive(self.archive)

    def test_insecure_mode_or_second_link_rejected(self):
        self.write(tarfile.TarInfo('ordinary'))
        self.assertEqual(keep.check_archive(self.archive), 2)
        os.chmod(self.archive, 0o644)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_PERMISSIONS'):
            keep.check_archive(self.archive)
        os.chmod(self.archive, 0o600)
        os.link(self.archive, self.archive.with_suffix('.alternate'))
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_PERMISSIONS'):
            keep.check_archive(self.archive)


class DrainWitness(unittest.TestCase):
    def test_activity_reports_the_actual_sample_before_stopping(self):
        inventory = [{'containerId': str(i), 'service': 'platform-pg' if i < 2 else 'pg-source'} for i in range(4)]
        busy = {'0': [0, 0, 0, 0, 0, 1]}
        facts = []
        with (patch.object(drain, 'product_tables', return_value=list(drain.TABLES)),
              patch.object(drain, 'fence', side_effect=lambda *args: nullcontext(123)),
              patch.object(drain, 'confirm'),
              patch.object(drain, 'sample', side_effect=[{'0': [0]}, {'0': [0]}, busy])):
            with self.assertRaisesRegex(ValueError, 'DRAIN_ACTIVITY_DETECTED'):
                with drain.drained(inventory, facts.append) as (_, check):
                    check()
        self.assertEqual(facts, [busy])

    def test_activity_exclusion_only_applies_to_verified_backend(self):
        with patch.object(drain, 'query', return_value=['0']) as query:
            drain.sample([{'service': 'pg-source', 'containerId': 'source'}], {'source': 531})
        self.assertIn('pid<>531', query.call_args.args[1])
        self.assertNotIn('application_name', query.call_args.args[1])


class ReadmissionGuards(unittest.TestCase):
    def test_first_busy_database_is_persisted_before_any_later_database(self):
        from copy import deepcopy
        busy = {'queuedOrRunningMappingJobs': 1, 'nonIdleClients': 0, 'clients': []}
        state, written = {'samples': []}, []
        rows = [{'containerId': 'a'}, {'containerId': 'b'}]
        with (patch.object(drain, 'observed_database', return_value=busy) as observe,
              patch.object(readmit.cold, 'save', side_effect=lambda data: written.append(deepcopy(data)))):
            with self.assertRaisesRegex(ValueError, 'DRAIN_ACTIVITY_DETECTED'):
                readmit.record_round(state, rows, 'before-fence', {})
        observe.assert_called_once_with(rows[0], None)
        self.assertEqual(written[-1]['samples'][0]['databases'], {'a': busy})
        self.assertNotIn('completed', written[-1]['samples'][0])

    def test_active_client_classification_is_bound_to_same_sql_snapshot(self):
        row = {'containerId': 'platform', 'service': 'platform-pg'}
        with patch.object(drain, 'query', return_value=['{"clients":[{"category":"OTHER","count":1}]}']) as q:
            observed = drain.observed_database(row, 123)
        self.assertEqual(observed['nonIdleClients'], 1)
        statement = q.call_args.args[1]
        for name in (*drain.COUNT_NAMES, 'pid<>123', 'pg_stat_activity'):
            self.assertIn(name, statement)
        with self.assertRaisesRegex(ValueError, 'DRAIN_ACTIVITY_DETECTED'):
            drain.demand_zero(observed)

    def test_foreign_or_incomplete_fence_fails_owner_verification(self):
        with patch.object(drain, 'query', return_value=['connections."MappingJobs"']):
            with self.assertRaisesRegex(ValueError, 'PG_FENCE_OWNER_OR_COVERAGE_CHANGED'):
                drain.verify_fence_owner({}, ['connections."MappingJobs"', 'connections."MappingOutboxs"'], 111)


if __name__ == '__main__':
    unittest.main()
