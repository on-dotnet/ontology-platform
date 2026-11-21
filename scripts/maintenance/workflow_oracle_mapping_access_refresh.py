"""本次Reader短链修复的准确API更替边；五个持卷进程不换代，历史两边保持。"""
import copy
import json
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
from workflow_oracle_mapping_resources import require

TASK=c.TASK
RUN=c.RUN
AREA=c.AREA
PARENT='04f23ea8cfe34868a8500b80164d86fb'
OLD_COMMIT='1a62dc1bf190c991c0a23968f9bfcd16777044d6'


def bound_inputs(root,host,archive=None,return_bytes=False):
    from workflow_oracle_mapping_evidence import RuntimeOriginals
    files=RuntimeOriginals(root,{'host':host})
    def matches(raw):
        value=json.loads(raw)
        return value.get('taskId')==TASK and value.get('runId')==RUN and value.get('snapshotId')==host['snapshotId'] and value.get('composeSha256')==host['composeSha256'] and value.get('relaySha256')==host['runtimeHelperSha256']
    path=files.choose('formal-api-inputs*.json',matches)
    raw=c.raw(root,path.relative_to(root),archive)
    return raw if return_bytes else json.loads(raw)


def snapshot_builds(root,host,archive=None):
    """三份冻结程序集都由原构建输出、命令、原字节快照及准确目录共同决定。"""
    from workflow_m2_build import TARGETS
    inp=bound_inputs(root,host,archive);result={}
    for target,key in [('api','snapshotId'),('agent','sessionSnapshotId'),('query','querySnapshotId')]:
        identity=inp[key];path=AREA/'runtime-snapshots'/(identity+'.json');snap=json.loads(c.raw(root,path,archive))
        core={k:snap[k] for k in ('files','inputs','commandId','environment','taskId','resourceRun')}
        require(snap['schemaVersion']==2 and (snap['taskId'],snap['resourceRun'])==(TASK,RUN) and ex.sha(ex.encoded(core))==identity
            and snap['snapshotId']==identity and snap['directory']==str(AREA/'runtime-snapshots'/identity),'S23_REFRESH_SNAPSHOT')
        digest=snap['inputs']['receiptSha256'];base=Path('artifacts/workflow')/TASK;name=target+'-build-binding.json'
        candidates=[base/name,base/(target+'-build-binding-'+digest+'.json')]
        candidates=[p for p in candidates if (root/p).is_file() and ex.sha(ex.ordinary(root/p).read_bytes())==digest]
        require(candidates,'S23_REFRESH_BINDING_MISSING');binding=json.loads(c.raw(root,candidates[0],archive));prefix=str(Path(TARGETS[target]).parent/'bin/Debug/net10.0')+'/'
        require(binding['taskId']==TASK and binding['target']==target and binding['worktree']==str(root) and binding['status']=='PASS' and binding['exitCode']==0
            and snap['inputs']==dict(inputKey=binding['inputKey'],outputKey=ex.sha(json.dumps(binding['outputs'],sort_keys=True).encode()),receiptSha256=digest)
            and {k.removeprefix(prefix):v for k,v in binding['outputs'].items() if k.startswith(prefix)}==snap['files'],'S23_REFRESH_BUILD_FILES')
        log=base/(target+'-bound-build.txt');saved=base/(target+'-bound-build-'+binding['logSha256']+'.txt')
        chosen=next((p for p in (log,saved) if (root/p).is_file() and ex.sha(ex.ordinary(root/p).read_bytes())==binding['logSha256']),None)
        require(chosen is not None,'S23_REFRESH_BUILD_LOG');log_bytes=c.raw(root,chosen,archive)
        argv=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*binding['command']]
        require(binding['command'][1:]==['build',TARGETS[target],'--no-restore','--disable-build-servers','-m:1','-v:q'],'S23_REFRESH_BUILD_ARGV')
        receipt,out,err=c.command(root,snap['commandId'],RUN,argv,'command',binding['inputKey'],180,archive)
        require(out+err==log_bytes and receipt['environmentFingerprint']==snap['environment']['toolEnvironment'],'S23_REFRESH_BUILD_COMMAND')
        # 按已登记快照完整复核当前保留的原文件；原构建不被当前文件替换。
        import workflow_m4_query_runtime as snapshots
        snapshots.verify(root,snap,task=TASK,run_id=RUN)
        result[target]=dict(snapshotId=identity,directory=snap['directory'],build=snap['inputs'],commandId=snap['commandId'])
    require(result['api']['build']==inp['build'] and result['api']['commandId']==inp['buildCommandId'] and result['api']['build']['outputKey']==host['buildOutputKey']
        and all(row['build']['inputKey']==host['buildInputKey'] for row in result.values()),'S23_REFRESH_API_BUILD')
    return result


