"""新Oracle双表分发、单grant闭包、原子恢复和独立坏原件的离线回归。"""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
import workflow_oracle_mapping_s2 as s
import workflow_oracle_mapping_s2_contract as c
import workflow_execution as ex


def state():
    return dict(taskId=s.TASK,runId=s.RUN,scope=dict(organizationId='org-demo',siteIds=['site-a']),subjects={k:v[1] for k,v in s.ROSTER.items()},
        connectionId='a7913bb552eb4cd1a3f6eaf5b93cd619',catalog=dict(status='READY',connectionId='a7913bb552eb4cd1a3f6eaf5b93cd619',
        objects=[dict(schema=obj.split('/')[0],name=obj.split('/')[1],kind='TABLE',fields=[dict(ordinal=i,name=n) for i,n in enumerate(s.COLUMNS,1)]) for obj in s.OBJECTS]))


def grant(st,role,op,ident,scoped=True,expired=False):
    return dict(Id=ident,SubjectId=st['subjects'][role],Permission=op,OrganizationId='org-demo',SiteIds=['site-a'],ConnectionId=st['connectionId'] if scoped else None,
      ObjectRefs=s.OBJECTS if scoped else [],FieldRefs=s.FIELDS if scoped else [],ExpiresAtUtc='2026-11-20T04:00:00+00:00' if not expired else '2026-11-19T23:59:59+00:00',RevokedAtUtc=None)


def grant_bridge(directory, method, args):
    """离线分发回归仅替换时钟、数据库、登录及历史磁盘原件。"""
    import contextlib
    import shutil
    import workflow_oracle_mapping_continuity as continuity
    from uuid import uuid4
    root = Path(directory).resolve()
    batch = root/continuity.AREA/s.BATCH
    batch.mkdir(parents=True,exist_ok=True)
    implementation = batch.parent.parent/'implementation-01'
    st = state()
    st['batch'] = s.BATCH
    st['mappingReceipt'] = dict(mappingId='mapping',activationId='activation',activationRevision=1)
    ids = ['historical-'+str(i) for i in range(15)]
    st['combinedGrantIds'] = {role+':'+op:ident for (role,op),ident in zip(s.SCOPED,ids)}
    originals = [grant(st,role,op,ident,(role,op) in s.SCOPED,True)
                 for (role,op),ident in zip(s.SCOPED+s.WORKFLOW,ids,strict=True)]
    single = [{**row,'Id':'single-'+row['Id'],'ObjectRefs':s.OBJECTS[:1],'FieldRefs':s.FIELDS[:11]} for row in originals[:6]]
    initial = dict(epoch=106,clock=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp(),rows=single+originals,
                   audit=[dict(Resource=i,n=1,issued=1) for i in ids])
    # 补齐不参与本轮授权的既有行，结算测试同时核对75→90→105的完整闭集。
    initial['rows'].extend({**single[0], 'Id':'archived-'+str(i)} for i in range(54))
    if method == 'state':
        plan = 'scripts/maintenance/workflow-oracle-s2-runtime-plan.json'
        (root/plan).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/plan,root/plan)
        return st
    database = root/'pg.json'
    db = json.loads(database.read_bytes()) if database.exists() else copy.deepcopy(initial)
    commands = root/continuity.AREA.parent/'commands'/s.RUN
    def command_record(stage, body, out):
        ident = uuid4().hex
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        record = dict(commandId=ident,stage=stage,inputFingerprint=ex.sha(body),exitCode=0,classification='SUCCESS',
                      startedAtUtc=stamp,endedAtUtc=stamp,stdoutSha256=ex.sha(out.encode()))
        folder = commands/ident
        folder.mkdir(parents=True)
        (folder/'receipt.json').write_text(json.dumps(record))
        (folder/'stdout.txt').write_text(out)
        return ident
    def snapshot(_):
        body = b'BEGIN READ ONLY;\n'+s.grant_snapshot_sql(st)+b'\nCOMMIT;'
        ident = command_record('omq-pg-s23-grant-snapshot',body,json.dumps(db))
        return {**copy.deepcopy(db),'commandId':ident}
    def append(body,stage):
        items = json.loads((batch/('grant-plan-'+args[1]+'.json')).read_bytes())['planned']
        assert body == s.append_body(st,items,db['epoch'])[0]
        for item in items:
            expiry = dt.datetime.fromtimestamp(db['clock'] + 14400, dt.timezone.utc).isoformat()
            row = grant(st,item['role'],item['operation'],item['id'],item['kind']=='COMBINED')
            db['rows'].append({**row, 'ExpiresAtUtc':expiry})
            db['audit'].append(dict(Resource=item['id'],n=1,issued=1))
        db['epoch'] += len(items)
        database.write_text(json.dumps(db))
        return str(len(items)),command_record('omq-pg-'+stage,body,str(len(items)))
    def reopen(_,cid,run,argv,stage,key,seconds,archive):
        record = json.loads((commands/cid/'receipt.json').read_bytes())
        assert record['inputFingerprint'] == key and record['stage'] == stage
        return record,(commands/cid/'stdout.txt').read_bytes(),b''
    def pg(body,stage):
        if stage=='s23-current-catalog':
            out=json.dumps(st['catalog'])
            return out,command_record('omq-pg-'+stage,b'BEGIN READ ONLY;\n'+body+b'\nCOMMIT;',out)
        assert stage=='s23-current-activation'
        return json.dumps(dict(ActivationId='activation',ActivationRevision=1)),uuid4().hex
    with contextlib.ExitStack() as stack:
        for change in (patch.object(s.p,'ROOT',root), patch.object(s.p,'AREA',implementation),
                       patch.object(s,'check_grant_checkpoint',return_value=None),
                       patch.object(s,'accepted_registration',return_value=(initial,ids,ex.sha(ex.encoded({})))),
                       patch.object(s,'grant_rows',side_effect=snapshot),patch.object(s.p,'pg_command',side_effect=append),
                       patch.object(continuity,'command',side_effect=reopen),patch.object(s.p,'read_pg',side_effect=pg),
                       patch.object(s.p,'session_preflight',return_value={}),patch.object(s.p,'fixture_state',return_value=dict(counts=[1,1]))):
            stack.enter_context(change)
        if method=='consumer':
            report, = args
            class Originals:
                def __init__(self):
                    self.examined = {}
                    self.paths = {}

                def read(self,name):
                    if name.startswith('grant-plan-'): return json.loads((batch/name).read_bytes())
                    cid,leaf=name.split('-',1)
                    return json.loads((commands/cid/leaf).read_bytes())

                def command(self,cid,argv,stage,key,parent,origin):
                    assert origin==root and parent is None and argv[0]=='docker' and argv[-1]=='ON_ERROR_STOP=1'
                    row=self.read(cid+'-receipt.json');out=(commands/cid/'stdout.txt').read_bytes()
                    assert (row['stage'],row['inputFingerprint'],row['stdoutSha256']) == (stage,key,ex.sha(out))
                    return row,out,b''

            host=dict(services={'platform-pg':dict(containerId=continuity.PG)})
            c.reopen_grants(Originals(),report,host,root)
            return True
        return {'grants':s.grants,'ready':s.ready}[method](*args)


