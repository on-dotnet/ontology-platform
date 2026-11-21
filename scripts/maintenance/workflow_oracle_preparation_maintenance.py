"""本次准确源前置超时的隔离验收及任务收尾；不进入旧S0维护或更改持卷代次。"""
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
QUERY='query-c2195dd80e21477c9f75f44cf29e8ad0'
PARENT='7e3085f4533143fb84b49adc83159998'
EXECUTION='1a396b17dc654ab09d72119870db69e0'
OWNER='oracle-execution-2262397f3f0b4e4c884d201de49aea6e'
PG='79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545'
SOURCE='65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1'
STABLE='5b786878c681a5a05c2cddd0079d654fd06d7d7ed05001cab1ca5822594c1f57'
FAILURE_AUDIT='9bc224697554422480d502c2d9b2262d'
FAILURE_SHA='e8ffbaa43779ae60fc76c3e67d703365719f0a698cafa3e43c1f385d0078edf0'
DOCKER=['docker','--context','desktop-linux']
MIB=1024**2


def save(path,value):
    resume.platform.save(path,value,path.exists())


def command(stage,args,payload=None,timeout=30,cleanup=False):
    result=ex.run(args,ROOT,task=TASK,run_id=RUN,stage='s23-preparation-'+stage,
        stdin=payload,timeout=timeout,cleanup=cleanup,input_key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),
            producer=ex.sha(Path(__file__).read_bytes())))))
    require(result.returncode==0,'S23_PREPARATION_'+stage+'_'+result.receipt['commandId'])
    return result.stdout.decode().strip(),result.receipt['commandId']


