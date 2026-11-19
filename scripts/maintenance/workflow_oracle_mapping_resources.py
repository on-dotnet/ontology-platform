"""Oracle Mapping 的创建前资源观测，所有命令沿现有执行与失败保护。"""
import datetime as dt
import json
import re
import shutil
import socket
import uuid

from workflow_execution import ordinary, run, sha

TASK = 'G4-ORACLE-MAPPING-QUERY-001'
RUN = 'implementation-01'
GIB = 1 << 30
SOURCE = 'container-registry.oracle.com/database/free@sha256:844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8'
PROBE = 'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
INVENTORY_SHA = '2fda67495da82c7270e16f034efcb246a2fbd226f3dfb647076acea7f987e4c9'
KEEP_FORMAT = '{{.Id}}|{{.Name}}|{{.State.Status}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{.Image}}|{{range .Mounts}}{{.Type}}:{{if eq .Type "volume"}}{{.Name}}{{end}}:{{.Destination}} {{end}}|{{json .NetworkSettings.Ports}}'


def require(ok, code):
    if not ok:
        raise ValueError('ORACLE_ADMISSION_' + code)


def before_source(root, task, source_id=None, *, platform_stage=False, phase=None, running_roles=(), planned_roles=None):
    """创建前及运行时核对当前准入；运行时只容许已记录的准确源 ID。"""
    require(task == TASK, 'TASK')
    area = ordinary(root/'artifacts/workflow'/task)
    stage_run='s0-recovery-01' if phase else RUN
    require(not phase or (platform_stage and source_id is None), 'RECOVERY_STAGE')
    stamp = uuid.uuid4().hex
    record = dict(taskId=task, runId=stage_run, resourceRunId=RUN, phase=phase, attempt=stamp, status='STARTED', commands=[],
                  startedUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    path = area/stage_run/('source-admission-' + stamp + '.json')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def command(stage, argv, cleanup=False):
        result = run(argv, root, task=task, run_id=stage_run, stage='oracle-admission-' + stage,
                     timeout=18, diagnostic=True, cleanup=cleanup)
        record['commands'].append(dict(stage=stage, commandId=result.receipt['commandId'],
                                       exitCode=result.returncode, stdout=result.receipt['stdout'], stderr=result.receipt['stderr']))
        require(result.returncode == 0, stage)
        return result.stdout.decode().strip()

    def docker(stage, *args, cleanup=False):
        return command(stage, ['docker', '--context', 'desktop-linux', *args], cleanup)

    try:
        original = ordinary(area/'resource-inventory.json').read_bytes()
        require(sha(original) == INVENTORY_SHA, 'P0_INVENTORY')
        expected = json.loads(original)['retained']
        keep = [row.split('|') for row in expected]
        require(command('context', ['docker', 'context', 'show']) == 'desktop-linux', 'CONTEXT')
        current = docker('old-resources', 'inspect', '-f', KEEP_FORMAT, *[row[0] for row in keep]).splitlines()
        require(current == expected, 'RETAINED_DRIFT')
        running = [row for row in keep if row[2] == 'running']
        accounted = {r[0] for r in running}
        if source_id is not None:
            created = json.loads(ordinary(area/RUN/'source-create-01.json').read_bytes())
            require(created['taskId'] == task and created['runId'] == RUN, 'SOURCE_OWNER')
            volume = created['volume']
            if source_id != created['containerId']:
                replacement = json.loads(ordinary(area/RUN/'recovery-01-resume.json').read_bytes())
                require(replacement['taskId'] == task and replacement['runId'] == RUN and replacement['originalId'] == created['containerId']
                        and replacement['replacementId'] == source_id and replacement['status'] == 'NATIVE_RESTORED_PENDING_DRIVER', 'REPLACEMENT_OWNER')
                require(docker('offline-original', 'inspect', '-f', '{{.State.Status}}', created['containerId']) == 'exited', 'RECOVERY_OVERLAP')
                volume = replacement['replacementVolume']
            row = docker('warm-source','inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{range .Mounts}}{{.Name}}{{end}}',source_id).split('|')
            require(row == [source_id, SOURCE.split('@')[1], task, RUN, str(4*GIB), '2000000000', volume], 'SOURCE_DRIFT')
            accounted.add(source_id)
        platform_memory = 0
        held_ports = set()
        if phase:
            from workflow_oracle_mapping_platform_recovery import phase_inventory
            known,platform_memory,platform_cpu,held_ports,replacement=phase_inventory(area/RUN,phase,running_roles,docker)
            accounted.update(known)
            from workflow_oracle_mapping_platform import QUOTAS
            from workflow_oracle_mapping_platform_recovery import ORIGINAL_IDS
            upcoming=set(running_roles if planned_roles is None else planned_roles)
            require(upcoming<=set(ORIGINAL_IDS) and (phase!='closed' or not upcoming),'PLANNED_ROLE')
            pending_roles=upcoming-set(running_roles)
            next_memory=platform_memory+sum((4096 if n=='oracle' else QUOTAS[n][0])*1024**2 for n in pending_roles)
            next_cpu=platform_cpu+sum(int((2 if n=='oracle' else QUOTAS[n][1])*1e9) for n in pending_roles)
            record['projectedWithHelper']={'memory':4*GIB+next_memory,'nanoCpus':4_500_000_000+next_cpu}
            record['expectedRunningRoles']=sorted(running_roles)
            record['activeQuota']={'memory':int(3.5*GIB)+platform_memory,'nanoCpus':4_000_000_000+platform_cpu}
        elif platform_stage:
            from workflow_oracle_mapping_platform import verify_owned_platform
            known, platform_memory, held_ports = verify_owned_platform(area/RUN, docker)
            accounted.update(known)
        require(set(docker('all-running', 'ps', '-q', '--no-trunc').splitlines()) == accounted, 'RUNNING_DRIFT')
        require(len(running) == 3 and len(keep) == 20 and sum(int(r[3]) for r in running) == 7*GIB//2
                and sum(int(r[4]) for r in running) == 4_000_000_000, 'RETAINED_QUOTAS')
        record['protectedOriginalSha256'] = INVENTORY_SHA
        total, cpu, os_name, arch = docker('capacity', 'info', '-f', '{{.MemTotal}} {{.NCPU}} {{.OSType}} {{.Architecture}}').split()
        require(os_name == 'linux' and arch == 'aarch64' and int(total) >= 11*GIB and int(cpu) >= 8, 'VM_CAPACITY')
        stats = command('host-ram', ['vm_stat'])
        page = int(re.search(r'page size of (\d+) bytes', stats)[1])
        counts = {k: int(n) for k,n in re.findall(r'^Pages (free|inactive):\s+(\d+)\.', stats, re.M)}
        require(len(counts) == 2, 'HOST_OBSERVATION')
        host = dict(availableEstimate=page*sum(counts.values()), estimate='free + inactive pages',
                    diskBytes=shutil.disk_usage(root).free, pressure=command('pressure',['memory_pressure','-Q']),
                    swap=command('swap',['sysctl','-n','vm.swapusage']))
        record['host'] = host
        require(host['availableEstimate'] >= 4*GIB and host['diskBytes'] >= 14*GIB, 'HOST_FLOOR')
        available_ports = []
        for port in range(15741, 15748):
            with socket.socket() as sock:
                try:
                    sock.bind(('127.0.0.1', port))
                except OSError:
                    continue
                available_ports.append(port)
        frozen = json.loads((area/RUN/'source-create-01.json').read_bytes())['portMap'] if source_id or phase else None
        if frozen:
            require(set(frozen.values()) <= set(available_ports) | held_ports, 'FROZEN_PORT_COLLISION')
            record['portMap'] = frozen
        else:
            require(len(available_ports) >= 4, 'PORTS')
            record['portMap'] = dict(zip(('api','secondary','oidc','web'),available_ports[:4],strict=True))
        facts = []
        for kind, image in (('source', SOURCE),('probe', PROBE)):
            raw = docker(kind+'-image', 'image','inspect','-f','{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}|{{json .RepoDigests}}', image)
            ident, platform, arch, size, layers, digests = raw.split('|')
            require(ident == image.split('@')[1] and image in json.loads(digests) and (platform,arch) == ('linux','arm64'), 'IMAGE_ID')
            facts.append(dict(ref=image,id=ident,bytes=int(size),layers=json.loads(layers)))
        require(facts[0]['bytes'] <= 13*GIB and not set(facts[0]['layers']) & set(facts[1]['layers']), 'SOURCE_LAYER_BUDGET')
        record['sourceStageImages'] = facts
        # 三份 5 GiB 源数据分别对应原卷、冷备和替代恢复，准备缓存与日志另计。
        planned = dict(images=sum(r['bytes'] for r in facts), original=5*GIB, backup=5*GIB,
                       replacement=5*GIB, preparedAndBuild=4*GIB, logsAndEvidence=GIB)
        require(sum(planned.values()) <= 40*GIB, 'DISK_ENVELOPE')
        record['sourceStageDiskPlanBytes'] = planned
        require(docker('probe-volume-declaration','image','inspect','-f','{{json (index .Config "Volumes")}}',PROBE) in ('{}','null'), 'ANONYMOUS_VOLUME')
        if phase:
            from workflow_oracle_mapping_platform import disk_admission
            record['platformDisk']=disk_admission(root,area/RUN,command,phase=phase,replacement=replacement)
            require(record['projectedWithHelper']['memory']<=int(12.25*GIB)
                    and record['projectedWithHelper']['nanoCpus']<=9_500_000_000
                    and int(total)>=record['projectedWithHelper']['memory']+3*GIB
                    and int(cpu)*1_000_000_000>=record['projectedWithHelper']['nanoCpus']+1_500_000_000,'RECOVERY_CAPS')
        cid = docker('probe-create','create','--pull=never','--network=none','--read-only','--cap-drop=ALL',
                     '--security-opt=no-new-privileges','--user=65534:65534','--memory=64m','--memory-swap=64m',
                     '--cpus=.25','--pids-limit=16','--label','ontology.task='+task,'--label','ontology.run='+RUN,
                     '--label','ontology.attempt='+stamp,'--entrypoint=/bin/sh',PROBE,'-ec','cat /proc/meminfo /proc/loadavg; df -Pk /')
        require(re.fullmatch('[0-9a-f]{64}',cid), 'PROBE_ID')
        record['probeId'] = cid
        def state(label):
            row = docker(label,'inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{len .Mounts}} {{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid).split()
            require(row[:4] == [cid,facts[1]['id'],stamp,'0'], 'PROBE_IDENTITY')
            return row[4:]
        try:
            require(state('probe-before')[0] == 'created','PROBE_PRESTATE')
            raw = docker('probe-start','start','-a',cid)
            require(state('probe-exit') == ['exited','0','false'],'PROBE_EXIT')
        finally:
            require(state('probe-before-release')[0] in ('created','exited'), 'PROBE_RELEASE_STATE')
            docker('probe-remove','rm',cid,cleanup=True)
            require(not docker('probe-after','ps','-aq','--no-trunc','--filter','id='+cid,cleanup=True),'PROBE_REAPPEARED')
            record['probeRemoved'] = True
        vm = dict(total=int(total), cpus=int(cpu), available=int(re.search(r'^MemAvailable:\s+(\d+) kB',raw,re.M)[1])*1024,
                  availableFs=int(raw.splitlines()[-1].split()[-3])*1024,
                  load=next(line for line in raw.splitlines() if re.match(r'^\d+\.\d+ \d+\.\d+',line)))
        record['vm'] = vm
        if phase:
            require(vm['available']>=3*GIB+record['projectedWithHelper']['memory']-record['activeQuota']['memory'],'PROJECTED_VM_FLOOR')
        require(vm['available'] >= (7 if source_id or phase else 15)*GIB//2 and vm['availableFs'] >= 26*GIB, 'VM_FLOOR')
        if platform_stage and not phase:
            from workflow_oracle_mapping_platform import disk_admission
            require(source_id == created['containerId'] and int(total) >= 16.75*GIB and int(cpu) >= 12, 'FORMAL_PEAK_CAPS')
            # 已在运行的硬配额已计入当前可用量，另扣尚未启动的已授权服务与一次探针。
            pending = max(0, int(13.75*GIB) - int(7.5*GIB) - platform_memory)
            require(vm['available'] >= 3*GIB + pending, 'FORMAL_VM_HEADROOM')
            record['platformDisk'] = disk_admission(root,area/RUN,command)
        record['status'] = 'FORMAL_RESOURCE_READY' if platform_stage else 'SOURCE_STAGE_RESOURCE_READY'
        return record
    except Exception as error:
        record.update(status='BLOCKED',reason=str(error))
        raise
    finally:
        record['endedUtc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with path.open('x') as output:
            json.dump(record, output, indent=2)
            output.write('\n')
