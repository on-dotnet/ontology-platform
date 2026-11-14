#!/usr/bin/env python3
"""M4查询的同任务执行入口；公共证据和生命周期不另造执行协议。"""
import argparse
import json
import platform
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M4-QUERY-001'
RUN = 'query-impl-01'


def structural(root, task, phase='runtime'):
    """按切片检查真实注册，结构检查不冒充产品执行。"""
    from execution_preflight import source_path, uncomment
    if task != TASK or phase not in ('persistence', 'source', 'runtime'):
        raise ValueError('QUERY_TASK_PHASE_INVALID')
    paths = {
        'composition': 'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/SemanticQueryModule.cs',
        'context': 'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryDbContext.cs',
        'migration': 'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/Migrations/20261114000000_G4QueryPersistence.cs',
        'tests': 'backend/tests/OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs',
    }
    if phase in ('source', 'runtime'):
        paths['source'] = 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgQueryReader.cs'
        paths['binding'] = 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/QueryBindingReader.cs'
        paths['sourceTests'] = 'backend/tests/OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs'
    if phase == 'runtime':
        paths['authority'] = 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/QueryAuthorizationParticipant.cs'
        paths['endpoints'] = 'backend/src/Hosts/OntologyPlatform.Api/G4/QueryEndpoints.cs'
        paths['worker'] = 'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryWorker.cs'
        paths['audit'] = 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs'
        paths['gateway'] = 'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/SemanticGateway.cs'
        paths['host'] = 'backend/src/Hosts/OntologyPlatform.Api/Program.cs'
    texts = {key: uncomment(source_path(root, value).read_text()) for key, value in paths.items()}
    if 'AddDbContextFactory<G4QueryDbContext>' not in texts['composition'] or 'UseNpgsql' not in texts['composition']:
        raise ValueError('QUERY_FACTORY_NOT_REGISTERED')
    if phase in ('source', 'runtime') and any(token not in texts['source'] for token in ('ReadAsync', 'NpgsqlConnection', 'BeginTransactionAsync')):
        raise ValueError('QUERY_SOURCE_EXECUTION_NOT_IMPLEMENTED')
    if phase == 'runtime' and any('"'+action+'"' not in texts['audit'] for action in
                                  ('data.query.execute', 'data.query.read', 'data.query.cancel', 'data.query.evidence.read', 'data.query.expire')):
        raise ValueError('QUERY_AUDIT_NOT_REGISTERED')
    if phase == 'runtime':
        required = {'composition': ['AddScoped<G4QueryExecution>', 'AddHostedService<G4QueryWorker>', 'new G4QueryResultStore'],
                    'endpoints': ['G2EndpointGuard.TransportAsync', 'ExecuteG4Async', 'ReadG4Async', 'CancelG4Async', 'ReadG4EvidenceAsync'],
                    'gateway': ['queryExecution.ExecuteAsync', 'registry.Resolve(query)', 'ReadG4RootAsync'],
                    'worker': ['CreateAsyncScope', 'store.SweepAsync'], 'host': ['app.MapQueryEndpoints()']}
        if any(value not in texts[key] for key, values in required.items() for value in values):
            raise ValueError('QUERY_RUNTIME_CONSUMER_NOT_REGISTERED')
    return dict(taskId=TASK, phase=phase, status='STRUCTURAL_READY', lifecycle='NOT_RUN', consumers=paths)


def prepared():
    """仅消费当前工作树已核验的完整离线依赖，不读取旧runtime。"""
    import workflow_environment as environment
    packages, projects, input_files = environment.locks(ROOT)
    approved = environment.approved_archives(ROOT, TASK, packages)
    admission = environment.git_json(ROOT, environment.BASE, environment.ADMISSION)
    inputs = dict(platform=platform.system()+'-'+platform.machine(), osVersion=platform.mac_ver()[0],
                  files=input_files, tools=admission['files'], sdk=environment.SDK_ARCHIVES,
                  archives={key: row['archiveSha256'] for key, row in approved.items()})
    identity = environment.identities(inputs, ROOT)
    candidate = ROOT / 'artifacts/workflow' / TASK / 'environment' / identity['contentKey'] / 'ready.json'
    choices = [candidate] if candidate.is_file() else []
    if len(choices) != 1:
        raise ValueError('QUERY_ENVIRONMENT_NOT_UNIQUE')
    home = choices[0].parent
    ready = json.loads(choices[0].read_text())
    if ready.get('contentKey') != home.name or ready.get('workspaceKey') != environment.digest(environment.canonical([home.name, str(ROOT)])):
        raise ValueError('QUERY_WORKSPACE_MISMATCH')
    environment.verify_assets(ROOT, home, projects, packages, approved)
    return home, environment.environment(home)


def runtime_snapshot(label):
    """只采集本任务准确资源与配额，不读取或输出其他任务的环境凭据。"""
    import subprocess
    prefix = ['docker', '--context', 'desktop-linux']
    project = 'ontology-g4-m4-query-impl-01'
    rows = []
    for kind, listing in [('container', ['ps', '-aq']), ('network', ['network', 'ls', '-q']), ('volume', ['volume', 'ls', '-q'])]:
        ids = subprocess.check_output([*prefix, *listing, '--filter', 'label=com.docker.compose.project='+project], timeout=15).decode().split()
        for ident in ids:
            item = json.loads(subprocess.check_output([*prefix, kind, 'inspect', ident], timeout=15))[0]
            labels = item['Config']['Labels'] if kind == 'container' else item.get('Labels', {})
            if labels.get('ontology.task-id') != TASK or labels.get('ontology.run-id') != RUN:
                raise ValueError('QUERY_RUNTIME_OWNER_DRIFT')
            row = dict(kind=kind, id=item.get('Id', item.get('Name')), name=item.get('Name'),
                       service=labels.get('com.docker.compose.service'), taskId=TASK, runId=RUN)
            if kind == 'container':
                row.update(running=item['State']['Running'], status=item['State']['Status'], exitCode=item['State']['ExitCode'],
                           memory=item['HostConfig']['Memory'], nanoCpus=item['HostConfig']['NanoCpus'], imageId=item['Image'])
            rows.append(row)
    result = dict(taskId=TASK, runId=RUN, project=project, resources=rows)
    path = ROOT/'artifacts/workflow'/TASK/RUN/(label+'.json')
    with path.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    return result


def runtime_command(stage, command, timeout=60, offline=False, extra_inputs=None):
    """本任务命令统一保留原件和输入身份，不调用M3产品入口。"""
    from workflow_execution import run, sha, encoded
    _, env = prepared()
    if offline:
        command = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)', *command]
    result = run(command, ROOT, task=TASK, run_id=RUN, stage=stage, environment=env,
                 input_key=sha(encoded([sha(Path(__file__).read_bytes()), command, extra_inputs])), timeout=timeout)
    if result.returncode:
        print(result.stdout.decode(errors='replace')[-1500:])
        print(result.stderr.decode(errors='replace')[-1500:])
        raise ValueError('QUERY_RUNTIME_COMMAND_FAILED_'+result.receipt['commandId'])
    return result


