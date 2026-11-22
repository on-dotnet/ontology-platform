"""重开 05ea 后唯一一次 d368 专用 PG 维护关闭；向后只推进 PG 代次。"""
import json
import os
import re
from types import SimpleNamespace

import workflow_execution as ex
import workflow_oracle_d368_closure as seal
import workflow_oracle_mapping_continuity as c
import workflow_oracle_runtime_window as w
from workflow_oracle_mapping_evidence import utc
from workflow_oracle_mapping_resources import INVENTORY_SHA, KEEP_FORMAT, require

TASK, RUN, PLAN, PG = w.TASK, w.RUN, w.PLAN, c.PG
AREA, PREVIOUS, DOCKER = seal.AREA, seal.RESTORED, seal.DOCKER
KIND = 'D368_PG_ONLY'
STATE_FORMAT = '{{.Id}}|{{.State.Status}}|{{.State.Pid}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.State.OOMKilled}}|{{.State.Error}}'
PG_FAST = ['exec', '--user', 'postgres', PG, 'sh', '-ec',
           'test "$(id -u)" = 999 && pg_ctl status -D "$PGDATA" >/dev/null && exec pg_ctl stop -D "$PGDATA" -m fast -W']
REC = c.AREA.parent / c.RECOVERY


def ident(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value), 'D368_CLOSE_ID')
    return value


def raw_json(root, name, archive):
    return json.loads(c.raw(root, name, archive))


def record(root, run, cid, archive):
    return raw_json(root, c.AREA.parent / 'commands' / run / ident(cid) / 'receipt.json', archive)


def state_args(prior, formal):
    persistent = [prior['data'][role]['id'] for role in sorted(prior['data'])]
    apis = sorted({row['id'] for close in (formal, prior) for row in close['apis'].values()})
    return {'state': ['inspect', '-f', STATE_FORMAT, *persistent],
            'absent': ['ps', '-aq', '--no-trunc', *[v for api in apis for v in ('--filter', 'id=' + api)]]}


def capture_closed_state():
    """在当前 PG-only 窗 finally 收口之后、退出该窗前采集准确五角色和四个 API ID。"""
    import workflow_oracle_mapping_resume as resume
    require(w.policy()['priorCloseSha256'] == PREVIOUS, 'D368_CLOSE_WINDOW')
    prior = w.last_close(w.ROOT, digest=PREVIOUS)
    formal = w.last_close(w.ROOT, digest=seal.FORMAL)
    return {name: resume.command('d368-post-' + name, argv)[1]
            for name, argv in state_args(prior, formal).items()}


def native_references(pg_stop_attempt):
    """用准确 stop 原件的区间和角色 stage 选择唯一命令，立即冻结 ID。"""
    root = w.ROOT
    stop = raw_json(root, REC / ('stop-' + ident(pg_stop_attempt) + '.json'), None)
    require(stop['role'] == 'platform-pg' and stop['id'] == PG, 'D368_NATIVE_ROLE')
    stages = {'fast':'pg-fast', 'wait':'pg-wait', 'state':'stopped-state', 'control':'pg-control-execute',
              'controlCreate':'pg-control-create'}
    matches = {key:[] for key in stages}
    for path in (root/c.AREA.parent/'commands'/c.RECOVERY).glob('*/receipt.json'):
        row = json.loads(ex.ordinary(path).read_bytes())
        for key, stage in stages.items():
            if (row['stage'] == 'omq-recovery-' + stage and utc(stop['startedUtc']) <= utc(row['startedAtUtc'])
                    <= utc(row['endedAtUtc']) <= utc(stop['endedUtc'])):
                matches[key].append(row['commandId'])
    require(all(len(v) == 1 for v in matches.values()), 'D368_NATIVE_UNIQUE')
    steps = {k:v[0] for k,v in matches.items()}
    helper = c.raw(root,c.AREA.parent/'commands'/c.RECOVERY/steps['controlCreate']/'stdout.txt').decode().strip()
    require(re.fullmatch('[0-9a-f]{64}',helper), 'D368_CONTROL_HELPER')
    helpers = []
    for path in (root/REC).glob('helper-*.json'):
        row = json.loads(ex.ordinary(path).read_bytes())
        if row.get('id') == helper and row['stage'] == 'pg-control':
            helpers.append(row['attemptId'])
    require(len(helpers) == 1, 'D368_CONTROL_REGISTRY')
    steps['controlHelper'] = helpers[0]
    return steps


