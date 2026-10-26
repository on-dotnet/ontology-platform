"""Real isolated Git fixtures and bounded Docker CLI regression tests."""
import base64
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

ENGINE = Path(__file__).resolve().parents[1] / 'maintenance' / 'cleanup_resources.py'


def command(args, cwd=None, env=None):
    return subprocess.run([str(x) for x in args], cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ontology-cleanup-test-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'repo'
        self.remote = self.base / 'origin.git'
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.real_git=shutil.which('git')
        self.git('init', '--bare', self.remote, cwd=self.base)
        self.git('init', '-b', 'main', self.root, cwd=self.base)
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.git('remote', 'add', 'origin', 'https://github.com/on-dotnet/ontology-platform.git')
        (self.root / '.gitignore').write_text('bin/\n.tools/\nartifacts/\nnode_modules/\n')
        cache_targets=' '.join(str(self.base/'old-tree'/x) for x in ('bin','node_modules','.tools/pythonlibs','linked/bin','artifacts/governance-integration.json'))
        (self.root / 'proof.txt').write_text(cache_targets+' CLOSED synthetic TASK-OLD codex/old codex/bad ' + str(self.base / 'old-tree') + ' ' + str(self.base / 'old-tree' / 'bin') + ' ' + str(self.root / 'bin') + ' ' + str(self.root / 'linked' / 'bin') + ' ' + str(self.root / 'artifacts' / 'governance-integration.json') + ' ' + str(self.root / '.tools' / 'pythonlibs') + ' ' + 'a'*64 + ' test-volume sha256:' + 'b'*64 + ' hist123\n')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        self.main = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('push', '-u', 'origin', 'main')
        self.git('update-ref','refs/remotes/origin/main',self.main)
        self.git('branch', 'codex/old')
        self.git('push', 'origin', 'codex/old')
        self.make_cli('gh', "import json; print('[]')\n")
        self.transport=self.base/'git-fixture-transport'
        self.transport.write_text('#!'+sys.executable+'\nimport subprocess,sys\na=sys.argv[1:]\nif "push" in a or "ls-remote" in a: a=['+repr(str(self.remote))+' if x=="origin" else x for x in a]\nsys.exit(subprocess.run(['+repr(self.real_git)+']+a).returncode)\n')
        self.transport.chmod(0o755)
        self.make_cli('git','import os,sys\nos.execv('+repr(str(self.transport))+',['+repr(str(self.transport))+']+sys.argv[1:])\n')
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        now = dt.datetime.now(dt.timezone.utc)
        self.plan = dict(schemaVersion=1, taskId='PRE-G3-CLEANUP-FIX-002', project='on-dotnet/ontology-platform', repositoryRoot=str(self.root), gitCommonDir=str(self.root / '.git'), originUrl='https://github.com/on-dotnet/ontology-platform.git', expectedMainSha=self.main, createdAt=(now-dt.timedelta(minutes=1)).isoformat(), expiresAt=(now+dt.timedelta(hours=1)).isoformat(), allowedWorktreeRoots=[str(self.base)], protectedWorktrees=[str(self.root)], keep=[], operations=[])

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        transport_args=[str(self.remote) if x=='origin' else x for x in args] if args and args[0] in ('push','ls-remote') else args
        r = command([self.real_git,*transport_args], cwd=cwd or self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def make_cli(self, name, body):
        p = self.bin / name
        p.write_text('#!' + sys.executable + '\n' + body)
        p.chmod(0o755)

    def evidence(self):
        return dict(commit=self.main, path='proof.txt', taskId='TASK-OLD', closed=True, synthetic=True)

    def op(self, kind='git-local-branch', target='codex/old', **fields):
        return dict(type=kind, target=target, ownershipEvidence=self.evidence(), **fields)

    def run_engine(self, apply=False, log=True):
        path = self.base / 'plan.json'
        path.write_text(json.dumps(self.plan))
        args = [sys.executable, ENGINE, '--root', self.root, '--plan', path]
        if apply:
            args += ['--apply']
            if log:
                args += ['--log-path', self.base / 'apply.jsonl']
        return command(args, env=self.env)

    def assert_rejected(self, apply=True):
        r = self.run_engine(apply)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.git('show-ref', '--verify', 'refs/heads/codex/old').stdout)
        return r

    def fingerprint(self, p):
        spec = importlib.util.spec_from_file_location('cleanup', ENGINE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.metadata_fingerprint(Path(p))

    def test_dryrun_has_zero_repository_byte_changes(self):
        self.plan['operations'] = [self.op(expectedTip=self.main)]
        before = self.snapshot()
        r = self.run_engine()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.base / 'apply.jsonl').exists())

    def snapshot(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}

    def test_local_and_remote_ancestor_delete_exactly(self):
        self.plan['operations'] = [self.op('git-remote-branch', expectedTip=self.main), self.op(expectedTip=self.main)]
        r = self.run_engine(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(command(['git', 'show-ref', '--verify', 'refs/heads/codex/old'], self.root).returncode, 0)
        self.assertEqual(self.git('ls-remote', '--heads', 'origin', 'refs/heads/codex/old').stdout, '')
        records = [json.loads(x) for x in (self.base / 'apply.jsonl').read_text().splitlines()]
        self.assertEqual(sum(x.get('phase') == 'after' for x in records), 2)
        self.assertTrue(all('target' in x and 'expected' in x for x in records))

    def test_apply_requires_new_log(self):
        self.plan['operations'] = [self.op(expectedTip=self.main)]
        self.assertNotEqual(self.run_engine(True, False).returncode, 0)
        (self.base / 'apply.jsonl').write_text('sentinel')
        self.assert_rejected()
        self.assertEqual((self.base / 'apply.jsonl').read_text(), 'sentinel')

    def test_nonancestor_fails_before_any_deletion(self):
        self.git('switch', '-c', 'codex/bad')
        (self.root / 'new').write_text('unique')
        self.git('add', 'new')
        self.git('commit', '-m', 'unique')
        bad = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('switch', 'main')
        self.plan['operations'] = [self.op(expectedTip=self.main), self.op(target='codex/bad', expectedTip=bad)]
        self.assert_rejected()

    def test_expired_changed_tip_keep_duplicate_and_active_reject(self):
        for mutation in ('expiry', 'tip', 'keep', 'duplicate', 'active', 'ownership'):
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(self.plan)
                self.plan['operations'] = [self.op(expectedTip=self.main)]
                if mutation == 'expiry': self.plan['expiresAt'] = '2000-01-01T00:00:00+00:00'
                if mutation == 'tip': self.plan['operations'][0]['expectedTip'] = '0'*40
                if mutation == 'keep': self.plan['keep'] = ['codex/old']
                if mutation == 'duplicate': self.plan['operations'] *= 2
                if mutation == 'active': self.plan['operations'][0]['target'] = 'main'
                if mutation == 'ownership': self.plan['operations'][0]['ownershipEvidence']['synthetic'] = False
                self.assert_rejected()
                self.plan = plan
                (self.base / 'apply.jsonl').unlink(missing_ok=True)

    def add_tree(self):
        tree = self.base / 'old-tree'
        self.git('worktree', 'add', tree, 'codex/old')
        return tree

    def cache_tree(self):
        tree=self.base/'old-tree'
        return tree if tree.exists() else self.add_tree()

    def tree_op(self, tree):
        return self.op('worktree', str(tree), expectedTip=self.main, expectedBranch='codex/old')

    def test_registered_clean_worktree_removed_without_force(self):
        tree = self.add_tree()
        self.plan['operations'] = [self.tree_op(tree), self.op(expectedTip=self.main)]
        r = self.run_engine(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(tree.exists())

    def test_dirty_locked_protected_worktrees_reject(self):
        tree = self.add_tree()
        self.plan['operations'] = [self.tree_op(tree)]
        (tree / 'untracked').write_text('sentinel')
        self.assert_rejected()
        (tree / 'untracked').unlink()
        self.git('worktree', 'lock', tree)
        self.assert_rejected()
        self.git('worktree', 'unlock', tree)
        self.plan['protectedWorktrees'].append(str(tree))
        self.assert_rejected()

    def test_private_ignored_data_blocks_worktree(self):
        tree = self.add_tree()
        (tree / '.tools').mkdir()
        (tree / '.tools' / 'secret.pfx').write_text('private sentinel')
        self.plan['operations'] = [self.tree_op(tree)]
        self.assert_rejected()
        self.assertTrue((tree / '.tools' / 'secret.pfx').exists())

    def test_cache_then_worktree_deletes_only_exact_regenerable_cache(self):
        tree = self.add_tree()
        p = tree / 'bin'
        p.mkdir()
        (p / 'fixture.dll').write_bytes(b'fixture')
        cache = self.op('cache', str(p), treeRoot=str(tree), expectedTip=self.main, fingerprint=self.fingerprint(p))
        self.plan['operations'] = [cache, self.tree_op(tree)]
        r = self.run_engine(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(tree.exists())

    def test_cache_symlink_unlinks_never_follows(self):
        external = self.base / 'sentinel'
        external.mkdir()
        (external / 'keep').write_text('external')
        tools = self.cache_tree() / '.tools'
        tools.mkdir()
        p = tools / 'pythonlibs'
        p.symlink_to(external, target_is_directory=True)
        self.plan['operations'] = [self.op('cache', str(p), treeRoot=str(self.cache_tree()), expectedTip=self.main, fingerprint=self.fingerprint(p), linktarget=str(external))]
        r = self.run_engine(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(p.is_symlink())
        self.assertEqual((external / 'keep').read_text(), 'external')

    def test_cache_rejects_private_parent_link_and_outside(self):
        p = self.cache_tree() / 'bin'
        p.mkdir()
        private = p / '.env'
        private.write_text('private')
        self.plan['operations'] = [self.op('cache', str(p), treeRoot=str(self.cache_tree()), expectedTip=self.main, fingerprint=self.fingerprint(p))]
        self.assert_rejected()
        private.unlink()
        self.plan['operations'][0]['fingerprint'] = '0'*64
        self.assert_rejected()
        self.plan['operations'][0]['target'] = str(self.base / 'bin')
        self.assert_rejected()

    def docker_fixture(self):
        self.plan['historyBackend'] = dict(context='desktop-linux', engineId='fixture-engine-id', bridgeId='2'*64, buildxVersion='github.com/docker/buildx v0.38.1 0dbe87f36ed472fe36b6796c3f70b4210a731fc5', buildkitVersion='v0.34.0', driver='docker', nodeName='desktop-linux')
        self.state_path = self.base / 'docker-state.json'
        self.state_path.write_text(json.dumps(dict(containers=[dict(Id='a'*64, Name='/test-container', Image='sha256:'+'b'*64, State='exited', Mounts=[])], volumes=[dict(Name='test-volume', Driver='local', CreatedAt='2026-01-01T00:00:00Z')], images=[dict(Id='sha256:'+'b'*64, RepoTags=['fuseki:'+'c'*40])], history=[dict(Ref='hist123', Name='infra/development/fuseki', Dockerfile='Dockerfile', Context='/repo/ontology-platform/infra/development/fuseki', VCSRepository='https://github.com/on-dotnet/ontology-platform', VCSRevision=self.main, Status='completed')], calls=[])))
        self.make_cli('docker', '''import json,sys
from pathlib import Path
p=Path(''' + repr(str(self.state_path)) + ''')
s=json.loads(p.read_text()); a=sys.argv[1:]; s['calls'].append(a)
def fail(message):
 p.write_text(json.dumps(s)); print(message,file=sys.stderr); sys.exit(1)
try:
 if a==['context','show']: print('desktop-linux')
 elif a[:1]==['info']: print('fixture-engine-id')
 elif a[:2]==['network','inspect']: print(('3' if s.get('backendChanged') else '2')*64)
 elif a==['buildx','version']: print('github.com/docker/buildx v0.38.1 0dbe87f36ed472fe36b6796c3f70b4210a731fc5')
 elif a[:2]==['buildx','inspect']: print('Name: desktop-linux\\nDriver: docker\\nNodes:\\nName: desktop-linux\\nEndpoint: desktop-linux\\nBuildKit version: v0.34.0')
 elif a[:2]==['volume','ls']: print('\\n'.join(x['Name'] for x in s['volumes']))
 elif a[:2]==['image','ls']: print('\\n'.join(x['Id'] for x in s['images']))
 elif a[:3]==['buildx','history','ls']:
  visible=[x for x in s['history'] if x['Ref'] not in s.get('deleted',[])]
  if a[-1]=='json': print('\\n'.join(json.dumps({'ref':x['Ref']}) for x in visible))
  else: print('\\n'.join(x['Ref'] for x in visible))
 elif a[:2]==['container','ls']: print('\\n'.join(x['Id'] for x in s['containers']))
 elif a[:2]==['container','inspect']:
  x=next(x for x in s['containers'] if x['Id']==a[-1]); print(json.dumps({**x,'State':{'Status':x['State']}}))
 elif a[:2]==['volume','inspect']: print(json.dumps(next(x for x in s['volumes'] if x['Name']==a[-1])))
 elif a[:2]==['image','inspect']: print(json.dumps(next(x for x in s['images'] if x['Id']==a[-1])))
 elif a[:3]==['buildx','history','inspect']:
  ref=a[-1]; visible=[x for x in s['history'] if x['Ref'] not in s.get('deleted',[])]
  if ref.startswith('^'):
   index=int(ref[1:])+(1 if s.get('offsetMoved') else 0)
   if s.get('offsetMissing') or index>=len(visible): fail('ERROR: no record found for ref "'+ref+'"')
   print(json.dumps(visible[index]))
  else:
   if ref in s.get('deleted',[]): fail('ERROR: ref '+ref+' is deleted')
   record=next((x for x in s['history'] if x['Ref']==ref),None)
   if record is None: fail(s.get('afterError','ERROR: no record found for ref "'+ref+'"'))
   if s.get('pinBug'): s.setdefault('pinned',[]).append(ref)
   print(json.dumps(record))
 elif a[:2]==['container','rm']: s['containers']=[x for x in s['containers'] if x['Id']!=a[-1]]
 elif a[:2]==['volume','rm']: s['volumes']=[x for x in s['volumes'] if x['Name']!=a[-1]]
 elif a[:2]==['image','rm']: s['images']=[x for x in s['images'] if x['Id']!=a[-1]]
 elif a[:3]==['buildx','history','rm']:
  if s.get('pinBug') and a[-1] in s.get('pinned',[]): s.setdefault('deleted',[]).append(a[-1])
  else: s['history']=[x for x in s['history'] if x['Ref']!=a[-1]]
 else: raise ValueError('unsupported command')
except (StopIteration,ValueError): p.write_text(json.dumps(s)); sys.exit(1)
p.write_text(json.dumps(s))
''')

    def docker_ops(self):
        return [self.op('docker-container', 'a'*64, expectedName='/test-container', expectedImage='sha256:'+'b'*64, expectedState='exited', expectedMounts=[]), self.op('docker-volume', 'test-volume', expectedDriver='local', expectedCreatedAt='2026-01-01T00:00:00Z'), self.op('docker-image', 'sha256:'+'b'*64, expectedTags=['fuseki:'+'c'*40])]

    def test_docker_exact_whitelist_and_dryrun(self):
        self.docker_fixture()
        self.plan['operations'] = self.docker_ops()
        r = self.run_engine()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(self.state_path.read_text())['containers']), 1)
        r = self.run_engine(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(self.state_path.read_text())
        self.assertEqual([len(state[k]) for k in ('containers','volumes','images')], [0,0,0])
        deletions = [x for x in state['calls'] if 'rm' in x]
        self.assertEqual(deletions, [['container','rm','a'*64], ['volume','rm','test-volume'], ['image','rm','sha256:'+'b'*64]])

    def test_docker_keep_replaced_name_and_active_refs_reject(self):
        for mutation in ('keep','replaced','refs','running','foreign'):
            with self.subTest(mutation=mutation):
                self.docker_fixture()
                self.plan['operations'] = self.docker_ops()
                state = json.loads(self.state_path.read_text())
                if mutation == 'keep': self.plan['keep'] = ['sha256:'+'b'*64]
                if mutation == 'replaced': state['containers'][0]['Id']='d'*64
                if mutation == 'running': state['containers'][0]['State']='running'
                if mutation == 'refs':
                    state['containers'].append(dict(Id='d'*64,Name='/other',Image='sha256:'+'b'*64,State='exited',Mounts=[dict(Type='volume',Name='test-volume')]))
                if mutation == 'foreign': self.plan['operations'][0]['ownershipEvidence']['taskId']='OTHER'
                self.state_path.write_text(json.dumps(state))
                self.assert_rejected()
                self.assertFalse(any('rm' in x for x in json.loads(self.state_path.read_text())['calls']))
                self.plan['keep']=[]
                (self.base / 'apply.jsonl').unlink(missing_ok=True)

    def history_plan(self, later_branch=False):
        state=json.loads(self.state_path.read_text());h=state['history'][0]
        op=self.op('docker-history',h['Ref'],builder='desktop-linux',expectedContext=h['Context'],expectedVcs=h['VCSRepository'],expectedRevision=h['VCSRevision'],expectedStatus=h['Status'],fingerprint=hashlib.sha256(json.dumps(h,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.plan['operations']=[op]+([self.op(expectedTip=self.main)] if later_branch else [])

    def test_history_offset_prevents_zero_ref_tombstone_and_database_survives_restart(self):
        self.docker_fixture();state=json.loads(self.state_path.read_text());state['pinBug']=True;self.state_path.write_text(json.dumps(state));self.history_plan()
        result=self.run_engine(True);self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(self.state_path.read_text());self.assertEqual(state['history'],[], 'CLI success/list absence must not hide retained database records')
        rm=next(i for i,c in enumerate(state['calls']) if c[:3]==['buildx','history','rm'])
        self.assertTrue(all(c[-1].startswith('^') for c in state['calls'][:rm] if c[:3]==['buildx','history','inspect']))
        state['deleted']=[];state['pinned']=[]
        self.assertEqual(state['history'],[], 'Engine memory reset must not resurrect deleted database records')

    def test_history_existing_pin_tombstone_fails_and_stops_later_operations(self):
        self.docker_fixture();state=json.loads(self.state_path.read_text());state.update(pinBug=True,pinned=['hist123']);self.state_path.write_text(json.dumps(state));self.history_plan(True)
        result=self.run_engine(True);self.assertNotEqual(result.returncode,0)
        rows=[json.loads(x) for x in (self.base/'apply.jsonl').read_text().splitlines()]
        self.assertEqual(rows[-1]['phase'],'failed');self.assertEqual(rows[-1]['exit'],0)
        self.assertEqual(len(json.loads(self.state_path.read_text())['history']),1)
        self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)

    def test_history_offset_movement_or_range_error_refuses_before_delete(self):
        for flag in ('offsetMoved','offsetMissing'):
            with self.subTest(flag=flag):
                self.docker_fixture();state=json.loads(self.state_path.read_text());second=dict(state['history'][0],Ref='hist456');state['history'].append(second);state[flag]=True;self.state_path.write_text(json.dumps(state));self.history_plan()
                result=self.run_engine(True);self.assertNotEqual(result.returncode,0)
                self.assertFalse(any(c[:3]==['buildx','history','rm'] for c in json.loads(self.state_path.read_text())['calls']))
                self.assertFalse((self.base/'apply.jsonl').exists())

    def test_history_absence_diagnostic_rejects_other_errors_and_wrong_ref(self):
        for error in ('ERROR: transport sentinel-private-value', 'ERROR: permission denied', 'ERROR: no record found for ref "other123"', 'ERROR: no record found for ref "hist123" extra'):
            with self.subTest(error=error):
                self.docker_fixture();state=json.loads(self.state_path.read_text());state['afterError']=error;self.state_path.write_text(json.dumps(state));self.history_plan(True)
                result=self.run_engine(True);self.assertNotEqual(result.returncode,0)
                self.assertNotIn('sentinel-private-value',result.stderr)
                self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)
                (self.base/'apply.jsonl').unlink(missing_ok=True)

    def test_history_backend_generation_mismatch_refuses_before_delete(self):
        self.docker_fixture();state=json.loads(self.state_path.read_text());state['backendChanged']=True;self.state_path.write_text(json.dumps(state));self.history_plan()
        result=self.run_engine(True);self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[:3]==['buildx','history','rm'] for c in json.loads(self.state_path.read_text())['calls']))

    def test_docker_history_project_boundary(self):
        self.docker_fixture()
        h = json.loads(self.state_path.read_text())['history'][0]
        fp = hashlib.sha256(json.dumps(h, sort_keys=True, separators=(',',':')).encode()).hexdigest()
        self.plan['operations'] = [self.op('docker-history','hist123',builder='desktop-linux',expectedContext=h['Context'],expectedVcs=h['VCSRepository'],expectedRevision=h['VCSRevision'],expectedStatus=h['Status'],fingerprint=fp)]
        r=self.run_engine(True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(self.state_path.read_text())['history'],[])

    def test_permission_or_cli_failure_is_closed(self):
        self.make_cli('gh', 'import sys;sys.exit(13)\n')
        self.plan['operations'] = [self.op(expectedTip=self.main)]
        self.assert_rejected()


    def load_engine(self):
        spec = importlib.util.spec_from_file_location('cleanup_test_engine', ENGINE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_log_records_exact_nonzero_command_exit_and_stops(self):
        real_git = str(self.transport)
        self.make_cli('git', 'import subprocess,sys\na=sys.argv[1:]\nif "branch" in a and "-d" in a: sys.exit(13)\nsys.exit(subprocess.run([' + repr(real_git) + ']+a).returncode)\n')
        self.plan['operations'] = [self.op(expectedTip=self.main), self.op('git-remote-branch', expectedTip=self.main)]
        self.assert_rejected()
        records = [json.loads(x) for x in (self.base / 'apply.jsonl').read_text().splitlines()]
        self.assertEqual(records[-1]['phase'], 'failed')
        self.assertEqual(records[-1]['exit'], 13)
        self.assertIn('-d', records[-1]['command'])
        self.assertEqual(self.git('ls-remote','--heads','origin','refs/heads/codex/old').stdout.split()[0], self.main)

    def test_midrun_tip_change_refuses_before_delete(self):
        self.git('switch','-c','codex/bad')
        (self.root/'unique').write_text('new')
        self.git('add','unique')
        self.git('commit','-m','unique')
        tip=self.git('rev-parse','HEAD').stdout.strip()
        self.git('switch','main')
        counter=self.base/'gh-count'
        self.make_cli('gh', 'import subprocess\nfrom pathlib import Path\np=Path(' + repr(str(counter)) + ')\nn=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(n))\nif n==2: subprocess.run(["git","-C",' + repr(str(self.root)) + ',"update-ref","refs/heads/codex/old",' + repr(tip) + '],check=True)\nprint("[]")\n')
        self.plan['operations']=[self.op(expectedTip=self.main)]
        self.assert_rejected()
        self.assertEqual(self.git('rev-parse','codex/old').stdout.strip(),tip)
        self.assertFalse(any(json.loads(x)['phase']=='after' for x in (self.base/'apply.jsonl').read_text().splitlines()))

    def test_cache_nested_symlink_preserves_external_bytes(self):
        p=self.cache_tree()/'bin'
        p.mkdir()
        external=self.base/'external'
        external.mkdir()
        (external/'sentinel').write_bytes(b'never remove')
        (p/'junction').symlink_to(external,target_is_directory=True)
        self.plan['operations']=[self.op('cache',str(p),treeRoot=str(self.cache_tree()),expectedTip=self.main,fingerprint=self.fingerprint(p))]
        r=self.run_engine(True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((external/'sentinel').read_bytes(),b'never remove')
        self.assertFalse(p.exists())

    def test_cache_parent_symlink_refused(self):
        external=self.base/'external'
        external.mkdir()
        p=external/'bin'
        p.mkdir()
        (p/'sentinel').write_text('keep')
        (self.cache_tree()/'linked').symlink_to(external,target_is_directory=True)
        target=self.cache_tree()/'linked'/'bin'
        self.plan['operations']=[self.op('cache',str(target),treeRoot=str(self.cache_tree()),expectedTip=self.main,fingerprint=self.fingerprint(p))]
        self.assert_rejected()
        self.assertTrue((p/'sentinel').exists())

    def test_invalid_schema_repository_main_and_ttl_are_refused(self):
        mutations=[dict(project='other/project'),dict(expectedMainSha='f'*40),dict(gitCommonDir=str(self.remote)),dict(repositoryRoot=str(self.base)),dict(originUrl='https://example.invalid/other.git'),dict(expiresAt=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=3)).isoformat())]
        for mutation in mutations:
            with self.subTest(mutation=list(mutation)):
                saved=copy.deepcopy(self.plan)
                self.plan.update(mutation)
                self.plan['operations']=[self.op(expectedTip=self.main)]
                self.assert_rejected()
                self.plan=saved

    def test_open_prs_prevent_all_mutations(self):
        self.make_cli('gh','print(\'[{{"number":1,"headRefName":"codex/old"}}]\'.replace("{{","{").replace("}}","}"))\n')
        self.plan['operations']=[self.op(expectedTip=self.main)]
        self.assert_rejected()
        self.assertFalse((self.base/'apply.jsonl').exists())

    def test_history_rejects_foreign_running_changed_fingerprint(self):
        for key,value in [('VCSRepository','https://github.com/other/project'),('Status','running'),('Context','/other/infra/development/fuseki'),('Ref','other12')]:
            with self.subTest(key=key):
                self.docker_fixture()
                state=json.loads(self.state_path.read_text())
                h=state['history'][0]
                h[key]=value
                self.state_path.write_text(json.dumps(state))
                self.plan['operations']=[self.op('docker-history','hist123',builder='desktop-linux',expectedContext=h['Context'],expectedVcs=h['VCSRepository'],expectedRevision=h['VCSRevision'],expectedStatus=h['Status'],fingerprint=hashlib.sha256(json.dumps(h,sort_keys=True,separators=(',',':')).encode()).hexdigest())]
                self.assert_rejected()
                self.assertFalse(any('rm' in x for x in json.loads(self.state_path.read_text())['calls']))

    def test_expired_plan_is_rechecked_after_preflight(self):
        module=self.load_engine()
        self.plan['operations']=[self.op(expectedTip=self.main)]
        saved_path=os.environ['PATH']
        try:
            os.environ['PATH']=self.env['PATH']
            cleaner=module.Cleaner(str(self.root),self.plan)
            cleaner.setup()
            self.plan['expiresAt']='2000-01-01T00:00:00+00:00'
            with self.assertRaises(module.Refused):
                cleaner.execute(str(self.base/'apply.jsonl'))
        finally:
            os.environ['PATH']=saved_path
        self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)

    def test_cache_fingerprint_change_after_preflight_stops(self):
        module=self.load_engine()
        p=self.cache_tree()/'bin'
        p.mkdir()
        (p/'fixture').write_text('one')
        self.plan['operations']=[self.op('cache',str(p),treeRoot=str(self.cache_tree()),expectedTip=self.main,fingerprint=self.fingerprint(p))]
        saved_path=os.environ['PATH']
        try:
            os.environ['PATH']=self.env['PATH']
            cleaner=module.Cleaner(str(self.root),self.plan)
            cleaner.setup()
            (p/'fixture').write_text('changed')
            with self.assertRaises(module.Refused):
                cleaner.execute(str(self.base/'apply.jsonl'))
        finally:
            os.environ['PATH']=saved_path
        self.assertEqual((p/'fixture').read_text(),'changed')

    def test_docker_after_reports_remaining_resource(self):
        self.docker_fixture()
        self.plan['operations']=[self.docker_ops()[0]]
        script=(self.bin/'docker').read_text().replace("s['containers']=[x for x in s['containers'] if x['Id']!=a[-1]]", 'pass')
        (self.bin/'docker').write_text(script)
        self.assert_rejected()
        records=[json.loads(x) for x in (self.base/'apply.jsonl').read_text().splitlines()]
        self.assertEqual(records[-1]['phase'],'failed')
        self.assertEqual(len(json.loads(self.state_path.read_text())['containers']),1)


    def test_archived_small_file_requires_exact_committed_bytes(self):
        p=self.cache_tree()/'artifacts'/'governance-integration.json'
        p.parent.mkdir()
        raw=b'{"result":"passed"}\n'
        p.write_bytes(raw)
        archive=self.root/'archive.json'
        archive.write_bytes(raw)
        self.git('add','archive.json')
        self.git('commit','-m','archive fixture')
        tip=self.git('rev-parse','HEAD').stdout.strip()
        self.plan['operations']=[self.op('cache',str(p),treeRoot=str(self.cache_tree()),expectedTip=self.main,fingerprint=self.fingerprint(p),expectedFileSha256=hashlib.sha256(raw).hexdigest(),archiveCommittedPath='archive.json')]
        r=self.run_engine(True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse(p.exists())
        self.assertEqual(archive.read_bytes(),raw)
        (self.base/'apply.jsonl').unlink()
        p.write_bytes(b'{"changed":true}')
        self.plan['operations'][0].update(fingerprint=self.fingerprint(p),expectedFileSha256=hashlib.sha256(p.read_bytes()).hexdigest())
        self.assert_rejected()
        self.assertTrue(p.exists())

    def test_origin_change_after_preflight_rejects_mutation(self):
        module=self.load_engine()
        self.plan['operations']=[self.op(expectedTip=self.main)]
        saved_path=os.environ['PATH']
        try:
            os.environ['PATH']=self.env['PATH']
            cleaner=module.Cleaner(str(self.root),self.plan)
            cleaner.setup()
            self.git('remote','set-url','origin',str(self.remote))
            with self.assertRaises(module.Refused):
                cleaner.execute(str(self.base/'apply.jsonl'))
        finally:
            os.environ['PATH']=saved_path
        self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)


    def test_worktree_keep_descendant_or_ancestor_refuses_removal(self):
        tree=self.add_tree()
        self.plan['operations']=[self.tree_op(tree)]
        for kept in (tree/'proof.txt', self.base):
            with self.subTest(kept=str(kept)):
                self.plan['keep']=[str(kept)]
                result=self.run_engine(True)
                self.assertNotEqual(result.returncode,0,result.stdout)
                self.assertTrue((tree/'proof.txt').exists())
                (self.base/'apply.jsonl').unlink(missing_ok=True)

    def test_cache_current_protected_or_locked_tree_refuses_deletion(self):
        tree=self.add_tree()
        for state,root in (('current',self.root),('protected',tree),('locked',tree)):
            with self.subTest(state=state):
                p=root/'bin'
                p.mkdir(exist_ok=True)
                (p/'sentinel').write_text('retain')
                self.plan['operations']=[self.op('cache',str(p),treeRoot=str(root),expectedTip=self.main,fingerprint=self.fingerprint(p))]
                self.plan['protectedWorktrees']=[str(self.root)]+([str(tree)] if state=='protected' else [])
                if state=='locked': self.git('worktree','lock',tree)
                try:
                    result=self.run_engine(True)
                    self.assertNotEqual(result.returncode,0,result.stdout)
                    self.assertTrue((p/'sentinel').exists())
                finally:
                    if state=='locked': self.git('worktree','unlock',tree)
                    (self.base/'apply.jsonl').unlink(missing_ok=True)

    def test_remote_delete_compare_and_delete_preserves_concurrent_tip(self):
        self.git('switch','-c','codex/bad')
        (self.root/'unique').write_text('unique concurrent work')
        self.git('add','unique')
        self.git('commit','-m','unique concurrent work')
        newtip=self.git('rev-parse','HEAD').stdout.strip()
        self.git('push','origin','codex/bad')
        self.git('switch','main')
        real_git=str(self.transport)
        self.make_cli('git','import subprocess,sys\na=sys.argv[1:]\nif "push" in a and "--delete" in a: subprocess.run(['+repr(real_git)+',"--git-dir",'+repr(str(self.remote))+',"update-ref","refs/heads/codex/old",'+repr(newtip)+'],check=True)\nsys.exit(subprocess.run(['+repr(real_git)+']+a).returncode)\n')
        self.plan['operations']=[self.op('git-remote-branch',expectedTip=self.main),self.op(expectedTip=self.main)]
        result=self.run_engine(True)
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertEqual(self.git('ls-remote','--heads','origin','refs/heads/codex/old').stdout.split()[0],newtip)
        self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)
        records=[json.loads(x) for x in (self.base/'apply.jsonl').read_text().splitlines()]
        self.assertEqual(records[-1]['phase'],'failed')
        self.assertFalse(any(r['phase']=='after' for r in records))

    def test_history_dockerfile_accepts_only_two_exact_project_forms(self):
        for dockerfile,allowed in [('Dockerfile',True),('infra/development/fuseki/Dockerfile',True),('../Dockerfile',False),('other/Dockerfile',False)]:
            with self.subTest(dockerfile=dockerfile):
                self.docker_fixture()
                state=json.loads(self.state_path.read_text())
                h=state['history'][0]
                h['Dockerfile']=dockerfile
                self.state_path.write_text(json.dumps(state))
                self.plan['operations']=[self.op('docker-history','hist123',builder='desktop-linux',expectedContext=h['Context'],expectedVcs=h['VCSRepository'],expectedRevision=h['VCSRevision'],expectedStatus=h['Status'],fingerprint=hashlib.sha256(json.dumps(h,sort_keys=True,separators=(',',':')).encode()).hexdigest())]
                result=self.run_engine(True)
                self.assertEqual(result.returncode==0,allowed,result.stderr)
                if allowed: self.assertEqual(json.loads(self.state_path.read_text())['history'],[])
                else: self.assertEqual(len(json.loads(self.state_path.read_text())['history']),1)
                (self.base/'apply.jsonl').unlink(missing_ok=True)


    def test_effective_origin_rewrite_is_refused(self):
        self.git('config',f'url.{self.remote}.insteadOf',self.plan['originUrl'])
        self.plan['operations']=[self.op('git-remote-branch',expectedTip=self.main)]
        result=self.run_engine(True)
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertEqual(self.git('ls-remote','--heads','origin','refs/heads/codex/old').stdout.split()[0],self.main)
        self.assertFalse((self.base/'apply.jsonl').exists())

    def test_malformed_history_after_is_logged_and_later_branch_kept(self):
        for bad in ('null','not-json', '{"ref":null}'):
            with self.subTest(bad=bad):
                self.docker_fixture()
                h=json.loads(self.state_path.read_text())['history'][0]
                script=(self.bin/'docker').read_text()
                script=script.replace("print('\\n'.join(json.dumps({'ref':x['Ref']}) for x in visible))", 'print('+repr(bad)+')')
                # The replacement operates on the actual generated CLI script, not engine code.
                self.assertIn('print('+repr(bad)+')',script)
                (self.bin/'docker').write_text(script)
                self.plan['operations']=[self.op('docker-history','hist123',builder='desktop-linux',expectedContext=h['Context'],expectedVcs=h['VCSRepository'],expectedRevision=h['VCSRevision'],expectedStatus=h['Status'],fingerprint=hashlib.sha256(json.dumps(h,sort_keys=True,separators=(',',':')).encode()).hexdigest()),self.op(expectedTip=self.main)]
                result=self.run_engine(True)
                self.assertNotEqual(result.returncode,0,result.stdout)
                records=[json.loads(x) for x in (self.base/'apply.jsonl').read_text().splitlines()]
                self.assertEqual(records[-1]['phase'],'failed')
                self.assertNotIn('Traceback',result.stderr)
                self.assertEqual(json.loads(self.state_path.read_text())['history'],[])
                self.assertTrue(self.git('show-ref','--verify','refs/heads/codex/old').stdout)
                (self.base/'apply.jsonl').unlink(missing_ok=True)


    def test_exact_public_pnpm_asset_allows_closed_cache_cleanup(self):
        tree=self.cache_tree()
        cache=tree/'node_modules'
        asset=cache/'.pnpm/language-subtag-registry@0.3.23/node_modules/language-subtag-registry/data/json/private-use.json'
        asset.parent.mkdir(parents=True)
        asset.write_bytes(base64.b64decode('ewoJInFhYS4ucXR6IjogNTc2Ngp9Cg=='))
        self.plan['operations']=[self.op('cache',str(cache),treeRoot=str(tree),expectedTip=self.main,fingerprint=self.fingerprint(cache))]
        result=self.run_engine(True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(cache.exists())

    def test_public_asset_exception_rejects_wrong_path_bytes_size_link_and_stale_fingerprint(self):
        tree=self.cache_tree()
        cache=tree/'node_modules'
        expected=cache/'.pnpm/language-subtag-registry@0.3.23/node_modules/language-subtag-registry/data/json/private-use.json'
        raw=base64.b64decode('ewoJInFhYS4ucXR6IjogNTc2Ngp9Cg==')
        for mutation in ('location','content','size','symlink','stale'):
            with self.subTest(mutation=mutation):
                asset=cache/'other/private-use.json' if mutation=='location' else expected
                asset.parent.mkdir(parents=True,exist_ok=True)
                if mutation=='symlink':
                    external=self.base/'public-sentinel.json'
                    external.write_bytes(raw)
                    asset.symlink_to(external)
                else: asset.write_bytes((b'x'+raw[1:]) if mutation=='content' else (raw+b'x') if mutation=='size' else raw)
                self.plan['operations']=[self.op('cache',str(cache),treeRoot=str(tree),expectedTip=self.main,fingerprint='0'*64 if mutation=='stale' else self.fingerprint(cache))]
                result=self.assert_rejected()
                if mutation=='stale': self.assertIn('Cache metadata changed',result.stderr)
                self.assertTrue(asset.exists())
                if mutation=='symlink': self.assertEqual(external.read_bytes(),raw)
                shutil.rmtree(cache)
                (self.base/'apply.jsonl').unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
