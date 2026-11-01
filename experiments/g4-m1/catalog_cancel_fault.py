"""真实页面取消阻塞中的Npgsql目录任务，15秒独立源锁守卫。"""
from pathlib import Path
import hashlib,ipaddress,json,os,selectors,subprocess,threading,time,datetime
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
docker=['docker','--context','desktop-linux'];records=[];errors=[];lock=None;observer=None;browser=None;claim=None
report=dict(taskId='G4-M1-RECOVERY-001',status='FAIL',commands=records)
def inspect(name):
    obj=json.loads(subprocess.check_output(docker+['inspect',name],text=True,timeout=5))[0]
    assert obj['Config']['Labels']['ontology.task-id']=='G4-M1-RECOVERY-001' and obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
    return obj
source=inspect('ontology-g4-m1-recovery-001-pg-source-1')['Id'];platform=inspect('ontology-g4-m1-recovery-001-platform-pg-1')['Id'];api=inspect('ontology-g4-m1-recovery-001-api-1')
addresses={x['IPAddress'] for x in api['NetworkSettings']['Networks'].values()};report['apiIdentity']={'id':api['Id'],'addresses':sorted(addresses)}
def line(process,timeout):
    sel=selectors.DefaultSelector();sel.register(process.stdout,selectors.EVENT_READ)
    try:assert sel.select(timeout);value=process.stdout.readline();assert value;return json.loads(value)
    finally:sel.close()
def source_command():return docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt']
def observation():
    observer.stdin.write('EXECUTE recovery_cancel_activity;\n');observer.stdin.flush();value=line(observer,3)
    records.append(dict(operation='source_wait_observation',observedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),value=value));return value
