"""限定在本任务 Doris 夹具上的逐任务 Profile，只保存诊断字段。"""
import argparse
import datetime
import hashlib
import json
import re
import queue
import subprocess
import time
import textwrap
import zipfile
from pathlib import Path


FIXED_STATEMENT_HASH = '779405d77852bb511c189d4b0a404932b51eec629a56ca006debcf4a051ef564'
OPERATOR = re.compile(r'^(MATERIALIZATION_OPERATOR|EXCHANGE_OPERATOR|LOCAL_MERGE_SORT_SOURCE_OPERATOR|OLAP_SCAN_OPERATOR)\(')


def project(text):
    """只读取未合并 Fragments 下每个任务及其原始算子计数。"""
    sections = list(re.finditer(r'^[ \t]*Fragments:[ \t]*$', text, re.M))
    start = sections[-1] if sections else None
    if not start:
        raise ValueError('PROFILE_FRAGMENTS')
    rows = []
    task = None
    operator = None
    fragment = pipeline = None
    section = None
    scanner = False
    for line in text[start.end():].splitlines():
        item = line.strip()
        indent = len(line) - len(line.lstrip())
        fragment_match = re.fullmatch(r'Fragment (\d+):', item)
        pipeline_match = re.match(r'^Pipeline (\d+)\(host=', item)
        task_match = re.fullmatch(r'PipelineTask\(index=(\d+)\):',item)
        if fragment_match:
            fragment = int(fragment_match[1])
            task = operator = pipeline = None
        elif pipeline_match:
            pipeline = int(pipeline_match[1])
            task = operator = None
        elif task_match:
            if fragment is None or pipeline is None:
                raise ValueError('PROFILE_TASK_PARENT')
            task = dict(fragment=fragment,pipeline=pipeline,task=int(task_match[1]),operators={},planOperators=[],planNodes=[])
            rows.append(task)
            operator = None
        elif task is not None:
            if indent == 11 and item.startswith('- TaskState: '):
                task['state']=item.split(': ',1)[1]
            elif indent == 11 and item.startswith('- WakeUpEarly: '):
                task['wakeEarly']=int(item.split(': ',1)[1])
            elif re.match(r'^([A-Z][A-Z0-9_]*_OPERATOR)\(',item):
                section=None
                scanner=False
                op_name=item.split('(',1)[0]
                task['planOperators'].append(op_name)
                node = re.search(r'\((?:id|dest_id)=(-?\d+)\)',item)
                task['planNodes'].append(dict(name=op_name,nodeId=int(node[1]) if node else None))
                match=OPERATOR.match(item)
                operator=match[1] if match else None
                if operator:
                    if operator in task['operators']: raise ValueError('PROFILE_DUPLICATE_OPERATOR')
                    task['operators'][operator]={}
            elif operator:
                if indent == 12:
                    section = item
                    scanner=False
                elif indent == 14 and section=='CustomCounters:' and operator=='OLAP_SCAN_OPERATOR':
                    scanner=item=='Scanner:'
                    if scanner: task['operators'][operator]['scannerPresent']=True
                elif scanner and indent==16 and item in ('SegmentIterator:', 'IndexFilter:'):
                    task['operators'][operator][item[:-1]]=True
                elif section == 'CommonCounters:' and indent == 15 and item.startswith('- RowsProduced: '):
                    value=item.split(': ',1)[1]
                    # 人类缩放值可能截断。只认未缩放的整数或括号内的原始准确整数。
                    count=re.fullmatch(r'\d+',value) or re.search(r'\(([\d,]+)\)$',value)
                    if 'rows' in task['operators'][operator]:
                        raise ValueError('PROFILE_DUPLICATE_COUNTER')
                    if count:
                        raw=count[1] if count.lastindex else count[0]
                        task['operators'][operator]['rows']=int(raw.replace(',',''))
                elif scanner and section == 'CustomCounters:' and indent == 17 and item=='- EOS: True':
                    task['operators'][operator]['scanEos']=True
    return rows


