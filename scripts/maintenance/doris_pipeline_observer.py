"""只读采样本次单 BE 的实际流水线任务。仅输出任务身份、状态、计数和响应摘要。"""
import hashlib
import http.client
import json
import os
import re
import sys
import time


ID = r'[0-9a-f]{1,16}-[0-9a-f]{1,16}'


def decode(body):
    lines = body.decode('utf-8').strip()
    header = re.match(r'^(\d+) pipeline fragment contexts are still running! duration_limit=0(?:\n|$)', lines)
    if not header:
        raise ValueError('PIPELINE_HEADER')
    if int(header[1])==0 and lines!=header[0].strip():
        raise ValueError('PIPELINE_ZERO_HAS_PAYLOAD')
    groups = []
    # 每个 context 的每个 task 都输出自己的 QueryId 和 InstanceId。
    blocks = re.split(r'(?:^|\n)No\.\d+ \(elapse_second=', lines)[1:]
    for block in blocks:
        counts = re.search(r'PipelineFragmentContext Info: _closed_tasks=(\d+), _total_tasks=(\d+)', block)
        if not counts:
            raise ValueError('PIPELINE_COUNTS')
        closed, total = map(int, counts.groups())
        parts = re.split(r'(?:^|\n)Task \d+: QueryId: ', block)[1:]
        records = []
        tasks = []
        for part in parts:
            match = re.match('(' + ID + r')\nInstanceId: (' + ID +
                r')\nPipelineTask\[id = (\d+), open = (true|false|[01]), eos = (true|false|[01]), state = (\w+), dry run = (true|false|[01]), [^\]\n]*?_wake_up_early = (true|false|[01]), _wake_up_by = (-?\d+),[^\]\n]*?is running = (true|false|[01])\]',part)
            if not match:
                continue
            records.append(match.groups())
            query,instance,index,opened,eos,state,dry,wake,wake_by,running=match.groups()
            # 只提取本任务的已知算子名称、编号等结构字段，不复制 debug/依赖正文。
            operators=[]
            _, separator, details=part[match.end():].partition('\noperators:')
            if separator:
                details=details.split('\nRead Dependency Information:',1)[0]
                for op in re.finditer(r'^[ \t]*([A-Z][A-Z0-9_]*_OPERATOR): id=(-?\d+)(?:, parallel_tasks=(-?\d+))?, _is_serial_operator=(true|false|[01])',details,re.M):
                    operators.append(dict(name=op[1],nodeId=int(op[2]),parallelTasks=int(op[3]) if op[3] is not None else None,serial=op[4] in ('true','1')))
            tasks.append(dict(instance=instance,task=int(index),opened=opened in ('true','1'),eos=eos in ('true','1'),
                              state=state,dryRun=dry in ('true','1'),wakeEarly=wake in ('true','1'),
                              wakeBy=int(wake_by),running=running in ('true','1'),operators=operators))
        queries = {row[0] for row in records}
        complete = (0 <= closed <= total and total > 0 and len(records) == len(parts) == total and
                    len({(row['instance'],row['task']) for row in tasks}) == total and len(queries) == 1)
        groups.append(dict(query=next(iter(queries)) if len(queries)==1 else None,
                           closed=closed, total=total, complete=complete, tasks=tasks))
    return dict(count=int(header[1]), groups=groups, complete=int(header[1])==len(groups) and
                all(group['complete'] for group in groups), sha256=hashlib.sha256(body).hexdigest())


def sample(connection):
    begin = time.time_ns()
    mono = time.monotonic_ns()
    connection.request('GET','/api/running_pipeline_tasks')
    reply = connection.getresponse()
    content_length=reply.getheader('Content-Length')
    body = reply.read(262145)
    if (reply.status != 200 or len(body)>262144 or not reply.isclosed() or
        (content_length is not None and int(content_length)!=len(body)) or
        (content_length is None and not reply.chunked)):
        raise ValueError('PIPELINE_INCOMPLETE_HTTP')
    end = time.time_ns()
    elapsed = time.monotonic_ns() - mono
    return dict(beginNs=begin,endNs=end,beginMonoNs=mono,elapsedNs=elapsed,**decode(body))



NATIVE_SITES = {
    'fragment_mgr.cpp:729': 'register',
    'fragment_mgr.cpp:657': 'start',
    'internal_service.cpp:637': 'user_rpc',
    'pipeline_fragment_context.cpp:177': 'fragment_cancel',
    'pipeline_fragment_context.cpp:218': 'instance_cancel',
    'task_scheduler.cpp:84': 'task_close_error',
    'fragment_mgr.cpp:941': 'broadcast_return',
    'fragment_mgr.cpp:571': 'coordinator_error',
    'pipeline_fragment_context.cpp:142': 'fragment_end',
    'query_context.cpp:262': 'context_end',
}


