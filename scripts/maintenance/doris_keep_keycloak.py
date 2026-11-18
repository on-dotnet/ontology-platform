"""用原镜像在无网络隔离副本上读取两个既有 H2；只输出通过的检查数量。"""
import argparse
import json
import re
import subprocess
import time

import doris_keep_preservation as keep


def verify_copy(volume, fact, directory, image):
    path = directory / (volume + '.tar')
    keep.require(path.relative_to(keep.ROOT).as_posix() == fact['privatePath'], 'PRIVATE_PATH_BINDING')
    # 通过 IFEXISTS 绑定唯一恢复数据库，默认数据库不能落到新库；私有导出只流入容器内无输出的定型匹配器。
    script = r'''
set -euo pipefail
umask 077
shopt -s globstar nullglob
db=(/opt/keycloak/data/**/*.mv.db)
test "${#db[@]}" = 1
test -s "${db[0]}"
export KC_DB_URL="jdbc:h2:file:${db[0]%.mv.db};IFEXISTS=TRUE;DB_CLOSE_ON_EXIT=FALSE;NON_KEYWORDS=VALUE"
export JAVA_OPTS_KC_HEAP="-Xms64m -Xmx320m"
runtime=/opt/keycloak/data/runtime
mkfifo -m 0600 /tmp/realm.pipe
# 文件导出器可只记录数量；匹配实际导出流，读到 EOF，不回显匹配行。
LC_ALL=C grep -E '"realm"[[:space:]]*:[[:space:]]*"g2-[a-f0-9]{16}"' </tmp/realm.pipe >/dev/null &
checker=$!
"$runtime/bin/kc.sh" export --optimized --file=/tmp/realm.pipe > /tmp/verify.log 2>&1 || exit 21
grep -q 'KC-SERVICES0035' /tmp/verify.log || exit 22
wait "$checker" || exit 23
'''
    with keep.scratch() as name, keep.helper(keep.mount(name, '/slot', False), write=True) as writer:
        keep.start(writer)
        keep.restore_empty(writer, path, fact['sha256'])
        # 旧栈 12 GiB + 写者 512 MiB + 检查 896 MiB + 2 GiB 余量。
        cid = keep.execute('create', '--network=none', '--read-only', '--pull=never', '--memory=896m', '--memory-swap=896m',
                           '--cpus=1', '--pids-limit=192', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                           '--user=501:20', '--log-driver=none', '--tmpfs', '/tmp:size=32m,mode=1777',
                           '--label', 'ontology.task-id=' + keep.TASK, '--label', 'ontology.run-id=' + keep.RUN,
                           '--label', keep.LABEL + '=' + keep.ATTEMPT, *keep.mount(name, '/opt/keycloak/data', False),
                           '--entrypoint=/bin/bash', image, '-c', script)
        keep.require(bool(re.fullmatch('[0-9a-f]{64}', cid)), 'PROBE_ID')
        keep.record('created-keycloak-check', cid)
        try:
            keep.assert_owner(cid)
            keep.execute('start', cid)
            try:
                result = keep.execute('wait', cid, limit=90)
            except subprocess.TimeoutExpired:
                # 只向本次隔离检查发优雅停止请求；保留未退出实例及其卷。
                keep.assert_owner(cid)
                keep.execute('stop', '--timeout=-1', cid, limit=15)
                raise ValueError('KEYCLOAK_OFFLINE_DEADLINE') from None
            state = keep.helper_state(cid)
            keep.record('keycloak-offline-exit', cid, **state)
            keep.require(result == '0' and state['state']['ExitCode'] == 0 and not state['state']['OOMKilled'],
                         'KEYCLOAK_OFFLINE_EXIT_' + result)
        finally:
            keep.assert_owner(cid)
            if keep.execute('inspect', '-f', '{{.State.Running}}', cid) == 'false':
                keep.execute('rm', cid)
                keep.require(cid not in keep.execute('ps', '-aq', '--no-trunc', '--filter', 'id=' + cid).split(), 'PROBE_REMOVE')
                keep.record('removed-keycloak-check', cid)
        return cid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt')
    attempt = parser.parse_args().attempt
    keep.require(bool(re.fullmatch('[0-9a-f]{32}', attempt)), 'ATTEMPT_ID')
    rows, volumes = keep.inventory()
    memory, cpu = map(int, keep.execute('info', '-f', '{{.MemTotal}} {{.NCPU}}').split())
    running = set(keep.execute('ps', '-q', '--no-trunc').split())
    keep.require(memory >= (12 + 2) * 1024**3 + 1408 * 1024**2 and cpu >= 11 and
                 running == {row['containerId'] for row in rows}, 'VM_RESERVE')
    data = json.loads((keep.BASE / (attempt + '-capture-rehearse.json')).read_text())
    directory = keep.PRIVATE / attempt
    keep.require(directory.resolve() == directory and data['attempt'] == attempt and data['status'] == 'PASS'
                 and set(data['volumeFacts']) == set(volumes), 'RECEIPT_BINDING')
    results = {}
    for row in rows:
        if row['service'] == 'keycloak-test':
            volume = row['project'] + '_keycloak-data'
            try:
                cid = verify_copy(volume, data['volumeFacts'][volume], directory, row['imageId'])
                results[volume] = {'status': 'PASS', 'isolatedProbe': cid}
            except ValueError as error:
                results[volume] = {'status': 'FAIL', 'reason': str(error)}
    receipt = {'checkedAt': time.time(), 'sourceAttempt': attempt, 'isolatedRealmRead': results,
               'pointInTimeApplicationConsistency': 'NOT_VERIFIED'}
    (keep.BASE / (keep.ATTEMPT + '-keycloak-read.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print('isolated realm reads', [(v, r['status'], r.get('reason')) for v, r in results.items()])
    return 0 if len(results) == 2 and all(r['status'] == 'PASS' for r in results.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