def reopen_native(root, row, prior, archive):
    start = raw_json(root,REC/('start-'+ident(row['pgStartAttempt'])+'.json'),archive)
    stop = raw_json(root,REC/('stop-'+ident(row['pgStopAttempt'])+'.json'),archive)
    require((start['attempt'], start['stage'], start['role'], start['id'], start['status']) ==
            (row['pgStartAttempt'], RUN, 'platform-pg', PG, 'RUNNING') and
            (stop['role'],stop['group'],stop['id'],stop['status'],stop['operation'],stop['controlState']) ==
            ('platform-pg','replacement',PG,'CLEAN_STOP',row['operation'],'shut down') and stop['shutdownLogMarker'],
            'D368_NATIVE_SCOPE')
    start_cmd, out, _ = c.lifecycle_command(root, ident(row['pgStartCommand']), 'platform-pg', PG, 'data-start', archive)
    require(out.strip().decode() == PG, 'D368_START')
    before_start = inventory(root, start['resourceAttempt'], [], archive)
    after_start = inventory(root, start['post'], ['platform-pg'], archive)
    before_stop = inventory(root, stop['resourceAttempt'], ['platform-pg'], archive)
    require(utc(before_start['endedUtc']) <= utc(start_cmd['startedAtUtc']) <= utc(start_cmd['endedAtUtc']) <=
            utc(after_start['startedUtc']) <= utc(after_start['endedUtc']) <= utc(before_stop['startedUtc']) <=
            utc(before_stop['endedUtc']) <= utc(stop['startedUtc']), 'D368_ATTEMPT_ORDER')
    refs = row['pgNative']
    helper = raw_json(root, REC / ('helper-' + ident(refs['controlHelper']) + '.json'), archive)
    require((helper['taskId'],helper['runId'],helper['attemptId'],helper['volume'],helper['stage'],helper['status'],
             helper['write'],helper['after'],helper['removed']) ==
            (TASK,c.RECOVERY,refs['controlHelper'],'ontology-g4-omq-restore-01_platform-data','pg-control','PASS',False,
             ['exited','0','false'],True) and re.fullmatch('[a-f0-9]{64}',helper['id']), 'D368_CONTROL_MOUNT')
    specs = [('fast','pg-fast',PG_FAST,45), ('wait','pg-wait',['wait',PG],45),
             ('state','stopped-state',['inspect','-f','{{json .State}}',PG],45),
             ('control','pg-control-execute',['start','-a',helper['id']],45)]
    outputs = {}
    end = utc(stop['startedUtc'])
    for key, stage, args, timeout in specs:
        argv = [*DOCKER,*args]
        receipt, out, _ = c.command(root,ident(refs[key]),c.RECOVERY,argv,'omq-recovery-'+stage,ex.sha(ex.encoded(argv)),timeout,archive)
        require(end <= utc(receipt['startedAtUtc']) <= utc(receipt['endedAtUtc']) <= utc(stop['endedUtc']), 'D368_NATIVE_ORDER')
        end = utc(receipt['endedAtUtc'])
        outputs[key] = out.strip()
    state = json.loads(outputs['state'])
    require(outputs['wait'] == b'0' and outputs['control'] == b'shut down' and
            all(state[k] == v for k,v in stop['after'].items()) and
            (state['Status'],state['Pid'],state['ExitCode'],state['OOMKilled'],state['Error']) == ('exited',0,0,False,'') and
            utc(prior['data']['platform-pg']['after']['FinishedAt']) < utc(start_cmd['startedAtUtc']) <=
            utc(state['StartedAt']) <= utc(start_cmd['endedAtUtc']) <= utc(stop['startedUtc']) <= utc(state['FinishedAt']),
            'D368_PG_GENERATION')
    made = record(root,c.RECOVERY,refs['controlCreate'],archive)
    require(made['stage'] == 'omq-recovery-pg-control-create' and made['exitCode'] == 0 and
            utc(state['FinishedAt']) <= utc(made['startedAtUtc']) <= utc(made['endedAtUtc']) < end, 'D368_CONTROL_CREATE')
    for stream in ('stdout','stderr'):
        raw = c.raw(root,c.AREA.parent/'commands'/c.RECOVERY/refs['controlCreate']/(stream+'.txt'),archive)
        require(ex.sha(raw) == made[stream]['sha256'] and len(raw) == made[stream]['sizeBytes']
                and (stream != 'stdout' or raw.strip().decode() == helper['id']), 'D368_CONTROL_CREATE_STREAM')
    return state, start_cmd, stop


