"""本批 Oracle 双表的精确授权与可逆合成夹具；只经原平台入口调用。"""
import datetime as dt
import json
import re
import uuid

import workflow_execution as ex
import workflow_oracle_mapping_platform as p
from workflow_oracle_mapping_resources import TASK, require
from workflow_oracle_mapping_identity_recovery import ROSTER

BATCH = 's2-s3-01'
RUN = 'product-resume-01'
COLUMNS = ['ROW_ID','JOIN_KEY','VAL','ORG_ID','SITE_ID','EXT_ID','LABEL','FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS']
OBJECTS = ['PRODUCTION/OMQ_ENTITY','CaseOwner/OmqTarget']
FIELDS = [obj+'/'+str(i)+'/'+name for obj in OBJECTS for i,name in enumerate(COLUMNS,1)]
SCOPED = [('operator','mapping.source.validate'),('auditor','mapping.source.validate'),('activator','mapping.source.validate'),
          ('reader','data.query.execute'),('reader','data.query.result.read'),('reader','data.query.evidence.read')]
WORKFLOW = [('operator',op) for op in ['mapping.read','mapping.edit','mapping.validate','mapping.submit']] + [
    ('auditor',op) for op in ['mapping.read','mapping.review','mapping.approve']] + [('activator',op) for op in ['mapping.read','mapping.activate']]


def scope(state):
    require(p.product_run()==RUN and (state['taskId'],state['runId'])==(TASK,RUN)
            and state['scope']==dict(organizationId='org-demo',siteIds=['site-a']),'S2_SCOPE')
    require(state['subjects']=={k:v[1] for k,v in ROSTER.items()},'S2_SUBJECTS')
    cid=state['connectionId'];require(cid=='a7913bb552eb4cd1a3f6eaf5b93cd619','S2_CONNECTION')
    catalog=state['catalog']
    require(catalog['status']=='READY' and catalog['connectionId']==cid and len(catalog['objects'])==2,'S2_CATALOG')
    for obj in OBJECTS:
        owner,table=obj.split('/')
        matches=[x for x in catalog['objects'] if (x['schema'],x['name'],x['kind'])==(owner,table,'TABLE')]
        require(len(matches)==1 and [(f['ordinal'],f['name']) for f in matches[0]['fields']]==list(enumerate(COLUMNS,1)),'S2_FIELDS')
    return cid


def grant_snapshot_sql(state):
    cid=state["connectionId"]
    subjects=','.join("'"+v[1]+"'" for v in ROSTER.values())
    sql=f'''SELECT json_build_object('clock',extract(epoch from clock_timestamp()),'epoch',
      (SELECT "Revision" FROM governance."MappingAuthorizationEpochs" WHERE "OrganizationId"='org-demo'),
      'rows',(SELECT coalesce(json_agg(g ORDER BY "Id"),'[]') FROM (SELECT * FROM governance."MappingAuthorizationGrants"
       WHERE "OrganizationId"='org-demo' AND "SubjectId" IN ({subjects}) AND ("ConnectionId" IS NULL OR "ConnectionId"='{cid}')) g),
      'audit',(SELECT coalesce(json_agg(a ORDER BY "Resource"),'[]') FROM (SELECT "Resource",count(*) n,count(*) FILTER (WHERE "Id"=md5("Resource")) issued FROM governance.audit_records
       WHERE "Action"='mapping.grant.change' AND "Resource" LIKE 'omq-s23-%' GROUP BY "Resource") a));'''
    return sql.encode()


def grant_rows(state):
    scope(state)
    raw,command=p.read_pg(grant_snapshot_sql(state),'s23-grant-snapshot')
    return {**json.loads(raw),'commandId':command}


def covers(row,state,role,op,scoped=True):
    return (row['SubjectId']==state['subjects'][role] and row['Permission']==op and row['OrganizationId']=='org-demo'
            and row['SiteIds']==['site-a'] and row['ConnectionId']==(state['connectionId'] if scoped else None)
            and row['ObjectRefs']==(OBJECTS if scoped else []) and row['FieldRefs']==(FIELDS if scoped else []))


def ttl(row,clock):
    return dt.datetime.fromisoformat(row['ExpiresAtUtc'].replace('Z','+00:00')).timestamp()-float(clock)


