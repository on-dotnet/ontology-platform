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
               coldAttempt=cold['attempt'], openingBytes=total, ceiling=choose(total), policyVersion='20261121-1',
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


LAST_OPERATION = '330c11744f364d1187332e0d93801098'
LAST_CLOSE = '35bcf152b788c21a72690c7b3fa2cc7f58355b1c6b66fc54ec4074d2d83be691'
LAST_PARENT = '1080791aa97546f29c34fd915618ecef'
# 各角色依次绑定原生 stop 文件、退出状态命令和对应的关闭命令。
NATIVE_STOPS = {
    'oracle': ('317dd39db1f74a408220e0ef2ff53141',
            '63e7584705bf443b960047b0b0c83f4d',
            'a276d949d4ab43158baa1c10930f5a78',
            '7efc6a326e054c148cd68183eceaf18d'),
    'rustfs': ('e06824ffb8db449d83ba078f4006b4ec',
            '51369c267be84e03b8c9391a82a2d90d',
            'f2e7ed5d19284e5c8f6639153896b439'),
    'keycloak-test': ('81985700e5cd4326b55ba5c41cf25345',
            '2c82197f24fb4b23a5f5fb851c065239',
            '86c99ec2c2f04ba087af4c44b5c2c5b2'),
    'fuseki': ('df85df6f1f7f4ecf8dd3c252d63f7db7',
            'af58d6aa7f6d42aba07adbc9db5db2c8',
            'acd519e2fdb3496b99fa480d5e56a75a',
            'a0ad86db5e3d43dd9e6749245f8d0195'),
    'platform-pg': ('ffa315593e42425bb34777adcdc687a7',
            '953b33f64ce445c2bc192bdda4260b2e',
            'cd1f086d8a3d4525af0fa066181ca5bd',
            'c883e5f461d1441c8f2d886e4b19b047',
            'e6d6dfbd9d4341dead2dd1a1815bf7e7'),
}
API_STOPS = {
    'api': ('9c499e74e63b4c2ea67d687504a6b5ee',
            '12502f27b42349168b5a017619bc60c1',
            '03c1bcfb7a5043899bd02b44c44cf312',
            'd09bf181d8bb4ecba7c2245297079074'),
    'api-secondary': ('81b94685d70446eda0c145f3a93baa3d',
            '7bda3a72823146979629001f6d82793b',
            '6392e3c4243a4ef89da831b9854b6f9a',
            '0de9719fea5843e780abfe0532621f59'),
}


def last_close(root, archive=None):
    """重开上一父窗的原生停机、排空、保护清单及准确资源闭集。"""
    import workflow_execution as ex
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    area = c.AREA
    data = c.raw(root, area / BATCH / ('controlled-run-' + LAST_OPERATION + '.json'), archive)
    require(len(data) == 4170 and ex.sha(data) == LAST_CLOSE, 'WINDOW_LAST_CLOSE_ORIGINAL')
    close = json.loads(data)
    require((close['taskId'], close['runId'], close['batch'], close['planId'], close['operation']) ==
            (TASK, RUN, BATCH, PLAN, LAST_OPERATION) and close['parent']['commandId'] == LAST_PARENT and
            close['parent']['exitCode'] == close['exitCode'] == 1 and close['status'] == 'BLOCKED' and
            close['remaining'] == close['errors'] == [] and close['protectedSame'] is True and
            set(close['closed']) == set(close['starts']) == NATIVE_STOPS.keys() | API_STOPS.keys(), 'WINDOW_LAST_CLOSE_SCOPE')
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
    for role, (stop_id, state_id, *commands) in NATIVE_STOPS.items():
        stop = json.loads(read(area.parent / c.RECOVERY / ('stop-' + stop_id + '.json')))
        state = json.loads(output(c.RECOVERY, state_id, 'omq-recovery-stopped-state'))
        for cid in commands:
            output(c.RECOVERY, cid)
        record = close['closed'][role]
        require(stop['role'] == role and stop['operation'] == LAST_OPERATION and stop['group'] == 'replacement'
                and {key: stop[key] for key in record} == record and
                all(state[key] == value for key, value in record['after'].items()) and
                state['Status'] == 'exited' and state['Pid'] == 0 and not state['OOMKilled'] and
                utc(state['StartedAt']) < utc(state['FinishedAt']), 'WINDOW_LAST_NATIVE')
        normalized['ids'][role] = record['id']
        normalized['data'][role] = {**record, 'startedAt': state['StartedAt']}
    for role, (term, exited, removed, absent) in API_STOPS.items():
        cid = close['closed'][role]
        output(RUN, term, 'resume-api-term')
        require(output(RUN, exited, 'resume-api-exit').strip() in (b'exited 0 false', b'exited 143 false') and
                output(RUN, removed, 'resume-remove-stateless').decode().strip() == cid and
                not output(RUN, absent, 'resume-absent').strip() and cid == close['starts'][role]['id'], 'WINDOW_LAST_API')
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
    require(inventories[0] == inventories[1] and len(members) == 91 and
            ex.sha(ex.encoded(dict(sorted(members.items())))) == '851145a646d08cba58c378d845c21003adb63461faabf2e8dc4bb131693f555c',
            'WINDOW_LAST_RESOURCE_ORIGINALS')
    return normalized