class S2GrantTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ,OMQ_PRODUCT_RUN=s.RUN));self.st=state()

    def test_scope_task_run_connection_and_missing_column_reject_before_io(self):
        for key,value in [('taskId','other'),('runId','implementation-01'),('connectionId','b'*32)]:
            bad=copy.deepcopy(self.st);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):s.scope(bad)
        bad=copy.deepcopy(self.st);bad['catalog']['objects'][1]['fields'].pop()
        with self.assertRaisesRegex(ValueError,'S2_FIELDS'):s.scope(bad)
        with patch.object(s.p,'read_pg',side_effect=AssertionError('I/O must not run')):
            with self.assertRaisesRegex(ValueError,'S2_MODE'):s.ready(self.st,[],'a'*32,'s2-doris-mapping')

    def test_renewal_refuses_counterexample_or_scope_drift_before_any_append(self):
        for change in ('revoked','field','short','expired-case','workflow','orphan','overlap'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                st = grant_bridge(tmp,'state',[])
                ids = list(st['combinedGrantIds'].values())+['historical-'+str(i) for i in range(6,15)]
                rows = [grant(st,role,op,ident,(role,op) in s.SCOPED,True)
                        for (role,op),ident in zip(s.SCOPED+s.WORKFLOW,ids,strict=True)]
                single=[{**r,'Id':'single-'+r['Id'],'ObjectRefs':s.OBJECTS[:1],'FieldRefs':s.FIELDS[:11]} for r in rows[:6]]
                live = dict(epoch=106,clock=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp(),
                            rows=single+rows,audit=[dict(Resource=i,n=1,issued=1) for i in ids])
                if change=='revoked': rows[0]['RevokedAtUtc']='2026-11-19T02:00:00+00:00'
                if change=='field': rows[5]['FieldRefs']=s.FIELDS[:-1]
                if change=='workflow': rows[-1]['ObjectRefs']=s.OBJECTS
                if change=='short': rows[8]['ExpiresAtUtc']='2026-11-20T00:10:00+00:00'
                if change=='expired-case': rows[3]['ExpiresAtUtc']='2026-11-19T23:59:55+00:00'
                if change=='overlap': live['rows'].append({**rows[1],'Id':'unknown','ExpiresAtUtc':'2026-11-20T04:00:00+00:00'})
                batch=root/'artifacts/workflow'/s.TASK/s.RUN/s.BATCH
                if change=='orphan': (batch/('permission-case-'+'a'*32+'.json')).write_text('{}')
                db=root/'pg.json';db.write_text(json.dumps(live));original=db.read_bytes()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    grant_bridge(tmp,'grants',[st,'b'*32,True,s.RUNTIME_PLAN])
                self.assertEqual(original,db.read_bytes())
                self.assertFalse(list(batch.glob('grant-plan-*.json')))

    def test_durable_accepted_checkpoint_detects_truncation_and_edited_expiry(self):
        import workflow_oracle_runtime_window as w
        prev = dict(rows=[],audit=[],epoch=106,clock=1)
        actual = dict(rows=[dict(Id='signed',ExpiresAtUtc='original')],audit=[dict(Resource='signed',issued=1)],epoch=121,clock=2)
        after = ex.encoded(actual)
        checkpoint = dict(before='b'*32,after='a'*32,epoch=121,rows=1,afterSha256=ex.sha(after),
                          executionId='e'*32,commandId='d'*32)
        def snapshot(cid):
            return {'a'*32:after,'b'*32:ex.encoded(prev)}[cid]
        with patch.object(w,'close_registration',return_value={'grantCheckpoint':checkpoint}):
            self.assertEqual(s.check_grant_checkpoint(snapshot,actual,'f'*32,None),'d'*32)
            self.assertIsNone(s.check_grant_checkpoint(snapshot,prev,'e'*32,{}))
            for value in [prev,{**actual,'rows':[dict(Id='signed',ExpiresAtUtc='different')]}]:
                with self.assertRaisesRegex(ValueError,'CHECKPOINT_ROLLBACK'):
                    s.check_grant_checkpoint(snapshot,value,'f'*32,None)

    def test_second_commit_recovers_from_previous_registered_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = grant_bridge(directory, 'state', [])
            first = grant_bridge(directory, 'grants', [original, 'a'*32, True, s.RUNTIME_PLAN])
            self.assertEqual((len(first['afterSnapshot']['rows']), first['afterEpoch']), (90,121))
            state_after_first = {**original, 'combinedGrantIds':first['combinedGrantIds'],
                                 'workflowGrantIds':first['workflowIds']}
            path = root/'pg.json'
            db = json.loads(path.read_bytes())
            db['clock'] += 14401
            path.write_text(json.dumps(db))
            second = grant_bridge(directory, 'grants', [state_after_first, 'b'*32, True, s.RUNTIME_PLAN])
            self.assertEqual((len(second['afterSnapshot']['rows']), second['afterEpoch']), (105,136))
            self.assertEqual(second['renewal']['basis'], first['grantCommand'])
            # 第二笔提交完成，但写回状态前退出。仍持第一笔ID时按两笔原事务重建，数据库零写入。
            committed = path.read_bytes()
            replay = grant_bridge(directory, 'grants', [state_after_first, 'c'*32, True, s.RUNTIME_PLAN])
            self.assertEqual(replay['renewal']['basis'], second['grantCommand'])
            self.assertEqual([t['commandId'] for t in replay['renewal']['transactions']],
                             [first['grantCommand'], second['grantCommand']])
            self.assertEqual((replay['combinedGrantIds'],replay['workflowIds'],replay['issued'],replay['grantCommand']),
                             (second['combinedGrantIds'],second['workflowIds'],[],None))
            self.assertEqual(path.read_bytes(), committed)
            with self.assertRaisesRegex(ValueError,'S2_PREPARE_REGISTERED_IDS'):
                grant_bridge(directory,'grants',[original,'d'*32,True,s.RUNTIME_PLAN])
            for change in ('epoch','principal','permission','revoked'):
                with self.subTest(change=change):
                    bad = json.loads(committed)
                    if change == 'epoch':
                        bad['epoch'] += 1
                    else:
                        key = {'principal':'SubjectId','permission':'Permission','revoked':'RevokedAtUtc'}[change]
                        bad['rows'][-1][key] = 'unexpected'
                    path.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):
                        grant_bridge(directory,'grants',[state_after_first,'d'*32,True,s.RUNTIME_PLAN])

    def test_single_grant_covers_all_fields_without_composition(self):
        row=grant(self.st,'reader','data.query.execute','full')
        self.assertTrue(s.covers(row,self.st,'reader','data.query.execute'))
        for fields in (s.FIELDS[:11],s.FIELDS[11:],s.FIELDS[:-1]):
            self.assertFalse(s.covers({**row,'FieldRefs':fields},self.st,'reader','data.query.execute'))

    def test_append_six_and_only_expired_workflow_preserving_fifteen(self):
        clock=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp()
        old=[{**grant(self.st,role,op,'old-'+str(i),expired=True),'ObjectRefs':s.OBJECTS[:1],'FieldRefs':s.FIELDS[:11]} for i,(role,op) in enumerate(s.SCOPED)]
        old += [grant(self.st,role,op,'old-flow-'+str(i),False,True) for i,(role,op) in enumerate(s.WORKFLOW)]
        before=dict(clock=clock,epoch=1,rows=old,audit=[],commandId='b'*32)
        issued=[];plans=[]
        def issue(sql,stage):
            planned=plans[0]['planned'];issued.extend(planned)
            return str(len(planned)),'c'*32
        def snapshot(_):
            if not issued:return copy.deepcopy(before)
            rows=old+[grant(self.st,item['role'],item['operation'],item['id'],item['kind']=='COMBINED') for item in issued]
            return dict(clock=clock+1,epoch=16,rows=rows,audit=[dict(Resource=item['id'],n=1,issued=1) for item in issued],commandId='d'*32)
        with patch.object(s,'grant_rows',side_effect=snapshot),patch.object(s.p,'read_pg',return_value=(json.dumps(self.st['catalog']),'a'*32)),\
             patch.object(s.p,'pg_command',side_effect=issue),patch.object(s.p,'save',side_effect=lambda path,row,*args:plans.append(row)):
            result=s.grants(self.st,'e'*32,True)
        self.assertEqual((len(issued),result['grantCount'],result['fieldCount']),(15,6,22));self.assertTrue(result['historyPreserved'])
        self.assertEqual(len({item['id'] for item in issued}),15)
        self.assertTrue(all(row['ObjectRefs']==s.OBJECTS and row['FieldRefs']==s.FIELDS for row in result['rows']))

    def test_short_revoked_or_incomplete_registered_grant_is_not_repaired(self):
        clock=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp()
        rows=[{**grant(self.st,role,op,'old-'+str(i)),'ObjectRefs':s.OBJECTS[:1],'FieldRefs':s.FIELDS[:11]} for i,(role,op) in enumerate(s.SCOPED)]
        self.st['combinedGrantIds']={role+':'+op:'combined-'+str(i) for i,(role,op) in enumerate(s.SCOPED)}
        rows += [grant(self.st,role,op,'combined-'+str(i)) for i,(role,op) in enumerate(s.SCOPED)]
        for change in ({'ExpiresAtUtc':'2026-11-20T00:00:30+00:00'},{'RevokedAtUtc':'2026-11-20T00:00:00+00:00'},{'FieldRefs':s.FIELDS[:-1]}):
            bad=copy.deepcopy(rows);bad[6].update(change)
            with self.subTest(change=change),patch.object(s.p,'read_pg',return_value=(json.dumps(self.st['catalog']),'a'*32)),\
                 patch.object(s,'grant_rows',return_value=dict(clock=clock,rows=bad)),patch.object(s.p,'pg_command',side_effect=AssertionError('must not renew')):
                with self.assertRaises(ValueError):s.grants(self.st,'a'*32,True)

    def test_natural_expiry_requires_live_poststate_and_unchanged_rows(self):
        base=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()/'implementation-01';base.mkdir()
        area=base.parent/s.RUN/s.BATCH;area.mkdir(parents=True)
        token='a'*32;ident='omq-s23-'+'b'*32;self.st['combinedGrantIds']={'reader:data.query.execute':ident}
        clock=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc).timestamp()
        row=grant(self.st,'reader','data.query.execute',ident);row['ExpiresAtUtc']='2026-11-20T00:00:05+00:00'
        before=dict(rows=[row],clock=clock+1,epoch=2,commandId='c'*32)
        record=dict(taskId=s.TASK,runId=s.RUN,action='expired',kind='execute',id=ident,after=row,afterSnapshot=before)
        path=area/('permission-expired-'+token+'.json');path.write_text(json.dumps(record))
        after={**before,'clock':clock+5,'commandId':'d'*32}
        with patch.object(s.p,'AREA',base),patch.object(s,'grant_rows',return_value=after):
            result=s.await_expiry(self.st,token)
        self.assertEqual(result['status'],'NATURALLY_EXPIRED')
        record['afterSnapshot']['clock']=clock+5;path.write_text(json.dumps(record))
        with patch.object(s.p,'AREA',base),patch.object(s,'grant_rows',side_effect=AssertionError('already expired')):
            with self.assertRaisesRegex(ValueError,'S2_EXPIRY_MUST_START_LIVE'):s.await_expiry(self.st,token)

    def test_equivalent_postgres_time_does_not_block_restore(self):
        row=grant(self.st,'reader','data.query.result.read','id');row['RevokedAtUtc']='2026-11-20T00:00:00.123450+00:00'
        actual={**row,'RevokedAtUtc':'2026-11-20T00:00:00.12345+00:00'}
        self.assertTrue(s.same_grant(row,actual))
        before={**row,'RevokedAtUtc':None}
        original=s.permission_sql(row['Id'],before,row,'revoke','a'*32,'b'*32)
        self.assertNotEqual(original,s.permission_sql(row['Id'],before,actual,'revoke','a'*32,'b'*32))
        actual['RevokedAtUtc']='2026-11-20T00:00:00.123451+00:00';self.assertFalse(s.same_grant(row,actual))


class S2SourceTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ,OMQ_PRODUCT_RUN=s.RUN))
        self.rows=[[ [1,1,'9999999999999999999999.999999','org-demo','site-a','omq-entity-1','entity','20260101000000000001','20260201000000000001','20260102000000123456','20260102000001654321'] ],
                   [ [2,1,'-9999999999999999999999.999999','org-demo','site-a','omq-target-2','target','20260101000000000001','20260201000000000001','20260103000000123456','20260103000001654321'] ]]

    def test_snapshot_preserves_null_position_and_rejects_missing_column(self):
        rows=copy.deepcopy(self.rows);rows[0][0][1]=None
        def query(sql,stage):
            self.assertIn(' null on null returning varchar2(500)',sql)
            side=0 if s.TABLES[0] in sql else 1
            return json.dumps(rows[side][0]),'a'*32
        with patch.object(s.p,'native_fixture_sql',side_effect=query):
            observed=s.source_snapshot()
            self.assertEqual(observed['rows'],rows);self.assertEqual(observed['projectionVersion'],2)
            rows[0][0].pop(1)
            with self.assertRaisesRegex(ValueError,'S2_SOURCE_COLUMN_COUNT'):s.source_snapshot()

    def test_every_variant_locks_and_checks_exact_rows_in_both_directions(self):
        for action in s.SOURCE_CASES:
            after=s.expected_case(action,self.rows,'a'*32)
            for left,right in ((self.rows,after),(after,self.rows)):
                sql=s.source_transaction(left,right)
                with self.subTest(action=action):
                    self.assertEqual(sql.count(' IN EXCLUSIVE MODE NOWAIT'),2)
                    self.assertIn('SQL%ROWCOUNT<>1',sql);self.assertIn('S2_VALUE_CONFLICT',sql);self.assertIn('EXCEPTION WHEN OTHERS THEN ROLLBACK',sql)
                    self.assertNotIn('DELETE FROM "PRODUCTION"."OMQ_ENTITY";',sql)

    def test_postcommit_snapshot_failure_runs_exact_token_restore(self):
        area=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve();base=area/'implementation-01';base.mkdir();(area/s.RUN/s.BATCH).mkdir(parents=True)
        (base/'window-05.json').write_text(json.dumps({'afterHash':[ex.sha(ex.encoded(group[0])) for group in self.rows]}))
        before=dict(rows=self.rows,hashes=[ex.sha(ex.encoded(group)) for group in self.rows],commandIds=[])
        injected=s.expected_case('near',self.rows,'a'*32);current=dict(rows=injected,hashes=[ex.sha(ex.encoded(group)) for group in injected],commandIds=[])
        calls=[]
        with patch.object(s.p,'AREA',base),patch.object(s.p,'active_source_record',return_value=dict(containerId='a'*64)),\
             patch.object(s.p,'fixture_state',return_value={**before,'counts':[1,1]}),patch.object(s.uuid,'uuid4',return_value=type('Id',(),{'hex':'a'*32})()),\
             patch.object(s,'source_snapshot',side_effect=[before,RuntimeError('after failed'),current,before]),\
             patch.object(s.p,'native_fixture_sql',side_effect=lambda sql,stage:(calls.append((sql,stage)) or ('','b'*32))):
            with self.assertRaisesRegex(RuntimeError,'after failed'):s.source_case('near')
        self.assertEqual([stage for _,stage in calls],['s23-source-near','s23-source-restore'])
        self.assertTrue((area/s.RUN/s.BATCH/('source-restore-'+'a'*32+'.json')).exists())

    def test_wrong_source_or_modified_keys_reject_before_dml(self):
        # 派生计划不允许把基线键当清理白名单；源身份不同也拒绝。
        after=s.expected_case('fanout-10',self.rows,'a'*32)
        self.assertEqual([row[0] for row in after[1][1:]],list(range(71001,71010)))
        with self.assertRaisesRegex(ValueError,'S2_INSERT_KEY'):s.source_transaction(self.rows,[self.rows[0],self.rows[1]+[[3,*self.rows[1][0][1:]]]])