def grants(state,execution_id,issue=False):
    """仅首槽可追加六条组合授权及自然到期的九条原工作流授权；每次按准确ID核闭包。"""
    from workflow_m4_query import grant_transaction
    cid=scope(state)
    require(re.fullmatch('[a-f0-9]{32}',execution_id),'S2_EXECUTION')
    current,cat_command=p.read_pg((f'''SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"='{cid}' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;''').encode(),'s23-current-catalog')
    require(json.loads(current)==state['catalog'],'S2_CATALOG_CURRENT')
    before=grant_rows(state)
    selected=state.get('combinedGrantIds',{})
    if issue and not selected:
        recovered=[]
        for path in (p.AREA.parent/RUN/BATCH).glob('grant-plan-*.json'):
            plan=json.loads(ex.ordinary(path).read_bytes())
            require(plan['taskId']==TASK and plan['runId']==RUN and plan['batch']==BATCH and plan['connectionId']==cid
                    and plan['objects']==OBJECTS and plan['fields']==FIELDS,'S2_GRANT_PLAN_SCOPE')
            items=[item for item in plan['planned'] if item['kind']=='COMBINED']
            if len(items)==6 and all(any(row['Id']==item['id'] for row in before['rows']) for item in items):
                recovered.append({item['role']+':'+item['operation']:item['id'] for item in items})
        require(len(recovered)<=1,'S2_GRANT_RECOVERY_AMBIGUOUS')
        if recovered:selected=recovered[0]
    require(type(selected) is dict and (issue or len(selected)==6),'S2_GRANTS_NOT_REGISTERED')
    issued=[];expected={}
    for role,op in SCOPED:
        require(any(r['SubjectId']==state['subjects'][role] and r['Permission']==op and r['ConnectionId']==cid
                    and r['SiteIds']==['site-a'] and r['ObjectRefs']==OBJECTS[:1] and r['FieldRefs']==FIELDS[:11]
                    for r in before['rows']),'S2_SINGLE_TABLE_HISTORY_MISSING')
    for role,op in SCOPED:
        key=role+':'+op
        ident=selected.get(key)
        row=next((r for r in before['rows'] if r['Id']==ident),None)
        if ident:
            require(row is not None and covers(row,state,role,op) and row['RevokedAtUtc'] is None,'S2_GRANT_PRESTATE')
            require(ttl(row,before['clock'])>=210 or issue and ttl(row,before['clock'])<=0,'S2_GRANT_TTL')
        if row is None or ttl(row,before['clock'])<=0:
            require(issue,'S2_GRANT_EXPIRED')
            ident='omq-s23-'+ex.sha(ex.encoded([BATCH,execution_id,cid,role,op,OBJECTS,FIELDS]))[:32]
            require(not any(r['Id']==ident for r in before['rows']),'S2_GRANT_ID_ALREADY_USED')
            issued.append(dict(id=ident,role=role,operation=op,kind='COMBINED'))
        expected[key]=ident
    workflow=[]
    for role,op in WORKFLOW:
        # 仅在九项空范围历史中选择，不能将单表或双表源授权混入此分支。
        rows=[r for r in before['rows'] if covers(r,state,role,op,False)]
        require(rows,'S2_WORKFLOW_ORIGINAL_MISSING')
        row=max(rows,key=lambda r:r['ExpiresAtUtc'])
        require(row['RevokedAtUtc'] is None,'S2_WORKFLOW_REVOKED')
        if ttl(row,before['clock'])<210:
            require(issue and ttl(row,before['clock'])<=0,'S2_WORKFLOW_TTL')
            ident='omq-s23-'+ex.sha(ex.encoded([BATCH,execution_id,cid,role,op]))[:32]
            require(not any(r['Id']==ident for r in before['rows']),'S2_WORKFLOW_ID_ALREADY_USED')
            issued.append(dict(id=ident,role=role,operation=op,kind='WORKFLOW'))
            workflow.append(ident)
        else:workflow.append(row['Id'])
    command=None
    if issued:
        plan=p.AREA.parent/RUN/BATCH/('grant-plan-'+execution_id+'.json')
        p.save(plan,dict(taskId=TASK,runId=RUN,batch=BATCH,connectionId=cid,objects=OBJECTS,fields=FIELDS,before=before,planned=issued))
        ids_by_pair={(state['subjects'][r['role']],r['operation']):r['id'] for r in issued}
        pairs=[(state['subjects'][role],[r['operation'] for r in issued if r['role']==role]) for role in state['subjects']]
        sql,ids=grant_transaction(state,OBJECTS,FIELDS,pairs,lambda who,permission:ids_by_pair[(who,permission)],RUN)
        count,command=p.pg_command(sql,'s23-append-approved-grants')
        require(count.splitlines()[-1]==str(len(issued)) and set(ids)=={r['id'] for r in issued},'S2_GRANT_APPEND')
    after=grant_rows(state)
    require(all(row in after['rows'] for row in before['rows']),'S2_GRANT_HISTORY')
    chosen=[]
    for role,op in SCOPED:
        ident=expected[role+':'+op]
        rows=[r for r in after['rows'] if r['Id']==ident]
        require(len(rows)==1 and covers(rows[0],state,role,op) and rows[0]['RevokedAtUtc'] is None
                and 210<=ttl(rows[0],after['clock'])<=14400 and any(a['Resource']==ident and a['issued']==1 for a in after['audit']),'S2_GRANT_READBACK')
        chosen+=rows
    require(all(any(r['Id']==ident and r['RevokedAtUtc'] is None and ttl(r,after['clock'])>=210 for r in after['rows']) for ident in workflow),'S2_WORKFLOW_READBACK')
    return dict(taskId=TASK,runId=RUN,batch=BATCH,executionId=execution_id,combinedGrantIds=expected,fieldCount=22,grantCount=6,
                rows=chosen,catalogSnapshot=state['catalog'],workflowIds=workflow,issued=issued,grantCommand=command,catalogCommand=cat_command,beforeCommand=before['commandId'],afterCommand=after['commandId'],
                beforeEpoch=before['epoch'],afterEpoch=after['epoch'],beforeSnapshot=before,afterSnapshot=after,historyPreserved=True,beforeRowsSha256=ex.sha(ex.encoded(before['rows'])),
                afterRowsSha256=ex.sha(ex.encoded(after['rows'])),requiredSeconds=210,remainingSeconds=min(ttl(r,after['clock']) for r in chosen))