def db(sql):
    argv=docker+['exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt'];x=subprocess.run(argv,input="SET statement_timeout='2s';"+sql,capture_output=True,text=True,timeout=5)
    records.append(dict(command=argv,sql=sql,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==0;return json.loads(x.stdout)
def release():
    try:
        if lock and lock.poll() is None:lock.stdin.write('ROLLBACK;\n\\q\n');lock.stdin.flush()
    except Exception as error:errors.append(dict(operation='source_rollback',errorType=type(error).__name__))
def release_claim():
    try:
        if claim and claim.poll() is None:claim.stdin.write('ROLLBACK;\n\\q\n');claim.stdin.flush()
    except Exception as error:errors.append(dict(operation='claim_rollback',errorType=type(error).__name__))
guard=threading.Timer(15,release)
claim_guard=threading.Timer(9,release_claim)
try:
    value=json.loads((PRIVATE/'runtime.json').read_text());value.update(scenario='catalog-cancel',catalogCancelHandshake=True,connectionId='1bf23f9d36bf4ceba09d745f04d8f743')
    file=PRIVATE/'catalog-cancel-fresh-probe.json'
    with open(file,'x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(value,stream)
    argv=['node','scripts/acceptance/g4-m1-browser.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'browser')]
    browser=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    ready=line(browser,25);assert ready['event']=='CATALOG_CANCEL_READY' and ready['connectionId']==value['connectionId'] and ready['taskId']==report['taskId'] and ready['runId']=='recovery-20261101-01';report['ready']=ready
    observer=subprocess.Popen(source_command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    sql="SET statement_timeout='2s'; SET idle_session_timeout='30s'; SET plan_cache_mode=force_generic_plan; PREPARE recovery_cancel_activity AS SELECT coalesce(json_agg(json_build_object('pid',pid,'state',state,'waitType',wait_event_type,'wait',wait_event,'clientAddr',client_addr::text,'user',usename,'database',datname)),'[]') FROM pg_stat_activity WHERE backend_type='client backend' AND client_addr IS NOT NULL; EXECUTE recovery_cancel_activity;\n"
    observer.stdin.write(sql);observer.stdin.flush();initial=line(observer,3);assert initial==[];report['sourceBefore']=initial
    observer.stdin.write("PREPARE recovery_cancel_state(int,int) AS SELECT json_build_object('lockCount',(SELECT count(*) FROM pg_locks WHERE pid=$1 AND relation='pg_catalog.pg_shdepend'::regclass AND mode='AccessExclusiveLock' AND granted),'backendCount',(SELECT count(*) FROM pg_stat_activity WHERE pid=$2)); EXECUTE recovery_cancel_state(-1,-1);\n");observer.stdin.flush();assert line(observer,3)=={'lockCount':0,'backendCount':0}
    assert db('SELECT count(*) FROM connections."CatalogJobs" WHERE "Status" IN (\'QUEUED\',\'RUNNING\');')==0
    claim_argv=docker+['exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt']
    claim=subprocess.Popen(claim_argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    claim_sql="SET lock_timeout='2s';SET statement_timeout='10s';SET idle_in_transaction_session_timeout='10s';BEGIN;SELECT pg_advisory_xact_lock(hashtextextended('connection:catalog-claim',0));SELECT json_build_object('pid',pg_backend_pid(),'granted',exists(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted));\n"
    claim.stdin.write(claim_sql);claim.stdin.flush()
    # advisory函数本身返回空文本行；接着读取准确持锁JSON。
    sel=selectors.DefaultSelector();sel.register(claim.stdout,selectors.EVENT_READ);assert sel.select(3);assert claim.stdout.readline().strip()=='';claim_ready=json.loads(claim.stdout.readline());sel.close();assert claim_ready['granted'];report['claimLock']=dict(command=claim_argv,sql=claim_sql,held=claim_ready);claim_guard.start()
    lock=subprocess.Popen(source_command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    sql="SET application_name='g4_m1_recovery_cancel_lock'; SET lock_timeout='2s'; SET statement_timeout='15s'; SET idle_in_transaction_session_timeout='15s'; BEGIN; LOCK TABLE pg_catalog.pg_shdepend IN ACCESS EXCLUSIVE MODE; SELECT json_build_object('pid',pg_backend_pid(),'granted',exists(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND relation='pg_catalog.pg_shdepend'::regclass AND mode='AccessExclusiveLock' AND granted));\n"
    lock.stdin.write(sql);lock.stdin.flush();held=line(lock,3);assert held['granted'];report['lock']=dict(command=source_command(),sql=sql,held=held);guard.start()
    browser.stdin.write('SOURCE_LOCKED\n');browser.stdin.flush();started=line(browser,5)
    assert started['event']=='CATALOG_JOB_STARTED' and started['connectionId']==value['connectionId'] and started['taskId']==report['taskId'] and started['runId']=='recovery-20261101-01'
    job=started['jobId'];assert len(job)==32 and all(c in '0123456789abcdef' for c in job);report['jobId']=job
    state_sql='SELECT json_build_object(\'status\',"Status",\'cancelRequested\',"CancelRequested",\'fence\',"Fence",\'snapshot\',"SnapshotId",\'diagnostic\',"DiagnosticCode") FROM connections."CatalogJobs" WHERE "Id"=\''+job+'\';'
    queued=db(state_sql);assert queued['status']=='QUEUED' and queued['fence']==0
    deadline=time.monotonic()+.8
    while True:
        ui_waiters=observation()
        if ui_waiters:break
        assert time.monotonic()<deadline;time.sleep(.03)
    report['uiSourcePidBaselineWhileJobQueued']=ui_waiters
    baseline={x['pid'] for x in ui_waiters}
    release_claim();claim_guard.cancel();claim.wait(timeout=3);assert claim.returncode==0
    assert db('SELECT count(*) FROM pg_locks WHERE pid='+str(int(claim_ready['pid']))+" AND locktype='advisory';")==0
    report['claimLock']['exitCode']=claim.returncode;report['claimLock']['releasedCount']=0
    deadline=time.monotonic()+2
    while True:
        before=db(state_sql);waiting=observation()
        matching=[x for x in waiting if x['pid'] not in baseline and x['waitType']=='Lock' and x['user']=='fixture_reader' and x['database']=='fixture' and str(ipaddress.ip_interface(x['clientAddr']).ip) in addresses]
        if before['status']=='RUNNING' and len(matching)==1:break
        assert before['status'] in ('QUEUED','RUNNING') and time.monotonic()<deadline;time.sleep(.03)
    report['sourceBlockedBeforeCancel']=waiting;report['workerSourcePid']=matching[0]['pid'];report['jobBeforeCancel']=before
    assert not before['cancelRequested']
    browser.stdin.write('SOURCE_QUERY_WAITING\n');browser.stdin.flush();cancel_started=time.monotonic()
    while True:
        final=db(state_sql)
        observer.stdin.write('EXECUTE recovery_cancel_state('+str(int(held['pid']))+','+str(int(report['workerSourcePid']))+');\n');observer.stdin.flush();cancelled_source=line(observer,3)
        if final['status']=='CANCELLED' and cancelled_source=={'lockCount':1,'backendCount':0}:break
        assert cancelled_source['lockCount']==1 and time.monotonic()-cancel_started<1.5;time.sleep(.03)
    report['jobCancelledWhileSourceLocked']=final;report['sourceCancellationBeforeUnlock']={'observedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsedAfterCancelAckMs':(time.monotonic()-cancel_started)*1000,**cancelled_source}
    assert final['cancelRequested'] and final['snapshot'] is None and final['diagnostic']=='connection_cancelled'
    release();guard.cancel();lock.wait(timeout=5);assert lock.returncode==0;report['lock']['exitCode']=lock.returncode
    stdout,stderr=browser.communicate(timeout=8)
    records.append(dict(command=argv,exitCode=browser.returncode,stdout=stdout,stderr=stderr));assert browser.returncode==2
    report['status']='PASS'
finally:
    release();guard.cancel();release_claim();claim_guard.cancel()
    for name,process in [('lock',lock),('claim',claim),('observer',observer),('browser',browser)]:
        if process is None:continue
        try:
            if process.poll() is None:
                if name=='observer':process.stdin.write('\\q\n');process.stdin.flush()
                elif name=='browser':process.terminate()
                process.wait(timeout=5)
            report[name+'Exit']=process.poll()
        except Exception as error:errors.append(dict(operation=name+'_exit',errorType=type(error).__name__))
    try:
        if 'sourceBlockedBeforeCancel' in report:
            ids=','.join(str(int(x['pid'])) for x in report['sourceBlockedBeforeCancel']);pid=int(report['lock']['held']['pid'])
            sql=f"SET statement_timeout='2s';SELECT json_build_object('lockCount',(SELECT count(*) FROM pg_locks WHERE pid={pid}),'backendCount',(SELECT count(*) FROM pg_stat_activity WHERE pid IN ({ids})));"
            x=subprocess.run(source_command(),input=sql,capture_output=True,text=True,timeout=5);records.append(dict(command=source_command(),sql=sql,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==0
            report['sourceAfter']=json.loads(x.stdout);assert report['sourceAfter']=={'lockCount':0,'backendCount':0}
    except Exception as error:errors.append(dict(operation='source_cleanup_verification',errorType=type(error).__name__))
    try:
        if 'claimLock' in report:
            report['claimLockAfter']=db('SELECT count(*) FROM pg_locks WHERE pid='+str(int(report['claimLock']['held']['pid']))+" AND locktype='advisory';");assert report['claimLockAfter']==0
    except Exception as error:errors.append(dict(operation='claim_cleanup_verification',errorType=type(error).__name__))
    report['cleanupErrors']=errors
    if errors:report['status']='FAIL'
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'catalog-cancel-fault-fresh-probe.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],cleanupErrors=errors)))
if report['status']!='PASS':raise SystemExit(1)