def extract(identity):
    """在 FE 内只读引擎自己的压缩 Profile，验证精确 ID 和成员边界。"""
    if not re.fullmatch('[0-9a-f]{1,16}-[0-9a-f]{1,16}',identity): raise ValueError('PROFILE_ID')
    directory=Path('/opt/apache-doris/fe/log/profile')
    files=list(directory.glob('*_'+identity+'.zip'))
    if not files: return None
    if len(files)!=1 or files[0].is_symlink(): raise ValueError('PROFILE_FILE')
    with zipfile.ZipFile(files[0]) as archive:
        members=archive.infolist()
        if len(members)!=1 or not 0<members[0].file_size<4*1024*1024: raise ValueError('PROFILE_SIZE')
        content=archive.read(members[0])
    # 固定版本按两个大端四字节长度写出摘要 JSON 和执行正文。
    summary_size=int.from_bytes(content[:4],'big')
    cut=4+summary_size
    if cut+4>len(content) or int.from_bytes(content[cut:cut+4],'big')!=len(content)-cut-4:
        raise ValueError('PROFILE_SECTIONS')
    summary=json.loads(content[4:cut])['summaryProfile']['infoStrings']
    if summary.get('Profile ID')!=identity: raise ValueError('PROFILE_IDENTITY')
    return dict(query=identity,state=summary.get('Task State'),bytes=len(content),
                profileSha256=hashlib.sha256(content).hexdigest(),tasks=project(content[cut+4:].decode()))


def read_profile(fe,identity,seconds=30):
    """等待既有 FE 异步归档，预算判定采用本次源事件时间。"""
    script=Path(__file__).read_text()
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=subprocess.run(['docker','--context','desktop-linux','exec',fe,'python3','-c',script,
                               '--extract',identity],capture_output=True,timeout=4)
        if result.returncode!=0: raise ValueError('PROFILE_READER_FAILED')
        projection=json.loads(result.stdout)
        if projection is not None:return projection
        time.sleep(.5)
    return None


def node_map(profile):
    """固定计划恰有一条扫描、一路本地归并和一路最终物化，两个分片各一个实例。"""
    if not profile: return {}
    tasks=profile['tasks']
    if len(tasks)!=3 or len({(t['fragment'],t['pipeline'],t['task']) for t in tasks})!=3:return {}
    result={}
    for task in tasks:
        roots=set(task['operators']) & {'OLAP_SCAN_OPERATOR','LOCAL_MERGE_SORT_SOURCE_OPERATOR','MATERIALIZATION_OPERATOR'}
        if len(roots)!=1: return {}
        name=roots.pop()
        if name in result:return {}
        result[name]=task
    return result if len(result)==3 else {}


def group_size_for_operator(profile, name):
    return sum(name in task['planOperators'] for task in profile['tasks'])


