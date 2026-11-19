"""正式取消端点的双旁路观察，只输出任务、源查询 ID 及引擎事件类别。"""
import argparse
import contextlib
import datetime
import json
import queue
import signal
import re
import subprocess
import threading
import time
import uuid

import workflow_doris_vm as vm
from workflow_doris_s0_fixture import CLIENT, DIRECTORY, INDEX, record, stress_binding
from workflow_doris_s1 import OUT, live_stack


def emit(event, **facts):
    print(json.dumps(dict(event=event,**facts)),flush=True)


@contextlib.contextmanager
def channel(command, password=None):
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
    lines=queue.Queue()
    def read():
        for line in process.stdout: lines.put(line.decode().strip())
        lines.put(None)
    threading.Thread(target=read,daemon=True).start()
    if password: process.stdin.write(password+b'\n')
    def one(sql):
        process.stdin.write(sql.encode()+b'\n')
        raw=lines.get(timeout=3)
        vm.demand(raw is not None,'WITNESS_CLIENT_EXIT')
        return raw
    try: yield one
    finally:
        process.stdin.close()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)


def cancellation_order(events, visible):
    """仅比较共享 VM 时钟的微秒；读见已提交 CANCELLED 是保守上界，不冒充精确提交时刻。"""
    if not visible:
        return False
    seen = datetime.datetime.fromisoformat(visible).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    stamps = {}
    for event in events:
        stamps.setdefault(event['kind'],[]).append(datetime.datetime.strptime(event['beUtc'],'%Y%m%d %H:%M:%S.%f'))
    required = ('registered','cancel_arrived','task_cancelled','fragment_end','context_end')
    if not all(stamps.get(kind) for kind in required):
        return False
    return (min(stamps['registered']) <= seen <= min(stamps['cancel_arrived']) <= min(stamps['task_cancelled'])
            and max(stamps['task_cancelled']) <= max(stamps['fragment_end']) <= max(stamps['context_end']))


def canonical_id(value):
    halves=value.lower().split('-')
    vm.demand(len(halves)==2 and all(re.fullmatch('[0-9a-f]{1,16}',v) for v in halves),'WITNESS_QUERY_ID')
    return '-'.join(v.zfill(16) for v in halves)


