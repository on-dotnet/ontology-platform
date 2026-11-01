"""在真实TLS等待中断开浏览器请求，精确CommandKey核对持久取消。"""
from pathlib import Path
import hashlib,json,subprocess,threading,time
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
docker=['docker','--context','desktop-linux'];records=[];errors=[]
def inspect(name):
    obj=json.loads(subprocess.check_output(docker+['inspect',name],text=True,timeout=5))[0]
    assert obj['Config']['Labels']['ontology.task-id']=='G4-M1-RECOVERY-001' and obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
    return obj
source=inspect('ontology-g4-m1-recovery-001-pg-source-1')['Id']
platform=inspect('ontology-g4-m1-recovery-001-platform-pg-1')['Id']
def command(argv,stdin=None,timeout=15):
    start=time.monotonic()
    try:x=subprocess.run(argv,input=stdin,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        records.append(dict(command=argv,input=stdin,exitCode=None,timingStatus='TIMEOUT'));raise
    records.append(dict(command=argv,input=stdin,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr,elapsedSeconds=time.monotonic()-start));assert x.returncode==0
    return x.stdout.strip()
def restore():
    try:
        if inspect(source)['State']['Paused']:command(docker+['unpause',source])
    except Exception as error:errors.append(dict(operation='restore_source',errorType=type(error).__name__))
guard=threading.Timer(19,restore)
report=dict(taskId='G4-M1-RECOVERY-001',status='FAIL',commands=records)
try:
    assert not inspect(source)['State']['Paused']
    guard.start();command(docker+['pause',source]);assert inspect(source)['State']['Paused']
    out=command(['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(PRIVATE/'http-schema-change.json'),'--action','probe-client-cancel'],timeout=15)
    evidence=json.loads((ROOT/json.loads(out)['evidence']).read_text());key=evidence['commandKey'];assert len(key)==64 and all(x in '0123456789abcdef' for x in key)
    report['commandKey']=key;deadline=time.monotonic()+10
    while True:
        sql='SELECT coalesce(json_agg(json_build_object(\'id\',"Id",\'report\',"ReportJson"::jsonb)),\'[]\') FROM connections."ConnectionProbes" WHERE "CommandKey"=\''+key+'\';'
        rows=json.loads(command(docker+['exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt'],stdin="SET statement_timeout='2s';"+sql))
        assert len(rows)==1
        if rows[0]['report']['status']!='RUNNING':break
        assert time.monotonic()<deadline;time.sleep(.2)
    probe=rows[0]['report'];report['probe']=probe
    assert probe['status']=='CANCELLED'
    assert any(x['diagnosticCode']=='connection_cancelled' for x in probe['stages'])
    assert probe['stages'][0]['name']=='NETWORK' and probe['stages'][0]['status']=='PASS'
    report['status']='PASS'
finally:
    restore();guard.cancel()
    try:report['pausedAfter']=inspect(source)['State']['Paused'];assert report['pausedAfter'] is False
    except Exception as error:errors.append(dict(operation='verify_restore',errorType=type(error).__name__))
    report['cleanupErrors']=errors
    if errors:report['status']='FAIL'
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'client-cancel-fault.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],pausedAfter=report.get('pausedAfter'),cleanupErrors=errors)))
if report['status']!='PASS':raise SystemExit(1)
