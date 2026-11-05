#!/usr/bin/env python3
"""直接消费者与实际Compose配置的统一拒绝边界；不启动资源。"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import runtime as rt


def check_compose(m, config, group):
    """核对Compose实际展开后的项目、标签、网络、卷、绑定、镜像和预算。"""
    rt.require(config['name'] == 'ontology-g4-main-' + m['runId'], 'COMPOSE_PROJECT')
    services = config['services']
    rt.require(0 < len(services) <= 6, 'CONTAINER_BUDGET')
    rt.require(sum(int(s['mem_limit']) for s in services.values()) <= 6*1024**3, 'MEMORY_BUDGET')
    images = set(m['images'].values())
    binds = [rt.ROOT / 'apps/web', rt.ROOT / 'node_modules', rt.ROOT / 'backend',
             rt.private_dir(m['runId']), rt.ARTIFACTS / m['runId'] / 'helpers']
    for name, s in services.items():
        if name in ('api','api-recovery'):rt.require(s.get('init') is True,'API_INIT_REQUIRED')
        rt.require(s.get('image') in images and s.get('platform') == 'linux/arm64' and s.get('pull_policy') == 'never', 'COMPOSE_IMAGE')
        rt.require('build' not in s and not s.get('privileged') and not s.get('devices') and not s.get('gpus'), 'COMPOSE_PRIVILEGE')
        rt.require(not s.get('deploy',{}).get('resources',{}).get('reservations',{}).get('devices'),'GPU_REFUSED')
        allowed_caps = {'CHOWN','SETUID','SETGID','DAC_OVERRIDE','FOWNER'} if name in ('platform-pg','pg-source') else set()
        rt.require(set(s.get('cap_add',[])) <= allowed_caps,'EXTRA_CAPABILITY')
        rt.require('no-new-privileges:true' in s.get('security_opt',[]) and 0<int(s.get('pids_limit',0))<=256,'PROCESS_SECURITY')
        rt.require(set(s.get('networks',{})) <= set(config.get('networks',{})),'UNDECLARED_NETWORK')
        rt.require(bool(s.get('networks')) or s.get('network_mode')=='service:api','IMPLICIT_DEFAULT_NETWORK')
        for tmpfs in s.get('tmpfs',[]):
            size=re.search(r'(?:^|,)size=(\d+)([kmg])(?:,|$)',tmpfs.split(':',1)[-1])
            rt.require(size and int(size[1])*{'k':1024,'m':1024**2,'g':1024**3}[size[2]]<=64*1024**2,'TMPFS_BUDGET')
        rt.require(s.get('read_only') and 'ALL' in s.get('cap_drop', []), 'COMPOSE_SECURITY')
        rt.require(s.get('network_mode') in (None, 'service:api'), 'COMPOSE_NETWORK_MODE')
        labels = s.get('labels', {})
        rt.require(labels.get('ontology.task-id') == rt.TASK and labels.get('ontology.run-id') == m['runId'], 'COMPOSE_LABEL')
        for port in s.get('ports', []):
            rt.require(port.get('host_ip') == '127.0.0.1', 'LOOPBACK_ONLY')
        for mount in s.get('volumes', []):
            rt.require(mount['type'] in ('bind', 'volume'), 'MOUNT_TYPE')
            if mount['type'] == 'bind':
                p = Path(mount['source'])
                rt.require(any(p == b or p.is_relative_to(b) for b in binds), 'BIND_ALLOWLIST')
                rt.boundary(p, rt.ROOT)
                rt.require(mount.get('read_only') is True, 'BIND_WRITABLE')
            else:
                rt.require(mount['source'] in config.get('volumes', {}), 'UNREGISTERED_VOLUME')
    for name, network in config.get('networks', {}).items():
        rt.require(network.get('internal') is True and not network.get('external'), 'NETWORK_ISOLATION')
        rt.require(network['labels'].get('ontology.task-id') == rt.TASK and network['labels'].get('ontology.run-id') == m['runId'], 'NETWORK_LABEL')
    volume_bytes=0
    for name, volume in config.get('volumes', {}).items():
        rt.require(not volume.get('external') and volume['driver'] == 'local', 'VOLUME_EXTERNAL')
        rt.require(volume['driver_opts'].get('type') == 'tmpfs' and volume['driver_opts'].get('device')=='tmpfs', 'VOLUME_PERSISTENCE')
        size=re.search(r'(?:^|,)size=(\d+)m(?:,|$)',volume['driver_opts'].get('o',''))
        limit=1024 if group=='g3' and name=='fuseki-data' else 512
        rt.require(size and 0<int(size[1])<=limit,'VOLUME_CAPACITY')
        if limit==1024:
            rt.require('fuseki' in services and int(services['fuseki']['mem_limit'])>=2*1024**3,'FUSEKI_MEMORY_CAPACITY')
            consumers=[(service,mount.get('target')) for service,entry in services.items() for mount in entry.get('volumes',[]) if mount.get('type')=='volume' and mount.get('source')==name]
            rt.require(consumers==[('fuseki','/fuseki')],'FUSEKI_VOLUME_CONSUMER')
        volume_bytes+=int(size[1])*1024**2
        rt.require(volume['labels'].get('ontology.task-id') == rt.TASK and volume['labels'].get('ontology.run-id') == m['runId'], 'VOLUME_LABEL')
        rt.require(volume['name'] == config['name'] + '_' + name, 'VOLUME_NAME')
    rt.require(volume_bytes<=3*1024**3,'TOTAL_VOLUME_CAPACITY')
    return {'services': len(services), 'memoryBytes': sum(int(s['mem_limit']) for s in services.values()), 'group': group}


def check_runtime(m, path, evidence=None):
    """直接调用消费者也必须验证同一Run/T/清单；先验证后读取秘密。"""
    expected = rt.private_dir(m['runId']) / 'runtime.json'
    rt.require(Path(path) == expected, 'EXACT_RUNTIME')
    rt.boundary(expected.parent, expected.parent, exists=True, private=True)
    r = rt.runtime_value(m)
    for service in ('platform-pg','api','web','keycloak-test'):
        rt.require(service in r.get('containerIds',{}),'RUNTIME_RESOURCE_MISSING')
        rt.require(rt.inspect_owned(m,r['containerIds'][service],service)['State']['Running'],'RUNTIME_RESOURCE_DOWN')
    for key in ('realmFile', 'sourceSecretFile', 'certificatePath'):
        if key in r:
            rt.boundary(r[key], expected.parent, exists=True, private=True)
    if evidence is not None:
        target = rt.boundary(evidence, rt.ARTIFACTS / m['runId'])
        rt.require(target != rt.ARTIFACTS / m['runId'] and not target.exists(), 'EXISTING_OR_ROOT_OUTPUT')
    return r


def check_all(m):
    """真实config而非正则检查标签；不创建容器和卷。"""
    rows = []
    for group,profile in (('m1',None),('m1','pg-test'),('m1','lease'),('g3',None)):
        command = rt.compose_command(group) + (['--profile',profile] if profile else []) + ['config', '--format', 'json']
        p = subprocess.run(command, env=rt.compose_environment(m), capture_output=True, timeout=30)
        rt.require(p.returncode == 0, 'COMPOSE_CONFIG')
        config = json.loads(p.stdout)
        row=check_compose(m,config,group);row['profile']=profile;rows.append(row)
    return rows


def main():
    """统一CLI先完成所有拒绝检查再允许消费者启动。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--resource-manifest', required=True)
    parser.add_argument('--runtime-file')
    parser.add_argument('--evidence-dir')
    parser.add_argument('--consumer', choices=('http', 'browser', 'fault', 'g3-compatibility'))
    args = parser.parse_args()
    m = rt.load_manifest(args.resource_manifest, args.run_id, args.expected_head)
    if args.consumer:
        rt.require(args.evidence_dir is not None,'OUTPUT_REQUIRED')
        rt.verify_engine(m)
        rt.check_build(m)
        rt.require(args.runtime_file is not None, 'RUNTIME_REQUIRED')
        r = check_runtime(m, args.runtime_file, args.evidence_dir)
        if args.consumer == 'g3-compatibility':
            rt.require(re.fullmatch('[a-f0-9]{64}', r.get('rustfsContainerId', '')), 'RUSTFS_ID')
            rt.inspect_owned(m, r['rustfsContainerId'], 'rustfs')
        print(json.dumps({'status': 'CONSUMER_BOUNDARY_VERIFIED', 'taskId': rt.TASK, 'runId': args.run_id}))
    else:
        rt.verify_engine(m)
        print(json.dumps({'status': 'CONFIG_BOUNDARY_VERIFIED', 'groups': check_all(m)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print('REFUSED_CONSUMER_BOUNDARY', file=sys.stderr)
        raise SystemExit(2)
