"""第二次恢复对冻结账本、分项实测与新增临时资源的限定核验。"""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import workflow_evidence as evidence
import workflow_execution as ex
import workflow_oracle_mapping_platform as platform
from workflow_oracle_mapping_resources import TASK, RUN, PROBE, require

ROOT = platform.ROOT
BASE = '454d1a2f17581673cbbf44900a5fe241d603f5ef'
BATCH = 's0-recovery-02'
PRIOR = 's0-recovery-01'
AREA = platform.AREA.parent / BATCH
REL = Path('docs/evidence') / TASK
PREVIOUS = REL / PRIOR
ALT = 'ontology-g4-omq-restore-01'
REFERENCE = 'ontology-g4-omq-recovery-02_rustfs-reference'
NETS = {'platform-internal': 'd34e4f9438a9343814d3aecceaa90fb46eaa6787bcf79cd14f89edca386e4715',
        'host-entry': '108368563e923e867d65235981bfb26ab3461f298e8c1939e7f23e4f408038c6'}
PHASES = {'identity': {'platform-pg','keycloak-test','identity-host'},
          'objects': {'rustfs','objects-reader'}, 'reference': {'objects-reference','objects-reader','reference-loader'}, 'sealed': set()}
EXTRA = {'identity-host': (768,.5), 'objects-reference': (512,.5), 'objects-reader': (512,.5), 'reference-loader': (128,.25)}
ALT_IDS = {'platform-pg':'79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545',
           'keycloak-test':'27d6b6df9ad1ce713cf5943f865beeda86eab1ea8ea2c483bb6f008e35415af1',
           'rustfs':'65a98692a6340cd29d2680fff981c6c81c764b7af96320a7945725ca5eb650be'}
RUST_HASH = '6ff1aa706d27fd31f0c98c95168124d3a0f07a6018aef527f45bdb169e70be3e'
REGISTRY = AREA / 'registered-resources.json'
EXECUTED_ROOT = Path('/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform')
TAR_VERIFY = 'cd /data; test -z "$(find . -mindepth 1 -print -quit)"; tar --numeric-owner --sparse --acls --xattrs -xpf /frozen.tar; sync; tar --numeric-owner --acls --xattrs -df /frozen.tar'


def load(path):
    return json.loads(ex.ordinary(path).read_bytes())


def git_bytes(commit, relative):
    require(re.fullmatch('[0-9a-f]{40}',commit) and '..' not in Path(relative).parts and not Path(relative).is_absolute(),'GIT_INPUT')
    return subprocess.check_output(['git','show',commit+':'+str(relative)],cwd=ROOT)


def frozen(name):
    """从 Base 的 Git 原件恢复，校验已登记原始字节，而非信任新登记的散列。"""
    index=json.loads(git_bytes(BASE,PREVIOUS/'index.json'))
    target=str(PREVIOUS/'originals'/name)
    matches=[v for v in index['artifacts'] if v['originalPath']==target]
    require(len(matches)==1,'FROZEN_RECORD')
    row=matches[0]
    require((ROOT/row['path']).read_bytes()==git_bytes(BASE,row['path']),'FROZEN_GIT_BYTES')
    return json.loads(evidence.restore(ROOT,row))


def registry():
    value=load(REGISTRY) if REGISTRY.exists() else dict(taskId=TASK,runId=BATCH,base=BASE,ids={},volumes={})
    require((value['taskId'],value['runId'],value['base'])==(TASK,BATCH,BASE) and set(value['ids'])<=set(EXTRA)
            and set(value['volumes'])<={'objects-reference'},'COMPONENT_REGISTRY')
    return value


