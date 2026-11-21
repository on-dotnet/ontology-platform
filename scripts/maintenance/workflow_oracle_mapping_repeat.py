"""同批第二条正常认证代次边；完整保留第一边和所有失败原件。"""
import copy
import json
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
from workflow_oracle_mapping_resources import require

TASK=c.TASK
RUN=c.RUN
AREA=c.AREA
PARENT='654eaf461bec4c00b9cf618bf0a93211'
CLOSE=AREA/'s2-s3-01/closeout-followup-348c1f4ed5414666b78585b628e08d66.json'
CLOSE_SHA='c42edb5ac0887e09dc89daac25e5fcfcf21a6798beaea06c56fb945328f5d4fd'
GRAPH=AREA/'s2-s3-01/graph-continuity-present-again-01.json'
START=AREA/'s2-s3-01/fuseki-start-present-again-01.json'
RECOVERY_START=Path('artifacts/workflow')/TASK/c.RECOVERY/'start-5d3687924b5540bc81eb47020c3ac3d2.json'
# 运行前由准确新start原件冻结；未填写时不开放任何新代次。
GENERATION=('2026-11-21T02:11:57.323985554Z', 27834)
BRANCH="""    if cid=='52f84c336a3ade30341a3e20fbda302677fd77ea5a71237b801e3dc5b508d9a6' and (started,pid)==('2026-11-21T02:11:57.323985554Z', 27834) and row.get('productUse')=='AWAITING_CURRENT_GRAPH_QUALIFICATION':
        from workflow_oracle_mapping_repeat import graph_qualification
        graph_qualification(platform.ROOT,cid,started,pid)
        return row['attempt']
"""
raw=c.raw
command=c.command
observed_oracle=c.observed_oracle
lifecycle_spec=c.lifecycle_spec
lifecycle_command=c.lifecycle_command
find_command=c.find_command


