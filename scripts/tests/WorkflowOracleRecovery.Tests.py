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
        self.change(patch('workflow_oracle_mapping_capacity.before_product_source',return_value={'attempt':'product'}))

    def change(self,patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def engine(self,stage,*args,**options):
        if stage in ('tdb-generation','tdb-generation-after'):
            return 'running|2026-11-20T08:00:00Z|'+str(self.pid)
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
        self.pid=100
        (self.area/'stop-history.json').write_text(json.dumps(self.old))
        frozen=components.frozen('graphs-second-open.json')
        with patch.object(rdf,'full_scan',return_value={}) as scan:
            with self.assertRaisesRegex(ValueError,'TDB_CURRENT_SCAN'):
                recovery.start_owned('replacement','fuseki',set())
            scan.assert_called_once_with(self.cid)
        receipt=json.loads(next(self.area.glob('start-*.json')).read_bytes())
        self.assertEqual((receipt['status'],receipt['productUse']),('RUNNING','BLOCKED'))
        with self.assertRaisesRegex(ValueError,'TDB_PRODUCT_CURRENT_GRAPHS'):
            recovery.require_current_fuseki(self.cid,receipt['startedAt'],self.pid)
        self.assertEqual(receipt['checkpoint']['cleanShutdown'],'UNKNOWN')
        with patch.object(rdf,'full_scan',return_value=frozen['scan']),patch.object(rdf,'triples',return_value=set()):
            with self.assertRaisesRegex(ValueError,'TDB_CURRENT_RELEASE_GRAPHS'):
                recovery.start_owned('replacement','fuseki',set())
        sets=[set(map(str,range(g['triples']))) for g in frozen['graphs']]
        self.pid+=1
        with patch.object(rdf,'full_scan',return_value=frozen['scan']),patch.object(rdf,'triples',side_effect=sets) as reads, \
             patch.object(rdf,'fingerprint',side_effect=[g['sha256'] for g in frozen['graphs']]):
            ready=recovery.start_owned('replacement','fuseki',set())
        self.assertEqual([c.args for c in reads.call_args_list],[(self.cid,'ontology',g['graph']) for g in frozen['graphs']])
        self.assertEqual(ready['currentGraphs']['graphs'],frozen['graphs'])
        self.assertEqual(ready['productUse'],'CURRENT_GRAPHS_VERIFIED')
        self.assertEqual(recovery.require_current_fuseki(self.cid,ready['startedAt'],self.pid),ready['attempt'])
        with self.assertRaisesRegex(ValueError,'TDB_PRODUCT_GENERATION'):
            recovery.require_current_fuseki(self.cid,ready['startedAt'],self.pid+1)
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

class ArchiveDeviceRequalificationTests(unittest.TestCase):
    """当前设备号旁证必须经过真实备份抵扣消费者且保留旧账本。"""
    def setUp(self):
        import datetime as dt
        import os
        import workflow_execution as ex
        import workflow_oracle_archive_requalification as q
        self.q=q;self.ex=ex;self.dt=dt
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.area=self.root/'artifacts/workflow'/platform.TASK/platform.RUN;self.area.mkdir(parents=True)
        self.private=self.root/'.tools/security/g4-oracle-mapping-query-001'/platform.RUN/'s0-recovery-01'
        entries={}
        for name in q.NAMES:
            p=self.private/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_bytes(b'synthetic archive boundary fixture\n');p.chmod(0o600)
            st=p.stat();old=q.identity(st);old[0]+=1
            role='oracle' if name.startswith('source/') else Path(name).stem
            entries[name]=dict(privatePath=name,sourceId=recovery.ORIGINAL_IDS[role],volume='synthetic-'+role,
                identity=old,bytes=st.st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        self.ledger=self.area.parent/'s0-recovery-01/archive-ledger.json';self.ledger.parent.mkdir()
        self.ledger.write_text(json.dumps(dict(taskId=platform.TASK,operation='s0-recovery-01',archives=entries)))
        self.original=self.ledger.read_bytes();self.changed(patch.object(q,'LEDGER_SHA',ex.sha(self.original)))
        helper=self.root/q.HELPER;helper.parent.mkdir(parents=True);helper.write_bytes(Path(q.__file__).read_bytes())
        self.product=self.area.parent/q.PRODUCT;self.product.mkdir();self.cid='1'*32

    def changed(self,p):
        self.addCleanup(p.stop);return p.start()

    def proof(self,observation=None):
        q=self.q;ex=self.ex;observation=observation or q.observe(self.root)
        raw=json.dumps(observation,sort_keys=True).encode()+b'\n';directory=self.area.parent/'commands'/q.PRODUCT/self.cid;directory.mkdir(parents=True,exist_ok=True)
        argv,key=q.invocation(self.root)
        receipt=dict(schemaVersion=2,taskId=platform.TASK,runId=q.PRODUCT,commandId=self.cid,stage='archive-device-requalification',parentId=None,
            environmentFingerprint='e'*64,identity=ex.sha(ex.encoded([key,'e'*64,ex.sha(ex.encoded(argv)),str(self.root),120,ex.sha(Path(ex.__file__).read_bytes())])),
            cwd=str(self.root),inputFingerprint=key,commandSummary=dict(executable='python3',argumentCount=len(argv)-1,sha256=ex.sha(ex.encoded(argv))),
            started=True,exitCode=0,classification='SUCCESS',signal=None,deadlineSeconds=120,elapsedSeconds=2,
            startedAtUtc=(self.dt.datetime.fromisoformat(observation['startedAtUtc'])-self.dt.timedelta(seconds=1)).isoformat(),
            endedAtUtc=(self.dt.datetime.fromisoformat(observation['endedAtUtc'])+self.dt.timedelta(seconds=1)).isoformat())
        for name,data in [('stdout',raw),('stderr',b'')]:
            p=directory/(name+'.txt');p.write_bytes(data);receipt[name]=dict(path=str(p),sha256=ex.sha(data),sizeBytes=len(data))
        self.receipt=directory/'receipt.json';self.receipt.write_text(json.dumps(receipt))
        self.sidecar=self.product/('archive-device-requalification-'+self.cid+'.json')
        self.sidecar.write_text(json.dumps(dict(schemaVersion=1,commandId=self.cid,observationSha256=ex.sha(raw),observation=observation)))
        return receipt

    def test_device_only_hash_match_credits_real_blocks_and_preserves_ledger(self):
        self.proof();actual=platform.backup_allocation(self.root,self.area,'platform',phase=self.q.PRODUCT)
        expected=sum((self.private/n).stat().st_blocks*512 for n in self.q.NAMES if n.startswith('platform/'))
        self.assertEqual(actual,expected);self.assertEqual(self.ledger.read_bytes(),self.original)

    def test_nonproduct_phase_and_missing_proof_are_refused(self):
        with self.assertRaisesRegex(ValueError,'ARCHIVE_LEDGER_OWNER'):
            platform.backup_allocation(self.root,self.area,'platform',phase='restore')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_MISSING'):
            platform.backup_allocation(self.root,self.area,'platform',phase=self.q.PRODUCT)

    def test_changed_ledger_hash_is_refused(self):
        self.proof();self.ledger.write_bytes(self.original+b' ')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_LEDGER'):self.q.qualified(self.root)

    def test_wrong_source_and_relative_path_are_refused(self):
        for field,value in [('sourceId',recovery.ORIGINAL_IDS['rustfs']),('privatePath','platform/other.tar')]:
            data=json.loads(self.original);data['archives']['platform/fuseki.tar'][field]=value;raw=json.dumps(data).encode();self.ledger.write_bytes(raw)
            with patch.object(self.q,'LEDGER_SHA',self.ex.sha(raw)),self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_IDENTITY'):
                self.q.observe(self.root)

    def test_incomplete_or_foreign_observation_is_refused(self):
        data=self.q.observe(self.root);del data['archives']['source/database.tar'];self.proof(data)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_OBSERVATION'):self.q.qualified(self.root)
        data=self.q.observe(self.root);data['runId']='foreign';self.proof(data)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_OBSERVATION'):self.q.qualified(self.root)

    def test_current_file_or_mode_change_is_refused(self):
        self.proof();p=self.private/'platform/fuseki.tar';p.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_FILE'):self.q.qualified(self.root)
        p.chmod(0o600);p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_IDENTITY'):self.q.qualified(self.root)

    def test_symlink_is_refused(self):
        p=self.private/'platform/fuseki.tar';p.unlink();p.symlink_to(self.private/'platform/rustfs.tar')
        with self.assertRaisesRegex(ValueError,'LINKED_PATH'):self.q.observe(self.root)

    def test_hash_mismatch_is_refused_without_sidecar(self):
        with patch.object(self.q,'stream_digest',return_value='0'*64),self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_HASH'):
            self.q.observe(self.root)
        self.assertEqual(list(self.product.glob('archive-device-requalification-*')),[])

    def test_descriptor_change_during_read_is_refused(self):
        from types import SimpleNamespace
        p=self.private/'platform/fuseki.tar';info=p.stat();changed=SimpleNamespace(**{k:getattr(info,k) for k in ['st_dev','st_ino','st_size','st_ctime_ns','st_mode','st_nlink','st_uid']});changed.st_ctime_ns+=1
        with patch.object(self.q.os,'fstat',side_effect=[info,changed]),self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_DURING'):
            self.q.stream_digest(p,self.q.identity(info))

    def test_command_and_stream_replacement_are_refused(self):
        receipt=self.proof();receipt['commandSummary']['sha256']='0'*64;self.receipt.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_COMMAND'):self.q.qualified(self.root)
        receipt=self.proof();Path(receipt['stdout']['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_STREAM'):self.q.qualified(self.root)

    def test_late_window_and_failed_command_are_refused(self):
        receipt=self.proof();receipt['endedAtUtc']=receipt['startedAtUtc'];self.receipt.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_WINDOW'):self.q.qualified(self.root)
        receipt=self.proof();receipt['exitCode']=1;self.receipt.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_COMMAND'):self.q.qualified(self.root)

    def test_invalid_proof_never_triggers_another_hash_command(self):
        data=self.q.observe(self.root);del data['archives']['source/database.tar'];self.proof(data)
        with patch.object(self.q.ex,'run',side_effect=AssertionError('must not retry')):
            with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_OBSERVATION'):self.q.requalify(self.root)

    def test_missing_schema_environment_and_naive_time_are_refused(self):
        for key in ['schemaVersion','environmentFingerprint','identity']:
            receipt=self.proof();del receipt[key];self.receipt.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_COMMAND'):self.q.qualified(self.root)
        data=self.q.observe(self.root)
        data['startedAtUtc']=self.dt.datetime.fromisoformat(data['startedAtUtc']).replace(tzinfo=None).isoformat()
        data['endedAtUtc']=self.dt.datetime.fromisoformat(data['endedAtUtc']).replace(tzinfo=None).isoformat()
        self.proof(data)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUAL_WINDOW'):self.q.qualified(self.root)

    def test_real_child_command_produces_consumable_append_only_proof(self):
        import os
        helper=self.root/self.q.HELPER
        text=helper.read_text()
        text=text.replace("LEDGER_SHA = '270fca4d7f40f2fb1c1fee1ccf5e40bb00ac0509445e07d26f86287573315617'", "LEDGER_SHA = '"+self.q.LEDGER_SHA+"'")
        helper.write_text(text)
        with patch.dict(os.environ,{'PYTHONPATH':str(Path(platform.__file__).parent)}):
            proof=self.q.requalify(self.root)
        self.assertRegex(proof['commandId'],'^[a-f0-9]{32}$')
        self.assertEqual(len(proof['archives']),6)
        self.assertGreater(platform.backup_allocation(self.root,self.area,'source',phase=self.q.PRODUCT),0)
        self.assertEqual(self.ledger.read_bytes(),self.original)
        self.assertEqual(len(list(self.product.glob('archive-device-requalification-*'))),1)

    def test_requalification_reuses_valid_proof_without_rehash_or_rewrite(self):
        self.proof();before=self.sidecar.read_bytes()
        with patch.object(self.q.ex,'run',side_effect=AssertionError('unnecessary command')):
            self.assertEqual(self.q.requalify(self.root)['commandId'],self.cid)
        self.assertEqual(self.sidecar.read_bytes(),before);self.assertEqual(self.ledger.read_bytes(),self.original)


if __name__=='__main__':
    unittest.main()
