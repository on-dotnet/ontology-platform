"""Oracle 正式查询旁路。只读取本任务两张表的受限观察视图和准确的平台查询行。"""
import argparse
import contextlib
import datetime as dt
import json
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import workflow_execution as ex
from workflow_oracle_mapping_resources import TASK, RUN, require
from workflow_oracle_mapping_window import OBS_DSN

ROOT = Path(__file__).resolve().parents[2]
AREA = ROOT / 'artifacts/workflow' / TASK / RUN
PRIVATE = ROOT / '.tools/security/g4-oracle-mapping-query-001' / RUN
DOCKER = ['docker', '--context', 'desktop-linux']
STAMP = """to_char(sys_extract_utc(systimestamp),'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"')"""
ZONE = dt.timezone.utc
CLIENT = r'[0-9a-f]{32}'
QID = r'query-[0-9a-f]{32}'
NATIVE_SQL = r'[0-9a-z]{13}'
DEC = r'[0-9]+'
AUDIT_VERSION = 'oracle-read-audit-window-v1'
SQL_HEADER = """whenever sqlerror exit failure rollback
whenever oserror exit failure
set define off echo off verify off feedback off heading off pages 0 lines 2000 tab off trimspool on serveroutput on size 1000000
"""


def utc(value):
    """只接受明确偏移的 UTC。保留六位微秒并标记 UTC；七位以上时间由 ns() 保留原界。"""
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)', value), 'OBSERVER_TIME')
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZONE).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def ns(value):
    lower = dt.datetime.fromisoformat(utc(value).replace('Z', '+00:00')) - dt.datetime(1970, 1, 1, tzinfo=ZONE)
    fraction = re.search(r'\.(\d+)', value)
    return ((lower.days * 86400 + lower.seconds) * 1_000_000 + lower.microseconds) * 1000 + (
        int(fraction.group(1).ljust(9, '0')[6:9]) if fraction else 0)


def now():
    return dt.datetime.now(ZONE).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def public_json(path):
    return json.loads(ex.ordinary(path).read_bytes())


def source_ids():
    create = public_json(AREA / 'source-create-01.json')
    setup = public_json(AREA / 'observer-setup-02.json')
    require((create['taskId'], create['runId'], setup['taskId'], setup['runId']) == (TASK, RUN, TASK, RUN)
            and setup['containerId'] == create['containerId'] and re.fullmatch('[0-9a-f]{64}', create['containerId'])
            and setup['status'] == 'OBSERVER_PROVISIONED' and len(setup['sqlIds']) == 2
            and all(re.fullmatch(NATIVE_SQL, item) for item in setup['sqlIds']), 'OBSERVER_SOURCE_ID')
    return create['containerId'], setup['sqlIds'][0]


def login():
    # 密码只通过私有 stdin 送给已批准的 OMQ_OBSERVER TCPS 连接。
    secret = ex.ordinary(PRIVATE / 'observer-password').read_text()
    require(re.fullmatch('[a-zA-Z0-9]+', secret), 'OBSERVER_SECRET_FORMAT')
    return SQL_HEADER + 'connect OMQ_OBSERVER/"' + secret + '"@"' + OBS_DSN + '"\n'


def audit_invocation(source_id, start_utc, end_utc, client_id=None):
    """固定实际命令和 SQL，不包含私有登录前缀，资格器可独立重算。"""
    require(re.fullmatch('[0-9a-f]{64}', source_id) and (client_id is None or re.fullmatch(CLIENT, client_id)), 'AUDIT_SCOPE')
    start, end = utc(start_utc), utc(end_utc)
    require(start < end, 'AUDIT_RANGE')
    # 公开调用的起止采用半开 UTC 窗口；同窗口其它任务不属于已过滤的 Oracle 窄视图。
    at = lambda instant: "to_timestamp('" + instant + """','YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"')"""
    condition = "" if client_id is None else " AND client_identifier='" + client_id + "'"
    body = f"""select 'CLOCK|'||{STAMP} from dual;
select 'IDENTITY|'||sys_context('USERENV','SESSION_USER')||'|'||sys_context('USERENV','NETWORK_PROTOCOL')||'|'||sys_context('USERENV','CON_NAME') from dual;
select json_object('instance' value to_char(instance_id),'session' value to_char(sessionid),'entry' value to_char(entry_id),
 'statement' value to_char(statement_id),'auditExecution' value to_char(execution_id),'clientId' value client_identifier,
 'owner' value object_schema,'table' value object_name,'action' value action_name,'code' value return_code,
 'utc' value to_char(event_timestamp_utc,'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"') null on null returning varchar2(1000))
 from G4_CONTROL.OMQ_READ_AUDIT where event_timestamp_utc>={at(start)} and event_timestamp_utc<{at(end)}{condition}
 order by event_timestamp_utc,instance_id,sessionid,entry_id,statement_id fetch first 2001 rows only;
select 'CLOCK|'||{STAMP} from dual;
"""
    definition = dict(sourceId=source_id, startUtc=start, endUtc=end, clientId=client_id,
                      sqlSha256=ex.sha(body.encode()), parserSha256=ex.sha(Path(__file__).read_bytes()), parserVersion=AUDIT_VERSION)
    return {'argv': [*DOCKER, 'exec', '-i', source_id, 'sqlplus', '-L', '-s', '/nolog'], 'body': body,
            'identity': ex.sha(ex.encoded(definition)), 'definition': definition}


