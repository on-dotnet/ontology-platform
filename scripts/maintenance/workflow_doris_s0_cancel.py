"""从独立 FE/BE 活动视图观测单次真实只读 SQL 的取消。此原生见证不认证产品驱动。"""
import csv
import io
import json
import re
import secrets
import select
import subprocess
import time

import workflow_doris_s0_fixture as src
import workflow_doris_vm as vm


def rows(raw):
    return list(csv.DictReader(io.StringIO(raw),delimiter='\t',quoting=csv.QUOTE_NONE))


def activity_counts(raw):
    """只有匹配 FE 与 BE 的两个非负活动计数才是一次完整观测。"""
    parts = raw.split('\t')
    vm.demand(len(parts) == 2 and all(re.fullmatch(r'[0-9]+', item) for item in parts), 'SOURCE_OBSERVATION_INCOMPLETE')
    return tuple(map(int, parts))


def check():
    state=json.loads(src.INDEX.read_text())
    fe=state['services']['fe']['id']
    vm.demand(src.docker('cancel-owner','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{.State.Status}}',fe)
              ==fe+' '+vm.TASK+' running','SOURCE_IDENTITY')
    tag='dmq_cancel_'+secrets.token_hex(8)
    proof={'taskId':vm.TASK,'runId':vm.RUN,'fe':fe,'operation':tag,'totalMs':5000,'branchMs':1000,'cleanupMs':250,
           'instrument':'native mysql 8.0.44 / VERIFY_IDENTITY, independent admin SQL observer',
           'formalMySqlConnectorResult':'NOT_RUN','noReconnect':True,'samples':[]}
    for title,statement in (('fe','SHOW FRONTENDS;'),('be','SHOW BACKENDS;')):
        result=rows(src.sql(fe,'root',statement,True))
        vm.demand(len(result)==1 and result[0]['Alive'].lower()=='true' and '4.0.8' in result[0]['Version'],'SOURCE_ALIVE_VERSION')
        proof[title+'Build']=result[0]['Version']
    proof['readerTransport']=src.sql(fe,'reader','SELECT CURRENT_USER();')
    tls=subprocess.run(['openssl','s_client','-connect','localhost:19030','-starttls','mysql','-servername','localhost',
                        '-CAfile',str(src.DIRECTORY/'tls/ca.pem'),'-verify_hostname','localhost','-verify_return_error'],
                       input=b'',capture_output=True,timeout=4)
    vm.demand(tls.returncode==0 and b'Verify return code: 0' in tls.stdout,'HOST_CA_AND_DNS_SAN')
    proof['hostHandshake']={'hostname':'localhost','port':19030,'chainAndHostnameVerified':True}
    query=("SELECT SLEEP(CAST(IF(entity_id='E1',3,0) AS INT)) AS "+tag+
           " FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id='E1';")
    input_bytes=(src.DIRECTORY/'reader.pass').read_bytes()+b'\nSELECT CONNECTION_ID();\n'+query.encode()+b'\n'
    thread=None
    query_id=None
    started=time.monotonic()
    branch_end=started+1
    def elapsed():
        return round((time.monotonic()-started)*1000,3)
    def remaining(deadline):
        budget=deadline-time.monotonic()
        vm.demand(budget>0,'NATIVE_BUDGET_EXHAUSTED')
        return budget
    def observe(deadline):
        # 查询 ID 仅来自旁路 FE 自身；数值读数同时来自 FE 注册表和 BE 活跃任务表。
        counts=src.sql(fe,'root',
            "SELECT (SELECT count(*) FROM information_schema.active_queries WHERE query_id='"+query_id+"'),"
            "(SELECT count(*) FROM information_schema.backend_active_tasks WHERE query_id='"+query_id+"');",
            limit=remaining(deadline))
        front,back=activity_counts(counts)
        sample={'atMs':elapsed(),'feActive':front,'beActive':back}
        proof['samples'].append(sample)
        return front,back
    proc=subprocess.Popen(['docker','--context','desktop-linux','exec','-i',fe,'bash','-ec',src.CLIENT,'source',
                           'fixture_reader','--skip-column-names'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        proc.stdin.write(input_bytes)
        proc.stdin.close()
        vm.demand(select.select([proc.stdout],[],[],remaining(branch_end-.25))[0],'THREAD_OPEN_DEADLINE')
        first=proc.stdout.readline().strip()
        vm.demand(re.fullmatch(b'[1-9][0-9]{0,18}',first),'SOURCE_THREAD_RESPONSE')
        thread=int(first)
        proof['serverThread']=thread
        proof['readerOpenMs']=elapsed()
        while not query_id:
            current=rows(src.sql(fe,'root','SHOW FULL PROCESSLIST;',True,limit=remaining(branch_end-.25)))
            active=[r for r in current if r['Id']==str(thread) and r['User']=='fixture_reader' and tag in r['Info']]
            if active and re.fullmatch(r'[0-9a-fA-F]{16}-[0-9a-fA-F]{16}',active[0]['QueryId']):
                query_id=active[0]['QueryId']
                proof['queryId']=query_id
                proof['processObservedAtMs']=elapsed()
            else:time.sleep(.005)
        while not all(observe(branch_end-.25)):
            time.sleep(.005)
        cancel_at=time.monotonic()
        cleanup_end=min(branch_end,cancel_at+.25)
        proof['cancelRequestedAtMs']=elapsed()
        src.sql(fe,'reader','KILL CONNECTION '+str(thread)+';',limit=remaining(cleanup_end))
        proof['killAcknowledgedAtMs']=elapsed()
        while any(observe(cleanup_end)):
            time.sleep(.005)
        proof['sourceGoneAtMs']=elapsed()
        code=proc.wait(timeout=remaining(cleanup_end))
        proof['driverExitedAtMs']=elapsed()
        proof['nativeClientExitCode']=code
        output=proc.stdout.read()
        vm.demand(code!=0 and not output.strip() and time.monotonic()<=cleanup_end,'LATE_OR_SUCCESS_OUTPUT')
        proof.update(outcome='NATIVE_CANCELLATION_OBSERVED',cleanupElapsedMs=round((time.monotonic()-cancel_at)*1000,3))
    except (ValueError,subprocess.SubprocessError) as error:
        proof.update(outcome='NATIVE_CANCEL_NOT_VERIFIED',reason=str(error) if isinstance(error,ValueError) else type(error).__name__,
                     faultAtMs=elapsed())
    finally:
        # 错过任何原窗口即保留失败。仅作事后观测，固定三秒查询自行结束。
        try:
            code=proc.wait(timeout=max(.05,started+4.75-time.monotonic()))
            proof['finalNativeClientExitCode']=code
            proof['unexpectedResultBytes']=len(proc.stdout.read().strip())
            if query_id:
                proof['postmortemFeBe']=observe(started+5)
        except (ValueError,subprocess.SubprocessError) as error:
            proof['postmortem']='UNKNOWN_'+type(error).__name__
        proof['observationEndMs']=elapsed()
        src.record(vm.OUTPUT/(tag+'.json'),proof)
    print(json.dumps(proof),flush=True)
    return proof


if __name__=='__main__':
    raise SystemExit(0 if check()['outcome']=='NATIVE_CANCELLATION_OBSERVED' else 2)
