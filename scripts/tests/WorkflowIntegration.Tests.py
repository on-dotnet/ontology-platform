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
        with patch.object(q,'local_ready'),patch.object(q,'original_runtime_agent_test',return_value=1) as execute:
            with self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:runtime_session_or_proposal'):q.runtime_agent_test(aba_inflight=True)
            execute.assert_called_once_with(False,True,preflight=True)
        with patch.object(q,'local_ready',side_effect=ValueError('PREREQUISITE_STALE:fixture')),patch.object(q,'original_runtime_agent_test') as execute:
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

if __name__=='__main__':unittest.main()