def parse_audit(stdout):
    """拒绝额外列、重复身份、未审对象、非 SELECT、截断输出和不明客户端。"""
    lines = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
    require(len(lines) >= 3 and lines[0].startswith('CLOCK|') and lines[-1].startswith('CLOCK|')
            and lines[1].upper() == 'IDENTITY|OMQ_OBSERVER|TCPS|FREEPDB1', 'AUDIT_IDENTITY')
    rows = [json.loads(s) for s in lines[2:-1]]
    identity = set()
    for row in rows:
        require(set(row) == {'instance','session','entry','statement','auditExecution','clientId','owner','table','action','code','utc'}
                and all(re.fullmatch(DEC, row[k]) for k in ['instance','session','entry','statement'])
                and (row['auditExecution'] is None or re.fullmatch(DEC, row['auditExecution']))
                and re.fullmatch(CLIENT, row['clientId']) and row['action'] == 'SELECT' and type(row['code']) is int
                and (row['owner'], row['table']) in {('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget')}, 'AUDIT_NATIVE_RECORD')
        utc(row['utc'])
        key = tuple(row[k] for k in ['instance','session','entry','statement','owner','table'])
        require(key not in identity, 'AUDIT_DUPLICATE')
        identity.add(key)
    require(len(rows) <= 2000, 'AUDIT_LIMIT')
    return rows


def audit_window(start_utc, end_utc, client_id=None):
    """在可独立重开的真实命令外保存源身份、双时钟界及完整有界审计行。"""
    source, _ = source_ids()
    inv = audit_invocation(source, start_utc, end_utc, client_id)
    # 独立审计也逐 ID 核对当前运行者的镜像、TaskId、RunId。
    from workflow_oracle_mapping_resources import SOURCE
    check=ex.run([*DOCKER,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.State.Status}}',source],
                 ROOT, task=TASK, run_id=RUN,stage='oracle-audit-source-identity',input_key=ex.sha(ex.encoded([source,SOURCE,TASK,RUN])),timeout=5)
    require(check.returncode==0 and check.stdout.decode().strip()=='|'.join([source,SOURCE.split('@')[1],TASK,RUN,'running']),'AUDIT_LIVE_SOURCE')
    low = time.time_ns()
    call = ex.run(inv['argv'], ROOT, task=TASK, run_id=RUN, stage='oracle-formal-audit-window',
                  input_key=inv['identity'], stdin=(login() + inv['body'] + 'exit success\n').encode(), timeout=12)
    high = time.time_ns()
    require(call.returncode == 0, 'AUDIT_COMMAND')
    rows = parse_audit(call.stdout)
    require(all(utc(start_utc) <= r['utc'] < utc(end_utc) and (client_id is None or r['clientId'] == client_id) for r in rows), 'AUDIT_OUTSIDE')
    clocks = [r.strip()[6:] for r in call.stdout.decode().splitlines() if r.strip().startswith('CLOCK|')]
    require(len(clocks) == 2 and ns(clocks[0]) <= ns(clocks[1]), 'AUDIT_CLOCK')
    return dict(taskId=TASK, runId=RUN, startUtc=utc(start_utc), endUtc=utc(end_utc), clientId=client_id, sourceId=source,
                observerId='OMQ_OBSERVER', sourceIdentityCommand=check.receipt['commandId'],sourceClock=clocks, errorBounds=dict(lowerNs=low-ns(clocks[0])-999, upperNs=high-ns(clocks[1])),
                sourceAuditCount=len(rows), recordsSha256=ex.sha(ex.encoded(rows)), records=rows, commandId=call.receipt['commandId'])


