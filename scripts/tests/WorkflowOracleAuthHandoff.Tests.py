"""真实浏览器预算生产者与原件消费者的离线篡改回归，不宣称产品通过。"""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
import workflow_oracle_mapping_evidence as e
import workflow_oracle_mapping_platform as platform
spec=importlib.util.spec_from_file_location('fixtures',Path(__file__).with_name('WorkflowOracleMappingEvidence.Tests.py'))
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
def at(seconds):return (dt.datetime(2026,11,20,tzinfo=dt.timezone.utc)+dt.timedelta(seconds=seconds)).isoformat()

class BatchEvidenceTests(unittest.TestCase):
    write=fixtures.OracleQualificationTests.write
    def setUp(self):
        self.enterContext(patch.dict(os.environ,OMQ_PRODUCT_RUN='product-resume-01'))
        self.enterContext(patch.object(e,'RUN',e.PRODUCT_RUN))
        self.enterContext(patch.object(e,'BROWSER',e.BROWSER|{'s0-oracle-auth','auth-handoff-s1','reader-auth'}))
        fixtures.OracleQualificationTests.setUp(self)
        for name in e.drivers(ROOT,'auth-handoff-s1'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
        self.plan=e.batch_plan(self.root)
        self.stage=dict(phase='s0',mode='auth-handoff-s1',case='healthy',plan=self.plan,executionId='e'*32,batchInput='auth-handoff-'+'e'*32+'.json')
        self.cid='a'*32
        self.parent_name='browser-auth-handoff-s1-1790000000000.json'
        self.parent=dict(taskId=e.TASK,runId=e.RUN,mode='auth-handoff-s1',input=dict(executionId='e'*32,plan=self.plan),
                         startedAtUtc=at(1),finishedAtUtc=at(100),preMs=1000,postMs=1000,status='PASS',stages=[])
        self.reports={}
        for index,spec in enumerate(self.plan['stages']):
            mode=spec['mode'];name='browser-'+mode+'-1790000000000.json'
            phase=dict(mode=mode,case='healthy',phase='s1' if mode.startswith('s1') else 's0')
            report=dict(taskId=e.TASK,runId=e.RUN,mode=mode,stageInputs=phase,inputsUnchanged=True,status='PASS',
                        inputBinding=dict(api={**self.host,'commandId':'2'*32},web=None),outputBinding=dict(api={**self.host,'commandId':'3'*32},web=None),
                        http=[dict(status=200)],checks=[dict(name='oracle_current_original_subject_'+who,status='PASS')
                        for who in ('operator-ab','auditor-ab','operator-a','viewer-a')],browser=dict(authentication='INTERACTIVE_OIDC',channel='msedge',version='130.0'),
                        startedAtUtc=at(2+index*10),finishedAtUtc=at(3+index*10),elapsedMs=1000,
                        batch=dict(executionId='e'*32,planId='auth-handoff-01',index=index,**spec))
            self.reports[name]=report
            self.parent['stages'].append(dict(status='PASS',phase='phase',report=str(self.origin/'artifacts/workflow'/e.TASK/e.RUN/name),checks=4,failure=None,
                mode=mode,index=index,startedAtUtc=report['startedAtUtc'],finishedAtUtc=report['finishedAtUtc'],elapsedMs=1000))
        self.report_name='browser-s1-1790000000000.json'
        self.entry=dict(commandId=self.cid,report=self.report_name,batch=dict(report=self.parent_name,stageInputs=self.stage))
        self.argv,self.key,self.label=e.browser_invocation(self.root,'auth-handoff-s1','healthy',self.host,self.api,self.agent,self.stage)
        self.row=dict(schemaVersion=2,taskId=e.TASK,runId=e.RUN,commandId=self.cid,parentId=self.host['commandId'],stage=self.label,cwd=str(self.origin),
            commandSummary=e.summary(self.argv),inputFingerprint=self.key,started=True,signal=None,classification='SUCCESS',exitCode=0,deadlineSeconds=1620,
            startedAtUtc=at(0),endedAtUtc=at(101),elapsedSeconds=101,environmentFingerprint='a'*64)

    def store(self):
        result=dict(status=self.parent['status'],report=str(self.origin/'artifacts/workflow'/e.TASK/e.RUN/self.parent_name),stages=self.parent['stages'])
        for name,report in self.reports.items():self.write(name,report)
        for item in self.parent['stages']:
            item['reportSha256']=e.sha(e.encoded(self.reports[Path(item['report']).name])+b'\n')
        self.write(self.parent_name,self.parent)
        for stream,raw in [('stdout',e.encoded(result)),('stderr',b'')]:
            self.row[stream]=dict(sizeBytes=len(raw),sha256=e.sha(raw));self.write(self.cid+'-'+stream+'.txt',raw)
        self.row['identity']=e.digest_value([self.row['inputFingerprint'],self.row['environmentFingerprint'],self.row['commandSummary']['sha256'],str(self.origin),
                                          self.row['deadlineSeconds'],e.sha((self.root/'scripts/maintenance/workflow_execution.py').read_bytes())])
        self.write(self.cid+'-receipt.json',self.row)

    def consume(self):
        self.store();return e.browser_report(self.archive,self.entry,self.origin,'s1','healthy',self.host,self.api,self.agent,self.reports[self.report_name]['stageInputs'])

    def test_real_invocation_and_consumer_agree_on_fixed_budget(self):
        self.assertEqual(self.consume()[1]['deadlineSeconds'],1620)
        self.assertEqual(self.argv[-2:],['--batch-input',self.stage['batchInput']])
        self.assertIn('scripts/maintenance/workflow_oracle_mapping_formal_observer.py',e.drivers(ROOT,'auth-handoff-s1'))
        self.assertIn('scripts/maintenance/workflow_oracle_archive_requalification.py',e.drivers(ROOT,'auth-handoff-s1'))

    def test_reregistered_wrong_parent_command_is_rejected(self):
        self.row['parentId']='f'*32
        with self.assertRaisesRegex(ValueError,'OMQ_COMMAND_BINDING'):self.consume()

    def test_old_180_or_arbitrary_large_budget_is_rejected(self):
        for seconds in (180,1621,100000):
            self.row['deadlineSeconds']=seconds
            with self.subTest(seconds=seconds),self.assertRaisesRegex(ValueError,'OMQ_BROWSER_DEADLINE'):self.consume()

    def test_stage_replacement_order_and_overrun_are_rejected(self):
        original=copy.deepcopy(self.parent)
        for change in ('mode','index','elapsedMs'):
            self.parent=copy.deepcopy(original)
            item=self.parent['stages'][3];item[change]={'mode':'mapping','index':2,'elapsedMs':180001}[change]
            if change=='elapsedMs':self.reports[self.report_name]['elapsedMs']=180001
            with self.subTest(change=change),self.assertRaises(ValueError):self.consume()

    def test_plan_and_input_replacement_are_rejected(self):
        self.parent['input']['executionId']='f'*32
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_PARENT'):self.consume()
        self.parent['input']['executionId']='e'*32
        self.stage['plan']={**self.plan,'deadlineSeconds':180}
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_INPUT'):self.consume()

    def test_stage_input_substitution_cannot_change_parent_stdout(self):
        self.store()
        replaced=copy.deepcopy(self.reports[self.report_name]);replaced['stageInputs']['catalogSnapshotId']='substitute'
        self.write(self.report_name,replaced)
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_MEMBER_BINDING'):
            e.browser_report(self.archive,self.entry,self.origin,'s1','healthy',self.host,self.api,self.agent,replaced['stageInputs'])

    def test_runtime_entry_requires_actual_predecessor_consumers(self):
        area=self.root/'artifacts/workflow'/e.TASK/e.RUN;area.mkdir(parents=True)
        for name,report in self.reports.items():(area/name).write_bytes(e.encoded(report))
        (area/self.parent_name).write_bytes(e.encoded(self.parent))
        dispatch=dict(taskId=e.TASK,runId=e.RUN,mode='auth-handoff-s1',case='healthy',commandId=self.cid,reports=[self.parent_name],
                      testedCommit='d'*40,stageInputs=self.stage,host=self.host,builds=dict(api=self.api,agent=self.agent))
        (area/('formal-run-auth-handoff-s1-'+self.cid+'.json')).write_bytes(e.encoded(dispatch))
        modes=[]
        def consume(archive,entry,origin,mode,case):
            modes.append(mode)
            archive.auditIdentity={};archive.browserIdentity={}
            archive.persistence={};archive.persistenceWindow={}
            if mode=='s0-oracle-auth':raise ValueError('AUTH_ORIGINAL_REJECTED')
            return 1
        with patch.object(e,'build_binding',side_effect=lambda archive,target,origin:self.api if target=='api' else self.agent),patch.object(e,'reopen_browser',side_effect=consume):
            with self.assertRaisesRegex(ValueError,'AUTH_ORIGINAL_REJECTED'):
                e.reopen_runtime_case(self.root,e.TASK,e.RUN,self.cid,expected_mode='s1')
        self.assertEqual(modes,['s1','mapping',e.NATURAL_CANCEL,'s0-oracle-auth'])

    def test_outer_browser_run_uses_same_budget_without_pre_auth_source_read(self):
        captured={}
        class Done(Exception):pass
        def execute(argv,root,**kwargs):
            if argv[0]==e.NODE:captured.update(kwargs);raise Done()
            return type('R',(),dict(returncode=0,receipt=dict(commandId='b'*32)))()
        stage_area=self.root/'artifacts/workflow'/e.TASK/e.RUN;stage_area.mkdir(parents=True)
        with patch.object(platform,'ROOT',self.root),patch.object(platform,'AREA',stage_area.parent/platform.RUN), \
             patch.object(platform,'admission',return_value=dict(attempt='safe')),patch.object(platform,'runtime_binding',return_value=self.host), \
             patch.object(platform.build,'validate',side_effect=lambda kind,task:self.api if kind=='api' else self.agent), \
             patch.object(platform,'fixture_state',side_effect=AssertionError('pre-auth source read')),patch.object(platform.ex,'run',side_effect=execute):
            with self.assertRaises(Done):platform.browser_run('auth-handoff-s1')
        self.assertEqual(captured['timeout'],1620)
        self.assertRegex(captured['environment']['OMQ_PROGRESS_FILE'],r'^auth-handoff-[a-f0-9]{32}\.jsonl$')


class BatchAuditClosureTests(unittest.TestCase):
    """真实源审计命令/双流与父阶段集合；其余宿主/产品资格由原专项测试覆盖。"""
    def setUp(self):
        self.enterContext(patch.object(e,'RUN',e.PRODUCT_RUN))
        spec=importlib.util.spec_from_file_location('audit_memory',Path(__file__).with_name('WorkflowOracleAuthEvidence.Tests.py'))
        memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory)
        self.archive=memory.MemoryOriginals()
        self.enterContext(patch.object(e,'measured_audit_key',side_effect=lambda archive,call,commit:call['identity']))
        self.cid='a'*32
        self.source='9'*64
        self.host=dict(oracle=dict(containerId=self.source))
        self.entry=dict(commandId=self.cid,batch=dict(report='parent.json'))
        self.row=dict(startedAtUtc=at(0),endedAtUtc=at(101))
        self.parent=dict(stages=[dict(mode=item['mode'],startedAtUtc=at(2+i*10),finishedAtUtc=at(3+i*10))
                                for i,item in enumerate(e.batch_plan(ROOT)['stages'])])
        self.events=[dict(instance='1',session=str(i),entry='1',statement='11',auditExecution=None,clientId=str(i)*32,
                          owner='PRODUCTION',table='OMQ_ENTITY',action='SELECT',code=0,utc=at(t)) for i,t in [(1,12.5),(2,32.5)]]
        self.audits={}
        self.store()

    def observed_audit(self,name,start,end,records,client=None,index=0):
        from workflow_oracle_mapping_formal_observer import audit_invocation
        from workflow_oracle_mapping_resources import SOURCE, RUN
        command=f'{index+1:032x}';identity=f'{index+20:032x}'
        clock_start=102+index*3;clock_end=clock_start+1
        fmt='{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.State.Status}}'
        self.archive.observed(identity,['docker','--context','desktop-linux','inspect','-f',fmt,self.source],
            e.digest_value([self.source,SOURCE,e.TASK,RUN]),'oracle-audit-source-identity',clock_start-1,clock_start-.5,5,None,e.RUN,
            '|'.join([self.source,SOURCE.split('@')[1],e.TASK,RUN,'running']).encode(),b'')
        call=audit_invocation(self.source,start,end,client)
        raw=('CLOCK|'+at(clock_start)+'\nIDENTITY|OMQ_OBSERVER|TCPS|FREEPDB1\n'+
             ''.join(json.dumps(row)+'\n' for row in records)+'CLOCK|'+at(clock_end)+'\n').encode()
        self.archive.observed(command,call['argv'],call['identity'],'oracle-formal-audit-window',clock_start,clock_end,12,None,e.RUN,raw,b'')
        value=dict(taskId=e.TASK,runId=e.RUN,sourceId=self.source,startUtc=start,endUtc=end,clientId=client,
                   observerId='OMQ_OBSERVER',sourceIdentityCommand=identity,sourceClock=[at(clock_start),at(clock_end)],
                   errorBounds=dict(lowerNs=0,upperNs=0),sourceAuditCount=len(records),records=records,recordsSha256=e.digest_value(records),commandId=command)
        self.archive.save(name,value);self.audits[name]=value
        return value

    def store(self):
        self.archive.save('parent.json',self.parent)
        prefix='formal-audit-'+self.cid
        self.parent_name=prefix+'.json'
        self.observed_audit(self.parent_name,at(0),at(101),self.events)
        for i,item in enumerate(self.parent['stages'],1):
            rows=[r for r in self.events if e.utc(item['startedAtUtc'])<=e.utc(r['utc'])<e.utc(item['finishedAtUtc'])]
            self.observed_audit(prefix+'-'+item['mode']+'.json',item['startedAtUtc'],item['finishedAtUtc'],rows,index=i)

    def consume(self):
        return e.batch_audit_closure(self.archive,self.entry,self.row,self.host,ROOT,'d'*40)

    def test_complete_parent_and_six_stage_commands_reopen(self):
        result=self.consume()
        self.assertEqual(result['status'],'COMPLETE_EVENT_PARTITION')
        self.assertEqual(result['sourceAuditCount'],2)
        self.assertEqual([r['sourceAuditCount'] for r in result['stages']],[0,1,0,1,0,0])

    def test_filtered_a_with_rebound_sql_identity_is_rejected_by_actual_stage_entry(self):
        name='formal-audit-'+self.cid+'-'+e.NATURAL_CANCEL+'.json'
        original=self.audits[name]
        self.observed_audit(name,original['startUtc'],original['endUtc'],original['records'],self.events[0]['clientId'],index=2)
        # 单次审计原件及SQL身份完全自洽；拒绝来自正式阶段的无过滤要求。
        e.audit_observation(self.archive,self.audits[name],dict(startedAtUtc=original['startUtc'],endedAtUtc=original['endUtc']),self.host,ROOT,'d'*40)
        self.archive.save('host.json',dict(host=self.host,testedCommit='d'*40))
        report=dict(inputBinding=dict(api=dict(commandId='2'*32)),outputBinding=dict(api=dict(commandId='3'*32)))
        before={**self.host,'commandId':'1'*32};self.archive.save('host.json',dict(host=before,testedCommit='d'*40))
        times=[dict(commandId='1'*32,startedAtUtc=at(0),endedAtUtc=at(1)),
               dict(commandId='2'*32,startedAtUtc=at(3),endedAtUtc=at(4)),
               dict(commandId='3'*32,startedAtUtc=at(5),endedAtUtc=at(6))]
        with patch.object(e,'build_binding',return_value={}),patch.object(e,'browser_report',return_value=(report,dict(startedAtUtc=at(2),endedAtUtc=at(7)))), \
             patch.object(e,'host_observation',side_effect=times):
            with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_UNFILTERED'):
                e.reopen_browser(self.archive,dict(host='host.json',audit=name,stageInputs={}),ROOT,e.NATURAL_CANCEL,'healthy')
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_AUDIT_UNFILTERED'):self.consume()

    def test_parent_missing_wrong_source_window_and_command_rejected(self):
        original=self.archive.files.copy()
        del self.archive.files[self.parent_name]
        with self.assertRaises(KeyError):self.consume()
        for key,value in [('sourceId','8'*64),('startUtc',at(1)),('commandId','f'*32),('clientId','1'*32)]:
            self.archive.files=original.copy()
            audit={**self.audits[self.parent_name],key:value};self.archive.save(self.parent_name,audit)
            with self.subTest(key=key),self.assertRaises((KeyError,ValueError)):self.consume()

    def test_same_count_changed_content_is_not_an_event_partition(self):
        rows=copy.deepcopy(self.events);rows[0]['code']=1013
        self.observed_audit(self.parent_name,at(0),at(101),rows)
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_AUDIT_EVENT_SET'):self.consume()

    def test_gap_read_and_duplicate_event_cannot_be_hidden(self):
        rows=copy.deepcopy(self.events);rows[0]['utc']=at(14)
        self.observed_audit(self.parent_name,at(0),at(101),rows)
        item=self.parent['stages'][1]
        self.observed_audit('formal-audit-'+self.cid+'-'+item['mode']+'.json',item['startedAtUtc'],item['finishedAtUtc'],[],index=2)
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_AUDIT_GAP_OR_OMISSION'):self.consume()
        self.observed_audit(self.parent_name,at(0),at(101),[self.events[0],self.events[0]])
        with self.assertRaisesRegex(ValueError,'AUDIT_DUPLICATE'):self.consume()

    def test_source_clock_uncertainty_rejects_boundary_assignment(self):
        self.events[0]['utc']=at(12.999999);self.store()
        result=self.consume();self.assertEqual(result['sourceAuditCount'],2)
        # 末端再加1ns即落在半开窗口外。只改元数据不会改变事件或计数。
        audit=self.audits[self.parent_name];audit['errorBounds']['upperNs']=1
        self.archive.save(self.parent_name,audit)
        with self.assertRaisesRegex(ValueError,'OMQ_BATCH_AUDIT_CLOCK_AMBIGUOUS'):self.consume()


