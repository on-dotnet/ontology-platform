"""仅重开 d368 的专用源代次及生产者封闭原件；不执行数据库事务。"""
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import workflow_execution as ex
import workflow_oracle_mapping_access_refresh as refresh
import workflow_oracle_mapping_continuity as continuity
import workflow_oracle_runtime_window as window
from workflow_oracle_mapping_evidence import DRIVER, NODE, Originals, utc, verify_product_manifest
from workflow_oracle_mapping_resources import require
from workflow_oracle_mapping_s2 import runtime_invocation

ROOT = window.ROOT
TASK, RUN, BATCH = window.TASK, window.RUN, window.BATCH
AREA = continuity.AREA / BATCH
QUERY = 'query-d368ac610c7745889890e1589653af8f'
SOURCE = '65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1'
PG = continuity.PG
FORMAL = 'd1befd6fdf7cc5b531ab04e6802e460e947a804863d9f99bc9fafa42ba1aaf05'
RESTORED = '21d6d0cff882452f4e810c28e59e82418fbb31a30ea9c40d74849f29dc48776e'
PARENT = 'c02e89f8d8f2481f90058606ccf71b29'
CHILD = '5b90bb8f66fb4ddd9bfeddbe5015133a'
HOST = '21bee974f26e4ed4a8f7f3f623189bdf'
DOCKER = ['docker', '--context', 'desktop-linux']
ORIGINAL_CASE = 'c199b2b59310f875718d6655c5b91e5d089d2ce296f39fd5518f95b91c118de9'
SQLPLUS = [*DOCKER, 'exec', '-i', SOURCE, 'sqlplus', '-s', '/ as sysdba']
SHUTDOWN = b'whenever sqlerror exit failure\nshutdown immediate;\nexit success\n'
STOP_PAIRS = (
    ('1fed01a16b5447bfa1ed0efe1229692f', '94eaf05970dd4f558bbc45577f5ec887'),
    ('83907abf18554ff39bf770ec71935534', '16c17ac198d047459b2457cff1fb34f2'),
    ('eb499b6a2a764278bf608cb8ac6fd7a4', '6378711b6ebd47aeacc36d6a570d0911'),
)
FROZEN_ROW = {
    'systemIdentifier': '7709907053089669168', 'database': 'mapping', 'databaseUser': 'postgres',
    'queryId': QUERY, 'organizationId': 'org-demo', 'connectionId': 'a7913bb552eb4cd1a3f6eaf5b93cd619',
    'ownerSha256': '8fdc75f71c16c2972b1ab468d7a7ee79726888b2b45adc5970255183e569f013',
    'fence': 2, 'status': 'FAILED', 'cancelRequested': False,
    'createdUtc': '2026-11-21T13:52:17.360623+00:00', 'deadlineUtc': '2026-11-21T13:52:21.635112+00:00',
    'completedUtc': '2026-11-21T13:52:21.897952+00:00', 'leaseUntilUtc': '2026-11-21T13:52:21.635112+00:00',
    'requestSha256': 'e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd',
    'bindingSha256': 'f9791b46957e72f0240a2bb8861d7cf7d58856136905e151c0c7c6be377b4a0a',
    'stableRowSha256': 'c7e08ef5d06001addd262eb403a8d86cca760efffc172f675d5c4ff9956e3bf6',
    'resultHash': None, 'resultSize': 0, 'resultCiphertextLength': 0,
}
AUDIT_ID = '83330a307d7a4583aa44e7c2a6db4fa4'
AUDIT_SHA = 'ccad5f400813da2d9e641b2a2ba59af8dba87b41a5320e5bd095e40ee975d3c4'
BASELINE_RUNNING = {
    '57ef8d99c6eb37eb4681f9ae707537de93b556218394ad54c8703b2f2b2f5ce9',
    '3f1502f453da342d8cd57ab6514852d1fa06007baad709156abb7da0e5e2647f',
    'd3f2a4b9dd9d06bf3141e35c80b4c96246b47cc81092762f88171bf57dff5e04',
}