def native_boundary(stream):
    """只接受完整行边界，保留尚未落成一行的文件尾长度及摘要。"""
    stat = os.fstat(stream.fileno())
    stream.seek(max(0,stat.st_size-65536))
    tail = stream.read(stat.st_size-stream.tell())
    if tail and b'\n' not in tail:
        raise ValueError('NATIVE_NO_LINE_BOUNDARY')
    partial=tail.rsplit(b'\n',1)[-1]
    return dict(inode=stat.st_ino,endOffset=stat.st_size-len(partial),fileSize=stat.st_size,
                trailingBytes=len(partial),trailingSha256=hashlib.sha256(partial).hexdigest())


def native_events(query, instances, start):
    """在单 BE 上按准确身份读取原生日志。仅输出站点、TID、原因分类与原行摘要。"""
    if not all(re.fullmatch(ID, item) for item in [query, *instances]):
        raise ValueError('NATIVE_IDENTITIES')
    ids = {identity.encode() for identity in [query, *instances]}
    pattern = re.compile(r'^RuntimeLogger ([IWE])(\d{8} \d\d:\d\d:\d\d\.\d+)\s+(\d+) (\w+\.\w+:\d+)\]')
    rows = []
    with open('/opt/apache-doris/be/log/be.INFO', 'rb') as stream:
        boundary = native_boundary(stream)
        if start['inode']!=boundary['inode'] or not 0<=boundary['endOffset']-start['endOffset']<=16*1024*1024:
            raise ValueError('NATIVE_LOG_INTERVAL')
        stream.seek(start['endOffset'])
        while stream.tell() < boundary['endOffset']:
            offset = stream.tell()
            raw = stream.readline(1024 * 1024)
            if not raw.endswith(b'\n'):
                raise ValueError('NATIVE_LOG_TRUNCATED')
            if not any(ident in raw for ident in ids):
                continue
            line = raw[:-1].decode()
            matches = set(re.findall(r'\b' + ID + r'\b', line))
            if not matches.intersection({query, *instances}):
                continue
            header = pattern.match(line)
            if not header:
                raise ValueError('NATIVE_EVENT_FORMAT')
            level, timestamp, tid, site = header.groups()
            event = NATIVE_SITES.get(site, 'other')
            active_instances = matches.intersection(instances)
            fragment = re.search(r'fragment_id[=:] ?(\d+)', line)
            user = 'cancel query by user' in line
            if event in ('fragment_cancel', 'task_close_error', 'broadcast_return'):
                user = user and '[CANCELLED]' in line
            rows.append(dict(event=event, level=level, site=site, timestamp=timestamp, tid=int(tid),
                             queryField=query in matches, userCancel=user, offset=offset,
                             instance=next(iter(active_instances)) if len(active_instances)==1 else None,
                             fragment=int(fragment[1]) if fragment else None,
                             sha256=hashlib.sha256(raw[:-1]).hexdigest()))
        if stream.tell() != boundary['endOffset'] or os.stat(stream.name).st_ino != boundary['inode']:
            raise ValueError('NATIVE_FILE_CHANGED')
    return dict(query=query,start=start,boundary=boundary,events=rows)

def main():
    connection = http.client.HTTPConnection('127.0.0.1',8040,timeout=0.2)
    try:
        first = sample(connection)
        print(json.dumps(dict(ready=first['complete'],baseline=first['count'])),flush=True)
        if sys.stdin.readline().strip() != 'collect':
            return
        print('armed',flush=True)
        end = time.monotonic() + .7
        count = 0
        while time.monotonic() < end and count<260:
            try:
                current=sample(connection)
            except (OSError, ValueError, http.client.HTTPException) as error:
                category=str(error) if isinstance(error,ValueError) and str(error).startswith('PIPELINE_') else type(error).__name__
                print(json.dumps(dict(observationError=category)),flush=True)
                connection.close()
                break
            print(json.dumps(current,separators=(',',':')),flush=True)
            count+=1
            # 出现实任务时连续读取，仍受相同时间与总采样数限制。
            if current['count']==0:
                time.sleep(.002)
        print(json.dumps(dict(finished=True,count=count)),flush=True)
    finally:
        connection.close()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--native':
        print(json.dumps(native_events(sys.argv[2],sys.argv[4:],json.loads(sys.argv[3]))))
    elif len(sys.argv)>1 and sys.argv[1]=='--boundary':
        with open('/opt/apache-doris/be/log/be.INFO','rb') as source:
            print(json.dumps(native_boundary(source)))
    else:
        main()
