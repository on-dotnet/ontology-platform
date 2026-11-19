"""只消费本任务新 TCPS 源与准确 connections 构建。夹具写者独立提交，并还原初始行。"""
import argparse
import datetime as dt
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import workflow_execution as ex
import workflow_m2_build as build
from workflow_m2_evidence import mtp
from workflow_oracle_mapping_query import structural
from workflow_oracle_mapping_resources import before_source, require, PROBE, RUN, TASK

ROOT = Path(__file__).resolve().parents[2]


def probe_args(root, task, attempt, network, reader, sync, test):
    """两类短场景共享相同 CPU、内存、安全和挂载配置。"""
    return ['create','--pull=never','--read-only','--network',network,'--user',str(os.getuid()),
              '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--cap-drop=ALL',
              '--security-opt=no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728',
              '--label','ontology.task='+task,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
              '--mount','type=bind,source='+str(root/'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0')+',target=/app,readonly',
              '--mount','type=bind,source='+str(reader)+',target=/run/fixture,readonly',
              '--mount','type=bind,source='+str(sync)+',target=/run/sync',
              '--env','G4_ORACLE_MAPPING_TASK='+task,'--env','DOTNET_CLI_TELEMETRY_OPTOUT=1',
              '--env','TESTINGPLATFORM_TELEMETRY_OPTOUT=1','--env','XDG_DATA_HOME=/tmp/data',
              '--ulimit','core=0','--workdir','/tmp','--entrypoint','dotnet',PROBE,'/app/OntologyPlatform.ConnectionsTests.dll',
              '--filter','FullyQualifiedName~'+test,'--minimum-expected-tests','1',
              '--results-directory','/tmp/test-results','--no-ansi','--progress','off','--output','Detailed']