def digest(value):
    return ex.sha(ex.encoded(value))


def failed_command(archive, cid, argv, stage, key, parent, deadline, code):
    """旧父与真实 docker exec 均应为已退出的准确失败命令。"""
    class Streams(Originals):
        def __init__(self):
            self.root = ROOT

        def raw(self, name):
            files = {cid + '-' + item: item for item in ('receipt.json', 'stdout.txt', 'stderr.txt')}
            base = continuity.AREA.parent / 'commands' / RUN / cid
            return continuity.raw(ROOT, base / files[name], archive)

    row, _, _ = Streams().command(cid, argv, stage, key, parent, ROOT, command_run=RUN)
    require((row['classification'], row['exitCode'], row['deadlineSeconds']) == ('EXIT_FAILURE', code, deadline),
            'D368_PRODUCER_EXIT')
    return row


def historical_row(archive):
    """重新推导旧查询三条只读 SQL，检查全集并仅返回公开值。"""
    import workflow_oracle_access_maintenance as old
    receipts = f"""SELECT json_array_length(convert_from("BindingBytes",'UTF8')::json->'receipts') FROM semantic_query."Queries" WHERE "Id"='{QUERY}';"""
    sql = (
        ('row', '2ebff1911c1f4f348afc5858bbf42bda', old.ROW_SQL.replace(old.QUERY, QUERY)),
        ('audit', '2c29461d61d34cafb3b39b1aa3a0abdf', old.AUDIT_SQL.replace(old.QUERY, QUERY)),
        ('receipts', '70d2fcb66aad4508b51522134083fbb2', receipts),
    )
    argv = [*DOCKER, 'exec', '-i', '--user', 'postgres', PG, 'psql', '-XwqAt', '-d', 'mapping', '-v', 'ON_ERROR_STOP=1']
    values = []
    for label, cid, statement in sql:
        _, data, _ = continuity.command(ROOT, cid, RUN, argv, 'omq-pg-aba-maint-' + label,
                                         ex.sha(b'BEGIN READ ONLY;\n' + statement.encode() + b'\nCOMMIT;'), 15, archive)
        values.append(json.loads(data))
    row, audits, count = values
    row['ownerSha256'] = ex.sha(row.pop('owner').encode())
    require(row == FROZEN_ROW and count == 0 and len(audits) == 1 and
            [audits[0][key] for key in ('id', 'action', 'outcome', 'sha256')] ==
            [AUDIT_ID, 'data.query.execute', 'failure', AUDIT_SHA], 'D368_FROZEN_ROW')
    return dict(row=row, failureAuditId=AUDIT_ID, failureAuditSha256=AUDIT_SHA, readReceipts=count)


def shutdown_chain(archive):
    result = []
    for command_id, state_id in STOP_PAIRS:
        row, out, _ = continuity.command(ROOT, command_id, continuity.RECOVERY, SQLPLUS, 'omq-recovery-oracle-shutdown',
                                         ex.sha(ex.encoded(SQLPLUS) + SHUTDOWN), 90, archive)
        require(all(marker in out.lower() for marker in
                    (b'database closed', b'database dismounted', b'oracle instance shut down')), 'D368_SHUTDOWN')
        _, out, _ = continuity.lifecycle_command(ROOT, state_id, 'oracle', SOURCE, 'stopped', archive)
        state = json.loads(out)
        require(state['Status'] == 'exited' and state['Pid'] == 0 and not state['Error'] and not state['OOMKilled']
                and utc(state['StartedAt']) < utc(row['startedAtUtc']) <= utc(row['endedAtUtc']) <= utc(state['FinishedAt'])
                and (not result or utc(result[-1]['finishedAt']) < utc(state['StartedAt'])), 'D368_GENERATIONS')
        result.append(dict(shutdown=command_id, state=state_id, startedAt=state['StartedAt'], finishedAt=state['FinishedAt']))
    return result


