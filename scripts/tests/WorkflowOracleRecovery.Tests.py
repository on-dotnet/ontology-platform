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
import workflow_oracle_mapping_recovery_components as components
import workflow_oracle_mapping_identity_recovery as identity
import workflow_oracle_mapping_object_recovery as objects
import workflow_evidence as evidence


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


class RecoveryComponentTests(unittest.TestCase):
    def test_object_version_and_delete_marker_protocol(self):
        controls=objects.offline_cases()
        self.assertEqual(controls['positive']['inventoryEntries'],7)
        self.assertEqual(controls['positive']['deleteMarkers'],1)
        self.assertEqual(len(controls['rejected']),11)

    def test_fresh_platform_identity_controls(self):
        controls=identity.offline_tests()
        self.assertTrue({'healthy','expired','wrong_subject','wrong_issuer','wrong_client','wrong_alg',
                         'wrong_signature','wrong_role','missing_subject','only_jwks','unbound_callback'}<=set(controls))

    def test_prior_qualification_reopens_frozen_graph_bytes(self):
        prior=components.prior_qualifications()
        self.assertEqual(prior['shutdownHook'],'UNKNOWN')
        self.assertEqual(prior['oracleRows'],[1,1])

    def test_aggregate_rejects_reregistered_task_identity(self):
        selection=dict(taskId=components.TASK,runId=components.BATCH,base='0'*40)
        with patch.object(components,'record_bytes',return_value=json.dumps(selection).encode()):
            with self.assertRaisesRegex(ValueError,'AGGREGATE_ID'):components.aggregate()

    def test_aggregate_rejects_reregistered_reference_archive(self):
        attempt='2'*32
        selection=dict(taskId=components.TASK,runId=components.BATCH,base=components.BASE,
                       actual=attempt,reference=attempt,identity=attempt)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            docs=root/'docs/evidence';docs.mkdir(parents=True)
            forged=dict(taskId=components.TASK,runId=components.BATCH,attempt=attempt,
                        volume=components.REFERENCE,archiveSha256='0'*64)
            raw=json.dumps(forged).encode()
            target=docs/'reference-created.json';target.write_bytes(raw)
            record=dict(path='docs/evidence/reference-created.json',sizeBytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),encoding='raw')
            def rows(name):
                if name=='selected-attempts.json':return json.dumps(selection).encode()
                if name=='reference-created.json':return evidence.restore(root,record)
                if name.startswith('reference-plan-'):return json.dumps(dict(
                    taskId=components.TASK,runId=components.BATCH,archiveScope={},name=components.REFERENCE,
                    archiveSha256=components.RUST_HASH)).encode()
                return b'{}'
            actual=components.qualified_object
            def qualified(which,stamp):
                return (None,None) if which=='actual' else actual(which,stamp)
            with patch.object(components,'record_bytes',side_effect=rows),patch.object(components,'qualified_object',side_effect=qualified):
                observation=components.aggregate()
            self.assertEqual(observation['components']['rustfs'],dict(status='BLOCKED',reason='ORACLE_ADMISSION_SEALED_REFERENCE'))
            self.assertEqual(observation['status'],'BLOCKED')


if __name__=='__main__':
    unittest.main()
