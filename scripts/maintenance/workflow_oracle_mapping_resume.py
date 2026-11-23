"""正式 Oracle 恢复窗口：原五副本、两个无状态 API 与现有阶段资源核验。"""
import json
import os
import re
import uuid
from pathlib import Path

import workflow_execution as ex
import workflow_oracle_mapping_platform as platform
import workflow_oracle_mapping_platform_recovery as recovery
from workflow_oracle_mapping_resources import RUN, TASK, before_source, require

PRODUCT = 'product-resume-01'
PROJECT = 'ontology-g4-omq-product-resume-01'
ROOT = platform.ROOT
AREA = platform.AREA.parent / PRODUCT
APIS = ('api', 'api-secondary')
REGISTRY = AREA / 'formal-resources.json'
BASE = platform.AREA
RESTORED = platform.HOME_DIR / recovery.RECOVERY / 'restored-host'
SOURCE_NETWORK = 'source-internal'


def load(path):
    return json.loads(ex.ordinary(path).read_bytes())


def command(stage, args, timeout=30):
    result = ex.run(['docker', '--context', 'desktop-linux', *args], ROOT, task=TASK, run_id=PRODUCT,
                    stage=stage, timeout=timeout, input_key=ex.sha(ex.encoded(args)))
    require(result.returncode == 0, stage + '_' + result.receipt['commandId'])
    return result.stdout.decode().strip(), result.receipt['commandId']


def replacement_source():
    previous = load(BASE / 'recovery-01-final.json')
    source = load(BASE / 'source-create-01.json')
    require(previous['originalId'] == source['containerId'] and previous['replacementId'] == recovery.ALT_ORACLE, 'PRODUCT_SOURCE')
    return {**source, 'containerId': previous['replacementId'], 'volume': previous['replacementVolume'],
            'network': previous['network'], 'networkId': load(BASE / 'recovery-01.json')['replacementNetworkId']}


def data():
    row = load(recovery.RECOVERY_AREA / 'replacement-resources.json')
    require(row['taskId'] == TASK and row['project'] == recovery.ALT_PROJECT and set(row['ids']) == set(platform.VOLUMES), 'PRODUCT_DATA')
    source = replacement_source()
    return {**row['ids'], 'oracle': source['containerId']}, {**row['networks'], SOURCE_NETWORK: source['networkId'].split()[0]}


def manifest():
    require(not (AREA/'formal-api-refresh.json').exists(),'PRODUCT_REFRESH_PENDING')
    row = load(REGISTRY)
    ids, nets = data()
    require(row['taskId'] == TASK and row['runId'] == PRODUCT and row['project'] == PROJECT and row['networks'] == nets
            and {k: v for k, v in row['ids'].items() if k not in APIS} == ids, 'PRODUCT_MANIFEST')
    return row


def save_manifest(row):
    payload = (json.dumps(row, indent=2) + '\n').encode()
    history = AREA / ('formal-resources-' + ex.sha(payload) + '.json')
    if history.exists():
        require(history.read_bytes() == payload, 'PRODUCT_MANIFEST_HASH')
    else:
        with history.open('xb') as stream:
            stream.write(payload)
    temp = REGISTRY.with_suffix('.next')
    with temp.open('xb') as stream:
        stream.write(payload)
    temp.replace(REGISTRY)


def net_names():
    return {k: recovery.ALT_PROJECT + '_' + k for k in ('host-entry', 'platform-internal')} | {SOURCE_NETWORK: replacement_source()['network']}


