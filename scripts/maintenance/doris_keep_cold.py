"""追加授权的 R0 冷保存；只读持卷容器独立于控制进程，失败时持续挂载。"""
import argparse
import datetime as dt
import hashlib
import os
import subprocess
import json
from pathlib import Path
import re
import time

import doris_keep_preservation as keep
from doris_keep_drain import drained, sample
from doris_keep_keycloak import verify_copy


PIN_LABEL = 'ontology.doris-cold-pin'
PIN = keep.BASE / 'cold-pin.json'
HOT = keep.BASE / '5907b4c6ad2d4bc18d2f3faa18025759-capture-rehearse.json'
VOLUMES = sorted(project + '_' + suffix for project in keep.PROJECTS for suffix in keep.MOUNTS)
RUN_PIN = 'while test ! -f /control/approved-release; do sleep 2; done'


def read_pin():
    data = json.loads(PIN.read_text())
    cid = data['id']
    keep.require(bool(re.fullmatch('[0-9a-f]{64}', cid)), 'PIN_ID')
    fields = keep.execute('inspect', '-f', '{{.Id}} {{.Image}} {{.State.Status}} {{index .Config.Labels "ontology.doris-cold-pin"}} '
                          '{{index .Config.Labels "ontology.task-id"}} {{index .Config.Labels "ontology.run-id"}} '
                          '{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}}', cid).split()
    keep.require(fields == [cid, keep.IMAGE, 'running', data['attempt'], keep.TASK, keep.RUN, 'none', 'true'], 'PIN_IDENTITY')
    mounts = json.loads(keep.execute('inspect', '-f', '{{json .Mounts}}', cid))
    permanent = sorted((m.get('Name'), m['Destination'], m['RW']) for m in mounts if m['Type'] == 'volume')
    keep.require(permanent == [(v, '/v' + str(i), False) for i, v in enumerate(VOLUMES)] and
                 all(m['Type'] in ('tmpfs', 'volume') for m in mounts), 'PIN_MOUNTS')
    keep.require(keep.execute('inspect', '-f', '{{.State.StartedAt}}', cid) == data['started'], 'PIN_RESTARTED')
    return data


def create_pin():
    rows, volumes = keep.inventory()
    keep.require(volumes == VOLUMES and not PIN.exists(), 'PIN_ALREADY_REGISTERED')
    keep.require(not keep.execute('ps', '-aq', '--filter', 'label=' + PIN_LABEL), 'EXISTING_PIN')
    keep.require(set(keep.execute('ps', '-q', '--no-trunc').split()) == {r['containerId'] for r in rows}, 'RUNNING_SET')
    keep.require(keep.digest(HOT) == 'd98e329ecd5403bbab9ca294facefe7ddd2c24dc1d54535c1b03d992b631cdcb', 'REVIEWED_HOT_RECEIPT')
    facts = json.loads(HOT.read_text())['volumeFacts']
    for volume in VOLUMES:
        path = keep.PRIVATE / '5907b4c6ad2d4bc18d2f3faa18025759' / (volume + '.tar')
        keep.require(keep.digest(path) == facts[volume]['sha256'] and keep.check_archive(path) == facts[volume]['members'],
                     'HOT_RECHECK')
    memory, cores = map(int, keep.execute('info', '-f', '{{.MemTotal}} {{.NCPU}}').split())
    old = sum(int(keep.execute('inspect', '-f', '{{.HostConfig.Memory}}', r['containerId'])) for r in rows)
    keep.require(old == 12 * 1024**3 and old + 192 * 1024**2 + 2 * 1024**3 <= memory and cores >= 10, 'PIN_CAPACITY')
    mounts = [arg for i, v in enumerate(VOLUMES) for arg in keep.mount(v, '/v' + str(i))]
    cid = keep.execute('create', '--pull=never', '--network=none', '--read-only', '--restart=no', '--cap-drop=ALL',
                       '--cap-add=DAC_READ_SEARCH', '--security-opt=no-new-privileges', '--memory=192m', '--memory-swap=192m',
                       '--cpus=0.5', '--pids-limit=24', '--log-driver=none', '--tmpfs', '/var/lib/postgresql:size=1m',
                       '--tmpfs', '/control:size=1m,mode=0700', '--label', 'ontology.task-id=' + keep.TASK, '--label',
                       'ontology.run-id=' + keep.RUN, '--label', PIN_LABEL + '=' + keep.ATTEMPT, *mounts,
                       '--entrypoint=/bin/sh', keep.IMAGE, '-ec', RUN_PIN)
    keep.require(bool(re.fullmatch('[0-9a-f]{64}', cid)), 'PIN_CREATE')
    keep.record('created-continuous-pin', cid)
    keep.execute('start', cid)
    with PIN.open('x') as stream:
        json.dump({'id': cid, 'attempt': keep.ATTEMPT, 'started': keep.execute('inspect', '-f', '{{.State.StartedAt}}', cid),
                   'volumes': VOLUMES, 'oldCaps': old, 'dockerMemory': memory, 'cpu': cores,
                   'backups': {v: facts[v]['sha256'] for v in VOLUMES}}, stream, indent=2)
    read_pin()
    for i, v in enumerate(VOLUMES):
        keep.execute('exec', cid, 'sh', '-ec', 'test -n "$(find "$1" -mindepth 1 -print -quit)"', 'check', '/v' + str(i))
    keep.record('confirmed-continuous-pin-eight-nonempty-ro', cid)
    print('continuous read-only mounts', len(VOLUMES), cid)