def inspect_stage(area,phase,roles,docker):
    from workflow_oracle_mapping_platform_recovery import phase_inventory
    expected=set(roles)
    require(expected<=PHASES[phase],'COMPONENT_ROLE')
    original_roles=expected-set(EXTRA)
    active,memory,cpu,ports,repl=phase_inventory(area,'restore' if original_roles else 'closed',original_roles,docker)
    require(all(repl['ids'][k]==v for k,v in ALT_IDS.items()) and repl['networks']==NETS,'COMPONENT_FROZEN_IDS')
    for name,nid in NETS.items():
        net=docker('component-network','network','inspect','-f','{{.Id}}|{{.Name}}|{{.Internal}}|{{index .Labels "ontology.attempt"}}',nid).split('|')
        require(net==[nid,ALT+'_'+name,str(name=='platform-internal').lower(),repl['attempt']],'COMPONENT_NET')
    owned=registry()
    extra_vols=owned['volumes']
    if extra_vols:
        v=extra_vols['objects-reference']
        require(v['name']==REFERENCE and re.fullmatch('[0-9a-f]{32}',v['attempt']),'REF_VOL_ID')
        detail=docker('component-volume','volume','inspect','-f','{{.Name}}|{{.Driver}}|{{json .Options}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}|{{index .Labels "ontology.attempt"}}',REFERENCE).split('|')
        require(detail[:2]==[REFERENCE,'local'] and not json.loads(detail[2]) and detail[3:]==[TASK,BATCH,v['attempt']],'REF_VOLUME')
    for role,row in owned['ids'].items():
        cid=row['id']
        require(re.fullmatch('[0-9a-f]{64}',cid) and re.fullmatch('[0-9a-f]{32}',row['attempt']),'EXTRA_CID')
        fmt='{{.Id}}|{{.State.Status}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "ontology.attempt"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}|{{json .HostConfig.PortBindings}}|{{json .NetworkSettings.Networks}}|{{.HostConfig.ReadonlyRootfs}}'
        obs=docker('component-'+role,'inspect','-f',fmt,cid).split('|')
        ram,cores=EXTRA[role];image=platform.IMAGES['rustfs'] if role=='objects-reference' else PROBE.split('@')[1]
        require(obs[0]==cid and obs[2:8]==[image,TASK,BATCH,row['attempt'],str(ram*1024**2),str(int(cores*1e9))] and obs[11]=='true','EXTRA_OWNER')
        require(obs[1]=='running' if role in expected else obs[1] in ('created','exited'),'EXTRA_STATE')
        observed_mounts=sorted((m['Type'],m['Name'] if m['Type']=='volume' else (m['Source'][9:] if m['Source'].startswith('/host_mnt/Users/') else m['Source']),m['Destination'],m['RW']) for m in json.loads(obs[8]))
        require(observed_mounts==sorted(tuple(x) for x in row['mounts']) and all(not writable or (role in ('objects-reference','reference-loader') and (kind,src,dest)==('volume',REFERENCE,'/data')) for kind,src,dest,writable in observed_mounts),'EXTRA_MOUNTS')
        require((json.loads(obs[9]) or {})==({'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'15741'}]} if role=='identity-host' else {}),'EXTRA_PORT')
        networks=json.loads(obs[10]) or {}
        names=['platform-internal','host-entry'] if role=='identity-host' else ['platform-internal']
        if role=='reference-loader' and obs[1]!='exited':
            require(set(networks)=={'none'},'LOADER_NETWORK')
        elif obs[1]!='exited':
            require(set(networks)=={ALT+'_'+key for key in names} and all(networks[ALT+'_'+key]['NetworkID'] in ((NETS[key],) if obs[1]=='running' else ('',NETS[key])) for key in names),'EXTRA_NETWORK')
        if role in expected:
            active.add(cid);memory+=ram*1024**2;cpu+=int(cores*1e9)
            if role=='identity-host':ports.add(15741)
    require((expected & set(EXTRA))<=set(owned['ids']),'EXTRA_UNREGISTERED')
    return active,memory,cpu,ports,{**repl,'extraIds':{k:v['id'] for k,v in owned['ids'].items()},'extraVolumes':{k:v['name'] for k,v in extra_vols.items()}}


def admit(phase,roles=(),planned=None):
    return platform.before_source(ROOT,TASK,platform_stage=True,phase=phase,running_roles=roles,planned_roles=planned)


def command(stage,argv,*,payload=None,timeout=40,key=None):
    """所有新执行记录当前批次、命令摘要、输入以及真实双流。"""
    return ex.run(argv,ROOT,task=TASK,run_id=BATCH,stage=stage,timeout=timeout,stdin=payload,
                  input_key=key or ex.sha(ex.encoded(argv)+(payload or b'')))


def engine(stage,*args,payload=None,timeout=40):
    result=command(stage,['docker','--context','desktop-linux',*args],payload=payload,timeout=timeout)
    require(result.returncode==0,stage+'_'+result.receipt['commandId'])
    return result.stdout.decode().strip()


def save_record(name,data):
    platform.save(AREA/name,data)


API = ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
PRIVATE = platform.HOME_DIR/PRIOR/'restored-host/platform'
SOURCES = {'objects':'workflow_oracle_mapping_object_recovery','identity':'workflow_oracle_mapping_identity_recovery'}


def compile_driver(kind, source):
    """锁定编译器、本地 reference packs 和已接受 API 输出；每个组件独立生成一个小 DLL。"""
    require(kind in SOURCES and source.name==SOURCES[kind]+'.cs.txt','COMPILER_SOURCE')
    ready=load(next((AREA.parent/'environment').glob('*/runs/*/receipt.json')))
    original=frozen('recovery-cli-binding.json')
    previous=next(b for b in original['testedBuilds'] if b['target']=='api' and b['exitCode']==0)
    binding_path=AREA.parent/'api-build-binding.json'
    binding=load(binding_path)
    require(ex.sha(binding_path.read_bytes())==previous['binding'] and binding['outputs']==platform.build.outputs('api')
            and not subprocess.check_output(['git','diff',BASE,'--','backend'],cwd=ROOT),'REUSED_API_SNAPSHOT')
    pre=admit('sealed')
    dest=AREA/('build-'+kind+'-'+uuid.uuid4().hex);dest.mkdir(mode=0o700)
    input_bytes=ex.ordinary(source).read_bytes()
    snapshot=dest/(SOURCES[kind]+'.cs');snapshot.write_bytes(input_bytes)
    sdk=Path('/usr/local/share/dotnet')
    refs=[]
    for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref'):
        refs.extend(sorted((sdk/'packs'/pack/'10.0.13/ref/net10.0').glob('*.dll')))
    if kind=='identity':
        refs.extend(API/(name+'.dll') for name in ('OntologyPlatform.Api','Npgsql','Microsoft.AspNetCore.Authentication.OpenIdConnect',
            'Microsoft.IdentityModel.Abstractions','Microsoft.IdentityModel.Logging','Microsoft.IdentityModel.Tokens','Microsoft.IdentityModel.Protocols',
            'Microsoft.IdentityModel.Protocols.OpenIdConnect','Microsoft.IdentityModel.JsonWebTokens','System.IdentityModel.Tokens.Jwt'))
    compiler=sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'
    require(compiler.exists() and len(refs)>100 and all(f.is_file() for f in refs),'OFFLINE_COMPILER')
    dll=dest/('RecoveryIdentity.dll' if kind=='identity' else 'ObjectRecovery.dll')
    args=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',ready['dotnet'],str(compiler),'-nologo','-target:exe',
          '-nostdlib+','-nullable:enable','-out:'+str(dll),*['-r:'+str(path) for path in refs],str(snapshot)]
    fp=ex.sha(ex.encoded(dict(source=ex.sha(input_bytes),refs=[ex.sha(f.read_bytes()) for f in refs],compiler=ex.sha(compiler.read_bytes()))))
    result=ex.run(args,ROOT,task=TASK,run_id=BATCH,stage='compile-'+kind,environment=ready['environment'],input_key=fp,timeout=50)
    row=dict(kind=kind,taskId=TASK,runId=BATCH,inputFingerprint=fp,apiOutput=previous['output'],apiSource=previous['head'],apiBinding=previous['binding'],
             admission=pre['attempt'],sourceSha256=ex.sha(input_bytes),buildDir=str(dest.relative_to(ROOT)),commandId=result.receipt['commandId'],
             exitCode=result.returncode,dllSha256=ex.sha(dll.read_bytes()) if result.returncode==0 else None,dllName=dll.name)
    platform.save(dest/'receipt.json',row)
    if result.returncode:print(result.stdout.decode()[:2000])
    require(result.returncode==0,'COMPILE_'+kind)
    return row


def build_input(kind):
    source=ROOT/'scripts/maintenance'/(SOURCES[kind]+'.cs.txt')
    digest=ex.sha(source.read_bytes())
    rows=[load(p) for p in AREA.glob('build-'+kind+'-*/receipt.json')]
    matches=[r for r in rows if r['sourceSha256']==digest and r['exitCode']==0]
    require(bool(matches),'QUALIFIED_DRIVER_'+kind)
    row=matches[-1]
    require(ex.sha((ROOT/row['buildDir']/row['dllName']).read_bytes())==row['dllSha256'],'DLL_CHANGED')
    return row


def resource_id(role):
    return ALT_IDS[role] if role in ALT_IDS else registry()['ids'][role]['id']


def begin_service(phase,role,roles):
    import time
    require(role in PHASES[phase] and role not in roles,'START_COMPONENT_ROLE')
    pre=admit(phase,roles,set(roles)|{role})
    cid=resource_id(role)
    require(engine('start-identity','inspect','-f','{{.Id}}|{{.State.Status}}',cid) in (cid+'|created',cid+'|exited'),'START_STATE')
    result=engine('start-'+role,'start',cid)
    require(result==cid,'START_RESULT')
    if role=='platform-pg':
        until=time.monotonic()+45
        while time.monotonic()<until:
            state=engine('pg-health','inspect','-f','{{.State.Status}}|{{.State.Health.Status}}',cid)
            if state=='running|healthy':break
            require(state.startswith('running|'),'PG_EARLY_EXIT')
            time.sleep(.5)
        require(state=='running|healthy','PG_READINESS')
    post=admit(phase,set(roles)|{role})
    save_record('started-'+role+'-'+pre['attempt']+'.json',dict(role=role,id=cid,pre=pre['attempt'],post=post['attempt']))
    return cid


def stop_service(phase,role,roles):
    """只对当前准确 ID 发送原生停止；超时后不强杀。"""
    require(role in PHASES[phase] and role in roles,'STOP_COMPONENT_ROLE')
    cid=resource_id(role)
    stamp=uuid.uuid4().hex
    before=engine('stop-identity','inspect','-f','{{.Id}}|{{.State.Status}}|{{index .Config.Labels "ontology.task"}}',cid)
    require(before in (cid+'|running|'+TASK,cid+'|exited|'+TASK),'STOP_ID')
    if before==cid+'|running|'+TASK:
        if role=='platform-pg':
            engine('stop-pg-native','exec','--user','postgres',cid,'sh','-ec','pg_ctl status -D "$PGDATA" >/dev/null && exec pg_ctl stop -D "$PGDATA" -m fast -W')
        else:
            # 与上批相同，只发 TERM；有界 wait 单独记录，Docker 无自动 KILL 期限。
            engine('stop-term-'+role,'kill','--signal=TERM',cid)
        engine('stop-wait-'+role,'wait',cid,timeout=45)
    after=engine('stop-after','inspect','-f','{{.Id}}|{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.State.Error}}',cid).split('|')
    require(after[:2]==[cid,'exited'] and after[2] in ('0','143') and after[3:]==['false',''],'STOP_AFTER')
    post=admit(phase,set(roles)-{role})
    save_record('stopped-'+role+'-'+stamp+'.json',dict(id=cid,role=role,after=after,post=post['attempt']))


def create_driver(kind,phase,roles):
    driver=build_input(kind)
    role='identity-host' if kind=='identity' else 'objects-reader'
    require(role in PHASES[phase] and role not in registry()['ids'],'DRIVER_EXISTS')
    pre=admit(phase,roles,set(roles)|{role})
    run=uuid.uuid4().hex
    # 仅应用配置由受保护消费者在进程内消费。对象验证器不挂其他私有材料。
    mounts=[('bind',str(ROOT/driver['buildDir']),'/driver',False),('bind',str(API),'/app',False),
            ('bind',str(PRIVATE/'api/appsettings.json'),'/private/api/appsettings.json',False)]
    if kind=='identity':
        mounts += [('bind',str(PRIVATE/'api'/name),'/private/api/'+name,False) for name in ('keyring.pfx','platform-ca.crt')]
        mounts += [('bind',str(PRIVATE/'keyring'),'/keyring',False)]
    ram,cores=EXTRA[role]
    args=['create','-i','--pull=never','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user',str(os.getuid())+':'+str(os.getgid()),
          '--memory='+str(ram)+'m','--memory-swap='+str(ram)+'m','--cpus='+str(cores),'--pids-limit=128',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=24m,mode=1777','--log-driver=json-file','--log-opt=max-size=1m','--log-opt=max-file=1',
          '--network',ALT+'_platform-internal','--label','ontology.task='+TASK,'--label','ontology.run='+BATCH,'--label','ontology.attempt='+run,
          '--env','DOTNET_EnableDiagnostics=0','--env','DOTNET_CLI_TELEMETRY_OPTOUT=1']
    if kind=='identity':
        args+=['-p','127.0.0.1:15741:8080','--env','ASPNETCORE_ENVIRONMENT=Development','--env','OMQ_ATTEMPT='+run]
    for _,src,dst,_ in mounts:
        require(ex.ordinary(src).exists(),'DRIVER_BIND')
        args+=['--mount','type=bind,src='+src+',dst='+dst+',readonly']
    # 原 API 输出仅作程序集解析目录，入口固定为本批独立验证器。
    script='mkdir /tmp/check; for entry in /app/*; do ln -s "$entry" /tmp/check/; done; cp /driver/'+driver['dllName']+' /tmp/check/; exec dotnet exec --runtimeconfig /tmp/check/OntologyPlatform.Api.runtimeconfig.json --depsfile /tmp/check/OntologyPlatform.Api.deps.json /tmp/check/'+driver['dllName']
    args+=['--entrypoint=/bin/sh',PROBE,'-ec',script]
    cid=engine('create-'+role,*args)
    require(re.fullmatch('[0-9a-f]{64}',cid),'CREATED_DRIVER')
    ledger=registry();row=dict(id=cid,attempt=run,mounts=mounts,admission=pre['attempt'],driver=driver)
    ledger['ids'][role]=row;platform.save(REGISTRY,ledger,REGISTRY.exists())
    if kind=='identity':engine('identity-entry-network','network','connect',ALT+'_host-entry',cid)
    admit(phase,roles,set(roles)|{role})
    save_record('driver-'+run+'.json',dict(role=role,**row))
    return row


def release_driver(role):
    ledger=registry();row=ledger['ids'][role];cid=row['id']
    details=engine('release-identity','inspect','-f','{{.Id}}|{{.State.Status}}|{{index .Config.Labels "ontology.attempt"}}',cid).split('|')
    require(details[0]==cid and details[1] in ('exited','created') and details[2]==row['attempt'],'RELEASE_ID')
    engine('release-'+role,'rm',cid)
    require(engine('release-absent','ps','-aq','--no-trunc','--filter','id='+cid)=='','RELEASE_ABSENT')
    del ledger['ids'][role];platform.save(REGISTRY,ledger,True)
    save_record('release-'+row['attempt']+'.json',dict(role=role,id=cid,after='ABSENT'))


def observe_objects(which):
    import workflow_oracle_mapping_object_recovery as objects
    phase,service=('objects','rustfs') if which=='actual' else ('reference','objects-reference')
    require(which in ('actual','reference'),'OBJECTS_SCOPE')
    alt=frozen('replacement-resources.json')
    volume=alt['volumes']['rustfs'] if which=='actual' else REFERENCE
    host=create_driver('objects',phase,{service})
    cid=host['id'];build=host['driver']
    expected=objects.request(which,resource_id(service),volume,build['dllSha256'],host['attempt'])
    data=ex.encoded(expected)
    argv=['docker','--context','desktop-linux','start','-a','-i',cid]
    row=dict(taskId=TASK,runId=BATCH,resourceRun=RUN,base=BASE,role=which,serviceId=resource_id(service),volume=volume,
             input=expected,verifier=cid,driver=build,attempt=host['attempt'],argv=argv)
    try:
        out=command('rustfs-inventory-'+which,argv,payload=data,key=expected['inputFingerprint'],timeout=65)
        row.update(commandId=out.receipt['commandId'],exitCode=out.returncode,inputFingerprint=expected['inputFingerprint'],stdinSha256=ex.sha(data),
                   stdoutSha256=ex.sha(out.stdout),stderrSha256=ex.sha(out.stderr))
        response=json.loads(out.stdout)
        row['result']=response
        if out.returncode or response.get('status')!='OBSERVED':
            row['qualification']='BLOCKED'
        else:
            objects.inspect_observation(response,expected)
            row['qualification']='OBSERVED'
        return row
    finally:
        row['after']=engine('reader-exit','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',cid).split('|')
        save_record('objects-'+which+'-'+host['attempt']+'.json',row)
        release_driver('objects-reader')


def reference_resource():
    """先冻结新卷与服务配置，再登记 create 实际 ID，最后才向空的新卷提取已验归档。"""
    import workflow_oracle_mapping_object_recovery as objects
    ledger=registry()
    require(not ledger['volumes'] and not ledger['ids'],'REFERENCE_NOT_NEW')
    pre=admit('reference',(),{'objects-reference'})
    config=load(platform.AREA.parent/PRIOR/'restore-compose.json')
    source=config['services']['rustfs']
    archive=platform.HOME_DIR/PRIOR/'platform/rustfs.tar'
    scope=objects.archive_scope(archive)
    require(ex.sha(archive.read_bytes())==RUST_HASH and archive.stat().st_size==184320 and
            source['image'].split('@')[1]==platform.IMAGES['rustfs'],'REFERENCE_DERIVATION')
    attempt=uuid.uuid4().hex
    labels=['--label','ontology.task='+TASK,'--label','ontology.run='+BATCH,'--label','ontology.attempt='+attempt]
    mounts=[('volume',REFERENCE,'/data',True),*[('bind',str(PRIVATE/n),'/run/secrets/'+n,False) for n in ('s3-access','s3-secret')]]
    require(source['volumes'][1:]==[m[1]+':'+m[2]+':ro' for m in mounts[1:]],'REFERENCE_BIND_CONFIG')
    require(engine('reference-volume-absence','volume','ls','-q','--filter','name=^'+REFERENCE+'$')=='','REFERENCE_EXISTS')
    save_record('reference-plan-'+attempt+'.json',dict(taskId=TASK,runId=BATCH,attempt=attempt,name=REFERENCE,image=source['image'],mounts=mounts,
                networkId=NETS['platform-internal'],quota=EXTRA['objects-reference'],pre=pre['attempt'],archiveSha256=RUST_HASH,
                configurationSha256=ex.sha(ex.encoded(source)),archiveScope=scope,cleanup='only registered derived container ID then exact volume, verified absent'))
    require(engine('reference-volume-create','volume','create',*labels,REFERENCE)==REFERENCE,'REFERENCE_VOLUME_CREATE')
    ledger['volumes']['objects-reference']=dict(name=REFERENCE,attempt=attempt);platform.save(REGISTRY,ledger,REGISTRY.exists())
    admit('reference',(),{'objects-reference'})
    args=['create','--pull=never','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user',source['user'],
          '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=256','--tmpfs','/tmp:size=32m,mode=1777','--log-driver=json-file',
          '--log-opt=max-size=1m','--log-opt=max-file=1','--network',ALT+'_platform-internal','--network-alias','rustfs',*labels]
    for k,v in source['environment'].items():args+=['--env',k+'='+v]
    for kind,src,dst,rw in mounts:args+=['--mount',f'type={kind},src={src},dst={dst},'+('volume-nocopy' if rw else 'readonly')]
    require(source['entrypoint']==['/bin/sh','-ec'] and len(source['command'])==1,'REFERENCE_IMAGE_COMMAND')
    # 原 Compose 中 $$ 表示服务 shell 的 $；Docker CLI 直接调用没有 Compose 插值层。
    args+=['--entrypoint=/bin/sh',source['image'],'-ec',source['command'][0].replace('$$','$')]
    cid=engine('reference-container-create',*args)
    require(re.fullmatch('[0-9a-f]{64}',cid),'REFERENCE_CID')
    row=dict(id=cid,attempt=attempt,mounts=mounts)
    ledger['ids']['objects-reference']=row;platform.save(REGISTRY,ledger,True)
    pre=admit('reference',(),{'objects-reference'})
    # Docker cp 的 tar 回读不保留规范成员表示。使用登记的无网络 GNU tar 读写者，严格比较封存格式。
    helper=uuid.uuid4().hex
    mounts=[('volume',REFERENCE,'/data',True),('bind',str(archive),'/frozen.tar',False)]
    admit('reference',(),{'reference-loader'})
    verify=TAR_VERIFY
    helper_id=engine('reference-loader-create','create','--pull=never','--read-only','--network=none','--cap-drop=ALL',
        '--cap-add=CHOWN','--cap-add=FOWNER','--cap-add=DAC_OVERRIDE','--security-opt=no-new-privileges','--memory=128m','--memory-swap=128m',
        '--cpus=.25','--pids-limit=16','--user=0','--label','ontology.task='+TASK,'--label','ontology.run='+BATCH,'--label','ontology.attempt='+helper,
        '--mount','type=volume,src='+REFERENCE+',dst=/data,volume-nocopy','--mount','type=bind,src='+str(archive)+',dst=/frozen.tar,readonly',
        '--entrypoint=/bin/sh',PROBE,'-ec',verify)
    require(re.fullmatch('[a-f0-9]{64}',helper_id),'REFERENCE_LOADER_ID')
    ledger['ids']['reference-loader']=dict(id=helper_id,attempt=helper,mounts=mounts)
    platform.save(REGISTRY,ledger,True)
    try:
        admit('reference',(),{'reference-loader'})
        applied=command('reference-tar-extract-compare',['docker','--context','desktop-linux','start','-a',helper_id],
                        key=ex.sha(ex.encoded([cid,helper_id,REFERENCE,RUST_HASH,verify])),timeout=30)
        after=engine('ref-loader-status','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper_id)
        require(applied.returncode==0 and after=='exited|0|false' and not applied.stdout.strip() and not applied.stderr.strip(),'REFERENCE_COLD_MEMBERS')
        save_record('reference-created.json',dict(**row,taskId=TASK,runId=BATCH,volume=REFERENCE,archiveSha256=RUST_HASH,image=source['image'],
                    coldVerified=True,memberCount=scope['members'],pre=pre['attempt'],loaderId=helper_id,extractCommandId=applied.receipt['commandId']))
    finally:
        release_driver('reference-loader')
    return cid


def release_reference():
    ledger=registry()
    if 'objects-reference' in ledger['ids']:release_driver('objects-reference')
    ledger=registry()
    if not ledger['volumes']:return
    admit('reference')
    v=ledger['volumes']['objects-reference'];require(v['name']==REFERENCE,'REFERENCE_RELEASE')
    require(not engine('reference-volume-unused','ps','-aq','--filter','volume='+REFERENCE),'REFERENCE_IN_USE')
    engine('reference-volume-release','volume','rm',REFERENCE)
    require(not engine('reference-absent','volume','ls','-q','--filter','name=^'+REFERENCE+'$'),'REFERENCE_REMAINS')
    del ledger['volumes']['objects-reference'];platform.save(REGISTRY,ledger,True)
    save_record('reference-volume-released-'+v['attempt']+'.json',dict(name=REFERENCE,attempt=v['attempt'],state='ABSENT'))


def objects_window():
    """实际能力探针先行。只有实际清单完整合格时才创建封存参考。"""
    import workflow_oracle_mapping_object_recovery as objects
    start=dt.datetime.now(dt.timezone.utc).isoformat()
    row=dict(taskId=TASK,runId=BATCH,base=BASE,started=start,status='BLOCKED')
    try:
        require(load(AREA/'rustfs-offline.json')['exitCode']==0,'SIGNATURE_SELFTEST')
        archive=platform.HOME_DIR/PRIOR/'platform/rustfs.tar'
        row['archiveScope']=objects.archive_scope(archive)
        for phase,role,which in [('objects','rustfs','actual'),('reference','objects-reference','reference')]:
            if which=='actual':
                old=[load(f) for f in AREA.glob('objects-actual-*.json') if load(f).get('qualification')=='OBSERVED']
                if old:
                    require(len(old)==1,'AMBIGUOUS_ACTUAL')
                    qualified_object('actual',old[0]['attempt'])
                    row.update(actual=old[0]['attempt'],actualMode='REQUALIFIED')
                    continue
            if which=='reference':reference_resource()
            try:
                begin_service(phase,role,set())
                # 镜像健康端点的就绪仅用于避免把启动窗口当版本接口实测；不提交写操作。
                import time
                time.sleep(2)
                item=observe_objects(which)
                row[which]=item['attempt']
                require(item.get('qualification')=='OBSERVED','RUSTFS_'+which+'_PROTOCOL')
            finally:
                cid=resource_id(role)
                if engine('service-after-window','inspect','-f','{{.State.Status}}',cid)=='running':
                    stop_service(phase,role,{role})
        actual=load(AREA/('objects-actual-'+row['actual']+'.json'))
        reference=load(AREA/('objects-reference-'+row['reference']+'.json'))
        row['comparison']=objects.qualify(actual['result'],reference['result'],actual['input'],reference['input'])
        row['status']=row['comparison']['status']
    except Exception as err:
        reason=str(err)
        row['reason']=reason if re.fullmatch('[A-Za-z0-9_-]{1,150}',reason) else type(err).__name__
    finally:
        if registry()['volumes'] and 'objects-reference' not in registry()['ids']:
            release_reference()
        elif 'objects-reference' in registry()['ids']:
            ref=resource_id('objects-reference')
            if engine('ref-final-state','inspect','-f','{{.State.Status}}',ref) in ('created','exited'):release_reference()
        row['ended']=dt.datetime.now(dt.timezone.utc).isoformat()
        save_record('objects-window-'+uuid.uuid4().hex+'.json',row)
    return row


def current_pg(stamp,part):
    import workflow_oracle_mapping_checkpoint as checkpoint
    import workflow_oracle_mapping_identity_recovery as identity
    fixture=load(platform.AREA/'runtime-fixture.json')
    pg=checkpoint.collect_pg(ALT_IDS['platform-pg'],fixture,'4239ea404d924bbcae5e4ec41ad4cc27',stamp,measurement_run=BATCH)
    result=command('oidc-epoch-'+part,['docker','--context','desktop-linux','exec','-i','--user','postgres',ALT_IDS['platform-pg'],
                   'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],payload=identity.epoch_details_sql(),timeout=20)
    require(result.returncode==0,'AUTH_EPOCH_QUERY')
    return dict(pg=pg,details=json.loads(result.stdout),epochCommand=result.receipt['commandId'])


def auth_events(cid,attempt):
    # 正规宿主已关闭框架日志。仅接受该尝试的结构化观测；不记录服务或浏览器认证载荷。
    res=subprocess.run(['docker','--context','desktop-linux','logs',cid],capture_output=True,timeout=8)
    require(res.returncode==0 and len(res.stdout)+len(res.stderr)<=256*1024,'AUTH_LOG_SCOPE')
    require(not res.stderr.strip(),'AUTH_UNEXPECTED_STDERR')
    events=[]
    for line in res.stdout.splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        require(row['attempt']==attempt and set(row)=={'kind','attempt','utc','details'},'AUTH_LOG_ID')
        events.append(row)
    return events


def startup_diagnostic(cid):
    """只输出固定分类及退出码；认证宿主可能产生的框架原文不进入证据。"""
    output=subprocess.run(['docker','--context','desktop-linux','logs',cid],capture_output=True,timeout=5)
    sample=(output.stderr+output.stdout)[:262144].lower()
    markers=('permission denied','no such file','file not found','not found','unauthorizedaccessexception',
             'could not load file or assembly','failed to load','application to execute does not exist',
             'cannot create','read-only file system','exec format error','out of memory','you must install',
             'ontologyplatform.api','microsoft.identitymodel','libhostpolicy','recoveryidentity.dll','coreclr')
    return dict(exitState=engine('auth-host-exit','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',cid),
                categories=[m for m in markers if m.encode() in sample],stdoutBytes=len(output.stdout),stderrBytes=len(output.stderr))


def auth_public_readiness():
    import urllib.request
    import time
    expected=frozen('oidc-public-baseline.json')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    end=time.monotonic()+55
    while time.monotonic()<end:
        try:
            with opener.open(expected['issuer']+'/.well-known/openid-configuration',timeout=2) as response:
                cfg=json.loads(response.read(65536))
            require(cfg['issuer']==expected['issuer'] and cfg['jwks_uri']==expected['jwksUri'],'AUTH_ISSUER_DRIFT')
            return
        except (OSError,TimeoutError):time.sleep(1)
    raise ValueError('AUTH_DISCOVERY_TIMEOUT')


def identity_window(action):
    import time
    import workflow_oracle_mapping_identity_recovery as identity
    pointer=AREA/'auth-current.json'
    if action=='finish':
        active=load(pointer)
        row=registry()['ids']['identity-host']
        require(active['attempt']==row['attempt'] and active['id']==row['id'],'AUTH_SESSION')
        return finish_identity(active,row)
    require(action=='prepare' and not registry()['ids'] and not registry()['volumes'],'IDENTITY_PRECONDITION')
    facts=identity.frozen_inputs(ROOT)
    entered=set();host=None;started=round(time.time()*1000)
    active=dict(taskId=TASK,runId=BATCH,base=BASE,resourceRun=RUN,startedMs=started,frozenInputs=facts,denialOriginal='DENIAL_ORIGINAL_NOT_AVAILABLE')
    try:
        for role in ('platform-pg','keycloak-test'):
            begin_service('identity',role,entered);entered.add(role)
        auth_public_readiness()
        host=create_driver('identity','identity',entered)
        active.update(id=host['id'],attempt=host['attempt'],driver=host['driver'],pg=ALT_IDS['platform-pg'],idp=ALT_IDS['keycloak-test'])
        active['inputFingerprint']=ex.sha(ex.encoded([TASK,BATCH,BASE,host['id'],host['attempt'],host['driver']['dllSha256'],facts,ALT_IDS['platform-pg'],ALT_IDS['keycloak-test']]))
        active['before']=current_pg(host['attempt'],'before')
        require(active['before']['pg']['stable']==frozen('pg-baseline-0e8c1a69fbe5401292061ac13dda2874.json')['stable'],'BEFORE_AUTH_BUSINESS')
        admit('identity',entered,entered|{'identity-host'})
        argv=['docker','--context','desktop-linux','start',host['id']]
        start=command('dedicated-auth-start',argv,key=active['inputFingerprint'])
        active.update(commandId=start.receipt['commandId'],argv=argv)
        require(start.returncode==0,'AUTH_START')
        until=time.monotonic()+32
        while time.monotonic()<until:
            active['observed']=auth_events(host['id'],host['attempt'])
            if any(e['kind']=='ready' for e in active['observed']):break
            if engine('auth-ready-state','inspect','-f','{{.State.Status}}',host['id'])!='running':break
            time.sleep(.5)
        require(any(e['kind']=='ready' for e in active['observed']),'AUTH_ENTRY_NOT_READY')
        active['admission']=admit('identity',entered|{'identity-host'})['attempt']
        active['status']='AUTHENTICATION_ENTRY_READY'
        platform.save(pointer,active,pointer.exists())
        return dict(status=active['status'],attempt=host['attempt'],start=started,expiresMs=started+14*60000)
    except Exception as error:
        active['status']='BLOCKED'
        active['reason']=str(error) if re.fullmatch(r'[a-zA-Z0-9_-]{1,180}',str(error)) else type(error).__name__
        if host is None and 'identity-host' in registry()['ids']:
            host=registry()['ids']['identity-host']
        if host:active['startupDiagnostic']=startup_diagnostic(host['id'])
        save_record('auth-failure-'+uuid.uuid4().hex+'.json',active)
        if host:
            state=engine('auth-failed-state','inspect','-f','{{.State.Status}}',host['id'])
            if state=='running':stop_service('identity','identity-host',entered|{'identity-host'})
            release_driver('identity-host')
        entered={r for r in ('platform-pg','keycloak-test') if engine('auth-cleanup-state','inspect','-f','{{.State.Status}}',ALT_IDS[r])=='running'}
        stop_identity_services(entered)
        return dict(status='BLOCKED',reason=active['reason'],observed=[(e['kind'], e['details'] if e['kind']=='failed' else '') for e in active.get('observed',[])])


def stop_identity_services(roles):
    errors=[]
    for role in ('keycloak-test','platform-pg'):
        if role not in roles:continue
        try:stop_service('identity',role,roles)
        except (ValueError, subprocess.SubprocessError) as exc:errors.append(str(exc))
        if engine('auth-stop-post','inspect','-f','{{.State.Status}}',ALT_IDS[role])=='exited':roles.remove(role)
    # 回环端口可能短时仍在 TIME_WAIT。停止动作逐个完成后，以独立、完整的最终准入为准。
    import time
    for _ in range(3):
        try:
            admit('sealed')
            return
        except ValueError as err:
            if str(err)!='ORACLE_ADMISSION_FROZEN_PORT_COLLISION':raise
            time.sleep(1)
    raise ValueError('ORACLE_ADMISSION_SEALED_POSTSTATE')


def finish_identity(active,host):
    import time
    import workflow_oracle_mapping_identity_recovery as identity
    roles={'platform-pg','keycloak-test','identity-host'}
    events=[]
    active['status']='BLOCKED'
    try:
        try:stop_service('identity','identity-host',roles)
        except ValueError as err:
            if str(err)!='ORACLE_ADMISSION_FROZEN_PORT_COLLISION':raise
            require(engine('auth-host-exit','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',host['id'])=='exited|0|false','AUTH_HOST_EXIT')
        roles.remove('identity-host')
        # 关闭操作可能触发最后的正规票据操作，使用停止后的完整双流。
        events=auth_events(host['id'],host['attempt'])
        active.update(events=events,endMs=round(time.time()*1000),after=current_pg(host['attempt'],'after'))
        # Only persist the validated structured channel. Diagnostic/authentication middleware logs are never package inputs.
        stdout=command('auth-redacted-events',['docker','--context','desktop-linux','logs',host['id']],key=active['inputFingerprint'])
        require(stdout.returncode==0 and not stdout.stderr.strip()
                and all(json.loads(line) in events for line in stdout.stdout.splitlines() if line.strip()),'AUTH_LOG_OUTPUT')
        active['eventCommand']=stdout.receipt['commandId']
        try:
            observed=identity.qualify_partial(events,host['attempt'],active['startedMs'],active['endMs'])
            active['pgWrites']=identity.qualify_pg(active['before']['pg'],active['after']['pg'],observed,active['before']['details'],active['after']['details'])
            active['status']=observed['status']
        except ValueError as err:
            active['reason']=str(err);active['status']='BLOCKED'
    finally:
        save_record('auth-ended-'+host['attempt']+'.json',active)
        release_driver('identity-host')
        stop_identity_services(roles)
    return dict(status=active['status'],attempt=host['attempt'],normalLogins=sum(e['kind']=='me' for e in events))


def record_bytes(name):
    """优先以已发布的同批原件核资格；首次发布前读同一个实际执行目录。"""
    index=ROOT/REL/BATCH/'index.json'
    if index.is_file():
        entries=[r for r in load(index)['artifacts'] if r['originalPath']==str(REL/BATCH/'originals'/name)]
        require(len(entries)==1,'MISSING_OR_DUPLICATE_ORIGINAL')
        return evidence.restore(ROOT,entries[0])
    if name=='runtime-fixture.json':return ex.ordinary(platform.AREA/name).read_bytes()
    return ex.ordinary(AREA/name).read_bytes()


def command_bytes(cid,part):
    require(re.fullmatch('[0-9a-f]{32}',cid) and part in ('receipt.json','stdout.txt','stderr.txt'),'COMMAND_PATH')
    index=ROOT/REL/BATCH/'index.json'
    if index.is_file():
        rel=str(REL/BATCH/'commands'/cid/part)
        records=[v for v in load(index)['artifacts'] if v['originalPath']==rel]
        require(len(records)==1,'COMMAND_ORIGINAL')
        return evidence.restore(ROOT,records[0])
    return ex.ordinary(AREA.parent/'commands'/BATCH/cid/part).read_bytes()


def verified_command(cid,argv,key,stage):
    receipt=json.loads(command_bytes(cid,'receipt.json'));stdout=command_bytes(cid,'stdout.txt');stderr=command_bytes(cid,'stderr.txt')
    require(receipt['taskId']==TASK and receipt['runId']==BATCH and receipt['commandId']==cid and receipt['stage']==stage
            and receipt['started'] is True and receipt['classification']=='SUCCESS' and receipt['exitCode']==0 and receipt['inputFingerprint']==key
            and receipt['commandSummary']['sha256']==ex.sha(ex.encoded(argv)),'COMMAND_IDENTITY')
    for raw,part in [(stdout,'stdout'),(stderr,'stderr')]:
        require(receipt[part]['sha256']==ex.sha(raw) and receipt[part]['sizeBytes']==len(raw),'COMMAND_STREAM')
    return stdout


def qualify_build(build,kind):
    import workflow_oracle_mapping_recovery_build_qualification as compiler
    manifest=json.loads(record_bytes('build-qualification-'+kind+'.json'))
    return compiler.validate(build,kind,root=ROOT,executed_root=EXECUTED_ROOT,frozen=frozen,
                             command_bytes=command_bytes,manifest=manifest)


def qualified_object(which,attempt):
    import workflow_oracle_mapping_object_recovery as objects
    require(which in ('actual','reference') and isinstance(attempt,str) and re.fullmatch('[0-9a-f]{32}',attempt),'OBJECT_ATTEMPT')
    row=json.loads(record_bytes('objects-'+which+'-'+attempt+'.json'))
    driver=json.loads(record_bytes('driver-'+attempt+'.json'))
    ref=json.loads(record_bytes('reference-created.json')) if which=='reference' else None
    if ref:
        plan=json.loads(record_bytes('reference-plan-'+ref['attempt']+'.json'))
        scope=plan['archiveScope']
        require(ref['taskId']==plan['taskId']==TASK and ref['runId']==plan['runId']==BATCH and ref['volume']==plan['name']==REFERENCE
                and ref['archiveSha256']==plan['archiveSha256']==scope['archive']==RUST_HASH and ref['coldVerified'] is True
                and ref['memberCount']==scope['members']==56 and (scope['sizeBytes'],scope['expandedBytes'])==(184320,87689)
                and set(scope['roots'])=={'.rustfs','.rustfs.sys',objects.BUCKET}
                and ref['image']==plan['image'] and ref['image'].split('@')[1]==platform.IMAGES['rustfs']
                and ref['mounts']==plan['mounts'] and plan['networkId']==NETS['platform-internal']
                and list(EXTRA['objects-reference'])==plan['quota'],'SEALED_REFERENCE')
        loader=ref['loaderId'];require(re.fullmatch('[0-9a-f]{64}',loader) and loader!=ref['id'],'REFERENCE_LOADER')
        key=ex.sha(ex.encoded([ref['id'],loader,REFERENCE,RUST_HASH,TAR_VERIFY]))
        require(not verified_command(ref['extractCommandId'],['docker','--context','desktop-linux','start','-a',loader],key,'reference-tar-extract-compare')
                and not command_bytes(ref['extractCommandId'],'stderr.txt'),'REFERENCE_COLD_BYTES')
        linked=json.loads(record_bytes('reference-postcondition.json'))
        argv=['docker','--context','desktop-linux','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',loader]
        require(verified_command(linked['loaderExitCommand'],argv,ex.sha(ex.encoded(argv)),'ref-loader-status').decode().strip()=='exited|0|false','REFERENCE_COLD_EXIT')
    service=ref['id'] if ref else ALT_IDS['rustfs'];volume=objects.VOLUMES[which]
    build=driver['driver'];compile_rec=json.loads(command_bytes(build['commandId'],'receipt.json'))
    require(row['taskId']==TASK and row['runId']==BATCH and row['base']==BASE and row['resourceRun']==RUN and row['serviceId']==service
            and row['volume']==volume and row['attempt']==attempt==driver['attempt'] and row['verifier']==driver['id'] and row['driver']==build
            and row['role']==which and driver['role']=='objects-reader' and row['stderrSha256']==ex.sha(command_bytes(row['commandId'],'stderr.txt'))
            and row['after']==['exited','0','false'] and row['exitCode']==0 and row['qualification']=='OBSERVED'
            and compile_rec['stage']=='compile-objects' and compile_rec['inputFingerprint']==build['inputFingerprint'] and compile_rec['exitCode']==0
            and build['sourceSha256']==ex.sha(objects.DRIVER.read_bytes()),'OBSERVATION_IDENTITY')
    qualify_build(build,'objects')
    expected=objects.request(which,service,volume,build['dllSha256'],attempt)
    argv=['docker','--context','desktop-linux','start','-a','-i',driver['id']]
    raw=verified_command(row['commandId'],argv,expected['inputFingerprint'],'rustfs-inventory-'+which)
    result=json.loads(raw)
    require(row['argv']==argv and row['input']==expected and row['result']==result and row['stdoutSha256']==ex.sha(raw)
            and row['inputFingerprint']==expected['inputFingerprint'] and row['stdinSha256']==ex.sha(ex.encoded(expected)),'OBSERVATION_BYTES')
    objects.inspect_observation(result,expected)
    return result,expected


def prior_qualifications():
    data=frozen('checkpoint-ca3d35a7e5f94e539cd24ec39b8f7c0b.json')
    stable=data['observation']['stable']
    pg=frozen('pg-restored-ca3d35a7e5f94e539cd24ec39b8f7c0b.json')
    base=frozen('pg-baseline-0e8c1a69fbe5401292061ac13dda2874.json')
    first=frozen('graphs-restored.json');second=frozen('graphs-second-open.json');restored=frozen('restored-fuseki.json')
    ledger=frozen('archive-ledger.json')['archives']
    require(data['exitCode']==0 and pg['stable']==base['stable'] and pg['stableSha256']==data['pgSha256']==ex.sha(ex.encoded(pg['stable']))
            and len(pg['stable']['tables'])==48 and stable['oracle']['counts']==[1,1] and len(stable['oracle']['fields'])==11
            and stable['oracle']['tcps'] and len(stable['keys']['results'])==1 and pg['stable']['hold']['recoverAudit']==1,'PRIOR_PG_SOURCE_KEYS')
    require(first['id']==second['id']==restored['replacementId'] and restored['archiveHashes']==[ledger['platform/fuseki.tar']['sha256']]
            and first['scan']==second['scan'] and first['graphs']==second['graphs'] and first['originalShutdownHook']=='UNKNOWN'
            and first['scan']['default']['rows']==0 and first['scan']['named']['rows']==1372
            and [g['triples'] for g in first['graphs']]==[46,1326] and first['shapesSourceSha256']==pg['stable']['shapesHash'],'PRIOR_GRAPHS')
    return dict(mode='REUSED',pg=pg['stableSha256'],oracleRows=[1,1],keyring='PROTECTED_RESULT_VERIFIED',
                fuseki='ACCEPTED_FOR_FROZEN_CHECKPOINT',fusekiId=first['id'],archive=restored['archiveHashes'][0],shutdownHook='UNKNOWN')


def qualified_identity(row):
    import workflow_oracle_mapping_identity_recovery as identity
    import workflow_oracle_mapping_checkpoint as checkpoint
    require(isinstance(row.get('attempt'),str) and re.fullmatch('[0-9a-f]{32}',row['attempt']),'AUTH_ATTEMPT')
    host=json.loads(record_bytes('driver-'+row['attempt']+'.json'))
    require(row['taskId']==TASK and row['runId']==BATCH and row['base']==BASE and row['resourceRun']==RUN
            and row['pg']==ALT_IDS['platform-pg'] and row['idp']==ALT_IDS['keycloak-test'] and host['id']==row['id']
            and host['attempt']==row['attempt'] and host['role']=='identity-host' and host['driver']==row['driver'],'AUTH_QUALIFICATION')
    qualify_build(host['driver'],'identity')
    fixture=record_bytes('runtime-fixture.json')
    basis=identity.frozen_inputs(ROOT,fixture_bytes=fixture)
    fp=ex.sha(ex.encoded([TASK,BATCH,BASE,host['id'],host['attempt'],host['driver']['dllSha256'],basis,ALT_IDS['platform-pg'],ALT_IDS['keycloak-test']]))
    require(row['frozenInputs']==basis and row['inputFingerprint']==fp and host['driver']['sourceSha256']==ex.sha((ROOT/'scripts/maintenance'/(SOURCES['identity']+'.cs.txt')).read_bytes()),'AUTH_INPUT')
    argv=['docker','--context','desktop-linux','start',host['id']]
    require(row['argv']==argv and verified_command(row['commandId'],argv,fp,'dedicated-auth-start').decode().strip()==host['id'],'AUTH_COMMAND')
    raw=verified_command(row['eventCommand'],['docker','--context','desktop-linux','logs',host['id']],fp,'auth-redacted-events')
    events=[json.loads(line) for line in raw.splitlines()]
    require(events==row['events'],'AUTH_SEQUENCE')
    fresh=identity.qualify_partial(events,host['attempt'],row['startedMs'],row['endMs'])
    if fresh['status']=='WAITING_FOR_USER_AUTH':
        handoff=json.loads(record_bytes('manual-handoff.json'))
        require(handoff['taskId']==TASK and handoff['runId']==BATCH and handoff['attempt']==row['attempt']
                and handoff['hostId']==row['id'] and handoff['entry']==identity.LOGIN,'AUTH_HANDOFF')
    require(row['before']['pg']['stable']==frozen('pg-baseline-0e8c1a69fbe5401292061ac13dda2874.json')['stable'],'AUTH_BASELINE')
    for name in ('before','after'):
        st=row[name];db=st['pg']
        require(db['containerId']==ALT_IDS['platform-pg'] and db['stableSha256']==ex.sha(ex.encoded(db['stable'])),'AUTH_PG_SNAPSHOT')
        require((db['taskId'],db['runId'],db['attempt'])==(TASK,RUN,row['attempt']),'AUTH_PG_IDENTITY')
        pg_id=ALT_IDS['platform-pg']
        identity_argv=['docker','--context','desktop-linux','inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.State.Status}}',pg_id]
        snapshot=ex.sha(Path(checkpoint.__file__).read_bytes())
        def reopen_pg(cid,argv,stdin,kind):
            key=ex.sha(ex.encoded([pg_id,row['attempt'],argv,ex.sha(stdin),snapshot]))
            return verified_command(cid,argv,key,'omq-recovery-checkpoint-'+kind)
        observed=reopen_pg(db['identityCommandId'],identity_argv,b'','identity').decode().strip().split('|')
        require(observed==[pg_id,platform.IMAGES['platform-pg'],TASK,RUN,'running'],'AUTH_PG_OWNER')
        sql=checkpoint.pg_sql(json.loads(fixture),'4239ea404d924bbcae5e4ec41ad4cc27')
        data_argv=['docker','--context','desktop-linux','exec','-i','--user','postgres',pg_id,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
        rows=[json.loads(line) for line in reopen_pg(db['commandId'],data_argv,sql,'rows').splitlines()]
        tables={v['name']:dict(count=v['count'],sha256=v['sha256']) for v in rows if v['kind']=='table'}
        require(tables==db['stable']['tables'] and len(tables)==48 and [v for v in rows if v['kind']=='hold']==[db['stable']['hold']],'AUTH_PG_TABLE_BYTES')
        raw=json.loads(command_bytes(st['epochCommand'],'stdout.txt'))
        receipt=json.loads(command_bytes(st['epochCommand'],'receipt.json'))
        epoch_argv=['docker','--context','desktop-linux','exec','-i','--user','postgres',ALT_IDS['platform-pg'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
        verified_command(st['epochCommand'],epoch_argv,ex.sha(ex.encoded(epoch_argv)+identity.epoch_details_sql()),'oidc-epoch-'+name)
        require(raw==st['details'] and receipt['exitCode']==0,'AUTH_PG_EPOCH')
    writes=identity.qualify_pg(row['before']['pg'],row['after']['pg'],fresh,row['before']['details'],row['after']['details'])
    require(writes==row['pgWrites'] and row['status']==fresh['status'],'AUTH_STABLE_WRITES')
    return dict(status=fresh['status'],subjects=sorted(fresh['subjects']),writes=writes)


def aggregate():
    """两个分项各自重开真实命令和冻结身份，独立保留部分成立和失败。"""
    import workflow_oracle_mapping_object_recovery as objects
    rerun=json.loads(record_bytes('selected-attempts.json'))
    require((rerun['taskId'],rerun['runId'],rerun['base'])==(TASK,BATCH,BASE),'AGGREGATE_ID')
    components={'prior':prior_qualifications()}
    for component in ('rustfs','oidc'):
        try:
            if component=='rustfs':
                actual,areq=qualified_object('actual',rerun['actual'])
                reference,rreq=qualified_object('reference',rerun['reference'])
                components[component]=objects.qualify(actual,reference,areq,rreq)
            else:
                result=json.loads(record_bytes('auth-ended-'+rerun['identity']+'.json'))
                components[component]=qualified_identity(result)
        except (ValueError,KeyError,FileNotFoundError,TypeError) as error:
            reason=str(error)
            components[component]=dict(status='BLOCKED',reason=reason if re.fullmatch(r"[A-Za-z0-9_'-]{1,140}",reason) else type(error).__name__)
    passed=(components['rustfs']['status']=='RUSTFS_FROZEN_VERSIONS_VERIFIED' and components['oidc']['status']=='FOUR_NORMAL_AUTHENTICATIONS_VERIFIED')
    return dict(taskId=TASK,runId=BATCH,base=BASE,status='PASS_FOR_FROZEN_CHECKPOINT' if passed else 'BLOCKED',
                components=components,oracleS0='BLOCKED',cleanup250ms='NOT_QUALIFIED',g4='PARTIAL')
