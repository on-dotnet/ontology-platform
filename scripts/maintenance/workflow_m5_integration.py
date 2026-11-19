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
    output = ROOT/'artifacts/workflow'/TASK/RUN
    if any(json.loads(path.read_text()).get('catalog') for path in output.glob('scenario-*.json')):
        raise ValueError('PREREQUISITE_STALE:batch_schema_after_discovery')
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


def demand_agent_build():
    """复用既有测试构建绑定，逐项核当前源码、实际DLL及真实成功命令原件。"""
    from workflow_execution import sha
    path = ROOT/'artifacts/workflow'/TASK/RUN/'build-binding-OntologyPlatform.AgentTests.json'
    binding = json.loads(path.read_text())
    if binding['taskId'] != TASK or binding['runId'] != RUN or binding['receipt']['exitCode'] != 0:
        raise ValueError('PREREQUISITE_STALE:test_build')
    for group in ('inputs', 'binaries'):
        if not binding[group] or any(not (ROOT/name).is_file() or sha((ROOT/name).read_bytes()) != value for name, value in binding[group].items()):
            raise ValueError('PREREQUISITE_STALE:test_build_'+group)
    for stream in ('stdout', 'stderr'):
        original = binding['receipt'][stream]
        if sha(Path(original['path']).read_bytes()) != original['sha256']:
            raise ValueError('PREREQUISITE_STALE:test_build_original')
    return binding


