#!/usr/bin/env python3
"""已批准Doris本机生命周期夹具：只新增平台PG/OIDC，API/Web在宿主，复用FE/BE。"""
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.request

import workflow_execution as execution
import workflow_m2_build as build
from workflow_m2_doris import structural, TASK, ROOT


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, value):
    """独占创建私有文件，永不覆盖既有运行凭据。"""
    raw = value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value)).encode()
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(raw)


def prepare_control(directory, prepared):
    """已有驱动程序集的离线固定SQL工具，不新增依赖或下载。"""
    from workflow_environment import environment, offline
    from xml.sax.saxutils import escape
    directory.mkdir(mode=0o700)
    private(directory / 'Program.cs', (ROOT / 'scripts/maintenance/doris-fixture-control.cs.txt').read_bytes())
    assembly = ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/MySqlConnector.dll'
    private(directory / 'Control.csproj', '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><FrameworkReference Include="Microsoft.AspNetCore.App"/><Reference Include="MySqlConnector"><HintPath>' + escape(str(assembly)) + '</HintPath></Reference></ItemGroup></Project>')
    private(directory / 'NuGet.Config', '<configuration><packageSources><clear/></packageSources></configuration>')
    home = directory / 'home'
    env = environment(home)
    env['DOTNET_GCHeapHardLimit'] = '0x40000000'
    props = ['-p:ImportDirectoryBuildProps=false', '-p:ImportDirectoryBuildTargets=false', '-p:ManagePackageVersionsCentrally=false']
    project = str(directory / 'Control.csproj')
    for action in (['restore', project, '--configfile', str(directory / 'NuGet.Config'), '--disable-build-servers', '-m:1', *props], ['build', project, '--no-restore', '--disable-build-servers', '-m:1', '-v:q', *props]):
        command = offline([prepared['dotnet'], *action], ROOT, home, [{'path': str((directory / 'Control.csproj').relative_to(ROOT))}])
        command[2] += ' (allow file-write* (subpath ' + json.dumps(str(directory / 'bin')) + '))'
        result = execution.run(command, ROOT, task=TASK, stage='fixed-control-' + action[0], environment=env, timeout=30)
        require(result.returncode == 0, 'FIXTURE_CONTROL_BUILD')
    return str(directory / 'bin/Debug/net10.0/Control.dll')


def control(runtime_file, mode, cleanup=False):
    """固定夹具动作复用公共执行通道；不提供任意SQL、路径或容器目标。"""
    runtime_file = execution.ordinary(runtime_file)
    require(runtime_file.is_relative_to(ROOT / '.tools/security/g4-m2-doris-01'), 'CONTROL_RUNTIME_BOUNDARY')
    runtime = json.loads(runtime_file.read_text())
    require(runtime['taskId'] == TASK and runtime['worktree'] == str(ROOT), 'CONTROL_RUNTIME_IDENTITY')
    if mode in ('pause', 'unpause'):
        ident = runtime['dorisBeId']
        before = execution.run(['docker', '--context', 'desktop-linux', 'inspect', ident], ROOT, task=TASK, run_id=runtime['runId'], stage='be-fault-before', timeout=10, cleanup=cleanup)
        require(before.returncode == 0, 'BE_IDENTITY_READ')
        row = json.loads(before.stdout)[0]
        require(row['Id'] == ident and row['Config']['Labels'].get('ontology.task') == TASK and row['Config']['Labels'].get('com.docker.compose.service') == 'be', 'BE_FAULT_BOUNDARY')
        if (mode == 'pause') != row['State']['Paused']:
            result = execution.run(['docker', '--context', 'desktop-linux', mode, ident], ROOT, task=TASK, run_id=runtime['runId'], stage='be-fixture-' + mode, timeout=10, cleanup=cleanup)
            require(result.returncode == 0, 'BE_FAULT_COMMAND')
        after = execution.run(['docker', '--context', 'desktop-linux', 'inspect', '--format', '{{json .State}}', ident], ROOT, task=TASK, run_id=runtime['runId'], stage='be-fault-after', timeout=10, cleanup=cleanup)
        require(after.returncode == 0 and json.loads(after.stdout)['Paused'] == (mode == 'pause') and json.loads(after.stdout)['Running'], 'BE_FAULT_POSTCONDITION')
        if mode == 'unpause':
            end = time.monotonic() + 15
            while json.loads(after.stdout).get('Health', {}).get('Status') != 'healthy':
                require(time.monotonic() < end, 'BE_HEALTH_RECOVERY')
                time.sleep(.5)
                after = execution.run(['docker', '--context', 'desktop-linux', 'inspect', '--format', '{{json .State}}', ident], ROOT, task=TASK, run_id=runtime['runId'], stage='be-recovery-health', timeout=5, cleanup=cleanup)
                require(after.returncode == 0 and json.loads(after.stdout)['Running'], 'BE_RECOVERY_STATE')
        return {'status': 'APPLIED'}
    require(mode in ('revoke', 'grant', 'backup-schema', 'restore-schema', 'active-reader'), 'CONTROL_MODE')
    assembly = execution.ordinary(runtime['controlDll'])
    require(assembly.is_relative_to(runtime_file.parent / 'control') and execution.sha(assembly.read_bytes()) == runtime['controlSha256'], 'CONTROL_BUILD_BINDING')
    env = dict(os.environ, DOTNET_GCHeapHardLimit='0x20000000')
    result = execution.run([runtime['dotnet'], str(assembly), runtime['dorisRuntime'], mode, runtime['runId']], ROOT, task=TASK, run_id=runtime['runId'], stage='source-fixture-' + mode, timeout=15, environment=env, cleanup=cleanup)
    require(result.returncode == 0, 'SOURCE_FIXTURE_CONTROL_FAILED')
    return json.loads(result.stdout)


