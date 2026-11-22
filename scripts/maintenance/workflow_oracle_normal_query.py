"""普通 HTTP 诊断窗。固定源与 PG 维护后继，认证、实际请求、采集及收口独立计时。"""
import datetime as dt
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import workflow_oracle_access_maintenance as maintenance
import workflow_oracle_mapping_resume as r
import workflow_oracle_runtime_window as w
from doris_keep_drain import COUNTS
from workflow_oracle_mapping_evidence import NODE, DRIVER
from workflow_oracle_mapping_resources import require
from workflow_oracle_mapping_s2 import sample_source_clocks

AREA=r.AREA/w.BATCH
CONNECTION='a7913bb552eb4cd1a3f6eaf5b93cd619'
PG_CLOSE='b4a5acc7e4de1d788e666b44e125b642a338024b7d2000c44a8ace4820d4d430'
DATA=('platform-pg','oracle','keycloak-test','rustfs','fuseki')


def read_pg(sql,label):
    raw,cid=r.platform.read_pg(sql.encode(),'normal-'+label)
    return dict(value=json.loads(raw),commandId=cid)


def query_facts(http):
    """从同一正式请求的成功或失败审计定位 Q；失败 wire 可以没有 Q。"""
    trace,correlation=http['traceId'],http['correlation']
    require(all(re.fullmatch('[a-f0-9]{32}',v or '') for v in (trace,correlation)),'NORMAL_HTTP_TRACE')
    ident=read_pg(f"""SELECT json_agg("Resource") FROM governance.audit_records WHERE "TraceId"='{trace}' AND "CorrelationId"='{correlation}' AND "Action"='data.query.execute';""",'identify')
    value=ident['value']
    require(isinstance(value,list) and len(value)==1 and re.fullmatch('query-[a-f0-9]{32}',value[0]),'NORMAL_UNIQUE_QUERY')
    q=value[0]
    sql=maintenance.ROW_SQL.replace(maintenance.QUERY,q).replace("'owner',q.\"LeaseOwner\"", """'ownerSha256',encode(sha256(convert_to(q."LeaseOwner",'UTF8')),'hex')""")
    row=read_pg(sql,'row')
    audits=read_pg(maintenance.AUDIT_SQL.replace(maintenance.QUERY,q),'audit')
    data=read_pg(f"""SELECT json_build_object('errorCode',"ErrorCode",'receipts',json_array_length(convert_from("BindingBytes",'UTF8')::json->'receipts')) FROM semantic_query."Queries" WHERE "Id"='{q}';""",'receipts')
    require(row['value']['connectionId']==CONNECTION and audits['value'][0]['trace']==trace and audits['value'][0]['correlation']==correlation,'NORMAL_POST_SCOPE')
    return dict(ident=ident,row=row,audit=audits,data=data)


def host_identity(host):
    """将进程内 PID、模块 ID 分别与准确容器和宿主冻结程序集对应。"""
    cid=host['services']['api']['containerId']
    script='for f in /proc/[0-9]*/cmdline; do if grep -zFxq /app/OntologyPlatform.Api.dll "$f" 2>/dev/null; then p=${f%/cmdline}; echo "${p##*/}"; fi; done'
    pid,cmd=r.command('normal-api-pid',['exec',cid,'/bin/sh','-ec',script])
    require(re.fullmatch('[1-9][0-9]*',pid),'NORMAL_SINGLE_HOST_PROCESS')
    dll=r.AREA/'runtime-snapshots'/host['snapshotId']/'OntologyPlatform.Api.dll'
    ps='[System.Reflection.Assembly]::LoadFile($env:OMQ_FROZEN_API_DLL).ManifestModule.ModuleVersionId.ToString()'
    mvid=subprocess.check_output(['pwsh','-NoProfile','-Command',ps],cwd=r.ROOT,env={**os.environ,'OMQ_FROZEN_API_DLL':str(dll)},timeout=10,text=True).strip()
    return dict(module=str(uuid.UUID(mvid)),process=int(pid),container=cid,pidCommand=cmd,dllSha256=r.ex.sha(dll.read_bytes()))


