"""正式 Oracle 恢复窗口：原五副本、两个无状态 API 与现有阶段资源核验。"""
import json
import re
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


def prepare():
    require(not REGISTRY.exists(),'PRODUCT_ALREADY_PREPARED')
    admission=admit(APIS)
    ids,nets=data()
    old=load(BASE/'formal-api-inputs.json')
    specpath=BASE/'formal-api-compose.json'
    relay=BASE/'formal-relay'
    require(ex.sha(specpath.read_bytes())==old['composeSha256'] and ex.sha((relay/'OracleRelay.dll').read_bytes())==old['relaySha256'],'PRODUCT_OLD_RUNTIME')
    spec=load(specpath)
    require(set(spec['services'])==set(APIS),'PRODUCT_API_RECIPE')
    builds={}
    for target in ('api','query'):
        binding,row=bound_build(target)
        output=ROOT/Path(platform.build.TARGETS[target]).parent/'bin/Debug/net10.0'
        peak=sum(p.stat().st_blocks*512 for p in output.rglob('*') if p.is_file())
        require(peak*2 < admission['platformDisk']['allocations']['newBuildEvidenceAndLogs'] and
                peak*2+admission['platformDisk']['totalBytes'] < admission['platformDisk']['ceilingBytes'],'PRODUCT_SNAPSHOT_BUDGET')
        snap=platform.snapshots.freeze(ROOT,output,AREA/'runtime-snapshots',binding,row['commandId'],
              {'toolEnvironment':row['environmentFingerprint']},task=TASK,run_id=PRODUCT)
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
        if role=='api-secondary':targets['/query-tests']=ROOT/builds['query'][2]['directory']
        service['volumes']=[str(path)+':'+target+':ro' for target,path in targets.items()]
    platform.save(AREA/'formal-api-compose.json',spec)
    inp={**old,'runId':PRODUCT,'build':binding,'snapshotId':snap['snapshotId'],'buildCommandId':row['commandId'],
         'composeSha256':ex.sha((AREA/'formal-api-compose.json').read_bytes()),'querySnapshotId':builds['query'][2]['snapshotId']}
    platform.save(AREA/'formal-api-inputs.json',inp)
    registration=dict(taskId=TASK,runId=PRODUCT,project=PROJECT,ids=ids,networks=nets,snapshotId=snap['snapshotId'],
                      apiBuildId=row['commandId'],buildOutputKey=binding['outputKey'],admission=admission['attempt'])
    save_manifest(registration)
    state=load(BASE/'runtime-fixture.json')
    require((state['taskId'],state['runId'])==(TASK,RUN),'PRODUCT_RUNTIME_FIXTURE')
    platform.save(AREA/'runtime-fixture.json',{**state,'runId':PRODUCT})
    return registration


def create(role):
    require(role in APIS and role not in manifest()['ids'],'PRODUCT_CREATE_ROLE')
    admit([role])
    spec=AREA/'formal-api-compose.json'
    require(ex.sha(spec.read_bytes())==load(AREA/'formal-api-inputs.json')['composeSha256'],'PRODUCT_SPEC')
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
        if role in APIS:platform.snapshots.demand_mount(ROOT,snap,json.loads(mounts),task=TASK,run_id=PRODUCT)
        services[role]=dict(containerId=cid,imageId=image,pid=int(pid),startedAt=started,mountSha256=ex.sha(ex.encoded(json.loads(mounts))),networks=networks)
    require(inp['composeSha256']==ex.sha((AREA/'formal-api-compose.json').read_bytes()) and inp['relaySha256']==ex.sha((BASE/'formal-relay/OracleRelay.dll').read_bytes()),'PRODUCT_INPUT_DRIFT')
    return dict(taskId=TASK,runId=PRODUCT,ports=platform.PORTS,commandId=result.receipt['commandId'],snapshotId=inp['snapshotId'],
                buildInputKey=inp['build']['inputKey'],buildOutputKey=inp['build']['outputKey'],runtimeHelperSha256=inp['relaySha256'],
                composeSha256=inp['composeSha256'],resourceManifestSha256=ex.sha(REGISTRY.read_bytes()),services=services,
                oracle=dict(containerId=source['containerId'],imageId=platform.SOURCE.split('@')[1],networkId=rec['networks'][SOURCE_NETWORK]))


