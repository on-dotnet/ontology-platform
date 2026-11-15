"""M4只读运行快照：完整产物清单与来源构建绑定，不共享测试可变bin/obj。"""
import json
import shutil
import platform
from pathlib import Path
from workflow_execution import sha, encoded


def files(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink(): raise ValueError('QUERY_SNAPSHOT_LINK')
        if path.is_file(): result[str(path.relative_to(directory))] = sha(path.read_bytes())
    if not result or not any(name.endswith('.deps.json') for name in result) or not any(name.endswith('.runtimeconfig.json') for name in result):
        raise ValueError('QUERY_SNAPSHOT_INCOMPLETE')
    return result


def freeze(root, source, destination, inputs, command_id, environment=None):
    before = files(source)
    environment = environment or {}
    identity = sha(encoded(dict(files=before, inputs=inputs, commandId=command_id, environment=environment)))
    target = destination/identity
    if target.exists(): raise ValueError('QUERY_SNAPSHOT_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    if before != files(source) or before != files(target): raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
    for path in target.rglob('*'):
        if path.is_file(): path.chmod(0o444)
    row = dict(schemaVersion=1, taskId='G4-M4-QUERY-001', resourceRun='query-impl-01', snapshotId=identity,
               directory=str(target.relative_to(root)), files=before, inputs=inputs, commandId=command_id, environment=environment)
    with (destination/(identity+'.json')).open('x') as stream: json.dump(row, stream, indent=2); stream.write('\n')
    return row


def verify(root, row):
    directory = root/row['directory']
    if row.get('taskId') != 'G4-M4-QUERY-001' or row.get('resourceRun') != 'query-impl-01' or not directory.resolve().is_relative_to(root.resolve()) or directory.is_symlink():
        raise ValueError('QUERY_SNAPSHOT_BOUNDARY')
    if files(directory) != row['files'] or sha(encoded(dict(files=row['files'],inputs=row['inputs'],commandId=row['commandId'],environment=row['environment']))) != row['snapshotId']:
        raise ValueError('QUERY_SNAPSHOT_DRIFT')
    return {str((directory/path).relative_to(root)):digest for path,digest in row['files'].items()}


def demand_mount(root, row, mounts):
    verify(root, row)
    if any(mount['Destination'].startswith('/app/') for mount in mounts): raise ValueError('QUERY_SNAPSHOT_SHADOW_MOUNT')
    app = [mount for mount in mounts if mount['Destination'] == '/app']
    expected = str((root/row['directory']).resolve())
    if len(app) != 1: raise ValueError('QUERY_SNAPSHOT_MOUNT_DRIFT')
    source = app[0]['Source']
    if platform.system() == 'Darwin' and source.startswith('/host_mnt/'): source = source[len('/host_mnt'):]
    if app[0].get('RW') is not False or str(Path(source).resolve()) != expected:
        raise ValueError('QUERY_SNAPSHOT_MOUNT_DRIFT')