class S2PlanTests(unittest.TestCase):
    def test_new_plan_keeps_each_budget_and_old_plan_bytes(self):
        plan=c.frozen_plan(ROOT)
        self.assertEqual(plan['deadlineSeconds'],3240)
        self.assertTrue(all(row['seconds']==180 for row in plan['stages'] if row['kind']=='product'))
        self.assertEqual(ex.sha((ROOT/'scripts/maintenance/workflow-oracle-auth-plan.json').read_bytes()),'826aa393316000c6bc3fe7ce9017eab8f71db21ceb895893e39d5a22cafeecc5')

    def test_unknown_mode_missing_cases_and_bad_scope_fail(self):
        report=dict(taskId=s.TASK,runId=s.RUN,batch=dict(planId=s.BATCH),mode='s2-oracle-queries',oracleCases=[])
        with self.assertRaisesRegex(ValueError,'S23_CASES_MISSING'):c.qualify(report)
        report['runId']='implementation-01'
        with self.assertRaisesRegex(ValueError,'S23_REPORT_OWNER'):c.qualify(report)


class S2ContinuationTests(unittest.TestCase):
    def test_prefix_consumes_formal_chain_and_refuses_missing_or_wrong_identity(self):
        import workflow_oracle_mapping_continuation as n
        old = dict(activationId='a1',activationRevision=1,mappingReleaseId='release-a',mappingId='mapping',
                   previousReleaseId=None,manifestHash='manifest-a',kind='PUBLISH',proposalId='p1',
                   activatedAtUtc='2026-11-21T13:52:19.4744354+00:00')
        b = dict(old,activationId='b2',activationRevision=2,previousReleaseId='release-a',mappingReleaseId='release-b',
                 manifestHash='manifest-b',proposalId='p2')
        restored = dict(old,activationId='a3',activationRevision=3,previousReleaseId='release-b',kind='ROLLBACK',proposalId='p3')
        binding = dict(activation=old,connectionId='c',catalogSnapshotId='s')
        state = dict(mappingReceipt=restored,catalogFingerprint='f')
        receipts = [dict(receipt=value,connection='c',catalog='s',fingerprint='f',command='command-'+str(i),check='check-'+str(i))
                    for i,value in enumerate((old,b,restored))]
        chain = dict(current=['a3',3,'release-a'],receipts=receipts)
        n.check_activation_chain(binding,state,dict(b,activatedAtUtc='2026-11-21T13:52:19.4744354Z'),chain)
        invalid = [dict(chain,receipts=receipts[::2]),dict(chain,current=['a1',1,'release-a']),
                   dict(chain,receipts=[receipts[0],dict(receipts[1],receipt=dict(b,activationId='wrong')),receipts[2]]),
                   dict(chain,receipts=[receipts[0],receipts[1],dict(receipts[2],connection='other')])]
        for wrong in invalid:
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError,'S23_PREFIX_'):
                n.check_activation_chain(binding,state,b,wrong)

    def test_suffix_preserves_budgets_and_exact_qualified_prefix(self):
        import workflow_oracle_mapping_continuation as n
        old=c.frozen_plan(ROOT);new=c.frozen_plan(ROOT,n.PLAN_ID)
        self.assertEqual(new['stages'],[old['stages'][0],*old['stages'][5:]])
        self.assertEqual(len(new['stages']),11);self.assertEqual(new['deadlineSeconds'],2520)
        self.assertEqual(new['qualifiedPrefix'],n.PREFIX)
        self.assertEqual(ex.sha((ROOT/'scripts/maintenance/workflow-oracle-s2-plan.json').read_bytes()),'d1ee6baf39fb0ea645313769c4da0c0751e4fd11cc2c76958e8e3f0105862ff9')
        with self.assertRaisesRegex(ValueError,'S23_PLAN_ID'):c.frozen_plan(ROOT,'arbitrary-suffix')
        area=Path(self.enterContext(tempfile.TemporaryDirectory()));(area/'scripts/maintenance').mkdir(parents=True)
        bad=copy.deepcopy(new);bad['stages'][1:3]=reversed(bad['stages'][1:3])
        (area/'scripts/maintenance/workflow-oracle-s2-access-plan.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'S23_FROZEN_PLAN'):c.frozen_plan(area,n.PLAN_ID)

    def test_resource_manifest_relocates_only_exact_content_addressed_original(self):
        import workflow_oracle_mapping_continuation as n
        root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        relative=Path('artifacts/workflow')/n.TASK/n.RUN/'formal-resources.json'
        current=root/relative;current.parent.mkdir(parents=True);current.write_bytes(b'current')
        raw=b'original';item=dict(path=str(relative),sha256=ex.sha(raw),sizeBytes=len(raw))
        with self.assertRaises(FileNotFoundError):n.frozen_member(root,item)
        backup=current.with_name('formal-resources-'+item['sha256']+'.json');backup.write_bytes(raw)
        self.assertEqual(n.frozen_member(root,item),raw);self.assertEqual(current.read_bytes(),b'current')
        backup.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'S23_PREFIX_ORIGINAL_CHANGED'):n.frozen_member(root,item)
        other=current.with_name('report.json');other.write_bytes(b'current')
        with self.assertRaisesRegex(ValueError,'S23_PREFIX_ORIGINAL_CHANGED'):n.frozen_member(root,{**item,'path':str(other.relative_to(root))})

    def test_frozen_build_files_accept_only_fixed_hash_size_and_task(self):
        import workflow_oracle_mapping_continuation as n
        root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        raw=b'historical binding';digest=ex.sha(raw);name='api-build-binding.json'
        base=Path('artifacts/workflow')/n.TASK;path=root/base/name;path.parent.mkdir(parents=True)
        path.write_bytes(b'current build differs');backup=path.with_name(path.stem+'-'+digest+path.suffix);backup.write_bytes(raw)
        item=dict(path=str(base/name),sha256=digest,sizeBytes=len(raw))
        with patch.dict(n.BUILD_ORIGINALS,{name:(digest,len(raw))}):
            self.assertEqual(n.frozen_member(root,item),raw)
            for bad in ({**item,'sha256':'0'*64},{**item,'sizeBytes':len(raw)+1}):
                with self.assertRaisesRegex(ValueError,'S23_PREFIX_BUILD_ORIGINAL'):n.frozen_member(root,bad)
            backup.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'S23_PREFIX_ORIGINAL_CHANGED'):n.frozen_member(root,item)
        self.assertEqual(path.read_bytes(),b'current build differs')

    def test_history_context_is_closed_to_exact_qualified_parent(self):
        import workflow_oracle_mapping_continuation as n
        self.assertIsNone(n.frozen_build_context(ROOT,{'commandId':'0'*32},None))
        dispatch=dict(commandId=n.PREFIX['commandId'],taskId=n.TASK,runId=n.RUN,testedCommit=n.PREFIX['measuredCommit'],
            mode=n.MODES[0],case='healthy',batch=dict(stageInputs=dict(mode='s2-s3-oracle',plan=dict(planId='s2-s3-01'))))
        for key,value in [('taskId','other'),('runId','other'),('testedCommit','0'*40),('mode','s2-oracle-access'),('case','other')]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'S23_PREFIX_BUILD_SCOPE'):
                n.frozen_build_context(ROOT,{**dispatch,key:value},None)
        altered=copy.deepcopy(dispatch);altered['batch']['stageInputs']['plan']['planId']='s2-s3-01-access-01'
        with self.assertRaisesRegex(ValueError,'S23_PREFIX_BUILD_SCOPE'):n.frozen_build_context(ROOT,altered,None)
        self.assertEqual(n.historical_backend_input(ROOT),'53bddbec15779aa28ad25dc3082986027dbc6586f289add3326be2342d3d15ea')

    def test_restarted_host_keeps_all_persistent_inputs_and_real_ids(self):
        import workflow_oracle_mapping_continuation as n
        import workflow_oracle_mapping_evidence as e
        # 只隔离结构解析器；比较器自身必须保留所有未明确允许的真实宿主字段。
        old=dict(resourceManifestSha256='a'*64,oracle=dict(containerId='source',imageId='image',networkId='net'),
            snapshotId='snapshot',composeSha256='compose',buildInputKey='input',buildOutputKey='output',runtimeHelperSha256='relay',ports=dict(api=15741),
            services={role:dict(containerId=role,pid=1,startedAt='old',imageId='image',mountSha256='mount',networks={'net':'id'}) for role in ('api','api-secondary','platform-pg')})
        new=copy.deepcopy(old);new['resourceManifestSha256']='b'*64
        for role,service in new['services'].items():
            service.update(pid=2,startedAt='new')
            if role.startswith('api'):service['containerId']='new-'+role
        with patch.object(e,'stable_host',side_effect=lambda value:value):
            result=n.resumed_host(old,new);self.assertEqual(result['services']['api']['current']['containerId'],'new-api')
            for kind in ('source','data-id','image','mount','network','snapshot','compose','input','output','relay','ports','new-field'):
                bad=copy.deepcopy(new)
                if kind=='source':bad['oracle']['containerId']='different'
                elif kind=='data-id':bad['services']['platform-pg']['containerId']='different'
                elif kind in ('image','mount','network'):bad['services']['api'][{'image':'imageId','mount':'mountSha256','network':'networks'}[kind]]='different'
                elif kind in ('snapshot','compose','input','output','relay'):bad[{'snapshot':'snapshotId','compose':'composeSha256','input':'buildInputKey','output':'buildOutputKey','relay':'runtimeHelperSha256'}[kind]]='different'
                elif kind=='ports':bad['ports']['api']=15742
                else:bad['unexpected']='different'
                with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'S23_PREFIX_FIXED_HOST_CHANGED'):n.resumed_host(old,bad)

    def test_published_graph_delta_rejects_missing_extra_modified_and_duplicate_rows(self):
        import workflow_oracle_mapping_continuity as n
        import doris_keep_fuseki as rdf
        from urllib.parse import urlparse
        old=[]
        for suffix in ('ontology','data'):
            old.append({key:dict(type='uri',value=value) for key,value in dict(g='urn:ontology-platform:release:'+n.OLD_RELEASE+':'+suffix,
                s='urn:subject:'+suffix,p='urn:predicate',o='urn:value').items()})
        frozen=dict(scan=dict(default=dict(rows=0,sha256=rdf.fingerprint([])),named=dict(rows=len(old),sha256=rdf.fingerprint(map(rdf.canonical,old)))))
        observed=copy.deepcopy(old)
        for row in old:
            new=copy.deepcopy(row);new['g']['value']=new['g']['value'].replace(n.OLD_RELEASE,n.NEW_RELEASE);observed.append(new)
        triples=[('Reading','http://www.w3.org/1999/02/22-rdf-syntax-ns#type','http://www.w3.org/2002/07/owl#Class'),
            ('hasReading','http://www.w3.org/1999/02/22-rdf-syntax-ns#type','http://www.w3.org/2002/07/owl#ObjectProperty'),
            ('hasReading','http://www.w3.org/2000/01/rdf-schema#domain','urn:synthetic:mapping:Asset'),
            ('hasReading','http://www.w3.org/2000/01/rdf-schema#range','urn:synthetic:mapping:Reading')]
        for subject,predicate,value in triples:
            observed.append({key:dict(type='uri',value=item) for key,item in dict(g='urn:ontology-platform:release:'+n.NEW_RELEASE+':ontology',
                s='urn:synthetic:mapping:'+subject,p=predicate,o=value).items()})
        self.assertEqual(n.expected_graphs([],observed,frozen)['namedRows'],8)
        for kind in ('missing','extra','modified','duplicate','old-drift','default'):
            bad=copy.deepcopy(observed);default=[]
            if kind=='missing':bad.pop()
            elif kind=='duplicate':bad.append(copy.deepcopy(bad[-1]))
            elif kind=='extra':bad.append({**bad[-1],'g':dict(type='uri',value='urn:unknown')})
            elif kind in ('modified','old-drift'):bad[-1 if kind=='modified' else 0]['o']['value']='urn:wrong'
            else:default=[{}]
            with self.subTest(kind=kind),self.assertRaises(ValueError):n.expected_graphs(default,bad,frozen)

    def test_graph_consumer_rejects_wrong_generation_without_reading_any_files(self):
        import workflow_oracle_mapping_continuity as n
        with patch.object(n,'raw',side_effect=AssertionError('must reject before reading')):
            for cid,stamp,pid in [('0'*64,*n.GENERATION),(n.FUSEKI,'2026-11-21T01:20:00Z',n.GENERATION[1]),(n.FUSEKI,n.GENERATION[0],1)]:
                with self.assertRaisesRegex(ValueError,'S23_GRAPH_GENERATION'):n.graph_qualification(ROOT,cid,stamp,pid)

    def test_api_build_refresh_keeps_data_generations_and_private_mounts(self):
        import workflow_oracle_mapping_access_refresh as n
        import workflow_oracle_mapping_evidence as e
        roles=('api','api-secondary','platform-pg','oracle','fuseki','rustfs','keycloak-test')
        old=dict(resourceManifestSha256='old',snapshotId='old',composeSha256='old',buildInputKey='old',buildOutputKey='old',runtimeHelperSha256='same',
            services={r:dict(containerId=r,pid=1,startedAt='old',mountSha256='old',imageId='image',networks={'net':'id'}) for r in roles if r!='oracle'},oracle={'containerId':'oracle'})
        new=copy.deepcopy(old)
        for field in ('resourceManifestSha256','snapshotId','composeSha256','buildInputKey','buildOutputKey'):new[field]='new'
        builds=[{t:dict(directory='snapshot/'+side+'/'+t) for t in ('api','agent','query')} for side in ('old','new')]
        states=[]
        for side in range(2):
            rows={}
            for role in roles:
                mounts=[dict(Type='bind',RW=False,Destination='/private',Source='/same-private')]
                if role.startswith('api'):
                    new['services'][role].update(containerId='new-'+role,pid=2,startedAt='new',mountSha256='new')
                    for dest,target in {'/app':'api',**({'/session-tests':'agent','/query-tests':'query'} if role=='api-secondary' else {})}.items():
                        mounts.append(dict(Type='bind',RW=False,Destination=dest,Source=str(ROOT/builds[side][target]['directory'])))
                rows[role]=dict(containerId=('new-' if side and role.startswith('api') else '')+role,pid=2 if side and role.startswith('api') else 1,
                    startedAt='new' if side and role.startswith('api') else 'old',imageId='image',networks={'net':'id'},mounts=mounts)
            states.append(rows)
        original=copy.deepcopy((old,new))
        with patch.object(e,'stable_host',side_effect=lambda value:value):
            self.assertTrue(n.compare_hosts(ROOT,old,new,*states,builds));self.assertEqual((old,new),original)
            for kind in ('data-pid','data-start','data-mount','data-net','query-writable','query-wrong','query-cover','private'):
                bad=copy.deepcopy(states[1])
                if kind.startswith('data-'):
                    field={'data-pid':'pid','data-start':'startedAt','data-mount':'mounts','data-net':'networks'}[kind];bad['oracle'][field]='drift'
                else:
                    mounts=bad['api-secondary']['mounts'];q=next(m for m in mounts if m['Destination']=='/query-tests')
                    if kind=='query-writable':q['RW']=True
                    elif kind=='query-wrong':q['Source']='/wrong'
                    elif kind=='query-cover':mounts.append({**q,'Destination':'/query-tests/child'})
                    else:mounts[0]['Source']='/different-private'
                with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'S23_REFRESH_'):n.compare_hosts(ROOT,old,new,states[0],bad,builds)

    def test_bound_inputs_rejects_ambiguous_and_missing_historical_bytes(self):
        import workflow_oracle_mapping_access_refresh as n
        import workflow_oracle_mapping_evidence as e
        self.enterContext(patch.object(e,'RUN',n.RUN))
        root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve();area=root/n.AREA;area.mkdir(parents=True)
        host=dict(snapshotId='old',composeSha256='compose',runtimeHelperSha256='relay')
        data=dict(taskId=n.TASK,runId=n.RUN,snapshotId='old',composeSha256='compose',relaySha256='relay',extra='one')
        old=area/'formal-api-inputs-old.json';old.write_text(json.dumps(data));(area/'formal-api-inputs.json').write_text(json.dumps({**data,'snapshotId':'new'}))
        self.assertEqual(n.bound_inputs(root,host),data)
        other=area/'formal-api-inputs-ambiguous.json';other.write_text(json.dumps({**data,'extra':'two'}))
        with self.assertRaisesRegex(ValueError,'OMQ_RUNTIME_ARTIFACT_MISSING'):n.bound_inputs(root,host)
        other.unlink();old.unlink()
        with self.assertRaisesRegex(ValueError,'OMQ_RUNTIME_ARTIFACT_MISSING'):n.bound_inputs(root,host)

    def test_repeat_preserves_first_generation_consumer(self):
        import workflow_oracle_mapping_repeat as n
        previous={'original':'unchanged','snapshotId':'same'};current={'snapshotId':'same','services':{'fuseki':dict(startedAt=n.c.GENERATION[0],pid=n.c.GENERATION[1])}}
        with patch.object(n.c,'lifecycle',return_value={'first':'original'}) as original:
            self.assertEqual(n.lifecycle(ROOT,previous,current),{'first':'original'})
            original.assert_called_once_with(ROOT,previous,current,None,None)

    def test_repeat_rejects_unknown_generation_before_reading(self):
        import workflow_oracle_mapping_repeat as n
        current={'snapshotId':'same','services':{'fuseki':dict(startedAt='2099-01-01T00:00:00Z',pid=1)}}
        with patch.object(n,'raw',side_effect=AssertionError('must reject before reading')):
            with self.assertRaisesRegex(ValueError,'S23_REPEAT_CURRENT_GENERATION'):n.lifecycle(ROOT,{'snapshotId':'same'},current)
            with self.assertRaisesRegex(ValueError,'S23_REPEAT_GRAPH_GENERATION'):n.graph_qualification(ROOT,n.c.FUSEKI,'2099-01-01T00:00:00Z',1)

    def test_grant_order_does_not_hide_value_or_microsecond_differences(self):
        row=grant(state(),'reader','data.query.execute','id')
        row['RevokedAtUtc']='2026-11-20T00:00:00.123450+00:00'
        reverse=dict(reversed(list(row.items())));reverse['RevokedAtUtc']='2026-11-20T00:00:00.12345Z'
        self.assertTrue(s.same_grant(row,reverse))
        for key,value in [('RevokedAtUtc','2026-11-20T00:00:00.123451Z'),('Id','other'),('FieldRefs',s.FIELDS[:11])]:
            with self.subTest(key=key):self.assertFalse(s.same_grant(row,{**reverse,key:value}))

    def test_prefix_compatibility_rejects_scope_and_executed_code_drift(self):
        import workflow_oracle_mapping_continuation as n
        import workflow_oracle_mapping_evidence as e
        from types import SimpleNamespace
        area=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve();originals={}
        for name in e.drivers(ROOT,'s2-s3-oracle'):
            originals[name]=e.git_original(ROOT,n.PREFIX['measuredCommit'],name)
            target=area/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
        frozen=dict(browserIdentity=dict(measuredDrivers={name:ex.sha(raw) for name,raw in originals.items()}))
        archive=SimpleNamespace(root=area,dispatch=dict(commandId=n.PREFIX['commandId'],mode=n.MODES[-1]))
        stage=dict(plan=dict(planId='s2-s3-01'))
        with patch.object(n,'_frozen_qualification',return_value=frozen),patch.object(e,'git_original',side_effect=lambda root,commit,name:originals[name]):
            self.assertTrue(n.compatible_prefix(archive,n.PREFIX['measuredCommit'],'s2-s3-oracle',stage))
            for key,value in [('commandId','a'*32),('mode','s2-oracle-access')]:
                saved=archive.dispatch[key];archive.dispatch[key]=value
                with self.assertRaisesRegex(ValueError,'S23_PREFIX_COMPAT_SCOPE'):n.compatible_prefix(archive,n.PREFIX['measuredCommit'],'s2-s3-oracle',stage)
                archive.dispatch[key]=saved
            changes=[('scripts/maintenance/workflow-oracle-s2.mjs','async function queries(ctx)','async function queries(wrong)'),
                ('scripts/maintenance/workflow-oracle-s2.mjs','approved.decision.decidedBy === reviewer','approved.decision.decidedBy !== reviewer'),
                ('scripts/maintenance/workflow-oracle-query-fixture.mjs','export function currentProjection(','export function wrongCurrentProjection('),
                ('scripts/maintenance/workflow_oracle_mapping_platform.py','def audit_window(','def wrong_audit_window('),
                ('scripts/maintenance/workflow_oracle_mapping_s2_contract.py','def result_case(','def wrong_result_case(')]
            for name,old,new in changes:
                path=area/name;raw=path.read_text();self.assertTrue(old in raw,name)
                path.write_text(raw.replace(old,new,1))
                with self.subTest(name=name),self.assertRaises(ValueError):n.compatible_prefix(archive,n.PREFIX['measuredCommit'],'s2-s3-oracle',stage)
                path.write_text(raw)


