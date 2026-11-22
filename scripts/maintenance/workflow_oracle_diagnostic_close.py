"""重开仅派发一个诊断父、在历史结果自然过期处结束的七角色窗口。"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import workflow_execution as ex
import workflow_oracle_mapping_continuity as c
import workflow_oracle_d368_pg_close as pg
import workflow_oracle_prediagnostic_close as life
import workflow_oracle_runtime_window as w
import workflow_oracle_mapping_continuation as cont
from workflow_oracle_mapping_evidence import DRIVER, NODE, Originals
from workflow_oracle_mapping_resources import require
from workflow_oracle_mapping_s2_contract import reopen_grants

OP='7903de957c5b49b29b85a1e982cf2e6f'
PARENT='a576965c8f4d47999676d82ecfde9106'
COMMIT='54c1b7bc4db48fff7c0caf6ed4037b678f60409c'
EXEC='9cbbcc81c8c24544858f4984daee739f'
SHA='d5598f018a72a3b22eec696cc3d2d85090882d03b11440d9442484103d0aa1ff'
PRIOR=life.CLOSE
CHECKPOINT=dict(executionId=EXEC,commandId='016bb425031e49d4abaf60e63da55aa2',before='c95769d5a22f4166a57bd60fed872d8d',
                after='613e29625d64424f8916a4aa78a9c0c7',afterSha256='92b497265c8da4f4133244b510ea20c20c13b268cf23973ae1aba4bb718e604a',
                rows=105,epoch=136)
BASE=dict(kind='DIAGNOSTIC_CLOSE',operation=OP,sha256=SHA,sizeBytes=4282,previousSha256=PRIOR,
          diagnosticParent=PARENT,diagnosticChild=None,queryId=None,formalParents=0,grantCheckpoint=CHECKPOINT)
STOPS={'platform-pg':'f592acf1e0cd4e83a9583e0bf6b16e65','oracle':'b15a23267514425597e83b1b06390183',
       'keycloak-test':'88b034240fd94c9ab63162a3e6286696','rustfs':'44b5755aba8c49d8b8548b7f2508bf54','fuseki':'916586d87c6948398cbb96bcaa6e7c71'}
PG_NATIVE={'fast':'017d85fee34b413398b0665f6c339521','wait':'04dbd22f661c4ef687d263c31874b021','state':'550d83b5e7b84facb451254030408c32',
           'control':'c9a9ed98793e4d81a2de7fe495646a89','controlCreate':'a2e9b8fcca1a4ba1aaa31adf957f81d6','controlHelper':'dabc6c090938414db6a001345d194290'}
AREA=c.AREA/w.BATCH


def commands(root,cold,post):
    with ex.ordinary(root/c.AREA.parent/'command-events.jsonl').open('rb') as stream:
        stream.seek(111884283)
        raw=stream.read(3935979)
    require(ex.sha(raw)=='138cfc9ba04c3655f5f640b63b59416cb17a1ec507cf0261735675262020ddb2','DIAGNOSTIC_CLOSE_EVENTS')
    rows=list(map(json.loads,raw.splitlines()))
    starts=[r for r in rows if r['event']=='START']
    ends=[r for r in rows if r['event']=='END']
    require((rows[0]['commandId'],rows[-1]['commandId'])==(cold['commands'][0]['commandId'],post['commands'][-1]['commandId']) and
            len(starts)==len(ends)==1675 and {r['commandId'] for r in starts}=={r['commandId'] for r in ends} and
            [r['commandId'] for r in starts if r['stage']=='s23-diagnostic-aba']==[PARENT] and not any(
                r['stage'] in ('query-real-aba-inflight-runtime','omq-browser-s2-s3-oracle','normal-mapping-rollback') for r in starts),
            'DIAGNOSTIC_CLOSE_DISPATCH')
    return ends


def prepare_evidence(root,local):
    start,start_raw,_,_,_=cont.diagnostic_bound_inputs(root,local)
    require((start['executionId'],start['measuredCommit'],start['windowId'])==(EXEC,COMMIT,'600309f15a3143f2a3ca431fd1d94688'),
            'DIAGNOSTIC_CLOSE_START')
    argv=[NODE,DRIVER,'--task',w.TASK,'--run-id',w.RUN,'--mode','s2-oracle-aba','--diagnostic-id',EXEC]
    rec,out,err=cont.diagnostic_command(root,PARENT,argv,'s23-diagnostic-aba',cont.diagnostic_parent_key(start_raw),start['host']['commandId'],local)
    require(not err and (rec['deadlineSeconds'],rec['exitCode'])==(900,1),'DIAGNOSTIC_CLOSE_PARENT')
    first,last=map(json.loads,out.splitlines())
    stages=first['diagnosticStages']
    require(stages==last['stages'] and [(s['mode'],s['status']) for s in stages]==[('s0-oracle-auth','PASS'),('s2-oracle-aba','FAIL')]
            and stages[1]['failure']==dict(phase='launch',category='Error',code='http_10_200'),'DIAGNOSTIC_CLOSE_STAGES')
    reports=[]
    for stage in stages:
        ref=Path(stage['report']).relative_to(root)
        require(ref.parent==c.AREA,'DIAGNOSTIC_CLOSE_REPORT_PATH')
        b=c.raw(root,ref,local)
        require(ex.sha(b)==stage['reportSha256'],'DIAGNOSTIC_CLOSE_REPORT_HASH')
        reports.append(json.loads(b))
    r=reports[1]
    require(not r['oracleCases'] and r['http'][-1]['method']=='GET' and
            r['http'][-1]['path']=='/api/v1/data/semantic-queries/query-d293780099754592b3e2a00957e13c8b/result' and
            (r['http'][-1]['status'],r['http'][-1]['code'])==(410,'result_expired'),'DIAGNOSTIC_CLOSE_BEFORE_Q')
    class GrantFiles(Originals):
        def __init__(self):
            self.root=root
            self.examined,self.paths=local.examined,local.paths
        def raw(self,name):
            if re.fullmatch(r'grant-plan-[a-f0-9]{32}[.]json',name):
                return c.raw(root,AREA/name,local)
            m=re.fullmatch(r'([a-f0-9]{32})-(receipt[.]json|std(?:out|err)[.]txt)',name)
            require(m,'DIAGNOSTIC_CLOSE_GRANT_MEMBER')
            return c.raw(root,c.AREA.parent/'commands'/w.RUN/m[1]/m[2],local)
    _,argv,_,_=reopen_grants(GrantFiles(),r,start['host'],root)
    g=r['currentGrants']
    require((g['executionId'],g['grantCommand'],g['beforeCommand'],g['afterCommand'],g['beforeEpoch'],g['afterEpoch'])==
            (EXEC,CHECKPOINT['commandId'],CHECKPOINT['before'],CHECKPOINT['after'],121,136) and
            [len(g[v]['rows']) for v in ('beforeSnapshot','afterSnapshot')]==[90,105] and
            len(g['combinedGrantIds'])==6 and len(g['workflowIds'])==9 and len(g['issued'])==15 and
            ex.sha(c.raw(root,c.AREA.parent/'commands'/w.RUN/CHECKPOINT['after']/'stdout.txt',local))==CHECKPOINT['afterSha256'],
            'DIAGNOSTIC_CLOSE_GRANTS')
    prefix=start['prefix'];b=c.raw(root,AREA/prefix['file'],local)
    require(ex.sha(b)==prefix['sha256'],'DIAGNOSTIC_CLOSE_PREFIX')
    obs=json.loads(b)
    binding=r['oracleBinding'];active=binding['activation']
    name=obs['state']['latestQuery']['reportName']
    require(re.fullmatch(r'browser-s2-oracle-queries-[0-9]{13}[.]json',name),'DIAGNOSTIC_CLOSE_HISTORY')
    old=pg.raw_json(root,c.AREA/name,local)['oracleBinding']
    cont.prefix_activation(root,obs['host'],old,obs['state'],obs['activationChainCommand'],local)
    mid=active['mappingId'];body=(f"""BEGIN READ ONLY;