def inventory(root, ref, running, archive):
    admission = raw_json(root,c.AREA/('source-admission-'+ident(ref)+'.json'),archive)
    require((admission['attempt'],admission['taskId'],admission['runId'],admission['phase'],admission['status'],
             admission['expectedRunningRoles']) == (ref,TASK,RUN,RUN,'FORMAL_RESOURCE_READY',running), 'D368_ADMISSION')
    raw = c.raw(root,c.AREA.parent/'resource-inventory.json',archive)
    require(ex.sha(raw) == INVENTORY_SHA, 'D368_INVENTORY_BASE')
    expected = json.loads(raw)['retained']
    require(len(expected) == 20, 'D368_PROTECTED_COUNT')
    by_stage = {name:[item for item in admission['commands'] if item['stage']==name] for name in ('old-resources','all-running')}
    for name, items in by_stage.items():
        require(len(items)==1, 'D368_INVENTORY_STAGE')
        ref = items[0]['commandId']
        args = (['inspect','-f',KEEP_FORMAT,*[line.split('|')[0] for line in expected]] if name=='old-resources'
                else ['ps','-q','--no-trunc'])
        receipt = record(root,RUN,ref,archive)
        _, out, _ = c.command(root,ref,RUN,[*DOCKER,*args],'oracle-admission-'+name,receipt['inputFingerprint'],18,archive)
        lines=out.decode().strip().splitlines()
        require(lines==expected if name=='old-resources' else set(lines)==seal.BASELINE_RUNNING | ({PG} if running else set()),
                'D368_PROTECTED_DRIFT')
    return admission


def post_state(root,row,prior,pg_state,stop,archive):
    formal=w.last_close(root,archive,digest=seal.FORMAL)
    args=state_args(prior,formal)
    for key,argv in args.items():
        cmd,out,_=c.command(root,ident(row['postState'][key]),RUN,[*DOCKER,*argv],'d368-post-'+key,ex.sha(ex.encoded(argv)),30,archive)
        require(utc(stop['endedUtc']) <= utc(cmd['startedAtUtc']), 'D368_FINAL_ORDER')
        if key=='absent':
            require(not out.strip(), 'D368_FINAL_APIS')
            continue
        lines = [line.split('|') for line in out.decode().strip().splitlines()]
        for role,fields in zip(sorted(prior['data']),lines,strict=True):
            old=prior['data'][role]
            start,end=(pg_state['StartedAt'],pg_state['FinishedAt']) if role=='platform-pg' else (old['startedAt'],old['after']['FinishedAt'])
            require(fields==[old['id'],'exited','0',start,end,'false',''],'D368_FINAL_STATE_'+role)


