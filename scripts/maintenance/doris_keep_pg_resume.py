"""从已审的单卷恢复回执接续余三库；全程保留原异常退出事实。"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import subprocess

import doris_keep_cold as cold
import doris_keep_pg_recovery as pg
import doris_keep_preservation as keep
import doris_keep_readmit as admit


LIVE = {'b71ef14e5e484253c0b435332c4480fc071268f634c0b049d5d4aff57c383912',
        'c1bbd53e0b335a12c5e50bc860a58e6d3cb01de7d81a354ee87696dd0a941c81',
        'd267220f4227b7c92f5d2e37e7e85a4587644488157c10e5f95586613bd08952'}


def reviewed_copy(sha):
    keep.require(keep.digest(pg.PROOF) == sha, 'PG_RECOVERY_REVIEW_SHA')
    proof = json.loads(pg.PROOF.read_text())
    path = keep.ROOT / proof['privatePath']
    keep.require(path == keep.PRIVATE / proof['attempt'] / (pg.VOLUME + '.tar') and path.resolve() == path
                 and keep.check_archive(path) == proof['members'] and keep.digest(path) == proof['archiveSha256']
                 and path.stat().st_uid == os.getuid() and path.stat().st_size == proof['bytes'], 'PG_ARCHIVE_BINDING')
    markers = proof['walMarkers']
    keep.require(proof['parent'] == pg.HALT_SHA and proof['originalId'] == pg.ORIGINAL and proof['image'] == pg.IMAGE
                 and proof['volume'] == pg.VOLUME and proof['originalExitCode'] == 1 and proof['restoredBytesVerified']
                 and proof['sourceAndCopyBefore'] == 'in production' and proof['copyAfter'] == 'shut down'
                 and all(markers[k] for k in ('automaticRecovery','interrupted','fast','ready','cleanShutdown'))
                 and (markers['redoNotRequired'] or markers['redoStarted'] and markers['redoDone'])
                 and proof['nativeStop']['exitCode'] == 0 and proof['joinAndNullMatched'] and proof['scratchRemoved']
                 and [f['sha256'] for f in proof['fixtures']] == [sha for _, sha, _ in pg.RECEIPTS]
                 and all(f['allRowsAndTypesEqual'] for f in proof['fixtures']), 'PG_RECOVERY_PROOF')
    return proof


def accepted(state, originals):
    reviewed = reviewed_copy(state['pgRecoveryReview']['sha256'])
    prior = json.loads(cold.FUSEKI_RESUME.read_text())
    keep.require(keep.digest(cold.FUSEKI_RESUME) == pg.HALT_SHA and state['stopEvents'][:11] == prior['stopEvents']
                 and state['coldVolumes'] == prior['coldVolumes'] and state['previousSha256'] == pg.HALT_SHA,
                 'PG_PARENT_CHANGED')
    events = state['stopEvents']
    accepted_ids = {e['id'] for e in events[:10] if cold.qualified_exit(e, state)}
    failure = events[10]
    keep.require(len(accepted_ids) == 10 and failure['id'] == pg.ORIGINAL and failure['after']['ExitCode'] == 1
                 and failure['after']['FinishedAt'] == reviewed['originalFinishedAt'], 'PG_EXCEPTION_ID')
    accepted_ids.add(pg.ORIGINAL)
    for e in events[11:]:
        keep.require(e['id'] in LIVE and e['result'] == 'NATIVE_FAST_CLEAN_EXIT' and e['after']['ExitCode'] == 0
                     and e['native']['mode'] == 'fast' and e['native']['requestedByUid'] == 999
                     and e['shutdownMarkers'] == {'fast': True, 'clean': True} and e['control'] == 'shut down'
                     and e['after']['FinishedAt'] == e['native']['finishedAt'], 'PG_NATIVE_EXIT')
        accepted_ids.add(e['id'])
    keep.require(len(events) == 14 and accepted_ids == set(originals), 'PG_BATCH_INCOMPLETE')
    return accepted_ids


def stop_original(row, state, checkpoint):
    cid = row['id']
    keep.require(cid in LIVE and row['service'] in ('platform-pg','pg-source') and row['image'] == pg.IMAGE, 'PG_NATIVE_TARGET')
    cold.original(row, 'running')
    mount = [m for m in row['mounts'] if m['Type'] == 'volume' and m['Destination'] == '/var/lib/postgresql']
    suffix = '_source-data' if row['service'] == 'pg-source' else '_platform-data'
    keep.require(len(mount) == 1 and mount[0]['Name'] == row['project'] + suffix, 'PG_NATIVE_VOLUME')
    checkpoint()
    start = dt.datetime.now(dt.timezone.utc).isoformat()
    event = {'id': cid, 'project': row['project'], 'service': row['service'], 'startedAt': start,
             'result': 'REQUESTING_NATIVE_FAST'}
    state['stopEvents'].append(event)
    cold.save(state)
    event['native'] = pg.native_stop(cid)
    observed = pg.engine_state(cid)
    event['after'] = {k: observed[k] for k in ('Status','Running','ExitCode','OOMKilled','FinishedAt','StartedAt')}
    cold.save(state)
    cold.original(row, 'exited')
    logs = subprocess.run([*keep.DOCKER, 'logs', '--since', start, cid], capture_output=True, check=True, timeout=8)
    raw = logs.stdout + logs.stderr
    event['logSha256'] = pg.hashlib.sha256(raw).hexdigest()
    event['shutdownMarkers'] = {'fast': b'received fast shutdown request' in raw, 'clean': b'database system is shut down' in raw}
    cold.save(state)
    keep.require(all(event['shutdownMarkers'].values()), 'PG_NATIVE_CLOSE_LOG')
    with keep.helper(keep.mount(mount[0]['Name'], '/source'), image=pg.IMAGE) as reader:
        keep.start(reader)
        keep.require(keep.helper_state(reader)['volumes'] == [[mount[0]['Name'], '/source', False]], 'PG_CONTROL_MOUNT')
        event['control'] = pg.control(reader, '/source')
    keep.require(event['control'] == 'shut down', 'PG_NATIVE_CLOSE_CONTROL')
    event['result'] = 'NATIVE_FAST_CLEAN_EXIT'
    cold.save(state)


def run(sha):
    keep.require(not cold.PG_RESUME.exists() and keep.digest(cold.FUSEKI_RESUME) == pg.HALT_SHA, 'PG_PREVIOUS_STOP')
    proof = reviewed_copy(sha)
    state = json.loads(cold.FUSEKI_RESUME.read_text())
    prior = {e['id'] for e in state['stopEvents']}
    originals = cold.preexisting()
    keep.require(len(prior) == 11 and set(originals) - prior == LIVE and set(proof['remainingOriginals']) == LIVE
                 and set(keep.execute('ps','-q','--no-trunc').split()) == LIVE | {admit.OLD_PIN}, 'PG_REMAINING_SET')
    rows, _ = keep.inventory(prior)
    for row in originals.values():
        cold.original(row, 'exited' if row['id'] in prior else 'running')
    keep.require(cold.read_pin()['id'] == admit.OLD_PIN, 'PG_PIN')
    state.update(pgRecoveryReview={'reviewer': '/root/spec_review', 'sha256': sha}, previousSha256=pg.HALT_SHA,
                 remainingIds=sorted(LIVE), readmission=keep.ATTEMPT, samples=[], outcome='READMITTING_THREE')
    for key in ('reason','independentReview','awaitingReviewSha256'):
        state.pop(key, None)
    cold.save(state)
    live = sorted([r for r in rows if r['containerId'] in LIVE], key=lambda r: r['service'] == 'platform-pg')
    try:
        with admit.reviewed_fence(state, live.copy()) as fence:
            while live:
                row = live[0]
                def checkpoint():
                    ids = {r['containerId'] for r in live}
                    keep.require(set(keep.execute('ps','-q','--no-trunc').split()) == ids | {admit.OLD_PIN}, 'PG_LIVE_DRIFT')
                    fence('before-' + row['containerId'], live)
                stop_original(originals[row['containerId']], state, checkpoint)
                live.pop(0)
        accepted(state, originals)
        keep.require(keep.execute('ps', '-q', '--no-trunc').split() == [cold.read_pin()['id']], 'PG_FINAL_SET')
        state['outcome'] = 'ALL_STOPPED_COLD_CHECKED_PIN_HELD'
    except BaseException as error:
        state['outcome'] = 'HALTED_PIN_HELD'
        state['reason'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+', str(error)) else type(error).__name__
        cold.save(state)
        raise
    cold.save(state)
    print(state['outcome'], keep.digest(cold.PG_RESUME), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['continue-three','release-after-review'])
    parser.add_argument('--review-sha', required=True)
    args = parser.parse_args()
    with (keep.BASE / 'readmission-03.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'continue-three':
            run(args.review_sha)
        else:
            cold.release_after_review(pg_review_sha=args.review_sha)
