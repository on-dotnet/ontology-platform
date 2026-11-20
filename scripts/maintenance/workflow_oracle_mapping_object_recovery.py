"""冻结 RustFS 检查点的只读列表、版本正文、参考副本与 PG 发布清单资格。"""

import hashlib
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from workflow_execution import encoded, sha

TASK = 'G4-ORACLE-MAPPING-QUERY-001'
RUN = 's0-recovery-02'
RESOURCE_RUN = 'implementation-01'
BASE = '454d1a2f17581673cbbf44900a5fe241d603f5ef'
BUCKET = 'g4-oracle-mapping-synthetic'
IMAGE = 'sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b'
ARCHIVE = '6ff1aa706d27fd31f0c98c95168124d3a0f07a6018aef527f45bdb169e70be3e'
ACTUAL = '65a98692a6340cd29d2680fff981c6c81c764b7af96320a7945725ca5eb650be'
VOLUMES = {'actual': 'ontology-g4-omq-restore-01_rustfs-data',
           'reference': 'ontology-g4-omq-recovery-02_rustfs-reference'}
PG_EVIDENCE = 'docs/evidence/' + TASK + '/s0-recovery-01/originals/pg-baseline-0e8c1a69fbe5401292061ac13dda2874.json'
ROOT = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).with_suffix('.cs.txt')
HEX = re.compile(r'[0-9a-f]{64}\Z')
XML_CAP = 65536
BODY_CAP = 1048576
TOTAL_CAP = 2097152


def check(condition, code):
    if not condition:
        raise ValueError('RUSTFS_' + code)


