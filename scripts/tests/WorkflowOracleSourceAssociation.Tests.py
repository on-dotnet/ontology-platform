"""由实际 AgentTests 子进程的 ILogger 装配生成完整夹具，再由生产消费者重开。"""
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/maintenance'))
from workflow_oracle_mapping_s2_contract import source_associations, source_clock_intervals, next_connection_admission


class SourceAssociationTests(unittest.TestCase):
    def test_ordinary_rejection_requires_fresh_same_connection_after_release(self):
        old,new='query-'+'a'*32,'query-'+'b'*32
        original=dict(queryId=old,connectionId='conn',fence=1,leaseOwnerHash='e'*64,
            executionStatus='FAILED',postFence=2,postLeaseOwnerHash=None,postLeaseUntilUtc=None,
            postErrorCode='query_binding_stale',errorCode='query_binding_stale',
            queryAudits=[dict(id='f',outcome='failure')],successfulQueryAudits=0,failedQueryAudits=1,
            restoredAtUtc='2026-11-22T12:00:00Z')
        def wire(value):
            raw=json.dumps(value)
            return dict(raw=raw,sha256=hashlib.sha256(raw.encode()).hexdigest(),httpStatus=200)
        refs=[dict(evidenceId=new+':'+str(i),sourceReadReceiptId='s'+str(i),connectionId='conn') for i in range(2)]
        fresh=dict(name='connection-rebound',queryId=new,**wire(dict(status='FOUND',evidence=refs,
                   subSources=[dict(sourceReadReceiptId=r['sourceReadReceiptId']) for r in refs])),
                   evidenceProofs=[dict(evidenceId=r['evidenceId'],**wire(dict(evidence=r,receipt=dict(queryId=new,
                       connectionId='conn',receiptId=r['sourceReadReceiptId'],status='SUCCESS',readCompletedAtUtc='2026-11-22T12:00:01Z')))) for r in refs])
        report=dict(oracleBinding=dict(connectionId='conn'),oracleCases=[fresh],
                    http=[dict(method='POST',path='/api/v1/data/semantic-queries',status=200,sha256=fresh['sha256'])])
        self.assertEqual(next_connection_admission(report,original)['nextQueryId'],new)
        for override in [dict(queryId=new),dict(connectionId='wrong'),dict(postFence=1),
                         dict(postLeaseOwnerHash='e'*64,postLeaseUntilUtc='2026-11-22T12:00:00Z',deadlineAtUtc='2026-11-22T12:00:00Z'),
                         dict(failedQueryAudits=0),dict(restoredAtUtc='2026-11-22T12:00:02Z')]:
            with self.subTest(override=override),self.assertRaises(ValueError):
                next_connection_admission(report,{**original,**override})
        with self.assertRaises(ValueError):
            next_connection_admission({**report,'http':[]},original)

    def current_test_host(self,target):
        import workflow_m2_build as build
        task = 'G4-ORACLE-MAPPING-QUERY-001'
        area = ROOT/'artifacts/workflow'/task
        import workflow_oracle_mapping_resume as resume
        import workflow_oracle_mapping_evidence as evidence
        binding, event = resume.bound_build(target)
        record = (area/(target+'-build-binding.json')).read_bytes()
        self.assertEqual(hashlib.sha256(record).hexdigest(), binding['receiptSha256'])
        command = json.loads(record)['command']
        project = Path(build.TARGETS[target])
        self.assertEqual(command[1:3], ['build', str(project)])
        host = Path(command[0])
        self.assertTrue(host.is_absolute() and host.is_file())
        selection = json.loads((ROOT/'docs/evidence'/task/'product-resume-01/s2-s3-01/final-machine-receipt.json').read_bytes())
        ref = (selection['metadata'].get('normalQueryBatch') or selection['metadata']['testSelection'])['prepare']
        archive = evidence.CurrentTestOriginals(ROOT, {'prepare': ref})
        raw = archive.raw('prepare.json')
        home = area/'environment'/ref['contentKey']
        prepare = home/'runs'/ref['attempt']/'receipt.json'
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
        ready = json.loads(raw)
        self.assertEqual(Path(ready['runDirectory']), prepare.parent)
        self.assertEqual(Path(ready['environmentDirectory']), home)
        self.assertEqual(ready['dotnet'], str(host))
        self.assertEqual(json.loads((home/'environment.json').read_bytes()), ready['environment'])
        evidence.environment_checks(archive, ROOT)
        assembly = ROOT/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
        return ready,host,assembly,event,ref

    def test_reopen_normal_http_failure_and_overflow(self):
        from workflow_oracle_mapping_resume import qualify_normal_projection
        from workflow_m2_evidence import mtp
        ready,host,assembly,_,_=self.current_test_host('query')
        with tempfile.TemporaryDirectory(dir=ready['environment']['TMPDIR']) as results:
            run=subprocess.run([str(host),str(assembly),'--filter','FullyQualifiedName~NormalTransportExportsBoundedOriginal',
                    '--minimum-expected-tests','2','--results-directory',results],cwd=results,timeout=30,check=True,
                    capture_output=True,env={**ready['environment'],'OMQ_NORMAL_OFFLINE_EXPORT':results})
            self.assertEqual(mtp(run.stdout+run.stderr,2),2)
            failed,=Path(results).glob('failure-*.json')
            overflow,=Path(results).glob('overflow-*.json')
            raw=failed.read_bytes()
            original=json.loads(raw)
            identity=dict(query_id=original['source']['queryId'],trace_id=original['traceId'],correlation=original['correlation'],
                          status=503,module=original['module'],process=original['process'],audit=[])
            key=failed.stem.split('-')[-1]
            self.assertEqual(qualify_normal_projection(raw,key,**identity)['firstFailure'],'tls.failed')
            for field in ('query_id','trace_id','correlation','module','process','status'):
                with self.subTest(field=field),self.assertRaises(ValueError):
                    qualify_normal_projection(raw,key,**{**identity,field:None})
            for stage in ('tls','cleanup','observer'):
                changed=copy.deepcopy(original)
                changed['source']['events']=[e for e in changed['source']['events']
                    if not (e['stage']==stage and (stage!='tls' or e['outcome']=='enter'))]
                with self.subTest(stage=stage),self.assertRaises(ValueError):
                    qualify_normal_projection(json.dumps(changed).encode(),key,**identity)
            with self.assertRaises(ValueError):
                qualify_normal_projection(raw,key,**{**identity,'audit':[{'clientId':'unrelated'}]})
            with self.assertRaises(ValueError):
                qualify_normal_projection(overflow.read_bytes(),overflow.stem.split('-')[-1],**identity)

    def test_q1_failure_consumer_validates_release_budget_and_execution(self):
        from unittest.mock import patch
        import workflow_oracle_normal_query as normal
        import workflow_oracle_mapping_resume as resume

        observation = normal.AREA/'normal-observation-f3d2efe12c984042a324c0f2cc133b30.json'
        row = json.loads(observation.read_bytes())
        export = normal.AREA/('normal-export-'+row['identity']['container']+'-'+row['key']+'.json')
        receipt = json.loads(export.read_bytes())
        stream = resume.BASE.parent/'commands'/resume.PRODUCT/receipt['commandId']/'stdout.txt'
        raw = stream.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '6af20f5eb2369c71d3f95133e2f9d51ccb7bf633e137d7990cffb92cad358bc2')
        self.assertEqual(normal.consume_observation(row)['status'], 'FAILURE_TRACED')
        for case in ('release', 'origin', 'execution', 'confirmed'):
            projection = json.loads(raw)
            events = projection['source']['events']
            if case == 'release':
                events[:] = [event for event in events if event['stage'] not in ('disposeConnection', 'PHYSICAL_RELEASE')]
            elif case == 'origin':
                next(event for event in events if event['stage'] == 'branch').update(originTick=None, budgetTicks=None)
            elif case == 'execution':
                next(event for event in events if event['stage'] == 'workCutoff')['execution'] = 'f' * 32
            else:
                next(event for event in events if event['stage'] == 'cleanup')['outcome'] = 'confirmed'
            changed = json.dumps(projection).encode()
            registered = dict(receipt, sizeBytes=len(changed), sha256=hashlib.sha256(changed).hexdigest())
            with self.subTest(case=case), patch.object(resume, 'load', return_value=registered), \
                    patch.object(Path, 'read_bytes', return_value=changed), self.assertRaises(ValueError):
                normal.consume_observation(row)

    def test_reopen_two_branches_emitted_by_agent_test_process(self):
        from workflow_m2_evidence import mtp
        ready,host,assembly,event,ref=self.current_test_host('agent')
        with tempfile.TemporaryDirectory(dir=ready['environment']['TMPDIR']) as results:
            result = subprocess.run([str(host),str(assembly),'--filter','FullyQualifiedName=OntologyPlatform.AgentTests.OracleRuntimeSourceEventsTests.ExportTwoCompleteSourceBranchesForOfflineReopen',
                                '--minimum-expected-tests','1','--results-directory',results],
                               cwd=results,timeout=60,env={**ready['environment'],'OMQ_OFFLINE_SOURCE_EVENTS_DIRECTORY':results},check=True,capture_output=True,text=True)
            self.assertEqual(mtp((result.stdout+result.stderr).encode(),1),1)
            print(f"AgentTests build={event['commandId']} prepare={ref['commandId']} "
                  f"dllSha256={hashlib.sha256(assembly.read_bytes()).hexdigest()} passed=1 skipped=0")
            artifact,=Path(results).rglob('oracle-offline-source-events.json')
            data=artifact.read_bytes()
        self.assertNotIn(b'private-sentinel',data)
        original=json.loads(data)
        epoch=dt.datetime(2026,11,22,10,tzinfo=dt.timezone.utc)
        def stamp(ms):
            return (epoch+dt.timedelta(milliseconds=ms)).isoformat()
        audits=dict(startUtc=stamp(-2),endUtc=stamp(200),errorBounds=dict(lowerNs=-90000,upperNs=90000),records=[])
        for index,table in enumerate([('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget')],1):
            audits['records'].append(dict(clientId=str(index)*32,instance='1',session=str(index),owner=table[0],table=table[1],
                                          code=0,action='SELECT',utc=stamp(index*30+3.5)))
        def samples(n):
            return [dict(hostBefore=n+i*1000000,hostAfter=n+i*1000000+20000,
                         remote=n+i*1000000+10000,monoBefore=n+i*1000000,monoAfter=n+i*1000000+20000) for i in range(5)]
        brackets=[dict(source=samples(n),api=samples(n+100)) for n in [1000000,10000000]]
        clocks=source_clock_intervals(brackets)
        self.assertEqual(source_associations(original,audits,clocks),'TWO_SOURCE_BRANCHES_RELEASED')
        for change in [lambda r: r['sourceEvents'][0].update(QueryId='wrong'),
                       lambda r: r['sourceEvents'][3].update(ExecutionId='f'*32),
                       lambda r: r['sourceEvents'].__delitem__(slice(16,None)),
                       lambda r: r['sourceEvents'].__delitem__(11),
                       lambda r: r['sourceEvents'][10].update(RemainingTicks=-1),
                       lambda r: r['sourceEvents'][13].update(DeadlineUtc=stamp(2000)),
                       lambda r: r.update(sourceEventsDropped=1),
                       lambda r: r['events'][0].update(queryId='wrong')]:
            damaged=copy.deepcopy(original)
            change(damaged)
            with self.assertRaises(ValueError):
                source_associations(damaged,audits,clocks)
        for fields in [dict(session='900'),dict(utc=stamp(130)),dict(utc=stamp(33.5)),dict(utc=stamp(63.001))]:
            damaged=copy.deepcopy(audits)
            damaged['records'][1].update(fields)
            with self.assertRaises(ValueError):
                source_associations(original,damaged,clocks)
        with self.assertRaises(ValueError):
            source_associations(original,audits,{**clocks,'api':[-1_000_000,1_000_000]})


if __name__ == '__main__':
    unittest.main()