class Channel:
    """预建立只读进程；每条受控语句有界，关闭输入后等待实际退出。"""

    def __init__(self, cmd, kind):
        self.kind = kind
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.rows = queue.Queue()
        self.worker = threading.Thread(target=self._read, daemon=True)
        self.worker.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                if len(line) > 4096:
                    self.rows.put(None)
                    return
                self.rows.put(line.decode(errors='strict').strip())
        finally:
            self.rows.put(None)

    def run(self, sql, timeout=3):
        mark = 'OMQ_DONE_' + uuid.uuid4().hex
        end = ('prompt ' if self.kind == 'oracle' else '\\echo ') + mark
        self.proc.stdin.write((sql + '\n' + end + '\n').encode())
        due = time.monotonic() + timeout
        result = []
        while len(result) < 5000:
            line = self.rows.get(timeout=max(.001, due-time.monotonic()))
            require(line is not None and time.monotonic() <= due, 'OBSERVATION_STREAM')
            if line == mark:
                return result
            if line:
                require(not re.match(r'(?:ORA-|SP2-|ERROR:|FATAL:)', line), 'OBSERVATION_DATABASE_ERROR')
                result.append(line)
        raise ValueError('OBSERVATION_BUDGET')

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            # 仅关闭本次创建的宿主 CLI 进程；数据库语句另有服务器内硬上限。
            self.proc.terminate()
            self.proc.wait(timeout=3)
        self.proc.stdout.close()
        self.worker.join(timeout=.5)


def sample_clock(call):
    """从往返两端得到宿主减远端的偏移区间，不把 Docker 宿主与 VM 时钟视为相同。"""
    readings = []
    for _ in range(5):
        lo, mono = time.time_ns(), time.monotonic_ns()
        remote = call()
        after, hi = time.monotonic_ns(), time.time_ns()
        require(abs((after-mono)-(hi-lo)) <= 1_000_000, 'HOST_CLOCK_STEP')
        readings.append({'hostBefore':lo,'hostAfter':hi,'remote':remote,'monoBefore':mono,'monoAfter':after})
    return readings


def bounds(samples):
    low = max(s['hostBefore'] - s['remote'] - 1000 for s in samples)
    high = min(s['hostAfter'] - s['remote'] + 1000 for s in samples)
    require(low <= high, 'CLOCK_INTERVAL_EMPTY')
    return [low, high]


def api_clock(channel):
    # API 进程和此受限辅助读数共享同一个运行中容器的内核墙钟。
    result = channel.run("SELECT_UNUSED")
    require(len(result) == 1 and re.fullmatch(r'\d{18,20}', result[0]), 'API_CLOCK')
    return int(result[0])


def source_clock(channel):
    result = channel.run(f'select {STAMP} from dual;')
    require(len(result) == 1, 'SOURCE_CLOCK')
    return ns(result[0])


def pg_state(channel, key, subject):
    require(str(uuid.UUID(key)) == key and re.fullmatch(r'[A-Za-z0-9._:@/-]{1,160}', subject), 'PLATFORM_SCOPE')
    sql = f"""SELECT json_build_object('id',q."Id",'state',q."ExecutionStatus",'cancel',q."CancelRequested",
      'owner',q."LeaseOwner",'fence',q."Fence",'deadline',q."DeadlineAtUtc",'created',q."CreatedAtUtc",
      'observed',clock_timestamp(),'leaseUntil',q."LeaseUntilUtc",'hash',q."ResultHash",'bytes',octet_length(q."ResultCiphertext"),
      'receipts',jsonb_array_length(convert_from(q."BindingBytes",'UTF8')::jsonb->'receipts'),
      'cancelAudits',(SELECT count(*) FROM governance.audit_records WHERE "Resource"=q."Id" AND "Action"='data.query.cancel' AND "Outcome"='allowed'),
      'successAudits',(SELECT count(*) FROM governance.audit_records WHERE "Resource"=q."Id" AND "Action"='data.query.execute' AND "Outcome"='allowed'))
      FROM semantic_query."Queries" q WHERE q."OrganizationId"='org-demo' AND q."IdempotencyKey"='{key}'
      AND q."SubjectId"='{subject}' LIMIT 2;"""
    rows = channel.run(sql)
    require(len(rows) <= 1, 'PLATFORM_ID_AMBIGUOUS')
    return json.loads(rows[0]) if rows else None


def cursor_stats(channel, sqlid):
    rows = channel.run(f"""select child_number||'|'||plan_hash_value||'|'||executions||'|'||end_of_fetch_count||'|'||rows_processed||'|'||px_servers_executions
      from G4_CONTROL.OMQ_CURSOR_STATS where sql_id='{sqlid}' order by child_number;""")
    result = {}
    for row in rows:
        numbers = [int(v) for v in row.split('|')]
        require(len(numbers) == 6 and all(n >= 0 for n in numbers) and str(numbers[0]) not in result, 'CURSOR_STATS')
        result[str(numbers[0])] = numbers[1:]
    return result


