"""重开 PG 维护后实际启动七角色、在派发诊断之前结束的准确窗口。"""
import json
from types import SimpleNamespace
import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
import workflow_oracle_runtime_window as w
import workflow_oracle_d368_pg_close as pg
from workflow_oracle_d368_closure import DOCKER, SQLPLUS, SHUTDOWN
from workflow_oracle_mapping_evidence import utc
from workflow_oracle_mapping_resources import require
from doris_keep_drain import COUNTS

OP = 'ae2b00e0f9e6456c80c9b40103316123'
PRIOR = '134da209971bba43920d988ee52eb1b5de96ff6a3c1eba4e9e14de82f8b566e4'
CLOSE = '344cb4dd6841b71bdff51131e33cfd858b1287a98c1a427e6c4a1567b13288ba'
KIND = 'PRE_DIAGNOSTIC_CLOSE'
BASE = dict(kind=KIND, operation=OP, previousSha256=PRIOR, sha256=CLOSE,
            sizeBytes=4291, diagnosticParents=0, formalParents=0)
LEDGER = dict(offset=107943172, sizeBytes=3922305, sha256='d91cbc9134f74c51839a504cc31e46f9db723d839a572e750983453c74fef993')
DATA = ('platform-pg','oracle','keycloak-test','rustfs','fuseki')
APIS = ('api','api-secondary')
STOPS = {'oracle':'5c060598ce204341a77b49dd0ceaf5f6','platform-pg':'fdc7a572a390498da5cc4da91409ecd2',
         'rustfs':'c7c61a2f17f041b3bb12f0125789a0e3','fuseki':'47cdedba9ce149bb856670024d7e56f9',
         'keycloak-test':'75b50478cbd1499a809cff4f26774b7c'}
PG_NATIVE = {'fast':'3c6366dbc00e4f478311f715c714e988','wait':'45c573161bc3401789ceda5c993a195f',
             'state':'157c57f35d52448fa478b18394e8caef','control':'447f3cab5d9d4eb6bfb6a746ca5a0571',
             'controlCreate':'c14bdf71d0564010a4e1be23cfb17c02','controlHelper':'62ed6f94988040fcbc9882b1cbc1a4e8'}
ENTRY = {**BASE,'memberCount':167,'memberIndexSha256':'b48d4744069b00436a566dc28ed0c9ea52300f4b6b1c855f97235011cb2de899'}
ZERO = b"whenever sqlerror exit failure\nset pages 0 heading off feedback off\nselect count(*) from v$session where username='FIXTURE_READER';\nexit success\n"


def events(root, cold, post):
    # 固定切片可在账本后续追加时继续重开，同时要求边界恰为两次准入首末命令。
    with ex.ordinary(root/c.AREA.parent/'command-events.jsonl').open('rb') as stream:
        stream.seek(LEDGER['offset'])
        raw=stream.read(LEDGER['sizeBytes'])
    require(ex.sha(raw)==LEDGER['sha256'], 'PREDIAGNOSTIC_EVENTS_HASH')
    rows=[json.loads(line) for line in raw.splitlines()]
    require((rows[0]['event'],rows[0]['commandId'],rows[-1]['event'],rows[-1]['commandId']) ==
            ('START',cold['commands'][0]['commandId'],'END',post['commands'][-1]['commandId']),
            'PREDIAGNOSTIC_EVENTS_RANGE')
    starts=[r for r in rows if r['event']=='START']
    ends=[r for r in rows if r['event']=='END']
    require(len(rows)==3338 and len(starts)==len(ends)==len({r['commandId'] for r in starts}) and
            {r['commandId'] for r in starts}=={r['commandId'] for r in ends} and
            all(r['taskId']==w.TASK and (r['runId'] in (w.RUN,c.RECOVERY) or (r['runId'],r['stage'])==('implementation-01','omq-platform-pg-exact-owner')) for r in rows),
            'PREDIAGNOSTIC_EVENT_PAIRS')
    other={'omq-host-inspect','omq-pg-runtime-drain-after','omq-pg-runtime-drain-before','omq-platform-pg-exact-owner',
           's23-diagnostic-consumers','s23-runtime-graph-default','s23-runtime-graph-named','s23-runtime-graph-published'}
    require(all(r['stage'].startswith(('oracle-admission-','omq-recovery-','resume-')) or r['stage'] in other for r in starts)
            and sum(r['stage']=='s23-diagnostic-consumers' for r in starts)==1, 'PREDIAGNOSTIC_DISPATCH')
    return ends


def unique(items):
    require(len(items)==1,'PREDIAGNOSTIC_UNIQUE')
    return items[0]