def source_code(commit):
    """按实测提交重开固定 TCPS、实体/关系两表 SQL、原 DDL 与后台执行边界。"""
    adapters = 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/'
    files = {
        adapters + 'OracleQueryReader.cs': '39bba37aa406c830001ea10aef8af921cef4dac5999305a88b42aa6d3de9dc68',
        adapters + 'OracleSourceAdapter.cs': '61b885b9e8020b8419a17abf945545ee689fd295d2c7a169a70d913c8bf44e50',
        adapters + 'OracleSourceAdapter.Mapping.cs': '606a78e2f22db57de58b2672144871893c8211785e9418fe396a87d43a13014d',
        adapters + 'OracleMappingSourceValidator.cs': 'd04abc7587331c09f2352dc4c7bf686b9318a139a36360b03a06c35ab8e2e5d1',
        'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/OracleAdapterOptions.cs':
            '9428285e07030b6c925165af24fa983c4e91897b159f0dfd2f402ddc28a9c541',
        'backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryWorker.cs':
            'e568af93d25083c2fd3c7b36e7a4fd8df487f422b6f4816bc9c4e523868b94c2',
        'infra/oracle/config/mapping-query.sql': 'e32ab651866be8e95a8239000201637451bfd499c5427f39b448fd809fe4c835',
    }
    for path, expected in files.items():
        raw = subprocess.check_output(['git', 'cat-file', 'blob', commit + ':' + path], cwd=ROOT, timeout=5)
        require(ex.sha(raw) == expected, 'D368_SOURCE_BYTES')
    return files


def origin(archive, formal):
    raw = continuity.raw(ROOT, AREA / ('runtime-aba-' + CHILD + '.json'), archive)
    require(ex.sha(raw) == ORIGINAL_CASE, 'D368_ORIGINAL_CASE')
    case = json.loads(raw)
    host = case['host']
    require((host['commandId'], host['oracle']['containerId'], case['commandId']) == (HOST, SOURCE, CHILD), 'D368_HOST')
    _, rows = refresh.observed_rows(ROOT, host, archive)
    builds = refresh.snapshot_builds(ROOT, host, archive)
    target = formal['apis']['api-secondary']['id']
    require(rows['api-secondary']['containerId'] == target and rows['oracle']['startedAt'] == formal['data']['oracle']['startedAt']
            and rows['oracle']['networks'].items() <= rows['api-secondary']['networks'].items()
            and len(rows['oracle']['networks']) == 1 and case['input'] == builds['agent']['build'], 'D368_SCOPE')
    dispatch_raw = continuity.raw(ROOT, continuity.AREA / ('formal-run-s2-s3-oracle-' + PARENT + '.json'), archive)
    require(ex.sha(dispatch_raw) == 'fc2eb71f7601a7ad580d47229e3bf1cd8cba0f4acbd87c130432dbff8176b414', 'D368_DISPATCH')
    dispatch = json.loads(dispatch_raw)
    measured = '851906f140c0defc0201b392e838e191b20afa27'
    require(dispatch['commandId'] == PARENT and dispatch['testedCommit'] == measured and dispatch['exitCode'] == 1
            and dispatch['host']['services'] == host['services'], 'D368_PARENT_HOST')
    code = source_code(measured)
    formal_raw = continuity.raw(ROOT, AREA / 'controlled-run-9b81d52b3b7041ecb7b8530198d77ccd.json', archive)
    require(ex.sha(formal_raw) == FORMAL, 'D368_FORMAL')
    aba = json.loads(formal_raw)['aba']
    require((aba['commandId'], aba['queryId'], aba['exitCode']) == (CHILD, QUERY, 2), 'D368_Q_BINDING')
    manifest = continuity.raw(ROOT, continuity.AREA / ('formal-resources-' + host['resourceManifestSha256'] + '.json'), archive)
    verify_product_manifest(host, json.loads(manifest), ex.sha(manifest))
    compose = continuity.raw(ROOT, continuity.AREA / ('formal-api-compose-' + host['composeSha256'] + '.json'), archive)
    spec = json.loads(compose)
    require(ex.sha(compose) == host['composeSha256'] and set(spec['services']) == {'api', 'api-secondary'}
            and set(rows['oracle']['networks']) == {spec['networks']['source-internal']['name']}, 'D368_SOURCE_NETWORK')
    for destination, service in [('/session-tests','agent'), ('/app','api'), ('/query-tests','query')]:
        path = str(ROOT / builds[service]['directory'])
        selected = [m for m in rows['api-secondary']['mounts']
                    if m['Destination'] == destination or m['Destination'].startswith(destination + '/')]
        require(len(selected) == 1 and selected[0]['Destination'] == destination and selected[0]['Type'] == 'bind'
                and not selected[0]['RW'] and selected[0]['Source'].removeprefix('/host_mnt') == path
                and spec['services']['api-secondary']['volumes'].count(path + ':' + destination + ':ro') == 1,
                'D368_TEST_MOUNT')
    parent_args = [NODE, DRIVER, '--task', TASK, '--run-id', RUN, '--mode', 's2-s3-oracle', '--batch-input',
                   's2-s3-d102288604bb4000b5a04f86d0395e22.json']
    parent = failed_command(archive, PARENT, parent_args, 'omq-browser-s2-s3-oracle',
                            '417b36e482582e16bfddf5f4a211d8f1b425dd5819ad77e07508dcbdf8bc0791',
                            'cba3d44f0e7843d09323b4f83bd5e51b', 2340, 1)
    child = failed_command(archive, CHILD, runtime_invocation(target, case['nonce'], 'aba'), 'query-real-aba-inflight-runtime',
                           digest(case['input']), HOST, 25, 2)
    require(utc(parent['startedAtUtc']) <= utc(child['startedAtUtc']) < utc(FROZEN_ROW['createdUtc']) <
            utc(child['endedAtUtc']) <= utc(parent['endedAtUtc']) <= utc(formal['data']['oracle']['after']['FinishedAt']),
            'D368_PRODUCER_ORDER')
    return dict(parent=PARENT, child=CHILD, host=HOST, secondary=target, source=SOURCE, networks=rows['oracle']['networks'],
                measuredCommit=measured, sourceCode=code, composeSha256=host['composeSha256'],
                mountsSha256=digest(rows['oracle']['mounts']), snapshots={k:v['snapshotId'] for k,v in builds.items()},
                parentExitedAtUtc=parent['endedAtUtc'], childExitedAtUtc=child['endedAtUtc'])


