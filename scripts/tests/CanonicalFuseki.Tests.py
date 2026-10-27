"""Content-addressed Fuseki source and cache-hit regression tests."""
import importlib.util
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('canonical', ROOT / 'scripts/maintenance/canonical_fuseki.py')

class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ontology-fuseki-')
        self.context = Path(self.tmp.name)
        (self.context / 'Dockerfile').write_text('FROM scratch\n')
        self.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(self.mod)
    def tearDown(self): self.tmp.cleanup()
    def test_content_identity_ignores_metadata_but_tracks_every_byte(self):
        first = self.mod.context_digest(self.context)
        (self.context / 'entrypoint.sh').write_text('echo test\n')
        self.assertNotEqual(self.mod.context_digest(self.context), first)
        self.assertEqual(self.mod.context_digest(self.context), self.mod.context_digest(self.context))
    def test_symlink_and_unknown_input_are_rejected(self):
        (self.context / 'other').symlink_to('/tmp')
        with self.assertRaises(self.mod.BuildRefused): self.mod.context_digest(self.context)
    def test_cache_hit_never_builds_and_records_image_identity(self):
        digest = self.mod.context_digest(self.context)
        image = 'sha256:' + 'a'*64
        data = {'Id': image, 'Labels': {'org.opencontainers.image.source': self.mod.SOURCE, 'io.ontology-platform.context-sha256': digest}}
        def run(args, **kwargs):
            self.assertEqual(args[:3], ['docker','image','inspect'])
            return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
        with patch.object(self.mod, 'invoke', side_effect=run) as cli:
            result = self.mod.ensure_image(self.context, 'TEST-001', 'fixture')
            self.assertTrue(result['reused'])
            self.assertEqual(result['imageId'], image)
            self.assertEqual(cli.call_count, 1)
    def test_changed_existing_tag_is_refused(self):
        with patch.object(self.mod, 'invoke', return_value=subprocess.CompletedProcess([],0,json.dumps({'Id':'sha256:'+'a'*64,'Labels':{}}),'')):
            with self.assertRaises(self.mod.BuildRefused) as caught: self.mod.ensure_image(self.context,'TEST-001','fixture')
            self.assertEqual(caught.exception.diagnostic['command'][:3],['docker','image','inspect'])
            self.assertIn('sha256',caught.exception.diagnostic['stdout'])
    def test_socket_or_inspect_errors_do_not_trigger_build(self):
        with patch.object(self.mod, 'invoke', return_value=subprocess.CompletedProcess([],1,'','permission denied')) as cli:
            with self.assertRaises(self.mod.BuildRefused): self.mod.ensure_image(self.context,'TEST-001','fixture')
            self.assertEqual(cli.call_count,1)
    def failure_fixture(self):
        self.mod.ROOT=self.context
        context=self.context/'infra/development/fuseki'
        context.mkdir(parents=True)
        (context/'Dockerfile').write_text('FROM scratch\n')
        return self.mod.context_digest(context)
    def test_timeout_receipt_is_atomic_sanitized_and_lock_released_for_retry(self):
        digest=self.failure_fixture()
        tag=self.mod.REPOSITORY+':context-'+digest
        sentinel='SYNTHETIC_RAW_SECRET_NEVER_PERSIST'
        raw_out=b'#1 [internal] load build definition from Dockerfile\n#2 [1/2] RUN echo '+sentinel.encode()+b'\n'
        raw_err=b'#2 ERROR: '+sentinel.encode()+b' TLS handshake timeout\n'
        def cli(args,**kwargs):
            self.assertEqual(kwargs.get('timeout'),600)
            if args[0]=='git':return subprocess.CompletedProcess(args,0,str(self.context/'.git')+'\n','')
            if args[1:3]==['image','inspect']:return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such image: '+tag)
            raise subprocess.TimeoutExpired(args,600,output=raw_out,stderr=raw_err)
        out=io.StringIO()
        with patch.object(self.mod.subprocess,'run',side_effect=cli),contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            with self.assertRaises(self.mod.BuildRefused):self.mod.build('TASK-123','failed-run')
        receipts=list((self.context/'artifacts/fuseki-builds').glob('*.failed.json'))
        self.assertEqual(len(receipts),1)
        self.assertFalse(list((self.context/'artifacts/fuseki-builds').glob('*.partial')))
        self.assertFalse((self.context/'artifacts/fuseki-builds/canonical.lock').exists())
        raw=receipts[0].read_text();receipt=json.loads(raw)
        self.assertNotIn(sentinel,raw+out.getvalue())
        self.assertEqual(receipt['taskId'],'TASK-123')
        self.assertEqual(receipt['contextSha256'],digest)
        self.assertEqual(receipt['failure']['exitCode'],'TIMEOUT')
        self.assertEqual(receipt['failure']['stdout']['sha256'],hashlib.sha256(raw_out).hexdigest())
        self.assertEqual(receipt['failure']['stderr']['sizeBytes'],len(raw_err))
        self.assertIn('NETWORK_TIMEOUT',receipt['failure']['errorCategories'])
        self.assertIn('RUN',[x['phase'] for x in receipt['failure']['stageWindow']])
        def successful(args,**kwargs):
            if args[0]=='git':return subprocess.CompletedProcess(args,0,str(self.context/'.git')+'\n','')
            return subprocess.CompletedProcess(args,0,json.dumps({'Id':'sha256:'+'a'*64,'Labels':{'org.opencontainers.image.source':self.mod.SOURCE,'io.ontology-platform.context-sha256':digest}}),'')
        with patch.object(self.mod.subprocess,'run',side_effect=successful):
            self.assertTrue(self.mod.build('TASK-123','retry-run')['reused'])
        self.assertEqual(len(list((self.context/'artifacts/fuseki-builds').glob('*.failed.json'))),1)
    def test_nonzero_build_receipt_has_only_safe_command_and_output_hashes(self):
        digest=self.failure_fixture();tag=self.mod.REPOSITORY+':context-'+digest
        sentinel='SYNTHETIC_PRIVATE_BUILD_OUTPUT'
        def cli(args,**kwargs):
            if args[0]=='git':return subprocess.CompletedProcess(args,0,str(self.context/'.git')+'\n','')
            if args[1:3]==['image','inspect']:return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such image: '+tag)
            return subprocess.CompletedProcess(args,17,'#3 [2/2] COPY '+sentinel,'#3 ERROR: '+sentinel+' checksum mismatch')
        out,err=io.StringIO(),io.StringIO()
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'2','UNRELATED_PRIVATE_ENV':sentinel}),patch.object(self.mod.subprocess,'run',side_effect=cli),patch.object(sys,'argv',['canonical_fuseki.py','--task-id','TASK-123','--run-id','nonzero-run']),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(self.mod.main(),1)
        self.assertEqual(out.getvalue(),'')
        self.assertNotIn(sentinel,err.getvalue())
        self.assertIn('CANONICAL_FAILURE_RECEIPT ',err.getvalue())
        receipt_path=next((self.context/'artifacts/fuseki-builds').glob('*.failed.json'))
        receipt=json.loads(receipt_path.read_text())
        self.assertEqual(receipt['failure']['exitCode'],17)
        self.assertEqual(receipt['failure']['command'][:2],['docker','build'])
        self.assertNotIn(sentinel,receipt_path.read_text())
        self.assertNotIn('--build-arg',receipt_path.read_text())
        summary=json.loads(next(line.split(' ',1)[1] for line in err.getvalue().splitlines() if line.startswith('CANONICAL_FAILURE_RECEIPT ')))
        self.assertEqual(summary,receipt)
        self.assertEqual(receipt['ciContext'],{'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'2'})
        self.assertNotIn('UNRELATED_PRIVATE_ENV',receipt_path.read_text())
        self.assertFalse((self.context/'artifacts/fuseki-builds/canonical.lock').exists())

    def test_inspect_failure_receipt_never_launches_build(self):
        self.failure_fixture();calls=[]
        def cli(args,**kwargs):
            calls.append(args)
            if args[0]=='git':return subprocess.CompletedProcess(args,0,str(self.context/'.git')+'\n','')
            return subprocess.CompletedProcess(args,1,'','permission denied SYNTHETIC_INSPECT_SECRET')
        with patch.object(self.mod.subprocess,'run',side_effect=cli):
            with self.assertRaises(self.mod.BuildRefused):self.mod.build('TASK-123','inspect-failed')
        self.assertFalse(any(c[:2]==['docker','build'] for c in calls))
        receipt=next((self.context/'artifacts/fuseki-builds').glob('*.failed.json')).read_text()
        self.assertNotIn('SYNTHETIC_INSPECT_SECRET',receipt)
        self.assertIn('PERMISSION_DENIED',receipt)
        self.assertFalse((self.context/'artifacts/fuseki-builds/canonical.lock').exists())
    def test_diagnostic_drops_unrecognized_arguments_and_caps_stage_window(self):
        sentinel='SYNTHETIC_BUILDARG_SECRET'
        diagnostic=self.mod.command_diagnostic(['docker','build','--build-arg',sentinel],1,1,'\n'.join('#'+str(i)+' [1/1] RUN '+sentinel for i in range(30)),sentinel)
        self.assertNotIn(sentinel,json.dumps(diagnostic))
        self.assertLessEqual(len(diagnostic['stageWindow']),12)

    def test_both_apphost_profiles_and_acceptance_share_source(self):
        for name in ('G2Infrastructure.cs','DevelopmentInfrastructure.cs'):
            text = (ROOT/'backend/src/AppHost'/name).read_text()
            self.assertNotIn('AddDockerfile',text)
            self.assertIn('CanonicalFusekiImage.Add',text)
        text=(ROOT/'scripts/acceptance/g2-integration.ps1').read_text()
        self.assertIn('canonical_fuseki.py',text)
        self.assertNotIn('docker build',text)

if __name__ == '__main__': unittest.main()
