"""绑定第二次停点及 Fuseki 替代验收，复用既有持卷、排空、恢复与独立审查入口。"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re

import doris_keep_cold as cold
import doris_keep_fuseki as fuseki
import doris_keep_preservation as keep
import doris_keep_readmit as admit


PREVIOUS = 'd5bc136dcad532568740645779e6f10af37b49adfbaed529c7d25a92bd83dad6'
PREREQ = keep.BASE/'fuseki-alternative-prerequisite.json'
M4, M5 = keep.PROJECTS


def select(rows, project, service):
    choices = [r for r in rows if r['project']==project and r['service']==service]
    keep.require(len(choices)==1,'EXPECTED_SINGLE_SERVICE')
    return choices[0]


def starting_state():
    keep.require(keep.digest(cold.READMISSION)==PREVIOUS, 'PREVIOUS_FUSEKI_HALT_CHANGED')
    state = json.loads(cold.READMISSION.read_text())
    keep.require(state['outcome']=='HALTED_PIN_HELD' and state['reason']=='GRACEFUL_EXIT_NOT_PROVEN' and
                 state['pin']==admit.OLD_PIN and cold.read_pin()['id']==state['pin'], 'FUSEKI_RESUME_POINT')
    stopped = {e['id'] for e in state['stopEvents']}
    rows, _ = keep.inventory(stopped)
    originals = cold.preexisting()
    live = set(originals)-stopped
    keep.require(len(stopped)==6 and len(live)==8 and set(keep.execute('ps','-q','--no-trunc').split())==live|{state['pin']},'FUSEKI_RUNNING_SET')
    for row in originals.values():
        cold.original(row,'exited' if row['id'] in stopped else 'running')
    directory = keep.PRIVATE/state['attempt']
    keep.require(directory.resolve()==directory and directory.stat().st_uid==os.getuid()
                 and directory.stat().st_mode & 0o777 == 0o700,'COLD_DIRECTORY')
    os.umask(0o077)
    return state, rows, originals, directory


def engine(event, row):
    keep.require(event['id']==row['containerId'] and row['service']=='fuseki' and event['requestedSignal']=='SIGTERM',
                 'FUSEKI_STOP_TARGET')
    after = json.loads(keep.execute('inspect','-f','{{json .State}}',event['id']))
    keep.require(all(after[k]==v for k,v in event['after'].items()) and after['Status']=='exited' and after['ExitCode'] in (0,143)
                 and not after['Running'] and not after['OOMKilled'] and not after['Error'] and after['Pid']==0
                 and not after['Dead'] and not after['Restarting'], 'FUSEKI_ENGINE_POSTCONDITION')
    elapsed = (dt.datetime.fromisoformat(after['FinishedAt'])-dt.datetime.fromisoformat(event['startedAt'])).total_seconds()
    keep.require(0<=elapsed<=45, 'FUSEKI_STOP_DEADLINE')
    return {'signal':'SIGTERM','engineStopTimeout':-1,'controllerBoundSeconds':45,'observedSeconds':elapsed,
            'exitCode':after['ExitCode'],'finishedAt':after['FinishedAt'],'oomKilled':False,'engineError':False,
            'controlEvidence':'bounded docker stop --timeout=-1 returned successfully; no force escalation path',
            'shutdownHook':'UNKNOWN'}


def prove(row, rows, fact, archive, live_compare=True):
    pin = cold.read_pin()['id']
    volume = row['project']+'_fuseki-data'
    slot = '/v'+str(cold.VOLUMES.index(volume))
    initial = keep.volume_digest(pin,slot)
    if live_compare:
        keep.require(initial==fact['sha256'], 'COLD_INPUT_DIFFERS_FROM_PIN')
    proof = fuseki.verify_volume(row,select(rows,row['project'],'platform-pg'),fact,archive)
    final = keep.volume_digest(cold.read_pin()['id'],slot)
    if live_compare:
        keep.require(initial==final,'PINNED_SOURCE_CHANGED')
    proof.update(pinId=pin,slot=slot,sourceBefore=initial,sourceAfter=final)
    return proof


def prerequisite():
    state, rows, _, directory = starting_state()
    event = state['stopEvents'][-1]
    row = select(rows,M4,'fuseki')
    controlled = engine(event,row)
    state['fusekiAlternative'] = True
    state['outcome'] = 'FUSEKI_ALTERNATIVE_IN_PROGRESS'
    volume = M4+'_fuseki-data'
    if not (directory/(volume+'.tar')).exists():
        cold.capture_cold(volume,rows,state,directory)
    else:
        # 工具失败后的重验只复用已取得的冷归档与同ID回读原件。
        previous = json.loads(cold.FUSEKI_RESUME.read_text())
        fact = previous['coldVolumes'][volume]
        keep.require(fact['sha256']==keep.digest(directory/(volume+'.tar')) and fact['isolatedSameId'], 'COLD_REUSE_FAILED')
        state['coldVolumes'][volume] = fact
    fact = state['coldVolumes'][volume]
    fact['tdb2'] = prove(row,rows,fact,directory/(volume+'.tar'))
    fact['tdb2']['engine'] = controlled
    event['result'] = 'FUSEKI_TERM_AND_TDB2_VERIFIED'
    cold.save(state)
    # M5先检验已审热副本；其原写者退出后仍要对最终冷副本完整重验。
    m5vol = M5+'_fuseki-data'
    hot = json.loads(cold.HOT.read_text())['volumeFacts'][m5vol]
    candidate = prove(select(rows,M5,'fuseki'),rows,hot,keep.ROOT/hot['privatePath'],live_compare=False)
    result = {'previousSha256':PREVIOUS,'pin':state['pin'],'m4Cold':fact,'m4Engine':controlled,'m5HotProbe':candidate,
              'm5FinalCold':'REQUIRED_AFTER_TERM','attempt':keep.ATTEMPT}
    with PREREQ.open('x') as stream:
        json.dump(result,stream,indent=2)
    print('FUSEKI_ALTERNATIVE_READY',keep.digest(PREREQ),flush=True)


def continue_eight(review_sha):
    keep.require(review_sha==keep.digest(PREREQ),'FUSEKI_REVIEW_SHA')
    original_state,rows,originals,directory = starting_state()
    prior = json.loads(cold.FUSEKI_RESUME.read_text())
    keep.require(prior['outcome']=='FUSEKI_ALTERNATIVE_IN_PROGRESS' and len(prior['stopEvents'])==6,'EIGHT_ALREADY_ATTEMPTED')
    proof = json.loads(PREREQ.read_text())
    keep.require(proof['previousSha256']==PREVIOUS and proof['m4Cold']==prior['coldVolumes'][M4+'_fuseki-data']
                 and proof['m5HotProbe']['fullRead'] and cold.qualified_exit(prior['stopEvents'][-1],prior),'FUSEKI_PROOF_BINDING')
    for v,fact in prior['coldVolumes'].items():
        path=directory/(v+'.tar')
        keep.require(keep.digest(path)==fact['sha256'] and keep.check_archive(path)==fact['members']
                     and keep.volume_digest(prior['pin'],'/v'+str(cold.VOLUMES.index(v)))==fact['sha256'],'COLD_REUSE_FAILED')
    already = {e['id'] for e in original_state['stopEvents']}
    state=prior
    state.update(readmission=keep.ATTEMPT,previousSha256=PREVIOUS,remainingIds=sorted(set(originals)-already),
                 samples=[],outcome='READMITTING_EIGHT',alternativeReview={'reviewer':'/root/spec_review','sha256':review_sha})
    state.pop('reason',None)
    state.pop('independentReview',None)
    state.pop('awaitingReviewSha256',None)
    cold.save(state)
    databases=[r for r in rows if r['service'] in ('pg-source','platform-pg')]
    try:
        with admit.reviewed_fence(state, databases) as checkpoint:
            for project,service,suffix in [(M4,'rustfs','rustfs-data'),(M5,'keycloak-test','keycloak-data'),
                                          (M5,'fuseki','fuseki-data'),(M5,'rustfs','rustfs-data')]:
                row=select(rows,project,service)
                cold.stop_one(originals[row['containerId']],state,lambda:checkpoint('before-'+row['containerId']))
                volume=project+'_'+suffix
                cold.capture_cold(volume,rows,state,directory)
                if service=='fuseki':
                    event=state['stopEvents'][-1]
                    controlled=engine(event,row)
                    fact=state['coldVolumes'][volume]
                    fact['tdb2']=prove(row,rows,fact,directory/(volume+'.tar'))
                    fact['tdb2']['engine']=controlled
                    event['result']='FUSEKI_TERM_AND_TDB2_VERIFIED'
                    cold.save(state)
            checkpoint('before-releasing-fences-for-pg')
        admit.stop_databases(state, originals, databases)
        keep.require(len(state['coldVolumes'])==8 and len(state['stopEvents'])==14 and
                     {e['id'] for e in state['stopEvents'] if cold.qualified_exit(e,state)}==set(originals),'EIGHT_CLOSEOUT')
        state['outcome']='ALL_STOPPED_COLD_CHECKED_PIN_HELD'
        cold.save(state)
        print(state['outcome'],flush=True)
    except BaseException as error:
        state['outcome']='HALTED_PIN_HELD'
        state['reason']=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z0-9_]+',str(error)) else type(error).__name__
        cold.save(state)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prerequisite','continue-eight'])
    parser.add_argument('--review-sha')
    args=parser.parse_args()
    with (keep.BASE/'readmission-02.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.mode=='prerequisite':
            prerequisite()
        else:
            continue_eight(args.review_sha)
