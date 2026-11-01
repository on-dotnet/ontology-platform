"""仅断开准确任务源网络；十五秒守卫恢复原网络、IP和别名。"""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,threading,time
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001';PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
docker=['docker','--context','desktop-linux'];records=[];errors=[];mutex=threading.RLock();expired=threading.Event()
report=dict(taskId='G4-M1-RECOVERY-001',status='FAIL',commands=records,claim='Real source network unavailable; PostgreSQL process remains running.')
def inspect(kind,identity):
    obj=json.loads(subprocess.check_output(docker+[kind,'inspect',identity] if kind=='network' else docker+['inspect',identity],text=True,timeout=5))[0]
    labels=obj['Labels'] if kind=='network' else obj['Config']['Labels']
    assert labels['ontology.task-id']==report['taskId'] and labels['ontology.run-id']=='recovery-20261101-01'
    return obj
source=inspect('container','ontology-g4-m1-recovery-001-pg-source-1');sid=source['Id'];networks=source['NetworkSettings']['Networks'];assert len(networks)==1
name,before=next(iter(networks.items()));assert name=='ontology-g4-m1-recovery-001_source'
network=inspect('network',before['NetworkID']);assert network['Internal'];assert source['State']['Running'] and not source['State']['Paused']
report['before']=dict(containerId=sid,networkId=network['Id'],ip=before['IPAddress'],aliases=before['Aliases'])
def command(argv,timeout=10):
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();start=time.monotonic()
    try:x=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        records.append(dict(command=argv,startedUtc=started,elapsedSeconds=time.monotonic()-start,exitCode=None,timingStatus='TIMEOUT',timeoutSeconds=timeout));raise
    records.append(dict(command=argv,startedUtc=started,elapsedSeconds=time.monotonic()-start,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==0
    return x
def restore(watchdog=False):
    if watchdog:expired.set()
    with mutex:
        try:
            obj=inspect('container',sid);inspect('network',network['Id'])
            if name not in obj['NetworkSettings']['Networks']:
                argv=docker+['network','connect','--ip',before['IPAddress']]
                for alias in before['Aliases']:argv+=['--alias',alias]
                command(argv+[network['Id'],sid])
            after=inspect('container',sid)['NetworkSettings']['Networks'][name]
            assert after['NetworkID']==before['NetworkID'] and after['IPAddress']==before['IPAddress'] and sorted(after['Aliases'])==sorted(before['Aliases'])
            report['restored']=dict(networkId=after['NetworkID'],ip=after['IPAddress'],aliases=after['Aliases'])
        except Exception as error:errors.append(dict(operation='network_restore',errorType=type(error).__name__))
guard=threading.Timer(15,lambda:restore(True))
try:
    runtime=json.loads((PRIVATE/'runtime.json').read_text());runtime.update(scenario='source-unavailable',connectionId='1bf23f9d36bf4ceba09d745f04d8f743')
    file=PRIVATE/'source-network-unavailable.json'
    with open(file,'x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(runtime,stream)
    guard.start()
    with mutex:
        assert not expired.is_set();command(docker+['network','disconnect',network['Id'],sid]);assert inspect('container',sid)['NetworkSettings']['Networks']=={}
    argv=['node','scripts/acceptance/g4-m1-browser.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'browser')]
    x=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=13);records.append(dict(command=argv,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==2 and not expired.is_set()
    restore();guard.cancel();assert not errors
    command(['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(PRIVATE/'final-probe-refresh.json'),'--action','probe-refresh'],25)
    report['status']='PASS'
finally:
    restore();guard.cancel();report['cleanupErrors']=errors;report['watchdogExpired']=expired.is_set();report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if errors:report['status']='FAIL'
    with open(ART/'source-network-unavailable.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],cleanupErrors=errors)))

if report['status']!='PASS':raise SystemExit(1)
