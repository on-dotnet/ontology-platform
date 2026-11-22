"""本次准确源ACL失败的隔离验收及任务收尾；不进入旧S0维护或更改持卷代次。"""
import datetime as dt
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import workflow_execution as ex
import workflow_m2_build as build
import workflow_oracle_mapping_resume as resume
from workflow_oracle_mapping_resources import require

ROOT=resume.ROOT
TASK=resume.TASK
RUN=resume.PRODUCT
AREA=resume.AREA/'s2-s3-01'
QUERY='query-4b9f97e1bbdd45f7a39111c907447f65'
PARENT='04f23ea8cfe34868a8500b80164d86fb'
EXECUTION='b4b07ea50d304927975cd5d052ff58e4'
OWNER='oracle-execution-8db5f162e634422abf8b94caf509d2c9'
PG='79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545'
SOURCE='65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1'
STABLE='25e9289fe30b97d2e03ed49723134713966a9949faf53fdc1c199af74ac56f5a'
FAILURE_AUDIT='eb5cfd622f3049238006b828e1a4ff52'
FAILURE_SHA='5dda9b7f61a129ea975162da32706ae41433efad261039e09804ee8fe00c6c3f'
DOCKER=['docker','--context','desktop-linux']
MIB=1024**2


def save(path,value):
    resume.platform.save(path,value,path.exists())


def command(stage,args,payload=None,timeout=30,cleanup=False):
    result=ex.run(args,ROOT,task=TASK,run_id=RUN,stage='s23-access-'+stage,
        stdin=payload,timeout=timeout,cleanup=cleanup,input_key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),
            producer=ex.sha(Path(__file__).read_bytes())))))
    require(result.returncode==0,'S23_ACCESS_'+stage+'_'+result.receipt['commandId'])
    return result.stdout.decode().strip(),result.receipt['commandId']


