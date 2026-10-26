#!/usr/bin/env python3
"""Bounded project resource cleanup; import is read-only and never invokes CLI.

Plan schemaVersion=1 requires taskId, project, repositoryRoot, gitCommonDir,
originUrl, expectedMainSha (40 lowercase hex), createdAt/expiresAt (UTC-aware
ISO8601, maximum lifetime 24h), allowedWorktreeRoots (absolute approved parent
paths), protectedWorktrees, keep (exact resource identifiers), and operations.
Every operation has type, target, ownershipEvidence={commit,path,taskId,closed:
true,synthetic:true}. Evidence must be a text blob in the current committed
history containing the exact target/taskId and CLOSED/已关闭 and synthetic/合成/
可再生 markers. Approval must be reviewed before plan creation; text markers are
an auditable assertion, not a replacement for independent human review.

History operations additionally require historyBackend={context,engineId,bridgeId,
buildxVersion,buildkitVersion,driver,nodeName}; audited client v0.38.1 and server
v0.34.0 only. Offset inspection avoids the server zero-reference tombstone bug;
strong post-delete diagnosis distinguishes durable absence from an in-memory mark.

Types and additional fields:
 git-local-branch / git-remote-branch: expectedTip
 worktree: expectedTip, expectedBranch
 cache: treeRoot, expectedTip, fingerprint (metadata_fingerprint); root links
        additionally require linktarget; archived small-file exceptions require
        expectedFileSha256, archiveCommittedPath (same bytes in HEAD).
 docker-container: expectedName, expectedImage, expectedState, expectedMounts
 docker-volume: expectedDriver, expectedCreatedAt
 docker-image: expectedTags
 docker-history: builder='desktop-linux', expectedContext, expectedVcs,
                 expectedRevision, expectedStatus, fingerprint (safe projection)

Keep identifiers apply across operations; paths also protect descendants and
ancestors. SHA/image/container/ref formats are exact. Only explicit operation
commands exist. No shell, force update, prune, environment inspection, or network
resource deletion is supported. Remote branch deletion uses an exact old-tip
lease with --delete: this is compare-and-delete, never a commit/history update. DryRun performs read-only CLI preflight with
GIT_OPTIONAL_LOCKS=0; Apply creates a new JSONL log only after all preflights pass,
revalidates each step and stops at the first failure. Filesystem metadata is
fingerprinted without reading private file bytes or following links. Cache
operations require POSIX no-follow directory descriptors; unsupported platforms
refuse those operations rather than using an unsafe recursive fallback.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

PROJECT = 'on-dotnet/ontology-platform'
SHA = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}\Z')
BRANCH = re.compile(r'codex/[A-Za-z0-9][A-Za-z0-9._/-]*\Z')
PRIVATE = re.compile(r'(^\.env($|\.)|\.pfx$|\.p12$|\.pem$|\.key$|\.crt$|^credentials?$|^secrets?$|^private($|[-_.])|^\.runtime$|^auth\.json$|^\.ssh$|^\.aws$)', re.I)
TYPES = {'git-local-branch', 'git-remote-branch', 'worktree', 'cache', 'docker-container', 'docker-volume', 'docker-image', 'docker-history'}
CONTAINER_FORMAT = '{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},"State":{"Status":{{json .State.Status}}},"Mounts":{{json .Mounts}}}'
VOLUME_FORMAT = '{"Name":{{json .Name}},"Driver":{{json .Driver}},"CreatedAt":{{json .CreatedAt}}}'
IMAGE_FORMAT = '{"Id":{{json .Id}},"RepoTags":{{json .RepoTags}}}'
HISTORY_FIELDS = ('Ref', 'Name', 'Context', 'Dockerfile', 'VCSRepository', 'VCSRevision', 'Status')
HISTORY_FORMAT = '{' + ','.join('"'+k+'":{{printf "%q" .'+k+'}}' for k in HISTORY_FIELDS) + '}'


class Refused(Exception):
    """A safety precondition or exact operation failed; leave remaining state alone."""


class CommandFailed(Refused):
    """CLI failure with exact exit status, without exposing stderr contents."""
    def __init__(self, args, code):
        self.command = [str(x) for x in args]
        self.exit_code = code
        super().__init__('Command failed (exit %s): %s' % (code, ' '.join(self.command)))


def require(condition, message):
    if not condition:
        raise Refused(message)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def run(args, cwd=None, acceptable=(0,)):
    """Execute an argument vector; never expose stderr or inherited environment."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0', GH_PROMPT_DISABLED='1')
    try:
        result = subprocess.run([str(x) for x in args], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refused('CLI unavailable or timed out: ' + str(args[0])) from ex
    if result.returncode not in acceptable:
        raise CommandFailed(args, result.returncode)
    return result


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=strict_object)
    except (ValueError, TypeError) as ex:
        raise Refused('Invalid JSON response or plan') from ex


