"""对获准的 M5 源库离线卷取证，在隔离副本做 PostgreSQL 自身的 WAL 恢复与夹具核验。"""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

import doris_keep_cold as cold
import doris_keep_preservation as keep
import doris_keep_readmit as admit


ORIGINAL = '19f76154598ac31e4a075175aadafc0a2f22591281ecf5db0704fd65e26a502b'
IMAGE = 'sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437'
VOLUME = 'ontology-g4-m5-integration-01_source-data'
HALT_SHA = 'c9085a867a3fe54c6be053152b8c6e204390cb0eaf7af8b89c79bd34fd0080c6'
PROOF = keep.BASE / 'm5-source-wal-recovery.json'
ORIGINALS = keep.ROOT / 'docs/evidence/G4-M5-INTEGRATION-001/integration-01/originals/integration-01'
RECEIPTS = (
    ('scenario-ready-standard-11e91651b81040368e18b4068310cd9c.json',
     '84d30ddc0e7241fa3cfa745f6893e38dc2a68147762652970ae020d2064ad221', ('assets', 'readings')),
    ('scenario-ready-numeric-45ef4b59715348bdaf8c35fea54624a9.json',
     '41f5ad0356ba30adfcae664fe36cc1c2152d3b3f54d253c6900ca8dc22ccf4b2', ('numeric_assets', 'numeric_readings')),
)