R0_BEFORE = keep.BASE.parent / keep.RUN / 'r0-before.json'
COLD_INDEX = keep.BASE / 'controlled-stop.json'
API_TERM = r'''
set -eu
count=0
for d in /proc/[0-9]*; do
    test -r "$d/comm" || continue
    read -r role < "$d/comm" || continue
    test "$role" = dotnet || continue
    if tr '\000' '\n' < "$d/cmdline" | grep -Fxq '/app/OntologyPlatform.Api.dll'; then
        pid=${d##*/}
        count=$((count+1))
    fi
done
test "$count" -eq 1
kill -TERM "$pid"
'''


READMISSION = keep.BASE / 'readmission-01-stop.json'
FUSEKI_RESUME = keep.BASE / 'readmission-02-stop.json'
PG_RESUME = keep.BASE / 'readmission-03-stop.json'


def save(state):
    dest = READMISSION if 'readmission' in state else COLD_INDEX
    if state.get('fusekiAlternative'):
        dest = FUSEKI_RESUME
    if 'pgRecoveryReview' in state:
        dest = PG_RESUME
    tmp = dest.with_suffix('.pending')
    with tmp.open('w') as stream:
        json.dump(state, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, dest)


def preexisting():
    reviewed = json.loads(keep.REVIEW.read_text())
    keep.require(keep.digest(R0_BEFORE) == reviewed['inputSha256']['r0-before.json'], 'OLD_EVIDENCE_CHANGED')
    originals = json.loads(R0_BEFORE.read_text())
    keep.require(len(originals) == 14, 'EXPECTED_14')
    return {row['id']: row for row in originals}


def original(row, expected):
    cid = row['id']
    fmt = ('{{.Id}} {{.Name}} {{.Image}} {{index .Config.Labels "com.docker.compose.project"}} '
           '{{index .Config.Labels "com.docker.compose.service"}} {{.HostConfig.RestartPolicy.Name}} {{.State.Status}}')
    keep.require(keep.execute('inspect', '-f', fmt, cid).split() ==
                 [cid, row['name'], row['image'], row['project'], row['service'], 'no', expected], 'ORIGINAL_IDENTITY')
    mounts = json.loads(keep.execute('inspect', '-f', '{{json .Mounts}}', cid))
    keep.require(sorted(mounts, key=lambda m: m['Destination']) == sorted(row['mounts'], key=lambda m: m['Destination']),
                 'ORIGINAL_MOUNTS')
    for m in mounts:
        if m['Type'] == 'bind':
            path = Path(m['Source'].removeprefix('/host_mnt'))
            keep.require(path.is_absolute() and path.exists(), 'BIND_RESOURCE_MISSING')
        elif m['Type'] == 'volume':
            keep.require(keep.execute('volume', 'inspect', '-f', '{{.Name}}', m['Name']) == m['Name'], 'ORIGINAL_VOLUME')


