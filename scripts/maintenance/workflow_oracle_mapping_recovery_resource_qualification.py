"""重开三个已选组件窗口的准入、准确宿主和服务 inspect；不连接 Docker 或访问私有挂载。"""

import json
import re
from datetime import datetime
from pathlib import Path

from workflow_execution import encoded, sha
from workflow_oracle_mapping_platform import IMAGES, QUOTAS
from workflow_oracle_mapping_resources import INVENTORY_SHA, KEEP_FORMAT, PROBE, RUN, TASK

BATCH = 's0-recovery-02'
BASE = '454d1a2f17581673cbbf44900a5fe241d603f5ef'
ROOT = Path('/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform')
ALT = 'ontology-g4-omq-restore-01'
REF_VOLUME = 'ontology-g4-omq-recovery-02_rustfs-reference'
API = ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
PRIVATE = ROOT / '.tools/security/g4-oracle-mapping-query-001' / RUN / 's0-recovery-01/restored-host/platform'
DOCKER = ['docker', '--context', 'desktop-linux']
NET_FMT = '{{.Id}}|{{.Name}}|{{.Internal}}|{{index .Labels "ontology.attempt"}}'
VOL_FMT = '{{.Driver}}|{{json .Options}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}|{{index .Labels "com.docker.compose.project"}}'
REF_VOL_FMT = '{{.Name}}|{{.Driver}}|{{json .Options}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}|{{index .Labels "ontology.attempt"}}'
SERVICE_FMT = '{{.Id}}|{{.Image}}|{{.State.Status}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}|{{json .HostConfig.PortBindings}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{json .NetworkSettings.Networks}}'
EXTRA_FMT = '{{.Id}}|{{.State.Status}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "ontology.attempt"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}|{{json .HostConfig.PortBindings}}|{{json .NetworkSettings.Networks}}|{{.HostConfig.ReadonlyRootfs}}'
# 冻结准入原件，也限制可从原命令目录发布的 ID；先识别临近读取的当次窗口。
ADMISSIONS = {
    'actual': ('7a3553fcd49c4326809f502ac4c37bfb', '81ba8565b0e50cf9904b5475fc92601a56bde283f7f70b2845278d3df11a7867'),
    'reference': ('7165f9862e684a4da188eb6dbf37a81d', 'f2468b11fccb9752b487ef3134567ea0efd13696e50223814fab18423dfabe3f'),
    'identity': ('fabda336482d4dbc949c94e4db2b9169', '556a6b1ac791e8995228278f5ae2cd77f4b7b26b54c764984dceb93b967e714d'),
}
SERVICES = {'actual': ('rustfs',), 'reference': ('objects-reference',), 'identity': ('platform-pg', 'keycloak-test')}
HOSTS = {'actual': 'objects-reader', 'reference': 'objects-reader', 'identity': 'identity-host'}
ENGINE_POLICY = 'eb21a6e92a3e5dc732d6ff957f184ef9f1236b6291de7ee6adf950399c450fd1'
RETAINED_STDOUT = '9dd8045b6cc2036e83e450cbe8e7ec1040b2857ac0fcfa580c8ffa1804cf5cee'


def require(value, code):
    if not value:
        raise ValueError('COMPONENT_RESOURCE_' + code)


def admission_name(kind):
    return 'source-admission-' + ADMISSIONS[kind][0] + '.json'


def selected_rows(kind, admission):
    require(sha(encoded(admission)) == ADMISSIONS[kind][1], 'ADMISSION_DIGEST')
    wanted = {'context', 'old-resources', 'component-network', 'component-' + HOSTS[kind], 'all-running', 'capacity'}
    wanted.update(('component-' if role == 'objects-reference' else 'phase-replacement-') + role for role in SERVICES[kind])
    if kind == 'reference':
        wanted.add('component-volume')
    commands = admission['commands']
    rows = {}
    network_index = 0
    for index, item in enumerate(commands):
        stage = item['stage']
        if stage not in wanted:
            continue
        key = stage
        if stage == 'component-network':
            key += '-' + ('platform-internal', 'host-entry')[network_index]
            network_index += 1
        require(key not in rows, 'DUPLICATE_STAGE')
        rows[key] = item
        if stage.startswith('phase-replacement-'):
            volume = commands[index + 1]
            require(volume['stage'] == 'phase-volume', 'VOLUME_STAGE')
            rows[stage + '-volume'] = volume
    require(network_index == 2 and wanted == {r['stage'] for r in rows.values()} - {'phase-volume'}, 'SELECTED_STAGES')
    return rows


