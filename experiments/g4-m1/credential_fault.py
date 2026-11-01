"""仅轮换本任务合成源角色，私有SQL不记录，独立守卫和finally恢复原密码。"""
from pathlib import Path
import hashlib,json,selectors,subprocess,threading,time
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
docker=['docker','--context','desktop-linux'];records=[];errors=[];changed=False;child=None
report=dict(taskId='G4-M1-RECOVERY-001',status='FAIL',commands=records)
def inspect(name):
    obj=json.loads(subprocess.check_output(docker+['inspect',name],text=True,timeout=5))[0]
    assert obj['Config']['Labels']['ontology.task-id']=='G4-M1-RECOVERY-001' and obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
    return obj
source=inspect('ontology-g4-m1-recovery-001-pg-source-1')['Id']
platform=inspect('ontology-g4-m1-recovery-001-platform-pg-1')['Id']
def password(file):
    assert file.parent==PRIVATE and not file.is_symlink() and file.stat().st_mode&0o077==0
    value=file.read_text().strip();assert len(value)>=30 and all(c.isalnum() or c in '_-' for c in value)
    return value
def set_password(restore=False):
    global changed
    obj=inspect(source);assert obj['Id']==source and obj['State']['Running'] and not obj['State']['Paused']
    value=password(PRIVATE/('reader-password' if restore else 'rotation-password'))
    argv=docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt']
    # 凭据只存在子进程stdin内存中；关闭源语句/错误语句日志的原配置保持。
    try:
        x=subprocess.run(argv,input="SET lock_timeout='2s';SET statement_timeout='5s';ALTER ROLE fixture_reader PASSWORD '"+value+"';",capture_output=True,text=True,timeout=10)
        records.append(dict(command=argv,operation='restore_original_password' if restore else 'rotate_synthetic_password',exitCode=x.returncode,privateInput='SUPPRESSED',stdoutBytes=len(x.stdout),stderrBytes=len(x.stderr)))
        assert x.returncode==0
        changed=not restore
    finally:value=None
def restore():
    try:set_password(True)
    except Exception as error:errors.append(dict(operation='restore_password',errorType=type(error).__name__))
guard=threading.Timer(70,restore)
try:
    sql='SELECT (SELECT count(*) FROM connections."CatalogJobs" WHERE "Status" IN (\'QUEUED\',\'RUNNING\'))+(SELECT count(*) FROM connections."ConnectionProbes" WHERE "ReportJson"::jsonb->>\'status\'=\'RUNNING\');'
    x=subprocess.run(docker+['exec','-i',platform,'psql','-U','platform','-d','platform','-qAt'],input=sql,capture_output=True,text=True,timeout=5)
    assert x.returncode==0 and x.stdout.strip()=='0';report['activeWorkBefore']=0
    argv=['node','scripts/acceptance/g4-m1-http.mjs','--runtime-file',str(PRIVATE/'credential-lifecycle.json'),'--evidence-dir',str(ART/'http')]
    child=subprocess.Popen(argv,cwd=ROOT,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1)
    selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ);deadline=time.monotonic()+90;lines=[]
    while True:
        assert time.monotonic()<deadline
        if not selector.select(1):
            if child.poll() is not None:break
            continue
        line=child.stdout.readline()
        if not line:break
        lines.append(line);event=json.loads(line)
        if 'event' in event:
            assert event['taskId']=='G4-M1-RECOVERY-001' and event['runId']=='recovery-20261101-01'
            if event['event']=='CREDENTIAL_ROTATION_READY':
                assert not changed;guard.start();set_password();child.stdin.write('SOURCE_PASSWORD_ROTATED\n');child.stdin.flush()
            elif event['event']=='CREDENTIAL_RESTORE_READY':
                set_password(True);child.stdin.write('SOURCE_PASSWORD_RESTORED\n');child.stdin.flush();guard.cancel()
            else:raise AssertionError('unexpected_event')
        else:
            assert event['taskId']=='G4-M1-RECOVERY-001' and event['scenario']=='credential-lifecycle'
            report['consumerSummary']=event;child.stdin.close();break
    selector.close();child.wait(timeout=5)
    records.append(dict(command=argv,exitCode=child.returncode,stdout=''.join(lines),stderr=child.stderr.read()))
    assert child.returncode==2 and not changed
    report['status']='PASS'
finally:
    restore();guard.cancel()
    if child and child.poll() is None:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:errors.append(dict(operation='driver_exit',errorType='TimeoutExpired'))
    report['cleanupErrors']=errors;report['originalPasswordRestored']=not changed and not errors
    if errors:report['status']='FAIL'
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'credential-fault-fixed.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],originalPasswordRestored=report['originalPasswordRestored'])))
if report['status']!='PASS':raise SystemExit(1)
