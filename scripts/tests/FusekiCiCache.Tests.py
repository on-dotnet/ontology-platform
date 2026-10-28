"""Exercise transport boundaries; product cache correctness lives in canonical real tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import re
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ci_cache',ROOT/'scripts/maintenance/fuseki_ci_cache.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CacheTransportTests(unittest.TestCase):
    def identity(self):
        key='ontology-fuseki-image-v2-linux-amd64-'+'a'*64
        return dict(schemaVersion=2,cacheKey=key,failureStateKey=key+'-failure-v1-'+'b'*64,
            envFingerprint='b'*64,inputFingerprint='a'*64,contextSha256='c'*64,
            platform='linux/amd64',image='ontology-platform-fuseki:context-'+'a'*64)

    def test_only_exact_controlled_identity_becomes_action_output(self):
        m.validate_identity(self.identity())
        for key,value in [('cacheKey','prefix'),('failureStateKey','other'),('platform','linux/386'),
                          ('inputFingerprint','a'*64+'\nextra=unsafe'),('schemaVersion',1),('image','other')]:
            with self.assertRaises(ValueError):m.validate_identity({**self.identity(),key:value})

    def test_unknown_usage_and_paid_or_large_storage_are_blocked(self):
        self.assertEqual(m.budget(dict(active_caches_size_in_bytes=0),123)['status'],'PASS')
        for usage,size in [({},0),(dict(active_caches_size_in_bytes=True),0),
                           (dict(active_caches_size_in_bytes=-1),0),
                           (dict(active_caches_size_in_bytes=m.MAX_PROJECT_STORAGE),1),
                           (dict(active_caches_size_in_bytes=0),m.MAX_ARCHIVE+1)]:
            with self.assertRaises(ValueError):m.budget(usage,size)

    def test_directory_cannot_include_links(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'image.tar').write_bytes(b'123')
            self.assertEqual(m.directory_size(path),3)
            (path/'linked').symlink_to(path/'image.tar')
            with self.assertRaises(ValueError):m.directory_size(path)


class WorkflowScopeTests(unittest.TestCase):
    def setUp(self):
        self.workflow=(ROOT/'.github/workflows/ci.yml').read_text()

    def scope_condition(self):
        return re.search(r'  engineering:\n    needs: scope\n    if: (.+)',self.workflow).group(1)

    def evaluate(self,event,ref,message='',manual=False):
        path=ROOT/'scripts/maintenance/ci_scope.py'
        spec=importlib.util.spec_from_file_location('ci_scope',path)
        scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
        payload={'head_commit':{'message':message},'inputs':{'canonical_only':manual}}
        return not scope.canonical_only(event,ref,payload)

    def test_diagnostic_marker_only_skips_exact_authorized_push_branch(self):
        marker='fix [canonical-diagnostic]'
        self.assertFalse(self.evaluate('push','refs/heads/codex/g3-m3-master',marker))
        for event,ref in [('push','refs/heads/main'),('push','refs/heads/other'),('push','refs/heads/CODEX/G3-M3-MASTER'),
                          ('pull_request','refs/pull/1/merge')]:
            self.assertTrue(self.evaluate(event,ref,marker))
        self.assertTrue(self.evaluate('push','refs/heads/codex/g3-m3-master','ordinary fix'))
        self.assertTrue(self.evaluate('push','refs/heads/codex/g3-m3-master','[CANONICAL-DIAGNOSTIC]'))
        self.assertFalse(self.evaluate('workflow_dispatch','refs/heads/codex/g3-m3-master','',True))
        self.assertTrue(self.evaluate('workflow_dispatch','refs/heads/codex/g3-m3-master','',False))

    def test_actual_scope_cli_writes_only_boolean_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);event=root/'event.json';output=root/'output.txt'
            event.write_text(json.dumps({'head_commit':{'message':'[canonical-diagnostic]'}}))
            env={**os.environ,'GITHUB_EVENT_PATH':str(event),'GITHUB_OUTPUT':str(output),
                 'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/codex/g3-m3-master'}
            result=subprocess.run([sys.executable,str(ROOT/'scripts/maintenance/ci_scope.py')],
                                  env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0)
            self.assertEqual(output.read_text(),'canonical_only=true\n')
            self.assertIn('full required CI NOT_VERIFIED',result.stdout)

    def test_invalid_manual_values_are_not_coerced_to_approval(self):
        for value in [0,1,None,[],{},'TRUE','true\nother=unsafe']:
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):
                self.evaluate('workflow_dispatch','refs/heads/main',manual=value)

    def test_workflow_is_manual_by_default_across_host_platforms(self):
        triggers=self.workflow.split('permissions:',1)[0]
        self.assertIn('  workflow_dispatch:',triggers)
        self.assertNotRegex(triggers,r'(?m)^  (push|pull_request|schedule):')

    def test_all_application_steps_use_same_guard_and_cache_saves_only_trusted_manual_main(self):
        guard=self.scope_condition()
        self.assertEqual(guard,"needs.scope.outputs.canonical_only != 'true'")
        self.assertEqual(self.workflow.count('    needs: scope'),2)
        self.assertIn('run: python3 scripts/maintenance/ci_scope.py',self.workflow)
        self.assertEqual(self.workflow.count('if: '+guard),5)
        for name in ['Frozen restore and backend build','Real PostgreSQL security integration',
                     'Real G2 semantic publishing query MCP MAF and native SSE integration']:
            self.assertIn('- name: '+name+'\n        if: '+guard,self.workflow)
        for action in re.finditer(r'        uses: actions/cache/save@',self.workflow):
            line=self.workflow[:action.start()].splitlines()[-1]
            self.assertIn("github.event_name == 'workflow_dispatch'",line)
            self.assertIn("github.ref == 'refs/heads/main'",line)
        self.assertIn('CANONICAL_DIAGNOSTIC_ONLY; product NOT_RUN; full required CI NOT_VERIFIED',self.workflow)


if __name__=='__main__':unittest.main()
