"""本次M5组合浏览器获审后的六条既有真实门禁；非通用恢复平台，不重复600子链。"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def load(name, path):
    """只加载当前仓库已批准的固定执行器。"""
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file',required=True,type=Path)
    args=parser.parse_args()
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=Path(__file__).parent,text=True).strip()).resolve()
    folder=root/'docs/evidence/G3-M5-001/master/final-four'
    proof=json.loads((folder/'m5-full-e2e.json').read_text())
    if proof['status']!='PASS' or proof['scope']!='COMPOSITE_BROWSER' or proof['repairedM5']['fixedRelease']!='PASS':
        raise ValueError('Browser repair not verified')
    for source in proof['sourceReports']:
        path=root/source['path']
        if not path.resolve().is_relative_to(root/'docs/evidence/G3-M5-001') or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('Source report changed')
    runtime_path=args.runtime_file.resolve()
    if not runtime_path.is_relative_to(root/'.tools/security') or runtime_path.parent.name!=proof['runtimePrefix']:
        raise ValueError('Unowned runtime refused')
    runtime=json.loads(runtime_path.read_text())
    if runtime['volumePrefix']!=proof['runtimePrefix']:
        raise ValueError('Runtime identity mismatch')
    sys.path.insert(0,str(root/'scripts/acceptance'))
    shared=load('shared_runtime',root/'scripts/acceptance/g2-acceptance-runtime.py')
    timeline=load('timeline',root/'scripts/maintenance/task_run_timeline.py')
    preflight=load('preflight',root/'scripts/maintenance/execution_preflight.py')
    host=load('host',root/'scripts/maintenance/host_continuity.py')
    if host.inspect().get('assurance')=='BLOCKED_HOST_SLEEP_ASSURANCE':
        raise ValueError('Host continuity blocked')
    preflight.check_consumers(root,'M5')
    fingerprint=preflight.product_input_fingerprint(root)
    env={**os.environ,'PLATFORM_TASK_ID':'G3-M5-001','PLATFORM_EVIDENCE_DIR':str(folder.relative_to(root)),
         'G3_READER_IDENTITY_SHA':json.loads((root/'artifacts/g3-m5/prewrite-reader-freeze.json').read_text())['freezeSha256']}
    os.environ['PLATFORM_EVIDENCE_DIR']=env['PLATFORM_EVIDENCE_DIR']
    process=subprocess.Popen([sys.executable,str(root/'scripts/acceptance/g3-runtime.py'),'full','--runtime-file',str(runtime_path),'--milestone','M5'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    commands=[
      [sys.executable,'scripts/acceptance/g3-compatibility.py'],
      [sys.executable,'scripts/acceptance/g1-regression.py','--runtime-file',str(runtime_path),'--runtime-only'],
      [sys.executable,'scripts/acceptance/g2-observability.py','--runtime-file',str(runtime_path)],
      ['node','scripts/acceptance/g2-trace-browser.mjs',str(runtime_path)],
      [sys.executable,'scripts/acceptance/g2-readiness-fault.py','--runtime-file',str(runtime_path)],
      [sys.executable,'scripts/acceptance/performance-baseline.py','--from-observed-run','--chain-report','m5-full-e2e.json']]
    commands=commands[2:]
    for name in ('full-chain-identifiers.json','performance-observations.json','m5-full-e2e.json'):
        if not (folder/name).is_file():raise ValueError('Required bounded evidence missing before launcher')
    report={'taskId':'G3-M5-001','runId':'final-four','startedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),'harnessSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'FOUR_REAL_GATES_AFTER_BOUND_INPUT_REPAIR','status':'RUNNING','sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'productInputFingerprint':fingerprint,'browserProofSha256':hashlib.sha256((folder/'m5-full-e2e.json').read_bytes()).hexdigest(),'ownerPid':process.pid,
            'gates':[{'name':Path(command[1]).name,'status':'NOT_RUN','exitCode':None} for command in commands]}
    def save():
        (folder/'final-four-gates.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        shared.wait_for('http://localhost:15100/health/ready',{'X-Health-Key':runtime['healthKey']})
        previous=None
        for index,command in enumerate(commands):
            name=Path(command[1]).name
            report['gates'][index]['status']='RUNNING';save()
            start=dt.datetime.now(dt.timezone.utc);tick=time.monotonic()
            with (root/('artifacts/g3-m5/final-four-'+name+'.log')).open('x') as output:
                result=subprocess.run(command,cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT)
            row=dict(schemaVersion=1,taskId='G3-M5-001',runId='final-four',stepId=name,taskType='TEST',inputFingerprint=fingerprint,
                     startedAtUtc=start.isoformat(),endedAtUtc=start.isoformat(),durationMs=0,outcome='PASS',errorCategory=None,
                     dependsOn=[previous] if previous else [],concurrencyGroup='runtime',attempt=1,exitCode=0,commandLabel=name)
            row=timeline.complete(row,dt.datetime.now(dt.timezone.utc).isoformat(),round((time.monotonic()-tick)*1000),result.returncode)
            timeline.append(folder/'task-run-timeline.jsonl',row,assign_attempt=True)
            report['gates'][index].update(status='PASS' if result.returncode==0 else 'FAIL',exitCode=result.returncode);save()
            print(json.dumps(report['gates'][index]),flush=True)
            if result.returncode:
                report['status']='FAIL';return result.returncode
            previous=name
        report['status']='PASS';return 0
    finally:
        shared.stop(process)
        report['endedAtUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
        report['launcherStopped']=process.poll() is not None
        report['launcherExitCode']=process.returncode
        if report['status']=='RUNNING' or not report['launcherStopped']:report['status']='FAIL'
        save()


if __name__=='__main__':
    raise SystemExit(main())