def browser_session_ready(actors):
    """同一API容器内短检内存Cookie；临时测试程序集精确登记和回收。"""
    import subprocess
    import uuid
    from workflow_execution import run, sha, encoded
    runtime_probe = actors is None
    if not runtime_probe and (len(actors) != 2 or any(set(actor) != {'cookie', 'subjectId'} for actor in actors)):
        raise ValueError('PREREQUISITE_STALE:session_input')
    build = demand_agent_build()
    binding = consumer.runtime_binding()
    cid = binding['process']['id']
    directory = ROOT/'backend/tests/OntologyPlatform.AgentTests/bin/Debug/net10.0'
    binaries = {path.name: sha(path.read_bytes()) for path in directory.iterdir() if path.is_file()}
    if 'OntologyPlatform.AgentTests.dll' not in binaries:
        raise ValueError('PREREQUISITE_STALE:session_probe_build')
    # 既有API容器/tmp承载有界测试文件，无第八容器或运行挂载变更。
    size = sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())
    if size > 96*1024**2:
        raise ValueError('PREREQUISITE_STALE:session_probe_size')
    prefix = ['docker', '--context', 'desktop-linux']
    target = '/tmp/m5-session-probe-'+uuid.uuid4().hex
    output = ROOT/'artifacts/workflow'/TASK/RUN
    path = output/(target.rsplit('/', 1)[1]+'.json')
    record = dict(taskId=TASK, runId=RUN, containerId=cid, path=target, binaries=binaries, sizeBytes=size, buildCommandId=build['receipt']['commandId'], buildInputs=build['inputs'], status='PREPARING')
    path.write_text(json.dumps(record, indent=2)+'\n')
    try:
        import io
        import tarfile
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as bundle:
            for source in sorted(directory.rglob('*')):
                if source.is_symlink():
                    raise ValueError('PREREQUISITE_STALE:session_probe_link')
                if source.is_file():
                    bundle.add(source, arcname=str(source.relative_to(directory)), recursive=False)
        copied = run([*prefix, 'exec', '-i', cid, 'sh', '-c', 'mkdir "$1" && tar -xf - -C "$1"', 'm5-probe', target],
                     ROOT, task=TASK, run_id=RUN, stage='browser-session-probe-copy', timeout=15,
                     stdin=archive.getvalue(), input_key=sha(encoded(binaries)))
        if copied.returncode:
            raise ValueError('PREREQUISITE_STALE:session_probe_copy')
        runtime_environment = []
        method = 'BrowserSessionsCoverRegisteredExecutionDeadline'
        if runtime_probe:
            state = json.loads((output/consumer.fixture_file()).read_text())
            runtime_environment = ['-e', 'G4_QUERY_PREFLIGHT_ONLY=1', '-e', 'G4_QUERY_RUNTIME_QUERY_ID='+state['latestQuery']['queryId'],
                                   '-e', 'G4_QUERY_RUNTIME_ACTOR='+json.dumps(state['latestQuery']['actor'], separators=(',', ':'))]
            if consumer.SCENARIO == 'aba':
                runtime_environment += ['-e', 'G4_QUERY_ABA_PROPOSAL='+state['s2AbaInFlight']['b']['approved']['proposalId']]
            method = 'ActualMafUsesCurrentGatewayAndOnePersistentBudget'
        result = run([*prefix, 'exec', '-i', '-e', 'G4_BROWSER_PREFLIGHT=1', '-e', 'G4_BROWSER_REPORT='+target+'/session-ready.json', '-e', 'G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,
                      '-e', 'ASPNETCORE_ENVIRONMENT=Development', *runtime_environment, '-w', '/private/api', cid, 'dotnet', target+'/OntologyPlatform.AgentTests.dll',
                      '--filter', 'FullyQualifiedName~'+method, '--timeout', '20s', '--zero-tests-policy', 'strict', '--results-directory', target+'/results'],
                     ROOT, task=TASK, run_id=RUN, stage='browser-current-session-preflight', timeout=25,
                     stdin=encoded(actors), input_key=sha(encoded(binaries)))
        record.update(commandId=result.receipt['commandId'], exitCode=result.receipt['exitCode'])
        if runtime_probe:
            return dict(status='READY' if result.returncode == 0 else 'REJECTED', exitCode=result.receipt['exitCode'], commandId=result.receipt['commandId'])
        if result.returncode:
            raise ValueError('PREREQUISITE_STALE:session_deadline')
        report = consumer.runtime_command('browser-session-probe-report', [*prefix, 'exec', cid, 'cat', target+'/session-ready.json'], timeout=5)
        observations = json.loads(report.stdout)
        if len(observations) != 2:
            raise ValueError('PREREQUISITE_STALE:session_observations')
        return dict(status='READY', commandId=result.receipt['commandId'], observations=observations)
    finally:
        removed = consumer.runtime_command('browser-session-probe-remove', [*prefix, 'exec', cid, 'rm', '-rf', '--', target], timeout=10)
        after = subprocess.run([*prefix, 'exec', cid, 'test', '!', '-e', target], capture_output=True, timeout=5)
        record.update(status='REMOVED' if after.returncode == 0 else 'KEEP_UNVERIFIED', cleanupCommandId=removed.receipt['commandId'])
        path.write_text(json.dumps(record, indent=2)+'\n')
        if after.returncode:
            raise ValueError('PREREQUISITE_STALE:session_probe_cleanup')


