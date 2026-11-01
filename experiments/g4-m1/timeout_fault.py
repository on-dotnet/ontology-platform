"""浏览器真实就绪后暂停准确合成源；19秒独立守卫及finally恢复。"""
from pathlib import Path
import hashlib, json, os, selectors, subprocess, threading, time
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
TASK='G4-M1-RECOVERY-001';RUN='recovery-20261101-01'
docker=['docker','--context','desktop-linux'];records=[];child=None
def source():
    obj=json.loads(subprocess.check_output(docker+['inspect','ontology-g4-m1-recovery-001-pg-source-1'],text=True))[0]
    assert obj['Config']['Labels']['ontology.task-id']==TASK and obj['Config']['Labels']['ontology.run-id']==RUN
    return obj
source_id=source()['Id']
def command(args):
    start=time.monotonic();x=subprocess.run(args,capture_output=True,text=True,timeout=10)
    records.append(dict(command=args,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr,elapsedSeconds=time.monotonic()-start));assert x.returncode==0
def restore():
    obj=source();assert obj['Id']==source_id
    if obj['State']['Paused']:command(docker+['unpause',source_id])
guard=threading.Timer(19,restore)
value=json.loads((PRIVATE/'runtime.json').read_text())
value.update(scenario='source-timeout',sourcePauseHandshake=True,connectionId='1bf23f9d36bf4ceba09d745f04d8f743')
file=PRIVATE/'source-timeout.json'
if file.exists():assert not file.is_symlink() and file.stat().st_mode&0o077==0 and json.loads(file.read_text())==value
else:
    with open(file,'x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(value,stream)
report=dict(taskId=TASK,sourceId=source_id,commands=records,status='FAIL')
try:
    obj=source();assert obj['State']['Running'] and not obj['State']['Paused']
    argv=['node','scripts/acceptance/g4-m1-browser.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'browser')]
    child=subprocess.Popen(argv,cwd=ROOT,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1)
    sel=selectors.DefaultSelector();sel.register(child.stdout,selectors.EVENT_READ);assert sel.select(25)
    line=child.stdout.readline();event=json.loads(line);sel.close()
    assert event['event']=='SOURCE_TIMEOUT_READY' and event['taskId']==TASK and event['runId']==RUN and event['connectionId']==value['connectionId']
    report['ready']=event
    guard.start();command(docker+['pause',source_id]);assert source()['State']['Paused']
    report['pauseObserved']=True
    child.stdin.write('SOURCE_PAUSED\n');child.stdin.flush()
    stdout,stderr=child.communicate(timeout=25)
    records.append(dict(command=argv,exitCode=child.returncode,stdout=line+stdout,stderr=stderr))
    report['status']='PASS' if child.returncode==2 else 'FAIL'
finally:
    restore();guard.cancel()
    if child and child.poll() is None:child.terminate();child.wait(timeout=5)
    report['pausedAfter']=source()['State']['Paused']
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'source-timeout-fixed.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],pausedAfter=report['pausedAfter'])))