def consume_observation(row):
    """只在实际命令原件、两套宿主证据和 PG/源原件完全对应时给出资格。"""
    http=row['http']
    identity=row['identity']
    key=row['key']
    facts=row['facts']
    db=facts['row']['value']
    audit=facts['audit']['value']
    require(len(audit)==1 and audit[0]['action']=='data.query.execute' and audit[0]['correlation']==http['correlation']
            and audit[0]['trace']==http['traceId'],'NORMAL_COMMAND_AUDIT')
    exported=r.load(AREA/('normal-export-'+identity['container']+'-'+key+'.json'))
    require(exported['status']=='EXPORTED' and exported['exitCode']==0,'NORMAL_EXPORT_MISSING')
    raw=(r.BASE.parent/'commands'/r.PRODUCT/exported['commandId']/'stdout.txt').read_bytes()
    require(len(raw)==exported['sizeBytes'] and r.ex.sha(raw)==exported['sha256'],'NORMAL_EXPORT_BYTES')
    verdict=r.qualify_normal_projection(raw,key,query_id=db['queryId'],trace_id=http['traceId'],correlation=http['correlation'],
            status=http['status'],process=identity['process'],module=identity['module'],audit=row['audit']['records'])
    if http['status']==200:
        require(row['parentExit']==0 and http['queryId']==db['queryId']==row['get']['queryId'] and http['elapsedMs']<=5000
                and http['sha256']==db['resultHash']==row['get']['sha256'] and row['get']['sizeBytes']==db['resultSize']
                and db['resultCiphertextLength']>0 and db['ownerSha256'] is None and db['leaseUntilUtc'] is None
                and facts['data']['value']['receipts']==2 and audit[0]['outcome']=='success'
                and len(row['getWindows'])==1 and row['getWindows'][0]['audit']['records']==[],'NORMAL_HEALTHY_POSTSTATE')
    else:
        require(audit[0]['outcome']=='failure' and db['resultSize']==0 and db['resultHash'] is None and
                facts['data']['value']['receipts']==0,'NORMAL_FAILURE_POSTSTATE')
    return verdict


