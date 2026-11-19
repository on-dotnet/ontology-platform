"""按真实 disk_admission 的分类核对冷备由预留转为落盘，以及缺失和越界。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maintenance'))
import workflow_oracle_mapping_platform as platform
import workflow_oracle_mapping_platform_recovery as recovery


class OracleDiskAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.area=self.root/'artifacts/workflow'/platform.TASK/platform.RUN
        self.area.mkdir(parents=True)
        self.measure=self.root/'measurement'
        self.measure.mkdir()
        self.change(patch.object(platform,'MEASURE_TREE',self.measure))
        originals=platform.ROOT/'docs/evidence'/platform.TASK/platform.RUN/'s0/originals'
        for name in ('platform-image-layer-closure-01.json','recovery-01.json','recovery-01-final.json','formal-platform-size-basis.json','source-create-01.json'):
            (self.area/name).write_bytes((originals/name).read_bytes())
        source=json.loads((self.area/'source-create-01.json').read_bytes())['volume']
        self.usage={'volumesLogicalBytes':{source:4*platform.GIB,'alternative':4*platform.GIB},'platformVolumes':dict.fromkeys(platform.VOLUMES,1024),
                    'replacementVolumes':{},'containerWritableBytes':{'owner':1024}}
        self.change(patch.object(platform,'current_storage',return_value=self.usage))
        self.host=5*platform.GIB
        (self.area/'formal-planned.json').write_text(json.dumps({'resourceAttempt':'basis'}))
        (self.area/'source-admission-basis.json').write_text(json.dumps({'platformDisk':{'allocations':{'currentHostIncludingFirstBackup':self.host}}}))
        self.missing=False
        self.folder=self.root/'.tools/security/g4-oracle-mapping-query-001'/platform.RUN/recovery.RECOVERY/'platform'
        self.folder.mkdir(mode=0o700,parents=True)
        self.ledger=self.area.parent/recovery.RECOVERY/'archive-ledger.json'
        self.ledger.parent.mkdir()

    def change(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def command(self,stage,argv):
        if argv[0]=='git':
            return 'worktree '+str(self.root)+'\nbranch refs/heads/codex/other'
        return str(self.host//1024)+'\t'+str(self.root)+(('\n0\t'+str(self.measure)) if not self.missing else '')

    def budget(self):
        return platform.disk_admission(self.root,self.area,self.command,phase='preserve')

    def disk_copy(self,owner):
        path=self.folder/'fuseki.tar'
        path.write_bytes(b'x'*65536)
        path.chmod(0o600)
        st=path.stat()
        self.host+=st.st_blocks*512
        self.ledger.write_text(json.dumps(dict(taskId=platform.TASK,operation=recovery.RECOVERY,archives={'platform/fuseki.tar':dict(
            sourceId=owner,privatePath='platform/fuseki.tar',identity=[st.st_dev,st.st_ino,st.st_size,st.st_ctime_ns],
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())})))
        return st.st_blocks*512

    def test_reserved_copy_becomes_actual_once(self):
        before=self.budget()
        amount=self.disk_copy(recovery.ORIGINAL_IDS['fuseki'])
        after=self.budget()
        self.assertEqual(before['totalBytes'],after['totalBytes'])
        self.assertEqual(before['allocations']['platformCheckpointRemaining']-after['allocations']['platformCheckpointRemaining'],amount)

    def test_normal_growth_is_charged(self):
        before=self.budget()
        self.usage['containerWritableBytes']['owner']+=12345
        self.assertEqual(self.budget()['totalBytes']-before['totalBytes'],12345)

    def test_allocation_over_cap_is_refused(self):
        self.host+=40*platform.GIB
        with self.assertRaisesRegex(ValueError,'FORMAL_TOTAL_DISK'):
            self.budget()

    def test_missing_host_and_source_measurements_are_refused(self):
        self.missing=True
        with self.assertRaisesRegex(ValueError,'HOST_MEASUREMENT_SET'):
            self.budget()
        self.missing=False
        del self.usage['volumesLogicalBytes']['alternative']
        with self.assertRaisesRegex(ValueError,'OBSERVED_SOURCE_SIZE'):
            self.budget()

    def test_copy_from_wrong_owner_is_refused(self):
        self.disk_copy(recovery.ORIGINAL_IDS['rustfs'])
        with self.assertRaisesRegex(ValueError,'ARCHIVE_LEDGER_OWNER'):
            self.budget()


if __name__=='__main__':
    unittest.main()