def bind_session_tests():
    """在创建容器前把既有票据检查装入副实例的只读测试快照。"""
    rec=manifest()
    require(not set(APIS).intersection(rec['ids']),'PRODUCT_BIND_BEFORE_CREATE')
    specpath=AREA/'formal-api-compose.json';inpath=AREA/'formal-api-inputs.json'
    spec=load(specpath);inputs=load(inpath)
    if 'sessionSnapshotId' in inputs:
        return inputs['sessionSnapshotId']
    admission=admit(APIS)
    binding,row=bound_build('agent')
    source=ROOT/Path(platform.build.TARGETS['agent']).parent/'bin/Debug/net10.0'
    size=sum(p.stat().st_blocks*512 for p in source.rglob('*') if p.is_file())
    require(size+admission['platformDisk']['totalBytes']<=admission['platformDisk']['ceilingBytes'],'PRODUCT_SESSION_SNAPSHOT_COST')
    snap=platform.snapshots.freeze(ROOT,source,AREA/'runtime-snapshots',binding,row['commandId'],
                                  {'toolEnvironment':row['environmentFingerprint']},task=TASK,run_id=PRODUCT)
    spec['services']['api-secondary']['volumes'].append(str(ROOT/snap['directory'])+':/session-tests:ro')
    for original in (inpath,specpath):
        (AREA/(original.stem+'-'+ex.sha(original.read_bytes())+'.json')).write_bytes(original.read_bytes())
    platform.save(specpath,spec,True)
    inputs.update(sessionSnapshotId=snap['snapshotId'],composeSha256=ex.sha(specpath.read_bytes()))
    platform.save(inpath,inputs,True)
    return snap['snapshotId']


def verify_sessions(actors,seconds):
    """同一已准副 API 内运行既有票据检查。真实 Cookie 只交现有消费者的 stdin。"""
    from workflow_m2_evidence import mtp
    require(seconds==210 and len(actors)==4,'PRODUCT_SESSION_WINDOW')
    inp=load(AREA/'formal-api-inputs.json')
    snap=load(AREA/'runtime-snapshots'/(inp['sessionSnapshotId']+'.json'))
    platform.snapshots.verify(ROOT,snap,task=TASK,run_id=PRODUCT)
    binding=platform.build.validate('agent',TASK)
    require(binding==snap['inputs'],'PRODUCT_SESSION_BUILD')
    host=host_binding()
    cid=host['services']['api-secondary']['containerId']
    # 验证程序在独占临时目录输出不含认证内容的结果，证据正文不记录 stdin。
    runner='set -eu; d=$(mktemp -d /tmp/omq-session.XXXXXXXX); trap \'rm -r -- "$d"\' EXIT; export G4_BROWSER_REPORT="$d/ready.json"; cd "$d"; dotnet /session-tests/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline --minimum-expected-tests 1 --no-ansi --progress off --results-directory "$d/results"; cat "$G4_BROWSER_REPORT"; echo'
    args=['docker','--context','desktop-linux','exec','-i','-e','HOME=/tmp','-e','DOTNET_CLI_HOME=/tmp',
          '-e','G4_BROWSER_PREFLIGHT=1','-e','G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,'-e','OMQ_SESSION_SECONDS='+str(seconds),
          cid,'/bin/sh','-ec',runner]
    result=ex.run(args,ROOT,task=TASK,run_id=PRODUCT,stage='omq-session-real',stdin=ex.encoded(actors),
                  input_key=ex.sha(ex.encoded(binding)),parent_id=host['commandId'],timeout=22)
    require(result.returncode==0,'PRODUCT_SESSION_REJECTED_'+result.receipt['commandId'])
    mtp(result.stdout+result.stderr,1)
    obs=json.loads(result.stdout.splitlines()[-1])
    require([v['subjectId'] for v in obs]==[v['subjectId'] for v in actors],'PRODUCT_SESSION_SUBJECT')
    return dict(commandId=result.receipt['commandId'],observations=obs)


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
    platform.save(AREA/('api-ready-'+role+'.json'),row)
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
    platform.save(AREA/('api-removed-'+role+'.json'),dict(id=cid,pre=before['attempt'],post=post['attempt'],commands=actions))
