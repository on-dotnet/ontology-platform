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


def shutdown_chain(archive, pairs=STOP_PAIRS):
    result = []
    for command_id, state_id in pairs:
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


NORMAL_QUERY = 'query-f1599097a7274c20b82cbf0dfcea4e2b'
NORMAL_PARENT = '4032c1d770b240989966ba3275d86999'
NORMAL_CLOSE = 'a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348'


METADATA_CLOSE = '64bdc66845958810935eb00e9b633108b6c5dc7ebf56ea19d030c396a5db5040'
METADATA_QUERY = 'query-5d891e89221e4a3f8f6893873b1d7a9d'
METADATA_PARENT = 'e1c70fc2faf344f39c98ac6731a061aa'
METADATA_OPERATION = 'f3d2efe12c984042a324c0f2cc133b30'
METADATA_OUTER_SHA = '9b956c976814dc2f5e77c48b4d83114a304c5bc5dbecf4f31d229a1a124d018e'


def metadata_inputs(archive):
    """重开冻结的外层完成行、Node 正式父和所有有能力接触源的注册命令。"""
    entry = window.close_registration(METADATA_CLOSE)
    closed = window.last_close(ROOT, archive, METADATA_CLOSE)
    # 原始调度器在仓库命令账本之外，单独重开准确完成事件，不读取历史会话其它字节。
    session = Path.home()/'.codex/sessions/2026/11/22/rollout-2026-11-22T22-05-24-01a20393-7456-76f3-b937-014dc810533c.jsonl'
    with ex.ordinary(session).open('rb') as stream:
        stream.seek(6611299)
        outer = stream.read(940)
    require(ex.sha(outer) == METADATA_OUTER_SHA, 'METADATA_OUTER_ORIGINAL')
    item = json.loads(outer)['payload']['item']
    require(item['id'] == 'exec-221bcd2c-e188-43e4-8ac6-2627636422a7' and item['exit_code'] == 1
            and item['cwd'] == ROOT.as_uri() and item['command'] == ['/bin/zsh', '-lc',
            'env OMQ_PRODUCT_RUN=product-resume-01 python3 -B scripts/maintenance/workflow_oracle_normal_query.py']
            and item['aggregated_output'] == 'normal-observation-'+METADATA_OPERATION+'.json 1 [] []\n', 'METADATA_OUTER')
    raw = continuity.raw(ROOT, AREA/('normal-observation-'+METADATA_OPERATION+'.json'), archive)
    require(ex.sha(raw) == METADATA_CLOSE and len(raw) == 19744 and entry['memberCount'] == 167
            and entry['memberIndexSha256'] == '04db460676617adf7394adba42c034e6bde5f4942d8499c1f767cd30fabc4a45', 'METADATA_CLOSE')
    row = json.loads(raw)
    host = row['host']
    _, services = refresh.observed_rows(ROOT, host, archive)
    builds = refresh.snapshot_builds(ROOT, host, archive)
    apis = {name: {'id': services[name]['containerId']} for name in ('api', 'api-secondary')}
    require(all(row['closed'][name] == data['id'] for name, data in apis.items()), 'METADATA_API_IDS')
    # 从当前已复核的生命周期原件重建本代启动与退出，通用历史结构中可能仍保留更早代次。
    data = {name: {**native, 'startedAt': services[name]['startedAt'], 'after': row['closed'][name]['after']}
            for name, native in closed['data'].items()}
    require(all(item['id'] == services[name]['containerId'] == row['closed'][name]['id'] for name, item in data.items()),
            'METADATA_DATA_IDS')
    network = services['oracle']['networks']
    require(len(network) == 1 and list(network.values()) == ['26fd20922335607a74f39db63b00715a116760047f76c9c64b58790b891e91dd']
            and all(network.items() <= services[k]['networks'].items() for k in apis)
            and digest(services['oracle']['mounts']) == 'cab41c9abaccb8b2d35c9d6221cc6c7165dbfd5dd29428b2e62e92efa7b8b887', 'METADATA_NETWORK')
    argv = [NODE, DRIVER, '--task', TASK, '--run-id', RUN, '--mode', 's2-oracle-normal', '--normal-id', METADATA_OPERATION]
    parent = failed_command(archive, METADATA_PARENT, argv, 'omq-browser-normal-q1', digest([METADATA_OPERATION,host,argv]),
                            host['commandId'], 804, 1)
    book = entry['ledger']
    with ex.ordinary(ROOT/continuity.AREA.parent/'command-events.jsonl').open('rb') as stream:
        stream.seek(book['offset'])
        ledger = stream.read(book['sizeBytes'])
    require(ex.sha(ledger) == '165eec5e8971a47fc22c125507f8c0fdf2d39a98ca9f40e8e86c4f5156ddd772', 'METADATA_LEDGER')
    starts, ends = {}, {}
    for line in ledger.splitlines():
        event = json.loads(line)
        bucket = starts if event['event'] == 'START' else ends
        require(event['event'] in ('START', 'END') and event['commandId'] not in bucket, 'METADATA_COMMAND_PAIR')
        bucket[event['commandId']] = event
    require(len(starts) == 1714 and starts.keys() == ends.keys(), 'METADATA_PRODUCER_SET')
    for cid, start in starts.items():
        end = ends[cid]
        require(all(start[k] == end[k] for k in ('identity','cwd','commandSummary','inputFingerprint','stage','parentId','runId'))
                and end['exitCode'] is not None, 'METADATA_PRODUCER_EXIT')
    require(utc(parent['endedAtUtc']) < utc(data['oracle']['after']['FinishedAt']), 'METADATA_EXIT_ORDER')
    facts = row['facts']
    for label, sha in [('row','a08ebed4e8c3fed65b076a4bd8988999d2f2f84c8308df8d8158734df678bab3'),
                       ('audit','40c3fbca6174d0a8d69393752d6794f74eaff3ebca50ede85c86e284949e84c7'),
                       ('data','f553c53c619b931252a15a8c46218163bd8565e0e0bcb3253a8c2b355aaa2d6c'),
                       ('ident','11b60a6e31c626ca581339f3181daf469c426395bb07c94224f660938ed50106')]:
        command = facts[label]['commandId']
        result = continuity.raw(ROOT, continuity.AREA.parent/'commands'/RUN/command/'stdout.txt', archive)
        require(ex.sha(result) == sha and json.loads(result) == facts[label]['value'] and ends[command]['exitCode'] == 0, 'METADATA_ORIGINAL_'+label)
    generation = dict(queryId=METADATA_QUERY, parent=METADATA_PARENT, close=METADATA_CLOSE, source=SOURCE,
                      start=data['oracle']['startedAt'], end=data['oracle']['after']['FinishedAt'], outer=METADATA_OUTER_SHA,
                      ledger=book, networks=network, mounts=digest(services['oracle']['mounts']),
                      host=host['commandId'], snapshots={name:b['snapshotId'] for name,b in builds.items()})
    seal = dict(queryId=METADATA_QUERY, closedApis=sorted(item['id'] for item in apis.values()), parent=METADATA_PARENT,
                ended=parent['endedAtUtc'], outer=item['id'], matchingDrivers=0)
    history = dict(row=facts['row']['value'], audit=facts['audit']['value'], **facts['data']['value'])
    return {**closed,'data':data,'apis':apis},generation,seal,history