def runtime_prepare():
    """核验共同真实预算、白名单镜像并生成全新任务runtime；不启动服务或复制旧私有材料。"""
    import ast
    import os
    import secrets
    import shutil
    import socket
    import subprocess
    import canonical_fuseki
    import host_continuity
    from workflow_execution import sha
    prepared()
    structural(ROOT, TASK, 'runtime')
    output = ROOT/'artifacts/workflow'/TASK/RUN
    private = ROOT/'.tools/security/g4-m4-query-001'/RUN
    runtime = private/'runtime'
    if runtime.exists(): raise ValueError('QUERY_RUNTIME_PRESERVE_EXISTING')
    policy = host_continuity.inspect(task_id=TASK)
    if policy['assurance'] != 'POLICY_READY': raise ValueError('QUERY_HOST_POLICY_BLOCKED')
    prefix = ['docker', '--context', 'desktop-linux']
    info = json.loads(subprocess.check_output([*prefix, 'info', '--format', '{{json .}}'], timeout=15))
    existing = []
    for cid in subprocess.check_output([*prefix, 'ps', '-q'], timeout=15).decode().split():
        # format只选配额和身份，不读取Config.Env。
        row = json.loads(subprocess.check_output([*prefix, 'inspect', '--format',
            '{"id":{{json .Id}},"memory":{{json .HostConfig.Memory}},"cpu":{{json .HostConfig.NanoCpus}},"labels":{{json .Config.Labels}}}', cid], timeout=15))
        if row['memory'] <= 0 or row['cpu'] <= 0: raise ValueError('QUERY_OTHER_RESOURCE_BUDGET_UNKNOWN')
        existing.append(row)
    # 除已有两PG，预留KC/Fuseki/RustFS/API及短命第二API；低于实际12核，不套用纸面16核。
    added_memory = (1024+1536+512+768+768)*1024*1024
    added_cpu = 3_000_000_000
    if sum(row['memory'] for row in existing)+added_memory > min(14*1024**3, info['MemTotal']) \
        or sum(row['cpu'] for row in existing)+added_cpu > min(16, info['NCPU'])*1_000_000_000:
        raise ValueError('QUERY_SHARED_RESOURCE_BUDGET_EXCEEDED')
    if shutil.disk_usage(ROOT).free < 20*1024**3: raise ValueError('QUERY_DISK_BUDGET_BLOCKED')
    for port in [15441,15442,15443,15446,15447,15448]:
        with socket.socket() as probe: probe.bind(('127.0.0.1', port))
    expected = canonical_fuseki.identity(ROOT/'infra/development/fuseki', 'linux/arm64')
    actual = canonical_fuseki.inspect_image(expected)
    if not actual: raise ValueError('QUERY_CANONICAL_FUSEKI_MISSING')
    canonical_fuseki.validate_image(actual, expected, 'sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c')
    images = ['quay.io/keycloak/keycloak@sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4',
              'rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b',
              'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55']
    image_records=[]
    for reference in images:
        item=json.loads(subprocess.check_output([*prefix,'image','inspect',reference],timeout=15))[0]
        if item['Architecture'] != 'arm64' or item['Id'] != reference.split('@')[1]: raise ValueError('QUERY_RUNTIME_IMAGE_DRIFT')
        image_records.append(dict(reference=reference,id=item['Id']))
    (output/'runtime-admission.json').write_text(json.dumps(dict(taskId=TASK,runId=RUN,host=policy,existing=existing,
        addedMemory=added_memory,addedNanoCpus=added_cpu,engineCpus=info['NCPU'],engineMemory=info['MemTotal'],
        fuseki=dict(expected=expected,actual=actual),images=image_records),indent=2)+'\n')
    helper=output/'runtime-helper';helper.mkdir()
    # 只复用仓库公开固定目标代理源文本，绝不调用旧任务运行函数或读取其runtime。
    module=ast.parse((ROOT/'scripts/maintenance/workflow_m3_mapping.py').read_text())
    source=next(ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign)
                and any(isinstance(target,ast.Name) and target.id=='LOOPBACK_SOURCE' for target in node.targets))
    for old,new in [('15680','15443'),('15603','15446'),('15690','15447'),('15630','15442')]: source=source.replace(old,new)
    source=source.replace('本任务隔离运行夹具','G4-M4-QUERY-001 隔离运行夹具')
    (helper/'QueryLoopback.cs').write_text(source)
    references=sorted(Path('/usr/local/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
    if not references: raise ValueError('QUERY_REFERENCE_PACK_MISSING')
    runtime_command('query-loopback-build',['/usr/local/share/dotnet/dotnet','/usr/local/share/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll',
        '-nologo','-target:exe','-nostdlib+','-out:'+str(helper/'QueryLoopback.dll'),
        *['-reference:'+str(path) for path in references],str(helper/'QueryLoopback.cs')],offline=True)
    (helper/'QueryLoopback.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}})+'\n')
    runtime.mkdir(mode=0o700);(runtime/'api').mkdir(mode=0o700)
    def put(path,data):
        with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as stream: stream.write(data if isinstance(data,bytes) else data.encode())
    for name in ['keycloak-password','s3-access','s3-secret']: put(runtime/name,secrets.token_urlsafe(40))
    put(runtime/'api/g4-key',secrets.token_bytes(32))
    put(runtime/'api/ca.crt',(private/'pg-source/server.crt').read_bytes())
    put(runtime/'api/platform-ca.crt',(private/'platform-pg/server.crt').read_bytes())
    put(runtime/'runtime.json',json.dumps(dict(taskId=TASK,runId=RUN,publicOrigin='http://localhost:15441',
        certificatePath=str(runtime/'api/keyring.pfx'),certificatePassword=secrets.token_urlsafe(40),healthKey=secrets.token_urlsafe(32),realmFile=str(runtime/'realm.json'))))
    runtime_command('query-keyring-create',['pwsh','-NoProfile','-File','scripts/acceptance/new-wave2-certificate.ps1','-RuntimeFile',str(runtime/'runtime.json')],offline=True)
    # 只读取已审查的公开compose结构，所有实例身份/私有路径/配额/端口由M4明确替换。
    sys.path.insert(0,str(ROOT/'.tools/pythonlibs'))
    import yaml
    template=(ROOT/'experiments/g4-m3-mapping-001/compose.yaml').read_text()
    replacements={'${MAPPING_RUN_ID:?explicit run required}':RUN,'${MAPPING_HOST_UID:-501}':str(os.getuid()),
        '${MAPPING_HOST_GID:-20}':str(os.getgid()),'${MAPPING_RUNTIME_PRIVATE_DIR:-/not-configured}':str(runtime),
        '${MAPPING_RUNTIME_HELPER_DIR:-/not-configured}':str(helper)}
    for old,new in replacements.items(): template=template.replace(old,new)
    template=template.replace('G4-M3-MAPPING-001',TASK).replace('.mapping-built','.query-built').replace('MappingLoopback.dll','QueryLoopback.dll')
    for old,new in [('15680','15443'),('15603','15446'),('15690','15447'),('15600','15441')]: template=template.replace(old,new)
    parsed=yaml.safe_load(template)
    services={name:parsed['services'][name] for name in ['keycloak-test','fuseki','rustfs','api']}
    for name,service in services.items():
        # PyYAML 1.1会把未加引号的501:20解释为六十进制整数，运行用户必须明确保留字符串。
        if name != 'fuseki': service['user']=f'{os.getuid()}:{os.getgid()}'
        service['networks']=['platform','edge'] if name=='api' else ['edge']
        service['cpus']={'keycloak-test':0.5,'fuseki':0.75,'rustfs':0.25,'api':0.75}[name]
        service['mem_limit']={'keycloak-test':'1g','fuseki':'1536m','rustfs':'512m','api':'768m'}[name]
    binaries=ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    services['api']['volumes'][0]=str(binaries)+':/app:ro'
    query_keyring=runtime/'query-keyring'
    query_keyring.mkdir(mode=0o700)
    services['api']['volumes'].append(str(query_keyring)+':/query-keyring')
    labels={'ontology.task-id':TASK,'ontology.run-id':RUN,'ontology.synthetic':'true'}
    volumes={name:parsed['volumes'][name] for name in ['keycloak-data','fuseki-data','rustfs-data','api-keyring']}
    compose=dict(name='ontology-g4-m4-query-impl-01',services=services,volumes=volumes,
        networks={'platform':{'external':True,'name':'ontology-g4-m4-query-impl-01_platform'},'edge':{'labels':labels}})
    (output/'runtime-compose.json').write_text(json.dumps(compose,indent=2)+'\n')
    (output/'runtime-build-binding.json').write_text(json.dumps({str(path.relative_to(ROOT)):sha(path.read_bytes())
        for directory in [binaries,helper] for path in directory.iterdir() if path.is_file()},indent=2)+'\n')
    return dict(taskId=TASK,status='RUNTIME_PREPARED',downloads=0,servicesStarted=0,secrets='PRIVATE_ONLY')


def runtime_start(api=False):
    """只创建本任务缺席的准确服务，创建前后登记全部准确资源，不移交旧KEEP。"""
    import subprocess
    import uuid
    from workflow_execution import sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    binding=json.loads((output/'runtime-build-binding.json').read_text())
    if not binding or any(sha((ROOT/path).read_bytes()) != digest for path,digest in binding.items()):
        raise ValueError('QUERY_RUNTIME_BINARY_DRIFT')
    services=['api'] if api else ['keycloak-test','fuseki','rustfs']
    tag='runtime-'+('api' if api else 'infrastructure')+'-'+uuid.uuid4().hex[:8]
    before=runtime_snapshot(tag+'-before')
    if any(row.get('service') in services for row in before['resources']): raise ValueError('QUERY_RUNTIME_PRESERVE_EXISTING')
    if api and not (ROOT/'.tools/security/g4-m4-query-001'/RUN/'runtime/api/appsettings.json').is_file():
        raise ValueError('QUERY_RUNTIME_CONFIG_MISSING')
    prefix=['docker','--context','desktop-linux']
    info=json.loads(subprocess.check_output([*prefix,'info','--format','{{json .}}'],timeout=15))
    memory=0;cpu=0
    for cid in subprocess.check_output([*prefix,'ps','-q'],timeout=15).decode().split():
        values=subprocess.check_output([*prefix,'inspect','--format','{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}',cid],timeout=15).decode().split()
        size,cores=map(int,values)
        if size <= 0 or cores <= 0: raise ValueError('QUERY_OTHER_RESOURCE_BUDGET_UNKNOWN')
        memory+=size;cpu+=cores
    added_memory=(768 if api else 3072)*1024*1024
    added_cpu=750_000_000 if api else 1_500_000_000
    if memory+added_memory > min(14*1024**3,info['MemTotal']) or cpu+added_cpu > min(16,info['NCPU'])*1_000_000_000:
        raise ValueError('QUERY_SHARED_RESOURCE_BUDGET_EXCEEDED')
    try:
        result=runtime_command(tag+'-start',[*prefix,'compose','-f',str(output/'runtime-compose.json'),
            'up','-d','--no-deps','--no-build','--pull','never',*services],timeout=120)
    finally:
        after=runtime_snapshot(tag+'-after')
    created=[row for row in after['resources'] if row.get('service') in services]
    if len(created)!=len(services) or any(not row['running'] for row in created):
        raise ValueError('QUERY_RUNTIME_NOT_RUNNING')
    if api:
        # 进程启动身份与磁盘程序集绑定，后续改码或重启不能沿用此前测试身份。
        item=json.loads(subprocess.check_output([*prefix,'inspect','--format',
            '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}}}',created[0]['id']],timeout=15))
        (output/'runtime-api-start.json').write_text(json.dumps(item,indent=2)+'\n')
    return dict(taskId=TASK,status='STARTED_NOT_YET_HEALTH_VERIFIED',resources=created,commandId=result.receipt['commandId'])


def runtime_api_pause():
    """构建前只停止已绑定的本任务API，保留容器、卷和准确恢复身份。"""
    import subprocess
    import uuid
    output=ROOT/'artifacts/workflow'/TASK/RUN
    # 停止必须依赖准确进程身份，磁盘产物漂移时仍应允许停止该实例进行修复。
    started=json.loads((output/'runtime-api-start.json').read_text())
    actual=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
        '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}},"running":{{json .State.Running}},"labels":{{json .Config.Labels}}}',started['id']],timeout=15))
    if actual['id']!=started['id'] or actual['startedAt']!=started['startedAt'] or not actual['running'] \
        or actual['labels'].get('ontology.task-id')!=TASK or actual['labels'].get('ontology.run-id')!=RUN:
        raise ValueError('QUERY_API_STOP_PROCESS_DRIFT')
    from workflow_execution import sha
    expected=json.loads((output/'runtime-build-binding.json').read_text())
    bound=dict(process=started,binaries=expected,binaryDrift=[path for path,digest in expected.items() if sha((ROOT/path).read_bytes())!=digest])
    tag='api-pause-'+uuid.uuid4().hex[:8]
    runtime_snapshot(tag+'-before')
    result=runtime_command(tag,['docker','--context','desktop-linux','stop','--time','10',bound['process']['id']])
    after=runtime_snapshot(tag+'-after')
    target=[row for row in after['resources'] if row['id']==bound['process']['id']]
    if len(target)!=1 or target[0]['running']: raise ValueError('QUERY_API_STOP_POSTCHECK_FAILED')
    record=dict(taskId=TASK,runId=RUN,previous=bound,commandId=result.receipt['commandId'],status='STOPPED_FOR_AUTHORIZED_REBUILD')
    (output/(tag+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    (output/'runtime-api-paused.json').write_text(json.dumps(record,indent=2)+'\n')
    return dict(status=record['status'],commandId=record['commandId'])


def runtime_api_rebuild():
    """本任务API停止后离线构建，将前后相同的源文件集合与实际程序集绑定。"""
    import subprocess
    from workflow_execution import sha,encoded
    output=ROOT/'artifacts/workflow'/TASK/RUN
    paused=json.loads((output/'runtime-api-paused.json').read_text())
    cid=paused['previous']['process']['id']
    if subprocess.check_output(['docker','--context','desktop-linux','inspect','--format','{{.State.Running}}',cid],timeout=15).strip()!=b'false':
        raise ValueError('QUERY_API_MUST_BE_STOPPED_BEFORE_BUILD')
    def inputs():
        return {str(path.relative_to(ROOT)):sha(path.read_bytes()) for pattern in ['backend/src/**/*.cs','backend/src/**/*.csproj','backend/src/**/packages.lock.json','docs/contracts/g4-connections.openapi.json']
                for path in sorted(ROOT.glob(pattern)) if 'obj' not in path.parts and 'bin' not in path.parts}
    before=inputs()
    result=runtime_command('query-api-bound-build',['/usr/local/share/dotnet/dotnet','build','backend/src/Hosts/OntologyPlatform.Api',
        '--no-restore','--disable-build-servers','-m:1','-v:q'],timeout=180,offline=True)
    if before!=inputs(): raise ValueError('QUERY_API_SOURCE_CHANGED_DURING_BUILD')
    original=json.loads((output/'runtime-build-binding.json').read_text())
    binaries={path:sha((ROOT/path).read_bytes()) for path in original}
    for path in (ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0').iterdir():
        if path.is_file(): binaries[str(path.relative_to(ROOT))]=sha(path.read_bytes())
    record=dict(taskId=TASK,runId=RUN,commandId=result.receipt['commandId'],inputs=before,binaries=binaries,inputHash=sha(encoded(before)))
    (output/('api-build-'+result.receipt['commandId']+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    (output/'runtime-api-build.json').write_text(json.dumps(record,indent=2)+'\n')
    (output/'runtime-build-binding.json').write_text(json.dumps(binaries,indent=2)+'\n')
    return dict(status='BUILT_NOT_STARTED',commandId=result.receipt['commandId'])


def runtime_api_resume():
    """只恢复同一准确容器，启动后记录新的进程身份并核验当前构建绑定。"""
    import subprocess
    import uuid
    from workflow_execution import sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    built=json.loads((output/'runtime-api-build.json').read_text())
    for group in ['inputs','binaries']:
        if any(not (ROOT/path).is_file() or sha((ROOT/path).read_bytes())!=digest for path,digest in built[group].items()):
            raise ValueError('QUERY_API_BUILD_DRIFT')
    paused=json.loads((output/'runtime-api-paused.json').read_text())
    cid=paused['previous']['process']['id'];tag='api-resume-'+uuid.uuid4().hex[:8]
    before=runtime_snapshot(tag+'-before')
    target=[row for row in before['resources'] if row['id']==cid and row.get('service')=='api']
    if len(target)!=1 or target[0]['running']: raise ValueError('QUERY_API_RESUME_BOUNDARY')
    result=runtime_command(tag,['docker','--context','desktop-linux','start',cid])
    after=runtime_snapshot(tag+'-after')
    if not any(row['id']==cid and row.get('running') for row in after['resources']): raise ValueError('QUERY_API_RESUME_POSTCHECK')
    process=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
        '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}}}',cid],timeout=15))
    (output/(tag+'.json')).write_text(json.dumps(dict(process=process,buildCommandId=built['commandId'],commandId=result.receipt['commandId']),indent=2)+'\n')
    (output/'runtime-api-start.json').write_text(json.dumps(process,indent=2)+'\n')
    runtime_binding()
    return dict(status='RESUMED_NOT_HEALTH_VERIFIED',commandId=result.receipt['commandId'])


def runtime_persist_query_keyring():
    """修复本任务合成key ring的临时卷寿命；旧失败与卷保留，不读或复制密钥。"""
    import subprocess
    import uuid
    import os
    from workflow_execution import sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    previous=runtime_binding()
    directory=ROOT/'.tools/security/g4-m4-query-001'/RUN/'runtime/query-keyring'
    if directory.exists(): raise ValueError('QUERY_PERSISTENT_KEYRING_ALREADY_EXISTS')
    spec_path=output/'runtime-compose.json';spec=json.loads(spec_path.read_text())
    mounts=spec['services']['api']['volumes']
    if mounts.count('query-keyring:/query-keyring')!=1: raise ValueError('QUERY_KEYRING_MOUNT_UNEXPECTED')
    tag='query-keyring-persist-'+uuid.uuid4().hex[:8]
    before=runtime_snapshot(tag+'-before')
    runtime_api_pause()
    directory.mkdir(mode=0o700)
    if os.stat(directory).st_mode & 0o077: raise ValueError('QUERY_KEYRING_MODE_INVALID')
    old_hash=sha(spec_path.read_bytes())
    spec['services']['api']['volumes']=[str(directory)+':/query-keyring' if value=='query-keyring:/query-keyring' else value for value in mounts]
    spec_path.write_text(json.dumps(spec,indent=2)+'\n')
    result=runtime_command(tag,['docker','--context','desktop-linux','compose','-f',str(spec_path),
        'up','-d','--no-deps','--no-build','--pull','never','--force-recreate','api'],timeout=120)
    after=runtime_snapshot(tag+'-after')
    old_id=previous['process']['id']
    if any(row['id']==old_id for row in after['resources']): raise ValueError('QUERY_OLD_API_STILL_PRESENT')
    protected={row['id'] for row in before['resources'] if row['id']!=old_id}
    if not protected.issubset({row['id'] for row in after['resources']}): raise ValueError('QUERY_RESOURCE_PRESERVATION_FAILED')
    new=[row for row in after['resources'] if row.get('service')=='api' and row.get('running')]
    if len(new)!=1: raise ValueError('QUERY_NEW_API_NOT_RUNNING')
    process=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
        '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}}}',new[0]['id']],timeout=15))
    (output/'runtime-api-start.json').write_text(json.dumps(process,indent=2)+'\n')
    record=dict(taskId=TASK,runId=RUN,oldContainer=old_id,newProcess=process,oldComposeHash=old_hash,newComposeHash=sha(spec_path.read_bytes()),
        status='PERSISTENT_PRIVATE_KEYRING_CONFIGURED_NOT_VALIDATED',oldQueries='PRESERVED_UNRECOVERABLE_KEY_LOSS',commandId=result.receipt['commandId'])
    (output/(tag+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    return record


def runtime_binding():
    """真实API进程、程序集及当前来源同时固定，测试过程中发生漂移即失效。"""
    import subprocess
    from workflow_execution import sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    binaries=json.loads((output/'runtime-build-binding.json').read_text())
    if any(sha((ROOT/path).read_bytes())!=digest for path,digest in binaries.items()): raise ValueError('QUERY_RUNTIME_BINARY_DRIFT')
    started=json.loads((output/'runtime-api-start.json').read_text())
    actual=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
        '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}},"running":{{json .State.Running}},"labels":{{json .Config.Labels}}}',started['id']],timeout=15))
    if actual['id']!=started['id'] or actual['startedAt']!=started['startedAt'] or not actual['running'] \
        or actual['labels'].get('ontology.task-id')!=TASK or actual['labels'].get('ontology.run-id')!=RUN:
        raise ValueError('QUERY_RUNTIME_PROCESS_DRIFT')
    sources={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in ROOT.glob('backend/src/**/*.cs') if 'obj' not in path.parts and 'bin' not in path.parts}
    built_path=output/'runtime-api-build.json'
    if built_path.exists():
        built=json.loads(built_path.read_text())
        if any(not (ROOT/path).is_file() or sha((ROOT/path).read_bytes())!=digest for path,digest in built['inputs'].items()):
            raise ValueError('QUERY_RUNTIME_SOURCE_BUILD_DRIFT')
    sources['scripts/maintenance/workflow-m4-query.mjs']=sha((ROOT/'scripts/maintenance/workflow-m4-query.mjs').read_bytes())
    secondary=None
    secondary_path=output/'runtime-secondary-api.json'
    if secondary_path.exists():
        secondary=json.loads(secondary_path.read_text())['process']
        current=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
            '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}},"running":{{json .State.Running}}}',secondary['id']],timeout=15))
        if not current.pop('running') or current!=secondary: raise ValueError('QUERY_SECONDARY_PROCESS_DRIFT')
    return dict(taskId=TASK,runId=RUN,process=started,secondary=secondary,binaries=binaries,sources=sources)