def stop_one(row, state, before_signal=None):
    cid, service = row['id'], row['service']
    read_pin()
    original(row, 'running')
    if before_signal is not None:
        before_signal()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    event = {'id': cid, 'project': row['project'], 'service': service, 'startedAt': now, 'result': 'REQUESTING'}
    state['stopEvents'].append(event)
    save(state)
    if service in ('api', 'api-secondary'):
        keep.execute('exec', cid, 'sh', '-c', API_TERM, limit=10)
        keep.execute('wait', cid, limit=40)
        event['requestedSignal'] = 'SIGTERM_TO_VERIFIED_FOREGROUND_API'
    else:
        signal = keep.execute('inspect', '-f', '{{.Config.StopSignal}}', cid) or 'SIGTERM'
        keep.require(signal in ('SIGTERM', 'SIGINT'), 'UNEXPECTED_STOP_SIGNAL')
        event['requestedSignal'] = signal
        event['stopTimeout'] = -1
        event['controllerDeadlineSeconds'] = 45
        keep.execute('stop', '--timeout=-1', cid, limit=45)
        event['engineCommandExit'] = 0
    original(row, 'exited')
    observed = json.loads(keep.execute('inspect', '-f', '{{json .State}}', cid))
    event['after'] = {k: observed[k] for k in ('Status', 'Running', 'ExitCode', 'OOMKilled', 'FinishedAt', 'StartedAt')}
    # 服务日志留在 Docker 的原私有 local 驱动；只提取关停信号与诊断散列。
    logs = subprocess.run([*keep.DOCKER, 'logs', '--since', now, '--tail', '180', cid], capture_output=True, timeout=7)
    raw = logs.stdout + logs.stderr
    shutdown = bool(re.search(rb'shut(?:ting)?[ -]?down|\bstopped\b|shutdown|terminat(?:ing|ion)', raw, re.I))
    errors = bool(re.search(rb'out of memory|fatal (error|exception)|data corruption', raw, re.I))
    event.update(shutdownLogMarker=shutdown, logSha256=hashlib.sha256(raw).hexdigest(), logExit=logs.returncode)
    save(state)
    alternative = service == 'fuseki' and state.get('fusekiAlternative') and event['requestedSignal'] == 'SIGTERM'
    keep.require(not observed['OOMKilled'] and not observed['Error'] and logs.returncode == 0 and not errors and
                 (observed['ExitCode'] == 0 or observed['ExitCode'] == 143 and (shutdown or alternative)), 'GRACEFUL_EXIT_NOT_PROVEN')
    event['result'] = 'FUSEKI_ENGINE_EXIT_PENDING_DATA' if alternative else 'GRACEFUL_EXIT'
    read_pin()
    save(state)


def capture_cold(volume, rows, state, directory):
    pin = read_pin()['id']
    keep.require(keep.execute('ps', '-q', '--no-trunc', '--filter', 'volume=' + volume).split() == [pin],
                 'OTHER_LIVE_VOLUME_USERS')
    slot = '/v' + str(VOLUMES.index(volume))
    path = directory / (volume + '.tar')
    logical = int(keep.execute('exec', pin, 'du', '-sb', slot).split()[0])
    total = sum(f.stat().st_size for f in keep.PRIVATE.rglob('*.tar'))
    keep.require(logical < 224 * 1024**2 and total + 256 * 1024**2 <= 2 * 1024**3, 'COLD_CAPACITY')
    digest = keep.capture(pin, slot, path)
    fact = {'sha256': digest, 'bytes': path.stat().st_size, 'members': keep.check_archive(path),
            'privatePath': str(path.relative_to(keep.ROOT)), 'mode': '0600'}
    keep.require(keep.volume_digest(pin, slot) == digest, 'COLD_READBACK_MISMATCH')
    facts = {volume: fact}
    keep.rehearse({volume: path}, facts, read_pin)
    if volume.endswith('_keycloak-data'):
        row = next(r for r in rows if r['project'] + '_keycloak-data' == volume and r['service'] == 'keycloak-test')
        fact['isolatedRealmProbe'] = verify_copy(volume, fact, directory, row['imageId'])
    state['coldVolumes'][volume] = fact
    save(state)