def prove_metadata_closure(*, pg_start_command=None):
    """对准确正常请求的旧代次复查历史和当前生产者，任何漂移均关闭维护。"""
    require(os.environ.get('OMQ_PRODUCT_RUN') == RUN, 'METADATA_RUN')
    archive = SimpleNamespace(paths={},examined={})
    closed,generation,seal,history = metadata_inputs(archive)
    live = live_state(closed, set(seal['closedApis']), pg_start_command, archive, metadata=True)
    originals = {p:dict(sha256=archive.examined[k],sizeBytes=(ROOT/p).stat().st_size) for k,p in archive.paths.items()}
    return dict(kind='DEDICATED_ORACLE_GENERATION_TERMINATED',queryId=METADATA_QUERY, originals=originals,
                originalsSha256=digest(originals),generation=generation,generationSha256=digest(generation),
                seal=seal,sealSha256=digest(seal),historical=history,live=live,
                verifiedUtc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds'))


def target(normal=False):
    """维护目标的身份和证明均在源码内冻结，调用者不能指定任意行或原件路径。"""
    if normal == 'metadata':
        path = ROOT/continuity.AREA.parent/'commands'/RUN/'6795cc23c706473ba61daf2830a1670c/stdout.txt'
        raw = ex.ordinary(path).read_bytes()
        require(ex.sha(raw) == 'a08ebed4e8c3fed65b076a4bd8988999d2f2f84c8308df8d8158734df678bab3', 'METADATA_FROZEN_ROW')
        return SimpleNamespace(query=METADATA_QUERY,parent=METADATA_PARENT,child=None,close=METADATA_CLOSE,prefix='metadata',
            prove=prove_metadata_closure,frozen=json.loads(raw),audit='3e1ca8e4e1af42efa3ac8d0007c8debf',
            audit_sha='8625e5892d8c7360efd0a5eaaaf5da78e808c6fb859c4f15c529b36244c88de3',mode='NORMAL_GENERATION',
            generation_sha='3004a217e2551b91d104092fd3faad8cc8d8fa56ee4eac0119e5f37d7327a858',seal_sha='2120d6d36a993bdc5234e8febce44d42d83d3315fd0ad405f6bbfc3e9ef2588b',
            start='2026-11-22T15:03:56.505162467Z',end='2026-11-22T15:06:22.192480006Z')
    require(type(normal) is bool, 'MAINTENANCE_TARGET')
    if not normal:
        return SimpleNamespace(query=QUERY,parent=PARENT,child=CHILD,close=RESTORED,prefix='d368',prove=prove_d368_closure,
            frozen=FROZEN_ROW,audit=AUDIT_ID,audit_sha=AUDIT_SHA,mode='DEDICATED_GENERATION',
            generation_sha='a617d1e838631e9f16b5e9bc65aa97842c3a85cfc7c9991137262a537881c3d0',
            seal_sha='1d39291bc79d057dc310bdad98049442305aff73b236e4a004b4829d3890edb2',
            start='2026-11-21T13:49:57.33078955Z',end='2026-11-21T13:52:47.119332336Z')
    raw=ex.ordinary(ROOT/continuity.AREA.parent/'commands'/RUN/'c4dafca14fbf4e12bf8687c2d78b0351/stdout.txt').read_bytes()
    require(ex.sha(raw)=='afab62d7f6d11f8b651ef55b5c9a55bdc4120ab8d8b66ff8f4cb816962862ae8','NORMAL_FROZEN_ROW')
    return SimpleNamespace(query=NORMAL_QUERY,parent=NORMAL_PARENT,child=None,close=NORMAL_CLOSE,prefix='normal',prove=prove_normal_closure,
        frozen=json.loads(raw),audit='38ebcc6e08504994b36a322edc4ffd86',audit_sha='91713b546c40b9d6925079220bfa0420e6bbfc3d8dbd18c1a9c335cc2e0d422c',
        mode='NORMAL_GENERATION',generation_sha='d3bd83e5b832d68295dd3abeeb84a558bf290b51ce882b5df7a9995c4aefce6b',
        seal_sha='34fd7fda857fc5ca2f2456ad5cb76885b8473fafe00b588366d187286e0fd9c5',
        start='2026-11-22T12:48:17.47353763Z',end='2026-11-22T12:51:07.888426792Z')


def normal_generation(archive):
    """从正式父、同代宿主、唯一失败行和完整执行账本绑定普通 POST 的专用源代次。"""
    entry = window.close_registration(NORMAL_CLOSE)
    require(entry['operation']=='c35242b898c04ae3ad5529ba346d320f' and entry['parentId']==NORMAL_PARENT,'NORMAL_CLOSE_ID')
    closed = window.last_close(ROOT,archive,NORMAL_CLOSE)
    def load(relative):
        return json.loads(continuity.raw(ROOT,relative,archive))
    raw = continuity.raw(ROOT,continuity.AREA/('formal-run-s2-s3-oracle-'+NORMAL_PARENT+'.json'),archive)
    require(ex.sha(raw)==entry['parentSha256'],'NORMAL_DISPATCH')
    dispatch=json.loads(raw)
    host=dispatch['host']
    _,rows=refresh.observed_rows(ROOT,host,archive)
    builds=refresh.snapshot_builds(ROOT,host,archive)
    require(dispatch['testedCommit']=='9e84841423bac82911fc989b7b0a4ec999ac1ac7' and host['commandId']=='e53018d6c4f242b0ae94cf462eb54a0f'
            and all(rows[k]['containerId']==ident for k,ident in closed['ids'].items())
            and rows['oracle']['startedAt']==closed['data']['oracle']['startedAt'] and len(rows['oracle']['networks'])==1
            and all(rows['oracle']['networks'].items()<=rows[k]['networks'].items() for k in closed['apis']),'NORMAL_HOST')
    manifest=continuity.raw(ROOT,continuity.AREA/('formal-resources-'+host['resourceManifestSha256']+'.json'),archive)
    verify_product_manifest(host,json.loads(manifest),ex.sha(manifest))
    compose=continuity.raw(ROOT,continuity.AREA/('formal-api-compose-'+host['composeSha256']+'.json'),archive)
    spec=json.loads(compose)
    require(ex.sha(compose)==host['composeSha256'] and set(spec['services'])=={'api','api-secondary'}
            and set(rows['oracle']['networks'])=={spec['networks']['source-internal']['name']},'NORMAL_SOURCE_NETWORK')
    for role,destination,build_name in (('api','/app','api'),('api-secondary','/app','api'),
            ('api-secondary','/session-tests','agent'),('api-secondary','/query-tests','query')):
        path=str(ROOT/builds[build_name]['directory'])
        mounts=[m for m in rows[role]['mounts'] if m['Destination']==destination or m['Destination'].startswith(destination+'/')]
        require(len(mounts)==1 and mounts[0]['Destination']==destination and mounts[0]['Type']=='bind' and not mounts[0]['RW']
                and mounts[0]['Source'].removeprefix('/host_mnt')==path
                and spec['services'][role]['volumes'].count(path+':'+destination+':ro')==1,'NORMAL_SOURCE_MOUNT')
    chain=shutdown_chain(archive,[('4944ef11156e4789a871a14261cdc8ac','fa04a5c3408645faa78fbcc283ac3847')])
    args=[NODE,DRIVER,'--task',TASK,'--run-id',RUN,'--mode','s2-s3-oracle','--batch-input',dispatch['stageInputs']['batchInput']]
    parent=failed_command(archive,NORMAL_PARENT,args,'omq-browser-s2-s3-oracle',
                          'bec919fe3c153200d4d05267e5b9045ffb3a12ba6b0bde4836da3d575b48af3d',host['commandId'],2340,1)
    independent_raw=continuity.raw(ROOT,AREA/'independent-final-c352.json',archive)
    require(ex.sha(independent_raw)=='788eec2150f40ca9163c5a5db796c973b2dc536c41cd67b387479940ac3d5499','NORMAL_INDEPENDENT')
    evidence=json.loads(independent_raw)
    book=evidence['ledger']
    ledger=ROOT/continuity.AREA.parent/'command-events.jsonl'
    with ex.ordinary(ledger).open('rb') as stream:
        stream.seek(book['offset'])
        data=stream.read(book['sizeBytes'])
    require(ex.sha(data)==book['sha256'],'NORMAL_LEDGER')
    starts=[r for raw in data.splitlines() if (r:=json.loads(raw)).get('event')=='START']
    require([r['commandId'] for r in starts if r['stage']=='omq-browser-s2-s3-oracle']==[NORMAL_PARENT]
            and not any(r['stage']=='query-real-aba-inflight-runtime' for r in starts),'NORMAL_PRODUCERS')
    import workflow_oracle_access_maintenance as access
    identification='''SET TIME ZONE 'UTC'; SELECT json_agg("Id" ORDER BY "CreatedAtUtc") FROM semantic_query."Queries" WHERE "ConnectionId"='a7913bb552eb4cd1a3f6eaf5b93cd619' AND "CreatedAtUtc" BETWEEN '2026-11-22T12:50:36.306Z' AND '2026-11-22T12:50:37.978Z';'''
    seed_sql={'identification':identification,'row':access.ROW_SQL.replace(access.QUERY,NORMAL_QUERY).replace(''''owner',q."LeaseOwner"''',''''ownerSha256',encode(sha256(convert_to(q."LeaseOwner",'UTF8')),'hex')'''),
              'audit':access.AUDIT_SQL.replace(access.QUERY,NORMAL_QUERY),'receipts':f'''SELECT json_array_length(convert_from("BindingBytes",'UTF8')::json->'receipts') FROM semantic_query."Queries" WHERE "Id"='{NORMAL_QUERY}';'''}
    command_ids={'identification':'c23e34fe3ef049f29a78510983807d44','row':'c4dafca14fbf4e12bf8687c2d78b0351',
                 'audit':'19b582350d8740d482ba3658e74e2934','receipts':'4a7ac0543a234f7992e0e041845fa66f'}
    argv=[*DOCKER,'exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    originals={}
    for label,sql in seed_sql.items():
        stage='omq-pg-formal-seed-'+('identification' if label=='identification' else 'post-'+label)
        key=ex.sha(('BEGIN READ ONLY;\n'+sql+'\nCOMMIT;').encode())
        receipt,out,err=continuity.command(ROOT,command_ids[label],RUN,argv,stage,key,15,archive)
        require(not err and utc(parent['endedAtUtc'])<utc(receipt['startedAtUtc'])<utc(closed['data']['platform-pg']['after']['FinishedAt']),
                'NORMAL_PG_ORIGINAL_WINDOW')
        originals[label]=json.loads(out)
    found,row,audits,receipts=(originals[k] for k in ('identification','row','audit','receipts'))
    require(found==[NORMAL_QUERY] and row['queryId']==NORMAL_QUERY and row['stableRowSha256']=='8bbdb6cb314c00994015ef3eef5c36c5f9ec60d41f005875256129f2b7d91a57'
            and len(audits)==1 and audits[0]['id']=='38ebcc6e08504994b36a322edc4ffd86' and receipts==0,'NORMAL_TARGET')
    require(utc(chain[0]['startedAt'])<utc(parent['startedAtUtc'])<utc(row['createdUtc'])<utc(row['completedUtc'])
            <utc(parent['endedAtUtc'])<utc(chain[0]['finishedAt']),'NORMAL_SOURCE_ORDER')
    generation=dict(queryId=NORMAL_QUERY,parent=NORMAL_PARENT,child=None,host=host['commandId'],close=NORMAL_CLOSE,
                    source=SOURCE,networks=rows['oracle']['networks'],shutdown=chain,code=source_code(dispatch['testedCommit']),
                    snapshots={name:value['snapshotId'] for name,value in builds.items()})
    return closed,generation,dict(row=row,audit=audits,receipts=receipts)


def prove_normal_closure(*,pg_start_command=None):
    """只为冻结的普通失败请求重开本代证明与当前生产者状态。"""
    require(os.environ.get('OMQ_PRODUCT_RUN')==RUN,'NORMAL_RUN')
    archive=SimpleNamespace(paths={},examined={})
    closed,generation,historical=normal_generation(archive)
    apis={row['id'] for row in closed['apis'].values()}
    live=live_state(closed,apis,pg_start_command,archive)
    seal=dict(queryId=NORMAL_QUERY,parent=NORMAL_PARENT,child=None,closedApis=sorted(apis),
              sourceFinishedAt=live['states'][SOURCE]['finishedAt'],matchingDrivers=live['matchingDrivers'])
    members={p:dict(sha256=archive.examined[k],sizeBytes=(ROOT/p).stat().st_size) for k,p in archive.paths.items()}
    return dict(kind='DEDICATED_ORACLE_GENERATION_TERMINATED',queryId=NORMAL_QUERY,originals=members,originalsSha256=digest(members),
                generation=generation,generationSha256=digest(generation),seal=seal,sealSha256=digest(seal),
                live=live,historical=historical,verifiedUtc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds'))


def live_state(restored, old_apis, pg_start_command, archive, *, metadata=False):
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
    if metadata:
        pattern = (r'^([^ ]*/)?(node|python[0-9.]*|dotnet) +([^ ]+ +)*'
                   r'(.*workflow-m4-query\.mjs.*s2-(s3-oracle|oracle-normal).*|.*workflow_oracle_normal_query\.py.*|'
                   r'.*workflow-oracle-query-fixture\.mjs.*|.*OracleActivationRevisionRejectsInflightQuery.*)$')
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
