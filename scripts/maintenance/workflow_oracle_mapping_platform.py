"""Oracle 最小正式根使用现有 M4 配方、持久卷与固定目标 relay，各服务绑定本任务。"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import time
import urllib.request

import canonical_fuseki
import workflow_execution as ex
import workflow_m2_build as build
import workflow_m4_query_runtime as snapshots
from workflow_doris_fixture import private
from workflow_oracle_mapping_resources import TASK, RUN, GIB, SOURCE, PROBE, before_source, require

ROOT=Path(__file__).resolve().parents[2]
AREA=ROOT/'artifacts/workflow'/TASK/RUN
HOME_DIR=ROOT/'.tools/security/g4-oracle-mapping-query-001'/RUN
RUNTIME=HOME_DIR/'platform'
PG=RUNTIME/'postgres'
PROJECT='ontology-g4-omq-platform-01'
MEASURE_TREE=Path('/private/tmp/omq-implementation-01-measure-7d113e3c')
COMPOSE=AREA/'formal-compose.json'
OWNERS=AREA/'formal-resources.json'
PORTS={'api':15741,'secondary':15742,'oidc':15743,'web':15744}
QUOTAS={'platform-pg':(768,.5),'keycloak-test':(1024,1),'fuseki':(2048,1),'rustfs':(512,.5),'api':(768,.5),'api-secondary':(768,.5)}
VOLUMES={'platform-pg':'platform-data','keycloak-test':'keycloak-data','fuseki':'fuseki-data','rustfs':'rustfs-data'}
IMAGES={'platform-pg':'sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437',
        'keycloak-test':'sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4',
        'fuseki':'sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c',
        'rustfs':'sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b',
        'api':PROBE.split('@')[1],'api-secondary':PROBE.split('@')[1]}


def save(path,data,replace=False):
    temp=path.with_suffix('.pending')
    if path.exists() and not replace:raise ValueError('FORMAL_ORIGINAL_EXISTS')
    with temp.open('x') as f:
        json.dump(data,f,indent=2);f.write('\n')
    temp.replace(path)


def verify_owned_platform(area,docker):
    """只用本次创建回执逐 ID 确认准确配额、镜像、标记及端口；未知活动仍由总入口拒绝。"""
    path=area/'formal-resources.json'
    if not path.exists():return set(),0,set()
    record=json.loads(path.read_bytes())
    require((record['taskId'],record['runId'])==(TASK,RUN),'PLATFORM_RECORD')
    running=set();memory=0;ports=set()
    for name,cid in record['ids'].items():
        require(name in QUOTAS and re.fullmatch('[0-9a-f]{64}',cid),'PLATFORM_ID')
        fields=docker('admitted-'+name,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{.State.Status}}|{{json .HostConfig.PortBindings}}',cid).split('|')
        ram,cores=QUOTAS[name]
        require(fields[:7]==[cid,IMAGES[name],TASK,RUN,name,str(ram*1024**2),str(int(cores*1e9))],'PLATFORM_DRIFT_'+name)
        allowed={'keycloak-test':('8080/tcp',PORTS['oidc']),'api':('8080/tcp',PORTS['api']),'api-secondary':('8080/tcp',PORTS['secondary'])}.get(name)
        expected={} if not allowed else {allowed[0]:[{'HostIp':'127.0.0.1','HostPort':str(allowed[1])}]}
        require((json.loads(fields[8]) or {})==expected,'PLATFORM_PORT_'+name)
        if fields[7]=='running':
            running.add(cid);memory+=ram*1024**2
            if allowed:ports.add(allowed[1])
    return running,memory,ports


def current_storage(area, replacement=None):
    """只回传已登记的准确容器可写字节及卷大小。读取本机引擎元数据，不挂载卷。"""
    import http.client
    import socket
    import subprocess
    endpoint=subprocess.check_output(['docker','context','inspect','desktop-linux','--format','{{.Endpoints.docker.Host}}'],timeout=4).decode().strip()
    require(endpoint.startswith('unix://'),'ENGINE_CONTEXT')
    def get(path):
        conn=http.client.HTTPConnection('localhost',timeout=8)
        sock=socket.socket(socket.AF_UNIX);sock.settimeout(8);sock.connect(endpoint[7:]);conn.sock=sock
        try:
            conn.request('GET','/v1.52/'+path)
            response=conn.getresponse()
            require(response.status==200,'ENGINE_SIZE')
            return json.load(response)
        finally:conn.close()
    old=json.loads((area/'formal-current-storage-01.json').read_bytes())
    volumes=set(old['volumesLogicalBytes']);ids=set(old['containerWritableBytes'])
    services={}
    path=area/'formal-resources.json'
    if path.exists():
        owned=json.loads(path.read_bytes())
        services=owned['volumes']
        volumes.update(services.values())
        ids.update(owned['ids'].values());ids.update(owned.get('archivedApiIds',{}).values())
    replacement_services = {}
    if replacement:
        replacement_services = replacement['volumes']
        volumes.update(replacement_services.values())
        ids.update(replacement['ids'].values())
    extra_ids = set((replacement or {}).get('extraIds',{}).values())
    extra_volumes = (replacement or {}).get('extraVolumes',{})
    ids.update(extra_ids);volumes.update(extra_volumes.values())
    all_volumes=get('system/df?type=volume')['Volumes']
    if replacement is not None:
        from urllib.parse import urlencode
        require({v['Name'] for v in all_volumes if (v.get('Labels') or {}).get('ontology.task')==TASK}==volumes,'UNACCOUNTED_TASK_VOLUME')
        query=urlencode({'all':'1','filters':json.dumps({'label':['ontology.task='+TASK]})})
        require({v['Id'] for v in get('containers/json?'+query)}==ids,'UNACCOUNTED_TASK_CONTAINER')
    sizes={v['Name']:v['UsageData']['Size'] for v in all_volumes if v['Name'] in volumes}
    require(set(sizes)==volumes and all(type(x)==int and x>=0 for x in sizes.values()),'VOLUME_SIZE_MISSING')
    layer_sizes={}
    for cid in sorted(ids):
        require(re.fullmatch('[a-f0-9]{64}',cid),'STORAGE_CID')
        val=get('containers/'+cid+'/json?size=1')
        require(val['Id']==cid and val['Config']['Labels'].get('ontology.task')==TASK and val['Config']['Labels'].get('ontology.run')==(replacement.get('extraRun','s0-recovery-02') if cid in extra_ids else RUN),'SIZE_OWNER')
        require(type(val['SizeRw']) is int and val['SizeRw'] >= 0, 'CONTAINER_SIZE_MISSING')
        layer_sizes[cid]=val['SizeRw']
    return dict(volumesLogicalBytes={k:sizes[k] for k in old['volumesLogicalBytes']},containerWritableBytes=layer_sizes,
                platformVolumes={k:sizes[v] for k,v in services.items()},
                replacementVolumes={k:sizes[v] for k,v in replacement_services.items()},
                componentVolumes={k:sizes[v] for k,v in extra_volumes.items()},componentLayers={k:layer_sizes[k] for k in sorted(extra_ids)})


def backup_allocation(root, area, group):
    """只从任务私有固定目录抵扣同一个未来副本。未完成文件占用留在主机实际量内。"""
    import stat
    private = root/'.tools/security/g4-oracle-mapping-query-001'/RUN/'s0-recovery-01'
    approved = {'source': ('database.tar', 'trust-and-auth.tar'), 'platform': tuple(n+'.tar' for n in VOLUMES)}
    require(group in approved, 'ARCHIVE_CLASS')
    directory = private/group
    if not directory.exists():
        return 0
    require(directory.resolve() == directory and directory.is_dir() and directory.stat().st_uid==os.getuid()
            and not directory.stat().st_mode & 0o077, 'ARCHIVE_OWNER')
    ledger_path=area.parent/'s0-recovery-01/archive-ledger.json'
    ledger=json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {}
    if ledger:
        require((ledger.get('taskId'),ledger.get('operation'))==(TASK,'s0-recovery-01'), 'ARCHIVE_LEDGER_ID')
    credited = 0
    for name in approved[group]:
        path = directory/name
        if not path.exists() and not path.is_symlink():
            continue
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
                and not info.st_mode & 0o077, 'ARCHIVE_IDENTITY')
        entry=ledger.get('archives',{}).get(group+'/'+name)
        if entry is None:
            continue
        from workflow_oracle_mapping_platform_recovery import ORIGINAL_IDS
        role='oracle' if group=='source' else name.removesuffix('.tar')
        require(entry['sourceId']==ORIGINAL_IDS[role] and entry['privatePath']==str(path.relative_to(private))
                and entry['identity']==[info.st_dev,info.st_ino,info.st_size,info.st_ctime_ns]
                and re.fullmatch('[a-f0-9]{64}',entry['sha256']), 'ARCHIVE_LEDGER_OWNER')
        credited += info.st_blocks*512
    return credited


def disk_admission(root,area,command,*,phase=None,replacement=None):
    """统计所有当期工作树、镜像及三份源数据，替代恢复的原盘、备份和副本同时保留。"""
    layer=json.loads((area/'platform-image-layer-closure-01.json').read_bytes())
    require(layer['taskId']==TASK and len(layer['imageSizes'])==6 and len(layer['sharedEmptyLayers'])==3,'IMAGE_CLOSURE')
    # 只有两个相同压缩空层共享；其余已证有界的保守镜像总量全部计费。
    images=layer['deduplicatedImageUpperBytes']
    require(images==sum(layer['imageSizes'])-layer['duplicateCompressedBytes'],'IMAGE_BYTES')
    rec=json.loads((area/'recovery-01.json').read_bytes());reopened=json.loads((area/'recovery-01-final.json').read_bytes())
    require(reopened['status']=='EARLY_SOURCE_RECOVERY_PASS','EARLY_RECOVERY')
    source=rec['allocatedSourceBytes'];host_dirs=[root,MEASURE_TREE]
    all_trees=command('formal-worktrees',['git','worktree','list','--porcelain'])
    for block in all_trees.split('\n\n'):
        lines=block.splitlines()
        if any(line in ['branch refs/heads/codex/omq-source-bindings','branch refs/heads/codex/omq-deadline-store'] for line in lines) or Path(lines[0].removeprefix('worktree ')).parent.name in ('omq-source-bindings','omq-deadline-store'):
            host_dirs.append(Path(lines[0].removeprefix('worktree ')))
    if phase == 'product-resume-01':
        host_dirs.extend(p for p in (Path('/private/tmp/omq-product-resume-observer'), Path('/private/tmp/omq-product-resume-measure-4924')) if p.is_dir())
    host_roots=[p for p in host_dirs if p.is_dir()]
    measurements=[line.split(None,1) for line in command('formal-host-bytes',['du','-sk',*[str(p) for p in host_roots]]).splitlines()]
    require([row[1] for row in measurements]==[str(p) for p in host_roots], 'HOST_MEASUREMENT_SET')
    host=sum(int(row[0])*1024 for row in measurements)
    # 初次完整准入的主机字节已经包含首份备份。之后的构建消费已登记的增长余量。
    initial_record=area/'formal-planned.json'
    host_start=host
    require(not phase or initial_record.is_file(), 'RECOVERY_BASELINE_MISSING')
    if initial_record.exists():
        attempt=json.loads(initial_record.read_bytes())['resourceAttempt']
        previous=json.loads((area/('source-admission-'+attempt+'.json')).read_bytes())['platformDisk']
        host_start=previous['allocations']['currentHostIncludingFirstBackup']
    released=area/'early-checkout-release-01.json'
    if released.exists():
        reduced=json.loads(released.read_bytes())
        require(reduced['checkout']==str(host_dirs[1]) and reduced['beforeBytes']-reduced['afterBytes']==reduced['releasedBytes'],'SPARSE_BASIS')
        host_start-=reduced['releasedBytes']
    # 保留两个卷、两次冷备和已验证的替代卷。最终恢复只写已复核可重建的本任务替代卷。
    usage = current_storage(area, replacement) if phase else current_storage(area)
    basis = json.loads((area/'formal-platform-size-basis.json').read_bytes())
    source_caps = {key: int(4.25*GIB) for key in usage['volumesLogicalBytes']}
    require(len(source_caps)==2 and source<=min(source_caps.values()) and all(
        type(size) is int and size>=0 and (phase or size<=source_caps[name]) for name,size in usage['volumesLogicalBytes'].items()),'OBSERVED_SOURCE_SIZE')
    # 两份同构历史样本各含四项服务数据；另外以三份平台 PG 中的最大值计费。
    samples=[row['bytes'] for row in basis['sourceRawVolumeFacts']]
    require(len(samples)==8 and len(basis['pgVolumeMetadataOnly'])==3,'PLATFORM_SIZE_BASIS')
    sample=max(sum(samples[:4]),sum(samples[4:]))+max(basis['pgVolumeMetadataOnly'].values())
    platform_copy=3*GIB//4
    require(sample*1.5<=platform_copy and sum(usage['platformVolumes'].values())<=platform_copy,'PLATFORM_SAMPLE_GROWTH')
    reserved={'images':images,'sourceAndReplacement':sum(source_caps.values()),
              'containerLayers':sum(usage['containerWritableBytes'].values()),'currentHostIncludingFirstBackup':host,
              'secondColdSourceCopy':int(4.25*GIB),'platformOriginalFirstBackupFinalBackupAndReplacement':platform_copy*4,
              'boundedContainerLogs':16*20*1024**2,'boundedProbeAndStreamingTemporary':64*1024**2,
              'newBuildEvidenceAndLogs':max(64*1024**2,host_start+int(.75*GIB)-host)}
    if phase:
        from workflow_oracle_mapping_recovery_components import BATCH, PHASES
        require(phase in ('preserve','restore','closed','product-resume-01') or phase in PHASES, 'RECOVERY_PHASE')
        require(len(set(host_dirs))==len(host_dirs) and all(p.is_dir() for p in host_dirs), 'RECOVERY_HOST_MEASUREMENT')
        sizes = usage['volumesLogicalBytes']
        original = json.loads((area/'source-create-01.json').read_bytes())['volume']
        require(original in sizes and set(usage['platformVolumes'])==set(VOLUMES), 'RECOVERY_VOLUME_ID')
        # 两个 Oracle 卷均保留。当前原卷大小及归档头部/增长余量同时约束还原卷与新冷备。
        source_limit = max(int(4.25*GIB), sizes[original]+64*1024**2)
        reserved['sourceAndReplacement'] = sum(max(size,source_limit) for size in sizes.values())
        source_credited = backup_allocation(root,area,'source')
        platform_credited = backup_allocation(root,area,'platform')
        require(source_credited+platform_credited<=host, 'ARCHIVES_OUTSIDE_HOST_MEASUREMENT')
        reserved['secondColdSourceCopy'] = max(0,source_limit-source_credited)
        # 原卷、当前检查点和替代卷各有一项。备份实际落盘量已在 host 当中。
        del reserved['platformOriginalFirstBackupFinalBackupAndReplacement']
        reserved['platformOriginal'] = platform_copy
        reserved['platformCheckpointRemaining'] = max(0,platform_copy-platform_credited)
        reserved['platformReplacement'] = max(platform_copy,sum(usage['replacementVolumes'].values()))
        reserved['newBuildEvidenceAndLogs'] = max(64*1024**2,host_start+int(.75*GIB)-(host-source_credited-platform_credited))
        source_caps = {name:max(source_limit,size) for name,size in sizes.items()}
    component_budget=None
    if phase and phase in PHASES:
        start=json.loads((area.parent/BATCH/'disk-start.json').read_bytes())
        require(start['limitIncrement']==64*1024**2 and start['diskPaths']==[str(p) for p in host_dirs],'COMPONENT_DISK_BASIS')
        # 宿主与各容器可写层已经计入原账本，只增加准确参考卷实耗和本批尚未消费的预留。
        base_host=min(start['hostBytes'],start['previousHostBytes'])
        growth=max(0,host-base_host);reference=sum(usage['componentVolumes'].values());layers=sum(usage['componentLayers'].values())
        used=growth+reference+layers
        require(used<=start['limitIncrement'],'COMPONENT_64M_LIMIT_'+str(used))
        remaining=start['limitIncrement']-used
        component_budget=dict(hostGrowth=growth,referenceVolume=reference,componentLayers=layers,used=used,remaining=remaining,limit=start['limitIncrement'])
        reserved['componentReferenceActual']=reference
        transfer=min(remaining,reserved['newBuildEvidenceAndLogs'])
        reserved['newBuildEvidenceAndLogs']-=transfer
        reserved['componentGrowthRemaining']=remaining
    total=sum(reserved.values())
    require(total<=40*GIB,'FORMAL_TOTAL_DISK_'+str(total))
    return dict(allocations=reserved,componentBudget=component_budget,totalBytes=total,ceilingBytes=40*GIB,hostPaths=[str(p) for p in host_dirs],
                representativePlatformBytes=sample,platformCopyCeiling=platform_copy,
                sourceVolumeCaps=source_caps,initialSourceMeasurement=usage,
                measuredAgainBeforeExpansionOrRestore=True)



def local(stage,args,timeout=60,env=None):
    result=ex.run(args,ROOT,task=TASK,run_id=RUN,stage='omq-platform-'+stage,timeout=timeout,environment=env)
    require(result.returncode==0,stage+'_'+result.receipt['commandId'])
    return result.stdout.decode().strip()


def docker(stage,*args):
    return local(stage,['docker','--context','desktop-linux',*args])


def source_record():
    return json.loads((AREA/'source-create-01.json').read_bytes())


def product_run():
    value=os.environ.get('OMQ_PRODUCT_RUN','')
    require(value in ('','product-resume-01'),'PRODUCT_RUN')
    return value


def active_service_ids():
    if product_run():
        from workflow_oracle_mapping_resume import manifest
        return manifest()['ids']
    return json.loads(OWNERS.read_bytes())['ids']


def active_source_record():
    if product_run():
        from workflow_oracle_mapping_resume import replacement_source
        return replacement_source()
    return source_record()


def admission():
    if product_run():
        from workflow_oracle_mapping_resume import admit
        return admit()
    source=source_record()
    require(source['portMap']==PORTS,'FORMAL_FROZEN_PORTS')
    return before_source(ROOT,TASK,source['containerId'],platform_stage=True)


def render():
    os.umask(0o077)
    resource=admission()
    require(not RUNTIME.exists() and not COMPOSE.exists(),'FORMAL_PRESTATE')
    for directory in (RUNTIME,PG,RUNTIME/'api',RUNTIME/'keyring',RUNTIME/'query-keyring'):
        directory.mkdir(mode=0o700)
    for filename in ['keycloak-password','s3-access','s3-secret']:
        private(RUNTIME/filename,secrets.token_urlsafe(36))
    private(PG/'password',secrets.token_urlsafe(36))
    private(PG/'pg_hba.conf','local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::0/0 scram-sha-256\n')
    private(PG/'certificate.cnf','[req]\ndistinguished_name=dn\nx509_extensions=extensions\nprompt=no\n[dn]\nCN=platform-pg\n[extensions]\nsubjectAltName=DNS:platform-pg\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    local('platform-ca',['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','7','-config',str(PG/'certificate.cnf'),'-keyout',str(PG/'server.key'),'-out',str(PG/'server.crt')])
    private(RUNTIME/'api/g4-key',secrets.token_bytes(32))
    private(RUNTIME/'runtime.json',dict(taskId=TASK,runId=RUN,publicOrigin='http://localhost:15741',
            certificatePath=str(RUNTIME/'api/keyring.pfx'),certificatePassword=secrets.token_urlsafe(40),healthKey=secrets.token_urlsafe(32)))
    local('keyring',['pwsh','-NoProfile','-File','scripts/acceptance/new-wave2-certificate.ps1','-RuntimeFile',str(RUNTIME/'runtime.json')])
    sys.path.insert(0,str(ROOT/'.tools/pythonlibs'))
    import yaml
    template=(ROOT/'experiments/g4-m3-mapping-001/compose.yaml').read_text()
    for old,new in [('${MAPPING_RUN_ID:?explicit run required}',RUN),('${MAPPING_HOST_UID:-501}',str(os.getuid())),
                    ('${MAPPING_HOST_GID:-20}',str(os.getgid())),('${MAPPING_RUNTIME_PRIVATE_DIR:-/not-configured}',str(RUNTIME)),
                    ('${MAPPING_PRIVATE_DIR:?explicit private directory required}',str(PG)),('15680','15743')]:
        template=template.replace(old,new)
    conf=yaml.safe_load(template)
    labels={'ontology.task':TASK,'ontology.run':RUN}
    services={k:conf['services'][k] for k in VOLUMES}
    for name,service in services.items():
        ram,cores=QUOTAS[name]
        service.update(labels=labels,mem_limit=ram*1024**2,memswap_limit=ram*1024**2,cpus=cores,networks=['platform-internal'],
                       logging={'driver':'json-file','options':{'max-size':'10m','max-file':'2'}})
        service.pop('ports',None)
    for name in ('keycloak-test','rustfs'):
        services[name]['user']=str(os.getuid())+':'+str(os.getgid())
    services['keycloak-test'].update(ports=['127.0.0.1:15743:8080'],networks=['platform-internal','host-entry'])
    fuse=canonical_fuseki.identity(ROOT/'infra/development/fuseki','linux/arm64')
    canonical_fuseki.validate_image(canonical_fuseki.inspect_image(fuse),fuse,IMAGES['fuseki'])
    services['fuseki']['image']=fuse['image']
    for name,service in services.items():
        actual=docker('platform-frozen-'+name,'image','inspect','-f','{{.Id}} {{.Os}} {{.Architecture}}',service['image'])
        require(actual==IMAGES[name]+' linux arm64','PLATFORM_IMAGE_'+name)
    spec=dict(name=PROJECT,services=services,volumes={v:dict(driver='local',labels=labels) for v in VOLUMES.values()},
              networks={'platform-internal':dict(internal=True,labels=labels),'host-entry':dict(internal=False,labels=labels)})
    save(COMPOSE,spec)
    save(AREA/'formal-planned.json',dict(taskId=TASK,runId=RUN,resourceAttempt=resource['attempt'],portMap=PORTS,serviceQuotas=QUOTAS,images=IMAGES,volumes=VOLUMES,networkRoles=spec['networks'],composeSha256=ex.sha(COMPOSE.read_bytes()),
                                        retention='Private persistent volumes and keys. Native quiesce, cold copy and alternative restore before release. Source-only early recovery is separately verified.'))
    return {'status':'FORMAL_SPEC_READY','disk':resource['platformDisk']}


def compose(*args):
    return local('compose-'+args[0],['docker','--context','desktop-linux','compose','-p',PROJECT,
                                    '-f',str(COMPOSE),*args],timeout=100)


def create_platform():
    admission()
    plan=json.loads((AREA/'formal-planned.json').read_bytes())
    require(plan['composeSha256']==ex.sha(COMPOSE.read_bytes()) and not OWNERS.exists(),'PLATFORM_PLAN')
    require(not docker('project-prestate','ps','-aq','--filter','label=com.docker.compose.project='+PROJECT),'PROJECT_EXISTS')
    for kind in ('volume','network'):
        require(not any(x.startswith(PROJECT+'_') for x in docker(kind+'-prestate',kind,'ls','--format','{{.Name}}').splitlines()),'NAME_COLLISION')
    record=dict(taskId=TASK,runId=RUN,ids={},volumes={},networks={},state='CREATING')
    save(OWNERS,record)
    try:
        compose('create','--pull','never','--no-build',*VOLUMES)
    finally:
        for name,volume in VOLUMES.items():
            cid=compose('ps','-a','-q',name)
            if not cid:continue
            require(re.fullmatch('[0-9a-f]{64}',cid),'PLATFORM_CREATED_ID')
            mount=json.loads(docker('created-mount-'+name,'inspect','-f','{{json .Mounts}}',cid))
            vols=[r['Name'] for r in mount if r['Type']=='volume']
            require(vols==[PROJECT+'_'+volume],'PLATFORM_MOUNT_'+name)
            record['ids'][name]=cid
            record['volumes'][name]=vols[0]
            save(OWNERS,record,True)
    for name,internal in [('platform-internal','true'),('host-entry','false')]:
        ident,flag,owner=docker('new-network','network','inspect','-f','{{.Id}} {{.Internal}} {{index .Labels "ontology.task"}}',PROJECT+'_'+name).split()
        require(re.fullmatch('[0-9a-f]{64}',ident) and flag==internal and owner==TASK,'NEW_NETWORK')
        record['networks'][name]=ident
    require(set(record['ids'])==set(VOLUMES),'MISSING_SERVICE')
    record['state']='CREATED'
    save(OWNERS,record,True)
    return record


def init_volumes():
    admission()
    record=json.loads(OWNERS.read_bytes())
    require(record['state']=='CREATED','VOLUME_INIT_ORDER')
    args=[]
    for name in ('keycloak-test','fuseki','rustfs'):
        volume=record['volumes'][name]
        require(docker('volume-labels','volume','inspect','-f','{{index .Labels "ontology.task"}} {{index .Labels "ontology.run"}} {{index .Labels "com.docker.compose.project"}}',volume)==TASK+' '+RUN+' '+PROJECT,'VOLUME_OWNER')
        require(docker('stopped-before-volume-init','inspect','-f','{{.State.Status}}',record['ids'][name])=='created','VOLUME_IN_USE')
        args.extend(['--mount','type=volume,src='+volume+',dst=/'+name])
    script='chown '+str(os.getuid())+':'+str(os.getgid())+' /keycloak-test /rustfs && chown 10001:10001 /fuseki && stat -c "%u:%g" /keycloak-test /rustfs /fuseki'
    helper=docker('volume-init-create','create','--pull=never','--network=none','--read-only','--user=0:0','--cap-drop=ALL',
                  '--cap-add=CHOWN','--security-opt=no-new-privileges','--memory=64m','--memory-swap=64m','--cpus=.25','--pids-limit=16',
                  '--label','ontology.task='+TASK,'--label','ontology.run='+RUN,*args,'--entrypoint=/bin/sh',PROBE,'-ec',script)
    require(re.fullmatch('[0-9a-f]{64}',helper),'HELPER_ID')
    record['volumeHelperId']=helper
    save(OWNERS,record,True)
    require(docker('volume-helper-identity','inspect','-f','{{.Image}} {{index .Config.Labels "ontology.task"}} {{len .Mounts}} {{.State.Status}}',helper)==IMAGES['api']+' '+TASK+' 3 created','HELPER_IDENTITY')
    result=docker('volume-helper-execute','start','-a',helper)
    uid=str(os.getuid())+':'+str(os.getgid())
    require(result.splitlines()==[uid,uid,'10001:10001'],'VOLUME_UIDS')
    require(docker('volume-helper-exit','inspect','-f','{{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Status}}',helper)=='0 false exited','HELPER_POST')
    docker('volume-helper-release','rm',helper)
    require(not docker('volume-helper-absent','ps','-aq','--no-trunc','--filter','id='+helper),'HELPER_REAPPEARED')
    record['state']='INITIALIZED';save(OWNERS,record,True)
    return {'status':record['state']}


def start_platform():
    admission()
    rec=json.loads(OWNERS.read_bytes())
    require(rec['state']=='INITIALIZED','START_ORDER')
    compose('start',*VOLUMES)
    ready=False
    for _ in range(38):
        states=[docker('warm-'+name,'inspect','-f','{{.State.Status}} {{.State.OOMKilled}}',cid) for name,cid in rec['ids'].items()]
        require(all(s=='running false' for s in states),'SERVICE_EARLY_EXIT')
        try:
            with urllib.request.urlopen('http://127.0.0.1:15743/realms/master/.well-known/openid-configuration',timeout=1) as resp:
                discovery=json.load(resp)
            require(discovery['issuer']=='http://localhost:15743/realms/master','ISSUER')
            ready=True;break
        except (ConnectionError,ValueError,OSError):
            time.sleep(1)
    require(ready,'OIDC_PREWARM')
    require(docker('platform-pg-health','exec','--user','postgres',rec['ids']['platform-pg'],'psql','-XAt','-d','mapping','-c','select 1')=='1','PLATFORM_PG_NATIVE')
    result=admission()
    rec['state']='RUNNING_BASE';rec['postwarmAttempt']=result['attempt'];save(OWNERS,rec,True)
    return {'status':rec['state'],'attempt':result['attempt']}


def prepare_api():
    require(json.loads(OWNERS.read_bytes())['state']=='RUNNING_BASE','BASE_BEFORE_API')
    admission()
    binding=build.validate('api',TASK)
    rows=[json.loads(line) for line in (AREA.parent/'command-events.jsonl').read_text().splitlines()]
    prepared=json.loads(next((AREA.parent/'environment').glob('*/runs/*/receipt.json')).read_bytes())
    target=build.TARGETS['api']
    prog=[prepared['dotnet'],'build',target,'--no-restore','--disable-build-servers','-m:1','-v:q']
    argv=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*prog]
    matches=[r for r in rows if r.get('exitCode')==0 and r.get('inputFingerprint')==binding['inputKey'] and
             r.get('commandSummary',{}).get('sha256')==ex.sha(ex.encoded(argv))]
    require(bool(matches),'CURRENT_API_BUILD_COMMAND')
    buildcmd=matches[-1]
    helper=AREA/'formal-relay'
    helper.mkdir()
    tree=ast.parse((ROOT/'scripts/maintenance/workflow_m3_mapping.py').read_text())
    src=next(ast.literal_eval(x.value) for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='LOOPBACK_SOURCE' for n in x.targets))
    for old,new in [('15680','15743'),('15603','15745'),('15690','15746'),('15630','15744')]:src=src.replace(old,new)
    (helper/'OracleRelay.cs').write_text(src)
    refs=sorted(Path('/usr/local/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
    require(bool(refs),'RELAY_REFERENCE_PACK')
    local('relay-build',['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',prepared['dotnet'],
          '/usr/local/share/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll','-nologo','-target:exe','-nostdlib+','-out:'+str(helper/'OracleRelay.dll'),
          *['-reference:'+str(p) for p in refs],str(helper/'OracleRelay.cs')],env=prepared['environment'])
    save(helper/'OracleRelay.runtimeconfig.json',{'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}})
    snap=snapshots.freeze(ROOT,ROOT/Path(target).parent/'bin/Debug/net10.0',AREA/'runtime-snapshots',binding,buildcmd['commandId'],
                          {'toolEnvironment':buildcmd['environmentFingerprint']},task=TASK,run_id=RUN)
    identity=json.loads((RUNTIME/'runtime.json').read_bytes())
    env=os.environ.copy()
    env['WAVE2_KEYCLOAK_ADMIN_PASSWORD']=(RUNTIME/'keycloak-password').read_text()
    local('realm',['python3','-B','infra/security/bootstrap-keycloak.py','--profile','g2','--keycloak-origin','http://localhost:15743',
                  '--public-origin',identity['publicOrigin'],'--runtime-output',str(RUNTIME/'realm.json')],timeout=90,env=env)
    realm=json.loads((RUNTIME/'realm.json').read_bytes())
    require(re.fullmatch(r'http://localhost:15743/realms/g2-[0-9a-f]{16}',realm['authority']),'REALM_ORIGIN')
    private(RUNTIME/'api/platform-ca.crt',(PG/'server.crt').read_bytes())
    private(RUNTIME/'api/oracle-ca.pem',(HOME_DIR/'reader/ca.pem').read_bytes())
    cfg={'ConnectionStrings':{'governance':'Host=platform-pg;Database=mapping;Username=postgres;Password='+(PG/'password').read_text()+';SSL Mode=VerifyFull;Root Certificate=/private/api/platform-ca.crt;Timeout=5;Command Timeout=5'},
         'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],'PublicOrigin':identity['publicOrigin'],
                     'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx','CertificatePassword':identity['certificatePassword'],'HealthKey':identity['healthKey']},
         'Web':{'Origin':'http://127.0.0.1:15744'},'G2':{'Enabled':True,'ApplyMigrations':True},'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},
         'G4':{'Enabled':True,'ApplyMigrations':True,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/platform-ca.crt','AllowEmptyPublicSchema':True,
               'Oracle':{'RootCertificatePath':'/private/api/oracle-ca.pem','WalletDirectory':'/private/oracle-wallet'},'Mapping':{'Enabled':True},'QueryEnabled':True,'QueryKeyRingPath':'/query-keyring'},
         'Semantics':{'ValidationOrigin':'http://127.0.0.1:15745/validation','PublishedOrigin':'http://127.0.0.1:15745/ontology'},
         'Publishing':{'S3Endpoint':'http://127.0.0.1:15746','AccessKey':(RUNTIME/'s3-access').read_text(),'SecretKey':(RUNTIME/'s3-secret').read_text(),'Bucket':'g4-oracle-mapping-synthetic'},
         'Logging':{'LogLevel':{'Default':'Warning','OntologyPlatform.Modules.SemanticQuery':'Information'}}}
    private(RUNTIME/'api/appsettings.json',cfg)
    public=json.loads(COMPOSE.read_bytes())
    public['networks']['source-internal']={'external':True,'name':source_record()['network']}
    for name in ('api','api-secondary'):
        ram,cores=QUOTAS[name]
        port=PORTS['api' if name=='api' else 'secondary']
        public['services'][name]=dict(image=PROBE,platform='linux/arm64',pull_policy='never',mem_limit=ram*1024**2,memswap_limit=ram*1024**2,cpus=cores,pids_limit=192,
            init=True,read_only=True,user=str(os.getuid())+':'+str(os.getgid()),security_opt=['no-new-privileges:true'],cap_drop=['ALL'],
            labels={'ontology.task':TASK,'ontology.run':RUN},ports=['127.0.0.1:'+str(port)+':8080'],working_dir='/private/api',
            entrypoint=['/bin/sh','-ec'],command=['dotnet /runtime/OracleRelay.dll &\nproxy=$$!\ntrap \'kill "$$proxy" 2>/dev/null || true\' EXIT\ndotnet /app/OntologyPlatform.Api.dll'],
            environment={'ASPNETCORE_ENVIRONMENT':'Development','ASPNETCORE_URLS':'http://0.0.0.0:8080','DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_EnableDiagnostics':'0'},
            volumes=[str(ROOT/snap['directory'])+':/app:ro',str(RUNTIME/'api')+':/private/api:ro',str(HOME_DIR/'reader/client-wallet')+':/private/oracle-wallet:ro',
                     str(helper)+':/runtime:ro',str(RUNTIME/'keyring')+':/keyring',str(RUNTIME/'query-keyring')+':/query-keyring'],
            tmpfs=['/tmp:size=32m,mode=1777'],networks=['source-internal','platform-internal','host-entry'],logging={'driver':'json-file','options':{'max-size':'10m','max-file':'2'}})
    save(AREA/'formal-api-compose.json',public)
    value=dict(taskId=TASK,runId=RUN,snapshotId=snap['snapshotId'],build=binding,buildCommandId=buildcmd['commandId'],
               relaySha256=ex.sha((helper/'OracleRelay.dll').read_bytes()),composeSha256=ex.sha((AREA/'formal-api-compose.json').read_bytes()))
    save(AREA/'formal-api-inputs.json',value)
    return value


def start_api(name):
    admission()
    rec=json.loads(OWNERS.read_bytes())
    require(name in ('api','api-secondary') and name not in rec['ids'],'API_START_ORDER')
    conf=AREA/'formal-api-compose.json';spec=json.loads((AREA/'formal-api-inputs.json').read_bytes())
    require(ex.sha(conf.read_bytes())==spec['composeSha256'] and build.validate('api',TASK)==spec['build'],'API_IMAGE_PLAN')
    snap=json.loads((AREA/'runtime-snapshots'/(spec['snapshotId']+'.json')).read_bytes())
    snapshots.verify(ROOT,snap,task=TASK,run_id=RUN)
    project=json.loads(conf.read_bytes())['name']
    require(project in (PROJECT,PROJECT+'-api02'),'API_PROJECT')
    prefix=['docker','--context','desktop-linux','compose','-p',project,'-f',str(conf)]
    local('api-create-'+name,[*prefix,'create','--pull','never','--no-build',name])
    cid=local('api-created-'+name,[*prefix,'ps','-aq',name])
    require(re.fullmatch('[0-9a-f]{64}',cid),'NEW_API_ID')
    rec['ids'][name]=cid;save(OWNERS,rec,True)
    mounts=json.loads(docker('api-mount-'+name,'inspect','-f','{{json .Mounts}}',cid))
    snapshots.demand_mount(ROOT,snap,mounts,task=TASK,run_id=RUN)
    verify_owned_platform(AREA,docker)
    docker('api-start-'+name,'start',cid)
    port=PORTS['api' if name=='api' else 'secondary'];health=json.loads((RUNTIME/'runtime.json').read_bytes())['healthKey']
    ready=False
    for _ in range(45):
        try:
            req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/health/ready',headers={'X-Health-Key':health})
            with urllib.request.urlopen(req,timeout=1) as resp:ready=resp.status==200
            if ready:break
        except (OSError,ValueError):pass
        require(docker('api-state-'+name,'inspect','-f','{{.State.Status}} {{.State.OOMKilled}}',cid)=='running false','API_EARLY_EXIT_'+name)
        time.sleep(.4)
    require(ready,'API_HEALTH_'+name)
    post=admission()
    return dict(containerId=cid,status='READY',postwarmAttempt=post['attempt'])


HOST_FORMAT=('{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|'
             '{{.State.Status}}|{{.State.Pid}}|{{.State.StartedAt}}|{{json .Mounts}}|'
             '{{range $key,$net := .NetworkSettings.Networks}}{{$key}}={{$net.NetworkID}} {{end}}')


def runtime_binding():
    if product_run():
        from workflow_oracle_mapping_resume import host_binding
        return host_binding()
    rec=json.loads(OWNERS.read_bytes())
    inp=json.loads((AREA/'formal-api-inputs.json').read_bytes())
    require(build.validate('api',TASK)==inp['build'],'HOST_BUILD')
    snap=json.loads((AREA/'runtime-snapshots'/(inp['snapshotId']+'.json')).read_bytes())
    source=source_record()
    source_net=source['networkId'].split()[0]
    service_order=sorted(rec['ids'])
    argv=['docker','--context','desktop-linux','inspect','-f',HOST_FORMAT,*[rec['ids'][k] for k in service_order],source['containerId']]
    proc=ex.run(argv,ROOT,task=TASK,run_id=RUN,stage='omq-host-inspect',input_key=ex.sha(ex.encoded([inp,rec['ids'],source['containerId'],HOST_FORMAT])),timeout=12)
    require(proc.returncode==0,'HOST_INSPECT')
    lines=proc.stdout.decode().strip().splitlines()
    require(len(lines)==len(service_order)+1,'HOST_CARDINALITY')
    services={}
    for n,line in zip([*service_order,'oracle'],lines,strict=True):
        cid,image,owner,run,status,pid,started,mounts,networks=line.split('|')
        require(owner==TASK and run==RUN and status=='running' and int(pid)>0,'HOST_PROCESS')
        nets=dict(s.split('=') for s in networks.split())
        if n=='oracle':
            require(cid==source['containerId'] and image==SOURCE.split('@')[1] and nets=={source['network']:source_net},'HOST_ORACLE')
            continue
        require(cid==rec['ids'][n] and image==IMAGES[n],'HOST_IMAGE')
        expected={PROJECT+'_platform-internal':rec['networks']['platform-internal']}
        if n in ('api','api-secondary','keycloak-test'):
            expected[PROJECT+'_host-entry']=rec['networks']['host-entry']
        if n in ('api','api-secondary'):
            expected[source['network']]=source_net
            snapshots.demand_mount(ROOT,snap,json.loads(mounts),task=TASK,run_id=RUN)
        require(nets==expected,'HOST_NETWORK_'+n)
        services[n]=dict(containerId=cid,imageId=image,pid=int(pid),startedAt=started,mountSha256=ex.sha(ex.encoded(json.loads(mounts))),networks=nets)
    require(inp['composeSha256']==ex.sha((AREA/'formal-api-compose.json').read_bytes()) and inp['relaySha256']==ex.sha((AREA/'formal-relay/OracleRelay.dll').read_bytes()),'HOST_RUNTIME_INPUTS')
    return dict(taskId=TASK,runId=RUN,ports=PORTS,commandId=proc.receipt['commandId'],snapshotId=inp['snapshotId'],buildInputKey=inp['build']['inputKey'],
                buildOutputKey=inp['build']['outputKey'],runtimeHelperSha256=inp['relaySha256'],composeSha256=inp['composeSha256'],services=services,
                oracle=dict(containerId=source['containerId'],imageId=SOURCE.split('@')[1],networkId=source_net))


def pg_command(sql_bytes,stage):
    require(isinstance(sql_bytes,bytes) and re.fullmatch('[a-z0-9-]+',stage),'PG_INPUT')
    cid=active_service_ids()['platform-pg']
    require(docker('pg-exact-owner','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{.State.Status}}',cid)==cid+' '+TASK+' running','PG_OWNERSHIP')
    args=['docker','--context','desktop-linux','exec','-i','--user','postgres',cid,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    r=ex.run(args,ROOT,task=TASK,run_id=product_run() or RUN,stage='omq-pg-'+stage,stdin=sql_bytes,input_key=ex.sha(sql_bytes),timeout=15)
    require(r.returncode==0,'PG_'+stage+'_'+r.receipt['commandId'])
    return r.stdout.decode().strip(),r.receipt['commandId']


def read_pg(sql_bytes,stage):
    return pg_command(b'BEGIN READ ONLY;\n'+sql_bytes+b'\nCOMMIT;',stage)


def grant_fixture(mode,objects,fields,state):
    from workflow_m4_query import grant_transaction
    require(mode in ('mapping','query') and (state['taskId'],state['runId'])==(TASK,product_run() or RUN) and state['scope']=={'organizationId':'org-demo','siteIds':['site-a']},'GRANT_SCOPE')
    cid=state['connectionId'];cat=state['catalog']
    require(re.fullmatch('[a-f0-9]{32}',cid) and cat['connectionId']==cid and cat['status']=='READY','GRANT_CATALOG')
    cols=['ROW_ID','JOIN_KEY','VAL','ORG_ID','SITE_ID','EXT_ID','LABEL','FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS']
    require(objects==['PRODUCTION/OMQ_ENTITY'] and fields==[objects[0]+'/'+str(i)+'/'+c for i,c in enumerate(cols,1)],'GRANT_FIELDS')
    current,_=read_pg(('SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+cid+'\' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;').encode(),'grant-catalog')
    require(json.loads(current)==cat,'GRANT_CATALOG_CURRENT')
    require(len(cat['objects'])==2 and len(set(state['subjects'].values()))==4,'GRANT_SUBJECTS')
    perms={'operator':['mapping.read','mapping.source.validate','mapping.edit','mapping.validate','mapping.submit'],
           'auditor':['mapping.read','mapping.source.validate','mapping.review','mapping.approve'],
           'activator':['mapping.read','mapping.source.validate','mapping.activate']} if mode=='mapping' else {'reader':['data.query.execute','data.query.result.read','data.query.evidence.read']}
    def key(sub,op):
        if product_run():
            return 'omq-r1-'+ex.sha(ex.encoded([product_run(),cid,sub,op]))[:32]
        return 'omq-s0-'+ex.sha(ex.encoded([cid,sub,op]))[:32]
    for sub in state['subjects'].values():
        require(re.fullmatch('[A-Za-z0-9:_-]{1,120}',sub),'GRANT_SUBJECT')
    pairs=[(state['subjects'][k],v) for k,v in perms.items()]
    sql,ids=grant_transaction(state,objects,fields,pairs,key,product_run() or RUN)
    count,command=pg_command(sql,'grant-'+mode)
    require(count.splitlines()[-1]==str(len(ids)),'GRANT_WRITTEN')
    keys=','.join("'"+i+"'" for i in ids)
    query=f'''SELECT json_agg(g) FROM (SELECT "Id","SubjectId","Permission","ConnectionId","ObjectRefs","FieldRefs","SiteIds","OrganizationId",
       extract(epoch from ("ExpiresAtUtc"-now()))::int ttl,
       (SELECT count(*) FROM governance.audit_records a WHERE a."Resource"="Id" AND a."Action"='mapping.grant.change') audit
       FROM governance."MappingAuthorizationGrants" WHERE "Id" IN ({keys}) AND "RevokedAtUtc" IS NULL) g;'''
    query=query.replace('a."Resource"="Id"','a."Resource"=g0."Id"').replace('governance."MappingAuthorizationGrants" WHERE','governance."MappingAuthorizationGrants" g0 WHERE')
    actual,check=read_pg(query.encode(),'grant-current-'+mode);rows=json.loads(actual)
    require(len(rows)==len(ids),'GRANT_RECEIPTS')
    for r in rows:
        sub=r['SubjectId'];op=r['Permission'];scoped=op=='mapping.source.validate' or op.startswith('data.query.')
        require(r['Id']==key(sub,op) and any(who==sub and op in allowed for who,allowed in pairs) and r['audit']==1 and r['ttl']>0 and
                r['OrganizationId']=='org-demo' and r['SiteIds']==['site-a'] and r['ConnectionId']==(cid if scoped else None) and
                set(r['ObjectRefs'])==set(objects if scoped else []) and set(r['FieldRefs'])==set(fields if scoped else []),'GRANT_READBACK')
    return dict(taskId=TASK,runId=product_run() or RUN,mode=mode,commandId=command,verificationId=check,grantCount=len(rows),fieldCount=len(fields),remainingSeconds=min(r['ttl'] for r in rows),inputsUnchanged=True)


def pause_unused_apis():
    """在正式请求投递前封存旧快照；只有本任务双方平台库完整为空时才能使用此切换。"""
    admission()
    rec=json.loads(OWNERS.read_bytes())
    names=('api','api-secondary')
    require(all(n in rec['ids'] for n in names) and not rec.get('archivedApiIds'),'REBIND_PRESTATE')
    sql=b"""SELECT json_build_array((SELECT count(*) FROM semantic_query."Queries"),(SELECT count(*) FROM agents."Runs"),
      (SELECT count(*) FROM connections."MappingJobs"),(SELECT count(*) FROM connections."MappingOutboxs"),(SELECT count(*) FROM publishing."Outbox"));"""
    before,cmd=read_pg(sql,'pre-business-drain')
    require(json.loads(before)==[0]*5 and not (AREA/'runtime-fixture.json').exists(),'NONEMPTY_FORMAL_ROOT')
    ids={n:rec['ids'][n] for n in names}
    for name,cid in ids.items():
        require(docker('prestop-'+name,'inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{.State.Status}}',cid)==cid+' '+TASK+' running','API_TO_STOP')
        docker('graceful-'+name,'stop','--signal','TERM','--timeout','-1',cid)
        require(docker('poststop-'+name,'inspect','-f','{{.State.Status}} {{.State.OOMKilled}} {{.State.ExitCode}}',cid) in ('exited false 0','exited false 143'),'API_STOP_RESULT')
    after,after_cmd=read_pg(sql,'post-business-drain')
    require(after==before,'DRAIN_POST')
    rec['archivedApiIds']=ids
    for n in names:del rec['ids'][n]
    rec['state']='REBUILD_BASE'
    save(AREA/'formal-api-first-drain.json',dict(taskId=TASK,runId=RUN,old=ids,beforeCommand=cmd,afterCommand=after_cmd,counts=json.loads(after)))
    save(OWNERS,rec,True)
    return {'status':'REBUILD_BASE','counts':json.loads(after)}


def next_api_snapshot():
    admission()
    rec=json.loads(OWNERS.read_bytes());require(rec['state']=='REBUILD_BASE','REBUILD_ORDER')
    for cid in rec['archivedApiIds'].values():require(docker('archived-state','inspect','-f','{{.State.Status}} {{.State.OOMKilled}}',cid)=='exited false','ARCHIVED_OWNER')
    previous=json.loads((AREA/'formal-api-inputs.json').read_bytes())
    conf=json.loads((AREA/'formal-api-compose.json').read_bytes())
    binding=build.validate('api',TASK)
    require(binding['inputKey']!=previous['build']['inputKey'],'REBUILD_REASON')
    argv=json.loads((AREA.parent/'api-build-binding.json').read_bytes())['command']
    command_sha=ex.sha(ex.encoded(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*argv]))
    row=next(json.loads(l) for l in reversed((AREA.parent/'command-events.jsonl').read_text().splitlines())
             if json.loads(l).get('exitCode')==0 and json.loads(l)['commandSummary']['sha256']==command_sha and json.loads(l)['inputFingerprint']==binding['inputKey'])
    snap=snapshots.freeze(ROOT,ROOT/Path(build.TARGETS['api']).parent/'bin/Debug/net10.0',AREA/'runtime-snapshots',binding,row['commandId'],
                          {'toolEnvironment':row['environmentFingerprint']},task=TASK,run_id=RUN)
    logcfg=RUNTIME/'api/appsettings.json'
    oldcfg=RUNTIME/'api-settings-first.private.json'
    require(not oldcfg.exists(),'OLD_API_CONFIG')
    cfg=json.loads(logcfg.read_bytes())
    cfg['Logging']['LogLevel']['OntologyPlatform.Modules.Connections.OracleSourceAdapter']='Information'
    logcfg.rename(oldcfg)
    private(logcfg,cfg)
    # 保留首个 API 的容器、文件和原快照。新代单独 compose project 接同一组准确已登记网络。
    conf['name']=PROJECT+'-api02'
    conf['services']={n:conf['services'][n] for n in ('api','api-secondary')}
    del conf['volumes']
    for k in ('platform-internal','host-entry'):conf['networks'][k]={'external':True,'name':PROJECT+'_'+k}
    for service in conf['services'].values():service['volumes'][0]=str(ROOT/snap['directory'])+':/app:ro'
    for filename in ('formal-api-compose','formal-api-inputs'):
        f=AREA/(filename+'.json');old=AREA/(filename+'-01.json');require(not old.exists(),'ORIGINAL_EXISTS');f.rename(old)
    save(AREA/'formal-api-compose.json',conf)
    value={**previous,'snapshotId':snap['snapshotId'],'build':binding,'buildCommandId':row['commandId'],'composeSha256':ex.sha((AREA/'formal-api-compose.json').read_bytes())}
    save(AREA/'formal-api-inputs.json',value)
    rec['state']='NEW_API_SNAPSHOT';save(OWNERS,rec,True)
    return value


def native_fixture_sql(body,stage):
    source=active_source_record()['containerId']
    require(docker('fixture-owner','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{.State.Status}}',source)==source+' '+TASK+' running','SOURCE_FIXTURE_OWNER')
    args=['docker','--context','desktop-linux','exec','-i',source,'sqlplus','-L','-s','/ as sysdba']
    head='whenever sqlerror exit failure rollback\nset echo off heading off pages 0 lines 900 feedback off verify off tab off\nalter session set container=FREEPDB1;\n'
    r=ex.run(args,ROOT,task=TASK,run_id=product_run() or RUN,stage=stage,stdin=(head+body+'\nexit success\n').encode(),input_key=ex.sha(body.encode()),timeout=12)
    require(r.returncode==0,'SOURCE_FIXTURE_'+r.receipt['commandId'])
    return r.stdout.decode().strip(),r.receipt['commandId']


def fixture_state():
    columns='ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,'+','.join("to_char("+col+",'YYYYMMDDHH24MISSFF6')" for col in ('FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS'))
    tables=['"PRODUCTION"."OMQ_ENTITY"','"CaseOwner"."OmqTarget"']
    rows=[];ids=[]
    for table in tables:
        raw,cmd=native_fixture_sql('select json_array('+columns+' returning varchar2(500)) from '+table+' order by ROW_ID;','omq-fixture-before')
        rows.append([json.loads(line.strip(),parse_float=str) for line in raw.splitlines() if line.strip()]);ids.append(cmd)
    require(rows[0] and rows[1] and len(rows[0])<=100 and len(rows[1])==1,'FIXTURE_NORMAL_COUNT')
    baseline=json.loads((AREA/'window-05.json').read_bytes())['afterHash']
    require([ex.sha(ex.encoded(group[0])) for group in rows]==baseline,'FIXTURE_BASELINE_VALUES')
    return dict(counts=list(map(len,rows)),baseHashes=baseline,hashes=[ex.sha(ex.encoded(x)) for x in rows],commandIds=ids)


def session_preflight(actors,seconds):
    """复用正式票据解密与治理数据库。探针只用平台内网及必要的只读挂载。"""
    import uuid
    from workflow_m2_evidence import mtp
    if product_run():
        from workflow_oracle_mapping_resume import verify_sessions
        return verify_sessions(actors,seconds)
    binding=build.validate('agent',TASK)
    inputs=json.loads((AREA/'formal-api-inputs.json').read_bytes())['build']
    require(inputs['inputKey']==binding['inputKey'],'SESSION_BUILD')
    nonce=uuid.uuid4().hex
    scratch='/tmp/omq-session-probe-'+nonce
    cfg=json.loads(OWNERS.read_bytes())
    # Docker 在同网络命名空间提供正式 DNS、PG 与认证回环。
    api=cfg['ids']['api'];require(re.fullmatch('[0-9a-f]{64}',api),'SESSION_API')
    testdir=ROOT/Path(build.TARGETS['agent']).parent/'bin/Debug/net10.0'
    script='mkdir -m 700 '+scratch+'; cd /tmp; dotnet /app/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline --minimum-expected-tests 1 --no-ansi --progress off --results-directory /tmp/results; cat "$G4_BROWSER_REPORT"; echo'
    args=['create','-i','--pull=never','--network','container:'+api,'--read-only','--user',str(os.getuid())+':'+str(os.getgid()),'--cap-drop=ALL',
          '--security-opt=no-new-privileges','--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--tmpfs','/tmp:rw,mode=1777,size=32m',
          '--log-driver=none','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+nonce,
          '--mount','type=bind,src='+str(testdir)+',dst=/app,readonly','--mount','type=bind,src='+str(RUNTIME/'api')+',dst=/private/api,readonly',
          '--mount','type=bind,src='+str(RUNTIME/'keyring')+',dst=/keyring,readonly','-e','HOME=/tmp','-e','DOTNET_CLI_HOME=/tmp',
          '-e','ASPNETCORE_ENVIRONMENT=Development','-e','G4_BROWSER_PREFLIGHT=1','-e','G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,'-e','OMQ_SESSION_SECONDS='+str(seconds),
          '-e','G4_BROWSER_REPORT='+scratch+'/session-ready.json','--entrypoint=/bin/sh',PROBE,'-ec',script]
    cid=docker('session-probe-create',*args)
    require(re.fullmatch('[0-9a-f]{64}',cid),'SESSION_PROBE')
    value=docker('session-identity','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{.State.Status}}',cid)
    require(value==cid+' '+IMAGES['api']+' '+nonce+' created','SESSION_PROBE_ID')
    r=ex.run(['docker','--context','desktop-linux','start','-ai',cid],ROOT,task=TASK,run_id=RUN,stage='omq-session-real',stdin=ex.encoded(actors),input_key=ex.sha(ex.encoded(binding)),timeout=22)
    state=docker('session-exit','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.attempt"}} {{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid)
    require(state.startswith(cid+' '+nonce+' exited '),'SESSION_PROBE_UNKNOWN')
    docker('session-release','rm',cid)
    require(not docker('session-absent','ps','-aq','--no-trunc','--filter','id='+cid),'SESSION_REAPPEARED')
    require(r.returncode==0 and state.endswith('exited 0 false'),'SESSION_REJECTED_'+r.receipt['commandId'])
    mtp(r.stdout+r.stderr,1)
    obs=json.loads(r.stdout.splitlines()[-1]);require(len(obs)==4 and [x['subjectId'] for x in obs]==[a['subjectId'] for a in actors],'SESSION_SUBJECT')
    return dict(commandId=r.receipt['commandId'],observations=obs)


def ready_grants_sql(cid,q):
    require(re.fullmatch('[a-f0-9]{32}',cid) and re.fullmatch('[A-Za-z0-9:_-]{1,120}',q),'READY_GRANT_ID')
    return f"""SELECT coalesce(json_agg(g),'[]') FROM (SELECT "Permission","ObjectRefs","FieldRefs","SiteIds","OrganizationId",floor(extract(epoch from ("ExpiresAtUtc"-now())))::int ttl FROM governance."MappingAuthorizationGrants"
      WHERE "RevokedAtUtc" IS NULL AND "SubjectId"='{q}' AND "ConnectionId"='{cid}' AND "Permission" IN ('data.query.execute','data.query.result.read','data.query.evidence.read')) g;""".encode()


def ready_fixture(state):
    cid=state['connectionId'];q=state['subjects']['reader']
    require((state['taskId'],state['runId'])==(TASK,RUN) and re.fullmatch('[a-f0-9]{32}',cid) and re.fullmatch('[A-Za-z0-9:_-]{1,120}',q),'READY_SCOPE')
    cols=['ROW_ID','JOIN_KEY','VAL','ORG_ID','SITE_ID','EXT_ID','LABEL','FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS']
    obj='PRODUCTION/OMQ_ENTITY';fields=[obj+'/'+str(i)+'/'+v for i,v in enumerate(cols,1)]
    current,_=read_pg(('SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+cid+'\' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;').encode(),'ready-current-catalog')
    require(json.loads(current)==state['catalog'],'OMQ_READY_CATALOG_STALE')
    mr=state['mappingReceipt'];mid=mr['mappingId'];require(re.fullmatch('[a-zA-Z0-9-]{1,96}',mid),'READY_MAPPING')
    raw,command=read_pg(ready_grants_sql(cid,q),'ready-current-grants')
    pointer_raw,pointer_cmd=read_pg((f'''SELECT to_jsonb(a) FROM connections."MappingActives" a WHERE "MappingId"='{mid}';''').encode(),'ready-activation')
    pointer=json.loads(pointer_raw)
    require(pointer['ActivationId']==mr['activationId'] and pointer['ActivationRevision']==mr['activationRevision'],'OMQ_READY_ACTIVATION_STALE')
    wanted={'data.query.execute','data.query.result.read','data.query.evidence.read'}
    rows=[r for r in json.loads(raw) if r['ttl']>0 and r['SiteIds']==['site-a'] and r['OrganizationId']=='org-demo' and r['ObjectRefs']==[obj] and set(r['FieldRefs'])==set(fields)]
    require(len(rows)==3 and {r['Permission'] for r in rows}==wanted,'OMQ_READY_GRANT_EXPIRED')
    # 实际待执行驱动硬截止为180秒，另留30秒供证据与夹具恢复。
    seconds=210;remaining=min(r['ttl'] for r in rows);require(remaining>=seconds,'OMQ_READY_GRANT_TTL_SHORT')
    actors=state['actors'];require([a['subjectId'] for a in actors]==[state['subjects'][k] for k in ('operator','auditor','activator','reader')],'READY_ROLES')
    session=session_preflight(actors,seconds);fixture=fixture_state()
    require(fixture['counts']==([100,1] if state['mode'] in ('s0-oracle-natural','s0-oracle-cancel') else [1,1]),'READY_SOURCE_ROWS')
    return dict(taskId=TASK,runId=product_run() or RUN,status='READY',remainingSeconds=remaining,requiredSeconds=seconds,fieldCount=11,grantCount=3,fixtureBefore=fixture,
                session=session,commandId=command,activationCommand=pointer_cmd)


def web_binding():
    return dict(taskId=TASK,runId=RUN,buildId=(ROOT/'apps/web/.next/BUILD_ID').read_text().strip(),**build.validate('web',TASK))


def audit_window(start_utc,end_utc,client_id=None):
    from workflow_oracle_mapping_formal_observer import scoped_audit_window as audit
    return audit(start_utc,end_utc,client_id)


def browser_run(mode,case='healthy'):
    import uuid
    from workflow_oracle_mapping_evidence import browser_invocation
    require(mode in ('provision','mapping','s0-oracle-ready','s0-oracle-natural','s0-oracle-cancel','s0-oracle-natural-cancel','s1','s1-reopen'),'FORMAL_MODE')
    run=product_run() or RUN
    area=AREA.parent/run
    resource=admission()
    pre=ex.run(['python3','-B','scripts/maintenance/execution_preflight.py','check','--milestone',TASK,'--phase','runtime'],ROOT,
               task=TASK,run_id=run,stage='omq-consumers-'+mode,input_key=ex.sha(Path(__file__).read_bytes()),timeout=18)
    require(pre.returncode==0,'FORMAL_CONSUMERS_'+pre.receipt['commandId'])
    stage={'phase':'s1' if mode in ('s1','s1-reopen') else 's0','mode':mode,'case':case}
    statefile=area/'runtime-fixture.json'
    if statefile.exists():
        state=json.loads(statefile.read_bytes());stage['prerequisiteSha256']=ex.sha(statefile.read_bytes())
        stage.update({k:state[k] for k in ('connectionId',) if k in state})
        if 'subjects'in state:stage['readerSubjectId']=state['subjects']['reader']
        if 'catalog'in state:stage['catalogSnapshotId']=state['catalog']['snapshotId'];stage['catalogFingerprint']=state['catalog']['schemaFingerprint']
        if 'mappingReceipt'in state:stage['activationRevision']=state['mappingReceipt']['activationRevision'];stage['mappingReleaseId']=state['mappingReceipt']['mappingReleaseId']
    if mode=='s1-reopen':
        original=state['latestQuery']['oraclePersistence']['reportName']
        require(re.fullmatch(r'browser-s1-[0-9]{13}\.json',original),'S1_ORIGIN_NAME')
        origins=[json.loads(ex.ordinary(path).read_bytes()) for path in area.glob('formal-run-s1-*.json')]
        matches=[item for item in origins if item.get('mode')=='s1' and item.get('reports')==[original] and item.get('exitCode')==0]
        require(len(matches)==1,'S1_ORIGIN_AMBIGUOUS')
        stage['originCommandId']=matches[0]['commandId']
    stage['fixtureBefore']=fixture_state()
    host=runtime_binding();api=build.validate('api',TASK);tests=build.validate('agent',TASK)
    argv,key,label=browser_invocation(ROOT,mode,case,host,api,tests,stage)
    report_pattern='browser-'+mode+'-'+'[0-9]'*13+'.json'
    before=set(area.glob(report_pattern))
    result=ex.run(argv,ROOT,task=TASK,run_id=run,stage=label,input_key=key,parent_id=host['commandId'],timeout=180)
    after=set(area.glob(report_pattern))-before
    entry=dict(taskId=TASK,runId=run,mode=mode,case=case,stageInputs=stage,host=host,builds={'api':api,'agent':tests},
               commandId=result.receipt['commandId'],exitCode=result.returncode,resourceAttempt=resource['attempt'],preflightCommandId=pre.receipt['commandId'],
               reports=[p.name for p in sorted(after)],testedCommit=local('tested-head',['git','rev-parse','HEAD']))
    path=area/('formal-run-'+mode+'-'+result.receipt['commandId']+'.json')
    save(path,entry)
    try:
        audit=audit_window(result.receipt['startedAtUtc'],result.receipt['endedAtUtc'])
        save(area/('formal-audit-'+result.receipt['commandId']+'.json'),audit)
    except Exception as error:
        save(area/('formal-audit-failure-'+result.receipt['commandId']+'.json'),{'taskId':TASK,'reason':str(error)})
        raise
    return {'mode':mode,'commandId':result.receipt['commandId'],'exitCode':result.returncode,'reports':entry['reports'],
            'stageFailure':[json.loads(p.read_bytes()).get('failure') for p in after]}


def fixed_window_pair():
    """两表正常行数界内比较自然结束和正式取消，同一组私有准确键在结束时恢复。"""
    import uuid
    token=uuid.uuid4().hex
    status={'taskId':TASK,'runId':RUN,'fixtureOwner':token,'status':'STARTED','stages':[]}
    baseline=fixture_state();require(baseline['counts']==[1,1],'WINDOW_PRESTATE')
    status['before']=baseline
    path=AREA/('formal-window-fixture-'+token+'.json')
    save(path,status)
    admission()
    # 变更行数前先复核本次签发确已生效且有当前余量，随后每一正式场景仍重核四张票据。
    import datetime as dt
    state=json.loads((AREA/'runtime-fixture.json').read_bytes())
    ready_file=max(AREA.glob('browser-s0-oracle-ready-*.json'),key=lambda f:f.stat().st_mtime_ns)
    ready=json.loads(ready_file.read_bytes())
    now=dt.datetime.now(dt.timezone.utc)
    require(ready['status']=='PASS' and ready['inputsUnchanged'] is True and ready['scenarioReady']['fixtureBefore']['hashes']==baseline['hashes']
            and all(dt.datetime.fromisoformat(w['ExpiresAtUtc'].replace('Z','+00:00'))>now+dt.timedelta(seconds=210)
                    for w in ready['scenarioReady']['session']['observations']),'LOAD_SESSION_PRESTATE')
    gr,gr_cmd=read_pg(ready_grants_sql(state['connectionId'],state['subjects']['reader']),'load-current-grants')
    current_grants=json.loads(gr)
    require(len(current_grants)==3 and len({g['Permission'] for g in current_grants})==3
            and all(g['ttl']>=210 and len(g['FieldRefs'])==11 for g in current_grants),'LOAD_GRANT_PRESTATE')
    mr=state['mappingReceipt'];mid=mr['mappingId'];require(re.fullmatch('mapping-[a-f0-9]{32}',mid),'LOAD_MAPPING_ID')
    pointer,ptr_cmd=read_pg((f'''SELECT to_jsonb(a) FROM connections."MappingActives" a WHERE "MappingId"='{mid}';''').encode(),'load-current-activation')
    pointer=json.loads(pointer)
    require(pointer['ActivationId']==mr['activationId'] and pointer['ActivationRevision']==mr['activationRevision'],'LOAD_ACTIVATION')
    status['prerequisite']={'ready':ready_file.name,'grants':gr_cmd,'activation':ptr_cmd,'minimumTtl':min(g['ttl'] for g in current_grants)}
    body=f"""DECLARE
      n number;
      BEGIN
       select count(*) into n from "PRODUCTION"."OMQ_ENTITY";
       if n!=1 then raise_application_error(-20004,'normal window prestate'); end if;
       insert into "PRODUCTION"."OMQ_ENTITY"
       select 50000+level, JOIN_KEY,VAL,ORG_ID,SITE_ID,'fw-'||substr('{token}',1,12)||'-'||level,LABEL,FROM_TS,TO_TS,EVENT_TS,OBSERVED_TS
       from "PRODUCTION"."OMQ_ENTITY" where ROW_ID=1 connect by level<=99;
       if sql%rowcount!=99 then raise_application_error(-20005,'normal window insert'); end if;
       commit;
      END;
      /"""
    inserted=False
    try:
        _,cmd=native_fixture_sql(body,'omq-formal-100-load')
        inserted=True
        status['loadCommand']=cmd
        status['expanded']=fixture_state()
        require(status['expanded']['counts']==[100,1],'WINDOW_COUNT')
        for mode in ('s0-oracle-natural','s0-oracle-cancel'):
            result=browser_run(mode)
            status['stages'].append(result)
            save(path,status,True)
            if result['exitCode']!=0:break
        status['status']='PASS' if len(status['stages'])==2 and all(r['exitCode']==0 for r in status['stages']) else 'FAIL'
    except Exception as error:
        status.update(status='UNCONFIRMED',reason=str(error));raise
    finally:
        if inserted:
            _,cmd=native_fixture_sql(f"""begin
             delete from "PRODUCTION"."OMQ_ENTITY" where ROW_ID between 50001 and 50099
             and EXT_ID='fw-'||substr('{token}',1,12)||'-'||(ROW_ID-50000);
             if sql%rowcount!=99 then raise_application_error(-20006,'exact key restore'); end if;
             commit;
             end;
             /""",'omq-formal-100-restore')
            status['restoreCommand']=cmd;status['after']=fixture_state()
            require(status['after']['hashes']==baseline['hashes'] and status['after']['counts']==[1,1],'WINDOW_RESTORE')
        save(path,status,True)
    return status


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action',choices=('admission','render','create','init-volumes','start','prepare-api','primary','secondary','pause-apis','next-snapshot','observe','browser','window-pair'))
    cli.add_argument('--mode')
    cli.add_argument('--case',default='healthy')
    cli.add_argument('--idempotency-key')
    cli.add_argument('--query-id')
    cli.add_argument('--output')
    args=cli.parse_args()
    if args.action=='observe':
        from workflow_oracle_mapping_formal_observer import observe
        observe(args.idempotency_key,args.output,args.query_id)
        raise SystemExit(0)
    actions={'admission':admission,'render':render,'create':create_platform,'init-volumes':init_volumes,'start':start_platform,'prepare-api':prepare_api,'primary':lambda:start_api('api'),'secondary':lambda:start_api('api-secondary'),'pause-apis':pause_unused_apis,'next-snapshot':next_api_snapshot,'browser':lambda:browser_run(args.mode,args.case),'window-pair':fixed_window_pair}
    if product_run():
        import workflow_oracle_mapping_resume as resume
        def prepare_product_api():
            info=resume.prepare()
            resume.bind_session_tests()
            return info
        def create_and_start(role):
            if role not in resume.manifest()['ids']:
                resume.create(role)
            return resume.start_api(role)
        actions={'admission':admission,'prepare-api':prepare_product_api,'primary':lambda:create_and_start('api'),
                 'secondary':lambda:create_and_start('api-secondary'),'browser':lambda:browser_run(args.mode,args.case)}
        require(args.action in actions,'PRODUCT_ACTION')
    result=actions[args.action]()
    print(json.dumps(result,default=str))
    if args.action=='browser':
        raise SystemExit(result['exitCode'])
    if args.action=='window-pair' and result['status']!='PASS':
        raise SystemExit(1)