def reopen(root, entry, prior, archive=None):
    local=SimpleNamespace(paths={},examined={})
    def read(path): return pg.raw_json(root,path,local)
    raw=c.raw(root,c.AREA/w.BATCH/('controlled-run-'+OP+'.json'),local)
    require(all(entry.get(k)==v for k,v in BASE.items()) and len(raw)==BASE['sizeBytes'] and ex.sha(raw)==CLOSE,
            'PREDIAGNOSTIC_ORIGINAL')
    row=json.loads(raw)
    require((row['operation'],row['taskId'],row['runId'],row['batch'],row['planId'],row['status'],row['exitCode'])==
            (OP,w.TASK,w.RUN,w.BATCH,w.PLAN,'BLOCKED',1) and row['remaining']==[] and row['protectedSame'] is True and
            set(row['starts'])==set(row['closed'])==set(DATA+APIS) and all(k not in row for k in ('parent','diagnostic','aba'))
            and len(row['errors'])==1 and row['errors'][0]['step']=='diagnostic','PREDIAGNOSTIC_SCOPE')
    window=read(c.AREA/w.BATCH/('window-'+pg.ident(row['windowId'])+'.json'))
    require((window['taskId'],window['runId'],window['batch'],window['plan'],window['id'],window['state'],
             window['priorCloseSha256'],window['coldAttempt'])==(w.TASK,w.RUN,w.BATCH,w.PLAN,row['windowId'],'CLOSED',PRIOR,row['cold']) and
            window['ceiling']==w.choose(window['openingBytes']), 'PREDIAGNOSTIC_WINDOW')
    cold,post=[pg.inventory(root,row[part],[],local) for part in ('cold','post')]
    commands=events(root,cold,post)
    def command(run,stage,argv,key,seconds,ref=None,lower=None,upper=None):
        matches=[r for r in commands if r['runId']==run and r['stage']==stage and r['inputFingerprint']==key and
                 (ref is None or r['commandId']==ref) and (lower is None or utc(lower)<=utc(r['startedAtUtc'])) and
                 (upper is None or utc(r['endedAtUtc'])<=utc(upper))]
        event=unique(matches)
        r,out,_=c.command(root,event['commandId'],run,argv,stage,key,seconds,local)
        require(all(r[k]==event[k] for k in ('identity','commandSummary','startedAtUtc','endedAtUtc','stdout','stderr')),
                'PREDIAGNOSTIC_EVENT_RECEIPT')
        return r,out.strip()
    end={role:r['after']['FinishedAt'] for role,r in prior['data'].items()}
    for edge in prior.get('maintenance',[]):end.update(edge['finishedAt'])
    finishes={}
    for role in DATA:
        resource=prior['data'][role]['id']
        started=read(pg.REC/('start-'+pg.ident(row['starts'][role])+'.json'))
        stop=read(pg.REC/('stop-'+STOPS[role]+'.json'))
        require(stop['operation']==OP and stop['role']==role,'PREDIAGNOSTIC_NATIVE_TARGET')
        require((started['id'],started['role'],started['attempt'],started['stage'],started['status'])==
                (resource,role,row['starts'][role],w.RUN,'RUNNING') and stop['id']==resource and
                stop['group']=='replacement' and stop['status']==('PROCESS_EXITED' if role=='fuseki' else 'CLEAN_STOP') and
                {k:stop[k] for k in row['closed'][role]}==row['closed'][role],'PREDIAGNOSTIC_PERSISTENT')
        run,argv,stage,key,timeout=c.lifecycle_spec(role,resource,'data-start',root)
        start,out=command(run,stage,argv,key,timeout)
        require(out==resource.encode(),'PREDIAGNOSTIC_START')
        def native(stage,args,timeout=45,stdin=b''):
            return command(c.RECOVERY,'omq-recovery-'+stage,args,ex.sha(ex.encoded(args)+stdin),timeout,
                           lower=stop['startedUtc'],upper=stop['endedUtc'])[1]
        state=json.loads(native('stopped-state',[*DOCKER,'inspect','-f','{{json .State}}',resource]))
        require(all(state[k]==v for k,v in stop['after'].items()) and
                (state['Status'],state['Pid'],state['OOMKilled'],state['Error'])==('exited',0,False,'')
                and state['ExitCode'] in (0,143) and utc(end[role])<utc(start['startedAtUtc'])<=utc(state['StartedAt'])
                <=utc(start['endedAtUtc'])<=utc(stop['startedUtc'])<utc(state['FinishedAt'])<=utc(stop['endedUtc'])
                <=utc(post['startedUtc']),'PREDIAGNOSTIC_GENERATION')
        if role=='platform-pg':
            args=dict(operation=OP,pgStartAttempt=started['attempt'],pgStopAttempt=STOPS[role],
                      pgStartCommand=start['commandId'],pgNative=PG_NATIVE)
            pg.reopen_native(root,args,prior,local)
        else:
            require(native('native-state',[*DOCKER,'inspect','-f','{{.State.Status}}',resource])==b'running' and
                    native('term',[*DOCKER,'stop','--signal=TERM','--timeout=-1',resource])==resource.encode(),
                    'PREDIAGNOSTIC_TERM')
        if role=='oracle':
            require(native('oracle-zero',SQLPLUS,stdin=ZERO)==b'0' and stop['nativeShutdown'] is True,'PREDIAGNOSTIC_ORACLE_ZERO')
            msg=native('oracle-shutdown',SQLPLUS,90,SHUTDOWN).lower()
            require(all(v in msg for v in (b'database closed',b'database dismounted',b'oracle instance shut down')),
                    'PREDIAGNOSTIC_ORACLE_SHUTDOWN')
        if role=='fuseki':
            from workflow_oracle_mapping_platform_recovery import fuseki_termination
            fuseki_termination(stop)
            require(stop['cleanShutdown']=='UNKNOWN' and stop['processExited'] is True and
                    started['productUse']=='CURRENT_GRAPHS_VERIFIED' and started['startedAt']==state['StartedAt'] and
                    started['currentGraphs']['close']==PRIOR and started['pid']>0, 'PREDIAGNOSTIC_FUSEKI')
            graphs=started['currentGraphs']
            require(set(graphs['commands'])=={'default','named','published'} and
                    graphs==w.published_graphs(resource,started['startedAt'],started['pid'],started['checkpoint'],
                                               graphs['commands'],close_sha=PRIOR),'PREDIAGNOSTIC_GRAPH_ORIGINALS')
            for cid in graphs['commands'].values():
                for member in ('receipt.json','stdout.txt','stderr.txt'):
                    c.raw(root,c.AREA.parent/'commands'/w.RUN/pg.ident(cid)/member,local)
            c.raw(root,c.AREA/w.BATCH/'frozen-graphs-second-open.json',local)
        finishes[role]=state['FinishedAt']
    for role in APIS:
        start=row['starts'][role]
        api=row['closed'][role]
        require(start['id']==api and start['anonymousMe']==401 and api not in prior['ids'].values(),'PREDIAGNOSTIC_API_ID')
        sequence=[('resume-start-'+role,['start',api],40,'id'),('resume-api-term',['stop','--signal','TERM','--timeout','-1',api],45,'id'),
                  ('resume-api-exit',['inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',api],30,'exit'),
                  ('resume-remove-stateless',['rm',api],30,'id'),
                  ('resume-absent',['ps','-a','--no-trunc','--filter','id='+api,'--format','{{.ID}}'],30,'empty')]
        last=cold['endedUtc']
        for stage,args,timeout,mode in sequence:
            result,out=command(w.RUN,stage,[*DOCKER,*args],ex.sha(ex.encoded(args)),timeout,lower=last,upper=post['startedUtc'])
            require(out in ((b'exited 0 false',b'exited 143 false') if mode=='exit' else
                            ((api.encode(),) if mode=='id' else (b'',))) and
                    (stage!='resume-start-'+role or result['commandId']==start['startCommand']), 'PREDIAGNOSTIC_API_RELEASE')
            last=result['endedAtUtc']
    sql=('BEGIN READ ONLY;\nSELECT json_build_array('+','.join('('+v.strip()+')' for v in COUNTS)+');\nCOMMIT;').encode()
    for label in ('before','after'):
        receipt,out=command(w.RUN,'omq-pg-runtime-drain-'+label,[*DOCKER,'exec','-i','--user','postgres',c.PG,'psql',
                            '-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],ex.sha(sql),15,row['drain'][label]['commandId'])
        require(json.loads(out)==row['drain'][label]['values']==[0]*7,'PREDIAGNOSTIC_DRAIN')
    members={p:local.examined[k] for k,p in local.paths.items()}
    index=ex.sha(ex.encoded(members))
    if 'memberIndexSha256' in entry:
        require((entry['memberCount'],entry['memberIndexSha256'])==(len(members),index),'PREDIAGNOSTIC_MEMBERS')
    if archive is not None:
        for k,p in local.paths.items():
            require(archive.examined.get(k,local.examined[k])==local.examined[k],'PREDIAGNOSTIC_ARCHIVE')
            archive.paths[k]=p
            archive.examined[k]=local.examined[k]
    normalized={**prior,'maintenance':[*prior.get('maintenance',[]),dict(operation=OP,finishedAt=finishes)]}
    return normalized,len(members),index
