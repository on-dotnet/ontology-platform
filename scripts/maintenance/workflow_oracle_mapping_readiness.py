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
    probe=qualify(report);item=report['oracleReadiness'];body=b'BEGIN READ ONLY;\n'+snapshot_sql(probe['probeId'])+b'\nCOMMIT;'
    args=['docker','--context','desktop-linux','exec','-i','--user','postgres',host['services']['platform-pg']['containerId'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    command,out,err=archive.command(item['snapshot']['commandId'],args,'omq-pg-s23-oracle-readiness',ex.sha(body),None,origin)
    window=next(w for w in report['oracleWindows'] if w['name']=='oracle-current-api-readiness')
    require(command['classification']=='SUCCESS' and command['exitCode']==0 and command['deadlineSeconds']==15 and not err and json.loads(out)==item['snapshot']['value']
        and utc(probe['completedAtUtc'])<=utc(command['startedAtUtc'])<=utc(command['endedAtUtc'])<=utc(window['finishedAtUtc']),'S23_READINESS_SNAPSHOT_ORIGINAL')
    return dict(status='CURRENT_API_CONNECTION_READY',probeId=probe['probeId'],queryColdStart='NOT_QUALIFIED',sourceBusinessReads=0)