def runtime_second_api():
    """按批准的15448及768MiB预算创建第二API，复用本任务key ring和平台PG。"""
    import subprocess
    import socket
    import copy
    import uuid
    output=ROOT/'artifacts/workflow'/TASK/RUN
    runtime_binding()
    tag='secondary-api-'+uuid.uuid4().hex[:8]
    before=runtime_snapshot(tag+'-before')
    if any(row.get('service')=='api-secondary' for row in before['resources']): raise ValueError('QUERY_SECONDARY_ALREADY_EXISTS')
    with socket.socket() as probe: probe.bind(('127.0.0.1',15448))
    prefix=['docker','--context','desktop-linux'];memory=0;cpu=0
    info=json.loads(subprocess.check_output([*prefix,'info','--format','{{json .}}'],timeout=15))
    for cid in subprocess.check_output([*prefix,'ps','-q'],timeout=15).decode().split():
        size,cores=map(int,subprocess.check_output([*prefix,'inspect','--format','{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}',cid],timeout=15).decode().split())
        if size<=0 or cores<=0: raise ValueError('QUERY_OTHER_RESOURCE_BUDGET_UNKNOWN')
        memory+=size;cpu+=cores
    if memory+768*1024**2>min(14*1024**3,info['MemTotal']) or cpu+750_000_000>min(16,info['NCPU'])*1_000_000_000:
        raise ValueError('QUERY_SECONDARY_BUDGET_EXCEEDED')
    path=output/'runtime-compose.json';spec=json.loads(path.read_text())
    service=copy.deepcopy(spec['services']['api']);service['ports']=['127.0.0.1:15448:15441']
    spec['services']['api-secondary']=service;path.write_text(json.dumps(spec,indent=2)+'\n')
    result=runtime_command(tag,[*prefix,'compose','-f',str(path),'up','-d','--no-deps','--no-build','--pull','never','api-secondary'],timeout=120)
    after=runtime_snapshot(tag+'-after')
    if not {row['id'] for row in before['resources']}.issubset({row['id'] for row in after['resources']}): raise ValueError('QUERY_SECONDARY_RESOURCE_LOST')
    created=[row for row in after['resources'] if row.get('service')=='api-secondary' and row.get('running')]
    if len(created)!=1: raise ValueError('QUERY_SECONDARY_NOT_RUNNING')
    process=json.loads(subprocess.check_output([*prefix,'inspect','--format','{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}}}',created[0]['id']],timeout=15))
    record=dict(taskId=TASK,runId=RUN,process=process,commandId=result.receipt['commandId'],decision='KEEP',reason='S2 cross-instance verification',release='After S2 proof and final review safe closeout')
    (output/'runtime-secondary-api.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def runtime_secondary_state(running):
    """在同一批准槽位切换短命测试与第二API，保留容器和原始资源身份。"""
    import subprocess
    import uuid
    output=ROOT/'artifacts/workflow'/TASK/RUN
    path=output/'runtime-secondary-api.json';record=json.loads(path.read_text())
    tag='secondary-'+('resume-' if running else 'pause-')+uuid.uuid4().hex[:8]
    before=runtime_snapshot(tag+'-before');cid=record['process']['id']
    selected=[row for row in before['resources'] if row['id']==cid and row.get('service')=='api-secondary']
    if len(selected)!=1 or selected[0]['running']==running: raise ValueError('QUERY_SECONDARY_STATE_BOUNDARY')
    result=runtime_command(tag,['docker','--context','desktop-linux',*(['start'] if running else ['stop','--time','10']),cid])
    after=runtime_snapshot(tag+'-after')
    if not any(row['id']==cid and row.get('running')==running for row in after['resources']): raise ValueError('QUERY_SECONDARY_STATE_POSTCHECK')
    original=record['process']
    if running:
        record['process']=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format',
            '{"id":{{json .Id}},"startedAt":{{json .State.StartedAt}}}',cid],timeout=15))
        path.write_text(json.dumps(record,indent=2)+'\n')
    receipt=dict(taskId=TASK,runId=RUN,previous=original,current=record['process'],running=running,commandId=result.receipt['commandId'])
    (output/(tag+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def runtime_health():
    """仅对本任务loopback端口轮询真实依赖，就绪不等同产品测试通过。"""
    import time
    import urllib.request
    import urllib.error
    output=ROOT/'artifacts/workflow'/TASK/RUN
    # 创建失败或缺少准确运行实例时立即停止，不能盲等一个从未启动的端口。
    snapshot=runtime_snapshot('runtime-health-before-'+__import__('uuid').uuid4().hex[:8])
    for service in ['keycloak-test','fuseki','rustfs']:
        if not any(row.get('service')==service and row.get('running') for row in snapshot['resources']):
            raise ValueError('QUERY_RUNTIME_SERVICE_NOT_RUNNING_'+service)
    urls={'keycloak':'http://127.0.0.1:15443/realms/master','fuseki':'http://127.0.0.1:15446/$/ping','rustfs':'http://127.0.0.1:15447/health'}
    pending=dict(urls);rows={};deadline=time.monotonic()+150
    while pending and time.monotonic()<deadline:
        for name,url in list(pending.items()):
            try:
                with urllib.request.urlopen(url,timeout=2) as response:
                    if response.status==200: rows[name]=dict(status=200);pending.pop(name)
            except (urllib.error.URLError,TimeoutError,ConnectionError): pass
        if pending: time.sleep(2)
    result=dict(taskId=TASK,runId=RUN,status='DEPENDENCIES_HEALTHY' if not pending else 'BLOCKED',checks=rows,missing=list(pending))
    (output/'runtime-health.json').write_text(json.dumps(result,indent=2)+'\n')
    if pending: raise ValueError('QUERY_RUNTIME_HEALTH_BLOCKED_'+','.join(pending))
    return result


def runtime_configure():
    """在新任务realm创建显式合成主体，并生成独立API私有配置；绝不复用M3身份。"""
    import os
    from workflow_execution import run,sha
    _,env=prepared()
    output=ROOT/'artifacts/workflow'/TASK/RUN
    private=ROOT/'.tools/security/g4-m4-query-001'/RUN
    runtime=private/'runtime'
    if json.loads((output/'runtime-health.json').read_text())['status']!='DEPENDENCIES_HEALTHY':
        raise ValueError('QUERY_DEPENDENCIES_NOT_HEALTHY')
    if (runtime/'realm.json').exists() or (runtime/'api/appsettings.json').exists():
        raise ValueError('QUERY_REALM_PRESERVE_EXISTING')
    identity=json.loads((runtime/'runtime.json').read_text())
    env['WAVE2_KEYCLOAK_ADMIN_PASSWORD']=(runtime/'keycloak-password').read_text()
    result=run(['python3','-B','infra/security/bootstrap-keycloak.py','--profile','g2',
        '--keycloak-origin','http://localhost:15443','--public-origin',identity['publicOrigin'],
        '--runtime-output',str(runtime/'realm.json')],ROOT,task=TASK,run_id=RUN,stage='query-realm-bootstrap',environment=env,
        timeout=90,input_key=sha(Path(__file__).read_bytes()))
    if result.returncode: raise ValueError('QUERY_REALM_BOOTSTRAP_FAILED_'+result.receipt['commandId'])
    realm=json.loads((runtime/'realm.json').read_text())
    if not realm['authority'].startswith('http://localhost:15443/realms/g2-'): raise ValueError('QUERY_REALM_ORIGIN_INVALID')
    config={'ConnectionStrings':{'governance':'Host=platform-pg;Database=query;Username=postgres;Password='+(private/'platform-pg/password').read_text()
        +';SSL Mode=VerifyFull;Root Certificate=/private/api/platform-ca.crt;Timeout=5;Command Timeout=5'},
        'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],
            'PublicOrigin':identity['publicOrigin'],'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx',
            'CertificatePassword':identity['certificatePassword'],'HealthKey':identity['healthKey']},
        'Web':{'Origin':'http://127.0.0.1:15442'},'G2':{'Enabled':True,'ApplyMigrations':True},
        'G4':{'Enabled':True,'ApplyMigrations':True,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/ca.crt',
            'AllowEmptyPublicSchema':True,'Mapping':{'Enabled':True},'QueryEnabled':True,'QueryKeyRingPath':'/query-keyring'},
        'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},
        'Semantics':{'ValidationOrigin':'http://127.0.0.1:15446/validation','PublishedOrigin':'http://127.0.0.1:15446/ontology'},
        'Publishing':{'S3Endpoint':'http://127.0.0.1:15447','AccessKey':(runtime/'s3-access').read_text(),
            'SecretKey':(runtime/'s3-secret').read_text(),'Bucket':'g4-m4-query-synthetic'},
        'Logging':{'LogLevel':{'Default':'Warning'}}}
    with os.fdopen(os.open(runtime/'api/appsettings.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as stream:
        json.dump(config,stream)
    return dict(taskId=TASK,status='RUNTIME_CONFIGURED',secrets='PRIVATE_ONLY',commandId=result.receipt['commandId'])


def browser_test(mode):
    """唯一当前任务浏览器入口，真实OIDC与API响应，不运行旧M3验收或下载浏览器。"""
    if mode not in ['provision','mapping','s1','s1-reopen','ui-s1','s2-basic','s2-runtime','s2-race','s2-aba','s2-capacity','s2-connection','s2-inflight','s3-provision','s3','ui-s3','replace-disabled-connection']: raise ValueError('QUERY_BROWSER_MODE_INVALID')
    binding=runtime_binding()
    web=web_binding() if mode in ['ui-s1','ui-s3'] else None
    result=runtime_command('query-browser-'+mode,['/opt/homebrew/Cellar/node@24/24.22.1/bin/node',
        'scripts/maintenance/workflow-m4-query.mjs','--task',TASK,'--run-id',RUN,'--mode',mode],timeout=180,
        extra_inputs=dict(api=binding,web=web))
    print(result.stdout.decode(errors='replace')[-2000:])
    return result.returncode


def synthetic_grants(mode):
    """仅在本任务合成库授予准确主体和资产字段，不从角色隐式升级查询许可。"""
    import subprocess
    import urllib.parse
    from workflow_execution import run,sha
    if mode not in ['mapping','query']: raise ValueError('QUERY_GRANT_MODE_INVALID')
    output=ROOT/'artifacts/workflow'/TASK/RUN
    state=json.loads((output/'runtime-fixture.json').read_text())
    resource=json.loads((output/'platform-resources.json').read_text())
    if state['taskId']!=TASK or state['runId']!=RUN or state['scope']!={'organizationId':'org-demo','siteIds':['site-a','site-b']}:
        raise ValueError('QUERY_SYNTHETIC_SCOPE_INVALID')
    container=resource['resources'][0]['id']
    prefix=['docker','--context','desktop-linux']
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',container],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_GRANT_CONTAINER_OWNER')
    catalog=state['catalog']
    if catalog['connectionId']!=state['connectionId'] or catalog['status']!='READY': raise ValueError('QUERY_GRANT_CATALOG_INVALID')
    tables=[item for item in catalog['objects'] if item['schema']=='production' and item['name'] in (['assets','readings'] if state.get('s3') else ['assets']) and item['kind']=='TABLE']
    if len(tables)!=(2 if state.get('s3') else 1) or not any(item['name']=='assets' and len(item['fields'])==6 for item in tables): raise ValueError('QUERY_GRANT_SOURCE_FIELDS')
    objects=['production/'+table['name'] for table in tables]
    fields=['production/'+table['name']+'/'+str(item['ordinal'])+'/'+urllib.parse.quote(item['name'],safe='') for table in tables for item in table['fields']]
    def literal(value):
        if not isinstance(value,str) or len(value)>512 or any(ord(char)<32 for char in value): raise ValueError('QUERY_GRANT_LITERAL')
        return "'"+value.replace("'","''")+"'"
    def array(values): return 'ARRAY['+','.join(literal(value) for value in values)+']::text[]'
    statements=["BEGIN; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='2s';"]
    ids=[]
    for role,subject in state['subjects'].items():
        if role not in ['operator','auditor']: raise ValueError('QUERY_GRANT_SUBJECT_INVALID')
        permissions=(['mapping.read','mapping.source.validate']+(['mapping.edit','mapping.validate','mapping.submit','mapping.activate'] if role=='operator' else ['mapping.review','mapping.approve'])) if mode=='mapping' else (
            ['data.query.execute','data.query.result.read','data.query.evidence.read'] if role=='operator' else [])
        for permission in permissions:
            ident='m4-fixture-'+sha((state['connectionId']+subject+permission+('s3' if state.get('s3') else '')).encode())[:32];ids.append(ident)
            source=permission=='mapping.source.validate' or permission.startswith('data.query.')
            values=[literal(ident),literal(subject),"'org-demo'",array(state['scope']['siteIds']),literal(permission),
                literal(state['connectionId']) if source else 'NULL',array(objects if source else []),array(fields if source else []),"now()+interval '4 hours'",'NULL']
            statements.append('WITH inserted AS (INSERT INTO governance."MappingAuthorizationGrants" '
                '("Id","SubjectId","OrganizationId","SiteIds","Permission","ConnectionId","ObjectRefs","FieldRefs","ExpiresAtUtc","RevokedAtUtc") VALUES ('+','.join(values)+') ON CONFLICT ("Id") DO NOTHING RETURNING "Id") '
                'INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId") '
                'SELECT md5("Id"),now(),\'synthetic-query-fixture\',\'mapping.grant.change\',"Id",\'allowed\',\'query-impl-01\',\'query-impl-01\',\'org-demo\','+array(state['scope']['siteIds'])+',NULL FROM inserted;')
    statements+=['COMMIT;','SELECT count(*) FROM governance."MappingAuthorizationGrants" WHERE "Id"=ANY('+array(ids)+') AND "RevokedAtUtc" IS NULL AND "ExpiresAtUtc">now();']
    sql='\n'.join(statements).encode()
    result=run([*prefix,'exec','-i',container,'psql','-U','postgres','-d','query','-v','ON_ERROR_STOP=1','-qAt'],ROOT,
        task=TASK,run_id=RUN,stage='query-synthetic-grant-'+mode,stdin=sql,input_key=sha(sql),timeout=20)
    if result.returncode or result.stdout.decode().strip()!=str(len(ids)): raise ValueError('QUERY_GRANT_FAILED_'+result.receipt['commandId'])
    return dict(taskId=TASK,mode=mode,status='EXPLICIT_SYNTHETIC_GRANTS_CREATED',count=len(ids),commandId=result.receipt['commandId'])


def source_scan_snapshot():
    """只观察本任务assets业务表累计扫描，不重置统计或读取业务行。"""
    import subprocess
    from workflow_execution import run,sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    record=json.loads((output/'source-resources.json').read_text())
    container=record['resources'][0]['id'];prefix=['docker','--context','desktop-linux']
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',container],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_STATS_CONTAINER_OWNER')
    sql=b'''SELECT json_build_object('database',current_database(),'table','production.assets','seqScan',seq_scan,'idxScan',coalesce(idx_scan,0),'observedAtUtc',clock_timestamp()) FROM pg_stat_user_tables WHERE schemaname='production' AND relname='assets';'''
    result=run([*prefix,'exec','-i',container,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],ROOT,
        task=TASK,run_id=RUN,stage='query-source-scan-observe',stdin=sql,input_key=sha(sql+container.encode()),timeout=15)
    if result.returncode: raise ValueError('QUERY_STATS_READ_FAILED')
    value=json.loads(result.stdout)
    if value['database']!='fixture' or value['table']!='production.assets': raise ValueError('QUERY_STATS_SCOPE_INVALID')
    return dict(taskId=TASK,runId=RUN,containerId=container,commandId=result.receipt['commandId'],**value)


def query_fixture_control(action, value=None):
    """仅当前合成容器的固定故障/授权夹具动作，不接收自由SQL或业务表名。"""
    import subprocess
    import re
    from workflow_execution import run,sha
    output=ROOT/'artifacts/workflow'/TASK/RUN
    source=action in ['source-hold','source-lock-probe','source-deny','source-allow','readings-deny','readings-allow','readings-budget-add','readings-budget-remove']
    record=json.loads((output/('source-resources.json' if source else 'platform-resources.json')).read_text())
    container=record['resources'][0]['id'];prefix=['docker','--context','desktop-linux']
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',container],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_FIXTURE_CONTROL_OWNER')
    if action=='source-hold':
        sql="BEGIN; SET LOCAL statement_timeout='6s'; SET LOCAL lock_timeout='1s'; LOCK TABLE production.assets IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(4); ROLLBACK; SELECT 'RELEASED';"
    elif action=='source-lock-probe':
        sql="SELECT count(*) FROM pg_locks WHERE relation='production.assets'::regclass AND mode='AccessExclusiveLock' AND granted;"
    elif action in ['source-deny','source-allow']:
        sql=("REVOKE SELECT ON production.assets FROM fixture_reader;" if action=='source-deny' else "GRANT SELECT ON production.assets TO fixture_reader;")+" SELECT has_table_privilege('fixture_reader','production.assets','SELECT');"
    elif action in ['readings-deny','readings-allow']:
        sql=("REVOKE SELECT ON production.readings FROM fixture_reader;" if action=='readings-deny' else "GRANT SELECT ON production.readings TO fixture_reader;")+" SELECT has_table_privilege('fixture_reader','production.readings','SELECT');"
    elif action in ['readings-budget-add','readings-budget-remove']:
        # 仅本任务固定99个新增合成行，完整主键和时间限定避免碰到原三行。
        owned="organization_id='org-demo' AND site_id='site-a' AND asset_id='asset-1' AND reading_id IN (SELECT 'm4-query-impl-01-budget-'||n FROM generate_series(1,99) n) AND valid_from='2026-11-14T00:00:00Z'::timestamptz"
        if action=='readings-budget-add':
            sql="BEGIN; DO $$ BEGIN IF EXISTS (SELECT 1 FROM production.readings WHERE "+owned+") THEN RAISE EXCEPTION 'owned budget fixture already exists'; END IF; END $$; "
            sql+="INSERT INTO production.readings SELECT 'org-demo','site-a','m4-query-impl-01-budget-'||n,'asset-1','2026-11-14T00:00:00Z'::timestamptz,'2026-11-14T00:01:00Z'::timestamptz,'2026-11-14T00:00:01.123456Z'::timestamptz,20.1250,'Cel',jsonb_build_object('quality',repeat(chr(9),4096)) FROM generate_series(1,99) n; COMMIT; "
        else:
            sql="DELETE FROM production.readings WHERE "+owned+"; "
        sql+="SELECT json_build_object('ownedRows',(SELECT count(*) FROM production.readings WHERE "+owned+"),'siteRows',(SELECT count(*) FROM production.readings WHERE organization_id='org-demo' AND site_id='site-a'));"
    elif action=='query-probe':
        if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f-]{36}',value): raise ValueError('QUERY_FIXTURE_KEY_INVALID')
        sql='SELECT json_build_object(\'id\',"Id",\'status\',"ExecutionStatus",\'fence\',"Fence",\'cancel\',"CancelRequested") FROM semantic_query."Queries" WHERE "IdempotencyKey"=\''+value+'\';'
    elif action in ['revoke-execute','restore-execute','revoke-result','restore-result','revoke-evidence','restore-evidence']:
        state=json.loads((output/'runtime-fixture.json').read_text())
        permission={'execute':'data.query.execute','result':'data.query.result.read','evidence':'data.query.evidence.read'}[action.split('-')[1]]
        ident='m4-fixture-'+sha((state['connectionId']+state['subjects']['operator']+permission+('s3' if state.get('s3') else '')).encode())[:32]
        revoked="now()" if action.startswith('revoke-') else 'NULL'
        sql='BEGIN; SET LOCAL statement_timeout=\'5s\'; SELECT "Revision" FROM governance."MappingAuthorizationEpochs" WHERE "OrganizationId"=\'org-demo\' FOR UPDATE; '
        sql+='UPDATE governance."MappingAuthorizationGrants" SET "RevokedAtUtc"='+revoked+' WHERE "Id"=\''+ident+'\' AND "OrganizationId"=\'org-demo\'; '
        sql+='UPDATE governance."MappingAuthorizationEpochs" SET "Revision"="Revision"+1 WHERE "OrganizationId"=\'org-demo\'; '
        sql+='INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId") '
        sql+="VALUES (md5(random()::text||clock_timestamp()::text),now(),'synthetic-query-fixture','mapping.grant.change','"+ident+"','allowed','query-impl-01','query-impl-01','org-demo',ARRAY['site-a','site-b'],NULL); COMMIT; "
        sql+='SELECT "RevokedAtUtc" IS NOT NULL FROM governance."MappingAuthorizationGrants" WHERE "Id"=\''+ident+'\';'
    else: raise ValueError('QUERY_FIXTURE_ACTION_INVALID')
    result=run([*prefix,'exec','-i',container,'psql','-U','postgres','-d','fixture' if source else 'query','-v','ON_ERROR_STOP=1','-qAt'],ROOT,
        task=TASK,run_id=RUN,stage='query-fixture-'+action,stdin=sql.encode(),input_key=sha((sql+container).encode()),timeout=10)
    if result.returncode: raise ValueError('QUERY_FIXTURE_CONTROL_FAILED_'+result.receipt['commandId'])
    return dict(taskId=TASK,action=action,commandId=result.receipt['commandId'],output=result.stdout.decode().strip())


