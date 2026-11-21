"""本次源前置失败的准确两API同构建重建边；原三边和所有失败保持。"""
import json
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
import workflow_oracle_mapping_access_refresh as refresh
from workflow_oracle_mapping_access_refresh import bound_inputs,snapshot_builds,observed_rows,compare_hosts
from workflow_oracle_mapping_resources import require
TASK=c.TASK
RUN=c.RUN
AREA=c.AREA
PARENT='7e3085f4533143fb84b49adc83159998'
OLD_COMMIT='451d26a9de8c77e9ec408d9b2208d2dcac4755e0'


def lifecycle(root,previous,current,proof=None,archive=None):
    """旧失败只作真实宿主锚点，完整消费原三边后连接本次准确两API同构建重建边。"""
    from workflow_oracle_mapping_evidence import utc,stable_host
    import workflow_oracle_mapping_repeat as repeat
    path=AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json');data=c.raw(root,path,archive)
    require(ex.sha(data)=='7157305e4b5a50374c32c1cdd1fa45c441bf84789d2a633ee6348d66fb698085','S23_PREPARATION_REFRESH_PARENT_HASH');dispatch=json.loads(data)
    require((dispatch['taskId'],dispatch['runId'],dispatch['commandId'],dispatch['testedCommit'],dispatch['exitCode'])==(TASK,RUN,PARENT,OLD_COMMIT,1),'S23_PREPARATION_REFRESH_FAILED_PARENT')
    from workflow_oracle_mapping_evidence import Originals,NODE,DRIVER
    class Parent(Originals):
        def __init__(self):self.root=root
        def raw(self,name):
            require(name.startswith(PARENT+'-'),'S23_PREPARATION_REFRESH_PARENT_MEMBER')
            return c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PARENT/name.removeprefix(PARENT+'-'),archive)
    argv=[NODE,DRIVER,'--task',TASK,'--run-id',RUN,'--mode','s2-s3-oracle','--batch-input',dispatch['stageInputs']['batchInput']]
    parent,_,_=Parent().command(PARENT,argv,'omq-browser-s2-s3-oracle','877fffa7f1588dc89c677576d1d9110e288ee367a28a3de5bccb8edb067d0047','497193cefee9445eb708881f077be62c',root,command_run=RUN)
    require(parent['deadlineSeconds']==2520,'S23_PREPARATION_REFRESH_PARENT_BUDGET')
    require(parent['exitCode']==1 and parent['classification']=='EXIT_FAILURE','S23_PREPARATION_REFRESH_PARENT_FAILURE')
    middle=dispatch['host'];require(previous['snapshotId']!=middle['snapshotId']==current['snapshotId'],'S23_PREPARATION_REFRESH_CHAIN_SCOPE')
    observed=c.raw(root,AREA/'s2-s3-01/prefix-observation-85751d15c3ea4bf6aedc6222739960de.json',archive)
    require(ex.sha(observed)=='f88056757c79d612016b375a7776ba304aeae8caf26f309b56942c79e1f7cf4f','S23_PREPARATION_REFRESH_MIDDLE_OBSERVATION')
    observation=json.loads(observed);require(stable_host(middle)==stable_host(observation['host']),'S23_PREPARATION_REFRESH_MIDDLE_HOST')
    prior=refresh.lifecycle(root,previous,middle,observation['hostContinuity'],archive)
    oldreceipt,oldrows=observed_rows(root,middle,archive);newreceipt,newrows=observed_rows(root,current,archive)
    builds=[snapshot_builds(root,host,archive) for host in (middle,current)]
    require(builds[0]==builds[1],'S23_PREPARATION_REFRESH_BUILD_UNCHANGED')
    compare_hosts(root,middle,current,oldrows,newrows,builds)
    # 三份构建和compose本次保持相同；只允许准确两API身份/进程更替。
    recipes=[]
    for side,host in enumerate((middle,current)):
        path=AREA/('formal-api-compose-'+host['composeSha256']+'.json')
        if not (root/path).exists():path=AREA/'formal-api-compose.json'
        raw=c.raw(root,path,archive);require(ex.sha(raw)==host['composeSha256'],'S23_PREPARATION_REFRESH_COMPOSE_HASH');spec=json.loads(raw)
        for role,service in spec['services'].items():
            expected={'/app':'api',**({'/session-tests':'agent','/query-tests':'query'} if role=='api-secondary' else {})}
            for destination,target in expected.items():
                old=str(root/builds[side][target]['directory'])+':'+destination+':ro'
                require(service['volumes'].count(old)==1,'S23_PREPARATION_REFRESH_COMPOSE_MOUNT');service['volumes'][service['volumes'].index(old)]='VERIFIED_'+target+':'+destination+':ro'
        recipes.append(spec)
    require(recipes[0]==recipes[1],'S23_PREPARATION_REFRESH_COMPOSE_DRIFT')
    # 精确资源清单除API身份和构建字段外不变。
    manifests=[]
    for side,host in enumerate((middle,current)):
        digest=host['resourceManifestSha256'];raw=c.raw(root,AREA/('formal-resources-'+digest+'.json'),archive);require(ex.sha(raw)==digest,'S23_PREPARATION_REFRESH_MANIFEST_HASH');value=json.loads(raw)
        require(value['ids']=={k:v['containerId'] for k,v in (oldrows if host is middle else newrows).items()},'S23_PREPARATION_REFRESH_MANIFEST_IDS')
        require(value['snapshotId']==host['snapshotId'] and value['apiBuildId']==builds[side]['api']['commandId'] and value['buildOutputKey']==host['buildOutputKey']
            and value['inputsSha256']==ex.sha(bound_inputs(root,host,archive,return_bytes=True)),'S23_PREPARATION_REFRESH_MANIFEST_BUILD')
        for key in ('snapshotId','apiBuildId','buildOutputKey','inputsSha256','admission'):value.pop(key)
        for role in ('api','api-secondary'):value['ids'].pop(role)
        manifests.append(value)
    require(manifests[0]==manifests[1],'S23_PREPARATION_REFRESH_MANIFEST_DRIFT')
    lower=utc(parent['endedAtUtc']);upper=utc(newreceipt['startedAtUtc']);require(utc(oldreceipt['endedAtUtc'])<=lower<upper,'S23_PREPARATION_REFRESH_ORDER')
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
                    require(len(matches)==1,'S23_PREPARATION_REFRESH_UNIQUE_COMMAND');cid=matches[0]
                else:cid=references[label]
                receipt,out,_=c.command(root,cid,RUN,argv,stage,key,seconds,archive)
            else:
                cid=c.find_command(root,role,resource,kind,lower,upper) if proof is None else references[label]
                receipt,out,_=c.lifecycle_command(root,cid,role,resource,kind,archive)
            require(end<=utc(receipt['startedAtUtc'])<=utc(receipt['endedAtUtc'])<=upper,'S23_PREPARATION_REFRESH_COMMAND_ORDER')
            if kind=='exit':require(out.strip() in (b'exited 0 false',b'exited 143 false'),'S23_PREPARATION_REFRESH_EXIT')
            elif kind=='absent':require(not out.strip(),'S23_PREPARATION_REFRESH_ABSENT')
            elif kind in ('term','remove','api-id','api-start'):require(out.decode().strip()==resource,'S23_PREPARATION_REFRESH_ACTION_ID')
            if kind=='api-start':require(utc(receipt['startedAtUtc'])<=utc(new['startedAt'])<=utc(receipt['endedAtUtc']),'S23_PREPARATION_REFRESH_START_GENERATION')
            consumed[label]=cid;end=utc(receipt['endedAtUtc'])
    recovery=maintenance_result(root,middle,current,builds[1],consumed,archive)
    result=dict(recovery=recovery,status='THREE_PRIOR_EDGES_AND_SAME_BUILD_API_RESTART',failedParent=PARENT,prior=prior,commands=consumed,
        builds=builds,dataScope='Five persistent service identities and process generations unchanged; exact failed query lease maintenance separately recorded')
    require(proof is None or proof==result,'S23_PREPARATION_REFRESH_PROOF');return result


