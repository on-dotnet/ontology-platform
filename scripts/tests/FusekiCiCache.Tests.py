"""Exercise transport boundaries; product cache correctness lives in canonical real tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import re

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
        return re.search(r'  engineering:\n    if: (.+)',self.workflow).group(1)

    def evaluate(self,event,ref,message='',manual=False):
        expression=self.scope_condition()
        values={'github.event_name':event,'github.ref':ref,
                'github.event.head_commit.message':message,'inputs.canonical_only':manual}
        for key,value in sorted(values.items(),key=lambda pair:-len(pair[0])):
            expression=expression.replace(key,repr(value))
        expression=expression.replace('&&',' and ').replace('||',' or ').replace('!contains','not contains')
        expression=re.sub(r'\btrue\b','True',expression)
        return eval(expression,{'__builtins__':{},'contains':lambda source,part:part in source},{})

    def test_diagnostic_marker_only_skips_exact_authorized_push_branch(self):
        marker='fix [canonical-diagnostic]'
        self.assertFalse(self.evaluate('push','refs/heads/codex/g3-m3-master',marker))
        for event,ref in [('push','refs/heads/main'),('push','refs/heads/other'),
                          ('pull_request','refs/pull/1/merge')]:
            self.assertTrue(self.evaluate(event,ref,marker))
        self.assertTrue(self.evaluate('push','refs/heads/codex/g3-m3-master','ordinary fix'))
        self.assertFalse(self.evaluate('workflow_dispatch','refs/heads/codex/g3-m3-master','',True))
        self.assertTrue(self.evaluate('workflow_dispatch','refs/heads/codex/g3-m3-master','',False))

    def test_all_application_steps_use_same_guard_and_cache_is_still_push_only(self):
        guard=self.scope_condition()
        self.assertEqual(self.workflow.count('if: '+guard),5)
        for name in ['Frozen restore and backend build','Real PostgreSQL security integration',
                     'Real G2 semantic publishing query MCP MAF and native SSE integration']:
            self.assertIn('- name: '+name+'\n        if: '+guard,self.workflow)
        for action in re.finditer(r'        uses: actions/cache/save@',self.workflow):
            line=self.workflow[:action.start()].splitlines()[-1]
            self.assertIn("github.event_name == 'push'",line)
        self.assertIn('CANONICAL_DIAGNOSTIC_ONLY; product NOT_RUN; full required CI NOT_VERIFIED',self.workflow)


if __name__=='__main__':unittest.main()
