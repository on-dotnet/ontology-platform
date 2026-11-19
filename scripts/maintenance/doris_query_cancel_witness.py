"""正式取消端点的双旁路观察，只输出任务、源查询 ID 及引擎事件类别。"""
import argparse
import contextlib
import datetime
import json
import hashlib
from pathlib import Path
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
import doris_query_profile_witness as task_profile


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


@contextlib.contextmanager
def pipeline_sampler(container):
    """预置单个独立只读通道，消除每一笔样本启动 docker 客户端的开销。"""
    script = Path(__file__).with_name('doris_pipeline_observer.py').read_text()
    process = subprocess.Popen(['docker','--context','desktop-linux','exec','-i',container,
                                'python3','-u','-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,text=True)
    received = queue.Queue()
    def drain():
        for line in process.stdout:
            received.put(line.strip())
        received.put(None)
    worker = threading.Thread(target=drain,daemon=True)
    worker.start()
    try:
        first = json.loads(received.get(timeout=5))
        vm.demand(first['ready'] and first['baseline']==0,'PIPELINE_BASELINE')
        def arm():
            process.stdin.write('collect\n')
            process.stdin.flush()
            vm.demand(received.get(timeout=2)=='armed','PIPELINE_ARM_FAILED')
        def read_all():
            data=[]
            issues=[]
            deadline=time.monotonic()+3
            while len(data)<=260 and time.monotonic()<deadline:
                line=received.get(timeout=max(.001,deadline-time.monotonic()))
                if line is None:
                    issues.append('PIPELINE_OBSERVER_EXIT')
                    break
                row=json.loads(line)
                if 'observationError' in row:
                    issues.append(row['observationError'])
                elif row.get('finished'):
                    if row['count']!=len(data): issues.append('PIPELINE_COUNT_MISMATCH')
                    break
                else:
                    data.append(row)
            else: issues.append('PIPELINE_STREAM_LIMIT')
            return data,issues
        yield arm,read_all
    finally:
        process.stdin.close()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=2)
        worker.join(1)


def instant_ns(value):
    stamp=datetime.datetime.fromisoformat(value)
    return int(stamp.timestamp())*1_000_000_000 + stamp.microsecond*1000


def engine_stamp(raw):
    return datetime.datetime.strptime(raw,'%Y%m%d %H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc).isoformat()


def fe_terminal(container, identity):
    """只公开准确 FE 查询的 AFTER_QUERY 审计白名单字段。"""
    audit_path='/opt/apache-doris/fe/log/fe.audit.log'
    cmd=['docker','--context','desktop-linux','exec',container]
    tag='|QueryId='+identity+'|'
    # AFTER_QUERY 可异步落盘，验收只用原事件的终态采样时刻。
    deadline=time.monotonic()+14
    while True:
        proc=subprocess.run([*cmd,'grep','-F',tag,audit_path],capture_output=True,timeout=2)
        if proc.returncode!=1 or time.monotonic()>=deadline: break
        time.sleep(.25)
    if proc.returncode!=0: return dict(complete=False)
    rows=proc.stdout.splitlines()
    if len(rows)!=1: return dict(complete=False)
    head,sep,statement=rows[0].decode().partition('|Stmt=')
    if not sep: return dict(complete=False)
    pairs=[part.split('=',1) for part in head.split('|')[1:] if '=' in part]
    fields=dict(pairs)
    if len(fields)!=len(pairs): return dict(complete=False)
    inode=subprocess.check_output([*cmd,'stat','-c','%i',audit_path],text=True,timeout=2).strip()
    statement_hash=hashlib.sha256(statement.encode()).hexdigest()
    if fields.get('QueryId')!=identity: return dict(complete=False)
    start=datetime.datetime.fromisoformat(fields['Timestamp']).replace(tzinfo=datetime.timezone.utc)
    end=start+datetime.timedelta(milliseconds=int(fields['Time(ms)']))
    err=fields.get('ErrorMessage','').lower()
    return dict(complete=True,query=identity,state=fields['State'],errorCode=fields['ErrorCode'],
                userCancel='cancel query by user' in err,timeout='timeout' in err,
                reader=fields.get('User')=='fixture_reader',statementSha256=statement_hash,
                auditInode=inode,fixedEntity=statement_hash=='779405d77852bb511c189d4b0a404932b51eec629a56ca006debcf4a051ef564',
                isSelect=fields.get('StmtType')=='SELECT',returnRows=int(fields['ReturnRows']),
                startUtc=start.isoformat(),durationMs=int(fields['Time(ms)']),endUtc=end.isoformat(),
                endExclusiveUpperUtc=(end+datetime.timedelta(milliseconds=1)).isoformat(),
                lineSha256=hashlib.sha256(rows[0]).hexdigest(),sqlHash=fields.get('SqlHash'))



def native_task_closes(native, groups, arrival, ended):
    """根据同一原生线程的取消、实例和关闭顺序定位任务。多任务实例保留歧义。"""
    rows = native['events']
    cancel_sites = {'user_rpc', 'fragment_cancel', 'task_close_error', 'broadcast_return', 'coordinator_error'}
    if any((r['event'] in cancel_sites and not r['userCancel']) or
           (r['event'] == 'other' and r['level'] in ('W', 'E')) for r in rows):
        return {}, set()
    lifecycle = {site: [r for r in rows if r['event']==site and r['queryField']]
                 for site in ('register','user_rpc','context_end')}
    if (any(len(matching)!=1 for matching in lifecycle.values()) or
        instant_ns(engine_stamp(lifecycle['register'][0]['timestamp'])) >= arrival or
        instant_ns(engine_stamp(lifecycle['user_rpc'][0]['timestamp'])) != arrival or
        instant_ns(engine_stamp(lifecycle['context_end'][0]['timestamp'])) != ended):
        return {}, set()
    by_instance = {}
    for group in groups:
        for task in group['tasks']:
            by_instance.setdefault(task['instance'], set()).add(task['task'])
    by_fragment = {}
    closed = set()
    workers = {}
    for row in sorted(rows, key=lambda event: (event['timestamp'], event['offset'])):
        if not arrival <= instant_ns(engine_stamp(row['timestamp'])) <= ended:
            continue
        worker = row['tid']
        if row['event'] == 'fragment_cancel' and row['queryField'] and row['fragment'] is not None:
            workers[worker] = (row['fragment'], None)
        elif row['event'] == 'instance_cancel' and worker in workers:
            fragment, _ = workers[worker]
            instance = row['instance']
            if instance not in by_instance or by_fragment.setdefault(fragment, instance) != instance:
                return {}, set()
            workers[worker] = (fragment, instance)
        elif row['event'] == 'task_close_error' and row['queryField']:
            _, instance = workers.pop(worker, (None, None))
            candidates = by_instance.get(instance, set())
            if len(candidates) == 1:
                closed.add((canonical_id(instance), next(iter(candidates))))
    if set(by_fragment.values()) != set(by_instance) or len(set(by_fragment.values())) != len(by_fragment):
        return {}, set()
    return by_fragment, closed


def equivalent_termination(observed, samples, raw_lines):
    """从完整的任务集合、取消原因、时钟及终态回执独立判定。历史统计另存。"""
    identity=observed['sourceQueryId']
    qid=canonical_id(identity)
    anchor=instant_ns(observed['beforeUnlockPgUtc'])
    visible=instant_ns(observed['cancelVisiblePgUtc'])
    first=samples[0]
    clock_drift=max(abs((x['beginNs']-first['beginNs'])-(x['beginMonoNs']-first['beginMonoNs']))+
                    abs((x['endNs']-x['beginNs'])-x['elapsedNs']) for x in samples)
    deadline=anchor+250_000_000-clock_drift
    relevant=[]
    for sample in samples:
        groups=[group for group in sample['groups'] if group['query'] and canonical_id(group['query'])==qid]
        relevant.append(dict(beginNs=sample['beginNs'],endNs=sample['endNs'],complete=sample['complete'],
                             globalCount=sample['count'],groups=groups,sha256=sample['sha256']))
    exact=[]
    instances=set()
    for sample in relevant:
        for group in sample['groups']:
            instances.update(canonical_id(task['instance']) for task in group['tasks'])
    for line in raw_lines:
        timestamp=re.match(r'^[IWE](\d{8} \d\d:\d\d:\d\d\.\d+)',line)
        ids=re.findall(r'\b[0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16}\b',line)
        if not timestamp or not ids: continue
        first=canonical_id(ids[0])
        kind=None
        extra={}
        if first==qid:
            if 'fragment_mgr.cpp:729]' in line:
                found=re.search(r'total fragment num on current host: (\d+)',line)
                if found: kind='registered';extra['expectedFragments']=int(found[1])
            elif 'internal_service.cpp:637]' in line and 'cancel query by user' in line:
                kind='user_cancel_rpc'
            elif 'pipeline_fragment_context.cpp:177]' in line and 'cancel query by user' in line:
                kind='fragment_cancel'
            elif 'pipeline_fragment_context.cpp:142]' in line:
                kind='fragment_end'
            elif 'fragment_mgr.cpp:941]' in line and 'cancel query by user' in line:
                kind='cancel_broadcast_returned'
            elif 'query_context.cpp:262]' in line:
                kind='context_end'
            elif 'task_scheduler.cpp:84]' in line:
                kind=('user_cancel_task_close' if '[CANCELLED]' in line and 'cancel query by user' in line
                      else 'other_task_error')
            elif 'fragment_mgr.cpp:571]' in line and 'cancel query by user' in line:
                kind='coordinator_cancel_error'
            if kind in ('fragment_end','fragment_cancel'):
                match=re.search(r'fragment_id[=:] ?(\d+)',line)
                if not match: continue
                extra['fragment']=int(match[1])
        if first in instances and 'pipeline_fragment_context.cpp:218]' in line:
            kind='cancel_instance';extra['instance']=first
        if kind:
            exact.append(dict(event=kind,utc=engine_stamp(timestamp[1]),lineSha256=hashlib.sha256(line.encode()).hexdigest(),**extra))
    def events(kind):
        return [row for row in exact if row['event']==kind]
    regs=events('registered')
    expected=regs[0]['expectedFragments'] if len(regs)==1 else None
    cancels=events('user_cancel_rpc')
    arrival=instant_ns(cancels[0]['utc']) if len(cancels)==1 else 0
    # 行锁释放只作清理计时锚点。单条独立 READ COMMITTED 的 RUNNING 观察可进一步约束真实提交。
    running_times=[instant_ns(row['statement']) for row in observed.get('platformStates',[])
                   if row['state']=='RUNNING' and row['isolation']=='read committed' and row['query']==observed['queryId']]
    before_commit=max([anchor,*running_times])
    before=[x for x in relevant if x['complete'] and x['groups'] and len(x['groups'])==expected
            and x['endNs']+clock_drift<=before_commit]
    snapshot=before[-1] if before else None
    pending=[]
    if snapshot:
        for group in snapshot['groups']:
            active=[t for t in group['tasks'] if t['state'].upper() not in ('FINISHED','FINALIZED')]
            if len(active)!=group['total']-group['closed']:
                snapshot=None
                break
            pending.extend(active)
    def task_key(t): return (canonical_id(t['instance']),t['task'])
    wanted={task_key(task) for task in pending}
    end_events=events('context_end')
    ended=instant_ns(end_events[0]['utc']) if len(end_events)==1 else 0
    # 所有执行实例退出后再从独立全任务视图得到完整 0，禁止拿查询索引消失或窗口外 0 作证。
    empty=next((x for x in relevant if x['complete'] and x['globalCount']==0 and x['beginNs']>=ended>arrival and x['endNs']<=deadline),None)
    cancel_instances={x['instance'] for x in events('cancel_instance') if arrival<=instant_ns(x['utc'])<=ended}
    cancelled_fragments={x['fragment'] for x in events('fragment_cancel') if arrival<=instant_ns(x['utc'])<=ended}
    early_natural=[x for x in events('fragment_end') if anchor<=instant_ns(x['utc'])<arrival]
    task_error_count=sum(arrival<=instant_ns(x['utc'])<=ended for x in events('user_cancel_task_close'))
    # 非 OK 调度器日志没有任务键，只作诊断。在源端逐键捕获仍活跃到无 EOS 终态的转换。
    live_after=set()
    finalized=set()
    for x in relevant:
        if not x['complete'] or x['beginNs']<arrival: continue
        for group in x['groups']:
            for t in group['tasks']:
                key=task_key(t)
                if not t['eos'] and t['state'].upper() not in ('FINISHED','FINALIZED'):
                    live_after.add(key)
                if key in live_after and t['state'].upper()=='FINALIZED' and not t['eos'] and key[0] in cancel_instances:
                    finalized.add(key)
    post_commit=[x for x in relevant if x['complete'] and visible+clock_drift<=x['beginNs']
                 and x['endNs']+clock_drift<=arrival and x['groups']]
    same_live_after_commit=any({task_key(t) for g in x['groups'] if g['closed']==0 for t in g['tasks']
                                if not t['eos'] and t['state'] not in ('FINALIZED','FINISHED')}==wanted for x in post_commit)
    audit=fe_terminal(observed['fe'],identity)
    fe_ok=(audit['complete'] and audit['state']=='ERR' and audit['userCancel'] and not audit['timeout']
           and audit['reader'] and audit['fixedEntity'] and audit['isSelect'] and audit['returnRows']==0
           and arrival>0 and arrival<=instant_ns(audit['endUtc']) and instant_ns(audit['endExclusiveUpperUtc'])<=deadline
           and observed.get('feInactiveUpperMs',float('inf'))<=250 and observed['feClockControl']['passed'])
    fragment_ends=events('fragment_end')
    end_ids={x['fragment'] for x in fragment_ends}
    profile_tasks=[]
    fragment_instances, named_closes = {}, set()
    if snapshot and instances and arrival and ended:
        native=task_profile.be_log(observed['be'],'--native',identity,json.dumps(observed['nativeStart']),*sorted(instances))
        record(OUT/('overlap-native-events-'+observed['idempotencyKey']+'.json'),native)
        fragment_instances, named_closes = native_task_closes(native, snapshot['groups'], arrival, ended)
    reference_path=OUT/('overlap-profile-reference-'+observed['stress']['attempt']+'.json')
    if reference_path.is_file():
        reference=json.loads(reference_path.read_bytes())
        vm.demand(reference.get('binding')==observed['stress'] and reference.get('statementSha256')==audit.get('statementSha256')
                  and reference.get('fe')==observed['fe'] and reference.get('be')==observed['be'],'PROFILE_REFERENCE_IDENTITY')
        terminal_profile=task_profile.read_profile(observed['fe'],identity)
        if terminal_profile is not None:
            profile_tasks=task_profile.compare_tasks(terminal_profile,reference,snapshot,fragment_instances)
            record(OUT/('overlap-profile-'+observed['idempotencyKey']+'.json'),terminal_profile)
    # 封闭计划只有一个扫描、一个主归并和一个最终物化。直接原因或同查询必经单路产出不足均按准确任务键对账。
    shortfalls={(canonical_id(t['instance']),t['index']) for t in profile_tasks
                if (t['observedShortfall'] and t['soleMerge']) or t['nonEosScan']}
    # 同一查询全体实例收到用户取消且无其它原生错误后，才可使用完整终态的少行证明。
    causal_keys=named_closes | shortfalls if fragment_instances and fe_ok else set()
    # 无 EOS 的终态、匿名关闭次数或实例取消单独均不认证任务因果。
    checks=dict(clockContinuity=clock_drift<1_000_000,fullActivePopulation=bool(snapshot and wanted and len(wanted)==len(pending) and same_live_after_commit),
                platformBeforeSource=bool(0<anchor<=visible and visible+clock_drift<=arrival),
                allLiveInstancesCancelled=bool(wanted and {key[0] for key in wanted}<=cancel_instances and not early_natural),
                allTasksCausallyClosed=bool(wanted and causal_keys==wanted and not events('other_task_error')),
                allFragmentsAccounted=bool(expected and len(end_ids)==len(fragment_ends)==expected and cancelled_fragments==end_ids
                                           and len(end_events)==1 and all(arrival<=instant_ns(e['utc'])<=ended for e in fragment_ends)),
                endOfExecution=bool(any(arrival<=instant_ns(e['utc'])<=ended for e in events('coordinator_cancel_error')) and anchor<ended<=deadline and empty),
                feUserCancelInWindow=bool(fe_ok))
    # 保留全部命中样本和窗口内第一个严格空响应，其他查询仅保留样本数。
    selected=[x for x in relevant if x['groups'] or x is empty]
    return dict(status='PASS' if all(checks.values()) else 'NO_GO',checks=checks,anchorNs=anchor,beforeCommitBoundNs=before_commit,liveAfterCommitted=same_live_after_commit,
                feAudit=audit,profileComparisons=profile_tasks,identifiedTaskCloses=sorted(named_closes),clockDriftUpperNs=clock_drift,expectedFragments=expected,samplesRead=len(relevant),samples=selected,events=exact,
                pendingTasks=len(wanted),userCancelTaskCloses=task_error_count,finalizedWithoutEos=len(finalized & wanted),
                pipelineZeroUpperMs=(empty['endNs']-anchor)/1.e6 if empty else None)


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
    window=None
    with contextlib.ExitStack() as stack:
        platform=stack.enter_context(channel(pg))
        if overlap:
            vm.demand(platform('SHOW transaction_isolation;')=='read committed','PLATFORM_OBSERVER_ISOLATION')
        source=stack.enter_context(channel(fe,(DIRECTORY/'root.pass').read_bytes()))
        if overlap:
            locker=stack.enter_context(channel(pg))
            locker_pid=int(locker("SELECT pg_backend_pid();"))
            registered,ended=stack.enter_context(registered_queries(ids['be'],mark()))
            control_start=platform('SELECT clock_timestamp();')
            vm.demand(source("SELECT /*+ SET_VAR(enable_sql_cache=false) */ COUNT(*) FROM fixture.dmq_target WHERE target_id='T3';")=='1','OVERLAP_CONTROL')
            control_id=source("SELECT LAST_QUERY_ID();")
            control=canonical_id(control_id)
            control_end=platform('SELECT clock_timestamp();')
            until=time.monotonic()+3
            while time.monotonic()<until and not (control in registered and control in ended): time.sleep(.001)
            vm.demand(control in registered and control in ended,'OVERLAP_BE_SUBSCRIBED')
            observed['observerControlQueryId']=control
            control_audit=fe_terminal(ids['fe'],control_id)
            calibrated=(control_audit['complete'] and control_audit['state']=='EOF' and
                        instant_ns(control_start)-1_000_000<=instant_ns(control_audit['startUtc']) and
                        instant_ns(control_audit['endUtc'])<=instant_ns(control_end))
            observed['feClockControl']=dict(passed=calibrated,pgBefore=control_start,pgAfter=control_end,audit=control_audit)
            vm.demand(calibrated,'FE_AUDIT_WALL_CLOCK')
            # PG 墙钟和 BE 日志使用同一内核的实时时钟，容器可各自持有单调时钟命名空间。
            clocks={}
            for role in ('be','fe','platform-pg'):
                sample=subprocess.check_output(['docker','--context','desktop-linux','exec',ids[role],'sh','-ec',
                    'readlink /proc/1/ns/time && cat /proc/1/timens_offsets && cat /proc/sys/kernel/random/boot_id && date +%z'],text=True,timeout=3).splitlines()
                vm.demand(len(sample)==5 and re.fullmatch(r'time:\[\d+\]',sample[0]) and sample[1].split()==['monotonic','0','0']
                          and sample[2].split()==['boottime','0','0'] and str(uuid.UUID(sample[3]))==sample[3] and sample[4]=='+0000','OVERLAP_VM_CLOCK_SAMPLE')
                clocks[role]=dict(timeNamespace=sample[0],bootId=sample[3],utcOffset=sample[4])
            vm.demand(len({c['bootId'] for c in clocks.values()})==1,'OVERLAP_SHARED_VM')
            observed['vmClocks']=clocks
            scan="SELECT CONCAT(COUNT(*),'/',IFNULL(MAX(QueryId),'absent'),'/',IFNULL(MAX(Id),0)) FROM information_schema.processlist WHERE User='fixture_reader' AND Info LIKE '%SET_VAR(enable_sql_cache=false)%' AND Info LIKE '%FROM fixture.dmq_entity%';"
            observed['nativeStart']=task_profile.be_log(ids['be'],'--boundary')
            arm_pipeline,read_pipeline=stack.enter_context(pipeline_sampler(ids['be']))
            permit=OUT/('overlap-permit-'+key+'.json')
            vm.demand(not permit.exists() and stress['rowsByTable']=={'dmq_entity':4194304,'dmq_target':3},'OVERLAP_SCOPE')
            stack.callback(permit.unlink,missing_ok=True)
            armed=OUT/('overlap-source-ready-'+key+'.json')
            vm.demand(not armed.exists(),'OVERLAP_ARMED_EXISTS')
            stack.callback(armed.unlink,missing_ok=True)
        vm.demand(platform(lookup)=='absent' and source(scan)==('0/absent/0' if overlap else 'absent'),'WITNESS_INITIAL_STATE')
        def load_sample():
            return json.loads(platform("""SELECT json_build_object('clock',clock_timestamp(),'serverStarted',pg_postmaster_start_time(),
                'since',d.stats_reset,'commits',d.xact_commit,'rollbacks',d.xact_rollback,'reads',d.blks_read,'hits',d.blks_hit,
                'queryTableIndexScans',t.idx_scan,'queryTableSequentialScans',t.seq_scan)
                FROM pg_stat_database d,pg_stat_user_tables t WHERE d.datname=current_database()
                AND t.schemaname='semantic_query' AND t.relname='Queries';""".replace('\n',' ')))
        observed['loadBefore']=load_sample()
        if overlap and (OUT/('overlap-profile-reference-'+stress['attempt']+'.json')).is_file():
            observed['profileResourcesBefore']=task_profile.resource_counters(ids)
            window=task_profile.HandshakeWindow(source,ids['fe'],key,OUT,stress['attempt'])
            stack.callback(window.finish)
        begin=mark()
        emit('ready')
        end=time.monotonic()+(18 if overlap else 8)
        app_id=qid=None
        delivered=False
        while time.monotonic()<end:
            if window: window.tick()
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
                    if admit_first:
                        emit('admitted',queryId=app_id)
                        delivered=True
            if overlap and app_id and not delivered and armed.exists():
                vm.demand(window is None or window.row.get('handshakeScoped'),'PROFILE_HANDSHAKE_MISSED')
                vm.demand(json.loads(armed.read_bytes())=={'key':key},'OVERLAP_ARMED_KEY')
                observed['sourceReadyBeforeCancel']=platform('SELECT clock_timestamp();')
                record(file,observed)
                emit('admitted',queryId=app_id)
                delivered=True
            if overlap and delivered and 'waiterPid' not in observed:
                count,wait=platform("SELECT count(*)||'/'||coalesce(max(pid),0) FROM pg_stat_activity WHERE "+str(locker_pid)+"=ANY(pg_blocking_pids(pid)) AND wait_event_type='Lock' AND query LIKE '%semantic_query.%Queries%FOR UPDATE%';").split('/')
                vm.demand(count in ('0','1'),'OVERLAP_MULTIPLE_WAITERS')
                if count=='1':
                    observed.update(waiterPid=int(wait),verifiedWaitPgUtc=platform("SELECT clock_timestamp();"))
                    record(file,observed)
                    arm_pipeline()
                    record(permit,dict(key=key,queryId=app_id,waiterPid=int(wait)))
            if overlap and delivered and time.monotonic()>lock_deadline: break
            current=source(scan)
            if overlap:
                matches,current,physical=current.split('/')
                vm.demand(matches in ('0','1'),'OVERLAP_AMBIGUOUS_SOURCE')
                if matches=='1':
                    observed['sourceThread']=int(physical)
                    vm.demand(window is None or window.row['openedConnections']==[int(physical)],'PROFILE_WRONG_CONNECTION')
                    vm.demand(qid is None or canonical_id(qid)==canonical_id(current),'OVERLAP_SOURCE_CHANGED')
            if re.fullmatch('[0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16}',current):
                qid=current.lower()
                observed.setdefault('feActiveObservedAt',mark())
            if app_id and qid:
                if not overlap: break
                if canonical_id(qid) in registered and canonical_id(qid) not in ended:
                    observed['liveWitness']='registered_log'
                # 获准的握手已锁定唯一源连接。FE 接到准确业务 SQL 即可解锁，由独立样本证明 BE 与实际提交交叠。
                if 'waiterPid' in observed and ('liveWitness' in observed or (window and window.row.get('handshakeScoped'))):
                    observed['unlockTrigger']='FIXED_ACTIVE_FE' if window else 'REGISTERED_BE'
                    cleanup_begin=time.monotonic_ns()
                    observed['beforeUnlockPgUtc']=platform("SELECT clock_timestamp();")
                    observed['afterUnlockPgUtc']=locker("ROLLBACK; SELECT clock_timestamp();")
                    record(file,observed)
                    break
            if delivered and not (window and 'waiterPid' in observed) and platform('SELECT "ExecutionStatus" FROM semantic_query."Queries" WHERE "Id"='+repr(app_id)+';') != 'RUNNING': break
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
        observed['platformStates']=[]
        while time.monotonic()<stop and status=='RUNNING':
            visible = json.loads(platform("""SELECT json_build_object('query',"Id",'state',"ExecutionStatus",'statement',statement_timestamp(),
                'isolation',current_setting('transaction_isolation'),'observed',clock_timestamp())
                FROM semantic_query."Queries" WHERE "Id"='""".replace('\n',' ')+app_id+"';"))
            observed['platformStates'].append(visible)
            status = visible['state']
            if status=='CANCELLED':
                observed['cancelVisiblePgUtc']=visible['observed']
            if status=='RUNNING': time.sleep(.005)
        observed.update(terminal=status,terminalObservedAt=mark())
        observed['sourceCounts']=None if qid is None else source("SELECT (SELECT count(*) FROM information_schema.active_queries WHERE QUERY_ID='"+qid+"'),(SELECT count(*) FROM information_schema.backend_active_tasks WHERE QUERY_ID='"+qid+"');")
        def note_fe_exit():
            if overlap and observed.get('sourceCounts','').split('\t')[0]=='0':
                observed.setdefault('feInactiveUpperMs',(time.monotonic_ns()-cleanup_begin)/1.e6)
        if overlap: note_fe_exit()
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
                if overlap: note_fe_exit()
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
        if overlap and observed.get('cancelVisiblePgUtc') and events:
            raw_lines=(logs.stdout+b'\n'+logs.stderr).decode(errors='replace').splitlines()
            record(file,observed)
            samples,issues=read_pipeline()
            observed['pipelineStreamIssues']=issues
            # 双旁路原件先于后置 Profile/日志解码保存，避免后者失败掩盖本次计时。
            record(OUT/('overlap-pipeline-'+key+'.json'),dict(query=qid,issues=issues,samples=[
                dict(x,groups=[g for g in x['groups'] if g['query'] and canonical_id(g['query'])==canonical_id(qid)])
                for x in samples if x['count']==0 or any(g['query'] and canonical_id(g['query'])==canonical_id(qid) for g in x['groups'])]))
            vm.demand(bool(samples),'PIPELINE_NO_SAMPLES')
            evidence=equivalent_termination(observed,samples,raw_lines)
            source_file=OUT/('overlap-equivalent-'+key+'.json')
            record(source_file,evidence)
            observed['equivalent']={k:evidence[k] for k in ('status','checks','pipelineZeroUpperMs')}
            observed['equivalent']['sha256']=hashlib.sha256(source_file.read_bytes()).hexdigest()
            if window: observed['profileResourcesAfter']=task_profile.resource_counters(ids)
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
    try:
        watch(args.key,args.admit_first,args.overlap)
    except Exception as error:
        import traceback
        if args.overlap and str(uuid.UUID(args.key))==args.key:
            frames=traceback.extract_tb(error.__traceback__)
            tag=str(error) if re.fullmatch('[A-Z_]{4,80}',str(error)) else None
            record(OUT/('overlap-observer-failure-'+args.key+'.json'),dict(key=args.key,
                   category=type(error).__name__,code=tag,frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name) for f in frames]))
        raise