def maintenance_result(root,previous,current,builds,lifecycle_commands,archive=None):
    """离线重开同次两列恢复；用实际CAS时间核五分钟证明，绝不重执行维护或使用当前时钟。"""
    from workflow_oracle_mapping_evidence import utc
    from workflow_oracle_mapping_platform import HOST_FORMAT,PROBE,IMAGES
    from workflow_m2_build import TARGETS
    from doris_keep_drain import COUNTS,ACTIVITY
    import workflow_oracle_preparation_maintenance as a
    import datetime as dt
    producer='2670f1d2c64b4b8f50a4f0f0eae6bd8f1f09e8ddd0c33fa9419d0096b8be87a3'
    require(ex.sha(ex.ordinary(root/'scripts/maintenance/workflow_oracle_preparation_maintenance.py').read_bytes())==producer,'S23_PREPARATION_REFRESH_MAINTENANCE_PRODUCER')
    attempt='e5c8e3028ca649fc8b8270c1df1eb474';base=AREA/'s2-s3-01'
    pre=json.loads(c.raw(root,base/('preparation-prestate-'+attempt+'.json'),archive));proof=pre['proof']
    result=json.loads(c.raw(root,base/('preparation-recovery-'+attempt+'.json'),archive));sealed_raw=c.raw(root,base/'preparation-api-seal.json',archive);sealed=json.loads(sealed_raw)
    require(ex.sha(sealed_raw)==proof['sealSha256']=='fdd3d8ab116b2af85ed3d8cd28fc18907773073cfa46d94262ba5228a6e880ee'
        and pre['proofSha256']==result['proofSha256']==ex.sha(ex.encoded(proof))=='c2e9730c607a5bb45d19af398cc3eaf60372a64b2804bfee6145193f7aef4693'
        and result['attemptId']==pre['attemptId']==proof['attemptId']==attempt and result['build']==builds['api']['build']
        and result['status']=='TASK_LEVEL_RECOVERY' and result['exitCode']==0 and result['helperReleased'] and result['originalCleanup250ms']=='NOT_QUALIFIED','S23_PREPARATION_REFRESH_RECOVERY_SCOPE')
    termination=pre['termination'];require(ex.sha(ex.encoded(termination))==proof['terminationProofSha256'] and termination['commands']==pre['commands']
        and termination['host']==pre['host'] and termination['queryId']==proof['queryId']==a.QUERY and termination['sourceExecutionId']==proof['sourceExecutionId']==a.EXECUTION
        and termination['sourceId']==proof['sourceContainerId']==a.SOURCE and termination['sourceSessions']==0,'S23_PREPARATION_REFRESH_TERMINATION')
    ids=sealed['ids'];dataids={k:v for k,v in ids.items() if k not in ('api','api-secondary')}
    require(ids=={**{k:v['containerId'] for k,v in previous['services'].items()},'oracle':previous['oracle']['containerId']} and set(sealed['apis'])=={'api','api-secondary'},'S23_PREPARATION_REFRESH_SEAL_SCOPE')
    def call(cid,stage,args,payload=None,timeout=30,source=producer):
        key=ex.sha(ex.encoded(dict(args=args,payloadSha256=ex.sha(payload or b''),producer=source)))
        return c.command(root,cid,RUN,args,'s23-preparation-'+stage,key,timeout,archive)
    def rows(data,names):
        answer={}
        for name,line in zip(names,data.decode().strip().splitlines(),strict=True):
            value=line.split('|');require(len(value)==9,'S23_PREPARATION_REFRESH_RECOVERY_HOST_FIELDS')
            answer[name]=[*value[:7],json.loads(value[7]),dict(pair.split('=') for pair in value[8].split())]
        return answer
    def canonical(value):return {k:[*v[:7],json.loads(v[7]),dict(x.split('=') for x in v[8].split())] for k,v in value.items()}
    oldproducer=producer
    observations=[]
    for stage,selected in [('before',ids),('after',dataids)]:
        names=sorted(selected);rec,out,_=call(sealed[stage]['commandId'],'seal-'+stage,[*a.DOCKER,'inspect','-f',HOST_FORMAT,*[selected[n] for n in names]],source=oldproducer)
        require(rows(out,names)==canonical(sealed[stage]['rows']),'S23_PREPARATION_REFRESH_SEAL_ROWS');observations.append(rec)
    oldrec,oldrows=observed_rows(root,previous,archive)
    for name,value in canonical(sealed['before']['rows']).items():
        old=oldrows[name];require(value[0:2]==[old['containerId'],old['imageId']] and int(value[5])==old['pid'] and value[6:]==[old['startedAt'],old['mounts'],old['networks']],'S23_PREPARATION_REFRESH_SEAL_GENERATION')
    require(canonical(sealed['after']['rows'])=={k:v for k,v in canonical(sealed['before']['rows']).items() if k in dataids},'S23_PREPARATION_REFRESH_SEAL_DATA')
    for role in ('api','api-secondary'):
        require(sealed['apis'][role]['id']==ids[role] and sealed['apis'][role]['absentCommandId']==lifecycle_commands[role+':absent'],'S23_PREPARATION_REFRESH_SEAL_ABSENCE')
        before=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':term']/'receipt.json',archive))
        after=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':absent']/'receipt.json',archive))
        require(utc(observations[0]['endedAtUtc'])<=utc(before['startedAtUtc'])<=utc(after['endedAtUtc'])<=utc(observations[1]['startedAtUtc']),'S23_PREPARATION_REFRESH_SEAL_ORDER')
    names=sorted(dataids);rec,out,_=call(pre['host']['commandId'],'prestate-host',[*a.DOCKER,'inspect','-f',HOST_FORMAT,*[dataids[n] for n in names]])
    require(rows(out,names)==canonical(pre['host']['rows'])==canonical(sealed['after']['rows']) and utc(observations[1]['endedAtUtc'])<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_PRESTATE_HOST');end=utc(rec['endedAtUtc'])
    for role in ('api','api-secondary'):
        rec,out,_=call(pre['commands']['absent-'+role],'prestate-absent-'+role,[*a.DOCKER,'ps','-aq','--no-trunc','--filter','id='+ids[role]])
        require(not out.strip() and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_PRESTATE_ABSENCE');end=utc(rec['endedAtUtc'])
    pg=[*a.DOCKER,'exec','-i','--user','postgres',a.PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    sql='SELECT json_build_array('+','.join('('+s.strip()+')' for s in (*COUNTS,ACTIVITY))+');'
    rec,out,_=call(pre['commands']['drain'],'prestate-drain',pg,sql.encode());require(json.loads(out)==[0]*8 and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_DRAIN');end=utc(rec['endedAtUtc'])
    for which in ('first','second'):
        rec,out,_=call(pre['commands']['source-'+which],'source-zero-'+which,[*a.DOCKER,'exec','-i',a.SOURCE,'sqlplus','-L','-s','/ as sysdba'],a.SOURCE_SQL.encode())
        require(out.strip()==b'0' and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_SOURCE_ZERO');end=utc(rec['endedAtUtc'])
    prestate={}
    for name,sql in [('row',a.ROW_SQL),('audit',a.AUDIT_SQL)]:
        rec,out,_=call(pre['commands'][name],'prestate-'+name,pg,sql.encode());require(end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_PRESTATE_ORDER');end=utc(rec['endedAtUtc']);prestate[name]=json.loads(out)
    require(end<=utc(proof['verifiedUtc']) and prestate['row']['stableRowSha256']==a.STABLE and prestate['row']['owner']==a.OWNER
        and prestate['row']['status']=='FAILED' and prestate['row']['fence']==2 and len(prestate['audit'])==1
        and prestate['audit'][0]['id']==a.FAILURE_AUDIT and prestate['audit'][0]['sha256']==a.FAILURE_SHA and prestate['audit'][0]['outcome']=='failure','S23_PREPARATION_REFRESH_PRESTATE_BYTES')
    helper=result['helperId'];args,script=a.recovery_argv(proof,pre['proofSha256'])
    import workflow_oracle_preparation_runner as runner
    runner_binding=runner.verified_runner()
    reopen_isolated(root,runner_binding,archive)
    require(result['runnerBinding']==runner_binding,'S23_PREPARATION_RUNNER_BINDING')
    c.raw(root,runner.DIRECTORY.relative_to(root)/'build.json',archive)
    c.raw(root,Path(runner_binding['dll']['path']),archive)
    for name in runner_binding['inputs']:
        path=Path(name)
        if not path.is_absolute() and path.is_relative_to(runner.DIRECTORY.relative_to(root)):c.raw(root,path,archive)
    for name in ('receipt.json','stdout.txt','stderr.txt'):
        c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/runner_binding['commandId']/name,archive)
    rec,out,_=call(result['createCommandId'],'recovery-create',[*args,'--entrypoint=/bin/sh',PROBE,'-ec',script]);require(out.decode().strip()==helper and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_HELPER_CREATE');end=utc(rec['endedAtUtc'])
    rec,out,_=call(result['beforeCommandId'],'recovery-before',[*a.DOCKER,'inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}',helper])
    require(out.decode().strip()=='|'.join((helper,IMAGES['api'],attempt,'created')) and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_HELPER_OWNER');end=utc(rec['endedAtUtc'])
    cas,out,err=c.command(root,result['actualCommandId'],RUN,[*a.DOCKER,'start','-a','-i',helper],'s23-preparation-recovery-cas',pre['proofSha256'],32,archive)
    require(end<=utc(cas['startedAtUtc']) and utc(proof['verifiedUtc'])<=utc(cas['startedAtUtc'])<=utc(cas['endedAtUtc'])<utc(proof['validUntilUtc'])
        and utc(proof['validUntilUtc'])-utc(proof['verifiedUtc'])==dt.timedelta(minutes=5) and json.loads(out)==result['commitEnvelope']
        and result['commitEnvelope']['status']=='TASK_LEVEL_RECOVERY' and result['commitEnvelope']['operationId']==proof['operationId']==result['operationId']
        and utc(cas['startedAtUtc'])<=utc(result['commitEnvelope']['lowerUtc'])<=utc(result['commitEnvelope']['upperUtc'])<=utc(cas['endedAtUtc'])
        and (not err or len(err)==127 and ex.sha(err)=='6a55ce9418db27c92344e3846e6ec6fe5718cb84e315fe05c82d3403ebff3a9d'),'S23_PREPARATION_REFRESH_CAS');end=utc(cas['endedAtUtc'])
    for field,stage,args,expected in [('exitCommandId','recovery-exit',[*a.DOCKER,'inspect','-f','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',helper],b'exited|0|false'),
        ('removeCommandId','recovery-remove',[*a.DOCKER,'rm',helper],helper.encode()),('absentCommandId','recovery-absent',[*a.DOCKER,'ps','-aq','--no-trunc','--filter','id='+helper],b'')]:
        rec,out,_=call(result[field],stage,args);require(out.strip()==expected and end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_HELPER_RELEASE');end=utc(rec['endedAtUtc'])
    post={}
    for name,sql in [('row',a.ROW_SQL),('audit',a.AUDIT_SQL)]:
        rec,out,_=call(result[name+'CommandId'],'post-'+name,pg,sql.encode());require(end<=utc(rec['startedAtUtc']),'S23_PREPARATION_REFRESH_POST_ORDER');end=utc(rec['endedAtUtc']);post[name]=json.loads(out)
    require(post['row']==result['post']=={**prestate['row'],'owner':None,'leaseUntilUtc':None} and post['audit']==result['audits'] and len(post['audit'])==2
        and prestate['audit'][0] in post['audit'],'S23_PREPARATION_REFRESH_POST_BYTES')
    new=next(item for item in post['audit'] if item!=prestate['audit'][0]);require(new['action']=='data.query.cleanup.recover' and new['outcome']=='allowed' and new['actor']==proof['operatorId']
        and new['trace']==proof['operationId'] and new['correlation']==attempt and new['organization']=='org-demo' and new['sites']==['site-a'],'S23_PREPARATION_REFRESH_POST_AUDIT')
    for role in ('api','api-secondary'):
        started=json.loads(c.raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/lifecycle_commands[role+':api-create']/'receipt.json',archive))
        require(end<=utc(started['startedAtUtc']),'S23_PREPARATION_REFRESH_AFTER_RECOVERY')
    return dict(status='TASK_LEVEL_RECOVERY',commandId=result['actualCommandId'],queryId=a.QUERY,proofSha256=pre['proofSha256'],postRowCommandId=result['rowCommandId'],postAuditCommandId=result['auditCommandId'],originalCleanup250ms='NOT_QUALIFIED')


def reopen_isolated(root,runner_binding,archive=None):
    """非作者已重开的48件固定测试原件；实际MTP总数/退出码/身份仍逐件核对。"""
    base=AREA/'s2-s3-01/preparation-pg-6b7675c651b84ffbb3d9d87683545f62'
    raw=c.raw(root,base/'receipt.json',archive);require(ex.sha(raw)=='1bd0437577fd7537b3b9c94593af1db56c2175959716c3f9b6200461177e0d68','S23_PREPARATION_TEST_RECEIPT')
    row=json.loads(raw);members={str(base/'receipt.json'):raw}
    for cid in [*[v['commandId'] for v in row['commands']],row['actualCommandId']]:
        for name in ('receipt.json','stdout.txt','stderr.txt'):
            path=Path('artifacts/workflow')/TASK/'commands'/RUN/cid/name;members[str(path)]=c.raw(root,path,archive)
    for name in ('stdout.txt','stderr.txt'):
        path=base/'streams'/name;members[str(path)]=c.raw(root,path,archive)
    index=[dict(path=k,sizeBytes=len(v),sha256=ex.sha(v)) for k,v in sorted(members.items())]
    require(len(index)==48 and ex.sha(ex.encoded(index))=='1ab6f16d7827560e75592c83eb7100b9a8feb97c48af048977de170f71fa7109','S23_PREPARATION_TEST_FROZEN_INDEX')
    require(row['runnerBinding']==runner_binding and row['status']=='PASS' and row['helperReleased'] and row['databaseReleased'],'S23_PREPARATION_TEST_BINDING')
    before={k:v for k,v in row.items() if k not in ('actualCommandId','actualExitCode','test','execution','helperReleased','databaseReleased','afterAdmission')}
    before['status']='PREPARING';before['commands']=row['commands'][:8]
    rec,out,_=c.command(root,row['actualCommandId'],RUN,['docker','--context','desktop-linux','start','-a',row['helperId']],'s23-preparation-pg-actual',ex.sha(ex.encoded(before)),80,archive)
    test=json.loads(out);require(row['test']==[test] and test['method']=='G4QueryRaceTests.OraclePreparationFailureMaintenanceInIsolatedPostgres'
        and test['total']==test['succeeded']==test['expected']==1 and test['failed']==test['skipped']==test['exitCode']==0 and not test['timedOut'],'S23_PREPARATION_TEST_ACTUAL')
    for kind in ('stdout','stderr'):
        raw=members[str(base/'streams'/(kind+'.txt'))];require(ex.sha(raw)==test[kind+'Sha256'] and len(raw)==test[kind+'Bytes'],'S23_PREPARATION_TEST_STREAM')
    return dict(status='PASS',commandId=row['actualCommandId'],tests=1,indexSha256=ex.sha(ex.encoded(index)),mtpGenerationArgv='NOT_REOPENED')
