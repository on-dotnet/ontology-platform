"""真实临时Git验证只读盘点的保护传播、未知ignored与准确候选分类。"""
from pathlib import Path
import os
import shutil
import json
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'maintenance/inspect-resources.ps1'


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ontology-inspector-')
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'root'
        self.tree = self.base / 'old'
        self.root.mkdir()
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.root / '.gitignore').write_text('bin/\n.env\n')
        (self.root / 'app.txt').write_text('synthetic fixture\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.tip = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.tip)
        self.git('worktree', 'add', '-qb', 'codex/closed', str(self.tree))
        self.git('update-ref', 'refs/remotes/origin/codex/closed', self.tip)
        (self.tree / 'bin').mkdir()
        (self.tree / 'bin/cache.txt').write_text('generated cache\n')
        self.approval = {'schemaVersion': 1, 'project': 'on-dotnet/ontology-platform', 'protectedWorktrees': [], 'keep': [], 'operations': [
            {'type': 'cache', 'target': str(self.tree / 'bin'), 'treeRoot': str(self.tree), 'expectedTip': self.tip},
            {'type': 'worktree', 'target': str(self.tree), 'expectedTip': self.tip, 'expectedBranch': 'codex/closed'},
            {'type': 'git-local-branch', 'target': 'codex/closed', 'expectedTip': self.tip},
            {'type': 'git-remote-branch', 'target': 'codex/closed', 'expectedTip': self.tip}]}

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '--no-optional-locks', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def inspect(self, root=None, env=None):
        approval = self.base / 'approved.json'
        approval.write_text(json.dumps(self.approval))
        indexes = {p: p.read_bytes() for p in [self.root / '.git/index', self.root / '.git/worktrees/old/index']}
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(SCRIPT), '-Root', str(root or self.root), '-ApprovalPath', str(approval)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, before in indexes.items():
            self.assertEqual(path.read_bytes(), before, 'Inspector wrote Git index')
        report = json.loads(result.stdout)
        tree = next(w for w in report['worktrees'] if w['path'] == str(self.tree))
        refs = [r for r in report['refs'] if r['ref'].endswith('/codex/closed')]
        return tree, refs

    def test_approved_closed_clean_tree_and_refs_are_candidates(self):
        tree, refs = self.inspect()
        self.assertEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] == 'SAFE_CANDIDATE' for r in refs))

    def test_protected_ancestor_propagates_to_tree_and_refs(self):
        self.approval['protectedWorktrees'] = [str(self.base)]
        tree, refs = self.inspect()
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))

    def test_locked_tree_protection_propagates_to_refs(self):
        self.git('worktree', 'lock', str(self.tree))
        tree, refs = self.inspect()
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))

    def test_private_ignored_file_blocks_tree_and_refs(self):
        (self.tree / '.env').write_text('synthetic placeholder\n')
        tree, refs = self.inspect()
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))

    def test_current_tree_symlink_alias_is_protected(self):
        alias = self.base / 'current-alias'
        alias.symlink_to(self.tree, target_is_directory=True)
        tree, refs = self.inspect(alias)
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))

    def test_private_cache_segments_block_tree_and_refs(self):
        for segment in ('.runtime', '.ssh', '.aws'):
            with self.subTest(segment=segment):
                directory = self.tree / 'bin' / segment
                directory.mkdir()
                fixture = directory / 'run.json'
                fixture.write_text('synthetic placeholder\n')
                tree, refs = self.inspect()
                self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
                self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))
                fixture.unlink()
                directory.rmdir()

    @unittest.skipIf(os.name == 'nt', 'POSIX fault-injection shim')
    def test_failed_ignored_listing_blocks_tree_and_refs(self):
        shim = self.base / 'shim'
        shim.mkdir()
        executable = shim / 'git'
        executable.write_text('#!/usr/bin/env python3\nimport os,sys\nif "ls-files" in sys.argv: sys.exit(13)\nos.execv('+repr(shutil.which('git'))+', ["git"]+sys.argv[1:])\n')
        executable.chmod(0o755)
        env = dict(os.environ, PATH=str(shim)+os.pathsep+os.environ['PATH'])
        tree, refs = self.inspect(env=env)
        self.assertEqual(tree['ignoredExitCode'], 13)
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))

    def test_public_package_names_do_not_imply_private_data(self):
        (self.tree / 'bin/credential-management.js').write_text('public synthetic feature fixture\n')
        (self.tree / 'bin/index.db').write_text('synthetic regenerable package index\n')
        tree, refs = self.inspect()
        self.assertEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] == 'SAFE_CANDIDATE' for r in refs))

    def test_keep_descendant_blocks_tree_and_refs(self):
        self.approval['keep'] = [str(self.tree / 'app.txt')]
        tree, refs = self.inspect()
        self.assertNotEqual(tree['classification'], 'SAFE_CANDIDATE')
        self.assertTrue(all(r['classification'] != 'SAFE_CANDIDATE' for r in refs))


if __name__ == '__main__':
    unittest.main(verbosity=2)