def compare_tasks(final, reference, sample, instances):
    """核对同计划逐任务行数。此差异仅供审查，不能单独认证任务因取消结束。"""
    paths = {
        'MATERIALIZATION_OPERATOR': ['RESULT_SINK_OPERATOR','MATERIALIZATION_OPERATOR','EXCHANGE_OPERATOR'],
        'LOCAL_MERGE_SORT_SOURCE_OPERATOR': ['DATA_STREAM_SINK_OPERATOR','LOCAL_MERGE_SORT_SOURCE_OPERATOR'],
        'OLAP_SCAN_OPERATOR': ['SORT_SINK_OPERATOR','OLAP_SCAN_OPERATOR'],
    }
    if not reference or reference.get('rowCount')!=101 or not final or not sample:
        return []
    control = reference.get('profile') or {}
    if (control.get('state') != 'OK' or final.get('state') not in ('OK', 'ERR', 'ERROR', 'CANCELLED') or
        not final.get('query') or not control.get('query') or final['query'] == control['query']):
        return []
    normal=node_map(control)
    cancelled=node_map(final)
    if set(normal)!=set(paths) or set(cancelled)!=set(paths): return []
    groups=sample['groups']
    if len(groups)!=2 or sorted(g['total'] for g in groups)!=[1,2]:return []
    result=[]
    for name,operators in paths.items():
        n=normal[name];c=cancelled[name]
        # FE Fragment 显示序号与 BE 的真实 fragment_id 各自独立。
        # 从本次 task debug 的算子名、真实 node_id 和 task index 找到准确 instance。
        core = next((n for n in c.get('planNodes',[]) if n['name']==name),None)
        candidates=[t for g in groups if g['complete'] and g['closed']==0
                    for t in g['tasks'] if t['instance'] in instances.values() and t['task']==c['task']
                    and core and core['nodeId'] is not None and any(o['name']==core['name'] and o['nodeId']==core['nodeId'] for o in t.get('operators',[]))
                    and [op['name'] for op in t['operators']]==operators[::-1]]
        before=candidates[0] if len(candidates)==1 else {}
        fields=('fragment','pipeline','task')
        shape=(all(c[k]==n[k] for k in fields) and c['planOperators']==n['planOperators']==operators and c.get('planNodes')==n.get('planNodes'))
        baseline=n['operators'][name].get('rows')
        actual=c['operators'][name].get('rows')
        # 保留实际算子和逐任务少行观测。早退、EOS 与下界须在同一压力执行上单独核验。
        bound=(shape and isinstance(baseline,int) and baseline>=101 and isinstance(actual,int) and actual>=0
                  and n.get('state')==c.get('state')=='FINALIZED' and n.get('wakeEarly')==c.get('wakeEarly')==0
                  and before.get('opened') is True and before.get('eos') is False and before.get('wakeEarly') is False and before.get('dryRun') is False
                  and before.get('state') not in (None,'FINISHED','FINALIZED'))
        scanner=c['operators'][name]
        control_scanner=n['operators'][name]
        # 已产出行排除 open 时的空扫描快返。完整 Scanner 中可见两个子节，正控制实际记录了 EOS。
        full_scan=(name=='OLAP_SCAN_OPERATOR' and all(scanner.get(k) and control_scanner.get(k)
                   for k in ('scannerPresent','SegmentIterator','IndexFilter')) and control_scanner.get('scanEos') is True)
        result.append(dict(operator=name,instance=before.get('instance'),index=c['task'],pipeline=c['pipeline'],
                           referenceRows=baseline,cancelledRows=actual,observedShortfall=bool(bound and actual<101),
                           nonEosScan=bool(bound and actual>0 and full_scan and 'scanEos' not in scanner),
                           finalWakeEarly=c.get('wakeEarly'),
                           soleMerge=(name!='LOCAL_MERGE_SORT_SOURCE_OPERATOR' or
                                      (c['task']==0 and group_size_for_operator(final,name)==1)),
                           nativeNodes=before.get('operators',[])))
    return result



def be_log(be, *args):
    script=Path(__file__).with_name('doris_pipeline_observer.py').read_text()
    return json.loads(subprocess.check_output(['docker','--context','desktop-linux','exec',be,
                                               'python3','-c',script,*args],timeout=12))

def resource_counters(ids):
    """从已核准的 FE/BE cgroup 回读内存和 CPU 累计值，不打开源连接。"""
    counters = {}
    for role in ('fe','be'):
        raw = subprocess.check_output(['docker','--context','desktop-linux','exec',ids[role],
            'sh','-ec','cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/cpu.stat'],
            text=True,timeout=3).splitlines()
        cpu = dict(line.split() for line in raw[2:])
        counters[role] = dict(currentBytes=int(raw[0]),peakBytes=int(raw[1]),usageUsec=int(cpu['usage_usec']))
    return counters


GLOBAL_VALUES = 'SELECT @@global.enable_profile,@@global.profile_level;'
FRESH_VALUES = 'SELECT CONNECTION_ID(),@@global.enable_profile,@@global.profile_level,@@enable_profile,@@profile_level;'


