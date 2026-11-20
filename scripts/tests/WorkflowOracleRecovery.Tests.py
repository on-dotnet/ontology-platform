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


class FusekiLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.area=Path(temporary.name).resolve()
        self.change(patch.object(recovery,'RECOVERY_AREA',self.area))
        registry=components.frozen('replacement-resources.json')
        (self.area/'replacement-resources.json').write_text(json.dumps(registry))
        self.cid=registry['ids']['fuseki']
        self.old=components.frozen('stop-b0da0df44bd6482eb366d29140d3f227.json')
        self.state={**self.old['after'],'Error':''}
        self.files=self.old['tdbCloseFiles']
        self.log=b''
        self.change(patch.object(platform,'product_run',return_value='product-resume-01'))
        self.eng=self.change(patch.object(recovery,'engine_step',side_effect=self.engine))
        self.change(patch.object(recovery,'one_helper',side_effect=lambda *a,**kw:'\n'.join(self.files)))
        self.change(patch('workflow_oracle_mapping_resources.before_source',return_value={'attempt':'before'}))
        self.change(patch.object(platform,'before_source',return_value={'attempt':'post'}))

    def change(self,patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def engine(self,stage,*args,**options):
        if stage=='tdb-active-locks':return '\n'.join(self.old['tdbLocksBefore'])
        if stage in ('stopped-state','tdb-stopped-state'):return json.dumps(self.state)
        if stage=='native-state':return 'running'
        if stage in ('term','start-fuseki','tdb-read-ready'):return ''
        self.fail(stage)

    def stop(self):
        from subprocess import CompletedProcess
        with patch('subprocess.run',return_value=CompletedProcess([],0,self.log,b'')):
            return recovery.native_stop('replacement','fuseki',{'fuseki'},'entry-fix-regression')

    def test_term_and_retained_locks_do_not_claim_clean_or_recovery(self):
        self.assertEqual(self.old['status'],'BLOCKED')
        row=self.stop()
        self.assertEqual((row['status'],row['allTdbLocksRemoved'],row['processExited']),
                         ('PROCESS_EXITED',False,True))
        self.assertEqual((row['cleanShutdown'],row['checkpointRecovery'],row['productUse']),
                         ('UNKNOWN','NOT_VERIFIED','NOT_VERIFIED'))
        self.assertEqual(recovery.fuseki_termination(self.old),row['observedJournals'])
        self.assertIn(('term','stop','--signal=TERM','--timeout=-1',self.cid),
                      [call.args for call in self.eng.call_args_list])
        self.files=['Data-0001/journal.jrnl|0']
        self.assertEqual(self.stop()['cleanShutdown'],'UNKNOWN')

    def test_nonempty_journal_activity_log_or_bad_exit_still_block(self):
        self.files+=['Data-0002/journal.jrnl|5']
        with self.assertRaisesRegex(ValueError,'TDB_JOURNAL_UNCONFIRMED'):self.stop()
        self.files=['tdb.lock|2']
        with self.assertRaisesRegex(ValueError,'TDB_JOURNAL_UNCONFIRMED'):self.stop()
        self.files=['Data-0001/journal.jrnl|0']
        self.log=b"TransactionException: Can't expel: Active transactions for location"
        with self.assertRaisesRegex(ValueError,'TDB_TRANSACTION_OR_CLOSE_ERROR'):self.stop()
        self.log=b'fatal exception'
        with self.assertRaisesRegex(ValueError,'NATIVE_LOG_ERROR'):self.stop()
        self.log=b''
        for key,value in (('ExitCode',137),('OOMKilled',True),('Error','engine error')):
            with self.subTest(key=key),patch.dict(self.state,{key:value}):
                with self.assertRaisesRegex(ValueError,'NATIVE_EXIT'):self.stop()

    def test_actual_product_start_requires_exact_termination_and_checkpoint(self):
        with self.assertRaisesRegex(ValueError,'TDB_REUSE_STOP_GENERATION'):
            recovery.start_owned('replacement','fuseki',set())
        (self.area/'stop-history.json').write_text(json.dumps(self.old))
        with patch.dict(self.state,{'FinishedAt':'a different engine generation'}):
            with self.assertRaisesRegex(ValueError,'TDB_REUSE_STOP_GENERATION'):
                recovery.start_owned('replacement','fuseki',set())
        registry=self.area/'replacement-resources.json'
        row=json.loads(registry.read_bytes())
        row['volumes']['fuseki']+='-other'
        registry.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,'TDB_CHECKPOINT_OWNER'):
            recovery.start_owned('replacement','fuseki',set())
        with self.assertRaisesRegex(ValueError,'TDB_PRODUCT_GROUP'):
            recovery.start_owned('original','fuseki',set())
        self.assertNotIn('start-fuseki',[c.args[0] for c in self.eng.call_args_list])

    def test_current_graph_read_separates_frozen_and_live_qualification(self):
        import doris_keep_fuseki as rdf
        (self.area/'stop-history.json').write_text(json.dumps(self.old))
        frozen=components.frozen('graphs-second-open.json')
        with patch.object(rdf,'full_scan',return_value={}) as scan:
            with self.assertRaisesRegex(ValueError,'TDB_CURRENT_SCAN'):
                recovery.start_owned('replacement','fuseki',set())
            scan.assert_called_once_with(self.cid)
        receipt=json.loads(next(self.area.glob('start-*.json')).read_bytes())
        self.assertEqual((receipt['status'],receipt['productUse']),('RUNNING','BLOCKED'))
        self.assertEqual(receipt['checkpoint']['cleanShutdown'],'UNKNOWN')
        with patch.object(rdf,'full_scan',return_value=frozen['scan']),patch.object(rdf,'triples',return_value=set()):
            with self.assertRaisesRegex(ValueError,'TDB_CURRENT_RELEASE_GRAPHS'):
                recovery.start_owned('replacement','fuseki',set())
        sets=[set(map(str,range(g['triples']))) for g in frozen['graphs']]
        with patch.object(rdf,'full_scan',return_value=frozen['scan']),patch.object(rdf,'triples',side_effect=sets) as reads, \
             patch.object(rdf,'fingerprint',side_effect=[g['sha256'] for g in frozen['graphs']]):
            ready=recovery.start_owned('replacement','fuseki',set())
        self.assertEqual([c.args for c in reads.call_args_list],[(self.cid,'ontology',g['graph']) for g in frozen['graphs']])
        self.assertEqual(ready['currentGraphs']['graphs'],frozen['graphs'])
        self.assertEqual(ready['productUse'],'CURRENT_GRAPHS_VERIFIED')
        self.assertEqual(ready['checkpoint']['checkpointRecovery'],'ACCEPTED_FOR_FROZEN_CHECKPOINT')


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
