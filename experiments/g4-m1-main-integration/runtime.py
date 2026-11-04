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
MODULE_PHASES = {'SemanticTests':'modules-semantic','PublishingTests':'modules-publishing','QueryTests':'modules-query','AgentTests':'modules-agent'}
INGRESS_GROUPS = ('modules','g3','m1',*MODULE_PHASES.values())
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
        duration=r'\d[\d.,]*\s*(?:ms|s|m|h|毫秒|秒|分钟|小时)'
        name=re.sub(r'\s+\('+duration+r'(?:\s+'+duration+r')*\)$','',match[2])
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


def compose_environment(m, *, certificate_variant='server'):
    """只有本树登记绑定，不允许共享旧私有目录。"""
    require(certificate_variant in ('server','wrong-san'),'CERTIFICATE_VARIANT')
    env = environment(m['runId'])
    env.update(G4_CERTIFICATE_VARIANT=certificate_variant,G4_RUN_ID=m['runId'], G4_PRIVATE_DIR=m['privateDirectory'], G4_ROOT=str(ROOT),
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
    """统一入口先绑定身份；仅显式ingress模式启动固定组监听。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingress', choices=INGRESS_GROUPS)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--resource-manifest', required=True)
    args = parser.parse_args()
    require(len(sys.argv)==(9 if args.ingress else 7) and len(set(sys.argv[1::2]))==(4 if args.ingress else 3),'EXACT_ARGUMENT_SET')
    m = load_manifest(args.resource_manifest, args.run_id, args.expected_head)
    if args.ingress:
        import asyncio
        asyncio.run(ingress_daemon(m,args.ingress))
        return
    verify_engine(m)
    print(json.dumps({'taskId': TASK, 'runId': args.run_id, 'status': 'IDENTITY_VERIFIED'}))


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
const root=process.env.G4_ROOT, run=process.env.G4_RUN_ID, group=process.env.G4_GROUP;
if(root!==__ROOT__ || !/^b-continue-[0-9]{8}-[0-9]{2}$/.test(run) || !['g3','m1'].includes(group)) process.exit(2);
// API 与 Web 共用网络命名空间；仅 G3 注册产品合同要求的内部回环服务。
const mappings=[[15180,'keycloak-test',8080],...(group==='g3'?[[15303,'fuseki',3030],[15900,'rustfs',9000]]:[])];
const sockets=new Set();
const servers=mappings.map(([port,host,target])=>{
  const server=net.createServer(client=>{
    const remote=net.connect({host,port:target});
    sockets.add(client);sockets.add(remote);
    const close=()=>{client.destroy();remote.destroy();sockets.delete(client);sockets.delete(remote);};
    for(const socket of [client,remote]){
      socket.setTimeout(30000,close);socket.on('error',close);socket.on('close',close);
    }
    client.pipe(remote);remote.pipe(client);
  });
  server.maxConnections=64;server.listen(port,'127.0.0.1');return server;
});
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{
  for(const server of servers)server.close();
  for(const socket of sockets)socket.destroy();
  setTimeout(()=>process.exit(0),1000).unref();
});
const dir=path.join(root,'apps/web');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'.next/required-server-files.json'),'utf8'));
process.env.__NEXT_PRIVATE_STANDALONE_CONFIG=JSON.stringify(manifest.config);
process.chdir(dir);
const require=createRequire(path.join(dir,'package.json'));
await require('next/dist/server/lib/start-server').startServer({dir,hostname:'0.0.0.0',port:15300,isDev:false,allowRetry:false,keepAliveTimeout:5000});
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


# 历史host-ingress的受限stdio设计；内部目标、期限和程序均由本任务冻结。
INGRESS_PORTS={'platform-pg':(15432,5432),'fuseki':(15303,3030),'rustfs':(15900,9000),
              'keycloak-test':(15180,8080),'api':(15100,15100),'web':(15300,15300)}
INGRESS_IMAGES={service:IMAGES[image] for service,image in {'platform-pg':'postgres','fuseki':'fuseki','rustfs':'rustfs','keycloak-test':'keycloak','api':'aspnet','web':'node'}.items()}
INGRESS_LIMIT=32
INGRESS_SECONDS=120
RELAY_PERL=r'''use strict; use warnings; use Socket; use POSIX ':sys_wait_h';
my ($ip,$port,$token,$seconds)=@ARGV;
die "ARGS\n" unless @ARGV==4 && $ip=~/^\d+\.\d+\.\d+\.\d+$/ && $port=~/^\d+$/ && $seconds>=1 && $seconds<=120 && $token=~/^g4-relay-[a-z0-9-]+$/;
$SIG{PIPE}='IGNORE'; my $child;
sub finish { if($child){kill 'TERM',$child;waitpid($child,0);} exit($_[0]); }
$SIG{TERM}=sub{finish(0)}; $SIG{INT}=sub{finish(0)}; $SIG{ALRM}=sub{finish(124)}; alarm($seconds);
socket(my $tcp,PF_INET,SOCK_STREAM,0) or die "SOCKET\n";
if($port==5432){
setsockopt($tcp,Socket::IPPROTO_TCP(),Socket::TCP_NODELAY(),pack("i",1)) or die "TCP_NODELAY\n";
my $nodelay=getsockopt($tcp,Socket::IPPROTO_TCP(),Socket::TCP_NODELAY());
die "TCP_NODELAY_READBACK\n" unless defined($nodelay) && unpack("i",$nodelay)==1;
}
connect($tcp,sockaddr_in($port,inet_aton($ip))) or die "CONNECT\n";
binmode STDIN;binmode STDOUT;binmode $tcp;
$child=fork();defined $child or die "FORK\n";
if(!$child){
 $SIG{TERM}=sub{exit(0)};$SIG{INT}=sub{exit(0)};$SIG{ALRM}=sub{exit(124)};alarm($seconds);
 while(1){my $n=sysread(STDIN,my $buf,65536);exit(2) unless defined $n;last unless $n;
  my $offset=0;while($offset<$n){my $w=syswrite($tcp,$buf,$n-$offset,$offset);exit(2) unless $w;$offset+=$w;}}
 shutdown($tcp,1);exit(0);
}
print STDERR "PIDS $$ $child\n";
my $sent=0;
while(1){my $n=sysread($tcp,my $buf,65536);finish(2) unless defined $n;last unless $n;
 my $offset=0;while($offset<$n){my $w=syswrite(STDOUT,$buf,$n-$offset,$offset);finish(2) unless $w;$offset+=$w;$sent+=$w;}}
print STDERR "OUTPUT_EOF $sent\n";close STDOUT;waitpid($child,0);my $status=$?;$child=0;
exit(($status & 127) ? 128+($status & 127) : ($status >> 8));
'''
RELAY_REAP_PERL=r'''use strict;use warnings;
my($mode,@tokens)=@ARGV;die "ARGS" unless $mode eq 'inspect' || $mode eq 'terminate';
my %tokens=map { die "TOKEN" unless /^g4-relay-[a-z0-9-]+$/; $_=>1 } @tokens;
my @found;
for my $file(glob('/proc/[0-9]*/cmdline')){
 open my $f,'<',$file or next;local $/;my $raw=<$f>;close $f;
 my @args=split(/\0/,$raw);next unless @args>=2 && $args[0] eq 'perl' && $args[1] eq '-e';
 next if $raw eq '';my @matches=grep {$tokens{$_}} @args;next unless @matches;
 $file=~m{/proc/(\d+)/};my $pid=$1;next if $pid==$$;
 push @found,$pid;kill 'TERM',$pid if $mode eq 'terminate';
}
print join(',',sort {$a<=>$b} @found);
'''


def ingress_services(group):
    """三个冻结运行组；不接受外部端口、地址或命令。"""
    require(group in INGRESS_GROUPS,'INGRESS_GROUP')
    return ('platform-pg','fuseki','rustfs') if group=='modules' or group in MODULE_PHASES.values() else (
        ('platform-pg','keycloak-test','api','web','fuseki','rustfs') if group=='g3' else
        ('platform-pg','keycloak-test','api','web'))


def engine_frame_header(header):
    """解析非TTY Docker stdcopy帧；诊断流与协议原始字节分离。"""
    require(len(header)==8 and header[0] in (1,2) and header[1:4]==b'\0\0\0','ENGINE_FRAME')
    size=int.from_bytes(header[4:8],'big');require(size<=1024*1024,'ENGINE_FRAME_SIZE')
    return header[0],size


class TaskEngine:
    """仅固定本机context的Unix API；不读取凭据，不提供任意Docker命令入口。"""
    def __init__(self,m):
        import socket
        context=json.loads(subprocess.check_output(['docker','context','inspect','desktop-linux'],timeout=10))[0]
        self.endpoint=context['Endpoints']['docker']['Host']
        require(self.endpoint=='unix:///Users/chasen/.docker/run/docker.sock','ENGINE_SOCKET_BOUNDARY')
        self.path=self.endpoint[7:];self.m=m;self.created_execs=set();self.allowed_targets=set()
        info=self.request('GET','/info')
        require(info['ID']==ENGINE and info['ServerVersion']=='29.9.2' and info['Architecture']=='aarch64','ENGINE_DRIFT')
        require(self.request('GET','/version')['ApiVersion']=='1.56','ENGINE_API_VERSION')

    def request_boundary(self,method,path):
        """同步准入与异步数据入口共用准确API路径白名单。"""
        if method=='GET' and path.startswith('/containers/json?'):
            import urllib.parse
            query=urllib.parse.parse_qs(path.split('?',1)[1],strict_parsing=True)
            require(set(query)=={'all','filters'} and query['all']==['1'] and len(query['filters'])==1,'ENGINE_LIST_BOUNDARY')
            value=json.loads(query['filters'][0]);require(set(value)=={'id'},'ENGINE_LIST_BOUNDARY')
            ids=value['id'];require(isinstance(ids,list) and 1<=len(ids)<=6 and len(set(ids))==len(ids) and all(re.fullmatch('[a-f0-9]{64}',v or '') for v in ids),'ENGINE_LIST_BOUNDARY')
            return
        require((method=='GET' and (path in ('/info','/version') or re.fullmatch(r'/(containers|exec)/[a-f0-9]{64}/json',path) or re.fullmatch(r'/networks/[a-f0-9]{64}',path))) or
                (method=='POST' and re.fullmatch(r'/containers/[a-f0-9]{64}/exec',path)),'ENGINE_REQUEST_BOUNDARY')

    def request(self,method,path,body=None):
        """启动前同步核验；运行中的每连接请求使用非阻塞版本。"""
        import http.client,socket
        self.request_boundary(method,path)
        endpoint=self.path
        class LocalConnection(http.client.HTTPConnection):
            def connect(self):
                self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                self.sock.settimeout(5);self.sock.connect(endpoint)
        connection=LocalConnection('localhost',timeout=5)
        try:
            connection.request(method,'/v1.56'+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(4*1024*1024+1)
            require(response.status in (200,201) and len(raw)<=4*1024*1024,'ENGINE_RESPONSE')
            return json.loads(raw)
        finally:connection.close()

    async def async_request(self,method,path,body=None):
        """五秒有界Unix HTTP；避免Engine停顿阻塞全部连接和生命周期定时器。"""
        import asyncio
        self.request_boundary(method,path)
        async def exchange():
            reader,writer=await asyncio.open_unix_connection(self.path,limit=65536)
            try:
                payload=json.dumps(body).encode() if body is not None else b''
                # HTTP/1.0关闭连接定界，不接受未实现的chunked响应。
                writer.write((f'{method} /v1.56{path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n').encode()+payload)
                await writer.drain();header=await reader.readuntil(b'\r\n\r\n')
                require(re.fullmatch(rb'HTTP/1\.[01] (200|201) [^\r\n]*',header.split(b'\r\n')[0]) and b'transfer-encoding:' not in header.lower(),'ENGINE_RESPONSE')
                data=bytearray()
                while chunk:=await reader.read(65536):
                    data.extend(chunk);require(len(data)<=4*1024*1024,'ENGINE_RESPONSE_SIZE')
                return json.loads(data)
            finally:writer.close();await writer.wait_closed()
        return await asyncio.wait_for(exchange(),5)

    def list_path(self,ident):
        """完整ID过滤，不接受前缀、名字或全局无过滤列表。"""
        import urllib.parse
        ids=[ident] if isinstance(ident,str) else ident
        require(isinstance(ids,list) and 1<=len(ids)<=6 and len(ids)==len(set(ids)) and all(re.fullmatch('[a-f0-9]{64}',v or '') for v in ids),'CONTAINER_ID')
        return '/containers/json?all=1&filters='+urllib.parse.quote(json.dumps({'id':ids},separators=(',',':')),safe='')

    def listed_item(self,rows,ident,service,*,allow_paused=False):
        """列表返回的准确身份/镜像/状态/网络投影足够逐连接核验，不取Env。"""
        require(isinstance(rows,list) and len(rows)==1 and rows[0]['Id']==ident,'INGRESS_LIST_IDENTITY')
        row=rows[0];state=row['State'];paused=state=='paused' or '(Paused)' in row.get('Status','')
        item={'Id':row['Id'],'Image':row['ImageID'],'Config':{'Labels':row['Labels'],'Image':row['Image']},
            'State':{'Running':state in ('running','paused'),'Paused':paused},'HostConfig':row['HostConfig'],'NetworkSettings':row['NetworkSettings']}
        return self.check_owned(item,ident,service,allow_paused=allow_paused)

    def owned(self,ident,service,*,allow_paused=False):
        """准确ID、Run、服务及冻结镜像必须仍一致。"""
        require(re.fullmatch('[a-f0-9]{64}',ident or ''),'CONTAINER_ID')
        rows=self.request('GET',self.list_path(ident))
        return self.listed_item(rows,ident,service,allow_paused=allow_paused)

    def check_owned(self,item,ident,service,*,allow_paused=False):
        """验证内存中的准确容器投影，不输出完整inspect的Env。"""
        labels=item['Config']['Labels']
        require(item['Id']==ident and labels.get('ontology.task-id')==TASK and labels.get('ontology.run-id')==self.m['runId'] and labels.get('com.docker.compose.service')==service,'INGRESS_OWNER')
        require(service in INGRESS_IMAGES and item['State']['Running'] and (allow_paused or not item['State']['Paused']) and item['Config']['Image']==INGRESS_IMAGES[service],'INGRESS_CONTAINER_STATE')
        return item

    def command_boundary(self,command):
        """固定程序、同Run token及已核验目标，拒绝调用者注入命令。"""
        require(command[:2]==['perl','-e'] and len(command)>=4,'INGRESS_EXEC_COMMAND')
        if command[2]==RELAY_PERL:
            import ipaddress
            require(len(command)==7 and ipaddress.ip_address(command[3]).version==4 and
                (ipaddress.ip_address(command[3]).is_private or command[3]=='127.0.0.1') and
                (command[3],int(command[4])) in self.allowed_targets and
                re.fullmatch('g4-relay-'+self.m['runId']+'-[a-f0-9]{32}',command[5]) and command[6]==str(INGRESS_SECONDS),'INGRESS_EXEC_ARGUMENTS')
        else:
            require(command[2]==RELAY_REAP_PERL and command[3] in ('inspect','terminate') and
                all(re.fullmatch('g4-relay-'+self.m['runId']+'-[a-f0-9]{32}',v) for v in command[4:]),'INGRESS_EXEC_COMMAND')

    def create(self,broker,command):
        """准入诊断中的同步Exec；正式运行使用异步版本。"""
        self.command_boundary(command)
        self.owned(broker,'platform-pg')
        result=self.request('POST','/containers/'+broker+'/exec',{'AttachStdin':True,'AttachStdout':True,'AttachStderr':True,'Tty':False,'Privileged':False,'User':'999:999','Cmd':command})
        require(re.fullmatch('[a-f0-9]{64}',result.get('Id','')),'ENGINE_EXEC_ID')
        self.created_execs.add(result['Id']);return result['Id']

    async def async_create(self,broker,command):
        """异步创建未启动的准确Exec；只有登记ExecID后才允许附接启动。"""
        self.command_boundary(command)
        self.listed_item(await self.async_request('GET',self.list_path(broker)),broker,'platform-pg')
        result=await self.async_request('POST','/containers/'+broker+'/exec',{'AttachStdin':True,'AttachStdout':True,'AttachStderr':True,'Tty':False,'Privileged':False,'User':'999:999','Cmd':command})
        require(re.fullmatch('[a-f0-9]{64}',result.get('Id','')),'ENGINE_EXEC_ID')
        self.created_execs.add(result['Id']);return result['Id']

    async def attach(self,ident):
        """本机Unix HTTP升级为Exec原始stdio，保留双向半关闭。"""
        import asyncio
        require(ident in self.created_execs,'ENGINE_EXEC_ID')
        reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(self.path,limit=65536),5)
        try:
            body=b'{"Detach":false,"Tty":false}'
            request=(f'POST /v1.56/exec/{ident}/start HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: tcp\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
            writer.write(request);await writer.drain()
            header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
            require(header.split(b'\r\n')[0]==b'HTTP/1.1 101 UPGRADED','ENGINE_HIJACK')
            return reader,writer
        except BaseException:writer.close();await writer.wait_closed();raise

    async def reap(self,broker,tokens,event):
        """按准确连接token清理并后验容器内父/子；不能凭宿主socket断开宣称退出。"""
        import asyncio
        observations=[]
        for mode in ('terminate','inspect'):
            ident=await self.async_create(broker,['perl','-e',RELAY_REAP_PERL,mode,*sorted(tokens)])
            event('reap_exec_created',execId=ident,mode=mode)
            reader,writer=await self.attach(ident);writer.write_eof();output=b''
            try:
                while True:
                    try:header=await asyncio.wait_for(reader.readexactly(8),10)
                    except asyncio.IncompleteReadError as error:
                        require(not error.partial,'REAP_FRAME');break
                    stream,size=engine_frame_header(header);data=await reader.readexactly(size)
                    require(stream==1 and len(output)+len(data)<65536,'REAP_OUTPUT');output+=data
            finally:writer.close();await writer.wait_closed()
            for _ in range(50):
                result=await self.async_request('GET','/exec/'+ident+'/json')
                if not result['Running']:break
                await asyncio.sleep(.1)
            require(result['ContainerID']==broker and not result['Running'] and result['ExitCode']==0,'REAP_EXEC_FAILED')
            require(re.fullmatch(rb'(?:[0-9]+(?:,[0-9]+)*)?',output),'REAP_PID_FORMAT')
            observations.append({'execId':ident,'mode':mode,'pids':[int(v) for v in output.split(b',') if v],'exitCode':result['ExitCode']})
            if mode=='terminate':await asyncio.sleep(.5)
            else:require(not output,'REMOTE_RELAY_REMAINS')
        event('remote_reaped',observations=observations)
        return observations


def ingress_route_projection(m,engine,group,ids,listed):
    """纯投影共用全部身份/网络规则；只为准确本Run容器建立固定路由。"""
    import ipaddress
    services=ingress_services(group);expected={ids[s] for s in services}
    require(isinstance(listed,list) and len(listed)==len(expected) and {v['Id'] for v in listed}==expected,'INGRESS_LIST_IDENTITY')
    items={s:engine.listed_item([next(v for v in listed if v['Id']==ids[s])],ids[s],s,allow_paused=s!='platform-pg') for s in services}
    broker=items['platform-pg']
    network='ontology-g4-main-'+m['runId']+'_front';bn=broker['NetworkSettings']['Networks']
    require(set(bn)=={network},'INGRESS_BROKER_NETWORK');netid=bn[network]['NetworkID']
    routes=[];networks_to_verify={netid:network}
    for service in services:
        # 目标pause是获批故障语义：继续透明等待TCP，不替换成适配器立即拒绝。
        item=items[service];provider=item
        if service=='web':
            require(item['HostConfig']['NetworkMode']=='container:'+ids['api'],'INGRESS_WEB_NAMESPACE')
            provider=items['api']
        networks=provider['NetworkSettings']['Networks']
        expected_networks={network}
        if group=='m1' and service in ('api','web'):expected_networks.add('ontology-g4-main-'+m['runId']+'_source')
        require(set(networks)==expected_networks and networks[network]['NetworkID']==netid,'INGRESS_TARGET_NETWORK')
        for other in expected_networks-{network}:
            other_id=networks[other]['NetworkID'];require(other_id not in networks_to_verify or networks_to_verify[other_id]==other,'INGRESS_NETWORK_ALIAS')
            networks_to_verify[other_id]=other
        ip=networks[network]['IPAddress'];require(ipaddress.ip_address(ip).version==4 and ipaddress.ip_address(ip).is_private,'INGRESS_TARGET_ADDRESS')
        host_port,port=INGRESS_PORTS[service]
        routes.append({'service':service,'targetId':ids[service],'providerId':provider['Id'],'brokerId':broker['Id'],
            'networkId':netid,'targetIp':ip,'connectIp':'127.0.0.1' if service=='platform-pg' else ip,'port':port,'hostPort':host_port})
    require(all(re.fullmatch('[a-f0-9]{64}',n or '') for n in networks_to_verify),'INGRESS_NETWORK_ID')
    return routes,networks_to_verify


def ingress_network_projection(m,networks,observed):
    """每个网络必须是准确名称/ID、同Run归属的internal bridge。"""
    require(len(observed)==len(networks) and {v['Id'] for v in observed}==set(networks),'INGRESS_NETWORK_SET')
    for value in observed:
        require(value['Name']==networks[value['Id']] and value['Internal'] is True and value['Driver']=='bridge' and value['Labels'].get('ontology.task-id')==TASK and value['Labels'].get('ontology.run-id')==m['runId'],'INGRESS_NETWORK_ISOLATION')


def ingress_runtime_group(value, group):
    """模块phase既绑定三服务路由，也绑定当前运行状态，拒绝旧phase复用。"""
    ingress_services(group)
    expected='g3' if group=='modules' or group in MODULE_PHASES.values() else group
    require(value['group']==expected,'INGRESS_GROUP_RUNTIME')
    if group in MODULE_PHASES.values():require(value.get('modulePhase')==group,'INGRESS_MODULE_PHASE')
    return expected


def ingress_routes(m,engine,group):
    """仅启动前同步冻结；运行中的复核使用下方可取消异步入口。"""
    value=runtime_value(m);ingress_runtime_group(value,group)
    ids=value['containerIds'];listed=engine.request('GET',engine.list_path([ids[s] for s in ingress_services(group)]))
    routes,networks=ingress_route_projection(m,engine,group,ids,listed)
    ingress_network_projection(m,networks,[engine.request('GET','/networks/'+ident) for ident in networks])
    engine.allowed_targets={(row['connectIp'],row['port']) for row in routes};return routes


async def async_ingress_routes(m,engine,group):
    """整条每连接复核可取消；无后台同步线程延长退出期限。"""
    import asyncio
    value=runtime_value(m);ingress_runtime_group(value,group)
    ids=value['containerIds'];listed=await engine.async_request('GET',engine.list_path([ids[s] for s in ingress_services(group)]))
    routes,networks=ingress_route_projection(m,engine,group,ids,listed)
    ingress_network_projection(m,networks,await asyncio.gather(*[engine.async_request('GET','/networks/'+ident) for ident in networks]))
    engine.allowed_targets={(row['connectIp'],row['port']) for row in routes};return routes


async def relay_copy(client_reader,client_writer,engine_reader,engine_writer,on_control):
    """有界原始字节流；EOF只关闭相应写半边，控制信息不进入客户端。"""
    import asyncio
    async def upstream():
        while data:=await client_reader.read(65536):engine_writer.write(data);await engine_writer.drain()
        engine_writer.write_eof();await engine_writer.drain()
    async def downstream():
        control=b'';received=0;expected=None;half_closed=False
        while True:
            try:header=await engine_reader.readexactly(8)
            except asyncio.IncompleteReadError as error:
                require(not error.partial,'ENGINE_TRUNCATED_FRAME');break
            stream,size=engine_frame_header(header);data=await engine_reader.readexactly(size)
            if stream==1:
                received+=len(data);require(expected is None or received<=expected,'REMOTE_EOF_COUNT')
                client_writer.write(data);await client_writer.drain()
            else:
                control+=data;require(len(control)<=4096,'ENGINE_CONTROL_SIZE')
                while b'\n' in control:
                    line,control=control.split(b'\n',1)
                    if re.fullmatch(rb'OUTPUT_EOF [0-9]{1,18}',line):
                        require(expected is None,'REMOTE_DUPLICATE_EOF');expected=int(line.split()[1])
                        require(received<=expected,'REMOTE_EOF_COUNT')
                    elif re.fullmatch(rb'PIDS [0-9]+ [0-9]+',line):on_control([int(n) for n in line.split()[1:]])
                    else:raise ValueError('REMOTE_RELAY_FAILED')
            # stdout/stderr跨流无顺序保证；全部stdout字节到达后才发送TCP写半关闭。
            if expected==received and not half_closed:
                if client_writer.can_write_eof():client_writer.write_eof();await client_writer.drain()
                half_closed=True
        require(not control,'ENGINE_CONTROL_TRUNCATED')
        require(expected==received,'REMOTE_EOF_COUNT')
    tasks=[asyncio.create_task(upstream()),asyncio.create_task(downstream())]
    try:await asyncio.gather(*tasks)
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


async def ingress_daemon(m,group,*,evidence_directory=None):
    """固定loopback守护进程，32连接/120秒/4小时；每次连接重验设施身份。"""
    import asyncio,signal,uuid,datetime
    engine=TaskEngine(m);routes=ingress_routes(m,engine,group)
    a=ARTIFACTS/m['runId']
    if evidence_directory is not None:a=boundary(evidence_directory,a,exists=True)
    events=a/('ingress-'+group+'-events.jsonl')
    require(not events.exists(),'EXISTING_INGRESS_EVENTS')
    journal=events.open('x');active=set();active_tokens=set();reservations=set();execs={};exited=set();watchers=set();stopping=asyncio.Event();servers=[]
    def event(kind,**values):
        journal.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':os.getpid(),'event':kind,**values})+'\n');journal.flush();os.fsync(journal.fileno())
    async def observe_exit(ident,broker,token):
        deadline=time.monotonic()+INGRESS_SECONDS+10
        while time.monotonic()<deadline:
            result=await engine.async_request('GET','/exec/'+ident+'/json')
            require(result['ContainerID']==broker,'EXEC_CONTAINER_DRIFT')
            if not result['Running'] and type(result['ExitCode']) is int:
                exited.add(ident)
                if token not in active_tokens:reservations.discard(token)
                event('exec_exited',execId=ident,token=token,containerId=broker,running=False,exitCode=result['ExitCode']);return
            await asyncio.sleep(.25)
        event('exec_exit_unproven',execId=ident,token=token);stopping.set();raise ValueError('EXEC_EXIT_UNPROVEN')
    async def accepted(reader,writer,route):
        if stopping.is_set() or len(reservations)>=INGRESS_LIMIT:
            event('refused_capacity',hostPort=route['hostPort']);writer.close();await writer.wait_closed();return
        task=asyncio.current_task();active.add(task);pipe=None;exec_id=None
        token='g4-relay-'+m['runId']+'-'+uuid.uuid4().hex
        active_tokens.add(token);reservations.add(token)
        event('reserved',token=token,hostPort=route['hostPort'])
        async def serve():
            nonlocal exec_id,pipe
            require(await async_ingress_routes(m,engine,group)==routes,'INGRESS_ROUTE_DRIFT')
            event('connection',token=token,service=route['service'],hostPort=route['hostPort'])
            exec_id=await engine.async_create(route['brokerId'],['perl','-e',RELAY_PERL,route['connectIp'],str(route['port']),token,str(INGRESS_SECONDS)])
            execs[exec_id]=token;event('exec_created',execId=exec_id,token=token,brokerId=route['brokerId'])
            er,ew=await engine.attach(exec_id);pipe=ew
            watcher=asyncio.create_task(observe_exit(exec_id,route['brokerId'],token));watchers.add(watcher)
            def checked(done):
                if not done.cancelled() and done.exception() is not None:
                    event('exec_observer_failed',execId=exec_id,token=token);stopping.set()
            watcher.add_done_callback(checked)
            await relay_copy(reader,writer,er,ew,lambda pids:event('remote_pids',execId=exec_id,token=token,pids=pids))
        try:
            await asyncio.wait_for(serve(),INGRESS_SECONDS)
        except (ValueError,OSError,asyncio.TimeoutError,asyncio.IncompleteReadError):event('connection_closed_error',token=token)
        finally:
            try:
                if pipe:pipe.close();await pipe.wait_closed()
            except OSError:pass
            finally:
                writer.close()
                try:await writer.wait_closed()
                except OSError:pass
                active.discard(task);active_tokens.discard(token)
                if exec_id is None or exec_id in exited:reservations.discard(token)
                event('connection_closed',token=token,execId=exec_id)
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stopping.set)
    deadline=loop.call_later(14400,stopping.set)
    try:
        for route in routes:
            server=await asyncio.start_server(lambda r,w,route=route:accepted(r,w,route),'127.0.0.1',route['hostPort'],limit=65536,start_serving=False)
            servers.append(server)
            event('listener_bound',hostPort=route['hostPort'])
        for server in servers:await server.start_serving()
        write_json(a/('ingress-'+group+'-ready.json'),{'pid':os.getpid(),'taskId':TASK,'runId':m['runId'],'testedCommit':m['_head'],'manifestSha256':m['_sha256'],'runtimeSha256':digest(Path(__file__).read_bytes()),'engineSocket':engine.endpoint,'apiVersion':'1.56','routes':routes,'maxConcurrent':INGRESS_LIMIT,'connectionSeconds':INGRESS_SECONDS,'processSeconds':14400})
        event('ready');await stopping.wait()
    finally:
        deadline.cancel()
        for server in servers:server.close();await server.wait_closed()
        pending=list(active)
        for task in pending:task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        pending_tokens={token for ident,token in execs.items() if ident not in exited}
        if pending_tokens:await engine.reap(routes[0]['brokerId'],pending_tokens,event)
        outcomes=await asyncio.gather(*watchers,return_exceptions=True)
        require(not any(isinstance(v,BaseException) for v in outcomes),'INGRESS_EXEC_EXIT_FAILED')
        event('stopped',remainingConnections=len(active),execIds=list(execs));journal.close()


def start_ingress(m,group):
    """登记本任务后台进程；端口占用或身份漂移必须停止对应门禁。"""
    import sys
    ingress_services(group);a=ARTIFACTS/m['runId'];record=a/('ingress-'+group+'-process.json')
    require(all(not (a/('ingress-'+group+suffix)).exists() for suffix in ('-process.json','-ready.json','-events.jsonl','-process.log')),'EXISTING_INGRESS')
    command=[sys.executable,'-B',str(HERE/'runtime.py'),'--ingress',group,'--run-id',m['runId'],'--expected-head',m['_head'],'--resource-manifest',m['_path']]
    with (a/('ingress-'+group+'-process.log')).open('xb') as output:
        process=subprocess.Popen(command,cwd=ROOT,env=environment(m['runId']),stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    birth=subprocess.check_output(['ps','-p',str(process.pid),'-o','lstart='],text=True).strip()
    write_json(record,{'pid':process.pid,'birth':birth,'command':command,'taskId':TASK,'runId':m['runId'],'testedCommit':m['_head'],'runtimeSha256':digest(Path(__file__).read_bytes())})
    ready=a/('ingress-'+group+'-ready.json');deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        require(process.poll() is None,'INGRESS_START_FAILED')
        if ready.exists():
            require(json.loads(ready.read_text())['pid']==process.pid,'INGRESS_READY_PID');return
        time.sleep(.1)
    process.terminate();process.wait(timeout=5);raise ValueError('INGRESS_START_TIMEOUT')


def stop_ingress(m,group,*,evidence_directory=None):
    """核对PID出生身份后停止listener，并独立证明准确ExecID与远端token均已退出。"""
    import signal,asyncio,socket
    a=ARTIFACTS/m['runId']
    if evidence_directory is not None:a=boundary(evidence_directory,a,exists=True)
    path=a/('ingress-'+group+'-process.json')
    if not path.exists():return {'status':'NOT_STARTED'}
    record=json.loads(path.read_text());require(record['taskId']==TASK and record['runId']==m['runId'] and record['testedCommit']==m['_head'],'INGRESS_PROCESS_OWNER')
    closed=a/('ingress-'+group+'-closed.json')
    query=subprocess.run(['ps','-p',str(record['pid']),'-o','lstart='],capture_output=True,text=True)
    if query.returncode==0:
        require(query.stdout.strip()==record['birth'],'INGRESS_PID_REUSED')
        command=subprocess.check_output(['ps','-p',str(record['pid']),'-o','command='],text=True)
        require(str(HERE/'runtime.py') in command and '--ingress '+group in command and m['runId'] in command,'INGRESS_PROCESS_COMMAND')
        require(not closed.exists(),'INGRESS_CLOSED_PROCESS_REAPPEARED')
        os.kill(record['pid'],signal.SIGTERM)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            p=subprocess.run(['ps','-p',str(record['pid']),'-o','stat='],capture_output=True,text=True)
            if p.returncode!=0 or p.stdout.strip().startswith('Z'):break
            time.sleep(.1)
        else:raise ValueError('INGRESS_STOP_TIMEOUT')
    if closed.exists():return {'status':'ALREADY_CLOSED','receiptSha256':digest(closed.read_bytes())}
    engine=TaskEngine(m);ready=a/('ingress-'+group+'-ready.json')
    events=a/('ingress-'+group+'-events.jsonl')
    rows=[json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    frozen=json.loads(ready.read_text()) if ready.exists() else None
    if frozen:
        require(frozen['pid']==record['pid'] and frozen['taskId']==TASK and frozen['runId']==m['runId'] and frozen['testedCommit']==m['_head'] and frozen['manifestSha256']==m['_sha256'] and frozen['runtimeSha256']==record['runtimeSha256'],'INGRESS_READY_BINDING')
        routes=frozen['routes']
        require([(v['service'],v['hostPort'],v['port']) for v in routes]==[(s,*INGRESS_PORTS[s]) for s in ingress_services(group)],'INGRESS_READY_ROUTES')
        require(len({v['brokerId'] for v in routes})==1,'INGRESS_BROKER_SET')
        broker=routes[0]['brokerId']
    else:
        ports=[v['hostPort'] for v in rows if v['event']=='listener_bound']
        require(len(ports)==len(set(ports)) and set(ports)<={INGRESS_PORTS[s][0] for s in ingress_services(group)},'INGRESS_BOUND_PORTS')
        routes=[{'hostPort':port} for port in ports]
        broker=runtime_value(m)['containerIds']['platform-pg']
    created={v['execId']:v for v in rows if v['event']=='exec_created'}
    proven={v['execId']:v for v in rows if v['event']=='exec_exited'}
    observations=[]
    if created:
        require(all(v['brokerId']==broker and re.fullmatch('g4-relay-'+m['runId']+'-[a-f0-9]{32}',v['token']) for v in created.values()),'INGRESS_JOURNAL_OWNER')
        item=engine.request('GET','/containers/'+broker+'/json');labels=item['Config']['Labels']
        require(item['Id']==broker and labels.get('ontology.task-id')==TASK and labels.get('ontology.run-id')==m['runId'] and labels.get('com.docker.compose.service')=='platform-pg','INGRESS_BROKER_OWNER')
        if item['State']['Running']:
            require(not item['State']['Paused'],'INGRESS_BROKER_PAUSED')
            tokens=sorted({v['token'] for v in created.values()})
            for offset in range(0,len(tokens),128):
                asyncio.run(engine.reap(broker,set(tokens[offset:offset+128]),lambda kind,**v:observations.append({'event':kind,**v})))
        else:
            require(item['State']['Pid']==0,'STOPPED_BROKER_PID')
            observations.append({'event':'broker_namespace_stopped','containerId':broker,'running':False,'pid':0})
    for ident,row in created.items():
        if ident in proven:
            require(proven[ident]['running'] is False and type(proven[ident]['exitCode']) is int and proven[ident]['containerId']==row['brokerId'],'EXEC_EXIT_RECEIPT')
        else:
            value=engine.request('GET','/exec/'+ident+'/json')
            require(value['ContainerID']==row['brokerId'] and value['Running'] is False and type(value['ExitCode']) is int,'EXEC_STILL_RUNNING')
            proven[ident]={'execId':ident,'containerId':value['ContainerID'],'running':False,'exitCode':value['ExitCode']}
    for route in routes:
        with socket.socket() as probe:
            # 重新绑定成功是准确listener释放见证；不凭进程列表缺席推断。
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('127.0.0.1',route['hostPort']))
    result={'status':'PASS','taskId':TASK,'runId':m['runId'],'testedCommit':m['_head'],'pid':record['pid'],'processReceiptSha256':digest(path.read_bytes()),'portsReleased':[v['hostPort'] for v in routes],'execExits':list(proven.values()),'remoteObservations':observations}
    write_json(a/('ingress-'+group+'-closed.json'),result);return result


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


def observed_volume_usage(m, volumes):
    """每个本Run卷都必须有实际占用观测，脱离挂载的遗留卷不能静默漏算。"""
    owned=docker(m,['volume','ls','-q','--filter','label=ontology.task-id='+TASK,
                    '--filter','label=ontology.run-id='+m['runId']]).decode().split()
    require(len(owned)==len(set(owned)) and set(owned)==set(volumes),'UNOBSERVED_OWNED_VOLUME')
    return sum(value['usedBytes'] for value in volumes.values())


def resource_snapshot(m, group, name, *, certificate_variant='server'):
    """实际资源ID/镜像/限额/挂载检查；不归档Env或秘密。"""
    require(certificate_variant in ('server','wrong-san') and (certificate_variant=='server' or group=='m1'),'CERTIFICATE_VARIANT')
    ids = docker(m,['ps','-aq','--no-trunc','--filter','label=ontology.task-id='+TASK,
                     '--filter','label=ontology.run-id='+m['runId']]).decode().split()
    require(len(ids)<=6,'ACTUAL_CONTAINER_BUDGET')
    verify_engine(m)
    # 全profile仅取得声明目录；运行预算仍由实际容器计数和内存核实。
    configured=subprocess.run(compose_command(group)+['--profile','*','config','--format','json'],
        env=compose_environment(m,certificate_variant=certificate_variant),capture_output=True,timeout=30)
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
    used=observed_volume_usage(m,volumes)
    require(used<3*1024**3,'VOLUME_STOP_THRESHOLD')
    result=dict(taskId=TASK,runId=m['runId'],group=group,certificateVariant=certificate_variant,composeConfigSha256=digest(configured.stdout),containers=rows,totalMemoryBytes=memory,observedVolumes=volumes,observedVolumeUsedBytes=used)
    write_json(ARTIFACTS/m['runId']/(name+'.json'),result)
    update_runtime(m,containerIds=container_ids,group=group,**({'rustfsContainerId':container_ids['rustfs']} if 'rustfs' in container_ids else {}))
    return result


def start_group(m, group, *, modules=False, module_phase=None):
    """真实Compose受控启动，调用前全部绑定且不得叠加运行组。"""
    import consumer_check
    require((modules and group=='g3' and module_phase in MODULE_PHASES.values()) or (not modules and module_phase is None),'MODULE_PHASE')
    verify_engine(m);check_build(m);consumer_check.check_all(m)
    r=runtime_value(m)
    require(not r['containerIds'],'PREVIOUS_GROUP_NOT_RECLAIMED')
    helper=ARTIFACTS/m['runId']/'helpers/loopback-proxy.mjs'
    require(digest(helper.read_bytes())==digest(WEB_HELPER.replace('__ROOT__',json.dumps(str(ROOT))).encode()),'HELPER_DRIFT')
    services=['platform-pg','fuseki','rustfs'] if modules else (['platform-pg','keycloak-test','api','web','fuseki','rustfs'] if group=='g3' else ['pg-source','platform-pg','keycloak-test','api','web'])
    tag=module_phase if modules else group
    command=compose_command(group)+['up','-d','--no-build','--pull','never',*services]
    import closeout
    before=closeout.inventory(m)
    require(all(not before[k]['owned'] for k in before),'PREEXISTING_RUN_RESOURCE')
    write_json(ARTIFACTS/m['runId']/('resources-'+tag+'-before.json'),before)
    update_runtime(m,modulePhase=module_phase)
    try:
        execute(m,'start-'+tag,command,env=compose_environment(m),timeout=180,sensitive=True)
    finally:
        created=closeout.inventory(m)
        require(all(before[k]['keep']==created[k]['keep'] for k in before),'CREATION_KEEP_DRIFT')
        write_json(ARTIFACTS/m['runId']/('resources-'+tag+'-owned.json'),created)
        resource_snapshot(m,group,'resources-'+tag+'-created')
    wait_pg(m,'platform-pg')
    if group=='m1':wait_pg(m)
    start_ingress(m,tag)
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
        config.update(Semantics={'ValidationOrigin':'http://127.0.0.1:15303/validation','PublishedOrigin':'http://127.0.0.1:15303/ontology'},
            Publishing={'S3Endpoint':'http://127.0.0.1:15900','AccessKey':(d/'s3-access').read_text(),'SecretKey':(d/'s3-secret').read_text(),'Bucket':'g4-main-synthetic'})
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


if __name__ == '__main__':
    try:
        cli()
    except (ValueError, OSError, subprocess.SubprocessError):
        print('REFUSED_RUNTIME_BOUNDARY', file=sys.stderr)
        raise SystemExit(2)