def live_state(restored, old_apis, pg_start_command, archive):
    """只向 Docker 请求当前状态和别名；进程查询只取匹配 PID。"""
    def docker(*args):
        return subprocess.check_output([*DOCKER, *args], cwd=ROOT, timeout=10, text=True).strip()

    expected = BASELINE_RUNNING | ({PG} if pg_start_command is not None else set())
    require(set(docker('ps', '-q', '--no-trunc').splitlines()) == expected, 'D368_RUNNING_SET')
    ids = set(docker('ps', '-aq', '--no-trunc').splitlines())
    require(not ids.intersection(old_apis), 'D368_API_PRESENT')
    fields = '{{.Id}}|{{.State.Status}}|{{.State.Pid}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.State.OOMKilled}}|{{.State.Error}}'
    found = {}
    for line in docker('inspect', '-f', fields, *[x['id'] for x in restored['data'].values()]).splitlines():
        ident, status, pid, start, end, oom, error = line.split('|')
        found[ident] = dict(status=status, pid=int(pid), startedAt=start, finishedAt=end)
        require(oom == 'false' and not error, 'D368_CONTAINER_ERROR')
    for role, native in restored['data'].items():
        state = found[native['id']]
        if role == 'platform-pg' and pg_start_command is not None:
            require(re.fullmatch('[a-f0-9]{32}', pg_start_command) is not None, 'D368_PG_START_ID')
            receipt, out, _ = continuity.lifecycle_command(ROOT, pg_start_command, role, PG, 'data-start', archive)
            require(out.strip().decode() == PG and state['status'] == 'running' and state['pid'] > 0 and
                    utc(native['after']['FinishedAt']) < utc(receipt['startedAtUtc']) <= utc(state['startedAt']) <=
                    utc(receipt['endedAtUtc']), 'D368_PG_ONLY_START')
        else:
            require(state == dict(status='exited', pid=0, startedAt=native['startedAt'], finishedAt=native['after']['FinishedAt']),
                    'D368_STOPPED_' + role)
    network = 'ontology-g4-omq-replacement-01_source-internal'
    aliases = json.loads(docker('inspect', '-f', '{{json (index .NetworkSettings.Networks "' + network + '").Aliases}}', SOURCE))
    network_id = docker('network', 'inspect', '-f', '{{.Id}}', network)
    require(network_id == '26fd20922335607a74f39db63b00715a116760047f76c9c64b58790b891e91dd', 'D368_LIVE_NETWORK')
    require('oracle-source' in aliases, 'D368_SOURCE_ALIAS')
    # pgrep 只对实际工作流可执行程序开头匹配；不会读取密钥文件或输出进程命令行。
    pattern = r'^([^ ]*/)?(node|python[0-9.]*|dotnet) +([^ ]+ +)*(.*workflow-m4-query\.mjs.*s2-s3-oracle.*|.*workflow-oracle-query-fixture\.mjs.*|.*G4QueryMafRuntimeTests\.OracleActivationRevisionRejectsInflightQuery.*)$'
    observed = subprocess.run(['/usr/bin/pgrep', '-f', pattern], capture_output=True, timeout=5, text=True)
    require(observed.returncode == 1 and not observed.stderr.strip() and not observed.stdout.strip(), 'D368_ACTIVE_PRODUCER')
    return dict(running=sorted(expected), absentApis=sorted(old_apis), states=found, sourceAliases=aliases,
                matchingDrivers=0, pgStartCommand=pg_start_command)


