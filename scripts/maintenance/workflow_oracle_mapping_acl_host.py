"""上一失败窗口关闭后同一批次的物理图库及宿主原件。"""
import json
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
from workflow_oracle_mapping_resources import require

TASK, RUN, AREA = c.TASK, c.RUN, c.AREA
START = AREA / 's2-s3-01/lease-3e6-fuseki-start.json'
GRAPH = AREA / 's2-s3-01/lease-3e6-current-graph.json'
CLOSE = AREA / 's2-s3-01/closeout-70da4fc46f004170846f569dd421ec7a.json'
CLOSE_SHA = '952094d4182ccac4ea312917b653c1d527674dc9157aa64902e20afd540ccd9e'
raw, command, lifecycle_command = c.raw, c.command, c.lifecycle_command
BRANCH = """    if row.get('priorCloseSha256')=='952094d4182ccac4ea312917b653c1d527674dc9157aa64902e20afd540ccd9e' and row.get('productUse')=='AWAITING_CURRENT_GRAPH_QUALIFICATION':
        from workflow_oracle_mapping_acl_host import graph_qualification
        graph_qualification(platform.ROOT,cid,started,pid)
        return row['attempt']
"""


def closed(root, archive=None):
    data = raw(root, CLOSE, archive)
    require(ex.sha(data) == CLOSE_SHA, 'ACL_LEASE_CLOSE_BYTES')
    row = json.loads(data)
    require(row['status'] == 'PASS' and row['remaining'] == [] and row['data']['fuseki']['cleanShutdown'] == 'UNKNOWN', 'ACL_LEASE_CLOSE_SCOPE')
    return row


