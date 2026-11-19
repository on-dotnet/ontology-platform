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


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation',choices=('status',))
    cli.add_argument('--witness',required=True)
    args=cli.parse_args()
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