def run(prepared, doris_runtime, browser_script):
    """固定配套服务及消费者验证；精确记录和回收，不改主线或其它项目。"""
    structural(ROOT, TASK)
    bindings = {target: build.validate(target, TASK) for target in ('api', 'web')}
    prepared = json.loads(execution.ordinary(prepared).read_text())
    require(prepared['taskId'] == TASK and prepared['worktree'] == str(ROOT), 'PREPARED_IDENTITY')
    doris_runtime = execution.ordinary(doris_runtime)
    require(doris_runtime.is_relative_to(ROOT / 'artifacts/workflow' / TASK), 'DORIS_RUNTIME_BOUNDARY')
    run_id = 'doris-' + secrets.token_hex(6)
    root = ROOT / '.tools/security/g4-m2-doris-01' / run_id
    root.mkdir(parents=True, mode=0o700)
    out = ROOT / 'artifacts/workflow' / TASK / run_id
    out.mkdir(mode=0o700)
    state = dict(taskId=TASK, runId=run_id, status='PLANNED', buildBindings=bindings, containers={}, createdNetworks=[], services=[], cleanup=[], privateRuntime=str(root))
    services = []
    compose = None
    monitor_stop = threading.Event()
    budget_failed = threading.Event()
    state['hostPeakRssBytes'] = 0

    def save():
        (out / 'resources.json').write_text(json.dumps(state, indent=2) + '\n')

    def command(args, stage, timeout=20, env=None, cleanup=False):
        result = execution.run(args, ROOT, task=TASK, run_id=run_id, stage=stage, timeout=timeout, environment=env, cleanup=cleanup, identity_key=execution.sha(stage.encode()))
        if stage == 'doris-ui-lifecycle':
            state['browserExecution'] = result.receipt
            save()
        require(result.returncode == 0, stage + '_FAILED_' + str(result.returncode))
        return result.stdout

    def docker(args, stage, timeout=20, cleanup=False):
        return command(['docker', '--context', 'desktop-linux', *args], stage, timeout, cleanup=cleanup)

    def wait_http(url, timeout, headers=None):
        end = time.monotonic() + timeout
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < end:
            for ident in state['containers'].values():
                current = json.loads(docker(['inspect', '--format', '{{json .State}}', ident], 'service-state'))
                require(current['Running'] and not current['OOMKilled'], 'CONTAINER_EXIT_OR_OOM')
            require(not budget_failed.is_set(), 'HOST_RESOURCE_BUDGET')
            for service in services:
                require(service.process.poll() is None, 'HOST_SERVICE_EXITED')
            try:
                with opener.open(urllib.request.Request(url, headers=headers or {}), timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.3)
        raise ValueError('HTTP_READY_TIMEOUT')

    def host(args, env, name):
        # 常驻进程复用公共START/READY/END；环境只携非敏感路径和预算。
        service = execution.Service(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))', '/usr/bin/env', '-i', *[key + '=' + value for key, value in env.items()], *args], ROOT, TASK)
        services.append(service)
        state['services'].append(dict(name=name, pid=service.process.pid, status='STARTED'))
        save()
        service.reader_threads = []
        for stream, target in ((service.process.stdout, service.out), (service.process.stderr, service.err)):
            def drain(source=stream, destination=target):
                while True:
                    chunk = source.read(4096)
                    if not chunk:
                        break
                    if len(destination) + len(chunk) > 2 * 1024**2:
                        budget_failed.set()
                        os.killpg(service.process.pid, signal.SIGTERM)
                        break
                    destination.extend(chunk)
            thread = threading.Thread(target=drain, daemon=True)
            service.reader_threads.append(thread)
            thread.start()
        return service

    def monitor():
        # 汇总本运行器全部后代（API/Web/浏览器及驱动），不只计算托管堆。
        while not monitor_stop.is_set():
            result = execution.run(['ps', '-axo', 'pid=,ppid=,rss='], ROOT, task=TASK, run_id=run_id, stage='host-resource-observation', timeout=5, diagnostic=True)
            if result.returncode != 0:
                budget_failed.set()
                return
            rows = [tuple(map(int, line.split())) for line in result.stdout.decode().splitlines() if len(line.split()) == 3]
            selected = {os.getpid()}
            while True:
                children = {pid for pid, parent, rss in rows if parent in selected}
                if children <= selected:
                    break
                selected |= children
            total = sum(rss * 1024 for pid, parent, rss in rows if pid in selected)
            state['hostPeakRssBytes'] = max(state['hostPeakRssBytes'], total)
            if total > 4 * 1024**3:
                budget_failed.set()
                # 仅中止本运行器直接创建的独立进程组；从不触碰其它任务。
                for pid, parent, rss in rows:
                    if parent == os.getpid():
                        try:
                            if os.getpgid(pid) == pid:
                                os.killpg(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                return
            monitor_stop.wait(1)

    save()
    try:
        # 当前VM与已有任务实例必须再次符合资源上限，不根据静态模板推定。
        info = json.loads(docker(['info', '--format', '{{json .}}'], 'engine-preflight'))
        require(info['MemTotal'] >= 15 * 1024**3, 'VM_MEMORY')
        running = docker(['ps', '-q', '--no-trunc'], 'running-containers').decode().split()
        retained = json.loads((doris_runtime / 'service-resources-network07.json').read_text())
        require(retained['taskId'] == TASK and retained['status'] == 'MINIMAL_TLS_METADATA_PASS', 'DORIS_RETAINED_RECEIPT')
        expected = {row['id']: row['kind'] for row in retained['containers']}
        require(set(expected.values()) == {'fe', 'be'} and set(running) == set(expected), 'EXPECTED_EXACT_FE_BE')
        images = {'fe': 'apache/doris@sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02', 'be': 'apache/doris@sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7'}
        for ident in running:
            row = json.loads(docker(['inspect', ident], 'existing-resource-identity'))[0]
            kind = expected[ident]
            require(row['Config']['Labels'].get('ontology.task') == TASK and row['Config']['Labels'].get('com.docker.compose.service') == kind and row['State']['Running'] and row['State'].get('Health', {}).get('Status') == 'healthy', 'FOREIGN_OR_UNHEALTHY_RESOURCE')
            image = json.loads(docker(['image', 'inspect', images[kind]], 'doris-image-identity'))[0]
            require(images[kind] in image.get('RepoDigests', []) and image['Architecture'] == 'arm64' and image['Os'] == 'linux', 'DORIS_MANIFEST_IDENTITY')
            require(row['Config']['Image'] == images[kind] and row['Image'] == image['Id'], 'DORIS_IMAGE_DRIFT')
            require(row['HostConfig']['Memory'] == (4 if kind == 'fe' else 6) * 1024**3 and row['HostConfig']['MemorySwap'] == row['HostConfig']['Memory'], 'DORIS_RESOURCE_DRIFT')
            if row['Config']['Labels'].get('com.docker.compose.service') == 'fe':
                prerequisites = docker(['exec', ident, 'sh', '-c', 'cat /proc/sys/vm/max_map_count; cat /proc/swaps'], 'vm-prerequisites').decode().splitlines()
                require(int(prerequisites[0]) >= 2000000 and len(prerequisites) == 2, 'VM_MAP_OR_SWAP')
        for port in (15432, 15180, 15100, 15300):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        for name in ('platform-password', 'keycloak-password'):
            private(root / name, secrets.token_urlsafe(36))
        api_dir = root / 'api'
        api_dir.mkdir(mode=0o700)
        (root / 'keyring').mkdir(mode=0o700)
        private(api_dir / 'g4-key', secrets.token_bytes(32))
        runtime = dict(taskId=TASK, runId=run_id, worktree=str(ROOT), publicOrigin='http://localhost:15100', realmFile=str(root / 'realm.json'), sourceSecretFile=str(doris_runtime / 'private/reader.pass'), certificatePath=str(api_dir / 'keyring.pfx'), certificatePassword=secrets.token_urlsafe(40), healthKey=secrets.token_urlsafe(32))
        runtime.update(dorisRuntime=str(doris_runtime), dorisBeId=next(ident for ident, kind in expected.items() if kind == 'be'), dotnet=prepared['dotnet'])
        runtime['controlDll'] = prepare_control(root / 'control', prepared)
        runtime['controlSha256'] = execution.sha(Path(runtime['controlDll']).read_bytes())
        private(root / 'certificate-input.json', runtime)
        command(['pwsh', '-NoProfile', '-File', str(ROOT / 'scripts/acceptance/new-wave2-certificate.ps1'), '-RuntimeFile', str(root / 'certificate-input.json')], 'api-private-certificate')
        env = dict(os.environ, DORIS_PLATFORM_PRIVATE=str(root), DORIS_HOST_UID=str(os.getuid()), DORIS_HOST_GID=str(os.getgid()))
        args = ['compose', '--env-file', str(doris_runtime / 'private/compose.env'), '-f', 'infra/doris/compose.yaml', '-f', 'infra/doris/compose.test.yaml', '-f', 'infra/doris/compose.platform.yaml', 'config', '--format', 'json']
        rendered = json.loads(command(['docker', '--context', 'desktop-linux', *args], 'platform-render', env=env))
        # 只创建两个配套服务，单独项目避免误操作已有FE/BE。
        rendered['name'] = 'g4-m2-doris-01-' + run_id
        rendered['services'] = {name: rendered['services'][name] for name in ('platform-pg', 'keycloak-test')}
        rendered['networks'] = {'platform-entry': rendered['networks']['platform-entry']}
        rendered['volumes'] = {name: rendered['volumes'][name] for name in ('platform-data', 'keycloak-data')}
        for collection in ('networks', 'volumes'):
            for name, value in rendered[collection].items():
                value['name'] = rendered['name'] + '_' + name
                value.setdefault('labels', {})['ontology.run'] = run_id
        image_ids = {}
        for name, value in rendered['services'].items():
            value['labels']['ontology.run'] = run_id
            image = json.loads(docker(['image', 'inspect', value['image']], 'platform-image-identity'))[0]
            require(image['Architecture'] == 'arm64' and image['Os'] == 'linux', 'PLATFORM_IMAGE_ARCH')
            if name == 'platform-pg':
                # 复用已批准内容寻址导入身份；该历史缓存没有RepoDigests，不冒充registry manifest。
                from workflow_smoke import validate_image
                validate_image(image, value['image'])
            else:
                require(value['image'] in image.get('RepoDigests', []), 'PLATFORM_IMAGE_DIGEST')
            image_ids[name] = image['Id']
        require(sum(int(v['mem_limit']) for v in rendered['services'].values()) == int(1.5 * 1024**3), 'PLATFORM_RESOURCE_BUDGET')
        compose = root / 'compose.json'
        private(compose, rendered)
        state['recipeSha256'] = execution.sha(compose.read_bytes())
        state['volumes'] = [v['name'] for v in rendered['volumes'].values()]
        state['createdNetworks'] = [v['name'] for v in rendered['networks'].values()]
        save()
        state['engine'] = {'id': info['ID'], 'version': info['ServerVersion'], 'context': 'desktop-linux'}
        state['imageIds'] = image_ids
        stable_input = execution.sha(execution.encoded({'bindings': bindings, 'drivers': build.driver_inputs(), 'compose': {str(p.relative_to(ROOT)): execution.sha(p.read_bytes()) for p in sorted((ROOT / 'infra/doris').glob('*.yaml'))}}))
        stable_environment = execution.sha(execution.encoded({'engine': state['engine'], 'images': image_ids}))
        with execution.operation(ROOT, TASK, 'doris-lifecycle', stable_input, stable_environment):
            execution.CONTEXT.set({**execution.CONTEXT.get(), 'run_id': run_id})
            prefix = ['compose', '-f', str(compose)]
            docker([*prefix, 'create', '--pull', 'never', 'platform-pg', 'keycloak-test'], 'platform-create', 60)
            for name in rendered['services']:
                ident = docker([*prefix, 'ps', '--all', '--quiet', name], 'created-identity').decode().strip()
                require(len(ident) == 64, 'CREATED_ID_MISSING')
                state['containers'][name] = ident
                actual = json.loads(docker(['inspect', ident], 'created-resource-limits'))[0]
                require(actual['Image'] == image_ids[name] and actual['HostConfig']['Memory'] == int(rendered['services'][name]['mem_limit']), 'CREATED_RESOURCE_DRIFT')
                save()
            docker([*prefix, 'start', 'platform-pg', 'keycloak-test'], 'platform-start', 60)
            with execution.waiting(ROOT, TASK, 'oidc-ready'):
                wait_http('http://localhost:15180/realms/master/.well-known/openid-configuration', 180)
            bootstrap_env = dict(os.environ, WAVE2_KEYCLOAK_ADMIN_PASSWORD=(root / 'keycloak-password').read_text())
            command(['python3', '-B', str(ROOT / 'infra/security/bootstrap-keycloak.py'), '--profile', 'g2', '--keycloak-origin', 'http://localhost:15180', '--public-origin', runtime['publicOrigin'], '--runtime-output', runtime['realmFile']], 'oidc-bootstrap', 60, bootstrap_env)
            realm = json.loads((root / 'realm.json').read_text())
            config = {'ConnectionStrings': {'governance': 'Host=localhost;Port=15432;Database=platform;Username=platform;Password=' + (root / 'platform-password').read_text()},
                      'Security': {'Authority': realm['authority'], 'ClientId': realm['clientId'], 'ClientSecret': realm['clientSecret'], 'PublicOrigin': runtime['publicOrigin'], 'KeyRingPath': str(root / 'keyring'), 'CertificatePath': runtime['certificatePath'], 'CertificatePassword': runtime['certificatePassword'], 'HealthKey': runtime['healthKey']},
                      'Web': {'Origin': 'http://127.0.0.1:15300'}, 'G2': {'Enabled': False},
                      'G4': {'Enabled': True, 'ApplyMigrations': True, 'KeyFile': str(api_dir / 'g4-key'), 'SourceCaPath': str(doris_runtime / 'tls/ca.pem'), 'Doris': {'RootCertificatePath': str(doris_runtime / 'tls/ca.pem')}},
                      'Governance': {'ApplyMigrations': True, 'SeedDevelopmentResources': True}, 'Logging': {'LogLevel': {'Default': 'Warning'}}}
            private(api_dir / 'appsettings.json', config)
            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()
            api = host([prepared['dotnet'], str(ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll')], {'PATH': os.environ['PATH'], 'ASPNETCORE_ENVIRONMENT': 'Development', 'ASPNETCORE_CONTENTROOT': str(api_dir), 'ASPNETCORE_URLS': 'http://127.0.0.1:15100', 'DOTNET_GCHeapHardLimit': '0x40000000', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1'}, 'api')
            web = host([prepared['node'], str(ROOT / 'apps/web/node_modules/next/dist/bin/next'), 'start', str(ROOT / 'apps/web'), '--hostname', '127.0.0.1', '--port', '15300'], {'PATH': os.environ['PATH'], 'NODE_OPTIONS': '--max-old-space-size=1024', 'NEXT_TELEMETRY_DISABLED': '1'}, 'web')
            with execution.waiting(ROOT, TASK, 'api-web-ready'):
                wait_http(runtime['publicOrigin'] + '/health/live', 90, {'X-Health-Key': runtime['healthKey']})
                wait_http('http://127.0.0.1:15300', 30)
            api.ready()
            web.ready()
            private(root / 'runtime.json', runtime)
            state['status'] = 'READY'
            save()
            result = command(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))', prepared['node'], str(browser_script), str(root / 'runtime.json')], 'doris-ui-lifecycle', 180)
            require(not budget_failed.is_set(), 'HOST_RESOURCE_BUDGET')
            report = json.loads(result)
            require(report['status'] == 'PASS' and report['tests'] > 0, 'BROWSER_ASSERTIONS')
            (out / 'browser.json').write_text(json.dumps(report, indent=2) + '\n')
            # 发布前只做内存中的秘密泄漏断言，原始dump保存在公共执行器私有原件目录。
            dump = docker(['exec', state['containers']['platform-pg'], 'pg_dump', '-U', 'platform', '-d', 'platform', '--data-only'], 'platform-audit-dump')
            secret = (doris_runtime / 'private/reader.pass').read_bytes()
            require(secret not in dump, 'PERSISTED_SOURCE_SECRET')
            actions = ['connection.secret.intake', 'connection.create', 'connection.probe.start', 'connection.probe.complete', 'connection.enable', 'connection.disable', 'connection.catalog.start', 'connection.catalog.finish', 'connection.secret.rotate', 'connection.update']
            require(all(action.encode() in dump for action in actions), 'AUDIT_ACTION_MISSING')
            require(all(secret not in bytes(service.out) + bytes(service.err) for service in services), 'HOST_LOG_SOURCE_SECRET')
            from workflow_m2_evidence import doris_audit
            associations = doris_audit(dump, report)
            associations.update(taskId=TASK, runId=run_id, privateDumpSha256=execution.sha(dump), browserSha256=execution.sha(result))
            (out / 'audit-associations.json').write_text(json.dumps(associations, indent=2) + '\n')
            state['auditAndSecretScan'] = dict(platformDump=True, hostLogs=True, actions=actions, raw='PRIVATE_ONLY', associationsSha256=execution.sha((out / 'audit-associations.json').read_bytes()))
            require(bindings == {target: build.validate(target, TASK) for target in ('api', 'web')}, 'BUILD_CHANGED_DURING_LIFECYCLE')
            state['status'] = 'LIFECYCLE_CHECKS_PASSED'
    except Exception as error:
        state.update(status='FAIL', reason=type(error).__name__ + ':' + (str(error) if isinstance(error, ValueError) else 'operation failed'))
    finally:
        monitor_stop.set()
        if 'monitor_thread' in locals():
            monitor_thread.join(timeout=6)
        for service in reversed(services):
            try:
                # 进程组由本运行器创建，即使主进程先退出也核对并回收其后代。
                group = service.process.pid
                try:
                    os.killpg(group, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    service.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(group, signal.SIGKILL)
                    service.process.wait(timeout=3)
                groups = execution.run(['ps', '-axo', 'pgid='], ROOT, task=TASK, run_id=run_id, stage='host-group-after-term', timeout=5, cleanup=True)
                present = str(group) in groups.stdout.decode().split()
                if present:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    time.sleep(.1)
                    groups = execution.run(['ps', '-axo', 'pgid='], ROOT, task=TASK, run_id=run_id, stage='host-group-after-kill', timeout=5, cleanup=True)
                absent = groups.returncode == 0 and str(group) not in groups.stdout.decode().split()
                state['cleanup'].append(dict(kind='process-group', id=group, afterAbsent=absent))
                if not absent:
                    state.update(status='FAIL', reason='HOST_GROUP_NOT_ABSENT')
                for thread in service.reader_threads:
                    thread.join(timeout=1)
                    require(not thread.is_alive(), 'SERVICE_LOG_READER_ACTIVE')
                service.finish()
            except Exception:
                state['cleanup'].append(dict(kind='process-group', id=service.process.pid, afterAbsent=False, error='CLEANUP_FAILED'))
                state.update(status='FAIL', reason='HOST_CLEANUP_FAILED')
            save()
        if (root / 'runtime.json').is_file():
            for mode in ('unpause', 'grant'):
                try:
                    control(root / 'runtime.json', mode, cleanup=True)
                except Exception:
                    state.update(status='FAIL', reason='SOURCE_FIXTURE_RESTORE_FAILED')
                save()
        # create失败也查询本任务准确项目服务；任何单项失败都不阻断其它准确ID清理。
        if compose is not None:
            for name in ('platform-pg', 'keycloak-test'):
                if name not in state['containers']:
                    try:
                        ids = docker(['compose', '-f', str(compose), 'ps', '--all', '--quiet', name], 'recover-created-id', cleanup=True).decode().split()
                        if len(ids) == 1:
                            state['containers'][name] = ids[0]
                    except Exception:
                        state['cleanup'].append(dict(kind='container-lookup', name=name, afterAbsent=False))
                        state.update(status='FAIL', reason='CREATED_RESOURCE_LOOKUP_FAILED')
                    save()
            for name, ident in state['containers'].items():
                try:
                    row = json.loads(docker(['inspect', ident], 'cleanup-before', cleanup=True))[0]
                    require(row['Config']['Labels'].get('ontology.run') == run_id, 'CLEANUP_OWNER')
                    docker(['rm', '-f', ident], 'cleanup-container', cleanup=True)
                    absent = not docker(['ps', '-aq', '--no-trunc', '--filter', 'id=' + ident], 'cleanup-after', cleanup=True).strip()
                    state['cleanup'].append(dict(kind='container', id=ident, afterAbsent=absent))
                    if not absent:
                        state.update(status='FAIL', reason='CLEANUP_NOT_ABSENT')
                except Exception:
                    state['cleanup'].append(dict(kind='container', id=ident, afterAbsent=False, error='CLEANUP_FAILED'))
                    state.update(status='FAIL', reason='CONTAINER_CLEANUP_FAILED')
                save()
        state['keep'] = 'Private credentials, pre-cleanup platform dump, empty tmpfs volume handles and task networks retained for current-task diagnosis/review; tmpfs data is not retained after container removal. Release after evidence publication and scoped cleanup.'
        save()
    return state


def expired_certificate(prepared_file, runtime_directory):
    """准确FE证书临时替换的真实TLS负例，始终恢复原字节并验证正常目录读取。"""
    prepared = json.loads(execution.ordinary(prepared_file).read_text())
    require(prepared['taskId'] == TASK and prepared['worktree'] == str(ROOT), 'TLS_PREPARED_IDENTITY')
    runtime = execution.ordinary(runtime_directory)
    require(runtime.is_relative_to(ROOT / 'artifacts/workflow' / TASK), 'TLS_RUNTIME_BOUNDARY')
    binding = build.validate('connections', TASK)
    retained = json.loads((runtime / 'service-resources-network07.json').read_text())
    ident = next(row['id'] for row in retained['containers'] if row['kind'] == 'fe')
    run_id = 'tls-expired-' + secrets.token_hex(6)
    directory = ROOT / '.tools/security/g4-m2-doris-01' / run_id
    directory.mkdir(mode=0o700)
    output = ROOT / 'artifacts/workflow' / TASK / run_id
    output.mkdir(mode=0o700)
    state = dict(taskId=TASK, runId=run_id, feId=ident, status='PLANNED', buildBinding=binding, privateRuntime=str(directory))
    def save():
        (output / 'tls-receipt.json').write_text(json.dumps(state, indent=2) + '\n')
    def run_command(args, stage, cleanup=False, timeout=20, env=None):
        result = execution.run(args, ROOT, task=TASK, run_id=run_id, stage=stage, timeout=timeout, environment=env, cleanup=cleanup)
        require(result.returncode == 0, stage + '_FAILED')
        return result.stdout
    def inspect(cleanup=False):
        row = json.loads(run_command(['docker', '--context', 'desktop-linux', 'inspect', ident], 'tls-fe-inspect', cleanup))[0]
        require(row['Id'] == ident and row['Config']['Labels'].get('ontology.task') == TASK and row['Config']['Labels'].get('com.docker.compose.service') == 'fe', 'TLS_FE_IDENTITY')
        return row
    def restart(cleanup=False):
        inspect(cleanup)
        run_command(['docker', '--context', 'desktop-linux', 'restart', '--time', '10', ident], 'tls-fe-restart', cleanup, 45)
        end = time.monotonic() + 120
        while True:
            row = inspect(cleanup)
            require(row['State']['Running'] and not row['State']['OOMKilled'], 'TLS_FE_EXIT_OR_OOM')
            if row['State'].get('Health', {}).get('Status') == 'healthy':
                return
            require(time.monotonic() < end, 'TLS_FE_READY_TIMEOUT')
            time.sleep(1)
    def test(filter_value, name, cleanup=False):
        env = dict(prepared['environment'], G4_DORIS_TEST_RUNTIME=str(runtime), DOTNET_GCHeapHardLimit='0x40000000')
        raw = run_command([prepared['dotnet'], str(ROOT / 'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0/OntologyPlatform.ConnectionsTests.dll'), '--filter', filter_value, '--minimum-expected-tests', '1', '--no-ansi', '--progress', 'off'], name, cleanup, 20, env)
        from workflow_m2_evidence import mtp
        require(mtp(raw, 1) == 1, 'TLS_TEST_COUNT')
        (output / (name + '.txt')).write_bytes(raw)
        state[name] = dict(exitCode=0, tests=1, logSha256=execution.sha(raw))
        save()
    save()
    certificate = execution.ordinary(runtime / 'tls/server_certificate.p12')
    original = certificate.read_bytes()
    private(directory / 'original-server.p12', original)
    state['originalKeystoreSha256'] = execution.sha(original)
    replaced = False
    try:
        inspect()
        # 私有CA、原server密钥和CSR只用于签发已过期的同SAN测试证书。
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        not_before = (now - datetime.timedelta(days=2)).strftime('%Y%m%d%H%M%SZ')
        not_after = (now - datetime.timedelta(days=1)).strftime('%Y%m%d%H%M%SZ')
        run_command(['openssl', 'x509', '-req', '-in', str(runtime / 'private/server.csr'), '-CA', str(runtime / 'tls/ca.pem'), '-CAkey', str(runtime / 'private/ca.key'), '-set_serial', '9040813', '-not_before', not_before, '-not_after', not_after, '-extfile', str(runtime / 'private/cert.cnf'), '-extensions', 'v3', '-out', str(directory / 'expired.pem')], 'create-expired-certificate')
        expired = execution.run(['openssl', 'x509', '-in', str(directory / 'expired.pem'), '-checkend', '0', '-noout'], ROOT, task=TASK, run_id=run_id, stage='assert-expired', timeout=10)
        require(expired.returncode == 1, 'CERTIFICATE_NOT_EXPIRED')
        run_command(['openssl', 'pkcs12', '-export', '-name', 'server', '-inkey', str(runtime / 'private/server.key'), '-in', str(directory / 'expired.pem'), '-certfile', str(runtime / 'tls/ca.pem'), '-out', str(directory / 'expired.p12'), '-passout', 'file:' + str(runtime / 'private/store.pass')], 'package-expired-certificate')
        os.chmod(directory / 'expired.p12', 0o600)
        state['status'] = 'REPLACING_CERTIFICATE'
        save()
        replaced = True
        certificate.write_bytes((directory / 'expired.p12').read_bytes())
        restart()
        # 独立只读握手确认服务实际呈现的叶证书，不能只以挂载文件推断。
        observed = execution.run(['openssl', 's_client', '-connect', 'localhost:19030', '-starttls', 'mysql', '-servername', 'localhost', '-CAfile', str(runtime / 'tls/ca.pem'), '-verify_hostname', 'localhost', '-verify_return_error', '-showcerts'], ROOT, task=TASK, run_id=run_id, stage='observe-expired-leaf', stdin=b'', timeout=10, diagnostic=True)
        import re
        import ssl
        leaf = re.search(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', observed.stdout, re.S)
        require(leaf is not None, 'PRESENTED_LEAF_MISSING')
        actual = execution.sha(ssl.PEM_cert_to_DER_cert(leaf[0].decode()))
        expected_leaf = execution.sha(ssl.PEM_cert_to_DER_cert((directory / 'expired.pem').read_text()))
        require(actual == expected_leaf and observed.returncode != 0 and b'certificate has expired' in observed.stderr, 'EXPIRED_LEAF_NOT_OBSERVED')
        state['presentedCertificate'] = dict(sha256=actual, matchesGenerated=True, notBefore=not_before, notAfter=not_after, opensslRejectedExpired=True, observerExitCode=observed.returncode)
        save()
        test('FullyQualifiedName~DorisExpiredTlsTests', 'expired-rejection')
        state['status'] = 'NEGATIVE_PASSED_RESTORE_PENDING'
    except Exception as error:
        state['primaryFailure'] = type(error).__name__ + (':' + str(error) if isinstance(error, ValueError) else '')
    finally:
        state['status'] = 'RESTORE_PENDING' if replaced else 'FAIL'
        save()
        try:
            if replaced:
                certificate.write_bytes(original)
                os.chmod(certificate, 0o600)
                require(execution.sha(certificate.read_bytes()) == state['originalKeystoreSha256'], 'TLS_RESTORE_BYTES')
                state['restoredOriginalBytes'] = True
                save()
                restart(True)
                state['restoredFeHealthy'] = True
                save()
                test('FullyQualifiedName~DorisFixtureSecurityTests.RealAdapterReadsSyntheticMetadata', 'restored-product-probe', True)
            require(binding == build.validate('connections', TASK), 'TLS_BUILD_CHANGED')
        except Exception as error:
            state['restoreFailure'] = type(error).__name__ + (':' + str(error) if isinstance(error, ValueError) else '')
        finally:
            state['status'] = 'PASS' if state.get('expired-rejection') and state.get('restored-product-probe') and not state.get('primaryFailure') and not state.get('restoreFailure') else 'FAIL'
            save()
    return state


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('control',))
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--mode', required=True, choices=('pause', 'unpause', 'grant', 'revoke', 'backup-schema', 'restore-schema', 'active-reader'))
    args = parser.parse_args()
    print(json.dumps(control(args.runtime, args.mode)))