def graph_qualification(root,cid,started,pid,archive=None,upper=None):
    """本次第二代真实启动、全图与Published源码单独核验。"""
    from workflow_oracle_mapping_evidence import utc
    require(cid==c.FUSEKI,'ACL_LEASE_GRAPH_CONTAINER')
    close=closed(root,archive);proof=json.loads(raw(root,GRAPH,archive));start_raw=raw(root,START,archive);start=json.loads(start_raw)
    require(raw(root,Path('artifacts/workflow')/TASK/c.RECOVERY/('start-'+start['attempt']+'.json'),archive)==start_raw,'ACL_LEASE_START_ORIGINAL')
    require((proof['taskId'],proof['runId'],proof['batch'])==(TASK,RUN,'s2-s3-01') and proof['startSha256']==ex.sha(start_raw),'ACL_LEASE_GRAPH_SCOPE')
    require((start['id'],start['startedAt'],start['pid'])==(cid,started,pid) and start['stage']==RUN and start['role']=='fuseki' and start['status']=='RUNNING'
        and start['productUse']=='AWAITING_CURRENT_GRAPH_QUALIFICATION' and start['priorCloseSha256']==CLOSE_SHA,'ACL_LEASE_START')
    state_args=['inspect','-f','{{json .State}}',cid];argv=['docker','--context','desktop-linux',*state_args]
    before,out,_=command(root,start['beforeCommandId'],RUN,argv,'s23-acl-lease-fuseki-before',ex.sha(ex.encoded(state_args)),30,archive)
    state=json.loads(out);require({k:state[k] for k in close['data']['fuseki']['after']}==close['data']['fuseki']['after'],'ACL_LEASE_STOP_GENERATION')
    row,out,_=lifecycle_command(root,start['startCommandId'],'fuseki',cid,'data-start',archive)
    require(out.decode().strip()==cid and utc(before['endedAtUtc'])<=utc(row['startedAtUtc'])<=utc(started)<=utc(row['endedAtUtc']),'ACL_LEASE_START_COMMAND')
    fmt='{{.State.Status}}|{{.State.StartedAt}}|{{.State.Pid}}';args=['inspect','-f',fmt,cid]
    generation,body,_=command(root,start['generationCommandId'],RUN,['docker','--context','desktop-linux',*args],'s23-acl-lease-fuseki-generation',ex.sha(ex.encoded(args)),30,archive)
    require(body.decode().strip()=='running|'+started+'|'+str(pid) and utc(row['endedAtUtc'])<=utc(generation['startedAtUtc']),'ACL_LEASE_LIVE_GENERATION')
    scans={}
    for kind in ('default','named'):
        args=c.scan_argv(kind);row,out,err=command(root,proof['scans'][kind],RUN,args,'s23-acl-lease-graph-'+kind,ex.sha(ex.encoded(args)),25,archive)
        require(not err and utc(generation['endedAtUtc'])<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'ACL_LEASE_SCAN_ORDER')
        value=json.loads(out);fields={'s','p','o'}|({'g'} if kind=='named' else set())
        require(set(value['head']['vars'])==fields and all(set(v)==fields for v in value['results']['bindings']),'ACL_LEASE_GRAPH_FIELDS');scans[kind]=value['results']['bindings']
    args=['docker','--context','desktop-linux','exec','-i','--user','postgres',c.PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    row,out,err=command(root,proof['publicationCommandId'],RUN,args,'s23-acl-lease-published-sources',ex.sha(c.publication_sql()),25,archive)
    require(not err and utc(started)<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'ACL_LEASE_PUBLICATION_ORDER')
    c.check_publications([json.loads(line) for line in out.decode().splitlines() if line.strip()])
    frozen_raw=raw(root,AREA/'s2-s3-01/frozen-graphs-second-open.json',archive)
    require(ex.sha(frozen_raw)=='393a597292cfba79d9b772bf7bac9a34d3e7d843bcf0c7e9ed3e97e9fd87c328','ACL_LEASE_FROZEN')
    expected=c.expected_graphs(scans['default'],scans['named'],json.loads(frozen_raw));require(proof['expected']==expected,'ACL_LEASE_EXPECTED')
    return expected


PARENT = '685e33e9abd749168f6152789677859a'
CURRENT = 'f7efba86a7680d59c5b266fe090506110828887ebca50728e22bb20d6bcbba0c'
MAINTENANCE = AREA / 's2-s3-01/acl-lease-recovery-da07fbda978e45e8bc755d01029e0f5a.json'


def pinned(root, path, digest, archive):
    data = raw(root, path, archive)
    require(ex.sha(data) == digest, 'ACL_LEASE_ORIGINAL_CHANGED')
    return json.loads(data)


def lifecycle(root, previous, current, proof=None, archive=None):
    """从已独立核完整原件的五条旧边接续，重开本次真实停止、启动、持卷、三构建和维护边。"""
    from workflow_oracle_mapping_evidence import utc, stable_host
    import workflow_oracle_mapping_access_refresh as refresh
    from workflow_oracle_mapping_continuation import PREFIX
    import copy
    import subprocess
    if current['snapshotId'] != CURRENT:
        from workflow_oracle_mapping_repeat import lifecycle as history
        return history(root, previous, current, proof, archive)
    failed = pinned(root,AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json'),'33fb3d51316cd362b76595a5ea17ab4589fbbad1a4ad3ca97cfe608b3bcfd337',archive)
    parent = pinned(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PARENT/'receipt.json','51a3f7a383a18b716b7a5d22f8140513b270f8219f8799559d494eea66996214',archive)
    middle = failed['host']
    require(failed['testedCommit']=='ee802b487f386417e312d40e84978ab49e78c182' and failed['commandId']==PARENT
            and parent['commandId']==PARENT and parent['exitCode']==failed['exitCode']==1 and parent['deadlineSeconds']==2520, 'ACL_LEASE_FAILED_PARENT')
    for stream in ('stdout','stderr'):
        data=raw(root,Path(parent[stream]['path']).relative_to(root),archive)
        require(len(data)==parent[stream]['sizeBytes'] and ex.sha(data)==parent[stream]['sha256'],'ACL_LEASE_PARENT_STREAM')
    ref=failed['stageInputs']['qualifiedPrefix']
    old=pinned(root,AREA/'s2-s3-01'/ref['file'],'c4bb342453225bea4f41a40a40aff9966c125237a085b3c40e2943703f18e631',archive)
    require(old['qualifiedPrefix']==PREFIX and stable_host(old['host'])==stable_host(middle),'ACL_LEASE_OLD_HOST')
    history_path='docs/evidence/'+TASK+'/'+RUN+'/s2-s3-01/non-author-review.json'
    review=subprocess.check_output(['git','show','095d2dd8ff957afa64f01fd938f18ffd357d8d5c:'+history_path],cwd=root)
    require(ex.sha(review)=='801474acc47b5899ce9a01818334cfe0c4133a7cf031c2edcdb21798a3c15943','ACL_LEASE_PRIOR_REVIEW')
    qualification=json.loads(review)['scopes'][3]
    require(qualification['members']==693 and qualification['indexSha256']=='944dbae383af63b2314a60e326271ed752aa132715950ee445f82a9cdd417c4c'
            and qualification['status']=='QUALIFIED_ON_MEASURED_BUILD','ACL_LEASE_PRIOR_EDGES')
    original=json.loads(raw(root,AREA/('formal-run-s2-s3-oracle-'+PREFIX['commandId']+'.json'),archive))
    require(stable_host(original['host'])==stable_host(previous),'ACL_LEASE_FIRST_HOST')
    close=closed(root,archive)
    before,oldrows=refresh.observed_rows(root,middle,archive)
    after,newrows=refresh.observed_rows(root,current,archive)
    require(close['ids']=={k:v['containerId'] for k,v in oldrows.items()} and oldrows.keys()==newrows.keys(),'ACL_LEASE_RESOURCE_SET')
    lower,upper=utc(parent['endedAtUtc']),utc(after['startedAtUtc'])
    require(utc(before['endedAtUtc'])<=utc(parent['startedAtUtc'])<lower<upper,'ACL_LEASE_HOST_ORDER')
    builds=[refresh.snapshot_builds(root,host,archive) for host in (middle,current)]
    require(current['buildInputKey']=='7cea75160944c1a12b91335cb3897ca9c30a6b299f300348ce6ed4382a45af3f' and middle['buildInputKey']!=current['buildInputKey'],'ACL_LEASE_NEW_BUILD')
    consumed={}
    for role,oldrow in oldrows.items():
        newrow=newrows[role]
        end=lower
        api=role in ('api','api-secondary')
        for kind in (('remove','absent','api-create','api-id','api-start') if api else ('stopped','data-start')):
            resource=(oldrow if kind in ('stopped','remove','absent') else newrow)['containerId']
            key=role+':'+kind
            cid=COMMANDS[key] if proof is None else proof['commands'][key]
            require(cid==COMMANDS[key],'ACL_LEASE_COMMAND_ID')
            receipt,body,_=lifecycle_command(root,cid,role,resource,kind,archive)
            require(end<=utc(receipt['startedAtUtc'])<=utc(receipt['endedAtUtc'])<=upper,'ACL_LEASE_LIFECYCLE_ORDER')
            if kind=='stopped':
                state=json.loads(body);observed=close['data'][role]['after']
                require({k:state[k] for k in observed}==observed and state['Status']=='exited' and not state['Error'] and not state['OOMKilled']
                        and utc(oldrow['startedAt'])<utc(state['FinishedAt'])<utc(newrow['startedAt']),'ACL_LEASE_STOPPED')
            elif kind=='absent':require(not body.strip(),'ACL_LEASE_API_ABSENT')
            elif kind!='api-create':require(body.decode().strip()==resource,'ACL_LEASE_COMMAND_RESOURCE')
            if kind in ('data-start','api-start'):
                require(utc(receipt['startedAtUtc'])<=utc(newrow['startedAt'])<=utc(receipt['endedAtUtc']),'ACL_LEASE_GENERATION')
            end=utc(receipt['endedAtUtc']);consumed[key]=cid
    # 只有已从上面实测命令逐个验证的持卷进程代次在比较时归一化。
    comparable_host=copy.deepcopy(middle);comparable_rows=copy.deepcopy(oldrows)
    for role,newrow in newrows.items():
        if role in ('api','api-secondary'):continue
        for key in ('startedAt','pid'):
            comparable_rows[role][key]=newrow[key]
            if role!='oracle':comparable_host['services'][role][key]=newrow[key]
    refresh.compare_hosts(root,comparable_host,current,comparable_rows,newrows,builds)
    # 原compose必须完整重开，只有三处程序集目录可更替。
    recipes=[]
    for side,host in enumerate((middle,current)):
        path=AREA/('formal-api-compose-'+host['composeSha256']+'.json')
        if not (root/path).exists():path=AREA/'formal-api-compose.json'
        recipe_bytes=c.raw(root,path,archive);require(ex.sha(recipe_bytes)==host['composeSha256'],'S23_REFRESH_COMPOSE_HASH');spec=json.loads(recipe_bytes)
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
        digest=host['resourceManifestSha256'];manifest_bytes=c.raw(root,AREA/('formal-resources-'+digest+'.json'),archive);require(ex.sha(manifest_bytes)==digest,'S23_REFRESH_MANIFEST_HASH');value=json.loads(manifest_bytes)
        require(value['ids']=={k:v['containerId'] for k,v in (oldrows if host is middle else newrows).items()},'S23_REFRESH_MANIFEST_IDS')
        require(value['snapshotId']==host['snapshotId'] and value['apiBuildId']==builds[side]['api']['commandId'] and value['buildOutputKey']==host['buildOutputKey']
            and value['inputsSha256']==ex.sha(refresh.bound_inputs(root,host,archive,return_bytes=True)),'S23_REFRESH_MANIFEST_BUILD')
        for key in ('snapshotId','apiBuildId','buildOutputKey','inputsSha256','admission'):value.pop(key)
        for role in ('api','api-secondary'):value['ids'].pop(role)
        manifests.append(value)
    require(manifests[0]==manifests[1],'S23_REFRESH_MANIFEST_DRIFT')

    recovered=pinned(root,MAINTENANCE,'f8fe5d7f6b318a3ddbc264fbf834bf64b5d8ce5f18b2e8e7847bfa1a862f5aa3',archive)
    require(recovered['status']=='TASK_LEVEL_RECOVERY' and recovered['post']['owner'] is None
            and recovered['post']['leaseUntilUtc'] is None and recovered['post']['status']=='FAILED' and recovered['post']['fence']==2,'ACL_LEASE_CAS')
    f=newrows['fuseki'];graph=graph_qualification(root,f['containerId'],f['startedAt'],f['pid'],archive,upper)
    result=dict(status='FIVE_REUSED_EDGES_AND_VERIFIED_RESTART',prior=qualification,oldObservationSha256=ref['sha256'],
        failedParent=PARENT,commands=consumed,graphQualification=graph,builds=builds,maintenanceCommand=recovered['actualCommandId'])
    require(proof is None or proof==result,'ACL_LEASE_EDGE_PROOF')
    return result


COMMANDS = {
    "api-secondary:absent": "2f2be42b12384b40b965f073b6f0e7fe",
    "api-secondary:api-create": "ab8ce16cba0b4802ad439d59c5ebb39b",
    "api-secondary:api-id": "b9595bc791c648c7a1bd5ae88a82d074",
    "api-secondary:api-start": "c0b583ce4df446a28802e48e947f6951",
    "api-secondary:remove": "6f09d36f824e409991faefc1a6102749",
    "api:absent": "c761304f32f74d1f81f738813d8a951e",
    "api:api-create": "8d076b5ebc134e808a4046d470fa2816",
    "api:api-id": "fc3afde3b54e468ba1dd7e2a4e8ea192",
    "api:api-start": "b14e1307855d4453b3b5951f8aabf50f",
    "api:remove": "4c87f50872e149858f091cf2494f3e85",
    "fuseki:data-start": "ce9098f928684357b06ad44dbf7326c9",
    "fuseki:stopped": "b7a7ef5e720742b89938862226edc3a5",
    "keycloak-test:data-start": "de3b79c3dc1948d28f5a32d561df2d60",
    "keycloak-test:stopped": "9f974333a2a64d3dab26ec5562ce4606",
    "oracle:data-start": "0b2acac383614ac58efb0c11f97db286",
    "oracle:stopped": "8a002e9ccc7743bdacae23b5bad2c73d",
    "platform-pg:data-start": "3577069aa4de4c349efd77725e5a735a",
    "platform-pg:stopped": "dcc2f03318eb4e8689c00e3e84432837",
    "rustfs:data-start": "5043cf16587642fe960383116d2beb35",
    "rustfs:stopped": "b7d960e6fb1c4e759bef25a1e10fa613"
}
