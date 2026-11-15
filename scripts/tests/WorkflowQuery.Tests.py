#!/usr/bin/env python3
"""查询任务只接受批准闭包与真实准入，不借历史TaskId宣称成功。"""
import sys
import json
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
import workflow_environment as environment
import workflow_web_cache as web
import workflow
import workflow_m4_query as query

TASK = 'G4-M4-QUERY-001'


class QueryAdmissionTests(unittest.TestCase):
    def test_aba_qualification_requires_actual_case_not_just_maf_pass(self):
        row = dict(taskId=TASK, case='AC-05_INFLIGHT_ABA', status='PASS', abaCompleted=True,
                   queryId='query-'+'a'*32, errorStatus=409, errorCode='query_binding_stale', executionStatus='FAILED',
                   resultHash=None, ciphertextBytes=0, resultSize=0, committedReadReceipts=0, successfulQueryAudits=0,
                   elapsedMs=1500, capturedA=dict(mappingReleaseId='release-'+'a'*32, activationId='activation-'+'a'*32, activationRevision='1'),
                   activatedB=dict(mappingReleaseId='release-'+'b'*32, activationId='activation-'+'b'*32, activationRevision=2),
                   activatedA=dict(mappingReleaseId='release-'+'a'*32, activationId='activation-'+'c'*32, activationRevision=3))
        # 明确标记合成资格器夹具，时间/顺序不是产品运行证据。
        row.update(resourceRun=query.RUN, mappingId='mapping-'+'d'*32,
                   admittedAtUtc='2026-11-15T00:00:00Z', deadlineAtUtc='2026-11-15T00:00:05Z')
        for part in ['capturedA', 'activatedB', 'activatedA']:
            row[part]['mappingId'] = row['mappingId']
        row['activatedB']['previousReleaseId'] = row['capturedA']['mappingReleaseId']
        row['activatedA']['previousReleaseId'] = row['activatedB']['mappingReleaseId']
        row['events'] = [dict(phase=phase, sequence=i+1, monotonicMs=100*(i+1),
                              utc=f'2026-11-15T00:00:00.{i+1}00Z', queryId=row['queryId'], mappingId=row['mappingId'])
                         for i, phase in enumerate(['SOURCE_READ_COMPLETED', 'B_ACTIVATED', 'A_ACTIVATED', 'COMMIT_REJECTED'])]
        query.demand_aba_original(json.dumps(row).encode(), 'query-real-aba-inflight-runtime')
        import copy
        mutations = [lambda r: r.pop('events'), lambda r: r.update(deadlineAtUtc='2026-11-15T00:00:06Z'),
            lambda r: r['activatedB'].update(mappingId='foreign'), lambda r: r['activatedA'].update(previousReleaseId='foreign'),
            lambda r: r['events'][2].update(queryId='query-'+'f'*32), lambda r: r['events'][1].update(mappingId='foreign'),
            lambda r: r['events'][1].update(utc='2026-11-15T00:00:06Z'), lambda r: r['events'][2].update(monotonicMs=50),
            lambda r: r['events'].reverse(), lambda r: r['events'].pop(), lambda r: r['events'][1].update(sequence=1),
            lambda r: r['activatedA'].update(activationRevision=2)]
        for mutation in mutations:
            changed = copy.deepcopy(row); mutation(changed)
            with self.subTest(causal=changed), self.assertRaises(ValueError):
                query.demand_aba_original(json.dumps(changed).encode(), 'query-real-aba-inflight-runtime')

        for key in ['executionStatus', 'queryId', 'resultHash', 'capturedA', 'activatedB', 'activatedA']:
            incomplete = {name:value for name,value in row.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                query.demand_aba_original(json.dumps(incomplete).encode(), 'query-real-aba-inflight-runtime')
        for part in ['capturedA','activatedB','activatedA']:
            for key in ['mappingReleaseId','activationId','activationRevision']:
                incomplete = dict(row, **{part:{name:value for name,value in row[part].items() if name != key}})
                with self.subTest(part=part, missing=key), self.assertRaises(ValueError):
                    query.demand_aba_original(json.dumps(incomplete).encode(), 'query-real-aba-inflight-runtime')
        with self.assertRaisesRegex(ValueError, 'QUERY_ABA_STAGE_INVALID'):
            query.demand_aba_original(json.dumps(row).encode(), 'query-real-maf-runtime')
        with self.assertRaisesRegex(ValueError, 'QUERY_ABA_ORIGINAL_REQUIRED'):
            query.demand_aba_original(b'Test run summary: Passed! Total: 1', 'query-real-aba-inflight-runtime')
        for key, value in [('status', 'FAIL'), ('abaCompleted', False), ('errorCode', 'mapping_conflict'),
                           ('errorStatus', 503), ('elapsedMs', 5001), ('successfulQueryAudits', 1),
                           ('committedReadReceipts', 1), ('ciphertextBytes', 10), ('resultHash', 'hash'),
                           ('executionStatus', 'COMPLETED'), ('executionStatus', 'UNKNOWN'), ('activatedA', row['capturedA'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                query.demand_aba_original(json.dumps(dict(row, **{key:value})).encode(), 'query-real-aba-inflight-runtime')
        with self.assertRaisesRegex(ValueError, 'QUERY_ABA_ORIGINAL_REQUIRED'):
            query.demand_aba_original((json.dumps(row)+'\n'+json.dumps(row)).encode(), 'query-real-aba-inflight-runtime')

    def test_aba_causal_fields_cannot_be_omitted(self):
        # 旧报告有身份与零残留但无因果顺序，不能通过新资格。
        row = dict(taskId=TASK, case='AC-05_INFLIGHT_ABA', status='PASS', abaCompleted=True,
                   queryId='query-'+'a'*32, errorStatus=409, errorCode='query_binding_stale', executionStatus='FAILED',
                   resultHash=None, ciphertextBytes=0, resultSize=0, committedReadReceipts=0, successfulQueryAudits=0,
                   elapsedMs=1500, capturedA=dict(mappingReleaseId='release-'+'a'*32, activationId='activation-'+'a'*32, activationRevision='1'),
                   activatedB=dict(mappingReleaseId='release-'+'b'*32, activationId='activation-'+'b'*32, activationRevision=2),
                   activatedA=dict(mappingReleaseId='release-'+'a'*32, activationId='activation-'+'c'*32, activationRevision=3))
        with self.assertRaises(ValueError):
            query.demand_aba_original(json.dumps(row).encode(), 'query-real-aba-inflight-runtime')

    def test_runtime_snapshot_is_complete_immutable_and_mount_bound(self):
        from workflow_m4_query_runtime import freeze, verify, demand_mount
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'bin'; source.mkdir()
            for name in ['Api.dll', 'Api.deps.json', 'Api.runtimeconfig.json']:
                (source/name).write_text(name)
            (source/'nested').mkdir(); (source/'nested/content.json').write_text('original')
            frozen = freeze(root, source, root/'snapshots', {'source.cs':'hash'}, 'build-command')
            (source/'nested/content.json').write_text('test-build-overwrite')
            verify(root, frozen)
            mount = dict(Destination='/app', Source=str(root/frozen['directory']), RW=False)
            demand_mount(root, frozen, [mount])
            with patch('platform.system',return_value='Darwin'): demand_mount(root, frozen, [dict(mount,Source='/host_mnt'+mount['Source'])])
            with self.assertRaises(ValueError): demand_mount(root, frozen, [mount,dict(mount,Destination='/app/Api.dll')])
            with self.assertRaises(ValueError): demand_mount(root, frozen, [dict(mount, RW=True)])
            with self.assertRaises(ValueError): demand_mount(root, frozen, [dict(mount, Source=str(source))])
            (root/frozen['directory']/'nested/content.json').chmod(0o644)
            (root/frozen['directory']/'nested/content.json').write_text('drift')
            with self.assertRaises(ValueError): verify(root, frozen)

    def test_layered_inputs_fail_closed_without_replaying_archive_changes(self):
        from workflow_m4_query_inputs import qualification_change, select
        for path, expected in [('docs/evidence/G4-M4-QUERY-001/display.md','ARCHIVE'),
                ('scripts/maintenance/workflow_m4_query_evidence.py','REPARSE'),
                ('backend/src/Modules/SemanticQuery/Key.cs','EXECUTE'),
                ('scripts/maintenance/workflow-m4-query.mjs','EXECUTE'),
                ('backend/tests/OntologyPlatform.QueryTests/G4QueryTests.cs','EXECUTE'),
                ('docs/contracts/g4-connections.openapi.json','EXECUTE')]:
            self.assertEqual(expected,qualification_change({path:'old'},{path:'new'}))
        with self.assertRaisesRegex(ValueError,'UNCLASSIFIED'): qualification_change({}, {'unknown/new.dat':'new'})
        self.assertEqual([],workflow.select_gates(['docs/tasks/templates/sdd-task.md'])['unknown'])
        inputs=query.qualification_inputs()
        chosen=select(ROOT,'query-unit',inputs)
        self.assertIn('backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryKeyEquality.cs',chosen)
        self.assertNotIn('scripts/maintenance/workflow_m4_query_evidence.py',chosen)
        self.assertNotIn('scripts/create-review-package.ps1',chosen)
        self.assertIn('experiments/g4-m3-mapping-001/fixture.sql',chosen)
        changed=dict(inputs); changed['experiments/g4-m3-mapping-001/fixture.sql']='mutation'
        self.assertNotEqual(chosen,select(ROOT,'query-unit',changed))
        row=dict(taskId=TASK,runId=query.RUN,name='query-unit',status='PASS',exitCode=0,inputsUnchanged=True,inputs=chosen,allInputs=inputs,commands=[{'path':'original'}])
        with self.assertRaisesRegex(ValueError,'QUALIFICATION_INVALID'): query.demand_qualification(row,'query-unit',select(ROOT,'query-unit',changed),changed)
        unknown=dict(inputs,**{'scripts/maintenance/unclassified_new.py':'mutation'})
        with self.assertRaisesRegex(ValueError,'ENGINEERING_DRIFT'): query.demand_qualification(row,'query-unit',chosen,unknown)
        parser=dict(inputs,**{'scripts/maintenance/workflow_m4_query_evidence.py':'new-parser'})
        query.demand_qualification(row,'query-unit',select(ROOT,'query-unit',parser),parser)

        self.assertEqual(chosen,select(ROOT,'query-unit',dict(inputs,**{'docs/development/unrelated-connector.md':'changed'})))

    def test_interpreter_split_preserves_execution_and_rejects_assertion_or_top_level_change(self):
        from workflow_m4_query_inputs import execution_driver_hash, project_original
        source="TASK='G4-M4-QUERY-001'\ndef prepared(): return 1\ndef web_check(stage): assert stage=='unit'\ndef qualify(): return 1\n"
        self.assertEqual(execution_driver_hash(source,'web-unit'),execution_driver_hash(source.replace('def qualify(): return 1','def qualify(): return 2'),'web-unit'))
        for changed in [source.replace("assert stage=='unit'","assert stage=='other'"),source+"raise RuntimeError()\n"]:
            self.assertNotEqual(execution_driver_hash(source,'web-unit'),execution_driver_hash(changed,'web-unit'))
        inputs=query.qualification_inputs();driver=(ROOT/'scripts/maintenance/workflow_m4_query.py').read_text()
        row=dict(inputs=inputs, taskId=TASK, runId=query.RUN, name='web-unit', inputsUnchanged=True,status='PASS',exitCode=0)
        project_original(ROOT,row,'web-unit',inputs,driver)
        for key,value in [('taskId','foreign'),('runId','foreign'),('name','query-unit'),('inputsUnchanged',False)]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'ORIGINAL_QUALIFICATION_IDENTITY'):
                project_original(ROOT,dict(row,**{key:value}),'web-unit',inputs,driver)
        for changed in [source.replace('def qualify():',"def qualify(x=__import__('os').environ.update({'MODE':'Changed'})):"), source.replace('def qualify():','@dangerous\ndef qualify():'), source.replace('def qualify():','def qualify(x: dangerous()):')]:
            with self.assertRaisesRegex(ValueError,'IMPORT_SIDE_EFFECT'):
                execution_driver_hash(changed,'web-unit')
        altered=dict(inputs);altered['apps/web/src/features/semantic/g4-query.test.ts']='changed-assertions'
        with self.assertRaisesRegex(ValueError,'EXECUTION_CHANGED'): project_original(ROOT,row,'web-unit',altered,driver)
        with self.assertRaisesRegex(ValueError,'DRIVER_HASH'): project_original(ROOT,row,'web-unit',inputs,driver+'# forged')

    def test_build_closure_rejects_old_receipt_missing_embedded_schema(self):
        inputs = {'backend/src/Query.cs': 'source', 'docs/contracts/g4-connections.openapi.json': 'schema',
                  'Directory.Build.props': 'config', 'apps/web/src/page.tsx': 'web'}
        expected = {key:value for key,value in inputs.items() if not key.startswith('apps/')}
        query.demand_build_inputs({'inputs': expected}, inputs)
        for omitted in expected:
            with self.subTest(omitted=omitted), self.assertRaisesRegex(ValueError, 'QUERY_BUILD_INPUT_CLOSURE'):
                query.demand_build_inputs({'inputs': {key:value for key,value in expected.items() if key != omitted}}, inputs)
        with self.assertRaisesRegex(ValueError, 'QUERY_BUILD_INPUT_CLOSURE'):
            query.demand_build_inputs({'inputs': dict(expected, obsolete='stale')}, inputs)

    def test_qualification_rejects_stale_failed_foreign_and_zero_originals(self):
        inputs = {'source.cs': 'current'}
        row = dict(taskId=TASK, runId=query.RUN, name='contract', status='PASS', exitCode=0,
                   inputsUnchanged=True, inputs=inputs, commands=[{'path': 'actual-receipt'}])
        query.demand_qualification(row, 'contract', inputs)
        for key, value in [('taskId', 'G4-M3-MAPPING-001'), ('runId', 'old'), ('name', 'other'),
                           ('status', 'FAIL'), ('exitCode', 1), ('inputsUnchanged', False),
                           ('inputs', {'source.cs': 'old'}), ('commands', [])]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'QUERY_QUALIFICATION_INVALID'):
                query.demand_qualification(dict(row, **{key: value}), 'contract', inputs)

    def test_persistence_database_cannot_target_live_or_foreign_database(self):
        self.assertEqual('m4_query_test_0123456789ab', query.test_database_name('0123456789ab'))
        for value in ('query', '', 'a' * 11, '0123456789ab;DROP DATABASE query', 'ABCDEF012345'):
            with self.assertRaisesRegex(ValueError, 'QUERY_TEST_DATABASE_ID_INVALID'):
                query.test_database_name(value)

    def test_database_guard_rejects_existing_unmarked_and_foreign_before_destructive_sql(self):
        labels = json.dumps({'ontology.task-id':TASK,'ontology.run-id':query.RUN}).encode()
        for create, owner in [(True,None),(False,None),(False,TASK+':other:0123456789ab')]:
            inspected=SimpleNamespace(returncode=0,stdout=json.dumps(dict(exists=True,owner=owner)).encode(),receipt={})
            with patch('subprocess.check_output',return_value=labels),patch('workflow_execution.run',return_value=inspected) as run:
                with self.assertRaisesRegex(ValueError,'OWNER_MISMATCH'): query.test_database_control('owned','0123456789ab',create)
                self.assertEqual(1,run.call_count)
                self.assertTrue(run.call_args.kwargs['stdin'].startswith(b'SELECT'))
        with patch('subprocess.check_output',return_value=b'{}'),patch('workflow_execution.run') as run:
            with self.assertRaisesRegex(ValueError,'CONTAINER_OWNER'): query.test_database_control('foreign','0123456789ab',True)
            run.assert_not_called()

    def test_partial_database_creation_has_explicit_keep_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'artifacts/workflow' / TASK / query.RUN
            output.mkdir(parents=True)
            labels = json.dumps({'ontology.task-id': TASK, 'ontology.run-id': query.RUN}).encode()
            inspected = SimpleNamespace(returncode=0, stdout=b'{"exists":false,"owner":null}', receipt={'commandId': 'inspection'})
            with patch.object(query, 'ROOT', root), patch('subprocess.check_output', return_value=labels), patch('workflow_execution.run', side_effect=[inspected, OSError('injected')]):
                with self.assertRaises(OSError):
                    query.test_database_control('exact-owned-container', '0123456789ab', True)
            record = json.loads((output / 'm4_query_test_0123456789ab-create.json').read_text())
            self.assertEqual('KEEP_UNVERIFIED', record['status'])
            self.assertEqual('m4_query_test_0123456789ab', record['database'])
            self.assertIn('task_marker', record['releaseCondition'])

    def test_container_cleanup_timeout_records_database_keep(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'artifacts/workflow' / TASK / query.RUN
            output.mkdir(parents=True)
            project = 'ontology-g4-m4-query-impl-01'
            (output / 'platform-resources.json').write_text(json.dumps(dict(taskId=TASK, runId=query.RUN, status='HEALTHY', project=project, resources=[{'id': 'owned-pg'}])))
            private = root / '.tools/security/g4-m4-query-001' / query.RUN / 'platform-pg'
            private.mkdir(parents=True)
            (private / 'password').write_text('synthetic-test-only')
            labels = {'ontology.task-id': TASK, 'ontology.run-id': query.RUN}
            container = dict(Config={'Labels': labels}, State={'Health': {'Status': 'healthy'}})
            image = dict(Id='sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55', Architecture='arm64')
            name = project + '-persistence-test-0123456789ab'
            absent = SimpleNamespace(returncode=1, stderr=('No such container: '+name).encode())
            completed = SimpleNamespace(returncode=0, stdout=b'', receipt={'commandId': 'test'})
            with patch.object(query, 'ROOT', root), patch.object(query, 'prepared'), patch.object(query, 'runtime_query_inventory', return_value=[]), patch.object(query, 'test_database_control'), patch('uuid.uuid4', return_value=SimpleNamespace(hex='0123456789ab')), patch('subprocess.check_output', side_effect=[json.dumps([container]).encode(), json.dumps([image]).encode()]), patch('subprocess.run', side_effect=[absent, subprocess.TimeoutExpired('inspect', 10)]), patch('workflow_execution.run', return_value=completed):
                with self.assertRaises(subprocess.TimeoutExpired):
                    query.persistence_test()
            record = json.loads((output / 'm4_query_test_0123456789ab-keep.json').read_text())
            self.assertEqual('KEEP_UNVERIFIED', record['status'])
            self.assertEqual(name, record['containerName'])
            self.assertIn('exact_test_container_absent', record['releaseCondition'])
            self.assertFalse((private / 'test-0123456789ab.env').exists())

    def test_public_m4_originals_have_exact_policy_gate(self):
        current = workflow.select_gates(['docs/evidence/G4-M4-QUERY-001/query-impl-01/stdout.txt.raw.json'])
        self.assertEqual('PLANNED', current['status'])
        self.assertIn('policy', current['affected'])
        self.assertEqual('BLOCKED', workflow.select_gates(['docs/evidence/G4-M4-UNKNOWN/raw.json'])['status'])

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
