"""M0 隔离开发验收：直接保存脱敏原始输出，不读取现有秘密。"""
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

root = Path(sys.argv[1]).resolve()
evidence = root / 'docs/evidence/M0-MAC-PORTABILITY-001/master'
prefix = 'm0-mac-observed-' + secrets.token_hex(4)
environment = os.environ.copy()
secret_values = [secrets.token_hex(24) for _ in range(5)]
for name, value in zip(['postgres-password', 'rustfs-access-key', 'rustfs-secret-key', 'keycloak-admin-password'], secret_values):
    environment['Parameters__' + name] = value
environment['AppHost__DashboardApiKey'] = secret_values[-1]
environment['DevelopmentInfrastructure__VolumePrefix'] = prefix
records = []
lock = threading.Lock()
log = (evidence / 'runtime-raw-sanitized.txt').open('w')


def clean(text):
    for value in secret_values:
        text = text.replace(value, '[REDACTED]')
    return re.sub(r'(?i)([?&](?:t|token|key)=)[^\s&]+', r'\1[REDACTED]', text)


def emit(text):
    text = clean(text)
    with lock:
        log.write(text.rstrip() + '\n')
        log.flush()
        print(text.rstrip(), flush=True)


def command(args, expected=0, child_environment=None, timeout=90):
    process = subprocess.run(args, cwd=root, env=child_environment, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=timeout)
    result = {'command': args, 'exitCode': process.returncode, 'output': clean(process.stdout)}
    records.append(result)
    emit('$ ' + subprocess.list2cmdline(args) + '\nexitCode=' + str(process.returncode) + '\n' + process.stdout)
    if expected is not None and process.returncode != expected:
        raise RuntimeError('Unexpected command exit: ' + args[0])
    return process.stdout


