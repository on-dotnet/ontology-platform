#!/usr/bin/env python3
"""M2零恢复构建与准确输入/输出绑定；测试消费者拒绝旧产物。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
TASK='G4-M2-WEB-01'
TARGETS={'connections':'backend/tests/OntologyPlatform.ConnectionsTests/OntologyPlatform.ConnectionsTests.csproj','wire':'backend/tests/OntologyPlatform.G2ContractTests/OntologyPlatform.G2ContractTests.csproj','api':'backend/src/Hosts/OntologyPlatform.Api/OntologyPlatform.Api.csproj','web':'apps/web'}


def sha(data):return hashlib.sha256(data).hexdigest()


def inputs(target):
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    rows={}
    for name in sorted(set(names)-{''}):
        if not (name.startswith('apps/web/' if target=='web' else 'backend/') or name in ('global.json','NuGet.Config','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version') or name.startswith('Directory.')):continue
        if any(part in ('bin','obj','node_modules','.next') for part in Path(name).parts):continue
        path=ROOT/name
        if path.is_symlink():raise ValueError('BUILD_LINK')
        rows[name]=sha(path.read_bytes())
    return sha(json.dumps(rows,sort_keys=True).encode())


def outputs(target):
    directory=ROOT/'apps/web/.next' if target=='web' else ROOT/Path(TARGETS[target]).parent/'bin/Debug/net10.0'
    marker=directory/'required-server-files.json' if target=='web' else directory/(Path(TARGETS[target]).stem+'.dll')
    if not marker.is_file():raise ValueError('BUILD_OUTPUT_MISSING')
    rows={}
    for file in sorted(directory.rglob('*')):
        if any(p in ('cache','diagnostics','types') for p in file.relative_to(directory).parts) or file.name in ('trace','trace-build'):continue
        if file.is_symlink():raise ValueError('BUILD_OUTPUT_LINK')
        if file.is_file():rows[str(file.relative_to(ROOT))]=sha(file.read_bytes())
    return rows


def begin_cleanup(state,expected):
    """任何删除命令之前撤回完成态；中断只能留下未核实，而不能留下PASS。"""
    state['testStatus']=state['status'];state['status']='NOT_VERIFIED'
    state['cleanupExpected']=sorted(expected);state['cleanupComplete']=False


def finish_cleanup(state):
    """每个准确预期资源必须恰好有一次成功的缺席后验。"""
    rows=state['cleanup']
    complete=sorted(row['id'] for row in rows)==state['cleanupExpected'] and all(row['afterAbsent'] for row in rows)
    state['cleanupComplete']=complete;state['status']=state['testStatus'] if complete else 'FAIL'


def driver_layers():
    """显式登记执行、资格、归档层；新增未映射 M2 模块关闭复用。"""
    execution=('workflow_m2_web.py','workflow_m2_fixture.py','workflow_m2_smoke.py','workflow_m2_build.py','workflow_smoke.py','workflow_execution.py','workflow_environment.py','workflow_web_cache.py','workflow.py','workflow-m2-web.mjs')
    qualification=('workflow_m2_evidence.py','workflow_evidence.py')
    rows={ 'scripts/maintenance/'+name:'execution' for name in execution}
    rows.update({'scripts/maintenance/'+name:'qualification' for name in qualification})
    rows['experiments/g4-m2-web-01/https-fixture.mjs']='execution'
    unknown={str(path.relative_to(ROOT)) for path in (ROOT/'scripts/maintenance').glob('workflow_m2_*.py')}-set(rows)
    if unknown:raise ValueError('UNMAPPED_EXECUTION_INPUT')
    return rows


def driver_inputs():
    return {path:sha((ROOT/path).read_bytes()) for path in driver_layers()}


def execution_unchanged(previous):
    layers=driver_layers();current=driver_inputs()
    if set(previous)!=set(current):return False
    return all(previous[path]==current[path] for path in current if layers[path]=='execution')


def validate(target,task=TASK):
    path=ROOT/'artifacts/workflow'/task/(target+'-build-binding.json')
    receipt=json.loads(path.read_text())
    if receipt.get('status')!='PASS' or receipt.get('taskId')!=task or receipt.get('worktree')!=str(ROOT) or receipt.get('inputKey')!=inputs(target) or receipt.get('outputs')!=outputs(target):raise ValueError('BUILD_BINDING_MISMATCH')
    return {'receiptSha256':sha(path.read_bytes()),'inputKey':receipt['inputKey'],'outputKey':sha(json.dumps(receipt['outputs'],sort_keys=True).encode())}


def build(target,prepared):
    if target not in TARGETS:raise ValueError('BUILD_TARGET')
    receipt=json.loads(Path(prepared).read_text());env=receipt['environment']
    initial=inputs(target);cwd=ROOT
    if target=='web':
        cwd=ROOT/'apps/web';command=[str(cwd/'node_modules/.bin/next'),'build','--webpack'];profile='(version 1) (allow default) (deny network-outbound)'
    else:
        command=[receipt['dotnet'],'build',TARGETS[target],'--no-restore','--disable-build-servers','-m:1','-v:q'];profile='(version 1) (allow default) (deny network*)'
    from workflow_execution import run
    start=time.monotonic();result=run(['/usr/bin/sandbox-exec','-p',profile,*command],cwd,task=receipt['taskId'],environment=env,timeout=180,input_key=initial)
    directory=ROOT/'artifacts/workflow'/receipt['taskId'];log=directory/(target+'-bound-build.txt');log.write_bytes(result.stdout+result.stderr)
    value=dict(taskId=receipt['taskId'],worktree=str(ROOT),target=target,status='PASS' if result.returncode==0 and initial==inputs(target) else 'FAIL',exitCode=result.returncode,elapsedSeconds=time.monotonic()-start,inputKey=initial,logSha256=sha(log.read_bytes()),command=command,outputs=outputs(target) if result.returncode==0 else {})
    (directory/(target+'-build-binding.json')).write_text(json.dumps(value,indent=2)+'\n')
    return {key:value[key] for key in ('target','status','exitCode','elapsedSeconds','inputKey')}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--task',required=True);parser.add_argument('--target',choices=TARGETS,required=True);parser.add_argument('--prepared',required=True);args=parser.parse_args()
    if args.task not in (TASK,'G4-ENG-DELIVERY-002'):raise SystemExit(2)
    result=build(args.target,args.prepared);print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 2)