def absolute(value):
    require(isinstance(value, str) and '\x00' not in value and Path(value).is_absolute(), 'Absolute path required')
    p = Path(value)
    require('..' not in p.parts and str(p) == os.path.normpath(value), 'Noncanonical path or traversal')
    return p


def under(path, parent):
    return path == parent or parent in path.parents


def no_parent_links(path, boundary):
    require(under(path, boundary), 'Path outside boundary')
    current = boundary
    require(not current.is_symlink(), 'Symlink boundary refused')
    for part in path.relative_to(boundary).parts[:-1]:
        current = current / part
        require(not current.is_symlink(), 'Parent symlink refused')
        require(current.is_dir(), 'Missing parent directory')


def secure_parent(path):
    """Open each absolute parent using O_NOFOLLOW; refuse unsupported platforms."""
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and os.open in os.supports_dir_fd, 'Safe no-follow filesystem operations unavailable on this platform')
    path = absolute(str(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def metadata_entry(st, rel, linktarget):
    require(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode), 'Special cache file refused')
    return dict(path=rel, mode=st.st_mode, size=st.st_size, mtime_ns=st.st_mtime_ns, inode=st.st_ino, device=st.st_dev, linktarget=linktarget)


def metadata_entries(path):
    """Return lstat-only entries through no-follow descriptors; never read bytes."""
    path = Path(path)
    entries = []
    def visit(parent, name, rel):
        st = os.stat(name, dir_fd=parent, follow_symlinks=False)
        link = os.readlink(name, dir_fd=parent) if stat.S_ISLNK(st.st_mode) else None
        entry = metadata_entry(st, rel, link)
        entries.append(entry)
        if stat.S_ISDIR(st.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                require(metadata_entry(os.fstat(child),rel,None) == entry, 'Directory changed while fingerprinting')
                names = sorted(os.listdir(child))
                for item in names:
                    visit(child, item, str(PurePosixPath(rel) / item))
                require(metadata_entry(os.fstat(child),rel,None) == entry and sorted(os.listdir(child)) == names, 'Directory changed while fingerprinting')
            finally:
                os.close(child)
    parent = secure_parent(path)
    try:
        visit(parent, path.name, '.')
    finally:
        os.close(parent)
    return entries


def remove_exact_cache(path, expected):
    """Delete only snapshotted entries using directory descriptors and no-follow."""
    by_path = {e['path']: e for e in expected}
    def visit(parent, name, rel):
        st = os.stat(name, dir_fd=parent, follow_symlinks=False)
        link = os.readlink(name, dir_fd=parent) if stat.S_ISLNK(st.st_mode) else None
        require(metadata_entry(st, rel, link) == by_path.get(rel), 'Cache entry changed during deletion')
        if stat.S_ISDIR(st.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                require(metadata_entry(os.fstat(child),rel,None) == by_path[rel], 'Directory replaced during deletion')
                names = sorted(os.listdir(child))
                required_names = sorted(PurePosixPath(key).name for key in by_path if key != '.' and str(PurePosixPath(key).parent) == rel)
                require(names == required_names, 'Cache entries changed during deletion')
                for item in names:
                    visit(child, item, str(PurePosixPath(rel) / item))
                require(not os.listdir(child), 'New cache entry during deletion')
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require((current.st_ino,current.st_dev) == (st.st_ino,st.st_dev), 'Directory replaced before removal')
                os.rmdir(name, dir_fd=parent)
            finally:
                os.close(child)
        else:
            os.unlink(name, dir_fd=parent)
    parent = secure_parent(path)
    try:
        visit(parent, path.name, '.')
    finally:
        os.close(parent)


def approved_public_cache_asset(tree, cache, entry):
    """Match one official CC0 npm asset; never exempt a generic private filename."""
    target=cache / entry['path']
    approved='node_modules/.pnpm/language-subtag-registry@0.3.23/node_modules/language-subtag-registry/data/json/private-use.json'
    if target.relative_to(tree).as_posix()!=approved or entry['size']!=22 or not stat.S_ISREG(entry['mode']):
        return False
    parent=secure_parent(target)
    descriptor=None
    try:
        descriptor=os.open(target.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
        require(metadata_entry(os.fstat(descriptor),entry['path'],None)==entry,'Approved public asset changed before read')
        raw=os.read(descriptor,23)
        require(metadata_entry(os.fstat(descriptor),entry['path'],None)==entry and metadata_entry(os.stat(target.name,dir_fd=parent,follow_symlinks=False),entry['path'],None)==entry,'Approved public asset changed during read')
        require(len(raw)==22 and hashlib.sha256(raw).hexdigest()=='74989640a41c9c1c4a7bfab371b4e6f30a4e81f3a848381faa0ed622ae400cca','Approved public asset bytes changed')
        return True
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


def metadata_fingerprint(path):
    """Public read-only planner API: SHA256 of lstat metadata, including link text."""
    return digest(metadata_entries(Path(path)))


def history_refs(builder='desktop-linux'):
    """Read a ref-only list; a blank server ref does not pin individual records."""
    require(builder=='desktop-linux','Unsupported history builder')
    output=run(['docker','buildx','history','ls','--builder',builder,'--format','{{.Ref}}']).stdout
    refs=[]
    for line in output.splitlines():
        require(re.fullmatch(r'(?:desktop-linux/desktop-linux/)?[a-z0-9]{6,64}',line),'Invalid history ref list')
        refs.append(line.split('/')[-1])
    require(len(refs)==len(set(refs)),'Ambiguous duplicate history refs')
    return refs


def safe_docker_snapshot(kind, target, builder='desktop-linux'):
    """Public planner API; inspect only whitelisted, non-secret Docker fields."""
    if kind == 'docker-container':
        value = read_json(run(['docker', 'container', 'inspect', '--format', CONTAINER_FORMAT, target]).stdout)
        require(isinstance(value, dict), 'Invalid container schema')
        mounts = value.get('Mounts')
        require(isinstance(mounts, list), 'Invalid mounts schema')
        return dict(Id=value.get('Id'), Name=value.get('Name'), Image=value.get('Image'), State=(value.get('State') or {}).get('Status'), Mounts=[{k: m[k] for k in ('Type', 'Name', 'Source', 'Destination', 'RW') if k in m} for m in mounts])
    if kind == 'docker-volume':
        value = read_json(run(['docker', 'volume', 'inspect', '--format', VOLUME_FORMAT, target]).stdout)
        require(isinstance(value, dict), 'Invalid volume schema')
        return {k: value.get(k) for k in ('Name', 'Driver', 'CreatedAt')}
    if kind == 'docker-image':
        value = read_json(run(['docker', 'image', 'inspect', '--format', IMAGE_FORMAT, target]).stdout)
        require(isinstance(value, dict), 'Invalid image schema')
        return dict(Id=value.get('Id'), RepoTags=sorted(value.get('RepoTags') or []))
    require(kind == 'docker-history' and builder == 'desktop-linux', 'Unsupported Docker snapshot')
    require(re.fullmatch(r'[a-z0-9]{6,64}',target),'Invalid history target')
    refs=history_refs(builder)
    require(target in refs,'History target not listed')
    # Buildx maps ^offset to a blank server Ref. An exact Ref would create a
    # zero-count key in BuildKit v0.34.0 and make later deletion memory-only.
    offset='^'+str(refs.index(target))
    value = read_json(run(['docker', 'buildx', 'history', 'inspect', '--builder', builder, '--format', HISTORY_FORMAT, offset]).stdout)
    require(isinstance(value,dict) and value.get('Ref')==target,'History offset moved or selected another record')
    require(isinstance(value, dict) and all(isinstance(value.get(k), str) for k in HISTORY_FIELDS), 'Unsupported history CLI schema')
    return {k: value[k] for k in HISTORY_FIELDS}


safeDockerSnapshot = safe_docker_snapshot


class Cleaner:
    def __init__(self, root, plan):
        self.root = absolute(root).resolve()
        self.plan = plan
        self.done = set()
        self.log = None
        self.ops = []

    def git(self, *args, cwd=None, acceptable=(0,)):
        return run(['git', '--no-optional-locks', '-C', cwd or self.root, *args], acceptable=acceptable)

    def validate_time(self):
        try:
            start, end = (dt.datetime.fromisoformat(self.plan[k].replace('Z','+00:00')) for k in ('createdAt','expiresAt'))
            now = dt.datetime.now(dt.timezone.utc)
            require(start.tzinfo and end.tzinfo and start <= now < end and dt.timedelta(0) < end-start <= dt.timedelta(hours=24), 'Plan expired, future-dated, or excessive TTL')
        except (TypeError, ValueError) as ex:
            raise Refused('Invalid plan times') from ex

    def main_unchanged(self):
        require(self.git('remote','get-url','--all','origin').stdout.splitlines() == [self.plan['originUrl']],'Effective origin fetch URL changed')
        require(self.git('remote','get-url','--push','--all','origin').stdout.splitlines() == [self.plan['originUrl']],'Effective origin push URL changed')
        require(self.git('config','--get-all','remote.origin.url').stdout.strip() == self.plan['originUrl'],'Origin URL changed')
        require(self.git('config','--get-all','remote.origin.pushurl',acceptable=(0,1)).stdout.strip() in ('',self.plan['originUrl']),'Origin push URL changed')
        require(self.git('rev-parse', 'refs/remotes/origin/main').stdout.strip() == self.plan['expectedMainSha'], 'origin/main changed')
        live = self.git('ls-remote', '--heads', 'origin', 'refs/heads/main').stdout.split()
        require(live == [self.plan['expectedMainSha'], 'refs/heads/main'], 'Live main changed')
        prs = read_json(run(['gh', 'pr', 'list', '--repo', PROJECT, '--state', 'open', '--json', 'number,headRefName', '--limit', '1000'], cwd=self.root).stdout)
        require(isinstance(prs, list) and not prs, 'Open PRs or unreadable PR state')

    def registered(self):
        raw = self.git('worktree', 'list', '--porcelain', '-z').stdout
        result, record = {}, {}
        for field in raw.split('\0'):
            if not field:
                if 'worktree' in record:
                    result[record['worktree']] = record
                record = {}
            else:
                key, _, value = field.partition(' ')
                record[key] = value
        if 'worktree' in record:
            result[record['worktree']] = record
        return result

    def ownership(self, op):
        evidence = op.get('ownershipEvidence')
        require(isinstance(evidence, dict), 'Missing ownership evidence')
        require(evidence.get('closed') is True and evidence.get('synthetic') is True, 'Closed synthetic task proof required')
        commit, path, task = (evidence.get(k) for k in ('commit', 'path', 'taskId'))
        require(isinstance(commit, str) and SHA.fullmatch(commit), 'Invalid evidence commit')
        require(isinstance(path, str) and not path.startswith('-') and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts and ':' not in path, 'Invalid evidence path')
        require(isinstance(task, str) and re.fullmatch(r'[A-Za-z0-9_-]{3,100}', task), 'Invalid evidence task')
        require(self.git('merge-base', '--is-ancestor', commit, 'HEAD', acceptable=(0,1)).returncode == 0, 'Evidence commit outside current history')
        require(self.git('cat-file', '-t', commit + ':' + path).stdout.strip() == 'blob', 'Evidence is not committed blob')
        size = int(self.git('cat-file', '-s', commit + ':' + path).stdout)
        require(size <= 4_000_000, 'Evidence blob oversized')
        text = self.git('show', commit + ':' + path).stdout
        require(task in text and op['target'] in text and re.search(r'CLOSED|已关闭', text, re.I) and re.search(r'synthetic|合成|可再生', text, re.I), 'Ownership evidence does not prove this exact target')

    def setup(self):
        p = self.plan
        require(isinstance(p, dict), 'Plan must be object')
        required = {'schemaVersion','taskId','project','repositoryRoot','gitCommonDir','originUrl','expectedMainSha','createdAt','expiresAt','allowedWorktreeRoots','protectedWorktrees','keep','operations'}
        require(required <= p.keys(), 'Missing plan fields')
        require(type(p['schemaVersion']) is int and p['schemaVersion'] == 1 and p['project'] == PROJECT and p['taskId'] == 'PRE-G3-CLEANUP-FIX-002', 'Plan identity mismatch')
        require(absolute(p['repositoryRoot']).resolve() == self.root, 'Repository root mismatch')
        require(self.git('rev-parse', '--show-toplevel').stdout.strip() == str(self.root), 'Root must be Git toplevel')
        common = Path(self.git('rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip()).resolve()
        require(absolute(p['gitCommonDir']).resolve() == common, 'Git common directory mismatch')
        require(isinstance(p['originUrl'], str) and re.fullmatch(r'(https://github\.com/|git@github\.com:)on-dotnet/ontology-platform(?:\.git)?', p['originUrl']), 'Origin project mismatch')
        require(self.git('config', '--get-all', 'remote.origin.pushurl', acceptable=(0,1)).stdout.strip() in ('', p['originUrl']), 'Origin push URL mismatch')
        require(self.git('config', '--get-all', 'remote.origin.url').stdout.strip() == p['originUrl'], 'Origin URL mismatch')
        require(isinstance(p['expectedMainSha'],str) and SHA.fullmatch(p['expectedMainSha']), 'Invalid main SHA')
        self.validate_time()
        require(all(isinstance(p[k],list) for k in ('allowedWorktreeRoots','protectedWorktrees','keep','operations')), 'Plan collections must be arrays')
        self.boundaries = [absolute(x).resolve() for x in p['allowedWorktreeRoots']]
        require(self.boundaries and all(x != Path(x.anchor) and x != Path.home() for x in self.boundaries), 'Unsafe worktree parent boundary')
        self.protected = {str(absolute(x).resolve()) for x in p['protectedWorktrees']} | {str(self.root)}
        require(all(isinstance(x,str) and x for x in p['keep']), 'Invalid keep identifier')
        self.keep = set(p['keep']) | {'main','bridge','host','none'}
        self.ops = p['operations']
        require(self.ops and len(self.ops) <= 1000, 'Empty or excessive operation list')
        ids = set()
        for i, op in enumerate(self.ops):
            require(isinstance(op,dict) and op.get('type') in TYPES and isinstance(op.get('target'),str) and op['target'] and '\x00' not in op['target'], 'Invalid operation')
            key = (op['type'],op['target'])
            require(key not in ids, 'Duplicate operation')
            ids.add(key)
            require(op['target'] not in self.keep, 'Keep target refused')
            self.ownership(op)
            if op['type'] == 'cache':
                for earlier in self.ops[:i]:
                    if earlier['type'] == 'cache':
                        a,b=absolute(earlier['target']),absolute(op['target'])
                        require(not under(a,b) and not under(b,a), 'Overlapping cache operations')
        self.root_head = self.git('rev-parse','HEAD').stdout.strip()
        self.main_unchanged()
        for op in self.ops:
            self.check(op, preflight=True)

    def history_backend(self):
        """Pin the reviewed single-node daemon generation and diagnostic contract."""
        expected=self.plan.get('historyBackend')
        require(isinstance(expected,dict) and set(expected)=={'context','engineId','bridgeId','buildxVersion','buildkitVersion','driver','nodeName'},'Exact reviewed history backend required')
        require(expected['context']=='desktop-linux' and expected['driver']=='docker' and expected['nodeName']=='desktop-linux' and expected['buildkitVersion']=='v0.34.0','Unaudited history backend')
        require(isinstance(expected['buildxVersion'],str) and re.fullmatch(r'github\.com/docker/buildx v0\.38\.1 [0-9a-f]{40}',expected['buildxVersion']),'Unaudited history diagnostic version')
        require(isinstance(expected['engineId'],str) and re.fullmatch(r'[A-Za-z0-9-]{6,100}',expected['engineId']) and isinstance(expected['bridgeId'],str) and HEX64.fullmatch(expected['bridgeId']),'Invalid history daemon identity')
        require(run(['docker','context','show']).stdout.strip()==expected['context'],'History Docker context changed')
        require(run(['docker','info','--format','{{.ID}}']).stdout.strip()==expected['engineId'],'History daemon ID changed')
        require(run(['docker','network','inspect','bridge','--format','{{.Id}}']).stdout.strip()==expected['bridgeId'],'History daemon generation changed')
        require(run(['docker','buildx','version']).stdout.strip()==expected['buildxVersion'],'History CLI version changed')
        topology=run(['docker','buildx','inspect','desktop-linux']).stdout
        values=lambda key:[line.split(':',1)[1].strip() for line in topology.splitlines() if line.startswith(key+':')]
        require(values('Name')==['desktop-linux','desktop-linux'] and values('Driver')==['docker'] and values('Endpoint')==['desktop-linux'] and values('BuildKit version')==[expected['buildkitVersion']],'History builder topology/version changed')

    def check_tip(self, op, tip):
        require(isinstance(op.get('expectedTip'),str) and SHA.fullmatch(op['expectedTip']) and op['expectedTip'] == tip, 'Target tip changed')

    def ancestor(self, tip, cherry=False):
        if self.git('merge-base','--is-ancestor',tip,self.plan['expectedMainSha'],acceptable=(0,1)).returncode == 0:
            return
        require(cherry, 'Nonancestor branch refused')
        lines = self.git('cherry',self.plan['expectedMainSha'],tip).stdout.splitlines()
        require(lines and all(x.startswith('- ') for x in lines), 'Unique unintegrated commits refused')

    def tree_state(self, tree, op):
        require(not tree.is_symlink(), 'Worktree symlink refused')
        require(str(tree) in self.registered(), 'Unregistered worktree')
        common = Path(self.git('rev-parse','--path-format=absolute','--git-common-dir',cwd=tree).stdout.strip()).resolve()
        require(common == absolute(self.plan['gitCommonDir']).resolve(), 'Cross-project worktree')
        self.check_tip(op,self.git('rev-parse','HEAD',cwd=tree).stdout.strip())
        require(not self.git('status','--porcelain=v1','--untracked-files=all',cwd=tree).stdout, 'Dirty or untracked worktree')
        return self.registered()[str(tree)]

    def worktree_path(self, value):
        path=absolute(value)
        matches=[x for x in self.boundaries if under(path,x) and path != x]
        require(matches, 'Worktree outside approved parents')
        no_parent_links(path,max(matches,key=lambda x:len(x.parts)))
        require(path.resolve() == path, 'Noncanonical worktree')
        return path

    def ignored_paths(self, tree):
        raw=self.git('ls-files','--others','--ignored','--exclude-standard','-z',cwd=tree).stdout
        return [tree / x for x in raw.split('\0') if x]

    def protect_path(self, path):
        """An exact keep path protects both its contents and containing removal."""
        for keep in self.keep:
            if Path(keep).is_absolute():
                kept=absolute(keep)
                require(not under(kept,path) and not under(path,kept),'Removal overlaps keep path')

    def cache_state(self, op):
        tree=self.worktree_path(op.get('treeRoot'))
        path=absolute(op['target'])
        require(path != tree and under(path,tree), 'Cache outside tree')
        no_parent_links(path,tree)
        require(not any(under(tree,Path(p)) or under(Path(p),tree) for p in self.protected),'Protected cache worktree')
        record=self.tree_state(tree,op)
        require(not any(flag in record for flag in ('locked','prunable','bare')) and record.get('branch')!='refs/heads/main','Locked, main, or invalid cache worktree')
        self.protect_path(path)
        rel=path.relative_to(tree).as_posix()
        parts=PurePosixPath(rel).parts
        ordinary = any(x in ('bin','obj','node_modules','.next','.turbo','__pycache__') for x in parts) or rel in ('.tools/nuget','.tools/pnpm','.tools/pnpm-store','.tools/pythonlibs','apps/web/tsconfig.tsbuildinfo')
        archived = rel in ('apps/web/artifacts/test-results/g2/.last-run.json','apps/web/artifacts/test-results/ui/.last-run.json','artifacts/governance-integration.json')
        require(ordinary or archived, 'Cache path not an approved regenerable category')
        require(not any(PRIVATE.search(x) for x in parts), 'Private cache path refused')
        entries=metadata_entries(path)
        require(isinstance(op.get('fingerprint'),str) and HEX64.fullmatch(op['fingerprint']) and digest(entries) == op['fingerprint'], 'Cache metadata changed')
        # Validate the whole metadata snapshot before reading the one approved public asset.
        for entry in entries:
            if any(PRIVATE.search(part) for part in PurePosixPath(entry['path']).parts):
                require(approved_public_cache_asset(tree,path,entry),'Private-looking file inside cache')
        if path.is_symlink():
            require(op.get('linktarget') == os.readlink(path), 'Cache linktarget changed')
        tracked=self.git('ls-files','-z','--',rel,cwd=tree).stdout
        require(not tracked, 'Tracked cache path refused')
        if archived:
            require(path.is_file() and not path.is_symlink() and path.stat().st_size < 4_000_000, 'Archived file must be bounded regular file')
            raw=path.read_bytes()
            require(op.get('expectedFileSha256') == hashlib.sha256(raw).hexdigest(), 'Archived file SHA mismatch')
            ap=op.get('archiveCommittedPath')
            require(isinstance(ap,str) and not PurePosixPath(ap).is_absolute() and '..' not in PurePosixPath(ap).parts and ':' not in ap and not ap.startswith('-'), 'Invalid archive proof path')
            blob=self.git('rev-parse','HEAD:'+ap).stdout.strip()
            archived_bytes=subprocess.run(['git','--no-optional-locks','-C',str(self.root),'cat-file','blob',blob],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,GIT_OPTIONAL_LOCKS='0'),check=False)
            require(archived_bytes.returncode == 0 and archived_bytes.stdout == raw, 'Committed archive differs')
            if rel.endswith('.last-run.json'):
                value=read_json(raw)
                require(value == {'status':'passed','failedTests':[]}, 'Failed or nonstandard test result refused')
        return dict(fingerprint=digest(entries),logicalBytes=sum(x['size'] for x in entries if stat.S_ISREG(x['mode'])),entries=len(entries))

    def container_ids(self):
        ids=[x for x in run(['docker','container','ls','--all','--no-trunc','--quiet']).stdout.splitlines() if x]
        require(all(HEX64.fullmatch(x) for x in ids), 'Invalid container IDs')
        return ids

    def references(self, op, preflight):
        refs=[]
        index=self.ops.index(op)
        prior={x['target'] for x in self.ops[:index] if x['type']=='docker-container'} if preflight else set()
        for ident in self.container_ids():
            c=safe_docker_snapshot('docker-container',ident)
            used = c['Image']==op['target'] if op['type']=='docker-image' else any(m.get('Type')=='volume' and m.get('Name')==op['target'] for m in c['Mounts'])
            if used:
                require(ident in prior and c['State'] in ('exited','created','dead'), 'Docker resource has container reference')
                refs.append(ident)
        return refs

    def check(self, op, preflight=False):
        typ,target=op['type'],op['target']
        require(target not in self.keep, 'Kept target')
        if typ.startswith('git-'):
            require(BRANCH.fullmatch(target) and '..' not in target and '@{' not in target and not target.endswith(('/', '.lock','.')), 'Unsafe branch name')
            require(self.git('check-ref-format','--branch',target).returncode==0,'Invalid branch')
            trees=self.registered()
            attached=[p for p,r in trees.items() if r.get('branch')=='refs/heads/'+target]
            if preflight:
                index=self.ops.index(op)
                removals={x['target'] for x in self.ops[:index] if x['type']=='worktree'}
                require(all(p in removals and p not in self.protected for p in attached),'Active worktree branch')
            else:
                require(not attached,'Branch still attached to worktree')
            if typ=='git-local-branch':
                tip=self.git('rev-parse','refs/heads/'+target).stdout.strip()
            else:
                live=self.git('ls-remote','--heads','origin','refs/heads/'+target).stdout.split()
                require(len(live)==2 and live[1]=='refs/heads/'+target,'Remote branch missing or ambiguous')
                tip=live[0]
            self.check_tip(op,tip)
            self.ancestor(tip)
            return dict(tip=tip)
        if typ=='worktree':
            tree=self.worktree_path(target)
            require(not any(under(tree,Path(p)) or under(Path(p),tree) for p in self.protected),'Protected worktree')
            self.protect_path(tree)
            record=self.tree_state(tree,op)
            require('locked' not in record and 'prunable' not in record and 'bare' not in record,'Locked or invalid worktree')
            branch=op.get('expectedBranch')
            require(isinstance(branch,str) and BRANCH.fullmatch(branch) and record.get('branch')=='refs/heads/'+branch,'Worktree branch changed')
            self.ancestor(op['expectedTip'],cherry=True)
            ignored=self.ignored_paths(tree)
            if preflight:
                index=self.ops.index(op)
                caches=[absolute(x['target']) for x in self.ops[:index] if x['type']=='cache' and x.get('treeRoot')==target]
                require(all(any(under(x,c) for c in caches) for x in ignored),'Ignored data not covered by exact prior cache operations')
            else:
                require(not ignored,'Ignored data remains at removal')
            return dict(tip=op['expectedTip'],branch=branch,ignoredCount=len(ignored))
        if typ=='cache':
            return self.cache_state(op)
        if typ=='docker-container':
            require(HEX64.fullmatch(target),'Full container ID required')
            c=safe_docker_snapshot(typ,target)
            require(c['Id']==target and c['Name']==op.get('expectedName') and c['Image']==op.get('expectedImage') and IMAGE.fullmatch(c['Image']),'Container identity changed')
            require(c['State']==op.get('expectedState') and c['State'] in ('exited','created','dead'),'Container active or state changed')
            require(c['Mounts']==op.get('expectedMounts'),'Container mounts changed')
            return c
        if typ=='docker-volume':
            require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}',target),'Invalid volume name')
            v=safe_docker_snapshot(typ,target)
            require(v==dict(Name=target,Driver=op.get('expectedDriver'),CreatedAt=op.get('expectedCreatedAt')) and v['Driver']=='local' and isinstance(v['CreatedAt'],str) and v['CreatedAt'],'Volume identity changed')
            v['references']=self.references(op,preflight)
            return v
        if typ=='docker-image':
            require(IMAGE.fullmatch(target),'Full image digest required')
            image=safe_docker_snapshot(typ,target)
            tags=op.get('expectedTags')
            require(isinstance(tags,list) and tags and all(isinstance(t,str) and re.fullmatch(r'fuseki:[0-9a-f]{40}',t) for t in tags),'Only proven duplicate Fuseki tags allowed')
            require(image==dict(Id=target,RepoTags=sorted(tags)),'Image identity/tags changed')
            require(not any(t in self.keep for t in tags),'Kept image tag')
            image['references']=self.references(op,preflight)
            return image
        require(typ=='docker-history' and op.get('builder')=='desktop-linux' and re.fullmatch(r'[a-z0-9]{6,64}',target),'Invalid history identity/builder')
        self.history_backend()
        h=safe_docker_snapshot(typ,target)
        require(h['Ref']==target and h['Context']==op.get('expectedContext') and h['VCSRepository']==op.get('expectedVcs') and h['VCSRevision']==op.get('expectedRevision') and h['Status']==op.get('expectedStatus'),'Build history identity changed')
        require(h['Status'] in ('completed','failed') and SHA.fullmatch(h['VCSRevision']),'Running or invalid history revision')
        require(re.fullmatch(r'https://github\.com/on-dotnet/ontology-platform(?:\.git)?',h['VCSRepository']),'Other project history refused')
        require(h['Name']=='infra/development/fuseki' and h['Dockerfile'] in ('Dockerfile','infra/development/fuseki/Dockerfile') and Path(h['Context']).is_absolute() and h['Context'].endswith('/ontology-platform/infra/development/fuseki'),'History context outside project')
        require(op.get('fingerprint')==digest(h),'History metadata changed')
        return h

    def write_log(self, phase, op, **fields):
        record=dict(phase=phase,type=op['type'],target=op['target'],expected={k:v for k,v in op.items() if k not in ('ownershipEvidence','target','type')},**fields)
        self.log.write(canonical_json(record)+'\n')
        self.log.flush()
        os.fsync(self.log.fileno())

    def execute(self, log_path):
        path=absolute(log_path)
        require(path.parent.is_dir() and path.parent.resolve() == path.parent,'Log parent must exist without links')
        require(not path.exists() and not path.is_symlink(),'Log already exists')
        require(not any(op['type'] in ('cache','worktree') and under(path,absolute(op['target'])) for op in self.ops),'Log inside deletion target')
        # O_EXCL prevents accidental overwrite. Do not create directories in DryRun.
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as self.log:
            for op in self.ops:
                before, args, command_exit = None, None, None
                try:
                    self.validate_time()
                    require(self.git('rev-parse','HEAD').stdout.strip() == self.root_head,'Current root HEAD changed')
                    if op['type'].startswith('git-') or op['type']=='worktree':
                        self.main_unchanged()
                    before=self.check(op)
                    typ,target=op['type'],op['target']
                    if typ=='git-local-branch': args=['git','--no-optional-locks','-C',str(self.root),'branch','-d','--',target]
                    elif typ=='git-remote-branch':
                        # A deletion-only old-tip lease is CAS; no commit is pushed and no --force update is allowed.
                        args=['git','--no-optional-locks','-C',str(self.root),'push','origin','--delete',target,'--force-with-lease=refs/heads/'+target+':'+op['expectedTip']]
                    elif typ=='worktree': args=['git','--no-optional-locks','-C',str(self.root),'worktree','remove',target]
                    elif typ=='cache': args=['filesystem-unlink-exact-cache',target]
                    elif typ=='docker-history': args=['docker','buildx','history','rm','--builder','desktop-linux',target]
                    else: args=['docker',typ.removeprefix('docker-'),'rm',target]
                    self.write_log('before',op,before=before,command=args)
                    if typ=='cache':
                        entries=metadata_entries(absolute(target))
                        require(digest(entries)==op['fingerprint'],'Cache changed immediately before deletion')
                        remove_exact_cache(absolute(target),entries)
                    else: run(args,cwd=self.root)
                    command_exit=0
                    self.write_log('after',op,command=args,exit=0,after=self.after(op),logicalBytes=before.get('logicalBytes',0))
                    self.done.add((typ,target))
                except (Refused,OSError,ValueError,TypeError,KeyError,AttributeError) as ex:
                    self.write_log('failed',op,before=before,command=getattr(ex,'command',args),exit=getattr(ex,'exit_code',command_exit if command_exit is not None else 1),after={'status':'not_verified'},error=type(ex).__name__)
                    raise

    def after(self, op):
        typ,target=op['type'],op['target']
        if typ=='cache': require(not Path(target).exists() and not Path(target).is_symlink(),'Cache remains')
        elif typ=='worktree': require(target not in self.registered() and not Path(target).exists(),'Worktree remains')
        elif typ=='git-local-branch': require(self.git('show-ref','--verify','--quiet','refs/heads/'+target,acceptable=(0,1)).returncode==1,'Branch remains')
        elif typ=='git-remote-branch': require(not self.git('ls-remote','--heads','origin','refs/heads/'+target).stdout.strip(),'Remote branch remains')
        elif typ=='docker-container': require(target not in self.container_ids(),'Container remains')
        else:
            # Exact inspect must report absence; API failure here also leaves a failed log.
            if typ=='docker-volume': args=['docker','volume','ls','--quiet']
            elif typ=='docker-image': args=['docker','image','ls','--quiet','--no-trunc']
            else: args=['docker','buildx','history','ls','--builder','desktop-linux','--format','json']
            output=run(args).stdout
            if typ=='docker-history':
                refs=[]
                for line in output.splitlines():
                    if not line.strip(): continue
                    value=read_json(line)
                    require(isinstance(value,dict) and isinstance(value.get('ref'),str) and re.fullmatch(r'(?:desktop-linux/desktop-linux/)?[a-z0-9]{6,64}',value['ref']),'Invalid history after schema')
                    refs.append(value['ref'].split('/')[-1])
                require(target not in refs,'Build history remains')
                self.history_backend()
                result=run(['docker','buildx','history','inspect','--builder','desktop-linux','--format',HISTORY_FORMAT,target],acceptable=(0,1))
                require(result.returncode==1 and not result.stdout and result.stderr.strip()=='ERROR: no record found for ref "'+target+'"','Durable history absence not verified; tombstone or unexpected backend response')
                self.history_backend()
            else:
                values=[value for value in output.splitlines() if value]
                pattern=IMAGE if typ=='docker-image' else re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}\Z')
                require(all(pattern.fullmatch(value) for value in values),'Invalid Docker after schema')
                require(target not in values,'Docker resource remains')
        return dict(absent=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--plan',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--log-path')
    args=parser.parse_args(argv)
    try:
        require(not args.apply or args.log_path,'Apply requires --log-path')
        require(args.apply or not args.log_path,'DryRun does not accept a log path')
        with open(args.plan,encoding='utf-8') as stream:
            plan=read_json(stream.read())
        cleaner=Cleaner(args.root,plan)
        cleaner.setup()
        if args.apply:
            cleaner.execute(args.log_path)
        print(canonical_json(dict(mode='Apply' if args.apply else 'DryRun',validated=len(cleaner.ops),completed=len(cleaner.done))))
        return 0
    except (Refused,OSError,ValueError,KeyError,TypeError,AttributeError) as ex:
        # No raw CLI stderr, file contents, environment, or secret-bearing exception text.
        message=str(ex) if isinstance(ex,Refused) else type(ex).__name__
        print('REFUSED: '+message,file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