def session_expiry_control(session_hash, value):
    """仅操纵本次浏览器短检确认的精确合成会话期限；返回原期限供finally恢复。"""
    import re
    import subprocess
    import datetime
    from workflow_execution import run, sha
    if not re.fullmatch('[0-9a-f]{64}', session_hash):
        raise ValueError('SESSION_FIXTURE_HASH_INVALID')
    if value in ('expired', 'short'):
        expiry = "now() + interval '" + ('-1 second' if value == 'expired' else '30 seconds') + "'"
    else:
        restored = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        expiry = "'"+restored.isoformat()+"'::timestamptz"
    output = ROOT/'artifacts/workflow'/TASK/RUN
    cid = json.loads((output/'platform-resources.json').read_text())['resources'][0]['id']
    prefix = ['docker', '--context', 'desktop-linux']
    labels = json.loads(subprocess.check_output([*prefix, 'inspect', '--format', '{{json .Config.Labels}}', cid], timeout=10))
    if labels.get('ontology.task-id') != TASK or labels.get('ontology.run-id') != RUN:
        raise ValueError('PREREQUISITE_STALE:owner')
    where = "encode(sha256(convert_to(\"Id\",'UTF8')),'hex')='"+session_hash+"'"
    sql = """BEGIN; SET LOCAL statement_timeout='5s';
SELECT json_build_object('expires',"ExpiresAtUtc") FROM governance.server_sessions WHERE """+where+""" FOR UPDATE;
UPDATE governance.server_sessions SET "ExpiresAtUtc"="""+expiry+' WHERE '+where+""" AND "RevokedAtUtc" IS NULL RETURNING json_build_object('expires',"ExpiresAtUtc"); COMMIT;"""
    result = run([*prefix, 'exec', '-i', cid, 'psql', '-U', 'postgres', '-d', 'query', '-qAt', '-v', 'ON_ERROR_STOP=1'], ROOT,
                 task=TASK, run_id=RUN, stage='browser-session-expiry-fixture', timeout=10, stdin=sql.encode(), input_key=sha(sql.encode()))
    if result.returncode:
        raise ValueError('SESSION_FIXTURE_FAILED')
    rows = [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
    if len(rows) != 2:
        raise ValueError('SESSION_FIXTURE_NOT_EXACT')
    return dict(before=rows[0]['expires'], after=rows[1]['expires'], commandId=result.receipt['commandId'])


def prepare_batch_schema():
    """首次发现目录前统一建立已知numeric表，保留激活后的NULL数据阶段。"""
    import subprocess
    from workflow_execution import run
    output = ROOT/'artifacts/workflow'/TASK/RUN
    resource = json.loads((output/'source-resources.json').read_text())
    cid = resource['resources'][0]['id']
    prefix = ['docker', '--context', 'desktop-linux']
    labels = json.loads(subprocess.check_output([*prefix, 'inspect', '--format', '{{json .Config.Labels}}', cid], timeout=10))
    if labels.get('ontology.task-id') != TASK or labels.get('ontology.run-id') != RUN:
        raise ValueError('PREREQUISITE_STALE:owner')
    result = run([*prefix, 'exec', '-i', cid, 'psql', '-U', 'postgres', '-d', 'fixture', '-qAt', '-v', 'ON_ERROR_STOP=1'],
                 ROOT, task=TASK, run_id=RUN, stage='batch-schema-probe', timeout=10,
                 stdin=b"SELECT count(*) FROM information_schema.tables WHERE table_schema='production' AND table_name IN ('numeric_assets','numeric_readings');")
    if result.returncode:
        raise ValueError('PREREQUISITE_STALE:schema_probe')
    count = int(result.stdout.strip())
    if count == 0:
        if any(json.loads(path.read_text()).get('catalog') for path in output.glob('scenario-*.json')):
            raise ValueError('PREREQUISITE_STALE:batch_schema_after_discovery')
        numeric_source_fixture()
    elif count != 2:
        raise ValueError('PREREQUISITE_STALE:partial_batch_schema')
    from workflow_execution import sha, encoded
    schema_sql = "SELECT coalesce(json_agg(c ORDER BY table_name,ordinal_position),'[]'::json) FROM information_schema.columns c WHERE table_schema='production';"
    schema = run([*prefix, 'exec', '-i', cid, 'psql', '-U', 'postgres', '-d', 'fixture', '-qAt', '-v', 'ON_ERROR_STOP=1'],
                 ROOT, task=TASK, run_id=RUN, stage='batch-schema-fingerprint', timeout=10, stdin=schema_sql.encode(), diagnostic=True)
    if schema.returncode:
        raise ValueError('PREREQUISITE_STALE:schema_probe')
    columns = json.loads(schema.stdout)
    numeric_columns = {row['table_name']: (row['numeric_precision'], row['numeric_scale'], row['is_nullable'])
                       for row in columns if row['column_name'] == 'numeric_key' and row['table_name'] in ('numeric_assets', 'numeric_readings')}
    if numeric_columns != {'numeric_assets': (10, 2, 'NO'), 'numeric_readings': (12, 3, 'YES')}:
        raise ValueError('PREREQUISITE_STALE:batch_schema_shape')
    preparation = dict(status='BATCH_SCHEMA_PRESENT', probeCommandId=result.receipt['commandId'],
                       fingerprintCommandId=schema.receipt['commandId'], independentSchemaSha256=sha(encoded(json.loads(schema.stdout))))
    state_path = output/consumer.fixture_file()
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(taskId=TASK, runId=RUN, scenario=consumer.SCENARIO,
        s3=True, numeric=consumer.SCENARIO == 'numeric', scope=dict(organizationId='org-demo', siteIds=['site-a', 'site-b']))
    state['schemaPreparation'] = preparation
    state_path.write_text(json.dumps(state, indent=2)+'\n')
    return preparation


original_browser_test = consumer.browser_test

def browser_test(mode):
    """实际首次provision入口先完成本批DDL，再调用既有正式浏览器发现。"""
    if mode == 'provision':
        prepare_batch_schema()
    return original_browser_test(mode)


consumer.browser_test = browser_test


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


def demand_grants(rows,state,mapping=False, required_seconds=0):
    """同一grant须完整覆盖本场景，不把多个残缺grant拼接成授权。"""
    import urllib.parse
    import datetime
    deadline = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=required_seconds)
    if required_seconds:
        rows = [row for row in rows if row.get('ExpiresAtUtc') and datetime.datetime.fromisoformat(row['ExpiresAtUtc'].replace('Z', '+00:00')) >= deadline]
    tables=['numeric_assets','numeric_readings'] if state.get('numeric') else ['assets','readings']
    objects=['production/'+name for name in tables]
    fields=['production/'+table['name']+'/'+str(field['ordinal'])+'/'+urllib.parse.quote(field['name'],safe='') for table in state['catalog']['objects'] if table['schema']=='production' and table['name'] in tables for field in table['fields']]
    if not fields:raise ValueError('PREREQUISITE_STALE:grant')
    permissions={role:(['mapping.read','mapping.source.validate']+(['mapping.edit','mapping.validate','mapping.submit','mapping.activate'] if role=='operator' else ['mapping.review','mapping.approve'])) if mapping else (['data.query.execute','data.query.result.read','data.query.evidence.read'] if role=='operator' else []) for role in state['subjects']}
    demand_scoped_grants(rows,state,objects,fields,permissions)