def selected_commands(kind, admission):
    """返回需要 publish 的命令 ID。每个 ID 只选 receipt.json、stdout.txt、stderr.txt。"""
    return [row['commandId'] for row in selected_rows(kind, admission).values()]


def mount_rows(raw):
    result = []
    for mount in json.loads(raw):
        kind = mount['Type']
        require(kind in ('volume', 'bind'), 'MOUNT_TYPE')
        source = mount['Name'] if kind == 'volume' else mount['Source'].removeprefix('/host_mnt')
        result.append([kind, source, mount['Destination'], mount['RW']])
    return sorted(result)


def expected_mounts(role, volume, driver):
    def bind(source, destination):
        return ['bind', str(source), destination, False]

    if role in ('rustfs', 'objects-reference'):
        return sorted([['volume', volume, '/data', True]] + [bind(PRIVATE / n, '/run/secrets/' + n) for n in ('s3-access', 's3-secret')])
    if role == 'keycloak-test':
        return sorted([['volume', volume, '/opt/keycloak/data', True], bind(PRIVATE / 'keycloak-password', '/run/secrets/keycloak-password')])
    if role == 'platform-pg':
        return sorted([['volume', volume, '/var/lib/postgresql', True], bind(PRIVATE / 'postgres', '/run/secrets')])
    build = driver['driver']
    subtree = Path('artifacts/workflow') / TASK / BATCH
    kind = 'identity' if role == 'identity-host' else 'objects'
    directory = Path(build['buildDir'])
    require(directory.parent == subtree and re.fullmatch('build-' + kind + '-[a-f0-9]{32}', directory.name), 'BUILD_MOUNT')
    mounts = [bind(ROOT / directory, '/driver'), bind(API, '/app'), bind(PRIVATE / 'api/appsettings.json', '/private/api/appsettings.json')]
    if role == 'identity-host':
        mounts.extend(bind(PRIVATE / 'api' / n, '/private/api/' + n) for n in ('keyring.pfx', 'platform-ca.crt'))
        mounts.append(bind(PRIVATE / 'keyring', '/keyring'))
    return sorted(mounts)