def ready(state,actors,execution_id,mode):
    """紧前重核正式目录、当前激活、已登记组合授权、会话和正常源前态。"""
    require(mode in ('s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-queries','s2-oracle-relations','s2-oracle-access',
                     's2-oracle-aba','s2-oracle-connection','s2-oracle-versions','s2-oracle-states','s2-oracle-reopen','s3','ui-s3','ui-s1'),'S2_MODE')
    scope(state)
    result=grants(state,execution_id)
    require([a['subjectId'] for a in actors]==[v[1] for v in ROSTER.values()],'S2_ACTORS')
    result['session']=p.session_preflight(actors,210)
    if mode not in ('s2-oracle-vocabulary','s2-oracle-mapping'):
        active=state.get('mappingCurrentReceipt') or state['mappingReceipt'];mid=active['mappingId']
        require(re.fullmatch('[a-zA-Z0-9-]{1,96}',mid),'S2_MAPPING_ID')
        raw,command=p.read_pg((f'''SELECT to_jsonb(a) FROM connections."MappingActives" a WHERE "MappingId"='{mid}';''').encode(),'s23-current-activation')
        row=json.loads(raw)
        require(row['ActivationId']==active['activationId'] and row['ActivationRevision']==active['activationRevision'],'S2_ACTIVATION_STALE')
        result['activationCommand']=command
    result['fixtureBefore']=None if mode=='s2-oracle-reopen' else p.fixture_state()
    require(result['fixtureBefore'] is None or result['fixtureBefore']['counts']==[1,1],'S2_NORMAL_PRESTATE')
    result['status']='READY'
    return result

TABLES = ['"PRODUCTION"."OMQ_ENTITY"','"CaseOwner"."OmqTarget"']
SOURCE_CASES = ('near','negative','null-parent','null-target','touch','micro-overlap','duplicate-target','multiple-parents','fanout-10','fanout-11','normal-100','sentinel-101','ambiguous')


def source_snapshot():
    """独立写者只投影两表十一列；保留NUMBER词法和六位时间，不经过浮点。"""
    columns="ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,"+','.join("to_char("+c+",'YYYYMMDDHH24MISSFF6')" for c in COLUMNS[7:])
    rows=[];commands=[]
    for table in TABLES:
        raw,command=p.native_fixture_sql('select json_array('+columns+' returning varchar2(500)) from '+table+' order by ROW_ID;','s23-independent-source-snapshot')
        rows.append([json.loads(line,parse_float=str) for line in raw.splitlines() if line.strip()]);commands.append(command)
    require(all(len(group)<=101 for group in rows),'S2_SOURCE_ROW_LIMIT')
    return dict(rows=rows,hashes=[ex.sha(ex.encoded(group)) for group in rows],commandIds=commands)


