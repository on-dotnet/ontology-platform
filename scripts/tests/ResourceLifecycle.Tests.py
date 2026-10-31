"""Real temporary runtime persistence and narrow Docker metadata regressions."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
SOURCE=Path(__file__).resolve().parents[1]/'acceptance/wave2-runtime.py'
spec=importlib.util.spec_from_file_location('lifecycle_runtime',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ontology-lifecycle-')
        self.root=Path(self.tmp.name)
        self.old_root=m.ROOT;m.ROOT=self.root
        self.old_evidence=m.EVIDENCE;m.EVIDENCE=self.root/'docs/evidence/fixture'
    def tearDown(self):
        m.ROOT=self.old_root;m.EVIDENCE=self.old_evidence;self.tmp.cleanup()
    def prepare(self):
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0)),contextlib.redirect_stdout(io.StringIO()):
            m.prepare('g2',task_id='TASK-123',run_id='run-123')
        path=next((self.root/'.tools/security').glob('*/runtime.json'))
        return path,json.loads(path.read_text())
    def test_real_prepare_persists_nonsecret_prepared_manifest(self):
        path,value=self.prepare()
        manifest=json.loads((self.root/'artifacts/resource-lifecycle/run-123.json').read_text())
        self.assertEqual(manifest['taskId'],'TASK-123')
        self.assertEqual(manifest['state'],'PREPARED')
        self.assertEqual(len(manifest['expectedVolumes']),8)
        raw=json.dumps(manifest)
        for secret in m.secret_values(value): self.assertNotIn(secret,raw)
        self.assertNotIn('certificatePath',raw)
        self.assertEqual(value['resourceLifecycle']['runId'],'run-123')
    def test_m2_ownership_is_supported_but_future_milestones_refuse(self):
        value={'volumePrefix':'g3-m2-control','resourceLifecycle':{'taskId':'G3-M2-001','runId':'m2-control'}}
        meta=m.lifecycle_identity(value,'g2')
        self.assertEqual(meta['taskId'],'G3-M2-001')
        self.assertTrue(all(name.startswith('g3-m2-control-') for name in meta['expectedVolumes']))
        for prefix in ('g3-m5-control','../g3-m2-control'):
            with self.assertRaises(ValueError):m.lifecycle_identity(dict(value,volumePrefix=prefix),'g2')

    def test_m3_ownership_persists_exact_authorized_prefix(self):
        value={'volumePrefix':'g3-m3-control','resourceLifecycle':{'taskId':'G3-M3-001','runId':'m3-control'}}
        meta=m.lifecycle_identity(value,'g2')
        self.assertEqual(meta['taskId'],'G3-M3-001')
        self.assertTrue(all(name.startswith('g3-m3-control-') for name in meta['expectedVolumes']))

    def test_m4_ownership_persists_only_the_authorized_phase(self):
        value={'volumePrefix':'g3-m4-control','resourceLifecycle':{'taskId':'G3-M4-001','runId':'m4-control'}}
        meta=m.lifecycle_identity(value,'g2')
        self.assertEqual(meta['taskId'],'G3-M4-001')
        self.assertEqual(len(meta['expectedVolumes']),8)
        self.assertTrue(all(name.startswith('g3-m4-control-') for name in meta['expectedVolumes']))
        with self.assertRaises(ValueError):
            m.lifecycle_identity(dict(value,volumePrefix='g3-m5-control'),'g2')

    def test_m5_exact_stage_identity_is_supported_and_m6_refuses(self):
        value={'volumePrefix':'g3-m5-control','resourceLifecycle':{'taskId':'G3-M5-001','runId':'m5-control'}}
        meta=m.lifecycle_identity(value,'g2')
        self.assertEqual(meta['taskId'],'G3-M5-001')
        self.assertEqual(len(meta['expectedVolumes']),8)
        with self.assertRaises(ValueError):m.lifecycle_identity(dict(value,volumePrefix='g3-m6-control'),'g2')

    def test_existing_private_runtime_is_not_rewritten(self):
        path,value=self.prepare();value.pop('resourceLifecycle');path.write_text(json.dumps(value))
        original=path.read_bytes()
        with patch.dict(os.environ,{'PLATFORM_TASK_ID':'NEW-TASK'}): meta=m.lifecycle_identity(value,'g2')
        self.assertEqual(meta['taskId'],'NEW-TASK')
        self.assertEqual(path.read_bytes(),original)
    def test_unsafe_identity_refuses_before_persistence(self):
        for task in ('../bad','bad\nline',''):
            with self.assertRaises(ValueError):m.lifecycle_identity({'volumePrefix':'g2-test','resourceLifecycle':{'taskId':task,'runId':'run-123'}},'g2')
        self.assertFalse((self.root/'artifacts').exists())
    def test_snapshot_reads_only_double_label_containers_and_exact_volumes(self):
        meta=m.lifecycle_identity({'volumePrefix':'g2-test','resourceLifecycle':{'taskId':'TASK-123','runId':'run-123'}},'g2')
        calls=[]
        def cli(args,**kwargs):
            calls.append(args)
            if args[1:3]==['container','ls']:return subprocess.CompletedProcess(args,0,'a'*64+'\n','')
            if args[1:3]==['container','inspect']:return subprocess.CompletedProcess(args,0,json.dumps({'Id':'a'*64,'Name':'/postgres-test','Image':'sha256:'+'b'*64,'State':'running','TaskId':'TASK-123','RunId':'run-123','Service':'postgres','Mounts':[{'Type':'volume','Name':'g2-test-postgres-data','Destination':'/data','Source':'MUST_NOT_PERSIST','RW':True}]}),'')
            return subprocess.CompletedProcess(args,0,json.dumps({'Name':args[-1],'Driver':'local','CreatedAt':'2026-10-27T00:00:00Z','Labels':None}),'')
        with patch.object(m.subprocess,'run',side_effect=cli):value=m.lifecycle_snapshot(meta)
        self.assertEqual(value['status'],'OBSERVED')
        self.assertEqual(len(value['containers']),1)
        self.assertTrue(all('--format' in call or call[1:3]==['container','ls'] for call in calls))
        self.assertIn('label=io.ontology-platform.task-id=TASK-123',calls[0])
        self.assertIn('label=io.ontology-platform.run-id=run-123',calls[0])
        self.assertNotIn('MUST_NOT_PERSIST',json.dumps(value))
    def test_mismatched_label_or_socket_never_claims_observed(self):
        meta=m.lifecycle_identity({'volumePrefix':'g2-test'},'g2')
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','permission denied sentinel')):
            value=m.lifecycle_snapshot(meta)
        self.assertEqual(value['status'],'BLOCKED')
        self.assertNotIn('sentinel',json.dumps(value))
    def test_foreign_double_label_response_is_rejected(self):
        meta=m.lifecycle_identity({'volumePrefix':'g2-test'},'g2')
        result=[subprocess.CompletedProcess([],0,'a'*64+'\n',''),subprocess.CompletedProcess([],0,json.dumps({'Id':'a'*64,'TaskId':'OTHER','RunId':meta['runId'],'Service':'postgres'}),'')]
        with patch.object(m.subprocess,'run',side_effect=result):value=m.lifecycle_snapshot(meta)
        self.assertEqual(value['status'],'BLOCKED')
    def test_linked_artifact_directory_refused(self):
        meta=m.lifecycle_identity({'volumePrefix':'g2-test'},'g2')
        target=self.root/'outside';target.mkdir()
        (self.root/'artifacts').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):m.lifecycle_write(meta,'PREPARED',[])
        self.assertFalse(list(target.iterdir()))
    def test_run_passes_identity_and_records_exit_without_secrets(self):
        path,value=self.prepare()
        class Process:
            stdout=['ready\n']
            def wait(self,timeout=None):return 0
        with patch.object(m.subprocess,'Popen',return_value=Process()) as process,patch.object(m,'lifecycle_snapshot',return_value={'status':'OBSERVED','containers':[],'volumes':[]}),contextlib.redirect_stdout(io.StringIO()):
            result=m.run(path,'core','g2','Release')
        self.assertEqual(result,0)
        env=process.call_args.kwargs['env']
        self.assertEqual(env['ResourceLifecycle__TaskId'],'TASK-123')
        self.assertEqual(env['ResourceLifecycle__RunId'],'run-123')
        manifest=json.loads((self.root/'artifacts/resource-lifecycle/run-123.json').read_text())
        self.assertEqual(manifest['state'],'EXITED')
        self.assertEqual(manifest['exitCode'],0)
        for secret in m.secret_values(value):self.assertNotIn(secret,json.dumps(manifest))

if __name__=='__main__':unittest.main(verbosity=2)
