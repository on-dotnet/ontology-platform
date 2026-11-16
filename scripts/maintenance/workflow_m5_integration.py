#!/usr/bin/env python3
"""M5薄消费者；复用既有PG执行能力，但Task/Run/私有目录/端口/场景均独立。"""
import argparse
from functools import partial
import importlib.util
import json
from pathlib import Path
import sys
from workflow_pg_profile import profile

ROOT=Path(__file__).resolve().parents[2]
TASK='G4-M5-INTEGRATION-001'
RUN='integration-01'
PROFILE=profile(TASK)
# 独立模块命名空间避免改变M4入口的默认身份；没有复制或动态改写源代码。
spec=importlib.util.spec_from_file_location('_m5_pg_consumer',ROOT/'scripts/maintenance/workflow_m4_query.py')
consumer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)
consumer.TASK=TASK
consumer.RUN=RUN
consumer.PROFILE=PROFILE
consumer.demand_aba_original=partial(consumer.demand_aba_original,task=TASK,run_id=RUN)
consumer.demand_qualification=partial(consumer.demand_qualification,task=TASK,run_id=RUN)


# 原分层解释器重开当前M5 Task/Run原件，不接受M4身份或其PASS包装。
consumer.qualify=partial(consumer.qualify,consumer=consumer)


def scenario(name):
    if name not in ('standard','numeric','safety','aba'):
        raise ValueError('INTEGRATION_SCENARIO_INVALID')
    consumer.SCENARIO=name


scenario('standard')


def __getattr__(name):
    return getattr(consumer,name)


def prepare_scenario(name):
    """固定本体发布可复用；连接、映射、会话和查询均从新场景正式产生。"""
    if name=='standard':raise ValueError('INTEGRATION_STANDARD_ALREADY_SETUP')
    scenario(name)
    output=ROOT/'artifacts/workflow'/TASK/RUN
    original=json.loads((output/'scenario-standard.json').read_text())
    if not original.get('mappingReceipt'):raise ValueError('INTEGRATION_STANDARD_CHAIN_REQUIRED')
    path=output/consumer.fixture_file()
    if path.exists():raise ValueError('INTEGRATION_SCENARIO_PRESERVE_EXISTING')
    row={key:value for key,value in original.items() if key.startswith('ontology')}
    row.update(taskId=TASK,runId=RUN,scenario=name,s3=True,numeric=name=='numeric',numericFixturePhase='SETUP' if name=='numeric' else None,scope=original['scope'],connectionDisplayName='M5 synthetic PG '+name)
    path.write_text(json.dumps(row,indent=2)+'\n')
    return dict(taskId=TASK,runId=RUN,scenario=name,fixedOntologyRelease=original['ontologyRelease']['manifest']['releaseId'])


def demand_ready(facts):
    """缺一项即失败；合成反例只检本判定器，不冒充真实场景ready。"""
    for key in ('api','web','build','session','connection','grant','activation','fixture','owner','budget'):
        if facts.get(key) is not True:raise ValueError('PREREQUISITE_STALE:'+key)
    return 'SCENARIO_READY'