@contextlib.contextmanager
def registered_queries(container, begin):
    """只缓存本次准确 BE 的实时注册 ID，持续排空引擎输出。"""
    process = subprocess.Popen(['docker','--context','desktop-linux','logs','--since',begin,'--follow',container],
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    seen, ended = set(), set()
    def consume():
        for raw in process.stdout:
            match=re.search(rb'\b([0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16})\b',raw)
            if match:
                identity=canonical_id(match.group(1).decode())
                if b'fragment_mgr.cpp:729]' in raw and b'total fragment num' in raw: seen.add(identity)
                if b'query_context.cpp:262]' in raw and b'deconstructed' in raw: ended.add(identity)
    worker = threading.Thread(target=consume,daemon=True)
    worker.start()
    try: yield seen, ended
    finally:
        process.terminate()
        process.wait(timeout=3)
        worker.join(2)


def watch(key, admit_first=False, overlap=False):
    ids=live_stack()
    state=json.loads(INDEX.read_bytes())
    stress=stress_binding(state)
    vm.demand(str(uuid.UUID(key))==key,'CANCEL_KEY')
    prefix=['docker','--context','desktop-linux','exec','-i']
    pg=[*prefix,ids['platform-pg'],'psql','-XwqAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','mapping']
    fe=[*prefix,ids['fe'],'bash','-ec',CLIENT,'source','root','--skip-column-names']
    observed=dict(stress=stress,idempotencyKey=key,run=vm.RUN,taskId=vm.TASK,be=ids['be'],fe=ids['fe'])
    file=OUT/('formal-cancel-'+key+'.json')
    def mark(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')
    # 只匹配固定产品模板的 fixture_reader 会话；观察 SQL 运行于不同主体。
    scan="""SELECT IFNULL(MAX(QUERY_ID),'absent') FROM information_schema.active_queries WHERE USER='fixture_reader' AND SQL LIKE '%SET_VAR(enable_sql_cache=false)%' AND SQL LIKE '%FROM fixture.dmq_entity%';"""
    lookup='''SELECT COALESCE((SELECT "Id" FROM semantic_query."Queries" WHERE "OrganizationId"='org-demo' AND "IdempotencyKey"='%s'),'absent');'''%key
    with contextlib.ExitStack() as stack:
        platform=stack.enter_context(channel(pg))
        source=stack.enter_context(channel(fe,(DIRECTORY/'root.pass').read_bytes()))
        if overlap:
            locker=stack.enter_context(channel(pg))
            locker_pid=int(locker("SELECT pg_backend_pid();"))
            registered,ended=stack.enter_context(registered_queries(ids['be'],mark()))
            vm.demand(source("SELECT /*+ SET_VAR(enable_sql_cache=false) */ COUNT(*) FROM fixture.dmq_target WHERE target_id='T3';")=='1','OVERLAP_CONTROL')
            control=canonical_id(source("SELECT LAST_QUERY_ID();"))
            until=time.monotonic()+3
            while time.monotonic()<until and not (control in registered and control in ended): time.sleep(.001)
            vm.demand(control in registered and control in ended,'OVERLAP_BE_SUBSCRIBED')
            observed['observerControlQueryId']=control
            clock_ids=[subprocess.check_output(['docker','--context','desktop-linux','exec',ids[role],'readlink','/proc/1/ns/time'],text=True,timeout=3).strip() for role in ('be','platform-pg')]
            vm.demand(clock_ids[0]==clock_ids[1] and re.fullmatch(r'time:\[\d+\]',clock_ids[0]),'OVERLAP_VM_CLOCK')
            observed['vmTimeNamespace']=clock_ids[0]
            scan="SELECT CONCAT(COUNT(*),'/',IFNULL(MAX(QueryId),'absent'),'/',IFNULL(MAX(Id),0)) FROM information_schema.processlist WHERE User='fixture_reader' AND Info LIKE '%SET_VAR(enable_sql_cache=false)%' AND Info LIKE '%FROM fixture.dmq_entity%';"
            permit=OUT/('overlap-permit-'+key+'.json')
            vm.demand(not permit.exists() and stress['rowsByTable']=={'dmq_entity':4194304,'dmq_target':3},'OVERLAP_SCOPE')
            stack.callback(permit.unlink,missing_ok=True)
        vm.demand(platform(lookup)=='absent' and source(scan)==('0/absent/0' if overlap else 'absent'),'WITNESS_INITIAL_STATE')
        def load_sample():
            return json.loads(platform("""SELECT json_build_object('clock',clock_timestamp(),'serverStarted',pg_postmaster_start_time(),
                'since',d.stats_reset,'commits',d.xact_commit,'rollbacks',d.xact_rollback,'reads',d.blks_read,'hits',d.blks_hit,
                'queryTableIndexScans',t.idx_scan,'queryTableSequentialScans',t.seq_scan)
                FROM pg_stat_database d,pg_stat_user_tables t WHERE d.datname=current_database()
                AND t.schemaname='semantic_query' AND t.relname='Queries';""".replace('\n',' ')))
        observed['loadBefore']=load_sample()
        begin=mark()
        emit('ready')
        end=time.monotonic()+(18 if overlap else 8)
        app_id=qid=None
        delivered=False
        while time.monotonic()<end:
            # 独立平台键先命中，随后采样 FE；两个准确 ID 同属当前唯一业务投递。
            if app_id is None:
                value=platform(lookup)
                if re.fullmatch('query-[a-f0-9]{32}',value):
                    app_id=value
                    observed['admissionObservedAt']=mark()
                    if overlap:
                        lock_deadline=time.monotonic()+.72
                        locked=locker("BEGIN; SET LOCAL idle_in_transaction_session_timeout='2s'; SELECT \"ExecutionStatus\" FROM semantic_query.\"Queries\" WHERE \"Id\"='"+app_id+"' AND \"IdempotencyKey\"='"+key+"' FOR UPDATE;")
                        vm.demand(locked=='RUNNING','OVERLAP_ROW_NOT_RUNNING')
                        observed.update(lockerPid=locker_pid,lockedQueryId=app_id)
                    if admit_first or overlap:
                        emit('admitted',queryId=app_id)
                        delivered=True
            if overlap and delivered and 'waiterPid' not in observed:
                count,wait=platform("SELECT count(*)||'/'||coalesce(max(pid),0) FROM pg_stat_activity WHERE "+str(locker_pid)+"=ANY(pg_blocking_pids(pid)) AND wait_event_type='Lock' AND query LIKE '%semantic_query.%Queries%FOR UPDATE%';").split('/')
                vm.demand(count in ('0','1'),'OVERLAP_MULTIPLE_WAITERS')
                if count=='1':
                    observed.update(waiterPid=int(wait),verifiedWaitPgUtc=platform("SELECT clock_timestamp();"))
                    record(file,observed)
                    record(permit,dict(key=key,queryId=app_id,waiterPid=int(wait)))
            if overlap and delivered and time.monotonic()>lock_deadline: break
            current=source(scan)
            if overlap:
                matches,current,physical=current.split('/')
                vm.demand(matches in ('0','1'),'OVERLAP_AMBIGUOUS_SOURCE')
                if matches=='1':
                    observed['sourceThread']=int(physical)
                    vm.demand(qid is None or canonical_id(qid)==canonical_id(current),'OVERLAP_SOURCE_CHANGED')
            if re.fullmatch('[0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16}',current):
                qid=current.lower()
                observed.setdefault('feActiveObservedAt',mark())
            if app_id and qid:
                if not overlap: break
                if canonical_id(qid) in registered and canonical_id(qid) not in ended:
                    observed['liveWitness']='registered_log'
                if 'liveWitness' in observed and 'waiterPid' in observed:
                    cleanup_begin=time.monotonic_ns()
                    observed['beforeUnlockPgUtc']=platform("SELECT clock_timestamp();")
                    observed['afterUnlockPgUtc']=locker("ROLLBACK; SELECT clock_timestamp();")
                    record(file,observed)
                    break
            if delivered and platform('SELECT "ExecutionStatus" FROM semantic_query."Queries" WHERE "Id"='+repr(app_id)+';') != 'RUNNING': break
            time.sleep(.001)
        observed.update(queryId=app_id,sourceQueryId=qid)
        if overlap and 'afterUnlockPgUtc' not in observed:
            observed['syncStatus']='NO_ACTIVE_BE_AT_UNLOCK'
            record(file,observed)
            emit('miss',**observed)
            return
        if not app_id or (not qid and not admit_first):
            record(file,observed)
            emit('miss',**observed)
            return
        if not delivered: emit('active',queryId=app_id,sourceQueryId=qid)
        record(file,observed)
        # 端点执行与观察并行；最终事实取 PostgreSQL 持久状态及同一 BE QueryId。
        stop=time.monotonic()+5
        status='RUNNING'
        while time.monotonic()<stop and status=='RUNNING':
            visible = json.loads(platform("""SELECT json_build_object('state',"ExecutionStatus",'observed',clock_timestamp())
                FROM semantic_query."Queries" WHERE "Id"='""".replace('\n',' ')+app_id+"';"))
            status = visible['state']
            if status=='CANCELLED':
                observed['cancelVisiblePgUtc']=visible['observed']
            if status=='RUNNING': time.sleep(.005)
        observed.update(terminal=status,terminalObservedAt=mark())
        observed['sourceCounts']=None if qid is None else source("SELECT (SELECT count(*) FROM information_schema.active_queries WHERE QUERY_ID='"+qid+"'),(SELECT count(*) FROM information_schema.backend_active_tasks WHERE QUERY_ID='"+qid+"');")
        safe=platform('''SELECT json_build_object('bytes',octet_length("ResultCiphertext"),'resultHash',"ResultHash",'resultSize',"ResultSize",'readReceipts',jsonb_array_length(convert_from("BindingBytes",'UTF8')::jsonb->'receipts'),'completedAtUtc',"CompletedAtUtc",'cancelRequested',"CancelRequested") FROM semantic_query."Queries" WHERE "Id"='%s';'''%app_id)
        observed['persisted']=json.loads(safe)
        observed['successfulAuditCount']=int(platform('''SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.execute' AND "Outcome"='allowed' AND "Resource"='%s';'''%app_id))
        observed['cancelAuditCount']=int(platform('''SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.cancel' AND "Outcome"='allowed' AND "Resource"='%s';'''%app_id))
        # 只读统计包含整库活动与旁路，平台对外可见的采样刻度单独记录。
        observed['loadAfter']=load_sample()
        if qid and status=='CANCELLED':
            until=time.monotonic()+.25
            if overlap: until=cleanup_begin/1.e9+.25
            while observed['sourceCounts']!='0\t0' and time.monotonic()<until:
                observed['sourceCounts']=source("SELECT (SELECT count(*) FROM information_schema.active_queries WHERE QUERY_ID='"+qid+"'),(SELECT count(*) FROM information_schema.backend_active_tasks WHERE QUERY_ID='"+qid+"');")
            observed['sourceCountsObservedAt']=mark()
            if overlap: observed['dualZeroUpperMs']=(time.monotonic_ns()-cleanup_begin)/1.e6
        # 不返回 BE 日志正文。只解析本次准确 QueryId 与固定版本源码位置的交集。
        logs=subprocess.run(['docker','--context','desktop-linux','logs','--since',begin,ids['be']],capture_output=True,timeout=6,check=True)
        events=[]
        for line in (logs.stdout+b'\n'+logs.stderr).decode(errors='replace').splitlines():
            match_id=re.search(r'\b([0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16})\b',line)
            if not qid or not match_id or canonical_id(qid)!=canonical_id(match_id.group(1)): continue
            for label,location,term in [('registered','fragment_mgr.cpp:729]','total fragment num'),
                ('cancel_arrived','internal_service.cpp:637]','cancel query by user'),
                ('task_cancelled','task_scheduler.cpp:84]','cancel query by user'),
                ('fragment_end','pipeline_fragment_context.cpp:142]','~PipelineFragmentContext'),
                ('context_end','query_context.cpp:262]','deconstructed')]:
                match=re.match(r'^[IWE](\d{8} \d\d:\d\d:\d\d\.\d+)',line)
                if match and location in line and term in line and (label!='task_cancelled' or '[CANCELLED]' in line): events.append(dict(kind=label,beUtc=match.group(1)))
        observed['beEvents']=events
        observed['cancelVisibleBeforeBeKilled']=cancellation_order(events,observed.get('cancelVisiblePgUtc'))
        if overlap and events and observed.get('cancelVisiblePgUtc'):
            started=[e['beUtc'] for e in events if e['kind']=='registered']
            ended=[e['beUtc'] for e in events if e['kind']=='context_end']
            if started and ended:
                def pg_time(value): return datetime.datetime.fromisoformat(value).astimezone(datetime.timezone.utc).replace(tzinfo=None)
                def be_time(value): return datetime.datetime.strptime(value,'%Y%m%d %H:%M:%S.%f')
                release=pg_time(observed['beforeUnlockPgUtc'])
                observed['activeBeforeUnlock']=be_time(min(started))<=release<be_time(max(ended))
                observed['cleanupUpperMs']=(be_time(max(ended))-release).total_seconds()*1000
        record(file,observed)
        emit('finished',**observed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('key')
    parser.add_argument('--admit-first',action='store_true')
    parser.add_argument('--overlap',action='store_true')
    args=parser.parse_args()
    if args.overlap:
        def unwind(signum, frame):
            raise SystemExit(128+signum)
        signal.signal(signal.SIGTERM,unwind)
    watch(args.key,args.admit_first,args.overlap)
