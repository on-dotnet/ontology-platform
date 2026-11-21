"""Oracle S0 阻断后只读回读受保护资源、准确取消占位和已验证的恢复范围。"""
import argparse
import contextlib
import datetime as dt
import json
import re
import uuid

import doris_keep_drain as drain
import workflow_execution as ex
import workflow_oracle_mapping_formal_observer as observer
import workflow_oracle_mapping_platform as platform
from workflow_oracle_mapping_resources import INVENTORY_SHA, KEEP_FORMAT, RUN, SOURCE, TASK, require

AREA = platform.AREA
CID = r'[0-9a-f]{64}'
SOURCE_FORMAT = ('{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}'
                 '|{{.State.Status}}|{{.State.OOMKilled}}|{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}'
                 '|{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')


RECOVERY='s0-recovery-01'
ORIGINAL_IDS={
    'oracle':'00c4f5dabf4a9348adf0f8910f28015f4a84301f56548e4da23642227c223f09',
    'platform-pg':'eb3c386dbfe423d22f71f638d1be1c62d30d181e6e6decc039ead85b3ea2dbe5',
    'keycloak-test':'15e05cb8e15b7c4e86eb0b9e1efeab79bdbcb620bc863f6e8c5679f7a23d9f5b',
    'fuseki':'9300ad957c05e496fec424c34c10b62b368984ce470eb366c4af3a4a473912eb',
    'rustfs':'f426493417bf179e887c095dd14164d0a3cf3aa71575e01fe1e77bd306c859bd'}
API_IDS={'api':'9ebfe02c2d5d4aae584add715eeee938988ae6c53e2a77e4f82f70d52d06a92d',
         'api-secondary':'872a44afe819ddcd0c6c9040c97204a9633d5b24e09442df450898e09b05d7fd'}
ARCHIVED_API_IDS={'api':'f90b7e7b599ffb4e9b298ce3679f9f24b25c762b472487fe09fd52e3f8e378cf',
                  'api-secondary':'0f04589574f7ace57e784e1bf0525e6c2587819a0c882ebfc15a09f7203e689f'}
ALT_ORACLE='65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1'
ALT_PROJECT='ontology-g4-omq-restore-01'


