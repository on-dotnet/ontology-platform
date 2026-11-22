"""Oracle 固定十槽的当期核算、保守预留和有界采样。"""
import contextlib
import contextvars
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from workflow_oracle_mapping_resources import TASK, GIB, require

RUN = 'product-resume-01'
BATCH = 's2-s3-01'
PLAN = 's2-s3-01-runtime-01'
ACTIVE = contextvars.ContextVar('oracle_runtime_window', default=None)
ROOT = Path(__file__).resolve().parents[2]
AREA = ROOT / 'artifacts/workflow' / TASK / RUN
COLD_MEASUREMENT = contextvars.ContextVar('oracle_runtime_cold_measurement', default=False)
CLOSING = contextvars.ContextVar('oracle_runtime_closing', default=False)
CHECKOUT = GIB
EXIT_MARGIN = 4 * GIB
RUN_MARGIN = 2 * GIB


def choose(total):
    """完整当期账本须能容纳候选检出、运行增长与保护退出。"""
    needed = total + CHECKOUT + RUN_MARGIN + EXIT_MARGIN
    require(needed <= 48 * GIB, 'WINDOW_BUDGET_DEFICIT_' + str(needed - 48 * GIB))
    return (40 if needed <= 40 * GIB else 48) * GIB


def policy():
    nonce = ACTIVE.get()
    if nonce is None:
        return None
    require(re.fullmatch('[a-f0-9]{32}', nonce) and os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'WINDOW_SCOPE')
    row = json.loads((AREA / BATCH / ('window-' + nonce + '.json')).read_bytes())
    require((row['taskId'], row['runId'], row['batch'], row['plan'], row['id'], row['state']) ==
            (TASK, RUN, BATCH, PLAN, nonce, 'OPEN'), 'WINDOW_DECISION_SCOPE')
    require(row['ceiling'] == choose(row['openingBytes']), 'WINDOW_DECISION_LIMIT')
    require(row['priorCloseSha256'] == close_registration()['sha256'], 'WINDOW_DECISION_GENERATION')
    return row


@contextlib.contextmanager
def close_resources():
    token = CLOSING.set(True)
    try:
        yield
    finally:
        CLOSING.reset(token)


def ceiling(total=None):
    if COLD_MEASUREMENT.get():
        require(total is not None and not ACTIVE.get() and os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'WINDOW_COLD_SCOPE')
        return choose(total)
    decision = policy()
    if decision and total is not None and not CLOSING.get():
        require(total + CHECKOUT + EXIT_MARGIN <= decision['ceiling'], 'WINDOW_EARLY_DISK_EXIT')
    return decision['ceiling'] if decision else 40 * GIB


@contextlib.contextmanager
def open_window():
    """由 Master 的单次冷态准入创建限本树、本批的决定，退出时撤销。"""
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_resume as resume
    from workflow_oracle_mapping_s2_contract import frozen_plan
    require(not ACTIVE.get() and not COLD_MEASUREMENT.get() and p.product_run() == RUN and
            ROOT == resume.ROOT and frozen_plan(ROOT, PLAN)['planId'] == PLAN, 'WINDOW_COLD_SCOPE')
    head = close_registration()
    require(head.get('kind') not in ('D368_PG_ONLY','NORMAL_PG_ONLY') or head['status'] == 'TASK_LEVEL_RECOVERY', 'WINDOW_D368_PRODUCT_BLOCKED')
    measuring = COLD_MEASUREMENT.set(True)
    try:
        cold = resume.admit(set(resume.recovery.ORIGINAL_IDS) | set(resume.APIS))
    finally:
        COLD_MEASUREMENT.reset(measuring)
    require(cold['phase'] == RUN and cold['resourceRunId'] == 'implementation-01' and
            cold['platformDisk']['ceilingBytes'] == choose(cold['platformDisk']['totalBytes']) and
            (cold['taskId'], cold['runId'], cold['status']) == (TASK, RUN, 'FORMAL_RESOURCE_READY') and
            not cold['expectedRunningRoles'] and cold['projectedWithHelper'] == dict(memory=14763950080, nanoCpus=10500000000) and
            json.loads((AREA / ('source-admission-' + cold['attempt'] + '.json')).read_bytes()) == cold, 'WINDOW_OPEN_BASIS')
    total = cold['platformDisk']['totalBytes']
    nonce = uuid.uuid4().hex
    path = AREA / BATCH / ('window-' + nonce + '.json')
    row = dict(taskId=TASK, runId=RUN, batch=BATCH, plan=PLAN, id=nonce, state='OPEN',
               coldAttempt=cold['attempt'], openingBytes=total, ceiling=choose(total), policyVersion='20261121-2',
               priorCloseSha256=close_registration()['sha256'],
               allocations=cold['platformDisk']['allocations'], sampleWaitSeconds=5, sampleTimeoutSeconds=25,
               writers=['oracle volume','platform replacement volumes','container layers','host trees','bounded logs'],
               checkoutReserve=CHECKOUT, runReserve=RUN_MARGIN, exitReserve=EXIT_MARGIN)
    p.save(path, row)
    token = ACTIVE.set(nonce)
    try:
        yield row
    finally:
        ACTIVE.reset(token)
        p.save(path, {**row, 'state': 'CLOSED'}, True)


