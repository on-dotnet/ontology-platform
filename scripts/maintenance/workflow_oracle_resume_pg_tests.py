"""在当前批次准确替代 PG 和已登记副 API 内执行三个 PG 锁反例与两个正式对照。"""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import workflow_execution as ex
import workflow_m2_build as build
import workflow_oracle_mapping_checkpoint as checkpoint
import workflow_oracle_mapping_platform as platform

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-ORACLE-MAPPING-QUERY-001'
RUN = 'product-resume-01'
AREA = ROOT / 'artifacts/workflow' / TASK / RUN
PROJECT = 'ontology-g4-omq-product-resume-01'
PG = '79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545'
FIXTURE_HASH = '5f5e12e5ddb269f145bd60f8f47b5ce9991ef51cbe5c84b56e5e9bee276a2a9f'
HOLD = 'query-18b5ee00b53e4e4eafc43cc4717bd293'
OWNER = TASK + ':implementation-01:'
TESTDIR = ROOT / Path(build.TARGETS['query']).parent / 'bin/Debug/net10.0'
SOURCE = Path(__file__).with_suffix('.cs.txt')
MIB = 1024**2
DOCKER = ['docker', '--context', 'desktop-linux']
CASES = [('G4OracleSettlementTests.OriginalCutoffIsCheckedAfterPostgresRowLock', 3),
         ('G4QueryRaceTests.OracleTerminalOwnerSurvivesSweepAndRejectsStaleConfirmation', 1),
         ('G4QueryRaceTests.RevocationBlocksAtomicResultAndAudit', 1)]


def need(ok, name):
    if not ok:
        raise ValueError('OMQ_RESUME_PG_' + name)


def digest(path):
    return ex.sha(ex.ordinary(path).read_bytes())


def command(stage, argv, input_key, *, payload=None, seconds=24, cleanup=False):
    key = ex.sha(ex.encoded([input_key, argv, ex.sha(payload or b''), digest(Path(__file__))]))
    return ex.run(argv, ROOT, task=TASK, run_id=RUN, stage='resume-pg-'+stage, input_key=key,
                  stdin=payload, timeout=seconds, cleanup=cleanup)


def build_driver():
    """只使用已锁定 Roslyn、官方本地引用包及当期 QueryTests 中的 Npgsql；不 restore。"""
    need(os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'RUN_SCOPE')
    choices = list((AREA.parent/'environment').glob('*/runs/*/receipt.json'))
    need(bool(choices), 'PREPARED')
    ready = next((v for v in (json.loads(p.read_bytes()) for p in choices)
                  if v.get('taskId') == TASK and v.get('status') == 'DEPENDENCIES_READY' and v.get('worktree') == str(ROOT)), None)
    need(ready is not None, 'PREPARED_OWNER')
    sdk = Path('/usr/local/share/dotnet')
    compiler = sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'
    refs = [p for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref')
            for p in sorted((sdk/'packs'/pack/'10.0.13/ref/net10.0').glob('*.dll'))] + [TESTDIR/'Npgsql.dll']
    need(len(refs) > 100 and Path(ready['dotnet']).resolve() == (sdk/'dotnet').resolve(), 'COMPILER')
    basis = dict(source=digest(SOURCE),compiler=digest(compiler),references=ex.sha(ex.encoded([(str(p),digest(p)) for p in refs])))
    fp = ex.sha(ex.encoded(basis))
    dest = AREA/('pg-driver-'+uuid.uuid4().hex)
    dest.mkdir(mode=0o700, parents=True)
    dll = dest/'IsolatedPgTests.dll'
    argv = ['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',ready['dotnet'],str(compiler),
            '-nologo','-target:exe','-deterministic+','-nostdlib+','-nullable:enable','-out:'+str(dll),
            *['-r:'+str(p) for p in refs],str(SOURCE)]
    result = ex.run(argv,ROOT,task=TASK,run_id=RUN,stage='resume-pg-driver-build',environment=ready['environment'],input_key=fp,timeout=45)
    row = dict(taskId=TASK,runId=RUN,inputs=basis,fingerprint=fp,commandId=result.receipt['commandId'],exitCode=result.returncode)
    if not result.returncode: row['dllSha256']=digest(dll)
    platform.save(dest/'build.json',row)
    need(result.returncode==0, 'DRIVER_BUILD_'+result.receipt['commandId'])
    return dest/'build.json'


