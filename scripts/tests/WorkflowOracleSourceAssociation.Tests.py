"""由实际 AgentTests 子进程的 ILogger 装配生成完整夹具，再由生产消费者重开。"""
import copy
import datetime as dt
import hashlib
import json
import os
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

    def test_reopen_two_branches_emitted_by_agent_test_process(self):
        assembly=ROOT/'backend/tests/OntologyPlatform.AgentTests/bin/Debug/net10.0/OntologyPlatform.AgentTests.dll'
        with tempfile.TemporaryDirectory() as results:
            subprocess.run(['dotnet',str(assembly),'--filter','FullyQualifiedName=OntologyPlatform.AgentTests.OracleRuntimeSourceEventsTests.ExportTwoCompleteSourceBranchesForOfflineReopen',
                                '--minimum-expected-tests','1','--results-directory',results],
                               cwd=results,env={**os.environ,'OMQ_OFFLINE_SOURCE_EVENTS_DIRECTORY':results},check=True,capture_output=True,text=True)
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
