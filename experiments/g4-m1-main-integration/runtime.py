#!/usr/bin/env python3
"""本任务身份、输入绑定、受限进程及资源操作；导入不产生副作用。"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import urllib.request
import urllib.error
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TASK = 'G4-M1-MAIN-INTEGRATION-001'
ARTIFACTS = ROOT / 'artifacts/g4-m1-main-integration-001'
MAIN = 'd1a61daffe844475b07705797e3ad325cc3f2945'
ENGINE = '7a8785bb-6b6e-4ae4-8065-996f4bf83016'
NAMES = ('run.py', 'consumer_check.py', 'runtime.py', 'pg_fixture.py', 'module-tests.py',
         'startup-boundary.py', 'migration-boundary.py', 'contract-check.mjs', 'http.mjs',
         'browser.mjs', 'fault.mjs', 'g3-compatibility.mjs', 'readback.py', 'closeout.py',
         'tests.py', 'host_continuity.py', 'compose.m1.yaml', 'compose.g3.yaml', 'hooks/pre-push')


APPROVAL_SHA = 'af474229e97eaf40e00f1c60e7a4d2aafc3a4c9570133712755683572595c624'
IMAGES = {
    'postgres':'postgres@sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437',
    'keycloak':'quay.io/keycloak/keycloak@sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4',
    'aspnet':'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55',
    'node':'node@sha256:a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f',
    'rustfs':'rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b',
    'fuseki':'sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c'}


def validate_admission(m):
    """清单不是扩大镜像、工具或审批的接口。"""
    require(m.get('approvalSha256') == APPROVAL_SHA, 'APPROVAL_BINDING')
    require(m.get('images') == IMAGES, 'IMAGE_ADMISSION')
    source = ROOT / 'docs/evidence/G4-M1-MAIN-INTEGRATION-001/p0/tools-admission.json'
    report = json.loads(source.read_text())
    expected = {x['path']:x['sha256'] for x in report['files']}
    require(m.get('tools') == expected and expected, 'TOOL_ADMISSION')
    for path, sha in expected.items():
        require(digest(Path(path).read_bytes()) == sha, 'TOOL_DRIFT')


def bounded_process(command, *, cwd, env, timeout):
    """超时或中断回收本次独立会话的整组进程，不影响其他任务。"""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        raw, _ = process.communicate(timeout=timeout)
        return raw, process.returncode, False
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as failure:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            raw, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            raw, _ = process.communicate(timeout=5)
        # 父进程退出不代表孙进程退出；准确会话组仍存在时强制回收。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if isinstance(failure, KeyboardInterrupt):
            raise
        return raw, process.returncode, True


def wait_http(url, timeout=120, headers=None):
    """只访问本次固定loopback入口，禁止代理和重定向越界。"""
    require(url.startswith(('http://127.0.0.1:', 'http://localhost:')), 'HTTP_ORIGIN')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(urllib.request.Request(url, headers=headers or {}), timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise ValueError('HTTP_READY_TIMEOUT')


def require(value, code):
    """仅固定错误码可进入公开诊断。"""
    if not value:
        raise ValueError(code)


def digest(data):
    """绑定实际字节，不把路径视为输入身份。"""
    return hashlib.sha256(data).hexdigest()


def run_id(value):
    """拒绝历史任务身份和路径语法，只接受本任务前缀。"""
    require(isinstance(value, str) and re.fullmatch(r'b-continue-[0-9]{8}-[0-9]{2}', value), 'RUN_ID')
    return value


def boundary(path, base, *, exists=False, private=False):
    """拒绝词法穿越与所有祖先链接；不解析链接后才作越界判断。"""
    path, base = Path(path), Path(base)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(base), 'PATH_BOUNDARY')
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'SYMLINK')
    if exists:
        require(path.exists(), 'PATH_MISSING')
    if private and path.exists():
        require(path.stat().st_mode & 0o077 == 0, 'PRIVATE_MODE')
    return path


def write_json(path, value, *, private=False):
    """独占写入，不覆盖原证据或凭证。"""
    path = Path(path)
    boundary(path, ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600 if private else 0o644), 'w') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def git(*args):
    """固定仓库只读Git入口。"""
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()


def private_dir(run):
    """每Run独立私有根，不能引用旧私有树。"""
    return ROOT / '.tools/security' / ('g4-m1-main-integration-001-' + run_id(run))


def run_temp(run):
    """Run独立临时目录位于ignored工具树，避免混入正式artifacts输出边界。"""
    return boundary(ROOT/'.tools/g4-m1-main-integration-001'/run_id(run)/'tmp',ROOT)


def load_manifest(path, run, expected_head, *, check_head=True):
    """清单固定准入与所有工具散列；清单不能追加执行命令或提升预算。"""
    run_id(run)
    require(re.fullmatch('[a-f0-9]{40}', expected_head or ''), 'HEAD_FORMAT')
    require(Path.cwd() == ROOT, 'CWD')
    path = boundary(path, ARTIFACTS / run, exists=True)
    require(path.name == 'resource-manifest.json' and path.is_file(), 'MANIFEST_PATH')
    m = json.loads(path.read_text())
    require(m.get('schemaVersion') == 1 and m.get('taskId') == TASK and m.get('runId') == run, 'MANIFEST_IDENTITY')
    require(m.get('approvedMain') == MAIN and m.get('root') == str(ROOT), 'MANIFEST_BASE')
    require(m.get('docker') == {'context': 'desktop-linux', 'engineId': ENGINE, 'version': '29.9.2'}, 'ENGINE_BINDING')
    require(m.get('budget') == {'containers': 6, 'memoryBytes': 6 * 1024**3, 'volumeStopBytes': 3 * 1024**3, 'downloads': 0, 'gpu': 0, 'fees': 0}, 'RESOURCE_BUDGET')
    require(m.get('privateDirectory') == str(private_dir(run)), 'PRIVATE_RUN_BINDING')
    require(m.get('temporaryDirectory') == str(run_temp(run)), 'TEMP_RUN_BINDING')
    require(m.get('riskDisposition') == 'AMBER-A1_INTERNAL_SYNTHETIC_NON_DISTRIBUTION', 'RISK_ADMISSION')
    validate_admission(m)
    require(set(m.get('drivers', {})) == set(NAMES), 'CONSUMER_SET')
    for name, expected in m['drivers'].items():
        p = boundary(HERE / name, HERE, exists=True)
        require(p.is_file() and digest(p.read_bytes()) == expected, 'DRIVER_DRIFT')
    if check_head:
        require(git('rev-parse', 'HEAD') == expected_head, 'HEAD_DRIFT')
        require(not git('status', '--porcelain', '--untracked-files=normal'), 'DIRTY_SOURCE')
        require(git('branch', '--show-current') == 'codex/g4-m1-main-integration-001', 'BRANCH')
        for name in NAMES:
            rel = (HERE / name).relative_to(ROOT).as_posix()
            require(subprocess.check_output(['git', 'show', expected_head + ':' + rel], cwd=ROOT) == (HERE / name).read_bytes(), 'UNCOMMITTED_DRIVER')
    m['_path'], m['_sha256'], m['_head'] = str(path), digest(path.read_bytes()), expected_head
    return m


def environment(run=None):
    """所有版本固定在已有本地制品；不继承测试夹具或包源注入。"""
    cli_home=ARTIFACTS/run_id(run)/'dotnet-cli-home' if run is not None else ROOT/'.tools/dotnet-offline-home'
    boundary(cli_home,ROOT)
    cache_root=cli_home.parent if run is not None else cli_home
    temporary=run_temp(run) if run is not None else cli_home/'tmp'
    env = {k: v for k, v in os.environ.items() if not k.startswith(('G1_', 'G2_', 'G4_', 'ConnectionStrings__', 'NUGET_', 'DOTNET_', 'PNPM_', 'Security__', 'G3_', 'RUSTFS_', 'ASPNETCORE_', 'G2__', 'G4__')) and not k.lower().startswith('msbuild')}
    env.update(DOTNET_ROOT='/usr/local/share/dotnet', DOTNET_CLI_HOME=str(cli_home),
               NUGET_PACKAGES=str(cache_root/'nuget-packages'),
               NUGET_HTTP_CACHE_PATH=str(cache_root/'nuget-http-cache'),
               NUGET_SCRATCH=str(cache_root/'nuget-scratch'),
               TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary),
               DOTNET_CLI_TELEMETRY_OPTOUT='1',
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1', DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true',
               PYTHONPATH=str(ROOT / '.tools/pythonlibs'), PYTHONDONTWRITEBYTECODE='1',
               NEXT_TELEMETRY_DISABLED='1', PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1',
               DOTNET_GENERATE_ASPNET_CERTIFICATE='false',NUGET_CERT_REVOCATION_MODE='offline',
               DOTNET_CLI_USE_MSBUILD_SERVER='0',MSBUILDDISABLENODEREUSE='1')
    env['PATH'] = '/opt/homebrew/opt/node@24/bin:/usr/local/share/dotnet:' + env.get('PATH', '')
    return env


def command_file_inputs(command):
    """长命令文本是内容，不作为文件路径进行stat；文件参数仍逐字节绑定。"""
    result={}
    for index, value in enumerate(command):
        if index and command[index-1] in ('-Command','-c','-e'):
            continue
        if len(value)>4096 or '\n' in value or not ('/' in value or value.endswith(('.py','.ps1','.mjs','.dll','.json'))):
            continue
        path=Path(value[1:] if value.startswith('@') else value)
        try:
            if path.is_file():result[str(path.absolute())]=digest(path.read_bytes())
        except OSError:
            continue
    return result


def offline_command(command, *, loopback=False):
    """Mac内核拒绝外网；工程用例可显式保留loopback，依赖恢复拒绝全部网络。"""
    require(sys.platform=='darwin' and Path('/usr/bin/sandbox-exec').is_file(),'OFFLINE_OS_BOUNDARY_UNAVAILABLE')
    profile='(version 1) (allow default) (deny network*)'
    if loopback:
        profile='(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))'
    return ['/usr/bin/sandbox-exec','-p',profile,*command]


def execute(m, name, command, *, env=None, timeout=900, sensitive=False, cwd=ROOT, allowed_codes=(0,)):
    """有界运行且保留真实退出/输入散列；秘密环境只允许私有日志。"""
    require(re.fullmatch('[a-zA-Z0-9_-]{1,80}', name), 'COMMAND_NAME')
    out = boundary(ARTIFACTS / m['runId'] / 'commands', ARTIFACTS)
    out.mkdir(parents=True, exist_ok=True)
    receipt = out / (name + '.json')
    require(not receipt.exists(), 'EXISTING_OUTPUT')
    log = (private_dir(m['runId']) / 'logs' if sensitive else out) / (name + '.log')
    boundary(log,ROOT)
    require(not log.exists(), 'EXISTING_OUTPUT')
    require(isinstance(command, list) and command and all(isinstance(x, str) for x in command), 'COMMAND_SHAPE')
    require(not any(x in ('install', 'pull', 'load', '--force', '--force-with-lease') for x in command), 'DOWNLOAD_OR_FORCE_REFUSED')
    inputs = command_file_inputs(command)
    started, tick = datetime.datetime.now(datetime.timezone.utc).isoformat(), time.monotonic()
    raw, code, timed_out = bounded_process(command, cwd=cwd, env=env or environment(m['runId']), timeout=timeout)
    drift = any(digest(Path(p).read_bytes()) != h for p, h in inputs.items())
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw)
    row = dict(taskId=TASK, runId=m['runId'], testedCommit=m['_head'], command=command,
               startedAtUtc=started, endedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               elapsedSeconds=time.monotonic()-tick, exitCode=code, timingStatus='OBSERVED',
               timedOut=timed_out, executedInputDrift=drift, inputHashes=inputs, manifestSha256=m['_sha256'],
               commandSha256=digest(json.dumps(command).encode()), logSha256=digest(raw), logBytes=len(raw), logVisibility='PRIVATE' if sensitive else 'TASK_EVIDENCE')
    write_json(receipt, row)
    require(not drift, 'EXECUTED_INPUT_DRIFT')
    require(not timed_out and code in allowed_codes, 'COMMAND_FAILED_' + name)
    return raw


def parse_test_cases(text):
    """只接受真实Detailed逐案例与摘要一致，保留参数化身份。"""
    cases=[];states={'passed':'PASS','已通过':'PASS','成功':'PASS','failed':'FAIL','失败':'FAIL','skipped':'SKIP','已跳过':'SKIP'}
    for number,line in enumerate(text.splitlines(),1):
        match=re.fullmatch(r'\s*(passed|已通过|成功|failed|失败|skipped|已跳过)\s+([A-Za-z_][^\r\n]*)',line,re.IGNORECASE)
        if not match:continue
        name=re.sub(r'\s+\(\d[\d., ]*(?:ms|s|秒|毫秒|分钟)\)$','',match[2])
        cases.append({'case':name,'status':states[match[1].lower()],'line':number})
    summary={}
    for key,labels in {'total':'total|总计','PASS':'succeeded|passed|成功|已通过','FAIL':'failed|失败','SKIP':'skipped|已跳过'}.items():
        values=re.findall(r'^\s+(?:'+labels+r'):\s*(\d+)\s*$',text,re.MULTILINE|re.IGNORECASE)
        require(len(values)==1,'TEST_SUMMARY_CARDINALITY');summary[key]=int(values[0])
    require(cases and len(cases)==summary['total'],'TEST_CASE_CARDINALITY')
    require(all(sum(r['status']==status for r in cases)==summary[status] for status in ('PASS','FAIL','SKIP')),'TEST_CASE_SUMMARY_MISMATCH')
    return {'cases':cases,'summary':summary}


def test_projection(m,name,project,raw):
    """公开投影仅保存正式用例身份和结果；真实原始日志另按敏感级别保留。"""
    value=parse_test_cases(raw.decode(errors='replace'))
    receipt=ARTIFACTS/m['runId']/'commands'/(name+'.json')
    observed=json.loads(receipt.read_text())
    require(observed['testedCommit']==m['_head'] and observed['manifestSha256']==m['_sha256'] and observed['logSha256']==digest(raw) and observed['exitCode']==0,'TEST_PROJECTION_BINDING')
    assembly=ROOT/f'backend/tests/OntologyPlatform.{project}/bin/Debug/net10.0/OntologyPlatform.{project}.dll'
    value.update(taskId=TASK,runId=m['runId'],testedCommit=m['_head'],project=project,assemblySha256=digest(assembly.read_bytes()),rawLogSha256=digest(raw),commandReceiptSha256=digest(receipt.read_bytes()),command=name)
    write_json(ARTIFACTS/m['runId']/'case-projections'/(name+'.json'),value)
    return value


def docker(m, args, *, input_bytes=None):
    """固定Engine上下文；调用者不得传入宿主Docker默认context。"""
    command = ['docker', '--context', 'desktop-linux', *args]
    r = subprocess.run(command, input=input_bytes, capture_output=True, timeout=120)
    require(r.returncode == 0, 'DOCKER_COMMAND_FAILED')
    return r.stdout


def verify_engine(m):
    """实际Engine身份与限额能力必须匹配已审准入。"""
    info = json.loads(docker(m, ['info', '--format', '{{json .}}']))
    require(info['ID'] == ENGINE and info['ServerVersion'] == '29.9.2' and info['Architecture'] == 'aarch64', 'ENGINE_DRIFT')
    require(info['MemoryLimit'] and info['MemTotal'] >= 6 * 1024**3, 'ENGINE_CAPACITY')


def compose_environment(m):
    """只有本树登记绑定，不允许共享旧私有目录。"""
    env = environment(m['runId'])
    env.update(G4_RUN_ID=m['runId'], G4_PRIVATE_DIR=m['privateDirectory'], G4_ROOT=str(ROOT),
               G4_HOST_UID=str(os.getuid()), G4_HOST_GID=str(os.getgid()),
               G4_API_OUTPUT=str(ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'),
               G4_PG_TEST_OUTPUT=str(ROOT / 'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0'),
               G4_SHARED_WEB_MODULES=str(ROOT / 'apps/web/node_modules'),
               G4_SHARED_ROOT_MODULES=str(ROOT / 'node_modules'), G4_HELPERS=str(ARTIFACTS / m['runId'] / 'helpers'))
    return env


def compose_command(group):
    """两套精确配置，运行组串行共享本任务Run。"""
    require(group in ('m1', 'g3'), 'GROUP')
    return ['docker', '--context', 'desktop-linux', 'compose', '-f', str(HERE / ('compose.' + group + '.yaml'))]


def inspect_owned(m, ident, service=None):
    """仅接受准确容器ID和本任务本Run标签，不从名字推归属。"""
    require(re.fullmatch('[a-f0-9]{64}', ident or ''), 'CONTAINER_ID')
    item = json.loads(docker(m, ['inspect', ident]))[0]
    labels = item['Config']['Labels']
    require(item['Id'] == ident and labels.get('ontology.task-id') == TASK and labels.get('ontology.run-id') == m['runId'], 'CONTAINER_OWNER')
    if service:
        require(labels.get('com.docker.compose.service') == service, 'CONTAINER_SERVICE')
    return item


def runtime_value(m):
    """只读运行时，不将私有内容输出到普通回执。"""
    p = boundary(private_dir(m['runId']) / 'runtime.json', private_dir(m['runId']), exists=True, private=True)
    require(p.is_file(), 'RUNTIME_FILE')
    r = json.loads(p.read_text())
    require(r.get('taskId') == TASK and r.get('runId') == m['runId'] and r.get('publicOrigin') == 'http://localhost:15100', 'RUNTIME_IDENTITY')
    require(r.get('resourceManifest') == m['_path'] and r.get('manifestSha256') == m['_sha256'] and r.get('testedCommit') == m['_head'], 'RUNTIME_BINDING')
    return r


def cli():
    """只读CLI用于所有JS消费者同一边界；无隐式资源创建。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--resource-manifest', required=True)
    args = parser.parse_args()
    m = load_manifest(args.resource_manifest, args.run_id, args.expected_head)
    verify_engine(m)
    print(json.dumps({'taskId': TASK, 'runId': args.run_id, 'status': 'IDENTITY_VERIFIED'}))


