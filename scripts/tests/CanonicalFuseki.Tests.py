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
        self.context = Path(self.tmp.name).resolve()
        (self.context / 'Dockerfile').write_text('FROM scratch\n')
        self.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(self.mod)
        for name in ('fetch-fuseki.sh','entrypoint.sh','g2-config.ttl','g2-log4j2.properties','.dockerignore'):
            (self.context/name).write_text('fixture\n')
        self.engine = patch.object(self.mod,'engine_identity',return_value=dict(platform='linux/amd64',engineVersion='29.9.2',buildxVersion='v0.34.1'))
        self.engine.start()
        self.source_tmp=tempfile.TemporaryDirectory(prefix='ontology-prepared-',dir=Path(tempfile.gettempdir()).resolve())
        source_dir=Path(self.source_tmp.name);(source_dir/'fuseki.tar.gz').write_bytes(b'fixture')
        self.prepared=patch.object(self.mod,'prepare_source',return_value=contextlib.nullcontext(dict(directory=source_dir,receipt={},stages=[],verified=True,downloaded=False)),create=True)
        self.source_valid=patch.object(self.mod,'validate_source_context',return_value=7,create=True)
        self.prepared.start();self.source_valid.start()
    def tearDown(self): self.source_valid.stop();self.prepared.stop();self.source_tmp.cleanup();self.engine.stop();self.tmp.cleanup()
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
        data = {'Id':image,'Labels':self.mod.expected_labels(self.mod.identity(self.context)),'Os':'linux','Architecture':'amd64'}
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
        for name in ('fetch-fuseki.sh','entrypoint.sh','g2-config.ttl','g2-log4j2.properties','.dockerignore'):
            (context/name).write_text('fixture\n')
        return self.mod.context_digest(context)
    def test_timeout_receipt_is_atomic_sanitized_and_lock_released_for_retry(self):
        digest=self.failure_fixture()
        tag=self.mod.identity(self.context/'infra/development/fuseki')['image']
        sentinel='SYNTHETIC_RAW_SECRET_NEVER_PERSIST'
        raw_out=b'#1 [internal] load build definition from Dockerfile\n#2 [1/2] RUN echo '+sentinel.encode()+b'\n'
        raw_err=b'#2 ERROR: '+sentinel.encode()+b' TLS handshake timeout\n'
        def cli(args,**kwargs):
            self.assertGreater(kwargs.get('timeout'),0);self.assertLessEqual(kwargs.get('timeout'),600)
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
            return subprocess.CompletedProcess(args,0,json.dumps({'Id':'sha256:'+'a'*64,'Labels':self.mod.expected_labels(self.mod.identity(self.context/'infra/development/fuseki')),'Os':'linux','Architecture':'amd64'}),'')
        with patch.object(self.mod.subprocess,'run',side_effect=successful):
            self.assertTrue(self.mod.build('TASK-123','retry-run')['reused'])
        self.assertEqual(len(list((self.context/'artifacts/fuseki-builds').glob('*.failed.json'))),1)
    def test_nonzero_build_receipt_has_only_safe_command_and_output_hashes(self):
        digest=self.failure_fixture();tag=self.mod.identity(self.context/'infra/development/fuseki')['image']
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
        self.assertIn('--failure-state',text)
        host=(ROOT/'backend/src/AppHost/CanonicalFusekiImage.cs').read_text()
        self.assertIn('--failure-state',host)
        self.assertIn('artifacts/fuseki-failures',host)

    def test_ci_cold_build_precedes_restore_and_integration_requires_cache_hit(self):
        workflow=(ROOT/'.github/workflows/ci.yml').read_text().split('  governance-integration:',1)[1]
        self.assertLess(workflow.index('Preflight canonical Fuseki'),workflow.index('actions/setup-dotnet'))
        self.assertIn('PLATFORM_TASK_ID: G3-M3-001',workflow)
        integration=(ROOT/'scripts/acceptance/g2-integration.ps1').read_text()
        self.assertIn('CANONICAL_FUSEKI_RECEIPT',integration)
        self.assertIn("$env:CI -eq 'true' -and -not $fuseki.reused",integration)