def demand_scoped_grants(rows,state,objects,fields,permissions):
    """逐主体及权限核实一条完整授权，M5 与 Doris 共享相同覆盖判定。"""
    for role,subject in state['subjects'].items():
        for permission in permissions.get(role, ()):
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


def demand_budget(containers, owned_count, pending_memory=0, pending_cpu=0, pending_count=0,
                  engine_memory=14*1024**3, engine_cpu=12):
    """同一算法核当前运行配额及拟分配峰值；停止实例仅占槽位。"""
    running = [row for row in containers if row.get('running', True)]
    owned = [row for row in running if row['task'] == TASK]
    if engine_memory <= 0 or engine_cpu <= 0 or owned_count + pending_count > 7:
        raise ValueError('PREREQUISITE_STALE:budget')
    if any(row['memory'] <= 0 or row['cpu'] <= 0 for row in running):
        raise ValueError('PREREQUISITE_STALE:budget')
    result = dict(ownedCount=owned_count + pending_count,
                  ownedMemory=sum(row['memory'] for row in owned) + pending_memory,
                  ownedCpu=sum(row['cpu'] for row in owned) + pending_cpu,
                  sharedMemory=sum(row['memory'] for row in running) + pending_memory,
                  sharedCpu=sum(row['cpu'] for row in running) + pending_cpu)
    if (result['ownedMemory'] > 6.5*1024**3 or result['ownedCpu'] > 8e9
            or result['sharedMemory'] > min(14*1024**3, engine_memory)
            or result['sharedCpu'] > min(12, engine_cpu)*1e9):
        raise ValueError('PREREQUISITE_STALE:budget')
    return result


