"""Doris 独立预期的定向反例；这些检查不启动或认证 Doris。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from workflow_doris_mapping_query import fixture_instant, fixture_tables, reference_targets
import workflow_doris_s0_cancel as cancellation
import doris_pipeline_observer as pipeline
import doris_query_profile_witness as profile
import doris_query_cancel_witness as witness
from copy import deepcopy
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

    def test_product_qualification_and_frozen_inputs_reach_all_five_gates(self):
        product={'environment','contract','backend','web','interaction'}
        for path in ('scripts/maintenance/workflow_doris_mapping_evidence.py',
                     'docs/evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s3/tls/command.json'):
            with self.subTest(path=path):
                self.assertTrue(product<=set(select_gates([path])['affected']))

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

    def test_pipeline_observer_rejects_missing_or_duplicate_members(self):
        header = '1 pipeline fragment contexts are still running! duration_limit=0\n'
        context = 'No.0 (elapse_second=0s): PipelineFragmentContext Info: _closed_tasks=0, _total_tasks=2\n'
        task = ('Task 0: QueryId: aa-bb\nInstanceId: aa-bc\n'
                'PipelineTask[id = 0, open = false, eos = false, state = BLOCKED, dry run = false, '
                '_wake_up_early = false, _wake_up_by = 0, is running = false]\n')
        self.assertFalse(pipeline.decode((header + context + task).encode())['complete'])
        self.assertFalse(pipeline.decode((header + context + task + task).encode())['complete'])
        second = task.replace('id = 0','id = 1')
        self.assertTrue(pipeline.decode((header + context + task + second).encode())['complete'])
        with self.assertRaisesRegex(ValueError, 'PIPELINE_HEADER'):
            pipeline.decode(b'Query context not found')
        with self.assertRaisesRegex(ValueError, 'PIPELINE_ZERO_HAS_PAYLOAD'):
            pipeline.decode(b'0 pipeline fragment contexts are still running! duration_limit=0\ninvalid')

    def test_profile_count_comparison_preserves_missing_or_ambiguous_evidence(self):
        roots = [
            ['RESULT_SINK_OPERATOR','MATERIALIZATION_OPERATOR','EXCHANGE_OPERATOR'],
            ['DATA_STREAM_SINK_OPERATOR','LOCAL_MERGE_SORT_SOURCE_OPERATOR'],
            ['SORT_SINK_OPERATOR','OLAP_SCAN_OPERATOR']]
        names=['MATERIALIZATION_OPERATOR','LOCAL_MERGE_SORT_SOURCE_OPERATOR','OLAP_SCAN_OPERATOR']
        normal={'tasks':[],'state':'OK','query':'aa-bb'}
        groups=[]
        for fragment, indices in enumerate(([0],[1,2])):
            tasks=[]
            for task_id,index in enumerate(indices):
                normal['tasks'].append(dict(fragment=fragment,pipeline=task_id,task=task_id,
                    planOperators=roots[index],planNodes=[dict(name=n,nodeId=i) for i,n in enumerate(roots[index])],state='FINALIZED',wakeEarly=0,operators={names[index]:{'rows':101}}))
                tasks.append(dict(task=task_id,instance=str(fragment),opened=True,state='BLOCKED',eos=False,wakeEarly=False,dryRun=False,
                                  operators=list(reversed(normal['tasks'][-1]['planNodes']))))
            groups.append(dict(complete=True,total=len(indices),closed=0,tasks=tasks))
        final=deepcopy(normal)
        final.update(state='ERR',query='aa-cc')
        for index,t in enumerate(final['tasks']): t['operators'][names[index]]['rows']=0
        def verdict():
            return [t['observedShortfall'] for t in profile.compare_tasks(final,{'profile':normal,'rowCount':101},{'groups':groups},{1:'0',0:'1'})]
        self.assertEqual(verdict(),[True,True,True])
        final['tasks'][1]['operators'][names[1]]['rows']=101
        self.assertEqual(verdict(),[True,False,True])
        del final['tasks'][2]['operators'][names[2]]['rows']
        self.assertEqual(verdict(),[True,False,False])
        final['query']=normal['query']
        self.assertEqual(verdict(),[])
        final['query']='aa-cc'
        groups[0]['tasks'][0]['dryRun']=True
        self.assertEqual(verdict(),[False,False,False])

    def test_two_anonymous_closes_cannot_identify_two_tasks_in_one_instance(self):
        groups=[{'tasks':[{'instance':'aa-ab','task':0},{'instance':'aa-ab','task':1}]},
                {'tasks':[{'instance':'aa-ac','task':0}]}]
        rows=[]
        for worker,fragment,instance in [(12,0,'aa-ab'),(13,1,'aa-ac'),(14,0,'aa-ab')]:
            for event in ('fragment_cancel','instance_cancel','task_close_error'):
                rows.append(dict(event=event,level='W',timestamp='20261119 05:18:28.559791',tid=worker,
                                 queryField=event!='instance_cancel',userCancel=True,offset=len(rows),
                                 fragment=fragment if event=='fragment_cancel' else None,
                                 instance=instance if event=='instance_cancel' else None))
        for kind,instant in [('register','20261119 05:18:28.500000'),('user_rpc','20261119 05:18:28.510000'),
                             ('context_end','20261119 05:18:28.560000')]:
            rows.append(dict(event=kind,level='I',timestamp=instant,queryField=True,userCancel=kind=='user_rpc',
                             tid=5,offset=len(rows)))
        def verdict():
            return witness.native_task_closes({'events':rows},groups,
                witness.instant_ns(witness.engine_stamp(rows[-2]['timestamp'])),
                witness.instant_ns(witness.engine_stamp(rows[-1]['timestamp'])))
        self.assertEqual(verdict(),({0:'aa-ab',1:'aa-ac'},{(witness.canonical_id('aa-ac'),0)}))
        rows[0]['userCancel']=False
        self.assertEqual(verdict(),({},set()))

    def test_review_fix_02_rejects_inconsistent_e1_execution_evidence(self):
        """在修复后的正式入口核验五个真实场景；替换只对本测试读取的证据副本可见。"""
        import json
        from unittest.mock import patch
        import workflow
        import workflow_doris_mapping_evidence as consumer
        from workflow_execution import sha

        self.assertEqual(consumer.E1_RUN, 'review-fix-02')
        import subprocess
        import tempfile
        import workflow_m2_build as build
        import workflow_m4_query as query
        from contextlib import ExitStack

        # 临时仓库只读共享 Git 对象，检出测试实际消费的历史文件。
        stack = self.enterContext(ExitStack())
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        revision = '698ca0e2e4c5b50659e02637c77473e32bc1a343'
        product = '9780c8f91cd084c1df11c604186d22d7f08f3023'
        def git(*args, cwd=root):
            return subprocess.check_output(['git', *args], cwd=cwd)
        git('cat-file', '-e', product+'^{commit}', cwd=workflow.ROOT)
        objects = git('rev-parse','--path-format=absolute','--git-path','objects',cwd=workflow.ROOT).decode().strip()
        git('init','-q')
        (root/'.git/objects/info/alternates').write_text(objects+'\n')
        inputs = ['backend','apps/web','scripts','docs/contracts/g4-connections.openapi.json',
                  'docs/evidence/G4-DORIS-MAPPING-QUERY-001/review-fix-01',
                  'docs/evidence/G4-DORIS-MAPPING-QUERY-001/review-fix-02',
                  'docs/evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s3/prepare.json',
                  'Directory.Build.props','Directory.Packages.props','global.json','NuGet.Config',
                  'package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version']
        listing = git('ls-tree','-rlz',revision,'--',*inputs)
        total = sum(int(entry.split(b'\t',1)[0].split()[-1]) for entry in listing.split(b'\0') if entry)
        self.assertLess(total, 20*1024**2)
        git('update-ref','HEAD',revision)
        git('read-tree',revision)
        git('checkout',revision,'--',*inputs)
        stack.enter_context(patch.object(build,'ROOT',root))
        stack.enter_context(patch.object(query,'ROOT',root))
        public=root/'docs/evidence/G4-DORIS-MAPPING-QUERY-001'
        history=public/'review-fix-01/current-inputs.json'
        selected=public/consumer.E1_RUN/'selected.json'
        index=json.loads(selected.read_bytes())
        former=json.loads(history.read_bytes())
        cases=index['cases']
        empty_digest='0'*64
        def receipt(label):
            return cases[label]['command']+'-receipt.json'
        def reject(label, manifest_path, members, code, window=False):
            with self.subTest(case=label):
                manifest=json.loads(manifest_path.read_bytes())
                overlays={}
                for name,field,value in members:
                    item=manifest['originals'][name]
                    self.assertEqual(item['encoding'],'raw')
                    path=root/item['path']
                    document=json.loads(path.read_bytes())
                    target=document
                    for key in field[:-1]:
                        target=target[key]
                    target[field[-1]]=value
                    content=json.dumps(document,ensure_ascii=False).encode()+b'\n'
                    item.update(sha256=sha(content),sizeBytes=len(content))
                    overlays[path]=content
                if window:
                    manifest['audit']['windows'][cases['expired']['report']][0]-=1000
                overlays[manifest_path]=json.dumps(manifest).encode()
                original_read=Path.read_bytes
                def fixture_bytes(path):
                    return overlays[path] if path in overlays else original_read(path)
                with patch.object(Path,'read_bytes',fixture_bytes):
                    key=workflow.input_key(root,'interaction')
                    with self.assertRaisesRegex(ValueError,'^'+code+'$'):
                        consumer.qualify_review_fix('interaction',key,history.parent)
                print('RF02 rejected '+label+' '+code,flush=True)

        # 沿真实 git、构建、解封、命令及审计链路，旧原件与本批五次选定原件分开核验。
        valid=consumer.qualify_review_fix('interaction',workflow.input_key(root,'interaction'),history.parent)
        self.assertEqual((valid['status'],valid['runId']),('PASS',consumer.E1_RUN))
        for label in ('expired','short'):
            reject(label+'-fingerprint',selected,[(receipt(label),['inputFingerprint'],empty_digest)],'RF02_FINGERPRINT')
        reject('wrong-argv',selected,[(receipt('catalog'),['commandSummary','sha256'],empty_digest)],'RF02_ARGV')
        reject('healthy-command',selected,[(receipt('healthy'),['inputFingerprint'],empty_digest)],'RF02_FINGERPRINT')
        session=cases['healthy']['events'].removeprefix('service-events-')
        healthy_receipt=json.loads((selected.parent/'originals'/('ready-'+session)).read_bytes())
        reject('healthy-session-command',selected,[(healthy_receipt['sessionCommand']+'-receipt.json',['inputFingerprint'],empty_digest)],'RF02_SESSION_COMMAND')
        reject('driver',selected,[(cases['catalog']['dispatch'],['driverSha256',consumer.BROWSER_SOURCES[0]],empty_digest)],'RF02_DRIVER')
        reject('stage',selected,[(cases['activation']['host'],['stageInputs','expectedStale'],'catalog')],'RF02_STAGE')
        reject('unstable-input',selected,[(cases['short']['report'],['inputsUnchanged'],False)],'RF02_REPORT_INPUT')
        reject('wrong-host',selected,[(cases['healthy']['host'],['commandId'],'0'*32)],'RF02_HOST')
        reject('wrong-build-on-both',selected,[(cases['healthy']['host'],['snapshotId'],empty_digest),
                                             (cases['healthy']['report'],['inputBinding','api','snapshotId'],empty_digest)],'RF02_HOST')
        reject('audit-window',selected,[],'RF02_AUDIT_WINDOW',window=True)
        for label,cid in [('legacy-expired','8a864f478fd5458e8117ba3299431be5'),('legacy-short','82a33f60da0048698f44a4bcb7750e67')]:
            self.assertIn(cid,former['readinessCommands'].values())
            reject(label,history,[(cid+'-receipt.json',['inputFingerprint'],empty_digest)],'RF02_HISTORICAL_ORIGINAL')
        reject('e2-control',history,[('628055b05b084b2393307ecc8b5029c9-receipt.json',['inputFingerprint'],empty_digest)],'RF_E2_EXECUTION')
        changed = 'backend/src/Contracts/OntologyPlatform.Contracts/G4MappingRules.cs'
        new_bytes = git('show','c44c6294e31ee990b068d2e95bfce9a7476be397:'+changed,cwd=workflow.ROOT)
        self.assertNotEqual((root/changed).read_bytes(), new_bytes)
        (root/changed).write_bytes(new_bytes)
        git('add','--',changed)
        tree = git('write-tree').decode().strip()
        candidate = git('-c','user.name=Fixture','-c','user.email=fixture@localhost',
                        'commit-tree',tree,'-p',revision,'-m','Change bound backend input').decode().strip()
        git('update-ref','HEAD',candidate,revision)
        with self.assertRaisesRegex(ValueError,'^RF_PRODUCT_REVISION$'):
            consumer.qualify_review_fix('interaction',workflow.input_key(root,'interaction'),history.parent)


    def test_last_microsecond_is_preserved(self):
        self.assertEqual(fixture_instant('2026-11-17 12:00:00.123459'), '2026-11-17T12:00:00.123459Z')
        for invalid in ('2026-11-17 12:00:00.12345', '2026-11-17 12:00:00.1234590'):
            with self.assertRaises(ValueError):
                fixture_instant(invalid)


if __name__ == '__main__':
    unittest.main()