def digest(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def source_sha256():
    """绑定真正的签名、读取和再资格消费者源码。"""
    return sha(encoded([sha(DRIVER.read_bytes()), sha(Path(__file__).read_bytes())]))


def request(role, container_id, volume, driver_sha256, attempt):
    """Master 从准确 live registry 和零下载验证器程序集建立单次 stdin。"""
    check(role in VOLUMES and VOLUMES[role] == volume and digest(container_id) and digest(driver_sha256)
          and isinstance(attempt, str) and re.fullmatch('[0-9a-f]{32}', attempt), 'BINDING')
    check((role == 'actual') == (container_id == ACTUAL), 'INSTANCE')
    fields = dict(taskId=TASK, run=RUN, resourceRun=RESOURCE_RUN, base=BASE, image=IMAGE,
                  archive=ARCHIVE, role=role, volume=volume, containerId=container_id, attempt=attempt,
                  sourceSha256=source_sha256(), driverSha256=driver_sha256)
    return {**fields, 'inputFingerprint': sha(encoded(fields))}


def frozen_objects():
    """读取不可变 Git 原件中的五个发布引用，绝不从当前 RustFS 输出制造预期。"""
    data = subprocess.check_output(['git', 'show', BASE + ':' + PG_EVIDENCE], cwd=ROOT, timeout=8)
    pg = json.loads(data)
    stable = pg['stable']
    check(pg['taskId'] == TASK and pg['runId'] == RESOURCE_RUN
          and sha(encoded(stable)) == pg['stableSha256'] == 'bc3a0c7014cb66a731f183aff6fae3a792f2cccb89badb23c33a5608b63e844a',
          'PG_BASELINE')
    result = {o['objectKey']: (o['sizeBytes'], o['hash']) for o in stable['objects']}
    check(len(result) == len(stable['objects']) == 5 and all(n > 0 and digest(h) for n, h in result.values()),
          'PUBLISHED_OBJECTS')
    return result


def archive_scope(path):
    """Master 冷态只读：确认归档身份与顶层桶，既有通用归档机制继续负责成员安全及解包。"""
    path = Path(path)
    check(path.name == 'rustfs.tar' and path.is_file() and not path.is_symlink() and path.stat().st_size == 184320
          and path.stat().st_mode & 0o777 == 0o600, 'ARCHIVE_FILE')
    with path.open('rb') as stream:
        check(hashlib.file_digest(stream, 'sha256').hexdigest() == ARCHIVE, 'ARCHIVE_DIGEST')
    roots = set()
    metadata = set()
    count = extent = 0
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            check(not name.is_absolute() and '..' not in name.parts and (member.isdir() or member.isfile()),
                  'ARCHIVE_MEMBER')
            if name.parts:
                roots.add(name.parts[0])
                if name.parts[:2] == ('.rustfs.sys', 'buckets') and len(name.parts) >= 3:
                    metadata.add(name.parts[2])
            count += 1
            extent += member.size
    check(count == 56 and extent == 87689 and BUCKET in roots
          and roots == {BUCKET, '.rustfs.sys', '.rustfs'}, 'ARCHIVE_BUCKET_SCOPE')
    check(metadata == {BUCKET, '.bloomcycle.bin', '.scanner-pause-backlog.json', '.usage-cache.bin',
                       '.usage-cache.bin.bkp', '.usage.v2.json', '.usage.v2.json.bkp'}, 'ARCHIVE_BUCKET_METADATA')
    return dict(archive=ARCHIVE, sizeBytes=184320, members=count, expandedBytes=extent,
                roots=sorted(roots), bucketMetadata=sorted(metadata))


def bounded_integer(value, low, high):
    return type(value) is int and low <= value <= high


def valid_id(value, key=False):
    return isinstance(value, str) and 0 < len(value.encode('utf-8')) <= 1024 and all(
        ord(c) >= 32 and not 127 <= ord(c) <= 159 for c in value) and (not key or not any(
            p in ('.', '..') for p in value.split('/')))


def stamp(value):
    check(isinstance(value, str) and len(value) <= 64, 'TIMESTAMP')
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('RUSTFS_TIMESTAMP') from None
    check(instant.tzinfo is not None, 'TIMESTAMP_ZONE')
    return instant.astimezone(timezone.utc)


def inspect_observation(data, expected):
    """按实发命令的独立 stdin 核实一份输出，逐页重走游标、历史条目和每次 GET。"""
    bound = request(expected['role'], expected['containerId'], expected['volume'],
                    expected['driverSha256'], expected['attempt'])
    check(expected == bound and data.get('binding') == bound and data.get('status') == 'OBSERVED', 'COMMAND_BINDING')
    state = data.get('versioning')
    check(state in ('UNSET', 'Enabled', 'Suspended') and digest(data.get('versioningSha256'))
          and bounded_integer(data.get('versioningBytes'), 1, XML_CAP), 'VERSIONING')
    pages = data.get('pages')
    check(isinstance(pages, list) and 1 < len(pages) <= 16 and bounded_integer(data.get('elapsedMs'), 0, 45000), 'PAGE_BUDGET')
    cursor = (None, None)
    visited = {cursor}
    versions = {}
    latest = {}
    consumed = data['versioningBytes']
    for page_index, page in enumerate(pages):
        check(cursor == (page.get('keyMarker'), page.get('versionMarker')) and digest(page.get('xmlSha256'))
              and bounded_integer(page.get('xmlBytes'), 1, XML_CAP), 'PAGE_CHAIN')
        consumed += page['xmlBytes']
        rows = page.get('rows')
        # 抵达非截断末页；最后一页可以没有条目，后续还要核 PG 的五个已发布引用。
        check(isinstance(rows, list) and len(rows) <= 2 and (rows or not page['truncated']) and type(page.get('truncated')) is bool
              and page['truncated'] == (page_index < len(pages) - 1), 'PAGE_TERMINATION')
        for item in rows:
            key, vid, kind = item.get('key'), item.get('versionId'), item.get('kind')
            check(valid_id(key, True) and valid_id(vid) and (key, vid) not in versions and len(versions) < 32, 'VERSION_TUPLE')
            current = item.get('isLatest')
            check(type(current) is bool and kind in ('Version', 'DeleteMarker'), 'VERSION_KIND')
            instant = stamp(item['lastModified'])
            check(bounded_integer(item.get('responseBytes'), 0, BODY_CAP if kind == 'Version' else XML_CAP)
                  and digest(item.get('responseSha256')), 'RESPONSE_BYTES')
            consumed += item['responseBytes']
            check(item.get('responseVersionId') == vid or
                  (state == 'UNSET' and vid == 'null' and kind == 'Version' and item.get('responseVersionId') is None),
                  'GET_EXACT_VERSION')
            projection = dict(key=key, versionId=vid, kind=kind, isLatest=current, lastModified=instant.isoformat())
            if kind == 'Version':
                check(item.get('status') == 200 and item.get('responseDeleteMarker') in (None, 'false')
                      and bounded_integer(item.get('listedBytes'), 0, BODY_CAP)
                      and item['listedBytes'] == item['responseBytes'], 'GET_VERSION')
                projection.update(sizeBytes=item['responseBytes'], sha256=item['responseSha256'])
            else:
                check(item.get('status') in (404, 405) and item.get('responseDeleteMarker') == 'true'
                      and item.get('listedBytes') is None and
                      int(stamp(item['responseLastModified']).timestamp()) == int(instant.timestamp()), 'GET_MARKER')
            versions[key, vid] = projection
            if current:
                check(key not in latest, 'LATEST_DUPLICATE')
                latest[key] = projection
        cursor = page.get('nextKey'), page.get('nextVersion')
        if page['truncated']:
            check(valid_id(cursor[0], True) and valid_id(cursor[1]) and cursor not in visited, 'CONTINUATION')
            visited.add(cursor)
        else:
            check(cursor == (None, None), 'FINAL_CURSOR')
    check(set(latest) == {key for key, vid in versions} and consumed == data.get('totalResponseBytes')
          and consumed <= TOTAL_CAP, 'COVERAGE')
    if state == 'UNSET':
        check(all(v['versionId'] == 'null' and v['kind'] == 'Version' and v['isLatest'] for v in versions.values()),
              'UNVERSIONED_SEMANTICS')
    manifest = frozen_objects()
    for key, (length, checksum) in manifest.items():
        value = latest.get(key, {})
        check(value.get('kind') == 'Version' and (value.get('sizeBytes'), value.get('sha256')) == (length, checksum),
              'PG_PUBLISHED_OBJECT')
    return dict(versioning=state, inventory=[versions[k] for k in sorted(versions)],
                pageCount=len(pages), publishedObjects=len(manifest), totalResponseBytes=consumed,
                deleteMarkerCount=sum(v['kind'] == 'DeleteMarker' for v in versions.values()))


def qualify(actual, reference, actual_request, reference_request):
    """分别验证两个有界读取，然后逐版本对账。两份实跑命令/流/资源身份由共享分发独立重开。"""
    check(actual_request['role'] == 'actual' and reference_request['role'] == 'reference'
          and actual_request['attempt'] != reference_request['attempt']
          and actual_request['driverSha256'] == reference_request['driverSha256'], 'INDEPENDENT_RUNS')
    left = inspect_observation(actual, actual_request)
    right = inspect_observation(reference, reference_request)
    check((left['versioning'],left['inventory']) == (right['versioning'],right['inventory']), 'ARCHIVE_COMPARISON')
    return dict(status='RUSTFS_FROZEN_VERSIONS_VERIFIED', bucket=BUCKET, archive=ARCHIVE,
                versioning=left['versioning'], actualPages=left['pageCount'], referencePages=right['pageCount'],
                publishedObjects=left['publishedObjects'], inventoryEntries=len(left['inventory']),
                deleteMarkers=left['deleteMarkerCount'], inventorySha256=sha(encoded(left['inventory'])))


def offline_cases():
    """共享 Oracle 测试入口调用。合成 witness 只走资格解释器，不产生任何实跑回执。"""
    from copy import deepcopy
    driver = '1' * 64
    a = request('actual', ACTUAL, VOLUMES['actual'], driver, '1' * 32)
    r = request('reference', '2' * 64, VOLUMES['reference'], driver, '2' * 32)
    items = []
    moment = '2026-01-01T00:00:00Z'
    published = frozen_objects()
    def item(key, version_id, size, checksum, latest=True):
        return dict(key=key, versionId=version_id, kind='Version', isLatest=latest, lastModified=moment,
                    listedBytes=size, status=200, responseVersionId=version_id, responseDeleteMarker=None,
                    responseLastModified=moment, responseBytes=size, responseSha256=checksum)
    for key, (size, checksum) in sorted(published.items()):
        items.append(item(key, 'null', size, checksum))
    key = items[1]['key']
    items.insert(2, item(key, 'older/version+%2F', 3, sha(b'old'), False))
    marker = dict(key='z +/备份%2F', versionId='marker/+', kind='DeleteMarker', isLatest=True,
                  lastModified=moment, listedBytes=None, status=405, responseVersionId='marker/+',
                  responseDeleteMarker='true', responseLastModified=moment, responseBytes=0, responseSha256=sha(b''))
    items.append(marker)
    pages = []
    cursor = None, None
    for i in range(0, len(items), 2):
        rows = items[i:i+2]
        more = i + 2 < len(items)
        successor = (rows[-1]['key'], rows[-1]['versionId']) if more else (None, None)
        pages.append(dict(keyMarker=cursor[0], versionMarker=cursor[1], nextKey=successor[0], nextVersion=successor[1],
                          truncated=more, xmlBytes=10, xmlSha256=sha(encoded(rows)), rows=rows))
        cursor = successor
    record = dict(status='OBSERVED', binding=a, versioning='Enabled', versioningBytes=5, versioningSha256=sha(b'xml'),
                  pages=pages, totalResponseBytes=5+len(pages)*10+sum(row['responseBytes'] for row in items), elapsedMs=11)
    other = deepcopy(record)
    other['binding'] = r
    good = qualify(record, other, a, r)
    check(good['inventoryEntries'] == 7 and good['deleteMarkers'] == 1 and good['publishedObjects'] == 5,
          'OFFLINE_SUCCESS')
    failures = {}
    def rejects(name, mutate):
        changed = deepcopy(record)
        mutate(changed)
        try:
            qualify(changed, other, a, r)
        except ValueError as error:
            failures[name] = str(error)
            return
        raise AssertionError('accepted: ' + name)
    rejects('missing_cursor', lambda x: x['pages'][0].update(nextVersion=None))
    rejects('repeated_page', lambda x: x['pages'].__setitem__(1, x['pages'][0]))
    rejects('missing_terminal', lambda x: x['pages'].pop())
    rejects('duplicate_tuple', lambda x: x['pages'][1]['rows'].__setitem__(0, x['pages'][0]['rows'][1]))
    rejects('missing_literal_null_id', lambda x: x['pages'][0]['rows'][0].update(versionId=None))
    rejects('wrong_response_version', lambda x: x['pages'][0]['rows'][0].update(responseVersionId='wrong'))
    rejects('unproved_marker', lambda x: x['pages'][-1]['rows'][0].update(responseDeleteMarker=None))
    rejects('different_reference_version_bytes', lambda x: x['pages'][1]['rows'][0].update(responseSha256='e'*64))
    rejects('wrong_published_bytes', lambda x: x['pages'][0]['rows'][0].update(responseSha256='f'*64))
    rejects('reference_as_actual', lambda x: x.update(binding=r))
    rejects('counterfeit_fingerprint', lambda x: x['binding'].update(inputFingerprint='0'*64))
    return dict(status='PASS', synthetic=True, positive=good, rejected=failures)