def phase_inventory(area,phase,roles,docker):
    """核对恢复阶段预期运行者、所有原件/替代身份及挂载。返回值仍须与引擎全运行集合对账。"""
    require(phase in ('preserve','restore','closed') and set(roles)<=set(ORIGINAL_IDS)
            and (phase!='closed' or not roles), 'PHASE_ID')
    owned=json.loads((area/'formal-resources.json').read_bytes())
    require(owned['ids']=={**{k:v for k,v in ORIGINAL_IDS.items() if k!='oracle'},**API_IDS}
            and owned['archivedApiIds']==ARCHIVED_API_IDS, 'PHASE_ORIGINAL_IDS')
    source=json.loads((area/'source-create-01.json').read_bytes())
    early=json.loads((area/'recovery-01-final.json').read_bytes())
    require(source['containerId']==early['originalId']==ORIGINAL_IDS['oracle'] and early['replacementId']==ALT_ORACLE,
            'PHASE_SOURCE_IDS')
    replacement={'ids':{},'volumes':{},'networks':{}}
    registry=area.parent/RECOVERY/'replacement-resources.json'
    if registry.exists():
        replacement=json.loads(registry.read_bytes())
        require((replacement['taskId'],replacement['runId'],replacement['operation'],replacement['project'])==
                (TASK,RUN,RECOVERY,ALT_PROJECT) and set(replacement['ids'])<=set(platform.VOLUMES)
                and set(replacement['volumes'])==set(replacement['ids'])
                and all(replacement['volumes'][k]==ALT_PROJECT+'_'+platform.VOLUMES[k] for k in replacement['volumes']),
                'REPLACEMENT_RECORD')
    if phase=='closed':
        require(set(replacement['ids'])==set(platform.VOLUMES),'CLOSED_INCOMPLETE_STACK')
    primary={**ORIGINAL_IDS,**API_IDS}
    sources={'oracle':source['volume'],**owned['volumes']}
    target={'oracle':ALT_ORACLE,**replacement['ids']}
    target_volumes={'oracle':early['replacementVolume'],**replacement['volumes']}
    running=set();ports=set();memory=0;cpu=0
    for group,ids,volumes in [('original',primary,sources),('replacement',target,target_volumes),('archived',ARCHIVED_API_IDS,{})]:
        for role,cid in ids.items():
            require(re.fullmatch(CID,cid),'PHASE_CID')
            fmt='{{.Id}}|{{.Image}}|{{.State.Status}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{json .Mounts}}|{{json .HostConfig.PortBindings}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{json .NetworkSettings.Networks}}'
            loc=docker('phase-'+group+'-'+role,'inspect','-f',fmt,cid).split('|')
            image=SOURCE.split('@')[1] if role=='oracle' else platform.IMAGES[role]
            quota=(4096,2) if role=='oracle' else platform.QUOTAS[role]
            project=('ontology-g4-oracle-mapping-query-001' if group=='original' else 'ontology-g4-omq-replacement-01') if role=='oracle' else (ALT_PROJECT if group=='replacement' else platform.PROJECT)
            if group=='original' and role in API_IDS:
                spec=(area/'formal-api-compose.json').read_bytes()
                require(ex.sha(spec)==json.loads((area/'formal-api-inputs.json').read_bytes())['composeSha256'],'API_COMPOSE_ID')
                project=json.loads(spec)['name']
            require(loc[0]==cid and loc[1]==image and loc[3:7]==[TASK,RUN,str(quota[0]*1024**2),str(int(quota[1]*1e9))]
                    and loc[9:11]==[project,'oracle-source' if role=='oracle' else role],'PHASE_OWNER_'+role)
            expected=(phase=='preserve' and group=='original' or phase=='restore' and group=='replacement') and role in roles
            require(loc[2]=='running' if expected else loc[2] in (('exited','created') if group=='replacement' and phase!='closed' else ('exited',)),
                    'PHASE_STATE_'+group+'_'+role)
            mounts=[m['Name'] for m in json.loads(loc[7]) if m['Type']=='volume']
            require(mounts==([volumes[role]] if role in volumes else []),'PHASE_MOUNT_'+role)
            for vol in mounts:
                fields=docker('phase-volume','volume','inspect','-f','{{.Driver}}|{{json .Options}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}|{{index .Labels "com.docker.compose.project"}}',vol).split('|')
                require(fields[0]=='local' and not json.loads(fields[1]) and fields[2:]==[TASK,RUN,project],'PHASE_VOL_OWNER')
            allowed={'keycloak-test':15743,'api':15741,'api-secondary':15742}.get(role)
            port_bindings=json.loads(loc[8]) or {}
            require(port_bindings==({'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(allowed)}]} if allowed else {}),'PHASE_PORTS')
            if expected:
                network_ids={k:v['NetworkID'] for k,v in json.loads(loc[11]).items()}
                if role=='oracle':
                    netname=source['network'] if group=='original' else early['network']
                    nid=source['networkId'].split()[0] if group=='original' else json.loads((area/'recovery-01.json').read_bytes())['replacementNetworkId'].split()[0]
                    require(network_ids=={netname:nid}, 'PHASE_SOURCE_NET')
                else:
                    nets=owned['networks'] if group=='original' else replacement['networks']
                    names=['platform-internal']+(['host-entry'] if role=='keycloak-test' else [])
                    require(network_ids=={project+'_'+n:nets[n] for n in names},'PHASE_NET_'+role)
                running.add(cid);memory+=int(loc[5]);cpu+=int(loc[6])
                if allowed:ports.add(allowed)
    return running,memory,cpu,ports,replacement


def record(name):
    path = ex.ordinary(AREA / name)
    row = json.loads(path.read_bytes())
    require((row.get('taskId'), row.get('runId')) == (TASK, RUN), 'RECORD_OWNER')
    return row


def ref(name):
    data = ex.ordinary(AREA / name).read_bytes()
    return {'path': name, 'bytes': len(data), 'sha256': ex.sha(data)}


def docker(stage, *argv):
    # 这个适配器只允许 Docker 读取命令；不注册临时探针或启动服务。
    require(argv[0] in ('inspect', 'ps') or argv[:2] in (('volume', 'inspect'), ('network', 'inspect')), 'READ_ONLY_DOCKER')
    return platform.docker('blocked-' + stage, *argv)


def protected_resources():
    path = ex.ordinary(AREA.parent / 'resource-inventory.json')
    data = path.read_bytes()
    require(ex.sha(data) == INVENTORY_SHA, 'P0_INVENTORY_CHANGED')
    retained = json.loads(data)['retained']
    require(len(retained) == 20 and all(re.fullmatch(CID, row.split('|')[0]) for row in retained), 'RETAINED_COUNT')
    observed = docker('keep', 'inspect', '-f', KEEP_FORMAT, *[r.split('|')[0] for r in retained]).splitlines()
    require(observed == retained, 'PROTECTED_RESOURCE_DRIFT')
    rows = [r.split('|') for r in retained]
    running = {r[0] for r in rows if r[2] == 'running'}
    require(len(running) == 3 and sum(r[2] == 'exited' for r in rows) == 17, 'RETAINED_STATE')
    return running, {'inventorySha256': INVENTORY_SHA, 'exactRetainedRows': observed}


def source_status():
    original = record('source-create-01.json')
    clone = record('recovery-01-resume.json')
    cold = record('recovery-01.json')
    accepted = record('recovery-01-final.json')
    require(clone['originalId'] == accepted['originalId'] == cold['originalId'] == original['containerId']
            and accepted['replacementId'] == cold['replacementId'] == clone['replacementId']
            and accepted['status'] == 'EARLY_SOURCE_RECOVERY_PASS'
            and clone['beforeHash'] == clone['restoredHash'] == accepted['originalAfterHash'], 'SOURCE_RECOVERY_CHAIN')
    result = {}
    for role, cid, volume, network, netid, state in (
        ('original', original['containerId'], original['volume'], original['network'], original['networkId'], 'running'),
        ('alternative', clone['replacementId'], clone['replacementVolume'], clone['network'], cold['replacementNetworkId'], 'exited')
    ):
        require(re.fullmatch(CID, cid), 'SOURCE_ID')
        row = docker(role, 'inspect', '-f', SOURCE_FORMAT, cid).split('|')
        require(row[:7] == [cid, SOURCE.split('@')[1], TASK, RUN, state, 'false', volume] and row[7].split() == [network], 'SOURCE_DRIFT_'+role)
        vol = docker('source-volume', 'volume', 'inspect', '-f', '{{.Name}}|{{.Driver}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}', volume)
        require(vol == '|'.join((volume,'local',TASK,RUN)), 'SOURCE_VOLUME_'+role)
        net = docker('source-net', 'network', 'inspect', '-f', '{{.Id}} {{.Internal}} {{index .Labels "ontology.task"}}', network)
        require(net == netid and re.fullmatch(CID,net.split()[0]), 'SOURCE_NETWORK_'+role)
        result[role] = dict(containerId=cid, volume=volume, networkId=net.split()[0], state=state)
    return result, dict(status='EARLY_SOURCE_RECOVERY_PASS', scope='early Oracle source data and separate trust/auth only',
                        records=[ref(n) for n in ('recovery-01.json','recovery-01-resume.json','recovery-01-final.json')],
                        backupFiles=cold['backupFiles'], sourceDriverEvidence=accepted['sourceDriverEvidence'],
                        diskBytesAtOriginalBackup=cold['allocatedSourceBytes'], backupRereadThisCheck=False)


def platform_status(witness):
    owned = record('formal-resources.json')
    require(set(owned['ids']) == set(platform.QUOTAS) and set(owned['volumes']) == set(platform.VOLUMES), 'PLATFORM_SET')
    running, _, ports = platform.verify_owned_platform(AREA, docker)
    require(owned['state']=='S0_BLOCKED_SEALED' and running == {owned['ids'][n] for n in platform.VOLUMES}
            and ports == {15743}, 'PLATFORM_SEALED_STATE')
    seal=record('s0-blocked-seal-01.json')
    obs=record(witness)
    require(seal['status']=='BUSINESS_ENTRY_SEALED_OWNER_RETAINED' and seal['queryId']==obs['queryId']
            and seal['oldInventorySha256']==INVENTORY_SHA, 'SEAL_ID')
    stages=seal['steps']
    require([r.get('stage',r.get('service')) for r in stages]==
            ['pre','pre-confirm','api-secondary','after-api-secondary','api','after-api'],'SEAL_STAGES')
    for row in (r for r in stages if 'counts' in r):
        counts=dict(row['counts'])
        require(counts.pop('owner')==obs['terminalReadback']['state']['owner'] and
                set(counts)=={'mappingJobs','mappingOutbox','publishingOutbox','agentRuns','activeQueries'}
                and not any(counts.values()) and row['sourceReaderSessions']==0, 'SEAL_DRAIN')
    sealed={r['service']:r for r in stages if 'service' in r}
    compose=ex.ordinary(AREA/'formal-api-compose.json').read_bytes()
    require(ex.sha(compose)==obs['hostAfter']['composeSha256']==record('formal-api-inputs.json')['composeSha256'],'SEALED_COMPOSE')
    config=json.loads(compose)
    original = record('source-create-01.json')
    networks = {platform.PROJECT+'_'+role: value for role,value in owned['networks'].items()}
    networks[original['network']] = original['networkId'].split()[0]
    expected = {platform.PROJECT+'_platform-internal'}
    services = {}
    for name,cid in owned['ids'].items():
        query = '{{json .Mounts}}|{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.NetworkID}} {{end}}'
        mounts, nets = docker('exact-mounts','inspect','-f',query,cid).split('|')
        row_nets = dict(item.split('=') for item in nets.split())
        required = set(expected)
        if name in ('api','api-secondary','keycloak-test'):
            required.add(platform.PROJECT+'_host-entry')
        if name in ('api','api-secondary'):
            required.add(original['network'])
        configured={k:networks[k] for k in required}
        tracking='running'
        if name in sealed:
            step=sealed[name]
            require(step['before']==[cid,TASK,RUN,'running','0','false'] and step['after'][:4]==[cid,TASK,RUN,'exited']
                    and step['after'][4] in ('0','143') and step['after'][5]=='false', 'SEALED_ID')
            frozen=obs['hostAfter']['services'][name]
            require(frozen['containerId']==cid and frozen['imageId']==platform.IMAGES[name] and frozen['networks']==configured
                    and frozen['mountSha256']==ex.sha(ex.encoded(json.loads(mounts))), 'PRE_SEAL_BINDING')
            actual=docker('sealed-api-state','inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.HostConfig.NetworkMode}}',cid).split('|')
            require(actual[:3]==step['after'][3:] and actual[3] in configured and
                    set(config['services'][name]['networks'])=={'source-internal','platform-internal','host-entry'} and
                    config['networks']['source-internal']['name']==original['network'], 'SEALED_STATE_NETWORK_CONFIG')
            # Docker 对退出容器清空活动端点。保留当前仍可见的值，按停前冻结网络逐项核验。
            require(set(row_nets)<=required and all(not v or v==configured[k] for k,v in row_nets.items()),'SEALED_NETWORK_DRIFT')
            tracking='exited'
        else:
            require(row_nets==configured,'PLATFORM_NETWORK_'+name)
        volumes = [r['Name'] for r in json.loads(mounts) if r['Type']=='volume']
        require(volumes == ([owned['volumes'][name]] if name in platform.VOLUMES else []), 'PLATFORM_MOUNT_'+name)
        if volumes:
            identity=docker('volume-identity','volume','inspect','-f','{{.Name}}|{{.Driver}}|{{index .Labels "ontology.task"}}|{{index .Labels "ontology.run"}}|{{index .Labels "com.docker.compose.project"}}',volumes[0])
            require(identity=='|'.join((volumes[0],'local',TASK,RUN,platform.PROJECT)), 'PLATFORM_VOLUME_OWNER')
        services[name]=dict(containerId=cid,volumes=volumes,observedNetworkIds=row_nets,frozenNetworkIds=configured,state=tracking,mountsSha256=ex.sha(mounts.encode()))
    archived={}
    for name,cid in owned['archivedApiIds'].items():
        require(name in ('api','api-secondary') and re.fullmatch(CID,cid) and cid not in running, 'ARCHIVED_ID')
        query='{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}} {{.State.OOMKilled}}'
        require(docker('archived','inspect','-f',query,cid).split()==[cid,platform.IMAGES[name],TASK,RUN,'exited','false'], 'ARCHIVED_STATE')
        archived[name]=cid
    return running, dict(services=services,archivedStoppedApiIds=archived,seal=ref('s0-blocked-seal-01.json'),activePlatformPorts=sorted(ports),privateMaterials='KEEP_IN_PLACE')


def held_query(witness):
    obs = record(witness)
    key = obs['idempotencyKey']
    require(witness=='formal-witness-'+str(uuid.UUID(key))+'.json' and obs['status']=='OBSERVED'
            and re.fullmatch(observer.QID,obs['queryId']) and re.fullmatch(observer.CLIENT,obs['final']['clientId']), 'FORMAL_WITNESS')
    original = obs['terminalReadback']['state']
    require(original['id']==obs['queryId'] and original['state']=='CANCELLED' and original['cancel'] is True and original['fence']==2
            and re.fullmatch('oracle-execution-[0-9a-f]{32}',original['owner']) and not obs['final']['slotReleased']
            and not obs['final']['sameExecutionActiveAtCommit'] and not obs['final']['nativeCancelCausedTermination'], 'FAILED_POSITIVE')
    state=record('runtime-fixture.json')
    sql=observer.pg_query(key,state['subjects']['reader']).encode()
    text, cmd=platform.read_pg(sql,'blocked-held-query')
    row=json.loads(text)
    require(all(row[k]==original[k] for k in ('id','cancel','state','owner','fence','hash','bytes','receipts','successAudits','cancelAudits'))
            and row['hash'] is None and (row['bytes'],row['receipts'],row['successAudits'],row['cancelAudits'])==(0,0,0,1), 'CANCELLED_ROW_DRIFT')
    sql='SELECT json_build_array('+','.join('('+q+')' for q in drain.COUNTS)+');'
    counts, counts_id=platform.read_pg(sql.encode(),'blocked-work-counts')
    samples=dict(zip(drain.COUNT_NAMES,json.loads(counts),strict=True))
    require(not any(samples.values()),'CURRENT_WORK')
    source, sqlid=observer.source_ids()
    require(obs['sourceId']==source and obs['sqlId']==sqlid,'WITNESS_SOURCE')
    client=obs['final']['clientId']
    with contextlib.closing(observer.source_channel(source)) as channel:
        result=channel.run("select count(*) from G4_CONTROL.OMQ_SESSIONS where client_identifier='"+client+"';")
    require(result==['0'],'CURRENT_SOURCE_SESSION')
    return dict(witness=ref(witness),queryId=row['id'],clientId=client,platformReadId=cmd,observedUtc=row['observed'],
                heldOwner=row['owner'],fence=row['fence'],status=row['state'],cancelAudits=1,successEffects=[0,0,0],
                currentWork=samples,currentWorkReadId=counts_id,sourceObserver='OMQ_OBSERVER TCPS FREEPDB1',currentMatchingSourceSessions=0,
                nativeTerminationAtCommit='NOT_PROVEN',cleanup='UNCONFIRMED_HOLD',slotReleased=False)


def status(witness):
    require(re.fullmatch('formal-witness-[a-f0-9-]{36}\\.json',witness),'WITNESS_PATH')
    running,retained=protected_resources()
    source,backup=source_status()
    platform_ids,platforms=platform_status(witness)
    require(set(docker('all-running','ps','-q','--no-trunc').splitlines())==running|platform_ids|{source['original']['containerId']},
            'UNACCOUNTED_RUNNING_RESOURCE')
    hold=held_query(witness)
    post=record('formal-cancel-postmortem-log-01.json')
    require(post['queryId']==hold['queryId'],'POSTMORTEM_ID')
    return dict(protected=retained,source=source,platform=platforms,heldQuery=hold,
                postmortem=ref('formal-cancel-postmortem-log-01.json'),earlyOracleRecovery=backup,
                earlyFullPlatformBackup='NOT_RUN',earlyIsolatedFullStackRestore='NOT_RUN',finalPrivateBackup='NOT_RUN',
                finalIsolatedFullStackRestore='NOT_RUN',productIntake='NO_NEW_DELIVERY_BY_THIS_CHECK',
                disposition='KEEP current source and four platform services running, both current and archived API instances stopped, alternative source volume and private material',
                resumption=['A separate decision must establish a measurable positive using a still-in-flight formal fixed SQL.',
                            'Preserve this QueryId, immutable failed witness and owner/fence. Resolve UNKNOWN by an explicitly reviewed recovery condition.',
                            'Record actual native cold copies and isolated whole-stack recovery before crediting platform or final recovery.'])


QUERY='query-18b5ee00b53e4e4eafc43cc4717bd293'
CLIENT='0e224578b55b4b479d98d3fa4ff1ac46'
CONNECTION='a7913bb552eb4cd1a3f6eaf5b93cd619'
OWNER='oracle-execution-004f5b3e04084f1998201939aaeec5e6'
WITNESS='formal-witness-071127c7-2a34-40d7-9675-7cf967edfdb0.json'
RECOVERY_AREA=AREA.parent/RECOVERY


def proof_before_cas(attempt,operation,running_roles=None):
    """封闭所有投递，在独立源通道核原执行，再私存单行和原审计。同一证明仅供此次短维护使用。"""
    import hashlib
    import os
    import pwd
    import subprocess
    from pathlib import Path

    require(uuid.UUID(attempt).hex==attempt and uuid.UUID(operation).hex==operation,'ATTEMPT')
    source=ORIGINAL_IDS['oracle']
    roles=set(ORIGINAL_IDS if running_roles is None else running_roles)
    require({'oracle','platform-pg'}<=roles,'PROOF_SERVICES')
    budget=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='preserve',running_roles=roles)
    projected={'heldQuery':held_query(WITNESS),'platform':{'seal':ref('s0-blocked-seal-01.json')}}
    require(record('s0-blocked-seal-01.json')['queryId']==QUERY,'ORIGINAL_SEAL')
    archived=platform.ROOT/'docs/evidence'/TASK/RUN/'s0-blocked/originals'/WITNESS
    require(archived.read_bytes()==(AREA/WITNESS).read_bytes(),'FORMAL_ORIGINAL')
    w=record(WITNESS)
    require(w['queryId']==QUERY and w['final']['clientId']==CLIENT and w['nativeExecutionIdentity'][:5]==['60','51748','50045','3','16777219']
            and w['sqlId']=='dum3m3c96vc07' and w['cursorDelta']=={'child':'0','plan':1347626742,'executions':1,'eof':1,'rows':100,'px':0},
            'ORIGINAL_EXECUTION')
    hold=projected['heldQuery']
    require(hold['heldOwner']==OWNER and hold['fence']==2 and hold['status']=='CANCELLED'
            and hold['successEffects']==[0,0,0] and hold['cancelAudits']==1,'HOLD_TUPLE')
    started=dt.datetime.now(dt.timezone.utc)
    with contextlib.closing(observer.source_channel(source)) as channel:
        rows=channel.run("""select sys_context('USERENV','INSTANCE')||'|'||sys_context('USERENV','CON_ID')||'|'||
        (select count(*) from G4_CONTROL.OMQ_SESSIONS)||'|'||
        (select count(*) from G4_CONTROL.OMQ_SESSIONS where client_identifier='0e224578b55b4b479d98d3fa4ff1ac46'
        or (sid=60 and serial_no=51748 and audsid=50045)) from dual;""")
    require(rows==['1|3|0|0'],'ORACLE_INDEPENDENT_TERMINATION')
    ps=subprocess.check_output(['ps','-axo','pid=,command='],text=True,timeout=4)
    # 仅核本机可能承接本任务投递的可执行入口，命令行可能含私有材料，禁止保存或显示。
    process_names=('OntologyPlatform.Api.dll','OntologyPlatform.Worker.dll','workflow-m4-query.mjs','next-server')
    active=[line.split()[0] for line in ps.splitlines()
            if any(n in line for n in process_names) and ('/g4-oracle-mapping-query-001/' in line or TASK in line)
            and not any(shell in line for shell in ('-lc ','-c '))]
    require(not active,'HOST_TASK_CONSUMER')
    with contextlib.ExitStack() as stack:
        import socket
        for port in (15741,15742,15744):
            sock=stack.enter_context(socket.socket());sock.bind(('127.0.0.1',port))
    post=record('formal-cancel-postmortem-log-01.json')
    evidence=post['observations']['api']
    require(any('action=EOF ' in e and CLIENT in e and QUERY in e for e in evidence)
            and any('action=PHYSICAL_RELEASE ' in e and CLIENT in e and QUERY in e for e in evidence),'NO_RELEASE_LOG')
    end=dt.datetime.now(dt.timezone.utc)
    termination=dict(attemptId=attempt,operationId=operation,taskId=TASK,resourceRunId=RUN,
                     startedUtc=started.isoformat(),endedUtc=end.isoformat(),observer='OMQ_OBSERVER|TCPS|FREEPDB1',
                     admission=budget['attempt'],originalWitness=ref(WITNESS),postmortem=ref('formal-cancel-postmortem-log-01.json'),
                     originalWorkerContainerIds=[*API_IDS.values(),*ARCHIVED_API_IDS.values()],workerState='exited',
                     hostTaskConsumerCount=len(active),intakePortsFree=[15741,15742,15744],
                     sourceId=source,clientId=CLIENT,sqlId=w['sqlId'],sourceExecution=w['nativeExecutionIdentity'],
                     instanceId=1,conId=3,matchingPhysicalSessions=0,currentTaskSourceSessions=0,originalCursor=w['cursorDelta'],
                     currentWork=hold['currentWork'],seal=projected['platform']['seal'])
    proof_file=RECOVERY_AREA/('termination-'+attempt+'.json');platform.save(proof_file,termination)
    secret=platform.HOME_DIR/RECOVERY/'prestate'/attempt
    oldmask=os.umask(0o077)
    try:
        secret.mkdir(parents=True,mode=0o700)
        sql=f"""BEGIN READ ONLY; SET LOCAL TIME ZONE 'UTC';
        SELECT jsonb_build_object('rawRow',to_jsonb(q),'rawAudit',to_jsonb(a),'bindingConnectionId',
          convert_from(q."BindingBytes",'UTF8')::jsonb#>>'{{binding,connectionId}}','platform',current_database(),
          'systemIdentifier',(select system_identifier::text from pg_control_system()),'org',q."OrganizationId",
          'databaseUser',current_user,'requestSha256',encode(sha256(q."RequestBytes"),'hex'),
          'bindingSha256',encode(sha256(q."BindingBytes"),'hex'),
          'stableRowSha256',encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'),
          'cancelAuditSha256',encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex'))
        FROM semantic_query."Queries" q JOIN governance.audit_records a ON a."Resource"=q."Id"
        AND a."Action"='data.query.cancel' AND a."Outcome"='allowed' WHERE q."Id"='{QUERY}'; COMMIT;"""
        cmd=['docker','--context','desktop-linux','exec','-i','--user','postgres',ORIGINAL_IDS['platform-pg'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
        pre=secret/'row-and-audit.json'
        with pre.open('xb') as out,(secret/'pg.stderr').open('xb') as errors:
            r=subprocess.run(cmd,input=sql.encode(),stdout=out,stderr=errors,timeout=10)
        require(not r.returncode,'PRIVATE_PRESTATE_READ')
        saved=json.loads(pre.read_bytes())
        q=saved['rawRow'];audit=saved['rawAudit']
        require(saved['bindingConnectionId']==q['ConnectionId']==CONNECTION and q['Id']==QUERY and q['LeaseOwner']==OWNER
                and q['CancelRequested'] and q['ExecutionStatus']=='CANCELLED' and q['Fence']==2
                and q['RequestHash']==saved['requestSha256'] and saved['org']=='org-demo' and saved['platform']=='mapping','PRIVATE_TUPLE')
        received=dt.datetime.now(dt.timezone.utc)
        proof=dict(taskId=TASK,runId=RUN,attemptId=attempt,operationId=operation,operatorId='os-uid-'+str(os.getuid()),
                   database=saved['platform'],databaseUser=saved['databaseUser'],organizationId=q['OrganizationId'],
                   systemIdentifier=saved['systemIdentifier'],queryId=QUERY,connectionId=CONNECTION,owner=OWNER,
                   originalFence=1,terminalFence=2,clientId=CLIENT,instanceId=1,conId=3,sid=60,serial=51748,audsid=50045,
                   sqlId=w['sqlId'],sqlExecId=16777219,platformContainerId=ORIGINAL_IDS['platform-pg'],sourceContainerId=source,
                   createdUtc=q['CreatedAtUtc'],deadlineUtc=q['DeadlineAtUtc'],completedUtc=q['CompletedAtUtc'],
                   leaseUntilUtc=q['LeaseUntilUtc'],cancelAuditId=audit['Id'],sealSha256=projected['platform']['seal']['sha256'],
                   terminationProofSha256=ex.sha(proof_file.read_bytes()),verifiedUtc=started.isoformat(),
                   validUntilUtc=(started+dt.timedelta(minutes=4)).isoformat(),
                   **{k:saved[k] for k in ('requestSha256','bindingSha256','stableRowSha256','cancelAuditSha256')})
        platform.save(secret/'proof.json',proof)
        public=dict(proof=proof,phase='PRESTATE_ONLY',osUser=pwd.getpwuid(os.getuid()).pw_name,dbPrivateSnapshotBytes=pre.stat().st_size,
                    rawPrivateSha256=ex.sha(pre.read_bytes()),privateProofSha256=ex.sha((secret/'proof.json').read_bytes()),
                    privatePath=str(pre.relative_to(platform.HOME_DIR)),atUtc=received.isoformat())
        platform.save(RECOVERY_AREA/('prestate-'+attempt+'.json'),public)
        return public
    finally:
        os.umask(oldmask)


def engine_step(stage,*args,stdin=None,timeout=45):
    """记录资源命令真实双流。数据库私有前态和服务日志走专用去密路径。"""
    args=['docker','--context','desktop-linux',*args]
    r=ex.run(args,platform.ROOT,task=TASK,run_id=RECOVERY,stage='omq-recovery-'+stage,stdin=stdin,
             timeout=timeout,input_key=ex.sha(ex.encoded(args)+(stdin or b'')))
    require(r.returncode==0,stage+'_'+r.receipt['commandId'])
    return r.stdout.decode().strip()


def one_helper(stage,volume,target,script,*,image=None,user='0',bind=None,timeout=45,write=False):
    """一次只用一个定额 helper。仅替代清单上的卷可被写入，冷备和检查始终只读原卷。"""
    import os
    from workflow_oracle_mapping_resources import PROBE
    original=record('formal-resources.json')['volumes']
    source=record('source-create-01.json')['volume']
    alternative=record('recovery-01-final.json')['replacementVolume']
    manifest=RECOVERY_AREA/'replacement-resources.json'
    restored=json.loads(manifest.read_bytes())['volumes'] if manifest.exists() else {}
    require(volume in {source,alternative,*original.values(),*restored.values()} and (not write or volume in {alternative,*restored.values()}),'HELPER_VOLUME')
    image=image or PROBE
    require(image in (PROBE,platform.IMAGES['platform-pg']) and target in ('/source','/var/lib/postgresql'),'HELPER_SCOPE')
    nonce=uuid.uuid4().hex
    args=['create','--pull=never','--read-only','--network=none','--cap-drop=ALL','--security-opt=no-new-privileges',
          '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=32','--tmpfs','/tmp:rw,nosuid,nodev,size=16m',
          '--user',user,'--label','ontology.task='+TASK,'--label','ontology.run='+RECOVERY,'--label','ontology.attempt='+nonce,
          '--mount',f'type=volume,src={volume},dst={target},volume-nocopy'+('' if write else ',readonly')]
    if bind or write:
        # 冷读取/还原涉及不同服务的固定 UID；能力仅作用于列明卷，原件挂载一直只读。
        args+=['--cap-add=DAC_OVERRIDE']
        if write:args+=['--cap-add=CHOWN','--cap-add=FOWNER','--cap-add=FSETID']
    if bind:
        path,readonly=bind
        require(path.is_dir() and not path.is_symlink() and path.resolve()==path and path.is_relative_to(platform.HOME_DIR/RECOVERY)
                and path.stat().st_uid==os.getuid() and not path.stat().st_mode & 0o077,'PRIVATE_BIND')
        args+=['--mount',f'type=bind,src={path},dst=/backup'+(',readonly' if readonly else '')]
    cid=engine_step(stage+'-create',*args,'--entrypoint=/bin/sh',image,'-ec',script)
    require(re.fullmatch(CID,cid),'HELPER_ID')
    registry=RECOVERY_AREA/('helper-'+nonce+'.json')
    detail=dict(attemptId=nonce,taskId=TASK,runId=RECOVERY,id=cid,volume=volume,write=write,stage=stage,status='CREATED')
    platform.save(registry,detail)
    def read_state():
        info=engine_step('helper-state','inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{json .Mounts}}',cid).split('|')
        require(info[:3]==[cid,image.split('@')[-1],nonce],'HELPER_IDENTITY')
        mounts=json.loads(info[6])
        require([m['Name'] for m in mounts if m['Type']=='volume']==[volume] and
                [m['RW'] for m in mounts if m['Type']=='volume']==[write],'HELPER_MOUNT')
        return info[3:6]
    try:
        require(read_state()[0]=='created','HELPER_PRE')
        result=engine_step(stage+'-execute','start','-a',cid,timeout=timeout)
        require(read_state()==['exited','0','false'],'HELPER_FAILED')
        detail['status']='PASS'
        return result
    finally:
        state=read_state();detail['after']=state
        if state[0] in ('exited','created'):
            engine_step('helper-release','rm',cid)
            require(not engine_step('helper-absent','ps','-aq','--no-trunc','--filter','id='+cid),'HELPER_REMAINS')
            detail['removed']=True
        platform.save(registry,detail,True)


def fuseki_journals(files):
    """只核停机后可见的文件。Jena 6.2.0 释放的是文件锁，锁路径及其 PID 可以保留。"""
    observed={}
    for line in files:
        match=re.fullmatch(r'((?:Data-[0-9]+/)?tdb[.]lock|Data-[0-9]+/journal[.]jrnl)[|]([0-9]+)',line)
        require(match and match[1] not in observed,'TDB_FILE_OBSERVATION')
        observed[match[1]]=int(match[2])
    journals={name:size for name,size in observed.items() if name.endswith('/journal.jrnl')}
    require(journals and all(size==0 for size in journals.values()),'TDB_JOURNAL_UNCONFIRMED')
    return journals


def fuseki_termination(row):
    """接受已观测的有界进程退出；早期因锁路径仍存在而拒绝的原件保留原判。"""
    observed=row.get('after',{})
    legacy=row.get('status')=='BLOCKED' and row.get('reason')=='ORACLE_ADMISSION_TDB_CLOSE_UNCONFIRMED'
    # 已审旧窗口关闭日志禁用；其原进程退出可复用，不能用未知日志放行或补写 clean。
    if legacy:require(row.get('logSha256')==ex.sha(b'') and row.get('shutdownLogMarker') is False,'TDB_LEGACY_LOG')
    require(row.get('role')=='fuseki' and observed.get('Status')=='exited' and
            observed.get('ExitCode') in (0,143) and observed.get('OOMKilled') is False and
            row.get('logExit')==0 and re.fullmatch(CID,row.get('logSha256','')) and
            (row.get('status')=='PROCESS_EXITED' and row.get('termSent') is True or legacy),'TDB_PROCESS_EXIT')
    return fuseki_journals(row.get('tdbCloseFiles',[]))


def fuseki_reuse_basis(cid,registry):
    """将当前引擎退出代次、准确替代卷及已审冻结检查点的两份全读原件绑定在一起。"""
    import workflow_oracle_mapping_recovery_components as components
    prior=components.prior_qualifications()
    restored=components.frozen('restored-fuseki.json')
    require(prior['fuseki']=='ACCEPTED_FOR_FROZEN_CHECKPOINT' and
            cid==prior['fusekiId']==restored['replacementId'] and restored['sourceId']==ORIGINAL_IDS['fuseki'] and
            restored['volume']==registry['volumes']['fuseki']==ALT_PROJECT+'_'+platform.VOLUMES['fuseki'] and
            restored['status']=='REPLACEMENT_COLD_BYTES_VERIFIED','TDB_CHECKPOINT_OWNER')
    current=json.loads(engine_step('tdb-stopped-state','inspect','-f','{{json .State}}',cid))
    require(current['Status']=='exited' and not current['Error'] and not current['OOMKilled'],'TDB_REUSE_EXIT')
    after={key:current[key] for key in ('Status','ExitCode','OOMKilled','FinishedAt')}
    records=[json.loads(ex.ordinary(path).read_bytes()) for path in RECOVERY_AREA.glob('stop-*.json')]
    matches=[r for r in records if r.get('id')==cid and r.get('group')=='replacement' and r.get('after')==after]
    require(len(matches)==1,'TDB_REUSE_STOP_GENERATION')
    fuseki_termination(matches[0])
    frozen=components.frozen('graphs-second-open.json')
    return dict(archiveSha256=prior['archive'],volume=restored['volume'],finishedAt=after['FinishedAt'],
                cleanShutdown='UNKNOWN',checkpointRecovery=prior['fuseki'],scan=frozen['scan'],graphs=frozen['graphs'])


def current_fuseki_graphs(cid,basis):
    """业务入口开放前，在本次启动的准确副本重新核读默认图、全部命名图和发布图。"""
    import doris_keep_fuseki as rdf
    engine_step('tdb-read-ready','exec',cid,'curl','--noproxy','*','--silent','--fail','--retry','20',
                '--retry-connrefused','--retry-delay','1','--retry-max-time','20','--max-time','2',
                'http://127.0.0.1:3030/$/ping',timeout=25)
    scan=rdf.full_scan(cid)
    require(scan==basis['scan'],'TDB_CURRENT_SCAN')
    current=[]
    for expected in basis['graphs']:
        triples=rdf.triples(cid,'ontology',expected['graph'])
        current.append(dict(graph=expected['graph'],triples=len(triples),sha256=rdf.fingerprint(triples)))
    require(current==basis['graphs'],'TDB_CURRENT_RELEASE_GRAPHS')
    return dict(status='CURRENT_GRAPHS_VERIFIED',scan=scan,graphs=current)


def require_current_fuseki(cid,started,pid):
    """每次正式宿主绑定都核同一进程代次的启动与当前全图库原件。"""
    import workflow_oracle_mapping_recovery_components as components
    matches=[]
    for path in RECOVERY_AREA.glob('start-*.json'):
        row=json.loads(ex.ordinary(path).read_bytes())
        if (row.get('id'),row.get('startedAt'),row.get('pid'))==(cid,started,pid):
            matches.append(row)
    require(len(matches)==1,'TDB_PRODUCT_GENERATION')
    row=matches[0]
    if cid=='52f84c336a3ade30341a3e20fbda302677fd77ea5a71237b801e3dc5b508d9a6' and (started,pid)==('2026-11-21T01:19:10.950405047Z',94067) and row.get('productUse')=='BLOCKED' and row.get('reason')=='ORACLE_ADMISSION_TDB_CURRENT_SCAN':
        from workflow_oracle_mapping_continuity import graph_qualification
        graph_qualification(platform.ROOT,cid,started,pid)
        return row['attempt']
    frozen=components.frozen('graphs-second-open.json')
    require(row['stage']=='product-resume-01' and row['role']=='fuseki' and row['status']=='RUNNING'
            and row.get('productUse')=='CURRENT_GRAPHS_VERIFIED'
            and row.get('currentGraphs')==dict(status='CURRENT_GRAPHS_VERIFIED',scan=frozen['scan'],graphs=frozen['graphs']),
            'TDB_PRODUCT_CURRENT_GRAPHS')
    return row['attempt']


def native_stop(group,role,roles,operation):
    """先核阶段实际配额，用原生停机/有界 TERM；后验不确定即停止序列。"""
    import subprocess
    from workflow_oracle_mapping_resources import before_source
    require(group in ('original','replacement') and role in ORIGINAL_IDS,'OWNED_GROUP_ROLE')
    phase='preserve' if group=='original' else 'restore'
    product=platform.product_run()
    if product:
        require(group=='replacement','TDB_PRODUCT_GROUP')
        phase=product
    if role=='fuseki':require(role in roles,'TDB_LIVE_OWNER')
    check=before_source(platform.ROOT,TASK,platform_stage=True,phase=phase,running_roles=roles)
    cid=ORIGINAL_IDS[role] if group=='original' else (ALT_ORACLE if role=='oracle' else json.loads((RECOVERY_AREA/'replacement-resources.json').read_bytes())['ids'][role])
    step=uuid.uuid4().hex
    path=RECOVERY_AREA/('stop-'+step+'.json')
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    row=dict(role=role,id=cid,group=group,operation=operation,resourceAttempt=check['attempt'],startedUtc=started,status='STARTED')
    platform.save(path,row)
    try:
        if role=='oracle':
            raw=engine_step('oracle-zero','exec','-i',cid,'sqlplus','-s','/ as sysdba',stdin=b"whenever sqlerror exit failure\nset pages 0 heading off feedback off\nselect count(*) from v$session where username='FIXTURE_READER';\nexit success\n")
            require(raw=='0','ORACLE_READER_BUSY')
            msg=engine_step('oracle-shutdown','exec','-i',cid,'sqlplus','-s','/ as sysdba',stdin=b'whenever sqlerror exit failure\nshutdown immediate;\nexit success\n',timeout=90)
            row['nativeShutdown']=all(m in msg.lower() for m in ('database closed','database dismounted','oracle instance shut down'))
            require(row['nativeShutdown'],'NATIVE_ORACLE_SHUTDOWN')
        elif role=='platform-pg':
            engine_step('pg-fast','exec','--user','postgres',cid,'sh','-ec','test "$(id -u)" = 999 && pg_ctl status -D "$PGDATA" >/dev/null && exec pg_ctl stop -D "$PGDATA" -m fast -W')
        elif role=='fuseki':
            row.update(cleanShutdown='UNKNOWN',checkpointRecovery='NOT_VERIFIED',productUse='NOT_VERIFIED')
            row['tdbLocksBefore']=engine_step('tdb-active-locks','exec',cid,'sh','-ec','cd /fuseki; find databases/ontology -name tdb.lock -type f -print | sort').splitlines()
            require(all(re.fullmatch(r'databases/ontology/(?:Data-[0-9]+/)?tdb.lock',n) for n in row['tdbLocksBefore']), 'TDB_LOCK_BASIS')
        if role=='platform-pg':
            engine_step('pg-wait','wait',cid,timeout=45)
        elif engine_step('native-state','inspect','-f','{{.State.Status}}',cid)=='running':
            engine_step('term','stop','--signal=TERM','--timeout=-1',cid,timeout=45)
            if role=='fuseki':row['termSent']=True
        elif role=='fuseki':
            require(False,'TDB_EXIT_BEFORE_TERM')
        state=json.loads(engine_step('stopped-state','inspect','-f','{{json .State}}',cid))
        row['after']={k:state[k] for k in ('Status','ExitCode','OOMKilled','FinishedAt')}
        require(state['Status']=='exited' and not state['OOMKilled'] and not state['Error'] and state['ExitCode'] in (0,143),'NATIVE_EXIT')
        if role=='fuseki':row['processExited']=True
        logs=subprocess.run(['docker','--context','desktop-linux','logs','--since',started,cid],capture_output=True,timeout=8)
        raw=logs.stdout+logs.stderr
        marker=bool(re.search(rb'shut(?:ting)?[ -]?down|\bstopped\b|terminat(?:ing|ion)',raw,re.I))
        row.update(logExit=logs.returncode,shutdownLogMarker=marker,logSha256=ex.sha(raw))
        require(logs.returncode==0 and not re.search(rb'out of memory|fatal (?:error|exception)|data corruption',raw,re.I),'NATIVE_LOG_ERROR')
        remaining=set(roles)-{role}
        if role in ('platform-pg','fuseki'):
            before_source(platform.ROOT,TASK,platform_stage=True,phase=phase,running_roles=remaining)
            manifest=record('formal-resources.json') if group=='original' else json.loads((RECOVERY_AREA/'replacement-resources.json').read_bytes())
            if role=='platform-pg':
                raw=one_helper('pg-control',manifest['volumes'][role],'/var/lib/postgresql',
                               'export LC_ALL=C; pg_controldata /var/lib/postgresql/18/docker > /tmp/control 2>/tmp/warnings; test ! -s /tmp/warnings; sed -n "s/^Database cluster state: *//p" /tmp/control',
                               image=platform.IMAGES['platform-pg'],user='999')
                row['controlState']=raw
                require(raw=='shut down' and marker,'PG_NOT_CLEAN')
            else:
                files=one_helper('tdb-closed',manifest['volumes'][role],'/source',
                                 'cd /source; test -d databases/ontology; find databases/ontology -type f \\( -name tdb.lock -o -name journal.jrnl \\) -printf "%P|%s\\n" | sort')
                row['tdbCloseFiles']=files.splitlines()
                row['allTdbLocksRemoved']=not any(line.split('|')[0].endswith('tdb.lock') for line in files.splitlines())
                require(not re.search(rb"can't expel: active transactions|transactionexception|failed to (?:unlock|close)|recovery failed",raw,re.I),
                        'TDB_TRANSACTION_OR_CLOSE_ERROR')
                row['observedJournals']=fuseki_journals(row['tdbCloseFiles'])
        else:
            require(state['ExitCode']==0 or marker or row.get('nativeShutdown'),'NATIVE_CLOSE_UNCONFIRMED')
        row['status']='PROCESS_EXITED' if role=='fuseki' else 'CLEAN_STOP'
    except Exception as exc:
        row['status']='BLOCKED'
        row['reason']=str(exc) if str(exc).startswith('ORACLE_ADMISSION_') else type(exc).__name__
        raise
    finally:
        row['endedUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
        platform.save(path,row,True)
    return row


def start_owned(group,role,running):
    """按创建回执仅启动一个准确已退出实例，并复核新合集、原持久卷及额度。"""
    import time
    require(group in ('original','replacement') and role in ORIGINAL_IDS,'OWNED_GROUP_ROLE')
    phase='preserve' if group=='original' else 'restore'
    product=platform.product_run()
    if product:
        require(group=='replacement','TDB_PRODUCT_GROUP')
        phase=product
    current=set(running);after=current|{role}
    require(role not in current and role in ORIGINAL_IDS,'START_ROLE')
    pre=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase=phase,running_roles=current,planned_roles=after)
    basis=None
    if group=='original':
        cid=ORIGINAL_IDS[role]
        clean=[json.loads(p.read_bytes()) for p in RECOVERY_AREA.glob('stop-*.json')]
        require(any(row['id']==cid and row['status']=='CLEAN_STOP' for row in clean),'ORIGINAL_CLEAN_STATE_'+role)
    else:
        registry=json.loads((RECOVERY_AREA/'replacement-resources.json').read_bytes()) if role!='oracle' else {}
        cid=ALT_ORACLE if role=='oracle' else registry['ids'][role]
        if product and role=='fuseki':basis=fuseki_reuse_basis(cid,registry)
    nonce=uuid.uuid4().hex
    receipt=dict(attempt=nonce,stage=phase,role=role,id=cid,resourceAttempt=pre['attempt'],status='STARTING')
    if basis:receipt.update(checkpoint=basis,productUse='NOT_VERIFIED')
    out=RECOVERY_AREA/('start-'+nonce+'.json')
    platform.save(out,receipt)
    try:
        engine_step('start-'+role,'start',cid,timeout=50)
        if role in ('oracle','platform-pg'):
            until=time.monotonic()+160
            while time.monotonic()<until:
                state=engine_step('wait-health','inspect','-f','{{.State.Status}}|{{.State.Health.Status}}',cid)
                if state=='running|healthy':break
                require(state.startswith('running|'),'START_EXITED')
                time.sleep(2)
            require(state=='running|healthy','HEALTH_TIMEOUT')
        post=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase=phase,running_roles=after)
        receipt.update(status='RUNNING',post=post['attempt'])
        if basis:
            fmt='{{.State.Status}}|{{.State.StartedAt}}|{{.State.Pid}}'
            generation=engine_step('tdb-generation','inspect','-f',fmt,cid)
            state,started,pid=generation.split('|')
            require(state=='running' and int(pid)>0,'TDB_LIVE_OWNER')
            receipt.update(startedAt=started,pid=int(pid))
            receipt['currentGraphs']=current_fuseki_graphs(cid,basis)
            require(engine_step('tdb-generation-after','inspect','-f',fmt,cid)==generation,'TDB_PRODUCT_GENERATION')
            receipt['productUse']='CURRENT_GRAPHS_VERIFIED'
    except Exception as exc:
        if basis:
            receipt['productUse']='BLOCKED'
            receipt['reason']=str(exc) if str(exc).startswith('ORACLE_ADMISSION_') else type(exc).__name__
        raise
    finally:
        platform.save(out,receipt,True)
    return receipt


def recover_fixed_row():
    """在已核隔离 PG 和物理构建上只投递一次。封闭、证据有效期和准确数据库在两端分别核验。"""
    import os
    import subprocess
    nonce=uuid.uuid4().hex;operation=uuid.uuid4().hex
    build=platform.build.validate('api',TASK)
    query_build=platform.build.validate('query',TASK)
    qualified=[json.loads(p.read_bytes()) for p in RECOVERY_AREA.glob('real-pg-*.json')]
    require(any(r['build']==query_build and r['status']=='PASS' and r['total']>=4 and r['released'] for r in qualified),'CAS_TEST_NOT_QUALIFIED')
    require(os.getuid()==501 and not (RECOVERY_AREA/'real-maintenance-dispatch.json').exists(),'MAINTENANCE_ONCE')
    verified=proof_before_cas(nonce,operation,{'oracle','platform-pg'})
    proof=verified['proof']
    private=platform.HOME_DIR/RECOVERY/'prestate'/nonce/'proof.json'
    raw=private.read_bytes()
    require(ex.sha(raw)==verified['privateProofSha256'] and json.loads(raw)==proof,'CAS_INPUT_REOPEN')
    api=platform.ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    # 采用与隔离 PG 测试相同的私有挂载。连接材料只在验证器不可外读的 tmpfs 中供正式 Npgsql 客户端消费。
    script=('umask 077; set -eu; test "$(id -u)" = 501; '
            'printf "Host=platform-pg;Port=5432;Database=mapping;Username=postgres;SSL Mode=VerifyFull;Root Certificate=/ca;Password=%s" '
            '"$(cat /auth)" > /tmp/maintenance.dsn; exec dotnet /app/OntologyPlatform.Api.dll --recover-omq-s0')
    args=['create','--pull=never','-i','--network',platform.PROJECT+'_platform-internal','--read-only','--user',str(os.getuid())+':'+str(os.getgid()),
          '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--security-opt=no-new-privileges','--cap-drop=ALL',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RECOVERY,
          '--label','ontology.attempt='+nonce,'--mount','type=bind,src='+str(api)+',dst=/app,readonly',
          '--mount','type=bind,src='+str(platform.PG/'password')+',dst=/auth,readonly','--mount','type=bind,src='+str(platform.PG/'server.crt')+',dst=/ca,readonly']
    env={'OMQ_RECOVERY_DSN_FILE':'/tmp/maintenance.dsn','OMQ_RECOVERY_OPERATOR':proof['operatorId'],
         'OMQ_RECOVERY_PROOF_SHA256':verified['privateProofSha256'],'OMQ_RECOVERY_TERMINATION_SHA256':proof['terminationProofSha256'],
         'OMQ_RECOVERY_SEAL_SHA256':proof['sealSha256'],'HOME':'/tmp','DOTNET_EnableDiagnostics':'0'}
    for key,value in env.items():args+=['-e',key+'='+value]
    cid=engine_step('maintenance-create',*args,'--entrypoint=/bin/sh',platform.PROBE,'-ec',script)
    require(re.fullmatch(CID,cid),'MAINTENANCE_ID')
    path=RECOVERY_AREA/('maintenance-'+nonce+'.json')
    receipt=dict(attempt=nonce,operationId=operation,queryId=QUERY,validatorId=cid,build=build,proofSha256=verified['privateProofSha256'],status='CREATED')
    platform.save(path,receipt)
    def state():
        values=engine_step('maintenance-id','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid).split()
        require(values[:3]==[cid,platform.PROBE.split('@')[1],nonce],'MAINTENANCE_OWNER')
        return values[3:]
    try:
        require(state()[0]=='created' and not (RECOVERY_AREA/'real-maintenance-dispatch.json').exists(),'MAINTENANCE_PRE')
        platform.save(RECOVERY_AREA/'real-maintenance-dispatch.json',dict(operationId=operation,attempt=nonce,queryId=QUERY,cid=cid))
        start=dt.datetime.now(dt.timezone.utc)
        res=ex.run(['docker','--context','desktop-linux','start','-a','-i',cid],platform.ROOT,task=TASK,run_id=RECOVERY,
                   stage='one-real-maintenance-cas',input_key=ex.sha(raw),stdin=raw,timeout=32)
        receipt.update(startedUtc=start.isoformat(),endedUtc=dt.datetime.now(dt.timezone.utc).isoformat(),
                       commandId=res.receipt['commandId'],exitCode=res.returncode,after=state())
        require(not res.returncode and receipt['after']==['exited','0','false'],'MAINTENANCE_OUTCOME')
        result=json.loads(res.stdout)
        require(result['status']=='TASK_LEVEL_RECOVERY' and result['operationId']==operation,'MAINTENANCE_OUTPUT')
        receipt['commitEnvelope']=result
    finally:
        after=state()
        if after[0] in ('exited','created'):
            engine_step('maintenance-release','rm',cid)
            receipt['validatorAbsent']=not engine_step('maintenance-post','ps','-aq','--no-trunc','--filter','id='+cid)
        platform.save(path,receipt,True)
    # 新连接完整对账两列以外的查询字节，核原取消审计字节、维护主体与其余零成功事实。
    sql=f"""SET LOCAL TIME ZONE 'UTC';
        SELECT jsonb_build_object('id',q."Id",'state',q."ExecutionStatus",'fence',q."Fence",'owner',q."LeaseOwner",'lease',q."LeaseUntilUtc",
        'stable',encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'),
        'resultBytes',octet_length(q."ResultCiphertext"),'receiptCount',jsonb_array_length(convert_from(q."BindingBytes",'UTF8')::jsonb->'receipts'),
        'audits',(SELECT jsonb_agg(jsonb_build_object('id',a."Id",'action',a."Action",'outcome',a."Outcome",'actor',a."Actor",
            'trace',a."TraceId",'correlation',a."CorrelationId",'sha',encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex')))
            FROM governance.audit_records a WHERE a."Resource"=q."Id" AND a."Action" IN ('data.query.execute','data.query.cancel','data.query.cleanup.recover') AND a."Outcome"='allowed'))
        FROM semantic_query."Queries" q WHERE q."Id"='{QUERY}';"""
    output,command=platform.read_pg(sql.encode(),'maintenance-postcondition')
    current=json.loads(output);audits=current['audits']
    require(current['state']=='CANCELLED' and current['fence']==2 and current['owner'] is None and current['lease'] is None
            and current['stable']==proof['stableRowSha256'] and current['resultBytes']==current['receiptCount']==0
            and len(audits)==2 and any(a['id']==proof['cancelAuditId'] and a['sha']==proof['cancelAuditSha256'] for a in audits)
            and any(a['action']=='data.query.cleanup.recover' and a['actor']==proof['operatorId']
                    and a['trace']==operation and a['correlation']==nonce for a in audits),'MAINTENANCE_POSTCONDITION')
    receipt.update(status='TASK_LEVEL_RECOVERY',newConnection=command,post=current,originalCleanup250ms='NOT_QUALIFIED')
    platform.save(path,receipt,True)
    return receipt


def archive_identity(path,limit):
    """完整读取安全归档。内部相对链接可以保留，拒绝越界目标、特殊文件及穿过链接的成员。"""
    import hashlib,os,posixpath,stat,tarfile
    from pathlib import PurePosixPath
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600
            and path.resolve()==path and st.st_size<=limit,'PRIVATE_ARCHIVE')
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    names={};links={};expanded=0
    with tarfile.open(path,'r:') as archive:
        for item in archive:
            name=PurePosixPath(item.name)
            require(not name.is_absolute() and '..' not in name.parts and name not in names and
                    (item.isdir() or item.isfile() or item.issym() or item.islnk()),'ARCHIVE_MEMBER')
            if item.issym() or item.islnk():
                dest=PurePosixPath(item.linkname)
                dest=PurePosixPath(posixpath.normpath(str((name.parent/dest) if item.issym() else dest)))
                require(not dest.is_absolute() and '..' not in dest.parts,'ARCHIVE_LINK')
                links[name]=dest
            names[name]=item.type
            expanded+=item.size
            require(expanded<=limit and len(names)<=100000,'ARCHIVE_EXPANSION')
    require(names and all(parent not in links for name in names for parent in name.parents)
            and all(target in names for target in links.values()),'ARCHIVE_TREE')
    require([st.st_ino,st.st_size,st.st_ctime_ns]==[path.stat().st_ino,path.stat().st_size,path.stat().st_ctime_ns],'ARCHIVE_CHANGED')
    return dict(bytes=st.st_size,sha256=digest,members=len(names),expanded=expanded,identity=[st.st_dev,st.st_ino,st.st_size,st.st_ctime_ns])


def cold_archive(role):
    """每个准确原卷只复制一次，登记后重新核算已落盘量。仅 Fuseki 可在独立冷验证前保留待验原件。"""
    import os
    require(role in ORIGINAL_IDS,'COLD_ROLE')
    sample=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='preserve',running_roles=[])
    completed=[json.loads(p.read_bytes()) for p in RECOVERY_AREA.glob('maintenance-*.json')]
    require(len(completed)==1 and completed[0]['status']=='TASK_LEVEL_RECOVERY','MAINTENANCE_REQUIRED')
    origin=ORIGINAL_IDS[role]
    stops=sorted((json.loads(p.read_bytes()) for p in RECOVERY_AREA.glob('stop-*.json')),key=lambda x:x['endedUtc'])
    last=[r for r in stops if r['id']==origin][-1]
    fuse_pending=role=='fuseki'
    if fuse_pending:fuseki_termination(last)
    else:require(last['status']=='CLEAN_STOP','COLD_TERMINATION')
    group='source' if role=='oracle' else 'platform'
    private=platform.HOME_DIR/RECOVERY
    directory=private/group;directory.mkdir(mode=0o700,exist_ok=True)
    source_spec=record('source-create-01.json')
    vol=source_spec['volume'] if role=='oracle' else record('formal-resources.json')['volumes'][role]
    ledger_path=RECOVERY_AREA/'archive-ledger.json'
    ledger=json.loads(ledger_path.read_bytes()) if ledger_path.exists() else dict(taskId=TASK,operation=RECOVERY,archives={})
    files=('database.tar','trust-and-auth.tar') if role=='oracle' else (role+'.tar',)
    require(all(not (directory/n).exists() and group+'/'+n not in ledger['archives'] for n in files),'COLD_EXISTS')
    if role=='oracle':
        script="""cd /source; umask 077
test -d g4-tls && test -d dbconfig/FREE/.tls-wallet && test -d clientWallet && test -d dbconfig/FREE/dbs
tar --sparse --numeric-owner --xattrs --acls --exclude=./g4-tls --exclude=./clientWallet --exclude=./dbconfig/FREE/.tls-wallet --exclude=./dbconfig/FREE/dbs -cpf /backup/database.tar .
tar --sparse --numeric-owner --xattrs --acls -cpf /backup/trust-and-auth.tar ./g4-tls ./clientWallet ./dbconfig/FREE/.tls-wallet ./dbconfig/FREE/dbs
sync"""
    else:
        script='cd /source; umask 077; tar --sparse --numeric-owner --xattrs --acls -cpf /backup/'+files[0]+' .; sync'
    one_helper('cold-'+role,vol,'/source',script,bind=(directory,False),timeout=420)
    total=0;limit=max(sample['platformDisk']['sourceVolumeCaps'].values()) if role=='oracle' else sample['platformDisk']['platformCopyCeiling']
    for name in files:
        facts=archive_identity(directory/name,limit)
        total+=facts['bytes']
        ledger['archives'][group+'/'+name]=dict(**facts,sourceId=origin,volume=vol,privatePath=group+'/'+name,
            state='COLD_PENDING_NATIVE_TDB2' if fuse_pending else 'COLD_VERIFIED_ARCHIVE')
    if role!='oracle':
        total=sum(v['bytes'] for k,v in ledger['archives'].items() if k.startswith('platform/'))
    require(total<=limit,'COLD_REALIZED_CAP')
    platform.save(ledger_path,ledger,ledger_path.exists())
    post=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='preserve',running_roles=[])
    return dict(role=role,bytes=total,post=post['attempt'],archives=files)


def host_private_archive():
    """一次不解析地保全实际 API/PG 配置、PFX/keyring、钱包及源认证材料，只报告归档身份。"""
    import os,subprocess
    out=platform.HOME_DIR/RECOVERY/'host'
    out.mkdir(mode=0o700)
    path=out/'materials.tar'
    args=['/usr/bin/tar','-cpf',str(path),'-C',str(platform.HOME_DIR),'platform','reader','oracle.env','reader-password','observer-password']
    old=os.umask(0o077)
    try:
        proc=subprocess.run(args,capture_output=True,timeout=45)
    finally:
        os.umask(old)
    require(proc.returncode==0,'HOST_PRIVATE_BACKUP')
    row=archive_identity(path,128*1024**2)
    platform.save(RECOVERY_AREA/'host-materials.json',dict(privatePath='host/materials.tar',**row))
    return row


def create_replacements():
    """从原任务实际 Compose 和保全的宿主材料建立隔离副本，创建回执逐资源绑定实际 ID。"""
    import os,subprocess
    from pathlib import Path
    pre=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='preserve',running_roles=[])
    ledger=json.loads((RECOVERY_AREA/'archive-ledger.json').read_bytes())['archives']
    require(set(ledger)=={'source/database.tar','source/trust-and-auth.tar',*['platform/'+s+'.tar' for s in platform.VOLUMES]},'INCOMPLETE_CHECKPOINT')
    private=platform.HOME_DIR/RECOVERY
    target=private/'restored-host'
    materials=private/'host/materials.tar';saved=json.loads((RECOVERY_AREA/'host-materials.json').read_bytes())
    require(archive_identity(materials,128*1024**2)['sha256']==saved['sha256'],'HOST_ARCHIVE_DRIFT')
    if not target.exists():
        target.mkdir(mode=0o700)
        result=subprocess.run(['/usr/bin/tar','-xpf',str(materials),'-C',str(target)],capture_output=True,timeout=45)
        require(result.returncode==0,'HOST_UNPACK')
    import hashlib,tarfile
    require(target.resolve()==target and not target.stat().st_mode & 0o077,'HOST_RESTORE_OWNER')
    with tarfile.open(materials,'r:') as archive:
        expected=set()
        for member in archive:
            destination=target/member.name
            if destination.name.startswith('._'):
                # bsdtar 在 macOS 将 AppleDouble 成员恢复为目标文件的扩展属性。
                actual=destination.with_name(destination.name[2:])
                original=platform.HOME_DIR/actual.relative_to(target)
                require(actual.exists() and original.exists()
                        and ex.sha(subprocess.check_output(['/usr/bin/xattr','-lx',str(actual)],timeout=5))==
                            ex.sha(subprocess.check_output(['/usr/bin/xattr','-lx',str(original)],timeout=5)),'HOST_EXTENDED_METADATA')
                continue
            original=platform.HOME_DIR/member.name
            require((destination.stat().st_mode & 0o7777,destination.stat().st_uid,destination.stat().st_gid)==
                    (original.stat().st_mode & 0o7777,original.stat().st_uid,original.stat().st_gid),'HOST_RESTORE_PERMISSIONS')
            require(destination.resolve()==destination and destination.exists(),'HOST_RESTORE_PATH')
            expected.add(destination)
            if member.isfile():
                with archive.extractfile(member) as old, destination.open('rb') as copy:
                    require(hashlib.file_digest(old,'sha256').digest()==hashlib.file_digest(copy,'sha256').digest(),'HOST_RESTORE_BYTES')
        require(set(target.rglob('*'))==expected,'HOST_RESTORE_SET')
    specbytes=platform.COMPOSE.read_bytes()
    require(ex.sha(specbytes)==record('formal-planned.json')['composeSha256'],'ORIGINAL_COMPOSE')
    spec=json.loads(specbytes);spec['name']=ALT_PROJECT
    operation=uuid.uuid4().hex
    for role,service in spec['services'].items():
        require(role in platform.VOLUMES,'RESTORE_SERVICE')
        volumes=[]
        for entry in service['volumes']:
            if isinstance(entry,dict):
                require(entry['type']=='bind' and entry['read_only'] is True,'COMPOSE_BIND_ACCESS')
                parts=[entry['source'],entry['target'],'ro']
            else:
                parts=entry.split(':')
            if parts[0]==platform.VOLUMES[role]:
                volumes.append({'type':'volume','source':parts[0],'target':parts[1],'volume':{'nocopy':True}})
            else:
                host=Path(parts[0])
                require(host.is_absolute() and host.is_relative_to(platform.RUNTIME) and parts[2:]==['ro'],'RESTORE_BIND_ROOT')
                copy=target/'platform'/host.relative_to(platform.RUNTIME)
                require(copy.exists() and not copy.is_symlink() and copy.resolve()==copy,'RESTORED_BIND_FILE')
                volumes.append(':'.join([str(copy),*parts[1:]]))
        service['volumes']=volumes
        service['labels'].update({'ontology.recovery':RECOVERY,'ontology.attempt':operation})
    for group in (spec['volumes'],spec['networks']):
        for obj in group.values():obj['labels'].update({'ontology.recovery':RECOVERY,'ontology.attempt':operation})
    specfile=RECOVERY_AREA/'restore-compose.json';platform.save(specfile,spec)
    ctx=['compose','-p',ALT_PROJECT,'-f',str(specfile)]
    require(not engine_step('new-project-pre','ps','-aq','--filter','label=com.docker.compose.project='+ALT_PROJECT),'ALT_PROJECT_EXISTS')
    for kind in ('volume','network'):
        existing=engine_step('new-'+kind+'-pre',kind,'ls','--format','{{.Name}}').splitlines()
        require(not any(v.startswith(ALT_PROJECT+'_') for v in existing),'ALT_NAME_CONFLICT')
    registry=RECOVERY_AREA/'replacement-resources.json'
    value=dict(taskId=TASK,runId=RUN,operation=RECOVERY,attempt=operation,project=ALT_PROJECT,ids={},volumes={},networks={},
               composeSha256=ex.sha(specfile.read_bytes()),baseComposeSha256=ex.sha(specbytes),admission=pre['attempt'],status='CREATING')
    platform.save(registry,value)
    try:
        engine_step('create-alternative',*ctx,'create','--pull','never','--no-build',*platform.VOLUMES,timeout=90)
    finally:
        for role,shortname in platform.VOLUMES.items():
            cid=engine_step('alternative-created-id',*ctx,'ps','-a','-q',role)
            if not cid:continue
            require(re.fullmatch(CID,cid),'ALTERNATIVE_ID')
            volume=ALT_PROJECT+'_'+shortname
            row=engine_step('alternative-owner','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}',cid).split()
            require(row==[cid,platform.IMAGES[role],operation,volume],'ALTERNATIVE_SCOPE')
            value['ids'][role]=cid;value['volumes'][role]=volume
            platform.save(registry,value,True)
        for n,internal in [('platform-internal','true'),('host-entry','false')]:
            facts=engine_step('alternative-network-id','network','inspect','-f','{{.Id}} {{.Internal}} {{index .Labels "ontology.attempt"}}',ALT_PROJECT+'_'+n).split()
            require(re.fullmatch(CID,facts[0]) and facts[1:]==[internal,operation],'ALTERNATIVE_NETWORK')
            value['networks'][n]=facts[0]
        platform.save(registry,value,True)
    require(set(value['ids'])==set(platform.VOLUMES),'ALTERNATIVE_SET')
    value['status']='CREATED';platform.save(registry,value,True)
    post=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='restore',running_roles=[])
    return post['attempt']