def observed_rows(root,host,archive=None):
    from workflow_oracle_mapping_platform import HOST_FORMAT
    inp=bound_inputs(root,host,archive);ids={k:v['containerId'] for k,v in host['services'].items()};roles=sorted(ids);source=host['oracle']['containerId']
    args=['docker','--context','desktop-linux','inspect','-f',HOST_FORMAT,*[ids[k] for k in roles],source]
    receipt,out,_=c.command(root,host['commandId'],RUN,args,'omq-host-inspect',ex.sha(ex.encoded([inp,ids,source,HOST_FORMAT])),12,archive)
    rows={}
    for role,line in zip([*roles,'oracle'],out.decode().strip().splitlines(),strict=True):
        parts=line.split('|');require(len(parts)==9,'S23_REFRESH_HOST_ROW');cid,image,task,run,status,pid,started,mounts,nets=parts
        require(cid==(source if role=='oracle' else ids[role]) and task==TASK and run==(RUN if role in ('api','api-secondary') else 'implementation-01') and status=='running' and int(pid)>0,'S23_REFRESH_HOST_IDENTITY')
        rows[role]=dict(containerId=cid,imageId=image,pid=int(pid),startedAt=started,mounts=json.loads(mounts),networks=dict(x.split('=') for x in nets.split()))
    return receipt,rows


def compare_hosts(root,previous,current,oldrows,newrows,builds):
    """仅两个API的身份、进程与三处已核程序集Source允许变化；全部其他字段必须相同。"""
    from workflow_oracle_mapping_evidence import stable_host
    before=copy.deepcopy(stable_host(previous));after=copy.deepcopy(stable_host(current))
    for host in (before,after):
        for field in ('snapshotId','buildInputKey','buildOutputKey','composeSha256','resourceManifestSha256'):host.pop(field)
        for role in ('api','api-secondary'):
            for field in ('containerId','pid','startedAt','mountSha256'):host['services'][role].pop(field)
    require(before==after and set(oldrows)==set(newrows),'S23_REFRESH_FIXED_HOST')
    for role,old in oldrows.items():
        new=newrows[role]
        if role not in ('api','api-secondary'):
            require(old==new,'S23_REFRESH_DATA_GENERATION');continue
        require(old['containerId']!=new['containerId'] and old['imageId']==new['imageId'] and old['networks']==new['networks'],'S23_REFRESH_API_IDENTITY')
        normalized=[]
        for side,row in enumerate((old,new)):
            mounts=copy.deepcopy(row['mounts']);expected={'/app':'api',**({'/session-tests':'agent','/query-tests':'query'} if role=='api-secondary' else {})}
            for destination,target in expected.items():
                selected=[m for m in mounts if m['Destination']==destination or m['Destination'].startswith(destination+'/')]
                require(len(selected)==1 and selected[0]['Destination']==destination and selected[0]['Type']=='bind' and selected[0]['RW'] is False
                    and selected[0]['Source'].removeprefix('/host_mnt')==str(root/builds[side][target]['directory']),'S23_REFRESH_SNAPSHOT_MOUNT')
                selected[0]['Source']='VERIFIED_'+target
            normalized.append(sorted(mounts,key=lambda m:m['Destination']))
        require(normalized[0]==normalized[1],'S23_REFRESH_PRIVATE_MOUNT_DRIFT')
    return True


