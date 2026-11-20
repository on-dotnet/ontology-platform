"""正式 Oracle 恢复窗口：原五副本、两个无状态 API 与现有阶段资源核验。"""
import json
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
    return before_source(ROOT,TASK,platform_stage=True,phase=PRODUCT,running_roles=active,planned_roles=active|set(planned))


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
            snapshot_id=inp.get('sessionSnapshotId','')
            require(re.fullmatch('[0-9a-f]{64}',snapshot_id),'PRODUCT_SESSION_SNAPSHOT_ID')
            expected=str(AREA/'runtime-snapshots'/snapshot_id)
            session=[m for m in json.loads(mounts) if m['Destination']=='/session-tests' or m['Destination'].startswith('/session-tests/')]
            require(len(session)==1 and session[0]['Destination']=='/session-tests' and session[0]['RW'] is False
                    and session[0]['Source'].removeprefix('/host_mnt')==expected,'PRODUCT_SESSION_LIVE_MOUNT')
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


def release_api(role):
    """先向准确 API 进程发 TERM 并观察引擎自然退出，再只移除该无状态实例。"""
    require(role in APIS and role in manifest()['ids'],'PRODUCT_RELEASE_ROLE')
    cid=manifest()['ids'][role]
    before=admit(); actions=[]
    state,_=command('resume-close-state',['inspect','-f','{{.State.Status}}',cid])
    if state=='running':
        _,sig=command('resume-api-term',['stop','--signal','TERM','--timeout','-1',cid],timeout=45)
        actions.append(sig)
    if state in ('running','exited'):
        out,observed=command('resume-api-exit',['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid])
        actions.append(observed)
        require(out in ('exited 0 false','exited 143 false'),'PRODUCT_API_SHUTDOWN')
    else:
        require(state=='created','PRODUCT_API_CLOSED_STATE')
    # 复核准确无状态容器后按授权删除，无 force/卷参数。
    _,removed=command('resume-remove-stateless',['rm',cid]);actions.append(removed)
    remaining,_=command('resume-absent',['ps','-a','--no-trunc','--filter','id='+cid,'--format','{{.ID}}'])
    require(not remaining,'PRODUCT_API_STILL_PRESENT')
    row=manifest();del row['ids'][role];save_manifest(row)
    post=admit()
    save_api_observation('removed',role,dict(id=cid,pre=before['attempt'],post=post['attempt'],commands=actions))