def sample_source(channel, client, sqlid):
    require(re.fullmatch(CLIENT, client) and re.fullmatch(NATIVE_SQL, sqlid), 'SAMPLE_FILTER')
    # 在 Oracle 端保留每次状态变化的第一和最后原始采样；中间不输出其它 SQL 身份。
    sql = f"""declare
      until_ts timestamp with time zone:=systimestamp+numtodsinterval(1.3,'SECOND');
      l varchar2(40); h varchar2(40); p varchar2(400):='?'; v varchar2(400);
      tail varchar2(600); cnt number; samples number:=0;
    begin
      while systimestamp<until_ts loop
        select {STAMP} into l from dual;
        select count(*),nvl(max(sid||'|'||serial_no||'|'||audsid||'|'||con_id||'|'||status||'|'||
         case when sql_id='{sqlid}' then sql_id||'|'||nvl(to_char(sql_exec_id),'-')||'|'||nvl(to_char(sql_exec_start,'YYYYMMDDHH24MISS'),'-')
              else '-|-|-' end||'|'||
         case when prev_sql_id='{sqlid}' then prev_sql_id||'|'||nvl(to_char(prev_exec_id),'-') else '-|-' end),'ABSENT')
        into cnt,v from G4_CONTROL.OMQ_SESSIONS where client_identifier='{client}';
        select {STAMP} into h from dual;
        if cnt>1 then raise_application_error(-20009,'ambiguous'); end if;
        if v<>p then
          if tail is not null then dbms_output.put_line(tail); end if;
          dbms_output.put_line(l||'|'||h||'|'||v); p:=v;
        end if;
        tail:=l||'|'||h||'|'||v; samples:=samples+1;
      end loop;
      dbms_output.put_line(tail);dbms_output.put_line('COUNT|'||samples);
    end;
    /"""
    rows = channel.run(sql, 3.2)
    require(rows and rows[-1].startswith('COUNT|') and int(rows[-1][6:]) > 1, 'SAMPLE_UNAVAILABLE')
    parsed = []
    for row in rows[:-1]:
        parts = row.split('|')
        require(len(parts) in (3, 12) and ns(parts[0]) <= ns(parts[1]), 'SAMPLE_FORMAT')
        if len(parts) == 3:
            require(parts[2] == 'ABSENT', 'SAMPLE_ABSENCE')
            parsed.append(dict(lo=parts[0], hi=parts[1], absent=True))
        else:
            sid, serial, audsid, con, state, current, execution, start, prev, prev_exec = parts[2:]
            require(all(re.fullmatch(DEC,v) for v in (sid,serial,audsid,con)) and current in (sqlid,'-') and prev in (sqlid,'-'), 'SAMPLE_ID')
            parsed.append(dict(lo=parts[0], hi=parts[1], sid=sid, serial=serial, audsid=audsid, con=con,
                               state=state, sql=current, execution=execution, start=start, previous=prev, previousExecution=prev_exec))
    return dict(samples=int(rows[-1][6:]), events=parsed)


def source_channel(source):
    channel = Channel([*DOCKER,'exec','-i',source,'stdbuf','-oL','sqlplus','-L','-s','/nolog'], 'oracle')
    try:
        identity = channel.run(login() + "select sys_context('USERENV','SESSION_USER')||'|'||sys_context('USERENV','NETWORK_PROTOCOL')||'|'||sys_context('USERENV','CON_NAME') from dual;", 6)
        require([line.upper() for line in identity] == ['OMQ_OBSERVER|TCPS|FREEPDB1'], 'OBSERVER_LOGIN')
        return channel
    except BaseException:
        channel.close()
        raise


def clock_channel(container):
    # 只接受一个固定读钟指令和宿主内部的完成标记；无可执行 SQL/用户字符串。
    script = """while IFS= read -r line; do
      case "$line" in SELECT_UNUSED) date -u +%s%N;; *OMQ_DONE_*) printf '%s\\n' "${line#* }";; *) exit 3;; esac
    done"""
    return Channel([*DOCKER,'exec','-i',container,'sh','-c',script], 'clock')