def lifecycle(root,previous,current,proof=None,archive=None):
    """旧失败只作真实宿主锚点，先完整两边，再接本次三处程序集更替边。"""
    from workflow_oracle_mapping_evidence import utc,stable_host
    import workflow_oracle_mapping_repeat as repeat
    path=AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json');data=c.raw(root,path,archive)
    require(ex.sha(data)=='170263a71d9af33b240e86ab3d9bf1ab983eeb3c8e94741d5b261c492fc87013','S23_REFRESH_PARENT_HASH');dispatch=json.loads(data)
    require((dispatch['taskId'],dispatch['runId'],dispatch['commandId'],dispatch['testedCommit'],dispatch['exitCode'])==(TASK,RUN,PARENT,OLD_COMMIT,1),'S23_REFRESH_FAILED_PARENT')
    from workflow_oracle_mapping_evidence import Originals,NODE,DRIVER
    class Parent(Originals):
        def __init__(self):self.root=root
        def raw(self,name):
            require(name.startswith(PARENT+'-'),'S23_REFRESH_PARENT_MEMBER')
            return c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PARENT/name.removeprefix(PARENT+'-'),archive)
    argv=[NODE,DRIVER,'--task',TASK,'--run-id',RUN,'--mode','s2-s3-oracle','--batch-input',dispatch['stageInputs']['batchInput']]
    parent,_,_=Parent().command(PARENT,argv,'omq-browser-s2-s3-oracle','40011faaf7ec10fc3ffc03397dc42fa4f285dbe2be394a6516c770287af29168','064b4491c1c142af89c385565217d19b',root,command_run=RUN)
    require(parent['deadlineSeconds']==2520,'S23_REFRESH_PARENT_BUDGET')
    require(parent['exitCode']==1 and parent['classification']=='EXIT_FAILURE','S23_REFRESH_PARENT_FAILURE')
    middle=dispatch['host'];require(previous['snapshotId']==middle['snapshotId']!=current['snapshotId'],'S23_REFRESH_CHAIN_SCOPE')
    observed=c.raw(root,AREA/'s2-s3-01/prefix-observation-779f00cbdd5444359384de1e496212fa.json',archive)
    require(ex.sha(observed)=='beccaab4b648dea597ee77b60b4ba95b6f1a9c827cd46d0a5f3c59a8d55d1a1c','S23_REFRESH_MIDDLE_OBSERVATION')
    observation=json.loads(observed);require(stable_host(middle)==stable_host(observation['host']),'S23_REFRESH_MIDDLE_HOST')
    prior=repeat.lifecycle(root,previous,middle,observation['hostContinuity'],archive)
    oldreceipt,oldrows=observed_rows(root,middle,archive);newreceipt,newrows=observed_rows(root,current,archive)
    builds=[snapshot_builds(root,host,archive) for host in (middle,current)]
    require(builds[0]['api']['build']['inputKey']!=builds[1]['api']['build']['inputKey'],'S23_REFRESH_BUILD_UNCHANGED')
    compare_hosts(root,middle,current,oldrows,newrows,builds)
    # 原compose必须完整重开，只有三处程序集目录可更替。
    recipes=[]
    for side,host in enumerate((middle,current)):
        path=AREA/('formal-api-compose-'+host['composeSha256']+'.json')
        if not (root/path).exists():path=AREA/'formal-api-compose.json'
        raw=c.raw(root,path,archive);require(ex.sha(raw)==host['composeSha256'],'S23_REFRESH_COMPOSE_HASH');spec=json.loads(raw)
        for role,service in spec['services'].items():
            expected={'/app':'api',**({'/session-tests':'agent','/query-tests':'query'} if role=='api-secondary' else {})}
            for destination,target in expected.items():
                old=str(root/builds[side][target]['directory'])+':'+destination+':ro'
                require(service['volumes'].count(old)==1,'S23_REFRESH_COMPOSE_MOUNT');service['volumes'][service['volumes'].index(old)]='VERIFIED_'+target+':'+destination+':ro'
        recipes.append(spec)
    require(recipes[0]==recipes[1],'S23_REFRESH_COMPOSE_DRIFT')
    # 精确资源清单除API身份和构建字段外不变。
    manifests=[]
    for side,host in enumerate((middle,current)):
        digest=host['resourceManifestSha256'];raw=c.raw(root,AREA/('formal-resources-'+digest+'.json'),archive);require(ex.sha(raw)==digest,'S23_REFRESH_MANIFEST_HASH');value=json.loads(raw)
        require(value['ids']=={k:v['containerId'] for k,v in (oldrows if host is middle else newrows).items()},'S23_REFRESH_MANIFEST_IDS')
        require(value['snapshotId']==host['snapshotId'] and value['apiBuildId']==builds[side]['api']['commandId'] and value['buildOutputKey']==host['buildOutputKey']
            and value['inputsSha256']==ex.sha(bound_inputs(root,host,archive,return_bytes=True)),'S23_REFRESH_MANIFEST_BUILD')
        for key in ('snapshotId','apiBuildId','buildOutputKey','inputsSha256','admission'):value.pop(key)
        for role in ('api','api-secondary'):value['ids'].pop(role)
        manifests.append(value)
    require(manifests[0]==manifests[1],'S23_REFRESH_MANIFEST_DRIFT')
    lower=utc(parent['endedAtUtc']);upper=utc(newreceipt['startedAtUtc']);require(utc(oldreceipt['endedAtUtc'])<=lower<upper,'S23_REFRESH_ORDER')
    references={} if proof is None else proof['commands'];consumed={}
    for role in ('api','api-secondary'):
        end=lower;old=oldrows[role];new=newrows[role]
        for kind in ('term','exit','remove','absent','api-create','api-id','api-start'):
            resource=(old if kind in ('term','exit','remove','absent') else new)['containerId'];label=role+':'+kind
            if kind in ('term','exit'):
                args=['stop','--signal','TERM','--timeout','-1',resource] if kind=='term' else ['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',resource]
                stage='resume-api-'+kind;seconds=45 if kind=='term' else 30;argv=['docker','--context','desktop-linux',*args];key=ex.sha(ex.encoded(args))
                if proof is None:
                    matches=[]
                    for path in (root/'artifacts/workflow'/TASK/'commands'/RUN).glob('*/receipt.json'):
                        r=json.loads(ex.ordinary(path).read_bytes())
                        if r['stage']==stage and r['inputFingerprint']==key and r['exitCode']==0 and lower<=utc(r['startedAtUtc'])<=utc(r['endedAtUtc'])<=upper:matches.append(r['commandId'])
                    require(len(matches)==1,'S23_REFRESH_UNIQUE_COMMAND');cid=matches[0]
                else:cid=references[label]
                receipt,out,_=c.command(root,cid,RUN,argv,stage,key,seconds,archive)
            else:
                cid=c.find_command(root,role,resource,kind,lower,upper) if proof is None else references[label]
                receipt,out,_=c.lifecycle_command(root,cid,role,resource,kind,archive)
            require(end<=utc(receipt['startedAtUtc'])<=utc(receipt['endedAtUtc'])<=upper,'S23_REFRESH_COMMAND_ORDER')
            if kind=='exit':require(out.strip() in (b'exited 0 false',b'exited 143 false'),'S23_REFRESH_EXIT')
            elif kind=='absent':require(not out.strip(),'S23_REFRESH_ABSENT')
            elif kind in ('term','remove','api-id','api-start'):require(out.decode().strip()==resource,'S23_REFRESH_ACTION_ID')
            if kind=='api-start':require(utc(receipt['startedAtUtc'])<=utc(new['startedAt'])<=utc(receipt['endedAtUtc']),'S23_REFRESH_START_GENERATION')
            consumed[label]=cid;end=utc(receipt['endedAtUtc'])
    recovery=maintenance_result(root,middle,current,builds[1],consumed,archive)
    result=dict(recovery=recovery,status='TWO_ACTUAL_GENERATION_EDGES_AND_API_BUILD_REPLACEMENT',failedParent=PARENT,prior=prior,commands=consumed,
        builds=builds,dataScope='Five persistent service identities and process generations unchanged; exact failed query lease maintenance separately recorded')
    require(proof is None or proof==result,'S23_REFRESH_PROOF');return result