def resource_inventory(full=True):
    """冷库存仅读取Docker身份和配额，完全不依赖API或数据库运行。"""
    import subprocess
    prefix = ['docker', '--context', 'desktop-linux']
    info = json.loads(subprocess.check_output([*prefix, 'info', '--format', '{{json .}}'], timeout=15))
    ids = subprocess.check_output([*prefix, 'ps', '-aq'], timeout=15).decode().split()
    rows = []
    if ids:
        raw = subprocess.check_output([*prefix, 'inspect', '--format',
            '{"id":{{json .Id}},"running":{{.State.Running}},"memory":{{.HostConfig.Memory}},"cpu":{{.HostConfig.NanoCpus}},"task":{{json (index .Config.Labels "ontology.task-id")}},"run":{{json (index .Config.Labels "ontology.run-id")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}}}', *ids], timeout=15)
        rows = [json.loads(line) for line in raw.decode().splitlines()]
    if not full:
        return dict(containers=rows, engineMemory=info['MemTotal'], engineCpu=info['NCPU'])
    # 复用M5收尾的cwd与后代选择，覆盖会改进程标题的Next服务。
    processes = [list(map(int, line.split())) for line in subprocess.check_output(
        ['ps', '-axo', 'pid=,ppid=,rss='], timeout=10).decode().splitlines()]
    cwd = subprocess.run(['lsof', '-d', 'cwd', '-Fn'], capture_output=True, timeout=15)
    if cwd.returncode not in (0, 1):
        raise ValueError('PREREQUISITE_STALE:host_inventory')
    selected = set()
    pid = None
    for line in cwd.stdout.decode().splitlines():
        if line.startswith('p') and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith('n') and pid is not None:
            path = Path(line[1:])
            if path == ROOT or path.is_relative_to(ROOT):
                selected.add(pid)
    while True:
        children = {pid for pid, parent, rss in processes if parent in selected}
        if children <= selected:
            break
        selected.update(children)
    host_rss = sum(rss*1024 for pid, parent, rss in processes if pid in selected)
    if not selected:
        raise ValueError('PREREQUISITE_STALE:host_inventory')
    import re
    import math
    workspace_bytes = int(subprocess.check_output(['du', '-sk', str(ROOT)], timeout=30).split()[0])*1024
    volumes = json.loads(subprocess.check_output([*prefix, 'system', 'df', '-v', '--format', '{{json .Volumes}}'], timeout=30))
    volume_bytes = 0
    task_volumes = []
    for volume in volumes or []:
        labels = dict(item.split('=', 1) for item in volume.get('Labels', '').split(',') if '=' in item)
        if labels.get('ontology.task-id') != TASK:
            continue
        match = re.fullmatch(r'([0-9.]+)(B|kB|MB|GB|TB)', volume['Size'])
        if not match:
            raise ValueError('PREREQUISITE_STALE:volume_size_unknown')
        unit = 1000**['B', 'kB', 'MB', 'GB', 'TB'].index(match[2])
        size = math.ceil((float(match[1])+1)*unit)
        volume_bytes += size
        task_volumes.append(dict(name=volume['Name'], upperBytes=size))
    writable_bytes = 0
    for row in rows:
        if row['task'] == TASK:
            writable_bytes += int(subprocess.check_output([*prefix, 'inspect', '--size', '--format', '{{.SizeRw}}', row['id']], timeout=10))
    return dict(containers=rows, engineMemory=info['MemTotal'], engineCpu=info['NCPU'],
                hostRssBytes=host_rss, hostPids=sorted(selected), taskDiskUpperBytes=workspace_bytes+volume_bytes+writable_bytes,
                diskScope='Conservative whole worktree plus task volumes and writable layers; shared image/cache counted zero times', taskVolumes=task_volumes)