class HandshakeWindow:
    """只在本次正式主连接握手的两个同步点之间调整该独占 FE 的默认值。"""

    def __init__(self, source, fe, key, out, attempt):
        from workflow_doris_s0_fixture import record, sql
        self.source, self.fe, self.key, self.out = source, fe, key, out
        self.record, self.sql = record, sql
        self.file = out / ('overlap-profile-window-'+key+'.json')
        self.paths = {name:out/('overlap-profile-'+name+'-'+key+'.json') for name in
                      ('request','before-open','enabled','after-open','restored')}
        self.changed = False
        if self.file.exists() or any(p.exists() for p in self.paths.values()):
            raise ValueError('PROFILE_WINDOW_COLLISION')
        if any(json.loads(p.read_bytes()).get('recoveryRequired') for p in out.glob('overlap-profile-window-*.json')):
            raise ValueError('PROFILE_PREVIOUS_WINDOW_UNRECOVERED')
        fields = sql(fe,'reader',FRESH_VALUES).split('\t')
        old = source(GLOBAL_VALUES).split('\t')
        if len(fields)!=5 or fields[1:3]!=old or fields[3:]!=old or old[0]!='0' or old[1] not in ('1','2','3'):
            raise ValueError('PROFILE_WINDOW_BASELINE')
        self.old = old
        self.row = dict(key=key,fe=fe,fixtureAttempt=attempt,original=old,baselineConnection=int(fields[0]),stage='ARMED',recoveryRequired=False)
        self.record(self.file,self.row)
        self.mark('request')

    def mark(self, name):
        self.record(self.paths[name],dict(key=self.key))

    def participants(self):
        raw = self.source("SELECT IFNULL(GROUP_CONCAT(CONCAT(Id,':',User)), 'none') FROM information_schema.processlist;")
        rows = [v.split(':',1) for v in raw.split(',')]
        if any(len(row)!=2 or row[1] not in ('root','fixture_reader') for row in rows):
            raise ValueError('PROFILE_NON_FIXTURE_SESSION')
        return {int(ident):user for ident,user in rows}

    def enable(self):
        before = self.participants()
        if list(before.values()).count('fixture_reader') or self.source(GLOBAL_VALUES).split('\t')!=self.old:
            raise ValueError('PROFILE_NONEXCLUSIVE_BEFORE')
        marker=self.sql(self.fe,'reader',FRESH_VALUES).split('\t')
        if len(marker)!=5 or marker[1:3]!=self.old or marker[3:]!=self.old:
            raise ValueError('PROFILE_BEFORE_HANDSHAKE')
        self.row.update(before=before,preHandshakeConnection=int(marker[0]),stage='OPENING',recoveryRequired=True)
        self.record(self.file,self.row)
        self.changed = True
        self.row['beforeSetNs'] = time.time_ns()
        self.start = time.monotonic_ns()
        values=self.source('SET GLOBAL profile_level=3; SET GLOBAL enable_profile=true; '+GLOBAL_VALUES).split('\t')
        if values!=['1','3']:
            raise ValueError('PROFILE_WINDOW_ENABLE')
        self.row.update(enabled=values,stage='ENABLED',enabledNs=time.time_ns())
        self.record(self.file,self.row)
        self.mark('enabled')

    def restore(self, completed=False):
        if not self.changed:
            return
        current = self.participants() if completed else {}
        # 失败时也从写前台账恢复两个真实原值。若原连接失败，准确 FE 的新管理会话仅作恢复。
        command='SET GLOBAL enable_profile=false; SET GLOBAL profile_level='+self.old[1]+'; '+GLOBAL_VALUES
        try:
            after=self.source(command).split('\t')
        except (RuntimeError, ValueError, OSError, EOFError, TimeoutError, queue.Empty):
            after=self.sql(self.fe,'root',command).split('\t')
        self.row.update(restoredGlobal=after,restoredNs=time.time_ns(),
                        windowUpperMs=(time.monotonic_ns()-self.start)/1e6)
        fresh=self.sql(self.fe,'reader',FRESH_VALUES).split('\t')
        if after!=self.old or len(fresh)!=5 or fresh[1:3]!=self.old or fresh[3:]!=self.old:
            raise ValueError('PROFILE_RESTORE_FAILED')
        self.changed=False
        self.row.update(stage='RESTORED',recoveryRequired=False,freshConnection=int(fresh[0]),fresh=fresh[1:])
        self.record(self.file,self.row)
        if completed:
            opened=set(current)-set(self.row['before'])
            expected=self.row['preHandshakeConnection']+1
            self.row['handshakeScoped']=(self.row['windowUpperMs']<=220 and opened=={expected} and current[expected]=='fixture_reader' and
                                         int(fresh[0])==expected+1)
            self.row['openedConnections']=sorted(opened)
            self.record(self.file,self.row)
            if not self.row['handshakeScoped']:
                raise ValueError('PROFILE_HANDSHAKE_SCOPE')
            self.mark('restored')

    def tick(self):
        for signal,stage,action in [('before-open','ARMED',self.enable),('after-open','ENABLED',lambda:self.restore(True))]:
            if self.row['stage']==stage and self.paths[signal].exists():
                if json.loads(self.paths[signal].read_bytes())!={'key':self.key}:
                    raise ValueError('PROFILE_SIGNAL_KEY')
                action()
        if self.changed and time.monotonic_ns()-self.start>220_000_000:
            self.restore()
            raise ValueError('PROFILE_HANDSHAKE_EXPIRED')

    def finish(self):
        try:
            self.restore()
        finally:
            for path in self.paths.values():
                path.unlink(missing_ok=True)

