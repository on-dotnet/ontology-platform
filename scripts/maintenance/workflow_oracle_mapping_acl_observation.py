"""核实际撤 READ 的同一查询、连接释放、租约、终态和源会话。"""
import json
import re
import subprocess

import workflow_execution as ex
from workflow_oracle_mapping_formal_observer import ns
from workflow_oracle_mapping_resources import require

ZERO_SQL = 'SELECT COUNT(*) FROM G4_CONTROL.OMQ_SESSIONS;'
FIELDS = {
    'OracleBranchBegin': 'query owner fence execution utc workDeadlineUtc branchDeadlineUtc',
    'OracleSourceOwnership': 'phase query execution acquisition utc',
    'OracleSourceCleanup': 'trigger query execution acquisition utc deadlineUtc remainingTicks',
    'OracleSourceEvent': 'action query execution utc',
    'OracleBranchRelease': 'query execution confirmed observedUtc',
}


def sql(query):
    require(re.fullmatch(r'query-[0-9a-f]{32}', query), 'ACL_QUERY_ID')
    return f'''SELECT json_build_array("Id","ExecutionStatus","LeaseOwner","LeaseUntilUtc","ResultHash","CompletedAtUtc"<="DeadlineAtUtc") FROM semantic_query."Queries" WHERE "Id"='{query}';'''.encode()


def log_command(container, start, end, query):
    return ['python3', '-B', 'scripts/maintenance/workflow_oracle_mapping_acl_observation.py', container, start, end, query]


def projected_logs(container, start, end, query):
    sql(query)
    require(re.fullmatch('[0-9a-f]{64}', container) and 0 < ns(end) - ns(start) <= 180_000_000_000, 'ACL_LOG_SCOPE')
    raw = subprocess.run(['docker','--context','desktop-linux','logs','--since',start,'--until',end,container],
                         capture_output=True,timeout=8,check=True)
    events = []
    for line in (raw.stdout + raw.stderr).decode().splitlines():
        if 'query='+query+' ' not in line:
            continue
        fields = line.strip().split()
        if not fields or fields[0] not in FIELDS:
            continue
        names = FIELDS[fields[0]].split()
        values = dict(part.split('=',1) for part in fields[1:] if '=' in part)
        require(all(name in values for name in names) and values['query']==query and re.fullmatch('[0-9a-f]{32}',values['execution']), 'ACL_LOG_IDENTITY')
        events.append({'name': fields[0], **{name:values[name] for name in names}})
    return events


def collect(report):
    import workflow_oracle_mapping_platform as p
    item = next(r for r in report['oracleCases'] if r['name']=='source-acl')
    window = next(w for w in report['oracleWindows'] if w['name']=='source-acl')
    cid = report['inputBinding']['api']['services']['api']['containerId']
    require(p.product_run()=='product-resume-01' and cid==p.runtime_binding()['services']['api']['containerId'], 'ACL_API_INSTANCE')
    args = log_command(cid, window['startedAtUtc'], window['finishedAtUtc'], item['queryId'])
    logs = ex.run(args,p.ROOT,task=p.TASK,run_id=p.product_run(),stage='s23-acl-cleanup-observation',timeout=12,input_key=ex.sha(ex.encoded(args)))
    require(logs.returncode==0 and not logs.stderr, 'ACL_LOG_CAPTURE')
    row, pg = p.read_pg(sql(item['queryId']), 's23-acl-terminal-row')
    count, source = p.native_fixture_sql(ZERO_SQL,'s23-acl-zero-sessions')
    value = dict(events=json.loads(logs.stdout),logCommand=logs.receipt['commandId'],row=json.loads(row),rowCommand=pg,sourceSessions=int(count),sourceCommand=source)
    qualify(report,value)
    return value


