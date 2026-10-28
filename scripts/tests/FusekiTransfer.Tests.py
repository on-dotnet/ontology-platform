"""Strict transfer guard tests; fixtures never authorize an actual upload."""
import datetime as dt
import importlib.util
import json
import hashlib
import io
import tarfile
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/maintenance/fuseki_transfer.py'


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(),'transfer guard implementation is required')
        spec=importlib.util.spec_from_file_location('transfer',SCRIPT)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.now=dt.datetime(2026,10,28,15,tzinfo=dt.timezone.utc)
        self.proof=dict(schemaVersion=1,repository='on-dotnet/ontology-platform',owner='on-dotnet',confirmedAtUtc=self.now.isoformat(),
                        hardSpendLimitUSD=0,remainingIncludedBytes=450*1024**2,humanConfirmed=True,
                        confirmationSource='human-current-session',scope='owner-actions-artifacts-and-packages')
        self.repo=dict(id=123,full_name='on-dotnet/ontology-platform',private=False,visibility='public')
        self.env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='on-dotnet/ontology-platform',
                      GITHUB_SHA='a'*40,GITHUB_RUN_ID='1234',GITHUB_RUN_ATTEMPT='1',GITHUB_REF='refs/heads/main',
                      RUNNER_OS='Linux',RUNNER_ARCH='ARM64',RUNNER_ENVIRONMENT='github-hosted')
        self.event=dict(ref='refs/heads/main',inputs={},repository=self.repo)

    def inventory(self,artifacts=(),total=None):
        calls=[]
        def fetch(path):
            calls.append(path)
            if path=='/repos/on-dotnet/ontology-platform':return self.repo,{}
            return dict(total_count=len(artifacts) if total is None else total,artifacts=list(artifacts)),{}
        return self.m.inventory(fetch),calls

    def test_synthetic_current_zero_overage_proof_allows_only_bounded_budget(self):
        snapshot,_=self.inventory()
        result=self.m.budget(150*1024**2,snapshot,self.proof,self.now)
        self.assertEqual(result['status'],'BUDGET_CHECKED')
        self.assertEqual(result['conservativeLimitBytes'],450*1024**2)
        self.assertFalse(result['uploadPerformed'])

    def test_missing_proof_never_uses_empty_repo_as_account_budget(self):
        snapshot,_=self.inventory()
        with self.assertRaises(self.m.TransferRefused) as caught:self.m.budget(1,snapshot,None,self.now)
        self.assertEqual(caught.exception.category,'ACCOUNT_BUDGET_UNKNOWN')

    def test_unknown_fields_private_owner_paid_or_unconfirmed_proofs_fail(self):
        for change in ({'extra':'SYNTHETIC_PRIVATE_TOKEN'},{'repository':'other/repo'},{'owner':'other'},
                       {'hardSpendLimitUSD':1},{'hardSpendLimitUSD':False},{'humanConfirmed':False},
                       {'remainingIncludedBytes':True},{'scope':'repository-only'},{'confirmationSource':'event-input'}):
            with self.subTest(change=change):
                proof=dict(self.proof,**change)
                with self.assertRaises(self.m.TransferRefused):self.m.proof_headroom(proof,self.now)

    def test_stale_future_or_naive_proof_is_unknown(self):
        for timestamp in ('2026-10-28T13:59:59+00:00','2026-10-28T15:00:01+00:00','2026-10-28T15:00:00'):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(self.m.TransferRefused):self.m.proof_headroom(dict(self.proof,confirmedAtUtc=timestamp),self.now)

    def test_oversize_or_exhausted_budget_is_refused(self):
        snapshot,_=self.inventory()
        for size in (0,True,512*1024**2+1,450*1024**2):
            with self.subTest(size=size):
                with self.assertRaises(self.m.TransferRefused):self.m.budget(size,snapshot,self.proof,self.now)
        with self.assertRaises(self.m.TransferRefused):self.m.budget(20*1024**2,snapshot,dict(self.proof,remainingIncludedBytes=1),self.now)

    def test_all_artifacts_including_expired_are_counted(self):
        snapshot,_=self.inventory([dict(id=1,name='old',size_in_bytes=100,expired=True),dict(id=2,name='other',size_in_bytes=20,expired=False)])
        self.assertEqual(snapshot['currentBytes'],120)
        self.assertEqual(snapshot['artifactCount'],2)

    def test_existing_transfer_prevents_second_transfer(self):
        snapshot,_=self.inventory([dict(id=1,name='canonical-fuseki-arm64-'+'a'*40,size_in_bytes=1,expired=False)])
        with self.assertRaises(self.m.TransferRefused):self.m.budget(1,snapshot,self.proof,self.now)

    def test_private_or_forged_live_repository_is_refused(self):
        for change in ({'private':True},{'visibility':'private'},{'full_name':'other/repo'},{'id':True}):
            with self.subTest(change=change):
                self.repo.update(change)
                with self.assertRaises(self.m.TransferRefused):self.inventory()
                self.repo=dict(id=123,full_name='on-dotnet/ontology-platform',private=False,visibility='public')

    def test_partial_pagination_duplicate_ids_unknown_sizes_and_limits_fail(self):
        cases=[([dict(id=1,name='a',size_in_bytes=1,expired=False)],2),
               ([dict(id=1,name='a',size_in_bytes=1,expired=False)]*2,2),
               ([dict(id=1,name='a',size_in_bytes=True,expired=False)],1),([],301)]
        for artifacts,total in cases:
            with self.subTest(total=total,artifacts=artifacts):
                with self.assertRaises(self.m.TransferRefused):self.inventory(artifacts,total)

    def test_api_failure_is_never_empty_budget(self):
        with self.assertRaises(self.m.TransferRefused):self.m.inventory(lambda path:(_ for _ in ()).throw(OSError('SYNTHETIC_PRIVATE_TOKEN')))

    def test_exact_event_and_native_runner_required(self):
        context=self.m.context(self.env,self.event,system='Linux',machine='aarch64')
        self.assertEqual(context['head'],'a'*40)
        for change in ({'GITHUB_EVENT_NAME':'push'},{'GITHUB_REPOSITORY':'other/repo'},{'RUNNER_ENVIRONMENT':'self-hosted'},
                       {'RUNNER_ARCH':'X64'},{'GITHUB_REF':'refs/pull/1/merge'}):
            with self.subTest(change=change):
                with self.assertRaises(self.m.TransferRefused):self.m.context(dict(self.env,**change),self.event,system='Linux',machine='aarch64')
        with self.assertRaises(self.m.TransferRefused):self.m.context(self.env,self.event,system='Darwin',machine='arm64')

    def test_event_unknown_fields_inputs_and_private_claims_fail(self):
        for change in ({'unknown':'SYNTHETIC_PRIVATE_TOKEN'},{'inputs':{'allow_paid':True}},{'repository':dict(self.repo,private=True)}):
            with self.subTest(change=change):
                with self.assertRaises(self.m.TransferRefused):self.m.context(self.env,dict(self.event,**change),system='Linux',machine='aarch64')

    def test_live_run_must_confirm_dispatch_exact_head_and_repository(self):
        ctx=self.m.context(self.env,self.event,system='Linux',machine='aarch64')
        run=dict(event='workflow_dispatch',head_sha='a'*40,head_branch='main',status='in_progress',run_attempt=1,
                 repository=self.repo,head_repository=self.repo)
        self.m.confirm_run(lambda path:(run,{}),ctx)
        for change in ({'event':'push'},{'head_sha':'b'*40},{'head_repository':dict(self.repo,id=456)},{'status':'completed'}):
            with self.subTest(change=change):
                with self.assertRaises(self.m.TransferRefused):self.m.confirm_run(lambda path:(dict(run,**change),{}),ctx)

    def test_complete_bounded_pagination_is_counted_without_following_external_links(self):
        def fetch(path):
            if path=='/repos/on-dotnet/ontology-platform':return self.repo,{}
            page=1 if path.endswith('page=1') else 2
            artifacts=[dict(id=i,name='a',size_in_bytes=1,expired=False) for i in (range(1,101) if page==1 else [101])]
            return dict(total_count=101,artifacts=artifacts),({'Link':'<https://api.github.com/repos/on-dotnet/ontology-platform/actions/artifacts?page=2&per_page=100>; rel="next"'} if page==1 else {})
        result=self.m.inventory(fetch)
        self.assertEqual(result['artifactCount'],101)
        self.assertEqual(result['currentBytes'],101)

    def test_api_only_sends_fixed_origin_get_without_authorization(self):
        client=self.m.PublicApi();requests=[]
        class Response:
            status=200
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return 'https://api.github.com/repos/on-dotnet/ontology-platform'
            def read(self,limit):return b'{}'
        class Opener:
            def open(self,request,timeout):requests.append((request,timeout));return Response()
        client.opener=Opener();client('/repos/on-dotnet/ontology-platform')
        request,timeout=requests[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertFalse(any(key.lower()=='authorization' for key in request.headers))
        self.assertIsNone(request.data)
        self.assertLessEqual(timeout,5)
        with self.assertRaises(self.m.TransferRefused):client('/orgs/on-dotnet/settings/billing/usage')

    def test_directory_uses_actual_canonical_validation_and_exact_producer_head(self):
        canonical=self.m.load_canonical()
        expected=dict(cacheKey='fixture',inputFingerprint='a'*64,contextSha256='b'*64,platform='linux/arm64',
                      image='ontology-platform-fuseki:context-'+'a'*64)
        config=dict(os='linux',architecture='arm64',config={'Labels':canonical.expected_labels(expected)},
                    rootfs={'type':'layers','diff_ids':['sha256:'+hashlib.sha256(b'layer').hexdigest()]})
        raw=json.dumps(config).encode();image_id='sha256:'+hashlib.sha256(raw).hexdigest();config_name=image_id[7:]+'.json'
        manifest=[dict(Config=config_name,RepoTags=[expected['image']],Layers=['layer/layer.tar'])]
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as temporary:
            directory=Path(temporary);path=directory/'image.tar'
            with tarfile.open(path,'w') as archive:
                for name,data in [('manifest.json',json.dumps(manifest).encode()),(config_name,raw),('layer/layer.tar',b'layer')]:
                    member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
            receipt=dict(schemaVersion=2,**expected,imageId=image_id,archiveSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         archiveSizeBytes=path.stat().st_size,producerRunId='fixture',producerHead='a'*40,jenaSha512=canonical.JENA_SHA512,
                         baseDigest=canonical.BASE_DIGEST,sourceChecksumVerified=False)
            (directory/'receipt.json').write_text(json.dumps(receipt))
            with patch.object(self.m,'load_canonical',return_value=canonical),patch.object(canonical,'identity',return_value=expected):
                self.assertGreater(self.m.validate_directory(directory,'a'*40)[0],0)
                with self.assertRaises(self.m.TransferRefused):self.m.validate_directory(directory,'b'*40)
                receipt['unknown']='SYNTHETIC_PRIVATE_TOKEN';(directory/'receipt.json').write_text(json.dumps(receipt))
                with self.assertRaises(self.m.TransferRefused):self.m.validate_directory(directory,'a'*40)
                receipt.pop('unknown');(directory/'receipt.json').write_text(json.dumps(receipt));(directory/'extra').write_text('not allowed')
                with self.assertRaises(self.m.TransferRefused):self.m.validate_directory(directory,'a'*40)

    def test_cli_missing_confirmation_is_blocked_without_secret_output(self):
        result=subprocess.run([sys.executable,str(SCRIPT),'preflight'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        data=json.loads(result.stdout)
        self.assertEqual(data['status'],'BLOCKED')
        self.assertFalse(data['uploadPerformed'])


if __name__=='__main__':unittest.main()