def pg(stage,sql,database='mapping',cleanup=False):
    require(database in ('mapping','postgres') or re.fullmatch('omq_query_test_[a-f0-9]{12}',database),'S23_ACCESS_DB')
    return command(stage,[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d',database,'-v','ON_ERROR_STOP=1'],sql.encode(),cleanup=cleanup)


def isolated_test(*, generation=False):
    """在当前替代PG的新nonce库实测正式恢复事务，只有该库及本次辅助进程可被收口。"""
    require(os.environ.get('OMQ_PRODUCT_RUN')==RUN,'S23_ACCESS_RUN')
    manifest=resume.manifest();require(manifest['ids']['platform-pg']==PG and manifest['ids']['oracle']==SOURCE,'S23_ACCESS_INSTANCES')
    attempt=uuid.uuid4().hex;nonce=attempt[:12];database='omq_query_test_'+nonce
    owner=TASK+':implementation-01:'+nonce
    directory=AREA/('access-pg-'+attempt);directory.mkdir(mode=0o700)
    evidence=directory/'streams';evidence.mkdir(mode=0o700)
    file=directory/'receipt.json';row=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',attempt=attempt,database=database,owner=owner,pgId=PG,status='PREPARING',commands=[])
    def call(stage,args,payload=None,timeout=30,cleanup=False):
        out,cid=command(stage,args,payload,timeout,cleanup);row['commands'].append(dict(stage=stage,commandId=cid));save(file,row);return out
    def query(stage,sql,db='postgres',cleanup=False):
        return call(stage,[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d',db,'-v','ON_ERROR_STOP=1'],sql.encode(),cleanup=cleanup)
    def db_state(stage):
        return json.loads(query(stage,f"SELECT COALESCE((SELECT json_build_object('oid',oid,'owner',pg_get_userbyid(datdba),'comment',shobj_description(oid,'pg_database'),'sessions',(SELECT count(*) FROM pg_stat_activity WHERE datid=pg_database.oid)) FROM pg_database WHERE datname='{database}'),'null'::json);",cleanup=True))
    created=False;helper=None
    try:
        admission=resume.admit();row['beforeAdmission']=admission['attempt'];save(file,row)
        ceiling=40*1024**3
        if generation:
            from workflow_oracle_runtime_window import policy, EXIT_MARGIN
            ceiling=policy()['ceiling']-EXIT_MARGIN
        allowance=ceiling-admission['platformDisk']['totalBytes']-64*MIB
        if generation:
            allowance=min(256*MIB,allowance-1024*MIB)
        require(allowance>=16*MIB,'S23_ACCESS_PG_HEADROOM')
        row['capacityBytes']=allowance
        prepared=ROOT/'artifacts/workflow'/TASK/'environment/d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43/runs/3463d8ec1a64483989d9f2b531190dbb/receipt.json'
        prep=json.loads(ex.ordinary(prepared).read_bytes())
        # 只使用已恢复的本地引用及展开包，不宣称已回收feed的完整prepare仍然READY。
        source=Path(__file__).with_suffix('.cs.txt')
        method='G4QueryRaceTests.OracleAccessFailureMaintenanceInIsolatedPostgres'
        if generation:
            method='G4QueryRaceTests.OracleGenerationMaintenanceInIsolatedPostgres'
        sdk=Path(prep['dotnet']).parent
        refs=[p for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref') for p in sorted((sdk/'packs'/pack/'10.0.13/ref/net10.0').glob('*.dll'))]
        tests=ROOT/Path(build.TARGETS['query']).parent/'bin/Debug/net10.0'
        refs.append(tests/'Npgsql.dll');dll=directory/'IsolatedPgTests.dll'
        argv=[prep['dotnet'],str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-target:exe','-deterministic+','-nostdlib+','-nullable:enable','-out:'+str(dll),*['-r:'+str(p) for p in refs],str(source)]
        result=ex.run(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*argv],ROOT,task=TASK,run_id=RUN,
            stage='s23-access-pg-driver-build',input_key=ex.sha(ex.encoded({str(p):ex.sha(p.read_bytes()) for p in [source,*refs]})),environment=prep['environment'],timeout=45)
        row['commands'].append(dict(stage='driver-build',commandId=result.receipt['commandId']));save(file,row);require(result.returncode==0,'S23_ACCESS_DRIVER_BUILD')
        row['driverSha256']=ex.sha(dll.read_bytes());row['buildInputKey']=build.inputs('query');row['outputs']=build.outputs('query')
        require(db_state('test-db-absent') is None,'S23_ACCESS_TEST_DB_EXISTS')
        query('test-db-create',f'CREATE DATABASE {database};');created=True
        query('test-db-bind',f"COMMENT ON DATABASE {database} IS '{owner}';")
        state=db_state('test-db-identity');require(state['comment']==owner and state['owner']=='postgres' and state['sessions']==0,'S23_ACCESS_TEST_DB_OWNER');row['databaseOid']=state['oid'];save(file,row)
        lsn=query('test-db-lsn','SELECT pg_current_wal_insert_lsn();');require(re.fullmatch('[0-9A-F]+/[0-9A-F]+',lsn),'S23_ACCESS_LSN')
        # 使用同一个现有平台网络及合成配置；无监听端口，无源网络，不创建数据卷。
        script='set -eu; umask 077; cd /tmp; mkdir run; cd run; for f in /app/*.dll; do ln -s "$f" .; done; cp /runner/IsolatedPgTests.dll .; exec dotnet exec --runtimeconfig /app/OntologyPlatform.QueryTests.runtimeconfig.json --depsfile /app/OntologyPlatform.QueryTests.deps.json IsolatedPgTests.dll "$@"'
        args=[*DOCKER,'create','--pull=never','--read-only','--network',resume.net_names()['platform-internal'],'--user',str(os.getuid())+':'+str(os.getgid()),
            '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--cap-drop=ALL','--security-opt=no-new-privileges',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
            '--mount','type=bind,src='+str(tests)+',dst=/app,readonly','--mount','type=bind,src='+str(tests)+',dst=/query-tests,readonly',
            '--mount','type=bind,src='+str(resume.RESTORED/'platform/api')+',dst=/private/api,readonly','--mount','type=bind,src='+str(directory)+',dst=/runner,readonly',
            '--mount','type=bind,src='+str(evidence)+',dst=/evidence','--entrypoint=/bin/sh',resume.platform.PROBE,'-ec',script,'access-pg',nonce,lsn,str(allowance),*(['generation'] if generation else [])]
        helper=call('test-helper-create',args);require(re.fullmatch('[a-f0-9]{64}',helper),'S23_ACCESS_HELPER');row['helperId']=helper;save(file,row)
        fmt='{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}'
        before=call('test-helper-before',[*DOCKER,'inspect','-f',fmt,helper]);row['helperBefore']=before;save(file,row)
        require(before.split('|')[:6]==[helper,resume.platform.IMAGES['api'],attempt,'created',str(512*MIB),'500000000'],'S23_ACCESS_HELPER_IDENTITY')
        if generation:
            resume.platform.save(directory/'actual-input.json',row)
        result=ex.run([*DOCKER,'start','-a',helper],ROOT,task=TASK,run_id=RUN,stage='s23-access-pg-actual',timeout=80,input_key=ex.sha(ex.encoded(row)))
        row['actualCommandId']=result.receipt['commandId'];row['actualExitCode']=result.returncode;save(file,row)
        row['test']=[json.loads(line) for line in result.stdout.splitlines() if line.strip()];save(file,row)
        require(result.returncode==0 and len(row['test'])==1,'S23_ACCESS_TEST_FAILED')
        test=row['test'][0];require(test['method']==method and test['total']==test['succeeded']==test['expected']==1
            and test['failed']==test['skipped']==test['exitCode']==0 and not test['timedOut'] and test['peakDbPlusWalBytes']<allowance,'S23_ACCESS_TEST_RESULT')
        for kind in ('stdout','stderr'):
            raw=ex.ordinary(evidence/(kind+'.txt')).read_bytes();require(ex.sha(raw)==test[kind+'Sha256'] and len(raw)==test[kind+'Bytes'],'S23_ACCESS_TEST_STREAM')
        require(row['buildInputKey']==build.inputs('query') and row['outputs']==build.outputs('query'),'S23_ACCESS_TEST_BUILD_CHANGED')
        row['execution']='PASS'
    except Exception as error:
        row['execution']='FAIL';row['error']=str(error) if str(error).startswith('ORACLE_ADMISSION_') else type(error).__name__;raise
    finally:
        if helper:
            state=call('test-helper-exit',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True)
            if state.startswith('running|'):
                call('test-helper-term',[*DOCKER,'stop','--signal','TERM','--timeout','-1',helper],timeout=15,cleanup=True)
                state=call('test-helper-exit-after',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True)
            require(state.startswith('exited|') and state.endswith('|false'),'S23_ACCESS_TEST_HELPER_EXIT')
            call('test-helper-remove',[*DOCKER,'rm',helper],cleanup=True)
            require(not call('test-helper-absent',[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],cleanup=True),'S23_ACCESS_HELPER_REAPPEARED');row['helperReleased']=True
        if created:
            state=db_state('test-db-before-drop');require(state and state['oid']==row['databaseOid'] and state['comment']==owner and state['owner']=='postgres' and state['sessions']==0,'S23_ACCESS_TEST_DB_KEEP')
            query('test-db-drop',f'DROP DATABASE {database};',cleanup=True);require(db_state('test-db-after-drop') is None,'S23_ACCESS_TEST_DB_DROP');row['databaseReleased']=True
        after=resume.admit();row['afterAdmission']=after['attempt'];row['status']='PASS' if row.get('execution')=='PASS' and row.get('helperReleased') and row.get('databaseReleased') else 'FAIL';save(file,row)
    return dict(status=row['status'],receipt=str(file.relative_to(ROOT)),actualCommandId=row['actualCommandId'])


SEAL=AREA/'access-api-seal.json'
ROW_SQL=f'''SET TIME ZONE 'UTC'; SELECT json_build_object('systemIdentifier',(SELECT system_identifier::text FROM pg_control_system()),
'database',current_database(),'databaseUser',current_user,'queryId',q."Id",'organizationId',q."OrganizationId",'connectionId',q."ConnectionId",
'owner',q."LeaseOwner",'fence',q."Fence",'status',q."ExecutionStatus",'cancelRequested',q."CancelRequested",
'createdUtc',q."CreatedAtUtc",'deadlineUtc',q."DeadlineAtUtc",'completedUtc',q."CompletedAtUtc",'leaseUntilUtc',q."LeaseUntilUtc",
'requestSha256',q."RequestHash",'bindingSha256',encode(sha256(q."BindingBytes"),'hex'),
'stableRowSha256',encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'),
'resultHash',q."ResultHash",'resultSize',q."ResultSize",'resultCiphertextLength',octet_length(q."ResultCiphertext"))
FROM semantic_query."Queries" q WHERE q."Id"='{QUERY}';'''
AUDIT_SQL=f'''SET TIME ZONE 'UTC'; SELECT COALESCE(json_agg(json_build_object('id',a."Id",'action',a."Action",'outcome',a."Outcome",
'actor',a."Actor",'trace',a."TraceId",'correlation',a."CorrelationId",'organization',a."OrganizationId",'sites',a."ScopeSiteIds",
'sha256',encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex')) ORDER BY a."Id"),'[]')
FROM governance.audit_records a WHERE a."Resource"='{QUERY}';'''
SOURCE_SQL="set heading off feedback off pagesize 0 verify off echo off\nwhenever sqlerror exit failure rollback\nalter session set container=FREEPDB1;\nselect count(*) from G4_CONTROL.OMQ_SESSIONS;\nexit\n"


def host_rows(stage,ids):
    names=sorted(ids)
    raw,cid=command(stage,[*DOCKER,'inspect','-f',resume.platform.HOST_FORMAT,*[ids[n] for n in names]])
    rows={n:line.split('|') for n,line in zip(names,raw.splitlines(),strict=True)}
    for n,v in rows.items():
        require(len(v)==9 and v[0]==ids[n] and v[2]==TASK and v[3]==(RUN if n in resume.APIS else 'implementation-01')
            and v[4]=='running' and int(v[5])>0,'S23_ACCESS_HOST_IDENTITY')
    return dict(commandId=cid,rows=rows)


def seal():
    """只封闭本次失败父窗的两个无状态API；五个持卷进程保持同代，原失败不变。"""
    from doris_keep_drain import COUNTS
    import socket,time
    require(os.environ.get('OMQ_PRODUCT_RUN')==RUN and not SEAL.exists(),'S23_ACCESS_SEAL_ONCE')
    manifest=resume.manifest();ids=manifest['ids'].copy()
    previous=json.loads((resume.AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json')).read_bytes())
    require(previous['exitCode']==1 and previous['host']['oracle']['containerId']==SOURCE
        and ids=={**{k:v['containerId'] for k,v in previous['host']['services'].items()},'oracle':SOURCE},'S23_ACCESS_SEAL_PARENT')
    row=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',parentCommandId=PARENT,queryId=QUERY,ids=ids,status='SEALING',apis={})
    row['before']=host_rows('seal-before',ids);save(SEAL,row)
    counts,cid=pg('seal-drain-before','SELECT json_build_array('+','.join('('+s.strip()+')' for s in COUNTS)+');')
    require(json.loads(counts)==[0]*7,'S23_ACCESS_SEAL_DRAIN');row['drainBefore']=cid;save(SEAL,row)
    for role in resume.APIS:
        try:resume.release_api(role)
        except ValueError as error:
            if str(error)!='ORACLE_ADMISSION_FROZEN_PORT_COLLISION' or role in resume.manifest()['ids']:raise
            row['apis'][role]=dict(id=ids[role],postAdmissionError=str(error));save(SEAL,row)
            deadline=__import__('time').monotonic()+75
            while True:
                with socket.socket() as probe:
                    try:probe.bind(('127.0.0.1',resume.platform.PORTS['secondary' if role=='api-secondary' else 'api']));break
                    except OSError:
                        require(time.monotonic()<deadline,'S23_ACCESS_PORT_DRAIN');time.sleep(1)
            row['apis'][role]['postAdmission']=resume.admit()['attempt'];save(SEAL,row)
        absent,cid=resume.command('entry-api-absent-'+role,['ps','-aq','--no-trunc','--filter','id='+ids[role]])
        require(not absent and role not in resume.manifest()['ids'],'S23_ACCESS_SEAL_PRESENT')
        row['apis'].setdefault(role,dict(id=ids[role]))['absentCommandId']=cid;save(SEAL,row)
    row['after']=host_rows('seal-after',{k:v for k,v in ids.items() if k not in resume.APIS})
    require(row['after']['rows']=={k:v for k,v in row['before']['rows'].items() if k not in resume.APIS},'S23_ACCESS_DATA_RESTARTED')
    row['status']='APIS_REMOVED_DATA_GENERATIONS_UNCHANGED';save(SEAL,row);return row


def original(cid,kind='stdout.txt'):
    return ex.ordinary(ROOT/'artifacts/workflow'/TASK/'commands'/RUN/cid/kind).read_bytes()


def reopen_command(cid,args,stage,payload=None,timeout=30):
    """复核命令身份、真实双流、受控argv及固定入口输入，不信摘要中的PASS。"""
    import workflow_oracle_mapping_evidence as e
    class Commands(e.Originals):
        def __init__(self):self.root=ROOT
        def raw(self,name):
            match=re.fullmatch('([a-f0-9]{32})-(receipt.json|stdout.txt|stderr.txt)',name)
            require(match is not None,'S23_ACCESS_COMMAND_NAME');return original(match[1],match[2])
    producer=ex.sha(Path(__file__).read_bytes())
    if stage in ('seal-before','seal-after'):
        producer='ab963c25658b7846224da2b671b501e68d291d3f4503987f2c5b8d8f88c6e16f'
        require(ex.sha(ex.ordinary(AREA/('access-maintenance-producer-'+producer+'.py')).read_bytes())==producer,'S23_ACCESS_SEAL_PRODUCER')
    key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),producer=producer)))
    receipt,out,err=Commands().command(cid,args,'s23-access-'+stage,key,None,ROOT,command_run=RUN)
    require(receipt['classification']=='SUCCESS' and receipt['exitCode']==0 and receipt['deadlineSeconds']==timeout,'S23_ACCESS_COMMAND_FAILED')
    return receipt,out,err


def verify_seal():
    """准确失败父窗与两个API TERM/退出/移除/缺席全部真实命令组成封闭证明。"""
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    data=original(PARENT,'receipt.json');require(ex.sha(data)=='919ba3d8ee3a208e2bb911243341f6a6495b3d93c64bc2141ac1c8bb04d318f7','S23_ACCESS_PARENT_RECEIPT')
    parent=json.loads(data);require(parent['exitCode']==1 and parent['classification']=='EXIT_FAILURE','S23_ACCESS_PARENT_FAILED')
    data=ex.ordinary(resume.AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json')).read_bytes()
    require(ex.sha(data)=='170263a71d9af33b240e86ab3d9bf1ab983eeb3c8e94741d5b261c492fc87013','S23_ACCESS_PARENT_DISPATCH')
    dispatch=json.loads(data);ids={**{k:v['containerId'] for k,v in dispatch['host']['services'].items()},'oracle':SOURCE}
    row=json.loads(ex.ordinary(SEAL).read_bytes())
    require((row['taskId'],row['runId'],row['batch'],row['parentCommandId'],row['queryId'],row['status'])==(TASK,RUN,'s2-s3-01',PARENT,QUERY,'APIS_REMOVED_DATA_GENERATIONS_UNCHANGED')
        and row['ids']==ids and set(row['apis'])==set(resume.APIS),'S23_ACCESS_SEAL_SCOPE')
    hosts=[]
    for stage,selected in [('before',ids),('after',{k:v for k,v in ids.items() if k not in resume.APIS})]:
        names=sorted(selected)
        receipt,out,_=reopen_command(row[stage]['commandId'],[*DOCKER,'inspect','-f',resume.platform.HOST_FORMAT,*[selected[n] for n in names]],'seal-'+stage)
        require(row[stage]['rows']=={n:line.split('|') for n,line in zip(names,out.decode().strip().splitlines(),strict=True)},'S23_ACCESS_SEAL_HOST')
        hosts.append(receipt)
    require(row['after']['rows']=={k:v for k,v in row['before']['rows'].items() if k not in resume.APIS}
        and utc(parent['endedAtUtc'])<=utc(hosts[0]['startedAtUtc'])<utc(hosts[1]['startedAtUtc']),'S23_ACCESS_SEAL_GENERATIONS')
    c.observed_oracle(ROOT,dispatch['host'])
    host_names=[*sorted(dispatch['host']['services']),'oracle']
    original_rows={name:line.split('|') for name,line in zip(host_names,original(dispatch['host']['commandId']).decode().strip().splitlines(),strict=True)}
    def canonical_rows(rows):
        return {name:[*value[:7],json.loads(value[7]),dict(pair.split('=') for pair in value[8].split())] for name,value in rows.items()}
    require(canonical_rows(row['before']['rows'])==canonical_rows(original_rows),'S23_ACCESS_SEAL_PARENT_GENERATIONS')
    for role,api in row['apis'].items():
        resource=ids[role];require(api['id']==resource,'S23_ACCESS_SEAL_API_ID');end=utc(hosts[0]['endedAtUtc'])
        for kind in ('term','exit','remove','absent'):
            if kind=='term':args=['stop','--signal','TERM','--timeout','-1',resource];stage='resume-api-term';seconds=45
            elif kind=='exit':args=['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',resource];stage='resume-api-exit';seconds=30
            elif kind=='remove':args=['rm',resource];stage='resume-remove-stateless';seconds=30
            else:args=['ps','-aq','--no-trunc','--filter','id='+resource];stage='entry-api-absent-'+role;seconds=30
            argv=[*DOCKER,*args];key=ex.sha(ex.encoded(args));matches=[]
            for path in (ROOT/'artifacts/workflow'/TASK/'commands'/RUN).glob('*/receipt.json'):
                value=json.loads(ex.ordinary(path).read_bytes())
                if value['stage']==stage and value['inputFingerprint']==key and value['exitCode']==0 and end<=utc(value['startedAtUtc'])<=utc(value['endedAtUtc'])<=utc(hosts[1]['startedAtUtc']):matches.append(value['commandId'])
            require(len(matches)==1,'S23_ACCESS_SEAL_COMMAND_UNIQUE');cid=matches[0]
            receipt,out,_=c.command(ROOT,cid,RUN,argv,stage,key,seconds)
            if kind=='exit':require(out.strip() in (b'exited 0 false',b'exited 143 false'),'S23_ACCESS_SEAL_EXIT')
            elif kind=='absent':require(cid==api['absentCommandId'] and not out.strip(),'S23_ACCESS_SEAL_ABSENT')
            else:require(out.decode().strip()==resource,'S23_ACCESS_SEAL_ACTION')
            end=utc(receipt['endedAtUtc'])
    return hosts[1]


def prestate():
    """独立新连接采集准确行、所有审计与两次源端零会话；返回五分钟有界证明。"""
    from doris_keep_drain import COUNTS,ACTIVITY
    require(os.getuid()==501 and os.environ.get('OMQ_PRODUCT_RUN')==RUN,'S23_ACCESS_OPERATOR')
    verify_seal()
    sealed=json.loads(ex.ordinary(SEAL).read_bytes());require(sealed['status']=='APIS_REMOVED_DATA_GENERATIONS_UNCHANGED','S23_ACCESS_NOT_SEALED')
    ids=resume.manifest()['ids'];require(set(ids)==set(sealed['after']['rows']) and ids['platform-pg']==PG and ids['oracle']==SOURCE,'S23_ACCESS_CLOSED_IDS')
    attempt=uuid.uuid4().hex;path=AREA/('access-prestate-'+attempt+'.json');row=dict(taskId=TASK,runId=RUN,attemptId=attempt,commands={},status='OBSERVING')
    row['host']=host_rows('prestate-host',ids);require(row['host']['rows']==sealed['after']['rows'],'S23_ACCESS_GENERATIONS')
    for role,api in sealed['apis'].items():
        absent,cid=command('prestate-absent-'+role,[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+api['id']]);require(not absent,'S23_ACCESS_API_RETURNED');row['commands']['absent-'+role]=cid
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    value,cid=pg('prestate-drain',sql);require(json.loads(value)==[0]*8,'S23_ACCESS_DRAIN');row['commands']['drain']=cid
    for which in ('first','second'):
        value,cid=command('source-zero-'+which,[*DOCKER,'exec','-i',SOURCE,'sqlplus','-L','-s','/ as sysdba'],SOURCE_SQL.encode())
        require(value.strip()=='0','S23_ACCESS_SOURCE_SESSIONS');row['commands']['source-'+which]=cid
    data,cid=pg('prestate-row',ROW_SQL);row['commands']['row']=cid;before=json.loads(data)
    require(before==json.loads(original('97aa3d42aa61459fadf39575262c4ccd')),'S23_ACCESS_ROW_CHANGED')
    data,cid=pg('prestate-audit',AUDIT_SQL);row['commands']['audit']=cid;audits=json.loads(data)
    require(audits==json.loads(original('55872d563ecf45919cff4b85cafecd12')),'S23_ACCESS_AUDIT_CHANGED')
    now=dt.datetime.now(dt.timezone.utc)
    termination=dict(taskId=TASK,runId=RUN,queryId=QUERY,sourceExecutionId=EXECUTION,sourceId=SOURCE,sealSha256=ex.sha(SEAL.read_bytes()),
        commands=row['commands'],host=row['host'],sourceSessions=0,claim='Task-level physical absence after exact APIs exited; original cleanup250ms NOT_QUALIFIED')
    row['termination']=termination
    proof={k:before[k] for k in ('systemIdentifier','database','databaseUser','organizationId','queryId','connectionId','owner','createdUtc','deadlineUtc','completedUtc','leaseUntilUtc','requestSha256','bindingSha256','stableRowSha256')}
    proof.update(taskId=TASK,runId=RUN,attemptId=attempt,operationId=uuid.uuid4().hex,operatorId='os-uid-501',originalFence=1,terminalFence=2,
        sourceExecutionId=EXECUTION,parentCommandId=PARENT,platformContainerId=PG,sourceContainerId=SOURCE,failureAuditId=FAILURE_AUDIT,failureAuditSha256=FAILURE_SHA,
        sealSha256=ex.sha(SEAL.read_bytes()),terminationProofSha256=ex.sha(ex.encoded(termination)),verifiedUtc=now.isoformat(),validUntilUtc=(now+dt.timedelta(minutes=5)).isoformat())
    row.update(proof=proof,proofSha256=ex.sha(ex.encoded(proof)),status='OBSERVED');save(path,row)
    return path


def verify_prestate(path):
    """恢复前重开每份强后验原件；不读取密码，不依赖运行摘要代替零会话。"""
    from doris_keep_drain import COUNTS,ACTIVITY
    from workflow_oracle_mapping_evidence import utc
    seal_end=verify_seal()
    row=json.loads(ex.ordinary(path).read_bytes());proof=row['proof'];sealed=json.loads(SEAL.read_bytes())
    require(path.parent==AREA and path.name=='access-prestate-'+proof['attemptId']+'.json' and row['proofSha256']==ex.sha(ex.encoded(proof))
        and proof['sealSha256']==ex.sha(SEAL.read_bytes()) and proof['terminationProofSha256']==ex.sha(ex.encoded(row['termination'])),'S23_ACCESS_PROOF_HASH')
    now=dt.datetime.now(dt.timezone.utc);require(utc(proof['verifiedUtc'])<=now<utc(proof['validUntilUtc']) and utc(proof['validUntilUtc'])-utc(proof['verifiedUtc'])==dt.timedelta(minutes=5),'S23_ACCESS_PROOF_STALE')
    ids=resume.manifest()['ids'];names=sorted(ids)
    host,body,_=reopen_command(row['host']['commandId'],[*DOCKER,'inspect','-f',resume.platform.HOST_FORMAT,*[ids[n] for n in names]],'prestate-host')
    require(row['host']['rows']==sealed['after']['rows']=={n:line.split('|') for n,line in zip(names,body.decode().strip().splitlines(),strict=True)},'S23_ACCESS_PROOF_HOST')
    require(utc(seal_end['endedAtUtc'])<=utc(host['startedAtUtc']),'S23_ACCESS_PROOF_AFTER_SEAL')
    last_absence=utc(host['endedAtUtc'])
    for role,api in sealed['apis'].items():
        receipt,out,_=reopen_command(row['commands']['absent-'+role],[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+api['id']],'prestate-absent-'+role)
        require(not out.strip() and last_absence<=utc(receipt['startedAtUtc']),'S23_ACCESS_PROOF_ABSENT')
        last_absence=utc(receipt['endedAtUtc'])
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    receipt,out,_=reopen_command(row['commands']['drain'],[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],'prestate-drain',sql.encode())
    require(json.loads(out)==[0]*8 and last_absence<=utc(receipt['startedAtUtc']),'S23_ACCESS_PROOF_DRAIN');end=utc(receipt['endedAtUtc'])
    for which in ('first','second'):
        receipt,out,_=reopen_command(row['commands']['source-'+which],[*DOCKER,'exec','-i',SOURCE,'sqlplus','-L','-s','/ as sysdba'],'source-zero-'+which,SOURCE_SQL.encode())
        require(out.strip()==b'0' and end<=utc(receipt['startedAtUtc']),'S23_ACCESS_PROOF_ZERO');end=utc(receipt['endedAtUtc'])
    for name,sql,expected in [('row',ROW_SQL,'97aa3d42aa61459fadf39575262c4ccd'),('audit',AUDIT_SQL,'55872d563ecf45919cff4b85cafecd12')]:
        receipt,out,_=reopen_command(row['commands'][name],[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],'prestate-'+name,sql.encode())
        require(json.loads(out)==json.loads(original(expected)) and end<=utc(receipt['startedAtUtc'])<=utc(receipt['endedAtUtc'])<=utc(proof['verifiedUtc']),'S23_ACCESS_PROOF_ORIGINAL');end=utc(receipt['endedAtUtc'])
    require(proof['stableRowSha256']==STABLE and proof['failureAuditId']==FAILURE_AUDIT and proof['failureAuditSha256']==FAILURE_SHA,'S23_ACCESS_PROOF_TARGET')
    return row


def recover(path):
    """只执行准确FAILED行的一次两列CAS；维护审计和新连接后验独立于产品成功。"""
    row=verify_prestate(path);proof=row['proof'];attempt=proof['attemptId'];file=AREA/('access-recovery-'+attempt+'.json')
    require(not file.exists() and not list(AREA.glob('access-recovery-*.json')),'S23_ACCESS_RECOVERY_ONCE')
    qualified=json.loads((AREA/'access-pg-b02e8847eb3741ca9ec4e24311483d4b/receipt.json').read_bytes())
    require(qualified['status']=='PASS' and qualified['helperReleased'] and qualified['databaseReleased'] and qualified['buildInputKey']==build.inputs('query')
        and qualified['outputs']==build.outputs('query'),'S23_ACCESS_TEST_BINDING')
    receipt=run_recovery_helper(row,path,file,lambda: verify_prestate(path))
    data,cid=pg('post-row',ROW_SQL);receipt['rowCommandId']=cid;post=json.loads(data);before=json.loads(original('97aa3d42aa61459fadf39575262c4ccd'))
    require(post=={**before,'owner':None,'leaseUntilUtc':None},'S23_ACCESS_POST_ROW')
    data,cid=pg('post-audit',AUDIT_SQL);receipt['auditCommandId']=cid;audits=json.loads(data);failure=json.loads(original('55872d563ecf45919cff4b85cafecd12'))[0]
    require(len(audits)==2 and failure in audits,'S23_ACCESS_POST_FAILURE_AUDIT')
    new=next(a for a in audits if a!=failure);require(new['action']=='data.query.cleanup.recover' and new['outcome']=='allowed' and new['actor']==proof['operatorId']
        and new['trace']==proof['operationId'] and new['correlation']==attempt and new['organization']=='org-demo' and new['sites']==['site-a'],'S23_ACCESS_POST_RECOVERY_AUDIT')
    receipt.update(status='TASK_LEVEL_RECOVERY',post=post,audits=audits,originalCleanup250ms='NOT_QUALIFIED');save(file,receipt);return receipt



def run_recovery_helper(row,path,file,verify_before,*,generation=False):
    """在只接平台内网的短命 Linux 宿主提交一次，未知结果由外层原件保留。"""
    proof=row['proof'];attempt=proof['attemptId']
    binding=build.validate('api',TASK);api=ROOT/Path(build.TARGETS['api']).parent/'bin/Debug/net10.0'
    private=resume.RESTORED/'platform/postgres';require(all((private/n).is_file() and not (private/n).is_symlink() for n in ('password','server.crt')),'S23_ACCESS_PRIVATE_INPUTS')
    script=('umask 077; set -eu; test "$(id -u)" = 501; '
        'printf "Host=platform-pg;Port=5432;Database=mapping;Username=postgres;SSL Mode=VerifyFull;Root Certificate=/ca;Password=%s" '
        '"$(cat /auth)" > /tmp/maintenance.dsn; exec dotnet /app/OntologyPlatform.Api.dll --recover-omq-s23-access')
    if generation:
        script=script.replace('--recover-omq-s23-access','--recover-omq-normal' if proof['proofKind']=='NORMAL_GENERATION' else '--recover-omq-s23-d368')
    args=[*DOCKER,'create','--pull=never','-i','--network',resume.net_names()['platform-internal'],'--read-only','--user',str(os.getuid())+':'+str(os.getgid()),
        '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--security-opt=no-new-privileges','--cap-drop=ALL',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
        '--mount','type=bind,src='+str(api)+',dst=/app,readonly','--mount','type=bind,src='+str(private/'password')+',dst=/auth,readonly',
        '--mount','type=bind,src='+str(private/'server.crt')+',dst=/ca,readonly']
    env={'DSN_FILE':'/tmp/maintenance.dsn','OPERATOR':proof['operatorId'],'PROOF_SHA256':row['proofSha256'],'SEAL_SHA256':proof['sealSha256'],'TERMINATION_SHA256':proof['terminationProofSha256']}
    for key,value in env.items():args+=['-e','OMQ_S23_MAINTENANCE_'+key+'='+value]
    helper,cid=command('recovery-create',[*args,'--entrypoint=/bin/sh',resume.platform.PROBE,'-ec',script]);require(re.fullmatch('[a-f0-9]{64}',helper),'S23_ACCESS_RECOVERY_ID')
    receipt=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',helperId=helper,attemptId=attempt,operationId=proof['operationId'],proofFile=str(path.relative_to(ROOT)),
        proofSha256=row['proofSha256'],build=binding,createCommandId=cid,status='CREATED');save(file,receipt)
    try:
        state,cid=command('recovery-before',[*DOCKER,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}',helper]);receipt['beforeCommandId']=cid
        require(state=='|'.join((helper,resume.platform.IMAGES['api'],attempt,'created')),'S23_ACCESS_RECOVERY_OWNER')
        verify_before()
        result=ex.run([*DOCKER,'start','-a','-i',helper],ROOT,task=TASK,run_id=RUN,stage='s23-access-recovery-cas',stdin=ex.encoded(proof),timeout=32,input_key=row['proofSha256'])
        receipt['actualCommandId']=result.receipt['commandId'];receipt['exitCode']=result.returncode;save(file,receipt)
        require(result.returncode==0 and (not result.stderr or (len(result.stderr)==127 and ex.sha(result.stderr)=='6a55ce9418db27c92344e3846e6ec6fe5718cb84e315fe05c82d3403ebff3a9d')),'S23_ACCESS_RECOVERY_FAILED');receipt['commitEnvelope']=json.loads(result.stdout)
        require(receipt['commitEnvelope']['status']=='TASK_LEVEL_RECOVERY' and receipt['commitEnvelope']['operationId']==proof['operationId'],'S23_ACCESS_RECOVERY_OUTCOME')
    except BaseException as first:
        try:
            release_recovery_helper(helper,file,receipt)
        except Exception as cleanup_error:
            first.add_note('S23_ACCESS_HELPER_CLEANUP_FAILED')
            raise first from cleanup_error
        raise
    else:
        release_recovery_helper(helper,file,receipt)
    return receipt


def release_recovery_helper(helper,file,receipt):
    """核实退出或从未启动的准确 helper，普通移除后按完整 ID 核验缺席。"""
    state,cid=command('recovery-exit',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True);receipt['exitCommandId']=cid;save(file,receipt)
    if state.startswith('running|'):
        command('recovery-term',[*DOCKER,'stop','--signal','TERM','--timeout','-1',helper],timeout=15,cleanup=True)
        state,cid=command('recovery-exit-after',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True);receipt['exitAfterCommandId']=cid
    if state == 'created|0|false':
        fmt = ('{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|'
               '{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "ontology.attempt"}}|'
               '{{.State.Status}}|{{.State.Pid}}|{{.State.StartedAt}}|{{.RestartCount}}')
        identity,cid=command('recovery-created-owner',[*DOCKER,'inspect','-f',fmt,helper],cleanup=True)
        receipt['createdOwnerCommandId']=cid
        save(file,receipt)
        expected=(helper,resume.platform.IMAGES['api'],TASK,RUN,receipt['attemptId'],'created','0','0001-01-01T00:00:00Z','0')
        require(identity=='|'.join(expected),'S23_ACCESS_CREATED_OWNER')
    else:
        require(state.startswith('exited|') and state.endswith('|false'),'S23_ACCESS_RECOVERY_EXIT')
    _,cid=command('recovery-remove',[*DOCKER,'rm',helper],cleanup=True);receipt['removeCommandId']=cid
    out,cid=command('recovery-absent',[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],cleanup=True);receipt['absentCommandId']=cid;receipt['helperReleased']=not out;save(file,receipt)
    require(not out,'S23_ACCESS_RECOVERY_HELPER_PRESENT')


def d368_pg_facts(phase, *, normal=False):
    """由三个新连接按准确目标读行、原审计及绑定收据，仅向公开回执提供 owner 摘要。"""
    import workflow_oracle_d368_closure as c
    target=c.target(normal)
    require(phase in ('before','after'),'D368_FACT_PHASE')
    sql=ROW_SQL.replace(QUERY,target.query).replace("'owner',q.\"LeaseOwner\"", """'ownerSha256',encode(sha256(convert_to(q."LeaseOwner",'UTF8')),'hex')""")
    receipts=f"""SELECT json_array_length(convert_from("BindingBytes",'UTF8')::json->'receipts') FROM semantic_query."Queries" WHERE "Id"='{target.query}';"""
    values,commands={},{}
    for key,query in [('row',sql),('audit',AUDIT_SQL.replace(QUERY,target.query)),('receipts',receipts)]:
        raw,commands[key]=resume.platform.read_pg(query.encode(),target.prefix+'-'+phase+'-'+key)
        values[key]=json.loads(raw)
    if normal:
        error,commands['errorCode']=resume.platform.read_pg(('SELECT COALESCE(to_json("ErrorCode")::text,CHR(110)||CHR(117)||CHR(108)||CHR(108)) FROM semantic_query."Queries" WHERE "Id"=\''+target.query+'\';').encode(),'normal-'+phase+'-error-code')
        values['errorCode']=json.loads(error)
    return values,commands


def recover_d368(operation,pg_start_command,isolated_receipt,*,normal=False):
    """仅对本次专用实例代次执行一次晚维护；提交不明时保留原件、禁止再次提交。"""
    import workflow_oracle_d368_closure as c
    target=c.target(normal)
    from workflow_oracle_runtime_window import policy
    require(policy() and re.fullmatch('[a-f0-9]{32}',operation) and
            policy()['priorCloseSha256']==target.close,'D368_PG_WINDOW')
    from workflow_oracle_mapping_continuity import command as reopen
    base=Path(isolated_receipt)
    require(not base.is_absolute() and base.parent.parent==AREA.relative_to(ROOT) and base.name=='receipt.json'
            and re.fullmatch('access-pg-[0-9a-f]{32}',base.parent.name),'D368_ISOLATED_PATH')
    qualified=json.loads(ex.ordinary(ROOT/base).read_bytes())
    query_build=build.validate('query',TASK)
    require(qualified['buildInputKey']==query_build['inputKey'] and qualified['attempt']==base.parent.name[10:]
            and qualified['pgId']==PG,'D368_QUERY_BUILD')
    test=qualified['test'][0]
    require(test['total']==test['expected']==test['succeeded']==1 and test['failed']==test['skipped']==test['exitCode']==0
            and not test['timedOut'] and len(qualified['test'])==1,'D368_ISOLATED_COUNT')
    actual=qualified['actualCommandId']
    request=ex.ordinary((ROOT/base).parent/'actual-input.json').read_bytes()
    actual_input=json.loads(request)
    require(all(actual_input[k]==qualified[k] for k in ('helperId','attempt','buildInputKey','outputs','driverSha256')),'D368_ISOLATED_INPUT')
    _,out,_=reopen(ROOT,actual,RUN,[*DOCKER,'start','-a',qualified['helperId']],'s23-access-pg-actual',ex.sha(ex.encoded(actual_input)),80)
    require([json.loads(line) for line in out.splitlines() if line.strip()]==[test],'D368_ISOLATED_RESULT')
    for stream in ('stdout','stderr'):
        data=ex.ordinary((ROOT/base).parent/'streams'/(stream+'.txt')).read_bytes()
        require(len(data)==test[stream+'Bytes'] and ex.sha(data)==test[stream+'Sha256'],'D368_ISOLATED_STREAM')
    require(qualified['status']=='PASS' and qualified['helperReleased'] and qualified['databaseReleased']
            and qualified['buildInputKey']==build.inputs('query') and qualified['outputs']==build.outputs('query')
            and qualified['test'][0]['method']=='G4QueryRaceTests.OracleGenerationMaintenanceInIsolatedPostgres','D368_ISOLATED_TEST')
    seal=target.prove(pg_start_command=pg_start_command)
    require(seal['generationSha256']==target.generation_sha and
            seal['sealSha256']==target.seal_sha,'D368_SEAL_CHANGED')
    save(AREA/(target.prefix+'-seal-pg-'+operation+'.json'),seal)
    before,commands=d368_pg_facts('before',normal=normal)
    require(before['row']==target.frozen and before['receipts']==0 and len(before['audit'])==1 and
            [before['audit'][0][k] for k in ('id','sha256','action','outcome')]==
            [target.audit,target.audit_sha,'data.query.execute','failure'],'D368_CURRENT_FROZEN_ROW')
    verified=dt.datetime.fromisoformat(seal['verifiedUtc'])
    proof={k:before['row'][k] for k in ('systemIdentifier','database','databaseUser','organizationId','queryId','connectionId',
           'ownerSha256','createdUtc','deadlineUtc','completedUtc','leaseUntilUtc','requestSha256','bindingSha256','stableRowSha256')}
    proof.update(taskId=TASK,runId=RUN,attemptId=uuid.uuid4().hex,operationId=operation,operatorId='os-uid-'+str(os.getuid()),
        originalFence=1,terminalFence=2,proofKind=target.mode,parentCommandId=target.parent,childCommandId=target.child,
        platformContainerId=PG,sourceContainerId=SOURCE,closeSha256=target.close,
        sourceStartedAt=target.start,sourceFinishedAt=target.end,
        failureAuditId=target.audit,failureAuditSha256=target.audit_sha,sealSha256=seal['sealSha256'],
        terminationProofSha256=seal['generationSha256'],verifiedUtc=verified.isoformat(),validUntilUtc=(verified+dt.timedelta(minutes=4)).isoformat())
    path=AREA/(target.prefix+'-proof-'+operation+'.json')
    row=dict(proof=proof,proofSha256=ex.sha(ex.encoded(proof)),before=commands,isolatedReceipt=isolated_receipt)
    resume.platform.save(path,row)
    # 排它单次标记先于 helper create，异常后由真实后态裁决。
    once=AREA/(target.prefix+'-cas-reservation.json')
    with once.open('x') as stream:
        json.dump(dict(operation=operation,proofSha256=row['proofSha256']),stream)
    file=AREA/(target.prefix+'-recovery-'+operation+'.json')
    def recheck_seal():
        current=target.prove(pg_start_command=pg_start_command)
        require(all(current[k]==seal[k] for k in ('generationSha256','sealSha256','live','historical')),'D368_SEAL_BEFORE_CAS')
    try:
        result=run_recovery_helper(row,path,file,recheck_seal,generation=True)
    except BaseException as first:
        # 即使回执丢失也绝不再次提交。原 PG 仍在本窗时通过新连接读取真实后态。
        reconciliation=dict(status='COMMIT_UNKNOWN',queryId=target.query,operation=operation)
        try:
            observed,refs=d368_pg_facts('after',normal=normal)
            reconciliation.update(post=observed,commands=refs)
            if observed==before:
                reconciliation['status']='ORIGINAL_STATE_OBSERVED'
            elif (observed['row']=={**before['row'],'ownerSha256':None,'leaseUntilUtc':None}
                  and observed['receipts']==0 and observed.get('errorCode')==before.get('errorCode')
                  and len(observed['audit'])==2 and before['audit'][0] in observed['audit']):
                added=next(a for a in observed['audit'] if a!=before['audit'][0])
                if [added[k] for k in ('action','actor','outcome','trace','correlation','organization','sites')]==[
                        'data.query.cleanup.recover',proof['operatorId'],'allowed',operation,proof['attemptId'],'org-demo',['site-a']]:
                    reconciliation['status']='COMMITTED_STATE_OBSERVED'
        except Exception:
            first.add_note('READ_ONLY_RECONCILIATION_FAILED')
        save(AREA/(target.prefix+'-reconciliation-'+operation+'.json'),reconciliation)
        raise
    after,final=d368_pg_facts('after',normal=normal)
    require(after['row']=={**before['row'],'ownerSha256':None,'leaseUntilUtc':None}
            and after['receipts']==0 and len(after['audit'])==2 and before['audit'][0] in after['audit'],'D368_POST_STABLE')
    if normal:
        require(after['errorCode']==before['errorCode'],'NORMAL_ERROR_CODE_CHANGED')
    audit=next(item for item in after['audit'] if item!=before['audit'][0])
    require([audit[k] for k in ('action','actor','outcome','trace','correlation','organization','sites')]==
            ['data.query.cleanup.recover',proof['operatorId'],'allowed',operation,proof['attemptId'],'org-demo',['site-a']],
            'D368_POST_SINGLE_AUDIT')
    result.update(before=commands,after=final,status='TASK_LEVEL_RECOVERY',post=after,originalCleanup250ms='NOT_QUALIFIED')
    save(file,result)
    return result


def d368_maintenance_window(*, normal=False, review_prestate=None):
    """冷态打开并只启动本任务 PG。完整关闭后再发布实际的单角色维护后继。"""
    import workflow_oracle_d368_closure as c
    target=c.target(normal)
    import workflow_oracle_d368_pg_close as close
    import workflow_oracle_runtime_window as w
    recovery=resume.recovery
    require(not normal or callable(review_prestate),'NORMAL_PRESTATE_REVIEW')
    require(w.close_registration()['sha256']==target.close and not (AREA/(target.prefix+'-cas-reservation.json')).exists(),'D368_ONCE')
    for build_target in ('api','query'):
        build.validate(build_target,TASK)
    operation=uuid.uuid4().hex
    log=AREA.parent.parent/'command-events.jsonl'
    file=AREA/(target.prefix+'-pg-only-'+operation+'.json')
    summary=dict(taskId=TASK,runId=RUN,batch=w.BATCH,planId=w.PLAN,operation=operation,
                 priorCloseSha256=target.close,queryId=target.query,status='BLOCKED')
    stopped=False
    try:
        with w.open_window() as window:
            summary.update(windowId=window['id'],cold=window['coldAttempt'])
            summary['beforeSeal']=target.prefix+'-seal-cold-'+operation+'.json'
            save(AREA/summary['beforeSeal'],target.prove())
            save(file,summary)
            # PG-only 原入口对每个原生动作前后准入；短命只读助手另外约束临时盘及实测 DB+WAL。
            def check_capacity(attempt):
                disk=resume.load(resume.AREA/('source-admission-'+attempt+'.json'))['platformDisk']
                require(disk['totalBytes']+w.CHECKOUT+64*MIB < window['ceiling']-w.EXIT_MARGIN,'D368_PG_EARLY_DISK_EXIT')
            check_capacity(window['coldAttempt'])
            offset=log.stat().st_size
            try:
                start=recovery.start_owned('replacement','platform-pg',set())
                summary['pgStartAttempt']=start['attempt']
                with log.open('rb') as stream:
                    stream.seek(offset)
                    rows=[json.loads(line) for line in stream if line.strip()]
                ids=[row['commandId'] for row in rows if row.get('event')=='END' and row.get('exitCode')==0
                     and row['stage']=='omq-recovery-start-platform-pg' and row['runId']==recovery.RECOVERY]
                require(len(ids)==1,'D368_PG_START_COMMAND')
                summary['pgStartCommand']=ids[0]
                summary['pgSeal']=target.prefix+'-seal-pg-'+operation+'.json'
                save(AREA/summary['pgSeal'],target.prove(pg_start_command=ids[0]))
                current,refs=d368_pg_facts('before',normal=normal)
                require(current['row']==target.frozen and current['receipts']==0 and len(current['audit'])==1
                        and current['audit'][0]['sha256']==target.audit_sha,'D368_FRESH_PRESTATE')
                summary['initialPgFacts']=refs
                save(file,summary)
                check_capacity(start['post'])
                checked=isolated_test(generation=True)
                summary['isolated']=checked
                save(file,summary)
                if normal:
                    review_prestate(file,operation)
                check_capacity(resume.admit()['attempt'])
                summary['cas']=target.prefix+'-recovery-'+operation+'.json'
                save(file,summary)
                receipt=recover_d368(operation,ids[0],checked['receipt'],normal=normal)
                summary['status']=receipt['status']
            finally:
                with w.close_resources():
                    if 'platform-pg' in resume.running_roles():
                        stop=recovery.native_stop('replacement','platform-pg',{'platform-pg'},operation)
                        matches=[path.stem[5:] for path in recovery.RECOVERY_AREA.glob('stop-*.json')
                                 if json.loads(ex.ordinary(path).read_bytes())==stop]
                        require(len(matches)==1,'D368_EXACT_STOP')
                        summary['pgStopAttempt']=matches[0]
                        summary['pgNative']=close.native_references(matches[0])
                        summary['postState']=close.capture_closed_state(normal=normal)
                        summary['post']=resume.admit()['attempt']
                        stopped=True
                    save(file,summary)
    finally:
        if stopped:
            close.publish_d368_pg_close(operation,normal=normal)
    return summary