def query_source_barrier():
    """持锁连接直接确认就绪；四秒后回滚，不用慢容器探针猜测源故障窗口。"""
    import subprocess
    from workflow_execution import Service,CONTEXT
    output=ROOT/'artifacts/workflow'/TASK/RUN
    record=json.loads((output/'source-resources.json').read_text());container=record['resources'][0]['id']
    labels=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format','{{json .Config.Labels}}',container],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_BARRIER_OWNER_INVALID')
    CONTEXT.set({'task':TASK,'run_id':RUN})
    service=Service(['docker','--context','desktop-linux','exec','-i',container,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],ROOT,TASK)
    try:
        service.process.stdin.write(b"BEGIN; SET LOCAL statement_timeout='6s'; SET LOCAL lock_timeout='1s'; LOCK TABLE production.assets IN ACCESS EXCLUSIVE MODE; SELECT 'BARRIER_READY';\n");service.process.stdin.flush()
        line=service.process.stdout.readline();service.out.extend(line)
        if line.strip()!=b'BARRIER_READY': raise ValueError('QUERY_BARRIER_NOT_READY')
        service.ready();print(json.dumps(dict(status='READY',commandId=service.ident)),flush=True)
        stdout,stderr=service.process.communicate(b"SELECT pg_sleep(4); ROLLBACK; SELECT 'RELEASED';\n",timeout=8)
        service.out.extend(stdout);service.err.extend(stderr)
        if service.process.returncode or b'RELEASED' not in stdout: raise ValueError('QUERY_BARRIER_RELEASE_UNCONFIRMED')
        print(json.dumps(dict(status='RELEASED',commandId=service.ident)),flush=True)
    finally:
        if service.process.poll() is None:
            service.process.kill();stdout,stderr=service.process.communicate(timeout=3);service.out.extend(stdout);service.err.extend(stderr)
        service.finish()


def query_admission_watch(key, revoke=False):
    """预先建立只读观察连接，在真实提交准入后立即输出ID；不插入或修改产品记录。"""
    import subprocess
    import re
    from workflow_execution import Service,CONTEXT
    if not re.fullmatch(r'[0-9a-f-]{36}',key): raise ValueError('QUERY_WATCH_KEY_INVALID')
    output=ROOT/'artifacts/workflow'/TASK/RUN
    record=json.loads((output/'platform-resources.json').read_text());container=record['resources'][0]['id']
    labels=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','--format','{{json .Config.Labels}}',container],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_WATCH_OWNER_INVALID')
    CONTEXT.set({'task':TASK,'run_id':RUN})
    service=Service(['docker','--context','desktop-linux','exec','-i',container,'psql','-U','postgres','-d','query','-v','ON_ERROR_STOP=1','-qAt'],ROOT,TASK)
    try:
        service.process.stdin.write(b"BEGIN READ ONLY; SET LOCAL statement_timeout='12s'; SELECT 'WATCH_READY';\n");service.process.stdin.flush()
        line=service.process.stdout.readline();service.out.extend(line)
        if line.strip()!=b'WATCH_READY': raise ValueError('QUERY_WATCH_NOT_READY')
        service.ready();print(json.dumps(dict(status='READY',commandId=service.ident)),flush=True)
        sql='DO $$ DECLARE found_id text; stop_at timestamptz := clock_timestamp()+interval \'10 seconds\'; BEGIN LOOP '
        sql+='SELECT "Id" INTO found_id FROM semantic_query."Queries" WHERE "IdempotencyKey"=\''+key+'\'; '
        sql+="IF found_id IS NOT NULL THEN RAISE NOTICE 'QUERY_ID:%',found_id; EXIT; END IF; IF clock_timestamp()>=stop_at THEN RAISE EXCEPTION 'QUERY_WATCH_TIMEOUT'; END IF; PERFORM pg_sleep(0.01); END LOOP; END $$; COMMIT;\n"
        if revoke:
            from workflow_execution import sha
            state=json.loads((output/'runtime-fixture.json').read_text())
            ident='m4-fixture-'+sha((state['connectionId']+state['subjects']['operator']+'data.query.execute'+('s3' if state.get('s3') else '')).encode())[:32]
            sql += "BEGIN; SET LOCAL statement_timeout='2s'; SELECT \"Revision\" FROM governance.\"MappingAuthorizationEpochs\" WHERE \"OrganizationId\"='org-demo' FOR UPDATE; "
            sql += 'UPDATE governance."MappingAuthorizationGrants" SET "RevokedAtUtc"=now() WHERE "Id"=\''+ident+'\'; '
            sql += 'UPDATE governance."MappingAuthorizationEpochs" SET "Revision"="Revision"+1 WHERE "OrganizationId"=\'org-demo\'; '
            sql += 'INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId") '
            sql += "VALUES (md5(random()::text||clock_timestamp()::text),now(),'synthetic-query-fixture','mapping.grant.change','"+ident+"','allowed','query-impl-01','query-impl-01','org-demo',ARRAY['site-a','site-b'],NULL); COMMIT;\n"
        stdout,stderr=service.process.communicate(sql.encode(),timeout=15);service.out.extend(stdout);service.err.extend(stderr)
        match=re.search(rb'QUERY_ID:(query-[0-9a-f]{32})',stderr)
        if service.process.returncode or match is None: raise ValueError('QUERY_WATCH_NO_ADMISSION')
        print(json.dumps(dict(status='FOUND',queryId=match.group(1).decode(),commandId=service.ident)),flush=True)
    finally:
        if service.process.poll() is None:
            service.process.kill();stdout,stderr=service.process.communicate(timeout=3);service.out.extend(stdout);service.err.extend(stderr)
        service.finish()