def restore_volume(role):
    """只在原五服务退出、归档完整且目标身份已登记的情况下写替代卷。"""
    require(role in ORIGINAL_IDS and not (RECOVERY_AREA/('restored-'+role+'.json')).exists(),'RESTORE_ALREADY_RECORDED')
    private=platform.HOME_DIR/RECOVERY
    pre=platform.before_source(platform.ROOT,TASK,platform_stage=True,phase='restore',running_roles=[])
    ledger=json.loads((RECOVERY_AREA/'archive-ledger.json').read_bytes())['archives']
    registry=json.loads((RECOVERY_AREA/'replacement-resources.json').read_bytes())
    if role=='oracle':
        group='source';files=('database.tar','trust-and-auth.tar');vol=record('recovery-01-final.json')['replacementVolume']
        review=json.loads((RECOVERY_AREA/'early-alternative-independent-review.json').read_bytes())
        dossier=(RECOVERY_AREA/'early-alternative-eligibility.json').read_bytes()
        require(review['status']=='ACCEPT_EXACT_TARGET' and review['containerId']==ALT_ORACLE and
                review['volume']==vol and review['dossierSha256']==ex.sha(dossier)
                and all(ex.sha((RECOVERY_AREA/n).read_bytes())==review['reopened'][n] for n in
                        ('early-source-reread.json','archive-ledger.json','early-alternative-eligibility.json')),'EARLY_ALTERNATIVE_REVIEW')
        # 这个卷是已获准覆盖的早期替代目标。原卷只进入 cold_archive 并保持只读。
        require(vol=='ontology-g4-omq-replacement-01_oracle-data' and vol!=record('source-create-01.json')['volume'],'RESTORE_SOURCE_VOLUME')
    else:
        group='platform';files=(role+'.tar',);vol=registry['volumes'][role]
    directory=private/group
    for n in files:
        row=ledger[group+'/'+n]
        require(archive_identity(directory/n,6*platform.GIB)['sha256']==row['sha256'] and row['sourceId']==ORIGINAL_IDS[role],'RESTORE_ARCHIVE')
    initial='test -z "$(find . -mindepth 1 -print -quit)"' if role!='oracle' else 'test -d FREE && test -d dbconfig && test -f .FREE.created; find . -xdev -mindepth 1 -delete; test -z "$(find . -mindepth 1 -print -quit)"'
    # GNU tar 从已经逐成员核过的档中还原 UID/GID、权限、稀疏文件和数据。随后在服务启动前逐文件比较。
    extract='\n'.join('tar --sparse --numeric-owner --acls --xattrs -xpf /backup/'+n for n in files)
    compare='\n'.join('tar --numeric-owner --acls --xattrs -df /backup/'+n for n in files)
    platform.save(RECOVERY_AREA/('restore-dispatch-'+role+'.json'),
                  dict(taskId=TASK,role=role,volume=vol,admission=pre['attempt'],archiveSha256=[ledger[group+'/'+n]['sha256'] for n in files]))
    result=one_helper('restore-'+role,vol,'/source','cd /source\n'+initial+'\n'+extract+'\nsync\n'+compare,
                      bind=(directory,True),write=True,timeout=420)
    require(not result,'COLD_COMPARE_DIFFERENCE')
    output=dict(role=role,taskId=TASK,sourceId=ORIGINAL_IDS[role],replacementId=ALT_ORACLE if role=='oracle' else registry['ids'][role],volume=vol,
                archiveHashes=[ledger[group+'/'+n]['sha256'] for n in files],pre=pre['attempt'],status='REPLACEMENT_COLD_BYTES_VERIFIED')
    platform.save(RECOVERY_AREA/('restored-'+role+'.json'),output)
    return output


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation',choices=('status','recover-fixed-row','observe-restored'))
    cli.add_argument('--witness')
    cli.add_argument('--component',choices=('oidc','rustfs','aggregate'))
    cli.add_argument('--auth-action',choices=('prepare','finish'))
    args=cli.parse_args()
    require(args.component is None or (args.operation=='observe-restored' and args.witness is None),'COMPONENT_COMMAND')
    require(args.auth_action is None or args.component=='oidc','AUTH_ACTION')
    if args.component:
        import workflow_oracle_mapping_recovery_components as components
        if args.component=='rustfs':
            row=components.objects_window()
        elif args.component=='oidc':
            row=components.identity_window(args.auth_action or 'prepare')
        else:
            row=components.aggregate()
        print(json.dumps(row,ensure_ascii=False))
        return int(row['status'] not in ('RUSTFS_FROZEN_VERSIONS_VERIFIED','FOUR_NORMAL_AUTHENTICATIONS_VERIFIED','AUTHENTICATION_ENTRY_READY','PASS_FOR_FROZEN_CHECKPOINT'))
    if args.operation=='observe-restored':
        from workflow_oracle_mapping_checkpoint import observe_restored
        require(args.witness is None,'FIXED_VERIFIER_INPUT')
        observed=observe_restored()
        print(json.dumps({'status':observed['status'],'attempt':observed['attempt'],'recovery':'BLOCKED'}))
        return int(observed['status']!='CHECKPOINT_COMPONENTS_OBSERVED')
    if args.operation=='recover-fixed-row':
        require(args.witness is None,'FIXED_MAINTENANCE_INPUT')
        result=recover_fixed_row()
        print(json.dumps({'status':result['status'],'attempt':result['attempt'],'operationId':result['operationId']}))
        return 0
    require(args.witness is not None,'WITNESS_REQUIRED')
    attempt=uuid.uuid4().hex
    receipt=dict(taskId=TASK,runId=RUN,attempt=attempt,startedUtc=dt.datetime.now(dt.timezone.utc).isoformat(),status='STARTED',productGate='BLOCKED')
    output=AREA/('blocked-resource-status-'+attempt+'.json')
    platform.save(output,receipt)
    try:
        receipt['facts']=status(args.witness)
        receipt['status']='READBACK_COMPLETE'
    except Exception as error:
        # 私有连接异常和 SQL*Plus 登录材料绝不进入输出。
        code=str(error)
        receipt.update(status='READBACK_INCOMPLETE',reason=code if re.fullmatch('[a-zA-Z0-9_-]{1,180}',code) else type(error).__name__)
    finally:
        receipt['endedUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
        platform.save(output,receipt,True)
    print(json.dumps({'status':receipt['status'],'productGate':'BLOCKED','receipt':str(output)}))
    return int(receipt['status']!='READBACK_COMPLETE')


if __name__=='__main__':
    raise SystemExit(main())
