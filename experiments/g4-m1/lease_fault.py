"""真实源锁、API暂停与第二实例租约接管；所有自身故障有独立期限和finally恢复。"""
from pathlib import Path
import datetime, hashlib, importlib.util, ipaddress, json, os, selectors, subprocess, threading, time

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE = ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
TASK = 'G4-M1-RECOVERY-001'
RUN = 'recovery-20261101-01'
CONNECTION = '1bf23f9d36bf4ceba09d745f04d8f743'
records = []
cleanup_errors = []
docker = ['docker', '--context', 'desktop-linux']
replica = None
source_lock = None
observer = None
paused = False
result = dict(taskId=TASK, status='FAIL', commands=records)

def command(argv, timeout=15, stdin=None, env=None):
    started = time.monotonic()
    try:
        x = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        records.append(dict(command=argv,input=stdin,exitCode=None,timingStatus='TIMEOUT',elapsedSeconds=time.monotonic()-started))
        raise
    records.append(dict(command=argv, input=stdin, exitCode=x.returncode,
                        elapsedSeconds=time.monotonic()-started, stdout=x.stdout, stderr=x.stderr))
    assert x.returncode == 0
    return x.stdout.strip()

def inspect(name):
    obj = json.loads(subprocess.check_output(docker+['inspect', name], text=True, timeout=10))[0]
    assert obj['Config']['Labels']['ontology.task-id'] == TASK
    assert obj['Config']['Labels']['ontology.run-id'] == RUN
    return obj

source = inspect('ontology-g4-m1-recovery-001-pg-source-1')['Id']
platform = inspect('ontology-g4-m1-recovery-001-platform-pg-1')['Id']
api_info = inspect('ontology-g4-m1-recovery-001-api-1')
api = api_info['Id']
api_addresses = {value['IPAddress'] for value in api_info['NetworkSettings']['Networks'].values()}
result['apiIdentity']={'id':api,'addresses':sorted(api_addresses)}

def is_api_waiter(value):
    return value['waitType']=='Lock' and str(ipaddress.ip_interface(value['clientAddr']).ip) in api_addresses
def db(sql):
    assert inspect(platform)['Id'] == platform
    return command(docker+['exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt'], stdin="SET lock_timeout='2s'; SET statement_timeout='5s';"+sql)

ACTIVITY_SQL="SELECT coalesce(json_agg(json_build_object('pid',pid,'state',state,'waitType',wait_event_type,'wait',wait_event,'user',usename,'database',datname,'clientAddr',client_addr::text)),'[]') FROM pg_stat_activity WHERE backend_type='client backend' AND client_addr IS NOT NULL"
def observer_query(sql):
    observer.stdin.write(sql+'\n');observer.stdin.flush()
    sel=selectors.DefaultSelector();sel.register(observer.stdout,selectors.EVENT_READ)
    try:assert sel.select(4);line=observer.stdout.readline();value=json.loads(line)
    finally:sel.close()
    records.append(dict(operation='prepared_source_observer',sql=sql,value=value))
    return value

def source_state():
    if observer and observer.poll() is None:return observer_query('EXECUTE recovery_activity;')
    return json.loads(command(docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],stdin="SET statement_timeout='2s'; "+ACTIVITY_SQL+';'))

def open_observer():
    global observer
    argv=docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt']
    observer=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    records.append(dict(operation='open_source_observer',command=argv,pid=observer.pid))
    observer_query("SET application_name='g4_m1_recovery_observer'; SET statement_timeout='2s'; SET idle_session_timeout='90s'; SET plan_cache_mode=force_generic_plan; PREPARE recovery_activity AS "+ACTIVITY_SQL+'; EXECUTE recovery_activity;')

def close_observer():
    if observer and observer.poll() is None:
        observer.stdin.write('\\q\n');observer.stdin.flush();observer.wait(timeout=5)


