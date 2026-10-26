"""只读扫描全部可达 Git 历史与任务 refs；输出位置/类别，绝不输出疑似秘密原文。"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

STRONG = [
    ('private-key-material', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('github-token-like', re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}')),
    ('cloud-key-like', re.compile(r'AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{32,}')),
    ('credential-assignment-like', re.compile(r'(?im)^\s*["\x27]?(?:password|client_secret|api_key|access_token)["\x27]?\s*[:=]\s*["\x27]?(?!\$|<|\{|\[|REPLACE|CHANGEME|example|placeholder|set.locally)[A-Za-z0-9_+/=.-]{8,}')),
    ('potential-private-endpoint', re.compile(r'https?://(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|[^/\s"\x27]+\.(?:internal|corp|lan)(?=[:/\s"\x27]))', re.I)),
]
PATH = re.compile(r'(?i)(?:\.(?:pfx|p12|pem|key|dump|bak|sqlite3?|db)$|(?:^|/)(?:\.env(?:\.[^/]+)?|id_rsa|id_ed25519|credentials|auth\.json)$)')


def git(root, *args, input_bytes=None):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), '-c', 'color.ui=false', *args], input=input_bytes, capture_output=True)
    if result.returncode:
        raise RuntimeError('Git read failed: ' + args[0] + '; raw output suppressed')
    return result.stdout


def private_path(path):
    return bool(PATH.search(path)) and not path.endswith('/.env.example') and path != '.env.example' or any(marker in ('/' + path) for marker in ('/.tools/security/', '/.ssh/', '/.aws/'))


def scan(root, max_blob_bytes=64 * 1024 * 1024):
    root = Path(root).resolve()
    refs = git(root, 'for-each-ref', '--format=%(refname)').decode().splitlines()
    commits = git(root, 'rev-list', '--all').decode().splitlines()
    nonaux_commits = set(git(root, 'rev-list', '--exclude=refs/codex/*', '--all').decode().splitlines())
    path_map = defaultdict(set)
    commit_map = defaultdict(set)
    path_findings = set()
    # 枚举每个提交树，避免同一blob被复用为PFX等敏感路径时被rev-list首个路径掩盖。
    for commit in commits:
        for record in git(root, 'ls-tree', '-r', '-z', commit).split(b'\0'):
            if not record:
                continue
            info, name = record.split(b'\t', 1)
            mode, kind, oid = info.decode().split(' ')
            path = name.decode('utf-8', errors='replace')
            if kind != 'blob':
                continue
            path_map[oid].add(path)
            commit_map[oid].add(commit)
            if private_path(path):
                path_findings.add((oid, path))
    direct_refs = git(root, 'for-each-ref', '--format=%(refname) %(objectname) %(objecttype)').decode().splitlines()
    ref_sources = defaultdict(set)
    extra_types = {}
    for ref_line in direct_refs:
        ref, oid, kind = ref_line.split(' ')
        peeled = git(root, 'rev-parse', ref + '^{}').decode().strip() if kind == 'tag' else oid
        peeled_kind = git(root, 'cat-file', '-t', peeled).decode().strip()
        if kind == 'tag':
            path_map[oid].add('<tag:' + ref + '>')
            ref_sources[oid].add(ref)
            extra_types[oid] = 'tag'
        if peeled_kind == 'tree':
            for record in git(root, 'ls-tree', '-r', '-z', peeled).split(b'\0'):
                if not record:
                    continue
                info, name = record.split(b'\t', 1)
                mode, entry_kind, blob = info.decode().split(' ')
                if entry_kind == 'blob':
                    path = name.decode('utf-8', errors='replace')
                    path_map[blob].add(path)
                    ref_sources[blob].add(ref)
                    if private_path(path):
                        path_findings.add((blob, path))
        elif peeled_kind == 'blob':
            path_map[peeled].add('<blob-ref:' + ref + '>')
            ref_sources[peeled].add(ref)
    reachable = git(root, 'rev-list', '--objects', '--all', '--no-object-names').decode().splitlines()
    all_types = git(root, 'cat-file', '--batch-check=%(objectname) %(objecttype)', input_bytes=('\n'.join(reachable) + '\n').encode()).decode().splitlines() if reachable else []
    # 嵌套annotated tag即使没有独立ref，也必须检查消息；内容只进入内存，不输出。
    for object_line in all_types:
        oid, kind = object_line.split(' ')
        if kind == 'tag' and oid not in extra_types:
            extra_types[oid] = kind
            path_map[oid].add('<reachable-tag-object>')
    local_aux = [line.split(' ', 1)[0] for line in direct_refs if line.startswith('refs/codex/')]
    findings = [{'path': path, 'category': 'credential-file-path', 'blobOid': oid, 'commits': sorted(commit_map[oid]), 'assessment': 'REVIEW_REQUIRED; path is not proof of a real credential.'} for oid, path in sorted(path_findings)]
    oids = sorted(path_map)
    if oids:
        sizes = git(root, 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)', input_bytes=('\n'.join(oids) + '\n').encode()).decode().splitlines()
    else:
        sizes = []
    omitted = []
    batches = []
    batch = []
    batch_bytes = 0
    total_bytes = 0
    for line in sizes:
        oid, kind, count = line.split(' ')
        size = int(count)
        # PFX/私有路径仅报告位置；仅由本地辅助snapshot可达的私有数据不读取内容。
        names = path_map[oid]
        auxiliary_only = not (set(commit_map[oid]) & nonaux_commits) and bool(commit_map[oid] or ref_sources[oid]) and all(ref.startswith('refs/codex/') for ref in ref_sources[oid])
        if any(private_path(name) for name in names):
            omitted.append({'blobOid': oid, 'paths': sorted(names), 'reason': 'Credential/private path metadata only; content intentionally not read.', 'exposure': 'local-auxiliary-only-not-proof-of-publication' if auxiliary_only else 'reachable-ref-path-requires-review'})
            continue
        if size > max_blob_bytes:
            omitted.append({'blobOid': oid, 'sizeBytes': size, 'paths': sorted(path_map[oid]), 'reason': 'Blob exceeds explicit scan memory bound; content NOT_VERIFIED.'})
            continue
        if batch and (batch_bytes + size > 8 * 1024 * 1024 or len(batch) >= 64):
            batches.append(batch)
            batch = []
            batch_bytes = 0
        batch.append(oid)
        batch_bytes += size
        total_bytes += size
    if batch:
        batches.append(batch)
    for batch in batches:
        data = git(root, 'cat-file', '--batch', input_bytes=('\n'.join(batch) + '\n').encode())
        offset = 0
        for expected in batch:
            end = data.index(b'\n', offset)
            oid, kind, count = data[offset:end].decode().split(' ')
            if oid != expected or kind not in ('blob', 'tag'):
                raise RuntimeError('Unexpected Git batch response; content suppressed')
            size = int(count)
            content = data[end + 1:end + 1 + size]
            offset = end + 2 + size
            categories = set()
            for encoding in ['utf-8', 'utf-16-le', 'utf-16-be']:
                text = content.decode(encoding, errors='replace')
                categories.update(category for category, pattern in STRONG if pattern.search(text))
            for category in sorted(categories):
                for path in sorted(path_map[oid]):
                    findings.append({'path': path, 'category': category, 'blobOid': oid, 'commits': sorted(commit_map[oid]), 'sourceRefs': sorted(ref_sources[oid]), 'assessment': 'REVIEW_REQUIRED; finite pattern is not proof of production data or a live credential.'})
    # 提交消息也可能泄漏秘密，只记录commit和类别，不输出消息文本。
    for commit in commits:
        message = git(root, 'show', '-s', '--format=%B', commit).decode('utf-8', errors='replace')
        for category, pattern in STRONG:
            if pattern.search(message):
                findings.append({'path': '<commit-message>', 'category': category, 'commits': [commit], 'assessment': 'REVIEW_REQUIRED; message contents suppressed.'})
    return {'schemaVersion': 1, 'observedAt': datetime.now(timezone.utc).isoformat(), 'status': 'REVIEW_REQUIRED' if findings else ('PARTIAL' if omitted else 'PASS_FINITE_SCAN'), 'readOnly': True, 'scope': 'Every reachable commit tree and message, local/remote task refs, direct tree/blob refs and annotated tag messages; includes deleted files and historical evidence. Local Codex auxiliary refs are identified separately and are not proof of public exposure. No ignored/private working-tree files read; sensitive-path contents metadata-only.', 'refs': refs, 'commitCount': len(commits), 'uniqueBlobCount': len(oids) - len(extra_types), 'annotatedTagObjects': len(extra_types), 'localAuxiliaryRefsMetadata': local_aux, 'blobBytesScanned': total_bytes, 'findings': findings, 'unscannedBlobs': omitted, 'limitations': 'Finite patterns are not proof of absence of secrets/production/private business data. Semantic privacy, arbitrary obfuscation and unreachable/pruned remote objects are NOT_VERIFIED. Human triage required; no values printed and no history rewritten.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    try:
        result = scan(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result['findings'] or result['unscannedBlobs'] else 0
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED', 'category': type(error).__name__, 'reason': 'Git history scan failed; raw contents/output suppressed.'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