def receipt(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def control(reader, mount):
    """仅保留原生状态，原生工具的 CRC 警告或错误一律阻断。"""
    raw = subprocess.run([*keep.DOCKER, 'exec', '-e', 'LC_ALL=C', reader, 'pg_controldata', mount + '/18/docker'],
                         capture_output=True, timeout=8)
    keep.require(raw.returncode == 0 and not raw.stderr and not re.search(rb'warning|checksum mismatch', raw.stdout, re.I),
                 'PG_CONTROL_DIAGNOSTIC')
    fields = dict(line.split(':', 1) for line in raw.stdout.decode().splitlines() if ':' in line)
    keep.require(fields['pg_control version number'].strip() == '1800', 'PG_CONTROL_VERSION')
    return fields['Database cluster state'].strip()


def fixture_query(tables):
    counts = ','.join('(SELECT count(*) FROM production.' + t + ')' for t in tables)
    types = ("(SELECT json_agg(json_build_object('table',table_name,'column',column_name,'ordinal',ordinal_position,"
             "'type',data_type,'precision',numeric_precision,'scale',numeric_scale,'nullable',is_nullable) "
             "ORDER BY table_name,ordinal_position) FROM information_schema.columns WHERE table_schema='production' "
             "AND table_name IN (" + ','.join("'" + t + "'" for t in tables) + '))')
    rows = ','.join('(SELECT json_agg(t ORDER BY site_id,' + key + ') FROM production.' + table + ' t)'
                    for table, key in zip(tables, ('asset_id', 'reading_id'), strict=True))
    return "SELECT json_build_object('rows',json_build_array(" + counts + "),'types'," + types + ",'data',json_build_array(" + rows + '));'


def check_fixtures(cid):
    def query(sql):
        result = keep.execute('exec', '--user=postgres', cid, 'psql', '-XwqAt', '-v', 'ON_ERROR_STOP=1',
                              '-U', 'postgres', '-h', '/tmp', '-d', 'fixture', '-c',
                              "BEGIN READ ONLY; SET LOCAL TIME ZONE 'UTC'; " + sql + ' COMMIT;', limit=10)
        return json.loads(result, parse_float=Decimal)
    facts = []
    for name, sha, tables in RECEIPTS:
        frozen = ORIGINALS / name
        keep.require(keep.digest(frozen) == sha, 'FIXTURE_ANCHOR_CHANGED')
        expected = json.loads(frozen.read_text(), parse_float=Decimal)['fixture']
        actual = query(fixture_query(tables))
        keep.require(actual == expected, 'RESTORED_FIXTURE_MISMATCH')
        facts.append({'origin': name, 'sha256': sha, 'tables': tables, 'rowCounts': actual['rows'],
                      'columnsCompared': len(actual['types']), 'allRowsAndTypesEqual': True})
    pairs = query("""SELECT json_build_object('matched',
        (SELECT json_agg(r.reading_id ORDER BY r.reading_id) FROM production.numeric_assets a
        JOIN production.numeric_readings r USING(organization_id,site_id,numeric_key)
        WHERE a.organization_id='org-demo' AND a.site_id='site-a' AND a.asset_id='asset-1'),
        'nullCount',(SELECT count(*) FROM production.numeric_readings WHERE numeric_key IS NULL));""")
    keep.require(pairs == {'matched': ['numeric-target-1', 'numeric-target-2'], 'nullCount': 1}, 'FIXTURE_JOIN')
    return facts


def engine_state(cid):
    return json.loads(keep.execute('inspect', '-f', '{{json .State}}', cid))


def native_stop(cid):
    # pg_ctl 自身报告已送达 fast 请求；宿主独立等待 PID 1 退出，避免一起退出的 exec 丢失确认。
    started = time.monotonic()
    command = ('test "$(id -u)" = 999 && pg_ctl status -D "$PGDATA" >/dev/null && '
               'exec pg_ctl stop -D "$PGDATA" -m fast -W')
    keep.execute('exec', '--user=postgres', cid, 'sh', '-ec', command, limit=8)
    result = keep.execute('wait', cid, limit=30)
    after = engine_state(cid)
    elapsed = time.monotonic() - started
    keep.require(result == '0' and after['ExitCode'] == 0 and after['Status'] == 'exited' and not after['Error']
                 and not after['OOMKilled'] and not after['Dead'] and after['Pid'] == 0 and elapsed <= 40, 'PG_EXIT_POSTCONDITION')
    return {'requestedByUid': 999, 'mode': 'fast', 'waitSeconds': 30, 'observedSeconds': elapsed,
            'exitCode': after['ExitCode'], 'finishedAt': after['FinishedAt'], 'oomKilled': after['OOMKilled']}


@contextmanager
def isolated_server(scratch):
    # 新副本仅通过 Unix socket + OS peer 接受 postgres 本人，原服务与凭证不挂入。
    command = ('umask 077; echo "local fixture postgres peer" > /tmp/peer.conf; '
               'exec postgres -D "$PGDATA" -c listen_addresses= -c unix_socket_directories=/tmp '
               '-c hba_file=/tmp/peer.conf -c ssl=off -c logging_collector=off -c log_destination=stderr '
               '-c log_statement=none -c log_min_messages=log')
    cid = keep.execute('create', '--pull=never', '--network=none', '--read-only', '--restart=no', '--user=999:999',
                       '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=768m', '--memory-swap=768m',
                       '--cpus=1', '--pids-limit=128', '--tmpfs', '/tmp:size=16m,mode=1777', '--log-driver=local',
                       '--label', 'ontology.task-id=' + keep.TASK, '--label', 'ontology.run-id=' + keep.RUN,
                       '--label', keep.LABEL + '=' + keep.ATTEMPT, *keep.mount(scratch, '/var/lib/postgresql', False),
                       '--env', 'LC_ALL=C', '--entrypoint=/bin/sh', IMAGE, '-ec', command)
    keep.record('created-isolated-postgres', cid)
    try:
        keep.assert_owner(cid)
        fmt = '{{.Id}} {{.Image}} {{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{json .HostConfig.PortBindings}}'
        observed = keep.execute('inspect', '-f', fmt, cid).split()
        keep.require(observed[:4] == [cid, IMAGE, 'none', 'true'] and not json.loads(observed[4]), 'PG_COPY_ISOLATION')
        mounts = json.loads(keep.execute('inspect', '-f', '{{json .Mounts}}', cid))
        keep.require([(m.get('Name'), m['Destination'], m['RW']) for m in mounts if m['Type'] != 'tmpfs']
                     == [(scratch, '/var/lib/postgresql', True)], 'PG_COPY_MOUNTS')
        keep.start(cid)
        for _ in range(20):
            ready = subprocess.run([*keep.DOCKER, 'exec', cid, 'pg_isready', '-t', '1', '-h', '/tmp', '-d', 'fixture'],
                                   capture_output=True, timeout=3)
            if ready.returncode == 0:
                break
            keep.require(engine_state(cid)['Running'], 'PG_RECOVERY_START_EXITED')
            time.sleep(.3)
        else:
            raise ValueError('PG_RECOVERY_READY_TIMEOUT')
        yield cid
    finally:
        keep.assert_owner(cid)
        if engine_state(cid)['Running']:
            native_stop(cid)
        keep.record('exited-isolated-postgres', cid, **keep.helper_state(cid))
        keep.execute('rm', cid)
        keep.require(not keep.execute('ps', '-aq', '--no-trunc', '--filter', 'id=' + cid), 'PG_COPY_CONTAINER_REAPPEARED')
        keep.record('removed', cid)


def capture_and_verify():
    keep.require(not PROOF.exists() and keep.digest(cold.FUSEKI_RESUME) == HALT_SHA, 'RECOVERY_PARENT')
    state = json.loads(cold.FUSEKI_RESUME.read_text())
    event = state['stopEvents'][-1]
    row = cold.preexisting()[ORIGINAL]
    source = ORIGINALS / 'source-resources.json'
    keep.require(keep.digest(source) == 'c2b2da05f74c68b7d5a8a0b4af54ffe5af466b57d93b565aa227be8fb34de66a'
                 and json.loads(source.read_text())['resources'][0]['id'] == ORIGINAL, 'SOURCE_ANCHOR')
    keep.require(event['id'] == ORIGINAL and event['after']['ExitCode'] == 1 and row['image'] == IMAGE
                 and row['project'] == keep.PROJECTS[1] and row['service'] == 'pg-source'
                 and cold.read_pin()['id'] == admit.OLD_PIN, 'PG_RECOVERY_IDENTITY')
    cold.original(row, 'exited')
    keep.require([(m['Name'], m['Destination']) for m in row['mounts'] if m['Type'] == 'volume']
                 == [(VOLUME, '/var/lib/postgresql')], 'PG_RECOVERY_VOLUME')
    keep.require(not keep.execute('ps', '-q', '--filter', 'volume=' + VOLUME), 'PG_VOLUME_IN_USE')
    live = set(keep.execute('ps', '-q', '--no-trunc').split())
    keep.require(live == (set(cold.preexisting()) - {e['id'] for e in state['stopEvents']}) | {admit.OLD_PIN}, 'PG_RUNNING_SET')
    memory, cpu = map(int, keep.execute('info', '-f', '{{.MemTotal}} {{.NCPU}}').split())
    caps = sum(int(keep.execute('inspect', '-f', '{{.HostConfig.Memory}}', cid)) for cid in live)
    keep.require(caps + (1280 + 2048) * 1024**2 <= memory and cpu >= 10, 'RECOVERY_HEADROOM')
    directory = keep.private_dir()
    archive = directory / (VOLUME + '.tar')
    with keep.helper(keep.mount(VOLUME, '/source'), image=IMAGE) as reader:
        keep.start(reader)
        keep.require(keep.helper_state(reader)['volumes'] == [[VOLUME, '/source', False]], 'SOURCE_NOT_READONLY')
        before = control(reader, '/source')
        size = int(keep.execute('exec', reader, 'du', '-sb', '/source').split()[0])
        keep.require(size <= 224 * 1024**2 and before == 'in production', 'PG_SOURCE_SIZE_OR_STATE')
        sha = keep.capture(reader, '/source', archive)
        keep.require(keep.volume_digest(reader, '/source') == sha, 'PG_COLD_COPY_CHANGED')
        members = keep.check_archive(archive)
    with keep.scratch() as scratch, keep.helper(keep.mount(scratch, '/slot', False), write=True, image=IMAGE) as writer:
        keep.start(writer)
        keep.restore_empty(writer, archive, sha)
        keep.require(control(writer, '/slot') == before, 'PG_COPY_PRESTATE')
        with isolated_server(scratch) as cid:
            fixtures = check_fixtures(cid)
            exit_facts = native_stop(cid)
            logs = subprocess.run([*keep.DOCKER, 'logs', cid], capture_output=True, check=True, timeout=8)
            raw = logs.stdout + logs.stderr
            markers = {k: needle in raw for k, needle in {
                'interrupted': b'database system was interrupted', 'automaticRecovery': b'automatic recovery in progress',
                'redoStarted': b'redo starts at', 'redoDone': b'redo done at', 'redoNotRequired': b'redo is not required',
                'ready': b'database system is ready to accept connections', 'fast': b'received fast shutdown request',
                'cleanShutdown': b'database system is shut down'}.items()}
            keep.require(all(markers[k] for k in ('interrupted','automaticRecovery','ready','fast','cleanShutdown'))
                         and (markers['redoNotRequired'] or markers['redoStarted'] and markers['redoDone']), 'WAL_MARKERS')
            copy = cid
        keep.require(control(writer, '/slot') == 'shut down', 'PG_RECOVERY_SHUTDOWN_CONTROL')
    cold.original(row, 'exited')
    keep.require(engine_state(ORIGINAL)['FinishedAt'] == event['after']['FinishedAt'] and cold.read_pin()['id'] == admit.OLD_PIN
                 and set(keep.execute('ps', '-q', '--no-trunc').split()) == live, 'ORIGINALS_DRIFTED')
    result = {'taskId': keep.TASK, 'runId': keep.RUN, 'attempt': keep.ATTEMPT, 'parent': HALT_SHA, 'originalId': ORIGINAL,
              'originalExitCode': 1, 'originalFinishedAt': event['after']['FinishedAt'], 'volume': VOLUME, 'image': IMAGE,
              'privatePath': str(archive.relative_to(keep.ROOT)), 'archiveSha256': sha, 'bytes': archive.stat().st_size,
              'mode': '0600', 'members': members, 'isolatedId': copy, 'restoredBytesVerified': True,
              'sourceAndCopyBefore': before, 'copyAfter': 'shut down', 'logsSha256': hashlib.sha256(raw).hexdigest(),
              'walMarkers': markers, 'nativeStop': exit_facts, 'fixtures': fixtures, 'joinAndNullMatched': True,
              'remainingOriginals': sorted(live - {admit.OLD_PIN}), 'pin': admit.OLD_PIN, 'scratchRemoved': True}
    receipt(PROOF, result)
    print('WAL_RECOVERY_REVIEW_READY', keep.digest(PROOF), flush=True)


if __name__ == '__main__':
    import fcntl
    with (keep.BASE / 'm5-source-recovery.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture_and_verify()
