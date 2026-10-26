"""公开仓库历史检查的真实隔离 Git 回归；不读取用户凭证。"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'maintenance' / 'audit-public-history.py'


class PublicHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ontology-public-history-')
        self.root = Path(self.temp.name)
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.write('.gitignore', '.tools/\n')
        self.write('README.md', '# 合成测试\n')
        self.write('.env.example', 'CLIENT_SECRET=<set-locally>\n')
        self.commit()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(self.root), *args], check=True, capture_output=True)
        return result.stdout

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8')

    def commit(self):
        self.git('add', '--all')
        self.git('commit', '-qm', 'synthetic fixture')

    def audit(self):
        self.assertTrue(SCRIPT.exists(), 'public history audit implementation missing')
        result = subprocess.run(['python3' if os.name != 'nt' else 'python', str(SCRIPT), '--root', str(self.root)], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        return result, json.loads(result.stdout)

    def test_clean_full_history_and_ignored_credentials_are_not_read(self):
        self.write('.tools/security/private.json', 'gh' + 'p_' + 'X' * 36)
        tree = self.git('rev-parse', 'HEAD^{tree}').decode().strip()
        self.git('update-ref', 'refs/codex/turn-diffs/checkpoints/fixture', tree)
        index = (self.root / '.git/index').read_bytes()
        result, report = self.audit()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['status'], 'PASS_FINITE_SCAN')
        self.assertEqual(report['findings'], [])
        self.assertNotIn('private.json', result.stdout)
        self.assertEqual(index, (self.root / '.git/index').read_bytes())

    def test_deleted_secret_and_task_branch_secret_are_detected_without_values(self):
        first = 'gh' + 'p_' + 'A' * 36
        second = 'sk' + '-' + 'B' * 40
        self.write('deleted.txt', first + '\n')
        self.commit()
        self.git('rm', 'deleted.txt')
        self.commit()
        self.git('switch', '-qc', 'codex/closed-task')
        self.write('branch-only.txt', second + '\n')
        self.commit()
        self.git('switch', '-q', 'main')
        result, report = self.audit()
        self.assertEqual(result.returncode, 2)
        self.assertTrue({'deleted.txt', 'branch-only.txt'} <= {f['path'] for f in report['findings']})
        self.assertNotIn(first, result.stdout + result.stderr)
        self.assertNotIn(second, result.stdout + result.stderr)
        self.assertIn('refs/heads/codex/closed-task', report['refs'])

    def test_annotated_tag_message_is_scanned_without_values(self):
        value = 'gh' + 'p_' + 'D' * 36
        self.git('tag', '-a', 'synthetic-tag', '-m', value)
        result, report = self.audit()
        self.assertTrue(any(f['category'] == 'github-token-like' for f in report['findings']))
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_nested_annotated_tag_message_is_scanned(self):
        value = 'gh' + 'p_' + 'F' * 36
        self.git('tag', '-a', 'inner', '-m', value)
        self.git('tag', '-a', 'outer', 'inner', '-m', 'synthetic outer')
        self.git('tag', '-d', 'inner')
        result, report = self.audit()
        self.assertTrue(any(f['category'] == 'github-token-like' for f in report['findings']))
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_direct_blob_and_tree_refs_are_scanned_with_paths(self):
        value = 'gh' + 'p_' + 'E' * 36
        obj = subprocess.run(['git', '-C', str(self.root), 'hash-object', '-w', '--stdin'], input=value.encode(), capture_output=True, check=True).stdout.decode().strip()
        self.git('tag', 'blob-ref', obj)
        tree = subprocess.run(['git', '-C', str(self.root), 'mktree'], input=('100644 blob ' + obj + '\tbranch.txt\n').encode(), capture_output=True, check=True).stdout.decode().strip()
        self.git('update-ref', 'refs/tags/tree-ref', tree)
        result, report = self.audit()
        self.assertTrue(any(f['path'] == 'branch.txt' for f in report['findings']))
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_auxiliary_snapshot_commit_private_runtime_is_metadata_only(self):
        value = 'gh' + 'p_' + 'G' * 36
        self.git('switch', '--detach', '-q')
        self.write('.tools/security/private.json', value)
        self.git('add', '-f', '.tools/security/private.json')
        self.git('commit', '-qm', 'synthetic local snapshot')
        snapshot = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('update-ref', 'refs/codex/snapshots/synthetic-fixture', snapshot)
        self.git('switch', '-q', 'main')
        result, report = self.audit()
        self.assertFalse(any(f['category'] == 'github-token-like' for f in report['findings']))
        self.assertTrue(any('.tools/security/private.json' in o['paths'] for o in report['unscannedBlobs']))
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_sensitive_path_is_reported_even_with_reused_normal_blob(self):
        self.write('normal.txt', 'synthetic certificate placeholder\n')
        self.commit()
        self.write('private/test.pfx', 'synthetic certificate placeholder\n')
        self.commit()
        _, report = self.audit()
        self.assertIn(('private/test.pfx', 'credential-file-path'), {(f['path'], f['category']) for f in report['findings']})

    def test_utf16_secret_is_detected_without_printing_value(self):
        value = 'gh' + 'p_' + 'C' * 36
        (self.root / 'utf16.txt').write_bytes(value.encode('utf-16'))
        self.commit()
        result, report = self.audit()
        self.assertIn('utf16.txt', {f['path'] for f in report['findings']})
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_private_endpoint_is_review_candidate_not_confirmed_production(self):
        endpoint = 'https://' + '10.27.4.19' + ':9443/model'
        self.write('model.json', json.dumps({'endpoint': endpoint}) + '\n')
        self.commit()
        result, report = self.audit()
        self.assertIn('potential-private-endpoint', {f['category'] for f in report['findings']})
        self.assertNotIn(endpoint, result.stdout)
        self.assertIn('not proof', report['limitations'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