def charged(disk, current, host):
    """固定项保留；逐项叠加正向实耗，不借用同窗其他行下降。"""
    allocations = disk['allocations']
    sources = current['volumesLogicalBytes']
    initial = disk['initialSourceMeasurement']
    require(sources.keys() == disk['sourceVolumeCaps'].keys() and
            all(current[key].keys() == initial[key].keys() for key in
                ('platformVolumes', 'replacementVolumes', 'containerWritableBytes')), 'WINDOW_STORAGE_IDENTITIES')
    source = sum(max(size, disk['sourceVolumeCaps'][name]) for name, size in sources.items())
    layers = sum(max(size, initial['containerWritableBytes'][key]) for key, size in current['containerWritableBytes'].items())
    growth = dict(source=source - allocations['sourceAndReplacement'],
                  layers=layers - allocations['containerLayers'],
                  host=max(0, host - allocations['currentHostIncludingFirstBackup']))
    for group, reserved in [('platformVolumes', 'platformOriginal'), ('replacementVolumes', 'platformReplacement')]:
        growth[group] = max(0, sum(current[group].values()) - allocations[reserved])
    return disk['totalBytes'] + sum(growth.values()), growth


def sample(attempt):
    import workflow_oracle_mapping_resume as r
    require(os.environ.get('OMQ_PRODUCT_RUN') == RUN and re.fullmatch('[a-f0-9]{32}', attempt), 'WINDOW_SAMPLE_SCOPE')
    basis = r.load(AREA / ('source-admission-' + attempt + '.json'))
    ids = r.manifest()['ids']
    require(set(ids) == set(basis['expectedRunningRoles']) and basis['runId'] == RUN and
            basis['status'] == 'FORMAL_RESOURCE_READY', 'WINDOW_SAMPLE_ROLES')
    replacement = r.load(r.recovery.RECOVERY_AREA / 'replacement-resources.json')
    usage = r.platform.current_storage(r.BASE, {**replacement, 'extraIds': {k: ids[k] for k in r.APIS}, 'extraRun': RUN})
    disk = basis['platformDisk']
    paths = disk['hostPaths']
    sizes = [line.split(None, 1) for line in subprocess.check_output(['du', '-sk', *paths], text=True, timeout=15).splitlines()]
    require([path for size, path in sizes] == paths, 'WINDOW_HOST_SET')
    total, growth = charged(disk, usage, sum(int(size)*1024 for size, path in sizes))
    vm = subprocess.check_output(['docker', '--context', 'desktop-linux', 'exec', ids['platform-pg'],
                                  'sh', '-ec', 'df -Pk /; cat /proc/meminfo'], text=True, timeout=5)
    raw = subprocess.check_output(['vm_stat'], text=True, timeout=3)
    page = int(re.search(r'page size of (\d+) bytes', raw)[1])
    memory = page * sum(int(re.search('Pages '+name+r':\s*(\d+)', raw)[1]) for name in ('free', 'inactive'))
    return dict(atUtc=dt.datetime.now(dt.timezone.utc).isoformat(), totalBytes=total, growth=growth,
                hostFree=shutil.disk_usage(ROOT).free, vmFree=int(vm.splitlines()[1].split()[-3])*1024,
                hostMemory=memory, hostBytes=sum(int(size)*1024 for size, path in sizes), storage=usage, vmMemory=int(re.search(r'^MemAvailable:\s+(\d+)', vm, re.M)[1])*1024)