class CanonicalDownloadTests(unittest.TestCase):
    """Run the actual shell download boundary with deterministic public-byte transports."""
    def exercise(self,mode):
        script=ROOT/'infra/development/fuseki/fetch-fuseki.sh'
        self.assertTrue(script.is_file(),'Missing bounded official Fuseki download entry')
        with tempfile.TemporaryDirectory(prefix='ontology-download-') as directory:
            root=Path(directory);binary=root/'bin';binary.mkdir();calls=root/'calls.jsonl'
            curl=binary/'curl'
            curl.write_text('#!'+sys.executable+'\n'+
                'import json,os,sys\nfrom pathlib import Path\n'+
                'a=sys.argv[1:]\nwith Path(os.environ["CALLS"]).open("a") as f:f.write(json.dumps(a)+"\\n")\n'+
                'mode=os.environ["MODE"];primary="dlcdn.apache.org" in a[-1]\n'+
                'if mode=="timeout":sys.exit(28)\n'+
                'if mode=="connect":sys.exit(7)\n'+
                'if mode=="both-fail" or (mode=="fallback" and primary):sys.exit(22)\n'+
                'Path(a[a.index("--output")+1]).write_bytes(b"wrong" if mode=="bad-hash" else b"canonical-fixture")\n')
            checksum=binary/'sha512sum'
            checksum.write_text('#!'+sys.executable+'\n'+
                'import hashlib,sys\nfrom pathlib import Path\n'+
                'expected,name=sys.stdin.read().rstrip("\\n").split("  ",1)\n'+
                'sys.exit(0 if hashlib.sha512(Path(name).read_bytes()).hexdigest()==expected else 1)\n')
            curl.chmod(0o755);checksum.chmod(0o755)
            result=subprocess.run(['sh',str(script),'6.2.0',hashlib.sha512(b'canonical-fixture').hexdigest(),str(root/'package.tar.gz')],
                env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],MODE=mode,CALLS=str(calls)),capture_output=True,text=True)
            return result,[json.loads(line) for line in calls.read_text().splitlines()]

    def test_official_primary_is_bounded_and_hash_checked(self):
        result,calls=self.exercise('primary')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][-1],'https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')
        args=calls[0]
        for flag,value in [('--connect-timeout','15'),('--max-time','180'),('--retry','0'),('--max-redirs','3'),('--proto','=https'),('--proto-redir','=https')]:
            self.assertEqual(args[args.index(flag)+1],value)

    def test_primary_transport_failure_uses_only_fixed_official_archive(self):
        result,calls=self.exercise('fallback')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][-1],'https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')
        self.assertEqual(sum(int(a[a.index('--max-time')+1]) for a in calls),360)

    def test_successful_download_with_bad_sha_never_falls_back(self):
        result,calls=self.exercise('bad-hash')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(calls),1)

    def test_both_failed_downloads_cannot_become_success_or_repeat(self):
        result,calls=self.exercise('both-fail')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(calls),2)

    def test_timeout_and_connect_failures_have_same_categories_as_short_probe(self):
        for mode,category in [('timeout','NETWORK_TIMEOUT'),('connect','NETWORK_CONNECT')]:
            with self.subTest(mode=mode):
                result,calls=self.exercise(mode)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(len(calls),2)
                stages=[json.loads(line.split('CANONICAL_STAGE ',1)[1]) for line in result.stdout.splitlines() if line.startswith('CANONICAL_STAGE ')]
                self.assertEqual([stage['errorCategory'] for stage in stages],[category,category])

    def test_download_reports_separate_actual_network_and_checksum_durations(self):
        result,_=self.exercise('primary')
        stages=[json.loads(line.split('CANONICAL_STAGE ',1)[1]) for line in result.stdout.splitlines() if line.startswith('CANONICAL_STAGE ')]
        self.assertEqual([stage['stage'] for stage in stages],['network','checksum'])
        self.assertTrue(all(stage['outcome']=='PASS' and type(stage['durationMs']) is int and stage['durationMs']>=0 for stage in stages))

    def test_checksum_failure_is_reported_without_network_fallback(self):
        result,calls=self.exercise('bad-hash')
        stages=[json.loads(line.split('CANONICAL_STAGE ',1)[1]) for line in result.stdout.splitlines() if line.startswith('CANONICAL_STAGE ')]
        self.assertEqual(len(calls),1)
        self.assertEqual(stages[-1]['errorCategory'],'CHECKSUM_MISMATCH')
        self.assertEqual(stages[-1]['outcome'],'FAIL')

    def test_real_dockerfile_extract_shell_emits_parseable_bounded_stage(self):
        dockerfile=(ROOT/'infra/development/fuseki/Dockerfile').read_text()
        command=dockerfile.split('RUN ',1)[1].split('\n\n',1)[0].replace('\\\n','')
        with tempfile.TemporaryDirectory(prefix='ontology-extract-') as directory:
            binary=Path(directory)
            for name in ('fetch-fuseki','sha512sum','mkdir','tar','rm','groupadd','useradd','chown'):
                script=binary/name;script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
            clock=binary/'date';clock.write_text('#!'+sys.executable+'\nimport time\nprint(time.time_ns())\n');clock.chmod(0o755)
            result=subprocess.run(['sh','-c',command],env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],JENA_VERSION='6.2.0',JENA_SHA512='fixture'),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        stages=[json.loads(line.split('CANONICAL_STAGE ',1)[1]) for line in result.stdout.splitlines() if line.startswith('CANONICAL_STAGE ')]
        self.assertEqual(len(stages),2)
        self.assertEqual(stages[0]['stage'],'checksum')
        self.assertEqual(stages[1]['stage'],'extract/COPY')
        self.assertEqual(stages[0]['outcome'],'PASS')
        self.assertGreaterEqual(stages[0]['durationMs'],0)

    def test_unique_dockerfile_verifies_before_extracting_without_version_change(self):
        dockerfile=(ROOT/'infra/development/fuseki/Dockerfile').read_text()
        self.assertIn('!fetch-fuseki.sh',(ROOT/'infra/development/fuseki/.dockerignore').read_text())
        self.assertIn('COPY --from=fuseki_source',dockerfile)
        self.assertLess(dockerfile.index('sha512sum --check --strict'),dockerfile.index('tar -xzf'))
        self.assertIn('ARG JENA_VERSION=6.2.0',dockerfile)
        self.assertIn('ba65f5867d2d4741b2ed9e2af5a0d4fbb447909894ab2a0c6bc4dac8997f4fe339c87b13c48d45d054977769f0f8bf763ea346b1f7792d5cdc458041bd43a132',dockerfile)

class CanonicalSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ontology-source-',dir=Path(tempfile.gettempdir()).resolve())
        self.root=Path(self.tmp.name);self.cache=self.root/'cache'
        self.mod=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(self.mod)
        self.payload=b'canonical-source-fixture'
        self.sha=hashlib.sha512(self.payload).hexdigest()
        self.checksum=patch.object(self.mod,'JENA_SHA512',self.sha);self.checksum.start()

    def tearDown(self):self.checksum.stop();self.tmp.cleanup()

    def seed(self,raw=None):
        self.cache.mkdir();path=self.cache/(self.sha+'.tar.gz');path.write_bytes(self.payload if raw is None else raw)
        return path

    def transport(self,mode='success'):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs))
            if mode=='timeout':return subprocess.CompletedProcess(args,28,None,b'timeout SYNTHETIC_PRIVATE_TOKEN')
            if mode=='too-large':return subprocess.CompletedProcess(args,63,None,b'exceeds limit')
            if mode=='fallback' and 'dlcdn.apache.org' in args[-1]:return subprocess.CompletedProcess(args,22,None,b'http failure')
            kwargs['stdout'].write(b'wrong' if mode=='bad-hash' else self.payload);kwargs['stdout'].flush()
            return subprocess.CompletedProcess(args,0,None,b'\nCANONICAL_HTTP 200 \n')
        return calls,run

    def test_valid_cached_source_is_rehashed_and_staged_as_exact_single_file(self):
        path=self.seed();temporary=None
        with patch.object(self.mod.subprocess,'run',side_effect=AssertionError('cached source must not download')):
            with self.mod.prepare_source(self.cache,'G3-M3-001','source-cache','a'*64) as source:
                temporary=source['directory']
                self.assertEqual(sorted(p.name for p in temporary.iterdir()),['fuseki.tar.gz'])
                self.assertEqual((temporary/'fuseki.tar.gz').read_bytes(),self.payload)
                self.assertTrue(source['verified']);self.assertFalse(source['downloaded'])
                self.assertEqual(source['receipt']['cacheOutcome'],'HIT')
                self.assertTrue(all(stage['executor']=='host' for stage in source['stages']))
        self.assertFalse(temporary.exists())
        self.assertTrue(source['receipt']['temporaryContextRemoved'])
        self.assertEqual(path.read_bytes(),self.payload)

    def test_cache_corruption_is_immediate_checksum_failure_without_download(self):
        self.seed(b'bad')
        with patch.object(self.mod.subprocess,'run',side_effect=AssertionError('bad hash cannot download fallback')):
            with self.assertRaises(self.mod.BuildRefused) as caught:
                with self.mod.prepare_source(self.cache,'TASK','bad','a'*64):pass
        self.assertEqual(caught.exception.category,'CHECKSUM_MISMATCH')
        self.assertEqual(caught.exception.stage,'checksum')

    def test_cache_symlink_ancestor_link_and_oversize_are_refused(self):
        actual=self.root/'actual';actual.write_bytes(self.payload);self.cache.mkdir()
        (self.cache/(self.sha+'.tar.gz')).symlink_to(actual)
        with self.assertRaises(self.mod.BuildRefused):
            with self.mod.prepare_source(self.cache,'TASK','link','a'*64):pass
        (self.cache/(self.sha+'.tar.gz')).unlink();(self.cache/(self.sha+'.tar.gz')).write_bytes(self.payload)
        with patch.object(self.mod,'MAX_SOURCE_BYTES',4,create=True):
            with self.assertRaises(self.mod.BuildRefused):
                with self.mod.prepare_source(self.cache,'TASK','large','a'*64):pass
        linked=self.root/'linked';linked.symlink_to(self.cache,target_is_directory=True)
        with self.assertRaises(self.mod.BuildRefused):
            with self.mod.prepare_source(linked,'TASK','ancestor','a'*64):pass

    def test_cold_host_download_uses_fixed_bounded_https_and_publishes_only_verified_source(self):
        calls,run=self.transport()
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.mod.prepare_source(self.cache,'TASK','download','a'*64) as source:
                self.assertTrue(source['downloaded']);self.assertTrue(source['verified'])
                self.assertEqual(source['receipt']['sizeBytes'],len(self.payload))
        self.assertEqual(len(calls),1)
        args,kwargs=calls[0]
        self.assertEqual(args[-1],'https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')
        for flag,value in [('--connect-timeout','15'),('--max-time','180'),('--retry','0'),('--max-redirs','3'),('--proto','=https'),('--proto-redir','=https')]:
            self.assertEqual(args[args.index(flag)+1],value)
        self.assertIn('--max-filesize',args)
        self.assertNotIn('--output',args)
        self.assertLessEqual(kwargs['timeout'],185)
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()),[self.sha+'.tar.gz'])

    def test_host_network_failure_falls_back_once_to_same_fixed_release(self):
        calls,run=self.transport('fallback')
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.mod.prepare_source(self.cache,'TASK','fallback','a'*64) as source:self.assertTrue(source['verified'])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][0][-1],'https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')

    def test_download_checksum_error_or_limit_never_falls_back_or_publishes(self):
        for mode in ('bad-hash','too-large'):
            with self.subTest(mode=mode):
                cache=self.root/mode;calls,run=self.transport(mode)
                with patch.object(self.mod.subprocess,'run',side_effect=run):
                    with self.assertRaises(self.mod.BuildRefused):
                        with self.mod.prepare_source(cache,'TASK',mode,'a'*64):pass
                self.assertEqual(len(calls),1)
                self.assertFalse((cache/(self.sha+'.tar.gz')).exists())

    def test_two_timeouts_preserve_only_sanitized_failure_stages(self):
        calls,run=self.transport('timeout')
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:
                with self.mod.prepare_source(self.cache,'TASK','timeouts','a'*64):pass
        self.assertEqual(caught.exception.category,'NETWORK_TIMEOUT')
        self.assertEqual(len(calls),2)
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))
        self.assertEqual(sum(stage['stage']=='network' for stage in caught.exception.stages),2)

    def test_named_context_extra_file_and_changed_bytes_are_refused(self):
        self.seed()
        with self.mod.prepare_source(self.cache,'TASK','context','a'*64) as source:
            extra=source['directory']/'extra';extra.write_bytes(b'bad')
            with self.assertRaises(self.mod.BuildRefused):self.mod.validate_source_context(source['directory'])
            extra.unlink()
            archive=source['directory']/'fuseki.tar.gz';archive.chmod(0o600);archive.write_bytes(b'bad')
            with self.assertRaises(self.mod.BuildRefused):self.mod.validate_source_context(source['directory'])
            archive.write_bytes(self.payload)

    def test_host_short_probe_does_not_require_or_start_a_docker_container(self):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs));self.assertEqual(args[0],'curl')
            return subprocess.CompletedProcess(args,28,'','timeout')
        with patch.object(self.mod.subprocess,'run',side_effect=run):result=self.mod.host_network_probe('TASK','probe')
        self.assertEqual(result['scope'],'host')
        self.assertEqual(result['outcome'],'REPRODUCED')
        self.assertEqual(result['sourceExitCodes'],[28,28])
        self.assertEqual(len(calls),2)
        self.assertLessEqual(sum(kw['timeout'] for args,kw in calls),20)
        self.assertTrue(all('--head' in args for args,kw in calls))

    def test_bad_source_cache_failure_is_actually_rechecked_and_fixed_cache_recovers(self):
        cache_file=self.seed(b'bad');context=self.root/'context';context.mkdir()
        for name in self.mod.CONTEXT_FILES:(context/name).write_text('fixture\n')
        expected=dict(inputFingerprint='a'*64,envFingerprint='b'*64,platform='linux/amd64')
        failure=None
        try:
            with self.mod.prepare_source(self.cache,'TASK','first','a'*64):pass
        except self.mod.BuildRefused as caught:failure=caught
        self.assertEqual(failure.category,'CHECKSUM_MISMATCH')
        state=self.root/'failure'
        self.mod.save_failure_state(state,expected,failure,'first','a'*40)
        with patch.object(self.mod.subprocess,'run',side_effect=AssertionError('checksum probe must not download/build')):
            with self.assertRaises(self.mod.BuildRefused) as caught:
                self.mod.failure_gate(state,expected,context,source_cache=self.cache)
            self.assertEqual(caught.exception.exit_code,2)
            self.assertEqual(caught.exception.diagnostic['probe']['operation'],'SOURCE_CACHE_VALIDATE')
            cache_file.write_bytes(self.payload)
            recovered=self.mod.failure_gate(state,expected,context,source_cache=self.cache)
            self.assertEqual(recovered['outcome'],'RECOVERED')
            self.assertTrue((state/'failure.json').exists())

    def test_malicious_redirect_and_parameters_do_not_start_another_request(self):
        calls=[]
        def run(args,**kw):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,None,b'\nCANONICAL_HTTP 302 https://SYNTHETIC_PRIVATE_TOKEN.example/source\n')
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:
                with self.mod.prepare_source(self.cache,'TASK','redirect','a'*64):pass
        self.assertEqual(caught.exception.category,'SOURCE_REDIRECT_REFUSED')
        self.assertEqual(len(calls),1)
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))
        with self.assertRaises(self.mod.BuildRefused):
            with self.mod.prepare_source(self.cache,'TASK;injection','bad','a'*64):pass

    def test_host_curl_disables_default_config_before_all_other_options(self):
        calls,run=self.transport()
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.mod.prepare_source(self.cache,'TASK','curlrc','a'*64):pass
        self.assertEqual(calls[0][0][:2],['curl','-q'])
        curl_home=self.root/'curl-home';curl_home.mkdir();output=curl_home/'unexpected-output'
        (curl_home/'.curlrc').write_text('location\noutput = "'+str(output)+'"\nurl = "file:///SYNTHETIC_NOT_READ"\nSYNTHETIC_INVALID_OPTION = yes\n')
        env=dict(os.environ,CURL_HOME=str(curl_home))
        control=subprocess.run(['curl','--version'],env=env,capture_output=True,text=True,timeout=3)
        self.assertIn('SYNTHETIC_INVALID_OPTION',control.stderr,'control must actually read isolated .curlrc')
        clean=subprocess.run(calls[0][0][:2]+['--version'],env=env,capture_output=True,text=True,timeout=3)
        self.assertEqual(clean.returncode,0)
        self.assertNotIn('SYNTHETIC_INVALID_OPTION',clean.stderr)
        self.assertFalse(output.exists())

    def test_real_test_cli_help_and_unknown_flag_never_touch_docker(self):
        binary=self.root/'cli-bin';binary.mkdir();marker=self.root/'docker-access'
        docker=binary/'docker';docker.write_text('#!/bin/sh\nprintf touched > "'+str(marker)+'"\nexit 83\n');docker.chmod(0o755)
        for flag,wanted in [('--help',0),('--synthetic-unknown',2)]:
            with self.subTest(flag=flag):
                marker.unlink(missing_ok=True)
                result=subprocess.run([sys.executable,str(ROOT/'scripts/tests/CanonicalFuseki.Real.Tests.py'),flag],
                                      env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH']),capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,wanted)
                self.assertFalse(marker.exists())

    def test_dockerfile_uses_named_source_and_checks_checksum_before_extract(self):
        text=(ROOT/'infra/development/fuseki/Dockerfile').read_text()
        self.assertIn('COPY --from=fuseki_source',text)
        self.assertLess(text.index('sha512sum --check --strict'),text.index('tar -xzf'))
        self.assertNotIn('fetch-fuseki "$JENA_VERSION"',text)

if __name__ == '__main__': unittest.main()
