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


def freeze(root, source, destination, inputs, command_id, environment=None, *, task='G4-M4-QUERY-001', run_id='query-impl-01'):
    before = files(source)
    environment = environment or {}
    from workflow_pg_profile import profile
    expected_run = 'implementation-01' if task in ('G4-DORIS-MAPPING-QUERY-001','G4-ORACLE-MAPPING-QUERY-001') else profile(task).run
    if run_id != expected_run and (task,run_id) not in (('G4-DORIS-MAPPING-QUERY-001','review-fix-01'),('G4-ORACLE-MAPPING-QUERY-001','product-resume-01')): raise ValueError('QUERY_SNAPSHOT_TASK_RUN')
    identity_values = dict(files=before, inputs=inputs, commandId=command_id, environment=environment)
    scoped = task in ('G4-M5-INTEGRATION-001','G4-DORIS-MAPPING-QUERY-001','G4-ORACLE-MAPPING-QUERY-001')
    if scoped: identity_values.update(taskId=task, resourceRun=run_id)
    identity = sha(encoded(identity_values))
    target = destination/identity
    if target.exists(): raise ValueError('QUERY_SNAPSHOT_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    if before != files(source) or before != files(target): raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
    for path in target.rglob('*'):
        if path.is_file(): path.chmod(0o444)
    row = dict(schemaVersion=2 if scoped else 1, taskId=task, resourceRun=run_id, snapshotId=identity,
               directory=str(target.relative_to(root)), files=before, inputs=inputs, commandId=command_id, environment=environment)
    with (destination/(identity+'.json')).open('x') as stream: json.dump(row, stream, indent=2); stream.write('\n')
    return row


def verify(root, row, *, task='G4-M4-QUERY-001', run_id='query-impl-01'):
    directory = root/row['directory']
    if row.get('taskId') != task or row.get('resourceRun') != run_id or not directory.resolve().is_relative_to(root.resolve()) or directory.is_symlink():
        raise ValueError('QUERY_SNAPSHOT_BOUNDARY')
    identity_values = dict(files=row['files'],inputs=row['inputs'],commandId=row['commandId'],environment=row['environment'])
    if task in ('G4-M5-INTEGRATION-001','G4-DORIS-MAPPING-QUERY-001','G4-ORACLE-MAPPING-QUERY-001'):
        expected_run = 'integration-01' if task=='G4-M5-INTEGRATION-001' else 'implementation-01'
        if row.get('schemaVersion') != 2 or (run_id != expected_run and (task,run_id) not in (('G4-DORIS-MAPPING-QUERY-001','review-fix-01'),('G4-ORACLE-MAPPING-QUERY-001','product-resume-01'))): raise ValueError('QUERY_SNAPSHOT_TASK_RUN')
        expected = root/'artifacts/workflow'/task/run_id/'runtime-snapshots'/row['snapshotId']
        if directory != expected or any(p.is_symlink() for p in [directory,*directory.parents]): raise ValueError('QUERY_SNAPSHOT_BOUNDARY')
        identity_values.update(taskId=task,resourceRun=run_id)
    if files(directory) != row['files'] or sha(encoded(identity_values)) != row['snapshotId']:
        raise ValueError('QUERY_SNAPSHOT_DRIFT')
    return {str((directory/path).relative_to(root)):digest for path,digest in row['files'].items()}


def demand_mount(root, row, mounts, *, task='G4-M4-QUERY-001', run_id='query-impl-01'):
    verify(root, row, task=task, run_id=run_id)
    if any(mount['Destination'].startswith('/app/') for mount in mounts): raise ValueError('QUERY_SNAPSHOT_SHADOW_MOUNT')
    app = [mount for mount in mounts if mount['Destination'] == '/app']
    expected = str((root/row['directory']).resolve())
    if len(app) != 1: raise ValueError('QUERY_SNAPSHOT_MOUNT_DRIFT')
    source = app[0]['Source']
    if platform.system() == 'Darwin' and source.startswith('/host_mnt/'): source = source[len('/host_mnt'):]
    if app[0].get('RW') is not False or str(Path(source).resolve()) != expected:
        raise ValueError('QUERY_SNAPSHOT_MOUNT_DRIFT')