def qualify(report, value):
    item = next(r for r in report['oracleCases'] if r['name']=='source-acl')
    require(item['httpStatus']==200 and json.loads(item['raw'])['status']=='UNAVAILABLE' and not json.loads(item['raw'])['evidence']
            and value['row']==[item['queryId'],'COMPLETED',None,None,item['sha256'],True] and value['sourceSessions']==0,'ACL_REJECTED_QUERY_POST')
    windows = [w['name'] for w in report['oracleWindows']]
    require(windows[:4]==['oracle-current-api-readiness','oracle-current-catalog-readiness','source-acl','source-acl-restore-denied']
            and not report['oracleWindows'][2]['audit']['records'],'ACL_CHECK_FIRST')
    denied=report['deniedSourceRestore']
    require(denied['path']=='/api/v1/data/semantic-queries/'+report['catalogReadiness']['queryId']+'/result'
            and denied['status']==503 and json.loads(denied['raw'])['code']=='query_source_unavailable'
            and denied['sha256']==ex.sha(denied['raw'].encode()) and not report['oracleWindows'][3]['audit']['records']
            and any(h['method']=='GET' and h['path']==denied['path'] and h['status']==503 and h.get('code')=='query_source_unavailable'
                    and h['sha256']==denied['sha256'] and 0<h['elapsedMs']<=5000 for h in report['http']), 'ACL_RESTORE_DENIAL')
    pair=report['sourceAcl']
    healthy=[['CaseOwner','OmqTarget','READ','NO'],['PRODUCTION','OMQ_ENTITY','READ','NO']]
    require([pair[action][when]['rows'] for action in ('changed','restored') for when in ('before','after')]==[healthy,healthy[1:],healthy[1:],healthy], 'ACL_EXACT_RESTORATION')
    events=value['events']
    require(events and {e['query'] for e in events}=={item['queryId']} and len({e['execution'] for e in events})==1,'ACL_LOG_QUERY')
    groups={name:[e for e in events if e['name']==name] for name in FIELDS}
    start,=groups['OracleBranchBegin']
    release,=groups['OracleBranchRelease']
    phases=groups['OracleSourceOwnership'];points=groups['OracleSourceCleanup'];action,=groups['OracleSourceEvent']
    require([e['phase'] for e in phases]==['ACQUIRED','PHYSICAL_DISPOSED','CONFIRMED'] and len({e['acquisition'] for e in phases+points})==1
            and [e['trigger'] for e in points]==['RESOURCE_FAILURE','PHYSICAL_DISPOSE','FINAL'] and action['action']=='PHYSICAL_RELEASE'
            and release['confirmed'].lower()=='true', 'ACL_RELEASE_SEQUENCE')
    timestamps=[ns(start['utc']),ns(phases[0]['utc']),ns(points[0]['utc']),ns(points[1]['utc']),ns(action['utc']),ns(phases[1]['utc']),
                ns(points[2]['utc']),ns(phases[2]['utc']),ns(release['observedUtc'])]
    require(timestamps==sorted(timestamps) and all(0<int(e['remainingTicks'])<=2_500_000 and ns(e['deadlineUtc'])==ns(e['utc'])+int(e['remainingTicks'])*100 for e in points)
            and timestamps[-1]<=min(ns(e['deadlineUtc']) for e in points) and timestamps[-1]<=ns(start['branchDeadlineUtc'])
            and 0<=timestamps[-1]-timestamps[2]<=250_000_000,'ACL_RELEASE_BUDGET')
    return (timestamps[-1]-timestamps[2])/1_000_000


def reopen(archive,report,host,root):
    item=next(r for r in report['oracleCases'] if r['name']=='source-acl')
    w=next(w for w in report['oracleWindows'] if w['name']=='source-acl')
    v=report['sourceCleanup'];qualify(report,v)
    args=log_command(host['services']['api']['containerId'],w['startedAtUtc'],w['finishedAtUtc'],item['queryId'])
    pg=['docker','--context','desktop-linux','exec','-i','--user','postgres',host['services']['platform-pg']['containerId'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    native=['docker','--context','desktop-linux','exec','-i',host['oracle']['containerId'],'sqlplus','-L','-s','/ as sysdba']
    for cid,argv,stage,key,seconds,expected in [
        (v['logCommand'],args,'s23-acl-cleanup-observation',ex.sha(ex.encoded(args)),12,v['events']),
        (v['rowCommand'],pg,'omq-pg-s23-acl-terminal-row',ex.sha(b'BEGIN READ ONLY;\n'+sql(item['queryId'])+b'\nCOMMIT;'),15,v['row']),
        (v['sourceCommand'],native,'s23-acl-zero-sessions',ex.sha(ZERO_SQL.encode()),12,v['sourceSessions'])]:
        rec,out,err=archive.command(cid,argv,stage,key,None,root)
        require(rec['exitCode']==0 and rec['classification']=='SUCCESS' and rec['deadlineSeconds']==seconds and not err and json.loads(out)==expected,'ACL_CLEANUP_ORIGINAL')


if __name__=='__main__':
    import sys
    print(json.dumps(projected_logs(*sys.argv[1:])))