def close_basis(root,archive=None,upper=None):
    """仅消费准确失败停机及其补证；实际后验绑定同一退出代次，绝不推导clean。"""
    from workflow_oracle_mapping_evidence import utc
    parent_raw=raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PARENT/'receipt.json',archive)
    require(ex.sha(parent_raw)=='55bc5836dc4a76844b20ea08c4a1ab8c8728e99b2c541e50a72077db52ce3f59','S23_REPEAT_PARENT_RECEIPT')
    lower=utc(json.loads(parent_raw)['endedAtUtc'])
    if upper is None:
        start=json.loads(raw(root,START,archive));args=['inspect','-f','{{json .State}}',c.FUSEKI]
        before,_,_=command(root,start['beforeCommandId'],RUN,['docker','--context','desktop-linux',*args],'s23-repeat-fuseki-before',ex.sha(ex.encoded(args)),30,archive)
        upper=utc(before['startedAtUtc'])
    require(lower<upper,'S23_REPEAT_CLOSE_WINDOW')
    value=raw(root,CLOSE,archive);require(ex.sha(value)==CLOSE_SHA,'S23_REPEAT_CLOSE_HASH');close=json.loads(value)
    require(close['status']=='PASS_WITH_RETAINED_PRIOR_FAILURE' and close['remaining']==[] and close['operation']=='d5adba74be984fee98de76e5f69b9704','S23_REPEAT_CLOSE')
    prior=AREA/'s2-s3-01'/close['priorFailure']['file'];oldraw=raw(root,prior,archive)
    require(ex.sha(oldraw)==close['priorFailure']['sha256']=='d0b0658223f08158a2b0acfae88351ba3aaf8f720d4386ab460ede330889a5c7','S23_REPEAT_FAILURE_HASH')
    old=json.loads(oldraw);f=close['data']['fuseki'];original=Path('artifacts/workflow')/TASK/f['originalFailedStop']['file'];data=raw(root,original,archive)
    require(ex.sha(data)==f['originalFailedStop']['sha256']=='41095251a66d1f10bd4b2bdab703d0f9001d168c0dbbc030cde9e416d0f68e8a','S23_REPEAT_STOP_HASH')
    stop=json.loads(data)
    require(old['operation']==stop['operation']==close['operation'] and old['status']==stop['status']=='BLOCKED'
        and stop['reason']==old['error'].removeprefix('ValueError ')=='ORACLE_ADMISSION_FORMAL_TOTAL_DISK_42950028222'
        and stop['id']==f['id']==c.FUSEKI and stop['after']==f['after'] and stop['termSent'] and stop['processExited']
        and f['status']=='PROCESS_EXITED' and f['cleanShutdown']=='UNKNOWN' and f['allTdbLocksRemoved'] is False
        and f['observedJournals']=={'Data-0001/journal.jrnl':0},'S23_REPEAT_STOP_SCOPE')
    args=['inspect','-f','{{json .State}}',c.FUSEKI];argv=['docker','--context','desktop-linux',*args]
    row,out,err=command(root,f['stateCommand'],RUN,argv,'s23-close-fuseki-state',ex.sha(ex.encoded(args)),30,archive)
    require(lower<=utc(row['startedAtUtc'])<=utc(row['endedAtUtc'])<=upper,'S23_REPEAT_CLOSE_WINDOW')
    state=json.loads(out);require({k:state[k] for k in f['after']}==f['after'] and not state['Error'] and not state['OOMKilled']
        and utc(f['after']['FinishedAt'])<=utc(row['startedAtUtc']),'S23_REPEAT_EXIT_OBSERVATION')
    from workflow_oracle_mapping_resources import PROBE
    helper='e608809f1c7d7df0cc60cbfa796e27821b1353f1e913c6a414e5dec3416fe9c3'
    script='cd /source; test -d databases/ontology; find databases/ontology -type f \\( -name tdb.lock -o -name journal.jrnl \\) -printf "%P|%s\\n" | sort'
    args=['docker','--context','desktop-linux','create','--pull=never','--read-only','--network=none','--cap-drop=ALL','--security-opt=no-new-privileges',
        '--memory=512m','--memory-swap=512m','--cpus=.5','--pids-limit=32','--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--user','0',
        '--label','ontology.task='+TASK,'--label','ontology.run='+c.RECOVERY,'--label','ontology.attempt=3d32f9eaf76d41fd8a14d774af92eb96',
        '--mount','type=volume,src=ontology-g4-omq-restore-01_fuseki-data,dst=/source,volume-nocopy,readonly','--entrypoint=/bin/sh',PROBE,'-ec',script]
    create,out,_=command(root,'3a3ef15ae1ee40eb8730ecb2f2ad1dea',c.RECOVERY,args,'omq-recovery-tdb-closed-followup-create',ex.sha(ex.encoded(args)),45,archive)
    require(lower<=utc(create['startedAtUtc'])<=utc(create['endedAtUtc'])<=upper,'S23_REPEAT_CLOSE_WINDOW')
    require(out.decode().strip()==helper and utc(f['after']['FinishedAt'])<=utc(create['startedAtUtc']),'S23_REPEAT_JOURNAL_CREATE')
    args=['docker','--context','desktop-linux','start','-a',helper]
    execute,out,_=command(root,'bf3acdcaf2ee49a69a9428ab71c41ec9',c.RECOVERY,args,'omq-recovery-tdb-closed-followup-execute',ex.sha(ex.encoded(args)),45,archive)
    require(lower<=utc(execute['startedAtUtc'])<=utc(execute['endedAtUtc'])<=upper,'S23_REPEAT_CLOSE_WINDOW')
    require(out.decode().splitlines()==['Data-0001/journal.jrnl|0','Data-0001/tdb.lock|2','tdb.lock|2'] and utc(create['endedAtUtc'])<=utc(execute['startedAtUtc']),'S23_REPEAT_JOURNAL_OUTPUT')
    return close


