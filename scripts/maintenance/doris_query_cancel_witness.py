"""正式取消端点的双旁路观察，只输出任务、源查询 ID 及引擎事件类别。"""
import argparse
import contextlib
import datetime
import json
import queue
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


def watch(key):
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
    with channel(pg) as platform,channel(fe,(DIRECTORY/'root.pass').read_bytes()) as source:
        vm.demand(platform(lookup)=='absent' and source(scan)=='absent','WITNESS_INITIAL_STATE')
        begin=mark()
        emit('ready')
        end=time.monotonic()+8
        app_id=qid=None
        while time.monotonic()<end:
            # 独立平台键先命中，随后采样 FE；两个准确 ID 同属当前唯一业务投递。
            if app_id is None:
                value=platform(lookup)
                if re.fullmatch('query-[a-f0-9]{32}',value): app_id=value
            current=source(scan)
            if re.fullmatch('[0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16}',current):
                qid=current.lower()
                observed.setdefault('feActiveObservedAt',mark())
            if app_id and qid: break
            time.sleep(.001)
        observed.update(queryId=app_id,sourceQueryId=qid)
        record(file,observed)
        if not (app_id and qid):
            emit('miss',**observed)
            return
        emit('active',queryId=app_id,sourceQueryId=qid)
        # 端点执行与观察并行；最终事实取 PostgreSQL 持久状态及同一 BE QueryId。
        stop=time.monotonic()+5
        status='RUNNING'
        while time.monotonic()<stop and status=='RUNNING':
            status=platform('SELECT "ExecutionStatus" FROM semantic_query."Queries" WHERE "Id"=\''+app_id+"';")
            if status=='RUNNING': time.sleep(.005)
        observed.update(terminal=status,terminalObservedAt=mark())
        observed['sourceCounts']=source("SELECT (SELECT count(*) FROM information_schema.active_queries WHERE QUERY_ID='"+qid+"'),(SELECT count(*) FROM information_schema.backend_active_tasks WHERE QUERY_ID='"+qid+"');")
        safe=platform('''SELECT json_build_object('bytes',octet_length("ResultCiphertext"),'resultHash',"ResultHash",'resultSize',"ResultSize") FROM semantic_query."Queries" WHERE "Id"='%s';'''%app_id)
        observed['persisted']=json.loads(safe)
        observed['successfulAuditCount']=int(platform('''SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.execute' AND "Outcome"='allowed' AND "Resource"='%s';'''%app_id))
        # 不返回 BE 日志正文。只解析本次准确 QueryId 与固定版本源码位置的交集。
        logs=subprocess.run(['docker','--context','desktop-linux','logs','--since',begin,ids['be']],capture_output=True,timeout=6,check=True)
        events=[]
        for line in (logs.stdout+b'\n'+logs.stderr).decode(errors='replace').splitlines():
            if qid not in line.lower(): continue
            for label,location,term in [('registered','fragment_mgr.cpp:729]','total fragment num'),
                ('cancel_arrived','internal_service.cpp:637]','cancel query by user'),
                ('task_cancelled','task_scheduler.cpp:84]','cancel query by user'),
                ('fragment_end','pipeline_fragment_context.cpp:142]','~PipelineFragmentContext'),
                ('context_end','query_context.cpp:262]','deconstructed')]:
                match=re.match(r'^[IWE](\d{8} \d\d:\d\d:\d\d\.\d+)',line)
                if match and location in line and term in line: events.append(dict(kind=label,beUtc=match.group(1)))
        observed['beEvents']=events
        record(file,observed)
        emit('finished',**observed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('key')
    watch(parser.parse_args().key)
