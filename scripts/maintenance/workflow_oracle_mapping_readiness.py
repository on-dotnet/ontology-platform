"""当前API代次的正式Oracle连接就绪原件；独立于Query一秒与清理250ms资格。"""
import json
import re
import workflow_execution as ex
from workflow_oracle_mapping_resources import require
from workflow_oracle_mapping_identity_recovery import ROSTER

CONNECTION='a7913bb552eb4cd1a3f6eaf5b93cd619'
SCOPE=dict(organizationId='org-demo',siteIds=['site-a'])


def snapshot_sql(probe):
    require(re.fullmatch('[a-f0-9]{32}',probe),'S23_READINESS_PROBE_ID')
    return f'''SELECT json_build_object('probe',(SELECT to_jsonb(p) FROM connections."ConnectionProbes" p WHERE p."Id"='{probe}' AND p."ConnectionId"='{CONNECTION}'),
      'connection',(SELECT json_build_object('Id',c."Id",'Revision',c."Revision",'ConfigHash',c."ConfigHash",'SecretVersion',c."SecretVersion",'State',c."State",'LastProbeId',c."LastProbeId") FROM connections."Connections" c WHERE c."Id"='{CONNECTION}'),
      'commands',(SELECT coalesce(json_agg(c),'[]') FROM connections."ConnectionCommands" c WHERE c."ReceiptJson"::jsonb->>'probeId'='{probe}'),
      'audit',(SELECT coalesce(json_agg(a ORDER BY a."Action"),'[]') FROM (SELECT "Id","Action","Outcome","Actor","Resource","TraceId" FROM governance.audit_records WHERE "Resource"='connection:{CONNECTION}' AND "TraceId"=(SELECT "ReportJson"::jsonb->>'traceId' FROM connections."ConnectionProbes" WHERE "Id"='{probe}') AND "Action" IN ('connection.probe.start','connection.probe.complete')) a));'''.encode()


def snapshot(probe):
    import workflow_oracle_mapping_platform as p
    require(p.product_run()=='product-resume-01','S23_READINESS_RUN')
    raw,command=p.read_pg(snapshot_sql(probe),'s23-oracle-readiness');return dict(commandId=command,value=json.loads(raw))


def qualify(report):
    from workflow_oracle_mapping_evidence import utc
    item=report['oracleReadiness'];parts=item['http'];require(len(parts)==4,'S23_READINESS_HTTP_COUNT')
    data=[];cursor=-1
    for part in parts:
        require(part['status']==200 and ex.sha(part['raw'].encode())==part['sha256'],'S23_READINESS_HTTP_BYTES')
        matches=[i for i,row in enumerate(report['http']) if i>cursor and all(row.get(k)==part[k] for k in ('method','path','status','sha256'))]
        require(matches,'S23_READINESS_HTTP_ORIGINAL');cursor=matches[0];data.append(json.loads(part['raw']))
    before,posted,after,probe=data;path='/api/v1/connections/'+CONNECTION
    require([(p['method'],p['path']) for p in parts]==[('GET',path),('POST',path+'/test'),('GET',path),('GET',path+'/probes/'+probe['probeId'])],'S23_READINESS_ROUTES')
    require(before['id']==after['id']==probe['connectionId']==CONNECTION and before['scope']==probe['scope']==SCOPE
        and before['state']=='ACTIVE' and before['secretConfigured'] is True and before['config']['type']=='ORACLE','S23_READINESS_CONNECTION')
    require({k:v for k,v in before.items() if k not in ('lastProbeId','probeFresh')}=={k:v for k,v in after.items() if k not in ('lastProbeId','probeFresh')}
        and parts[0]['etag']==parts[1]['etag']==parts[2]['etag']==f'"{before["configRevision"]}-{probe["configHash"]}"' and parts[3]['etag']=='','S23_READINESS_NO_VERSION_CHANGE')
    require(posted==probe and probe['probeId']!=before['lastProbeId'] and after['lastProbeId']==probe['probeId'] and after['probeFresh'] is True
        and probe['stale'] is False and probe['status']=='TEST_OK' and probe['secretVersion']==before['secretVersion'],'S23_READINESS_CURRENT_PROBE')
    require(item['actor']==ROSTER['operator'][1] and item['api']==report['inputBinding']['api']['services']['api'],'S23_READINESS_API_ACTOR')
    stages=probe['stages'];require([s['name'] for s in stages]==['NETWORK','TLS','AUTH','READ_ONLY','METADATA'] and
        all(s['status']=='PASS' and s['diagnosticCode'] is None and type(s['durationMs']) is int and 0<=s['durationMs']<=10000 for s in stages)
        and [s['durationMs'] for s in stages]==sorted(s['durationMs'] for s in stages),'S23_READINESS_FIVE_STAGES')
    windows=[w for w in report['oracleWindows'] if w['name']=='oracle-current-api-readiness'];require(len(windows)==1,'S23_READINESS_WINDOW')
    window=windows[0];require(window['expectedReads']==0 and utc(window['startedAtUtc'])<=utc(probe['startedAtUtc'])<utc(probe['completedAtUtc'])<=utc(window['finishedAtUtc'])<utc(probe['expiresAtUtc']),'S23_READINESS_TIME')
    observed=item['snapshot']['value'];db=observed['probe'];connection=observed['connection'];commands=observed['commands'];audits=observed['audit']
    require(json.loads(db['ReportJson'])==probe and db['Owner']==item['actor'] and db['ConnectionId']==CONNECTION and db['OrganizationId']=='org-demo'
        and db['SiteIds']==['site-a'] and db['Revision']==before['configRevision'] and db['ConfigHash']==probe['configHash'] and db['SecretVersion']==probe['secretVersion'],'S23_READINESS_PERSISTED_PROBE')
    require(connection==dict(Id=CONNECTION,Revision=before['configRevision'],ConfigHash=probe['configHash'],SecretVersion=before['secretVersion'],State='ACTIVE',LastProbeId=probe['probeId']),'S23_READINESS_PERSISTED_CONNECTION')
    require(len(commands)==1 and commands[0]['Id']==db['CommandKey'] and commands[0]['Etag']==parts[0]['etag'] and json.loads(commands[0]['ScopeJson'])==json.loads(commands[0]['ResultScopeJson'])==SCOPE and commands[0]['StatusCode']==200 and commands[0]['ErrorCode'] is None and json.loads(commands[0]['ReceiptJson'])==probe,'S23_READINESS_COMMAND_RECEIPT')
    require(len(audits)==2 and {a['Action'] for a in audits}=={'connection.probe.start','connection.probe.complete'} and all(a['Outcome']=='allowed' and a['Actor']==item['actor'] and a['Resource']=='connection:'+CONNECTION and a['TraceId']==probe['traceId'] for a in audits),'S23_READINESS_AUDITS')
    return probe


