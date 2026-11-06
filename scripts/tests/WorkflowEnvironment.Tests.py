#!/usr/bin/env python3
"""离线环境缓存的幂等、安全边界及路径分离回归。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class EnvironmentTests(unittest.TestCase):
    def test_environment_module_exists(self):
        self.assertTrue((ROOT/'scripts/maintenance/workflow_environment.py').is_file())

    def load(self):
        spec=importlib.util.spec_from_file_location('env',ROOT/'scripts/maintenance/workflow_environment.py')
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

    def test_content_cache_reuses_and_repairs_exact_owned_file(self):
        if not (ROOT/'scripts/maintenance/workflow_environment.py').exists(): self.skipTest('implementation absent')
        m=self.load()
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory).resolve()/'owned'/'file'
            self.assertTrue(m.materialize(p,b'approved'))
            self.assertFalse(m.materialize(p,b'approved'))
            p.write_bytes(b'broken')
            self.assertTrue(m.materialize(p,b'approved'))
            self.assertEqual(p.read_bytes(),b'approved')

    def test_symlink_is_rejected_not_repaired(self):
        if not (ROOT/'scripts/maintenance/workflow_environment.py').exists(): self.skipTest('implementation absent')
        m=self.load()
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory).resolve()/'link';p.symlink_to('/does-not-exist')
            with self.assertRaisesRegex(ValueError,'LINK'): m.materialize(p,b'value')

    def test_archive_paths_and_duplicates_are_rejected(self):
        if not (ROOT/'scripts/maintenance/workflow_environment.py').exists(): self.skipTest('implementation absent')
        m=self.load()
        import io,zipfile
        for names in (['../outside'],['A','a'],['/absolute']):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as z:
                for name in names:z.writestr(name,b'x')
            with self.assertRaises(ValueError):m.archive_payload(output.getvalue())

    def test_content_identity_excludes_worktree_but_runtime_includes_it(self):
        if not (ROOT/'scripts/maintenance/workflow_environment.py').exists(): self.skipTest('implementation absent')
        m=self.load()
        a=m.identities({'lock':'abc'},Path('/first'))
        b=m.identities({'lock':'abc'},Path('/second'))
        self.assertEqual(a['contentKey'],b['contentKey'])
        self.assertNotEqual(a['workspaceKey'],b['workspaceKey'])

    def test_web_marker_ignores_backend_key_and_binds_web_locks(self):
        m=self.load()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'apps/web').mkdir(parents=True)
            for name in ('package.json','apps/web/package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version'):
                (root/name).write_text('same')
            admission={'pnpm':{'integrity':'approved'},'files':[{'path':'node','sha256':'abc'}]}
            old=root/'artifacts/workflow/TASK/environment/old-backend-key'
            new=old.with_name('new-backend-key')
            first=m.web_marker(root,old,admission)
            self.assertEqual(first,m.web_marker(root,new,admission))
            (root/'pnpm-lock.yaml').write_text('changed')
            self.assertNotEqual(first,m.web_marker(root,new,admission))

if __name__=='__main__': unittest.main()