def action(name):
    out=command(['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(PRIVATE/'http-schema-change.json'),'--action',name],timeout=45)
    return json.loads((ROOT/json.loads(out)['evidence']).read_text())

def state(job):
    assert len(job)==32 and all(c in '0123456789abcdef' for c in job)
    return json.loads(db('SELECT json_build_object(\'status\',"Status",\'fence\',"Fence",\'attempt\',"Attempt",\'leaseUntil\',"LeaseUntil",\'expired\',"LeaseUntil"<now(),\'snapshot\',"SnapshotId",\'diagnostic\',"DiagnosticCode") FROM connections."CatalogJobs" WHERE "Id"=\''+job+'\';'))

def totals():
    return json.loads(db('SELECT json_build_object(\'snapshots\',(SELECT count(*) FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+CONNECTION+'\'),\'finishAudits\',(SELECT count(*) FROM governance.audit_records WHERE "Resource"=\'connection:'+CONNECTION+'\' AND "Action"=\'connection.catalog.finish\'));'))

def restore_api():
    obj=inspect(api)
    if obj['State']['Paused']:
        command(docker+['unpause',api])

def safe_cleanup(name,operation):
    try: operation()
    except Exception as error: cleanup_errors.append(dict(operation=name,errorType=type(error).__name__))

def release_lock():
    if source_lock and source_lock.poll() is None:
        try:
            source_lock.stdin.write('ROLLBACK;\n\\q\n'); source_lock.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

spec=importlib.util.spec_from_file_location('recovery_runtime',ROOT/'scripts/acceptance/g4-m1-runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
compose=runtime.compose()+['-f',str(ROOT/'experiments/g4-m1/compose.recovery-fault.yaml'),'--profile','recovery-fault']
guard=threading.Timer(100,lambda:safe_cleanup('deadline_api_unpause',restore_api))
lock_guard=threading.Timer(55,lambda:safe_cleanup('deadline_lock_release',release_lock))
try:
    running=subprocess.check_output(docker+['ps','-q'],text=True,timeout=10).split()
    assert len(running)==5
    assert sum(inspect(x)['HostConfig']['Memory'] for x in running)==4831838208
    existing=command(docker+['ps','-aq','--filter','name=^/ontology-g4-m1-recovery-001-api-recovery-1$'])
    assert not existing
    result['replicaNameAbsentBefore']=True
    # create只建立准确第六资源，租约过期前不启动第二消费者。
    command(compose+['create','--no-build','--no-recreate','--pull','never','api-recovery'],timeout=30,env=runtime.environment())
    obj=inspect('ontology-g4-m1-recovery-001-api-recovery-1');replica=obj['Id']
    assert not obj['State']['Running'] and obj['HostConfig']['Memory']==1073741824
    assert obj['HostConfig']['ReadonlyRootfs'] and not obj['HostConfig']['PortBindings']
    assert obj['Config']['Image']=='mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
    result['replicaId']=replica
    action('probe-refresh');before=totals();result['before']=before
    open_observer()
    argv=docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt']
    source_lock=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    sql="SET application_name='g4_m1_recovery_lease_lock'; SET lock_timeout='2s'; SET statement_timeout='60s'; SET idle_in_transaction_session_timeout='60s'; BEGIN; LOCK TABLE pg_catalog.pg_attribute IN ACCESS EXCLUSIVE MODE; SELECT json_build_object('lockPid',pg_backend_pid(),'granted',exists(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND relation='pg_catalog.pg_attribute'::regclass AND mode='AccessExclusiveLock' AND granted));\n"
    source_lock.stdin.write(sql);source_lock.stdin.flush()
    selector=selectors.DefaultSelector();selector.register(source_lock.stdout,selectors.EVENT_READ);assert selector.select(5)
    lock_ready=json.loads(source_lock.stdout.readline());selector.close();assert lock_ready['granted']
    result['sourceLock']=dict(command=argv,input=sql,ready=lock_ready);lock_guard.start();guard.start()
    job=action('job-start')['jobId'];result['jobId']=job
    deadline=time.monotonic()+2
    while True:
        first=state(job)
        if first['status']=='RUNNING':break
        assert time.monotonic()<deadline;time.sleep(.05)
    assert first['fence']==1 and first['attempt']==1
    deadline=time.monotonic()+2
    while True:
        waiting=source_state()
        if any(is_api_waiter(x) for x in waiting):break
        assert time.monotonic()<deadline;time.sleep(.05)
    result['sourceBeforePause']=waiting
    command(docker+['pause',api]);paused=True;result['firstClaim']=first
    result['sourceDuringPause']=source_state()
    assert any(is_api_waiter(x) for x in result['sourceDuringPause'])
    deadline=time.monotonic()+34
    while True:
        expired=state(job)
        assert expired['status']=='RUNNING' and expired['fence']==1
        if expired['expired']:break
        assert time.monotonic()<deadline;time.sleep(.4)
    result['expiredClaim']=expired
    command(docker+['start',replica],timeout=20)
    all_running=subprocess.check_output(docker+['ps','-q'],text=True,timeout=10).split();assert len(all_running)==6
    result['runningBudget']=dict(containers=6,memoryBytes=sum(inspect(x)['HostConfig']['Memory'] for x in all_running))
    assert result['runningBudget']['memoryBytes']==5905580032
    deadline=time.monotonic()+10
    while True:
        second=state(job)
        if second['fence']==2:break
        assert time.monotonic()<deadline;time.sleep(.1)
    assert second['status']=='RUNNING' and second['attempt']==2
    result['secondClaim']=second
    release_lock();lock_guard.cancel()
    source_lock.wait(timeout=5)
    result['sourceLock']['exitCode']=source_lock.returncode;assert source_lock.returncode==0
    deadline=time.monotonic()+10
    while True:
        completed=state(job)
        if completed['status'] not in ('RUNNING','QUEUED'):break
        assert time.monotonic()<deadline;time.sleep(.2)
    assert completed['status']=='SUCCEEDED' and completed['snapshot']
    result['completed']=completed;after=totals();result['afterReplica']=after
    assert after==dict(snapshots=before['snapshots']+1,finishAudits=before['finishAudits']+1)
    restore_api();paused=False
    deadline=time.monotonic()+8
    while True:
        remaining=source_state()
        if not any(x['pid'] in {v['pid'] for v in result['sourceDuringPause']} for x in remaining):break
        assert time.monotonic()<deadline;time.sleep(.2)
    result['oldSourceBackendsGone']=True
    time.sleep(5.5)
    result['afterOldWorkerResumed']=state(job);result['totalsAfterOldWorkerResumed']=totals()
    assert result['afterOldWorkerResumed']==completed and result['totalsAfterOldWorkerResumed']==after
    result['status']='PASS'
except Exception as error:
    result['failureType']=type(error).__name__
    raise
finally:
    # 各项独立清理，源/副本命令失败不能阻断原API恢复和最终witness。
    safe_cleanup('api_unpause',restore_api);guard.cancel()
    safe_cleanup('source_rollback',release_lock);lock_guard.cancel()
    if source_lock:
        safe_cleanup('source_process_wait',lambda:source_lock.wait(timeout=5))
        if source_lock.poll() is None:
            safe_cleanup('source_process_terminate',source_lock.terminate)
            safe_cleanup('source_process_final_wait',lambda:source_lock.wait(timeout=5))
    if replica:
        def remove_replica():
            obj=inspect(replica)
            assert obj['Id']==replica and obj['Config']['Labels'].get('ontology.purpose')=='lease-fence-fault'
            command(docker+['stop','--time','5',replica]);command(docker+['rm',replica])
        safe_cleanup('exact_replica_remove',remove_replica)
    result['cleanup']={}
    def verify_cleanup():
        result['cleanup'].update(apiPaused=inspect(api)['State']['Paused'],sourceSessions=source_state(),replicaAbsent=not bool(command(docker+['ps','-aq','--filter','name=^/ontology-g4-m1-recovery-001-api-recovery-1$'])))
        if 'sourceLock' in result:
            lock_pid=int(result['sourceLock']['ready']['lockPid'])
            locks=command(docker+['exec','-i',source,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],stdin="SET statement_timeout='2s'; SELECT count(*) FROM pg_locks WHERE pid="+str(lock_pid)+" AND relation='pg_catalog.pg_attribute'::regclass;")
            result['cleanup']['sourceLockCount']=int(locks);assert locks=='0'
        assert result['cleanup']['apiPaused'] is False and result['cleanup']['replicaAbsent'] is True
    safe_cleanup('cleanup_verification',verify_cleanup)
    safe_cleanup('close_source_observer',close_observer)
    if observer:result['observerExit']={'pid':observer.pid,'exitCode':observer.poll()}
    result['cleanupErrors']=cleanup_errors
    if cleanup_errors:result['status']='FAIL'
    result['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'lease-fault-client-observer.json','x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],cleanup=result['cleanup'],cleanupErrors=cleanup_errors)))

if result['status']!='PASS':raise SystemExit(1)
