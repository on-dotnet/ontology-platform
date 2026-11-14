#!/usr/bin/env python3
"""M3专属有界入口；分阶段准入不冒充完整映射生命周期。"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M3-MAPPING-001'
ACTIONS = ('mapping.create', 'mapping.update', 'mapping.validate.start', 'mapping.validate.finish',
           'mapping.validate.cancel', 'mapping.proposal.create', 'mapping.proposal.cancel',
           'mapping.decision', 'mapping.activate', 'mapping.rollback', 'mapping.grant.change')


def structural(root, task, phase='runtime'):
    """检查准确消费者；仅授权/持久化阶段不能标记产品完整可用。"""
    from execution_preflight import source_path, uncomment
    if task != TASK or phase not in ('persistence', 'source', 'runtime'):
        raise ValueError('MAPPING_TASK_PHASE_INVALID')
    paths = {
        'composition': 'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs',
        'authority': 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/MappingAuthorizationParticipant.cs',
        'audit': 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs',
        'persistence': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Persistence/ConnectionsDbContext.cs',
        'tests': 'backend/tests/OntologyPlatform.SecurityTests/G4MappingAuthorizationTests.cs',
    }
    if phase == 'source':
        paths.update(validator='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgMappingSourceValidator.cs',
                     sourceTests='backend/tests/OntologyPlatform.ConnectionsTests/G4MappingSourceTests.cs')
    if phase == 'runtime':
        paths.update(application='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingApplicationService.cs',
                     activation='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingActivationService.cs',
                     validator='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgMappingSourceValidator.cs',
                     endpoints='backend/src/Hosts/OntologyPlatform.Api/G4/MappingEndpoints.cs',
                     routes='backend/src/Hosts/OntologyPlatform.Api/G4/G4Endpoints.cs',
                     worker='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingJobWorker.cs',
                     outbox='backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingOutboxDispatcher.cs')
    texts = {key: uncomment(source_path(root, path).read_text()) for key, path in paths.items()}
    registrations = re.findall(r'\.Add(?:Scoped|Singleton|Transient)<([^>]+)>', texts['composition'])
    direct_authority = 'IMappingAuthorizationAuthority, MappingAuthorizationParticipant' in registrations
    shared_authority = 'MappingAuthorizationParticipant' in registrations and re.search(
        r'\.AddScoped<IMappingAuthorizationAuthority>\(provider\s*=>\s*provider\.GetRequiredService<MappingAuthorizationParticipant>\(\)\)',
        texts['composition']) is not None
    if not (direct_authority or shared_authority):
        raise ValueError('MAPPING_AUTHORITY_NOT_REGISTERED')
    if not any('IMappingSessionAuthority, MappingSessionAuthority' == value for value in registrations):
        raise ValueError('MAPPING_SESSION_NOT_REGISTERED')
    block = re.search(r'\bActions\s*=\s*new\([^;]*?\)\s*\{(.*?)\};', texts['audit'], re.S)
    registered = set(re.findall(r'"([a-z][a-z0-9_.]+)"', block[1])) if block else set()
    if not set(ACTIONS) <= registered:
        raise ValueError('MAPPING_AUDIT_NOT_REGISTERED')
    if phase == 'source' and 'IMappingSourceValidator, PgMappingSourceValidator' not in registrations:
        raise ValueError('MAPPING_SOURCE_NOT_REGISTERED')
    if phase == 'runtime' and not all(any(name in entry for entry in registrations)
                                      for name in ('MappingApplicationService', 'MappingActivationService', 'PgMappingSourceValidator')):
        raise ValueError('MAPPING_RUNTIME_NOT_REGISTERED')
    if phase == 'runtime':
        hosted = re.findall(r'\.AddHostedService<([^>]+)>', texts['composition'])
        if not {'MappingJobWorker', 'MappingOutboxDispatcher'} <= set(hosted) or '.MapMappingEndpoints()' not in texts['routes']:
            raise ValueError('MAPPING_CONSUMER_NOT_REGISTERED')
        if not all(name in texts['worker'] for name in ('AssessAsync(', 'DemandInTransactionAsync(', 'CurrentAsync(', 'WriteAsync(')):
            raise ValueError('MAPPING_WORKER_NOT_EXECUTABLE')
        if 'DispatchAsync(' not in texts['outbox'] or 'MappingOutboxReceipts' not in texts['outbox']:
            raise ValueError('MAPPING_OUTBOX_NOT_EXECUTABLE')
    return dict(taskId=task, phase=phase, status='STRUCTURAL_READY', consumers=paths,
                database='NOT_RUN', lifecycle='NOT_RUN', production='NOT_AUTHORIZED')


def persistence_tests(run_id):
    """真实PG阶段：检查资源归属、无恢复构建，再执行准确程序集并保留原始证据。"""
    import hashlib
    import subprocess
    import workflow_environment as environment
    import workflow_m2_build as build
    from workflow_execution import run
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', run_id):
        raise ValueError('MAPPING_RUN_INVALID')
    structural(ROOT, TASK, 'persistence')
    output = ROOT / 'artifacts/workflow' / TASK / run_id
    resource = json.loads((output / 'platform-resources.json').read_text())
    if resource['taskId'] != TASK or resource['runId'] != run_id or resource['status'] != 'HEALTHY':
        raise ValueError('MAPPING_RESOURCE_IDENTITY')
    container = next(row['id'] for row in resource['resources'] if row['kind'] == 'container')
    inspected = subprocess.run(['docker', '--context', resource['context'], 'inspect', container], capture_output=True, timeout=10)
    if inspected.returncode:
        raise ValueError('MAPPING_RESOURCE_UNAVAILABLE')
    actual = json.loads(inspected.stdout)[0]
    if actual['Config']['Labels'].get('ontology.task-id') != TASK or actual['Config']['Labels'].get('ontology.run-id') != run_id or not actual['State']['Running']:
        raise ValueError('MAPPING_RESOURCE_OWNER')
    private = ROOT / '.tools/security/g4-m3-mapping-001' / run_id / 'platform-pg'
    if str(private.relative_to(ROOT)) != resource['privatePath'] or private.is_symlink():
        raise ValueError('MAPPING_PRIVATE_BOUNDARY')
    home = next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir())
    env = environment.environment(home)
    # 仅新建合成密码在子进程环境使用，不进入命令、日志或公开回执。
    synthetic_password = (private / 'password').read_text()
    database_name = resource.get('databaseName')
    if database_name not in ('mapping_v2', 'mapping_v3'):
        raise ValueError('MAPPING_CURRENT_DATABASE_REQUIRED')
    env['MAPPING_TEST_PG'] = 'Host=127.0.0.1;Port=15463;Database=' + database_name + ';Username=postgres;Password=' + synthetic_password + ';SSL Mode=VerifyFull;Root Certificate=' + str(private / 'server.crt') + ';Timeout=5;Command Timeout=5;Application Name=G4-M3-MAPPING-001'
    project = 'backend/tests/OntologyPlatform.SecurityTests'
    source = build.inputs('wire')
    command = ['/usr/local/share/dotnet/dotnet', 'build', project, '--no-restore', '--disable-build-servers', '-m:1', '-v:q']
    compiled = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)', *command], ROOT,
                   task=TASK, run_id=run_id, stage='persistence-bound-build', environment=env, timeout=180, input_key=source)
    (output / 'persistence-bound-build.txt').write_bytes(compiled.stdout + compiled.stderr)
    if compiled.returncode or source != build.inputs('wire'):
        raise ValueError('MAPPING_BUILD_FAILED')
    dll = ROOT / project / 'bin/Debug/net10.0/OntologyPlatform.SecurityTests.dll'
    binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dll.parent.glob('*.dll')}
    key = hashlib.sha256(json.dumps([source, binaries, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), hashlib.sha256((ROOT / 'experiments/g4-m3-mapping-001/compose.yaml').read_bytes()).hexdigest()], sort_keys=True).encode()).hexdigest()
    command = ['/usr/local/share/dotnet/dotnet', str(dll), '--filter', 'FullyQualifiedName~G4MappingAuthorizationTests', '--timeout', '30s', '--zero-tests-policy', 'strict']
    profile = '(version 1) (allow default) (deny network-outbound) (allow network-outbound (remote ip "localhost:15463"))'
    tested = run(['/usr/bin/sandbox-exec', '-p', profile, *command], ROOT, task=TASK, run_id=run_id,
                 stage='persistence-real', environment=env, timeout=45, input_key=key)
    raw = tested.stdout + tested.stderr
    (output / 'persistence-real.txt').write_bytes(raw)
    # 返回码不代替真实测试计数；原始MTP摘要必须无skip、非零成功。
    text = raw.decode(errors='replace')
    success = re.search(r'(?:成功|Passed|succeeded):\s*(\d+)', text)
    skipped = re.search(r'(?:已跳过|Skipped|skipped):\s*(\d+)', text)
    passed = tested.returncode == 0 and success and int(success[1]) == 4 and skipped and int(skipped[1]) == 0 and source == build.inputs('wire')
    result = dict(taskId=TASK, runId=run_id, phase='persistence', status='PASS' if passed else 'FAIL', exitCode=tested.returncode,
                  inputKey=source, binaries=binaries, logSha256=hashlib.sha256(raw).hexdigest(), lifecycle='NOT_RUN', receipt=tested.receipt)
    (output / 'persistence-result.json').write_text(json.dumps(result, indent=2) + '\n')
    return dict(taskId=TASK, phase='persistence', status=result['status'], exitCode=tested.returncode, lifecycle='NOT_RUN')


def source_tests(run_id):
    """精确固定源网络中运行真实适配器测试，按ID回收短命测试容器。"""
    import hashlib
    import os
    import subprocess
    import uuid
    import workflow_m2_build as build
    from workflow_execution import run
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', run_id):
        raise ValueError('MAPPING_RUN_INVALID')
    structural(ROOT, TASK, 'source')
    output = ROOT / 'artifacts/workflow' / TASK / run_id
    source = json.loads((output / 'source-resources.json').read_text())
    if source.get('taskId') != TASK or source.get('runId') != run_id or source.get('status') != 'HEALTHY':
        raise ValueError('MAPPING_SOURCE_IDENTITY')
    context = source['context']
    image = 'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
    inspected = subprocess.run(['docker', '--context', context, 'image', 'inspect', image], capture_output=True, timeout=10)
    if inspected.returncode:
        raise ValueError('MAPPING_LOCAL_IMAGE_MISSING')
    image_info = json.loads(inspected.stdout)[0]
    if image_info['Id'] != 'sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55' or image_info['Architecture'] != 'arm64':
        raise ValueError('MAPPING_LOCAL_IMAGE_DRIFT')
    container_id = next(row['id'] for row in source['resources'] if row['kind'] == 'container')
    inspected = subprocess.run(['docker', '--context', context, 'container', 'inspect', container_id], capture_output=True, timeout=10)
    if inspected.returncode:
        raise ValueError('MAPPING_SOURCE_DOWN')
    actual = json.loads(inspected.stdout)[0]
    if actual['Config']['Labels'].get('ontology.task-id') != TASK or actual['Config']['Labels'].get('ontology.run-id') != run_id or actual['State']['Health']['Status'] != 'healthy':
        raise ValueError('MAPPING_SOURCE_OWNER')
    import workflow_environment as environment
    home = next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir())
    product_before_build = build.inputs('wire')
    compiled = run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
                    '/usr/local/share/dotnet/dotnet', 'build', 'backend/tests/OntologyPlatform.ConnectionsTests',
                    '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], ROOT, task=TASK, run_id=run_id,
                   stage='source-bound-build', environment=environment.environment(home), timeout=180, input_key=product_before_build)
    (output / 'source-bound-build.txt').write_bytes(compiled.stdout + compiled.stderr)
    if compiled.returncode or product_before_build != build.inputs('wire'):
        raise ValueError('MAPPING_SOURCE_BUILD_FAILED')
    binaries_path = ROOT / 'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0'
    binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in binaries_path.glob('*.dll')}
    if 'OntologyPlatform.ConnectionsTests.dll' not in binaries:
        raise ValueError('MAPPING_TEST_BUILD_MISSING')
    product = build.inputs('wire')
    drivers = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
        'scripts/maintenance/workflow_m3_mapping.py', 'experiments/g4-m3-mapping-001/compose.yaml', 'experiments/g4-m3-mapping-001/fixture.sql')}
    key = hashlib.sha256(json.dumps([product, binaries, drivers, image_info['Id']], sort_keys=True).encode()).hexdigest()
    name = source['project'] + '-source-test-' + uuid.uuid4().hex[:8]
    record = dict(taskId=TASK, runId=run_id, status='CREATING', name=name, imageId=image_info['Id'], inputKey=product, binaries=binaries, drivers=drivers)
    record_path = output / (name + '.json')
    record_path.write_text(json.dumps(record, indent=2))
    private = ROOT / '.tools/security/g4-m3-mapping-001' / run_id
    env = dict(os.environ, MAPPING_RUN_ID=run_id, MAPPING_PRIVATE_DIR=str(private / 'platform-pg'), MAPPING_SOURCE_PRIVATE_DIR=str(private / 'pg-source'))
    command = ['docker', '--context', context, 'compose', '-f', str(ROOT / 'experiments/g4-m3-mapping-001/compose.yaml'),
               'run', '--no-deps', '--name', name, '--pull', 'never', 'source-test']
    result = run(command, ROOT, task=TASK, run_id=run_id, stage='source-real', environment=env, timeout=45, input_key=key)
    raw = result.stdout + result.stderr
    log_path = output / (name + '.txt')
    log_path.write_bytes(raw)
    inspected = subprocess.run(['docker', '--context', context, 'container', 'inspect', name], capture_output=True, timeout=10)
    if inspected.returncode:
        record.update(status='FAIL', exitCode=result.returncode, receipt=result.receipt, resourceCreated=False,
                      logSha256=hashlib.sha256(raw).hexdigest())
        record_path.write_text(json.dumps(record, indent=2))
        raise ValueError('MAPPING_TEST_RESOURCE_MISSING')
    container = json.loads(inspected.stdout)[0]
    if container['Config']['Labels'].get('ontology.task-id') != TASK or container['Config']['Labels'].get('ontology.run-id') != run_id:
        raise ValueError('MAPPING_TEST_RESOURCE_OWNER')
    record.update(id=container['Id'], state=container['State']['Status'], exitCode=result.returncode, receipt=result.receipt,
                  logSha256=hashlib.sha256(raw).hexdigest(), status='NOT_VERIFIED')
    record_path.write_text(json.dumps(record, indent=2))
    if container['State']['Running']:
        stopped = subprocess.run(['docker', '--context', context, 'stop', '--time', '5', container['Id']], capture_output=True, timeout=10)
        if stopped.returncode:
            raise ValueError('MAPPING_TEST_STOP_FAILED')
    # 无数据卷的已退出测试容器可精确回收；源库与平台库保持KEEP。
    removed = subprocess.run(['docker', '--context', context, 'rm', container['Id']], capture_output=True, timeout=10)
    after = subprocess.run(['docker', '--context', context, 'container', 'inspect', container['Id']], capture_output=True, timeout=10)
    absent = removed.returncode == 0 and after.returncode == 1 and after.stderr.decode().strip() == 'Error response from daemon: No such container: ' + container['Id'] and json.loads(after.stdout) == []
    text = raw.decode(errors='replace')
    passed = re.search(r'(?:成功|Passed|succeeded):\s*(\d+)', text)
    skipped = re.search(r'(?:已跳过|Skipped|skipped):\s*(\d+)', text)
    record.update(cleanup=dict(beforeState=container['State']['Status'], command='docker container rm exact-id', exitCode=removed.returncode, afterAbsent=absent),
                  status='PASS' if result.returncode == 0 and passed and int(passed[1]) == 4 and skipped and int(skipped[1]) == 0 and absent and product == build.inputs('wire') else 'FAIL')
    record_path.write_text(json.dumps(record, indent=2))
    return dict(taskId=TASK, phase='source', status=record['status'], exitCode=result.returncode, cleanupComplete=absent, lifecycle='NOT_RUN')


# 临时回环桥仅来自本任务执行器，不新增项目或依赖，不提供任意目标代理。
LOOPBACK_SOURCE = r'''// <auto-generated/> 本任务隔离运行夹具；不进入产品程序集。
using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
internal static class Program
{
    private static readonly SemaphoreSlim Slots = new(64, 64);
    private static async Task Main()
    {
        await Task.WhenAll(Listen(15680, "keycloak-test", 8080), Listen(15603, "fuseki", 3030),
            Listen(15690, "rustfs", 9000), Listen(15630, "host.docker.internal", 15630));
    }
    private static async Task Listen(int port, string host, int target)
    {
        var listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start(64);
        while (true)
        {
            var client = await listener.AcceptTcpClientAsync();
            if (!await Slots.WaitAsync(0)) { client.Dispose(); continue; }
            _ = Forward(client, host, target);
        }
    }
    private static async Task Forward(TcpClient client, string host, int port)
    {
        using (client)
        using (var upstream = new TcpClient())
        using (var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
        {
            try
            {
                await upstream.ConnectAsync(host, port, deadline.Token);
                await Task.WhenAny(client.GetStream().CopyToAsync(upstream.GetStream(), deadline.Token),
                    upstream.GetStream().CopyToAsync(client.GetStream(), deadline.Token));
            }
            catch (Exception) { /* 固定目标失败关闭，不记录HTTP或认证材料。 */ }
            finally { deadline.Cancel(); Slots.Release(); }
        }
    }
}
'''


def runtime_paths(run_id):
    """固定任务根和已有PG Run，不能通过CLI改路径或读旧私有运行目录。"""
    if run_id != 'mapping-impl-01':
        raise ValueError('MAPPING_RUNTIME_RUN_INVALID')
    output = ROOT / 'artifacts/workflow' / TASK / run_id
    private = ROOT / '.tools/security/g4-m3-mapping-001' / run_id
    for path in (output, private):
        if not path.is_dir() or any(item.is_symlink() for item in (path, *path.parents)):
            raise ValueError('MAPPING_RUNTIME_PATH_INVALID')
    return output, private


def runtime_environment(run_id):
    """只继承已核零下载工具环境；所有Compose插值为本任务固定路径。"""
    import os
    import workflow_environment as environment
    output, private = runtime_paths(run_id)
    home = next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir())
    env = environment.environment(home)
    env.update(MAPPING_RUN_ID=run_id, MAPPING_PRIVATE_DIR=str(private / 'platform-pg'),
               MAPPING_SOURCE_PRIVATE_DIR=str(private / 'pg-source'), MAPPING_RUNTIME_PRIVATE_DIR=str(private / 'runtime'),
               MAPPING_RUNTIME_HELPER_DIR=str(output / 'runtime-helper'), MAPPING_HOST_UID=str(os.getuid()), MAPPING_HOST_GID=str(os.getgid()),
               DOCKER_CONTEXT='desktop-linux')
    return env


def runtime_command(run_id, stage, command, *, timeout=60, offline=False):
    """统一真实exit/timing/input回执，禁止任意下载或恢复命令。"""
    import hashlib
    import workflow_m2_build as build
    from workflow_execution import run
    output, _ = runtime_paths(run_id)
    if any(value in ('pull', 'install', 'restore', '--force', '--force-with-lease') for value in command):
        raise ValueError('MAPPING_RUNTIME_COMMAND_FORBIDDEN')
    key = hashlib.sha256((build.inputs('wire') + Path(__file__).read_text() + (ROOT / 'experiments/g4-m3-mapping-001/compose.yaml').read_text()).encode()).hexdigest()
    if offline:
        command = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)', *command]
    result = run(command, ROOT, task=TASK, run_id=run_id, stage=stage, environment=runtime_environment(run_id), timeout=timeout, input_key=key)
    (output / (stage + '.txt')).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('MAPPING_RUNTIME_COMMAND_FAILED_' + stage)
    return result.stdout


def runtime_snapshot(run_id, stage):
    """创建前后记录准确ID及预算，不输出环境/凭据，不动既有KEEP。"""
    import subprocess
    output, _ = runtime_paths(run_id)
    prefix = ['docker', '--context', 'desktop-linux']
    ids = subprocess.check_output([*prefix, 'ps', '-aq', '--filter', 'label=ontology.task-id=' + TASK,
                                   '--filter', 'label=ontology.run-id=' + run_id], timeout=10).decode().split()
    inspected = json.loads(subprocess.check_output([*prefix, 'inspect', *ids], timeout=10)) if ids else []
    # 失败启动也可能已经创建卷；不能只登记成功容器挂载过的卷。
    volume_names = subprocess.check_output([*prefix, 'volume', 'ls', '-q', '--filter', 'label=ontology.task-id=' + TASK,
                                           '--filter', 'label=ontology.run-id=' + run_id], timeout=10).decode().split()
    volumes = json.loads(subprocess.check_output([*prefix, 'volume', 'inspect', *volume_names], timeout=10)) if volume_names else []
    rows = []
    for item in inspected:
        labels = item['Config']['Labels']
        if labels.get('ontology.task-id') != TASK or labels.get('ontology.run-id') != run_id:
            raise ValueError('MAPPING_RUNTIME_OWNER')
        host = item['HostConfig']
        rows.append(dict(id=item['Id'], service=labels.get('com.docker.compose.service'), image=item['Image'],
                         state=item['State']['Status'], temporaryRole=labels.get('ontology.temporary-role'), memoryBytes=host['Memory'], nanoCpus=host['NanoCpus'], pidsLimit=host['PidsLimit'],
                         readOnly=host['ReadonlyRootfs'], privileged=host['Privileged'],
                         mounts=[{key: mount[key] for key in ('Type', 'Name', 'Source', 'Destination') if key in mount} for mount in item['Mounts']]))
    result = dict(taskId=TASK, runId=run_id, resources=rows, volumes=volumes, status='RECORDED', disposition='KEEP_FOR_CURRENT_IMPLEMENTATION')
    import time
    (output / (stage + '-' + str(time.time_ns()) + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    (output / (stage + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    temporary = [row for row in rows if row.get('temporaryRole') == 'mapping-api-takeover' and row['service'] == 'api']
    allowed = 7 if len(temporary) == 1 and temporary[0]['memoryBytes'] <= 1024**3 and temporary[0]['nanoCpus'] <= 10**9 else 6
    if len(rows) > allowed or sum(row['memoryBytes'] for row in rows) > 8 * 1024**3 or sum(row['nanoCpus'] for row in rows) > 8 * 10**9:
        raise ValueError('MAPPING_RUNTIME_RESOURCE_BUDGET')
    if any(row['privileged'] or not row['readOnly'] or not 0 < row['pidsLimit'] <= 256 or row['memoryBytes'] <= 0 for row in rows):
        raise ValueError('MAPPING_RUNTIME_CONTAINER_BOUNDARY')
    return result


def runtime_prepare(run_id):
    """核本地镜像/能源/消费者，编译零依赖回环夹具并生成新合成凭据；不下载。"""
    import hashlib
    import os
    import secrets
    import subprocess
    import canonical_fuseki
    import host_continuity
    output, private = runtime_paths(run_id)
    structural(ROOT, TASK, 'runtime')
    policy = host_continuity.inspect(task_id=TASK)
    (output / 'runtime-host-preflight.json').write_text(json.dumps(policy, indent=2) + '\n')
    if policy['assurance'] != 'POLICY_READY':
        raise ValueError('MAPPING_RUNTIME_HOST_BLOCKED')
    # 共享镜像的原创建者标签保留，逐输入内容身份核验后只读复用。
    expected = canonical_fuseki.identity(ROOT / 'infra/development/fuseki', 'linux/arm64')
    actual = canonical_fuseki.inspect_image(expected)
    if not actual:
        raise ValueError('MAPPING_CANONICAL_FUSEKI_MISSING')
    canonical_fuseki.validate_image(actual, expected, 'sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c')
    (output / 'runtime-canonical-fuseki.json').write_text(json.dumps(dict(expected=expected, actual=actual), indent=2) + '\n')
    images = ['quay.io/keycloak/keycloak@sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4',
              'rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b',
              'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55']
    receipts = []
    for image in images:
        item = json.loads(subprocess.check_output(['docker', '--context', 'desktop-linux', 'image', 'inspect', image], timeout=10))[0]
        if item['Architecture'] != 'arm64' or item['Os'] != 'linux' or item['Id'] != 'sha256:' + image.split('@sha256:')[1]:
            raise ValueError('MAPPING_RUNTIME_IMAGE_IDENTITY')
        receipts.append(dict(reference=image, id=item['Id'], architecture=item['Architecture'], size=item['Size']))
    (output / 'runtime-images.json').write_text(json.dumps(receipts, indent=2) + '\n')
    # 夹具使用已安装SDK/reference pack直接编译，无项目restore、NuGet或新依赖。
    helper = output / 'runtime-helper'
    helper.mkdir(exist_ok=True)
    source = helper / 'MappingLoopback.cs'
    source.write_text(LOOPBACK_SOURCE)
    sdk = Path('/usr/local/share/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll')
    references = sorted(Path('/usr/local/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
    if not sdk.is_file() or not references:
        raise ValueError('MAPPING_RUNTIME_LOCAL_COMPILER_MISSING')
    runtime_command(run_id, 'runtime-loopback-build', ['/usr/local/share/dotnet/dotnet', str(sdk), '-nologo', '-target:exe', '-nostdlib+',
                    '-out:' + str(helper / 'MappingLoopback.dll'), *['-reference:' + str(path) for path in references], str(source)], offline=True)
    (helper / 'MappingLoopback.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'tfm': 'net10.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': '10.0.13'}}}))
    runtime_command(run_id, 'runtime-api-build', ['/usr/local/share/dotnet/dotnet', 'build', 'backend/src/Hosts/OntologyPlatform.Api',
                    '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], timeout=180, offline=True)
    binaries = ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    (output / 'runtime-build-binding.json').write_text(json.dumps({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in (binaries, helper) for path in folder.iterdir() if path.is_file()}, indent=2) + '\n')
    runtime = private / 'runtime'
    runtime.mkdir(mode=0o700)
    (runtime / 'api').mkdir(mode=0o700)
    def put(path, content):
        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode())
    for name in ('keycloak-password', 's3-access', 's3-secret'):
        put(runtime / name, secrets.token_urlsafe(40))
    put(runtime / 'api/g4-key', secrets.token_bytes(32))
    put(runtime / 'api/ca.crt', (private / 'pg-source/server.crt').read_bytes())
    put(runtime / 'api/platform-ca.crt', (private / 'platform-pg/server.crt').read_bytes())
    identity = dict(taskId=TASK, runId=run_id, publicOrigin='http://localhost:15600', certificatePath=str(runtime / 'api/keyring.pfx'),
                    certificatePassword=secrets.token_urlsafe(40), healthKey=secrets.token_urlsafe(32), realmFile=str(runtime / 'realm.json'))
    put(runtime / 'runtime.json', json.dumps(identity))
    runtime_command(run_id, 'runtime-keyring-create', ['pwsh', '-NoProfile', '-File', 'scripts/acceptance/new-wave2-certificate.ps1',
                    '-RuntimeFile', str(runtime / 'runtime.json')], offline=True)
    return dict(taskId=TASK, status='RUNTIME_PREPARED', downloads=0, secrets='PRIVATE_ONLY', productLifecycle='NOT_RUN')


def runtime_start(run_id, api=False):
    """一次有界启动固定四项服务；API之前必须已经配置新合成realm。"""
    import hashlib
    output, private = runtime_paths(run_id)
    binding = json.loads((output / 'runtime-build-binding.json').read_text())
    if not binding or any(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest for path, digest in binding.items()):
        raise ValueError('MAPPING_RUNTIME_BINARY_DRIFT')
    stage = 'runtime-api' if api else 'runtime-infrastructure'
    before = runtime_snapshot(run_id, stage + '-before')
    services = ['api'] if api else ['keycloak-test', 'fuseki', 'rustfs']
    if any(row['service'] in services for row in before['resources']):
        raise ValueError('MAPPING_RUNTIME_PRESERVE_EXISTING')
    if api and not (private / 'runtime/api/appsettings.json').is_file():
        raise ValueError('MAPPING_RUNTIME_CONFIG_MISSING')
    compose = ['docker', '--context', 'desktop-linux', 'compose', '-f', 'experiments/g4-m3-mapping-001/compose.yaml']
    try:
        runtime_command(run_id, stage + '-start', [*compose, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services], timeout=120)
    finally:
        after = runtime_snapshot(run_id, stage + '-after')
    return dict(taskId=TASK, status='STARTED_NOT_YET_VERIFIED', containers=len(after['resources']), productLifecycle='NOT_RUN')


def runtime_configure(run_id):
    """只新建本任务realm及API配置；正式G3与M3消费者同时开启。"""
    import os
    from workflow_execution import run
    output, private = runtime_paths(run_id)
    runtime = private / 'runtime'
    identity = json.loads((runtime / 'runtime.json').read_text())
    env = runtime_environment(run_id)
    env['WAVE2_KEYCLOAK_ADMIN_PASSWORD'] = (runtime / 'keycloak-password').read_text()
    # helper仅输出合成身份标签；token和新密码仅进程/新私有文件，禁止公开原响应。
    result = run(['python3', '-B', 'infra/security/bootstrap-keycloak.py', '--profile', 'g2', '--keycloak-origin', 'http://localhost:15680',
                  '--public-origin', identity['publicOrigin'], '--runtime-output', str(runtime / 'realm.json')], ROOT,
                 task=TASK, run_id=run_id, stage='runtime-realm-bootstrap', environment=env, timeout=90, input_key='fresh-task-isolated-realm')
    (output / 'runtime-realm-bootstrap.txt').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('MAPPING_RUNTIME_REALM_BOOTSTRAP_FAILED')
    realm = json.loads((runtime / 'realm.json').read_text())
    if not realm['authority'].startswith('http://localhost:15680/realms/g2-'):
        raise ValueError('MAPPING_RUNTIME_REALM_ORIGIN')
    config = {'ConnectionStrings': {'governance': 'Host=platform-pg;Database=mapping_v2;Username=postgres;Password=' + (private / 'platform-pg/password').read_text()
              + ';SSL Mode=VerifyFull;Root Certificate=/private/api/platform-ca.crt;Timeout=5;Command Timeout=5'},
        'Security': {'Authority': realm['authority'], 'ClientId': realm['clientId'], 'ClientSecret': realm['clientSecret'],
                     'PublicOrigin': identity['publicOrigin'], 'KeyRingPath': '/keyring', 'CertificatePath': '/private/api/keyring.pfx',
                     'CertificatePassword': identity['certificatePassword'], 'HealthKey': identity['healthKey']},
        'Web': {'Origin': 'http://127.0.0.1:15630'}, 'G2': {'Enabled': True, 'ApplyMigrations': True},
        'G4': {'Enabled': True, 'ApplyMigrations': True, 'KeyFile': '/private/api/g4-key', 'SourceCaPath': '/private/api/ca.crt',
               'AllowEmptyPublicSchema': True, 'Mapping': {'Enabled': True}},
        'Governance': {'ApplyMigrations': True, 'SeedDevelopmentResources': True},
        'Semantics': {'ValidationOrigin': 'http://127.0.0.1:15603/validation', 'PublishedOrigin': 'http://127.0.0.1:15603/ontology'},
        'Publishing': {'S3Endpoint': 'http://127.0.0.1:15690', 'AccessKey': (runtime / 's3-access').read_text(),
                       'SecretKey': (runtime / 's3-secret').read_text(), 'Bucket': 'g4-m3-mapping-synthetic'},
        'Logging': {'LogLevel': {'Default': 'Warning'}}}
    with os.fdopen(os.open(runtime / 'api/appsettings.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as stream:
        json.dump(config, stream)
    return dict(taskId=TASK, status='RUNTIME_CONFIGURED', secrets='PRIVATE_ONLY', productLifecycle='NOT_RUN')


def runtime_refresh(run_id):
    """只停启本任务准确API，在停止窗口重编译及重新绑定，避免覆盖活跃进程映射的程序集。"""
    import hashlib
    import subprocess
    import workflow_m2_build as build
    output, _ = runtime_paths(run_id)
    before = runtime_snapshot(run_id, 'runtime-refresh-before')
    apis = [row for row in before['resources'] if row['service'] == 'api' and not row.get('temporaryRole')]
    if len(apis) != 1:
        raise ValueError('MAPPING_RUNTIME_API_IDENTITY')
    container = apis[0]['id']
    runtime_command(run_id, 'runtime-api-stop', ['docker', '--context', 'desktop-linux', 'stop', '--time', '10', container], timeout=20)
    stopped = json.loads(subprocess.check_output(['docker', '--context', 'desktop-linux', 'inspect', container], timeout=10))[0]
    if stopped['State']['Running']:
        raise ValueError('MAPPING_RUNTIME_STOP_NOT_CONFIRMED')
    source = build.inputs('wire')
    runtime_command(run_id, 'runtime-api-rebuild', ['/usr/local/share/dotnet/dotnet', 'build', 'backend/src/Hosts/OntologyPlatform.Api',
                    '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], timeout=180, offline=True)
    if source != build.inputs('wire'):
        raise ValueError('MAPPING_RUNTIME_SOURCE_DRIFT')
    folders = [ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0', output / 'runtime-helper']
    (output / 'runtime-build-binding.json').write_text(json.dumps({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in folders for path in folder.iterdir() if path.is_file()}, indent=2) + '\n')
    (output / 'runtime-source-binding.json').write_text(json.dumps(dict(taskId=TASK, runId=run_id, inputKey=source)) + '\n')
    runtime_command(run_id, 'runtime-api-start-existing', ['docker', '--context', 'desktop-linux', 'start', container], timeout=20)
    runtime_snapshot(run_id, 'runtime-refresh-after')
    record_api_start(run_id)
    return dict(taskId=TASK, status='API_REFRESHED_NEEDS_HEALTH_CHECK', containerId=container, lifecycle='NOT_RUN')


def record_api_start(run_id):
    """将准确API容器启动身份绑定到本次磁盘产物，重启后须重新登记。"""
    import hashlib
    import subprocess
    output, _ = runtime_paths(run_id)
    resource = runtime_snapshot(run_id, 'api-process-observe')
    apis = [row['id'] for row in resource['resources'] if row['service'] == 'api' and not row.get('temporaryRole')]
    if len(apis) != 1:
        raise ValueError('MAPPING_API_PROCESS_IDENTITY')
    actual = json.loads(subprocess.check_output(['docker', '--context', 'desktop-linux', 'inspect', apis[0]], timeout=10))[0]
    if not actual['State']['Running'] or actual['Config']['Labels'].get('ontology.task-id') != TASK or actual['Config']['Labels'].get('ontology.run-id') != run_id:
        raise ValueError('MAPPING_API_PROCESS_OWNER')
    binary = json.loads((output / 'runtime-build-binding.json').read_text())
    source = json.loads((output / 'runtime-source-binding.json').read_text())
    row = dict(taskId=TASK, runId=run_id, containerId=apis[0], startedAt=actual['State']['StartedAt'], imageId=actual['Image'],
               backend=source['inputKey'], apiOutput=hashlib.sha256(json.dumps(binary, sort_keys=True).encode()).hexdigest(),
               platformDatabase=json.loads((output / 'platform-resources.json').read_text())['databaseName'])
    import time
    path = output / ('api-process-' + str(time.time_ns()) + '.json')
    path.write_text(json.dumps(row, indent=2) + '\n')
    (output / 'api-process-current.json').write_text(json.dumps(dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())) + '\n')
    return row


def demand_process_build(record, current):
    """磁盘新构建不能替旧进程背书；只有启动时同一产物身份才可消费。"""
    if record != current:
        raise ValueError('MAPPING_PROCESS_BUILD_DRIFT')


def runtime_processes(run_id, backend, api_output, web):
    """只读核实准确API启动时间及Web端口拥有者，不读取进程环境或认证材料。"""
    import hashlib
    import subprocess
    from workflow_execution import ordinary
    output, _ = runtime_paths(run_id)
    def record(name):
        pointer = json.loads(ordinary(output / (name + '-current.json')).read_text())
        path = ordinary(ROOT / pointer['path'])
        if path.parent != output or hashlib.sha256(path.read_bytes()).hexdigest() != pointer['sha256']:
            raise ValueError('MAPPING_PROCESS_RECORD')
        return json.loads(path.read_text())
    api = record('api-process')
    actual = json.loads(subprocess.check_output(['docker', '--context', 'desktop-linux', 'inspect', api['containerId']], timeout=10))[0]
    if not actual['State']['Running'] or actual['State']['StartedAt'] != api['startedAt'] or actual['Image'] != api['imageId'] or actual['Config']['Labels'].get('ontology.task-id') != TASK or actual['Config']['Labels'].get('ontology.run-id') != run_id:
        raise ValueError('MAPPING_API_PROCESS_DRIFT')
    demand_process_build({key: api[key] for key in ('backend', 'apiOutput', 'platformDatabase')}, dict(backend=backend, apiOutput=api_output,
        platformDatabase=json.loads((output / 'platform-resources.json').read_text())['databaseName']))
    host = record('web-process')
    owners = subprocess.check_output(['lsof', '-nP', '-t', '-iTCP:15630', '-sTCP:LISTEN'], timeout=10).decode().split()
    if owners != [str(host['pid'])] or host['taskId'] != TASK or host['runId'] != run_id:
        raise ValueError('MAPPING_WEB_PROCESS_OWNER')
    started = subprocess.check_output(['ps', '-p', str(host['pid']), '-o', 'lstart='], timeout=10, env=dict(__import__('os').environ, LC_ALL='C')).decode().strip()
    cwd = subprocess.check_output(['lsof', '-a', '-p', str(host['pid']), '-d', 'cwd', '-Fn'], timeout=10).decode()
    if started != host['processStartedAt'] or '\nn' + str(ROOT) + '\n' not in cwd:
        raise ValueError('MAPPING_WEB_PROCESS_DRIFT')
    demand_process_build(host['build'], web)
    return dict(apiStartedAt=api['startedAt'], apiId=api['containerId'], webPid=host['pid'], webStartedAt=started)


def runtime_binding(run_id):
    """浏览器前后重核当前源码、实际构建输出和固定驱动；不接受只有PASS的摘要。"""
    import hashlib
    import workflow_m2_build as build
    output, _ = runtime_paths(run_id)
    source = json.loads((output / 'runtime-source-binding.json').read_text())
    if source.get('taskId') != TASK or source.get('runId') != run_id or source.get('inputKey') != build.inputs('wire'):
        raise ValueError('MAPPING_RUNTIME_SOURCE_DRIFT')
    binary = json.loads((output / 'runtime-build-binding.json').read_text())
    if not binary or any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest for name, digest in binary.items()):
        raise ValueError('MAPPING_RUNTIME_BINARY_DRIFT')
    drivers = ['scripts/maintenance/workflow_m3_mapping.py', 'scripts/maintenance/workflow-m3-mapping.mjs',
               'experiments/g4-m3-mapping-001/grant-fixture.py', 'experiments/g4-m3-mapping-001/fixture.sql',
               'experiments/g4-m3-mapping-001/compose.yaml', 'samples/g2/ontology.ttl', 'samples/g2/shapes.ttl',
               'samples/g2/vocabulary.ttl', 'samples/g2/data.ttl', 'samples/g3-m3/units.ttl']
    web = build.validate('web', TASK)
    api_output = hashlib.sha256(json.dumps(binary, sort_keys=True).encode()).hexdigest()
    processes = runtime_processes(run_id, source['inputKey'], api_output, web)
    return dict(taskId=TASK, runId=run_id, status='BOUND', backend=source['inputKey'],
                platformDatabase=json.loads((output / 'platform-resources.json').read_text())['databaseName'],
                apiOutput=api_output, web=web, processesVerified=bool(processes),
                drivers={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in drivers})


def local_tests(run_id):
    """定向本地合同/语义/UI验收，全部离线，输出原命令与当前输入绑定。"""
    import hashlib
    import uuid
    import workflow_environment as environment
    import workflow_m2_build as build
    from workflow_execution import run
    from workflow_m2_evidence import mtp
    from workflow_evidence import machine
    output, _ = runtime_paths(run_id)
    directory = output / ('local-' + uuid.uuid4().hex)
    directory.mkdir()
    env = environment.environment(next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir()))
    initial = dict(backend=build.inputs('wire'), web=build.inputs('web'))
    rows = []
    profile = '(version 1) (allow default) (deny network*)'

    def execute(stage, command, kind, key, cwd=ROOT, timeout=120):
        result = run(['/usr/bin/sandbox-exec', '-p', profile, *command], cwd, task=TASK, run_id=run_id,
                     stage=stage, environment=env, timeout=timeout, input_key=key)
        raw = result.stdout + result.stderr
        path = directory / (stage + '.txt')
        path.write_bytes(raw)
        count = mtp(raw, 1) if kind == 'mtp' and result.returncode == 0 else 0
        rows.append(dict(stage=stage, kind=kind, exitCode=result.returncode, tests=count, inputKey=key,
                         path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), receipt=result.receipt))
        if result.returncode:
            raise ValueError('MAPPING_LOCAL_FAILED:' + stage)
        return rows[-1]

    result = dict(taskId=TASK, runId=run_id, status='FAIL', inputs=initial, rows=rows)
    try:
        for target, assembly, selector in [('wire', 'G2ContractTests', 'G4MappingWireTests'), ('semantics', 'ConnectionsTests', 'G4MappingTests')]:
            project = 'backend/tests/OntologyPlatform.' + assembly
            execute(target + '-build', ['/usr/local/share/dotnet/dotnet', 'build', project, '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], 'build', initial['backend'], timeout=180)
            binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / project / 'bin/Debug/net10.0').glob('*.dll')}
            key = hashlib.sha256(json.dumps([initial['backend'], binaries], sort_keys=True).encode()).hexdigest()
            tested = execute(target, ['/usr/local/share/dotnet/dotnet', project + '/bin/Debug/net10.0/OntologyPlatform.' + assembly + '.dll', '--filter', 'FullyQualifiedName~' + selector,
                             '--timeout', '20s', '--zero-tests-policy', 'strict'], 'mtp', key, timeout=30)
            tested['binaries'] = binaries
        web = ROOT / 'apps/web'
        config = directory / 'vitest.config.mjs'
        report = directory / 'vitest-report.json'
        config.write_text('export default ' + json.dumps(dict(root=str(web), cacheDir=str(output / 'vite-cache'),
            test=dict(environment='node', include=['src/features/mappings/mappings.test.ts'], reporters=['default', 'json'],
                      outputFile=dict(json=str(report)), fsModuleCachePath=str(output / 'vite-modules')))) + ';\n')
        execute('typecheck', [str(web / 'node_modules/.bin/tsc'), '--noEmit'], 'check', initial['web'], web)
        execute('lint', [str(web / 'node_modules/.bin/eslint'), 'src/features/mappings', 'src/app/data/mappings', 'src/app/data/mapping-proposals',
                        'src/app/data/mapping-releases', 'src/features/connections/catalog.tsx'], 'check', initial['web'], web)
        row = execute('ui', [str(web / 'node_modules/.bin/vitest'), 'run', '--config', str(config), '--configLoader', 'native'], 'vitest', initial['web'], web)
        row.update(tests=machine(report.read_bytes(), 'vitest-json'), machinePath=str(report.relative_to(ROOT)), machineSha256=hashlib.sha256(report.read_bytes()).hexdigest())
        if initial != dict(backend=build.inputs('wire'), web=build.inputs('web')):
            raise ValueError('MAPPING_LOCAL_INPUT_DRIFT')
        result['status'] = 'PASS'
    finally:
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return dict(taskId=TASK, status=result['status'], report=str((directory / 'result.json').relative_to(ROOT)), tests=sum(row['tests'] for row in rows))


def demand_compatibility_reader(reader, binaries, manifest_hash):
    """逐成员核实际加载依赖和实际Manifest，入口DLL相同不能替宽松旧依赖背书。"""
    import hashlib
    from workflow_execution import ordinary
    actual = {path.name: hashlib.sha256(ordinary(path).read_bytes()).hexdigest() for path in reader.glob('*.dll')}
    manifest = ordinary(reader.parent / 'actual-v2-manifest.json')
    if actual != binaries or hashlib.sha256(manifest.read_bytes()).hexdigest() != manifest_hash:
        raise ValueError('MAPPING_COMPATIBILITY_READER_DRIFT')


def compatibility_tests(run_id):
    """只读历史公开Manifest及当前隔离库最小旧Run消费者；不复跑历史全链。"""
    import base64
    import hashlib
    import shutil
    import uuid
    import workflow_environment as environment
    import workflow_m2_build as build
    from workflow_execution import run
    from workflow_m2_evidence import mtp
    output, private = runtime_paths(run_id)
    directory = output / ('compatibility-' + uuid.uuid4().hex)
    directory.mkdir()
    source = build.inputs('wire')
    history = ROOT / 'docs/evidence/G3-M1-001/master/full-gate3-v2-manifest.base64.json'
    envelope = json.loads(history.read_text())
    original = base64.b64decode(envelope['dataBase64'], validate=True)
    if len(original) != 3160 or hashlib.sha256(original).hexdigest() != '750e626576e22b2eaff8f3abde0304dc44a7df73f60220058e409f2c653e83aa':
        raise ValueError('MAPPING_HISTORICAL_MANIFEST_IDENTITY')
    (directory / 'actual-v2-manifest.json').write_bytes(original)
    env = environment.environment(next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir()))
    database = json.loads((output / 'platform-resources.json').read_text())['databaseName']
    if database != 'mapping_v3':
        raise ValueError('MAPPING_COMPATIBILITY_DATABASE')
    env.update(G2_AI_PG='Host=127.0.0.1;Port=15463;Database=' + database + ';Username=postgres;Password=' + (private / 'platform-pg/password').read_text() + ';SSL Mode=VerifyFull;Root Certificate=' + str(private / 'platform-pg/server.crt') + ';Timeout=5;Command Timeout=5',
               G2_AI_JENA='http://127.0.0.1:15603', G2_AI_S3='http://127.0.0.1:15690', G2_AI_SAMPLES=str(ROOT / 'samples/g2'),
               RUSTFS_ACCESS_KEY=(private / 'runtime/s3-access').read_text(), RUSTFS_SECRET_KEY=(private / 'runtime/s3-secret').read_text())
    rows = []
    result = dict(taskId=TASK, runId=run_id, status='FAIL', inputKey=source, historyPath=str(history.relative_to(ROOT)), historySha256=hashlib.sha256(history.read_bytes()).hexdigest(), originalSha256=hashlib.sha256(original).hexdigest(), rows=rows)
    try:
        for assembly, name, selector in [('G2ContractTests', 'historical-manifest', 'CompatibilityBinaryReadsActualV2Manifest'),
                                         ('AgentTests', 'old-run', 'OldRunKeepsSnapshotAcrossNewPublishAndRollback')]:
            project = 'backend/tests/OntologyPlatform.' + assembly
            runtime_command(run_id, name + '-build', ['/usr/local/share/dotnet/dotnet', 'build', project, '--no-restore', '--disable-build-servers', '-m:1', '-v:q'], timeout=180, offline=True)
            binary_root = ROOT / project / 'bin/Debug/net10.0'
            binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in binary_root.glob('*.dll')}
            if name == 'historical-manifest':
                reader = directory / 'reader'
                shutil.copytree(binary_root, reader)
                demand_compatibility_reader(reader, binaries, result['originalSha256'])
                dll = reader / ('OntologyPlatform.' + assembly + '.dll')
                profile = '(version 1) (allow default) (deny network*)'
            else:
                dll = binary_root / ('OntologyPlatform.' + assembly + '.dll')
                profile = '(version 1) (allow default) (deny network-outbound) (allow network-outbound (remote ip "localhost:15463") (remote ip "localhost:15603") (remote ip "localhost:15690"))'
            key = hashlib.sha256(json.dumps([source, binaries, result['historySha256']], sort_keys=True).encode()).hexdigest()
            command = ['/usr/bin/sandbox-exec', '-p', profile, '/usr/local/share/dotnet/dotnet', str(dll), '--filter', 'FullyQualifiedName~' + selector, '--timeout', '60s', '--zero-tests-policy', 'strict']
            executed = run(command, ROOT, task=TASK, run_id=run_id, stage='compatibility-' + name, environment=env, timeout=90, input_key=key)
            if name == 'historical-manifest':
                demand_compatibility_reader(reader, binaries, result['originalSha256'])
            raw = executed.stdout + executed.stderr
            path = directory / (name + '.txt'); path.write_bytes(raw)
            rows.append(dict(name=name, project=project, binaries=binaries, command=command, fingerprint=key, receipt=executed.receipt, path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), tests=mtp(raw, 1) if executed.returncode == 0 else 0))
            if executed.returncode or rows[-1]['tests'] != 1:
                raise ValueError('MAPPING_COMPATIBILITY_FAILED:' + name)
        if source != build.inputs('wire') or result['historySha256'] != hashlib.sha256(history.read_bytes()).hexdigest():
            raise ValueError('MAPPING_COMPATIBILITY_INPUT_DRIFT')
        result['status'] = 'PASS'
    finally:
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return dict(taskId=TASK, status=result['status'], report=str((directory / 'result.json').relative_to(ROOT)), tests=sum(row['tests'] for row in rows))


def demand_command_identity(receipt, stage, fingerprint, command, cwd):
    """命令原件必须绑定准确输入和执行目标，摘要不能替旧命令自报当前成功。"""
    from workflow_execution import encoded, sha
    if receipt.get('stage') != stage or receipt.get('inputFingerprint') != fingerprint or receipt.get('cwd') != str(cwd) or receipt.get('commandSummary', {}).get('sha256') != sha(encoded(command)):
        raise ValueError('MAPPING_COMMAND_IDENTITY')


def demand_browser_coverage(mode, checks):
    """必需正反路径不能用一个普通PASS或删去关键断言替代。"""
    required = {
        'lifecycle': {'published_readback_original_catalog_differs_from_binding', 'first_definition_original_catalog_preserved', 'second_definition_original_catalog_preserved', 'rollback_definition_original_catalog_preserved'},
        'worker': {'cancel_fence_increased', 'takeover_new_fence_same_job_completed', 'primary_restarted_after_secondary_completed', 'takeover_seven_stages_pass', 'worker_fixture_takeover-finish'},
        'permissions': {'same_subject_other_session_rejected_explicitly', 'concurrent_distinct_subject_one_winner', 'cas_exactly_one_business_commit', 'ai_on_explicitly_disabled', 'source_comment_cannot_change_candidates_or_policy', 'changed_subject_no_previous_definition'},
        'authority': {'approved_expired_no_business_commit', 'approved_submitter_logout_no_business_commit', 'approved_reviewer_logout_no_business_commit', 'reviewer-revoke_no_business_commit', 'reviewer-expire_no_business_commit', 'reviewer-scope_no_business_commit', 'approved_source_schema_drift_failed_check_retained', 'approved_source_unavailable_failed_check_retained', 'expired_ui_cannot_activate', 'partial_failed_check_never_shown_as_pass', 'expired_projection_in_correct_filter', 'expired_projection_absent_from_approved', 'stale_projection_in_correct_filter', 'stale_projection_absent_from_approved'},
        'rotation': {'actual_new_secret_version', 'rotated_approval_no_commit', 'rollback_new_secret_binding', 'commit_succeeded_before_response_drop', 'actual_response_discarded', 'lost_response_original_receipt', 'lost_response_single_commit_audit', 'rollback_immutable_old_manifest', 'g3_fixed_original_manifest_preserved'},
        'visual': {'actual_theme_switch', 'theme_survives_reload', 'keyboard_focus_visible', 'mobile_sidebar_closed', 'mobile_main_visible'}
    }.get(mode, set())
    if not required.issubset({row.get('name') for row in checks if row.get('status') == 'PASS'}):
        raise ValueError('MAPPING_BROWSER_REQUIRED_COVERAGE:' + mode)


def qualify(run_id, gate, input_key):
    """重开原始命令与报告；未覆盖、旧输入、跳过、无实际计数一律拒绝产品门禁。"""
    import hashlib
    import platform
    import workflow as workflow
    import workflow_environment as environment
    import workflow_m2_build as build
    from workflow_execution import ordinary
    from workflow_m2_evidence import mtp
    from workflow_evidence import machine
    from workflow_web_cache import inspect, binding
    if gate not in ('environment', 'contract', 'backend', 'web', 'interaction') or input_key != workflow.input_key(ROOT, gate):
        raise ValueError('MAPPING_GATE_INPUT_INVALID')
    structural(ROOT, TASK)
    output, _ = runtime_paths(run_id)
    index = json.loads((output / 'product-proof-index.json').read_text())
    if index.get('taskId') != TASK or index.get('runId') != run_id or index.get('inputKeys', {}).get(gate) != input_key:
        raise ValueError('MAPPING_PROOF_INDEX_STALE')
    base = ROOT / 'artifacts/workflow' / TASK
    references = []

    def read(path, expected=None):
        path = ordinary(ROOT / path)
        if not path.is_relative_to(base) or '..' in path.parts:
            raise ValueError('MAPPING_PROOF_PATH')
        raw = path.read_bytes()
        if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('MAPPING_PROOF_HASH')
        return raw

    def proof(name):
        reference = index['proofs'][name]
        raw = read(reference['path'], reference['sha256'])
        row = json.loads(raw)
        if row.get('taskId') != TASK:
            raise ValueError('MAPPING_PROOF_TASK')
        references.append(reference)
        return row

    def command_receipt(row, stage, fingerprint, command, cwd=ROOT):
        receipt = row['receipt']
        path = base / 'commands' / receipt['runId'] / receipt['commandId'] / 'receipt.json'
        original = json.loads(read(path))
        demand_command_identity(receipt, stage, fingerprint, command, cwd)
        if original != receipt or receipt.get('classification') != 'SUCCESS' or receipt.get('exitCode') != 0 or not receipt.get('started'):
            raise ValueError('MAPPING_COMMAND_NOT_SUCCESS')
        raw = b''.join(read(receipt[stream]['path'], receipt[stream]['sha256']) for stream in ('stdout', 'stderr'))
        return raw

    count = 0
    if gate == 'environment':
        row = proof('environment')
        if row.get('status') != 'DEPENDENCIES_READY' or row.get('worktree') != str(ROOT) or any(row.get(key) != 0 for key in ('downloads', 'sdkDownloads', 'runtimeCredentialsCopied')):
            raise ValueError('MAPPING_ENVIRONMENT_ORIGINAL')
        packages, projects, files = environment.locks(ROOT)
        approved = environment.approved_archives(ROOT, TASK, packages)
        admission = environment.git_json(ROOT, environment.BASE, environment.ADMISSION)
        for tool in admission['files']:
            if environment.digest(ordinary(tool['path']).read_bytes()) != tool['sha256']:
                raise ValueError('MAPPING_TOOL_DRIFT')
        identity = environment.identities(dict(platform=platform.system()+'-'+platform.machine(), osVersion=platform.mac_ver()[0], files=files,
            tools=admission['files'], sdk=environment.SDK_ARCHIVES, archives={key: value['archiveSha256'] for key, value in approved.items()}), ROOT)
        if any(row[key] != identity[key] for key in ('contentKey', 'workspaceKey')):
            raise ValueError('MAPPING_ENVIRONMENT_INPUT_DRIFT')
        home = base / 'environment' / identity['contentKey']
        environment.verify_assets(ROOT, home, projects, packages, approved)
        rows, shims, links = inspect(ROOT, Path(admission['playwrightAndAjv']['store']), row['node'], environment)
        marker = json.loads(environment.web_marker(ROOT, home, admission).read_text())
        if marker['binding'] != binding(ROOT, rows, shims, links, environment):
            raise ValueError('MAPPING_WEB_CACHE_DRIFT')
        count = 1
    else:
        local = proof('local')
        if local.get('status') != 'PASS' or local.get('inputs') != dict(backend=build.inputs('wire'), web=build.inputs('web')):
            raise ValueError('MAPPING_LOCAL_INPUT_DRIFT')
        stages = {row['stage']: row for row in local['rows']}
        if set(stages) != {'wire-build', 'wire', 'semantics-build', 'semantics', 'typecheck', 'lint', 'ui'}:
            raise ValueError('MAPPING_LOCAL_COVERAGE')
        for name, row in stages.items():
            project = 'backend/tests/OntologyPlatform.' + ('G2ContractTests' if name.startswith('wire') else 'ConnectionsTests')
            sandbox = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)']
            fingerprint = local['inputs']['web' if name in ('ui', 'lint', 'typecheck') else 'backend']
            cwd = ROOT / 'apps/web' if name in ('ui', 'lint', 'typecheck') else ROOT
            if name.endswith('-build'):
                command = ['/usr/local/share/dotnet/dotnet', 'build', project, '--no-restore', '--disable-build-servers', '-m:1', '-v:q']
            elif name in ('wire', 'semantics'):
                assembly = 'G2ContractTests' if name == 'wire' else 'ConnectionsTests'
                command = ['/usr/local/share/dotnet/dotnet', project + '/bin/Debug/net10.0/OntologyPlatform.' + assembly + '.dll', '--filter',
                           'FullyQualifiedName~' + ('G4MappingWireTests' if name == 'wire' else 'G4MappingTests'), '--timeout', '20s', '--zero-tests-policy', 'strict']
            elif name == 'typecheck':
                command = [str(cwd / 'node_modules/.bin/tsc'), '--noEmit']
            elif name == 'lint':
                command = [str(cwd / 'node_modules/.bin/eslint'), 'src/features/mappings', 'src/app/data/mappings', 'src/app/data/mapping-proposals', 'src/app/data/mapping-releases', 'src/features/connections/catalog.tsx']
            else:
                command = [str(cwd / 'node_modules/.bin/vitest'), 'run', '--config', str(ROOT / Path(row['machinePath']).parent / 'vitest.config.mjs'), '--configLoader', 'native']
            if name in ('wire', 'semantics'):
                binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / project / 'bin/Debug/net10.0').glob('*.dll')}
                if row.get('binaries') != binaries:
                    raise ValueError('MAPPING_LOCAL_BINARY_DRIFT')
                fingerprint = hashlib.sha256(json.dumps([local['inputs']['backend'], binaries], sort_keys=True).encode()).hexdigest()
            raw = command_receipt(row, name, fingerprint, sandbox + command, cwd)
            if raw != read(row['path'], row['sha256']) or row['exitCode'] != 0:
                raise ValueError('MAPPING_LOCAL_LOG')
            if name in ('wire', 'semantics'):
                count += mtp(raw, 6 if name == 'wire' else 14)
            elif name == 'ui':
                count += machine(read(row['machinePath'], row['machineSha256']), 'vitest-json', 11)
        if gate in ('contract', 'backend', 'interaction'):
            compatibility = proof('compatibility')
            if compatibility.get('status') != 'PASS' or compatibility.get('inputKey') != build.inputs('wire') or compatibility.get('originalSha256') != '750e626576e22b2eaff8f3abde0304dc44a7df73f60220058e409f2c653e83aa':
                raise ValueError('MAPPING_COMPATIBILITY_DRIFT')
            if hashlib.sha256((ROOT / compatibility['historyPath']).read_bytes()).hexdigest() != compatibility['historySha256'] or {row['name'] for row in compatibility['rows']} != {'historical-manifest', 'old-run'}:
                raise ValueError('MAPPING_COMPATIBILITY_COVERAGE')
            for item in compatibility['rows']:
                binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / item['project'] / 'bin/Debug/net10.0').glob('*.dll')}
                key = hashlib.sha256(json.dumps([build.inputs('wire'), binaries, compatibility['historySha256']], sort_keys=True).encode()).hexdigest()
                if item['binaries'] != binaries or item['fingerprint'] != key:
                    raise ValueError('MAPPING_COMPATIBILITY_BINARY_DRIFT')
                selector = 'CompatibilityBinaryReadsActualV2Manifest' if item['name'] == 'historical-manifest' else 'OldRunKeepsSnapshotAcrossNewPublishAndRollback'
                expected_dll = ROOT / Path(index['proofs']['compatibility']['path']).parent / 'reader/OntologyPlatform.G2ContractTests.dll' if item['name'] == 'historical-manifest' else ROOT / 'backend/tests/OntologyPlatform.AgentTests/bin/Debug/net10.0/OntologyPlatform.AgentTests.dll'
                profile = '(version 1) (allow default) (deny network*)' if item['name'] == 'historical-manifest' else '(version 1) (allow default) (deny network-outbound) (allow network-outbound (remote ip "localhost:15463") (remote ip "localhost:15603") (remote ip "localhost:15690"))'
                command = ['/usr/bin/sandbox-exec', '-p', profile, '/usr/local/share/dotnet/dotnet', str(expected_dll), '--filter', 'FullyQualifiedName~' + selector, '--timeout', '60s', '--zero-tests-policy', 'strict']
                if item['name'] == 'historical-manifest':
                    demand_compatibility_reader(expected_dll.parent, binaries, compatibility['originalSha256'])
                raw = command_receipt(item, 'compatibility-' + item['name'], key, command)
                if raw != read(item['path'], item['sha256']) or hashlib.sha256(expected_dll.read_bytes()).hexdigest() != binaries[expected_dll.name]:
                    raise ValueError('MAPPING_COMPATIBILITY_ORIGINAL')
                count += mtp(raw, 1)
        if gate in ('backend', 'interaction'):
            for name in ('persistence', 'source'):
                row = proof(name)
                project = 'SecurityTests' if name == 'persistence' else 'ConnectionsTests'
                binaries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / ('backend/tests/OntologyPlatform.' + project + '/bin/Debug/net10.0')).glob('*.dll')}
                if row['binaries'] != binaries:
                    raise ValueError('MAPPING_TEST_BINARY_DRIFT')
                if name == 'persistence':
                    fingerprint = hashlib.sha256(json.dumps([build.inputs('wire'), binaries, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        hashlib.sha256((ROOT / 'experiments/g4-m3-mapping-001/compose.yaml').read_bytes()).hexdigest()], sort_keys=True).encode()).hexdigest()
                    command = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network-outbound) (allow network-outbound (remote ip "localhost:15463"))',
                        '/usr/local/share/dotnet/dotnet', str(ROOT / 'backend/tests/OntologyPlatform.SecurityTests/bin/Debug/net10.0/OntologyPlatform.SecurityTests.dll'),
                        '--filter', 'FullyQualifiedName~G4MappingAuthorizationTests', '--timeout', '30s', '--zero-tests-policy', 'strict']
                else:
                    drivers = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in ('scripts/maintenance/workflow_m3_mapping.py', 'experiments/g4-m3-mapping-001/compose.yaml', 'experiments/g4-m3-mapping-001/fixture.sql')}
                    if row['drivers'] != drivers or row['imageId'] != 'sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55':
                        raise ValueError('MAPPING_SOURCE_DRIVER_DRIFT')
                    fingerprint = hashlib.sha256(json.dumps([build.inputs('wire'), binaries, drivers, row['imageId']], sort_keys=True).encode()).hexdigest()
                    command = ['docker', '--context', 'desktop-linux', 'compose', '-f', str(ROOT / 'experiments/g4-m3-mapping-001/compose.yaml'), 'run', '--no-deps', '--name', row['name'], '--pull', 'never', 'source-test']
                raw = command_receipt(row, 'persistence-real' if name == 'persistence' else 'source-real', fingerprint, command)
                if row.get('status') != 'PASS' or row.get('exitCode') != 0 or row.get('inputKey') != build.inputs('wire') or hashlib.sha256(raw).hexdigest() != row['logSha256']:
                    raise ValueError('MAPPING_REAL_TEST_DRIFT')
                if name == 'source' and row.get('cleanup', {}).get('afterAbsent') is not True:
                    raise ValueError('MAPPING_SOURCE_TEST_NOT_CLOSED')
                count += mtp(raw, 4)
        modes = {'contract': [], 'backend': ['semantics', 'faults', 'worker', 'negative', 'permissions', 'authority', 'rotation'],
                 'web': ['recovery', 'visual'], 'interaction': ['lifecycle', 'faults', 'recovery', 'visual', 'semantics', 'worker', 'negative', 'permissions', 'authority', 'rotation']}[gate]
        current = runtime_binding(run_id) if modes else None
        for mode in modes:
            wrapper = proof('browser-' + mode)
            command = ['/opt/homebrew/opt/node@24/bin/node', 'scripts/maintenance/workflow-m3-mapping.mjs', '--task', TASK, '--run-id', run_id, '--mode', mode]
            raw = command_receipt(wrapper, 'browser-' + mode, hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest(), command)
            summary = json.loads(raw)
            if summary.get('status') != 'PASS' or summary.get('report') != str(ROOT / wrapper['reportPath']):
                raise ValueError('MAPPING_BROWSER_REPORT_SUBSTITUTED')
            if wrapper.get('status') != 'PASS' or wrapper.get('exitCode') != 0 or wrapper.get('mode') != mode:
                raise ValueError('MAPPING_BROWSER_COMMAND_FAILED')
            row = json.loads(read(wrapper['reportPath'], wrapper['reportSha256']))
            checks = row.get('checks', [])
            if row.get('status') != 'PASS' or row.get('mode') != mode or row.get('runId') != run_id or row.get('inputsUnchanged') is not True or row.get('inputBinding') != current:
                raise ValueError('MAPPING_BROWSER_DRIFT:' + mode)
            if not checks or any(item.get('status') != 'PASS' for item in checks) or not row.get('http'):
                raise ValueError('MAPPING_BROWSER_ZERO_OR_FAILED:' + mode)
            if mode == 'semantics':
                expected = {'one_to_many_exact_units_json', 'many_to_many', 'wrong_formal_endpoints', 'unknown_actual_unit', 'precision_loss',
                            'json_missing', 'json_empty_preserved', 'json_null_rejected', 'json_null_preserved', 'json_zero_not_string', 'json_missing_not_null', 'fanout_no_truncation', 'restored_valid'}
                if {item['label'] for item in row.get('semanticCases', [])} != expected:
                    raise ValueError('MAPPING_SEMANTIC_COVERAGE')
            demand_browser_coverage(mode, checks)
            count += len(checks)
    return dict(taskId=TASK, runId=run_id, gate=gate, status='PASS', executionMode='REUSED', qualificationMode='FRESH',
                inputKey=input_key, tests=count, skipped=0, originals=references, ci='NOT_RUN')


def browser_tests(run_id, mode):
    """真实浏览器通过公共执行器记录实际exitCode，报告PASS不能替代子进程原件。"""
    import hashlib
    import workflow_environment as environment
    from workflow_execution import run
    if mode not in ('provision', 'lifecycle', 'faults', 'recovery', 'visual', 'semantics', 'worker', 'negative', 'permissions', 'authority', 'rotation'):
        raise ValueError('MAPPING_BROWSER_MODE')
    output, _ = runtime_paths(run_id)
    current = runtime_binding(run_id)
    env = environment.environment(next((ROOT / 'artifacts/workflow' / TASK / 'environment').iterdir()))
    env['NODE_OPTIONS'] = '--max-old-space-size=1024'
    command = ['/opt/homebrew/opt/node@24/bin/node', 'scripts/maintenance/workflow-m3-mapping.mjs', '--task', TASK, '--run-id', run_id, '--mode', mode]
    result = run(command, ROOT, task=TASK, run_id=run_id, stage='browser-' + mode, environment=env, timeout=180,
                 input_key=hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest())
    summary = json.loads(result.stdout)
    path = Path(summary['report'])
    if path.parent != output or path.is_symlink() or not path.name.startswith('browser-' + mode + '-'):
        raise ValueError('MAPPING_BROWSER_REPORT_PATH')
    row = dict(taskId=TASK, runId=run_id, mode=mode, status='PASS' if result.returncode == 0 and summary['status'] == 'PASS' else 'FAIL',
               exitCode=result.returncode, receipt=result.receipt, reportPath=str(path.relative_to(ROOT)), reportSha256=hashlib.sha256(path.read_bytes()).hexdigest())
    record = output / ('browser-command-' + result.receipt['commandId'] + '.json')
    record.write_text(json.dumps(row, indent=2) + '\n')
    return dict(taskId=TASK, status=row['status'], exitCode=result.returncode, report=str(record.relative_to(ROOT)), browserReport=summary['report'])


def runtime_new_database(run_id):
    """保留开发失败原库，为最终当前输入链创建本任务新空库；绝不删除或恢复旧数据。"""
    import os
    import subprocess
    import time
    output, private = runtime_paths(run_id)
    resource = json.loads((output / 'platform-resources.json').read_text())
    if resource.get('taskId') != TASK or resource.get('runId') != run_id or resource.get('databaseName') != 'mapping_v2':
        raise ValueError('MAPPING_NEW_DATABASE_PRECONDITION')
    before = runtime_snapshot(run_id, 'new-database-before')
    api = [row['id'] for row in before['resources'] if row['service'] == 'api' and not row.get('temporaryRole')]
    platform_ids = [row['id'] for row in resource['resources'] if row['kind'] == 'container']
    if len(api) != 1 or len(platform_ids) != 1:
        raise ValueError('MAPPING_DATABASE_RESOURCE_IDENTITY')
    docker = ['docker', '--context', 'desktop-linux']
    actual = json.loads(subprocess.check_output([*docker, 'inspect', platform_ids[0]], timeout=10))[0]
    if actual['Config']['Labels'].get('ontology.task-id') != TASK or actual['Config']['Labels'].get('ontology.run-id') != run_id:
        raise ValueError('MAPPING_DATABASE_OWNER')
    check = subprocess.check_output([*docker, 'exec', platform_ids[0], 'psql', '-U', 'postgres', '-d', 'postgres', '-qAt', '-c', "SELECT count(*) FROM pg_database WHERE datname='mapping_v3'"], timeout=10).decode().strip()
    if check != '0':
        raise ValueError('MAPPING_PRESERVE_EXISTING_DATABASE')
    runtime_command(run_id, 'new-database-api-stop', [*docker, 'stop', '--time', '10', api[0]], timeout=20)
    stopped = json.loads(subprocess.check_output([*docker, 'inspect', api[0]], timeout=10))[0]
    if stopped['State']['Running']:
        raise ValueError('MAPPING_DATABASE_API_STILL_RUNNING')
    runtime_command(run_id, 'create-mapping-v3', [*docker, 'exec', platform_ids[0], 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE DATABASE mapping_v3'], timeout=20)
    stamp = str(time.time_ns())
    (output / ('platform-resources-v2-' + stamp + '.json')).write_bytes((output / 'platform-resources.json').read_bytes())
    config_path = private / 'runtime/api/appsettings.json'
    config = json.loads(config_path.read_text())
    connection = config['ConnectionStrings']['governance']
    if connection.count('Database=mapping_v2;') != 1:
        raise ValueError('MAPPING_DATABASE_CONFIG_PRECONDITION')
    config['ConnectionStrings']['governance'] = connection.replace('Database=mapping_v2;', 'Database=mapping_v3;')
    config_path.write_text(json.dumps(config)); os.chmod(config_path, 0o600)
    resource['databaseName'] = 'mapping_v3'
    resource['retainedDatabases'] = ['mapping', 'mapping_v2']
    (output / 'platform-resources.json').write_text(json.dumps(resource, indent=2) + '\n')
    fixture = output / 'runtime-fixture.json'
    (output / ('runtime-fixture-v2-' + stamp + '.json')).write_bytes(fixture.read_bytes())
    fixture.write_text(json.dumps(dict(taskId=TASK, runId=run_id, scope=dict(organizationId='org-demo', siteIds=['site-a'])), indent=2) + '\n')
    runtime_command(run_id, 'new-database-api-start', [*docker, 'start', api[0]], timeout=20)
    runtime_snapshot(run_id, 'new-database-after')
    record_api_start(run_id)
    receipt = dict(taskId=TASK, runId=run_id, database='mapping_v3', preserved=['mapping', 'mapping_v2'], apiId=api[0], status='STARTED_NEEDS_MIGRATION_HEALTH')
    (output / 'new-database-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'persistence-tests', 'source-tests', 'runtime-prepare', 'runtime-start', 'runtime-configure', 'runtime-api', 'runtime-refresh', 'runtime-binding', 'local-tests', 'qualify', 'browser-tests', 'runtime-new-database', 'web-start-binding', 'compatibility-tests'))
    parser.add_argument('--task', required=True)
    parser.add_argument('--phase', choices=('persistence', 'source', 'runtime'), default='runtime')
    parser.add_argument('--run-id')
    parser.add_argument('--mode')
    parser.add_argument('--gate')
    parser.add_argument('--input-key')
    args = parser.parse_args()
    if args.task != TASK:
        raise ValueError('MAPPING_TASK_INVALID')
    handlers = {'persistence-tests': persistence_tests, 'source-tests': source_tests, 'runtime-prepare': runtime_prepare,
                'runtime-start': runtime_start, 'runtime-configure': runtime_configure, 'runtime-api': lambda run: runtime_start(run, api=True), 'runtime-refresh': runtime_refresh, 'runtime-binding': runtime_binding, 'local-tests': local_tests, 'compatibility-tests': compatibility_tests, 'runtime-new-database': runtime_new_database}
    import workflow_m2_build as build
    result = build.validate('web', TASK) if args.action == 'web-start-binding' else browser_tests(args.run_id, args.mode) if args.action == 'browser-tests' else qualify(args.run_id, args.gate, args.input_key) if args.action == 'qualify' else structural(ROOT, args.task, args.phase) if args.action == 'preflight' else handlers[args.action](args.run_id)
    print(json.dumps(result, ensure_ascii=False))
    if result.get('status') == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