def web_pause():
    """只终止当前任务记录的准确Web进程，构建前核对PID、启动时间和命令行。"""
    import os
    import subprocess
    import time
    import uuid
    output=ROOT/'artifacts/workflow'/TASK/RUN
    matches=[]
    for path in output.glob('web-process-*.json'):
        row=json.loads(path.read_text())
        if row['taskId']!=TASK or row['runId']!=RUN or row['worktree']!=str(ROOT): raise ValueError('QUERY_WEB_OWNER_INVALID')
        actual=subprocess.run(['ps','-p',str(row['pid']),'-o','lstart='],capture_output=True,env={**os.environ,'LC_ALL':'C'},timeout=5)
        if actual.returncode or actual.stdout.decode().strip()!=row['processStartedAt']: continue
        command=subprocess.check_output(['ps','-p',str(row['pid']),'-o','command='],timeout=5).decode()
        # Next生产入口会改写进程标题；相同PID/启动时间还须核实工作目录，不能仅凭标题杀进程。
        cwd=subprocess.check_output(['lsof','-a','-p',str(row['pid']),'-d','cwd','-Fn'],timeout=5).decode().splitlines()
        valid_command=('workflow-m4-query.mjs' in command and '--mode serve' in command) or command.strip()=='next-server (v16.4.3)'
        if not valid_command or 'n'+str(ROOT) not in cwd: raise ValueError('QUERY_WEB_PROCESS_DRIFT')
        matches.append(row)
    if len(matches)!=1: raise ValueError('QUERY_WEB_EXACT_PROCESS_REQUIRED')
    row=matches[0];tag='web-pause-'+uuid.uuid4().hex[:8]
    (output/(tag+'-before.json')).write_text(json.dumps(row,indent=2)+'\n')
    result=runtime_command(tag,['/bin/kill','-TERM',str(row['pid'])])
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        probe=subprocess.run(['ps','-p',str(row['pid']),'-o','lstart='],capture_output=True,env={**os.environ,'LC_ALL':'C'},timeout=5)
        if probe.returncode or probe.stdout.decode().strip()!=row['processStartedAt']: break
        time.sleep(0.1)
    else: raise ValueError('QUERY_WEB_STOP_NOT_CONFIRMED')
    receipt=dict(taskId=TASK,runId=RUN,pid=row['pid'],originalStart=row['processStartedAt'],status='EXACT_PROCESS_EXITED',commandId=result.receipt['commandId'])
    (output/(tag+'-after.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def web_check(stage):
    """使用当前M4输入和独立报告/缓存路径，复用既有本地工具，不调用旧任务配置。"""
    import uuid
    from workflow_execution import run,sha,encoded
    from workflow_evidence import machine
    if stage not in ['typecheck','lint','unit','build']: raise ValueError('QUERY_WEB_STAGE_INVALID')
    _,env=prepared()
    web=ROOT/'apps/web';output=ROOT/'artifacts/workflow'/TASK/RUN
    directory=output/('web-'+stage+'-'+uuid.uuid4().hex[:8]);directory.mkdir()
    inputs={str(path.relative_to(ROOT)):sha(path.read_bytes()) for base in [web/'src',web/'scripts'] for path in sorted(base.rglob('*')) if path.is_file()}
    inputs['docs/contracts/g4-connections.openapi.json']=sha((ROOT/'docs/contracts/g4-connections.openapi.json').read_bytes())
    node='/opt/homebrew/Cellar/node@24/24.22.1/bin/node'
    commands={'typecheck':[node,'node_modules/typescript/bin/tsc','--noEmit'],
        'lint':[node,'node_modules/eslint/bin/eslint.js','src/features/semantic','src/lib/api/openapi-types.test.ts'],
        'build':[node,'node_modules/next/dist/bin/next','build','--webpack']}
    report=directory/'vitest-report.json'
    if stage=='unit':
        config=directory/'vitest.config.mjs'
        config.write_text('export default '+json.dumps(dict(root=str(web),cacheDir=str(output/'vite-cache'),test=dict(
            environment='node',include=['src/features/semantic/g4-query.test.ts','src/lib/api/openapi-types.test.ts'],
            reporters=['default','json'],outputFile=dict(json=str(report)),fsModuleCachePath=str(output/'vite-modules'))))+';\n')
        commands['unit']=[node,'node_modules/vitest/vitest.mjs','run','--config',str(config),'--configLoader','native']
    env['NEXT_TELEMETRY_DISABLED']='1';env['NODE_OPTIONS']='--max-old-space-size=4096'
    profile='(version 1) (allow default) (deny network-outbound)' if stage=='build' else '(version 1) (allow default) (deny network*)'
    result=run(['/usr/bin/sandbox-exec','-p',profile,*commands[stage]],web,
        task=TASK,run_id=RUN,stage='query-web-'+stage,environment=env,input_key=sha(encoded(inputs)),timeout=180 if stage=='build' else 60)
    print(result.stdout.decode(errors='replace')[-2500:]);print(result.stderr.decode(errors='replace')[-1500:])
    row=dict(taskId=TASK,stage=stage,exitCode=result.returncode,commandId=result.receipt['commandId'],inputs=inputs)
    if stage=='unit' and result.returncode==0: row.update(tests=machine(report.read_bytes(),'vitest-json'),report=str(report.relative_to(ROOT)),reportSha256=sha(report.read_bytes()))
    if stage=='build' and result.returncode==0:
        row['buildId']=(web/'.next/BUILD_ID').read_text().strip()
        row['files']={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted((web/'.next').rglob('*')) if path.is_file() and 'cache' not in path.parts and 'diagnostics' not in path.parts and path.name not in ['trace','trace-build']}
        (output/'web-build-binding.json').write_text(json.dumps(row,indent=2)+'\n')
    (directory/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    print(json.dumps({key:value for key,value in row.items() if key not in ['inputs','files']}))
    return result.returncode


def web_binding():
    """实际构建源与每个产品产物仍完全相同时才能启动或验收Web。"""
    from workflow_execution import sha,encoded
    output=ROOT/'artifacts/workflow'/TASK/RUN
    row=json.loads((output/'web-build-binding.json').read_text())
    if row['taskId']!=TASK or row['exitCode']!=0: raise ValueError('QUERY_WEB_BUILD_REQUIRED')
    for group in ['inputs','files']:
        if any(not (ROOT/path).is_file() or sha((ROOT/path).read_bytes())!=digest for path,digest in row[group].items()):
            raise ValueError('QUERY_WEB_'+group.upper()+'_DRIFT')
    return dict(taskId=TASK,buildId=row['buildId'],commandId=row['commandId'],inputHash=sha(encoded(row['inputs'])),filesHash=sha(encoded(row['files'])))


def contract_build(project="OntologyPlatform.G2ContractTests"):
    """测试先行的合同编译保留真实失败与退出码，不把编译当测试通过。"""
    from workflow_execution import run, sha, encoded
    import subprocess
    output=ROOT/'artifacts/workflow'/TASK/RUN
    # 提交会改变自动生成程序集元数据；即使只改测试，项目引用构建也可能重写挂载中的API。
    for name in ['runtime-api-start.json','runtime-secondary-api.json']:
        path=output/name
        if path.exists():
            record=json.loads(path.read_text());process=record.get('process',record)
            running=subprocess.check_output(['docker','--context','desktop-linux','inspect','--format','{{.State.Running}}',process['id']],timeout=15).strip()
            if running==b'true': raise ValueError('QUERY_API_STOP_REQUIRED_BEFORE_REFERENCE_BUILD')
    _, env = prepared()
    inputs = {path:digest for path,digest in qualification_inputs().items()
              if path.startswith('backend/') or '/' not in path}
    result = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
                  '/usr/local/share/dotnet/dotnet', 'build', 'backend/tests/' + project,
                  '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], ROOT,
                 task=TASK, run_id=RUN, stage='query-build-' + project, environment=env,
                 input_key=sha(encoded(inputs)), timeout=180)
    if result.returncode == 0:
        directory = ROOT/'backend/tests'/project/'bin/Debug/net10.0'
        binding = dict(taskId=TASK, runId=RUN, project=project, inputs=inputs,
                       binaries={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted(directory.glob('*.dll'))},
                       receipt=result.receipt)
        (output/('build-binding-'+project+'.json')).write_text(json.dumps(binding,indent=2)+'\n')
    print(result.stdout.decode(errors='replace')[-8000:])
    print(json.dumps({'exitCode': result.returncode, 'receipt': result.receipt['commandId']}))
    return result.returncode


def contract_test():
    """实际执行非零合同用例，旧G2覆盖同程序集且不触发外部服务。"""
    from workflow_execution import run, sha, encoded
    _, env = prepared()
    directory = ROOT / 'backend/tests/OntologyPlatform.G2ContractTests/bin/Debug/net10.0'
    inputs = {p.name: sha(p.read_bytes()) for p in directory.glob('*.dll')}
    result = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
                  '/usr/local/share/dotnet/dotnet', str(directory / 'OntologyPlatform.G2ContractTests.dll'),
                  '--filter', 'FullyQualifiedName~G4QueryWireTests|FullyQualifiedName~.WireContractTests', '--timeout', '60s', '--zero-tests-policy', 'strict'], ROOT,
                 task=TASK, run_id=RUN, stage='query-contract-tests', environment=env,
                 input_key=sha(encoded(inputs)), timeout=90)
    print(result.stdout.decode(errors='replace')[-8000:])
    print(result.stderr.decode(errors='replace')[-2000:])
    print(json.dumps({'exitCode': result.returncode, 'receipt': result.receipt['commandId']}))
    return result.returncode


def contract_export():
    """从真实路由和DTO导出合同，仅临时本机回环元数据Host，无产品依赖服务。"""
    from workflow_execution import run, sha, encoded
    _, env = prepared()
    directory = ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    inputs = {p.name: sha(p.read_bytes()) for p in directory.glob('*.dll')}
    result = run(['/usr/bin/sandbox-exec', '-p',
                  '(version 1) (allow default) (deny network*) (allow network-inbound (local ip "localhost:*")) (allow network-outbound (remote ip "localhost:*"))',
                  '/usr/local/share/dotnet/dotnet', str(directory/'OntologyPlatform.Api.dll'),
                  '--export-g4-openapi', str(ROOT/'docs/contracts/g4-connections.openapi.json')], ROOT,
                 task=TASK, run_id=RUN, stage='query-contract-export', environment=env,
                 input_key=sha(encoded(inputs)), timeout=60)
    print(result.stdout.decode(errors='replace')[-2000:])
    print(result.stderr.decode(errors='replace')[-2000:])
    print(json.dumps({'exitCode': result.returncode, 'receipt': result.receipt['commandId']}))
    return result.returncode


def unit_test(project, filter_name):
    """精确选择当前M4非零测试，原件与输入身份交给公共执行器。"""
    from workflow_execution import run, sha, encoded
    if (project, filter_name) not in (('OntologyPlatform.QueryTests', 'G4QueryTests'),
                                    ('OntologyPlatform.SecurityTests', 'G4QueryAuthorizationTests'),
                                    ('OntologyPlatform.ConnectionsTests', 'G4QuerySourceTests'),
                                    ('OntologyPlatform.AgentTests', 'G4QueryMcpTests')):
        raise ValueError('QUERY_TEST_SELECTION_INVALID')
    _, env = prepared()
    directory = ROOT / 'backend/tests' / project / 'bin/Debug/net10.0'
    inputs = {p.name: sha(p.read_bytes()) for p in directory.glob('*.dll')}
    result = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
                  '/usr/local/share/dotnet/dotnet', str(directory / (project+'.dll')),
                  '--filter', 'FullyQualifiedName~'+filter_name, '--timeout', '30s', '--zero-tests-policy', 'strict'], ROOT,
                 task=TASK, run_id=RUN, stage='query-unit-'+filter_name, environment=env,
                 input_key=sha(encoded(inputs)), timeout=45)
    print(result.stdout.decode(errors='replace')[-8000:])
    print(json.dumps({'exitCode':result.returncode,'receipt':result.receipt['commandId']}))
    return result.returncode


def host(mode):
    """通过现有宿主公共函数记录准确M4身份，不借用CLI旧白名单任务。"""
    import host_continuity
    output = ROOT / 'artifacts/workflow' / TASK / RUN / ('host-' + mode + '.jsonl')
    path = host_continuity.output_path(str(output))
    if mode == 'preflight':
        result = host_continuity.inspect(task_id=TASK)
        host_continuity.save(path, result)
    else:
        if path.exists() or path.with_suffix('.summary.json').exists():
            raise ValueError('QUERY_HOST_OUTPUT_EXISTS')
        result = host_continuity.monitor(path, 600, 5, task_id=TASK)
    print(json.dumps(result))
    return 0 if result.get('assurance') == 'POLICY_READY' or result.get('policyContinuouslyReady') else 2


