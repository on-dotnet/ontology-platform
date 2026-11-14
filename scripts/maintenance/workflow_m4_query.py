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
    texts = {key: uncomment(source_path(root, value).read_text()) for key, value in paths.items()}
    if 'AddDbContextFactory<G4QueryDbContext>' not in texts['composition'] or 'UseNpgsql' not in texts['composition']:
        raise ValueError('QUERY_FACTORY_NOT_REGISTERED')
    if phase in ('source', 'runtime') and any(token not in texts['source'] for token in ('ReadAsync', 'NpgsqlConnection', 'BeginTransactionAsync')):
        raise ValueError('QUERY_SOURCE_EXECUTION_NOT_IMPLEMENTED')
    if phase == 'runtime' and any('"'+action+'"' not in texts['audit'] for action in
                                  ('data.query.execute', 'data.query.read', 'data.query.cancel', 'data.query.evidence.read', 'data.query.expire')):
        raise ValueError('QUERY_AUDIT_NOT_REGISTERED')
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


def contract_build(project="OntologyPlatform.G2ContractTests"):
    """测试先行的合同编译保留真实失败与退出码，不把编译当测试通过。"""
    from workflow_execution import run, sha, encoded
    _, env = prepared()
    inputs = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for pattern in
              ('backend/src/**/*.cs', 'backend/tests/' + project + '/**/*.cs')
              for p in sorted(ROOT.glob(pattern)) if 'obj' not in p.parts and 'bin' not in p.parts}
    result = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
                  '/usr/local/share/dotnet/dotnet', 'build', 'backend/tests/' + project,
                  '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], ROOT,
                 task=TASK, run_id=RUN, stage='query-build-' + project, environment=env,
                 input_key=sha(encoded(inputs)), timeout=180)
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
                  '--filter', 'FullyQualifiedName~G4QueryWireTests', '--timeout', '60s', '--zero-tests-policy', 'strict'], ROOT,
                 task=TASK, run_id=RUN, stage='query-contract-tests', environment=env,
                 input_key=sha(encoded(inputs)), timeout=90)
    print(result.stdout.decode(errors='replace')[-8000:])
    print(result.stderr.decode(errors='replace')[-2000:])
    print(json.dumps({'exitCode': result.returncode, 'receipt': result.receipt['commandId']}))
    return result.returncode


def unit_test(project, filter_name):
    """精确选择当前M4非零测试，原件与输入身份交给公共执行器。"""
    from workflow_execution import run, sha, encoded
    if (project, filter_name) not in (('OntologyPlatform.QueryTests', 'G4QueryTests'),
                                    ('OntologyPlatform.SecurityTests', 'G4QueryAuthorizationTests'),
                                    ('OntologyPlatform.ConnectionsTests', 'G4QuerySourceTests')):
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
    connection = 'Host=platform-pg;Port=5432;Database=query;Username=postgres;Password='+ (private / 'password').read_text()+';SSL Mode=VerifyFull;Root Certificate=/run/query-ca.crt;Pooling=false;Include Error Detail=false'
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
    try:
        result = run(command, ROOT, task=TASK, run_id=RUN, stage='query-real-source-container' if source else 'query-real-persistence-container',
                     input_key=sha(encoded([inputs, sha(Path(__file__).read_bytes()), inspected['Id']])), timeout=60)
        print(result.stdout.decode(errors='replace')[-5000:])
        print(json.dumps({'exitCode': result.returncode, 'receipt':result.receipt['commandId']}))
    finally:
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
        receipt_path.write_text(json.dumps(lifecycle, indent=2)+'\n')
        envfile.unlink()
    if lifecycle.get('status') != 'REMOVED': raise ValueError('QUERY_TEST_CLEANUP_UNVERIFIED')
    return result.returncode if result is not None else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['platform-start', 'persistence-test', 'persistence-build', 'contract-build', 'contract-test', 'host-preflight', 'host-monitor'])
    args = parser.parse_args()
    try:
        return platform_start() if args.command == 'platform-start' else persistence_test() if args.command == 'persistence-test' else contract_build('OntologyPlatform.QueryTests') if args.command == 'persistence-build' else contract_build() if args.command == 'contract-build' else contract_test() if args.command == 'contract-test' else host(args.command.removeprefix('host-'))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
