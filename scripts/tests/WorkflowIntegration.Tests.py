#!/usr/bin/env python3
"""M5消费者身份与前提失效反例；非真实DB验收。"""
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch,Mock
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
class IntegrationTests(unittest.TestCase):
    def test_m5_does_not_change_m4_identity(self):
        import workflow_m4_query as old
        import workflow_m5_integration as new
        self.assertEqual(old.TASK,'G4-M4-QUERY-001')
        self.assertEqual(new.TASK,'G4-M5-INTEGRATION-001')
        self.assertNotEqual(old.PROFILE.project,new.PROFILE.project)
        self.assertNotEqual(old.PROFILE.private,new.PROFILE.private)
        self.assertFalse(set(old.PROFILE.ports.values())&set(new.PROFILE.ports.values()))
    def test_scenarios_have_separate_state_and_unknown_refuses(self):
        import workflow_m5_integration as new
        new.scenario('numeric');a=new.fixture_file()
        new.scenario('standard');b=new.fixture_file()
        self.assertNotEqual(a,b)
        with self.assertRaises(ValueError):new.scenario('../escape')
    def test_snapshot_task_relabel_and_mutable_bin_are_rejected(self):
        from workflow_m4_query_runtime import freeze,verify
        import workflow_m5_integration as q
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=root/'bin';source.mkdir()
            for name in ['Api.dll','Api.deps.json','Api.runtimeconfig.json']:(source/name).write_text(name)
            row=freeze(root,source,root/'artifacts/workflow'/q.TASK/q.RUN/'runtime-snapshots',{'source.cs':'hash'},'command',task=q.TASK,run_id=q.RUN)
            verify(root,row,task=q.TASK,run_id=q.RUN)
            for change in [{'taskId':'G4-M4-QUERY-001'},{'directory':'bin'},{'resourceRun':'old'},{'snapshotId':'0'*64}]:
                with self.subTest(change=change),self.assertRaises(ValueError):verify(root,{**row,**change},task=q.TASK,run_id=q.RUN)

    def test_wrong_database_and_owner_refused_before_destructive_sql(self):
        import workflow_m5_integration as q
        import workflow_execution
        with self.assertRaises(ValueError):q.test_database_name('query')
        with patch('subprocess.check_output',return_value=b'{"ontology.task-id":"G4-M4-QUERY-001","ontology.run-id":"query-impl-01"}'),patch.object(workflow_execution,'run') as execute:
            with self.assertRaisesRegex(ValueError,'CONTAINER_OWNER'):q.test_database_control('container','a'*12,False)
            execute.assert_not_called()
        labels=json.dumps({'ontology.task-id':q.TASK,'ontology.run-id':q.RUN}).encode()
        with patch('subprocess.check_output',return_value=labels),patch.object(workflow_execution,'run',return_value=SimpleNamespace(returncode=0,stdout=b'{"exists":true,"owner":"foreign"}')) as execute:
            with self.assertRaisesRegex(ValueError,'OWNER_MISMATCH'):q.test_database_control('container','a'*12,False)
            self.assertEqual(execute.call_count,1)
            self.assertTrue(execute.call_args.kwargs['stdin'].startswith(b'SELECT'))

    def test_readiness_rejects_each_stale_fact(self):
        from workflow_m5_integration import demand_ready
        good={'api':True,'web':True,'build':True,'session':True,'connection':True,'grant':True,'activation':True,'fixture':True,'owner':True,'budget':True}
        self.assertEqual(demand_ready(good),'SCENARIO_READY')
        for key in good:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:'+key):demand_ready({**good,key:False})
        with self.assertRaises(ValueError):demand_ready({})
    def test_complete_grant_cannot_be_assembled_from_partial_rows(self):
        import workflow_m5_integration as q
        import copy
        state=dict(subjects={'operator':'current','auditor':'reviewer'},scope={'organizationId':'org-demo','siteIds':['site-a','site-b']},connectionId='connection',catalog={'objects':[dict(schema='production',name=name,fields=[dict(ordinal=1,name='organization_id')]) for name in ['assets','readings']]})
        row=dict(SubjectId='current',OrganizationId='org-demo',SiteIds=['site-a','site-b'],ConnectionId='connection',ObjectRefs=['production/assets','production/readings'],FieldRefs=['production/assets/1/organization_id','production/readings/1/organization_id'])
        grants=[dict(row,Permission='data.query.'+permission) for permission in ['execute','result.read','evidence.read']]
        q.demand_grants(grants,state)
        for key,value in [('SubjectId','old'),('OrganizationId','foreign'),('SiteIds',['site-b']),('ObjectRefs',['production/assets']),('FieldRefs',['unrelated'])]:
            changed=copy.deepcopy(grants);changed[0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:grant'):q.demand_grants(changed,state)
        for missing in (1,2):
            with self.assertRaises(ValueError):q.demand_grants([r for i,r in enumerate(grants) if i!=missing],state)
        partial=copy.deepcopy(grants);partial[0]['FieldRefs']=row['FieldRefs'][:1]
        partial.append(dict(grants[0],FieldRefs=row['FieldRefs'][1:]))
        with self.assertRaises(ValueError):q.demand_grants(partial,state)

    def test_runtime_entry_stops_before_long_chain_when_original_session_fails(self):
        import workflow_m5_integration as q
        with patch.object(q,'demand_agent_build'),patch.object(q,'resource_admission'),patch.object(q,'local_ready'),patch.object(q,'original_runtime_agent_test',return_value=1) as execute:
            self.assertEqual(q.runtime_agent_test(aba_inflight=True), 1)
            execute.assert_called_once_with(False,True)
        with patch.object(q,'demand_agent_build'),patch.object(q,'resource_admission'),patch.object(q,'local_ready',side_effect=ValueError('PREREQUISITE_STALE:fixture')),patch.object(q,'original_runtime_agent_test') as execute:
            with self.assertRaises(ValueError):q.runtime_agent_test()
            execute.assert_not_called()

    def test_foreign_web_listener_is_rejected_before_http(self):
        import workflow_m5_integration as q
        with patch.object(q.consumer,'web_binding',return_value={'buildId':'new'}),patch('subprocess.check_output',return_value=b'99999999\n'),patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:web_process'):q.live_web_binding()
            request.assert_not_called()

    def test_projected_budget_rejects_stopped_slot_and_pending_overage(self):
        import workflow_m5_integration as q
        own=dict(task=q.TASK,memory=5.25*1024**3,cpu=3.75e9)
        other=dict(task='KEEP',memory=6*1024**3,cpu=4.5e9)
        pending=dict(pending_memory=768*1024**2,pending_cpu=2e9,pending_count=1)
        self.assertEqual(q.demand_budget([own,other],6,**pending)['sharedCpu'],10.25e9)
        for rows,count in [([own,other],7),([dict(own,memory=6*1024**3),other],6),([own,dict(other,cpu=7.25e9)],6),([own,dict(other,memory=8.5*1024**3)],6)]:
            with self.subTest(rows=rows,count=count),self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:budget'):q.demand_budget(rows,count,**pending)

    def test_catalog_ready_rejects_added_object_and_changed_unmapped_field(self):
        import workflow_m5_integration as q
        objects=[dict(schema='production',name='assets',kind='TABLE',fields=[dict(name='id',ordinal=1,nativeType='text',nullable=False)])]
        rows=[dict(schema='production',table='assets',kind='TABLE',column='id',ordinal=1,type='text',nullable=False)]
        q.demand_catalog(rows,objects)
        for actual in [rows+[dict(rows[0],table='new_numeric')],[dict(rows[0],type='integer')],[]]:
            with self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:source_catalog'):q.demand_catalog(actual,objects)

    def test_allocation_entries_reject_before_any_command(self):
        import workflow_m5_integration as q
        import workflow_execution
        entries = [('platform_start', ()), ('source_start', ()), ('runtime_start', ()),
                   ('runtime_second_api', ()), ('runtime_api_resume', ()),
                   ('runtime_secondary_state', (True,)), ('runtime_persist_query_keyring', ()),
                   ('persistence_test', ()), ('runtime_agent_test', ())]
        conditions = [
            dict(containers=[dict(task='KEEP', running=True, memory=14*1024**3, cpu=1e9, id='keep', run='other', service=None)], engineMemory=14*1024**3, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0),
            dict(containers=[dict(task=q.TASK, run=q.RUN, running=False, memory=0, cpu=0, id=str(i), service='stopped-'+str(i)) for i in range(7)], engineMemory=14*1024**3, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0),
            dict(containers=[], engineMemory=512*1024**2, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0),
            dict(containers=[], engineMemory=14*1024**3, engineCpu=.25, hostRssBytes=0, taskDiskUpperBytes=0),
            dict(containers=[dict(task='KEEP', running=True, memory=0, cpu=0, id='unknown', run='other', service=None)], engineMemory=14*1024**3, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0)]
        for name, args in entries:
            for inventory in conditions:
                with tempfile.TemporaryDirectory() as directory, patch.object(q, 'ROOT', Path(directory)), self.subTest(entry=name, inventory=inventory), patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_inventory', return_value=inventory), patch.object(q.consumer, 'runtime_command') as command, patch.object(workflow_execution, 'run') as execute:
                    with self.assertRaisesRegex(ValueError, 'PREREQUISITE_STALE:budget'):
                        getattr(q.consumer, name)(*args)
                    command.assert_not_called()
                    execute.assert_not_called()

    def test_cold_plan_without_services_and_stopped_memory(self):
        import workflow_m5_integration as q
        inventory = dict(containers=[], engineMemory=14*1024**3, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(q, 'ROOT', Path(directory)), patch.object(q, 'resource_inventory', return_value=inventory):
            result = q.resource_admission(['platform-pg'], cold=True)
            self.assertEqual(len(result['plans']), 3)
            self.assertTrue(all(row['budget']['ownedCount'] == 7 for row in result['plans']))
        stopped = dict(task='KEEP', running=False, memory=100*1024**3, cpu=100e9)
        self.assertEqual(q.demand_budget([stopped], 0)['sharedMemory'], 0)

    def test_stopped_quota_drift_rejects_actual_resume(self):
        import workflow_m5_integration as q
        inventory = dict(containers=[dict(id='secondary', task=q.TASK, run=q.RUN, service='api-secondary', running=False, memory=4*1024**3, cpu=.75e9)], engineMemory=14*1024**3, engineCpu=12, hostRssBytes=0, taskDiskUpperBytes=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(q, 'ROOT', Path(directory)), patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_inventory', return_value=inventory), patch.object(q.consumer, 'runtime_command') as command:
            with self.assertRaisesRegex(ValueError, 'resource_config'):
                q.consumer.runtime_secondary_state(True)
            command.assert_not_called()
            receipts = list((Path(directory)/'artifacts/workflow'/q.TASK/q.RUN).glob('resource-admission-*.json'))
            self.assertEqual(len(receipts), 1)
            self.assertEqual(json.loads(receipts[0].read_text())['inventory']['containers'][0]['id'], 'secondary')

    def test_provision_requires_batch_schema_before_browser(self):
        import workflow_m5_integration as q
        with patch.object(q, 'prepare_batch_schema', side_effect=ValueError('PREREQUISITE_STALE:partial_batch_schema')), patch.object(q, 'original_browser_test') as browser:
            with self.assertRaisesRegex(ValueError, 'partial_batch_schema'):
                q.consumer.browser_test('provision')
            browser.assert_not_called()
        order = []
        with patch.object(q, 'prepare_batch_schema', side_effect=lambda: order.append('schema')), patch.object(q, 'original_browser_test', side_effect=lambda mode: order.append(mode)):
            q.consumer.browser_test('provision')
            self.assertEqual(order, ['schema', 'provision'])

    def test_actual_runtime_entry_stops_on_live_service_or_catalog_failure(self):
        import workflow_m5_integration as q
        import workflow_execution
        q.scenario('standard')
        with patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_admission'), patch.object(q.consumer, 'runtime_binding', return_value={}), patch('socket.create_connection', side_effect=OSError('not listening')), patch.object(q, 'original_runtime_agent_test') as execute:
            with self.assertRaisesRegex(ValueError, 'PREREQUISITE_STALE:api'):
                q.runtime_agent_test()
            execute.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root/'artifacts/workflow'/q.TASK/q.RUN; output.mkdir(parents=True)
            (output/'scenario-standard.json').write_text(json.dumps(dict(taskId=q.TASK, runId=q.RUN, scenario='standard', catalog={'objects':[]})))
            (output/'source-resources.json').write_text(json.dumps({'resources':[{'id':'source'}]}))
            inventory = dict(containers=[dict(task=q.TASK, run=q.RUN, id='source', running=True, memory=768*1024**2, cpu=.75e9)], engineMemory=14*1024**3, engineCpu=12)
            new_column = dict(schema='production', table='new_table', kind='TABLE', column='id', ordinal=1, type='text', nullable=False)
            with patch.object(q, 'ROOT', root), patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_admission'), patch.object(q.consumer, 'runtime_binding', return_value={}), patch('socket.create_connection'), patch.object(q, 'resource_inventory', return_value=inventory), patch.object(workflow_execution, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps([new_column]).encode())), patch.object(q, 'original_runtime_agent_test') as execute:
                with self.assertRaisesRegex(ValueError, 'PREREQUISITE_STALE:source_catalog'):
                    q.runtime_agent_test()
                execute.assert_not_called()

    def test_runtime_entry_refuses_changed_activation_after_prepare(self):
        import workflow_m5_integration as q
        import workflow_execution
        q.scenario('standard')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root/'artifacts/workflow'/q.TASK/q.RUN; output.mkdir(parents=True)
            expected = dict(mappingId='mapping', activationId='old', activationRevision=1, mappingReleaseId='release', manifestHash='hash')
            state = dict(taskId=q.TASK, runId=q.RUN, scenario='standard', catalog={'objects':[]}, mappingReceipt=expected)
            (output/'scenario-standard.json').write_text(json.dumps(state))
            for resource in ['source', 'platform']:
                (output/(resource+'-resources.json')).write_text(json.dumps({'resources':[{'id':resource}]}))
            inventory = dict(containers=[dict(task=q.TASK, run=q.RUN, id=name, running=True, memory=768*1024**2, cpu=.75e9) for name in ['source','platform']], engineMemory=14*1024**3, engineCpu=12)
            replies = [[], {}, [], {'schema':True,'tables':[True,True],'readonly':True}, {'activationId':'changed','binding':{},'connection':{},'catalog':{}}]
            def sql(*args, **kwargs):
                return SimpleNamespace(returncode=0, stdout=json.dumps(replies.pop(0)).encode())
            with patch.object(q, 'ROOT', root), patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_admission'), patch.object(q.consumer, 'runtime_binding', return_value={}), patch('socket.create_connection'), patch.object(q, 'resource_inventory', return_value=inventory), patch.object(q, 'demand_fixture'), patch.object(q, 'demand_grants'), patch.object(workflow_execution, 'run', side_effect=sql), patch.object(q, 'original_runtime_agent_test') as execute:
                with self.assertRaisesRegex(ValueError, 'PREREQUISITE_STALE:activation'):
                    q.runtime_agent_test()
                execute.assert_not_called()

    def test_valid_runtime_entry_calls_same_process_once(self):
        import workflow_m5_integration as q
        with patch.object(q, 'demand_agent_build'), patch.object(q, 'resource_admission'), patch.object(q, 'local_ready'), patch.object(q, 'original_runtime_agent_test', return_value=0) as execute:
            self.assertEqual(q.runtime_agent_test(aba_inflight=True), 0)
            execute.assert_called_once_with(False, True)

if __name__=='__main__':unittest.main()