def allow_sample(row, limit):
    require(row['totalBytes'] + EXIT_MARGIN + CHECKOUT < limit, 'WINDOW_EARLY_DISK_EXIT')
    require(row['hostFree'] >= 15*GIB and row['vmFree'] >= 27*GIB, 'WINDOW_EARLY_PHYSICAL_EXIT')
    require(row['hostMemory'] >= 4*GIB and row['vmMemory'] >= 7*GIB//2, 'WINDOW_MEMORY_FLOOR')


@contextlib.contextmanager
def monitored(attempt):
    """启动前同步采样，父命令期间采样失败或余量不足即中断进程组。"""
    decision = policy()
    require(decision is not None, 'WINDOW_DECISION_REQUIRED')
    output = AREA / BATCH / ('samples-' + decision['id'] + '.jsonl')
    done = threading.Event()
    failed = []
    def record(row):
        with output.open('a') as stream:
            stream.write(json.dumps(row) + '\n')
    def once():
        result = subprocess.run([sys.executable, '-B', __file__, attempt], capture_output=True, timeout=25)
        require(result.returncode == 0, 'WINDOW_SAMPLER_EXIT_' + str(result.returncode))
        row = json.loads(result.stdout)
        record(row)
        allow_sample(row, decision['ceiling'])
    def watch():
        while not done.wait(5):
            try:
                once()
            except Exception as error:
                failed.append(str(error))
                try:
                    record(dict(status='PROTECTIVE_EXIT', reason=failed[-1]))
                finally:
                    if not done.is_set():
                        os.kill(os.getpid(), signal.SIGUSR1)
                return
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    try:
        once()
    except Exception as error:
        record(dict(status='PRESTART_REFUSED', reason=str(error)))
        raise
    old = signal.signal(signal.SIGUSR1, interrupt)
    thread = threading.Thread(target=watch)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()
        signal.signal(signal.SIGUSR1, old)
        require(not failed, 'WINDOW_PROTECTED_' + str(failed[:1]))
        once()


if __name__ == '__main__':
    print(json.dumps(sample(sys.argv[1])))

# 当前准许的替代副本由该次收口关闭，图库含两次已发布内容。
CLOSE_FILE = 'closeout-ec277a6910354c72884c646d9e3e6df0.json'
CLOSE_SHA = '285daba082c9b20328d9559cf51d65e6e71df363b3e9e4562025581088ba73d9'


def close_registration(digest=None):
    """只从本次驱动输入登记的连续代次中选择显式身份。"""
    import workflow_execution as ex
    index = json.loads(ex.ordinary(Path(__file__).with_name('workflow-oracle-runtime-close-registry.json')).read_bytes())
    require((index['taskId'], index['runId'], index['batch'], index['planId']) ==
            (TASK, RUN, BATCH, PLAN), 'WINDOW_CLOSE_REGISTRY_SCOPE')
    known = {}
    operations = set()
    parents = set()
    previous = CLOSE_SHA
    for row in index['generations']:
        kind = row.get('kind', 'FORMAL')
        require(row['previousSha256'] == previous and row['sha256'] not in known and
                row['operation'] not in operations and re.fullmatch('[a-f0-9]{32}', row['operation']) and
                row['sha256'] != CLOSE_SHA and re.fullmatch('[a-f0-9]{64}', row['sha256']),
                'WINDOW_CLOSE_REGISTRY_CHAIN')
        if kind == 'DIAGNOSTIC_CLOSE':
            from workflow_oracle_diagnostic_close import ENTRY
            require(row == ENTRY and known[previous]['kind'] == 'PRE_DIAGNOSTIC_CLOSE','WINDOW_DIAGNOSTIC_REGISTRY')
            known[previous] = {**known[previous],'nextDiagnosticClose':row['sha256']}
        elif kind == 'PRE_DIAGNOSTIC_CLOSE':
            from workflow_oracle_prediagnostic_close import ENTRY
            require(row == ENTRY and known[previous]['kind'] == 'D368_PG_ONLY'
                    and known[previous]['status'] == 'TASK_LEVEL_RECOVERY','WINDOW_PREDIAGNOSTIC_REGISTRY')
            row = {**row,'grantCheckpoint':known[previous]['grantCheckpoint']}
            known[previous] = {**known[previous],'nextPreDiagnosticClose':row['sha256']}
        elif kind in ('D368_PG_ONLY','NORMAL_PG_ONLY'):
            from workflow_oracle_d368_pg_close import PREVIOUS
            from workflow_oracle_d368_closure import QUERY
            if kind=='NORMAL_PG_ONLY':
                from workflow_oracle_d368_closure import NORMAL_CLOSE as PREVIOUS, NORMAL_QUERY as QUERY
            required = {'kind','operation','queryId','previousSha256','sha256','sizeBytes','status','memberCount','memberIndexSha256'}
            require(set(row) == required and previous == PREVIOUS and (kind=='NORMAL_PG_ONLY' or known[previous]['kind'] == 'MAPPING_RESTORE')
                    and row['queryId'] == QUERY and row['status'] in ('TASK_LEVEL_RECOVERY','BLOCKED')
                    and type(row['sizeBytes']) is int and row['sizeBytes'] > 0 and type(row['memberCount']) is int
                    and row['memberCount'] > 0 and re.fullmatch('[a-f0-9]{64}',row['memberIndexSha256']), 'WINDOW_D368_REGISTRY')
            row = {**row, 'grantCheckpoint':known[previous]['grantCheckpoint']}
            known[previous] = {**known[previous], 'nextPgOnlyClose':row['sha256']}
        elif kind == 'MAPPING_RESTORE':
            require(previous in known and 'parentId' not in row and 'parentSha256' not in row and
                    re.fullmatch('[a-f0-9]{32}', row['hostId']) and row['exitCode'] == 0,
                    'WINDOW_RESTORE_REGISTRY')
            row = {**row, 'grantCheckpoint': known[previous]['grantCheckpoint']}
            known[previous] = {**known[previous], 'nextRestoreHost': row['hostId']}
        else:
            require(kind == 'FORMAL' and row['parentId'] not in parents and
                    re.fullmatch('[a-f0-9]{32}', row['parentId']), 'WINDOW_CLOSE_REGISTRY_CHAIN')
            if row['sha256']=='a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348':
                require(known[previous]['kind']=='DIAGNOSTIC_CLOSE' and row['parentId']=='4032c1d770b240989966ba3275d86999','NORMAL_CLOSE_PREVIOUS')
                row={**row,'grantCheckpoint':known[previous]['grantCheckpoint']}
            parents.add(row['parentId'])
        operations.add(row['operation'])
        known[row['sha256']] = row
        previous = row['sha256']
    require(index['currentSha256'] == previous, 'WINDOW_CLOSE_REGISTRY_HEAD')
    selected = index['currentSha256'] if digest is None else digest
    require(selected in known, 'WINDOW_GRAPH_GENERATION')
    return known[selected]


def last_close(root, archive=None, digest=None):
    """逐件重开所选登记代次的原生停机、排空、保护清单及准确资源闭集。"""
    import workflow_execution as ex
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    entry = close_registration(digest)
    if entry.get('kind') == 'DIAGNOSTIC_CLOSE':
        from workflow_oracle_diagnostic_close import reopen
        prior = last_close(root, archive, entry['previousSha256'])
        return reopen(root, entry, prior, archive)[0]
    if entry.get('kind') == 'PRE_DIAGNOSTIC_CLOSE':
        from workflow_oracle_prediagnostic_close import reopen
        prior = last_close(root, archive, entry['previousSha256'])
        return reopen(root, entry, prior, archive)[0]
    if entry.get('kind') in ('D368_PG_ONLY','NORMAL_PG_ONLY'):
        from workflow_oracle_d368_pg_close import reopen
        previous = last_close(root, archive, entry['previousSha256'])
        normalized, _, _ = reopen(root, entry, previous, archive)
        return normalized
    area = c.AREA
    restore = entry.get('kind') == 'MAPPING_RESTORE'
    prefix = 'controlled-mapping-restore-' if restore else 'controlled-run-'
    data = c.raw(root, area / BATCH / (prefix + entry['operation'] + '.json'), archive)
    require(len(data) == entry['sizeBytes'] and ex.sha(data) == entry['sha256'], 'WINDOW_LAST_CLOSE_ORIGINAL')
    close = json.loads(data)
    native = entry['nativeStops']
    apis = entry['apiStops']
    require(set(native) == {'oracle', 'fuseki', 'platform-pg', 'keycloak-test', 'rustfs'} and
            set(apis) == {'api', 'api-secondary'} and
            (close['taskId'], close['runId'], close['batch'], close['planId'], close['operation']) ==
            (TASK, RUN, BATCH, PLAN, entry['operation']) and close['exitCode'] == entry['exitCode'] and
            close['remaining'] == close['errors'] == [] and close['protectedSame'] is True and
            set(close['closed']) == set(close['starts']) == native.keys() | apis.keys(), 'WINDOW_LAST_CLOSE_SCOPE')
    if restore:
        require(close['status'] == 'FINISHED' and 'parent' not in close and
                close['hostProof']['closeSha256'] == entry['previousSha256'] and
                close['hostProof']['host'] == close['host']['commandId'] == entry['hostId'],
                'WINDOW_RESTORE_HOST')
    else:
        require(close['parent']['commandId'] == entry['parentId'] and close['parent']['exitCode'] == close['exitCode']
                and close['status'] == ('PASS' if entry['exitCode'] == 0 else 'BLOCKED'), 'WINDOW_LAST_CLOSE_SCOPE')
    members = {}

    def read(path):
        value = c.raw(root, path, archive)
        members[str(path)] = ex.sha(value)
        return value

    def output(run, cid, stage=None):
        directory = area.parent / 'commands' / run / cid
        record = json.loads(read(directory / 'receipt.json'))
        out = read(directory / 'stdout.txt')
        err = read(directory / 'stderr.txt')
        require((record['taskId'], record['runId'], record['commandId'], record['exitCode']) == (TASK, run, cid, 0)
                and record['classification'] == 'SUCCESS' and (stage is None or record['stage'] == stage)
                and record['stdout']['sha256'] == ex.sha(out) and record['stderr']['sha256'] == ex.sha(err),
                'WINDOW_LAST_COMMAND')
        return out

    normalized = dict(ids={}, data={}, apis={})
    if restore:
        from workflow_oracle_mapping_continuation import prefix_activation
        win = json.loads(read(area / BATCH / ('window-' + close['windowId'] + '.json')))
        require((win['taskId'],win['runId'],win['batch'],win['plan'],win['state'],win['id'],win['coldAttempt']) ==
                (TASK,RUN,BATCH,PLAN,'CLOSED',close['windowId'],close['cold']) and
                win['priorCloseSha256'] == entry['previousSha256'] and win['ceiling'] == choose(win['openingBytes']),
                'WINDOW_RESTORE_ENVELOPE')
        report_path = area / BATCH / ('mapping-recovery-' + entry['operation'] + '.json')
        summary = json.loads(output(RUN,close['mappingCommand'],'normal-mapping-rollback'))
        report = json.loads(read(report_path))
        require(summary['status'] == report['status'] == 'PASS' and
                Path(summary['report']).parts[-len(report_path.parts):] == report_path.parts and
                (report['taskId'],report['runId'],report['batch'],report['executionId'],report['windowId']) ==
                (TASK,RUN,BATCH,entry['operation'],close['windowId']), 'WINDOW_RESTORE_REPORT')
        before = json.loads(output(RUN,report['chainBeforeCommand'],'omq-pg-s23-recovery-activation'))
        after = json.loads(output(RUN,report['chainAfterCommand'],'omq-pg-s23-recovery-activation'))
        prefix_chain = json.loads(output(RUN,close['prefixActivationCommand'],'omq-pg-s23-prefix-activation'))
        require(len(before['receipts']) == 2 and after == prefix_chain and after['receipts'][:2] == before['receipts']
                and before['current'] == [before['receipts'][1]['receipt'][key] for key in
                                         ('activationId','activationRevision','mappingReleaseId')],
                'WINDOW_RESTORE_CHAIN')
        original = before['receipts'][0]
        active = report['currentActive']
        receipt = report['currentReceipt']
        require(active['usable'] and all(active[key] == receipt[key] for key in
                ('mappingId','mappingReleaseId','activationRevision','manifestHash')), 'WINDOW_RESTORE_ACTIVE')
        prefix_activation(root,close['host'],dict(activation=original['receipt'],connectionId=original['connection'],
                          catalogSnapshotId=original['catalog']),dict(mappingReceipt=receipt,
                          catalogFingerprint=original['fingerprint']),close['prefixActivationCommand'],archive)
        from workflow_oracle_mapping_access_refresh import observed_rows
        _, restore_rows = observed_rows(root,close['host'],archive)
        normalized.update(restoreHost=close['host'], restoreHostProof=close['hostProof'])
    for role, (stop_id, state_id, *commands) in native.items():
        stop = json.loads(read(area.parent / c.RECOVERY / ('stop-' + stop_id + '.json')))
        state = json.loads(output(c.RECOVERY, state_id, 'omq-recovery-stopped-state'))
        for cid in commands:
            output(c.RECOVERY, cid)
        record = close['closed'][role]
        require(stop['role'] == role and stop['operation'] == entry['operation'] and stop['group'] == 'replacement'
                and {key: stop[key] for key in record} == record and
                all(state[key] == value for key, value in record['after'].items()) and
                state['Status'] == 'exited' and state['Pid'] == 0 and not state['OOMKilled'] and not state['Error'] and
                state['ExitCode'] in (0, 143) and stop['logExit'] == 0 and
                utc(state['StartedAt']) < utc(state['FinishedAt']), 'WINDOW_LAST_NATIVE')
        if restore:
            start = json.loads(read(area.parent / c.RECOVERY / ('start-' + close['starts'][role] + '.json')))
            host = restore_rows[role]
            require(start['attempt'] == close['starts'][role] and start['role'] == role and start['status'] == 'RUNNING'
                    and start['id'] == record['id'] == host['containerId'] and
                    stop['status'] == ('PROCESS_EXITED' if role == 'fuseki' else 'CLEAN_STOP')
                    and state['StartedAt'] == host['startedAt'], 'WINDOW_RESTORE_NATIVE_START')
        normalized['ids'][role] = record['id']
        normalized['data'][role] = {**record, 'startedAt': state['StartedAt']}
    for role, (term, exited, removed, absent) in apis.items():
        cid = close['closed'][role]
        output(RUN, term, 'resume-api-term')
        require(output(RUN, exited, 'resume-api-exit').strip() in (b'exited 0 false', b'exited 143 false') and
                output(RUN, removed, 'resume-remove-stateless').decode().strip() == cid and
                not output(RUN, absent, 'resume-absent').strip() and cid == close['starts'][role]['id'], 'WINDOW_LAST_API')
        if restore:
            require(cid == close['host']['services'][role]['containerId'] and
                    output(RUN,close['starts'][role]['startCommand'],'resume-start-'+role).decode().strip() == cid,
                    'WINDOW_RESTORE_API_START')
        normalized['ids'][role] = cid
        normalized['apis'][role] = {'id': cid}
    for label in ('before', 'after'):
        row = close['drain'][label]
        require(json.loads(output(RUN, row['commandId'], 'omq-pg-runtime-drain-' + label)) == row['values'] == [0]*7,
                'WINDOW_LAST_DRAIN')
    inventories = []
    for key in ('cold', 'post'):
        record = json.loads(read(area / ('source-admission-' + close[key] + '.json')))
        require(record['expectedRunningRoles'] == [] and record['status'] == 'FORMAL_RESOURCE_READY', 'WINDOW_LAST_ROLES')
        inventories.append({item['stage']: output(RUN, item['commandId'], 'oracle-admission-' + item['stage'])
                            for item in record['commands'] if item['stage'] in ('old-resources', 'all-running')})
    require(inventories[0] == inventories[1] and len(inventories[0]['old-resources'].splitlines()) == 20 and
            len(inventories[0]['all-running'].splitlines()) == 3 and len(members) == entry['memberCount'] and
            ex.sha(ex.encoded(dict(sorted(members.items())))) == entry['memberIndexSha256'],
            'WINDOW_LAST_RESOURCE_ORIGINALS')
    last_finished = {role: data['after']['FinishedAt'] for role,data in normalized['data'].items()}
    for edge in entry.get('maintenance', []):
        # 两副本读回/维护窗不能藏在完整七角色窗之间；逐角色推进结束时间，下次实测须晚于此边。
        members.clear()
        operation = edge['operation']
        require(re.fullmatch('[a-f0-9]{32}', operation), 'WINDOW_MAINT_OPERATION')
        observation = c.raw(root, area/BATCH/('aba-maintenance-observation-'+operation+'.json'), archive)
        require(ex.sha(observation) == edge['sha256'], 'WINDOW_MAINT_ORIGINAL')
        row = json.loads(observation)
        roles = set(edge['roles'])
        require((row['taskId'],row['runId'],row['batch'],row['priorClose'],row['operation']) ==
                (TASK,RUN,BATCH,entry['operation'],operation) and roles == set(row['closed']) == set(row['starts'])
                == {'platform-pg','oracle'} and row['observationStatus'] == 'OBSERVED' and not row['errors']
                and row['protectedSame'] and row['remaining'] == [], 'WINDOW_MAINT_SCOPE')
        window = json.loads(read(area/BATCH/('window-'+row['window']+'.json')))
        require((window['taskId'],window['runId'],window['batch'],window['plan'],window['state'],window['coldAttempt'])
                == (TASK,RUN,BATCH,PLAN,'CLOSED',row['cold']) and window['ceiling'] == choose(window['openingBytes']),
                'WINDOW_MAINT_ENVELOPE')
        for label in ('before','after'):
            require(json.loads(output(RUN,row['commands'][label],'omq-pg-aba-maint-'+label)) == row[label] == [0]*7,
                    'WINDOW_MAINT_DRAIN')
        for role in apis:
            require(not output(RUN,row['commands']['absent-'+role],'aba-maint-absent-'+role).strip(), 'WINDOW_MAINT_API')
        for side in ('cold','post'):
            audit = json.loads(read(area/('source-admission-'+row[side]+'.json')))
            observed = {part['stage']:output(RUN,part['commandId'],'oracle-admission-'+part['stage'])
                        for part in audit['commands'] if part['stage'] in ('old-resources','all-running')}
            require(audit['expectedRunningRoles'] == [] and audit['status'] == 'FORMAL_RESOURCE_READY'
                    and observed == inventories[1], 'WINDOW_MAINT_PROTECTED')
        for role, steps in edge['roles'].items():
            prior = output(RUN,row['commands']['prior-'+role],'aba-maint-stopped-'+role).decode().strip()
            cid = normalized['ids'][role]
            start = json.loads(read(area.parent/c.RECOVERY/('start-'+row['starts'][role]+'.json')))
            stop = json.loads(read(area.parent/c.RECOVERY/('stop-'+steps['stop']+'.json')))
            state = json.loads(output(c.RECOVERY,steps['state'],'omq-recovery-stopped-state'))
            require(start['role'] == stop['role'] == role and start['id'] == stop['id'] == cid
                    and start['status'] == 'RUNNING' and stop['group'] == 'replacement' and stop['operation'] == operation
                    and stop['status'] == 'CLEAN_STOP' and {k:stop[k] for k in row['closed'][role]} == row['closed'][role]
                    and all(state[k] == v for k,v in stop['after'].items()) and state['Status'] == 'exited'
                    and state['Pid'] == 0 and not state['OOMKilled'] and not state['Error'], 'WINDOW_MAINT_NATIVE')
            require(prior == 'exited|'+last_finished[role]+'|0' and
                    utc(last_finished[role]) < utc(state['StartedAt']) < utc(state['FinishedAt']),
                    'WINDOW_MAINT_ORDER')
            require(output(c.RECOVERY,steps['start'],'omq-recovery-start-'+role).decode().strip() == cid,
                    'WINDOW_MAINT_START')
            start_command = json.loads(read(area.parent/'commands'/c.RECOVERY/steps['start']/'receipt.json'))
            require(utc(start_command['startedAtUtc']) <= utc(state['StartedAt']) <= utc(start_command['endedAtUtc']),
                    'WINDOW_MAINT_START_ORDER')
            for stage, command in steps['native'].items():
                output(c.RECOVERY,command,'omq-recovery-'+stage)
            last_finished[role] = state['FinishedAt']
        require(ex.sha(ex.encoded(members)) == edge['memberIndexSha256'], 'WINDOW_MAINT_MEMBER_INDEX')
        normalized.setdefault('maintenance', []).append(dict(operation=operation,finishedAt={k:last_finished[k] for k in roles}))
    return normalized


def graph_stop(close):
    """沿已经重开的关闭链定位准确的最近一次 Fuseki 停机。"""
    from workflow_oracle_mapping_evidence import utc
    closed = close['data']['fuseki']
    finished = closed['after']['FinishedAt']
    for edge in close.get('maintenance', []):
        if 'fuseki' in edge['finishedAt']:
            newer = edge['finishedAt']['fuseki']
            require(utc(finished) < utc(newer), 'WINDOW_GRAPH_STOP_ORDER')
            finished = newer
    return closed['id'], finished


def published_graphs(cid, started, pid, basis, refs=None, archive=None, *, close_sha=CLOSE_SHA):
    import workflow_execution as ex
    import workflow_oracle_mapping_continuity as c
    import workflow_oracle_mapping_evidence as e
    from workflow_oracle_mapping_resume import recovery as r
    require(cid == c.FUSEKI and pid > 0, 'WINDOW_GRAPH_ROLE')
    if close_sha != CLOSE_SHA:
        stopped_id, finished = graph_stop(last_close(ROOT, archive, close_sha))
    else:
        require(close_sha == CLOSE_SHA and (started, pid) == ('2026-11-21T11:53:49.540115255Z', 87804), 'WINDOW_GRAPH_GENERATION')
        close_bytes = c.raw(ROOT, c.AREA / BATCH / CLOSE_FILE, archive)
        require(ex.sha(close_bytes) == CLOSE_SHA, 'WINDOW_CLOSE_ORIGINAL')
        stopped_id, finished = graph_stop(json.loads(close_bytes))
    require(stopped_id == cid and finished == basis['finishedAt'] and
            e.utc(basis['finishedAt']) < e.utc(started), 'WINDOW_GRAPH_STOP')
    capture = refs is None
    refs = {} if capture else refs.copy()
    if capture:
        r.engine_step('tdb-read-ready','exec',cid,'curl','--noproxy','*','--silent','--fail','--retry','20',
                      '--retry-connrefused','--retry-delay','1','--retry-max-time','20','--max-time','2',
                      'http://127.0.0.1:3030/$/ping',timeout=25)
    def original(name, argv, data=None):
        key = ex.sha(ex.encoded(argv) if data is None else data)
        stage = 's23-runtime-graph-' + name
        if capture:
            measured = ex.run(argv, ROOT, task=TASK, run_id=RUN, stage=stage, input_key=key, stdin=data, timeout=25)
            refs[name] = measured.receipt['commandId']
        rec, out, err = c.command(ROOT, refs[name], RUN, argv, stage, key, 25, archive)
        require(not err and e.utc(started) <= e.utc(rec['startedAtUtc']), 'WINDOW_GRAPH_ORDER')
        return out
    scans = [json.loads(original(kind, c.scan_argv(kind)))['results']['bindings'] for kind in ('default','named')]
    argv = ['docker','--context','desktop-linux','exec','-i','--user','postgres',c.PG,
            'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    c.check_publications([json.loads(line) for line in original('published', argv, c.publication_sql()).splitlines() if line.strip()])
    frozen = c.raw(ROOT, c.AREA / BATCH / 'frozen-graphs-second-open.json', archive)
    require(ex.sha(frozen) == '393a597292cfba79d9b772bf7bac9a34d3e7d843bcf0c7e9ed3e97e9fd87c328','WINDOW_GRAPH_FROZEN')
    return dict(kind=PLAN, close=close_sha, startedAt=started, pid=pid,
                observed=c.expected_graphs(*scans, json.loads(frozen)), commands=refs)


def runtime_continuity(root, previous, current, proof=None, archive=None):
    """以旧 access 的完整宿主链、确定的关闭和两端实测挂载核定当前新代。"""
    import workflow_execution as ex
    import workflow_oracle_mapping_continuity as c
    import workflow_oracle_mapping_acl_host as history
    import workflow_oracle_mapping_evidence as e
    from workflow_oracle_mapping_continuation import REUSED_ACCESS
    if proof is None or proof.get('closeSha256') != CLOSE_SHA:
        entry = close_registration(None if proof is None else proof['closeSha256'])
        if 'nextRestoreHost' in entry:
            require(current['commandId'] == entry['nextRestoreHost'], 'WINDOW_RETIRED_HOST')
        require('nextPgOnlyClose' not in entry, 'WINDOW_D368_RETIRED_HOST')
        require('nextPreDiagnosticClose' not in entry,'WINDOW_PREDIAGNOSTIC_RETIRED_HOST')
        if 'nextDiagnosticClose' in entry:
            require(proof is not None and proof.get('host') == current['commandId'] == 'd8f06371e55d4d34ab096f4452d1fab9',
                    'WINDOW_DIAGNOSTIC_RETIRED_HOST')
        if entry.get('kind') in ('MAPPING_RESTORE','D368_PG_ONLY','PRE_DIAGNOSTIC_CLOSE','DIAGNOSTIC_CLOSE'):
            require(entry.get('kind') != 'D368_PG_ONLY' or entry['status'] == 'TASK_LEVEL_RECOVERY', 'WINDOW_D368_PRODUCT_BLOCKED')
            close = last_close(root, archive, entry['sha256'])
            middle = close['restoreHost']
            runtime_continuity(root, previous, middle, close['restoreHostProof'], archive)
            return compare_generation(root, middle, current, close, entry['sha256'], proof, archive)
        current_close=entry['sha256']
        if entry.get('kind')=='NORMAL_PG_ONLY':
            require(entry['status']=='TASK_LEVEL_RECOVERY','NORMAL_PRODUCT_BLOCKED')
            entry=close_registration(entry['previousSha256'])
        data = c.raw(root, c.AREA / ('formal-run-s2-s3-oracle-' + entry['parentId'] + '.json'), archive)
        require(ex.sha(data) == entry['parentSha256'], 'WINDOW_LAST_PARENT')
        prior = json.loads(data)
        require((prior['taskId'], prior['runId'], prior['mode'], prior['case'], prior['commandId'],
                 prior['exitCode'], prior['stageInputs']['plan']['planId']) ==
                (TASK, RUN, 's2-s3-oracle', 'healthy', entry['parentId'], entry['exitCode'], PLAN),
                'WINDOW_LAST_PARENT_SCOPE')
        middle = prior['host']
        ref = prior['stageInputs']['qualifiedPrefix']
        observation = c.raw(root, c.AREA / BATCH / ref['file'], archive)
        require(ex.sha(observation) == ref['sha256'], 'WINDOW_LAST_PREFIX')
        prior_obs = json.loads(observation)
        require(e.stable_host(prior_obs['host']) == e.stable_host(middle) and
                prior_obs['hostContinuity']['closeSha256'] == entry['previousSha256'], 'WINDOW_LAST_HOST')
        runtime_continuity(root, previous, prior_obs['host'], prior_obs['hostContinuity'], archive)
        close = last_close(root, archive, current_close)
        return compare_generation(root, middle, current, close, current_close, proof, archive)
    parent = REUSED_ACCESS['commandId']
    data = c.raw(root, c.AREA / ('formal-run-s2-s3-oracle-'+parent+'.json'), archive)
    require(ex.sha(data) == 'b7861c9207dbed9d6018c8581c931b2c64f30c2697a302635a23974263428f2f','WINDOW_ACCESS_PARENT')
    dispatch = json.loads(data)
    middle = dispatch['host']
    ref = dispatch['stageInputs']['qualifiedPrefix']
    obs = c.raw(root, c.AREA / BATCH / ref['file'], archive)
    require(ex.sha(obs)==ref['sha256'] and e.stable_host(json.loads(obs)['host'])==e.stable_host(middle),'WINDOW_PRIOR_HOST')
    history.lifecycle(root, previous, middle, json.loads(obs)['hostContinuity'], archive)
    raw = c.raw(root, c.AREA / BATCH / CLOSE_FILE, archive)
    require(ex.sha(raw)==CLOSE_SHA,'WINDOW_HOST_CLOSE')
    close=json.loads(raw)
    require(close['remaining'] == [] and close['status'] == 'PASS', 'WINDOW_PRIOR_CLOSE')
    return compare_generation(root, middle, current, close, CLOSE_SHA, proof, archive)


def compare_generation(root, middle, current, close, digest, proof, archive):
    import copy
    import workflow_oracle_mapping_access_refresh as refresh
    import workflow_oracle_mapping_evidence as e
    rows = [refresh.observed_rows(root, host, archive)[1] for host in (middle,current)]
    builds = [refresh.snapshot_builds(root, host, archive) for host in (middle,current)]
    rebuilt = builds[0] != builds[1] and digest != CLOSE_SHA
    if rebuilt:
        require(digest != '35bcf152b788c21a72690c7b3fa2cc7f58355b1c6b66fc54ec4074d2d83be691' and middle['buildInputKey'] != current['buildInputKey']
                and all(builds[0][role]['snapshotId'] != builds[1][role]['snapshotId']
                        and builds[0][role]['commandId'] != builds[1][role]['commandId']
                        for role in ('api','agent','query')), 'WINDOW_LAST_BUILDS')
        from workflow_oracle_mapping_acl_host import compare_definitions
        compare_definitions(root,middle,current,*rows,builds,archive)
    require(close['ids']=={k:v['containerId'] for k,v in rows[0].items()},'WINDOW_PRIOR_ROLES')
    # 此处只消除已核的进程代次差异，再复用原像、挂载、网络、API快照比较器。
    normalized = [copy.deepcopy(host) for host in (middle,current)]
    normalized_rows = copy.deepcopy(rows)
    finished = {role: row['after']['FinishedAt'] for role,row in close['data'].items()}
    for edge in close.get('maintenance', []):
        finished.update(edge['finishedAt'])
    for role, old in rows[0].items():
        new=rows[1][role]
        if role in ('api','api-secondary'):
            require(close['apis'][role]['id']==old['containerId'] and new['containerId']!=old['containerId'] and
                    (digest == CLOSE_SHA or e.utc(finished['platform-pg']) < e.utc(new['startedAt'])), 'WINDOW_API_REPLACED')
            continue
        stop=close['data'][role]
        require(old['pid'] > 0 and new['pid'] > 0 and stop.get('startedAt', old['startedAt']) == old['startedAt'], 'WINDOW_PRIOR_PROCESS')
        require(old['containerId']==new['containerId']==stop['id'] and
                e.utc(old['startedAt']) < e.utc(stop['after']['FinishedAt']) <= e.utc(finished[role]) < e.utc(new['startedAt']), 'WINDOW_RESTART_ORDER')
        for field in ('pid','startedAt'):
            normalized_rows[1][role][field]=old[field]
            if role!='oracle':
                normalized[1]['services'][role][field]=old[field]
    refresh.compare_hosts(root,*normalized,*normalized_rows,builds)
    value=dict(status='CURRENT_RUNTIME_GENERATION',closeSha256=digest,oldHost=middle['commandId'],
               host=current['commandId'], builds=builds[1], stoppedRoles=sorted(close['ids']))
    if 'maintenance' in close:
        value['maintenance'] = close['maintenance']
    if rebuilt:
        value['buildTransition'] = dict(status='REBUILT', previous=builds[0], current=builds[1])
    require(proof is None or proof==value,'WINDOW_CONTINUITY_PROOF')
    return value
