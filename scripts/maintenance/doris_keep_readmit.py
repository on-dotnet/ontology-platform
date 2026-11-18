"""从经独立审核的两次退出和一份冷备接续，仅处置余下十二个原 ID。"""
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import select
import sys
import time

import doris_keep_cold as cold
import doris_keep_drain as drain
import doris_keep_preservation as keep


PREVIOUS_SHA = '7ad4ce74df269dd4e3f4477dff1624b4f6bbdc047b241f50bec7391ec156fb81'
OLD_PIN = 'aa3269ced429a06e7815f701fb425ac7505cc5a2d0fb8d3f28d0221a27a4780c'


def previous():
    keep.require(keep.digest(cold.COLD_INDEX) == PREVIOUS_SHA, 'PREVIOUS_HALT_CHANGED')
    state = json.loads(cold.COLD_INDEX.read_text())
    events = state['stopEvents']
    keep.require(state['outcome'] == 'HALTED_PIN_HELD' and state['reason'] == 'DRAIN_ACTIVITY_DETECTED'
                 and state['pin'] == OLD_PIN and len(events) == 2, 'RESUME_POINT')
    m4, _ = keep.PROJECTS
    stopped = {event['id'] for event in events if event['result'] == 'GRACEFUL_EXIT' and event['project'] == m4
               and event['service'] in ('api', 'api-secondary') and event['after']['ExitCode'] == 0}
    volume = m4 + '_api-keyring'
    keep.require(len(stopped) == 2 and set(state['coldVolumes']) == {volume}, 'RESUME_SET')
    pin = cold.read_pin()
    rows, volumes = keep.inventory(stopped)
    originals = cold.preexisting()
    running = set(originals) - stopped
    keep.require(pin['id'] == OLD_PIN and volumes == cold.VOLUMES and len(running) == 12 and
                 set(keep.execute('ps', '-q', '--no-trunc').split()) == running | {OLD_PIN}, 'RESUME_RUNNING_SET')
    for cid, row in originals.items():
        cold.original(row, 'exited' if cid in stopped else 'running')
        if cid in stopped:
            old = next(e['after'] for e in events if e['id'] == cid)
            now = json.loads(keep.execute('inspect', '-f', '{{json .State}}', cid))
            keep.require(all(now[k] == v for k, v in old.items()), 'STOPPED_ORIGINAL_CHANGED')
    directory = keep.PRIVATE / state['attempt']
    fact = state['coldVolumes'][volume]
    path = directory / (volume + '.tar')
    keep.require(directory.resolve() == directory and directory.stat().st_mode & 0o777 == 0o700
                 and directory.stat().st_uid == os.getuid() and path.stat().st_uid == os.getuid()
                 and keep.check_archive(path) == fact['members'] and keep.digest(path) == fact['sha256']
                 and keep.volume_digest(OLD_PIN, '/v' + str(volumes.index(volume))) == fact['sha256'], 'COLD_REUSE')
    # 同组后续归档继续独占创建，旧归档和旧中止回执不覆盖。
    os.umask(0o077)
    state.update(outcome='READMITTING', readmission=keep.ATTEMPT, previousSha256=PREVIOUS_SHA,
                 remainingIds=sorted(running), samples=[])
    state.pop('reason')
    cold.save(state)
    return state, rows, originals, directory


def record_round(state, rows, phase, pids):
    observation = {'phase': phase, 'started': time.time(), 'databases': {}}
    state['samples'].append(observation)
    for row in rows:
        cid = row['containerId']
        facts = drain.observed_database(row, pids.get(cid))
        observation['databases'][cid] = facts
        cold.save(state)
        drain.demand_zero(facts)
    observation['completed'] = time.time()
    cold.save(state)