def platform_start():
    """只创建本任务新合成TLS平台PG，原KEEP和共享镜像只读保护。"""
    import os
    import secrets
    import socket
    import subprocess
    from workflow_execution import run, sha, encoded
    structural(ROOT, TASK, 'persistence')
    prepared()
    output = ROOT / 'artifacts/workflow' / TASK / RUN
    private = ROOT / '.tools/security/g4-m4-query-001' / RUN / 'platform-pg'
    identity = output / 'platform-resources.json'
    if identity.exists() or private.exists():
        raise ValueError('QUERY_PLATFORM_ALREADY_REGISTERED')
    def docker(*args):
        return subprocess.check_output(['docker', '--context', 'desktop-linux', *args], timeout=15)
    info = json.loads(docker('info', '--format', '{{json .}}'))
    running = []
    for cid in docker('ps', '-q').decode().split():
        item = json.loads(docker('inspect', cid))[0]
        running.append(dict(id=item['Id'], memory=item['HostConfig']['Memory'], nanoCpus=item['HostConfig']['NanoCpus'],
                            taskId=item['Config'].get('Labels', {}).get('ontology.task-id')))
    if any(not item['memory'] or not item['nanoCpus'] for item in running):
        raise ValueError('QUERY_EXISTING_CAPACITY_UNKNOWN')
    if sum(item['memory'] for item in running) + 6500 * 1024**2 > min(info['MemTotal'], 14 * 1024**3):
        raise ValueError('QUERY_COMBINED_MEMORY_BUDGET')
    if sum(item['nanoCpus'] for item in running) + 5 * 10**9 > min(info['NCPU'], 16) * 10**9:
        raise ValueError('QUERY_COMBINED_CPU_BUDGET')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 15444))
    image = 'postgres@sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437'
    inspected = json.loads(docker('image', 'inspect', image))[0]
    if inspected['Architecture'] != 'arm64' or inspected['Os'] != 'linux':
        raise ValueError('QUERY_PLATFORM_IMAGE_PLATFORM')
    output.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, mode=0o700)
    os.chmod(private, 0o700)
    def put(name, value):
        with os.fdopen(os.open(private / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as stream:
            stream.write(value)
    put('password', secrets.token_urlsafe(40))
    put('pg_hba.conf', 'local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::0/0 scram-sha-256\n')
    put('certificate.cnf', '[req]\ndistinguished_name=dn\nx509_extensions=extensions\nprompt=no\n[dn]\nCN=platform-pg\n[extensions]\nsubjectAltName=DNS:platform-pg,DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    cert = run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '7',
                '-config', str(private / 'certificate.cnf'), '-keyout', str(private / 'server.key'), '-out', str(private / 'server.crt')],
               ROOT, task=TASK, run_id=RUN, stage='query-platform-new-synthetic-certificate', timeout=20)
    if cert.returncode:
        raise ValueError('QUERY_PLATFORM_CERTIFICATE_FAILED')
    os.chmod(private / 'server.key', 0o600)
    project = 'ontology-g4-m4-query-impl-01'
    labels = {'ontology.task-id': TASK, 'ontology.run-id': RUN, 'ontology.synthetic': 'true'}
    spec = {'name': project, 'services': {'platform-pg': {
        'image': image, 'platform': 'linux/arm64', 'pull_policy': 'never', 'mem_limit': '768m', 'cpus': 0.75,
        'pids_limit': 128, 'init': True, 'read_only': True, 'security_opt': ['no-new-privileges:true'],
        'cap_drop': ['ALL'], 'cap_add': ['CHOWN', 'SETUID', 'SETGID', 'DAC_OVERRIDE', 'FOWNER'], 'labels': labels,
        'environment': {'POSTGRES_DB': 'query', 'POSTGRES_USER': 'postgres', 'POSTGRES_PASSWORD_FILE': '/run/secrets/password'},
        'entrypoint': ['/bin/sh', '-ec'],
        'command': ['cp /run/secrets/server.crt /tmp/server.crt; cp /run/secrets/server.key /tmp/server.key; chown postgres:postgres /tmp/server.crt /tmp/server.key; chmod 600 /tmp/server.key; exec /usr/local/bin/docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key -c hba_file=/run/secrets/pg_hba.conf -c log_statement=none -c log_min_error_statement=panic'],
        'ports': ['127.0.0.1:15444:5432'],
        'volumes': ['platform-data:/var/lib/postgresql', {'type': 'bind', 'source': str(private), 'target': '/run/secrets', 'read_only': True}],
        'tmpfs': ['/tmp:size=16m,mode=1777', '/var/run/postgresql:size=4m,mode=3775,uid=999,gid=999'],
        'networks': ['platform'], 'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U postgres -d query'], 'interval': '2s', 'timeout': '2s', 'retries': 15}
    }}, 'volumes': {'platform-data': {'labels': labels}}, 'networks': {'platform': {'internal': True, 'labels': labels}}}
    compose = output / 'platform-compose.json'
    compose.write_text(json.dumps(spec, indent=2)+'\n')
    record = dict(taskId=TASK, runId=RUN, project=project, context='desktop-linux', engineId=info['ID'],
                  imageId=inspected['Id'], imageReference=image, status='CREATING', before=running,
                  privateDirectory=str(private), compose=str(compose), resources=[])
    identity.write_text(json.dumps(record, indent=2)+'\n')
    result = run(['docker', '--context', 'desktop-linux', 'compose', '-f', str(compose), 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '60'],
                 ROOT, task=TASK, run_id=RUN, stage='query-platform-create', input_key=sha(encoded(spec)), timeout=90)
    current = docker('ps', '-aq', '--filter', 'label=ontology.task-id='+TASK, '--filter', 'label=ontology.run-id='+RUN).decode().split()
    for cid in current:
        item = json.loads(docker('inspect', cid))[0]
        record['resources'].append(dict(kind='container', id=item['Id'], name=item['Name'],
                                       health=item['State'].get('Health', {}).get('Status'), mounts=[{'type':m['Type'],'name':m.get('Name')} for m in item['Mounts']]))
    record.update(exitCode=result.returncode, status='HEALTHY' if result.returncode == 0 and len(current)==1 and record['resources'][0]['health']=='healthy' else 'BLOCKED')
    identity.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'status':record['status'], 'exitCode':result.returncode, 'containerIds':current}))
    return result.returncode


SOURCE_UNKNOWN_TIME_SQL = """CREATE TABLE production.query_assets_unknown (LIKE production.assets INCLUDING ALL);
ALTER TABLE production.query_assets_unknown ALTER COLUMN valid_to DROP NOT NULL;
INSERT INTO production.query_assets_unknown SELECT organization_id,site_id,asset_id,valid_from,NULL,label FROM production.assets WHERE site_id='site-a';
GRANT SELECT ON production.query_assets_unknown TO fixture_reader;
"""


def source_start():
    """只创建M4独占合成源，复用本任务内部网络，历史服务保持KEEP。"""
    import os
    import secrets
    import socket
    import subprocess
    from workflow_execution import run, sha, encoded
    structural(ROOT, TASK, 'source')
    prepared()
    output = ROOT / 'artifacts/workflow' / TASK / RUN
    platform = json.loads((output / 'platform-resources.json').read_text())
    private = ROOT / '.tools/security/g4-m4-query-001' / RUN / 'pg-source'
    identity = output / 'source-resources.json'
    if private.exists() or identity.exists(): raise ValueError('QUERY_SOURCE_ALREADY_REGISTERED')
    prefix = ['docker', '--context', 'desktop-linux']
    def docker(*args): return subprocess.check_output([*prefix, *args], timeout=15)
    info = json.loads(docker('info', '--format', '{{json .}}'))
    if info['ID'] != platform['engineId']: raise ValueError('QUERY_ENGINE_DRIFT')
    running = []
    for cid in docker('ps', '-q').decode().split():
        item = json.loads(docker('inspect', cid))[0]
        running.append(dict(id=item['Id'], memory=item['HostConfig']['Memory'], nanoCpus=item['HostConfig']['NanoCpus']))
    if any(not item['memory'] or not item['nanoCpus'] for item in running): raise ValueError('QUERY_CAPACITY_UNKNOWN')
    if sum(item['memory'] for item in running) + 768*1024**2 > min(info['MemTotal'], 14*1024**3): raise ValueError('QUERY_MEMORY_BUDGET')
    if sum(item['nanoCpus'] for item in running) + 750000000 > min(info['NCPU'],16)*10**9: raise ValueError('QUERY_CPU_BUDGET')
    network = json.loads(docker('network','inspect',platform['project']+'_platform'))[0]
    if not network['Internal'] or network['Labels'].get('ontology.task-id') != TASK: raise ValueError('QUERY_NETWORK_DRIFT')
    with socket.socket() as probe: probe.bind(('127.0.0.1',15445))
    inspected = json.loads(docker('image','inspect',platform['imageReference']))[0]
    if inspected['Id'] != platform['imageId']: raise ValueError('QUERY_IMAGE_DRIFT')
    private.mkdir(mode=0o700)
    def put(name, value):
        with os.fdopen(os.open(private/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as stream: stream.write(value)
    put('password',secrets.token_urlsafe(40))
    reader = secrets.token_urlsafe(40)
    put('reader-password',reader)
    put('pg_hba.conf','local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::0/0 scram-sha-256\n')
    put('certificate.cnf','[req]\ndistinguished_name=dn\nx509_extensions=extensions\nprompt=no\n[dn]\nCN=pg-source\n[extensions]\nsubjectAltName=DNS:pg-source,DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    fixture = ROOT/'experiments/g4-m3-mapping-001/fixture.sql'
    baseline = subprocess.check_output(['git','show','f0afb730ce92ecbd3a5947d9c6f58faedc8b2138:experiments/g4-m3-mapping-001/fixture.sql'],cwd=ROOT)
    if fixture.read_bytes() != baseline: raise ValueError('QUERY_PUBLIC_FIXTURE_DRIFT')
    put('init.sql',baseline.decode().replace('__MAPPING_READER_PASSWORD__',reader) + SOURCE_UNKNOWN_TIME_SQL)
    certificate = run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','7','-config',str(private/'certificate.cnf'),'-keyout',str(private/'server.key'),'-out',str(private/'server.crt')],ROOT,task=TASK,run_id=RUN,stage='query-source-new-synthetic-certificate',timeout=20)
    if certificate.returncode: raise ValueError('QUERY_SOURCE_CERTIFICATE')
    os.chmod(private/'server.key',0o600)
    original = json.loads(Path(platform['compose']).read_text())
    service = original['services']['platform-pg']
    service['environment']['POSTGRES_DB'] = 'fixture'
    service['ports'] = ['127.0.0.1:15445:5432']
    service['volumes'] = ['source-data:/var/lib/postgresql',{'type':'bind','source':str(private),'target':'/run/secrets','read_only':True}, {'type':'bind','source':str(private/'init.sql'),'target':'/docker-entrypoint-initdb.d/01-fixture.sql','read_only':True}]
    service['healthcheck']['test'] = ['CMD-SHELL','pg_isready -U postgres -d fixture']
    labels = service['labels']
    spec = {'name':platform['project'],'services':{'pg-source':service},'volumes':{'source-data':{'labels':labels}},'networks':{'platform':{'external':True,'name':network['Name']}}}
    compose = output/'source-compose.json'
    compose.write_text(json.dumps(spec,indent=2)+'\n')
    record = dict(taskId=TASK,runId=RUN,project=platform['project'],engineId=info['ID'],networkId=network['Id'],imageId=inspected['Id'],fixtureSha256=sha(baseline + SOURCE_UNKNOWN_TIME_SQL.encode()),before=running,status='CREATING',resources=[])
    identity.write_text(json.dumps(record,indent=2)+'\n')
    result = run([*prefix,'compose','-f',str(compose),'up','-d','--no-deps','--no-build','--pull','never','--wait','--wait-timeout','60','pg-source'],ROOT,task=TASK,run_id=RUN,stage='query-source-create',input_key=sha(encoded([spec,sha(baseline + SOURCE_UNKNOWN_TIME_SQL.encode())])),timeout=90)
    ids = docker('ps','-aq','--filter','label=com.docker.compose.project='+platform['project'],'--filter','label=com.docker.compose.service=pg-source').decode().split()
    for cid in ids:
        item=json.loads(docker('inspect',cid))[0]
        record['resources'].append(dict(kind='container',id=item['Id'],name=item['Name'],health=item['State'].get('Health',{}).get('Status'),mounts=[dict(type=m['Type'],name=m.get('Name')) for m in item['Mounts']]))
    record.update(exitCode=result.returncode,status='HEALTHY' if result.returncode==0 and len(ids)==1 and record['resources'][0]['health']=='healthy' else 'BLOCKED')
    identity.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'status':record['status'],'containerIds':ids,'exitCode':result.returncode}))
    return result.returncode


def runtime_query_inventory(container):
    """只读运行库安全元数据，确认测试没有清除或改变既有查询，不读取结果密文或业务值。"""
    from workflow_execution import run, sha
    sql = 'BEGIN READ ONLY; SELECT coalesce(json_agg(x ORDER BY x.id), \'[]\'::json) FROM (SELECT "Id" AS id, "ExecutionStatus" AS status, "ResultHash" AS hash, "ResultSize" AS size, "Fence" AS fence FROM semantic_query."Queries") x; COMMIT;'
    result = run(['docker', '--context', 'desktop-linux', 'exec', '-i', container, 'psql', '-U', 'postgres', '-d', 'query', '-v', 'ON_ERROR_STOP=1', '-qAt'],
                 ROOT, task=TASK, run_id=RUN, stage='query-runtime-inventory', stdin=sql.encode(), input_key=sha(sql.encode()), timeout=10)
    if result.returncode: raise ValueError('QUERY_RUNTIME_INVENTORY_FAILED')
    return json.loads(result.stdout)


def test_database_name(suffix):
    """测试库只能来自本次随机标识；拒绝运行库与任意SQL标识符。"""
    import re
    if not isinstance(suffix, str) or not re.fullmatch('[0-9a-f]{12}', suffix):
        raise ValueError('QUERY_TEST_DATABASE_ID_INVALID')
    return 'm4_query_test_' + suffix