class S2ConsumerTests(unittest.TestCase):
    def test_current_reader_selection_matches_one_fresh_http_result(self):
        raw='{"status":"FOUND"}';digest=ex.sha(raw.encode());query={'capabilityId':'g4_resolve_entity'}
        history=dict(originQueryId='origin',currentQueryId='current',currentQueryHash=digest,selected=query)
        row=dict(name='aba-selection-current',queryId='current',query=query,httpStatus=200,sha256=digest,raw=raw)
        http=dict(method='POST',path='/api/v1/data/semantic-queries',status=200,sha256=digest)
        report=dict(historySelection=history,oracleCases=[row],http=[http])
        c.current_selection_receipt(report)
        for changed in ({'currentQueryId':'origin'},{'currentQueryHash':'0'*64},{'selected':{}}):
            with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'S23_CURRENT_READER_RESULT'):
                c.current_selection_receipt({**report,'historySelection':{**history,**changed}})
        for http_rows in ([],[http,http]):
            with self.assertRaisesRegex(ValueError,'S23_CURRENT_READER_HTTP'):
                c.current_selection_receipt({**report,'http':http_rows})

    def test_current_plan_requires_original_selection_header_on_success_and_conflict(self):
        from workflow_oracle_mapping_identity_recovery import ROSTER
        query={'filters':{'entityIri':'selected'}};raw='{"status":"FOUND"}';denied='{"code":"query_binding_stale"}'
        row=dict(name='aba-selection-current',queryId='selection',query=query,httpStatus=200,raw=raw,sha256=ex.sha(raw.encode()))
        history=dict(currentQueryId='selection',originQueryId='original',selected=query,currentQueryHash=row['sha256'],rejection=dict(raw=denied))
        http=dict(method='POST',path='/api/v1/data/semantic-queries',query=query,queryId='selection',status=200,sha256=row['sha256'],
                  subjectId=ROSTER['reader'][1],selectionQueryId='original')
        conflict={**http,'status':409,'queryId':None,'code':'query_binding_stale','sha256':ex.sha(denied.encode())}
        report=dict(batch=dict(planId='s2-s3-01-runtime-01'),oracleCases=[row],http=[http,conflict],historySelection=history)
        c.current_selection_receipt(report)
        for index in (0,1):
            for field in ('query','subjectId','selectionQueryId'):
                wrong=copy.deepcopy(report);wrong['http'][index][field]=None
                with self.assertRaisesRegex(ValueError,'SELECTION_CONTEXT'):c.current_selection_receipt(wrong)

    def test_seed_receipt_requires_current_reader_and_actual_request(self):
        from workflow_oracle_mapping_identity_recovery import ROSTER
        reader=ROSTER['reader'][1];query=dict(capabilityId=c.CAPABILITIES[2],relationshipIris=[c.RELATION],filters=dict(siteId='site-a',entityExternalId='omq-entity-1'))
        seed=dict(queryId='seed',query=query,resultHash=ex.sha(b'raw'),actor=reader,sessionHash='a'*64,executionId='parent')
        stored=dict(queryId='seed',resultHash=seed['resultHash'],subjectId=reader,sessionHash='a'*64,
                    requestHash=ex.sha(c.canonical(dict(query=query,selectionQueryId=None))))
        row=dict(name='aba-runtime-seed',query=query,queryId='seed',raw='raw',sha256=seed['resultHash'])
        http=dict(method='POST',path='/api/v1/data/semantic-queries',queryId='seed',query=query,status=200,subjectId=reader,selectionQueryId=None,sha256=row['sha256'])
        origin=dict(mode='s2-oracle-aba',batch=dict(executionId='parent'),runtimeQuery=seed,oracleCases=[row],http=[http],
                    scenarioReady=dict(session=dict(observations=[dict(subjectId=reader,sessionHash='a'*64)])))
        for mode in ('s2-oracle-aba','s2-oracle-connection'):
            report={**origin,'mode':mode};actual=dict(queryId='new',runtimeSeed=stored)
            c.runtime_seed(report,origin,actual)
            for field in stored:
                with self.subTest(mode=mode,field=field),self.assertRaisesRegex(ValueError,'SEED_STORED'):
                    c.runtime_seed(report,origin,{**actual,'runtimeSeed':{**stored,field:'old'}})
            for change in (dict(selectionQueryId='origin'),dict(queryId='other'),dict(subjectId='previous')):
                with self.assertRaisesRegex(ValueError,'SEED_HTTP'):
                    c.runtime_seed(report,{**origin,'http':[{**http,**change}]},actual)

    def test_four_action_windows_require_each_table_and_current_decider(self):
        from workflow_oracle_mapping_identity_recovery import ROSTER
        def at(i):return f'2026-11-21T01:00:00.{i:06}Z'
        def pair(i):
            return [dict(owner=o,table=t,utc=at(i+j),action='SELECT',code=0) for j,(o,t) in enumerate([('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget')])]
        counts=[2,1,1,2,8,0]
        names=['aba-runtime-seed','aba-selection-origin','aba-selection-current','mapping-aba-b','inflight-activation-aba','aba-history-and-selection']
        windows=[dict(name=n,expectedReads=k,audit=dict(clientId=None,records=[])) for n,k in zip(names,counts,strict=True)]
        windows[0]['audit']['records']=pair(1);windows[4]['audit']['records']=sum((pair(i) for i in (11,21,31,41)),[])
        auditor=ROSTER['auditor'][1];report=dict(oracleWindows=windows,batch=dict(planId='s2-s3-01'),scenarioReady=dict(session=dict(observations=[dict(subjectId=auditor,sessionHash='a'*64)])))
        original=dict(admittedAtUtc=at(10),events=[dict(utc=at(i)) for i in (20,30,50)],rollbackValidatedAtUtc=at(40),
                      activatedA=dict(proposalId='rollback'),activatedB=dict(proposalId='publish'),rollbackDecision=dict(
                          proposalId='rollback',submittedBy=ROSTER['operator'][1],decidedBy=auditor,sessionHash='a'*64,path='MappingApplicationService.DecideAsync'))
        c.aba_reads(report,original)
        for key in ('proposalId','decidedBy','sessionHash','path'):
            with self.assertRaisesRegex(ValueError,'CURRENT_DECISION'):
                c.aba_reads(report,{**original,'rollbackDecision':{**original['rollbackDecision'],key:'previous'}})
        for field,value in [('table','wrong'),('utc',at(31)),('code',1)]:
            bad=copy.deepcopy(report);bad['oracleWindows'][4]['audit']['records'][0][field]=value
            with self.assertRaisesRegex(ValueError,'TABLE_PAIR'):c.aba_reads(bad,original)
        windows[4]['expectedReads']=4
        with self.assertRaisesRegex(ValueError,'READ_PLAN'):c.aba_reads(report,original)

    def test_aba_phase_original_reopens_exact_claim_decision_binding_and_post_state(self):
        """纯原件消费者，不启动查询、映射命令、网络或数据库。"""
        deadline = '2026-11-21T00:00:05Z'
        b = dict(proposalId='bp', activationId='ba', mappingReleaseId='br', activationRevision=2)
        a = dict(proposalId='ap', activationId='aa', mappingReleaseId='ar', activationRevision=3)
        phases = []
        commands = []
        def sample(name, edge, resource, operation=None):
            index = len(phases) + 1
            phases.append(dict(phase=name, edge=edge, resourceId=resource, cancelled=False, queryId='q',
                utc='2026-11-21T00:00:00.'+str(index).zfill(3)+'Z', monotonicMs=index, deadlineAtUtc=deadline,
                remainingMs=5000-index, errorCode='query_binding_stale' if edge == 'ERROR' else None))
            if operation:
                phases[-1]['commandId'] = 'command-'+str(index)
                commands.append(dict(commandId=phases[-1]['commandId'], operation=operation))
        sample('CALLBACK', 'ENTER', 'bp')
        for name, begin, end, operation in [
                ('B_ACTIVATE','bp','ba','activate:bp'), ('ROLLBACK_VALIDATE_ENQUEUE','m','j','validate'),
                ('WORKER_RUN','j','j',None), ('ROLLBACK_JOB_READ','j','assessment',None),
                ('ROLLBACK_ASSESSMENT_READ','assessment','assessment',None), ('ROLLBACK_PROPOSE','assessment','ap','propose'),
                ('ROLLBACK_DECIDE','ap','ap','decide:ap'), ('A_ACTIVATE','ap','aa','activate:ap')]:
            sample(name, 'ENTER', begin, operation)
            sample(name, 'RETURN', end)
        sample('CALLBACK', 'RETURN', 'q')
        sample('FINAL_BINDING_CHECK', 'ENTER', 'q')
        sample('FINAL_BINDING_CHECK', 'ERROR', 'q')
        row = dict(queryId='q', mappingId='m', activatedB=b, activatedA=a, deadlineAtUtc=deadline,
                   diagnosticPhases=phases, diagnosticPhasesDropped=0, elapsedMs=99, queryAudits=[], successfulQueryAudits=0,
                   fence=1, leaseOwnerHash='a'*64, errorCode='query_binding_stale', executionStatus='RUNNING',
                   postFence=1, postLeaseOwnerHash='a'*64, postLeaseUntilUtc=deadline, postErrorCode=None,
                   failedQueryAudits=0, postStateStatus='READ', postStateMissing=[], postStateStartedAtUtc=deadline,
                   postStateFinishedAtUtc=deadline, postStateElapsedMs=0, events=[dict(utc=phases[-1]['utc'])], postCommands=commands,
                   postActive=dict(mappingId='m', releaseId='ar', activationId='aa', activationRevision=3),
                   postActivations=[dict(id=x['activationId'], proposalId=x['proposalId'], checkId=x['proposalId']+'c',
                       releaseId=x['mappingReleaseId'], activationRevision=x['activationRevision']) for x in (b, a)],
                   postChecks=[dict(id=x['proposalId']+'c', proposalId=x['proposalId'], status='PASS') for x in (b, a)])
        self.assertEqual(c.aba_diagnostics(row),'LEASE_HELD_NOT_QUALIFIED')
        settled = dict(row,executionStatus='FAILED',postFence=2,postLeaseOwnerHash=None,postLeaseUntilUtc=None,
                       postErrorCode='query_binding_stale',queryAudits=[dict(id='failure',outcome='failure')],failedQueryAudits=1)
        self.assertEqual(c.aba_diagnostics(settled),'FINAL_REJECTION_RELEASED')
        leftover = dict(settled,postErrorCode='query_timeout',postLeaseOwnerHash='a'*64,postLeaseUntilUtc=deadline)
        self.assertEqual(c.aba_diagnostics(leftover),'LEASE_HELD_NOT_QUALIFIED')
        for key in ('postFence','postLeaseOwnerHash','postLeaseUntilUtc','postErrorCode'):
            bad = dict(settled)
            del bad[key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError,'ROW_MISSING'):
                c.aba_diagnostics(bad)
        for bad in (dict(row,postFence=2), dict(row,postLeaseOwnerHash='b'*64),dict(row,postLeaseUntilUtc=None),
                    dict(row,postLeaseUntilUtc='2026-11-21T00:01:00Z'),dict(settled,postLeaseOwnerHash='a'*64,postLeaseUntilUtc=deadline),
                    dict(settled,queryAudits=[],failedQueryAudits=0),dict(settled,postErrorCode='query_forbidden')):
            with self.subTest(post=bad['postErrorCode']), self.assertRaises(ValueError):
                c.aba_diagnostics(bad)
        for label, change in [
                ('missing approval', lambda r: r['diagnosticPhases'].pop(14)),
                ('other claim', lambda r: r['diagnosticPhases'][6].update(resourceId='other')),
                ('wrong deadline', lambda r: r['diagnosticPhases'][1].update(remainingMs=5000)),
                ('wrong final cause', lambda r: r['diagnosticPhases'][-1].update(errorCode='query_timeout')),
                ('partial post-state', lambda r: r.update(postStateMissing=['query'])),
                ('wrong activation check', lambda r: r['postChecks'][0].update(proposalId='ap')),
                ('other command', lambda r: r['postCommands'][0].update(commandId='other'))]:
            bad = copy.deepcopy(row)
            change(bad)
            with self.subTest(label=label), self.assertRaises(ValueError):
                c.aba_diagnostics(bad)

    def healthy(self):
        import base64
        query_id='query-'+'1'*32;eid=query_id+':e-'+'2'*32;rid='read-'+'3'*32;release='release-'+'4'*32
        binding=dict(connectionId='a7913bb552eb4cd1a3f6eaf5b93cd619',mappingReleaseId=release,catalogSnapshotId='5'*32,
            activation=dict(activationId='activation-'+'6'*32,activationRevision=1))
        identity=dict(organizationId='org-demo',siteId='site-a',sourceNamespace='query-fixture-v1',externalId='omq-entity-1',
            effectiveTime={'from':c.time_value(c.FROM),'to':c.time_value(c.TO)})
        datum=dict(kind='entity',entityIri=c.ROOT_IRI,identity=identity,validTime=identity['effectiveTime'],typeIris=['urn:synthetic:mapping:Asset'],label=None,
            evidenceIds=[eid],properties=[dict(propertyIri='urn:synthetic:mapping:label',unit=None,value=dict(type='string',lexical='entity'),eventTime=c.time_value('2026-01-02T00:00:00.123456Z'),evidenceIds=[eid])])
        ref=dict(evidenceId=eid,connectionId=binding['connectionId'],mappingReleaseId=release,sourceCatalogSnapshotId=binding['catalogSnapshotId'],
            sourceReadReceiptId=rid,scope=dict(organizationId='org-demo',siteIds=['site-a']),precision='ROW_KEY',
            sourceDatasetRef='dataset-'+ex.sha(c.canonical(dict(snapshotId=binding['catalogSnapshotId'],schema='PRODUCTION',name='OMQ_ENTITY',kind='TABLE'))),
            validTime=dict(fromUtc=c.FROM,toUtc=c.TO),observedAtUtc='2026-11-20T00:00:00.200000Z',
            sourceRecordRef='key:'+base64.b64encode(c.canonical([dict(field='ROW_ID',value=dict(type='int64',lexical='1'))])).decode())
        data=dict(schemaVersion='g4.query-result.v1',status='FOUND',data=[datum],candidates=[],evidence=[ref],limited=False,traceId='trace',observedAtUtc='2026-11-20T00:00:00.300000Z',
            snapshot=dict(mappingReleaseIds=[release],sourceCatalogSnapshotIds=[binding['catalogSnapshotId']],capabilityId=c.CAPABILITIES[0],capabilityVersion='v1'),
            subSources=[dict(connectionId=binding['connectionId'],sourceReadReceiptId=rid,status='SUCCESS',watermarkKind='UNKNOWN',observedAtUtc='2026-11-20T00:00:00.200000Z')],diagnostics=[])
        receipt=dict(queryId=query_id,receiptId=rid,connectionId=binding['connectionId'],mappingReleaseId=release,originalCatalogSnapshotId=binding['catalogSnapshotId'],
            currentCatalogSnapshotId=binding['catalogSnapshotId'],activationId=binding['activation']['activationId'],activationRevision='1',watermarkKind='UNKNOWN',watermark=None,
            adapterVersion='oracle-query-v1',status='SUCCESS',rowCount=1,limited=False,manifestHash='a'*64,queryPlanHash='b'*64,resultHash='c'*64,traceId='trace',
            readStartedAtUtc='2026-11-20T00:00:00.100000Z',readCompletedAtUtc='2026-11-20T00:00:00.200000Z')
        proof=dict(schemaVersion='g4.source-evidence.v1',evidence=ref,receipt=receipt)
        row=dict(name='healthy-resolve',queryId=query_id,httpStatus=200,sourceCase=None,query=dict(timeoutMs=5000,maxRows=100,depth=1,capabilityId=c.CAPABILITIES[0],capabilityVersion='v1',mappingReleaseIds=[release]),
            evidenceProofs=[dict(evidenceId=eid,httpStatus=200,raw=json.dumps(proof),sha256=ex.sha(json.dumps(proof).encode()))])
        row.update(raw=json.dumps(data),bytes=len(json.dumps(data).encode()),sha256=ex.sha(json.dumps(data).encode()))
        return row,binding

    def test_real_shape_complete_evidence_and_resigned_bad_originals(self):
        row,binding=self.healthy();self.assertEqual(c.result_case(row,binding),'FOUND')
        for change in ('empty-evidence','empty-proofs','wrong-query','wrong-watermark','wrong-source-version','source-deadline','row-key','closed-reference','wrong-activation','target-key-on-root','target-dataset-on-root','source-effective-time'):
            bad=copy.deepcopy(row);data=json.loads(bad['raw']);proof=json.loads(bad['evidenceProofs'][0]['raw'])
            if change=='empty-evidence':data['evidence']=[]
            elif change=='empty-proofs':bad['evidenceProofs']=[]
            elif change=='wrong-query':proof['receipt']['queryId']='query-'+'f'*32
            elif change=='wrong-watermark':proof['receipt']['watermark']='invented'
            elif change=='wrong-source-version':proof['receipt']['adapterVersion']='doris-query-v1'
            elif change=='source-deadline':proof['receipt']['readStartedAtUtc']='2026-11-19T23:59:59.199999Z'
            elif change=='row-key':data['evidence'][0]['sourceRecordRef']='key:W10=';proof['evidence']=data['evidence'][0]
            elif change=='closed-reference':data['data'][0]['evidenceIds']=[]
            elif change=='target-key-on-root':
                import base64
                data['evidence'][0]['sourceRecordRef']='key:'+base64.b64encode(c.canonical([dict(field='ROW_ID',value=dict(type='int64',lexical='2'))])).decode();proof['evidence']=data['evidence'][0]
            elif change=='target-dataset-on-root':
                data['evidence'][0]['sourceDatasetRef']='dataset-'+ex.sha(c.canonical(dict(snapshotId=binding['catalogSnapshotId'],schema='CaseOwner',name='OmqTarget',kind='TABLE')));proof['evidence']=data['evidence'][0]
            elif change=='source-effective-time':data['evidence'][0]['validTime']['fromUtc']='2026-01-01T00:00:00.000002Z';proof['evidence']=data['evidence'][0]
            else:proof['receipt']['activationId']='activation-'+'f'*32
            if bad['evidenceProofs']:
                raw=json.dumps(proof);bad['evidenceProofs'][0].update(raw=raw,sha256=ex.sha(raw.encode()))
            raw=json.dumps(data);bad.update(raw=raw,sha256=ex.sha(raw.encode()),bytes=len(raw.encode()))
            with self.subTest(change=change),self.assertRaises(ValueError):c.result_case(bad,binding)

    def test_root_property_cannot_borrow_target_evidence(self):
        import base64
        row,binding=self.healthy();data=json.loads(row['raw']);root=data['data'][0]
        target=copy.deepcopy(data['evidence'][0]);target['evidenceId']=row['queryId']+':e-'+'7'*32;target['sourceReadReceiptId']='read-'+'8'*32
        target['sourceDatasetRef']='dataset-'+ex.sha(c.canonical(dict(snapshotId=binding['catalogSnapshotId'],schema='CaseOwner',name='OmqTarget',kind='TABLE')))
        target['sourceRecordRef']='key:'+base64.b64encode(c.canonical([dict(field='ROW_ID',value=dict(type='int64',lexical='2'))])).decode()
        endpoint,iri=c.identity('omq-target-2','omq-target-v1')
        data['data'].append(dict(kind='relationship',entityIri=c.ROOT_IRI,evidenceIds=[root['evidenceIds'][0],target['evidenceId']],relationshipIri=c.RELATION,
            validTime=root['validTime'],source=dict(entityIri=c.ROOT_IRI,identity=root['identity'],typeIris=root['typeIris']),target=dict(entityIri=iri,identity=endpoint,typeIris=['urn:synthetic:mapping:Reading'])))
        data['evidence'].append(target);data['subSources'].append({**data['subSources'][0],'sourceReadReceiptId':target['sourceReadReceiptId']})
        proof=json.loads(row['evidenceProofs'][0]['raw']);proof['evidence']=target;proof['receipt']['receiptId']=target['sourceReadReceiptId']
        raw=json.dumps(proof);row['evidenceProofs'].append(dict(evidenceId=target['evidenceId'],httpStatus=200,raw=raw,sha256=ex.sha(raw.encode())))
        row['name']='healthy-relations';row['query']['capabilityId']=data['snapshot']['capabilityId']=c.CAPABILITIES[2]
        raw=json.dumps(data);row.update(raw=raw,bytes=len(raw.encode()),sha256=ex.sha(raw.encode()))
        self.assertEqual(c.result_case(row,binding),'FOUND')
        root['properties'][0]['evidenceIds']=[target['evidenceId']]
        raw=json.dumps(data);row.update(raw=raw,bytes=len(raw.encode()),sha256=ex.sha(raw.encode()))
        with self.assertRaisesRegex(ValueError,'S23_PROPERTY_EXACT_ROOT_REFERENCE'):c.result_case(row,binding)

    def test_connection_patch_and_enable_have_distinct_versions(self):
        row=dict(taskId=s.TASK,resourceRun=s.RUN,case='CONNECTION_AFTER_READ',status='PASS',connectionId='a7913bb552eb4cd1a3f6eaf5b93cd619',subjectId=s.ROSTER['reader'][1],queryId='query-'+'a'*32,
            leaseOwnerHash='b'*64,fence=1,oldRevision=3,newRevision=4,restoredRevision=5,errorStatus=409,errorCode='query_binding_stale',executionStatus='FAILED',resultHash=None,
            resultSize=0,ciphertextBytes=0,committedReadReceipts=0,successfulQueryAudits=0,elapsedMs=301,admittedAtUtc='2026-11-20T00:00:00Z',deadlineAtUtc='2026-11-20T00:00:05Z',restoredAtUtc='2026-11-20T00:00:01Z')
        row['events']=[dict(phase=phase,sequence=i,queryId=row['queryId'],connectionId=row['connectionId'],utc='2026-11-20T00:00:00.'+str(i)+'00000Z',monotonicMs=i*100)
            for i,phase in enumerate(['SOURCE_READ_COMPLETED','CONNECTION_PATCH_COMMITTED','COMMIT_REJECTED'],1)]
        self.assertEqual(c.demand_connection_original(json.dumps(row).encode()),row)
        for change in ('wrong-restored-revision','late-reject','other-query','success-side-effect','restore-before-reject'):
            bad=copy.deepcopy(row)
            if change=='wrong-restored-revision':bad['restoredRevision']=4
            elif change=='late-reject':bad['events'][2]['utc']='2026-11-20T00:00:06Z'
            elif change=='other-query':bad['events'][1]['queryId']='query-'+'b'*32
            elif change=='success-side-effect':bad['successfulQueryAudits']=1
            else:bad['restoredAtUtc']=bad['events'][1]['utc']
            with self.subTest(change=change),self.assertRaises(ValueError):c.demand_connection_original(json.dumps(bad).encode())

    def test_native_statement_rollback_is_only_the_changed_row(self):
        st=state();before=grant(st,'reader','data.query.execute','omq-s23-'+'a'*32);after={**before,'FieldRefs':s.FIELDS[:-1]}
        sql=s.permission_sql(before['Id'],before,after,'field','b'*32,'c'*32)
        self.assertIn('AND to_jsonb(g)=',sql);self.assertIn("IF total<>1 THEN RAISE EXCEPTION",sql)
        self.assertIn('COMMIT; SELECT to_jsonb(g)',sql);self.assertEqual(sql.count('UPDATE governance."MappingAuthorizationGrants"'),1)