def pg(stage,sql,database='mapping',cleanup=False):
    require(database in ('mapping','postgres') or re.fullmatch('omq_query_test_[a-f0-9]{12}',database),'S23_PREPARATION_DB')
    return command(stage,[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d',database,'-v','ON_ERROR_STOP=1'],sql.encode(),cleanup=cleanup)


def isolated_test():
    """在当前替代PG的新nonce库实测正式恢复事务，只有该库及本次辅助进程可被收口。"""
    require(os.environ.get('OMQ_PRODUCT_RUN')==RUN,'S23_PREPARATION_RUN')
    manifest=resume.manifest();require(manifest['ids']['platform-pg']==PG and manifest['ids']['oracle']==SOURCE,'S23_PREPARATION_INSTANCES')
    attempt=uuid.uuid4().hex;nonce=attempt[:12];database='omq_query_test_'+nonce
    owner=TASK+':implementation-01:'+nonce
    directory=AREA/('preparation-pg-'+attempt);directory.mkdir(mode=0o700)
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
        allowance=40*1024**3-admission['platformDisk']['totalBytes']-64*MIB
        require(allowance>=16*MIB,'S23_PREPARATION_PG_HEADROOM')
        row['capacityBytes']=allowance
        prepared=ROOT/'artifacts/workflow'/TASK/'environment/d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43/runs/3463d8ec1a64483989d9f2b531190dbb/receipt.json'
        prep=json.loads(ex.ordinary(prepared).read_bytes())
        # 只使用已恢复的本地引用及展开包，不宣称已回收feed的完整prepare仍然READY。
        source=Path(__file__).with_suffix('.cs.txt');sdk=Path(prep['dotnet']).parent
        refs=[p for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref') for p in sorted((sdk/'packs'/pack/'10.0.13/ref/net10.0').glob('*.dll'))]
        tests=ROOT/Path(build.TARGETS['query']).parent/'bin/Debug/net10.0'
        refs.append(tests/'Npgsql.dll');dll=directory/'IsolatedPgTests.dll'
        argv=[prep['dotnet'],str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-target:exe','-deterministic+','-nostdlib+','-nullable:enable','-out:'+str(dll),*['-r:'+str(p) for p in refs],str(source)]
        result=ex.run(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*argv],ROOT,task=TASK,run_id=RUN,
            stage='s23-preparation-pg-driver-build',input_key=ex.sha(ex.encoded({str(p):ex.sha(p.read_bytes()) for p in [source,*refs]})),environment=prep['environment'],timeout=45)
        row['commands'].append(dict(stage='driver-build',commandId=result.receipt['commandId']));save(file,row);require(result.returncode==0,'S23_PREPARATION_DRIVER_BUILD')
        row['driverSha256']=ex.sha(dll.read_bytes());row['buildInputKey']=build.inputs('query');row['outputs']=build.outputs('query')
        require(db_state('test-db-absent') is None,'S23_PREPARATION_TEST_DB_EXISTS')
        query('test-db-create',f'CREATE DATABASE {database};');created=True
        query('test-db-bind',f"COMMENT ON DATABASE {database} IS '{owner}';")
        state=db_state('test-db-identity');require(state['comment']==owner and state['owner']=='postgres' and state['sessions']==0,'S23_PREPARATION_TEST_DB_OWNER');row['databaseOid']=state['oid'];save(file,row)
        lsn=query('test-db-lsn','SELECT pg_current_wal_insert_lsn();');require(re.fullmatch('[0-9A-F]+/[0-9A-F]+',lsn),'S23_PREPARATION_LSN')
        import workflow_oracle_preparation_runner as runner
        runner_binding=runner.verified_runner();row['runnerBinding']=runner_binding;save(file,row)
        # 使用同一个现有平台网络及合成配置；无监听端口，无源网络，不创建数据卷。
        script='set -eu; umask 077; cd /tmp; mkdir run; cd run; for f in /app/*.dll; do case "$f" in */OntologyPlatform.QueryTests.dll) ;; *) ln -s "$f" . ;; esac; done; cp /maintenance/OntologyPlatform.QueryTests.dll .; cp /runner/IsolatedPgTests.dll .; cp /app/OntologyPlatform.QueryTests.runtimeconfig.json .; cp /app/OntologyPlatform.QueryTests.deps.json .; exec dotnet exec --runtimeconfig /app/OntologyPlatform.QueryTests.runtimeconfig.json --depsfile /app/OntologyPlatform.QueryTests.deps.json IsolatedPgTests.dll "$1" "$2" "$3"'
        args=[*DOCKER,'create','--pull=never','--read-only','--network',resume.net_names()['platform-internal'],'--user',str(os.getuid())+':'+str(os.getgid()),
            '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--cap-drop=ALL','--security-opt=no-new-privileges',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
            '--mount','type=bind,src='+str(tests)+',dst=/app,readonly','--mount','type=bind,src='+str(tests)+',dst=/query-tests,readonly',
            '--mount','type=bind,src='+str(resume.RESTORED/'platform/api')+',dst=/private/api,readonly','--mount','type=bind,src='+str(directory)+',dst=/runner,readonly','--mount','type=bind,src='+str(runner.DIRECTORY)+',dst=/maintenance,readonly',
            '--mount','type=bind,src='+str(evidence)+',dst=/evidence','--entrypoint=/bin/sh',resume.platform.PROBE,'-ec',script,'preparation-pg',nonce,lsn,str(allowance)]
        helper=call('test-helper-create',args);require(re.fullmatch('[a-f0-9]{64}',helper),'S23_PREPARATION_HELPER');row['helperId']=helper;save(file,row)
        fmt='{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}'
        before=call('test-helper-before',[*DOCKER,'inspect','-f',fmt,helper]);row['helperBefore']=before;save(file,row)
        require(before.split('|')[:6]==[helper,resume.platform.IMAGES['api'],attempt,'created',str(512*MIB),'500000000'],'S23_PREPARATION_HELPER_IDENTITY')
        result=ex.run([*DOCKER,'start','-a',helper],ROOT,task=TASK,run_id=RUN,stage='s23-preparation-pg-actual',timeout=80,input_key=ex.sha(ex.encoded(row)))
        row['actualCommandId']=result.receipt['commandId'];row['actualExitCode']=result.returncode;save(file,row)
        row['test']=[json.loads(line) for line in result.stdout.splitlines() if line.strip()];save(file,row)
        require(result.returncode==0 and len(row['test'])==1,'S23_PREPARATION_TEST_FAILED')
        test=row['test'][0];require(test['method']=='G4QueryRaceTests.OraclePreparationFailureMaintenanceInIsolatedPostgres' and test['total']==test['succeeded']==test['expected']==1
            and test['failed']==test['skipped']==test['exitCode']==0 and not test['timedOut'] and test['peakDbPlusWalBytes']<allowance,'S23_PREPARATION_TEST_RESULT')
        for kind in ('stdout','stderr'):
            raw=ex.ordinary(evidence/(kind+'.txt')).read_bytes();require(ex.sha(raw)==test[kind+'Sha256'] and len(raw)==test[kind+'Bytes'],'S23_PREPARATION_TEST_STREAM')
        require(row['buildInputKey']==build.inputs('query') and row['outputs']==build.outputs('query'),'S23_PREPARATION_TEST_BUILD_CHANGED')
        row['execution']='PASS'
    except Exception as error:
        row['execution']='FAIL';row['error']=str(error) if str(error).startswith('ORACLE_ADMISSION_') else type(error).__name__;raise
    finally:
        if helper:
            state=call('test-helper-exit',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True)
            if state.startswith('running|'):
                call('test-helper-term',[*DOCKER,'stop','--signal','TERM','--timeout','-1',helper],timeout=15,cleanup=True)
                state=call('test-helper-exit-after',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True)
            require(state.startswith('exited|') and state.endswith('|false'),'S23_PREPARATION_TEST_HELPER_EXIT')
            call('test-helper-remove',[*DOCKER,'rm',helper],cleanup=True)
            require(not call('test-helper-absent',[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],cleanup=True),'S23_PREPARATION_HELPER_REAPPEARED');row['helperReleased']=True
        if created:
            state=db_state('test-db-before-drop');require(state and state['oid']==row['databaseOid'] and state['comment']==owner and state['owner']=='postgres' and state['sessions']==0,'S23_PREPARATION_TEST_DB_KEEP')
            query('test-db-drop',f'DROP DATABASE {database};',cleanup=True);require(db_state('test-db-after-drop') is None,'S23_PREPARATION_TEST_DB_DROP');row['databaseReleased']=True
        after=resume.admit();row['afterAdmission']=after['attempt'];row['status']='PASS' if row.get('execution')=='PASS' and row.get('helperReleased') and row.get('databaseReleased') else 'FAIL';save(file,row)
    return dict(status=row['status'],receipt=str(file.relative_to(ROOT)),actualCommandId=row['actualCommandId'])


SEAL=AREA/'preparation-api-seal.json'
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
            and v[4]=='running' and int(v[5])>0,'S23_PREPARATION_HOST_IDENTITY')
    return dict(commandId=cid,rows=rows)


def seal():
    """只封闭本次失败父窗的两个无状态API；五个持卷进程保持同代，原失败不变。"""
    from doris_keep_drain import COUNTS
    import socket,time
    require(os.environ.get('OMQ_PRODUCT_RUN')==RUN and not SEAL.exists(),'S23_PREPARATION_SEAL_ONCE')
    manifest=resume.manifest();ids=manifest['ids'].copy()
    previous=json.loads((resume.AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json')).read_bytes())
    require(previous['exitCode']==1 and previous['host']['oracle']['containerId']==SOURCE
        and ids=={**{k:v['containerId'] for k,v in previous['host']['services'].items()},'oracle':SOURCE},'S23_PREPARATION_SEAL_PARENT')
    row=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',parentCommandId=PARENT,queryId=QUERY,ids=ids,status='SEALING',apis={})
    row['before']=host_rows('seal-before',ids);save(SEAL,row)
    counts,cid=pg('seal-drain-before','SELECT json_build_array('+','.join('('+s.strip()+')' for s in COUNTS)+');')
    require(json.loads(counts)==[0]*7,'S23_PREPARATION_SEAL_DRAIN');row['drainBefore']=cid;save(SEAL,row)
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
                        require(time.monotonic()<deadline,'S23_PREPARATION_PORT_DRAIN');time.sleep(1)
            row['apis'][role]['postAdmission']=resume.admit()['attempt'];save(SEAL,row)
        absent,cid=resume.command('entry-api-absent-'+role,['ps','-aq','--no-trunc','--filter','id='+ids[role]])
        require(not absent and role not in resume.manifest()['ids'],'S23_PREPARATION_SEAL_PRESENT')
        row['apis'].setdefault(role,dict(id=ids[role]))['absentCommandId']=cid;save(SEAL,row)
    row['after']=host_rows('seal-after',{k:v for k,v in ids.items() if k not in resume.APIS})
    require(row['after']['rows']=={k:v for k,v in row['before']['rows'].items() if k not in resume.APIS},'S23_PREPARATION_DATA_RESTARTED')
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
            require(match is not None,'S23_PREPARATION_COMMAND_NAME');return original(match[1],match[2])
    producer=ex.sha(Path(__file__).read_bytes())
    key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),producer=producer)))
    receipt,out,err=Commands().command(cid,args,'s23-preparation-'+stage,key,None,ROOT,command_run=RUN)
    require(receipt['classification']=='SUCCESS' and receipt['exitCode']==0 and receipt['deadlineSeconds']==timeout,'S23_PREPARATION_COMMAND_FAILED')
    return receipt,out,err