def test_database_control(container, suffix, create):
    """只创建或删除本轮准确带所有权注释的空白隔离测试库；原运行库不参与测试。"""
    import subprocess
    from workflow_execution import run, sha
    name = test_database_name(suffix)
    owner = TASK + ':' + RUN + ':' + suffix
    prefix = ['docker', '--context', 'desktop-linux']
    labels = json.loads(subprocess.check_output([*prefix, 'inspect', '--format', '{{json .Config.Labels}}', container], timeout=15))
    if labels.get('ontology.task-id') != TASK or labels.get('ontology.run-id') != RUN:
        raise ValueError('QUERY_TEST_DATABASE_CONTAINER_OWNER')
    def inspect():
        result = run([*prefix, 'exec', '-i', container, 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-qAt'],
                     ROOT, task=TASK, run_id=RUN, stage='query-test-database-inspect',
                     stdin=("SELECT coalesce(shobj_description(oid,'pg_database'),'') FROM pg_database WHERE datname='" + name + "';").encode(),
                     input_key=sha((container + name + 'inspect').encode()), timeout=10)
        if result.returncode: raise ValueError('QUERY_TEST_DATABASE_INSPECT_FAILED')
        return result.stdout.decode().strip()
    before = inspect()
    if (create and before) or (not create and before != owner):
        raise ValueError('QUERY_TEST_DATABASE_OWNER_MISMATCH')
    sql = ('CREATE DATABASE "' + name + '"; COMMENT ON DATABASE "' + name + '" IS \'' + owner + "';") if create else ('DROP DATABASE "' + name + '";')
    intent = dict(taskId=TASK, runId=RUN, containerId=container, database=name, before=before, status='CREATING' if create else 'REMOVING')
    intent_path = ROOT/'artifacts/workflow'/TASK/RUN/(name+('-create.json' if create else '-remove.json'))
    intent_path.write_text(json.dumps(intent, indent=2)+'\n')
    try:
        result = run([*prefix, 'exec', '-i', container, 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-qAt'],
                     ROOT, task=TASK, run_id=RUN, stage='query-test-database-create' if create else 'query-test-database-remove',
                     stdin=sql.encode(), input_key=sha((container + sql).encode()), timeout=10, cleanup=not create)
        after = inspect()
        receipt = dict(taskId=TASK, runId=RUN, containerId=container, database=name, before=before, after=after,
                       commandId=result.receipt['commandId'], exitCode=result.returncode,
                       status=('CREATED' if create else 'REMOVED') if result.returncode == 0 and after == (owner if create else '') else 'KEEP_UNVERIFIED')
        (ROOT/'artifacts/workflow'/TASK/RUN/(name+('-create.json' if create else '-remove.json'))).write_text(json.dumps(receipt, indent=2)+'\n')
        if result.returncode or after != (owner if create else ''):
            raise ValueError('QUERY_TEST_DATABASE_POSTCONDITION_FAILED')
    except Exception:
        intent.update(status='KEEP_UNVERIFIED', reason='database_command_or_postcondition_failed',
                      releaseCondition='inspect_exact_database_task_marker_and_confirm_test_container_absent_before_drop')
        intent_path.write_text(json.dumps(intent, indent=2)+'\n')
        raise


def persistence_test(source=False):
    """内部网络中执行正式工厂测试，短命容器精确登记并回收。"""
    import os
    import subprocess
    import uuid
    from workflow_execution import run, sha, encoded
    prepared()
    output = ROOT / 'artifacts/workflow' / TASK / RUN
    record = json.loads((output / 'platform-resources.json').read_text())
    if record['taskId'] != TASK or record['runId'] != RUN or record['status'] != 'HEALTHY':
        raise ValueError('QUERY_PLATFORM_NOT_READY')
    prefix = ['docker', '--context', 'desktop-linux']
    current = json.loads(subprocess.check_output([*prefix, 'inspect', record['resources'][0]['id']], timeout=10))[0]
    if current['Config']['Labels'].get('ontology.task-id') != TASK or current['State']['Health']['Status'] != 'healthy':
        raise ValueError('QUERY_PLATFORM_IDENTITY_DRIFT')
    image = 'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
    inspected = json.loads(subprocess.check_output([*prefix, 'image', 'inspect', image], timeout=10))[0]
    if inspected['Id'] != image.split('@')[1] or inspected['Architecture'] != 'arm64':
        raise ValueError('QUERY_TEST_IMAGE_DRIFT')
    private = ROOT / '.tools/security/g4-m4-query-001' / RUN / 'platform-pg'
    project = 'OntologyPlatform.ConnectionsTests' if source else 'OntologyPlatform.QueryTests'
    directory = ROOT / 'backend/tests' / project / 'bin/Debug/net10.0'
    inputs = {p.name: sha(p.read_bytes()) for p in directory.glob('*.dll')}
    suffix = uuid.uuid4().hex[:12]
    name = record['project'] + ('-source-test-' if source else '-persistence-test-') + suffix
    before = subprocess.run([*prefix, 'container', 'inspect', name], capture_output=True, timeout=10)
    if before.returncode == 0 or ('No such container: '+name) not in before.stderr.decode():
        raise ValueError('QUERY_TEST_BEFORE_UNVERIFIED')
    envfile = private / ('test-' + suffix + '.env')
    connection = 'Host=platform-pg;Port=5432;Database='+test_database_name(suffix)+';Username=postgres;Password='+ (private / 'password').read_text()+';SSL Mode=VerifyFull;Root Certificate=/run/query-ca.crt;Pooling=false;Include Error Detail=false'
    source_private = ROOT / '.tools/security/g4-m4-query-001' / RUN / 'pg-source'
    if source:
        source_record = json.loads((output/'source-resources.json').read_text())
        source_current = json.loads(subprocess.check_output([*prefix,'inspect',source_record['resources'][0]['id']],timeout=10))[0]
        if source_current['State']['Health']['Status'] != 'healthy' or source_current['Config']['Labels'].get('ontology.task-id') != TASK:
            raise ValueError('QUERY_SOURCE_IDENTITY_DRIFT')
    with os.fdopen(os.open(envfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as stream:
        stream.write(('G4_QUERY_SOURCE_PASSWORD_FILE=/run/query-source-password\nG4_QUERY_SOURCE_CA=/run/query-source-ca.crt\n' if source else 'G4_QUERY_TEST_CONNECTION='+connection+'\n')
                     +'DOTNET_CLI_HOME=/tmp/dotnet\nDOTNET_CLI_TELEMETRY_OPTOUT=1\nDOTNET_SKIP_FIRST_TIME_EXPERIENCE=1\n')
    lifecycle = dict(taskId=TASK, runId=RUN, name=name, imageId=inspected['Id'], status='CREATING', beforeExists=False)
    receipt_path = output / (name + '.json')
    receipt_path.write_text(json.dumps(lifecycle, indent=2)+'\n')
    command = [*prefix, 'run', '--pull=never', '--name', name, '--network', record['project']+'_platform',
               '--label', 'ontology.task-id='+TASK, '--label', 'ontology.run-id='+RUN,
               '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=768m', '--cpus=0.5', '--pids-limit=128',
               '--tmpfs', '/tmp:size=64m,mode=1777', '--env-file', str(envfile),
               '--mount', 'type=bind,src='+str(directory)+',dst=/app,readonly',
               '--mount', 'type=bind,src='+str(private/'server.crt')+',dst=/run/query-ca.crt,readonly',
               *(['--mount','type=bind,src='+str(source_private/'reader-password')+',dst=/run/query-source-password,readonly',
                  '--mount','type=bind,src='+str(source_private/'server.crt')+',dst=/run/query-source-ca.crt,readonly'] if source else []),
               '--workdir', '/app', image, 'dotnet', project+'.dll',
               '--filter', 'FullyQualifiedName~G4QuerySourceIntegrationTests' if source else 'FullyQualifiedName~G4QueryPersistenceTests|FullyQualifiedName~G4QueryRaceTests', '--timeout', '30s', '--zero-tests-policy', 'strict']
    result = None
    runtime_before = runtime_query_inventory(record['resources'][0]['id']) if not source else None
    database_created = False
    try:
        if not source:
            test_database_control(record['resources'][0]['id'], suffix, True)
            database_created = True
        result = run(command, ROOT, task=TASK, run_id=RUN, stage='query-real-source-container' if source else 'query-real-persistence-container',
                     input_key=sha(encoded([inputs, sha(Path(__file__).read_bytes()), inspected['Id']])), timeout=60)
        print(result.stdout.decode(errors='replace')[-5000:])
        print(json.dumps({'exitCode': result.returncode, 'receipt':result.receipt['commandId']}))
    finally:
        try:
            inspection = subprocess.run([*prefix, 'inspect', name], capture_output=True, timeout=10)
            if inspection.returncode == 0:
                item = json.loads(inspection.stdout)[0]
                if item['Config']['Labels'].get('ontology.task-id') != TASK or item['Config']['Labels'].get('ontology.run-id') != RUN:
                    raise ValueError('QUERY_TEST_CLEANUP_OWNER')
                lifecycle.update(id=item['Id'], exitCode=item['State']['ExitCode'], running=item['State']['Running'])
                if item['State']['Running']:
                    stopped = run([*prefix, 'stop', '-t', '2', item['Id']], ROOT, task=TASK, run_id=RUN, stage='query-test-stop', cleanup=True, timeout=10)
                    if stopped.returncode: raise ValueError('QUERY_TEST_STOP_FAILED')
                removed = run([*prefix, 'rm', item['Id']], ROOT, task=TASK, run_id=RUN, stage='query-test-remove', cleanup=True, timeout=10)
                after = subprocess.run([*prefix, 'container', 'inspect', item['Id']], capture_output=True, timeout=10)
                verified = removed.returncode == 0 and after.returncode != 0 and ('No such container: '+item['Id']) in after.stderr.decode()
                lifecycle.update(status='REMOVED' if verified else 'CLEANUP_UNVERIFIED', removeExit=removed.returncode, exactIdAbsent=verified)
            elif ('No such object: '+name) in inspection.stderr.decode() or ('No such container: '+name) in inspection.stderr.decode():
                lifecycle.update(status='NOT_CREATED', exactNameAbsent=True)
            else:
                lifecycle.update(status='KEEP_UNVERIFIED', reason='container_existence_not_confirmed')
            receipt_path.write_text(json.dumps(lifecycle, indent=2)+'\n')
            envfile.unlink()
            if database_created and lifecycle.get('status') in ('REMOVED', 'NOT_CREATED'):
                test_database_control(record['resources'][0]['id'], suffix, False)
                runtime_after = runtime_query_inventory(record['resources'][0]['id'])
                unchanged = runtime_before == runtime_after
                (output / (test_database_name(suffix)+'-runtime-preservation.json')).write_text(json.dumps(dict(taskId=TASK, runId=RUN, before=runtime_before, after=runtime_after, unchanged=unchanged), indent=2)+'\n')
                if not unchanged: raise ValueError('QUERY_RUNTIME_CHANGED_DURING_ISOLATED_TEST')
            elif database_created:
                (output / (test_database_name(suffix)+'-keep.json')).write_text(json.dumps(dict(taskId=TASK, runId=RUN, database=test_database_name(suffix), status='KEEP_UNVERIFIED', reason='test_container_not_confirmed_absent', releaseCondition='exact_test_container_absent_then_owned_database_drop'), indent=2)+'\n')
        finally:
            if lifecycle.get('status') not in ('REMOVED', 'NOT_CREATED'):
                lifecycle.update(status='KEEP_UNVERIFIED', reason='test_container_cleanup_not_confirmed',
                                 releaseCondition='verify_exact_container_owner_and_exit_then_remove_exact_id')
                receipt_path.write_text(json.dumps(lifecycle, indent=2)+'\n')
                if database_created:
                    (output / (test_database_name(suffix)+'-keep.json')).write_text(json.dumps(dict(taskId=TASK, runId=RUN,
                        database=test_database_name(suffix), containerName=name, status='KEEP_UNVERIFIED',
                        reason='test_container_cleanup_not_confirmed',
                        releaseCondition='exact_test_container_absent_then_owned_database_drop'), indent=2)+'\n')
            envfile.unlink(missing_ok=True)
    if lifecycle.get('status') not in ('REMOVED', 'NOT_CREATED'): raise ValueError('QUERY_TEST_CLEANUP_UNVERIFIED')
    return result.returncode if result is not None else 2


def runtime_agent_test(binding_race=False):
    """真实MAF只恢复当前精确Query；复用正式API只读挂载，不运行迁移或Sweep。"""
    import subprocess
    import uuid
    from workflow_execution import run, sha, encoded
    output=ROOT/'artifacts/workflow'/TASK/RUN
    api=json.loads((output/'runtime-api-start.json').read_text())['id']
    secondary=json.loads((output/'runtime-secondary-api.json').read_text())['process']['id']
    prefix=['docker','--context','desktop-linux']
    if subprocess.check_output([*prefix,'inspect','--format','{{.State.Running}}',secondary],timeout=15).strip()!=b'false':
        raise ValueError('QUERY_RUNTIME_TEST_SECONDARY_SLOT_REQUIRED')
    labels=json.loads(subprocess.check_output([*prefix,'inspect','--format','{{json .Config.Labels}}',api],timeout=15))
    if labels.get('ontology.task-id')!=TASK or labels.get('ontology.run-id')!=RUN: raise ValueError('QUERY_RUNTIME_TEST_OWNER')
    state=json.loads((output/'runtime-fixture.json').read_text())
    directory=ROOT/'backend/tests/OntologyPlatform.AgentTests/bin/Debug/net10.0'
    image='mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
    name='ontology-g4-m4-query-impl-01-maf-test-'+uuid.uuid4().hex[:12]
    before=subprocess.run([*prefix,'inspect',name],capture_output=True,timeout=15)
    if before.returncode==0 or ('no such object: '+name) not in before.stderr.decode().lower(): raise ValueError('QUERY_RUNTIME_TEST_BEFORE_UNKNOWN')
    lifecycle=dict(taskId=TASK,runId=RUN,name=name,status='CREATING',beforeExists=False,readOnlyRuntimeFrom=api,queryId=state['latestQuery']['queryId'],bindingRace=binding_race)
    path=output/(name+'.json');path.write_text(json.dumps(lifecycle,indent=2)+'\n')
    cid=None
    try:
        created=runtime_command('query-maf-container-create',[*prefix,'create','--pull=never','--name',name,
            '--network','ontology-g4-m4-query-impl-01_platform','--label','ontology.task-id='+TASK,'--label','ontology.run-id='+RUN,
            '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user','501:20','--memory=768m','--cpus=0.5','--pids-limit=128',
            '--tmpfs','/tmp:size=64m,mode=1777','--volumes-from',api+':ro','--mount','type=bind,src='+str(directory)+',dst=/tests,readonly',
            '--workdir','/private/api','-e','ASPNETCORE_ENVIRONMENT=Development','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_EnableDiagnostics=0',
            '-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','TESTINGPLATFORM_TELEMETRY_OPTOUT=1','-e','XDG_DATA_HOME=/tmp/data',
            '-e','G4_QUERY_BINDING_RACE='+('1' if binding_race else '0'),
            '-e','G4_QUERY_RUNTIME_ACTOR='+json.dumps(state['latestQuery']['actor'],separators=(',',':')),
            '-e','G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,'-e','G4_QUERY_RUNTIME_QUERY_ID='+state['latestQuery']['queryId'],
            image,'sh','-c',"""dotnet /runtime/QueryLoopback.dll & bridge=$!; trap 'kill "$bridge" 2>/dev/null || true' EXIT; dotnet /tests/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName~G4QueryMafRuntimeTests --timeout 45s --zero-tests-policy strict --results-directory /tmp/TestResults"""])
        cid=created.stdout.decode().strip();lifecycle.update(id=cid,status='CREATED');path.write_text(json.dumps(lifecycle,indent=2)+'\n')
        runtime_command('query-maf-container-network',[*prefix,'network','connect','ontology-g4-m4-query-impl-01_edge',cid])
        inputs={p.name:sha(p.read_bytes()) for p in directory.glob('*.dll')}
        result=run([*prefix,'start','--attach',cid],ROOT,task=TASK,run_id=RUN,stage='query-real-maf-binding-runtime' if binding_race else 'query-real-maf-runtime',
            input_key=sha(encoded([inputs,state['latestQuery']['queryId'],binding_race,sha(Path(__file__).read_bytes())])),timeout=60)
        lifecycle['commandId']=result.receipt['commandId'];lifecycle['exitCode']=result.returncode
        print(result.stdout.decode(errors='replace')[-5000:]);print(json.dumps({'exitCode':result.returncode,'receipt':result.receipt['commandId']}))
        return result.returncode
    finally:
        try:
            if cid:
                actual=json.loads(subprocess.check_output([*prefix,'inspect',cid],timeout=15))[0]
                if actual['Config']['Labels'].get('ontology.task-id')!=TASK or actual['Config']['Labels'].get('ontology.run-id')!=RUN or actual['State']['Running']:
                    raise ValueError('QUERY_RUNTIME_TEST_CLEANUP_UNSAFE')
                removed=runtime_command('query-maf-container-remove',[*prefix,'rm',cid])
                after=subprocess.run([*prefix,'inspect',cid],capture_output=True,timeout=15)
                if after.returncode==0 or ('no such object: '+cid) not in after.stderr.decode().lower(): raise ValueError('QUERY_RUNTIME_TEST_CLEANUP_UNVERIFIED')
                lifecycle.update(status='REMOVED',afterExists=False,cleanupCommandId=removed.receipt['commandId'])
            else: lifecycle.update(status='KEEP_UNVERIFIED',release='Confirm exact created container ownership and stopped state before removal')
        finally:
            if lifecycle['status'] not in ['REMOVED','KEEP_UNVERIFIED']: lifecycle.update(status='KEEP_UNVERIFIED',release='Confirm exact stopped container and retry removal')
            path.write_text(json.dumps(lifecycle,indent=2)+'\n')


def qualification_inputs():
    """资格只绑定当前产品、测试与执行脚本；证据文档追加不会改变被测输入。"""
    from workflow_execution import sha
    import workflow
    paths = set(workflow.git(ROOT, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0'))-{''}
    return {path: sha((ROOT/path).read_bytes()) if (ROOT/path).is_file() else 'DELETED'
            for path in sorted(paths) if not path.startswith('docs/') or path.startswith('docs/contracts/')
            if path not in ['AGENTS.md', 'PLANS.md']}



def attest(name):
    """在实际执行前后封存输入和原件；失败也保存，不允许手填成功证明。"""
    import uuid
    from workflow_execution import sha
    actions = {
        'contract': contract_test,
        'query-unit': lambda: unit_test('OntologyPlatform.QueryTests', 'G4QueryTests'),
        'source-unit': lambda: unit_test('OntologyPlatform.ConnectionsTests', 'G4QuerySourceTests'),
        'security-unit': lambda: unit_test('OntologyPlatform.SecurityTests', 'G4QueryAuthorizationTests'),
        'agent-unit': lambda: unit_test('OntologyPlatform.AgentTests', 'G4QueryMcpTests'),
        'persistence': persistence_test,
        'source': lambda: persistence_test(True),
        'maf-binding': lambda: runtime_agent_test(True),
        **{mode: (lambda mode=mode: browser_test(mode)) for mode in
           ['s1', 's1-reopen', 's2-basic', 's2-runtime', 's2-race', 's2-aba', 's2-capacity', 's2-inflight', 's2-connection', 's3', 'ui-s1', 'ui-s3']},
        **{'web-'+stage: (lambda stage=stage: web_check(stage)) for stage in ['typecheck', 'lint', 'unit']},
    }
    if name not in actions: raise ValueError('QUERY_ATTEST_ACTION_INVALID')
    output = ROOT/'artifacts/workflow'/TASK/RUN
    commands = output.parent/'commands'/RUN
    before = set(commands.glob('*/receipt.json'))
    reports = set(output.glob('browser-*.json'))
    inputs = qualification_inputs()
    import workflow
    keys = {gate:workflow.input_key(ROOT, gate) for gate in ['environment','contract','backend','web','interaction']}
    row = dict(taskId=TASK, runId=RUN, name=name, inputs=inputs, inputKeys=keys, status='FAIL')
    projects = {'contract':'G2ContractTests','query-unit':'QueryTests','source-unit':'ConnectionsTests',
                'security-unit':'SecurityTests','agent-unit':'AgentTests','persistence':'QueryTests',
                'source':'ConnectionsTests','maf-binding':'AgentTests'}
    try:
        if name in projects:
            build = json.loads((output/('build-binding-OntologyPlatform.'+projects[name]+'.json')).read_text())
            if not build['binaries'] or any(sha((ROOT/path).read_bytes()) != digest for group in ['inputs','binaries'] for path,digest in build[group].items()):
                raise ValueError('QUERY_ATTEST_BUILD_DRIFT')
            row['build'] = build
        code = actions[name]()
        row['exitCode'] = code
        row['inputsUnchanged'] = inputs == qualification_inputs() and all(workflow.input_key(ROOT, gate) == key for gate,key in keys.items())
        if code == 0 and row['inputsUnchanged']: row['status'] = 'PASS'
        return code
    finally:
        row['commands'] = [dict(path=str(path.relative_to(ROOT)), sha256=sha(path.read_bytes())) for path in sorted(set(commands.glob('*/receipt.json'))-before)]
        row['reports'] = [dict(path=str(path.relative_to(ROOT)), sha256=sha(path.read_bytes())) for path in sorted(set(output.glob('browser-*.json'))-reports) if json.loads(path.read_text()).get('mode') == name]
        path = output/('qualification-'+name+'-'+uuid.uuid4().hex+'.json')
        path.write_text(json.dumps(row, indent=2)+'\n')
        print(json.dumps(dict(qualification=str(path.relative_to(ROOT)), status=row['status'])))


def demand_qualification(row, name, inputs):
    """先拒绝外任务、失败、漂移与零原件，随后才打开实际命令报告。"""
    if row.get('taskId') != TASK or row.get('runId') != RUN or row.get('name') != name \
        or row.get('status') != 'PASS' or row.get('exitCode') != 0 or row.get('inputsUnchanged') is not True \
        or row.get('inputs') != inputs or not row.get('commands'):
        raise ValueError('QUERY_QUALIFICATION_INVALID')


def qualify(gate, input_key):
    """当前输入重开实际非零测试和浏览器原件；缺适配证据保持阻断。"""
    import workflow
    from workflow_execution import ordinary, sha
    from workflow_m2_evidence import mtp
    if gate not in ['environment', 'contract', 'backend', 'web', 'interaction'] or workflow.input_key(ROOT, gate) != input_key:
        raise ValueError('QUERY_QUALIFICATION_GATE_INVALID')
    prepared()
    structural(ROOT, TASK)
    required = {
        'environment': [], 'contract': ['contract'],
        'backend': ['query-unit', 'source-unit', 'security-unit', 'agent-unit', 'persistence', 'source', 'maf-binding'],
        'web': ['web-typecheck', 'web-lint', 'web-unit', 'ui-s1', 'ui-s3'],
        'interaction': ['s1', 's1-reopen', 's2-basic', 's2-runtime', 's2-race', 's2-aba', 's2-capacity', 's2-inflight', 's2-connection', 's3'],
    }[gate]
    output = ROOT/'artifacts/workflow'/TASK/RUN
    inputs = qualification_inputs()
    originals = []
    count = 1 if gate == 'environment' else 0
    def read(reference):
        path = ordinary(ROOT/reference['path'])
        if not path.is_relative_to(ROOT/'artifacts/workflow'/TASK): raise ValueError('QUERY_QUALIFICATION_PATH')
        raw = path.read_bytes()
        if sha(raw) != reference['sha256']: raise ValueError('QUERY_QUALIFICATION_HASH')
        originals.append(reference)
        return raw
    for name in required:
        candidates = sorted(output.glob('qualification-'+name+'-*.json'), key=lambda path: path.stat().st_mtime)
        if not candidates: raise ValueError('QUERY_QUALIFICATION_MISSING_'+name)
        path = candidates[-1]
        row = json.loads(read(dict(path=str(path.relative_to(ROOT)), sha256=sha(path.read_bytes()))))
        demand_qualification(row, name, inputs)
        if row.get('inputKeys', {}).get(gate) != input_key: raise ValueError('QUERY_QUALIFICATION_GATE_DRIFT')
        test_count = 0
        if 'build' in row:
            from workflow_execution import encoded
            build = row['build']; receipt = build['receipt']
            original = ROOT/'artifacts/workflow'/TASK/'commands'/RUN/receipt['commandId']/'receipt.json'
            if json.loads(original.read_text()) != receipt or receipt.get('exitCode') != 0 or receipt.get('stage') != 'query-build-'+build['project'] or receipt.get('inputFingerprint') != sha(encoded(build['inputs'])) or not build['binaries']:
                raise ValueError('QUERY_QUALIFICATION_BUILD')
            if any(inputs.get(path) != digest for path,digest in build['inputs'].items()): raise ValueError('QUERY_QUALIFICATION_BUILD_INPUT')
            read(dict(path=str(original.relative_to(ROOT)),sha256=sha(original.read_bytes())))
            for stream in ['stdout','stderr']: read(receipt[stream])
        for reference in row['commands']:
            command = json.loads(read(reference))
            if command.get('taskId') != TASK or command.get('runId') != RUN or command.get('exitCode') != 0 or command.get('classification') != 'SUCCESS' or not command.get('started'):
                raise ValueError('QUERY_QUALIFICATION_COMMAND')
            raw = b''.join(read(command[key]) for key in ['stdout', 'stderr'])
            if command['stage'].startswith(('query-unit-', 'query-contract-tests', 'query-real-')):
                test_count += mtp(raw, 1)
        if row['reports']:
            for reference in row['reports']:
                report = json.loads(read(reference))
                if report.get('taskId') != TASK or report.get('runId') != RUN or report.get('mode') != name or report.get('status') != 'PASS' or report.get('inputsUnchanged') is not True or not report.get('http') or not report.get('checks') or any(check.get('status') != 'PASS' for check in report['checks']):
                    raise ValueError('QUERY_QUALIFICATION_BROWSER')
                test_count += len(report['checks'])
        elif name.startswith('web-'):
            stage = name.removeprefix('web-')
            rows = [json.loads(path.read_text()) for path in output.glob('web-'+stage+'-*/result.json')]
            matching = [web for web in rows if any(json.loads(read(ref))['commandId'] == web['commandId'] for ref in row['commands'])]
            if len(matching) != 1 or matching[0]['exitCode'] != 0: raise ValueError('QUERY_QUALIFICATION_WEB')
            web = matching[0]
            if any(sha((ROOT/path).read_bytes()) != digest for path, digest in web['inputs'].items()): raise ValueError('QUERY_QUALIFICATION_WEB_INPUT')
            if stage == 'unit':
                from workflow_evidence import machine
                test_count += machine(read(dict(path=web['report'], sha256=web['reportSha256'])), 'vitest-json')
            else: test_count += 1
        if test_count <= 0: raise ValueError('QUERY_QUALIFICATION_ZERO_TESTS')
        count += test_count
    return dict(taskId=TASK, runId=RUN, gate=gate, status='PASS', executionMode='REUSED', qualificationMode='FRESH', tests=count, skipped=0, originals=originals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['platform-start', 'persistence-test', 'persistence-build', 'contract-build', 'contract-test', 'host-preflight', 'host-monitor', 'qualify'])
    parser.add_argument('--task', default=TASK)
    parser.add_argument('--run-id', default=RUN)
    parser.add_argument('--gate')
    parser.add_argument('--input-key')
    args = parser.parse_args()
    if args.task != TASK or args.run_id != RUN: raise ValueError('QUERY_CLI_IDENTITY')
    if args.command == 'qualify':
        print(json.dumps(qualify(args.gate, args.input_key)))
        return 0
    try:
        return platform_start() if args.command == 'platform-start' else persistence_test() if args.command == 'persistence-test' else contract_build('OntologyPlatform.QueryTests') if args.command == 'persistence-build' else contract_build() if args.command == 'contract-build' else contract_test() if args.command == 'contract-test' else host(args.command.removeprefix('host-'))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