def source_value(value, ordinal):
    """合成表字面量只由已保存的精确标量生成；日期固定六位、数字禁止浮点。"""
    if value is None:return 'NULL'
    if ordinal<3:
        require(type(value) in (int,str) and re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',str(value)),'S2_SQL_NUMBER')
        return str(value)
    require(type(value) is str and len(value)<=192,'S2_SQL_TEXT')
    if ordinal>=7:
        require(re.fullmatch('[0-9]{20}',value),'S2_SQL_TIME')
        return "to_timestamp('"+value+"','YYYYMMDDHH24MISSFF6')"
    return "'"+value.replace("'","''")+"'"


def row_predicate(row):
    require(type(row) is list and len(row)==11,'S2_SQL_ROW')
    return ' AND '.join(name+(' IS NULL' if value is None else '='+source_value(value,index))
                        for index,(name,value) in enumerate(zip(COLUMNS,row,strict=True)))


def source_transaction(before,after):
    """同事务锁定两张已登记合成表，逐行全值CAS和影响数断言，任一漂移整体回滚。"""
    require(len(before)==len(after)==2 and all(len(group)<=101 for group in (*before,*after)),'S2_TX_ROWS')
    statements=['DECLARE n PLS_INTEGER; BEGIN']
    for table in TABLES:statements.append('LOCK TABLE '+table+' IN EXCLUSIVE MODE NOWAIT;')
    def demand(table,rows):
        statements.append('SELECT COUNT(*) INTO n FROM '+table+'; IF n<>'+str(len(rows))+" THEN raise_application_error(-20001,'S2_COUNT_CONFLICT'); END IF;")
        for row in rows:
            statements.append('SELECT COUNT(*) INTO n FROM '+table+' WHERE '+row_predicate(row)+"; IF n<>1 THEN raise_application_error(-20002,'S2_VALUE_CONFLICT'); END IF;")
    for table,rows in zip(TABLES,before,strict=True):demand(table,rows)
    for table,old,new in zip(TABLES,before,after,strict=True):
        old_by={row[0]:row for row in old};new_by={row[0]:row for row in new}
        require(len(old_by)==len(old) and len(new_by)==len(new),'S2_DUPLICATE_KEY')
        for key,row in old_by.items():
            if key not in new_by:sql='DELETE FROM '+table+' WHERE '+row_predicate(row)+';'
            elif row!=new_by[key]:
                changed=[i for i in range(11) if row[i]!=new_by[key][i]]
                require(set(changed)<={1,7,8},'S2_UPDATE_SCOPE')
                sql='UPDATE '+table+' SET '+','.join(COLUMNS[i]+'='+source_value(new_by[key][i],i) for i in changed)+' WHERE '+row_predicate(row)+';'
            else:continue
            statements.extend([sql,"IF SQL%ROWCOUNT<>1 THEN raise_application_error(-20003,'S2_WRITE_CONFLICT'); END IF;"])
        for key,row in new_by.items():
            if key in old_by:continue
            require(71001<=key<=71100,'S2_INSERT_KEY')
            statements.extend(['INSERT INTO '+table+' ('+','.join(COLUMNS)+') VALUES ('+','.join(source_value(v,i) for i,v in enumerate(row))+');',
                               "IF SQL%ROWCOUNT<>1 THEN raise_application_error(-20004,'S2_INSERT_CONFLICT'); END IF;"])
    for table,rows in zip(TABLES,after,strict=True):demand(table,rows)
    statements+=['COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;','/']
    return '\n'.join(statements)


def expected_case(action,before,token):
    """在真实DML之前按批准字面量算出完整预期后态，恢复不依赖执行后才产生的快照。"""
    rows=json.loads(json.dumps(before))
    if action=='near':rows[1][0][1]='1.01'
    elif action=='negative':rows[0][0][1]=rows[1][0][1]=-1
    elif action=='null-parent':rows[0][0][1]=None
    elif action=='null-target':rows[1][0][1]=None
    elif action in ('touch','micro-overlap'):
        rows[1][0][7]='20260201000000000001' if action=='touch' else '20260201000000000000'
        rows[1][0][8]='20260301000000000001'
    else:
        parent=action in ('multiple-parents','normal-100','sentinel-101','ambiguous')
        side=0 if parent else 1
        count={'normal-100':99,'sentinel-101':100,'fanout-10':9,'fanout-11':10}.get(action,1)
        for index in range(1,count+1):
            row=rows[side][0].copy();row[0]=71000+index
            if action not in ('duplicate-target','ambiguous'):row[5]='s23-'+token[:10]+'-'+str(index)
            if action in ('normal-100','sentinel-101'):row[1]=1000+index
            if action=='ambiguous':row[7:9]=['20260201000000000001','20260301000000000001']
            rows[side].append(row)
    return rows


def source_case(action,token=None):
    """先保存可逆全值计划再DML；中断后可按PREPARED计划辨别未注入/已提交并安全恢复。"""
    require(p.product_run()==RUN and action in (*SOURCE_CASES,'restore'),'S2_SOURCE_CASE')
    area=p.AREA.parent/RUN/BATCH
    if action=='restore':
        require(re.fullmatch('[0-9a-f]{32}',token or ''),'S2_SOURCE_TOKEN')
        record=json.loads(ex.ordinary(area/('source-case-'+token+'.json')).read_bytes())
        require((record['taskId'],record['runId'],record['token'],record['status'])==(TASK,RUN,token,'PREPARED'),'S2_RESTORE_RECORD')
        require(record['sourceId']==p.active_source_record()['containerId'] and record['batch']==BATCH and record['action'] in SOURCE_CASES,'S2_RESTORE_SOURCE')
        original=record['before']['rows']
        baseline=json.loads((p.AREA/'window-05.json').read_bytes())['afterHash']
        require([len(group) for group in original]==[1,1] and [group[0][0] for group in original]==[1,2]
                and [ex.sha(ex.encoded(group[0])) for group in original]==baseline,'S2_RESTORE_BASELINE')
        require(record['expectedRows']==expected_case(record['action'],original,token)
                and record['insertedKeys']==[[row[0] for row in group[1:]] for group in record['expectedRows']]
                and record['sqlSha256']==ex.sha(source_transaction(original,record['expectedRows']).encode()),'S2_RESTORE_PLAN')
        current=source_snapshot()
        require(current['rows'] in (record['before']['rows'],record['expectedRows']),'S2_RESTORE_CONFLICT')
        command=None
        if current['rows']==record['expectedRows']:
            _,command=p.native_fixture_sql(source_transaction(record['expectedRows'],record['before']['rows']),'s23-source-restore')
        after=source_snapshot();require(after['hashes']==record['before']['hashes'],'S2_RESTORE_HASH')
        result=dict(taskId=TASK,runId=RUN,token=token,before=current,commandId=command,after=after,status='RESTORED')
        p.save(area/('source-restore-'+token+'.json'),result)
        return result
    require(token is None,'S2_SOURCE_NEW_TOKEN')
    initial=p.fixture_state();require(initial['counts']==[1,1],'S2_SOURCE_BASELINE')
    before=source_snapshot();require(before['hashes']==initial['hashes'],'S2_SOURCE_CHANGED')
    if action=='sentinel-101':
        require(not any(json.loads(path.read_bytes())['action']=='sentinel-101' for path in area.glob('source-case-*.json')),'S2_SENTINEL_ALREADY_ATTEMPTED')
    token=uuid.uuid4().hex;expected=expected_case(action,before['rows'],token)
    sql=source_transaction(before['rows'],expected)
    record=dict(taskId=TASK,runId=RUN,batch=BATCH,token=token,action=action,before=before,expectedRows=expected,
                insertedKeys=[[row[0] for row in group[1:]] for group in expected],sourceId=p.active_source_record()['containerId'],
                status='PREPARED',sqlSha256=ex.sha(sql.encode()))
    p.save(area/('source-case-'+token+'.json'),record)
    try:
        _,command=p.native_fixture_sql(sql,'s23-source-'+action)
        p.save(area/('source-command-'+token+'.json'),dict(taskId=TASK,runId=RUN,token=token,commandId=command,sqlSha256=record['sqlSha256']))
        after=source_snapshot();require(after['rows']==expected,'S2_SOURCE_AFTER')
        result=dict(**record,commandId=command,after=after)
        p.save(area/('source-injected-'+token+'.json'),result)
        return result
    except Exception:
        # 本次准确token已在DML之前落盘；即使调用者尚未收到返回值也先按全值CAS恢复。
        source_case('restore',token)
        raise


def same_grant(left,right):
    """PG时间JSON可能裁掉微秒尾零；比较真实时刻，其他字段仍逐字严格。"""
    if set(left)!=set(right):return False
    for key in left:
        if key in ('ExpiresAtUtc','RevokedAtUtc') and left[key] is not None and right[key] is not None:
            if dt.datetime.fromisoformat(left[key].replace('Z','+00:00'))!=dt.datetime.fromisoformat(right[key].replace('Z','+00:00')):return False
        elif left[key]!=right[key]:return False
    return True


def permission_sql(ident,current,desired,action,token,audit_id):
    """完整行CAS与原子审计的纯命令构造，消费者逐字复算。"""
    def literal(value):return "'"+value.replace("'","''")+"'"
    def stamp(value):return 'NULL' if value is None else literal(value)+'::timestamptz'
    # 完整比较锁定这一条获准新ID；历史授权和其他人的权限不能进入UPDATE范围。
    fields='ARRAY['+','.join(literal(v) for v in desired['FieldRefs'])+']::text[]'
    sql=f'''BEGIN; SET LOCAL statement_timeout='3s'; SET LOCAL lock_timeout='1s';
      DO $$ DECLARE total int; BEGIN
        UPDATE governance."MappingAuthorizationGrants" g SET "FieldRefs"={fields},"ExpiresAtUtc"={stamp(desired['ExpiresAtUtc'])},"RevokedAtUtc"={stamp(desired['RevokedAtUtc'])}
        WHERE "Id"={literal(ident)} AND to_jsonb(g)={literal(json.dumps(current))}::jsonb;
        GET DIAGNOSTICS total=ROW_COUNT; IF total<>1 THEN RAISE EXCEPTION 's23_permission_conflict'; END IF;
      END $$;
      INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId")
      VALUES ('{audit_id}',now(),'synthetic-query-fixture','mapping.grant.change',{literal(ident)},'allowed','s23-{action}','{token}','org-demo',ARRAY['site-a'],NULL);
      COMMIT; SELECT to_jsonb(g) FROM governance."MappingAuthorizationGrants" g WHERE "Id"={literal(ident)};'''
    return sql


def permission_case(state,action,kind,token=None):
    """新组合grant的单字段反例：完整行CAS、同事务审计、准确恢复；旧15行始终不写。"""
    scope(state)
    require(action in ('revoke','field','expired','short','restore') and kind in ('execute','result','evidence'),'S2_PERMISSION_ACTION')
    operation='data.query.'+{'execute':'execute','result':'result.read','evidence':'evidence.read'}[kind]
    ident=state['combinedGrantIds']['reader:'+operation]
    require(re.fullmatch('omq-s23-[a-f0-9]{32}',ident),'S2_PERMISSION_ID')
    area=p.AREA.parent/RUN/BATCH
    snapshot=grant_rows(state)
    rows=[r for r in snapshot['rows'] if r['Id']==ident];require(len(rows)==1,'S2_PERMISSION_ROW')
    current=rows[0]
    if action=='restore':
        require(re.fullmatch('[a-f0-9]{32}',token or ''),'S2_PERMISSION_TOKEN')
        record=json.loads(ex.ordinary(area/('permission-case-'+token+'.json')).read_bytes())
        require(record['taskId']==TASK and record['runId']==RUN and record['batch']==BATCH and record['id']==ident
                and record['kind']==kind and record['token']==token and covers(record['before'],state,'reader',operation),'S2_PERMISSION_RECORD')
        require(same_grant(current,record['after']) or same_grant(current,record['before']),'S2_PERMISSION_RESTORE_CONFLICT')
        if same_grant(current,record['before']):
            result=dict(taskId=TASK,runId=RUN,token=token,id=ident,kind=kind,action=action,commandId=None,before=current,after=current,beforeSnapshot=snapshot,afterSnapshot=snapshot)
            p.save(area/('permission-restore-'+token+'.json'),result)
            return result
        desired=record['before']
    else:
        require(token is None and covers(current,state,'reader',operation) and current['RevokedAtUtc'] is None
                and ttl(current,snapshot['clock'])>=210,'S2_PERMISSION_PRESTATE')
        token=uuid.uuid4().hex;desired=dict(current)
        stamp=dt.datetime.fromtimestamp(float(snapshot['clock']),dt.timezone.utc)
        if action=='revoke':desired['RevokedAtUtc']=stamp.isoformat(timespec='microseconds')
        elif action=='field':desired['FieldRefs']=FIELDS[:-1]
        elif action=='expired':desired['ExpiresAtUtc']=(stamp+dt.timedelta(seconds=5)).isoformat(timespec='microseconds')
        else:desired['ExpiresAtUtc']=(stamp+dt.timedelta(seconds=30)).isoformat(timespec='microseconds')
        record=dict(taskId=TASK,runId=RUN,batch=BATCH,token=token,id=ident,kind=kind,action=action,before=current,after=desired,beforeEpoch=snapshot['epoch'])
        p.save(area/('permission-case-'+token+'.json'),record)
    sql=permission_sql(ident,current,desired,action,token,uuid.uuid4().hex)
    try:
        raw,command=p.pg_command(sql.encode(),'s23-permission-'+action);after=json.loads(raw.splitlines()[-1])
        require(same_grant(after,desired),'S2_PERMISSION_READBACK')
        result=dict(taskId=TASK,runId=RUN,token=token,id=ident,kind=kind,action=action,commandId=command,before=current,after=after,sql=sql,beforeSnapshot=snapshot,afterSnapshot=grant_rows(state))
        p.save(area/('permission-'+action+'-'+token+'.json'),result)
        return result
    except Exception:
        if action!='restore':permission_case(state,'restore',kind,token)
        raise


def await_expiry(state,token):
    """独立平台时钟观察新反例grant自然到期，不篡改过期时刻或启动业务读取。"""
    import time
    scope(state)
    require(re.fullmatch('[a-f0-9]{32}',token),'S2_EXPIRY_TOKEN')
    area=p.AREA.parent/RUN/BATCH
    record=json.loads(ex.ordinary(area/('permission-expired-'+token+'.json')).read_bytes())
    require(record['taskId']==TASK and record['runId']==RUN and record['action']=='expired' and record['kind']=='execute'
        and record['id']==state['combinedGrantIds']['reader:data.query.execute'],'S2_EXPIRY_OWNER')
    before=record['afterSnapshot'];require(ttl(record['after'],before['clock'])>0,'S2_EXPIRY_MUST_START_LIVE')
    stop=time.monotonic()+6;observations=[]
    while time.monotonic()<stop:
        current=grant_rows(state);observations.append(current)
        row=next(r for r in current['rows'] if r['Id']==record['id'])
        require(same_grant(row,record['after']) and current['epoch']==before['epoch'],'S2_EXPIRY_UNCHANGED')
        if ttl(row,current['clock'])<=0:
            result=dict(taskId=TASK,runId=RUN,token=token,id=record['id'],before=before,observations=observations,status='NATURALLY_EXPIRED')
            p.save(area/('expiry-'+token+'.json'),result);return result
        time.sleep(min(.25,max(.001,ttl(row,current['clock']))))
    raise ValueError('S2_NATURAL_EXPIRY_NOT_OBSERVED')


def runtime_invocation(cid,nonce,case):
    require(re.fullmatch('[a-f0-9]{64}',cid) and re.fullmatch('[a-f0-9]{32}',nonce) and case in ('aba','connection'),'S2_RUNTIME_COMMAND')
    directory='/tmp/omq-s23-'+nonce
    method='OracleActivationRevisionRejectsInflightQuery' if case=='aba' else 'OracleConnectionRevisionRejectsInflightQuery'
    runner=(f'set -eu; umask 077; d={directory}; mkdir -m 700 -- "$d"; '
      'trap \'rm -r -- "$d"\' EXIT; export OMQ_RUNTIME_REPORT="$d/CASE-inflight.json"; cd "$d"; '
      'rc=0; dotnet /session-tests/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.METHOD '
      '--minimum-expected-tests 1 --no-ansi --progress off --results-directory "$d/results" || rc=$?; if test -f "$OMQ_RUNTIME_REPORT"; then cat "$OMQ_RUNTIME_REPORT"; echo; fi; exit "$rc"')
    runner=runner.replace('CASE',case).replace('METHOD',method)
    return ['docker','--context','desktop-linux','exec','-i','-e','HOME=/tmp','-e','DOTNET_CLI_HOME=/tmp',
      '-e','G4_QUERY_RUNTIME_TEST='+TASK+':'+RUN,cid,'/bin/sh','-ec',runner]


def runtime_case(case,envelope):
    """在现有副API配额内执行受控在途验证；凭证仅经stdin，原件由正式消费者重开。"""
    from workflow_oracle_mapping_resume import AREA,host_binding,current_session_snapshot,load
    from workflow_m2_evidence import mtp
    from workflow_m4_query_evidence import demand_aba_original
    require(p.product_run()==RUN and case in ('aba','connection'),'S2_RUNTIME_SCOPE')
    require(set(envelope)==({'queryId','proposalId','roles'} if case=='aba' else {'queryId','roles'}) and re.fullmatch('query-[a-f0-9]{32}',envelope['queryId'])
            and (case!='aba' or re.fullmatch('proposal-[a-f0-9]{32}',envelope['proposalId'])),'S2_RUNTIME_INPUT')
    require([r['role'] for r in envelope['roles']]==['A','B','C','Q']
            and [r['subjectId'] for r in envelope['roles']]==[v[1] for v in ROSTER.values()],'S2_RUNTIME_SUBJECTS')
    host=host_binding();binding=current_session_snapshot(load(AREA/'formal-api-inputs.json'))['inputs']
    nonce=uuid.uuid4().hex;args=runtime_invocation(host['services']['api-secondary']['containerId'],nonce,case)
    result=ex.run(args,p.ROOT,task=TASK,run_id=RUN,stage='query-real-'+case+'-inflight-runtime',stdin=ex.encoded(envelope),
                  input_key=ex.sha(ex.encoded(binding)),parent_id=host['commandId'],timeout=25)
    passed=mtp(result.stdout+result.stderr,1) if result.returncode==0 else 0
    summary=dict(taskId=TASK,runId=RUN,case=case,nonce=nonce,commandId=result.receipt['commandId'],host=host,input=binding,exitCode=result.returncode,passed=passed)
    p.save(AREA/BATCH/('runtime-'+case+'-'+result.receipt['commandId']+'.json'),summary)
    require(result.returncode==0 and passed==1,'S2_RUNTIME_FAILED_'+result.receipt['commandId'])
    if case=='aba':summary['original']=demand_aba_original(result.stdout,'query-real-aba-inflight-runtime',TASK,RUN)
    else:
        from workflow_oracle_mapping_s2_contract import demand_connection_original
        summary['original']=demand_connection_original(result.stdout)
    return summary


def source_acl():
    sql="SELECT json_array(OWNER,TABLE_NAME,PRIVILEGE,GRANTABLE) FROM DBA_TAB_PRIVS WHERE GRANTEE='FIXTURE_READER' AND (OWNER,TABLE_NAME) IN (('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget')) ORDER BY OWNER,TABLE_NAME,PRIVILEGE;"
    raw,command=p.native_fixture_sql(sql,'s23-source-acl')
    return dict(rows=[json.loads(line) for line in raw.splitlines() if line.strip()],commandId=command,sourceId=p.active_source_record()['containerId'])


def access_case(action,token=None):
    """只撤回并恢复原目标表的直接READ；不新增owner、对象、源角色或写权限。"""
    require(p.product_run()==RUN and action in ('revoke-read','restore-read'),'S2_SOURCE_ACCESS')
    area=p.AREA.parent/RUN/BATCH
    healthy=[['CaseOwner','OmqTarget','READ','NO'],['PRODUCTION','OMQ_ENTITY','READ','NO']]
    reduced=healthy[1:]
    before=source_acl()
    if action=='restore-read':
        require(re.fullmatch('[a-f0-9]{32}',token or ''),'S2_ACL_TOKEN')
        record=json.loads(ex.ordinary(area/('acl-case-'+token+'.json')).read_bytes())
        require((record['taskId'],record['runId'],record['token'],record['before']['sourceId'])==(TASK,RUN,token,before['sourceId'])
                and record['before']['rows']==healthy and before['rows'] in (healthy,reduced),'S2_ACL_RESTORE_PRESTATE')
        command=None
        if before['rows']==reduced:
            _,command=p.native_fixture_sql('GRANT READ ON "CaseOwner"."OmqTarget" TO FIXTURE_READER;','s23-restore-read')
        after=source_acl();require(after['rows']==healthy,'S2_ACL_RESTORE')
        result=dict(token=token,before=before,after=after,commandId=command)
        p.save(area/('acl-restored-'+token+'.json'),result);return result
    require(token is None and before['rows']==healthy,'S2_ACL_HEALTHY')
    token=uuid.uuid4().hex;p.save(area/('acl-case-'+token+'.json'),dict(taskId=TASK,runId=RUN,batch=BATCH,token=token,before=before))
    try:
        _,command=p.native_fixture_sql('REVOKE READ ON "CaseOwner"."OmqTarget" FROM FIXTURE_READER;','s23-revoke-read')
        after=source_acl();require(after['rows']==reduced,'S2_ACL_REVOKED')
        return dict(token=token,before=before,after=after,commandId=command)
    except Exception:
        access_case('restore-read',token)
        raise
