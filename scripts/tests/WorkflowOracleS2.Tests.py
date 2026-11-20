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

class S2ConsumerTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