class S2CapacityTests(unittest.TestCase):
    def test_original_budget_program_and_global_bindings_remain_exact(self):
        import workflow_oracle_mapping_capacity as capacity
        capacity.validate_programs()
        with patch.object(capacity,'GIB',capacity.GIB+1):
            with self.assertRaisesRegex(ValueError,'CAPACITY_GLOBAL_BINDING_GIB'):capacity.validate_programs()
        with patch.object(capacity,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError,'CAPACITY_GLOBAL_BINDING_run'):capacity.validate_programs()

    def test_capacity_guard_rejects_budget_relaxation_and_double_credit(self):
        import workflow_oracle_mapping_capacity as capacity
        original=Path.read_bytes;path=Path(capacity.__file__);source=original(path)
        for before,after in [(b'require(total<=limit,',b'require(total<limit+1,'),
                (b'host_start-=cache_release[',b'host-=cache_release['),
                (b"reserved['newBuildEvidenceAndLogs'] = max(64*1024**2",b"reserved['newBuildEvidenceAndLogs'] = max(32*1024**2")]:
            bad=source.replace(before,after);self.assertNotEqual(bad,source)
            with self.subTest(change=after),patch.object(Path,'read_bytes',lambda p:bad if p==path else original(p)):
                with self.assertRaisesRegex(ValueError,'CAPACITY_'):capacity.validate_programs()

    def test_scoped_runtime_budget_and_sample_boundaries(self):
        import workflow_oracle_runtime_window as window
        g = window.GIB
        self.assertEqual(window.ceiling(), 40*g)
        self.assertEqual(window.choose(32*g), 40*g)
        self.assertEqual(window.choose(39*g), 48*g)
        with self.assertRaisesRegex(ValueError,'WINDOW_BUDGET_DEFICIT'):
            window.choose(42*g)
        sample = dict(totalBytes=42*g, hostFree=16*g, vmFree=28*g, hostMemory=5*g, vmMemory=4*g)
        window.allow_sample(sample, 48*g)
        for field,value in [('totalBytes',44*g),('hostFree',14*g),('vmFree',26*g),('vmMemory',3*g)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                window.allow_sample({**sample,field:value},48*g)

    def test_cold_window_selects_before_default_cap_and_requires_completed_admission(self):
        import workflow_oracle_mapping_resume as resume
        import workflow_oracle_runtime_window as window
        g = window.GIB
        total = 41 * g
        stamp = 'a' * 32
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            (area / window.BATCH).mkdir()
            def exercise_window(measure):
                def observe(roles):
                    self.assertEqual(roles, set(resume.APIS) | set(resume.recovery.ORIGINAL_IDS))
                    disk = measure()
                    cold = dict(taskId=s.TASK, runId=s.RUN, status='FORMAL_RESOURCE_READY',
                                attempt=stamp, expectedRunningRoles=[], resourceRunId='implementation-01',
                                phase=s.RUN, projectedWithHelper=dict(memory=14763950080, nanoCpus=10500000000),
                                platformDisk=disk)
                    (area / ('source-admission-' + stamp + '.json')).write_text(json.dumps(cold))
                    return cold

                with patch.object(window, 'AREA', area), patch.dict(os.environ, OMQ_PRODUCT_RUN=s.RUN):
                    with patch.object(resume, 'admit', side_effect=observe):
                        with window.open_window() as decision:
                            self.assertEqual((decision['openingBytes'], window.ceiling()), (total, 48*g))
                    self.assertEqual(window.ceiling(total), 40*g)
                    usage['containerWritableBytes']['layer'] += 1
                    with patch.object(resume, 'admit', side_effect=observe), self.assertRaisesRegex(ValueError, 'WINDOW_BUDGET_DEFICIT'):
                        with window.open_window():
                            self.fail('window opened above the fully reserved capacity')
                    with patch.object(resume, 'admit', side_effect=ValueError('HOST_FLOOR')), self.assertRaisesRegex(ValueError, 'HOST_FLOOR'):
                        with window.open_window():
                            self.fail('window opened after a physical admission failure')
                    self.assertEqual(len(list((area/window.BATCH).glob('window-*.json'))), 1)
                    self.assertEqual(window.ceiling(total), 40*g)
            import contextlib
            import workflow_oracle_mapping_capacity as cap
            data = area/'implementation-01'
            data.mkdir()
            files = {
                'platform-image-layer-closure-01': dict(taskId=s.TASK,imageSizes=[1]*6,sharedEmptyLayers=[1]*3,
                                                        deduplicatedImageUpperBytes=6,duplicateCompressedBytes=0),
                'recovery-01': dict(allocatedSourceBytes=1),
                'recovery-01-final': dict(status='EARLY_SOURCE_RECOVERY_PASS'),
                'formal-planned': dict(resourceAttempt='base'),
                'source-admission-base': dict(platformDisk=dict(allocations=dict(currentHostIncludingFirstBackup=0))),
                'formal-platform-size-basis': dict(sourceRawVolumeFacts=[dict(bytes=1)]*8,pgVolumeMetadataOnly=dict(a=1,b=1,c=1)),
                'source-create-01': dict(volume='original')}
            for name,value in files.items(): (data/(name+'.json')).write_text(json.dumps(value))
            usage = dict(volumesLogicalBytes=dict(original=1,replacement=1),platformVolumes={v:1 for v in cap.VOLUMES},
                         replacementVolumes={'replacement':1},containerWritableBytes={'layer':0})
            def measurement(stage, argv):
                if stage=='formal-worktrees': return 'worktree '+str(area)
                self.assertEqual(stage,'formal-host-bytes')
                return '\n'.join('0 '+p for p in argv[2:])
            with contextlib.ExitStack() as stack:
                for name,value in [('MEASURE_TREE',data),('current_storage',lambda *args:usage),('backup_allocation',lambda *args,**kw:0)]:
                    for module in (cap,cap.original_platform):
                        stack.enter_context(patch.object(module,name,value))
                stack.enter_context(patch.object(cap,'baseline_cache_release',return_value=dict(releasedBytes=0)))
                def measure(): return cap.disk_admission(area,data,measurement,phase=s.RUN,replacement={})
                base = measure()['totalBytes']
                usage['containerWritableBytes']['layer'] = total-base
                with self.assertRaisesRegex(ValueError,'FORMAL_TOTAL_DISK'): measure()
                exercise_window(measure)

    def test_mapping_restore_preserves_historical_host_and_grant(self):
        import workflow_oracle_runtime_window as w
        registry = json.loads(Path(w.__file__).with_name('workflow-oracle-runtime-close-registry.json').read_bytes())
        row, = [r for r in registry['generations'] if r['operation'] == '05ea4538c0934951b200728ee739ce60']
        restore = w.close_registration(row['sha256'])
        prior = w.close_registration(restore['previousSha256'])
        self.assertEqual(restore['kind'], 'MAPPING_RESTORE')
        self.assertNotIn('parentId', restore)
        self.assertEqual(prior['nextRestoreHost'], restore['hostId'])
        self.assertEqual(restore['grantCheckpoint'], prior['grantCheckpoint'])
        self.assertEqual(prior['grantCheckpoint']['rows'], 90)
        self.assertEqual(len(prior['maintenance']), 1)
        with self.assertRaisesRegex(ValueError,'WINDOW_RETIRED_HOST'):
            w.runtime_continuity(ROOT,{},dict(commandId='0'*32),dict(closeSha256=prior['sha256']))

    def test_mapping_restore_cannot_acquire_formal_parent(self):
        import workflow_oracle_runtime_window as w
        source = Path(w.__file__).with_name('workflow-oracle-runtime-close-registry.json')
        registry = json.loads(source.read_bytes())
        row = next(r for r in registry['generations'] if r.get('kind') == 'MAPPING_RESTORE')
        row['parentId'] = '0'*32
        with tempfile.TemporaryDirectory() as temp:
            corrupt = Path(temp)/'registry.json'
            corrupt.write_text(json.dumps(registry))
            with patch.object(ex,'ordinary',return_value=corrupt), self.assertRaisesRegex(ValueError,'WINDOW_RESTORE_REGISTRY'):
                w.close_registration(row['sha256'])

    def test_close_generation_rejects_wrong_original_resource_and_time(self):
        import workflow_oracle_runtime_window as w
        import workflow_oracle_mapping_continuity as c
        import workflow_oracle_mapping_access_refresh as refresh
        with patch.object(c,'raw',return_value=b'{}'), self.assertRaisesRegex(ValueError,'WINDOW_LAST_CLOSE_ORIGINAL'):
            w.last_close(ROOT)
        first='2026-11-21T11:52:00Z';stop='2026-11-21T11:55:00Z';start='2026-11-21T12:01:00Z'
        old=dict(containerId=c.FUSEKI,pid=4,startedAt=first)
        new={**old,'pid':5,'startedAt':start}
        common=dict(ids={'fuseki':c.FUSEKI},data={'fuseki':dict(id=c.FUSEKI,startedAt=first,after=dict(FinishedAt=stop))})
        for update,reason in [({'containerId':'wrong'},'RESTART_ORDER'),({'startedAt':stop},'RESTART_ORDER'),({'pid':0},'PRIOR_PROCESS')]:
            with self.subTest(update=update),patch.object(refresh,'observed_rows',side_effect=[({},dict(fuseki=old)),({},dict(fuseki={**new,**update}))]),patch.object(refresh,'snapshot_builds',return_value={}),self.assertRaisesRegex(ValueError,reason):
                w.compare_generation(ROOT,{'services':{}},{'services':{}},common,w.close_registration()['sha256'],None,None)
        with self.assertRaisesRegex(ValueError,'GENERATION'):
            w.published_graphs(c.FUSEKI,start,5,{},refs={},close_sha='0'*64)

    def test_measured_child_is_stopped_on_future_threshold_or_failed_sample(self):
        import subprocess
        import workflow_oracle_runtime_window as window
        g = window.GIB
        nominal = dict(totalBytes=41*g,hostFree=16*g,vmFree=28*g,hostMemory=5*g,vmMemory=4*g)
        ok = subprocess.CompletedProcess([],0,json.dumps(nominal).encode(),b'')
        limit = subprocess.CompletedProcess([],0,json.dumps({**nominal,'totalBytes':44*g}).encode(),b'')
        fail = subprocess.CompletedProcess([],2,b'',b'')
        for after in (limit,fail):
            with self.subTest(returncode=after.returncode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();(root/window.BATCH).mkdir()
                decision=dict(id='a'*32,ceiling=48*g)
                with patch.object(window,'AREA',root),patch.object(window,'policy',return_value=decision), \
                     patch.object(window.subprocess,'run',side_effect=[ok,after]),self.assertRaisesRegex(ValueError,'WINDOW_PROTECTED'):
                    with window.monitored('b'*32):
                        ex.run([sys.executable,'-B','-c','import time; time.sleep(20)'],root,task='WINDOW-TEST',
                               run_id='bounded',stage='protected-child',input_key='fixture',timeout=25)
                receipts=list(root.glob('artifacts/workflow/WINDOW-TEST/commands/bounded/*/receipt.json'))
                self.assertEqual(len(receipts),1)
                command=json.loads(receipts[0].read_bytes())
                self.assertEqual((command['classification'],command['signal'],command['processGroupTerminated']),('CANCELLED',9,True))
                samples=[json.loads(line) for line in next((root/window.BATCH).glob('samples-*')).read_text().splitlines()]
                self.assertEqual(samples[-1]['status'],'PROTECTIVE_EXIT')

    def test_capacity_extension_is_product_only_before_resource_io(self):
        import workflow_oracle_mapping_capacity as capacity
        for phase in (None,'closed','s0-recovery-01','s2-s3-02'):
            with self.subTest(phase=phase):
                with self.assertRaisesRegex(ValueError,'CAPACITY_PRODUCT_ONLY'):
                    capacity.before_product_source(ROOT,s.TASK,platform_stage=True,phase=phase)


class S2ReadinessTests(unittest.TestCase):
    @staticmethod
    def model():
        import workflow_oracle_mapping_readiness as r
        scope=copy.deepcopy(r.SCOPE);cid=r.CONNECTION;probe_id='a'*32;config_hash='f'*64;command_key='c'*64;actor=r.ROSTER['operator'][1]
        etag='"3-'+config_hash+'"';path='/api/v1/connections/'+cid
        before=dict(id=cid,displayName='Oracle model fixture',scope=scope,config=dict(type='ORACLE',profile=dict(host='oracle-source',port=2484,
            serviceName='FREEPDB1',username='FIXTURE_READER',tls=True,allowedOwners=['PRODUCTION','CaseOwner'])),configRevision=3,state='ACTIVE',
            secretConfigured=True,secretVersion=1,probeFresh=False,lastProbeId='b'*32,updatedAtUtc='2026-11-20T12:00:00+00:00')
        probe=dict(probeId=probe_id,connectionId=cid,configHash=config_hash,secretVersion=1,scope=scope,status='TEST_OK',
            stages=[dict(name=n,status='PASS',durationMs=ms,diagnosticCode=None) for n,ms in zip(['NETWORK','TLS','AUTH','READ_ONLY','METADATA'],[5,50,50,90,120])],
            startedAtUtc='2026-11-21T04:00:00.010000+00:00',completedAtUtc='2026-11-21T04:00:00.150000+00:00',expiresAtUtc='2026-11-21T04:10:00.010000+00:00',traceId='d'*32,stale=False)
        after={**before,'lastProbeId':probe_id,'probeFresh':True};parts=[]
        for method,url,data,tag in [('GET',path,before,etag),('POST',path+'/test',probe,etag),('GET',path,after,etag),('GET',path+'/probes/'+probe_id,probe,'')]:
            raw=json.dumps(data,separators=(',',':'));parts.append(dict(method=method,path=url,status=200,raw=raw,sha256=ex.sha(raw.encode()),etag=tag))
        db=dict(Id=probe_id,Owner=actor,ConnectionId=cid,OrganizationId='org-demo',SiteIds=['site-a'],Revision=3,ConfigHash=config_hash,SecretVersion=1,
            CommandKey=command_key,ActorJson=json.dumps(dict(subjectId=actor)),ReportJson=json.dumps(probe),ExpiresAtUtc=probe['expiresAtUtc'],Deadline=probe['completedAtUtc'])
        command=dict(Id=command_key,RequestHash='e'*64,ScopeJson=json.dumps(scope),ResultScopeJson=json.dumps(scope),ReceiptJson=json.dumps(probe),
            CreatedAtUtc=probe['startedAtUtc'],Etag=etag,StatusCode=200,ErrorCode=None)
        snapshot=dict(commandId='MODEL_NOT_A_COMMAND',value=dict(probe=db,connection=dict(Id=cid,Revision=3,ConfigHash=config_hash,SecretVersion=1,State='ACTIVE',LastProbeId=probe_id),
            commands=[command],audit=[dict(Id=str(i),Action=action,Outcome='allowed',Actor=actor,Resource='connection:'+cid,TraceId=probe['traceId'])
                for i,action in enumerate(['connection.probe.start','connection.probe.complete'])]))
        api={'modelOnly':True}
        return dict(taskId=s.TASK,runId='product-resume-01',mode='s2-oracle-access',batch=dict(planId='s2-s3-01-access-01'),inputBinding=dict(api=dict(services=dict(api=api))),
            http=[{k:v for k,v in part.items() if k not in ('raw','etag')} for part in parts],oracleReadiness=dict(actor=actor,api=api,http=parts,snapshot=snapshot),
            oracleWindows=[dict(name='oracle-current-api-readiness',expectedReads=0,startedAtUtc='2026-11-21T04:00:00+00:00',finishedAtUtc='2026-11-21T04:00:01+00:00')])

    def test_formal_model_accepts_cumulative_equal_phase_times(self):
        import workflow_oracle_mapping_readiness as r
        self.assertEqual(r.qualify(self.model())['status'],'TEST_OK')

    def test_probe_cannot_change_connection_or_forge_command_link(self):
        import workflow_oracle_mapping_readiness as r
        for name in ('etag','command','scope','updated-time','source-read','wrong-api','failed-phase'):
            bad=self.model();item=bad['oracleReadiness']
            if name=='etag':item['http'][1]['etag']='"3"'
            elif name=='command':item['snapshot']['value']['commands'][0]['Id']='d'*64
            elif name=='scope':item['snapshot']['value']['commands'][0]['ScopeJson']=json.dumps(dict(organizationId='org-demo',siteIds=['site-b']))
            elif name=='source-read':bad['oracleWindows'][0]['expectedReads']=1
            elif name=='wrong-api':item['api']={'modelOnly':'another'}
            else:
                idx=2 if name=='updated-time' else 1;part=item['http'][idx];data=json.loads(part['raw'])
                if name=='updated-time':data['updatedAtUtc']='2026-11-21T04:00:00+00:00'
                else:data['stages'][3]['status']='FAIL'
                raw=json.dumps(data,separators=(',',':'));part.update(raw=raw,sha256=ex.sha(raw.encode()));bad['http'][idx]['sha256']=part['sha256']
            with self.subTest(case=name),self.assertRaises(ValueError):r.qualify(bad)


if __name__=='__main__':unittest.main()
