"""从任务实际 Docker 上下文核算阶段峰值，用不启动 BE 的只读进程核验 VM 前提。"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import uuid

import workflow_execution as execution


ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-DORIS-MAPPING-QUERY-001'
RUN = 'implementation-01'
# 资源 Owner 在整个复审期保留原标签；命令与可变回执写入新运行目录。
EVIDENCE_RUN = os.environ.get('G4_DORIS_EVIDENCE_RUN', RUN)
if EVIDENCE_RUN not in (RUN, 'review-fix-01'):
    raise ValueError('DMQ_EVIDENCE_RUN')
OUTPUT = ROOT / 'artifacts/workflow' / TASK / EVIDENCE_RUN
GIB = 1 << 30
IMAGES = {'fe': 'apache/doris@sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02',
          'be': 'apache/doris@sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7'}
PORTS = [19030, *range(15641, 15648)]


def demand(value, reason):
    if not value:
        raise ValueError(reason)


def host(*args):
    return subprocess.check_output(args, timeout=8, text=True).strip()


def collect():
    stamp = uuid.uuid4().hex
    path = OUTPUT / ('vm-admission-' + stamp + '.json')
    facts = {'taskId': TASK, 'runId': RUN, 'attempt': stamp, 'context': 'desktop-linux',
             'observedAtUtc': dt.datetime.now(dt.timezone.utc).isoformat(), 'sourceTests': 'NOT_RUN'}
    def persist():
        partial = path.with_suffix('.pending')
        partial.write_text(json.dumps(facts, indent=2) + '\n')
        partial.replace(path)
    def docker(stage, *args, cleanup=False):
        result = execution.run(['docker', '--context', 'desktop-linux', *args], ROOT, task=TASK, run_id=RUN,
                               stage='doris-vm-' + stage, timeout=15, diagnostic=True, cleanup=cleanup)
        demand(result.returncode == 0, 'ENGINE_' + stage.upper().replace('-', '_'))
        return result.stdout.decode().strip()
    try:
        total, cpu, current = map(int, docker('info', 'info', '-f', '{{.MemTotal}} {{.NCPU}} {{.ContainersRunning}}').split())
        older = json.loads((ROOT/'docs/evidence'/TASK/RUN/'r0-review.json').read_text())['reviewedResources']
        ids = [r['containerId'] for r in older]
        fmt = '{{.Id}} {{.Image}} {{.State.Status}}'
        observed = [line.split() for line in docker('old-state','inspect','-f',fmt,*ids).splitlines()]
        demand(len(ids) == 14 and observed == [[r['containerId'],r['imageId'],'exited'] for r in older], 'OLD_STACK_DRIFT')
        live = docker('live','ps','--no-trunc','-q').splitlines()
        demand(current == len(live), 'LIVE_DRIFT')
        limits = {}
        for cid in live:
            quota = int(docker('quota','inspect','-f','{{.HostConfig.Memory}}',cid))
            demand(quota > 0, 'UNBOUNDED_OTHER_CONTAINER')
            limits[cid] = quota
        other = sum(limits.values())
        facts.update(vm={'bytes':total,'cpu':cpu,'otherRunningCaps':limits},oldOriginalsExited=ids)
        # 编译与业务互斥。SQL驱动在宿主；检查内核的 64 MiB 短进程在 FE/BE 创建前退出。
        phases = {}
        for name, memory, cores, host_bytes in [('kernelProbe',64 << 20,.25,256 << 20),
                ('S0_FE_BE',10*GIB,4,1*GIB),('S1_S3_services',int(14.25*GIB),9,int(5.5*GIB))]:
            phases[name] = {'taskCapBytes': memory, 'taskCpuQuota': cores, 'hostStageBudgetBytes': host_bytes,
                            'vmHeadroomBytes': total-other-memory, 'vmAfterTwoGiBReserveBytes': total-other-memory-2*GIB}
        facts['phaseEnvelope'] = phases
        physical, physical_cpu, logical_cpu = [int(host('sysctl','-n',key)) for key in ('hw.memsize','hw.physicalcpu','hw.logicalcpu')]
        pressure = host('memory_pressure','-Q')
        swap = host('sysctl','-n','vm.swapusage')
        free_percent = int(re.search(r'free percentage:\s*(\d+)%',pressure).group(1))
        swap_used = float(re.search(r'used\s*=\s*([\d.]+)M',swap).group(1))
        avail = shutil.disk_usage(ROOT).free
        facts['host'] = dict(physicalBytes=physical,physicalCpu=physical_cpu,logicalCpu=logical_cpu,
                             memoryPressureFreePercent=free_percent,swapUsedMiB=swap_used,diskAvailableBytes=avail,
                             nominalRemainderAfter20GiBVMAndPeak=physical-20*GIB-int(5.5*GIB))
        demand(phases['kernelProbe']['vmAfterTwoGiBReserveBytes'] >= 0 and cpu >= 1 and avail >= 12*GIB, 'PROBE_CAPACITY')
        facts['portsAvailableAtProbe'] = {}
        for port in PORTS:
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1',port))
                    facts['portsAvailableAtProbe'][port] = True
                except OSError:
                    facts['portsAvailableAtProbe'][port] = False
        facts['images'] = {}
        for name, ref in IMAGES.items():
            fmt = '{{.Id}} {{.Architecture}} {{.Os}} {{json .RepoDigests}} {{json (index .Config "Volumes")}}'
            ident, arch, system, refs, volumes = docker('image-'+name,'image','inspect','-f',fmt,ref).split()
            demand(arch == 'arm64' and system == 'linux' and ref in json.loads(refs) and not json.loads(volumes), 'IMAGE_IDENTITY')
            facts['images'][name] = {'id':ident,'ref':ref,'os':system,'arch':arch}
        labels = ['--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+stamp]
        # 不挂卷、不映射宿主端口，仅读取新 VM 内核；使用与服务相同的 nofile 上限。
        cmd = 'cat /proc/sys/vm/max_map_count; wc -l < /proc/swaps; ulimit -Sn; ulimit -Hn'
        cid = docker('create','create','--pull=never','--network=none','--read-only','--cap-drop=ALL',
                     '--security-opt=no-new-privileges','--user=65534:65534','--restart=no','--memory=64m',
                     '--memory-swap=64m','--cpus=.25','--pids-limit=16','--ulimit','nofile=65536:65536',
                     *labels,'--entrypoint=/bin/sh',IMAGES['be'],'-ec',cmd)
        demand(re.fullmatch('[0-9a-f]{64}',cid),'PROBE_ID')
        facts['kernelProbeId'] = cid
        persist()
        def identity():
            fmt = '{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{.State.Status}} {{len .Mounts}}'
            observed = docker('identity','inspect','-f',fmt,cid).split()
            demand(observed[:3] == [cid,facts['images']['be']['id'],stamp] and observed[4]=='0', 'PROBE_OWNERSHIP')
            return observed[3]
        try:
            demand(identity() == 'created','PROBE_BEFORE')
            output = docker('read-kernel','start','-a',cid)
            demand(identity() == 'exited' and docker('exit','inspect','-f','{{.State.ExitCode}} {{.State.OOMKilled}}',cid)
                   == '0 false','PROBE_EXIT')
            count, swap_lines, soft, hard = map(int,output.split())
            facts['kernel'] = {'maxMapCount':count,'swapDeviceCount':swap_lines-1,'nofileSoft':soft,'nofileHard':hard}
        finally:
            demand(identity() in ('created','exited'),'PROBE_STILL_RUNNING')
            docker('remove','rm',cid,cleanup=True)
            demand(not docker('postremove','ps','-aq','--no-trunc','--filter','id='+cid),'PROBE_REAPPEARED')
            facts['kernelProbeRemoved'] = True
        checks = {'vmCapacity': phases['S0_FE_BE']['vmAfterTwoGiBReserveBytes'] >= 0 and cpu >= 4,
                  'fixedSourcePort':facts['portsAvailableAtProbe'][19030], 'mapCount': count >= 2000000,
                  'swapDisabled':swap_lines==1,'nofile':min(soft,hard)>=60000}
        facts['s0Checks'] = checks
        facts['status'] = 'KERNEL_AND_VM_READY' if all(checks.values()) else 'BLOCKED'
    except BaseException as error:
        facts.update(status='ERROR', reason=str(error) if isinstance(error,ValueError) else type(error).__name__)
        raise
    finally:
        persist()
        print(path.relative_to(ROOT),facts['status'] if 'status' in facts else 'INCOMPLETE',flush=True)
    return facts


if __name__ == '__main__':
    result = collect()
    print(json.dumps({key:result[key] for key in ('vm','phaseEnvelope','host','portsAvailableAtProbe','kernel','s0Checks')}))
    raise SystemExit(0 if result['status']=='KERNEL_AND_VM_READY' else 2)