def graph_qualification(root,cid,started,pid,archive=None,upper=None):
    """本次第二代真实启动、全图与Published源码单独核验。"""
    from workflow_oracle_mapping_evidence import utc
    require(cid==c.FUSEKI and GENERATION is not None and (started,pid)==GENERATION,'S23_REPEAT_GRAPH_GENERATION')
    close=close_basis(root,archive);proof=json.loads(raw(root,GRAPH,archive));start_raw=raw(root,START,archive);start=json.loads(start_raw)
    require(raw(root,RECOVERY_START,archive)==start_raw,'S23_REPEAT_START_ORIGINAL')
    require((proof['taskId'],proof['runId'],proof['batch'])==(TASK,RUN,'s2-s3-01') and proof['startSha256']==ex.sha(start_raw),'S23_REPEAT_GRAPH_SCOPE')
    require((start['id'],start['startedAt'],start['pid'])==(cid,started,pid) and start['stage']==RUN and start['role']=='fuseki' and start['status']=='RUNNING'
        and start['productUse']=='AWAITING_CURRENT_GRAPH_QUALIFICATION' and start['priorCloseSha256']==CLOSE_SHA,'S23_REPEAT_START')
    state_args=['inspect','-f','{{json .State}}',cid];argv=['docker','--context','desktop-linux',*state_args]
    before,out,_=command(root,start['beforeCommandId'],RUN,argv,'s23-repeat-fuseki-before',ex.sha(ex.encoded(state_args)),30,archive)
    state=json.loads(out);require({k:state[k] for k in close['data']['fuseki']['after']}==close['data']['fuseki']['after'],'S23_REPEAT_STOP_GENERATION')
    row,out,_=lifecycle_command(root,start['startCommandId'],'fuseki',cid,'data-start',archive)
    require(out.decode().strip()==cid and utc(before['endedAtUtc'])<=utc(row['startedAtUtc'])<=utc(started)<=utc(row['endedAtUtc']),'S23_REPEAT_START_COMMAND')
    fmt='{{.State.Status}}|{{.State.StartedAt}}|{{.State.Pid}}';args=['inspect','-f',fmt,cid]
    generation,body,_=command(root,start['generationCommandId'],RUN,['docker','--context','desktop-linux',*args],'s23-repeat-fuseki-generation',ex.sha(ex.encoded(args)),30,archive)
    require(body.decode().strip()=='running|'+started+'|'+str(pid) and utc(row['endedAtUtc'])<=utc(generation['startedAtUtc']),'S23_REPEAT_LIVE_GENERATION')
    scans={}
    for kind in ('default','named'):
        args=c.scan_argv(kind);row,out,err=command(root,proof['scans'][kind],RUN,args,'s23-repeat-graph-'+kind,ex.sha(ex.encoded(args)),25,archive)
        require(not err and utc(generation['endedAtUtc'])<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'S23_REPEAT_SCAN_ORDER')
        value=json.loads(out);fields={'s','p','o'}|({'g'} if kind=='named' else set())
        require(set(value['head']['vars'])==fields and all(set(v)==fields for v in value['results']['bindings']),'S23_REPEAT_GRAPH_FIELDS');scans[kind]=value['results']['bindings']
    args=['docker','--context','desktop-linux','exec','-i','--user','postgres',c.PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    row,out,err=command(root,proof['publicationCommandId'],RUN,args,'s23-repeat-published-sources',ex.sha(c.publication_sql()),25,archive)
    require(not err and utc(started)<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'S23_REPEAT_PUBLICATION_ORDER')
    c.check_publications([json.loads(line) for line in out.decode().splitlines() if line.strip()])
    frozen_raw=raw(root,AREA/'s2-s3-01/frozen-graphs-second-open.json',archive)
    require(ex.sha(frozen_raw)=='393a597292cfba79d9b772bf7bac9a34d3e7d843bcf0c7e9ed3e97e9fd87c328','S23_REPEAT_FROZEN')
    expected=c.expected_graphs(scans['default'],scans['named'],json.loads(frozen_raw));require(proof['expected']==expected,'S23_REPEAT_EXPECTED')
    return expected


def prior_host(root,archive=None):
    """准确上窗的输入观察作为中间宿主；旧第一边仍由原消费者完整重开。"""
    from workflow_oracle_mapping_evidence import stable_host
    from workflow_oracle_mapping_continuation import frozen_member
    argv=['python3','-B','/private/tmp/omq-final-auth-failure-reopen.py']
    row,out,err=command(root,'0a18bb690dac4507bf6cbe7b453b1353',RUN,argv,'s23-final-auth-failed-window-reopen','8af572f8f0a6605ded8dcf0b4e4b10c6d123c388b508807ecb9dc8ab3272c6e7',120,archive)
    require(not err and ex.sha(out)=='db85fbd14d2ee61615a599ea557fca669f851090c44929ae3eeb29be5b35d948','S23_REPEAT_PRIOR_QUALIFICATION')
    qualified=json.loads(out)
    require(qualified['status']=='FAILED_WINDOW_ORIGINALS_REOPENED' and qualified['productQualification']=='NOT_QUALIFIED'
        and qualified['commandId']==PARENT and qualified['measuredCommit']=='fe3293b62459d29d32cd8a2ed86bc838d81f4d0c'
        and qualified['memberCount']==813 and ex.sha(ex.encoded(qualified['members']))=='469d94a5e5b1e222707ae3085cc958bf21607a697c1157307b5f66e6f5cb1c38','S23_REPEAT_PRIOR_INDEX')
    for name,item in qualified['members'].items():frozen_member(root,item,archive,'repeat-prior-'+name)
    dispatch=json.loads(raw(root,AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json'),archive))
    require(dispatch['testedCommit']=='fe3293b62459d29d32cd8a2ed86bc838d81f4d0c' and dispatch['commandId']==PARENT and dispatch['exitCode']==1,'S23_REPEAT_PRIOR_PARENT')
    ref=dispatch['stageInputs']['qualifiedPrefix'];require(ref['file']=='prefix-observation-bdad3c0158994260a5db0a8941fb6540.json'
        and ref['sha256']=='40be52818e65b54efb1ef837359efefc7c686815e182e56263770ef3effa5f08','S23_REPEAT_PRIOR_OBSERVATION')
    value=raw(root,AREA/'s2-s3-01'/ref['file'],archive);require(ex.sha(value)==ref['sha256'],'S23_REPEAT_PRIOR_OBSERVATION_HASH');observation=json.loads(value)
    require(stable_host(observation['host'])==stable_host(dispatch['host']),'S23_REPEAT_MIDDLE_HOST')
    return observation


def lifecycle(root,previous,current,proof=None,archive=None):
    """旧代次入口原样保留；新代次明确消费两条连续边而非跳接。"""
    if current['snapshotId']=='0b0326525f6e62ca272e243033def2396437265e5a82d1d345d3d94180ef30e6' and current['services']['api']['containerId']=='7f88656c9dc0d2699a5bcddd911d1ba88617c4a4be6354b97cc7d6006d4c0389':
        from workflow_oracle_mapping_postprobe import lifecycle as postprobe
        return postprobe(root,previous,current,proof,archive)
    if current['snapshotId']=='0b0326525f6e62ca272e243033def2396437265e5a82d1d345d3d94180ef30e6' and current['services']['api']['containerId']=='4d4b403d37e11d19e5082e0a2ead5235d66f135e52a3f46f22022ec9c333d89e':
        from workflow_oracle_mapping_preparation_refresh import lifecycle as preparation_refresh
        return preparation_refresh(root,previous,current,proof,archive)
    if current['snapshotId']!=previous['snapshotId']:
        from workflow_oracle_mapping_access_refresh import lifecycle as refresh
        return refresh(root,previous,current,proof,archive)
    observed=current['services']['fuseki']
    if (observed['startedAt'],observed['pid'])==c.GENERATION:return c.lifecycle(root,previous,current,proof,archive)
    require(GENERATION is not None and (observed['startedAt'],observed['pid'])==GENERATION,'S23_REPEAT_CURRENT_GENERATION')
    middle=prior_host(root,archive)
    first=c.lifecycle(root,previous,middle['host'],middle['hostContinuity'],archive)
    second=second_segment(root,middle['host'],current,None if proof is None else proof['second'],archive)
    result=dict(status='TWO_ACTUAL_GENERATION_EDGES',previousParent=PARENT,first=first,second=second)
    require(proof is None or proof==result,'S23_REPEAT_CHAIN');return result


def second_segment(root,previous,current,proof=None,archive=None):
    """准备时发现、重开时按固定引用核验全部允许变化的真实生命周期原件。"""
    from workflow_oracle_mapping_continuation import PREFIX,resumed_host
    from workflow_oracle_mapping_evidence import utc
    close_basis(root,archive)
    continuity=resumed_host(previous,current)
    oldrow,oldoracle=observed_oracle(root,previous,archive);newrow,neworacle=observed_oracle(root,current,archive)
    require(oldoracle['mounts']==neworacle['mounts'],'S23_CONTINUITY_ORACLE_MOUNTS')
    close=json.loads(raw(root,CLOSE,archive))
    require((close['taskId'],close['runId'],close['batch'],close['status'])==(TASK,RUN,'s2-s3-01','PASS_WITH_RETAINED_PRIOR_FAILURE') and close['remaining']==[],'S23_CONTINUITY_CLOSE')
    parent=json.loads(raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PARENT/'receipt.json',archive))
    lower=utc(parent['endedAtUtc']);upper=utc(newrow['startedAtUtc'])
    require(utc(oldrow['endedAtUtc'])<=lower<upper,'S23_CONTINUITY_ORDER')
    manifests=[]
    for host in (previous,current):
        digest=host['resourceManifestSha256'];data=raw(root,AREA/('formal-resources-'+digest+'.json'),archive)
        require(ex.sha(data)==digest,'S23_CONTINUITY_MANIFEST_HASH');value=json.loads(data)
        require(value['ids']=={**{k:v['containerId'] for k,v in host['services'].items()},'oracle':host['oracle']['containerId']},'S23_CONTINUITY_MANIFEST_IDS')
        value['ids']={k:v for k,v in value['ids'].items() if k not in ('api','api-secondary')};manifests.append(value)
    require(manifests[0]==manifests[1],'S23_CONTINUITY_MANIFEST_DRIFT')
    references={} if proof is None else proof['commands'];consumed={}
    oldservices={**previous['services'],'oracle':oldoracle};newservices={**current['services'],'oracle':neworacle}
    require(close['ids']=={k:v['containerId'] for k,v in oldservices.items()},'S23_CONTINUITY_CLOSE_IDS')
    for role,old in oldservices.items():
        new=newservices[role];api=role in ('api','api-secondary')
        kinds=('remove','absent','api-create','api-id','api-start') if api else ('stopped','data-start')
        previous_end=lower
        for kind in kinds:
            resource=old['containerId'] if kind in ('remove','absent','stopped') else new['containerId']
            label=role+':'+kind
            cid=find_command(root,role,resource,kind,lower,upper) if proof is None else references[label]
            row,out,err=lifecycle_command(root,cid,role,resource,kind,archive)
            require(previous_end<=utc(row['startedAtUtc'])<=utc(row['endedAtUtc'])<=upper,'S23_CONTINUITY_COMMAND_ORDER')
            if kind=='stopped':
                state=json.loads(out);after={k:state[k] for k in ('Status','ExitCode','OOMKilled','FinishedAt')}
                require(after==close['data'][role]['after'] and after['Status']=='exited' and not after['OOMKilled'] and after['ExitCode'] in (0,143)
                    and not state['Error'] and utc(old['startedAt'])<utc(after['FinishedAt'])<utc(new['startedAt']),'S23_CONTINUITY_STOP_GENERATION')
            elif kind=='absent':require(not out.strip(),'S23_CONTINUITY_API_ABSENT')
            elif kind in ('remove','data-start','api-id','api-start'):require(out.decode().strip()==resource,'S23_CONTINUITY_ACTION_ID')
            if kind in ('data-start','api-start'):
                require(utc(row['startedAtUtc'])<=utc(new['startedAt'])<=utc(row['endedAtUtc']),'S23_CONTINUITY_START_GENERATION')
            consumed[label]=cid;previous_end=utc(row['endedAtUtc'])
    require(proof is None or references==consumed,'S23_CONTINUITY_EXTRA_COMMAND')
    graph=graph_qualification(root,newservices['fuseki']['containerId'],newservices['fuseki']['startedAt'],newservices['fuseki']['pid'],archive,upper)
    result=dict(continuity=continuity,commands=consumed,oracleMountSha256=ex.sha(ex.encoded(oldoracle['mounts'])),graphQualification=graph)
    require(proof is None or proof==result,'S23_CONTINUITY_PROOF_CHANGED')
    return result