class GrantBoundaryTests(unittest.TestCase):
    def case(self,ttl=300,change=None):
        from workflow_oracle_mapping_identity_recovery import ROSTER
        roles=list(ROSTER);subjects={k:v[1] for k,v in ROSTER.items()};cid='c'*32;execution='e'*32
        permissions=[['mapping.read','mapping.source.validate','mapping.edit','mapping.validate','mapping.submit'],
                     ['mapping.read','mapping.source.validate','mapping.review','mapping.approve'],
                     ['mapping.read','mapping.source.validate','mapping.activate'],['data.query.execute','data.query.result.read','data.query.evidence.read']]
        obj='PRODUCTION/OMQ_ENTITY';fields=[obj+'/'+str(i)+'/'+n for i,n in enumerate('ROW_ID JOIN_KEY VAL ORG_ID SITE_ID EXT_ID LABEL FROM_TS TO_TS EVENT_TS OBSERVED_TS'.split(),1)]
        rows=[]
        for role,ops in zip(roles,permissions):
            for op in ops:
                scoped=op=='mapping.source.validate' or op.startswith('data.query.')
                rows.append(dict(Id='old-'+str(len(rows)),SubjectId=subjects[role],Permission=op,ConnectionId=cid if scoped else None,
                                 ObjectRefs=[obj] if scoped else [],FieldRefs=fields if scoped else [],SiteIds=['site-a'],OrganizationId='org-demo',
                                 RevokedAtUtc=None,ExpiresAtUtc=at(ttl)))
        if change:rows[0].update(change)
        original=copy.deepcopy(rows);writes=[]
        def read(sql,stage):return (str(dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp()) if 'clock' in stage else json.dumps(rows),'b'*32)
        def write(sql,stage):
            self.assertIn(b"now()+interval '4 hours'",sql);self.assertNotIn(b'UPDATE',sql)
            count=0
            for old in original:
                ident='omq-ah-'+e.digest_value([execution,cid,old['SubjectId'],old['Permission']])[:32]
                if ident.encode() in sql:
                    rows.append({**old,'Id':ident,'ExpiresAtUtc':at(14400)});count+=1
            writes.append(count);return str(count),'d'*32
        state=dict(taskId=e.TASK,runId=e.PRODUCT_RUN,scope=dict(organizationId='org-demo',siteIds=['site-a']),subjects=subjects,connectionId=cid)
        with patch.dict(os.environ,OMQ_PRODUCT_RUN=e.PRODUCT_RUN),patch.object(platform,'read_pg',side_effect=read),patch.object(platform,'pg_command',side_effect=write):
            result=platform.batch_grants(state,execution)
        self.assertTrue(all(old in rows for old in original));return result,writes

    def test_sufficient_current_fifteen_grants_are_read_only(self):
        result,writes=self.case();self.assertEqual(writes,[]);self.assertEqual(result['originalCount'],15)

    def test_expired_grants_append_exact_original_scope_and_preserve_history(self):
        result,writes=self.case(-1);self.assertEqual(writes,[5,4,3,3]);self.assertEqual(len(result['renewed']),4)

    def test_short_or_revoked_prestate_is_not_repaired(self):
        for ttl,change,reason in [(209,None,'BATCH_GRANT_TTL_SHORT'),(-1,dict(RevokedAtUtc=at(-2)),'BATCH_GRANT_NEGATIVE_PRESTATE')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):self.case(ttl,change)

if __name__=='__main__':unittest.main()
