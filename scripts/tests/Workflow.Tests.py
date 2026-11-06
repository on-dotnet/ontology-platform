#!/usr/bin/env python3
"""工程按影响计划的行为回归；隔离Git夹具不启动产品或下载。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'scripts/maintenance/workflow.py'
        if path.exists():
            spec = importlib.util.spec_from_file_location('workflow', path)
            cls.w = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.w)

    def test_entry_exists(self):
        self.assertTrue((ROOT / 'scripts/maintenance/workflow.py').is_file(), 'missing controlled workflow entry')

    def test_frontend_only_does_not_select_backend(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        plan = self.w.select_gates(['apps/web/src/components/connections/editor.tsx'])
        self.assertIn('web', plan['affected'])
        self.assertIn('interaction', plan['affected'])
        self.assertNotIn('backend', plan['affected'])
        self.assertNotIn('environment', plan['affected'])

    def test_driver_and_package_are_separate(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        browser = self.w.select_gates(['experiments/g4-m1-main-integration/browser.mjs'])
        self.assertIn('interaction', browser['affected'])
        self.assertNotIn('backend', browser['affected'])
        package = self.w.select_gates(['scripts/create-review-package.ps1'])
        self.assertIn('package', package['affected'])
        self.assertNotIn('backend', package['affected'])

    def test_shared_contract_propagates_and_unknown_refuses(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        plan = self.w.select_gates(['backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs'])
        self.assertTrue({'backend', 'web', 'interaction'} <= set(plan['affected']))
        self.assertEqual(self.w.select_gates(['new-unmapped-driver.py'])['status'], 'BLOCKED')
        self.assertEqual(self.w.select_gates(['docs/evidence/NEW/driver.py'])['status'], 'BLOCKED')

    def test_reuse_rejects_failure_skip_and_bad_hash(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'evidence.json'
            p.write_text('{}')
            row = dict(status='PASS', exitCode=0, tests=1, skipped=0, inputKey='key', environmentKey='env', policyKey='policy', evidenceSha256=self.w.digest(p.read_bytes()), sourceRun='T1', sourceCommit='a'*40, command=['python3','test.py'])
            self.assertTrue(self.w.reusable(row, 'key', 'env', 'policy', p))
            for change in ({'status':'FAIL'}, {'tests':0}, {'skipped':1}, {'evidenceSha256':'0'*64}, {'inputKey':'other'}, {'exitCode':1}):
                self.assertFalse(self.w.reusable(dict(row, **change), 'key', 'env', 'policy', p))
            p.unlink()
            self.assertFalse(self.w.reusable(row, 'key', 'env', 'policy', p))

    def test_content_keys_ignore_head_and_bind_transitive_files(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            subprocess.run(['git','init','-q',d],check=True)
            (root/'apps/web').mkdir(parents=True)
            (root/'apps/web/a.ts').write_text('one')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            first=self.w.input_key(root,'web')
            (root/'notes.md').write_text('unrelated')
            self.assertEqual(first,self.w.input_key(root,'web'))
            (root/'apps/web/a.ts').write_text('two')
            self.assertNotEqual(first,self.w.input_key(root,'web'))

    def test_json_evidence_does_not_invalidate_product(self):
        plan=self.w.select_gates(['docs/evidence/G4-ENG-WORKFLOW-001/summary.json'])
        self.assertNotIn('environment',plan['affected'])
        self.assertNotIn('backend',plan['affected'])
        self.assertIn('policy',plan['affected'])
        self.assertIn('environment',self.w.select_gates(['pnpm-lock.yaml'])['affected'])

    def test_zero_and_skipped_tests_refused(self):
        self.assertEqual(self.w.test_counts('Ran 0 tests in 0.000s\\nOK', 'python')[0],0)
        self.assertEqual(self.w.test_counts('Ran 4 tests in 0.001s\\nOK (skipped=1)', 'python'),(4,1))
        self.assertEqual(self.w.test_counts('Ran 7 tests in 0.001s\\nOK', 'python'),(7,0))

    def test_unknown_maintenance_never_claims_workflow_coverage(self):
        self.assertEqual(self.w.select_gates(['scripts/maintenance/new_runner.py'])['status'],'BLOCKED')

    def test_dependency_order(self):
        order=self.w.ordered(['interaction','web','backend','environment','contract'])
        self.assertLess(order.index('environment'),order.index('backend'))
        self.assertLess(order.index('backend'),order.index('interaction'))

    def test_timeout_keeps_actual_exit_and_output(self):
        code,raw=self.w.execute_gate([sys.executable,'-u','-c','import time; print("started"); time.sleep(5)'],ROOT,0.05)
        self.assertEqual(code,124)
        self.assertIn(b'started',raw)

    def test_immutable_reuse_reads_real_git_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            subprocess.run(['git','init','-q',d],check=True)
            folder=root/'docs/evidence/TEST';folder.mkdir(parents=True)
            log=folder/'run.log';log.write_text('Ran 2 tests in 0.01s\nOK\n')
            row=dict(gate='engineering',status='PASS',exitCode=0,tests=2,skipped=0,inputKey='key',environmentKey='env',policyKey='policy',command=self.w.registry()['engineering']['command'],sourceCommit='a'*40,sourceRun='T1',logPath='docs/evidence/TEST/run.log',evidenceSha256=self.w.digest(log.read_bytes()))
            (folder/'receipt.json').write_text(json.dumps(row))
            subprocess.run(['git','add','.'],cwd=root,check=True)
            subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','evidence'],cwd=root,check=True)
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            index={'engineering':{'commit':commit,'path':'docs/evidence/TEST/receipt.json'}}
            with patch.object(self.w,'ROOT',root):
                reused=self.w.load_reuse(index,'engineering','key','env','policy')
                self.assertEqual(reused['executionMode'],'REUSED')
                self.assertNotIn('exitCode',reused)
                with self.assertRaisesRegex(ValueError,'REUSE_INELIGIBLE'):
                    self.w.load_reuse(index,'engineering','changed','env','policy')
                log.write_text('tampered working copy')
                self.assertEqual(self.w.load_reuse(index,'engineering','key','env','policy')['evidenceCommit'],commit)

    def test_doc_executable_fixture_is_not_treated_as_prose(self):
        self.assertEqual(self.w.select_gates(['docs/evidence/OTHER/fixture.json'])['status'],'BLOCKED')
        self.assertEqual(self.w.select_gates(['docs/evidence/OTHER/driver.py'])['status'],'BLOCKED')

    def test_package_estimate_requires_exact_commits(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'FULL_COMMIT_REQUIRED'):
                self.w.package_budget(Path(d),'main','HEAD','TASK-001')


if __name__ == '__main__': unittest.main()