def verify_seal():
    """准确失败父窗与两个API TERM/退出/移除/缺席全部真实命令组成封闭证明。"""
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    data=original(PARENT,'receipt.json');require(ex.sha(data)=='baa50ea0b1515612b6fbb28b0df6c6a0f42dd5c6da2815866c7a5c4c0258a0f2','S23_PREPARATION_PARENT_RECEIPT')
    parent=json.loads(data);require(parent['exitCode']==1 and parent['classification']=='EXIT_FAILURE','S23_PREPARATION_PARENT_FAILED')
    data=ex.ordinary(resume.AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json')).read_bytes()
    require(ex.sha(data)=='7157305e4b5a50374c32c1cdd1fa45c441bf84789d2a633ee6348d66fb698085','S23_PREPARATION_PARENT_DISPATCH')
    dispatch=json.loads(data);ids={**{k:v['containerId'] for k,v in dispatch['host']['services'].items()},'oracle':SOURCE}
    row=json.loads(ex.ordinary(SEAL).read_bytes())
    require((row['taskId'],row['runId'],row['batch'],row['parentCommandId'],row['queryId'],row['status'])==(TASK,RUN,'s2-s3-01',PARENT,QUERY,'APIS_REMOVED_DATA_GENERATIONS_UNCHANGED')
        and row['ids']==ids and set(row['apis'])==set(resume.APIS),'S23_PREPARATION_SEAL_SCOPE')
    hosts=[]
    for stage,selected in [('before',ids),('after',{k:v for k,v in ids.items() if k not in resume.APIS})]:
        names=sorted(selected)
        receipt,out,_=reopen_command(row[stage]['commandId'],[*DOCKER,'inspect','-f',resume.platform.HOST_FORMAT,*[selected[n] for n in names]],'seal-'+stage)
        require(row[stage]['rows']=={n:line.split('|') for n,line in zip(names,out.decode().strip().splitlines(),strict=True)},'S23_PREPARATION_SEAL_HOST')
        hosts.append(receipt)
    require(row['after']['rows']=={k:v for k,v in row['before']['rows'].items() if k not in resume.APIS}
        and utc(parent['endedAtUtc'])<=utc(hosts[0]['startedAtUtc'])<utc(hosts[1]['startedAtUtc']),'S23_PREPARATION_SEAL_GENERATIONS')
    c.observed_oracle(ROOT,dispatch['host'])
    host_names=[*sorted(dispatch['host']['services']),'oracle']
    original_rows={name:line.split('|') for name,line in zip(host_names,original(dispatch['host']['commandId']).decode().strip().splitlines(),strict=True)}
    def canonical_rows(rows):
        return {name:[*value[:7],json.loads(value[7]),dict(pair.split('=') for pair in value[8].split())] for name,value in rows.items()}
    require(canonical_rows(row['before']['rows'])==canonical_rows(original_rows),'S23_PREPARATION_SEAL_PARENT_GENERATIONS')
    for role,api in row['apis'].items():
        resource=ids[role];require(api['id']==resource,'S23_PREPARATION_SEAL_API_ID');end=utc(hosts[0]['endedAtUtc'])
        for kind in ('term','exit','remove','absent'):
            if kind=='term':args=['stop','--signal','TERM','--timeout','-1',resource];stage='resume-api-term';seconds=45
            elif kind=='exit':args=['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',resource];stage='resume-api-exit';seconds=30
            elif kind=='remove':args=['rm',resource];stage='resume-remove-stateless';seconds=30
            else:args=['ps','-aq','--no-trunc','--filter','id='+resource];stage='entry-api-absent-'+role;seconds=30
            argv=[*DOCKER,*args];key=ex.sha(ex.encoded(args));matches=[]
            for path in (ROOT/'artifacts/workflow'/TASK/'commands'/RUN).glob('*/receipt.json'):
                value=json.loads(ex.ordinary(path).read_bytes())
                if value['stage']==stage and value['inputFingerprint']==key and value['exitCode']==0 and end<=utc(value['startedAtUtc'])<=utc(value['endedAtUtc'])<=utc(hosts[1]['startedAtUtc']):matches.append(value['commandId'])
            require(len(matches)==1,'S23_PREPARATION_SEAL_COMMAND_UNIQUE');cid=matches[0]
            receipt,out,_=c.command(ROOT,cid,RUN,argv,stage,key,seconds)
            if kind=='exit':require(out.strip() in (b'exited 0 false',b'exited 143 false'),'S23_PREPARATION_SEAL_EXIT')
            elif kind=='absent':require(cid==api['absentCommandId'] and not out.strip(),'S23_PREPARATION_SEAL_ABSENT')
            else:require(out.decode().strip()==resource,'S23_PREPARATION_SEAL_ACTION')
            end=utc(receipt['endedAtUtc'])
    return hosts[1]


def prestate():
    """独立新连接采集准确行、所有审计与两次源端零会话；返回五分钟有界证明。"""
    from doris_keep_drain import COUNTS,ACTIVITY
    require(os.getuid()==501 and os.environ.get('OMQ_PRODUCT_RUN')==RUN,'S23_PREPARATION_OPERATOR')
    verify_seal()
    sealed=json.loads(ex.ordinary(SEAL).read_bytes());require(sealed['status']=='APIS_REMOVED_DATA_GENERATIONS_UNCHANGED','S23_PREPARATION_NOT_SEALED')
    ids=resume.manifest()['ids'];require(set(ids)==set(sealed['after']['rows']) and ids['platform-pg']==PG and ids['oracle']==SOURCE,'S23_PREPARATION_CLOSED_IDS')
    attempt=uuid.uuid4().hex;path=AREA/('preparation-prestate-'+attempt+'.json');row=dict(taskId=TASK,runId=RUN,attemptId=attempt,commands={},status='OBSERVING')
    row['host']=host_rows('prestate-host',ids);require(row['host']['rows']==sealed['after']['rows'],'S23_PREPARATION_GENERATIONS')
    for role,api in sealed['apis'].items():
        absent,cid=command('prestate-absent-'+role,[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+api['id']]);require(not absent,'S23_PREPARATION_API_RETURNED');row['commands']['absent-'+role]=cid
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    value,cid=pg('prestate-drain',sql);require(json.loads(value)==[0]*8,'S23_PREPARATION_DRAIN');row['commands']['drain']=cid
    for which in ('first','second'):
        value,cid=command('source-zero-'+which,[*DOCKER,'exec','-i',SOURCE,'sqlplus','-L','-s','/ as sysdba'],SOURCE_SQL.encode())
        require(value.strip()=='0','S23_PREPARATION_SOURCE_SESSIONS');row['commands']['source-'+which]=cid
    data,cid=pg('prestate-row',ROW_SQL);row['commands']['row']=cid;before=json.loads(data)
    require(before==json.loads(original('e080f26719734e7c84b9e941680ac565')),'S23_PREPARATION_ROW_CHANGED')
    data,cid=pg('prestate-audit',AUDIT_SQL);row['commands']['audit']=cid;audits=json.loads(data)
    require(audits==json.loads(original('fad1a66d2ce94270afdf349400efa63f')),'S23_PREPARATION_AUDIT_CHANGED')
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
    require(path.parent==AREA and path.name=='preparation-prestate-'+proof['attemptId']+'.json' and row['proofSha256']==ex.sha(ex.encoded(proof))
        and proof['sealSha256']==ex.sha(SEAL.read_bytes()) and proof['terminationProofSha256']==ex.sha(ex.encoded(row['termination'])),'S23_PREPARATION_PROOF_HASH')
    now=dt.datetime.now(dt.timezone.utc);require(utc(proof['verifiedUtc'])<=now<utc(proof['validUntilUtc']) and utc(proof['validUntilUtc'])-utc(proof['verifiedUtc'])==dt.timedelta(minutes=5),'S23_PREPARATION_PROOF_STALE')
    ids=resume.manifest()['ids'];names=sorted(ids)
    host,body,_=reopen_command(row['host']['commandId'],[*DOCKER,'inspect','-f',resume.platform.HOST_FORMAT,*[ids[n] for n in names]],'prestate-host')
    require(row['host']['rows']==sealed['after']['rows']=={n:line.split('|') for n,line in zip(names,body.decode().strip().splitlines(),strict=True)},'S23_PREPARATION_PROOF_HOST')
    require(utc(seal_end['endedAtUtc'])<=utc(host['startedAtUtc']),'S23_PREPARATION_PROOF_AFTER_SEAL')
    last_absence=utc(host['endedAtUtc'])
    for role,api in sealed['apis'].items():
        receipt,out,_=reopen_command(row['commands']['absent-'+role],[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+api['id']],'prestate-absent-'+role)
        require(not out.strip() and last_absence<=utc(receipt['startedAtUtc']),'S23_PREPARATION_PROOF_ABSENT')
        last_absence=utc(receipt['endedAtUtc'])
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    receipt,out,_=reopen_command(row['commands']['drain'],[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],'prestate-drain',sql.encode())
    require(json.loads(out)==[0]*8 and last_absence<=utc(receipt['startedAtUtc']),'S23_PREPARATION_PROOF_DRAIN');end=utc(receipt['endedAtUtc'])
    for which in ('first','second'):
        receipt,out,_=reopen_command(row['commands']['source-'+which],[*DOCKER,'exec','-i',SOURCE,'sqlplus','-L','-s','/ as sysdba'],'source-zero-'+which,SOURCE_SQL.encode())
        require(out.strip()==b'0' and end<=utc(receipt['startedAtUtc']),'S23_PREPARATION_PROOF_ZERO');end=utc(receipt['endedAtUtc'])
    for name,sql,expected in [('row',ROW_SQL,'e080f26719734e7c84b9e941680ac565'),('audit',AUDIT_SQL,'fad1a66d2ce94270afdf349400efa63f')]:
        receipt,out,_=reopen_command(row['commands'][name],[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],'prestate-'+name,sql.encode())
        require(json.loads(out)==json.loads(original(expected)) and end<=utc(receipt['startedAtUtc'])<=utc(receipt['endedAtUtc'])<=utc(proof['verifiedUtc']),'S23_PREPARATION_PROOF_ORIGINAL');end=utc(receipt['endedAtUtc'])
    require(proof['stableRowSha256']==STABLE and proof['failureAuditId']==FAILURE_AUDIT and proof['failureAuditSha256']==FAILURE_SHA,'S23_PREPARATION_PROOF_TARGET')
    return row


def recover(path):
    """只执行准确FAILED行的一次两列CAS；维护审计和新连接后验独立于产品成功。"""
    row=verify_prestate(path);proof=row['proof'];attempt=proof['attemptId'];file=AREA/('preparation-recovery-'+attempt+'.json')
    require(not file.exists() and not list(AREA.glob('preparation-recovery-*.json')),'S23_PREPARATION_RECOVERY_ONCE')
    qualified_raw=ex.ordinary(AREA/'preparation-pg-6b7675c651b84ffbb3d9d87683545f62/receipt.json').read_bytes()
    require(ex.sha(qualified_raw)=='1bd0437577fd7537b3b9c94593af1db56c2175959716c3f9b6200461177e0d68','S23_PREPARATION_TEST_ORIGINAL')
    qualified=json.loads(qualified_raw)
    import workflow_oracle_preparation_runner as runner
    runner_binding=runner.verified_runner()
    require(qualified['runnerBinding']==runner_binding,'S23_PREPARATION_TEST_RUNNER')
    require(qualified['status']=='PASS' and qualified['helperReleased'] and qualified['databaseReleased'] and qualified['buildInputKey']==build.inputs('query')
        and qualified['outputs']==build.outputs('query'),'S23_PREPARATION_TEST_BINDING')
    binding=build.validate('api',TASK)
    args,script=recovery_argv(proof,row['proofSha256'])
    helper,cid=command('recovery-create',[*args,'--entrypoint=/bin/sh',resume.platform.PROBE,'-ec',script]);require(re.fullmatch('[a-f0-9]{64}',helper),'S23_PREPARATION_RECOVERY_ID')
    receipt=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',helperId=helper,attemptId=attempt,operationId=proof['operationId'],proofFile=str(path.relative_to(ROOT)),
        proofSha256=row['proofSha256'],build=binding,runnerBinding=runner_binding,qualifiedTest='preparation-pg-6b7675c651b84ffbb3d9d87683545f62/receipt.json',createCommandId=cid,status='CREATED');save(file,receipt)
    try:
        state,cid=command('recovery-before',[*DOCKER,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}',helper]);receipt['beforeCommandId']=cid
        require(state=='|'.join((helper,resume.platform.IMAGES['api'],attempt,'created')),'S23_PREPARATION_RECOVERY_OWNER')
        verify_prestate(path)
        result=ex.run([*DOCKER,'start','-a','-i',helper],ROOT,task=TASK,run_id=RUN,stage='s23-preparation-recovery-cas',stdin=ex.encoded(proof),timeout=32,input_key=row['proofSha256'])
        receipt['actualCommandId']=result.receipt['commandId'];receipt['exitCode']=result.returncode;save(file,receipt)
        require(result.returncode==0 and (not result.stderr or (len(result.stderr)==127 and ex.sha(result.stderr)=='6a55ce9418db27c92344e3846e6ec6fe5718cb84e315fe05c82d3403ebff3a9d')),'S23_PREPARATION_RECOVERY_FAILED');receipt['commitEnvelope']=json.loads(result.stdout)
        require(receipt['commitEnvelope']['status']=='TASK_LEVEL_RECOVERY' and receipt['commitEnvelope']['operationId']==proof['operationId'],'S23_PREPARATION_RECOVERY_OUTCOME')
    finally:
        state,cid=command('recovery-exit',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True);receipt['exitCommandId']=cid;save(file,receipt)
        if state.startswith('running|'):
            command('recovery-term',[*DOCKER,'stop','--signal','TERM','--timeout','-1',helper],timeout=15,cleanup=True)
            state,cid=command('recovery-exit-after',[*DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],cleanup=True);receipt['exitAfterCommandId']=cid
        require(state.startswith('exited|') and state.endswith('|false'),'S23_PREPARATION_RECOVERY_EXIT')
        _,cid=command('recovery-remove',[*DOCKER,'rm',helper],cleanup=True);receipt['removeCommandId']=cid
        out,cid=command('recovery-absent',[*DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],cleanup=True);receipt['absentCommandId']=cid;receipt['helperReleased']=not out;save(file,receipt)
        require(not out,'S23_PREPARATION_RECOVERY_HELPER_PRESENT')
    data,cid=pg('post-row',ROW_SQL);receipt['rowCommandId']=cid;post=json.loads(data);before=json.loads(original('e080f26719734e7c84b9e941680ac565'))
    require(post=={**before,'owner':None,'leaseUntilUtc':None},'S23_PREPARATION_POST_ROW')
    data,cid=pg('post-audit',AUDIT_SQL);receipt['auditCommandId']=cid;audits=json.loads(data);failure=json.loads(original('fad1a66d2ce94270afdf349400efa63f'))[0]
    require(len(audits)==2 and failure in audits,'S23_PREPARATION_POST_FAILURE_AUDIT')
    new=next(a for a in audits if a!=failure);require(new['action']=='data.query.cleanup.recover' and new['outcome']=='allowed' and new['actor']==proof['operatorId']
        and new['trace']==proof['operationId'] and new['correlation']==attempt and new['organization']=='org-demo' and new['sites']==['site-a'],'S23_PREPARATION_POST_RECOVERY_AUDIT')
    receipt.update(status='TASK_LEVEL_RECOVERY',post=post,audits=audits,originalCleanup250ms='NOT_QUALIFIED');save(file,receipt);return receipt


def recovery_argv(proof,proof_sha):
    """固定单条证明的一次性非HTTP执行器；产品bin仅只读挂载，所有新文件位于tmpfs。"""
    import workflow_oracle_preparation_runner as runner
    api=ROOT/Path(build.TARGETS['query']).parent/'bin/Debug/net10.0';attempt=proof['attemptId']
    private=resume.RESTORED/'platform/postgres';require(all((private/n).is_file() and not (private/n).is_symlink() for n in ('password','server.crt')),'S23_PREPARATION_PRIVATE_INPUTS')
    script=('umask 077; set -eu; test "$(id -u)" = 501; '
        'printf "Host=platform-pg;Port=5432;Database=mapping;Username=postgres;SSL Mode=VerifyFull;Root Certificate=/ca;Password=%s" '
        '"$(cat /auth)" > /tmp/maintenance.dsn; cd /tmp; mkdir run; cd run; '
        'for f in /app/*.dll; do case "$f" in */OntologyPlatform.QueryTests.dll) ;; *) ln -s "$f" . ;; esac; done; '
        'cp /maintenance/OntologyPlatform.QueryTests.dll .; cp /app/OntologyPlatform.QueryTests.runtimeconfig.json .; cp /app/OntologyPlatform.QueryTests.deps.json .; '
        'exec dotnet exec --runtimeconfig /tmp/run/OntologyPlatform.QueryTests.runtimeconfig.json --depsfile /tmp/run/OntologyPlatform.QueryTests.deps.json /tmp/run/OntologyPlatform.QueryTests.dll --recover-preparation')
    args=[*DOCKER,'create','--pull=never','-i','--network',resume.net_names()['platform-internal'],'--read-only','--user',str(os.getuid())+':'+str(os.getgid()),
        '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--security-opt=no-new-privileges','--cap-drop=ALL',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
        '--mount','type=bind,src='+str(api)+',dst=/app,readonly','--mount','type=bind,src='+str(private/'password')+',dst=/auth,readonly',
        '--mount','type=bind,src='+str(private/'server.crt')+',dst=/ca,readonly','--mount','type=bind,src='+str(runner.DIRECTORY)+',dst=/maintenance,readonly']
    env={'DSN_FILE':'/tmp/maintenance.dsn','OPERATOR':proof['operatorId'],'PROOF_SHA256':proof_sha,'SEAL_SHA256':proof['sealSha256'],'TERMINATION_SHA256':proof['terminationProofSha256']}
    for key,value in env.items():args+=['-e','OMQ_S23_MAINTENANCE_'+key+'='+value]
    return args,script