def validate(kind, row, driver, *, frozen, record_bytes, command_bytes):
    """以相邻资源窗口与正式 start 的时序重开本批准确绑定，只消费已登记的元数据命令输出。"""
    raw = record_bytes(admission_name(kind))
    admission = json.loads(raw)
    indexed = selected_rows(kind, admission)
    attempt = ADMISSIONS[kind][0]
    phase = 'objects' if kind == 'actual' else kind
    host = HOSTS[kind]
    active = set(SERVICES[kind])
    if kind == 'identity':
        active.add(host)
    require((admission['taskId'], admission['runId'], admission['resourceRunId'], admission['phase'], admission['attempt'], admission['status'])
            == (TASK, BATCH, RUN, phase, attempt, 'FORMAL_RESOURCE_READY') and set(admission['expectedRunningRoles']) == active
            and admission['protectedOriginalSha256'] == INVENTORY_SHA and admission['probeRemoved'] is True, 'WINDOW')
    begin, end = (datetime.fromisoformat(admission[k]) for k in ('startedUtc','endedUtc'))

    def read(key, args):
        info = indexed[key]
        cid = info['commandId']
        cmd = json.loads(command_bytes(cid, 'receipt.json'))
        argv_hash = sha(encoded(args))
        expected_identity = sha(encoded([cmd['inputFingerprint'], cmd['environmentFingerprint'], argv_hash, str(ROOT), 18, ENGINE_POLICY]))
        require(cmd['taskId'] == TASK and cmd['runId'] == BATCH and cmd['commandId'] == cid and cmd['stage'] == 'oracle-admission-' + info['stage']
                and cmd['schemaVersion'] == 2 and cmd['started'] is True and cmd['exitCode'] == info['exitCode'] == 0 and cmd['signal'] is None
                and cmd['classification'] == 'SUCCESS' and cmd['cwd'] == str(ROOT) and cmd['deadlineSeconds'] == 18 and cmd['identity'] == expected_identity
                and cmd['commandSummary'] == dict(executable=args[0], argumentCount=len(args)-1, sha256=argv_hash)
                and begin <= datetime.fromisoformat(cmd['startedAtUtc']) <= datetime.fromisoformat(cmd['endedAtUtc']) <= end, 'INSPECT_COMMAND')
        parts = []
        for name in ('stdout', 'stderr'):
            data = command_bytes(cid, name + '.txt')
            path = ROOT / 'artifacts/workflow' / TASK / 'commands' / BATCH / cid / (name + '.txt')
            require(cmd[name] == info[name] == dict(path=str(path),sizeBytes=len(data),sha256=sha(data)), 'INSPECT_STREAM')
            parts.append(data)
        require(not parts[1], 'INSPECT_STDERR')
        return parts[0].decode().strip()

    require(read('context',['docker','context','show']) == 'desktop-linux', 'CONTEXT')
    # 已冻准入中记录的哈希先限制原件，再以原件的 20 个准确 ID 重算 inspect 命令。
    registry = indexed['old-resources']
    old_bytes = command_bytes(registry['commandId'], 'stdout.txt')
    require(sha(old_bytes) == RETAINED_STDOUT, 'RETAINED_BYTES')
    old = [line.split('|') for line in old_bytes.decode().splitlines()]
    read('old-resources', DOCKER + ['inspect','-f',KEEP_FORMAT] + [fields[0] for fields in old])
    running = {fields[0] for fields in old if fields[2] == 'running'}
    require(len(old) == 20 and len(running) == 3, 'RETAINED_COUNT')
    ids = {}
    memory = sum(int(v[3]) for v in old if v[0] in running)
    cpu = sum(int(v[4]) for v in old if v[0] in running)
    repl = frozen('replacement-resources.json')
    require(repl['project'] == ALT and repl['taskId'] == TASK and repl['runId'] == RUN, 'REPLACEMENT')
    for name in ('platform-internal', 'host-entry'):
        network_id = repl['networks'][name]
        obs = read('component-network-' + name, DOCKER + ['network','inspect','-f',NET_FMT,network_id]).split('|')
        require(obs == [network_id, ALT + '_' + name, str(name == 'platform-internal').lower(), repl['attempt']], 'NETWORK')
    require(row['taskId'] == TASK and row['runId'] == BATCH and row['base'] == BASE and row['attempt'] == driver['attempt']
            and row['driver'] == driver['driver'] and driver['role'] == host and row['resourceRun'] == RUN, 'OPERATION')
    if kind == 'identity':
        require(row['admission'] == attempt and row['pg'] == repl['ids']['platform-pg'] and row['idp'] == repl['ids']['keycloak-test']
                and row['id'] == driver['id'], 'IDENTITY_IDS')
    else:
        require(row['role'] == kind and row['verifier'] == driver['id'], 'READER_ID')
    ref = json.loads(record_bytes('reference-created.json')) if kind == 'reference' else None
    for role in (*SERVICES[kind], host):
        service = role != host
        new = role in ('objects-reference',host)
        cid = (ref['id'] if role == 'objects-reference' else repl['ids'][role]) if service else driver['id']
        stage = ('component-' if new else 'phase-replacement-') + role
        obs = read(stage, DOCKER + ['inspect','-f',EXTRA_FMT if new else SERVICE_FMT,cid]).split('|')
        volume = (REF_VOLUME if role == 'objects-reference' else repl['volumes'][role]) if service else None
        image = (IMAGES['rustfs'] if role == 'objects-reference' else IMAGES[role]) if service else PROBE.split('@')[1]
        if service and kind != 'identity':
            require(row['serviceId'] == cid and row['volume'] == volume, 'OBJECT_DESTINATION')
        ram, cores = (QUOTAS['rustfs'] if role == 'objects-reference' else QUOTAS[role]) if service else ((768,.5) if kind == 'identity' else (512,.5))
        mem, nanos = int(ram * 1024**2), int(cores * 1e9)
        state = 'running' if role in active else 'created'
        if new:
            nonce = ref['attempt'] if service else driver['attempt']
            require(obs[:8] == [cid,state,image,TASK,BATCH,nonce,str(mem),str(nanos)] and obs[11] == 'true', 'EXTRA_IDENTITY')
            mounts, ports, networks = obs[8:11]
        else:
            require(obs[:7] == [cid,image,state,TASK,RUN,str(mem),str(nanos)] and obs[9:11] == [ALT,role], 'SERVICE_IDENTITY')
            mounts, ports, networks = obs[7],obs[8],obs[11]
        expected = expected_mounts(role, volume, driver)
        require(mount_rows(mounts) == expected, 'MOUNTS')
        if not service:
            require(sorted(driver['mounts']) == expected, 'DRIVER_MOUNTS')
        if role == 'objects-reference':
            fields = read('component-volume',DOCKER + ['volume','inspect','-f',REF_VOL_FMT,volume]).split('|')
            require(fields[:2] == [volume,'local'] and not json.loads(fields[2]) and fields[3:] == [TASK,BATCH,ref['attempt']]
                    and sorted(ref['mounts']) == expected, 'REFERENCE_VOLUME')
        elif service:
            fields = read(stage + '-volume',DOCKER + ['volume','inspect','-f',VOL_FMT,volume]).split('|')
            require(fields[0] == 'local' and not json.loads(fields[1]) and fields[2:] == [TASK,RUN,ALT], 'REPLACEMENT_VOLUME')
        port = {'identity-host':'15741','keycloak-test':'15743'}.get(role)
        require((json.loads(ports) or {}) == ({'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':port}]} if port else {}), 'PORTS')
        observed_nets = json.loads(networks)
        names = ['platform-internal'] + (['host-entry'] if port else [])
        require(set(observed_nets) == {ALT + '_' + n for n in names}, 'NETWORK_SET')
        for n in names:
            observed = observed_nets[ALT+'_'+n]
            require(observed['NetworkID'] == (repl['networks'][n] if state == 'running' else ''), 'NETWORK_ID')
            if service:
                alias = 'rustfs' if role == 'objects-reference' else role
                require(alias in (observed['Aliases'] or ()), 'SERVICE_ALIAS')
        ids[role] = cid
        if state == 'running':
            running.add(cid)
            memory += mem
            cpu += nanos
    observed_running = read('all-running',DOCKER + ['ps','-q','--no-trunc']).splitlines()
    require(len(observed_running) == len(running) and set(observed_running) == running, 'ALL_RUNNING')
    total, cpus, system, arch = read('capacity',DOCKER+['info','-f','{{.MemTotal}} {{.NCPU}} {{.OSType}} {{.Architecture}}']).split()
    vm = admission['vm']
    require((vm['total'],vm['cpus'],system,arch) == (int(total),int(cpus),'linux','aarch64'), 'CAPACITY')
    require(admission['activeQuota'] == dict(memory=memory,nanoCpus=cpu), 'ACTIVE_QUOTA')
    mem_increment = 512 * 1024**2 if kind == 'identity' else 1024**3
    cpu_increment = 500_000_000 if kind == 'identity' else 1_000_000_000
    projected_mem, projected_cpu = memory + mem_increment, cpu + cpu_increment
    require(admission['projectedWithHelper'] == dict(memory=projected_mem,nanoCpus=projected_cpu)
            and projected_mem + 3 * 1024**3 <= vm['total'] and projected_cpu + 1_500_000_000 <= vm['cpus'] * 10**9
            and vm['available'] >= mem_increment + 3 * 1024**3, 'HEADROOM')
    operation = json.loads(command_bytes(row['commandId'],'receipt.json'))
    argv = DOCKER + (['start',driver['id']] if kind == 'identity' else ['start','-a','-i',driver['id']])
    require(operation['taskId'] == TASK and operation['runId'] == BATCH and operation['commandId'] == row['commandId']
            and operation['commandSummary']['sha256'] == sha(encoded(argv)) and operation['exitCode'] == 0
            and operation['stage'] == ('dedicated-auth-start' if kind == 'identity' else 'rustfs-inventory-' + kind), 'OPERATION_COMMAND')
    if kind == 'identity':
        require(datetime.fromisoformat(operation['endedAtUtc']) <= begin, 'HOST_START_ORDER')
    else:
        require(end <= datetime.fromisoformat(operation['startedAtUtc']), 'READER_START_ORDER')
    return dict(admission=attempt, admissionSha256=sha(raw), phase=phase, ids=ids, runningIds=sorted(running),
                hostStateAtInspection='running' if kind == 'identity' else 'created', activeQuota=admission['activeQuota'],
                projectedWithHelper=admission['projectedWithHelper'], commandIds=selected_commands(kind,admission))
