"""本任务八个易失卷的私有原件与隔离同 ID 恢复演练。此入口没有处置旧容器的命令。"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid

from doris_keep_drain import drained, retain_error


ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-DORIS-MAPPING-QUERY-001'
RUN = 'implementation-01'
REVIEW = ROOT / 'docs/evidence' / TASK / RUN / 'r0-review.json'
BASE = ROOT / 'artifacts/workflow' / TASK / 'cold-save-01'
PRIVATE = ROOT / '.tools/security/g4-doris-mapping-query-001/cold-save-01'
PROJECTS = ('ontology-g4-m4-query-impl-01', 'ontology-g4-m5-integration-01')
MOUNTS = {'api-keyring': '/keyring', 'keycloak-data': '/opt/keycloak/data', 'rustfs-data': '/data', 'fuseki-data': '/fuseki'}
IMAGE = 'sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6'
DOCKER = ['docker', '--context', 'desktop-linux']
TAR = ['tar', '--format=posix', '--sort=name', '--numeric-owner', '--acls', '--xattrs', '--xattrs-include=*',
       '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime', '--one-file-system', '-cpf', '-']
EXTRACT = ['tar', '--numeric-owner', '--same-owner', '--same-permissions', '--acls', '--xattrs', '--xattrs-include=*', '-xpf', '-', '-C', '/slot']
LABEL = 'ontology.keep-attempt'
KEEPER = 'i=0; while test ! -f /control/finish && test "$i" -lt 840; do sleep 1; i=$((i+1)); done; test -f /control/finish'
ATTEMPT = uuid.uuid4().hex
JOURNAL = []


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def archive_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024**2, 256 * 1024**2))


def execute(*args, output=None, source=None, limit=35):
    result = subprocess.run([*DOCKER, *args], stdin=source or subprocess.DEVNULL,
                            stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, timeout=limit,
                            preexec_fn=archive_limit if output is not None else None)
    retain_error(result.stderr)
    require(result.returncode == 0, 'DOCKER_' + args[0].upper() + '_EXIT_' + str(result.returncode))
    if output is None:
        return result.stdout.decode().strip()


def record(action, identity, **facts):
    JOURNAL.append({'action': action, 'id': identity, 'time': time.time(), **facts})
    (BASE / (ATTEMPT + '-lifecycle.json')).write_text(json.dumps(JOURNAL, indent=2) + '\n')


def inventory(stopped=()):
    raw = REVIEW.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == 'a6dd11f647f351dc0025cc2907b20671beb069289fba7108feb756d690c16e87',
            'APPROVED_INVENTORY_CHANGED')
    rows = json.loads(raw)['reviewedResources']
    expected = sorted(p + '_' + suffix for p in PROJECTS for suffix in MOUNTS)
    seen = set()
    require(len(rows) == len({r['containerId'] for r in rows}) == 14, 'ALLOWLIST_COUNT')
    for row in rows:
        id_ = row['containerId']
        fmt = ('{{.Id}} {{.Image}} {{.State.Status}} {{index .Config.Labels "ontology.task-id"}} '
               '{{index .Config.Labels "ontology.run-id"}} {{index .Config.Labels "com.docker.compose.project"}} '
               '{{index .Config.Labels "com.docker.compose.service"}}')
        require(execute('inspect', '-f', fmt, id_).split() ==
                [id_, row['imageId'], 'exited' if id_ in stopped else 'running', *row['taskRunProject'].split(), row['service']], 'OWNER_OR_STATE')
        for mount in json.loads(execute('inspect', '-f', '{{json .Mounts}}', id_)):
            if mount['Destination'] in MOUNTS.values():
                suffix = next(k for k, v in MOUNTS.items() if v == mount['Destination'])
                name = row['project'] + '_' + suffix
                require(name in expected and mount.get('Name') == name and
                        name + ' local tmpfs' in row['volumeMedia'], 'REVIEWED_MOUNT')
                require(execute('volume', 'inspect', '-f', '{{.Driver}} {{index .Options "type"}}', name)
                        == 'local tmpfs', 'TMPFS_EXPECTED')
                seen.add(name)
    require(sorted(seen) == expected, 'EIGHT_REQUIRED')
    return rows, expected


def private_dir():
    os.umask(0o077)
    require(PRIVATE.resolve() == PRIVATE and BASE.resolve() == BASE, 'LINKED_DIRECTORY')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in (PRIVATE.parent.parent, PRIVATE.parent, PRIVATE):
        require(path.stat().st_uid == os.getuid() and stat.S_IMODE(path.stat().st_mode) == 0o700, 'PRIVATE_MODE')
    require(shutil.disk_usage(PRIVATE).free >= 2 * 1024**3, 'DISK_RESERVE')
    path = PRIVATE / ATTEMPT
    path.mkdir(mode=0o700)
    return path


def mount(name, destination, readonly=True):
    return ['--mount', f'type=volume,src={name},dst={destination},volume-nocopy' + (',readonly' if readonly else '')]


def assert_owner(cid):
    require(execute('inspect', '-f', '{{.Id}} {{index .Config.Labels "ontology.keep-attempt"}}', cid)
            == cid + ' ' + ATTEMPT, 'HELPER_IDENTITY')


def helper_state(cid):
    assert_owner(cid)
    state = json.loads(execute('inspect', '-f', '{{json .State}}', cid))
    mounts = json.loads(execute('inspect', '-f', '{{json .Mounts}}', cid))
    return {'state': {k: state[k] for k in ('Status', 'Running', 'ExitCode', 'OOMKilled', 'StartedAt', 'FinishedAt')},
            'volumes': [[m['Name'], m['Destination'], m['RW']] for m in mounts if m['Type'] == 'volume']}


def start(cid):
    assert_owner(cid)
    execute('start', cid)
    require(execute('inspect', '-f', '{{.State.Running}}', cid) == 'true', 'HELPER_START')
    record('started', cid, **helper_state(cid))


def finish(cid):
    assert_owner(cid)
    if execute('inspect', '-f', '{{.State.Running}}', cid) == 'true':
        execute('exec', cid, 'touch', '/control/finish')
        require(execute('wait', cid, limit=10) == '0', 'HELPER_EXIT')
    record('released', cid, **helper_state(cid))


@contextlib.contextmanager
def helper(mounts, write=False):
    flags = ['--cap-add=CHOWN', '--cap-add=FOWNER', '--cap-add=DAC_OVERRIDE'] if write else ['--cap-add=DAC_READ_SEARCH']
    args = ['--pull=never', '--network=none', '--read-only', '--cap-drop=ALL', *flags, '--security-opt=no-new-privileges',
            '--user=0:0', '--memory=512m', '--memory-swap=512m', '--cpus=0.5', '--pids-limit=24', '--log-driver=none',
            '--tmpfs', '/var/lib/postgresql:size=1m', '--tmpfs', '/control:size=1m,mode=0700',
            '--label', 'ontology.task-id=' + TASK, '--label', 'ontology.run-id=' + RUN,
            '--label', LABEL + '=' + ATTEMPT, *mounts, '--entrypoint=/bin/sh', IMAGE, '-ec', KEEPER]
    cid = execute('create', *args)
    require(bool(re.fullmatch('[0-9a-f]{64}', cid)), 'HELPER_CONTAINER_ID')
    record('created', cid)
    try:
        yield cid
    finally:
        finish(cid)
        execute('rm', cid)
        require(cid not in execute('ps', '-aq', '--no-trunc', '--filter', 'id=' + cid).split(), 'HELPER_REMOVE')
        record('removed', cid)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_archive(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1 and
            stat.S_IMODE(path.stat().st_mode) == 0o600, 'ARCHIVE_PERMISSIONS')
    # 解包前仅接受普通文件和目录，禁止链接、设备、路径穿越和重复成员。
    names = set()
    expanded = 0
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            key = PurePosixPath(member.name)
            require(not key.is_absolute() and '..' not in key.parts and key not in names and
                    (member.isfile() or member.isdir()), 'ARCHIVE_MEMBER_TYPE_OR_PATH')
            expanded += member.size
            require(expanded <= 256 * 1024**2 and len(names) < 20000, 'EXPANSION_LIMIT')
            names.add(key)
    require(PurePosixPath('.') in names, 'ARCHIVE_ROOT_MISSING')
    return len(names)


def capture(cid, directory, path):
    with path.open('xb') as stream:
        execute('exec', cid, *TAR, '-C', directory, '.', output=stream, limit=70)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(path)


def volume_digest(cid, directory):
    # 二进制仅在容器内流向 sha256sum；分别检查 tar 和摘要进程的结果。
    command = 'set -o pipefail; "$@" | sha256sum'
    raw = execute('exec', cid, 'bash', '-ec', command, 'hash', *TAR, '-C', directory, '.', limit=70)
    value = raw.split()[0]
    require(bool(re.fullmatch('[a-f0-9]{64}', value)), 'VOLUME_DIGEST')
    return value


@contextlib.contextmanager
def scratch():
    name = 'dmq-rehearsal-' + ATTEMPT + '-' + uuid.uuid4().hex[:8]
    require(not execute('volume', 'ls', '-q', '--filter', 'name=^' + name + '$'), 'SCRATCH_EXISTS')
    result = execute('volume', 'create', '--driver', 'local', '--opt', 'type=tmpfs', '--opt', 'device=tmpfs',
                     '--opt', 'o=size=256m', '--label', 'ontology.task-id=' + TASK, '--label',
                     'ontology.run-id=' + RUN, '--label', LABEL + '=' + ATTEMPT, name)
    require(result == name, 'SCRATCH_NAME')
    record('created-volume', name)
    try:
        yield name
    finally:
        require(execute('volume', 'inspect', '-f', '{{index .Labels "ontology.keep-attempt"}}', name) == ATTEMPT, 'SCRATCH_OWNER')
        attached = execute('ps', '-aq', '--no-trunc', '--filter', 'volume=' + name)
        if attached:
            record('retained-attached-scratch', name)
            raise ValueError('SCRATCH_STILL_ATTACHED')
        require(execute('volume', 'rm', name) == name, 'SCRATCH_REMOVE')
        require(not execute('volume', 'ls', '-q', '--filter', 'name=^' + name + '$'), 'SCRATCH_REAPPEARED')
        record('removed-volume', name)


def restore_empty(cid, path, expected):
    check_archive(path)
    require(digest(path) == expected, 'BACKUP_HASH_MISMATCH')
    execute('exec', cid, 'sh', '-ec', 'test -z "$(find /slot -mindepth 1 -print -quit)"')
    with path.open('rb') as stream:
        execute('exec', '-i', cid, *EXTRACT, source=stream, limit=70)
    require(volume_digest(cid, '/slot') == expected, 'EXTRACTION_MISMATCH')


def rehearse(paths, facts, checkpoint):
    with scratch() as name, helper(mount(name, '/slot', False), write=True) as writer, helper(mount(name, '/slot')) as consumer:
        start(writer)
        execute('exec', writer, 'touch', '/slot/proof-of-prior-mount')
        start(consumer)
        execute('exec', consumer, 'test', '-f', '/slot/proof-of-prior-mount')
        finish(writer)
        finish(consumer)
        for volume, path in paths.items():
            if volume not in facts:
                continue
            checkpoint()
            start(writer)
            restore_empty(writer, path, facts[volume]['sha256'])
            start(consumer)
            finish(writer)
            require(volume_digest(consumer, '/slot') == facts[volume]['sha256'], 'SAME_ID_READBACK')
            finish(consumer)
            facts[volume]['isolatedSameId'] = consumer
            record('verified-same-id-' + volume, consumer)


def run(mode):
    BASE.mkdir(parents=True, exist_ok=True)
    rows, volumes = inventory()
    with drained(rows) as (drain, checkpoint):
        if mode == 'drain-check':
            drain['end'] = checkpoint()
            return {'boundedAdmission': drain, 'rollbackOnExit': True}
        memory, cpu = map(int, execute('info', '-f', '{{.MemTotal}} {{.NCPU}}').split())
        # 采集与恢复阶段串行；恢复至多两个 512 MiB helper，原栈 12 GiB，保留 2 GiB。
        require(memory >= 15 * 1024**3 and cpu >= 10 and
                set(execute('ps', '-q', '--no-trunc').split()) == {r['containerId'] for r in rows}, 'VM_RESERVE')
        execute('image', 'inspect', '-f', '{{.Id}}', IMAGE)
        directory = private_dir()
        paths = {v: directory / (v + '.tar') for v in volumes}
        facts = {}
        failures = {}
        mounts = [arg for i, v in enumerate(volumes) for arg in mount(v, '/v' + str(i))]
        with helper(mounts) as reader:
            start(reader)
            sizes = [int(execute('exec', reader, 'du', '-sb', '/v' + str(i)).split()[0]) for i in range(8)]
            used = sum(f.stat().st_size for f in PRIVATE.rglob('*.tar'))
            require(max(sizes) < 224 * 1024**2 and used + sum(sizes) + 64 * 1024**2 < 2 * 1024**3, 'ARCHIVE_CAPACITY')
            for i, volume in enumerate(volumes):
                checkpoint()
                path = paths[volume]
                try:
                    hashed = capture(reader, '/v' + str(i), path)
                    require(volume_digest(reader, '/v' + str(i)) == hashed, 'LIVE_VOLUME_CHANGED')
                    facts[volume] = {'sha256': hashed, 'bytes': path.stat().st_size, 'members': check_archive(path),
                                     'privatePath': str(path.relative_to(ROOT)), 'mode': '0600'}
                except ValueError as error:
                    failures[volume] = str(error)
                (BASE / (ATTEMPT + '-capture.json')).write_text(json.dumps(
                    {'attempt': ATTEMPT, 'liveCopies': facts, 'failed': failures}, indent=2) + '\n')
        if facts:
            rehearse(paths, facts, checkpoint)
        drain['end'] = checkpoint()
        return {'attempt': ATTEMPT, 'boundedAdmission': drain, 'volumeFacts': facts,
                'status': 'PARTIAL' if failures else 'PASS', 'failedVolumes': failures,
                'originalStops': 0, 'consistency': 'LIVE_TWO_READS_AND_ISOLATED_ARCHIVE_ROUND_TRIP',
                'applicationConsistency': 'NOT_VERIFIED', 'r0Qualification': 'BLOCKED',
                'sameIdScope': 'ISOLATED_MOUNT_CONSUMER_ONLY', 'originalRecovery': 'NOT_RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['drain-check', 'capture-rehearse'])
    args = parser.parse_args()
    try:
        data = run(args.mode)
    except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        # 容器错误流可能有私有文件名，仅公布预定义失败码。
        reason = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_-]+', str(error)) else type(error).__name__
        data = {'status': 'FAILED', 'reason': reason, 'attempt': ATTEMPT}
    else:
        data.setdefault('status', 'PASS')
    (BASE / (ATTEMPT + '-' + args.mode + '.json')).write_text(json.dumps(data, indent=2) + '\n')
    print(args.mode, ATTEMPT, data['status'], data.get('reason', ''))
    sys.exit(0 if data['status'] == 'PASS' else 2)
