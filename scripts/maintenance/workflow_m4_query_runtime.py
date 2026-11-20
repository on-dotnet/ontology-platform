"""M4只读运行快照：完整产物清单与来源构建绑定，不共享测试可变bin/obj。"""
import json
import os
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


def _resume_snapshot(root, source, destination, row, remaining):
    """只授信同一产品轮、同一输入的封存字节，目录完整后才登记快照。"""
    import tempfile
    from workflow_execution import ordinary

    ordinary(source)
    ordinary(destination)
    identity = row['snapshotId']
    target = root/row['directory']
    receipt = ordinary(destination/(identity+'.json'))
    scope = dict(task=row['taskId'], run_id=row['resourceRun'])
    if destination != root/'artifacts/workflow'/scope['task']/scope['run_id']/'runtime-snapshots':
        raise ValueError('QUERY_SNAPSHOT_BOUNDARY')

    def validate(saved):
        verify(root, saved, **scope)
        if any((root/saved['directory']/name).stat().st_mode & 0o777 != 0o444 for name in saved['files']):
            raise ValueError('QUERY_SNAPSHOT_WRITABLE')

    if receipt.exists():
        saved = json.loads(receipt.read_bytes())
        if saved != row:
            raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
        validate(saved)
        return saved

    destination.mkdir(parents=True, exist_ok=True)
    peers = {}
    for path in sorted(destination.glob('*.json')):
        saved = json.loads(ordinary(path).read_bytes())
        if saved.get('inputs', {}).get('inputKey') != row['inputs']['inputKey']:
            continue
        if path.stem != saved.get('snapshotId'):
            raise ValueError('QUERY_SNAPSHOT_BOUNDARY')
        validate(saved)
        for name, digest in saved['files'].items():
            if row['files'].get(name) == digest:
                peers[name] = root/saved['directory']/name

    # 每项预留目录元数据，另计普通复制的逻辑长度（稀疏文件亦然）与登记原件。
    storage = os.statvfs(destination)
    block = max(storage.f_frsize or storage.f_bsize, 4096)
    directories = {parent for name in row['files'] for parent in Path(name).parents}
    receipt_bytes = (json.dumps(row, indent=2)+'\n').encode()
    estimate = block*(8+2*(len(directories)+len(row['files']))) + len(receipt_bytes)
    stage = ordinary(destination/('.refresh-'+identity))
    completed = set()
    if not target.exists():
        for name, digest in row['files'].items():
            member = ordinary(stage/name)
            if member.is_file() and sha(member.read_bytes()) == digest:
                if member.stat().st_mode & 0o777 != 0o444:
                    if member.stat().st_nlink != 1:
                        raise ValueError('QUERY_SNAPSHOT_PARTIAL_DRIFT')
                    member.chmod(0o444)
                completed.add(name)
            elif name not in peers:
                estimate += ((source/name).stat().st_size+block-1)//block*block
    if remaining is not None and estimate > remaining:
        raise ValueError('PRODUCT_SNAPSHOT_BUDGET')

    if not target.exists():
        # 断点暂存区只属于当前 identity。先验证每个已完成成员，再继续缺失的成员。
        stage.mkdir(exist_ok=True)
        for name, digest in row['files'].items():
            member = ordinary(stage/name)
            member.parent.mkdir(parents=True, exist_ok=True)
            if name in completed:
                continue
            if member.exists():
                if not member.is_file() or member.stat().st_nlink != 1 or member.stat().st_mode & 0o222 == 0:
                    raise ValueError('QUERY_SNAPSHOT_PARTIAL_DRIFT')
                member.unlink()  # 唯一可写暂存副本，可能中断在 copyfile 中。
            if name in peers:
                os.link(peers[name], member)
            else:
                with (source/name).open('rb') as origin, member.open('xb') as copied:
                    shutil.copyfileobj(origin, copied)
                if sha(member.read_bytes()) != digest:
                    raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
                member.chmod(0o444)
        if files(stage) != row['files'] or files(source) != row['files']:
            raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
        stage.rename(target)
    validate(row)
    # 只有完整目录才可见为可共享来源。落盘后用不覆盖的链接提交登记。
    with tempfile.NamedTemporaryFile(dir=destination, prefix='.refresh-receipt-',delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(receipt_bytes)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(pending, receipt)
        finally:
            pending.unlink(missing_ok=True)
    return row


def freeze(root, source, destination, inputs, command_id, environment=None, *, remaining_bytes=None, task='G4-M4-QUERY-001', run_id='query-impl-01'):
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
    if (task,run_id)==('G4-ORACLE-MAPPING-QUERY-001','product-resume-01'):
        row = dict(schemaVersion=2, taskId=task, resourceRun=run_id, snapshotId=identity,
                   directory=str(target.relative_to(root)), files=before, inputs=inputs, commandId=command_id, environment=environment)
        return _resume_snapshot(root, source, destination, row, remaining_bytes)
    if target.exists(): raise ValueError('QUERY_SNAPSHOT_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    if before != files(source) or before != files(target): raise ValueError('QUERY_SNAPSHOT_BUILD_DRIFT')
    for path in target.rglob('*'):
        if path.is_file() and path.stat().st_mode & 0o777!=0o444: path.chmod(0o444)
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