def prove_d368_closure(*, pg_start_command=None):
    """固定历史原件和当前受控代次共同成立才返回；无目标/路径/资格布尔输入。"""
    require(os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'D368_RUN')
    archive = SimpleNamespace(paths={}, examined={})
    formal = window.last_close(ROOT, archive, digest=FORMAL)
    closed = window.last_close(ROOT, archive, digest=RESTORED)
    require(formal['ids']['oracle'] == closed['ids']['oracle'] == SOURCE and
            formal['ids']['platform-pg'] == closed['ids']['platform-pg'] == PG and
            [row['operation'] for row in formal['maintenance']] == ['9386ea708d6842ae9117780bdd4413dd'],
            'D368_PREDECESSORS')
    old_apis = {row['id'] for close in (formal, closed) for row in close['apis'].values()}
    require(len(old_apis) == 4, 'D368_API_GENERATIONS')
    historical = historical_row(archive)
    chain = shutdown_chain(archive)
    source = origin(archive, formal)
    generation = dict(queryId=QUERY, sourceContainerId=SOURCE, source=source, shutdownChain=chain,
                      formalClose=FORMAL, currentClose=RESTORED)
    live = live_state(closed, old_apis, pg_start_command, archive)
    verified = dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')
    members = {path:dict(sha256=archive.examined[name], sizeBytes=ex.ordinary(ROOT / path).stat().st_size)
               for name, path in archive.paths.items()}
    seal = dict(queryId=QUERY, parent=PARENT, child=CHILD, childHost=source['secondary'],
                parentExitedAtUtc=source['parentExitedAtUtc'], childExitedAtUtc=source['childExitedAtUtc'],
                stoppedApis=sorted(old_apis), matchingDrivers=live['matchingDrivers'],
                sourceFinishedAt=live['states'][SOURCE]['finishedAt'])
    return dict(kind='DEDICATED_ORACLE_GENERATION_TERMINATED', queryId=QUERY, verifiedUtc=verified,
                generationSha256=digest(generation), sealSha256=digest(seal), generation=generation, seal=seal,
                live=live, historical=historical, originals=members, originalsSha256=digest(members))
