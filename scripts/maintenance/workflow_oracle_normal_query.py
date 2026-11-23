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
    require(row['value']['connectionId']==CONNECTION and sum(a['action']=='data.query.execute' and a['trace']==trace and a['correlation']==correlation for a in audits['value'])==1,'NORMAL_POST_SCOPE')
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
    audit=[a for a in facts['audit']['value'] if a['action']=='data.query.execute']
    require(len(audit)==1 and audit[0]['action']=='data.query.execute' and audit[0]['correlation']==http['correlation']
            and audit[0]['trace']==http['traceId'],'NORMAL_COMMAND_AUDIT')
    exported=r.load(AREA/('normal-export-'+identity['container']+'-'+key+'.json'))
    require(exported['status']=='EXPORTED' and exported['exitCode']==0,'NORMAL_EXPORT_MISSING')
    raw=(r.BASE.parent/'commands'/r.PRODUCT/exported['commandId']/'stdout.txt').read_bytes()
    require(len(raw)==exported['sizeBytes'] and r.ex.sha(raw)==exported['sha256'],'NORMAL_EXPORT_BYTES')
    verdict=r.qualify_normal_projection(raw,key,query_id=db['queryId'],trace_id=http['traceId'],correlation=http['correlation'],
            status=http['status'],process=identity['process'],module=identity['module'],audit=row['audit']['records'],
            profile=r.HISTORICAL_PROFILE if exported['commandId']=='56bca1e4a9d84523b85a993124b8a48e' and
            key=='f3d2efe12c984042a324c0f2cc133b30' else r.METADATA_PROFILE)
    if http['status']==200:
        require(row['parentExit']==0 and http['queryId']==db['queryId']==row['get']['queryId'] and http['elapsedMs']<=5000
                and http['sha256']==db['resultHash']==row['get']['sha256'] and row['get']['sizeBytes']==db['resultSize']
                and db['resultCiphertextLength']>0 and db['ownerSha256'] is None and db['leaseUntilUtc'] is None
                and facts['data']['value']['receipts']==2 and audit[0]['outcome']=='allowed' and any(a['action']=='data.query.read' and a['outcome']=='allowed' for a in facts['audit']['value'])
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
    prior=w.last_close(r.ROOT,digest=PG_CLOSE)
    pg=prior['data']['platform-pg']['id']
    end=prior['maintenance'][-1]['finishedAt']['platform-pg']
    state,_=r.command('normal-pg-closed',['inspect','-f','{{.State.Status}}|{{.State.Pid}}|{{.State.FinishedAt}}',pg])
    require(state=='exited|0|'+end,'NORMAL_CLOSED_PG')
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


def reopen_closed(root,entry,prior,archive=None):
    """复用七角色生命周期消费者，登记普通 Q 的末代并保持未知占位封闭。"""
    from types import SimpleNamespace
    import workflow_oracle_mapping_continuity as continuity
    import workflow_oracle_d368_pg_close as pg
    import workflow_oracle_prediagnostic_close as life
    local=SimpleNamespace(paths={},examined={})
    op=entry['operation']
    raw=continuity.raw(root,continuity.AREA/w.BATCH/('normal-observation-'+op+'.json'),local)
    require(len(raw)==entry['sizeBytes'] and r.ex.sha(raw)==entry['sha256'],'NORMAL_CLOSED_ORIGINAL')
    row=json.loads(raw)
    require(row['slot']=='Q1' and row['remaining']==row['errors']==[] and row['protectedSame'] and row['parentExit']==1
            and row['facts']['row']['value']['queryId']==entry['queryId'] and row['parentCommand']==entry['parentId']
            and row['windowId']==entry['windowId'] and row['closeSha256']==entry['previousSha256']==PG_CLOSE,'NORMAL_CLOSED_SCOPE')
    win=pg.raw_json(root,continuity.AREA/w.BATCH/('window-'+row['windowId']+'.json'),local)
    require(win['state']=='CLOSED' and win['id']==entry['windowId'] and win['coldAttempt']==row['cold']
            and win['priorCloseSha256']==PG_CLOSE,'NORMAL_WINDOW_CLOSED')
    book=entry['ledger']
    with r.ex.ordinary(root/continuity.AREA.parent/'command-events.jsonl').open('rb') as stream:
        stream.seek(book['offset'])
        data=stream.read(book['sizeBytes'])
    require(len(data)==book['sizeBytes'] and r.ex.sha(data)==book['sha256'],'NORMAL_CLOSE_LEDGER')
    ends=[v for line in data.splitlines() if (v:=json.loads(line))['event']=='END']
    require([v['commandId'] for v in ends if v['stage']=='omq-browser-normal-q1']==[entry['parentId']]
            and not any(v['stage'] in ('query-real-aba-inflight-runtime','omq-browser-s2-s3-oracle') for v in ends),'NORMAL_CLOSED_PARENT')
    cold=pg.inventory(root,row['cold'],[],local)
    post=pg.inventory(root,row['post'],[],local)
    record={**row,'closed':{**row['closed'],**{role:{k:v for k,v in row['closed'][role].items() if v is not None} for role in DATA}},
            'drain':{label:{'values':v['value'],'commandId':v['commandId']} for label,v in row['drain'].items()}}
    finishes=life.resources(root,record,prior,ends,cold,post,local,op,PG_CLOSE,entry['nativeStops'],entry['pgNative'],normal=True)
    normalized,count,index = life.result(local,archive,entry,prior,op,finishes)
    # 仅发布已经过七角色生命周期重开的当代字段；成员索引仍由原始文件集计算。
    import workflow_oracle_mapping_access_refresh as refresh
    _,services = refresh.observed_rows(root,row['host'],archive)
    normalized['data'] = {role:{**native,'startedAt':services[role]['startedAt'],'after':row['closed'][role]['after']}
                          for role,native in prior['data'].items()}
    normalized['apis'] = {role:{**prior['apis'][role],'id':row['closed'][role]} for role in ('api','api-secondary')}
    normalized['ids'] = {role:item['containerId'] for role,item in services.items()}
    return normalized,count,index



# 元数据探针使用相同生产方法与受限镜像。此入口没有业务表 SQL、平台 Query 或租约操作。
def metadata_probe(slot, catalog, snapshots, sample_dir, admission, *, question=None):
    from concurrent.futures import ThreadPoolExecutor
    from workflow_oracle_mapping_snapshot import probe_args
    import workflow_oracle_d368_closure as closure
    require(slot == 'B1' or slot == 'B2' and question, 'METADATA_SAMPLE_SLOT')
    key = uuid.uuid4().hex
    directory = sample_dir/slot
    directory.mkdir(mode=0o700)
    (directory/'execution').write_text(key)
    (directory/'catalog.json').write_bytes(r.ex.encoded(catalog))
    began = time.monotonic()
    state = dict(slot=slot,kind='DIAGNOSTIC_ONLY',key=key,question=question,commands={},sourceTermination='UNKNOWN',
                 source=closure.SOURCE,probeSnapshot=snapshots['connections']['snapshotId'],apiSnapshot=snapshots['api']['snapshotId'])
    original = directory/'observation.json'
    def save():
        r.platform.save(original,state,original.exists())
    def action(stage,args,limit=5,cleanup=False):
        left = 30 - (time.monotonic() - began)
        if not cleanup:
            require(left >= 1, 'METADATA_SUPERVISION_DEADLINE')
            limit = min(limit,left)
        result = r.ex.run([*closure.DOCKER,*args],r.ROOT,task=r.TASK,run_id=r.PRODUCT,stage='metadata-'+slot+'-'+stage,
                          input_key=r.ex.sha(r.ex.encoded(args)),timeout=limit,cleanup=cleanup)
        state['commands'][stage] = result.receipt['commandId']
        save()
        return result
    def read_source(stage,sql,limit):
        data = ("whenever sqlerror exit failure rollback\nset echo off feedback off heading off pages 0 lines 32000 "
                "verify off tab off trimspool on\nset serveroutput on size 1000000\nalter session set container=FREEPDB1;\n"
                +sql+"\nexit success\n").encode()
        observed = r.ex.run([*closure.DOCKER,'exec','-i',closure.SOURCE,'sqlplus','-L','-s','/ as sysdba'],r.ROOT,
                        task=r.TASK,run_id=r.PRODUCT,stage='metadata-'+slot+'-'+stage,stdin=data,
                        input_key=r.ex.sha(data),timeout=limit)
        # 每条命令独立持久化，资源监控保护退出也能找到已结束的实际观察。
        r.platform.save(directory/(stage+'-command.json'),dict(commandId=observed.receipt['commandId'],
                        exitCode=observed.returncode,stdout=observed.receipt['stdout'],stderr=observed.receipt['stderr']))
        return observed
    condition = ("con_id=to_number(sys_context('USERENV','CON_ID')) and username='FIXTURE_READER' "
                 "and module='G4-ORACLE-MAPPING-QUERY-001' and client_identifier='"+key+"'")
    watch = """declare
      t number; prev number := dbms_utility.get_time; maxgap number := 0;
    begin
      for i in 1..190 loop
        t := dbms_utility.get_time; maxgap := greatest(maxgap,t-prev); prev := t;
        for s in (select sid,serial#,audsid,con_id,sql_id,sql_child_number,prev_sql_id,prev_child_number
                  from v$session where """+condition+""") loop
          dbms_output.put_line(i||'|'||t||'|'||sys_context('USERENV','INSTANCE')||'|'||s.sid||'|'||s.serial#||'|'||
              s.audsid||'|'||s.con_id||'|'||s.sql_id||'|'||s.sql_child_number||'|'||s.prev_sql_id||'|'||s.prev_child_number);
        end loop;
        dbms_session.sleep(0.05);
      end loop;
      dbms_output.put_line('SUMMARY|190|'||maxgap);
    end;
/"""
    # 准确镜像、快照和配额在开始任何源调用前从引擎独立回读。
    base = probe_args(r.ROOT,r.TASK,key,r.net_names()['source-internal'],r.RESTORED/'reader',directory,'OracleMetadataCostTests')
    base = [arg.replace('--memory=512m','--memory=768m').replace('--memory-swap=512m','--memory-swap=768m')
            .replace('ontology.run=implementation-01','ontology.run='+r.PRODUCT)
            .replace(str(r.ROOT/'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0'),
                     str(r.ROOT/snapshots['connections']['directory'])) for arg in base]
    base[1:1] = ['--platform','linux/arm64']
    cid = None
    save()
    try:
        made = action('create',base)
        require(made.returncode == 0,'METADATA_CREATE')
        cid = made.stdout.decode().strip()
        require(re.fullmatch('[a-f0-9]{64}',cid),'METADATA_HELPER_ID')
        state['helper'] = cid
        save()
        fmt = '{{.Id}}|{{.Image}}|{{.State.Status}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.ReadonlyRootfs}}|{{index .Config.Labels "ontology.attempt"}}|{{json .Mounts}}|{{json .NetworkSettings.Networks}}'
        checked = action('identity',['inspect','-f',fmt,cid])
        fields = checked.stdout.decode().strip().split('|')
        require(checked.returncode == 0 and fields[:8] == [cid,r.platform.IMAGES['api'],'created','805306368','805306368',
                '500000000','true',key] and set(json.loads(fields[9])) == {r.net_names()['source-internal']}, 'METADATA_HOST')
        mounts = {m['Destination']:(m['Source'].removeprefix('/host_mnt'),m['RW']) for m in json.loads(fields[8]) if m['Type']=='bind'}
        require(mounts == {'/app':(str(r.ROOT/snapshots['connections']['directory']),False),
                          '/run/fixture':(str(r.RESTORED/'reader'),False),'/run/sync':(str(directory),True)},'METADATA_MOUNTS')
        with w.monitored(admission,metadata_helper=cid), ThreadPoolExecutor(max_workers=1) as pool:
            w.metadata_allow(30)
            require(30 - (time.monotonic() - began) >= 23, 'METADATA_SUPERVISION_RESERVE')
            observer = pool.submit(read_source,'sessions',watch,16)
            time.sleep(.35)
            launched = time.monotonic()
            driver = action('actual',['start','-a',cid],16)
            # 到期优先读回，不将 helper 已退出或 Dispose 返回解释成源会话已退出。
            post = read_source('post-session',"select count(*) from v$session where "+condition+";",4)
            post_seconds = time.monotonic()-launched
            watched = observer.result()
        state['commands'].update(observer=watched.receipt['commandId'],postSession=post.receipt['commandId'])
        state.update(outerLaunchToPostSeconds=post_seconds,driverExit=driver.returncode)
        require(post.returncode == watched.returncode == 0,'METADATA_SOURCE_OBSERVATION')
        lines = watched.stdout.decode().strip().splitlines()
        summary = lines[-1].strip().split('|')
        require(summary[:2] == ['SUMMARY','190'],'METADATA_SAMPLE_COUNT')
        rows = [line.strip().split('|') for line in lines[:-1] if line.strip()]
        require(all(len(row)==11 for row in rows),'METADATA_SESSION_SHAPE')
        state['sampleCount']=190
        state['maxSampleGapMs']=int(summary[2])*10
        state['matchedSamples']=len(rows)
        ids=sorted({tuple(row[2:7]) for row in rows})
        state['sessions']=ids
        state['sqlChildren']=sorted({(row[i],row[i+1]) for row in rows for i in (7,9)
                                    if re.fullmatch('[0-9a-z]{13}',row[i]) and row[i+1].isdigit()})
        raw = r.ex.ordinary(directory/'metadata.json').read_bytes()
        require(len(raw)<=r.METADATA_LIMIT,'METADATA_RAW_SIZE')
        data=json.loads(raw)
        require(data['source']['probe']==str(uuid.UUID(key)) and data['source']['queryId'] is None
                and data['source']['dropped']==0 and data['source']['frequency']==data['frequency']>0,'METADATA_PROBE_KIND')
        groups=r.check_metadata_spans(data['source'],component=True)
        spans=groups.get(key,[])
        identity=next((span['Session'] for span in spans if span['Session']),None)
        terminated=(len(ids)==1 and all(v.isdigit() and int(v)>0 for v in ids[0]) and identity
                    and tuple(map(int,(ids[0][0],ids[0][1],ids[0][3],ids[0][4]))) ==
                    (identity[0],identity[1],identity[2],identity[4]) and post.stdout.strip()==b'0')
        state.update(sourceTermination='CONFIRMED' if terminated else 'UNKNOWN',
                     sourceExitWithinDiagnostic=bool(terminated and post_seconds<=10),rawSha256=r.ex.sha(raw),
                     rawBytes=len(raw),workMs=(data['workEnd']-data['origin'])*1000/data['frequency'],
                     exitMs=(data['end']-data['origin'])*1000/data['frequency'])
        state['completed']=(driver.returncode==0 and len(spans)==12 and data['failure'] is None
                            and data['disposeFailure'] is None and state['workMs']<=8000 and state['exitMs']<=10000)
        save()
    finally:
        if cid:
            checked=action('exit',['inspect','-f','{{.Id}}|{{.State.Status}}|{{.State.Pid}}',cid],cleanup=True)
            ident,status,pid=checked.stdout.decode().strip().split('|')
            require(ident==cid and status in ('created','exited','running'),'METADATA_EXIT_ID')
            if status=='running':
                require(action('term',['stop','--signal','TERM','--timeout','-1',cid],limit=15,cleanup=True).returncode==0,'METADATA_TERM')
            require(action('remove',['rm',cid],cleanup=True).stdout.decode().strip()==cid,'METADATA_REMOVE')
            absent=action('absent',['ps','-aq','--no-trunc','--filter','id='+cid],cleanup=True)
            require(absent.returncode==0 and not absent.stdout.strip(),'METADATA_ABSENT')
            state['helperAbsent']=True
        state['outerSeconds']=time.monotonic()-began
        save()
    require(state['outerSeconds']<=30,'METADATA_SUPERVISION_OVERRUN')
    return state


def run_metadata_baseline():
    """用本代 PG 的真实目录和已关闭维护后继打开一个双角色诊断窗。"""
    import workflow_oracle_d368_closure as closure
    from workflow_m2_build import TARGETS, inputs
    head = w.close_registration()
    require(head['kind']=='METADATA_PG_ONLY' and head['status']=='TASK_LEVEL_RECOVERY' and head['queryId']==closure.METADATA_QUERY,
            'METADATA_PG_SUCCESSOR')
    w.last_close(r.ROOT,digest=head['sha256'])
    sample_dir=AREA/'metadata-baseline'
    sample_dir.mkdir(mode=0o700)
    operation=uuid.uuid4().hex
    record=dict(taskId=r.TASK,runId=r.PRODUCT,batch=w.BATCH,operation=operation,priorClose=head['sha256'],starts={},closed={})
    path=sample_dir/'window.json'
    def save():
        r.platform.save(path,record,path.exists())
    with w.metadata_batch_window('source1'), w.open_window() as decision:
        record.update(windowId=decision['id'],cold=decision['coldAttempt'])
        save()
        try:
            snapshots={}
            for target in ('api','connections'):
                binding,event=r.bound_build(target)
                src=r.ROOT/Path(TARGETS[target]).parent/'bin/Debug/net10.0'
                disk=r.admit()['platformDisk']
                snapshots[target]=r.platform.snapshots.freeze(r.ROOT,src,r.AREA/'runtime-snapshots',binding,event['commandId'],
                        {'toolEnvironment':event['environmentFingerprint']},task=r.TASK,run_id=r.PRODUCT,
                        remaining_bytes=decision['ceiling']-w.EXIT_MARGIN-w.CHECKOUT-disk['totalBytes'])
            modules=['OntologyPlatform.Modules.Connections.dll','OntologyPlatform.Contracts.dll','Oracle.ManagedDataAccess.dll']
            require(all(snapshots['api']['files'][n]==snapshots['connections']['files'][n] for n in modules),'METADATA_HOST_MODULES')
            record.update(modules={n:snapshots['api']['files'][n] for n in modules},snapshots={t:s['snapshotId'] for t,s in snapshots.items()},
                          buildInput=inputs('connections'),closeReserveSeconds=w.METADATA_CLOSE_SECONDS)
            save()
            for role in ('platform-pg','oracle'):
                w.metadata_allow(210)
                record['starts'][role]=r.recovery.start_owned('replacement',role,r.running_roles())['attempt']
                save()
            source_start,cmd=r.command('metadata-source-generation',['inspect','-f','{{.Id}}|{{.State.StartedAt}}|{{.State.Status}}',closure.SOURCE])
            require(source_start.startswith(closure.SOURCE+'|') and source_start.endswith('|running'),'METADATA_LIVE_SOURCE')
            record.update(sourceGeneration=source_start,sourceCommand=cmd)
            cat,cmd=r.platform.read_pg(('SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+CONNECTION+
                '\' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;').encode(),'metadata-current-catalog')
            catalog=json.loads(cat)
            require(catalog['connectionId']==CONNECTION and catalog['status']=='READY' and len(catalog['objects'])==2,'METADATA_CURRENT_CATALOG')
            record.update(catalogCommand=cmd,catalogSha256=r.ex.sha(r.ex.encoded(catalog)))
            save()
            ddl,cmd=r.platform.native_fixture_sql("set long 100000 longchunksize 30000 linesize 32000\n"
                        "select dbms_metadata.get_ddl('VIEW','READONLY_ATTESTATION','G4_CONTROL') from dual;",'metadata-view-definition')
            require('READONLY_ATTESTATION' in ddl and 'BLOCKED_COUNT' in ddl and len(ddl)<65536,'METADATA_VIEW_DDL')
            record.update(viewCommand=cmd,viewDdlSha256=r.ex.sha(ddl.encode()))
            where="owner='G4_CONTROL' and "
            obj="name='READONLY_ATTESTATION'"
            sections=[
                ("object","select json_array(owner,object_name,object_type,status) from dba_objects where "+where+"object_name='READONLY_ATTESTATION'"),
                ("view","select json_array(owner,view_name,bequeath) from dba_views where "+where+"view_name='READONLY_ATTESTATION'"),
                ("columns","select json_array(column_id,column_name,data_type,data_length,data_precision,data_scale) from dba_tab_columns where "+where+"table_name='READONLY_ATTESTATION' order by column_id"),
                ("grants","select json_array(grantee,privilege,grantable,grantor) from dba_tab_privs where "+where+"table_name='READONLY_ATTESTATION' order by 1"),
                ("dependencies","select json_array(referenced_owner,referenced_name,referenced_type) from dba_dependencies where "+where+obj+" and type='VIEW' order by 1"),
                ("dependents","select json_array(owner,name,type) from dba_dependencies where referenced_owner='G4_CONTROL' and referenced_name='READONLY_ATTESTATION' order by 1"),
                ("triggers","select json_array(owner,trigger_name,status) from dba_triggers where table_owner='G4_CONTROL' and table_name='READONLY_ATTESTATION' order by 1")]
            body='\n'.join('prompt SECTION_'+section+'\n'+sql+';' for section,sql in sections)
            meta,cmd=r.platform.native_fixture_sql(body,'metadata-view-dependencies')
            record.update(viewMetadataCommand=cmd,viewMetadata=meta.splitlines())
            save()
            admission=r.admit()
            sample=metadata_probe('B1',catalog,snapshots,sample_dir,admission['attempt'])
            record.update(sample=sample,trace='OFF')
            save()
            # 计划和累计统计仅针对本次实际命中的 child，不对短语句猜测归属。
            keys=sample.get('sqlChildren',[])
            if keys:
                require(len(keys)<=32,'METADATA_SQL_COUNT')
                exact=','.join("('"+q+"',"+n+")" for q,n in keys)
                selector="con_id=to_number(sys_context('USERENV','CON_ID')) and (sql_id,child_number) in ("+exact+")"
                sql=("select json_array(sql_id,child_number,plan_hash_value,executions,cpu_time,elapsed_time,dbms_lob.getlength(sql_fulltext),"
                     "rawtohex(standard_hash(dbms_lob.substr(sql_fulltext,4000,1),'SHA256'))) from v$sql where "+selector+
                     " and parsing_schema_name='FIXTURE_READER' order by sql_id,child_number;\nprompt PLAN\n"
                     "select json_array(sql_id,child_number,plan_hash_value,id,parent_id,operation,options) from v$sql_plan where "+
                     selector+" order by sql_id,child_number,id fetch first 1000 rows only;")
                _,record['planCommand']=r.platform.native_fixture_sql(sql,'metadata-sampled-plans')
                save()
        finally:
            with w.close_resources():
                failures=[]
                for role in ('oracle','platform-pg'):
                    try:
                        active=r.running_roles()
                        if role in active:
                            record['closed'][role]=r.recovery.native_stop('replacement',role,active,operation)
                            save()
                    except Exception as err:
                        failures.append((role,type(err).__name__))
                record['post']=r.admit()['attempt']
                record['remaining']=sorted(r.running_roles())
                record['closeErrors']=failures
                save()
                require(not failures and not record['remaining'],'METADATA_WINDOW_CLOSURE')
    return record


if __name__=='__main__':
    path=run_first()
    row=r.load(path)
    print(path.name,row.get('parentExit'),row.get('errors'),row.get('remaining'),flush=True)
    raise SystemExit(int(bool(row.get('parentExit',1) or row['errors'] or row.get('remaining') or not row.get('protectedSame'))))