def maintenance_result(root,previous,current,builds,lifecycle_commands,archive=None):
    """离线重开同次两列恢复；用实际CAS时间核五分钟证明，绝不重执行维护或使用当前时钟。"""
    from workflow_oracle_mapping_evidence import utc
    from workflow_oracle_mapping_platform import HOST_FORMAT,PROBE,IMAGES
    from workflow_m2_build import TARGETS
    from doris_keep_drain import COUNTS,ACTIVITY
    import workflow_oracle_access_maintenance as a
    import datetime as dt
    producer='98fe607245dd968652c06b17d6fe2fa29b607c155af5e3e4195ac9a0acd61e10'
    require(ex.sha(ex.ordinary(root/'scripts/maintenance/workflow_oracle_access_maintenance.py').read_bytes())==producer,'S23_REFRESH_MAINTENANCE_PRODUCER')
    attempt='b361c22392774a22915fce14249e7342';base=AREA/'s2-s3-01'
    pre=json.loads(c.raw(root,base/('access-prestate-'+attempt+'.json'),archive));proof=pre['proof']
    result=json.loads(c.raw(root,base/('access-recovery-'+attempt+'.json'),archive));sealed_raw=c.raw(root,base/'access-api-seal.json',archive);sealed=json.loads(sealed_raw)
    require(ex.sha(sealed_raw)==proof['sealSha256']=='29c0dc15d5ebf0c17c7656632369bfcc4df613d791fc12480a73bd3d31cd3558'
        and pre['proofSha256']==result['proofSha256']==ex.sha(ex.encoded(proof))=='197dfa30217255b39e4cd67b87667f70921b45a07ab7d0e2813f67f652bc094f'
        and result['attemptId']==pre['attemptId']==proof['attemptId']==attempt and result['build']==builds['api']['build']
        and result['status']=='TASK_LEVEL_RECOVERY' and result['exitCode']==0 and result['helperReleased'] and result['originalCleanup250ms']=='NOT_QUALIFIED','S23_REFRESH_RECOVERY_SCOPE')
    termination=pre['termination'];require(ex.sha(ex.encoded(termination))==proof['terminationProofSha256'] and termination['commands']==pre['commands']
        and termination['host']==pre['host'] and termination['queryId']==proof['queryId']==a.QUERY and termination['sourceExecutionId']==proof['sourceExecutionId']==a.EXECUTION
        and termination['sourceId']==proof['sourceContainerId']==a.SOURCE and termination['sourceSessions']==0,'S23_REFRESH_TERMINATION')
    ids=sealed['ids'];dataids={k:v for k,v in ids.items() if k not in ('api','api-secondary')}
    require(ids=={**{k:v['containerId'] for k,v in previous['services'].items()},'oracle':previous['oracle']['containerId']} and set(sealed['apis'])=={'api','api-secondary'},'S23_REFRESH_SEAL_SCOPE')
    def call(cid,stage,args,payload=None,timeout=30,source=producer):
        key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),producer=source)))
        return c.command(root,cid,RUN,args,'s23-access-'+stage,key,timeout,archive)
    def rows(data,names):
        answer={}
        for name,line in zip(names,data.decode().strip().splitlines(),strict=True):
            value=line.split('|');require(len(value)==9,'S23_REFRESH_RECOVERY_HOST_FIELDS')
            answer[name]=[*value[:7],json.loads(value[7]),dict(pair.split('=') for pair in value[8].split())]
        return answer
    def canonical(value):return {k:[*v[:7],json.loads(v[7]),dict(x.split('=') for x in v[8].split())] for k,v in value.items()}
    oldproducer='ab963c25658b7846224da2b671b501e68d291d3f4503987f2c5b8d8f88c6e16f'
    require(ex.sha(c.raw(root,base/('access-maintenance-producer-'+oldproducer+'.py'),archive))==oldproducer,'S23_REFRESH_SEAL_PRODUCER')
    observations=[]
    for stage,selected in [('before',ids),('after',dataids)]:
        names=sorted(selected);rec,out,_=call(sealed[stage]['commandId'],'seal-'+stage,[*a.DOCKER,'inspect','-f',HOST_FORMAT,*[selected[n] for n in names]],source=oldproducer)
        require(rows(out,names)==canonical(sealed[stage]['rows']),'S23_REFRESH_SEAL_ROWS');observations.append(rec)
    oldrec,oldrows=observed_rows(root,previous,archive)
    for name,value in canonical(sealed['before']['rows']).items():
        old=oldrows[name];require(value[0:2]==[old['containerId'],old['imageId']] and int(value[5])==old['pid'] and value[6:]==[old['startedAt'],old['mounts'],old['networks']],'S23_REFRESH_SEAL_GENERATION')
    require(canonical(sealed['after']['rows'])=={k:v for k,v in canonical(sealed['before']['rows']).items() if k in dataids},'S23_REFRESH_SEAL_DATA')
    for role in ('api','api-secondary'):
        require(sealed['apis'][role]['id']==ids[role] and sealed['apis'][role]['absentCommandId']==lifecycle_commands[role+':absent'],'S23_REFRESH_SEAL_ABSENCE')
        before=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':term']/'receipt.json',archive))
        after=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':absent']/'receipt.json',archive))
        require(utc(observations[0]['endedAtUtc'])<=utc(before['startedAtUtc'])<=utc(after['endedAtUtc'])<=utc(observations[1]['startedAtUtc']),'S23_REFRESH_SEAL_ORDER')
    names=sorted(dataids);rec,out,_=call(pre['host']['commandId'],'prestate-host',[*a.DOCKER,'inspect','-f',HOST_FORMAT,*[dataids[n] for n in names]])
    require(rows(out,names)==canonical(pre['host']['rows'])==canonical(sealed['after']['rows']) and utc(observations[1]['endedAtUtc'])<=utc(rec['startedAtUtc']),'S23_REFRESH_PRESTATE_HOST');end=utc(rec['endedAtUtc'])
    for role in ('api','api-secondary'):
        rec,out,_=call(pre['commands']['absent-'+role],'prestate-absent-'+role,[*a.DOCKER,'ps','-aq','--no-trunc','--filter','id='+ids[role]])
        require(not out.strip() and end<=utc(rec['startedAtUtc']),'S23_REFRESH_PRESTATE_ABSENCE');end=utc(rec['endedAtUtc'])
    pg=[*a.DOCKER,'exec','-i','--user','postgres',a.PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    rec,out,_=call(pre['commands']['drain'],'prestate-drain',pg,sql.encode());require(json.loads(out)==[0]*8 and end<=utc(rec['startedAtUtc']),'S23_REFRESH_DRAIN');end=utc(rec['endedAtUtc'])
    for which in ('first','second'):
        rec,out,_=call(pre['commands']['source-'+which],'source-zero-'+which,[*a.DOCKER,'exec','-i',a.SOURCE,'sqlplus','-L','-s','/ as sysdba'],a.SOURCE_SQL.encode())
        require(out.strip()==b'0' and end<=utc(rec['startedAtUtc']),'S23_REFRESH_SOURCE_ZERO');end=utc(rec['endedAtUtc'])
    prestate={}
    for name,sql in [('row',a.ROW_SQL),('audit',a.AUDIT_SQL)]:
        rec,out,_=call(pre['commands'][name],'prestate-'+name,pg,sql.encode());require(end<=utc(rec['startedAtUtc']),'S23_REFRESH_PRESTATE_ORDER');end=utc(rec['endedAtUtc']);prestate[name]=json.loads(out)
    require(end<=utc(proof['verifiedUtc']) and prestate['row']['stableRowSha256']==a.STABLE and prestate['row']['owner']==a.OWNER
        and prestate['row']['status']=='FAILED' and prestate['row']['fence']==2 and len(prestate['audit'])==1
        and prestate['audit'][0]['id']==a.FAILURE_AUDIT and prestate['audit'][0]['sha256']==a.FAILURE_SHA and prestate['audit'][0]['outcome']=='failure','S23_REFRESH_PRESTATE_BYTES')
    helper=result['helperId'];private=a.resume.RESTORED/'platform/postgres';api=root/Path(TARGETS['api']).parent/'bin/Debug/net10.0'
    script=('umask 077; set -eu; test "$(id -u)" = 501; '
        'printf "Host=platform-pg;Port=5432;Database=mapping;Username=postgres;SSL Mode=VerifyFull;Root Certificate=/ca;Password=%s" '
        '"$(cat /auth)" > /tmp/maintenance.dsn; exec dotnet /app/OntologyPlatform.Api.dll --recover-omq-s23-access')
    args=[*a.DOCKER,'create','--pull=never','-i','--network',a.resume.net_names()['platform-internal'],'--read-only','--user','501:20',
        '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=128','--security-opt=no-new-privileges','--cap-drop=ALL',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777','--label','ontology.task='+TASK,'--label','ontology.run='+RUN,'--label','ontology.attempt='+attempt,
        '--mount','type=bind,src='+str(api)+',dst=/app,readonly','--mount','type=bind,src='+str(private/'password')+',dst=/auth,readonly','--mount','type=bind,src='+str(private/'server.crt')+',dst=/ca,readonly']
    env={'DSN_FILE':'/tmp/maintenance.dsn','OPERATOR':proof['operatorId'],'PROOF_SHA256':pre['proofSha256'],'SEAL_SHA256':proof['sealSha256'],'TERMINATION_SHA256':proof['terminationProofSha256']}
    for key,value in env.items():args+=['-e','OMQ_S23_MAINTENANCE_'+key+'='+value]
    rec,out,_=call(result['createCommandId'],'recovery-create',[*args,'--entrypoint=/bin/sh',PROBE,'-ec',script]);require(out.decode().strip()==helper and end<=utc(rec['startedAtUtc']),'S23_REFRESH_HELPER_CREATE');end=utc(rec['endedAtUtc'])
    rec,out,_=call(result['beforeCommandId'],'recovery-before',[*a.DOCKER,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}',helper])
    require(out.decode().strip()=='|'.join((helper,IMAGES['api'],attempt,'created')) and end<=utc(rec['startedAtUtc']),'S23_REFRESH_HELPER_OWNER');end=utc(rec['endedAtUtc'])
    cas,out,err=c.command(root,result['actualCommandId'],RUN,[*a.DOCKER,'start','-a','-i',helper],'s23-access-recovery-cas',pre['proofSha256'],32,archive)
    require(end<=utc(cas['startedAtUtc']) and utc(proof['verifiedUtc'])<=utc(cas['startedAtUtc'])<=utc(cas['endedAtUtc'])<utc(proof['validUntilUtc'])
        and utc(proof['validUntilUtc'])-utc(proof['verifiedUtc'])==dt.timedelta(minutes=5) and json.loads(out)==result['commitEnvelope']
        and result['commitEnvelope']['status']=='TASK_LEVEL_RECOVERY' and result['commitEnvelope']['operationId']==proof['operationId']==result['operationId']
        and utc(cas['startedAtUtc'])<=utc(result['commitEnvelope']['lowerUtc'])<=utc(result['commitEnvelope']['upperUtc'])<=utc(cas['endedAtUtc'])
        and (not err or len(err)==127 and ex.sha(err)=='6a55ce9418db27c92344e3846e6ec6fe5718cb84e315fe05c82d3403ebff3a9d'),'S23_REFRESH_CAS');end=utc(cas['endedAtUtc'])
    for field,stage,args,expected in [('exitCommandId','recovery-exit',[*a.DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],b'exited|0|false'),
        ('removeCommandId','recovery-remove',[*a.DOCKER,'rm',helper],helper.encode()),('absentCommandId','recovery-absent',[*a.DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],b'')]:
        rec,out,_=call(result[field],stage,args);require(out.strip()==expected and end<=utc(rec['startedAtUtc']),'S23_REFRESH_HELPER_RELEASE');end=utc(rec['endedAtUtc'])
    post={}
    for name,sql in [('row',a.ROW_SQL),('audit',a.AUDIT_SQL)]:
        rec,out,_=call(result[name+'CommandId'],'post-'+name,pg,sql.encode());require(end<=utc(rec['startedAtUtc']),'S23_REFRESH_POST_ORDER');end=utc(rec['endedAtUtc']);post[name]=json.loads(out)
    require(post['row']==result['post']=={**prestate['row'],'owner':None,'leaseUntilUtc':None} and post['audit']==result['audits'] and len(post['audit'])==2
        and prestate['audit'][0] in post['audit'],'S23_REFRESH_POST_BYTES')
    new=next(item for item in post['audit'] if item!=prestate['audit'][0]);require(new['action']=='data.query.cleanup.recover' and new['outcome']=='allowed' and new['actor']==proof['operatorId']
        and new['trace']==proof['operationId'] and new['correlation']==attempt and new['organization']=='org-demo' and new['sites']==['site-a'],'S23_REFRESH_POST_AUDIT')
    for role in ('api','api-secondary'):
        started=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':api-create']/'receipt.json',archive))
        require(end<=utc(started['startedAtUtc']),'S23_REFRESH_AFTER_RECOVERY')
    return dict(status='TASK_LEVEL_RECOVERY',commandId=result['actualCommandId'],queryId=a.QUERY,proofSha256=pre['proofSha256'],postRowCommandId=result['rowCommandId'],postAuditCommandId=result['auditCommandId'],originalCleanup250ms='NOT_QUALIFIED')