def run_first():
    """独立一次性普通 Q1，不向旧 ABA、十槽或任何后继发派。"""
    slot='Q1'
    fixed=AREA/('normal-window-'+slot+'.json')
    require(not fixed.exists() and not (AREA/'normal-post-Q1.json').exists() and w.close_registration()['sha256']==PG_CLOSE,'NORMAL_FIRST_ONCE')
    require(w.last_close(r.ROOT,digest=PG_CLOSE)['data']['platform-pg']['after']['Pid']==0,'NORMAL_CLOSED_PG')
    key=uuid.uuid4().hex
    os.environ['OMQ_NORMAL_DIAGNOSTIC_KEY']=key
    os.environ['OMQ_NORMAL_SLOT']=slot
    start=time.monotonic()
    window_seconds=1100
    summary=dict(taskId=r.TASK,runId=r.PRODUCT,slot=slot,key=key,closeSha256=PG_CLOSE,errors=[],stages=[],starts={},closed={})
    output=AREA/('normal-observation-'+key+'.json')
    def save():
        r.platform.save(output,summary,output.exists())
    def step(name,call):
        began=time.monotonic()
        try:return call()
        finally:
            summary['stages'].append(dict(name=name,seconds=time.monotonic()-began))
            save()
    def capture(name,call):
        try:return step(name,call)
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z0-9_a-z-]{1,150}',str(error)) else type(error).__name__
            summary['errors'].append(dict(stage=name,reason=reason));save()
    def drain(label):
        result=read_pg('SELECT json_build_array('+','.join('('+q.strip()+')' for q in COUNTS)+');','drain-'+label)
        summary.setdefault('drain',{})[label]=result
        require(result['value']==[0]*7,'NORMAL_DRAIN')
    with w.open_window() as decision:
        summary.update(windowId=decision['id'],cold=decision['coldAttempt'])
        with fixed.open('x') as stream:json.dump({k:summary[k] for k in ('taskId','runId','slot','key','closeSha256','windowId')},stream)
        save()
        try:
            for role in DATA:
                summary['starts'][role]=step('start-'+role,lambda:r.recovery.start_owned('replacement',role,r.running_roles()))['attempt']
            unknown=read_pg(f"""SELECT count(*) FROM semantic_query."Queries" WHERE "ConnectionId"='{CONNECTION}' AND "LeaseOwner" IS NOT NULL;""",'unknown-owner')
            summary['preUnknown']=unknown
            require(unknown['value']==0,'NORMAL_PENDING_OWNER')
            step('prepare-mounts',r.prepare);step('session-mount',r.bind_session_tests)
            for role in r.APIS:
                step('create-'+role,lambda:r.create(role));summary['starts'][role]=step('start-'+role,lambda:r.start_api(role))
            host=step('bound-host',r.host_binding)
            summary['host']=host;summary['identity']=step('api-identity',lambda:host_identity(host))
            ids=r.manifest()['ids']
            probe='set -eu; umask 077; p="/tmp/omq-probe-$1"; test ! -e "$p"; printf "%s" "$1" > "$p.tmp"; mv "$p.tmp" "$p"; cat "$p"; rm "$p"'
            output_key,probe_cmd=r.command('normal-export-preflight',['exec',ids['api'],'/bin/sh','-ec',probe,'normal-probe',key])
            require(output_key==key,'NORMAL_EXPORT_PREFLIGHT')
            summary['exportProbeCommand']=probe_cmd
            summary['preClock']=step('pre-clock',lambda:sample_source_clocks(ids['oracle'],ids['api']))
            resource=r.admit()
            argv=[NODE,DRIVER,'--task',r.TASK,'--run-id',r.PRODUCT,'--mode','s2-oracle-normal','--normal-id',key]
            timeout=min(850,int(window_seconds-(time.monotonic()-start)-180))
            require(timeout>=650,'NORMAL_OUTER_RESERVE')
            prior=set(r.AREA.glob('browser-s2-oracle-normal-*.json'))
            with w.monitored(resource['attempt']):
                result=step('authenticated-http-parent',lambda:r.ex.run(argv,r.ROOT,task=r.TASK,run_id=r.PRODUCT,stage='omq-browser-normal-q1',
                    parent_id=host['commandId'],input_key=r.ex.sha(r.ex.encoded([key,host,argv])),timeout=timeout,
                    environment={**os.environ,'OMQ_PROGRESS_FILE':'s2-s3-'+key+'.jsonl'}))
            summary['parentCommand']=result.receipt['commandId'];summary['parentExit']=result.returncode
            summary['postClock']=step('post-clock',lambda:sample_source_clocks(ids['oracle'],ids['api']))
            parents=[]
            for path in set(r.AREA.glob('browser-s2-oracle-normal-*.json'))-prior:
                value=r.load(path)
                if value.get('input',{}).get('executionId')==key:parents.append((value,path))
            require(len(parents)==1,'NORMAL_PARENT_RECORD')
            parent,path=parents[0]
            summary['parentFile']=path.name
            require(len(parent['stages'])==2 and parent['stages'][0]['mode']=='s0-oracle-auth' and parent['stages'][0]['status']=='PASS','NORMAL_AUTH')
            report_path=Path(parent['stages'][1]['report'])
            require(report_path.parent==r.AREA and r.ex.sha(report_path.read_bytes())==parent['stages'][1]['reportSha256'],'NORMAL_STAGE_RECORD')
            stage=r.load(report_path)
            summary['reportFile']=report_path.name
            posts=[row for row in stage['http'] if row['method']=='POST' and row['path']=='/api/v1/data/semantic-queries']
            require(len(posts)==1,'NORMAL_POST_COUNT')
            http=posts[0]
            summary['http']={k:http.get(k) for k in ('status','queryId','traceId','correlation','elapsedMs','code','sha256')}
            summary['facts']=step('pg-facts',lambda:query_facts(http))
            summary['audit']=stage['normalPost']['audit']
            summary['get']=stage.get('normalGet')
            summary['getWindows']=[v for v in stage['oracleWindows'] if v['name']=='normal-get']
        except BaseException as failure:
            summary['errors'].append(dict(stage='normal-run',reason=str(failure) if isinstance(failure,ValueError) and re.fullmatch('[A-Za-z0-9_-]{1,150}',str(failure)) else type(failure).__name__))
        finally:
            with w.close_resources():
                if 'platform-pg' in r.running_roles():capture('drain-before',lambda:drain('before'))
                for role in r.APIS:
                    if role in r.manifest()['ids']:
                        ident=r.manifest()['ids'][role]
                        capture('release-'+role,lambda:r.release_api(role))
                        if role not in r.manifest()['ids']:summary['closed'][role]=ident
                if 'platform-pg' in r.running_roles():capture('drain-after',lambda:drain('after'))
                for role in ('oracle','rustfs','keycloak-test','fuseki','platform-pg'):
                    active=r.running_roles()
                    if role in active:
                        seen=capture('stop-'+role,lambda:r.recovery.native_stop('replacement',role,active,key))
                        if seen:summary['closed'][role]={k:seen.get(k) for k in ('id','status','after','cleanShutdown','resourceAttempt')}
                final=capture('final-inventory',r.admit)
                if final:
                    summary.update(post=final['attempt'],remaining=final['expectedRunningRoles'],protectedSame=final['protectedOriginalSha256']==r.load(r.AREA/('source-admission-'+decision['coldAttempt']+'.json'))['protectedOriginalSha256'])
                if 'facts' in summary and 'identity' in summary and 'audit' in summary:
                    summary['projection']=capture('qualify-trace',lambda:consume_observation(summary))
                summary['seconds']=time.monotonic()-start
                save()
    return output


if __name__=='__main__':
    path=run_first()
    row=r.load(path)
    print(path.name,row.get('parentExit'),row.get('errors'),row.get('remaining'),flush=True)
    raise SystemExit(int(bool(row.get('parentExit',1) or row['errors'] or row.get('remaining') or not row.get('protectedSame'))))