def stop_and_capture():
    pin = read_pin()
    keep.require(not COLD_INDEX.exists(), 'READ_PREVIOUS_STOP_RECEIPT_BEFORE_RESUME')
    rows, volumes = keep.inventory()
    originals = preexisting()
    keep.require(set(keep.execute('ps', '-q', '--no-trunc').split()) == set(originals) | {pin['id']}, 'RUNNING_SET')
    for row in originals.values():
        original(row, 'running')
    directory = keep.private_dir()
    state = {'taskId': keep.TASK, 'runId': keep.RUN, 'attempt': keep.ATTEMPT, 'pin': pin['id'], 'stopEvents': [],
             'coldVolumes': {}, 'outcome': 'IN_PROGRESS', 'started': time.time()}
    save(state)
    def save_failed_sample(current):
        state['failedDrainSample'] = {'observedAt': time.time(), 'counts': current}
        save(state)

    try:
        with drained(rows, on_failed_sample=save_failed_sample) as (checks, checkpoint):
            state['platformAdmission'] = checks
            save(state)
            for project in keep.PROJECTS:
                for service in ('api-secondary', 'api'):
                    checkpoint()
                    row = next(r for r in originals.values() if (r['project'], r['service']) == (project, service))
                    stop_one(row, state)
                capture_cold(project + '_api-keyring', rows, state, directory)
            state['platformAdmission']['postApi'] = checkpoint()
        for project in keep.PROJECTS:
            for service, suffix in [('keycloak-test', 'keycloak-data'), ('fuseki', 'fuseki-data'), ('rustfs', 'rustfs-data')]:
                row = next(r for r in originals.values() if (r['project'], r['service']) == (project, service))
                stop_one(row, state)
                capture_cold(project + '_' + suffix, rows, state, directory)
        databases = [r for r in rows if r['service'] in ('pg-source', 'platform-pg')]
        state['prePgStop'] = sample(databases)
        keep.require(not any(any(v) for v in state['prePgStop'].values()), 'PG_ACTIVITY_REAPPEARED')
        for row in databases:
            stop_one(originals[row['containerId']], state)
        keep.require(len(state['coldVolumes']) == 8 and len(state['stopEvents']) == 14, 'INCOMPLETE_COLD_SET')
        state['outcome'] = 'ALL_STOPPED_COLD_CHECKED_PIN_HELD'
        save(state)
    except BaseException as error:
        state['outcome'] = 'HALTED_PIN_HELD'
        state['reason'] = str(error) if isinstance(error, ValueError) else type(error).__name__
        save(state)
        raise
    print(state['outcome'], len(state['coldVolumes']), len(state['stopEvents']), pin['id'])


def qualified_exit(event, state):
    if not state.get('fusekiAlternative') or event['service'] != 'fuseki':
        return event['result'] == 'GRACEFUL_EXIT'
    volume = event['project'] + '_fuseki-data'
    proof = state['coldVolumes'].get(volume, {}).get('tdb2', {})
    archive = state['coldVolumes'].get(volume, {}).get('sha256')
    engine = proof.get('engine', {})
    graphs = proof.get('graphs', [])
    return (event['result'] == 'FUSEKI_TERM_AND_TDB2_VERIFIED' and proof.get('originalId') == event['id']
            and archive and proof.get('archiveSha256') == proof.get('sourceBefore') == proof.get('sourceAfter') == archive
            and proof.get('fullRead') is True and proof.get('scratchRemoved') is True and graphs
            and proof.get('publishedGraphsVerified') == len(graphs) and proof.get('shutdownHook') == 'UNKNOWN'
            and engine.get('signal') == 'SIGTERM' and engine.get('engineStopTimeout') == -1
            and engine.get('finishedAt') == event['after']['FinishedAt'] and engine.get('oomKilled') is False
            and engine.get('engineError') is False and engine.get('exitCode') == event['after']['ExitCode']
            and 0 <= engine.get('observedSeconds', -1) <= 45)