# 容器私有路径之外只使用两份只读绑定。删除目标限定为本次新建、无重用机会的 nonce 目录。
BOOT = """set -eu
umask 077
case "$1" in *[!a-f0-9]*|'') exit 2 ;; esac
test "${#1}" -eq 12
d="/tmp/omq-pg-$1"
mkdir -m 700 "$d"
trap 'rm -rf -- "$d"' EXIT
cd "$d"
for f in /app/*.dll; do ln -s "$f" .; done
cat > IsolatedPgTests.dll
echo "$4  IsolatedPgTests.dll" | sha256sum -c --status
dotnet exec --runtimeconfig /app/OntologyPlatform.Api.runtimeconfig.json --depsfile /app/OntologyPlatform.Api.deps.json IsolatedPgTests.dll "$1" "$2" "$3"
"""

INSPECT = """{{.Id}}|{{.Image}}|{{.State.Status}}|{{.State.OOMKilled}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{range .NetworkSettings.Networks}}{{.NetworkID}},{{end}}|{{range .Mounts}}{{if or (eq .Destination "/app") (eq .Destination "/query-tests")}}{{.Destination}}={{.RW}}={{.Source}};{{end}}{{end}}"""


def run(build_receipt, *, admit=None):
    """Master 串行调用；只读核本批两运行时身份后创建一个新库，失败也仅收口准确归属。"""
    need(os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'RUN_SCOPE')
    admit = admit or platform.admission
    registry = json.loads(ex.ordinary(AREA/'formal-resources.json').read_bytes())
    need((registry['taskId'],registry['runId'],registry['ids']['platform-pg'])==(TASK,RUN,PG), 'REGISTRY')
    api = registry['ids']['api-secondary']
    need(re.fullmatch('[a-f0-9]{64}',api) and registry['ids']['api'] != api, 'SECONDARY')
    prepared = ex.ordinary(Path(build_receipt)).resolve()
    need(prepared.name=='build.json' and prepared.parent.parent==AREA and re.fullmatch('pg-driver-[a-f0-9]{32}',prepared.parent.name), 'DRIVER_PATH')
    bound = json.loads(prepared.read_bytes()); dll = prepared.parent/'IsolatedPgTests.dll'
    need((bound['taskId'],bound['runId'],bound['exitCode'],bound['inputs']['source'],bound['dllSha256'])==
         (TASK,RUN,0,digest(SOURCE),digest(dll)) and dll.stat().st_size<MIB, 'DRIVER_BINDING')
    import workflow_oracle_mapping_resume as resume
    import workflow_m4_query_runtime as snapshots
    need(resume.manifest()==registry, 'FORMAL_MANIFEST')
    inputs=json.loads(ex.ordinary(AREA/'formal-api-inputs.json').read_bytes())
    query,query_event=resume.bound_build('query')
    api_build,api_event=resume.bound_build('api')
    need(registry['apiBuildId']==inputs['buildCommandId']==api_event['commandId']
         and registry['buildOutputKey']==api_build['outputKey'],'API_BUILD')
    frozen={}
    for name,sid,binding,event in [('api',registry['snapshotId'],api_build,api_event),
                                   ('query',inputs['querySnapshotId'],query,query_event)]:
        need(re.fullmatch('[a-f0-9]{64}',sid),'SNAPSHOT_FORMAT')
        snap=json.loads(ex.ordinary(AREA/'runtime-snapshots'/(sid+'.json')).read_bytes())
        snapshots.verify(ROOT,snap,task=TASK,run_id=RUN)
        need(snap['inputs']==binding and snap['commandId']==event['commandId'],'SNAPSHOT_BUILD')
        frozen[name]=ROOT/snap['directory']
    nonce = uuid.uuid4().hex[:12]; db = 'omq_query_test_'+nonce; owner = OWNER+nonce
    row = dict(taskId=TASK,runId=RUN,attempt=nonce,database=db,owner=owner,pgId=PG,apiId=api,
               registrySha256=digest(AREA/'formal-resources.json'),driver=bound,query=query,apiBuildId=api_event['commandId'],
               queryBuildId=query_event['commandId'],snapshots={name:path.name for name,path in frozen.items()},commands=[],
               head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),status='STARTED')
    out = AREA/('pg-verification-'+nonce+'.json')
    platform.save(out,row)
    key = ex.sha(ex.encoded(row))

    def call(stage,args,body=None,seconds=24,cleanup=False):
        r=command(stage,[*DOCKER,*args],key,payload=body,seconds=seconds,cleanup=cleanup)
        row['commands'].append(dict(stage=stage,id=r.receipt['commandId'],exitCode=r.returncode))
        platform.save(out,row,True)
        need(r.returncode==0,stage+'_'+r.receipt['commandId'])
        return r.stdout.decode().strip()

    def pg(stage,sql,maintenance=False,closing=False):
        return call(stage,['exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','postgres' if maintenance else 'mapping',
                           '-v','ON_ERROR_STOP=1'],sql if isinstance(sql,bytes) else sql.encode(),cleanup=closing)
    def db_state(stage):
        return json.loads(pg(stage,f"""SELECT COALESCE((SELECT json_build_object('oid',d.oid,'comment',shobj_description(d.oid,'pg_database'),
          'role',pg_get_userbyid(d.datdba),'sessions',(SELECT count(*) FROM pg_stat_activity WHERE datid=d.oid),'bytes',pg_database_size(d.oid))
          FROM pg_database d WHERE d.datname='{db}'),'null'::json);""",True,True))
    def layout(name,ident):
        fields=call(name+'-identity',['inspect','-f',INSPECT,ident]).split('|')
        need(len(fields)==11 and fields[:5]==[ident,platform.IMAGES[name],'running','false',TASK]
             and int(fields[7])==768*MIB and int(fields[8])==500000000,'LIVE_'+name)
        nets=set(filter(None,fields[9].split(',')))
        if name=='platform-pg':
            need(nets=={registry['networks']['platform-internal']},'PG_NETWORK')
        else:
            need(fields[5]==RUN and fields[6]==PROJECT and nets==set(registry['networks'].values()),'API_NETWORK')
            mounts={p.split('=',2)[0]:p.split('=',2)[1:] for p in fields[10].split(';') if p}
            for dest,target in [('/app','api'),('/query-tests','query')]:
                mode,source=mounts[dest]
                need(mode=='false' and Path(source.removeprefix('/host_mnt'))==frozen[target],'READONLY_MOUNTS')
            need(digest(frozen['api']/'Npgsql.dll')==digest(frozen['query']/'Npgsql.dll')==digest(TESTDIR/'Npgsql.dll'),'DRIVER_REFERENCE')
        return fields
    def checkpoint_rows(stage):
        fixture=AREA.parent/'implementation-01/runtime-fixture.json'
        need(digest(fixture)==FIXTURE_HASH,'FIXTURE')
        rows=[json.loads(line) for line in pg(stage,checkpoint.pg_sql(json.loads(fixture.read_bytes()),'4239ea404d924bbcae5e4ec41ad4cc27')).splitlines()]
        tables={r['name']:r for r in rows if r['kind']=='table'}
        hold=[r for r in rows if r['kind']=='hold']
        need(len(tables)==48 and checkpoint.CHECKPOINT_TABLES<=set(tables) and len(hold)==1
             and checkpoint.QUERY==HOLD and hold[0]==dict(kind='hold',state='CANCELLED',cancel=True,fence=2,released=True,
                 bytes=0,hash=None,receipts=0,cancelAudit=1,recoverAudit=1,operationAudit=1,success=0),'CHECKPOINT')
        return ex.sha(b'\n'.join(sorted(ex.encoded(r) for r in rows)))
    created=False
    try:
        before=admit()
        need((before['taskId'],before['runId'],before['status'])==(TASK,RUN,'FORMAL_RESOURCE_READY'),'ADMISSION')
        row['beforeAdmission']=before['attempt']
        layout('platform-pg',PG);layout('api-secondary',api)
        left=int(call('api-free',['exec',api,'sh','-ec','echo $(($(cat /sys/fs/cgroup/memory.max)-$(cat /sys/fs/cgroup/memory.current)))']))
        need(left>=512*MIB,'RUNNER_MEMORY')
        row['mappingBefore']=checkpoint_rows('mapping-before')
        need(db_state('db-before') is None,'DB_EXISTS')
        inventory=json.loads(pg('database-budget',"""SELECT json_build_object('template',pg_database_size('template1'),
          'old',coalesce((SELECT pg_database_size(oid) FROM pg_database WHERE datname='omq_query_test_5a42dafebb99'),0),
          'walSegment',pg_size_bytes(current_setting('wal_segment_size')),'lsn',pg_current_wal_insert_lsn()::text);""",True))
        disk=before['platformDisk']
        budget=disk['ceilingBytes']-disk['totalBytes']
        need(disk['ceilingBytes']==40*1024**3 and budget>0,'DISK_CAP')
        # 同一 PG scratch 数据与整个集群产生的 WAL 均计入增量。预留两段 WAL 分配和原 runner 32MiB 临时空间。
        usable=budget-32*MIB-2*inventory['walSegment']
        need(usable>=max(inventory['old'],2*inventory['template']) and re.fullmatch('[0-9A-F]+/[0-9A-F]+',inventory['lsn']),'DISK_HEADROOM')
        row['disk']=dict(before=inventory,additionalHeadroom=budget,meteredDbAndWalLimit=usable,
                         runnerTmpReserve=32*MIB,apiFreeBytes=left,
                         limitKind='sampled workload allowance; PostgreSQL has no per-database hard volume quota')
        pg('create-db',f"CREATE DATABASE {db};",True)
        created=True
        pg('bind-db',f"COMMENT ON DATABASE {db} IS '{owner}';",True)
        state=db_state('db-bound');need(state and state['comment']==owner and state['role']=='postgres' and state['sessions']==0,'NEW_DB_OWNER')
        row['databaseOid']=state['oid']; platform.save(out,row,True)
        argv=['exec','-i',api,'sh','-ec',BOOT,'omq-pg',nonce,inventory['lsn'],str(usable),bound['dllSha256']]
        result=command('actual-tests',[*DOCKER,*argv],key,payload=ex.ordinary(dll).read_bytes(),seconds=185)
        row['commands'].append(dict(stage='actual-tests',id=result.receipt['commandId'],exitCode=result.returncode))
        row['tests']=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        platform.save(out,row,True)
        need(result.returncode==0 and [(v.get('method'),v.get('expected')) for v in row['tests']]==CASES and
             all(v['total']==v['succeeded']==v['expected'] and v['failed']==v['skipped']==v['exitCode']==0
                 and not v['timedOut'] and v['sampled']>=2 and v['peakDbPlusWalBytes']<usable for v in row['tests']),'TEST_RESULTS')
        need(build.validate('query',TASK)==query and digest(dll)==bound['dllSha256'], 'BUILD_CHANGED')
        row['execution']='PASS'
    except Exception as error:
        row['reason']=str(error) if re.fullmatch(r'[\w.-]+',str(error)) else type(error).__name__
        row['execution']='BLOCKED'
    finally:
        try:
            if created:
                if any(c['stage']=='actual-tests' for c in row['commands']):
                    call('tmpfs-released',['exec',api,'sh','-ec','test ! -e "$1"','omq-verify','/tmp/omq-pg-'+nonce],cleanup=True)
                state=db_state('db-before-release')
                need(state and state['oid']==row.get('databaseOid') and state['comment']==owner and state['role']=='postgres' and state['sessions']==0,'KEEP_UNVERIFIED')
                pg('drop-exact-db',f'DROP DATABASE {db};',True,True)
                need(db_state('db-after') is None,'DROP_POSTCONDITION')
                row['databaseReleased']=True
            if 'mappingBefore' in row:
                row['mappingAfter']=checkpoint_rows('mapping-after')
                need(row['mappingAfter']==row['mappingBefore'],'MAPPING_CHANGED')
            if 'beforeAdmission' in row:
                after=admit();need(after['status']=='FORMAL_RESOURCE_READY' and after['runId']==RUN,'POST_ADMISSION')
                row['afterAdmission']=after['attempt']
            row['status']='PASS' if row.get('execution')=='PASS' and row.get('databaseReleased') else 'BLOCKED'
        except Exception as error:
            row['status']='BLOCKED'
            row['closeoutReason']=str(error) if re.fullmatch(r'[\w.-]+',str(error)) else type(error).__name__
        platform.save(out,row,True)
    return row


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('build','run'));parser.add_argument('--build-receipt',type=Path)
    args=parser.parse_args()
    if args.action=='build':print(build_driver())
    else:
        need(args.build_receipt is not None,'BUILD_RECEIPT')
        receipt=run(args.build_receipt);print(json.dumps({k:receipt[k] for k in ('attempt','status')}))
        raise SystemExit(0 if receipt['status']=='PASS' else 2)
