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
import datetime as dt
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'docs/development/verification-gates.json'


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
    direct = {name for name, gate in gates.items() if any(matches(p, gate['inputs']) for p in paths)}
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
    result=select_gates(paths)
    keys={name:input_key(ROOT,name) for name in registry()}
    if git(ROOT,'status','--porcelain').strip() or git(ROOT,'rev-parse','HEAD').decode().strip()!=head:
        raise ValueError('PLAN_INPUT_CHANGED_DURING_CHECK')
    return dict(schemaVersion=1,base=base,head=head,paths=paths,registrySha256=digest(REGISTRY.read_bytes()),inputKeys=keys,**result)


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
    counts=[int(x) for x in re.findall(r'Ran (\d+) tests? in',text)]
    skips=[int(x) for x in re.findall(r'skipped=(\d+)',text)]
    package=re.search(r'ReviewPackage: (\d+) tests, (\d+) failures, (\d+) platform cases NOT_RUN',text)
    if package:
        if int(package[2]): return 0,int(package[3])
        counts.append(int(package[1]));skips.append(int(package[3]))
    return sum(counts),sum(skips)


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
    tests,skips=test_counts(log.decode(errors='replace'),'auto')
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


def execute_gate(command, root, timeout=1800, environment=None):
    """有界子进程，超时终止本次进程组并保存其真实输出。"""
    child=subprocess.Popen(command,cwd=root,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           start_new_session=os.name!='nt')
    try:
        out,err=child.communicate(timeout=timeout)
        return child.returncode,out+err
    except subprocess.TimeoutExpired:
        if os.name!='nt': os.killpg(child.pid,signal.SIGKILL)
        else: child.kill()
        out,err=child.communicate()
        return 124,out+err


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


def verify(task, path, reuse=None, publish=False, diagnostic=False, hypothesis=None):
    expected=json.loads(safe_file(path).read_text())
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
    for name in ordered(set(actual['affected']) | set(index)):
        if digest(REGISTRY.read_bytes())!=actual['registrySha256']: raise ValueError('REGISTRY_CHANGED_DURING_RUN')
        gate=registry()[name];key=actual['inputKeys'][name];policy=policy_key(name)
        if any(outcomes.get(dep) not in (None,'PASS') for dep in gate['needs']):
            rows.append(dict(gate=name,status='NOT_RUN',reason='Upstream failed or unavailable'));outcomes[name]='NOT_RUN';continue
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
            cost='short' if diagnostic else 'expensive'
            guard.allow(cost)
            previous=None if diagnostic else load_reuse(index,name,key,environment,policy)
            if previous:
                rows.append(previous);outcomes[name]='PASS';continue
            if name not in actual['affected']: continue
            start=time.monotonic();started=dt.datetime.now(dt.timezone.utc).isoformat()
            code,raw=execute_gate(gate['command'],ROOT,20 if diagnostic else 1800,child_environment)
            elapsed=time.monotonic()-start
            record_timing(directory,task,run.name,name,key,started,elapsed,code)
            tests,skipped=test_counts(raw.decode(errors='replace'),'auto')
            inputs_unchanged=inputs_stable(ROOT,name,key,policy,actual['registrySha256'])
            passed=code==0 and inputs_unchanged and (not gate.get('testsRequired') or tests>0 and skipped==0)
            guard.record(cost,code if code else (0 if passed else 65))
            evidence_dir=run
            published_dir=safe_file(ROOT/'docs/evidence'/task/'gates'/run.name) if publish else run
            log=write_gate_output(evidence_dir,name,raw)
            row=dict(gate=name,status='PASS' if passed else 'FAIL',executionMode='FRESH',
                command=gate['command'],exitCode=code,tests=tests,skipped=skipped,diagnostic=diagnostic,hypothesis=hypothesis,inputsUnchanged=inputs_unchanged,
                errorSignature=error_signature(raw,code) if not passed else None,
                elapsedSeconds=elapsed,inputKey=key,environmentKey=environment,policyKey=policy,
                evidenceSha256=digest(raw),logPath=str((published_dir/log.name).relative_to(ROOT)),sourceRun=run.name,sourceCommit=actual['head'])
            write(evidence_dir/(name+'.json'),row);
            rows.append(row);outcomes[name]=row['status']
            if not passed: break
    result=dict(status='PASS' if rows and all(x['status']=='PASS' for x in rows) else 'BLOCKED',
                coverage='affected engineering gates only; product coverage requires separate task acceptance',checks=rows)
    # 全部命令结束才发布，证据输出不能污染同轮后续gate的输入。
    if publish:
        target=safe_file(ROOT/'docs/evidence'/task/'gates'/run.name);target.mkdir(parents=True)
        for row in rows:
            if row.get('executionMode')!='FRESH': continue
            for suffix in ('.txt','.json'): os.replace(run/(row['gate']+suffix),target/(row['gate']+suffix))
            write(run/(row['gate']+'.state.json'),{k:row[k] for k in ('status','inputKey','environmentKey','errorSignature')})
    write(run/'receipt.json',result)
    return result