def release_after_review(pg_review_sha=None):
    """仅在非作者核准全部冷原件后调用；先完成最后一次完整回读，再释放最后的挂载。"""
    pin = read_pin()
    index = FUSEKI_RESUME if FUSEKI_RESUME.exists() else READMISSION if READMISSION.exists() else COLD_INDEX
    if PG_RESUME.exists():
        import doris_keep_pg_resume as pg
        index = PG_RESUME
        keep.require(pg_review_sha == keep.digest(index), 'PG_FINAL_REVIEW_REQUIRED')
    state = json.loads(index.read_text())
    originals = preexisting()
    events = state['stopEvents']
    accepted = {x['id'] for x in events if qualified_exit(x, state)}
    if index == PG_RESUME:
        accepted = pg.accepted(state, originals)
        state['pinReleaseReview'] = {'reviewer': '/root/spec_review', 'sha256': pg_review_sha}
    keep.require(state['outcome'] == 'ALL_STOPPED_COLD_CHECKED_PIN_HELD' and state['pin'] == pin['id'] and
                 len(events) == 14 and accepted == set(originals)
                 and set(state['coldVolumes']) == set(VOLUMES), 'RELEASE_GATE')
    keep.require(keep.execute('ps', '-q', '--no-trunc').split() == [pin['id']], 'RUNNING_SET')
    for row in originals.values():
        original(row, 'exited')
    for i, volume in enumerate(VOLUMES):
        fact = state['coldVolumes'][volume]
        path = keep.PRIVATE / state['attempt'] / (volume + '.tar')
        keep.require(path.resolve() == path and str(path.relative_to(keep.ROOT)) == fact['privatePath']
                     and keep.digest(path) == fact['sha256'] and keep.check_archive(path) == fact['members']
                     and path.stat().st_size == fact['bytes'] and re.fullmatch('[a-f0-9]{64}', fact['isolatedSameId']),
                     'COLD_BACKUP_CHANGED')
        keep.require(keep.volume_digest(pin['id'], '/v' + str(i)) == fact['sha256'], 'COLD_SOURCE_CHANGED')
        if volume.endswith('_keycloak-data'):
            keep.require(bool(re.fullmatch('[0-9a-f]{64}', fact['isolatedRealmProbe'])), 'MISSING_REALM_READ')
    read_pin()
    keep.execute('exec', pin['id'], 'touch', '/control/approved-release')
    keep.require(keep.execute('wait', pin['id'], limit=10) == '0', 'PIN_EXIT')
    keep.require(keep.execute('inspect', '-f', '{{.Id}} {{.State.OOMKilled}} {{.State.Status}}', pin['id'])
                 == pin['id'] + ' false exited', 'PIN_EXIT_STATUS')
    keep.execute('rm', pin['id'])
    keep.require(not keep.execute('ps', '-aq', '--no-trunc', '--filter', 'id=' + pin['id']), 'PIN_REMOVE')
    for row in originals.values():
        original(row, 'exited')
    state['runningIdsAfter'] = keep.execute('ps', '-q', '--no-trunc').split()
    state['dockerAfter'] = keep.execute('info', '-f', '{{.MemTotal}} {{.NCPU}}')
    state['closedAt'] = time.time()
    state['outcome'] = 'STOPPED_KEEP'
    save(state)
    print('STOPPED_KEEP', len(originals), 'cold volumes', len(VOLUMES), 'VM', state['dockerAfter'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['pin', 'stop-and-capture', 'release-after-review'])
    mode = parser.parse_args().mode
    if mode == 'pin':
        create_pin()
    elif mode == 'stop-and-capture':
        stop_and_capture()
    else:
        release_after_review()
