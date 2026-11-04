#!/usr/bin/env python3
"""在本Run保留的G3合成平台PG上验证Host迁移、权限拒绝及恢复；不执行Down。"""
import json
import os
import secrets
import subprocess
import time
import runtime as rt
import readback
import closeout


def platform_sql(m, sql):
    """只供本文件固定故障语句与只读投影使用，不接受CLI SQL。"""
    ident=rt.runtime_value(m)['containerIds']['platform-pg'];rt.inspect_owned(m,ident,'platform-pg')
    return rt.docker(m,['exec','-i',ident,'psql','-X','-qAt','-U','platform','-d','platform','-v','ON_ERROR_STOP=1'],input_bytes=("SET statement_timeout='5s'; SET lock_timeout='2s';"+sql).encode()).decode().strip()


def g3_rows(m,audit_ids=None):
    """只输出现有G3表的计数和整行摘要，不导出行内容、票据或审计详情。"""
    names=platform_sql(m,"BEGIN READ ONLY; SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname IN ('ontology','publishing') ORDER BY 1; COMMIT;").splitlines()
    import re
    result={}
    for name in names:
        rt.require(re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*\.[a-zA-Z_][a-zA-Z_0-9]*',name),'G3_TABLE_IDENTIFIER')
        schema,table=name.split('.')
        value=platform_sql(m,'BEGIN READ ONLY; SELECT count(*)::text||\'|\'||coalesce(md5(string_agg(to_jsonb(t)::text,\'\' ORDER BY to_jsonb(t)::text)),\'empty\') FROM "'+schema+'"."'+table+'" t; COMMIT;')
        result[name]=value
    rt.require(result,'G3_ROWS_MISSING')
    if audit_ids is None:
        audit_ids=json.loads(platform_sql(m,'BEGIN READ ONLY; SELECT coalesce(json_agg("Id"::text ORDER BY "Id"),\'[]\'::json) FROM governance.audit_records; COMMIT;'))
    rt.require(audit_ids and all(re.fullmatch('[a-f0-9-]{32,36}',x) for x in audit_ids),'G3_AUDIT_IDS')
    ids=','.join("'"+x+"'" for x in audit_ids)
    result['governance.audit_records']={'ids':audit_ids,'summary':platform_sql(m,'BEGIN READ ONLY; SELECT count(*)::text||\'|\'||coalesce(md5(string_agg(to_jsonb(t)::text,\'\' ORDER BY to_jsonb(t)::text)),\'empty\') FROM governance.audit_records t WHERE "Id"::text IN ('+ids+'); COMMIT;')}
    return result


def replace_config(m, config, name):
    """每个受控配置保存只读前像及散列；动态凭据只写0700私有目录。"""
    path=rt.private_dir(m['runId'])/'api/appsettings.json'
    rt.boundary(path,path.parent,exists=True,private=True)
    old=path.read_bytes();backup=path.with_name('appsettings-'+name+'-before.json')
    rt.require(not backup.exists(),'EXISTING_CONFIG_WITNESS')
    os.rename(path,backup);rt.write_json(path,config,private=True)
    rt.write_json(rt.ARTIFACTS/m['runId']/('configuration-'+name+'.json'),{'testedCommit':m['_head'],'driverSha256':rt.digest(__import__('pathlib').Path(__file__).read_bytes()),'beforeSha256':rt.digest(old),'afterSha256':rt.digest(path.read_bytes())})


def restart(m):
    ident=rt.runtime_value(m)['containerIds']['api'];rt.inspect_owned(m,ident,'api')
    rt.docker(m,['restart',ident])
    rt.wait_http('http://localhost:15100/health/live',60,headers={'X-Health-Key':rt.runtime_value(m)['healthKey']})


def retire_g3_volumes(m, registered, *, apply=False):
    """仅回收本Run已登记、无容器引用的两卷；平台PG/OIDC与外部保留集不变。"""
    names=['ontology-g4-main-'+m['runId']+'_'+name for name in ('fuseki-data','rustfs-data')]
    before=closeout.inventory(m)
    rt.require(before['volume']==registered['volume'] and before['network']==registered['network'],'TRANSITION_REGISTRY_DRIFT')
    rt.require(all(before[k]['keep']==registered[k]['keep'] for k in before),'TRANSITION_KEEP_DRIFT')
    rows={row['id']:row for row in before['volume']['owned']}
    rt.require(all(name in rows for name in names),'TRANSITION_VOLUME_UNREGISTERED')
    def validate(name):
        value=json.loads(rt.docker(m,['volume','inspect',name]))[0]
        rt.require(value['Name']==name and value['CreatedAt']==rows[name]['created'],'TRANSITION_VOLUME_VERSION')
        labels=value.get('Labels') or {}
        rt.require(labels.get('ontology.task-id')==rt.TASK and labels.get('ontology.run-id')==m['runId'],'TRANSITION_VOLUME_OWNER')
        rt.require(not rt.docker(m,['ps','-aq','--no-trunc','--filter','volume='+name]).strip(),'TRANSITION_VOLUME_ATTACHED')
    for name in names:validate(name)
    result={'status':'DRY_RUN','taskId':rt.TASK,'runId':m['runId'],'before':before,'candidates':names,'commands':[],'deleted':[]}
    if not apply:return result
    rt.require(closeout.inventory(m)==before,'TRANSITION_RESOURCE_DRIFT')
    rt.write_json(rt.ARTIFACTS/m['runId']/'migration-volume-retirement-plan.json',result)
    journal=rt.ARTIFACTS/m['runId']/'migration-volume-retirement-commands.jsonl'
    rt.require(not journal.exists(),'TRANSITION_EXISTING_JOURNAL')
    def log(value):
        with journal.open('a') as output:
            output.write(json.dumps(value)+'\n');output.flush();os.fsync(output.fileno())
    def observed_command(command):
        try:
            value=subprocess.run(command,capture_output=True,timeout=20)
            return {'command':command,'exitCode':value.returncode,'timingStatus':'COMPLETED','stdoutSha256':rt.digest(value.stdout),'stderrSha256':rt.digest(value.stderr)},value.stderr
        except subprocess.TimeoutExpired as error:
            return {'command':command,'exitCode':None,'timingStatus':'TIMEOUT_EXIT_NOT_VERIFIED','stdoutSha256':rt.digest(error.output or b''),'stderrSha256':rt.digest(error.stderr or b'')},b''
        except OSError as error:
            return {'command':command,'exitCode':None,'timingStatus':'START_FAILED','errorType':type(error).__name__,'errorErrno':error.errno},b''
    result['status']='FAIL'
    try:
        for name in names:
            validate(name)
            command=['docker','--context','desktop-linux','volume','rm',name]
            log({'phase':'BEFORE','command':command,'expectedCreated':rows[name]['created']})
            removed,_=observed_command(command);result['commands'].append(removed)
            log({'phase':'COMMAND_EXIT',**removed})
            observed,stderr=observed_command(['docker','--context','desktop-linux','volume','inspect',name])
            absent=observed['timingStatus']=='COMPLETED' and observed['exitCode']!=0 and b'no such volume' in stderr.lower() and name.encode() in stderr
            observed['exactAbsent']=absent;result['commands'].append(observed)
            log({'phase':'AFTER',**observed})
            rt.require(removed['exitCode']==0,'TRANSITION_VOLUME_REMOVE_FAILED')
            rt.require(absent,'TRANSITION_VOLUME_ABSENCE')
            result['deleted'].append(name)
        after=closeout.inventory(m)
        expected=json.loads(json.dumps(before));expected['volume']['owned']=[row for row in expected['volume']['owned'] if row['id'] not in names]
        rt.require(after==expected,'TRANSITION_RETAINED_RESOURCE_DRIFT')
        result['status']='PASS'
    except BaseException as error:
        result['errorType']=type(error).__name__
        raise
    finally:
        try:result['after']=closeout.inventory(m)
        except BaseException as error:
            result['status']='FAIL';result['afterObservationError']=type(error).__name__
        rt.write_json(rt.ARTIFACTS/m['runId']/'migration-volume-retirement.json',result)
    rt.require(result['status']=='PASS','TRANSITION_AFTER_OBSERVATION_FAILED')
    return result


def verify_all(m):
    """G3保持原行，串行替换设施；真实Host首次、重复、权限恢复三类实测。"""
    rt.check_build(m);r=rt.runtime_value(m)
    rt.require(r['group']=='g3','G3_GROUP_REQUIRED')
    before=g3_rows(m)
    rt.require(platform_sql(m,"SELECT count(*) FROM pg_namespace WHERE nspname='connections';")=='0','G4_DISABLED_MIGRATED')
    before_resources=closeout.inventory(m)
    creation=json.loads((rt.ARTIFACTS/m['runId']/'resources-g3-owned.json').read_text())
    rt.require(all(creation[k]['owned']==before_resources[k]['owned'] for k in before_resources),'TRANSITION_CREATION_DRIFT')
    rt.write_json(rt.ARTIFACTS/m['runId']/'migration-g3-before.json',{'rows':before,'resources':before_resources})
    ingress_before=rt.stop_ingress(m,'g3')
    # 先回收4个已登记服务，保留本轮PG、OIDC和其合成卷；最大仍5容器。
    for service in ('web','api','fuseki','rustfs'):
        ident=r['containerIds'][service];rt.inspect_owned(m,ident,service)
        rt.docker(m,['stop','--time','10',ident]);rt.docker(m,['rm',ident])
    retire_g3_volumes(m,before_resources,apply=True)
    path=rt.private_dir(m['runId'])/'api/appsettings.json'
    path.rename(path.with_name('appsettings-g3-closed.json'))
    try:
        rt.execute(m,'transition-m1',rt.compose_command('m1')+['up','-d','--no-build','--pull','never','pg-source','api','web'],env=rt.compose_environment(m),sensitive=True,timeout=180)
    finally:
        rt.write_json(rt.ARTIFACTS/m['runId']/'resources-m1-owned.json',closeout.inventory(m))
        rt.resource_snapshot(m,'m1','resources-m1-created')
    rt.wait_pg(m)
    rt.start_ingress(m,'m1')
    rt.write_json(rt.ARTIFACTS/m['runId']/'migration-ingress-transition.json',{'g3Closed':ingress_before,'m1ReadySha256':rt.digest((rt.ARTIFACTS/m['runId']/'ingress-m1-ready.json').read_bytes())})
    source_before=readback.snapshot(m,'migration-source-before',source=True)
    rt.require(source_before[2]['rows']==['0'],'SOURCE_PLATFORM_SCHEMA')
    rt.configure_api(m,'m1',apply=False)
    config=json.loads(path.read_text());config['G4']['ApplyMigrations']=False
    replace_config(m,config,'apply-false')
    restart(m)
    rt.require(platform_sql(m,"SELECT count(*) FROM pg_namespace WHERE nspname='connections';")=='0','APPLY_FALSE_MIGRATED')
    migration_password=secrets.token_urlsafe(40)
    platform_sql(m,"CREATE ROLE g4_migration_limited LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '"+migration_password+"'; GRANT CONNECT ON DATABASE platform TO g4_migration_limited;")
    limited=json.loads(path.read_text());limited['G4']['ApplyMigrations']=True;limited['Governance']['ApplyMigrations']=False;limited['Governance']['SeedDevelopmentResources']=False
    limited['ConnectionStrings']['governance']='Host=platform-pg;Database=platform;Username=g4_migration_limited;Password='+migration_password
    replace_config(m,limited,'create-denied')
    api=rt.runtime_value(m)['containerIds']['api'];rt.docker(m,['restart',api])
    deadline=time.monotonic()+30
    while rt.inspect_owned(m,api,'api')['State']['Running'] and time.monotonic()<deadline:time.sleep(.2)
    state=rt.inspect_owned(m,api,'api')['State']
    raw=rt.execute(m,'migration-permission-container-log',['docker','--context','desktop-linux','logs','--since','60s',api],sensitive=True)
    log=rt.private_dir(m['runId'])/'logs/migration-create-denied.log'
    with open(log,'xb') as f:os.chmod(log,0o600);f.write(raw)
    rt.require(not state['Running'] and state['ExitCode']!=0 and b'42501' in raw and b'connections' in raw and b'permission denied' in raw.lower(),'EXACT_MIGRATION_PERMISSION_FAILURE')
    rt.require(platform_sql(m,"SELECT count(*) FROM pg_namespace WHERE nspname='connections';")=='0','PARTIAL_SCHEMA_AFTER_DENIAL')
    config['G4']['ApplyMigrations']=True
    replace_config(m,config,'permission-restored');restart(m)
    first=readback.snapshot(m,'migration-first-success')
    rt.require(first[-1]['rows']==['20261101115947_InitialConnections|10.0.13'],'EXACT_HISTORY')
    restart(m);second=readback.snapshot(m,'migration-repeat-success')
    rt.require(first==second,'REPEATED_MIGRATION_DRIFT')
    after=g3_rows(m,before['governance.audit_records']['ids']);rt.require(before==after,'G3_ROW_DRIFT')
    source_after=readback.snapshot(m,'migration-source-after',source=True)
    rt.require(source_before[:3]==source_after[:3],'SOURCE_SCHEMA_DRIFT')
    result={'status':'PASS','applyFalseNoMigration':True,'createPrivilegeDenied':{'exitCode':state['ExitCode'],'logSha256':rt.digest(raw)},'firstAndRepeatHistory':first[-1],'g3Before':before,'g3After':after,'sourceUnchanged':True}
    rt.write_json(rt.ARTIFACTS/m['runId']/'migration-complete.json',result)
    return result
