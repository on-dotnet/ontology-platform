#!/usr/bin/env python3
"""上下文选择及机器差异范围回归；临时Git夹具不启动产品。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
import workflow

class ContextTests(unittest.TestCase):
    def test_default_omits_logs_but_includes_registered_executable(self):
        import workflow_context as c
        result=c.context(ROOT,task='G4-M5-INTEGRATION-001')
        paths={r['path'] for r in result['files']}
        self.assertIn('scripts/maintenance/workflow.py',paths)
        self.assertIn('docs/evidence/G1-ENG-001/verify.tests.ps1',paths)
        self.assertFalse(any(p.endswith('.log') for p in paths))
        self.assertTrue(result['omissions'])
        self.assertTrue(all('source' in r for r in result['files']))

    def test_evidence_requires_exact_task_and_preserves_blob(self):
        import workflow_context as c
        with self.assertRaises(ValueError):c.context(ROOT,mode='evidence')
        result=c.context(ROOT,mode='evidence',task='G4-M4-QUERY-001')
        row=next(r for r in result['files'] if r['path'].endswith('/restart-recovery-witness.json'))
        self.assertEqual(row['blob'],subprocess.check_output(['git','rev-parse','HEAD:'+row['path']],cwd=ROOT,text=True).strip())
        self.assertTrue(all(r['path'].startswith('docs/evidence/G4-M4-QUERY-001/') for r in result['files']))

    def test_docs_do_not_schedule_product_unknown_fixture_blocks(self):
        for path in ['apps/web/AGENTS.md','docs/planning/g4-implementation-plan.md','docs/evidence/G4-M5-INTEGRATION-001/new-summary.json']:
            result=workflow.select_gates([path])
            self.assertEqual(result['status'],'PLANNED')
            self.assertFalse(set(result['affected'])&{'backend','web','interaction','environment','contract'})
        self.assertEqual(workflow.select_gates(['docs/evidence/UNKNOWN/fixture.sql'])['status'],'BLOCKED')
        self.assertIn('engineering-full',workflow.select_gates(['docs/evidence/G1-ENG-001/verify.tests.ps1'])['affected'])
        self.assertIn('backend',workflow.select_gates(['backend/src/Contracts/Example.cs'])['affected'])

    def test_rule_changes_schedule_policy(self):
        for path in ['scripts/verify.ps1','scripts/validate-structured-files.py','scripts/maintenance/workflow_context.py','scripts/maintenance/workflow.py','docs/development/verification-gates.json']:
            self.assertIn('policy',workflow.select_gates([path])['affected'])

    def test_unqualified_failed_tampered_or_changed_policy_base_refuses_reuse(self):
        import workflow_context as c
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base='a'*40;path=c.qualification_path(root,base)
            paths={'one.txt':{'mode':'100644','kind':'blob','blob':'b'*40}}
            with patch.object(c,'policy_identity',return_value={'validator':'one'}),patch.object(c,'tree',return_value=paths):
                self.assertIsNone(c.verified_base(root,base))
                path.parent.mkdir(parents=True)
                def put(checks,policy=None):
                    import hashlib
                    proof=json.dumps(checks).encode();path.with_suffix('.checks.json').write_bytes(proof)
                    path.write_text(json.dumps(dict(commit=base,policy=policy or {'validator':'one'},blobs=paths,scope='ALL_TRACKED',checksSha256=hashlib.sha256(proof).hexdigest())))
                put([{'Check':'repository-static','Status':'FAIL'}]);self.assertIsNone(c.verified_base(root,base))
                put([{'Check':'repository-static','Status':'PASS'}],{'validator':'old'});self.assertIsNone(c.verified_base(root,base))
                put([{'Check':'repository-static','Status':'PASS'}]);self.assertIsNone(c.verified_base(root,base))
                path.with_suffix('.checks.json').write_text('[]');self.assertIsNone(c.verified_base(root,base))

    def test_markdown_deletion_includes_unchanged_referrers(self):
        import workflow_context as c
        base='a'*40;head='b'*40
        rows={'docs/planning/referrer.md':dict(mode='100644',kind='blob',blob='c'*40)}
        with patch.object(c,'changed',return_value=['docs/planning/deleted.md']),patch.object(c,'tree',return_value=rows),patch.object(c,'verified_base',return_value={'commit':base}):
            result=c.scope(ROOT,base,head)
            self.assertIn('docs/planning/referrer.md',result['paths'])
            self.assertEqual(result['scope'],'ALL_TRACKED')

    def test_diff_recomputes_rename_delete_and_refuses_dirty(self):
        import workflow_context as c
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
            git('init','-q');git('config','user.email','test@example.invalid');git('config','user.name','fixture')
            (root/'old.md').write_text('old\n');(root/'remove.md').write_text('remove\n');git('add','.');git('commit','-qm','base');base=git('rev-parse','HEAD')
            (root/'old.md').rename(root/'new.md');(root/'remove.md').unlink();git('add','-A');git('commit','-qm','head');head=git('rev-parse','HEAD')
            result=c.changed(root,base,head)
            self.assertEqual(set(result),{'old.md','new.md','remove.md'})
            (root/'new.md').write_text('dirty\n')
            with self.assertRaises(ValueError):c.changed(root,base,head)

if __name__=='__main__':unittest.main()