def package_budget(root, base, head, task):
    """逐blob压缩估算，不制造中间ZIP；最终大小仍由生产构包器强验。"""
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}',task): raise ValueError('TASK_INVALID')
    for ref in (base,head):
        if not re.fullmatch('[0-9a-f]{40}',ref): raise ValueError('FULL_COMMIT_REQUIRED')
    subprocess.run(['git','merge-base','--is-ancestor',base,head],cwd=root,check=True)
    records=git(root,'ls-tree','-r','-z',head).split(b'\0')
    counts={'source':0,'currentEvidence':0};sizes=dict(counts);compressed=dict(counts)
    for entry in records:
        if not entry: continue
        metadata,name=entry.split(b'\t',1);mode,kind,oid=metadata.decode().split();path=name.decode()
        if kind!='blob' or mode not in ('100644','100755'): raise ValueError('PACKAGE_SPECIAL_PATH: '+path)
        if path.startswith('docs/evidence/') and not path.startswith('docs/evidence/'+task+'/'): continue
        category='currentEvidence' if path.startswith('docs/evidence/') else 'source'
        data=git(root,'cat-file','blob',oid)
        sizes[category]+=len(data);compressed[category]+=len(zlib.compress(data))+len(name)*2+256;counts[category]+=1
    patch=git(root,'diff','--binary',base,head)
    diffcheck=subprocess.run(['git','diff','--check',base,head],cwd=root,capture_output=True)
    estimate=sum(compressed.values())+len(zlib.compress(patch))+1024*1024
    return dict(status='PASS' if estimate<=15*1024*1024 and diffcheck.returncode==0 else 'BLOCKED',
        base=base,head=head,taskId=task,counts=counts,rawBytes=sizes,compressedEstimateBytes=compressed,
        estimatedZipBytes=estimate,explainComposition=estimate>10*1024*1024,diffCheckExitCode=diffcheck.returncode,
        argvPolicy='fixed small argv; blob IDs read individually; final packer retains exact safety checks',
        limitation='Estimate includes 1MiB metadata reserve; final V3 and independent VerifyOnly remain required')


def package_check(task, base, head, evidence):
    result=package_budget(ROOT,base,head,task)
    paths=set(git(ROOT,'ls-tree','-r','--name-only','-z',head).decode().split('\0'))
    paths.update(git(ROOT,'diff','--name-only','-z','--no-renames',base,head,'--').decode().split('\0'))
    validate_package_paths(ROOT,sorted(paths-{''}))
    result['pathPolicy']='PASS: existing V3 rules'
    proc=subprocess.run(['pwsh','-NoProfile','-File','scripts/verify.ps1'],cwd=ROOT,env=engineering_process_environment(task))
    result['formatExitCode']=proc.returncode
    if proc.returncode: result['status']='BLOCKED'
    if evidence:
        proc=subprocess.run(['pwsh','-NoProfile','-File','scripts/test-review-evidence.ps1',
                             '-EvidenceFile',str(safe_file(evidence)),'-ExpectedHead',head],cwd=ROOT,env=engineering_process_environment(task))
        result['evidenceSchemaExitCode']=proc.returncode
        if proc.returncode: result['status']='BLOCKED'
    else:
        result.update(status='BLOCKED',evidenceSchema='NOT_RUN: supply --evidence before final acceptance')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--task',required=True);prep.add_argument('--inventory')
    smoke=sub.add_parser('smoke');smoke.add_argument('--task',required=True)
    pl=sub.add_parser('plan');pl.add_argument('--base',required=True);pl.add_argument('--head',required=True);pl.add_argument('--output',required=True)
    ve=sub.add_parser('verify');ve.add_argument('--task',required=True);ve.add_argument('--plan',required=True);ve.add_argument('--reuse');ve.add_argument('--publish-evidence',action='store_true');ve.add_argument('--diagnostic',action='store_true');ve.add_argument('--hypothesis')
    pc=sub.add_parser('package-check');pc.add_argument('--task',required=True);pc.add_argument('--base',required=True);pc.add_argument('--head',required=True);pc.add_argument('--evidence')
    cl=sub.add_parser('closeout');cl.add_argument('--task',required=True);cl.add_argument('--dry-run',action='store_true',required=True)
    args=p.parse_args()
    try:
        if args.action=='prepare': result=prepare(args.task,args.inventory)
        elif args.action=='plan':
            result=plan(args.base,args.head);write(Path(args.output),result)
        elif args.action=='verify': result=verify(args.task,args.plan,args.reuse,args.publish_evidence,args.diagnostic,args.hypothesis)
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