def await_review(state, checkpoint):
    # 审查请求绑定不可变的准入快照；等待期间仍采样原栅栏，并受事务的14分钟上限约束。
    receipt = keep.BASE / (keep.ATTEMPT + '-admission.json')
    request = {k: state[k] for k in ('readmission', 'pin', 'remainingIds', 'previousSha256', 'fencePids', 'tables', 'samples')}
    with receipt.open('x') as stream:
        json.dump(request, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    digest = keep.digest(receipt)
    print('REVIEW_READY', receipt.name, digest, flush=True)
    state['awaitingReviewSha256'] = digest
    cold.save(state)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        ready, _, _ = select.select([sys.stdin], [], [], 6)
        if ready:
            answer = sys.stdin.readline().strip()
            keep.require(answer == 'GO ' + digest, 'REVIEW_NOT_GRANTED')
            checkpoint('after-independent-go')
            state['independentReview'] = {'reviewer': '/root/spec_review', 'admissionSha256': digest, 'time': time.time()}
            cold.save(state)
            return
        checkpoint('awaiting-independent-review')
    raise ValueError('REVIEW_WINDOW_ENDED')


def execute():
    keep.require(not cold.READMISSION.exists(), 'READMISSION_ALREADY_RECORDED')
    state, rows, originals, directory = previous()
    databases = [r for r in rows if r['service'] in ('pg-source', 'platform-pg')]
    platforms = [r for r in databases if r['service'] == 'platform-pg']
    m4, m5 = keep.PROJECTS
    try:
        record_round(state, databases, 'before-fence', {})
        tables = {r['containerId']: drain.product_tables(r) for r in platforms}
        with ExitStack() as stack:
            pids = {r['containerId']: stack.enter_context(drain.fence(r, tables[r['containerId']])) for r in platforms}
            state.update(fencePids=pids, tables=tables)
            for row in platforms:
                drain.confirm(row, tables[row['containerId']])
            def checkpoint(phase):
                cold.read_pin()
                for row in platforms:
                    cid = row['containerId']
                    drain.verify_fence_owner(row, tables[cid], pids[cid])
                record_round(state, databases, phase, pids)

            for i in range(3):
                if i:
                    time.sleep(1)
                checkpoint('admission-' + str(i + 1))
            await_review(state, checkpoint)
            for service in ('api-secondary', 'api'):
                row = next(r for r in originals.values() if (r['project'], r['service']) == (m5, service))
                cold.stop_one(row, state, lambda: checkpoint('before-' + row['id']))
            cold.capture_cold(m5 + '_api-keyring', rows, state, directory)
            for project in (m4, m5):
                for service, suffix in [('keycloak-test', 'keycloak-data'), ('fuseki', 'fuseki-data'), ('rustfs', 'rustfs-data')]:
                    row = next(r for r in originals.values() if (r['project'], r['service']) == (project, service))
                    cold.stop_one(row, state, lambda: checkpoint('before-' + row['id']))
                    cold.capture_cold(project + '_' + suffix, rows, state, directory)
            checkpoint('before-releasing-fences-for-pg')
        # 全部应用写者已退出，分别在仍运行的准确 PG 上复核，最后关闭平台数据库。
        remaining = sorted(databases, key=lambda r: r['service'] == 'platform-pg')
        while remaining:
            row = remaining[0]
            cold.stop_one(originals[row['containerId']], state,
                          lambda: record_round(state, remaining, 'before-' + row['containerId'], {}))
            remaining.pop(0)
        keep.require(len(state['coldVolumes']) == 8 and len(state['stopEvents']) == 14
                     and {e['id'] for e in state['stopEvents'] if e['result'] == 'GRACEFUL_EXIT'} == set(originals),
                     'COLD_SET_INCOMPLETE')
        state['outcome'] = 'ALL_STOPPED_COLD_CHECKED_PIN_HELD'
        cold.save(state)
    except BaseException as error:
        state['outcome'] = 'HALTED_PIN_HELD'
        state['reason'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+', str(error)) else type(error).__name__
        cold.save(state)
        raise
    print(state['outcome'], flush=True)


if __name__ == '__main__':
    with (keep.BASE / 'readmission-01.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute()