def recover_window(out, fe, attempt):
    """正式观察进程提前退出时，只对准确 FE 和本次夹具的未恢复台账补做恢复。"""
    from workflow_doris_s0_fixture import record, sql
    for path in out.glob('overlap-profile-window-*.json'):
        row=json.loads(path.read_bytes())
        if not row.get('recoveryRequired') or row.get('fixtureAttempt')!=attempt:
            continue
        old=row['original']
        if row.get('fe')!=fe or old not in (['0','1'],['0','2'],['0','3']):
            raise ValueError('PROFILE_RECOVERY_IDENTITY')
        current=sql(fe,'root',GLOBAL_VALUES).split('\t')
        if current not in (old,['0','3'],['1','3']):
            raise ValueError('PROFILE_RECOVERY_CONFLICT')
        after=sql(fe,'root','SET GLOBAL enable_profile=false; SET GLOBAL profile_level='+old[1]+'; '+GLOBAL_VALUES)
        fresh=sql(fe,'reader',FRESH_VALUES).split('\t')
        if after.split('\t')!=old or len(fresh)!=5 or fresh[1:3]!=old or fresh[3:]!=old:
            raise ValueError('PROFILE_RECOVERY_VERIFY')
        row.update(stage='RECOVERED_AFTER_INTERRUPTION',recoveryRequired=False,handshakeScoped=False,
                   freshConnection=int(fresh[0]),fresh=fresh[1:])
        record(path,row)


def reference(minimum_first_fragment_ms=None):
    """在本任务已准入的压力数据上，用独立只读会话绑定同计划的正常执行。"""
    from workflow_doris_s0_fixture import INDEX,record,sql,stress_binding
    from workflow_doris_s1 import OUT,ROOT,live_stack
    ids=live_stack()
    state=json.loads(INDEX.read_bytes())
    binding=stress_binding(state)
    if binding['rowsByTable']!={'dmq_entity':4194304,'dmq_target':3}:
        raise ValueError('PROFILE_REFERENCE_SCOPE')
    path=OUT/('overlap-profile-reference-'+binding['attempt']+'.json')
    if path.exists(): raise ValueError('PROFILE_REFERENCE_EXISTS')
    reader=ROOT/'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/DorisQueryReader.cs'
    match=re.search(r'private const string EntitySql = """\n(.*?)\n *""";',reader.read_text(),re.S)
    if not match: raise ValueError('PROFILE_TEMPLATE')
    select=textwrap.dedent(match[1]).replace('@org',"'org-demo'").replace('@site',"'site-a'").replace('@external','NULL')
    fingerprint=hashlib.sha256(select.replace('\n','\\n').encode()).hexdigest()
    if fingerprint!=FIXED_STATEMENT_HASH: raise ValueError('PROFILE_FIXED_STATEMENT')
    native_start=be_log(ids['be'],'--boundary')
    data=sql(ids['fe'],'reader','SET enable_profile=true; SET profile_level=3; '+select+'; SELECT LAST_QUERY_ID();',limit=6).splitlines()
    if len(data)!=102 or len({row.split('\t')[2] for row in data[:-1]})!=101:
        raise ValueError('PROFILE_REFERENCE_ROWS')
    profile=read_profile(ids['fe'],data[-1])
    tasks=node_map(profile)
    if not profile or profile.get('state')!='OK' or len(tasks)!=3 or not all(task.get('state')=='FINALIZED' and task['operators'][name].get('rows',-1)>=101
                                 for name,task in tasks.items()):
        raise ValueError('PROFILE_REFERENCE_INCOMPLETE')
    artifact=dict(binding=binding,fe=ids['fe'],be=ids['be'],statementSha256=fingerprint,rowCount=101,
                  rowHash=hashlib.sha256('\n'.join(data[:-1]).encode()).hexdigest(),profile=profile)
    # 成功对照的 Profile 和 BE 行日志分别刷新。只读同一 QueryId、inode 和原起点。
    # 等待发生在正常对照结束后，正式产品分支与取消的计时均不在此处。
    observed=time.monotonic()
    for attempt in range(24):
        native=be_log(ids['be'],'--native',data[-1],json.dumps(native_start))
        stages={event:[datetime.datetime.strptime(r['timestamp'],'%Y%m%d %H:%M:%S.%f')
                       for r in native['events'] if r['event']==event] for event in ('register','fragment_end','context_end')}
        complete=len(stages['register'])==len(stages['context_end'])==1 and len(stages['fragment_end'])==2
        if complete or time.monotonic()-observed>=5: break
        time.sleep(.2)
    artifact['nativeReadback']=dict(attempts=attempt+1,elapsedMs=(time.monotonic()-observed)*1000)
    first_ms=(min(stages['fragment_end'])-stages['register'][0]).total_seconds()*1000 if complete else None
    artifact.update(native=native,firstFragmentEndMs=first_ms,minimumFirstFragmentMs=minimum_first_fragment_ms)
    record(path,artifact)
    if minimum_first_fragment_ms is not None and (first_ms is None or first_ms<minimum_first_fragment_ms):
        raise ValueError('PROFILE_NATURAL_WINDOW_TOO_SHORT')
    return path