def build_api():
    """第一次API启动前完成离线构建与本任务完整只读快照。"""
    from workflow_execution import sha,encoded
    from workflow_m4_query_runtime import freeze,verify
    output=ROOT/'artifacts/workflow'/TASK/RUN
    output.mkdir(parents=True,exist_ok=True)
    before=consumer.runtime_source_inputs()
    result=consumer.runtime_command('query-api-bound-build',['/usr/local/share/dotnet/dotnet','build','backend/src/Hosts/OntologyPlatform.Api',
        '--no-restore','--disable-build-servers','-m:1','-v:q'],timeout=180,offline=True)
    if before!=consumer.runtime_source_inputs():raise ValueError('INTEGRATION_BUILD_INPUT_DRIFT')
    snapshot=freeze(ROOT,ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0',output/'runtime-snapshots',
                    before,result.receipt['commandId'],consumer.runtime_environment_identity(),task=TASK,run_id=RUN)
    binaries=verify(ROOT,snapshot,task=TASK,run_id=RUN)
    (output/'runtime-snapshot-current.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    record=dict(taskId=TASK,runId=RUN,commandId=result.receipt['commandId'],inputs=before,binaries=binaries,inputHash=sha(encoded(before)))
    (output/'runtime-api-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return dict(status='BUILT_FROZEN',snapshotId=snapshot['snapshotId'],commandId=result.receipt['commandId'])


def prepare_runtime():
    """沿用现有配方生成新私有身份，首启挂已冻结快照；不启动旧任务。"""
    from workflow_m4_query_runtime import verify
    output=ROOT/'artifacts/workflow'/TASK/RUN
    snapshot=json.loads((output/'runtime-snapshot-current.json').read_text())
    binaries=verify(ROOT,snapshot,task=TASK,run_id=RUN)
    result=consumer.runtime_prepare()
    path=output/'runtime-compose.json';compose=json.loads(path.read_text())
    # 2026-11-16用户明确批准继承M4双网络；bridge具出站能力，端口只绑定loopback。
    compose['networks']['edge']['internal']=False
    compose['services']['api']['volumes'][0]=str(ROOT/snapshot['directory'])+':/app:ro'
    path.write_text(json.dumps(compose,indent=2)+'\n')
    old=json.loads((output/'runtime-build-binding.json').read_text())
    binaries.update({p:h for p,h in old.items() if '/runtime-helper/' in p})
    (output/'runtime-build-binding.json').write_text(json.dumps(binaries,indent=2)+'\n')
    return result


def numeric_source_fixture():
    """建立可空列但初始非空的numeric夹具；正式Mapping后另加NULL反例。"""
    import subprocess
    from workflow_execution import run,sha
    result=consumer.numeric_source_fixture()
    output=ROOT/'artifacts/workflow'/TASK/RUN
    cid=json.loads((output/'source-resources.json').read_text())['resources'][0]['id']
    prefix=['docker','--context','desktop-linux']
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',cid],timeout=10))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN:raise ValueError('PREREQUISITE_STALE:owner')
    sql="""BEGIN; SET LOCAL statement_timeout='5s';
ALTER TABLE production.numeric_readings ALTER COLUMN numeric_key DROP NOT NULL;
COMMIT;
SELECT json_build_object('matchingTargets',(SELECT json_agg(r.reading_id ORDER BY r.reading_id) FROM production.numeric_assets a JOIN production.numeric_readings r ON a.numeric_key=r.numeric_key AND a.organization_id=r.organization_id AND a.site_id=r.site_id WHERE a.asset_id='asset-1' AND a.site_id='site-a'),'nullTargets',(SELECT count(*) FROM production.numeric_readings WHERE numeric_key IS NULL));
"""
    actual=run([*prefix,'exec','-i',cid,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],ROOT,
               task=TASK,run_id=RUN,stage='m5-numeric-null-independent-sql',stdin=sql.encode(),input_key=sha(sql.encode()),timeout=10)
    if actual.returncode or json.loads(actual.stdout)!={'matchingTargets':['numeric-target-1','numeric-target-2'],'nullTargets':0}:raise ValueError('NUMERIC_INDEPENDENT_SQL_FAILED')
    return dict(status='NUMERIC_FIXTURE_READY',original=result,commandId=actual.receipt['commandId'])


def numeric_add_null():
    """正式Mapping激活后仅增加一条本任务NULL数据，不改变已验证Schema。"""
    import subprocess
    from workflow_execution import run,sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    state_path=output/'scenario-numeric.json';state=json.loads(state_path.read_text())
    if consumer.SCENARIO!='numeric' or not state.get('mappingReceipt') or state.get('numericFixturePhase')!='SETUP':raise ValueError('NUMERIC_PHASE_INVALID')
    cid=json.loads((output/'source-resources.json').read_text())['resources'][0]['id']
    prefix=['docker','--context','desktop-linux']
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',cid],timeout=10))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN:raise ValueError('PREREQUISITE_STALE:owner')
    sql="BEGIN; SET LOCAL statement_timeout='5s'; INSERT INTO production.numeric_readings SELECT organization_id,site_id,'numeric-target-null',asset_id,valid_from,valid_to,observed_at,temperature,unit_code,attributes,NULL FROM production.numeric_readings WHERE reading_id='numeric-target-1'; COMMIT; SELECT count(*) FROM production.numeric_readings WHERE numeric_key IS NULL;"
    result=run([*prefix,'exec','-i',cid,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],ROOT,task=TASK,run_id=RUN,stage='numeric-post-activation-null',stdin=sql.encode(),input_key=sha(sql.encode()),timeout=10)
    if result.returncode or result.stdout.strip()!=b'1':raise ValueError('NUMERIC_NULL_INSERT_FAILED')
    state['numericFixturePhase']='POST_ACTIVATION';state_path.write_text(json.dumps(state,indent=2)+'\n')
    return dict(status='NUMERIC_POST_ACTIVATION_NULL_READY',commandId=result.receipt['commandId'])


def demand_fixture(fixture, numeric, include_null=True):
    """独立固定表/列/行预期；不调用产品映射、numeric比较器或结果canonical。"""
    import datetime
    tables=['numeric_assets','numeric_readings'] if numeric else ['assets','readings']
    names=[['organization_id','site_id','asset_id','valid_from','valid_to','label'],
           ['organization_id','site_id','reading_id','asset_id','valid_from','valid_to','observed_at','temperature','unit_code','attributes']]
    expected=[]
    for table,columns in zip(tables,names):
        for index,column in enumerate(columns+(['numeric_key'] if numeric else []),1):
            data_type='timestamp with time zone' if column in ('valid_from','valid_to','observed_at') else 'numeric' if column in ('temperature','numeric_key') else 'jsonb' if column=='attributes' else 'text'
            precision,scale=(10,2) if column=='numeric_key' and table==tables[0] else (12,3) if column=='numeric_key' else (12,4) if column=='temperature' else (None,None)
            expected.append(dict(table=table,column=column,ordinal=index,type=data_type,precision=precision,scale=scale,nullable='YES' if numeric and table==tables[1] and column=='numeric_key' else 'NO'))
    if fixture['types']!=expected:raise ValueError('PREREQUISITE_STALE:fixture_schema')
    assets=[dict(organization_id='org-demo',site_id='site-'+site,asset_id='asset-1',valid_from='2026-01-01T00:00:00+00:00',valid_to='2027-01-01T00:00:00+00:00',label='合成设备'+label) for site,label in [('a','A'),('b','B')]]
    readings=[]
    for site,ident,start,end,observed,temp in [('a','reading-1','00:00','00:01','00:00:01.123456',20.125),('a','reading-2','00:01','00:02','00:01:01',21),('b','reading-1','00:00','00:01','00:00:01',22)]:
        readings.append(dict(organization_id='org-demo',site_id='site-'+site,reading_id=ident,asset_id='asset-1',valid_from='2026-11-14T'+start+':00+00:00',valid_to='2026-11-14T'+end+':00+00:00',observed_at='2026-11-14T'+observed+'+00:00',temperature=temp,unit_code='Cel',attributes={'quality':'good'}))
    if numeric:
        assets=[dict(row,numeric_key=1) for row in assets]
        readings=[dict(readings[0],reading_id='numeric-target-'+ident,numeric_key=key) for ident,key in ([('1',1),('2',1),('3',1.01)]+([('null',None)] if include_null else []))]
    def normalize(rows):
        result=[]
        for row in rows:
            row=dict(row)
            for key in ('valid_from','valid_to','observed_at'):
                if key in row:row[key]=datetime.datetime.fromisoformat(row[key]).isoformat()
            result.append(row)
        return sorted(result,key=lambda row:json.dumps(row,sort_keys=True))
    if fixture['rows']!=[len(assets),len(readings)] or normalize(fixture['data'][0])!=normalize(assets) or normalize(fixture['data'][1])!=normalize(readings):raise ValueError('PREREQUISITE_STALE:fixture_data')


def demand_grants(rows,state,mapping=False):
    """同一grant须完整覆盖本场景，不把多个残缺grant拼接成授权。"""
    import urllib.parse
    tables=['numeric_assets','numeric_readings'] if state.get('numeric') else ['assets','readings']
    objects=['production/'+name for name in tables]
    fields=['production/'+table['name']+'/'+str(field['ordinal'])+'/'+urllib.parse.quote(field['name'],safe='') for table in state['catalog']['objects'] if table['schema']=='production' and table['name'] in tables for field in table['fields']]
    if not fields:raise ValueError('PREREQUISITE_STALE:grant')
    for role,subject in state['subjects'].items():
        permissions=(['mapping.read','mapping.source.validate']+(['mapping.edit','mapping.validate','mapping.submit','mapping.activate'] if role=='operator' else ['mapping.review','mapping.approve'])) if mapping else (['data.query.execute','data.query.result.read','data.query.evidence.read'] if role=='operator' else [])
        for permission in permissions:
            source=permission=='mapping.source.validate' or permission.startswith('data.query.')
            if not any(row['SubjectId']==subject and row['OrganizationId']==state['scope']['organizationId'] and set(state['scope']['siteIds'])<=set(row['SiteIds']) and row['Permission']==permission and ((row['ConnectionId']==state['connectionId'] and set(objects)<=set(row['ObjectRefs']) and set(fields)<=set(row['FieldRefs'])) if source else (row['ConnectionId'] is None and not row['ObjectRefs'] and not row['FieldRefs'])) for row in rows):raise ValueError('PREREQUISITE_STALE:grant:'+permission)


def live_web_binding():
    """核实本任务监听PID/开始时间/cwd及实际HTTP构建清单，不以TCP替代运行身份。"""
    import subprocess,os,urllib.request
    from workflow_execution import sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    build=consumer.web_binding()
    pids=subprocess.check_output(['lsof','-nP','-t','-iTCP:'+str(PROFILE.ports['web']),'-sTCP:LISTEN'],timeout=5).decode().split()
    if len(set(pids))!=1:raise ValueError('PREREQUISITE_STALE:web_process')
    pid=pids[0];path=output/('web-process-'+pid+'.json')
    if not path.is_file():raise ValueError('PREREQUISITE_STALE:web_process')
    row=json.loads(path.read_text())
    started=subprocess.check_output(['ps','-p',pid,'-o','lstart='],env={**os.environ,'LC_ALL':'C'},timeout=5).decode().strip()
    cwd=subprocess.check_output(['lsof','-a','-p',pid,'-d','cwd','-Fn'],timeout=5).decode().splitlines()
    if row['taskId']!=TASK or row['runId']!=RUN or row['worktree']!=str(ROOT) or row['port']!=PROFILE.ports['web'] or row['processStartedAt']!=started or 'n'+str(ROOT) not in cwd or row['build']!=build:raise ValueError('PREREQUISITE_STALE:web_process')
    relative='static/'+build['buildId']+'/_buildManifest.js'
    with urllib.request.urlopen('http://127.0.0.1:'+str(PROFILE.ports['web'])+'/_next/'+relative,timeout=3) as response:actual=response.read()
    if sha(actual)!=sha((ROOT/'apps/web/.next'/relative).read_bytes()):raise ValueError('PREREQUISITE_STALE:web_build')
    return dict(pid=int(pid),processStartedAt=started,build=build,servedManifestSha256=sha(actual))


def demand_catalog(rows,objects):
    """比较整个允许Schema的独立目录事实，不只检查本场景选中两表。"""
    expected=[dict(schema=obj['schema'],table=obj['name'],kind=obj['kind'],column=field['name'],ordinal=field['ordinal'],type=field['nativeType'],nullable=field['nullable']) for obj in objects for field in obj['fields']]
    key=lambda row:(row['schema'],row['table'],row['ordinal'])
    if sorted(rows,key=key)!=sorted(expected,key=key):raise ValueError('PREREQUISITE_STALE:source_catalog')


def demand_budget(containers, owned_count, pending_memory=0, pending_cpu=0, pending_count=0):
    """总容器数含停止实例；创建前按新增资源核本任务及12核VM共同上限。"""
    owned=[row for row in containers if row['task']==TASK]
    if owned_count+pending_count>7 or any(row['memory']<=0 or row['cpu']<=0 for row in containers):raise ValueError('PREREQUISITE_STALE:budget')
    if sum(row['memory'] for row in owned)+pending_memory>6.5*1024**3 or sum(row['cpu'] for row in owned)+pending_cpu>8e9 or sum(row['memory'] for row in containers)+pending_memory>14*1024**3 or sum(row['cpu'] for row in containers)+pending_cpu>12e9:raise ValueError('PREREQUISITE_STALE:budget')
    return dict(ownedCount=owned_count+pending_count,ownedMemory=sum(row['memory'] for row in owned)+pending_memory,ownedCpu=sum(row['cpu'] for row in owned)+pending_cpu,sharedMemory=sum(row['memory'] for row in containers)+pending_memory,sharedCpu=sum(row['cpu'] for row in containers)+pending_cpu)


def local_ready(require_web=True, require_grants=True, pending_memory=0, pending_cpu=0, pending_count=0):
    """短真实探针先核进程/构建/Owner/配额/源夹具与显式grant；会话和激活由正式API续核。"""
    import socket
    import subprocess
    import uuid
    from workflow_execution import run,sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    binding=consumer.runtime_binding()
    facts=dict(build=True,api=False,web=not require_web,owner=False,budget=False,fixture=False,grant=not require_grants)
    for key in ('api','web') if require_web else ('api',):
        try:
            with socket.create_connection(('127.0.0.1',PROFILE.ports[key]),timeout=2):facts[key]=True
        except OSError:raise ValueError('PREREQUISITE_STALE:'+key)
    web=live_web_binding() if require_web else None
    prefix=['docker','--context','desktop-linux']
    containers=[]
    for cid in subprocess.check_output([*prefix,'ps','-q'],timeout=10).decode().split():
        row=json.loads(subprocess.check_output([*prefix,'inspect','--format',
            '{"id":{{json .Id}},"memory":{{.HostConfig.Memory}},"cpu":{{.HostConfig.NanoCpus}},"task":{{json (index .Config.Labels "ontology.task-id")}},"run":{{json (index .Config.Labels "ontology.run-id")}}}',cid],timeout=10))
        containers.append(row)
    owned=[r for r in containers if r['task']==TASK]
    facts['owner']=bool(owned) and all(r['run']==RUN for r in owned)
    owned_count=len(subprocess.check_output([*prefix,'ps','-aq','--filter','label=ontology.task-id='+TASK],timeout=10).decode().split())
    budget=demand_budget(containers,owned_count,pending_memory,pending_cpu,pending_count)
    facts['budget']=True
    state=json.loads((output/consumer.fixture_file()).read_text())
    if state.get('taskId')!=TASK or state.get('runId')!=RUN or state.get('scenario')!=consumer.SCENARIO:raise ValueError('PREREQUISITE_STALE:scenario')
    def sql_probe(resource,database,sql):
        record=json.loads((output/resource).read_text());cid=record['resources'][0]['id']
        if not any(r['id']==cid and r['task']==TASK and r['run']==RUN for r in owned):raise ValueError('PREREQUISITE_STALE:owner')
        result=run([*prefix,'exec','-i',cid,'psql','-U','postgres','-d',database,'-v','ON_ERROR_STOP=1','-qAt'],ROOT,
                   task=TASK,run_id=RUN,stage='scenario-ready-'+consumer.SCENARIO,stdin=sql.encode(),input_key=sha(sql.encode()),timeout=10)
        if result.returncode:raise ValueError('PREREQUISITE_STALE:fixture')
        return json.loads(result.stdout)
    catalog_rows=sql_probe('source-resources.json','fixture',"SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT n.nspname AS schema,c.relname AS table,CASE WHEN c.relkind IN ('v','m') THEN 'VIEW' ELSE 'TABLE' END AS kind,a.attname AS column,a.attnum AS ordinal,pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,NOT (a.attnotnull OR t.typnotnull) AS nullable FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_class c ON c.relnamespace=n.oid JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid JOIN pg_catalog.pg_type t ON t.oid=a.atttypid WHERE n.nspname='production' AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum LIMIT 2001) x;")
    demand_catalog(catalog_rows,state['catalog']['objects'])
    tables=['numeric_assets','numeric_readings'] if state.get('numeric') else ['assets','readings']
    fixture=sql_probe('source-resources.json','fixture',"SELECT json_build_object('rows',json_build_array("+','.join('(SELECT count(*) FROM production.'+t+')' for t in tables)+"),'types',(SELECT json_agg(json_build_object('table',table_name,'column',column_name,'ordinal',ordinal_position,'type',data_type,'precision',numeric_precision,'scale',numeric_scale,'nullable',is_nullable) ORDER BY table_name,ordinal_position) FROM information_schema.columns WHERE table_schema='production' AND table_name IN ("+','.join("'"+t+"'" for t in tables)+")),'data',json_build_array("+','.join('(SELECT json_agg(t ORDER BY site_id,'+('asset_id' if t==tables[0] else 'reading_id')+') FROM production.'+t+' t)' for t in tables)+"));" )
    if state.get('numeric') and require_grants and state.get('numericFixturePhase')!='POST_ACTIVATION':raise ValueError('PREREQUISITE_STALE:numeric_phase')
    demand_fixture(fixture,bool(state.get('numeric')),include_null=state.get('numericFixturePhase')=='POST_ACTIVATION')
    facts['fixture']=True
    # 仅读取未撤销、仍有效的合成授权非秘密字段；匹配当前正式OIDC主体。
    grants=sql_probe('platform-resources.json','query',"SELECT coalesce(json_agg(g),'[]'::json) FROM (SELECT \"SubjectId\",\"OrganizationId\",\"SiteIds\",\"Permission\",\"ConnectionId\",\"ObjectRefs\",\"FieldRefs\" FROM governance.\"MappingAuthorizationGrants\" WHERE \"RevokedAtUtc\" IS NULL AND \"ExpiresAtUtc\">now()) g;")
    demand_grants(grants,state,mapping=not require_grants)
    facts['grant']=True
    acl=sql_probe('source-resources.json','fixture',"SELECT json_build_object('schema',has_schema_privilege('fixture_reader','production','USAGE'),'tables',json_build_array("+','.join("has_table_privilege('fixture_reader','production."+table+"','SELECT')" for table in tables)+"),'readonly',(SELECT NOT rolsuper AND NOT rolbypassrls AND rolconfig @> ARRAY['default_transaction_read_only=on'] FROM pg_roles WHERE rolname='fixture_reader'));")
    if acl!={'schema':True,'tables':[True,True],'readonly':True}:raise ValueError('PREREQUISITE_STALE:source_acl')
    # 查询不以M3管理Usability的旧epoch为前提；独立核当前固定激活/连接/目录与原字节。
    current_binding=None
    if require_grants:
        expected=state.get('mappingCurrentReceipt') or state['mappingReceipt']
        mapping=expected['mappingId'].replace("'","''")
        query="""SELECT json_build_object('activationId',a."Id",'revision',a."ActivationRevision",'releaseId',a."ReleaseId",'binding',a."BindingJson"::json,'receipt',encode(a."CanonicalBytes",'hex'),'receiptHash',a."ContentHash",'manifest',encode(r."CanonicalBytes",'hex'),'manifestHash',r."ContentHash",'connection',json_build_object('id',c."Id",'state',c."State",'revision',c."Revision",'hash',c."ConfigHash",'secret',c."SecretVersion"),'catalog',(SELECT cs."ViewJson"::json FROM connections."CatalogSnapshots" cs WHERE cs."ConnectionId"=c."Id" AND cs."ConfigHash"=c."ConfigHash" AND cs."SecretVersion"=c."SecretVersion" ORDER BY cs."CapturedAtUtc" DESC,cs."Id" DESC LIMIT 1)) FROM connections."MappingActives" m JOIN connections."MappingActivations" a ON a."Id"=m."ActivationId" JOIN connections."MappingReleases" r ON r."Id"=m."ReleaseId" JOIN connections."Connections" c ON c."Id"=a."BindingJson"::json->>'sourceConnectionId' WHERE m."MappingId"='"""+mapping+"';"
        current_binding=sql_probe('platform-resources.json','query',query)
        if not current_binding:raise ValueError('PREREQUISITE_STALE:activation')
        actual=current_binding;b=actual['binding'];c=actual['connection'];catalog=actual['catalog']
        if actual['activationId']!=expected['activationId'] or actual['revision']!=expected['activationRevision'] or actual['releaseId']!=expected['mappingReleaseId'] or actual['manifestHash']!=expected['manifestHash'] or sha(bytes.fromhex(actual['receipt']))!=actual['receiptHash'] or sha(bytes.fromhex(actual['manifest']))!=actual['manifestHash']:raise ValueError('PREREQUISITE_STALE:activation')
        if c!={'id':b['sourceConnectionId'],'state':'ACTIVE','revision':b['connectionRevision'],'hash':b['configHash'],'secret':b['secretVersion']} or c['id']!=state['connectionId']:raise ValueError('PREREQUISITE_STALE:connection_binding')
        if not catalog or catalog['snapshotId']!=b['sourceCatalogSnapshotId'] or catalog['schemaFingerprint']!=b['sourceCatalogFingerprint'] or catalog['status']!='READY' or catalog['connectionId']!=c['id']:raise ValueError('PREREQUISITE_STALE:catalog_binding')
        del actual['receipt'];del actual['manifest']
    for key,value in facts.items():
        if value is not True:raise ValueError('PREREQUISITE_STALE:'+key)
    receipt=dict(taskId=TASK,resourceOwner=TASK,runId=RUN,scenario=consumer.SCENARIO,build=binding,web=web,facts=facts,budget=budget,catalogColumns=len(catalog_rows),fixture=fixture,sourceAcl=acl,queryBinding=current_binding,
                 session='FORMAL_API_CHECK_REQUIRED',activation='FORMAL_API_CHECK_REQUIRED')
    path=output/('scenario-ready-'+consumer.SCENARIO+'-'+uuid.uuid4().hex+'.json')
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    return dict(facts=facts,receipt=str(path.relative_to(ROOT)),fixture=fixture)


original_runtime_agent_test=consumer.runtime_agent_test

def runtime_agent_test(binding_race=False,aba_inflight=False):
    """正式DI短验证精确持久会话/提案后才准入MAF/ABA长链，短验证不计产品PASS。"""
    local_ready(require_web=False,pending_memory=768*1024**2,pending_cpu=2e9,pending_count=1)
    if aba_inflight:local_ready(require_web=False,require_grants=False)
    if original_runtime_agent_test(binding_race,aba_inflight,preflight=True):raise ValueError('PREREQUISITE_STALE:runtime_session_or_proposal')
    return original_runtime_agent_test(binding_race,aba_inflight)


consumer.runtime_agent_test=runtime_agent_test

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['structural','host-preflight'])
    args=parser.parse_args()
    if args.command=='structural':print(json.dumps(consumer.structural(ROOT,TASK)))
    else:return consumer.host('preflight')
    return 0


if __name__=='__main__':sys.exit(main())