def snapshot(root, task, attempt, replacement=False):
    require(task == TASK and re.fullmatch(r'snapshot-[0-9]{2}',attempt), 'SNAPSHOT_ID')
    structural(root,task,'source')
    area = ex.ordinary(root/'artifacts/workflow'/task/RUN)
    private = ex.ordinary(root/'.tools/security/g4-oracle-mapping-query-001'/RUN)
    sync = private/attempt
    output = area/(attempt+'.json')
    require(not sync.exists() and not output.exists(), 'ORIGINAL_EXISTS')
    target = json.loads((area/'source-create-01.json').read_bytes())
    source = target['containerId']
    network = target['network']
    reader = private/'reader'
    if replacement:
        recovered = json.loads((area/'recovery-01-resume.json').read_bytes())
        require(recovered['originalId'] == source and recovered['beforeHash'] == recovered['restoredHash'], 'RESTORED_SOURCE_BINDING')
        source = recovered['replacementId']
        network = recovered['network']
        reader = private/'cold-01/reader'
    sample = before_source(root,task,source)
    binding = build.validate('connections',task)
    record = dict(taskId=task,runId=RUN,attempt=attempt,startedUtc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  sourceId=source,resourceAttempt=sample['attempt'],build=binding,status='STARTED',commands=[])
    docker = ['docker','--context','desktop-linux']
    sync.mkdir(mode=0o700)
    cid = None
    updated = False

    def save():
        temp = output.with_suffix('.pending')
        temp.write_text(json.dumps(record,indent=2)+'\n')
        temp.replace(output)

    def call(stage, args, stdin=None, timeout=20, cleanup=False):
        p = ex.run(docker+args,root,task=task,run_id=RUN,stage=stage,timeout=timeout,stdin=stdin,cleanup=cleanup)
        record['commands'].append(dict(stage=stage,command=p.receipt))
        return p

    def ok(stage, args, stdin=None, cleanup=False):
        result = call(stage,args,stdin,cleanup=cleanup)
        require(result.returncode==0,stage)
        return result.stdout.decode().strip()

    def sql(stage,text,cleanup=False):
        body = ('whenever sqlerror exit failure rollback\nset echo off heading off pages 0 lines 500 feedback off verify off tab off\n'
                +'alter session set container=FREEPDB1;\n'+text+'\nexit success\n').encode()
        return ok(stage,['exec','-i',source,'sqlplus','-s','/ as sysdba'],body,cleanup)

    def rows(stage):
        # 两表全行、确定排序及固定时间/小数投影，哈希在宿主计算。
        selects = []
        for table in ['"PRODUCTION"."OMQ_ENTITY"','"CaseOwner"."OmqTarget"']:
            selects.append("select json_array(ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,"
                           +','.join("to_char("+col+",'YYYY-MM-DD HH24:MI:SS.FF6')" for col in ['FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS'])
                           +" returning varchar2(500)) from "+table+" order by ROW_ID;")
        raw = sql(stage,'\n'.join(selects))
        data = [json.loads(line.strip(),parse_float=str) for line in raw.splitlines() if line.strip()]
        require(len(data)==2 and [row[0] for row in data]==[1,2], 'FIXTURE_CARDINALITY')
        return [ex.sha(ex.encoded(row)) for row in data]

    def change(stage,old,new,cleanup=False):
        require({old,new}=={'entity','entity-after-commit'},'WRITER_VALUES')
        statement = """begin
            update "PRODUCTION"."OMQ_ENTITY" set LABEL='%s' where ROW_ID=1 and EXT_ID='omq-entity-1' and LABEL='%s';
            if sql%%rowcount<>1 then raise_application_error(-20002,'synthetic key state'); end if;
            commit;
        end;
        /""" % (new,old)
        sql(stage,statement,cleanup)

    def identity():
        value = ok('snapshot-probe-identity',['inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}',cid])
        parts = value.split('|')
        require(parts[:3]==[cid,PROBE.split('@')[1],attempt],'SNAPSHOT_PROBE_IDENTITY')
        return parts[-1]

    try:
        initial = rows('snapshot-original-rows')
        record['beforeRowHashes']=initial
        argv=probe_args(root,task,attempt,network,reader,sync,'OracleMappingSnapshotTests')
        cid=ok('snapshot-probe-create',argv)
        require(re.fullmatch(r'[0-9a-f]{64}',cid),'SNAPSHOT_PROBE_ID')
        record['probeId']=cid; record['argvSha256']=ex.sha(ex.encoded(argv));save()
        require(identity()=='created','SNAPSHOT_PROBE_PRESTATE')
        with ThreadPoolExecutor(max_workers=1) as pool:
            testing = pool.submit(call,'snapshot-real-driver',['start','-a',cid],None,45)
            deadline = time.monotonic()+35
            while time.monotonic()<deadline and not testing.done():
                if (sync/'first-read').is_file():
                    execution=(sync/'first-read').read_text()
                    if not re.fullmatch('[a-f0-9]{32}',execution):
                        time.sleep(.01)
                        continue
                    change('snapshot-independent-commit','entity','entity-after-commit')
                    updated=True
                    (sync/'committed').write_text(execution)
                    record['execution']=execution
                    break
                time.sleep(.01)
            result=testing.result()
        record['testExitCode']=result.returncode
        require(result.returncode==0 and updated and identity()=='exited','SNAPSHOT_TEST_FAILED')
        require(mtp(result.stdout+result.stderr,1)==1,'SNAPSHOT_COUNT')
        require(build.validate('connections',task)==binding,'SNAPSHOT_BUILD_CHANGED')
        record['status']='PASS'
    except BaseException as e:
        record.update(status='FAIL',reason=str(e))
        raise
    finally:
        try:
            if updated:
                change('snapshot-restore-exact-key','entity-after-commit','entity',True)
            if 'beforeRowHashes' in record:
                record['afterRowHashes']=rows('snapshot-restored-rows')
                require(record['afterRowHashes']==record['beforeRowHashes'],'SNAPSHOT_RESTORE')
            if cid:
                require(identity() in ('created','exited'),'SNAPSHOT_PROBE_STILL_RUNNING')
                ok('snapshot-probe-remove',['rm',cid],cleanup=True)
                require(not ok('snapshot-probe-absent',['ps','-aq','--no-trunc','--filter','id='+cid],cleanup=True),'SNAPSHOT_PROBE_REAPPEARED')
                record['probeRemoved']=True
        except BaseException as cleanup_error:
            record.update(status='FAIL',cleanupReason=str(cleanup_error))
            raise
        finally:
            record['endedUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
            save()
    return dict(taskId=task,status=record['status'],attempt=attempt)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--task',required=True)
    cli.add_argument('--attempt',required=True)
    cli.add_argument('--replacement',action='store_true')
    args=cli.parse_args()
    print(json.dumps(snapshot(ROOT,args.task,args.attempt,args.replacement)))
