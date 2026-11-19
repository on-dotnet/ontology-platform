"""以受限 SQL*Plus 观察者采样被测 ODP 的同一固定游标，业务读者无观察权限。"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import workflow_execution as ex
import workflow_m2_build as build
from workflow_m2_evidence import mtp
from workflow_oracle_mapping_resources import before_source, require, PROBE, TASK, RUN
from workflow_oracle_mapping_snapshot import probe_args

ROOT = Path(__file__).resolve().parents[2]
STAMP = """to_char(sys_extract_utc(systimestamp),'YYYY-MM-DD"T"HH24:MI:SS.FF6')"""
OBS_DSN = '(DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST=oracle-source)(PORT=2484))(CONNECT_DATA=(SERVICE_NAME=FREEPDB1))(SECURITY=(SSL_SERVER_DN_MATCH=YES)(MY_WALLET_DIRECTORY=/opt/oracle/oradata/g4-tls/client-trust)))'


def observe(root, task, attempt, count, directed=False):
    require(task == TASK and re.fullmatch(r'window-[0-9]{2}',attempt) and count in (1,100), 'WINDOW_ARGUMENT')
    area = ex.ordinary(root/'artifacts/workflow'/task/RUN)
    private = ex.ordinary(root/'.tools/security/g4-oracle-mapping-query-001'/RUN)
    original = json.loads((area/'source-create-01.json').read_bytes())
    provision = json.loads((area/'observer-setup-02.json').read_bytes())
    source = original['containerId']
    require(provision['status']=='OBSERVER_PROVISIONED' and provision['containerId']==source,'OBSERVER_BINDING')
    require(not directed or count==100, 'DIRECTED_NORMAL_LIMIT')
    resources = before_source(root,task,source)
    output=area/(attempt+'.json')
    sync=private/attempt
    require(not output.exists() and not sync.exists(),'WINDOW_ORIGINAL_EXISTS')
    sync.mkdir(mode=0o700)
    execution=uuid.uuid4().hex
    (sync/'execution').write_text(execution)
    (sync/'count').write_text(str(count))
    binding=build.validate('connections',task)
    record=dict(taskId=task,runId=RUN,attempt=attempt,sourceId=source,execution=execution,count=count,build=binding,
                resourceAttempt=resources['attempt'],commands=[],status='STARTED',startedUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    cid=None
    expanded=False

    def call(stage,args,stdin=None,timeout=20,cleanup=False):
        r=ex.run(['docker','--context','desktop-linux',*args],root,task=task,run_id=RUN,stage=stage,timeout=timeout,stdin=stdin,cleanup=cleanup)
        record['commands'].append(dict(stage=stage,command=r.receipt))
        return r

    def checked(stage,args,stdin=None,timeout=20,cleanup=False):
        r=call(stage,args,stdin,timeout,cleanup)
        require(r.returncode==0,stage)
        return r.stdout.decode().strip()

    def sql(stage,body,observer=False,cleanup=False,program=None):
        prolog='whenever sqlerror exit failure rollback\nwhenever oserror exit failure\nset define off echo off verify off feedback off heading off pages 0 lines 1000 tab off trimspool on serveroutput on size 1000000\n'
        if observer:
            secret=ex.ordinary(private/'observer-password').read_text()
            require(re.fullmatch(r'[A-Za-z0-9]+',secret),'OBSERVER_SECRET_SHAPE')
            session=['/nolog']
            prolog+='connect OMQ_OBSERVER/"'+secret+'"@"'+OBS_DSN+'"\n'
        else:
            session=['/ as sysdba']
            prolog+='alter session set container=FREEPDB1;\n'
        command=program if program is not None else ['sqlplus','-L','-s',*session]
        return checked(stage,['exec','-i',source,*command],(prolog+body+'\nexit success\n').encode(),20,cleanup)

    def baseline(stage):
        columns="ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,"+','.join("to_char("+col+",'YYYYMMDDHH24MISSFF6')" for col in ['FROM_TS','TO_TS','EVENT_TS','OBSERVED_TS'])
        lines=sql(stage,'\n'.join('select json_array('+columns+' returning varchar2(500)) from '+table+' order by ROW_ID;' for table in ['"PRODUCTION"."OMQ_ENTITY"','"CaseOwner"."OmqTarget"'])).splitlines()
        data=[json.loads(v.strip(),parse_float=str) for v in lines if v.strip()]
        require(len(data)==2 and [x[0] for x in data]==[1,2],'BASELINE_ROWS')
        return [ex.sha(ex.encoded(x)) for x in data]

    try:
        record['beforeHash']=baseline('window-before')
        record['observerIdentity']=sql('window-observer-identity',"select sys_context('USERENV','SESSION_USER')||'|'||sys_context('USERENV','NETWORK_PROTOCOL')||'|'||sys_context('USERENV','CON_NAME') from dual;",True)
        require(record['observerIdentity'].upper()=='OMQ_OBSERVER|TCPS|FREEPDB1','OBSERVER_CONNECTION')
        if count==100:
            # 正常 100 行，只扩实体表。主键和外键均由本次私有执行 UUID 派生归属。
            body="""insert into "PRODUCTION"."OMQ_ENTITY"
            select 50000+level, JOIN_KEY, VAL, ORG_ID,SITE_ID,'w-'||substr('%s',1,12)||'-'||level,LABEL,FROM_TS,TO_TS,EVENT_TS,OBSERVED_TS
            from "PRODUCTION"."OMQ_ENTITY" where ROW_ID=1 connect by level<=99;
            commit;""" % execution
            sql('window-normal-100',body)
            expanded=True
        test='OracleMappingCancelProbeTests' if directed else 'OracleMappingWindowTests'
        argv=probe_args(root,task,attempt,original['network'],private/'reader',sync,test)
        cid=checked('window-probe-create',argv)
        require(re.fullmatch('[a-f0-9]{64}',cid),'WINDOW_ID')
        record['probeId']=cid
        identity='{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.attempt"}}|{{.State.Status}}'
        require(checked('window-probe-before',['inspect','-f',identity,cid])=='|'.join([cid,PROBE.split('@')[1],attempt,'created']),'WINDOW_PRESTATE')
        if directed:
            fmt='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
            (sync/'source-ip').write_text(checked('trigger-source-ip',['inspect','-f',fmt,source]))
        # 只投影专属会话。每轮两侧取源时钟，状态变化逐条记录，避免依赖客户端的结束时间。
        marker='/tmp/omq-observer-'+execution
        sampling = """declare
          stop_at timestamp with time zone := systimestamp+numtodsinterval(0.9,'SECOND');
          previous varchar2(1000):='?'; value varchar2(1000); observed varchar2(50);
          seen number; upper_stamp varchar2(50); count_samples number:=0; last_stamp varchar2(50); max_gap interval day to second;
          previous_ts timestamp with time zone:=systimestamp; now_ts timestamp with time zone;
        begin
          while systimestamp<stop_at loop
            select {stamp} into observed from dual;
            select count(*),nvl(max(to_char(sid)||'|'||serial_no||'|'||audsid||'|'||con_id||'|'||status||'|'||nvl(sql_id,'-')||'|'||nvl(to_char(sql_exec_id),'-')||'|'||nvl(prev_sql_id,'-')||'|'||nvl(to_char(prev_exec_id),'-')||'|'||event),'NO_SESSION')
            into seen,value from G4_CONTROL.OMQ_SESSIONS where client_identifier='{ident}';
            now_ts:=systimestamp;
            upper_stamp:=to_char(sys_extract_utc(now_ts),'YYYY-MM-DD"T"HH24:MI:SS.FF6');
            if seen>1 then raise_application_error(-20009,'nonunique session'); end if;
            count_samples:=count_samples+1;
            if max_gap is null or now_ts-previous_ts>max_gap then max_gap:=now_ts-previous_ts; end if;
            previous_ts:=now_ts;
            if value<>previous then dbms_output.put_line(observed||'|'||upper_stamp||'|'||seen||'|'||value); previous:=value; end if;
          end loop;
          dbms_output.put_line('SAMPLES='||count_samples||' GAP='||to_char(max_gap));
        end;
        /""".format(stamp=STAMP,ident=execution)
        with ThreadPoolExecutor(max_workers=2) as pool:
            product=pool.submit(call,'window-fixed-driver',['start','-a',cid],None,38)
            deadline=time.monotonic()+15
            while not (sync/'armed').exists() and not product.done() and time.monotonic()<deadline:
                time.sleep(.01)
            require((sync/'armed').is_file() and (sync/'armed').read_text()==execution,'WINDOW_DRIVER_ARM')
            if directed:
                from workflow_oracle_mapping_signal import native_trigger
                peer=checked('trigger-probe-ip',['inspect','-f',fmt,cid])
                relay,trigger=native_trigger(execution,provision['sqlIds'][0],peer)
                watching=pool.submit(sql,'window-native-directed',trigger+sampling,True,False,relay)
            else:
                watching=pool.submit(sql,'window-native-samples','host touch '+marker+'\n'+sampling,True)
                deadline=time.monotonic()+6
                while not watching.done() and time.monotonic()<deadline:
                    status=checked('window-observer-marker-read',['exec',source,'sh','-c',
                                   'if test -f "$1"; then echo PRESENT; else echo PENDING; fi','observer-ready',marker],timeout=3)
                    if status=='PRESENT':break
                    require(status=='PENDING','OBSERVER_MARKER_STATUS')
                    time.sleep(.025)
                require(not watching.done() and time.monotonic()<deadline,'OBSERVER_ARM')
                (sync/'release').write_text(execution)
            trace=watching.result(); result=product.result()
        record['sourceSamples']=trace.splitlines()
        metrics=[json.loads(line.strip()) for line in result.stdout.decode().splitlines() if line.strip().startswith('{"execution":')]
        record['driverExitCode']=result.returncode
        if len(metrics)==1:
            record['directed' if directed else 'natural']=metrics[0]
        record['cursorStats']=sql('window-real-cursor-stats',"select sql_id||'|'||child_number||'|'||plan_hash_value||'|'||executions||'|'||end_of_fetch_count||'|'||rows_processed||'|'||elapsed_time||'|'||px_servers_executions from G4_CONTROL.OMQ_CURSOR_STATS order by sql_id,child_number;",True).splitlines()
        record['plan']=sql('window-real-plan',"select sql_id||'|'||child_number||'|'||id||'|'||operation||'|'||options from G4_CONTROL.OMQ_PLAN order by sql_id,child_number,id;",True).splitlines()
        record['audit']=sql('window-real-audit',"select instance_id||'|'||sessionid||'|'||entry_id||'|'||statement_id||'|'||execution_id||'|'||object_schema||'|'||object_name||'|'||return_code||'|'||to_char(event_timestamp_utc,'YYYY-MM-DD HH24:MI:SS.FF6') from G4_CONTROL.OMQ_READ_AUDIT where client_identifier='"+execution+"' order by entry_id;",True).splitlines()
        require(build.validate('connections',task)==binding,'WINDOW_BUILD_DRIFT')
        require(len(metrics)==1 and metrics[0]['execution']==execution and (directed or metrics[0]['count']==count),'WINDOW_SAMPLE_ID')
        require(result.returncode==0 and mtp(result.stdout+result.stderr,1)==1,'WINDOW_DRIVER')
        record['status']='DIRECTED_ATTEMPT_OBSERVED' if directed else 'NATURAL_OBSERVED'
    except BaseException as error:
        record.update(status='FAIL',reason=str(error))
        raise
    finally:
        try:
            if expanded:
                sql('window-restore-99',"""begin
                delete from "PRODUCTION"."OMQ_ENTITY" where ROW_ID between 50001 and 50099 and EXT_ID='w-'||substr('%s',1,12)||'-'||(ROW_ID-50000);
                if sql%%rowcount<>99 then raise_application_error(-20008,'incorrect fixture row count'); end if;
                commit;
                end;
                /""" % execution,cleanup=True)
            if 'beforeHash' in record:
                record['afterHash']=baseline('window-after')
                require(record['afterHash']==record['beforeHash'],'WINDOW_ROWS_CHANGED')
            if cid:
                actual=checked('window-probe-close',['inspect','-f',identity,cid])
                require(actual in ['|'.join([cid,PROBE.split('@')[1],attempt,state]) for state in ['exited','created']],'WINDOW_OWNER')
                checked('window-probe-remove',['rm',cid],cleanup=True)
                require(not checked('window-probe-absent',['ps','-aq','--no-trunc','--filter','id='+cid],cleanup=True),'WINDOW_PROBE_PRESENT')
                record['probeRemoved']=True
        except BaseException as error:
            record.update(status='FAIL',cleanupReason=str(error))
            raise
        finally:
            record['endedUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
            with output.open('x') as stream:
                json.dump(record,stream,indent=2);stream.write('\n')
    return {k:record[k] for k in ('status','attempt','directed' if directed else 'natural','sourceSamples','audit')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',required=True)
    parser.add_argument('--attempt',required=True)
    parser.add_argument('--count',type=int,required=True,choices=(1,100))
    parser.add_argument('--directed',action='store_true')
    args=parser.parse_args()
    print(json.dumps(observe(ROOT,args.task,args.attempt,args.count,args.directed)))
