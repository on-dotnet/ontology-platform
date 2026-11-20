"""仅为当前产品批追加归档设备号变化的只读完整性旁证；旧账本永不改写。"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import workflow_execution as ex
from workflow_oracle_mapping_resources import TASK, RUN, require

PRODUCT = 'product-resume-01'
HELPER = 'scripts/maintenance/workflow_oracle_archive_requalification.py'
LEDGER_SHA = '270fca4d7f40f2fb1c1fee1ccf5e40bb00ac0509445e07d26f86287573315617'
NAMES = ('platform/fuseki.tar', 'platform/rustfs.tar', 'platform/keycloak-test.tar',
         'platform/platform-pg.tar', 'source/database.tar', 'source/trust-and-auth.tar')


def identity(info):
    """原账本四元组；device以外三项绝不放宽。"""
    return [info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns]


def regular(info):
    """受控归档须当前用户所有、单链接且仅所有者可读写。"""
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600, 'ARCHIVE_REQUAL_FILE')


def layout(root):
    """只核固定六项路径及stat，不读取归档正文。"""
    from workflow_oracle_mapping_platform_recovery import ORIGINAL_IDS
    root = ex.ordinary(root)
    area = root/'artifacts/workflow'/TASK
    ledger_path = ex.ordinary(area/'s0-recovery-01/archive-ledger.json')
    raw = ledger_path.read_bytes()
    require(ex.sha(raw) == LEDGER_SHA, 'ARCHIVE_REQUAL_LEDGER')
    ledger = json.loads(raw)
    require((ledger['taskId'], ledger['operation']) == (TASK, 's0-recovery-01')
            and set(ledger['archives']) == set(NAMES), 'ARCHIVE_REQUAL_SET')
    private = root/'.tools/security/g4-oracle-mapping-query-001'/RUN/'s0-recovery-01'
    facts = {}
    for name in NAMES:
        entry = ledger['archives'][name]
        path = ex.ordinary(private/name)
        directory = path.parent.stat()
        require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == os.getuid()
                and stat.S_IMODE(directory.st_mode) == 0o700, 'ARCHIVE_REQUAL_DIRECTORY')
        info = path.lstat()
        regular(info)
        current = identity(info)
        role = 'oracle' if name.startswith('source/') else Path(name).stem
        require(entry['privatePath'] == name and entry['sourceId'] == ORIGINAL_IDS[role]
                and len(entry['identity']) == 4 and current[1:] == entry['identity'][1:]
                and current[2] == entry['bytes'] and re.fullmatch('[a-f0-9]{64}', entry['sha256']),
                'ARCHIVE_REQUAL_IDENTITY')
        facts[name] = dict(privatePath=name, sourceId=entry['sourceId'], volume=entry['volume'],
                           oldIdentity=entry['identity'], currentIdentity=current, sha256=entry['sha256'])
    return root, area, private, facts


def stream_digest(path, expected):
    """仅流式散列；打开前、描述符与读后身份须一致，不解析成员或输出内容。"""
    before = path.lstat()
    regular(before)
    require(identity(before) == expected, 'ARCHIVE_REQUAL_BEFORE')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        regular(opened)
        require(identity(opened) == expected, 'ARCHIVE_REQUAL_OPEN')
        digest = hashlib.sha256()
        count = 0
        while True:
            chunk = stream.read(1024*1024)
            if not chunk:
                break
            count += len(chunk)
            require(count <= expected[2], 'ARCHIVE_REQUAL_LENGTH')
            digest.update(chunk)
        ended = os.fstat(stream.fileno())
        regular(ended)
        require(identity(ended) == expected, 'ARCHIVE_REQUAL_DURING')
    after = path.lstat()
    regular(after)
    require(identity(after) == expected and count == expected[2], 'ARCHIVE_REQUAL_AFTER')
    return digest.hexdigest()


def observe(root):
    """独立子进程完整核验六项旧摘要，仅返回固定安全元数据。"""
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    root, area, private, facts = layout(root)
    require(any(v['oldIdentity'] != v['currentIdentity'] for v in facts.values()), 'ARCHIVE_REQUAL_NO_DRIFT')
    for name, row in facts.items():
        require(stream_digest(private/name, row['currentIdentity']) == row['sha256'], 'ARCHIVE_REQUAL_HASH')
    require(layout(root)[3] == facts, 'ARCHIVE_REQUAL_SET_CHANGED')
    return dict(schemaVersion=1, taskId=TASK, runId=PRODUCT, status='CONTENT_MATCH_DEVICE_REQUALIFIED',
                sourceLedgerSha256=LEDGER_SHA, helperSha256=ex.sha((root/HELPER).read_bytes()),
                startedAtUtc=started, endedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(), archives=facts)


def invocation(root):
    """生产者与消费者使用同一固定argv及输入身份。"""
    argv = ['python3', '-B', str(root/HELPER), '--observe', '--root', str(root)]
    key = ex.sha(ex.encoded(dict(helperSha256=ex.sha((root/HELPER).read_bytes()), sourceLedgerSha256=LEDGER_SHA)))
    return argv, key


def qualified(root):
    """真实命令、双流及当前六项身份全部吻合才允许消费追加旁证。"""
    root, area, private, facts = layout(root)
    argv, key = invocation(root)
    matches = []
    for path in (area/PRODUCT).glob('archive-device-requalification-*.json'):
        proof = json.loads(ex.ordinary(path).read_bytes())
        require(set(proof) == {'schemaVersion', 'commandId', 'observationSha256', 'observation'}
                and proof['schemaVersion'] == 1, 'ARCHIVE_REQUAL_PROOF_SCHEMA')
        cid = proof.get('commandId', '')
        require(re.fullmatch('[a-f0-9]{32}', cid) and path.name == 'archive-device-requalification-'+cid+'.json',
                'ARCHIVE_REQUAL_PROOF_ID')
        observation = proof['observation']
        require(set(observation) == {'schemaVersion', 'taskId', 'runId', 'status', 'sourceLedgerSha256',
                'helperSha256', 'startedAtUtc', 'endedAtUtc', 'archives'} and observation['schemaVersion'] == 1
                and observation['taskId'] == TASK and observation['runId'] == PRODUCT
                and observation['sourceLedgerSha256'] == LEDGER_SHA
                and observation['helperSha256'] == ex.sha((root/HELPER).read_bytes())
                and observation['status'] == 'CONTENT_MATCH_DEVICE_REQUALIFIED'
                and set(observation['archives']) == set(NAMES), 'ARCHIVE_REQUAL_OBSERVATION')
        for name, old in facts.items():
            row = observation['archives'][name]
            require(set(row) == set(old) and {k:v for k,v in row.items() if k != 'currentIdentity'} ==
                    {k:v for k,v in old.items() if k != 'currentIdentity'}
                    and isinstance(row['currentIdentity'], list) and len(row['currentIdentity']) == 4
                    and all(type(x) is int and x > 0 for x in row['currentIdentity'])
                    and row['currentIdentity'][1:] == old['oldIdentity'][1:], 'ARCHIVE_REQUAL_OBSERVATION_IDENTITY')
        directory = area/'commands'/PRODUCT/cid
        receipt = json.loads(ex.ordinary(directory/'receipt.json').read_bytes())
        require(receipt.get('schemaVersion') == 2
                and re.fullmatch('[a-f0-9]{64}', receipt.get('environmentFingerprint', ''))
                and receipt.get('identity') == ex.sha(ex.encoded([key, receipt.get('environmentFingerprint'),
                    ex.sha(ex.encoded(argv)), str(root), 120, ex.sha(Path(ex.__file__).read_bytes())]))
                and (receipt['taskId'], receipt['runId'], receipt['commandId'], receipt['stage']) ==
                (TASK, PRODUCT, cid, 'archive-device-requalification') and receipt['parentId'] is None
                and receipt['cwd'] == str(root) and receipt['inputFingerprint'] == key
                and receipt['commandSummary'] == dict(executable='python3', argumentCount=len(argv)-1, sha256=ex.sha(ex.encoded(argv)))
                and receipt['started'] is True and receipt['exitCode'] == 0 and receipt['classification'] == 'SUCCESS'
                and receipt['signal'] is None and receipt['deadlineSeconds'] == 120
                and type(receipt['elapsedSeconds']) in (int, float)
                and 0 <= receipt['elapsedSeconds'] <= 120, 'ARCHIVE_REQUAL_COMMAND')
        streams = {}
        for name in ('stdout', 'stderr'):
            actual = ex.ordinary(directory/(name+'.txt'))
            require(receipt[name]['path'] == str(actual), 'ARCHIVE_REQUAL_STREAM_PATH')
            raw = actual.read_bytes()
            require(len(raw) == receipt[name]['sizeBytes'] and ex.sha(raw) == receipt[name]['sha256'], 'ARCHIVE_REQUAL_STREAM')
            streams[name] = raw
        require(not streams['stderr'] and ex.sha(streams['stdout']) == proof['observationSha256'], 'ARCHIVE_REQUAL_OUTPUT')
        observation = json.loads(streams['stdout'])
        require(observation == proof['observation'] and observation['taskId'] == TASK and observation['runId'] == PRODUCT
                and observation['sourceLedgerSha256'] == LEDGER_SHA and observation['helperSha256'] == ex.sha((root/HELPER).read_bytes())
                and observation['status'] == 'CONTENT_MATCH_DEVICE_REQUALIFIED',
                'ARCHIVE_REQUAL_OBSERVATION')
        times = [dt.datetime.fromisoformat(x) for x in (receipt['startedAtUtc'], observation['startedAtUtc'], observation['endedAtUtc'], receipt['endedAtUtc'])]
        require(all(t.utcoffset() is not None for t in times) and times == sorted(times), 'ARCHIVE_REQUAL_WINDOW')
        # 结构、旧账本、真实命令和双流全部合格后，才可跳过设备号已过时的历史旁证。
        if observation['archives'] != facts:
            continue
        matches.append(dict(commandId=cid, observationSha256=proof['observationSha256'], archives=facts))
    require(matches, 'ARCHIVE_REQUAL_MISSING')
    require(len(matches) == 1, 'ARCHIVE_REQUAL_AMBIGUOUS')
    return matches[0]


def requalify(root):
    """先复用已合格当前旁证；新核验只追加，不覆盖历史账本或失败。"""
    root = ex.ordinary(root)
    try:
        return qualified(root)
    except ValueError as error:
        if str(error) != 'ORACLE_ADMISSION_ARCHIVE_REQUAL_MISSING':
            raise
    argv, key = invocation(root)
    result = ex.run(argv, root, task=TASK, run_id=PRODUCT, stage='archive-device-requalification',
                    input_key=key, timeout=120)
    require(result.returncode == 0, 'ARCHIVE_REQUAL_EXECUTION')
    observation = json.loads(result.stdout)
    cid = result.receipt['commandId']
    target = root/'artifacts/workflow'/TASK/PRODUCT/('archive-device-requalification-'+cid+'.json')
    with ex.ordinary(target).open('x') as stream:
        json.dump(dict(schemaVersion=1, commandId=cid, observationSha256=ex.sha(result.stdout), observation=observation), stream, indent=2)
        stream.write('\n')
    return qualified(root)


def main():
    """固定本工作树入口，不接受外部目录或任意归档路径。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observe', action='store_true', required=True)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    require(root == Path(__file__).resolve().parents[2], 'ARCHIVE_REQUAL_ROOT')
    print(json.dumps(observe(root), sort_keys=True))


if __name__ == '__main__':
    main()