SELECT to_jsonb(a) FROM connections."MappingActives" a WHERE "MappingId"='{mid}';
COMMIT;""").encode()
    _,present,_=c.command(root,r['scenarioReady']['activationCommand'],w.RUN,argv,'omq-pg-s23-current-activation',ex.sha(body),15,local)
    cur=json.loads(present)
    require((cur['ActivationId'],cur['ActivationRevision'],cur['ReleaseId'])==(active['activationId'],3,active['mappingReleaseId'])
            and obs['state']['mappingReceipt']==active,'DIAGNOSTIC_CLOSE_A3')
    return start


def reopen(root,entry,prior,archive=None):
    local=SimpleNamespace(paths={},examined={})
    b=c.raw(root,AREA/('controlled-run-'+OP+'.json'),local)
    require(len(b)==4282 and ex.sha(b)==SHA and all(entry.get(k)==v for k,v in BASE.items()),'DIAGNOSTIC_CLOSE_ORIGINAL')
    row=json.loads(b)
    require((row['taskId'],row['runId'],row['planId'],row['batch'],row['operation'],row['testedCommit'],row['status'],row['exitCode'])==
            (w.TASK,w.RUN,w.PLAN,w.BATCH,OP,COMMIT,'BLOCKED',1) and row['errors']==row['remaining']==[] and row['protectedSame'] is True
            and set(row['starts'])==set(row['closed'])==set(life.DATA+life.APIS) and not any(k in row for k in ('parent','aba','extensionSha256')),
            'DIAGNOSTIC_CLOSE_SCOPE')
    outcome=pg.raw_json(root,cont.OUTCOME_FILE,local)
    require(row['diagnostic']==outcome==dict(taskId=w.TASK,runId=w.RUN,batch=w.BATCH,parentId=PARENT,childId=None,
                                             queryId=None,exitCode=1,measuredCommit=COMMIT),'DIAGNOSTIC_CLOSE_OUTCOME')
    win=pg.raw_json(root,AREA/('window-'+pg.ident(row['windowId'])+'.json'),local)
    require((win['taskId'],win['runId'],win['batch'],win['plan'],win['state'],win['id'],win['priorCloseSha256'],win['coldAttempt'])==
            (w.TASK,w.RUN,w.BATCH,w.PLAN,'CLOSED',row['windowId'],PRIOR,row['cold']) and win['ceiling']==w.choose(win['openingBytes']),
            'DIAGNOSTIC_CLOSE_WINDOW')
    cold,post=[pg.inventory(root,row[k],[],local) for k in ('cold','post')]
    refs=commands(root,cold,post)
    finishes=life.resources(root,row,prior,refs,cold,post,local,OP,PRIOR,STOPS,PG_NATIVE)
    start=prepare_evidence(root,local)
    require(start['windowId']==win['id'],'DIAGNOSTIC_CLOSE_WINDOW_ID')
    return life.result(local,archive,entry,prior,OP,finishes)


ENTRY={**BASE,'memberCount':598,'memberIndexSha256':'d80649cec9e1e98ed21ab47d7e717f5b0a6a99833732cfa8b3e311a31c70d5f9'}
