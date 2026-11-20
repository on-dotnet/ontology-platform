#!/usr/bin/env python3
"""按内容影响规划工程门禁；缺少可信环境/真实执行器时关闭放行。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import uuid
import shutil
import zlib
import signal
import tempfile
import contextlib
import datetime as dt
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
REGISTRY = ROOT / 'docs/development/verification-gates.json'

# 明确每个已准入任务的代表原件布局；范围相对本任务的证据目录。
MEASUREMENT_PATHS = {
    'G4-ORACLE-MAPPING-QUERY-001': ('implementation-01/admission/originals/*.json', 'implementation-01/s0/originals/*.json',
                                    'product-resume-01/originals/login-supplement.json'),
    'G4-M5-INTEGRATION-001': ('**/gates/**/*.json', '**/originals/**/*.json', '**/reports/**/*.json'),
    'G4-DORIS-MAPPING-QUERY-001': (
        '*/s0-*-review.json', '*/s0-*-validation.json', '*/s1/browser-s1-*.json',
        '*/s1/index.json', 'review-fix-01/originals/old-runtime.json.raw.json',
    ),
}



def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


@lru_cache(maxsize=1)
def registry():
    return json.loads(REGISTRY.read_text())['gates']


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def matches(path, patterns):
    def pattern_regex(pattern):
        tokens = re.split(r'(\*\*/|\*\*|\*|\?)', pattern)
        return ''.join({'**/':'(?:.*/)?', '**':'.*', '*':'[^/]*', '?':'[^/]'}.get(t, re.escape(t)) for t in tokens)
    return any(re.fullmatch(pattern_regex(pattern), path) for pattern in patterns)


def select_gates(paths):
    gates = registry()
    direct = {name for name, gate in gates.items() if any(matches(p, gate['inputs']) and not (p in ('apps/web/AGENTS.md','backend/AGENTS.md') and name in ('backend','web','contract','environment','interaction')) for p in paths)}
    unknown = [p for p in paths if not any(matches(p, g['inputs']) for g in gates.values())]
    affected = set(direct)
    while True:
        expanded = affected | {name for name, gate in gates.items() if set(gate['needs']) & affected}
        if expanded == affected: break
        affected = expanded
    return dict(status='BLOCKED' if unknown else 'PLANNED', affected=sorted(affected), unknown=unknown,
                unaffected=sorted(set(gates)-affected))


def input_patterns(name, visited=None):
    visited = set() if visited is None else visited
    if name in visited: return []
    visited.add(name)
    gate = registry()[name]
    return gate['inputs'] + gate.get('identityInputs',[]) + [p for dep in gate['needs'] for p in input_patterns(dep, visited)]


def input_key(root, name):
    paths = set(git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0'))-{''}
    entries = []
    patterns=input_patterns(name)
    for path in sorted(paths):
        if not matches(path, patterns): continue
        p = root/path
        if p.is_symlink(): raise ValueError('INPUT_LINKED: '+path)
        entries.append([path, digest(p.read_bytes()) if p.is_file() else 'DELETED'])
    closure=set()
    input_patterns(name,closure)
    return digest(canonical([{n:registry()[n] for n in sorted(closure)}, entries]))


def committed_input_key(root, name, commit):
    """从原测试提交重算相关源码内容，不能只信回执自报输入键。"""
    patterns=input_patterns(name);entries=[]
    for entry in git(root,'ls-tree','-r','-z',commit).split(b'\0'):
        if not entry: continue
        info,path=entry.split(b'\t',1);path=path.decode()
        if not matches(path,patterns): continue
        mode,kind,oid=info.decode().split()
        if kind!='blob' or mode not in ('100644','100755'): raise ValueError('REUSE_SOURCE_SPECIAL')
        entries.append([path,digest(git(root,'cat-file','blob',oid))])
    closure=set();input_patterns(name,closure)
    return digest(canonical([{n:registry()[n] for n in sorted(closure)},sorted(entries)]))


def reusable(row, key, environment, policy, evidence):
    """当前调用重新检查资格；历史测试绝不标成本轮exit0。"""
    return (row.get('status') == 'PASS' and row.get('exitCode') == 0 and
            type(row.get('tests')) is int and row['tests'] > 0 and row.get('skipped') == 0 and
            row.get('inputKey') == key and row.get('environmentKey') == environment and
            row.get('policyKey') == policy and bool(row.get('sourceRun')) and
            re.fullmatch('[0-9a-f]{40}', row.get('sourceCommit', '')) is not None and
            bool(row.get('command')) and evidence.is_file() and not evidence.is_symlink() and
            digest(evidence.read_bytes()) == row.get('evidenceSha256'))


def safe_file(path):
    p = Path(os.path.abspath(path))
    if any(x.is_symlink() for x in [p, *p.parents]): raise ValueError('LINKED_PATH: '+str(p))
    return p


def state_dir(task):
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}', task): raise ValueError('TASK_INVALID')
    p = safe_file(ROOT/'artifacts/workflow'/task)
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def write(path, value):
    path = safe_file(path)
    with path.open('x', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def prepare(task, inventory=None):
    """同一个任务级适配器供CLI和本地setup调用。"""
    path=ROOT/'scripts/maintenance/workflow_environment.py'
    if not path.is_file(): raise ValueError('IMPLEMENTATION_PENDING: environment adapter')
    spec=importlib.util.spec_from_file_location('workflow_environment',path)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    return adapter.prepare(ROOT,task)


def plan(base, head):
    base=git(ROOT,'rev-parse','--verify',base+'^{commit}').decode().strip()
    head=git(ROOT,'rev-parse','--verify',head+'^{commit}').decode().strip()
    subprocess.run(['git','merge-base','--is-ancestor',base,head],cwd=ROOT,check=True)
    if git(ROOT,'rev-parse','HEAD').decode().strip()!=head: raise ValueError('PLAN_HEAD_NOT_CHECKED_OUT')
    if git(ROOT,'status','--porcelain').strip(): raise ValueError('PLAN_DIRTY: commit the candidate first')
    paths=sorted(set(git(ROOT,'diff','--name-only','--no-renames','-z',base,head).decode().split('\0'))-{''})
    evidence_tasks = sorted({path.split('/')[2] for path in paths if path.startswith('docs/evidence/') and len(path.split('/')) > 3})
    measurements = [measure_committed_evidence(ROOT, base, head, task) for task in evidence_tasks
                    if task in MEASUREMENT_PATHS]

    result=select_gates(paths)
    keys={name:input_key(ROOT,name) for name in registry()}
    if git(ROOT,'status','--porcelain').strip() or git(ROOT,'rev-parse','HEAD').decode().strip()!=head:
        raise ValueError('PLAN_INPUT_CHANGED_DURING_CHECK')
    return dict(schemaVersion=1,base=base,head=head,paths=paths,registrySha256=digest(REGISTRY.read_bytes()),inputKeys=keys,earlyMeasurements=measurements,**result)


def ordered(names):
    result=[]
    visiting=set()
    def visit(name):
        if name in result: return
        if name in visiting: raise ValueError('GATE_CYCLE')
        visiting.add(name)
        for dep in registry()[name]['needs']:
            if dep in names: visit(dep)
        visiting.remove(name)
        result.append(name)
    for name in sorted(names): visit(name)
    return result


def test_counts(text, kind):
    """读取真实测试框架摘要，缺摘要不把exit0解释为测试成功。"""
    node_tests = node_skips = 0
    if kind == 'engineering-full':
        # StructuredFiles.Tests.ps1 在正例之间逐次断言这三个子命令 exit 1。
        # 只认整段有序实测输出，孤立、重复或位置异常的 FAIL 继续交由通用规则拒绝。
        valid = 'PASS: YAML/TOML syntax, 1 files; runtime compatibility not implied.'
        bad_compose = 'FAIL: structured syntax infra/oracle/compose.mapping-query.yaml (ConstructorError)'
        structured = '\n'.join((valid,
            'EXPECTED-REJECTION: FAIL: structured syntax invalid.yml (ParserError)',
            'EXPECTED-REJECTION: FAIL: structured syntax invalid.toml (TOMLDecodeError)',
            valid, valid, bad_compose, bad_compose, 'FAIL: structured syntax valid.yml (ConstructorError)', valid,
            'PASS: structured parser 10 real positive/negative cases.'))
        text = '\n'.join(text.splitlines())
        pattern = r'(?m)^' + re.escape(structured) + '$'
        if len(re.findall(pattern, text)) == 1:
            text = re.sub(pattern, 'StructuredFiles: three expected parser rejections checked.', text)
        # Node 在本机使用 spec 渲染，CI 也可产生 TAP 格式；两者均保留未执行的条目。
        node = re.findall(r'(?m)^(?:ℹ|#) (tests|suites|pass|fail|cancelled|skipped|todo) (\d+)$', text)
        if node:
            summary = {name:int(count) for name,count in node}
            if len(node) != 7 or set(summary) != {'tests','suites','pass','fail','cancelled','skipped','todo'}:
                return 0,0
            node_skips = summary['skipped'] + summary['todo']
            if summary['fail'] or summary['cancelled'] or summary['tests'] != summary['pass'] + node_skips:
                return 0,node_skips
            node_tests = summary['tests']
    if re.search(r'(?m)^(?:FAILED|FAIL:|ERROR:)|(?:failures|errors)=[1-9]',text):return 0,0
    counts=[int(x) for x in re.findall(r'Ran (\d+) tests? in',text)]
    skips=[int(x) for x in re.findall(r'skipped=(\d+)',text)]
    package=re.search(r'ReviewPackage: (\d+) tests, (\d+) failures, (\d+) platform cases NOT_RUN',text)
    if package:
        if int(package[2]): return 0,int(package[3])
        counts.append(int(package[1]));skips.append(int(package[3]))
    return sum(counts) + node_tests, sum(skips) + node_skips


def engineering_environment():
    tools={}
    for name in ('python3','pwsh','git'):
        path=shutil.which(name)
        if not path: raise ValueError('TOOL_MISSING: '+name)
        tools[name]=digest(Path(path).resolve().read_bytes())
    parser_root=safe_file(ROOT/'.tools/pythonlibs')
    parser_files={}
    if parser_root.is_dir():
        for p in sorted(parser_root.rglob('*')):
            safe_file(p)
            if p.is_file(): parser_files[str(p.relative_to(parser_root))]=digest(p.read_bytes())
    return digest(canonical([platform.system(),platform.release(),platform.machine(),tools,parser_files]))


def policy_key(name='engineering'):
    closure=set()
    input_patterns(name,closure)
    return digest(canonical([{n:registry()[n] for n in sorted(closure)},
        digest((ROOT/'scripts/maintenance/workflow.py').read_bytes()),
        digest((ROOT/'scripts/maintenance/execution_preflight.py').read_bytes()),
        digest((ROOT/'docs/development/local-validation-policy.md').read_bytes())]))


def load_reuse(index, gate, key, environment, policy):
    """原回执及原日志必须从同一精确Git提交恢复并重新核验。"""
    if gate not in index: return None
    ref=index[gate]
    commit=ref['commit'];path=ref['path']
    if not re.fullmatch('[0-9a-f]{40}',commit) or not re.fullmatch(r'docs/evidence/[A-Za-z0-9_./-]+\.json',path) or '..' in path.split('/'):
        raise ValueError('REUSE_REFERENCE_INVALID')
    row=json.loads(git(ROOT,'show',commit+':'+path))
    log_path=row['logPath']
    if not log_path.startswith(str(Path(path).parent)+'/') or '..' in log_path.split('/'):
        raise ValueError('REUSE_LOG_BOUNDARY')
    log=git(ROOT,'show',commit+':'+log_path)
    if row.get('publishedLog',{}).get('encoding')=='base64':
        import base64
        envelope=json.loads(log);log=base64.b64decode(envelope['base64'],validate=True)
        if digest(log)!=envelope['sha256']:raise ValueError('REUSE_ENVELOPE_HASH')
    tests,skips=test_counts(log.decode(errors='replace'),gate)
    valid=(row.get('inputsUnchanged') is True and row.get('status')=='PASS' and row.get('exitCode')==0 and tests>0 and skips==0 and
           row.get('tests')==tests and row.get('skipped')==skips and row.get('gate')==gate and
           row.get('inputKey')==key and row.get('environmentKey')==environment and row.get('policyKey')==policy and
           row.get('command')==registry()[gate]['command'] and row.get('evidenceSha256')==digest(log) and
           re.fullmatch('[0-9a-f]{40}',row.get('sourceCommit','')) is not None and bool(row.get('sourceRun')))
    if not valid: raise ValueError('REUSE_INELIGIBLE: '+gate)
    subprocess.run(['git','merge-base','--is-ancestor',row['sourceCommit'],commit],cwd=ROOT,check=True,capture_output=True)
    if committed_input_key(ROOT,gate,row['sourceCommit'])!=key: raise ValueError('REUSE_SOURCE_INPUT_MISMATCH')
    return dict(gate=gate,status='PASS',executionMode='REUSED',sourceCommit=row['sourceCommit'],
                sourceRun=row['sourceRun'],evidenceCommit=commit,evidencePath=path,evidenceSha256=digest(log),
                inputKey=key,reason='Immutable original success, identical input/environment/policy',
                qualificationCommand='workflow.py verify --plan <current controlled plan> --reuse <index>')


def verification_deadline(affected, diagnostic=False):
    """串行 gate 各有自己的执行预算和至多 10 秒回收；规划、签收另留有界时间。"""
    gate_seconds = 20 if diagnostic else 1800
    return 180 + len(affected) * (gate_seconds + 10)


def selftest_resources(root, admission_path, temporary):
    """从已完成的当前封闭准入重计工程阶段。工作树和压测以外的原账本项目逐项保留。"""
    task = 'G4-ORACLE-MAPPING-QUERY-001'
    area = root / 'artifacts/workflow' / task
    path = safe_file(admission_path)
    if path.parent != area / 's0-recovery-01' or not re.fullmatch(r'source-admission-[0-9a-f]{32}\.json', path.name):
        raise ValueError('SELFTEST_RESOURCE_ADMISSION_PATH')
    raw = path.read_bytes()
    admission = json.loads(raw)
    if (admission['taskId'], admission['runId'], admission['phase'], admission['status']) != (
            task, 's0-recovery-01', 'closed', 'FORMAL_RESOURCE_READY') or admission['expectedRunningRoles'] != [] or (
            admission['probeRemoved'] is not True or path.stem != 'source-admission-' + admission['attempt']):
        raise ValueError('SELFTEST_RESOURCE_ADMISSION_SCOPE')
    disk = admission['platformDisk']
    allocations = disk['allocations']
    gib = 1024**3
    if sum(allocations.values()) != disk['totalBytes'] or disk['ceilingBytes'] != 40 * gib:
        raise ValueError('SELFTEST_RESOURCE_LEDGER')
    # 55,256 个真实非空文件不能按三个逻辑字节计。以临时卷的实配单位、五个 PNG 集合
    # （工作文件、Git blob、V2 归档、V3 归档及暂存）、清单/目录/Git 辅助文件保守计费。
    temporary = safe_file(temporary)
    fragment = os.statvfs(temporary).f_frsize
    ignored = 55256 * fragment
    image = ((800 * (256 * 3 + 1) + 4096 + fragment - 1) // fragment) * fragment
    package_copies = 53 * 5 * image
    overhead = 32 * 1024**2
    temp_bytes = ignored + package_copies + overhead
    credit = min(temp_bytes, allocations['newBuildEvidenceAndLogs'])
    total = disk['totalBytes'] - credit + temp_bytes
    # 完整静态检查保留 JSON 解析结果。采用本候选实际 JSON 大小估算；采样夹具的父/子进程
    # RSS 约 243 MiB，再预留一个同体积的 PowerShell 子进程、解压缓冲和 Git 对象。
    names = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0')
    files = [root / name.decode() for name in names if name.endswith(b'.json')]
    json_bytes = sum(p.stat().st_size for p in files if p.is_file())
    ram_estimate = 8 * json_bytes + 512 * 1024**2 + 2 * 53 * image
    host_free = min(admission['host']['diskBytes'], shutil.disk_usage(root).free, shutil.disk_usage(temporary).free)
    if (total > disk['ceilingBytes'] or host_free < temp_bytes + 10 * gib or admission['vm']['availableFs'] < 10 * gib or
            admission['host']['availableEstimate'] < ram_estimate + 4 * gib):
        raise ValueError(f'SELFTEST_RESOURCE_HEADROOM: taskBytes={total} scratchBytes={temp_bytes} hostRssEstimate={ram_estimate}')
    return dict(admission=admission['attempt'], admissionSha256=digest(raw), measuredUtc=admission['endedUtc'],
                tempPath=str(temporary), tempDevice=temporary.stat().st_dev, allocationUnit=fragment,
                ignoredFileAllocation=ignored, pngAndCopyAllowance=package_copies, directoryAndToolAllowance=overhead,
                temporaryPeakBytes=temp_bytes, existingBuildReserveCredit=credit, projectedTaskBytes=total,
                taskCeilingBytes=disk['ceilingBytes'], currentHostDiskFree=host_free, hostJsonInputBytes=json_bytes,
                hostRssEstimateBytes=ram_estimate, hostAvailableAtAdmission=admission['host']['availableEstimate'],
                additionalVmServices=0, childDeadlineSeconds=1800, commandCleanupSeconds=10)


def execute_gate(command, root, timeout=None, environment=None, *, task='WORKFLOW', run_id=None, input_key=None, environment_key=None):
    """一般工程入口复用公共执行器；合并输出仅为兼容展示，原件双流独立保留。"""
    from workflow_execution import run
    args = [str(part) for part in command]
    if '--plan' in args and 'verify' in args and any((root / arg).resolve() == Path(__file__).resolve() for arg in args if arg.endswith('workflow.py')):
        plan_file = root / args[args.index('--plan') + 1]
        affected = json.loads(safe_file(plan_file).read_bytes())['affected']
        selected = ['engineering-full'] if '--selftest-only' in args else affected
        budget = verification_deadline(selected, '--diagnostic' in args)
        if timeout is not None and timeout < budget:
            raise ValueError(f'VERIFY_OUTER_DEADLINE: supplied={timeout} required={budget}')
        timeout = budget if timeout is None else timeout
        environment = dict(os.environ if environment is None else environment, WORKFLOW_VERIFY_DEADLINE=str(time.monotonic() + timeout))
    timeout = 1800 if timeout is None else timeout
    result=run(command,root,task=task,run_id=run_id,input_key=input_key,environment_key=environment_key,timeout=timeout,environment=environment)
    return result.returncode,result.stdout+result.stderr


def error_signature(raw, code):
    text=raw.decode(errors='replace')
    cases=sorted(set(re.findall(r'(?:FAIL|ERROR): ([A-Za-z0-9_.]+)',text)))
    categories=sorted(set(re.findall(r'\b([A-Z][A-Z0-9_]{4,})(?=:)',text)))
    if cases or categories: return digest(canonical([code,cases,categories]))
    lines=[line for line in text.splitlines() if re.search(r'error|failed|exception',line,re.I)]
    normalized=re.sub(r'(?<!\w)/[^\s]+','<path>','\n'.join(lines[-5:]))
    normalized=re.sub(r'\b[0-9a-f]{16,}\b','<hash>',normalized)
    normalized=re.sub(r'\d+(?:\.\d+)?','<number>',normalized)
    return digest(canonical([code,normalized or 'COMMAND_FAILED']))


def record_timing(directory, task, run, name, key, start, elapsed, code):
    spec=importlib.util.spec_from_file_location('task_run_timeline',ROOT/'scripts/maintenance/task_run_timeline.py')
    timeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(timeline)
    row=dict(schemaVersion=2,timingStatus='VALID',taskId=task,runId=run,stepId=name,taskType='TEST',
             inputFingerprint=key,startedAtUtc=start,endedAtUtc=start,durationMs=0,outcome='PASS',
             errorCategory=None,dependsOn=[],concurrencyGroup='workflow',attempt=1,exitCode=0,commandLabel=name)
    row=timeline.complete(row,dt.datetime.now(dt.timezone.utc).isoformat(),round(elapsed*1000),code)
    timeline.append(directory/'timeline.jsonl',row,assign_attempt=True)


def inputs_stable(root, name, key, policy, registry_sha):
    """登记原字节另行比较，缓存不能掩盖命令执行期间的政策变化。"""
    return digest(REGISTRY.read_bytes())==registry_sha and input_key(root,name)==key and policy_key(name)==policy


def engineering_process_environment(task):
    directory=state_dir(task)
    # 工程门禁不触发.NET/Web准备；缺工具由对应命令准确失败。
    child_environment={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','SystemRoot')}
    child_environment.update(PYTHONDONTWRITEBYTECODE='1',NEXT_TELEMETRY_DISABLED='1',PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
    parser_root=safe_file(ROOT/'.tools/pythonlibs')
    if parser_root.is_dir(): child_environment['PYTHONPATH']=str(parser_root)
    cli=directory/'engineering-cli-home';cli.mkdir(exist_ok=True)
    child_environment.update(DOTNET_CLI_HOME=str(cli),DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',DOTNET_GENERATE_ASPNET_CERTIFICATE='false',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true')
    return child_environment


def write_gate_output(directory, name, raw):
    # 可交付命令文本保持原字节，使用既有V3允许的文本格式。
    output=directory/(name+'.txt');output.write_bytes(raw);os.chmod(output,0o600)
    return output


def validate_package_paths(root, paths):
    # 直接复用构包器的路径边界，预检不能维护一份会漂移的放行规则。
    command=". ./scripts/create-review-package.ps1 -Library; try { foreach ($p in ([Console]::In.ReadToEnd() | ConvertFrom-Json)) { Assert-ReviewPath $p } } catch { exit 1 }"
    result=subprocess.run(['pwsh','-NoProfile','-Command',command],cwd=root,input=json.dumps(paths),text=True,capture_output=True)
    if result.returncode: raise ValueError('PACKAGE_PATH_REJECTED: existing V3 path policy; values suppressed')


def verify(task, path, reuse=None, publish=False, diagnostic=False, hypothesis=None, engineering_admission=None, selftest_only=False):
    expected=json.loads(safe_file(path).read_text())
    if selftest_only and ('engineering-full' not in expected['affected'] or diagnostic or reuse):
        raise ValueError('SELFTEST_ONLY_REQUIRES_AFFECTED_FULL_GATE')
    selected = ['engineering-full'] if selftest_only else expected['affected']
    outer_seconds = verification_deadline(selected, diagnostic)
    deadline = time.monotonic() + outer_seconds
    if 'WORKFLOW_VERIFY_DEADLINE' in os.environ:
        deadline = min(deadline, float(os.environ['WORKFLOW_VERIFY_DEADLINE']))
    actual=plan(expected['base'],expected['head'])
    if expected != actual or actual['head'] != git(ROOT,'rev-parse','HEAD').decode().strip():
        raise ValueError('PLAN_STALE_OR_TAMPERED')
    if actual['status'] != 'PLANNED': raise ValueError('UNMAPPED_INPUTS: '+','.join(actual['unknown']))
    index=json.loads(safe_file(reuse).read_text()) if reuse else {}
    if not isinstance(index,dict): raise ValueError('REUSE_INDEX_INVALID')
    directory=state_dir(task)
    run=directory/'runs'/uuid.uuid4().hex
    run.mkdir(parents=True,mode=0o700)
    spec=importlib.util.spec_from_file_location('execution_preflight',ROOT/'scripts/maintenance/execution_preflight.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    environment=engineering_environment()
    child_environment=engineering_process_environment(task)
    rows=[];outcomes={}
    for name in ordered(set(selected) | set(index)):
        if digest(REGISTRY.read_bytes())!=actual['registrySha256']: raise ValueError('REGISTRY_CHANGED_DURING_RUN')
        gate=registry()[name];key=actual['inputKeys'][name];policy=policy_key(name)
        if name=='policy':
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_context.py','--root',str(ROOT),'--check','--task',task,'--base',actual['base'],'--head',actual['head']]}
        if any(outcomes.get(dep) not in (None,'PASS') for dep in gate['needs']):
            rows.append(dict(gate=name,status='NOT_RUN',reason='Upstream failed or unavailable'));outcomes[name]='NOT_RUN';continue
        mapping_qualification=not gate['command'] and task == 'G4-M3-MAPPING-001' and name in {'environment','contract','backend','web','interaction'}
        product_qualification=not gate['command'] and task in ('G4-M2-WEB-01','G4-ENG-DELIVERY-002','G4-M2-DORIS-01','G4-M2-ORACLE-01') and name in {'environment','contract','backend','web','interaction'}
        if not gate['command'] and task in ('G4-M2-WEB-01','G4-ENG-DELIVERY-002','G4-M2-DORIS-01','G4-M2-ORACLE-01') and name in {'environment','contract','backend','web','interaction'}:
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_m2_evidence.py','--task',task,'--gate',name,'--input-key',key],'testsRequired':True}
        if mapping_qualification:
            product_qualification=True
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_m3_mapping.py','qualify','--task',task,'--run-id','mapping-impl-01','--gate',name,'--input-key',key],'testsRequired':True}
        if not gate['command'] and task == 'G4-M4-QUERY-001' and name in {'environment','contract','backend','web','interaction'}:
            product_qualification=True
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_m4_query.py','qualify','--task',task,'--run-id','query-impl-01','--gate',name,'--input-key',key],'testsRequired':True}
        if not gate['command'] and task == 'G4-DORIS-MAPPING-QUERY-001' and name in {'environment','contract','backend','web','interaction'}:
            product_qualification=True
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_doris_mapping_evidence.py','--gate',name,'--input-key',key],'testsRequired':True}
        if not gate['command'] and task == 'G4-ORACLE-MAPPING-QUERY-001' and name in {'environment','contract','backend','web','interaction'}:
            product_qualification=True
            gate={**gate,'command':['python3','-B','scripts/maintenance/workflow_oracle_mapping_evidence.py',
                  '--task',task,'--run-id','implementation-01','--gate',name,'--input-key',key],'testsRequired':True}
        if not gate['command'] and task == 'G4-M5-INTEGRATION-001' and name in {'environment','contract','backend','web','interaction'}:
            # M5复用同一原件解释器；固定消费者身份，不把缺适配器的空命令当通过。
            product_qualification=True
            gate={**gate,'command':['python3','-B','-c',
                "import sys,json;sys.path.insert(0,'scripts/maintenance');import workflow_m5_integration as consumer;print(json.dumps(consumer.qualify(sys.argv[1],sys.argv[2])))",
                name,key],'testsRequired':True}
        if not gate['command']:
            rows.append(dict(gate=name,status='NOT_RUN',reason='Product gate requires task-specific admitted executor'))
            outcomes[name]='NOT_RUN';continue
        previous_failures=[]
        for old in sorted([*(directory/'runs').glob('*/'+name+'.json'),*(directory/'runs').glob('*/'+name+'.state.json')], key=lambda p:p.stat().st_mtime):
            prior=json.loads(safe_file(old).read_text())
            if prior.get('status')=='PASS': previous_failures=[]
            elif prior.get('status')=='FAIL': previous_failures.append(prior)
        chain=previous_failures[-3:]
        if len(chain)==3 and len({(r.get('errorSignature'),r.get('environmentKey')) for r in chain})==1 and not diagnostic:
            if not hypothesis or chain[-1]['inputKey']==key:
                raise ValueError('THREE_REPAIR_FAILURES: run short diagnosis; changed input plus --hypothesis required for '+name)
        with helper.FailureState(directory/'failures.json',digest(canonical([key,environment,policy])),name,policy) as guard:
            cost='short' if diagnostic or product_qualification else 'expensive'
            guard.allow(cost)
            previous=None if diagnostic or product_qualification else load_reuse(index,name,key,environment,policy)
            if previous:
                rows.append(previous);outcomes[name]='PASS';continue
            if name not in actual['affected']: continue
            start=time.monotonic();started=dt.datetime.now(dt.timezone.utc).isoformat()
            child_seconds = 20 if diagnostic else 1800
            if deadline - time.monotonic() < child_seconds + 10:
                raise ValueError('VERIFY_INSUFFICIENT_REMAINING_FOR_CHILD_AND_CLEANUP: ' + name)
            resource_receipt = None
            gate_environment = child_environment
            with contextlib.ExitStack() as temporary_resources:
                if name == 'engineering-full' and task == 'G4-ORACLE-MAPPING-QUERY-001':
                    if engineering_admission is None:
                        raise ValueError('SELFTEST_CURRENT_CLOSED_ADMISSION_REQUIRED: supply --engineering-admission from the current measured window')
                    # Git 在未初始化的夹具内不得向上发现真实工作树。使用准确 OS 临时卷计费。
                    temp_base = Path(tempfile.gettempdir()).resolve()
                    if temp_base.is_relative_to(ROOT):
                        raise ValueError('SELFTEST_TMP_INSIDE_REPOSITORY')
                    temporary = Path(temporary_resources.enter_context(tempfile.TemporaryDirectory(prefix='ontology-full-',dir=temp_base)))
                    resource_receipt = selftest_resources(ROOT, engineering_admission, temporary)
                    write(run / 'selftest-resource.json', resource_receipt)
                    gate_environment = {**child_environment, **{k:str(temporary) for k in ('TMPDIR','TMP','TEMP')}}
                code,raw=execute_gate(gate['command'],ROOT,child_seconds,gate_environment,task=task,run_id=run.name,input_key=key,environment_key=environment)
            elapsed=time.monotonic()-start
            record_timing(directory,task,run.name,name,key,started,elapsed,code)
            tests,skipped=test_counts(raw.decode(errors='replace'),name)
            product_proof={}
            if product_qualification and code==0:
                product_proof=json.loads(raw)
                if product_proof.get('status')!='PASS' or product_proof.get('executionMode')!='REUSED':raise ValueError('PRODUCT_QUALIFICATION_INVALID')
                tests=product_proof['tests'];skipped=product_proof['skipped']
            inputs_unchanged=inputs_stable(ROOT,name,key,policy,actual['registrySha256'])
            passed=code==0 and inputs_unchanged and (not gate.get('testsRequired') or tests>0 and skipped==0)
            guard.record(cost,code if code else (0 if passed else 65))
            evidence_dir=run
            published_dir=safe_file(ROOT/'docs/evidence'/task/'gates'/run.name) if publish else run
            log=write_gate_output(evidence_dir,name,raw)
            row=dict(gate=name,status='PASS' if passed else 'FAIL',executionMode='REUSED' if product_qualification else 'FRESH',qualificationMode='FRESH',productProof=product_proof,
                command=gate['command'],exitCode=code,tests=tests,skipped=skipped,diagnostic=diagnostic,hypothesis=hypothesis,inputsUnchanged=inputs_unchanged,
                errorSignature=error_signature(raw,code) if not passed else None,
                elapsedSeconds=elapsed,inputKey=key,environmentKey=environment,policyKey=policy,
                evidenceSha256=digest(raw),logPath=str((published_dir/log.name).relative_to(ROOT)),sourceRun=run.name,sourceCommit=actual['head'])
            if resource_receipt is not None:
                row['resourceAdmission'] = resource_receipt
            write(evidence_dir/(name+'.json'),row);
            rows.append(row);outcomes[name]=row['status']
            if not passed: break
    result=dict(status='PASS' if rows and all(x['status']=='PASS' for x in rows) else 'BLOCKED',
                coverage='explicit full engineering SelfTest only' if selftest_only else 'affected engineering gates only; product coverage requires separate task acceptance',checks=rows)
    # 全部命令结束才发布，证据输出不能污染同轮后续gate的输入。
    if publish:
        target=safe_file(ROOT/'docs/evidence'/task/'gates'/run.name);target.mkdir(parents=True)
        for row in rows:
            if row.get('executionMode')!='FRESH' and row.get('qualificationMode')!='FRESH': continue
            from workflow_evidence import publish as publish_raw
            record=publish_raw(ROOT,str((target/(row['gate']+'.txt')).relative_to(ROOT)),(run/(row['gate']+'.txt')).read_bytes())
            row['publishedLog']=record;row['logPath']=record['path']
            write(target/(row['gate']+'.json'),row)
            write(run/(row['gate']+'.state.json'),{k:row[k] for k in ('status','inputKey','environmentKey','errorSignature')})
    if publish and task in MEASUREMENT_PATHS:
        result['earlyMeasurement'] = dict(status='NOT_READY', reason='New evidence awaits candidate commit; workflow plan automatically measures that committed candidate', representativePaths=[row.get('logPath') for row in rows])
    write(run/'receipt.json',result)
    return result


def measure_committed_evidence(root, base, head, task):
    """归档后首次计划自动精测当前已提交证据；使用生产构包器且不宣称验收。"""
    from workflow_execution import run
    import inspect
    from types import SimpleNamespace
    protocol_version = 1
    patterns = MEASUREMENT_PATHS[task]
    prefix = 'docs/evidence/' + task + '/'
    changed = git(root, 'diff', '--name-only', '--diff-filter=ACMRT', '-z', base, head, '--', prefix).decode().split('\0')
    candidate_paths = sorted(path for path in changed if path.startswith(prefix) and matches(path[len(prefix):], patterns))
    if not candidate_paths:
        return dict(status='NOT_READY', reason='No newly committed representative matched the registered paths', expectedPaths=list(patterns))
    directory = root/'artifacts/workflow'/task/'package-measurements'
    directory.mkdir(parents=True, exist_ok=True)
    identity = digest(canonical([base, head, candidate_paths, patterns, protocol_version,
                                digest(inspect.getsource(measure_committed_evidence).encode()),
                                digest((root/'scripts/create-review-package.ps1').read_bytes())]))
    path = directory/(identity+'.json')
    cached = path.exists()
    if cached:
        previous = json.loads(path.read_text())
        if (previous.get('base'), previous.get('head'), previous.get('measurementProtocolVersion')) != (base, head, protocol_version):
            raise ValueError('MEASUREMENT_CACHE_IDENTITY')
        streams = {}
        for stream in ('stdout', 'stderr'):
            original = previous['commandReceipt'][stream]
            streams[stream] = safe_file(original['path']).read_bytes()
            if digest(streams[stream]) != original['sha256'] or len(streams[stream]) != original['sizeBytes']:
                raise ValueError('MEASUREMENT_ORIGINAL_DRIFT')
        # 缓存只复用已核原始双流；每次重新解释生产协议，不能信任缓存中的解析结论。
        result = SimpleNamespace(stdout=streams['stdout'], returncode=previous['commandReceipt']['exitCode'], receipt=previous['commandReceipt'])
    else:
        result = run(['pwsh', '-NoProfile', '-File', 'scripts/create-review-package.ps1', '-Root', str(root),
                      '-BaseSha', base, '-HeadSha', head, '-TaskId', task, '-Status', 'NOT_RUN', '-MeasureOnly',
                      '-MeasurementPathsJson', json.dumps(candidate_paths, separators=(',', ':'))],
                     root, task=task, stage='early-package-measurement', timeout=180)
    row = dict(status='BLOCKED', base=base, head=head, representativePaths=candidate_paths,
               commandId=result.receipt['commandId'], exitCode=result.receipt['exitCode'], commandReceipt=result.receipt,
               measurementProtocolVersion=protocol_version)
    if not result.stdout and result.returncode == 0:
        raise ValueError('MEASUREMENT_PROTOCOL_INVALID')
    if result.stdout:
        measurement = json.loads(result.stdout)
        if measurement.get('measurement') != 'EXACT_CANDIDATE':
            raise ValueError('MEASUREMENT_PROTOCOL_INVALID')
        if measurement.get('measurement') == 'EXACT_CANDIDATE':
            description = measurement.get('representativeEvidence', {})
            if (measurement.get('baseSha'), measurement.get('headSha'), description.get('protocolVersion'),
                description.get('taskId'), description.get('baseSha'), description.get('headSha')) != (base, head, protocol_version, task, base, head):
                raise ValueError('MEASUREMENT_IDENTITY_INVALID')
            members = measurement.get('members')
            logical = description.get('sourceMembers')
            payloads = description.get('payloads')
            if not isinstance(members, list) or any(not isinstance(name, str) for name in members) or len(set(members)) != len(members) or not isinstance(logical, list) or not isinstance(payloads, list):
                raise ValueError('MEASUREMENT_MAPPING_INVALID')
            sources = {}
            for source in logical:
                if not isinstance(source, dict) or set(source) != {'gitPath', 'archivePath', 'blobOid', 'sha256', 'sizeBytes'} or not isinstance(source['gitPath'], str) or source['gitPath'] in sources:
                    raise ValueError('MEASUREMENT_MAPPING_INVALID')
                sources[source['gitPath']] = source
            if set(sources) != set(candidate_paths):
                raise ValueError('EARLY_REPRESENTATIVE_NOT_INCLUDED')
            actual = {}
            for payload in payloads:
                if not isinstance(payload, dict) or set(payload) != {'archivePath', 'sha256', 'sizeBytes'} or not isinstance(payload['archivePath'], str) or payload['archivePath'] in actual:
                    raise ValueError('MEASUREMENT_PAYLOAD_INVALID')
                actual[payload['archivePath']] = payload
            referenced = set()
            for name in candidate_paths:
                source = sources[name]
                raw = git(root, 'cat-file', 'blob', head+':'+name)
                blob = git(root, 'rev-parse', head+':'+name).decode().strip()
                if source['blobOid'] != blob or source['sha256'] != digest(raw) or type(source['sizeBytes']) is not int or source['sizeBytes'] != len(raw):
                    raise ValueError('MEASUREMENT_SOURCE_INVALID')
                archive = source['archivePath']
                if not isinstance(archive, str) or archive not in members or archive not in actual:
                    raise ValueError('MEASUREMENT_PAYLOAD_MISSING')
                payload = actual[archive]
                if payload['sha256'] != source['sha256'] or type(payload['sizeBytes']) is not int or payload['sizeBytes'] != len(raw):
                    raise ValueError('MEASUREMENT_PAYLOAD_INVALID')
                referenced.add(archive)
            if set(actual) != referenced:
                raise ValueError('MEASUREMENT_PAYLOAD_INVALID')
            row['measurement'] = measurement
            budget_path = 'docs/evidence/'+task+'/entry-fix-01/measurement-growth-budget.json'
            budget_exists = git(root, 'ls-tree', '--name-only', head, '--', budget_path).decode().strip()
            if budget_exists:
                budget = json.loads(git(root, 'show', head+':'+budget_path))
                if budget['taskId'] != task or budget['base'] != base:
                    raise ValueError('MEASUREMENT_GROWTH_IDENTITY')
                categories = budget['categories']
                if not isinstance(categories, list) or not categories or any(not entry.get('basis') for entry in categories):
                    raise ValueError('MEASUREMENT_GROWTH_INVALID')
                values = [budget['metadataReserveBytes'], budget['safetyReserveBytes']]
                values += [entry[key] for entry in categories for key in ('remainingCount', 'reservedBytesEach')]
                if any(type(value) is not int or value < 0 for value in values):
                    raise ValueError('MEASUREMENT_GROWTH_INVALID')
                reserved = sum(entry['remainingCount'] * entry['reservedBytesEach'] for entry in categories) + sum(values[:2])
                row['growthBudget'] = budget
                row['projectedUpperBytes'] = measurement['sizeBytes'] + reserved
                row['sizeAdmission'] = 'WITHIN_RESERVED_BUDGET' if row['projectedUpperBytes'] <= 15*1024**2 else 'BLOCKED_BY_RESERVED_BUDGET'
            else:
                row['sizeAdmission'] = 'UNKNOWN_REMAINING_EVIDENCE_BUDGET'
    if result.returncode == 0:
        row['status'] = 'MEASURED_NOT_READY_FOR_ACCEPTANCE'
    if not cached:
        write(path, row)
    return row


def package_budget(root, base, head, task):
    """逐blob压缩估算，不制造中间ZIP；最终大小仍由生产构包器强验。"""
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}',task): raise ValueError('TASK_INVALID')
    for ref in (base,head):
        if not re.fullmatch('[0-9a-f]{40}',ref): raise ValueError('FULL_COMMIT_REQUIRED')
    result=subprocess.run(['pwsh','-NoProfile','-File',str(root/'scripts/create-review-package.ps1'),
                           '-Root',str(root),'-BaseSha',base,'-HeadSha',head,'-TaskId',task,
                           '-Status','NOT_RUN','-MemberPlan'],cwd=root,capture_output=True,timeout=180)
    if result.returncode: raise ValueError('PACKAGE_MEMBER_PLAN_REJECTED: '+result.stderr.decode(errors='replace')[-1000:])
    plan=json.loads(result.stdout)
    plan.update(base=base,head=head,taskId=task,explainComposition=plan['estimatedZipBytes']>10*1024*1024,
                selector='production Get-ReviewSnapshot')
    return plan


def package_check(task, base, head, evidence):
    result=package_budget(ROOT,base,head,task)
    if result['status']=='NEEDS_EXACT_MEASUREMENT' and evidence:
        measured=subprocess.run(['pwsh','-NoProfile','-File','scripts/create-review-package.ps1','-Root',str(ROOT),
            '-BaseSha',base,'-HeadSha',head,'-TaskId',task,'-Status','PASS','-EvidencePath',str(evidence),'-MeasureOnly'],
            cwd=ROOT,capture_output=True,timeout=180)
        if measured.returncode: result['status']='BLOCKED'
        else:
            result['exactCandidate']=json.loads(measured.stdout)
            result['status']=result['exactCandidate']['status']

    paths=set(git(ROOT,'ls-tree','-r','--name-only','-z',head).decode().split('\0'))
    paths.update(git(ROOT,'diff','--name-only','-z','--no-renames',base,head,'--').decode().split('\0'))
    validate_package_paths(ROOT,sorted(paths-{''}))
    result['pathPolicy']='PASS: existing V3 rules'
    code,_=execute_gate(['pwsh','-NoProfile','-File','scripts/verify.ps1'],ROOT,environment=engineering_process_environment(task),task=task)
    result['formatExitCode']=code
    if code: result['status']='BLOCKED'
    if evidence:
        code,_=execute_gate(['pwsh','-NoProfile','-File','scripts/test-review-evidence.ps1',
                             '-EvidenceFile',str(safe_file(evidence)),'-ExpectedHead',head],ROOT,environment=engineering_process_environment(task),task=task)
        result['evidenceSchemaExitCode']=code
        if code: result['status']='BLOCKED'
    else:
        result.update(status='BLOCKED',evidenceSchema='NOT_RUN: supply --evidence before final acceptance')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    ctx=sub.add_parser('context');ctx.add_argument('--mode',choices=['code','evidence'],default='code');ctx.add_argument('--task');ctx.add_argument('--query')
    prep=sub.add_parser('prepare');prep.add_argument('--task',required=True);prep.add_argument('--inventory')
    smoke=sub.add_parser('smoke');smoke.add_argument('--task',required=True)
    pl=sub.add_parser('plan');pl.add_argument('--base',required=True);pl.add_argument('--head',required=True);pl.add_argument('--output',required=True)
    ve=sub.add_parser('verify');ve.add_argument('--task',required=True);ve.add_argument('--plan',required=True);ve.add_argument('--reuse');ve.add_argument('--publish-evidence',action='store_true');ve.add_argument('--diagnostic',action='store_true');ve.add_argument('--hypothesis');ve.add_argument('--engineering-admission');ve.add_argument('--estimate-deadline',action='store_true');ve.add_argument('--selftest-only',action='store_true')
    pc=sub.add_parser('package-check');pc.add_argument('--task',required=True);pc.add_argument('--base',required=True);pc.add_argument('--head',required=True);pc.add_argument('--evidence')
    cl=sub.add_parser('closeout');cl.add_argument('--task',required=True);cl.add_argument('--dry-run',action='store_true',required=True)
    args=p.parse_args()
    try:
        if args.action=='context':
            from workflow_context import context
            result=context(ROOT,args.mode,args.task,args.query)
        elif args.action=='prepare': result=prepare(args.task,args.inventory)
        elif args.action=='plan':
            result=plan(args.base,args.head);write(Path(args.output),result)
        elif args.action=='verify':
            if args.estimate_deadline:
                expected=json.loads(safe_file(args.plan).read_bytes())
                selected=['engineering-full'] if args.selftest_only else expected['affected']
                result=dict(status='PLANNED',outerDeadlineSeconds=verification_deadline(selected,args.diagnostic))
            else:
                result=verify(args.task,args.plan,args.reuse,args.publish_evidence,args.diagnostic,args.hypothesis,args.engineering_admission,args.selftest_only)
        elif args.action=='smoke':
            path=ROOT/'scripts/maintenance/workflow_smoke.py'
            if not path.is_file(): raise ValueError('IMPLEMENTATION_PENDING: smoke adapter')
            spec=importlib.util.spec_from_file_location('workflow_smoke',path)
            adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
            prepared=prepare(args.task)
            result=adapter.smoke(ROOT,args.task,node=prepared['node'])
        elif args.action=='package-check': result=package_check(args.task,args.base,args.head,args.evidence)
        else:
            directory=state_dir(args.task)
            result=dict(status='DRY_RUN',resources=[dict(path=str(directory),decision='KEEP',reason='active task cache/evidence',release='reviewed CLOSED and exact approved cleanup')],deleted=0)
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result['status'] in ('PASS','PLANNED','DRY_RUN','DEPENDENCIES_READY') else 2
    except (ValueError,OSError,subprocess.SubprocessError,KeyError) as exc:
        print(json.dumps(dict(status='BLOCKED',reason=str(exc)),ensure_ascii=False));return 2

if __name__=='__main__': sys.exit(main())