def dependency_proof(directory, key):
    """离线重开同一次执行的原件，核验普通堆排序的唯一上游因取消传播而提前终止。"""
    import uuid
    if str(uuid.UUID(key))!=key:
        raise ValueError('PROFILE_REOPEN_ID')
    used={}
    def get(prefix, suffix=key):
        path=directory/(prefix+suffix+'.json')
        data=path.read_bytes()
        used[path.name]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    w=get('formal-cancel-')
    original=get('overlap-equivalent-')
    execute=get('overlap-execute-')
    prof=get('overlap-profile-')
    native=get('overlap-native-events-')
    pipeline=get('overlap-pipeline-')
    window=get('overlap-profile-window-')
    cfg=get('equivalent-immutable-config-')
    plan=get('equivalent-physical-plan-')
    release=get('equivalent-heap-source-provenance','')
    core=get('equivalent-source-provenance','')
    attempt=w['stress']['attempt']
    reference=get('overlap-profile-reference-',attempt)
    fixture=get('s0-stress-fixture-',attempt+'-restored')
    browser_files=[path for path in directory.glob('browser-s2-doris-overlap-*.json')
                   if json.loads(path.read_bytes()).get('cancel',{}).get('key')==key]
    if len(browser_files)!=1:raise ValueError('PROFILE_OFFICIAL_CASE')
    browser=get('',browser_files[0].stem)
    source=w['sourceQueryId']
    audit=original['feAudit']
    records=plan['records']
    projected=original['profileComparisons']
    nodes={t['operator']:t for t in projected}
    scan=nodes['OLAP_SCAN_OPERATOR']
    merge=nodes['LOCAL_MERGE_SORT_SOURCE_OPERATOR']
    material=nodes['MATERIALIZATION_OPERATOR']
    by_operator=node_map(prof)
    all_keys={(t['instance'],t['index']) for t in projected}
    complete_groups=[s for s in original['samples'] if s['complete'] and len(s['groups'])==2 and
                     all(g['closed']==0 and g['complete'] for g in s['groups'])]
    def exact_group(s):
        return {(t['instance'],t['task']) for g in s['groups'] for t in g['tasks']
                if t['opened'] and not t['dryRun'] and not t['eos'] and not t['wakeEarly']}==all_keys
    checks=original['checks']
    known={'clockContinuity','fullActivePopulation','platformBeforeSource','allLiveInstancesCancelled','allTasksCausallyClosed',
           'allFragmentsAccounted','endOfExecution','feUserCancelInWindow'}
    native_kinds={'register','start','user_rpc','fragment_cancel','instance_cancel','task_close_error','broadcast_return',
                  'coordinator_error','fragment_end','context_end'}
    errs={'user_rpc','fragment_cancel','task_close_error','broadcast_return','coordinator_error'}
    events=native['events']
    fixed_nodes=['PhysicalResultSink','PhysicalProject','PhysicalLazyMaterialize','PhysicalTopN','PhysicalDistribute',
                 'PhysicalTopN','PhysicalProject','PhysicalFilter','PhysicalLazyMaterializeOlapScan','PhysicalOlapScan']
    layout=records['cancelled']['nodes']
    cn=scan['nativeNodes'];mn=merge['nativeNodes'];rn=material['nativeNodes']
    def shape(items):
        return [(item['name'],item['nodeId']) for item in items]
    expected_orders=['event_at#8 asc null first','entity_id#2 asc null first']
    opened=window['openedConnections']
    driver_events={i['name']:i for i in execute['events']}
    handshake=driver_events['doris.cancel.ready']['tags']
    profile_paths={t['operator']:t['nativeNodes'] for t in projected}
    required_sources={'pipeline_task.cpp','pipeline_fragment_context.cpp','pipeline.cpp','operator.h','sort_sink_operator.h',
                      'sort_sink_operator.cpp','local_merge_sort_source_operator.cpp','heap_sorter.cpp','sorter.cpp','task_scheduler.cpp'}
    source_files={Path(f['path']).name for doc in (release,core) for f in doc['files']}
    proof=dict(
        originalSevenChecks=(set(checks)==known and all(checks[k] for k in known-{'allTasksCausallyClosed'}) and
                             original['liveAfterCommitted'] and original['pipelineZeroUpperMs']<=250 and not pipeline['issues']),
        exactSourceAndReference=(source==prof['query']==native['query']==pipeline['query']==cfg['query']==audit['query']
            ==records['cancelled']['sourceQueryId'] and w['stress']==reference['binding']==plan['binding'] and
            prof['profileSha256']==records['cancelled']['nativeProfileSha256'] and
            reference['profile']['profileSha256']==records['control']['nativeProfileSha256'] and
            reference['profile']['query']==records['control']['sourceQueryId']!=source and prof['query']!=reference['profile']['query']
            and reference['statementSha256']==audit['statementSha256']==FIXED_STATEMENT_HASH),
        fixedVersion=(core['commit']==release['commit']=='bc8ea1bac6d62d92cdebd2e3ac33cc668961ec36' and required_sources<=source_files
            and cfg['be']==w['be']==reference['be'] and cfg['image']==fixture['source']['be']['image']
            =='sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7' and
            cfg['setting']==dict(name='enable_debug_points',type='bool',value=False,mutable=False)
            and datetime.datetime.fromisoformat(cfg['startedUtc'])<datetime.datetime.fromisoformat(w['beforeUnlockPgUtc'])),
        oneHeapPlan=(layout==records['control']['nodes'] and [i['node'] for i in layout]==fixed_nodes and
            [i['phase'] for i in layout if i['node']=='PhysicalTopN']==['MERGE_SORT','LOCAL_SORT'] and
            all(i['limit']==101 and i['offset']==0 and i['order']==expected_orders for i in layout if i['node']=='PhysicalTopN')
            and all(set(r['flags']['SortAlgorithm'])=={'HEAP_SORT'} and set(r['flags']['TOPN filter targets'])=={'[0:8]'}
                    for r in records.values()) and reference['rowCount']==101 and reference['firstFragmentEndMs']>=50),
        taskIdentities=(len(prof['tasks'])==len(profile_paths)==len(all_keys)==3 and
            scan['instance']==merge['instance']!=material['instance'] and scan['index']==1 and merge['index']==material['index']==0
            and any(exact_group(g) for g in complete_groups)
            and shape(cn)==[('OLAP_SCAN_OPERATOR',0),('SORT_SINK_OPERATOR',1)] and
            shape(mn)==[('LOCAL_MERGE_SORT_SOURCE_OPERATOR',1),('DATA_STREAM_SINK_OPERATOR',2)] and
            shape(rn)==[('EXCHANGE_OPERATOR',2),('MATERIALIZATION_OPERATOR',3),('RESULT_SINK_OPERATOR',2147483647)]
            and all(n['parallelTasks']==1 for items in (cn,mn,rn) for n in items[:-1]) and
            all(t['state']=='FINALIZED' for t in by_operator.values())),
        cancellationOnly=(set(e['event'] for e in events)<=native_kinds and all(e['userCancel'] for e in events if e['event'] in errs)
            and sum(e['event']=='register' for e in events)==sum(e['event']=='start' for e in events)==1
            and sum(e['event']=='user_rpc' for e in events)==sum(e['event']=='context_end' for e in events)==1
            and {e['instance'] for e in events if e['event']=='instance_cancel'}=={scan['instance'],material['instance']}
            and audit['state']=='ERR' and audit['userCancel'] and not audit['timeout'] and audit['returnRows']==0),
        downstreamCancellation=(merge['observedShortfall'] and merge['soleMerge'] and material['observedShortfall']
            and merge['referenceRows']==material['referenceRows']==101 and merge['cancelledRows']==material['cancelledRows']==0
            and merge['finalWakeEarly']==material['finalWakeEarly']==0),
        propagatedScanClosure=(scan['finalWakeEarly']==1 and 0<scan['cancelledRows'] and
            all(by_operator['OLAP_SCAN_OPERATOR']['operators']['OLAP_SCAN_OPERATOR'].get(k)
                for k in ('scannerPresent','SegmentIterator','IndexFilter')) and
            'scanEos' not in by_operator['OLAP_SCAN_OPERATOR']['operators']['OLAP_SCAN_OPERATOR']),
        actualHandshake=(window['handshakeScoped'] and window['fresh']==['0','1','0','1'] and not window['recoveryRequired']
            and opened==[handshake['source.thread']]==[w['sourceThread']] and handshake['auxiliary.thread']!=w['sourceThread']),
        officialOutcome=(browser['inputsUnchanged'] and browser['cancel']['httpStatus']==200 and browser['cancel']['queryId']==w['queryId']
            and browser['cancel']['execution']['exit']==0 and browser['cancel']['execution']['mtp']['passed']==1
            and execute['key']==key and execute['status']==503 and execute['code']=='query_timeout'
            and 0<execute['branchMs']<=1000 and 0<execute['elapsedMs']<=5000 and w['terminal']=='CANCELLED'
            and w['persisted']['bytes']==w['persisted']['resultSize']==w['persisted']['readReceipts']==w['successfulAuditCount']==0
            and w['persisted']['resultHash'] is None and w['persisted']['cancelRequested'] and w['cancelAuditCount']==1),
        fixtureRestored=(fixture['temporaryEntityEventAt']=='2026-11-17 12:00:00.123456' and fixture['status']=='RESTORED' and
                         all(t['before']==t['after'] for t in fixture['tables'].values())))
    return dict(case=key,sourceQuery=source,platformQuery=w['queryId'],checks=proof,status='PASS' if all(proof.values()) else 'NO_GO',
                originalBrowser=browser['status'],originalAutomatedCausality=checks['allTasksCausallyClosed'],
                method='Closed fixed HEAP sort dependency propagates verified merge cancellation to the unique scan.',
                scanWakeByObserved=any(t['wakeEarly'] for s in pipeline['samples'] for g in s['groups'] for t in g['tasks']),
                timing=dict(beZeroMs=original['pipelineZeroUpperMs'],feInactiveMs=w['feInactiveUpperMs'],branchMs=execute['branchMs'],totalMs=execute['elapsedMs']),
                inputs=used)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--extract')
    mode.add_argument('--reference',action='store_true')
    mode.add_argument('--reopen')
    parser.add_argument('--evidence-directory',type=Path)
    args=parser.parse_args()
    if args.reopen:
        if args.evidence_directory is None: parser.error('missing --evidence-directory')
        print(json.dumps(dependency_proof(args.evidence_directory,args.reopen),indent=2))
    elif args.reference:
        print(reference().name)
    else:
        print(json.dumps(extract(args.extract),separators=(',',':')))