def observations(root, phase, refs, archive):
    import workflow_oracle_access_maintenance as old
    row=old.ROW_SQL.replace(old.QUERY,seal.QUERY).replace('''\x27owner\x27,q."LeaseOwner"''',
        '''\x27ownerSha256\x27,encode(sha256(convert_to(q."LeaseOwner",\x27UTF8\x27)),\x27hex\x27)''')
    receipts=f"""SELECT json_array_length(convert_from("BindingBytes",'UTF8')::json->'receipts') FROM semantic_query."Queries" WHERE "Id"='{seal.QUERY}';"""
    argv=[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    values={}
    commands={}
    for label,sql in [('row',row),('audit',old.AUDIT_SQL.replace(old.QUERY,seal.QUERY)),('receipts',receipts)]:
        payload=b'BEGIN READ ONLY;\n'+sql.encode()+b'\nCOMMIT;'
        cmd,out,_=c.command(root,ident(refs[label]),RUN,argv,'omq-pg-d368-'+phase+'-'+label,ex.sha(payload),15,archive)
        values[label]=json.loads(out)
        commands[label]=cmd
    return values,commands


def verified_seal(root, row, key, archive):
    label='cold' if key=='beforeSeal' else 'pg'
    name='d368-seal-'+label+'-'+row['operation']+'.json'
    require(row[key]==name,'D368_SEAL_NAME')
    seen=raw_json(root,AREA/name,archive)
    require(seen['kind']=='DEDICATED_ORACLE_GENERATION_TERMINATED' and seen['queryId']==seal.QUERY and
            seen['generationSha256']==seal.digest(seen['generation'])=='a617d1e838631e9f16b5e9bc65aa97842c3a85cfc7c9991137262a537881c3d0' and
            seen['sealSha256']==seal.digest(seen['seal'])=='1d39291bc79d057dc310bdad98049442305aff73b236e4a004b4829d3890edb2' and
            seen['originalsSha256']==seal.digest(seen['originals']) and seen['historical']['row']==seal.FROZEN_ROW and
            seen['live']['pgStartCommand']==(None if key=='beforeSeal' else row['pgStartCommand']) and seen['live']['matchingDrivers']==0,
            'D368_SEAL_BINDING')
    return seen


def reopen_cas(root,row,pg_seal,pg_state,archive):
    name='d368-recovery-'+row['operation']+'.json'
    require(row['cas']==name, 'D368_CAS_NAME')
    receipt=raw_json(root,AREA/name,archive)
    proof_path=AREA/('d368-proof-'+row['operation']+'.json')
    require(receipt['proofFile']==str(proof_path), 'D368_PROOF_PATH')
    proof_row=raw_json(root,proof_path,archive)
    proof=proof_row['proof']
    require((receipt['taskId'],receipt['runId'],receipt['batch'],receipt['status'],receipt['exitCode'],receipt['helperReleased'])==
            (TASK,RUN,w.BATCH,'TASK_LEVEL_RECOVERY',0,True) and
            receipt['operationId']==proof['operationId'] and receipt['attemptId']==proof['attemptId'] and
            proof['queryId']==seal.QUERY and proof['sourceContainerId']==seal.SOURCE and proof['platformContainerId']==PG and
            proof['failureAuditId']==seal.AUDIT_ID and proof['failureAuditSha256']==seal.AUDIT_SHA and
            proof['sealSha256']==pg_seal['sealSha256'] and proof['terminationProofSha256']==pg_seal['generationSha256'] and
            receipt['proofSha256']==proof_row['proofSha256']==ex.sha(ex.encoded(proof)), 'D368_CAS_PROOF')
    helper=receipt['helperId']
    require(re.fullmatch('[a-f0-9]{64}',helper), 'D368_CAS_HELPER')
    cmd,out,_=c.command(root,ident(receipt['actualCommandId']),RUN,[*DOCKER,'start','-a','-i',helper],
                         's23-access-recovery-cas',receipt['proofSha256'],32,archive)
    envelope=json.loads(out)
    require(envelope==receipt['commitEnvelope'] and envelope['status']=='TASK_LEVEL_RECOVERY' and
            envelope['operationId']==proof['operationId'] and utc(proof['verifiedUtc']) <= utc(cmd['startedAtUtc']) <
            utc(cmd['endedAtUtc']) < utc(proof['validUntilUtc']), 'D368_CAS_COMMIT')
    before,pre=observations(root,'before',receipt['before'],archive)
    after,post=observations(root,'after',receipt['after'],archive)
    require(before['row']==seal.FROZEN_ROW and after['row']==dict(seal.FROZEN_ROW,ownerSha256=None,leaseUntilUtc=None) and
            before['receipts']==after['receipts']==0 and len(before['audit'])==1 and len(after['audit'])==2 and
            before['audit'][0]['id']==seal.AUDIT_ID and before['audit'][0]['sha256']==seal.AUDIT_SHA and
            before['audit'][0] in after['audit'], 'D368_CAS_POST')
    added,=[a for a in after['audit'] if a!=before['audit'][0]]
    require([added[k] for k in ('action','outcome','actor','trace','correlation','organization','sites')]==[
            'data.query.cleanup.recover','allowed',proof['operatorId'],proof['operationId'],proof['attemptId'],'org-demo',['site-a']],
            'D368_CAS_AUDIT')
    require(all(utc(pg_state['StartedAt']) < utc(v['startedAtUtc']) <= utc(v['endedAtUtc']) <= utc(cmd['startedAtUtc']) for v in pre.values())
            and all(utc(cmd['endedAtUtc']) <= utc(v['startedAtUtc']) <= utc(v['endedAtUtc']) < utc(pg_state['FinishedAt']) for v in post.values()),
            'D368_CAS_OBSERVATION_ORDER')
    for field,stage,args,expected in [('removeCommandId','recovery-remove',['rm',helper],helper),
                                       ('absentCommandId','recovery-absent',['ps','-aq','--no-trunc','--filter','id='+helper],'')]:
        cid=ident(receipt[field])
        log=record(root,RUN,cid,archive)
        r,out,_=c.command(root,cid,RUN,[*DOCKER,*args],'s23-access-'+stage,log['inputFingerprint'],30,archive)
        require(out.decode().strip()==expected and utc(cmd['endedAtUtc']) <= utc(r['startedAtUtc']), 'D368_CAS_HELPER_CLOSE')
    return receipt['actualCommandId']


def reopen(root,entry,prior,archive=None):
    """按维护后继的精确摘要重开，在此前正式宿主到下一正式宿主之间追加一个 PG 停机边。"""
    local=SimpleNamespace(paths={},examined={})
    operation=ident(entry['operation'])
    path=AREA/('d368-pg-only-'+operation+'.json')
    raw=c.raw(root,path,local)
    require(len(raw)==entry['sizeBytes'] and ex.sha(raw)==entry['sha256'],'WINDOW_LAST_CLOSE_ORIGINAL')
    row=json.loads(raw)
    require((row['taskId'],row['runId'],row['batch'],row['planId'],row['operation'],row['priorCloseSha256'],row['queryId']) ==
            (TASK,RUN,w.BATCH,PLAN,operation,PREVIOUS,seal.QUERY) and
            entry['previousSha256']==PREVIOUS and row['status'] in ('TASK_LEVEL_RECOVERY','BLOCKED') and
            row['status']==entry['status'], 'D368_CLOSE_SCOPE')
    win=raw_json(root,AREA/('window-'+ident(row['windowId'])+'.json'),local)
    require((win['state'],win['id'],win['taskId'],win['runId'],win['batch'],win['plan'],win['priorCloseSha256'],win['coldAttempt']) ==
            ('CLOSED',row['windowId'],TASK,RUN,w.BATCH,PLAN,PREVIOUS,row['cold']) and win['ceiling']==w.choose(win['openingBytes']),
            'D368_WINDOW')
    cold=inventory(root,row['cold'],[],local)
    post=inventory(root,row['post'],[],local)
    state,start,stop=reopen_native(root,row,prior,local)
    require(utc(cold['endedUtc']) <= utc(start['startedAtUtc']) < utc(state['FinishedAt']) <= utc(post['startedUtc']),
            'D368_ADMISSION_ORDER')
    post_state(root,row,prior,state,stop,local)
    cold_seal=verified_seal(root,row,'beforeSeal',local)
    require(utc(cold_seal['verifiedUtc']) <= utc(start['startedAtUtc']), 'D368_COLD_SEAL_ORDER')
    if row.get('pgSeal') is not None:
        pg_seal=verified_seal(root,row,'pgSeal',local)
        require(utc(state['StartedAt']) <= utc(pg_seal['verifiedUtc']) <= utc(stop['startedUtc']) and
                pg_seal['live']['states'][PG]['startedAt']==state['StartedAt'], 'D368_PG_SEAL_ORDER')
    if row['status']=='TASK_LEVEL_RECOVERY':
        require(row.get('pgSeal') is not None, 'D368_CAS_WITHOUT_SEAL')
        reopen_cas(root,row,pg_seal,state,local)
    elif row.get('cas'):
        require(row['cas']=='d368-recovery-'+operation+'.json', 'D368_FAILED_CAS_NAME')
        # 失败或未知回执只留作证据，永不取得后继产品窗准入。
        c.raw(root,AREA/row['cas'],local)
    members={p:local.examined[k] for k,p in local.paths.items()}
    index=ex.sha(ex.encoded(members))
    if 'memberIndexSha256' in entry:
        require(len(members)==entry['memberCount'] and index==entry['memberIndexSha256'], 'D368_CLOSE_MEMBERS')
    if archive is not None:
        for name,path in local.paths.items():
            require(archive.examined.get(name,local.examined[name]) == local.examined[name],'D368_ARCHIVE_DRIFT')
            archive.paths[name]=path
            archive.examined[name]=local.examined[name]
    normalized=dict(prior)
    normalized['maintenance']=[*prior.get('maintenance',[]),dict(operation=operation,finishedAt={'platform-pg':state['FinishedAt']})]
    return normalized,len(members),index


def publish_d368_pg_close(operation):
    """唯一 Master 在退出窗口后登记；同一组原件幂等，原件不全时保留关闭文件。"""
    from workflow_oracle_mapping_platform import save
    root=w.ROOT
    op=ident(operation)
    require(not w.ACTIVE.get() and os.environ.get('OMQ_PRODUCT_RUN')==RUN, 'D368_PUBLISH_SCOPE')
    registry_path=ex.ordinary(root/'scripts/maintenance/workflow-oracle-runtime-close-registry.json')
    initial=registry_path.read_bytes()
    registry=json.loads(initial)
    path=AREA/('d368-pg-only-'+op+'.json')
    data=c.raw(root,path)
    row=json.loads(data)
    digest=ex.sha(data)
    if registry['currentSha256']==digest:
        w.last_close(root,digest=digest)
        return w.close_registration(digest)
    require(registry['currentSha256']==PREVIOUS and w.close_registration()['kind']=='MAPPING_RESTORE', 'D368_PUBLISH_PREVIOUS')
    entry=dict(kind=KIND,operation=op,queryId=seal.QUERY,previousSha256=PREVIOUS,sha256=digest,sizeBytes=len(data),status=row['status'])
    _,count,index=reopen(root,entry,w.last_close(root,digest=PREVIOUS))
    entry.update(memberCount=count,memberIndexSha256=index)
    require(registry_path.read_bytes()==initial, 'D368_PUBLISH_CHANGED')
    registry['generations'].append(entry)
    registry['currentSha256']=digest
    save(registry_path,registry,True)
    w.last_close(root,digest=digest)
    return entry