def reopen(archive,report,host,origin):
    from workflow_oracle_mapping_evidence import utc
    qualify_catalog(report)
    probe=qualify(report);item=report['oracleReadiness'];body=b'BEGIN READ ONLY;\n'+snapshot_sql(probe['probeId'])+b'\nCOMMIT;'
    args=['docker','--context','desktop-linux','exec','-i','--user','postgres',host['services']['platform-pg']['containerId'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    command,out,err=archive.command(item['snapshot']['commandId'],args,'omq-pg-s23-oracle-readiness',ex.sha(body),None,origin)
    window=next(w for w in report['oracleWindows'] if w['name']=='oracle-current-api-readiness')
    require(command['classification']=='SUCCESS' and command['exitCode']==0 and command['deadlineSeconds']==15 and not err and json.loads(out)==item['snapshot']['value']
        and utc(probe['completedAtUtc'])<=utc(command['startedAtUtc'])<=utc(command['endedAtUtc'])<=utc(window['finishedAtUtc']),'S23_READINESS_SNAPSHOT_ORIGINAL')
    return dict(status='CURRENT_API_CONNECTION_READY',probeId=probe['probeId'],queryColdStart='NOT_QUALIFIED',sourceBusinessReads=0)


def zero_read_window(window):
    require(window['expectedReads']==0 and window['audit']['clientId'] is None and window['audit']['records']==[],
            'S23_CATALOG_READY_SOURCE')


def qualify_seed_catalog(report, original_query, first_post):
    """过期锚点只记录历史状态。核本父窗独立 GET 从当前 reader 恢复的 seed 原字节。"""
    from workflow_oracle_mapping_s2_contract import CAPABILITIES, RELATION
    from workflow_oracle_mapping_evidence import utc
    batch=report['batch']; seed=report['runtimeQuery']; restored=report['seedCatalogReadiness']; reader=ROSTER['reader'][1]
    require(report['mode']==batch['mode']=='s2-oracle-aba' and batch['planId']=='s2-s3-01-runtime-01'
            and re.fullmatch('[0-9a-f]{32}',batch['executionId']) and seed['executionId']==batch['executionId'],
            'S23_CATALOG_SEED_PARENT')
    sid=seed['queryId']; query=seed['query']; digest=seed['resultHash']
    require(re.fullmatch('query-[0-9a-f]{32}',sid) and sid!=original_query and restored['queryId']==sid
            and seed['actor']==restored['actor']==reader and query['capabilityId']==CAPABILITIES[2]
            and query['relationshipIris']==[RELATION] and query['filters']==dict(siteId='site-a',entityExternalId='omq-entity-1')
            and re.fullmatch('[0-9a-f]{64}',seed['sessionHash'])
            and [r['sessionHash'] for r in report['scenarioReady']['session']['observations'] if r['subjectId']==reader]==[seed['sessionHash']],
            'S23_CATALOG_SEED_READER')
    cases=[r for r in report['oracleCases'] if r['name']=='aba-runtime-seed']
    require(len(cases)==1,'S23_CATALOG_SEED_COUNT')
    row=cases[0];raw=restored['raw'].encode()
    require(row['query']==query and row['httpStatus']==200 and row['queryId']==sid and raw==row['raw'].encode()
            and row['bytes']==len(raw) and ex.sha(raw)==row['sha256']==restored['sha256']==digest and json.loads(raw)['status']=='FOUND',
            'S23_CATALOG_SEED_BYTES')
    endpoint='/api/v1/data/semantic-queries';http=report['http']
    posts=[i for i,h in enumerate(http) if h['method']=='POST' and h['path']==endpoint and h.get('queryId')==sid]
    require(posts==[first_post] and first_post<len(http),'S23_CATALOG_SEED_POST')
    post=http[first_post]
    require(post['status']==200 and post['query']==query and post['subjectId']==reader and post['selectionQueryId'] is None
            and post['sha256']==digest,'S23_CATALOG_SEED_POST')
    gets=[i for i,h in enumerate(http) if h['method']=='GET' and h['path']==endpoint+'/'+sid+'/result']
    require(len(gets)==1 and first_post<gets[0] and not any(h['method']=='POST' and h['path']==endpoint for h in http[first_post+1:gets[0]]),
            'S23_CATALOG_SEED_GET')
    response=http[gets[0]]
    require(response['status']==200 and 0<response['elapsedMs']<=5000 and response['subjectId']==reader and response['sha256']==digest,
            'S23_CATALOG_SEED_GET')
    windows=report['oracleWindows']; names=[w['name'] for w in windows]; stages=['oracle-current-catalog-readiness','aba-runtime-seed','oracle-current-seed-catalog-readiness']
    require(all(names.count(n)==1 for n in stages) and names[1:4]==stages and
            all(utc(windows[i]['finishedAtUtc'])<=utc(windows[i+1]['startedAtUtc']) for i in (1,2)), 'S23_CATALOG_SEED_WINDOWS')
    seed_window=windows[2]
    records=seed_window['audit']['records']
    require(seed_window['expectedReads']==2 and seed_window['audit']['clientId'] is None
            and sorted((r['owner'],r['table']) for r in records)==[('CaseOwner','OmqTarget'),('PRODUCTION','OMQ_ENTITY')]
            and all(r['action']=='SELECT' and r['code']==0 for r in records),'S23_CATALOG_SEED_READS')
    zero_read_window(windows[3])
    return dict(status='CURRENT_CATALOG_VERIFIED',queryId=sid,sha256=digest,historicalQueryId=original_query,historicalStatus=410)


def qualify_catalog(report):
    """当前reader在原五秒恢复期限内取得已资格关系结果原字节，同时完整核当前目录。"""
    item=report['catalogReadiness']
    query='query-d293780099754592b3e2a00957e13c8b'
    digest='fcb551ca11b24fb0a1cec8e38f07fb038d95ba774916c0cafdf2b3ad064c3e66'
    raw=item['raw'].encode()
    require(item['queryId']==query and item['actor']==ROSTER['reader'][1] and item['sha256']==ex.sha(raw),'S23_CATALOG_READY_ORIGINAL')
    path='/api/v1/data/semantic-queries/'+query+'/result'
    windows=[w for w in report['oracleWindows'] if w['name']=='oracle-current-catalog-readiness']
    require(len(windows)==1,'S23_CATALOG_READY_WINDOW')
    window=windows[0]
    zero_read_window(window)
    http=report['http']
    # 首次正式执行之后的恢复另按各自场景核验。
    query_start=next((i for i,h in enumerate(http) if h['method']=='POST' and h['path']=='/api/v1/data/semantic-queries'),len(http))
    prefix=http[:query_start]
    probe=report['oracleReadiness']['http'][-1]
    probes=[i for i,h in enumerate(prefix) if all(h[k]==probe[k] for k in ('method','path','status','sha256'))]
    requests=[i for i,h in enumerate(prefix) if h['method']=='GET' and h['path']==path]
    require(len(probes)==len(requests)==1 and probes[0]<requests[0],'S23_CATALOG_READY_ORDER')
    response=prefix[requests[0]]
    if item.get('status')==410:
        require(response['status']==410 and response['subjectId']==item['actor'] and response['sha256']==item['sha256']
                and item['historicalSha256']==digest and response['code']==item['code']==json.loads(raw)['code']=='result_expired'
                and 0<response['elapsedMs']<=5000,'S23_CATALOG_HISTORY_EXPIRED')
        return qualify_seed_catalog(report,query,query_start)
    require(item.get('status',200)==200 and 'seedCatalogReadiness' not in report and len(raw)==5056 and item['sha256']==digest,
            'S23_CATALOG_READY_ORIGINAL')
    require(response['status']==200 and response['sha256']==digest and 0<response['elapsedMs']<=5000,'S23_CATALOG_READY_HTTP')
    return dict(status='CURRENT_CATALOG_VERIFIED',queryId=query,sha256=digest)