def resource_admission(services, cold=False):
    """正式创建入口刷新库存；首次平台PG创建同时核常驻与互斥测试阶段。"""
    import shutil
    import subprocess
    import uuid
    output = ROOT/'artifacts/workflow'/TASK/RUN
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output/('resource-admission-'+uuid.uuid4().hex+'.json')
    inventory = None
    try:
        inventory = resource_inventory()
        if inventory['taskDiskUpperBytes'] > 10*1024**3:
            raise ValueError('PREREQUISITE_STALE:task_disk')
        if inventory['hostRssBytes'] > 4*1024**3:
            raise ValueError('PREREQUISITE_STALE:host_rss')
        rows = inventory['containers']
        owned = [row for row in rows if row['task'] == TASK]
        if any(row['run'] != RUN for row in owned):
            raise ValueError('PREREQUISITE_STALE:owner')
        # 来自现行配方的精确配额；后续创建配方由同一profile值绑定。
        limits = PROFILE.resources
        stages = [services]
        if cold:
            steady = ['platform-pg', 'pg-source', 'keycloak-test', 'fuseki', 'rustfs', 'api']
            stages = [steady + [extra] for extra in ['api-secondary', 'maf-test', 'persistence-test']]
        plans = []
        for stage in stages:
            memory = cpu = count = 0
            for service in stage:
                existing = [row for row in owned if row['service'] == service]
                if len(existing) > 1:
                    raise ValueError('PREREQUISITE_STALE:duplicate_service')
                quota = limits[service]
                if existing and any(existing[0][key] != quota[key] for key in ('memory', 'cpu')):
                    raise ValueError('PREREQUISITE_STALE:resource_config')
                if existing and existing[0]['running']:
                    continue
                memory += quota['memory']
                cpu += quota['cpu']
                count += not existing
            plans.append(dict(services=stage, budget=demand_budget(rows, len(owned), memory, cpu, count,
                         inventory['engineMemory'], inventory['engineCpu'])))
        if shutil.disk_usage(ROOT).free < 20*1024**3:
            raise ValueError('PREREQUISITE_STALE:disk')
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        receipt_path.write_text(json.dumps(dict(taskId=TASK, runId=RUN, status='BLOCKED',
            inventory=inventory, requestedServices=services, cold=cold, reason=str(error)), indent=2)+'\n')
        raise
    receipt = dict(taskId=TASK, runId=RUN, inventory=inventory, plans=plans, cold=cold)
    receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


consumer.resource_admission = resource_admission


def local_ready(require_web=True, require_grants=True, pending_memory=0, pending_cpu=0, pending_count=0, require_mapping=False):
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
    inventory = resource_inventory(full=False)
    containers = [row for row in inventory['containers'] if row['running']]
    owned = [row for row in containers if row['task'] == TASK]
    facts['owner'] = bool(owned) and all(row['run'] == RUN for row in owned)
    owned_count = sum(row['task'] == TASK for row in inventory['containers'])
    budget = demand_budget(containers, owned_count, pending_memory, pending_cpu, pending_count,
                           inventory['engineMemory'], inventory['engineCpu'])
    facts['budget']=True
    state=json.loads((output/consumer.fixture_file()).read_text())
    if state.get('taskId')!=TASK or state.get('runId')!=RUN or state.get('scenario')!=consumer.SCENARIO:raise ValueError('PREREQUISITE_STALE:scenario')
    def sql_probe(resource,database,sql):
        record=json.loads((output/resource).read_text());cid=record['resources'][0]['id']
        if not any(r['id']==cid and r['task']==TASK and r['run']==RUN for r in owned):raise ValueError('PREREQUISITE_STALE:owner')
        result=run([*prefix,'exec','-i',cid,'psql','-U','postgres','-d',database,'-v','ON_ERROR_STOP=1','-qAt'],ROOT,
                   task=TASK,run_id=RUN,stage='scenario-ready-'+consumer.SCENARIO,stdin=sql.encode(),input_key=sha(sql.encode()),timeout=10,diagnostic=True)
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
    grants=sql_probe('platform-resources.json','query',"SELECT coalesce(json_agg(g),'[]'::json) FROM (SELECT \"SubjectId\",\"OrganizationId\",\"SiteIds\",\"Permission\",\"ConnectionId\",\"ObjectRefs\",\"FieldRefs\",\"ExpiresAtUtc\" FROM governance.\"MappingAuthorizationGrants\" WHERE \"RevokedAtUtc\" IS NULL AND \"ExpiresAtUtc\">now()) g;")
    demand_grants(grants,state,mapping=not require_grants,required_seconds=210)
    if require_mapping and require_grants:
        demand_grants(grants,state,mapping=True,required_seconds=210)
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
    demand_agent_build()
    resource_admission(['maf-test'])
    local_ready(require_web=False,require_mapping=aba_inflight)
    # 正式测试进程内部紧邻MAF调用检查原会话与提案，避免跨两次容器生命周期复用READY。
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