def log_events(container, query, start, arrivals, stop):
    # Docker 原始日志不交由 workflow_execution，也不保存；只存同 query 固定格式投影。
    token = r'(?P<{}>[^\s",}}]+)'
    definitions = {
        'OracleBranchBegin':['query','owner','fence','execution','utc','workDeadlineUtc','branchDeadlineUtc'],
        'OracleCancelDispatch':['query','owner','fence','execution','utc','workDeadlineUtc','branchDeadlineUtc','cleanupRemainingMs'],
        'OracleCancelCommit':['query','originalFence','terminalFence','lowerUtc','upperUtc','durationMs'],
        'OracleSourceSession':['query','execution','instance','sid','audsid','unified','con','utc'],
        'OracleSourceEvent':['action','query','execution','utc'],
        'OracleBranchRelease':['query','execution','confirmed','observedUtc'],
        'OracleCleanupCas':['query','execution','fence','released','observedUtc']}
    process = subprocess.Popen([*DOCKER,'logs','--timestamps','--follow','--since',start,container],
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
    def watch():
        try:
            for raw in process.stdout:
                if stop.is_set():
                    break
                if query.encode() not in raw or len(raw) > 12000:
                    continue
                line = raw.decode(errors='replace')
                for name, parts in definitions.items():
                    if name + ' ' not in line:
                        continue
                    tail = line.split(name + ' ',1)[1]
                    row = {}
                    for key in parts:
                        match = re.search(r'(?:^| )' + key + '=' + token.format(key), tail)
                        if match:
                            row[key] = match[key]
                    if len(row) != len(parts) or row.get('query') != query:
                        continue
                    if 'execution' in row and not re.fullmatch(CLIENT,row['execution']):
                        continue
                    if 'action' in row and row['action'] not in ('EXECUTE','CANCEL_ENTER','CANCEL_RETURN','CANCEL_REJECT','NATIVE_1013','EOF','PHYSICAL_RELEASE'):
                        continue
                    if 'owner' in row and not re.fullmatch(r'oracle-execution-[a-zA-Z0-9._:-]{1,160}',row['owner']):
                        continue
                    for key in ('utc','workDeadlineUtc','branchDeadlineUtc','observedUtc','lowerUtc','upperUtc'):
                        if key in row:
                            utc(row[key])
                    for key in ('fence','instance','sid','audsid','unified','con','originalFence','terminalFence'):
                        if key in row:
                            require(re.fullmatch(DEC,row[key]), 'HOST_LOG_NUMBER')
                    arrivals.put((name,row))
        finally:
            process.stdout.close()
    thread = threading.Thread(target=watch,daemon=True)
    thread.start()
    return process,thread


def stream_summary(state, delta):
    """游标统计必须仅有一个计划实际执行；无多余执行、PX、重新加载或计数回绕。"""
    change = []
    if not set(state).issubset(delta):
        return None
    for child, row in delta.items():
        before = state.get(child, [row[0],0,0,0,0])
        if row[0] != before[0] or any(a < b for a,b in zip(row[1:],before[1:])):
            return None
        values = [a-b for a,b in zip(row[1:],before[1:])]
        if any(values):
            change.append(dict(child=child,plan=row[0],executions=values[0],eof=values[1],rows=values[2],px=values[3]))
    return change[0] if len(change) == 1 and change[0]['executions'] == 1 and change[0]['px'] == 0 else None


def classify(record):
    clocks = {}
    for key, samples in record['clocks'].items():
        require(len(samples)==10,'CLOCK_MISSING_BRACKET')
        first, last = bounds(samples[:5]), bounds(samples[5:])
        wall_elapsed = samples[-1]['hostAfter']-samples[0]['hostBefore']
        mono_elapsed = samples[-1]['monoAfter']-samples[0]['monoBefore']
        require(abs(wall_elapsed-mono_elapsed)<=1_000_000,'HOST_CLOCK_DRIFT')
        # 前后分别校准，合并为覆盖两端及实测时基误差的外界，不能用交集人为缩紧。
        guard=abs(wall_elapsed-mono_elapsed)+1000
        clocks[key]=[min(first[0],last[0])-guard,max(first[1],last[1])+guard]
    record['clockIntervalsNs'] = clocks
    def low(stamp, name):
        return ns(stamp) + clocks[name][0] - 1000
    def high(stamp, name):
        return ns(stamp) + clocks[name][1] + 1000
    def single(name, role='api', action=None):
        matches = [r for r in record['logs'][role] if r['name']==name and (action is None or r.get('action')==action)]
        return matches[0] if len(matches)==1 else {}
    begin = single('OracleBranchBegin')
    session = single('OracleSourceSession')
    commit = single('OracleCancelCommit','api-secondary')
    dispatch = single('OracleCancelDispatch')
    release = single('OracleBranchRelease')
    cas = single('OracleCleanupCas')
    native = lambda action: single('OracleSourceEvent',action=action)
    client = begin.get('execution')
    states = record['platformStates']
    terminal = states[-1]
    info = dict(status='FINAL',queryId=record['queryId'],clientId=client,
                successfulResults=int(terminal['hash'] is not None or bool(terminal['bytes'])),
                successReceipts=terminal['receipts'],successAudits=terminal['successAudits'],
                formalCancelCommitted=False,naturalCompletion=False,nativeCancelCausedTermination=False,
                allSourceWorkEnded=False,nativeErrorCode=None,deadlineOrDisconnectBeforeCommit=None,
                sameExecutionActiveAtCommit=False,residualSourceWork=None,slotReleased=terminal['owner'] is None)
    if not begin or not session or not release or not re.fullmatch(CLIENT,client or ''):
        return info
    scoped = [ev for role in record['logs'].values() for ev in role if 'execution' in ev]
    require(all(ev['execution']==client for ev in scoped),'MULTIPLE_BRANCH_IDENTITIES')
    samples = record['source'].get('events',[])
    current = [e for e in samples if e.get('sql')==record['sqlId'] and e['state']=='ACTIVE' and re.fullmatch(DEC,e['execution'])]
    sql_exec = {(e['sid'],e['serial'],e['audsid'],e['con'],e['execution'],e['start']) for e in current}
    if current:
        require(len(sql_exec)==1 and all((e['sid'],e['audsid'],e['con'])==(session['sid'],session['audsid'],session['con']) for e in current), 'SQL_EXECUTION_AMBIGUOUS')
        record['nativeExecutionIdentity']=list(next(iter(sql_exec)))
    audit = [r for r in record['audit']['records'] if r['clientId']==client]
    bridge = (len(audit)==1 and (audit[0]['instance'],audit[0]['session'],audit[0]['owner'],audit[0]['table'])
              == (session['instance'],session['unified'],'PRODUCTION','OMQ_ENTITY'))
    # 两套执行号分别保留。统一审计可不给 execution_id，其它关联必须和实际单次读者会话一致。
    record['auditBridge'] = dict(sameUniqueClientAndObject=bridge, sqlExecutionId=current[0]['execution'] if current else None,
                                 unifiedAuditExecutionId=audit[0]['auditExecution'] if len(audit)==1 else None,
                                 traditionalAuditSession=session['audsid'],unifiedAuditSession=session['unified'])
    stats = stream_summary(record['cursorBefore'],record['cursorAfter'])
    record['cursorDelta'] = stats
    begun, ended = native('EXECUTE'), native('PHYSICAL_RELEASE')
    confirmed = release.get('confirmed','').lower()=='true'
    if not begun or not ended or not bridge or not stats:
        return info
    absence = [s for s in samples if s.get('absent') and low(s['lo'],'source') >= high(begun['utc'],'api')]
    if samples and samples[-1].get('absent'):
        info['residualSourceWork'] = 0
    info['allSourceWorkEnded'] = confirmed and info['residualSourceWork']==0 and bool(absence)
    # 入库的 deadline 来源于原 HTTP 入口。计划对该调用使用 5000ms，不能改取准入时刻。
    deadline = ns(terminal['deadline']) + clocks['api'][0]
    branch_upper = high(release['observedUtc'],'api') - low(begin['utc'],'api')
    # 平台 terminal 以已观察到终态的第一笔 DB 读作保守上界，独立于审计时间。
    settled = next((s for s in states if s['state'] in ('CANCELLED','COMPLETED','FAILED') and s['owner'] is None), None)
    if not settled:
        return info
    complete_upper = max(high(ended['utc'],'api'), high(release['observedUtc'],'api'),high(settled['observed'],'pg'))
    info.update(branchUpperMs=branch_upper/1e6,totalUpperMs=(complete_upper-(deadline-5_000_000_000))/1e6)
    if terminal['state']=='COMPLETED' and not terminal['cancel'] and terminal['cancelAudits']==0:
        info['nativeErrorCode']=0 if native('EOF') and not native('NATIVE_1013') else None
        info['naturalCompletion'] = (stats['eof']==1 and stats['rows']>0 and info['nativeErrorCode']==0
                                     and not native('CANCEL_ENTER') and audit[0]['code']==0)
        return info
    if not commit or terminal['state']!='CANCELLED' or not terminal['cancel'] or terminal['cancelAudits']!=1:
        return info
    require(commit['originalFence']==begin['fence'] and int(commit['terminalFence'])==terminal['fence']==int(begin['fence'])+1, 'CANCEL_FENCE')
    info['formalCancelCommitted'] = True
    clo, chi = low(commit['lowerUtc'],'api-secondary'), high(commit['upperUtc'],'api-secondary')
    before = [e for e in current if high(e['hi'],'source') < clo]
    after = [e for e in current if low(e['lo'],'source') > chi]
    info['sameExecutionActiveAtCommit'] = bool(before and after)
    if before and after:
        # 从同一 SQL_EXEC_ID 且正活跃的前后读之间复核无消失、改身份或转至另一 SQL 的采样。
        interval = [e for e in samples if ns(before[-1]['lo']) <= ns(e['lo']) <= ns(after[0]['lo'])]
        info['sameExecutionActiveAtCommit'] = all(e.get('sql')==record['sqlId'] and e.get('execution')==before[-1]['execution']
                                                  and e.get('state')=='ACTIVE' for e in interval)
    enter, returned, failure = native('CANCEL_ENTER'), native('CANCEL_RETURN'), native('NATIVE_1013')
    if failure:
        info['nativeErrorCode'] = 1013
    if not (dispatch and enter and returned and failure and not native('EOF') and not native('CANCEL_REJECT') and cas):
        return info
    dispatch_at = ns(dispatch['utc'])
    require(dispatch['fence']==begin['fence'] and dispatch['owner']==begin['owner'] and dispatch['execution']==client, 'DISPATCH_BINDING')
    # 同一 API 上因果回调必须从正式平台取消先行，并排除原工作定时器与断开先行。
    order = (chi <= low(dispatch['utc'],'api') and dispatch_at <= ns(enter['utc']) <= ns(failure['utc'])
             and ns(enter['utc']) <= ns(returned['utc']) and high(failure['utc'],'api')<low(begin['workDeadlineUtc'],'api')
             and float(dispatch['cleanupRemainingMs'])>0 and high(failure['utc'],'api')<deadline)
    if order:
        info['deadlineOrDisconnectBeforeCommit'] = False
    if info['sameExecutionActiveAtCommit'] and after:
        gone = next((e for e in absence if ns(e['lo']) > ns(after[0]['hi'])),None)
        if gone and cas.get('released','').lower()=='true':
            info['cleanupUpperMs'] = (max(high(gone['hi'],'source'),high(ended['utc'],'api'),high(cas['observedUtc'],'api'))-clo)/1e6
            info['nativeCancelCausedTermination'] = order and stats['eof']==0 and 0 <= stats['rows'] < 100 and audit[0]['code'] in (0,1013)
    return info


def emit(status, **fields):
    print(json.dumps(dict(status=status, **fields),separators=(',',':')),flush=True)


def observe(idempotency_key, output, query_id=None):
    """正式 API 调用前预开独立只读观察者，一次证据不覆盖、一个原始时钟预算。"""
    from workflow_oracle_mapping_platform import runtime_binding
    require(str(uuid.UUID(idempotency_key))==idempotency_key and (query_id is None or re.fullmatch(QID,query_id))
            and output=='formal-witness-'+idempotency_key+'.json', 'FORMAL_OBSERVER_ARGUMENT')
    path = ex.ordinary(AREA/output)
    require(not path.exists(), 'FORMAL_WITNESS_EXISTS')
    source, sqlid = source_ids()
    rec = dict(taskId=TASK,runId=RUN,sourceId=source,sqlId=sqlid,idempotencyKey=idempotency_key,startedUtc=now(),
               platformStates=[],logs={'api':[],'api-secondary':[]},clocks={},status='STARTED')
    final = None
    try:
        rec['hostBefore'] = runtime_binding()
        containers = public_json(AREA/'formal-resources.json')['ids']
        # 已核容器声明均以本次准确全 ID 访问；绝不按名称连接其它任务。
        require(all(re.fullmatch('[a-f0-9]{64}',containers[k]) for k in ('api','api-secondary','platform-pg')), 'FORMAL_OBSERVER_HOSTS')
        state = public_json(AREA/'runtime-fixture.json')
        require(state['taskId']==TASK and state['runId']==RUN and state['scope']=={'organizationId':'org-demo','siteIds':['site-a']}, 'FORMAL_READER_STATE')
        subject = state['subjects']['reader']
        stop = threading.Event()
        with contextlib.ExitStack() as resources:
            oracle = source_channel(source)
            resources.callback(oracle.close)
            pg = Channel([*DOCKER,'exec','-i','--user','postgres',containers['platform-pg'],'psql','-XwqAt','-v','ON_ERROR_STOP=1','-d','mapping'], 'pg')
            resources.callback(pg.close)
            pg.run("SET default_transaction_read_only=on; SET statement_timeout='2s';")
            require(pg_state(pg,idempotency_key,subject) is None,'FORMAL_KEY_ALREADY_USED')
            clocks = {}
            for name in ('api','api-secondary'):
                clocks[name]=clock_channel(containers[name])
                resources.callback(clocks[name].close)
            def calibrate():
                jobs = {k:(lambda c=c:api_clock(c)) for k,c in clocks.items()}
                jobs['source'] = lambda:source_clock(oracle)
                jobs['pg'] = lambda:ns(pg.run("""SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"');""")[0])
                with ThreadPoolExecutor(max_workers=4) as pool:
                    work={k:pool.submit(sample_clock,fn) for k,fn in jobs.items()}
                    for k,job in work.items():
                        rec['clocks'].setdefault(k,[]).extend(job.result())
            calibrate()
            rec['cursorBefore']=cursor_stats(oracle,sqlid)
            emit('READY')
            until=time.monotonic()+7
            while time.monotonic()<until:
                row=pg_state(pg,idempotency_key,subject)
                if row:
                    break
                time.sleep(.002)
            require(row and re.fullmatch(QID,row['id']) and (query_id is None or row['id']==query_id),'FORMAL_ADMISSION_MISSED')
            rec['queryId']=row['id']
            rec['platformStates'].append(row)
            emit('ADMITTED',queryId=row['id'])
            arrivals={k:queue.Queue() for k in clocks}
            tails={k:log_events(containers[k],row['id'],rec['startedUtc'],arrivals[k],stop) for k in clocks}
            def close_logs():
                stop.set()
                for process,_ in tails.values():
                    process.terminate()
                for process,thread in tails.values():
                    process.wait(timeout=3);thread.join(timeout=.5)
            resources.callback(close_logs)
            def drain():
                for role,events in arrivals.items():
                    while not events.empty():
                        name,item=events.get_nowait()
                        rec['logs'][role].append(dict(name=name,**item))
                        require(len(rec['logs'][role])<=40,'FORMAL_LOG_BUDGET')
            client=None
            sampler=None
            with ThreadPoolExecutor(max_workers=1) as pool:
                while time.monotonic()<until:
                    drain()
                    begin=next((e for e in rec['logs']['api'] if e['name']=='OracleBranchBegin'),None)
                    if begin and client is None:
                        client=begin['execution']
                        sampler=pool.submit(sample_source,oracle,client,sqlid)
                    current=pg_state(pg,idempotency_key,subject)
                    require(current is not None and current['id']==row['id'],'FORMAL_QUERY_CHANGED')
                    last=rec['platformStates'][-1]
                    if (last['state'],last['fence'],last['owner'])!=(current['state'],current['fence'],current['owner']):
                        rec['platformStates'].append(current)
                    if sampler and sampler.done() and current['state']!='RUNNING':
                        break
                    if not sampler and current['state']!='RUNNING' and len(rec['platformStates'])>1 and time.monotonic()+4<until:
                        # 仍保留机会读取稍晚送达的正式分支日志。
                        time.sleep(.005)
                    time.sleep(.004)
                if sampler:
                    rec['source']=sampler.result()
                else:
                    rec['source']={'events':[],'samples':0}
            actual=pg_state(pg,idempotency_key,subject)
            require(actual and actual['id']==row['id'],'FORMAL_QUERY_EVIDENCE')
            rec['platformStates'].append(actual)
            active=next((e for e in rec['source']['events'] if e.get('sql')==sqlid and e['state']=='ACTIVE' and re.fullmatch(DEC,e['execution'])),None)
            if active:
                emit('ACTIVE',queryId=row['id'],clientId=client)
            rec['cursorAfter']=cursor_stats(oracle,sqlid)
            calibrate()
            drain()
            rec['audit']=audit_window(rec['startedUtc'],now(),client) if client else {'records':[]}
            if client:
                final=classify(rec)
            else:
                final=dict(status='FINAL',queryId=row['id'],clientId=None,reason='FORMAL_SOURCE_ID_NOT_OBSERVED')
            rec.update(status='OBSERVED',final=final)
        rec['hostAfter']=runtime_binding()
        require({k:v for k,v in rec['hostBefore'].items() if k!='commandId'} ==
                {k:v for k,v in rec['hostAfter'].items() if k!='commandId'}, 'FORMAL_OBSERVER_HOST_DRIFT')
    except BaseException as err:
        # 不保存原始数据库/进程异常正文；错误码只取本模块封闭断言。
        rec.update(status='FAIL',reason=(str(err) if isinstance(err,ValueError) and re.fullmatch('ORACLE_ADMISSION_[A-Z_]+',str(err))
                                         else type(err).__name__))
        final=dict(status='FINAL',queryId=rec.get('queryId'),clientId=None,reason=rec['reason'])
        raise
    finally:
        rec['endedUtc']=now()
        with path.open('x') as f:
            json.dump(rec,f,indent=2);f.write('\n')
        if final:
            print(json.dumps(final,separators=(',',':')),flush=True)
    return rec


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idempotency-key',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--query-id')
    args=parser.parse_args()
    observe(args.idempotency_key,args.output,args.query_id)