def published_graphs(cid, started, pid, basis, refs=None, archive=None, *, close_sha=CLOSE_SHA):
    import workflow_execution as ex
    import workflow_oracle_mapping_continuity as c
    import workflow_oracle_mapping_evidence as e
    from workflow_oracle_mapping_resume import recovery as r
    require(cid == c.FUSEKI and pid > 0, 'WINDOW_GRAPH_ROLE')
    if close_sha == LAST_CLOSE:
        closed = last_close(ROOT, archive)['data']['fuseki']
    else:
        require(close_sha == CLOSE_SHA and (started, pid) == ('2026-11-21T11:53:49.540115255Z', 87804), 'WINDOW_GRAPH_GENERATION')
        close_bytes = c.raw(ROOT, c.AREA / BATCH / CLOSE_FILE, archive)
        require(ex.sha(close_bytes) == CLOSE_SHA, 'WINDOW_CLOSE_ORIGINAL')
        closed = json.loads(close_bytes)['data']['fuseki']
    require(closed['id'] == cid and closed['after']['FinishedAt'] == basis['finishedAt'] and
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
        require(proof is None or proof.get('closeSha256') == LAST_CLOSE, 'WINDOW_CONTINUITY_PROOF')
        data = c.raw(root, c.AREA / ('formal-run-s2-s3-oracle-' + LAST_PARENT + '.json'), archive)
        require(ex.sha(data) == 'a5184fbf9752205389cf5bd12548b40b154186f0920689fb33286c5ec9e3c487', 'WINDOW_LAST_PARENT')
        prior = json.loads(data)
        middle = prior['host']
        ref = prior['stageInputs']['qualifiedPrefix']
        observation = c.raw(root, c.AREA / BATCH / ref['file'], archive)
        require(ex.sha(observation) == ref['sha256'], 'WINDOW_LAST_PREFIX')
        prior_obs = json.loads(observation)
        require(e.stable_host(prior_obs['host']) == e.stable_host(middle) and
                prior_obs['hostContinuity']['closeSha256'] == CLOSE_SHA, 'WINDOW_LAST_HOST')
        runtime_continuity(root, previous, prior_obs['host'], prior_obs['hostContinuity'], archive)
        close = last_close(root, archive)
        return compare_generation(root, middle, current, close, LAST_CLOSE, proof, archive)
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
    require(digest == CLOSE_SHA or builds[0] == builds[1], 'WINDOW_LAST_BUILDS')
    require(close['ids']=={k:v['containerId'] for k,v in rows[0].items()},'WINDOW_PRIOR_ROLES')
    # 此处只消除已核的进程代次差异，再复用原像、挂载、网络、API快照比较器。
    normalized = [copy.deepcopy(host) for host in (middle,current)]
    normalized_rows = copy.deepcopy(rows)
    for role, old in rows[0].items():
        new=rows[1][role]
        if role in ('api','api-secondary'):
            require(close['apis'][role]['id']==old['containerId'] and new['containerId']!=old['containerId'] and
                    (digest == CLOSE_SHA or e.utc(close['data']['platform-pg']['after']['FinishedAt']) < e.utc(new['startedAt'])), 'WINDOW_API_REPLACED')
            continue
        stop=close['data'][role]
        require(old['pid'] > 0 and new['pid'] > 0 and stop.get('startedAt', old['startedAt']) == old['startedAt'], 'WINDOW_PRIOR_PROCESS')
        require(old['containerId']==new['containerId']==stop['id'] and
                e.utc(old['startedAt']) < e.utc(stop['after']['FinishedAt']) < e.utc(new['startedAt']), 'WINDOW_RESTART_ORDER')
        for field in ('pid','startedAt'):
            normalized_rows[1][role][field]=old[field]
            if role!='oracle':
                normalized[1]['services'][role][field]=old[field]
    refresh.compare_hosts(root,*normalized,*normalized_rows,builds)
    value=dict(status='CURRENT_RUNTIME_GENERATION',closeSha256=digest,oldHost=middle['commandId'],
               host=current['commandId'], builds=builds[1], stoppedRoles=sorted(close['ids']))
    require(proof is None or proof==value,'WINDOW_CONTINUITY_PROOF')
    return value