if __name__ == '__main__':
    try:
        cli()
    except (ValueError, OSError, subprocess.SubprocessError):
        print('REFUSED_RUNTIME_BOUNDARY', file=sys.stderr)
        raise SystemExit(2)


def build_fingerprint():
    """读取实际API依赖集、全部测试程序集及Web生产构建，拒绝链接输入。"""
    paths = [ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0', ROOT/'apps/web/.next']
    paths += sorted((ROOT/'backend/tests').glob('*/bin/Debug/net10.0'))
    require(len(paths) >= 8 and all(p.is_dir() for p in paths), 'BUILD_MISSING')
    result = {}
    for directory in paths:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                boundary(path, ROOT)
                result[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    require(any(p.endswith('OntologyPlatform.Api.dll') for p in result) and any(p.endswith('.next/BUILD_ID') for p in result), 'BUILD_INCOMPLETE')
    return result


def check_build(m):
    """所有真实消费者重算相同构建，不能混入不同T的DLL或Next产物。"""
    p = boundary(ARTIFACTS/m['runId']/'build-inputs.json',ARTIFACTS,exists=True)
    value = json.loads(p.read_text())
    require(value['testedCommit'] == m['_head'] and value['files'] == build_fingerprint(), 'BUILD_DRIFT')


def update_runtime(m, **values):
    """私有状态每次有前像，替换仅限已验证本Run准确文件。"""
    r = runtime_value(m)
    p = private_dir(m['runId'])/'runtime.json'
    before = p.read_bytes()
    snapshot = p.parent/('runtime-before-'+str(time.time_ns())+'.json')
    write_json(snapshot,r,private=True)
    r.update(values)
    tmp = p.with_name('runtime-next.json')
    write_json(tmp,r,private=True)
    require(p.read_bytes()==before,'RUNTIME_CONCURRENT_WRITE')
    os.replace(tmp,p)
    return r


# 生成物的全部执行字节来自本文件；不复用旧任务helper的main/私有目录。
WEB_HELPER = r'''import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=process.env.G4_ROOT, run=process.env.G4_RUN_ID;
if(root!==__ROOT__ || !/^b-continue-[0-9]{8}-[0-9]{2}$/.test(run)) process.exit(2);
const server=net.createServer(client=>{
  const remote=net.connect({host:'keycloak-test',port:8080});
  client.on('error',()=>remote.destroy()); remote.on('error',()=>client.destroy());
  client.pipe(remote);remote.pipe(client);
});
server.listen(15180,'127.0.0.1');
const dir=path.join(root,'apps/web');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'.next/required-server-files.json'),'utf8'));
process.env.__NEXT_PRIVATE_STANDALONE_CONFIG=JSON.stringify(manifest.config);
process.chdir(dir);
const require=createRequire(path.join(dir,'package.json'));
await require('next/dist/server/lib/start-server').startServer({dir,hostname:'127.0.0.1',port:15300,isDev:false,allowRetry:false,keepAliveTimeout:5000});
'''


def prepare(m):
    """私有PG/OIDC/PFX与helper只在本轮独占目录生成，不启动容器。"""
    import secrets
    import pg_fixture
    d = private_dir(m['runId'])
    require(not d.exists(),'EXISTING_PRIVATE_RUN')
    pg = pg_fixture.generate(d)
    for name in ('platform-password','keycloak-password','s3-access','s3-secret'):
        pg_fixture.private_file(d,name,secrets.token_urlsafe(40))
    (d/'api').mkdir(mode=0o700)
    with os.fdopen(os.open(d/'api/g4-key',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(secrets.token_bytes(32))
    pg_fixture.private_file(d/'api','ca.crt',(d/'ca.crt').read_text())
    r = dict(taskId=TASK,runId=m['runId'],publicOrigin='http://localhost:15100',
        realmFile=str(d/'realm.json'),sourceSecretFile=str(d/'reader-password'),
        scope=dict(organizationId='org-demo',siteIds=['site-a']),browserChannel='msedge',
        certificatePath=str(d/'api/keyring.pfx'),certificatePassword=secrets.token_urlsafe(40),
        healthKey=secrets.token_urlsafe(32),resourceManifest=m['_path'],manifestSha256=m['_sha256'],
        testedCommit=m['_head'],containerIds={},group=None)
    write_json(d/'runtime.json',r,private=True)
    execute(m,'keyring-certificate',['pwsh','-NoProfile','-File',str(ROOT/'scripts/acceptance/new-wave2-certificate.ps1'),'-RuntimeFile',str(d/'runtime.json')],sensitive=True)
    helpers=ARTIFACTS/m['runId']/'helpers';helpers.mkdir()
    helper=WEB_HELPER.replace('__ROOT__',json.dumps(str(ROOT)))
    (helpers/'loopback-proxy.mjs').write_text(helper)
    write_json(ARTIFACTS/m['runId']/'generated-inputs.json',dict(pg=pg,helpers={'loopback-proxy.mjs':digest(helper.encode())},sourceDriverSha256=digest(Path(__file__).read_bytes())))


def wait_pg(m, service='pg-source', timeout=60):
    """等待精确任务PG真正接受本地连接；容器Running不等同数据库就绪。"""
    require(service in ('pg-source','platform-pg'),'PG_SERVICE')
    ident=runtime_value(m)['containerIds'][service]
    user,db=('postgres','fixture') if service=='pg-source' else ('platform','platform')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        inspect_owned(m,ident,service)
        proc=subprocess.run(['docker','--context','desktop-linux','exec',ident,'pg_isready','-U',user,'-d',db],capture_output=True,timeout=5)
        if proc.returncode==0:return
        time.sleep(.5)
    raise ValueError('PG_READINESS_TIMEOUT')


def validate_bind_mounts(actual, declared):
    """逐项目录匹配；Desktop映射只能是已登记原生路径前加准确/host_mnt。"""
    expected={}
    for mount in declared:
        if mount['type']!='bind':continue
        source=str(boundary(mount['source'],ROOT,exists=True))
        target=mount['target']
        require(target not in expected and mount.get('read_only') is True,'DECLARED_BIND_BOUNDARY')
        expected[target]=source
    seen=set();rows=[]
    for mount in actual:
        if mount['Type']!='bind':continue
        target=mount['Destination']
        require(target in expected and target not in seen,'ACTUAL_BIND_SET')
        source=expected[target]
        require(mount['Source'] in (source,'/host_mnt'+source),'ACTUAL_BIND_SOURCE')
        require(mount.get('RW') is False,'ACTUAL_WRITABLE_BIND')
        seen.add(target)
        rows.append({'nativeSource':source,'daemonSource':mount['Source'],'destination':target,'readOnly':True})
    require(seen==set(expected),'ACTUAL_BIND_SET')
    return rows


def resource_snapshot(m, group, name):
    """实际资源ID/镜像/限额/挂载检查；不归档Env或秘密。"""
    ids = docker(m,['ps','-aq','--no-trunc','--filter','label=ontology.task-id='+TASK,
                     '--filter','label=ontology.run-id='+m['runId']]).decode().split()
    require(len(ids)<=6,'ACTUAL_CONTAINER_BUDGET')
    verify_engine(m)
    # 全profile仅取得声明目录；运行预算仍由实际容器计数和内存核实。
    configured=subprocess.run(compose_command(group)+['--profile','*','config','--format','json'],
        env=compose_environment(m),capture_output=True,timeout=30)
    require(configured.returncode==0,'COMPOSE_CONFIG')
    declarations=json.loads(configured.stdout)['services']
    rows=[];memory=0;container_ids={};volumes={}
    for ident in ids:
        item=inspect_owned(m,ident);service=item['Config']['Labels']['com.docker.compose.service']
        require(service in declarations and service not in container_ids,'ACTUAL_SERVICE_SET')
        require(item['Config']['Image'] in IMAGES.values(),'ACTUAL_IMAGE')
        memory+=item['HostConfig']['Memory'];require(item['HostConfig']['Memory']>0,'UNBOUNDED_MEMORY')
        require(not item['HostConfig']['Privileged'] and item['HostConfig']['ReadonlyRootfs'],'ACTUAL_PRIVILEGE')
        bindings=validate_bind_mounts(item['Mounts'],declarations[service].get('volumes',[]))
        for mount in item['Mounts']:
            if mount['Type']=='volume' and item['State']['Running'] and not item['State']['Paused'] and mount['Name'] not in volumes:
                info=json.loads(docker(m,['volume','inspect',mount['Name']]))[0]
                labels=info.get('Labels') or {}
                require(labels.get('ontology.task-id')==TASK and labels.get('ontology.run-id')==m['runId'],'VOLUME_OWNER')
                observed=docker(m,['exec',ident,'df','-kP',mount['Destination']]).decode().splitlines()[-1].split()
                require(len(observed)>=6 and observed[2].isdigit(),'VOLUME_USAGE_FORMAT')
                volumes[mount['Name']]={'usedBytes':int(observed[2])*1024,'containerId':ident,'destination':mount['Destination']}
        container_ids[service]=ident
        rows.append(dict(id=ident,service=service,image=item['Image'],running=item['State']['Running'],paused=item['State']['Paused'],memoryBytes=item['HostConfig']['Memory'],bindMappings=bindings,mounts=[{k:v for k,v in x.items() if k in ('Type','Name','Source','Destination','RW')} for x in item['Mounts']]))
    require(memory<=6*1024**3,'ACTUAL_MEMORY_BUDGET')
    used=sum(v['usedBytes'] for v in volumes.values())
    require(used<3*1024**3,'VOLUME_STOP_THRESHOLD')
    result=dict(taskId=TASK,runId=m['runId'],group=group,composeConfigSha256=digest(configured.stdout),containers=rows,totalMemoryBytes=memory,observedVolumes=volumes,observedVolumeUsedBytes=used)
    write_json(ARTIFACTS/m['runId']/(name+'.json'),result)
    update_runtime(m,containerIds=container_ids,group=group,**({'rustfsContainerId':container_ids['rustfs']} if 'rustfs' in container_ids else {}))
    return result


def start_group(m, group, *, modules=False):
    """真实Compose受控启动，调用前全部绑定且不得叠加运行组。"""
    import consumer_check
    verify_engine(m);check_build(m);consumer_check.check_all(m)
    r=runtime_value(m)
    require(not r['containerIds'],'PREVIOUS_GROUP_NOT_RECLAIMED')
    helper=ARTIFACTS/m['runId']/'helpers/loopback-proxy.mjs'
    require(digest(helper.read_bytes())==digest(WEB_HELPER.replace('__ROOT__',json.dumps(str(ROOT))).encode()),'HELPER_DRIFT')
    services=['platform-pg','fuseki','rustfs'] if modules else (['platform-pg','keycloak-test','api','web','fuseki','rustfs'] if group=='g3' else ['pg-source','platform-pg','keycloak-test','api','web'])
    tag='modules' if modules else group
    command=compose_command(group)+['up','-d','--no-build','--pull','never',*services]
    import closeout
    before=closeout.inventory(m)
    require(all(not before[k]['owned'] for k in before),'PREEXISTING_RUN_RESOURCE')
    write_json(ARTIFACTS/m['runId']/('resources-'+tag+'-before.json'),before)
    try:
        execute(m,'start-'+tag,command,env=compose_environment(m),timeout=180,sensitive=True)
    finally:
        created=closeout.inventory(m)
        require(all(before[k]['keep']==created[k]['keep'] for k in before),'CREATION_KEEP_DRIFT')
        write_json(ARTIFACTS/m['runId']/('resources-'+tag+'-owned.json'),created)
        resource_snapshot(m,group,'resources-'+tag+'-created')
    wait_pg(m,'platform-pg')
    if group=='m1':wait_pg(m)
    if modules:
        wait_http('http://127.0.0.1:15303/$/ping')
        wait_http('http://127.0.0.1:15900/health/ready')
        return
    wait_http('http://localhost:15180/realms/master/.well-known/openid-configuration',180)
    d=private_dir(m['runId'])
    # 每组新OIDC状态保存到独立文件；旧组认证材料仍保留至审查后精确回收。
    realm=d/('realm-'+group+'.json')
    update_runtime(m,realmFile=str(realm))
    env=environment(m['runId']);env['WAVE2_KEYCLOAK_ADMIN_PASSWORD']=(d/'keycloak-password').read_text()
    execute(m,'bootstrap-'+group,['python3','-B',str(ROOT/'infra/security/bootstrap-keycloak.py'),'--profile','g2','--keycloak-origin','http://localhost:15180','--public-origin','http://localhost:15100','--runtime-output',str(realm)],env=env,sensitive=True)
    configure_api(m,group)
    wait_http('http://localhost:15100/health/live',120,headers={'X-Health-Key':runtime_value(m)['healthKey']})


def configure_api(m, group, *, apply=True):
    """隔离开发Host配置；G3关闭G4，M1仅PG，不访问任何外部模型。"""
    r=runtime_value(m);d=private_dir(m['runId']);realm=json.loads(Path(r['realmFile']).read_text())
    require(realm['authority'].startswith('http://localhost:15180/realms/g2-'),'OIDC_AUTHORITY')
    config={'ConnectionStrings':{'governance':'Host=platform-pg;Database=platform;Username=platform;Password='+(d/'platform-password').read_text()},
      'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],
        'PublicOrigin':r['publicOrigin'],'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx',
        'CertificatePassword':r['certificatePassword'],'HealthKey':r['healthKey']},
      'Web':{'Origin':'http://127.0.0.1:15300'},'G2':{'Enabled':group=='g3','ApplyMigrations':group=='g3'},
      'G4':{'Enabled':group=='m1','ApplyMigrations':group=='m1' and apply,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/ca.crt','AllowEmptyPublicSchema':True},
      'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},'Logging':{'LogLevel':{'Default':'Warning'}}}
    if group=='g3':
        config.update(Semantics={'ValidationOrigin':'http://fuseki:3030/validation','PublishedOrigin':'http://fuseki:3030/ontology'},
            Publishing={'S3Endpoint':'http://rustfs:9000','AccessKey':(d/'s3-access').read_text(),'SecretKey':(d/'s3-secret').read_text(),'Bucket':'g4-main-synthetic'})
    path=d/'api/appsettings.json'
    if path.exists():
        boundary(path,d,private=True)
        os.rename(path,path.with_name('appsettings-before-'+str(time.time_ns())+'.json'))
    write_json(path,config,private=True)


class PauseGuard:
    """暂停故障有独立会话的准确ID恢复守护；主入口异常退出也不能留下暂停。"""
    def __init__(self,m,service,seconds=19):
        self.m=m;self.service=service;self.seconds=seconds;self.guard=None
        require(service in ('pg-source','api','rustfs') and 1<=seconds<=100,'PAUSE_BOUNDARY')
        self.ident=runtime_value(m)['containerIds'][service]

    def __enter__(self):
        item=inspect_owned(self.m,self.ident,self.service)
        require(item['State']['Running'] and not item['State']['Paused'],'PAUSE_INITIAL_STATE')
        script='''import json,subprocess,sys,time
ident,task,run,seconds=sys.argv[1:]
time.sleep(int(seconds))
cmd=['docker','--context','desktop-linux']
p=subprocess.run(cmd+['inspect',ident],capture_output=True,timeout=5)
if p.returncode==0:
 item=json.loads(p.stdout)[0]
 if item['Id']==ident and item['Config']['Labels'].get('ontology.task-id')==task and item['Config']['Labels'].get('ontology.run-id')==run and item['State']['Paused']:
  subprocess.run(cmd+['unpause',ident],check=True,capture_output=True,timeout=5)
'''
        self.guard=subprocess.Popen([sys.executable,'-B','-c',script,self.ident,TASK,self.m['runId'],str(self.seconds)],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.record={'containerId':self.ident,'guardPid':self.guard.pid,'deadlineSeconds':self.seconds,'guardScriptSha256':digest(script.encode()),'startedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        write_json(ARTIFACTS/self.m['runId']/('pause-'+self.service+'-'+str(self.guard.pid)+'-start.json'),self.record)
        docker(self.m,['pause',self.ident])
        require(inspect_owned(self.m,self.ident,self.service)['State']['Paused'],'PAUSE_NOT_OBSERVED')
        return self

    def __exit__(self,*exc):
        item=inspect_owned(self.m,self.ident,self.service)
        if item['State']['Paused']:docker(self.m,['unpause',self.ident])
        require(not inspect_owned(self.m,self.ident,self.service)['State']['Paused'],'UNPAUSE_NOT_OBSERVED')
        if self.guard.poll() is None:
            self.guard.terminate();self.guard.wait(timeout=5)
        write_json(ARTIFACTS/self.m['runId']/('pause-'+self.service+'-'+str(self.guard.pid)+'-end.json'),dict(self.record,pausedAfter=False,guardExitCode=self.guard.returncode))