def inspect_product_stage(area, roles, docker):
    active = set(roles)
    require(active <= set(platform.VOLUMES) | {'oracle', *APIS}, 'PRODUCT_ROLES')
    known, ram, cpu, ports, replacement = recovery.phase_inventory(area, 'restore', active - set(APIS), docker)
    apis = {k: v for k,v in (manifest()['ids'] if REGISTRY.exists() else {}).items() if k in APIS}
    require(active.intersection(APIS) <= set(apis), 'PRODUCT_UNREGISTERED_API')
    for role, cid in apis.items():
        expected_port = platform.PORTS['api' if role == 'api' else 'secondary']
        fmt = '{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Status}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .HostConfig.PortBindings}}|{{json .Mounts}}|{{json .NetworkSettings.Networks}}|{{.HostConfig.ReadonlyRootfs}}'
        f = docker('product-'+role, 'inspect', '-f', fmt, cid).split('|')
        require(f[:6] == [cid,platform.IMAGES[role],TASK,PRODUCT,PROJECT,role] and f[7:9] == ['805306368','500000000']
                and json.loads(f[9]) == {'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(expected_port)}]} and f[12]=='true','PRODUCT_API_OWNER')
        require(f[6] == 'running' if role in active else f[6] in ('created','exited'), 'PRODUCT_API_STATE')
        spec = load(AREA/'formal-api-compose.json')['services'][role]
        expected={v.split(':')[1]:v.split(':')[0] for v in spec['volumes']}
        mounts=json.loads(f[10])
        binds={m['Destination']:m['Source'].removeprefix('/host_mnt') for m in mounts if m['Type']=='bind'}
        require(binds==expected and all((m['Type']=='bind' and not m['RW']) or
                (m['Type']=='tmpfs' and m['Destination']=='/tmp') for m in mounts),'PRODUCT_API_MOUNTS')
        if role in active:
            expectnets={v:manifest()['networks'][k] for k,v in net_names().items()}
            require({k:v['NetworkID'] for k,v in json.loads(f[11]).items()}==expectnets,'PRODUCT_API_NETWORK')
            known.add(cid);ram+=805306368;cpu+=500000000;ports.add(expected_port)
    return known,ram,cpu,ports,{**replacement,'extraIds':apis,'extraRun':PRODUCT}


def running_roles():
    ids = manifest()['ids'] if REGISTRY.exists() else data()[0]
    names = sorted(ids)
    states,_ = command('resume-phase-state',['inspect','-f','{{.Id}} {{.State.Status}}',*[ids[k] for k in names]])
    active=set()
    for name,line in zip(names,states.splitlines(),strict=True):
        cid,state=line.split()
        require(cid==ids[name] and state in ('running','created','exited'),'PRODUCT_CURRENT_ID')
        if state=='running': active.add(name)
    return active


def admit(planned=()):
    active=running_roles()
    from workflow_oracle_mapping_capacity import before_product_source
    return before_product_source(ROOT,TASK,platform_stage=True,phase=PRODUCT,running_roles=active,planned_roles=active|set(planned))


def bound_build(target):
    binding=platform.build.validate(target,TASK)
    args=load(BASE.parent/(target+'-build-binding.json'))['command']
    digest=ex.sha(ex.encoded(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*args]))
    events=(BASE.parent/'command-events.jsonl').read_text().splitlines()
    row=next(json.loads(s) for s in reversed(events) if json.loads(s).get('exitCode')==0 and
             json.loads(s).get('inputFingerprint')==binding['inputKey'] and json.loads(s)['commandSummary']['sha256']==digest)
    return binding,row


def _refresh_write(path, payload, replace):
    import os
    import tempfile
    path = ex.ordinary(path)
    if path.exists() and path.read_bytes() == payload:
        return
    require(replace or not path.exists(), 'PRODUCT_BINDING_ARCHIVE')
    with tempfile.NamedTemporaryFile(dir=AREA, prefix='.refresh-', delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
            if replace:
                temp.replace(path)
            else:
                os.link(temp,path)
        finally:
            temp.unlink(missing_ok=True)


def _refresh_projection(files, replacements=None):
    """清单最后提交。恢复只接受登记的旧/新字节，归档及失败暂存件原样保留。"""
    journal = ex.ordinary(AREA/'formal-api-refresh.json')

    def archive(path, digest):
        require(isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest), 'PRODUCT_BINDING_ARCHIVE')
        return ex.ordinary(path.with_name(path.stem+'-'+digest+'.json'))

    def hashes():
        return [ex.sha(ex.ordinary(path).read_bytes()) if path.exists() else None for path in files]

    if replacements is not None:
        require(not journal.exists() and len(files)==len(replacements)==3 and files[-1]==REGISTRY, 'PRODUCT_REFRESH_BUSY')
        before = hashes()
        after = [ex.sha(raw) for raw in replacements]
        for path, old, raw in zip(files,before,replacements,strict=True):
            if old is not None:
                _refresh_write(archive(path,old),path.read_bytes(),False)
            _refresh_write(archive(path,ex.sha(raw)),raw,False)
        tx = dict(taskId=TASK,runId=PRODUCT,files=[p.name for p in files],before=before,after=after)
        _refresh_write(journal,ex.encoded(tx),False)

    if journal.exists():
        tx = load(journal)
        require((tx['taskId'],tx['runId'],tx['files'])==(TASK,PRODUCT,[p.name for p in files])
                and len(tx['before'])==len(tx['after'])==3 and files[-1]==REGISTRY, 'PRODUCT_REFRESH_IDENTITY')
        after = []
        for path,previous,new,actual in zip(files,tx['before'],tx['after'],hashes(),strict=True):
            require(actual in (previous,new), 'PRODUCT_REFRESH_FOREIGN_BYTES')
            if previous is not None:
                require(ex.sha(archive(path,previous).read_bytes())==previous, 'PRODUCT_BINDING_ARCHIVE')
            raw = archive(path,new).read_bytes()
            require(ex.sha(raw)==new, 'PRODUCT_BINDING_ARCHIVE')
            after.append(raw)
        inputs,recipe,registry = map(json.loads,after)
        require(inputs['taskId']==registry['taskId']==TASK and inputs['runId']==registry['runId']==PRODUCT
                and inputs['snapshotId']==registry['snapshotId'] and registry['project']==recipe['name']==PROJECT
                and inputs['composeSha256']==tx['after'][1] and registry['inputsSha256']==tx['after'][0]
                and not set(APIS).intersection(registry['ids']), 'PRODUCT_REFRESH_GENERATION')
        for path,raw in zip(files,after,strict=True):
            _refresh_write(path,raw,True)
        require(hashes()==tx['after'], 'PRODUCT_REFRESH_COMMIT')
        journal.unlink()


def prepare():
    input_path=AREA/'formal-api-inputs.json'
    compose_path=AREA/'formal-api-compose.json'
    projections=(input_path,compose_path,REGISTRY)
    _refresh_projection(projections)
    previous=manifest() if REGISTRY.exists() else None
    require(not previous or not set(APIS).intersection(previous['ids']),'PRODUCT_BIND_BEFORE_CREATE')
    previous_inputs=load(input_path) if previous else {}
    if previous:
        require(previous_inputs['snapshotId']==previous['snapshotId'] and
                previous_inputs['composeSha256']==ex.sha(compose_path.read_bytes()) and
                previous.get('inputsSha256',ex.sha(input_path.read_bytes()))==ex.sha(input_path.read_bytes()),'PRODUCT_PREVIOUS_BINDING')
    else:
        require(not input_path.exists() and not compose_path.exists(), 'PRODUCT_ORPHAN_BINDING')
    admission=admit(APIS)
    ids,nets=data()
    old=load(BASE/'formal-api-inputs.json')
    specpath=BASE/'formal-api-compose.json'
    relay=BASE/'formal-relay'
    require(ex.sha(specpath.read_bytes())==old['composeSha256'] and ex.sha((relay/'OracleRelay.dll').read_bytes())==old['relaySha256'],'PRODUCT_OLD_RUNTIME')
    spec=load(specpath)
    require(set(spec['services'])==set(APIS),'PRODUCT_API_RECIPE')
    builds={}
    for target in ('api','query','agent'):
        binding,row=bound_build(target)
        output=ROOT/Path(platform.build.TARGETS[target]).parent/'bin/Debug/net10.0'
        disk=admit(APIS)['platformDisk'] if builds else admission['platformDisk']
        snap=platform.snapshots.freeze(ROOT,output,AREA/'runtime-snapshots',binding,row['commandId'],
              {'toolEnvironment':row['environmentFingerprint']},task=TASK,run_id=PRODUCT,
              remaining_bytes=disk['ceilingBytes']-disk['totalBytes'])
        receipt=ex.ordinary(BASE.parent/(target+'-build-binding.json')).read_bytes()
        prefix=str(output.relative_to(ROOT))+'/'
        registered={k.removeprefix(prefix):v for k,v in json.loads(receipt)['outputs'].items() if k.startswith(prefix)}
        require(ex.sha(receipt)==binding['receiptSha256'] and registered==snap['files'],'PRODUCT_BUILD_OUTPUTS')
        builds[target]=(binding,row,snap)
    binding,row,snap=builds['api']
    spec['name']=PROJECT
    spec['networks']={k:{'external':True,'name':v} for k,v in net_names().items()}
    diagnostic_key=os.environ.get('OMQ_NORMAL_DIAGNOSTIC_KEY')
    if diagnostic_key is not None:
        require(re.fullmatch('[0-9a-f]{32}',diagnostic_key) and os.environ.get('OMQ_PRODUCT_RUN')==PRODUCT,'NORMAL_DIAGNOSTIC_SCOPE')
        spec['services']['api']['environment']['G4__OracleDiagnosticKey']=diagnostic_key
    for role,service in spec['services'].items():
        service['labels']['ontology.run']=PRODUCT
        service['environment'].update({name:'false' for name in ('Governance__ApplyMigrations','Governance__SeedDevelopmentResources','G2__ApplyMigrations','G4__ApplyMigrations')})
        targets={'/app':ROOT/snap['directory'],'/private/api':RESTORED/'platform/api',
                 '/private/oracle-wallet':RESTORED/'reader/client-wallet','/runtime':relay,
                 '/keyring':RESTORED/'platform/keyring','/query-keyring':RESTORED/'platform/query-keyring'}
        require(all(path.is_dir() and not path.is_symlink() for path in targets.values()),'PRODUCT_BIND_MATERIAL')
        if role=='api-secondary':
            targets['/query-tests']=ROOT/builds['query'][2]['directory']
            targets['/session-tests']=ROOT/builds['agent'][2]['directory']
        service['volumes']=[str(path)+':'+target+':ro' for target,path in targets.items()]
    compose_bytes=(json.dumps(spec,indent=2)+'\n').encode()
    inp={**old,'runId':PRODUCT,'build':binding,'snapshotId':snap['snapshotId'],'buildCommandId':row['commandId'],
         'composeSha256':ex.sha(compose_bytes),'querySnapshotId':builds['query'][2]['snapshotId'],
         'sessionSnapshotId':builds['agent'][2]['snapshotId']}
    input_bytes=(json.dumps(inp,indent=2)+'\n').encode()
    registration=dict(taskId=TASK,runId=PRODUCT,project=PROJECT,ids=ids,networks=nets,snapshotId=snap['snapshotId'],
                      apiBuildId=row['commandId'],buildOutputKey=binding['outputKey'],inputsSha256=ex.sha(input_bytes))
    if diagnostic_key:
        registration['normalDiagnosticKey']=diagnostic_key
    unchanged=previous and all(previous.get(key)==value for key,value in registration.items())
    registration['admission']=previous['admission'] if unchanged else admission['attempt']
    registry_bytes=(json.dumps(registration,indent=2)+'\n').encode()
    if unchanged and previous_inputs==inp and compose_path.read_bytes()==compose_bytes:
        return previous
    state_bytes=b''
    if not previous:
        state=load(BASE/'runtime-fixture.json')
        require((state['taskId'],state['runId'])==(TASK,RUN),'PRODUCT_RUNTIME_FIXTURE')
        fixture=AREA/'runtime-fixture.json'
        expected={**state,'runId':PRODUCT}
        state_bytes=(json.dumps(expected,indent=2)+'\n').encode()
    new_bytes=sum(map(len,(input_bytes,compose_bytes,registry_bytes,state_bytes)))
    old_bytes=sum(p.stat().st_size for p in projections if p.exists())
    # 预留两代的内容归档、当前投影、原子提交暂存及目录元数据。
    disk=admit(APIS)['platformDisk']
    require(3*(new_bytes+old_bytes)+256*1024 <= disk['ceilingBytes']-disk['totalBytes'],'PRODUCT_REFRESH_BUDGET')
    if state_bytes:
        _refresh_write(fixture,state_bytes,False)
    _refresh_projection(projections,[input_bytes,compose_bytes,registry_bytes])
    return registration


def create(role):
    require(role in APIS and role not in manifest()['ids'],'PRODUCT_CREATE_ROLE')
    admit([role])
    spec=AREA/'formal-api-compose.json'
    require(ex.sha(spec.read_bytes())==load(AREA/'formal-api-inputs.json')['composeSha256'],'PRODUCT_SPEC')
    if role=='api-secondary':
        inp=load(AREA/'formal-api-inputs.json')
        snapshot=current_session_snapshot(inp)
        verify_session_recipe(load(spec),snapshot)
    args=['compose','-f',str(spec)]
    command('resume-create-'+role,[*args,'create','--no-build','--pull','never',role])
    cid,_=command('resume-id-'+role,[*args,'ps','--all','-q',role])
    require(re.fullmatch('[0-9a-f]{64}',cid),'PRODUCT_CREATED_ID')
    row=manifest();row['ids'][role]=cid;save_manifest(row)
    admit()
    return cid


def host_binding():
    rec=manifest();inp=load(AREA/'formal-api-inputs.json')
    require(platform.build.validate('api',TASK)==inp['build'] and set(rec['ids'])==set(platform.VOLUMES)|{'oracle',*APIS},'PRODUCT_HOST_BUILD')
    snap=load(AREA/'runtime-snapshots'/(inp['snapshotId']+'.json'))
    source=replacement_source();ids={k:v for k,v in rec['ids'].items() if k!='oracle'}
    names=sorted(ids)
    args=['docker','--context','desktop-linux','inspect','-f',platform.HOST_FORMAT,*[ids[k] for k in names],source['containerId']]
    result=ex.run(args,ROOT,task=TASK,run_id=PRODUCT,stage='omq-host-inspect',
        input_key=ex.sha(ex.encoded([inp,ids,source['containerId'],platform.HOST_FORMAT])),timeout=12)
    require(result.returncode==0,'PRODUCT_HOST_INSPECT')
    services={};netnames=net_names()
    for role,line in zip([*names,'oracle'],result.stdout.decode().strip().splitlines(),strict=True):
        cid,image,owner,run,state,pid,started,mounts,nets=line.split('|')
        expect={netnames['platform-internal']:rec['networks']['platform-internal']} if role!='oracle' else {}
        if role in (*APIS,'keycloak-test'):expect[netnames['host-entry']]=rec['networks']['host-entry']
        if role in (*APIS,'oracle'):expect[netnames[SOURCE_NETWORK]]=rec['networks'][SOURCE_NETWORK]
        networks=dict(x.split('=') for x in nets.split())
        require(cid==rec['ids'][role] and owner==TASK and run==(PRODUCT if role in APIS else RUN)
                and state=='running' and int(pid)>0 and networks==expect,'PRODUCT_HOST_RUNTIME')
        if role=='oracle':
            require(image==platform.SOURCE.split('@')[1],'PRODUCT_HOST_SOURCE_IMAGE')
            continue
        require(image==platform.IMAGES[role],'PRODUCT_HOST_IMAGE')
        if role=='fuseki':recovery.require_current_fuseki(cid,started,int(pid))
        if role in APIS:platform.snapshots.demand_mount(ROOT,snap,json.loads(mounts),task=TASK,run_id=PRODUCT)
        if role=='api-secondary':
            for destination, field in (('/query-tests','querySnapshotId'),('/session-tests','sessionSnapshotId')):
                snapshot_id=inp.get(field,'')
                require(re.fullmatch('[0-9a-f]{64}',snapshot_id),'PRODUCT_TEST_SNAPSHOT_ID')
                expected=str(AREA/'runtime-snapshots'/snapshot_id)
                mounts_at_path=[m for m in json.loads(mounts) if m['Destination']==destination or m['Destination'].startswith(destination+'/')]
                require(len(mounts_at_path)==1 and mounts_at_path[0]['Destination']==destination and mounts_at_path[0]['Type']=='bind'
                        and mounts_at_path[0]['RW'] is False and mounts_at_path[0]['Source'].removeprefix('/host_mnt')==expected,'PRODUCT_TEST_LIVE_MOUNT')
        services[role]=dict(containerId=cid,imageId=image,pid=int(pid),startedAt=started,mountSha256=ex.sha(ex.encoded(json.loads(mounts))),networks=networks)
    require(inp['composeSha256']==ex.sha((AREA/'formal-api-compose.json').read_bytes()) and inp['relaySha256']==ex.sha((BASE/'formal-relay/OracleRelay.dll').read_bytes()),'PRODUCT_INPUT_DRIFT')
    return dict(taskId=TASK,runId=PRODUCT,ports=platform.PORTS,commandId=result.receipt['commandId'],snapshotId=inp['snapshotId'],
                buildInputKey=inp['build']['inputKey'],buildOutputKey=inp['build']['outputKey'],runtimeHelperSha256=inp['relaySha256'],
                composeSha256=inp['composeSha256'],resourceManifestSha256=ex.sha(REGISTRY.read_bytes()),services=services,
                oracle=dict(containerId=source['containerId'],imageId=platform.SOURCE.split('@')[1],networkId=rec['networks'][SOURCE_NETWORK]))


def current_session_snapshot(inputs):
    """验证期望目录、冻结字节、当前构建回执与实际程序集输出的一致性。"""
    snapshot_id=inputs.get('sessionSnapshotId','')
    require(re.fullmatch('[0-9a-f]{64}',snapshot_id),'PRODUCT_SESSION_SNAPSHOT_ID')
    snapshot=load(AREA/'runtime-snapshots'/(snapshot_id+'.json'))
    require(snapshot['snapshotId']==snapshot_id and ROOT/snapshot['directory']==AREA/'runtime-snapshots'/snapshot_id,
            'PRODUCT_SESSION_SNAPSHOT_DIRECTORY')
    platform.snapshots.verify(ROOT,snapshot,task=TASK,run_id=PRODUCT)
    binding,row=bound_build('agent')
    raw=ex.ordinary(BASE.parent/'agent-build-binding.json').read_bytes()
    require(ex.sha(raw)==binding['receiptSha256'],'PRODUCT_SESSION_BUILD')
    receipt=json.loads(raw)
    prefix=str(Path(platform.build.TARGETS['agent']).parent/'bin/Debug/net10.0')+'/'
    files={k.removeprefix(prefix):v for k,v in receipt['outputs'].items() if k.startswith(prefix)}
    require(binding==snapshot['inputs'] and row['commandId']==snapshot['commandId'] and files==snapshot['files']
            and 'OntologyPlatform.AgentTests.dll' in files,'PRODUCT_SESSION_BUILD')
    return snapshot


def verify_session_recipe(spec,snapshot):
    """创建容器前只接受一个指向已核目录的只读会话程序集挂载，排除子路径遮盖。"""
    mounts=spec['services']['api-secondary']['volumes']
    matching=[m for m in mounts if isinstance(m,str) and len(m.rsplit(':',2))>=2 and
              (m.split(':')[1]=='/session-tests' or m.split(':')[1].startswith('/session-tests/'))]
    require(all(isinstance(m,str) for m in mounts) and matching==[str(ROOT/snapshot['directory'])+':/session-tests:ro'],
            'PRODUCT_SESSION_RECIPE')


def bind_session_tests():
    """在创建容器前把既有票据检查装入副实例的只读测试快照。"""
    rec=manifest()
    require(not set(APIS).intersection(rec['ids']),'PRODUCT_BIND_BEFORE_CREATE')
    specpath=AREA/'formal-api-compose.json';inpath=AREA/'formal-api-inputs.json'
    spec=load(specpath);inputs=load(inpath)
    require(ex.sha(specpath.read_bytes())==inputs['composeSha256'],'PRODUCT_SPEC')
    binding,row=bound_build('agent')
    if 'sessionSnapshotId' in inputs:
        previous_id=inputs['sessionSnapshotId']
        require(re.fullmatch('[0-9a-f]{64}',previous_id),'PRODUCT_SESSION_SNAPSHOT_ID')
        previous=load(AREA/'runtime-snapshots'/(previous_id+'.json'))
        require(previous['snapshotId']==previous_id and ROOT/previous['directory']==AREA/'runtime-snapshots'/previous_id,
                'PRODUCT_SESSION_SNAPSHOT_DIRECTORY')
        platform.snapshots.verify(ROOT,previous,task=TASK,run_id=PRODUCT)
        verify_session_recipe(spec,previous)
        if binding==previous['inputs'] and row['commandId']==previous['commandId']:
            return current_session_snapshot(inputs)['snapshotId']
        spec['services']['api-secondary']['volumes'].remove(str(ROOT/previous['directory'])+':/session-tests:ro')
    admission=admit(APIS)
    source=ROOT/Path(platform.build.TARGETS['agent']).parent/'bin/Debug/net10.0'
    # 新 API 输入重建后仍可沿用同一次 Agent 构建的准确已封存快照。
    retained=[]
    for path in (AREA/'runtime-snapshots').glob('*.json'):
        candidate=load(path)
        if candidate.get('inputs')==binding and candidate.get('commandId')==row['commandId']:
            require(path.stem==candidate['snapshotId'],'PRODUCT_SESSION_SNAPSHOT_ID')
            retained.append(candidate)
    require(len(retained)<=1,'PRODUCT_SESSION_SNAPSHOT_AMBIGUOUS')
    if retained:
        snap=current_session_snapshot(dict(sessionSnapshotId=retained[0]['snapshotId']))
    else:
        size=sum(p.stat().st_blocks*512 for p in source.rglob('*') if p.is_file())
        require(size+admission['platformDisk']['totalBytes']<=admission['platformDisk']['ceilingBytes'],'PRODUCT_SESSION_SNAPSHOT_COST')
        snap=platform.snapshots.freeze(ROOT,source,AREA/'runtime-snapshots',binding,row['commandId'],
                                      {'toolEnvironment':row['environmentFingerprint']},task=TASK,run_id=PRODUCT)
    spec['services']['api-secondary']['volumes'].append(str(ROOT/snap['directory'])+':/session-tests:ro')
    verify_session_recipe(spec,snap)
    current_session_snapshot(dict(sessionSnapshotId=snap['snapshotId']))
    for original in (inpath,specpath):
        (AREA/(original.stem+'-'+ex.sha(original.read_bytes())+'.json')).write_bytes(original.read_bytes())
    platform.save(specpath,spec,True)
    inputs.update(sessionSnapshotId=snap['snapshotId'],composeSha256=ex.sha(specpath.read_bytes()))
    platform.save(inpath,inputs,True)
    return snap['snapshotId']


def session_failure_code(output):
    """只取正常消费者独占报告的末行，未知失败不能进入仅限 TTL 的处理。"""
    try:
        row=json.loads(output.splitlines()[-1])
    except (IndexError,ValueError):
        return 'PRODUCT_SESSION_REJECTED'
    known=('OMQ_SESSION_TICKET_UNAVAILABLE','OMQ_SESSION_SUBJECT_MISMATCH','OMQ_SESSION_REVOKED','OMQ_SESSION_TTL_INSUFFICIENT')
    return row['code'] if isinstance(row,dict) and set(row)=={'code'} and row['code'] in known else 'PRODUCT_SESSION_REJECTED'


def session_invocation(cid,nonce,seconds=210):
    """用公开 nonce 和准确副 API 身份构造真实调用，供资格消费者逐字重算。"""
    require(re.fullmatch('[0-9a-f]{64}',cid) and re.fullmatch('[0-9a-f]{32}',nonce) and seconds==210,'PRODUCT_SESSION_COMMAND')
    directory='/tmp/omq-session-probe-'+nonce
    runner=(f'set -eu; umask 077; d={directory}; mkdir -m 700 -- "$d"; '
            'trap \'rm -r -- "$d"\' EXIT; export G4_BROWSER_REPORT="$d/session-ready.json"; cd "$d"; '
            'rc=0; dotnet /session-tests/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline '
            '--minimum-expected-tests 1 --no-ansi --progress off --results-directory "$d/results" || rc=$?; if test -f "$G4_BROWSER_REPORT"; then cat "$G4_BROWSER_REPORT"; echo; fi; exit "$rc"')
    return ['docker','--context','desktop-linux','exec','-i','-e','HOME=/tmp','-e','DOTNET_CLI_HOME=/tmp',
          '-e','G4_BROWSER_PREFLIGHT=1','-e','G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,'-e','OMQ_SESSION_SECONDS='+str(seconds),
          cid,'/bin/sh','-ec',runner]


def verify_sessions(actors,seconds):
    """同一已准副 API 内运行既有票据检查。真实 Cookie 只交现有消费者的 stdin。"""
    from workflow_m2_evidence import mtp
    require(seconds==210 and len(actors)==4,'PRODUCT_SESSION_WINDOW')
    inp=load(AREA/'formal-api-inputs.json')
    binding=current_session_snapshot(inp)['inputs']
    host=host_binding()
    cid=host['services']['api-secondary']['containerId']
    # 验证程序在独占临时目录输出不含认证内容的结果，证据正文不记录 stdin。
    nonce=uuid.uuid4().hex
    args=session_invocation(cid,nonce,seconds)
    result=ex.run(args,ROOT,task=TASK,run_id=PRODUCT,stage='omq-session-real',stdin=ex.encoded(actors),
                  input_key=ex.sha(ex.encoded(binding)),parent_id=host['commandId'],timeout=22)
    if result.returncode!=0:
        reason=session_failure_code(result.stdout)
        require(False,reason+'_'+result.receipt['commandId'])
    mtp(result.stdout+result.stderr,1)
    obs=json.loads(result.stdout.splitlines()[-1])
    require([v['subjectId'] for v in obs]==[v['subjectId'] for v in actors],'PRODUCT_SESSION_SUBJECT')
    return dict(commandId=result.receipt['commandId'],nonce=nonce,observations=obs)


def save_api_observation(event,role,row):
    """后续登录窗口单独记录其实例 ID，保留首个窗口的入口和回收原件。"""
    name='api-'+event+'-'+role
    path=AREA/(name+'.json')
    if path.exists():
        path=AREA/(name+'-'+row['pre']+'.json')
    platform.save(path,row)


def start_api(role):
    """按准确 ID 启动，通过本机正式 /me 的匿名拒绝确认路由已监听。"""
    import http.client
    import time
    require(role in APIS and role not in running_roles(),'PRODUCT_START_STATE')
    pre=admit([role]);cid=manifest()['ids'][role]
    _,start=command('resume-start-'+role,['start',cid],timeout=40)
    port=platform.PORTS['api' if role=='api' else 'secondary']
    deadline=time.monotonic()+30
    status=None
    while time.monotonic()<deadline:
        client=http.client.HTTPConnection('127.0.0.1',port,timeout=1)
        try:
            client.request('GET','/api/v1/platform/me')
            status=client.getresponse().status
            if status==401:break
        except OSError:
            pass
        finally:
            client.close()
        state,_=command('resume-wait-'+role,['inspect','-f','{{.State.Status}} {{.State.OOMKilled}}',cid])
        require(state=='running false','PRODUCT_EARLY_EXIT_'+role)
        time.sleep(.5)
    require(status==401,'PRODUCT_ANONYMOUS_ME_'+str(status))
    post=admit()
    row=dict(taskId=TASK,runId=PRODUCT,role=role,id=cid,startCommand=start,pre=pre['attempt'],post=post['attempt'],anonymousMe=status)
    save_api_observation('ready',role,row)
    return row


METADATA_PROFILE = 'oracle-metadata-v2'
HISTORICAL_PROFILE = 'normal-v1'
METADATA_LIMIT = 128 * 1024
STATEMENTS = ('identity', 'privileges', 'attestation', 'directRead', 'catalog', 'physical')


def check_metadata_spans(source, *, component=False):
    """在已绑定宿主和命令的 profile 内核真实驱动边界及实际取行，同会话允许重复。"""
    require(source['profile'] == METADATA_PROFILE and source['kind'] == ('DIAGNOSTIC_ONLY' if component else 'product'),
            'METADATA_PROFILE')
    spans = source['metadata']
    require(isinstance(spans, list) and len(spans) <= (12 if component else 24), 'METADATA_COUNT')
    events = source['events']
    acquisitions = {e['execution']:e['acquisition'] for e in events if e['stage'] == 'acquisition'}
    groups = {}
    sessions = {}
    for ordinal, span in enumerate(spans, 1):
        fields = ('Statement Post Ordinal Execution Acquisition Begin End ExecuteBegin ExecuteEnd ReadTicks ReadCalls Rows '
                  'FirstRow Eof CursorDisposeBegin CursorDisposeEnd CommandDisposeBegin OperationError CursorError CommandError Session')
        require(isinstance(span, dict) and set(span) == set(fields.split()) and span['Ordinal'] == ordinal
                and type(span['Post']) is bool, 'METADATA_FIELDS')
        execution = span['Execution']
        acquisition = source['probe'] if component else acquisitions.get(execution)
        require(acquisition and acquisition == span['Acquisition'] and (not component or uuid.UUID(acquisition).hex == execution),
                'METADATA_EXECUTION')
        calls = groups.setdefault(execution, [])
        index = len(calls)
        require(index < 12 and (span['Statement'], span['Post']) == (STATEMENTS[index % 6], index >= 6), 'METADATA_ORDER')
        calls.append(span)
        times = [span[k] for k in ('Begin', 'ExecuteBegin', 'ExecuteEnd', 'FirstRow', 'Eof',
                                    'CursorDisposeBegin', 'CursorDisposeEnd', 'CommandDisposeBegin', 'End') if span[k] is not None]
        require(all(type(t) is int and t >= 0 for t in times) and times == sorted(times)
                and span['Begin'] is not None and span['End'] is not None and span['CommandDisposeBegin'] is not None
                and (span['ExecuteBegin'] is None) == (span['ExecuteEnd'] is None)
                and (span['CursorDisposeBegin'] is None) == (span['CursorDisposeEnd'] is None), 'METADATA_TIME')
        require(all(type(span[k]) is int and span[k] >= 0 for k in ('ReadTicks', 'ReadCalls', 'Rows'))
                and span['Rows'] + int(span['Eof'] is not None) <= span['ReadCalls']
                and bool(span['Rows']) == (span['FirstRow'] is not None)
                and all(span[k] is None or type(span[k]) is int and -2 <= span[k] <= 2147483647
                        for k in ('OperationError','CursorError','CommandError')), 'METADATA_READ')
        require(span['CursorError'] is None or span['CursorDisposeEnd'] is not None, 'METADATA_CURSOR_ERROR')
        if span['Statement'] == 'identity':
            require(span['ReadCalls'] <= 1 and span['Eof'] is None if span['Rows'] else span['ReadCalls'] <= 1,
                    'METADATA_IDENTITY_READ')
        if span['Statement'] == 'privileges':
            require(not span['ReadCalls'] and span['CursorDisposeBegin'] is None, 'METADATA_SCALAR')
        if span['Session'] is not None:
            session = span['Session']
            require(span['Statement'] == 'identity' and isinstance(session, list) and len(session) == 5
                    and all(type(n) is int and 0 < n < 2**64 for n in session)
                    and sessions.setdefault(execution, session) == session, 'METADATA_SESSION')
    if not component:
        for branch in (e for e in events if e['stage'] == 'branch'):
            execution = branch['execution']
            rows = [e for e in events if e['execution'] == execution]
            items = groups.get(execution, [])
            native = [e['session'] for e in rows if e['stage'] == 'session' and e['session']]
            require(not native or sessions.get(execution) == native[0], 'METADATA_SESSION_MISMATCH')
            for stage, low, high in [('readOnly',0,4),('catalog',4,6),('postcheck',6,12)]:
                enter = next((e for e in rows if e['stage'] == stage and e['outcome'] == 'enter'), None)
                returned = next((e for e in rows if e['stage'] == stage and e['outcome'] == 'returned'), None)
                reached = items[low:high]
                require(not reached or enter and all(enter['tick'] <= s['Begin'] for s in reached), 'METADATA_STAGE_START')
                if returned:
                    rejected = stage == 'readOnly' and any(e['stage'] == stage and e['outcome'] == 'failed' for e in rows)
                    require(len(reached) in ((3,4) if rejected else (high-low,))
                            and all(s['End'] <= returned['tick'] for s in reached), 'METADATA_STAGE_COVERAGE')
                    for span in reached:
                        require(span['ExecuteEnd'] is not None and all(span[k] is None for k in ('OperationError','CursorError','CommandError')),
                                'METADATA_STAGE_OUTCOME')
                        if span['Statement'] != 'privileges':
                            require(span['CursorDisposeEnd'] is not None and (span['Session'] is not None
                                    if span['Statement'] == 'identity' else span['Eof'] is not None), 'METADATA_STAGE_READER')
    return groups


def reopen_normal_projection(raw,key,profile=METADATA_PROFILE):
    """验证准确请求的有界字段和本进程时基，返回经过重开的完整记录。"""
    from datetime import datetime
    require(profile in (METADATA_PROFILE, HISTORICAL_PROFILE) and len(raw)<=(METADATA_LIMIT if profile == METADATA_PROFILE else 65536) and re.fullmatch('[a-f0-9]{32}',key),'NORMAL_PROJECTION_SIZE')
    value=json.loads(raw)
    require(set(value)=={'generation','process','module','rootDeadline','traceId','correlation','status','source'} and
            value['generation']==key and type(value['process']) is int and value['process']>0 and
            all(re.fullmatch('[0-9a-f]{32}',value[k] or '') for k in ('traceId','correlation')) and
            uuid.UUID(value['module']) and type(value['status']) is int,'NORMAL_PROJECTION_IDENTITY')
    require(isinstance(value['rootDeadline'],str) and datetime.fromisoformat(value['rootDeadline']).utcoffset() is not None
            and 100<=value['status']<=599,'NORMAL_ROOT_DEADLINE')
    source=value['source']
    expected = {'queryId','firstFailure','firstSignal','dropped','frequency','events'}
    if profile == METADATA_PROFILE:
        expected.update(('profile','kind','probe','metadata'))
    require(set(source)==expected and
            re.fullmatch('query-[0-9a-f]{32}',source['queryId'] or '') and source['dropped']==0 and
            type(source['frequency']) is int and source['frequency']>0 and 1<=len(source['events'])<=160,'NORMAL_PROJECTION_INCOMPLETE')
    names=set('http initialLease permit permitCheck tls openCheck open permitReturn sessionTag readOnly catalog session transaction declareReadOnly execute commit rollback disposeTransaction postcheck disposeConnection observer cleanupStart cleanup workCutoff readerCutoff leaseTimeout leaseException formalCancel leaseInactive requestCancel requestDeadline branch acquisition source EXECUTE EOF NATIVE_1013 CANCEL_ENTER CANCEL_RETURN CANCEL_REJECT PHYSICAL_RELEASE'.split())
    last=-1
    for event in source['events']:
        require(set(event)=={'stage','outcome','tick','remainingTicks','cleanupTicks','execution','acquisition','budgetTicks','originTick','session'}
                and event['stage'] in names and event['outcome'] in ('enter','returned','failed','cancelled','unconfirmed','confirmed','signal')
                and type(event['tick']) is int and event['tick']>=last and all(event[k] is None or type(event[k]) is int for k in ('remainingTicks','cleanupTicks','budgetTicks','originTick'))
                and (event['session'] is None or (event['stage']=='session' and len(event['session'])==5 and all(type(v) is int and 0<v<2**64 for v in event['session'])))
                and (event['execution'] is None or re.fullmatch('[a-f0-9]{32}',event['execution']))
                and (event['acquisition'] is None or str(uuid.UUID(event['acquisition']))==event['acquisition']),'NORMAL_PROJECTION_EVENT')
        last=event['tick']
    events=source['events']
    require(events[0]['stage']=='http' and events[0]['outcome']=='enter' and type(events[0]['remainingTicks']) is int and 0<=events[0]['remainingTicks']<=50000000 and source['firstFailure']==next((e['stage']+'.'+e['outcome'] for e in events if e['outcome'] in ('failed','cancelled')),None)
            and source['firstSignal']==next((e['stage'] for e in events if e['outcome']=='signal'),None),'NORMAL_PROJECTION_FIRST')
    if profile == METADATA_PROFILE:
        require(source['probe'] is None, 'METADATA_PRODUCT')
        check_metadata_spans(source)
    return value


def qualify_normal_projection(raw,key,*,query_id,trace_id,correlation,status,module,process,audit,profile=METADATA_PROFILE):
    """外层只用独立 HTTP、PG、宿主与源审计签当前请求；缺失投影仍可单独保全。"""
    value=reopen_normal_projection(raw,key,profile)
    source=value['source']
    require((source['queryId'],value['traceId'],value['correlation'],value['status'],value['module'],value['process'])
            ==(query_id,trace_id,correlation,status,module,process),'NORMAL_WRONG_REQUEST')
    events=source['events']
    require(events[-1]['stage']=='http' and events[-1]['outcome']=='returned','NORMAL_INCOMPLETE_HTTP')
    branches=[e for e in events if e['stage']=='branch' and e['outcome']=='enter']
    require(1<=len(branches)<=2 and all(b['execution'] for b in branches) and len({b['execution'] for b in branches})==len(branches),
            'NORMAL_BRANCH_IDENTITIES')
    executions = {branch['execution'] for branch in branches}
    for event in events:
        request_scope = event['stage'] in ('http', 'requestCancel', 'requestDeadline')
        require(event['execution'] is None if request_scope else event['execution'] in executions,
                'NORMAL_EXECUTION_SCOPE')
    for branch in branches:
        require(type(branch['originTick']) is int and 0 <= branch['originTick'] <= branch['tick']
                and type(branch['budgetTicks']) is int and 0 < branch['budgetTicks'] <= 10000000,
                'NORMAL_BUDGET_ORIGIN')
    if status!=200:
        metrics = []
        require(source['firstFailure'] or source['firstSignal'],'NORMAL_NO_FIRST_CAUSE')
        covered=[]
        for branch in branches:
            rows=[e for e in events if e['execution']==branch['execution']]
            pairs=[(e['stage'],e['outcome']) for e in rows]
            require(('initialLease','enter') in pairs,'NORMAL_NO_LEASE')
            for index,event in enumerate(rows):
                if event['outcome'] in ('failed','cancelled'):
                    require((event['stage'],'enter') in pairs[:index],'NORMAL_UNOPENED_STAGE')
            if ('initialLease','returned') in pairs and not (('observer','enter') not in pairs and any(e['stage'] in ('formalCancel','leaseInactive') for e in rows)):
                require(('observer','enter') in pairs and ('observer','returned') in pairs
                        and rows[-1]['stage']=='cleanup','NORMAL_INCOMPLETE_RELEASE')
            prefix='initialLease permit acquisition permitCheck tls openCheck open permitReturn sessionTag readOnly catalog session transaction declareReadOnly'.split()
            for index,stage in enumerate(prefix[1:],1):
                if any(e['stage']==stage for e in rows):
                    position=next(n for n,e in enumerate(rows) if e['stage']==stage)
                    require(all((p,'returned') in pairs[:position] for p in prefix[:index]),'NORMAL_SOURCE_PREFIX')
            hz = source['frequency']
            elapsed = rows[-1]['tick'] - branch['originTick']
            within_budget = 0 <= elapsed * 10000000 <= branch['budgetTicks'] * hz
            acquisitions = [e['acquisition'] for e in rows if e['stage'] == 'acquisition']
            require(not acquisitions or (len(acquisitions) == 1 and acquisitions[0] is not None),
                    'NORMAL_ACQUISITION_ID')
            source_positions = [(i, outcome) for i, (stage, outcome) in enumerate(pairs) if stage == 'source']
            if ('observer', 'enter') in pairs:
                require(len(source_positions) == 2 and source_positions[0][1] == 'enter'
                        and source_positions[1][1] in ('failed', 'cancelled', 'returned')
                        and pairs.index(('observer', 'enter')) < source_positions[0][0]
                        and source_positions[-1][0] < pairs.index(('observer', 'returned'))
                        and [state for stage, state in pairs if stage == 'cleanup'] in (['confirmed'], ['unconfirmed']),
                        'NORMAL_SOURCE_TERMINAL')
            starts = [e for e in rows if e['stage'] == 'cleanupStart']
            require(all(len(acquisitions) == 1 and e['acquisition'] == acquisitions[0]
                        and type(e['originTick']) is int and branch['originTick'] <= e['originTick'] <= e['tick']
                        for e in starts), 'NORMAL_CLEANUP_ORIGIN')
            cleanup = rows[-1]['tick'] - min(e['originTick'] for e in starts) if starts else None
            terminal = ('returned', 'failed', 'cancelled')
            released = ('PHYSICAL_RELEASE', 'returned') in pairs
            opened = ('open', 'returned') in pairs
            dispose = [(i, state) for i, (name, state) in enumerate(pairs) if name == 'disposeConnection']
            if opened:
                require(len(dispose) == 2 and dispose[0][1] == 'enter' and dispose[1][1] in terminal
                        and pairs.index(('open', 'returned')) < dispose[0][0], 'NORMAL_DISPOSE_TERMINAL')
            if released:
                require(dispose and dispose[-1][1] == 'returned'
                        and dispose[-1][0] < pairs.index(('PHYSICAL_RELEASE', 'returned')) < source_positions[-1][0], 'NORMAL_PHYSICAL_RELEASE')
            if ('sessionTag', 'returned') in pairs and dispose and dispose[-1][1] == 'returned':
                require(released, 'NORMAL_MISSING_PHYSICAL_RELEASE')
            if ('transaction', 'returned') in pairs:
                require(any(('disposeTransaction', state) in pairs for state in terminal), 'NORMAL_TRANSACTION_TERMINAL')
            # 连接释放只能证明驱动资源退出。原事件须另证业务游标或原生取消、事务和后验的终态。
            business_end = (('EOF', 'returned') in pairs or ('NATIVE_1013', 'returned') in pairs)
            tx_end = ('commit', 'returned') in pairs or ('rollback', 'returned') in pairs
            source_end = (business_end and tx_end and ('disposeTransaction', 'returned') in pairs
                          and (('postcheck', 'enter') not in pairs or ('postcheck', 'returned') in pairs))
            acl_rejected = (('readOnly', 'returned') in pairs and ('readOnly', 'failed') in pairs
                            and pairs.index(('readOnly', 'returned')) < pairs.index(('readOnly', 'failed'))
                            and ('transaction', 'enter') not in pairs and ('catalog', 'enter') not in pairs
                            and ('source', 'failed') in pairs and not any(e['outcome'] == 'signal' for e in rows))
            confirmed = ('cleanup', 'confirmed') in pairs
            if confirmed:
                require(released and (source_end or acl_rejected) and len(acquisitions) == 1 and acquisitions[0]
                        and (acl_rejected or len([e for e in rows if e['stage'] == 'session' and e['session']]) == 1)
                        and (rows[-1]['cleanupTicks'] or 0) > 0 and (rows[-1]['remainingTicks'] or 0) > 0
                        and within_budget and cleanup is not None and 0 <= cleanup * 4 <= hz,
                        'NORMAL_UNPROVEN_CONFIRMATION')
            metrics.append(dict(execution=branch['execution'], elapsedTicks=elapsed, budgetTicks=branch['budgetTicks'],
                                budgetExceeded=not within_budget, cleanupTicks=cleanup,
                                physicalRelease='returned' if released else dispose[-1][1] if dispose else 'unobserved',
                                sourceTermination='observed' if source_end or acl_rejected else 'unconfirmed', cleanupQualified=confirmed))
            native=[a for a in audit if a['clientId']==branch['execution']]
            if native:
                sessions=[e['session'] for e in rows if e['stage']=='session' and e['session']]
                require(len(native)==len(sessions)==1 and ('EXECUTE','returned') in pairs and
                        int(native[0]['instance'])==sessions[0][0] and int(native[0]['session'])==sessions[0][3],
                        'NORMAL_FAILURE_NATIVE')
            covered.extend(native)
        require(len(covered)==len(audit),'NORMAL_UNRELATED_READ')
        return dict(status='FAILURE_TRACED', evidenceComplete=True, productSucceeded=False, branches=metrics,
                    frequency=source['frequency'], firstFailure=source['firstFailure'], firstSignal=source['firstSignal'])
    require(len(branches)==2 and len(audit)==2 and source['firstFailure'] is None and source['firstSignal'] is None,'NORMAL_SUCCESS_BRANCHES')
    if profile == METADATA_PROFILE:
        groups = check_metadata_spans(source)
        require(set(groups) == executions and all(len(items) == 12 for items in groups.values()), 'METADATA_PRODUCT_COVERAGE')
        for items in groups.values():
            for span in items:
                require(span['ExecuteEnd'] is not None and all(span[k] is None for k in ('OperationError','CursorError','CommandError')),
                        'METADATA_SQL_INCOMPLETE')
                if span['Statement'] != 'privileges':
                    require(span['CursorDisposeEnd'] is not None and (span['Session'] is not None
                            if span['Statement'] == 'identity' else span['Eof'] is not None), 'METADATA_READER_INCOMPLETE')
    metrics=[]
    required='initialLease permit acquisition permitCheck tls openCheck open permitReturn sessionTag readOnly catalog session transaction declareReadOnly EXECUTE EOF execute commit disposeTransaction postcheck disposeConnection PHYSICAL_RELEASE observer cleanup'.split()
    for index,branch in enumerate(branches):
        rows=[e for e in events if e['execution']==branch['execution']]
        observed=[e for e in rows if e['outcome'] in ('returned','confirmed')]
        offset=0
        for stage in required:
            while offset<len(observed) and observed[offset]['stage']!=stage:
                offset+=1
            require(offset<len(observed),'NORMAL_MISSING_'+stage)
            offset+=1
        acquisition=[e['acquisition'] for e in rows if e['stage']=='acquisition']
        session=[e['session'] for e in rows if e['stage']=='session' and e['session']]
        require(len(acquisition)==len(session)==1 and acquisition[0] and rows[-1]['stage']=='cleanup'
                and rows[-1]['outcome']=='confirmed','NORMAL_RELEASE')
        native=[a for a in audit if a['clientId']==branch['execution'] and a['action']=='SELECT' and a['code']==0]
        require(len(native)==1 and (native[0]['owner'],native[0]['table'])==(('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget'))[index] and int(native[0]['instance'])==session[0][0] and int(native[0]['session'])==session[0][3],'NORMAL_NATIVE_ASSOCIATION')
        starts=[e['originTick'] for e in rows if e['stage']=='cleanupStart' and e['acquisition']==acquisition[0]]
        hz=source['frequency']
        require(starts and branch['originTick']<=branch['tick'] and 0<branch['budgetTicks']<=10000000,'NORMAL_BUDGET_ORIGIN')
        elapsed=rows[-1]['tick']-branch['originTick']
        cleanup=rows[-1]['tick']-min(starts)
        require(0<=cleanup*4<=hz and 0<=elapsed*10000000<=branch['budgetTicks']*hz,'NORMAL_BRANCH_BUDGET')
        metrics.append(dict(execution=branch['execution'],acquisition=acquisition[0],elapsedTicks=elapsed,cleanupTicks=cleanup))
    require(events[-1]['remainingTicks']>0 and {r['table'] for r in audit}=={'OMQ_ENTITY','OmqTarget'},'NORMAL_ROOT_BUDGET')
    return dict(status='NORMAL_TRACE_VERIFIED',branches=metrics,frequency=source['frequency'])


def export_normal_projection(cid,key):
    """只读取准确宿主中已由 OnCompleted 原子发布的受限文件，不采集全量日志。"""
    require(re.fullmatch('[a-f0-9]{64}',cid) and re.fullmatch('[a-f0-9]{32}',key),'NORMAL_EXPORT_ID')
    # 最多两秒等待响应后导出，采集有自己的外层命令期限。
    script='i=0; while [ ! -f "$1" ] && [ "$i" -lt 20 ]; do sleep 0.1; i=$((i+1)); done; test -f "$1" && head -c 131073 "$1"'
    args=['exec',cid,'/bin/sh','-c',script,'normal-export','/tmp/omq-events-'+key+'.json']
    receipt=dict(containerId=cid,requestKey=key,commandId=None,exitCode=None,status='COLLECTION_FAILED')
    try:
        result=ex.run(['docker','--context','desktop-linux',*args],ROOT,task=TASK,run_id=PRODUCT,
                      stage='normal-api-export',timeout=5,input_key=ex.sha(ex.encoded(args)))
        rec=result.receipt
        receipt.update(commandId=rec['commandId'],exitCode=result.returncode)
        require(result.returncode==0,'NORMAL_EXPORT_COMMAND')
        directory=AREA.parent/'commands'/PRODUCT/rec['commandId']
        raw=ex.ordinary(directory/'stdout.txt').read_bytes()
        require(len(raw)==rec['stdout']['sizeBytes'] and ex.sha(raw)==rec['stdout']['sha256'],'NORMAL_EXPORT_STREAM')
        projection=reopen_normal_projection(raw,key)
        receipt.update(status='EXPORTED',queryId=projection['source']['queryId'],sha256=ex.sha(raw),sizeBytes=len(raw))
    finally:
        platform.save(AREA/'s2-s3-01'/('normal-export-'+cid+'-'+key+'.json'),receipt)
    return receipt


def release_api(role):
    """先向准确 API 进程发 TERM 并观察引擎自然退出，再只移除该无状态实例。"""
    require(role in APIS and role in manifest()['ids'],'PRODUCT_RELEASE_ROLE')
    cid=manifest()['ids'][role]
    before=admit(); actions=[]
    state,_=command('resume-close-state',['inspect','-f','{{.State.Status}}',cid])
    collection_failure=None
    exported=None
    key=manifest().get('normalDiagnosticKey')
    if role=='api' and key:
        try:
            exported=export_normal_projection(cid,key)
        except Exception as failure:
            collection_failure=failure
    if state=='running':
        _,sig=command('resume-api-term',['stop','--signal','TERM','--timeout','-1',cid],timeout=45)
        actions.append(sig)
    if state in ('running','exited'):
        out,observed=command('resume-api-exit',['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid])
        actions.append(observed)
        require(out in ('exited 0 false','exited 143 false'),'PRODUCT_API_SHUTDOWN')
    else:
        require(state=='created','PRODUCT_API_CLOSED_STATE')
    if exported is not None:
        try:
            raw=ex.ordinary(AREA.parent/'commands'/PRODUCT/exported['commandId']/'stdout.txt').read_bytes()
            require(len(raw)==exported['sizeBytes'] and ex.sha(raw)==exported['sha256'],'NORMAL_DRAIN_EXPORT_BYTES')
            reopen_normal_projection(raw,key)
        except Exception as failure:
            collection_failure=failure
            exported['status']='DRAIN_REOPEN_FAILED'
            platform.save(AREA/'s2-s3-01'/('normal-export-'+cid+'-'+key+'.json'),exported)
    # 复核准确无状态容器后按授权删除，无 force/卷参数。
    _,removed=command('resume-remove-stateless',['rm',cid]);actions.append(removed)
    remaining,_=command('resume-absent',['ps','-a','--no-trunc','--filter','id='+cid,'--format','{{.ID}}'])
    require(not remaining,'PRODUCT_API_STILL_PRESENT')
    row=manifest();del row['ids'][role];save_manifest(row)
    post=admit()
    save_api_observation('removed',role,dict(id=cid,pre=before['attempt'],post=post['attempt'],commands=actions))
    if collection_failure is not None:
        raise ValueError('NORMAL_EXPORT_FAILED_AFTER_SAFE_RELEASE') from collection_failure