def http(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode('utf-8')


def wait_health():
    endpoints = ['http://localhost:15888/', 'http://localhost:15080/health',
                 'http://localhost:15080/alive', 'http://localhost:13030/$/ping',
                 'http://localhost:19000/health/ready', 'http://localhost:19090/health/ready']
    deadline = time.monotonic() + 180
    for endpoint in endpoints:
        while True:
            try:
                status, _ = http(endpoint)
                if status == 200:
                    records.append({'command': ['GET', endpoint], 'exitCode': 0, 'httpStatus': status})
                    emit('GET ' + endpoint + ' HTTP ' + str(status))
                    break
            except (OSError, urllib.error.URLError):
                pass
            if apphost.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Health deadline: ' + endpoint)
            time.sleep(1)


apphost = None
reader = None
status = 'FAIL'
try:
    # 只查固定开发端口；存在监听就停止，避免抢占其他会话。
    ports = [15888, 15080, 15432, 13030, 19000, 19001, 18080, 19090, 14317, 18889]
    listening = ['lsof', '-nP'] + ['-iTCP:' + str(port) for port in ports] + ['-sTCP:LISTEN']
    before = command(listening, expected=1)
    if before.strip():
        raise RuntimeError('Development ports already occupied')
    launch = ['dotnet', 'run', '--no-build', '--no-restore', '--project',
              str(root / 'backend/src/AppHost/OntologyPlatform.AppHost.csproj')]
    emit('$ ' + subprocess.list2cmdline(launch) + '\nVolumePrefix=' + prefix + '\nSecrets=[process-generated, values not recorded]')
    apphost = subprocess.Popen(launch, cwd=root, env=environment, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    def read_startup():
        for line in apphost.stdout:
            if re.search(r'token|password|secret|login|api.key', line, re.I):
                emit('[sensitive startup line omitted]')
            else:
                emit(line)

    reader = threading.Thread(target=read_startup, daemon=True)
    reader.start()
    wait_health()
    names = command(['docker', 'ps', '--format', '{{.Names}}']).splitlines()
    selected = {}
    for resource in ['postgres', 'fuseki', 'rustfs', 'keycloak']:
        matching = [name for name in names if name.startswith(resource + '-')]
        if len(matching) != 1:
            raise RuntimeError('Ambiguous development resource: ' + resource)
        selected[resource] = matching[0]
    snapshots = {}
    for resource, container in selected.items():
        template = '{"image":{{json .Config.Image}},"imageId":{{json .Image}},"ports":{{json .NetworkSettings.Ports}},"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}},"restart":{{json .HostConfig.RestartPolicy.Name}}}'
        data = json.loads(command(['docker', 'inspect', '--format', template, container]))
        image_platform = command(['docker', 'image', 'inspect', '--format', '{{.Os}}/{{.Architecture}}', data['imageId']]).strip()
        if image_platform != 'linux/arm64' or data['restart'] != 'unless-stopped':
            raise RuntimeError('Unexpected resource platform or restart policy')
        for bindings in data['ports'].values():
            for binding in bindings or []:
                if binding['HostIp'] not in ['127.0.0.1', '::1']:
                    raise RuntimeError('Resource port is not loopback')
        if resource != 'keycloak' and not any(mount.get('Name', '').startswith(prefix + '-') for mount in data['mounts']):
            raise RuntimeError('Resource volume is not isolated')
        data['platform'] = image_platform
        data['container'] = container
        snapshots[resource] = data
    shared_networks = set.intersection(*(set(item['networks']) for item in snapshots.values()))
    if not shared_networks:
        raise RuntimeError('Resources do not share session network')
    runtime_listeners = command(listening)
    for line in runtime_listeners.splitlines()[1:]:
        if 'LISTEN' in line and '127.0.0.1:' not in line and '[::1]:' not in line:
            raise RuntimeError('Development listener is not loopback')
    persistence = ['pwsh', '-NoProfile', '-File', str(root / 'infra/development/test-resource-persistence.ps1'), '-VolumePrefix', prefix]
    for resource, parameter in [('postgres', 'PostgresContainer'), ('fuseki', 'FusekiContainer'), ('rustfs', 'RustfsContainer'), ('keycloak', 'KeycloakContainer')]:
        persistence += ['-' + parameter, selected[resource]]
    command(persistence, child_environment=environment, timeout=240)
    wait_health()
    for path in ['/api/telemetry/traces?limit=3', '/api/telemetry/resources']:
        code, _ = http('http://localhost:15888' + path)
        emit('GET ' + path + ' without API key HTTP ' + str(code))
        records.append({'command': ['GET', path, 'without-api-key'], 'exitCode': 0 if code == 401 else 1, 'httpStatus': code})
        if code != 401:
            raise RuntimeError('Dashboard missing-key request not rejected')
    trace_id = secrets.token_hex(16)
    parent_span = secrets.token_hex(8)
    code, _ = http('http://localhost:15080/m0-trace-observed', {'traceparent': '00-' + trace_id + '-' + parent_span + '-01'})
    emit('GET /m0-trace-observed traceId=' + trace_id + ' parentSpanId=' + parent_span + ' HTTP ' + str(code))
    if code != 404:
        raise RuntimeError('Unexpected trace probe result')
    trace_response = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        code, body = http('http://localhost:15888/api/telemetry/traces/' + trace_id,
                          {'X-API-Key': environment['AppHost__DashboardApiKey']})
        if code == 200:
            trace_response = json.loads(body)
            break
        time.sleep(1)
    emit('GET /api/telemetry/traces/' + trace_id + ' [authenticated header omitted] HTTP ' + str(code))
    emit(json.dumps(trace_response, ensure_ascii=False))
    if code != 200 or trace_response is None:
        raise RuntimeError('Trace query did not return telemetry')
    found = False
    for resource in trace_response['data']['resourceSpans']:
        service_names = [attribute.get('value', {}).get('stringValue') for attribute in resource['resource']['attributes'] if attribute['key'] == 'service.name']
        for scope in resource['scopeSpans']:
            for span in scope['spans']:
                if span['traceId'] == trace_id and span.get('parentSpanId') == parent_span and 'infrastructure-api' in service_names:
                    found = True
    if not found:
        raise RuntimeError('Trace/parent/resource mismatch')
    (evidence / 'runtime-trace-response.json').write_text(clean(json.dumps(trace_response, ensure_ascii=False, indent=2)) + '\n')
    (evidence / 'runtime-resource-snapshot.json').write_text(json.dumps({'volumePrefix': prefix, 'resources': snapshots, 'sharedNetworks': sorted(shared_networks)}, indent=2) + '\n')
    status = 'PASS'
except Exception as error:
    emit('FAIL: ' + type(error).__name__ + ' ' + str(error))
finally:
    if apphost is not None:
        if apphost.poll() is None:
            apphost.terminate()
        try:
            result = apphost.wait(timeout=60)
        except subprocess.TimeoutExpired:
            result = None
        if reader:
            reader.join(timeout=3)
        emit('AppHost final exit=' + str(result))
        if result != 0:
            status = 'FAIL'
    try:
        # 只验证本次确切资源名，不删除其他开发资源或卷。
        # DCP容器移除异步完成，等待明确本次容器消失，不把暂态当遗留。
        cleanup_deadline = time.monotonic() + 60
        while True:
            remaining = command(['docker', 'ps', '-a', '--format', '{{.Names}}']).splitlines()
            if not any(name in remaining for name in locals().get('selected', {}).values()):
                break
            if time.monotonic() >= cleanup_deadline:
                raise RuntimeError('This run left development containers')
            time.sleep(1)
        volumes = command(['docker', 'volume', 'ls', '--format', '{{.Name}}', '--filter', 'name=' + prefix]).splitlines()
        if set(volumes) != {prefix + '-' + item + '-data' for item in ['postgres', 'fuseki', 'rustfs']}:
            raise RuntimeError('Expected retained probe volumes not observed')
        command(listening, expected=1)
    except Exception as error:
        status = 'FAIL'
        emit('Cleanup observation failed: ' + type(error).__name__ + ' ' + str(error))
    (evidence / 'runtime-observed-validation.json').write_text(json.dumps({'status': status, 'volumePrefix': prefix, 'command': ['python3', 'runtime-harness.py', str(root)], 'exitCode': 0 if status == 'PASS' else 1, 'records': records, 'secretHandling': 'Values generated in process and redacted; no claim of OS/Docker internal disk absence.'}, ensure_ascii=False, indent=2) + '\n')
    emit('M0 runtime observed status=' + status)
    log.close()
sys.exit(0 if status == 'PASS' else 1)
