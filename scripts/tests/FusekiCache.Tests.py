"""Exercise canonical identity, untrusted docker archives and persistent stop-loss."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('cache_canonical', ROOT/'scripts/maintenance/canonical_fuseki.py')


class FusekiCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ontology-cache-')
        self.root = Path(self.tmp.name).resolve()
        self.context = self.root/'context'
        self.context.mkdir()
        for name in ('Dockerfile', 'fetch-fuseki.sh', 'entrypoint.sh', 'g2-config.ttl', 'g2-log4j2.properties', '.dockerignore'):
            (self.context/name).write_text('fixture\n')
        self.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(self.mod)
        self.engine = patch.object(self.mod, 'engine_identity', return_value={'platform':'linux/amd64', 'engineVersion':'29.9.2', 'buildxVersion':'v0.34.1'}, create=True)
        self.engine.start()

    def tearDown(self):
        self.engine.stop()
        self.tmp.cleanup()

    def identity(self, platform='linux/amd64'):
        self.assertTrue(hasattr(self.mod, 'identity'), 'identity interface is required before caching')
        return self.mod.identity(self.context, platform)

    def archive(self, identity=None, extra=None, mutate_config=None):
        identity = identity or self.identity()
        config = {'rootfs':{'type':'layers','diff_ids':['sha256:'+hashlib.sha256(b'layer').hexdigest()]},'os':'linux','architecture':'amd64','config':{'Labels':{
            'org.opencontainers.image.source':'https://github.com/on-dotnet/ontology-platform',
            'io.ontology-platform.context-sha256':identity['contextSha256'],
            'io.ontology-platform.input-fingerprint':identity['inputFingerprint'],
            'io.ontology-platform.platform':'linux/amd64'}}}
        if mutate_config:
            mutate_config(config)
        raw = json.dumps(config, sort_keys=True).encode()
        image_id = 'sha256:'+hashlib.sha256(raw).hexdigest()
        config_name = image_id[7:]+'.json'
        manifest = [{'Config':config_name, 'RepoTags':[identity['image']], 'Layers':['layer/layer.tar']}]
        directory = self.root/'cache'
        directory.mkdir(exist_ok=True)
        path = directory/'image.tar'
        with tarfile.open(path, 'w') as archive:
            for name, data in [('manifest.json', json.dumps(manifest).encode()), (config_name, raw), ('layer/layer.tar', b'layer')]:
                member = tarfile.TarInfo(name);member.size=len(data);archive.addfile(member, io.BytesIO(data))
            if extra:
                archive.addfile(extra)
        receipt = dict(schemaVersion=2,cacheKey=identity['cacheKey'],inputFingerprint=identity['inputFingerprint'],
            contextSha256=identity['contextSha256'],platform=identity['platform'],image=identity['image'],imageId=image_id,
            archiveSha256=hashlib.sha256(path.read_bytes()).hexdigest(),archiveSizeBytes=path.stat().st_size,
            producerRunId='producer-100',producerHead='a'*40,jenaSha512=self.mod.JENA_SHA512,
            baseDigest=self.mod.BASE_DIGEST,sourceChecksumVerified=True)
        (directory/'receipt.json').write_text(json.dumps(receipt))
        return directory, receipt

    def rewrite_archive(self, directory, receipt, entries):
        path=directory/'image.tar'
        with tarfile.open(path,'w') as archive:
            for name,data in entries:
                member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
        receipt.update(archiveSha256=hashlib.sha256(path.read_bytes()).hexdigest(),archiveSizeBytes=path.stat().st_size)
        (directory/'receipt.json').write_text(json.dumps(receipt))

    def oci_archive(self, broken=None):
        identity=self.identity();directory,receipt=self.archive(identity)
        with tarfile.open(directory/'image.tar') as archive:
            config=json.load(archive.extractfile('manifest.json'))[0]['Config']
            raw=archive.extractfile(config).read()
        def blob(raw,media):
            digest=hashlib.sha256(raw).hexdigest()
            return ('blobs/sha256/'+digest,raw),dict(mediaType=media,digest='sha256:'+digest,size=len(raw))
        config_entry,config_desc=blob(raw,'application/vnd.oci.image.config.v1+json')
        layer_entry,layer_desc=blob(b'compressed-layer','application/vnd.oci.image.layer.v1.tar+gzip')
        manifest={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json','config':config_desc,'layers':[layer_desc]}
        if broken=='config':manifest['config']=dict(config_desc,digest='sha256:'+'f'*64)
        manifest_entry,descriptor=blob(json.dumps(manifest).encode(),manifest['mediaType'])
        if broken=='platform':descriptor['platform']={'os':'linux','architecture':'arm64'}
        if broken=='tag':descriptor['annotations']={'io.containerd.image.name':'docker.io/library/foreign:latest'}
        if broken=='media':descriptor['mediaType']='application/octet-stream'
        index={'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':[descriptor]}
        docker_manifest=[{'Config':config_entry[0],'RepoTags':[identity['image']],'Layers':[layer_entry[0]]}]
        entries=[config_entry,layer_entry,manifest_entry,('manifest.json',json.dumps(docker_manifest).encode()),
                 ('index.json',json.dumps(index).encode()),('oci-layout',b'{"imageLayoutVersion":"1.0.0"}')]
        receipt['imageId']=descriptor['digest']
        if broken=='layer':entries[1]=(layer_entry[0],b'tampered-layer!!')
        if broken=='root':receipt['imageId']='sha256:'+'e'*64
        if broken=='divergent':docker_manifest[0]['Layers']=[];entries[3]=('manifest.json',json.dumps(docker_manifest).encode())
        self.rewrite_archive(directory,receipt,entries)
        return identity,directory,receipt

    def test_real_engine_oci_manifest_id_is_valid_without_config_id_confusion(self):
        identity,directory,receipt=self.oci_archive()
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_oci_descriptors_bind_platform_tag_media_config_layers_and_root(self):
        for broken in ('config','platform','tag','media','layer','root','divergent'):
            with self.subTest(broken=broken):
                identity,directory,_=self.oci_archive(broken)
                with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_duplicate_tar_paths_and_control_characters_are_refused(self):
        for name in ('manifest.json','odd\npath'):
            with self.subTest(name=name):
                identity=self.identity();directory,receipt=self.archive(identity)
                with tarfile.open(directory/'image.tar') as archive:
                    entries=[(m.name,archive.extractfile(m).read()) for m in archive if m.isfile()]
                entries.append((name,b'{}'))
                self.rewrite_archive(directory,receipt,entries)
                with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_empty_cache_directory_is_a_miss(self):
        directory=self.root/'empty';directory.mkdir()
        self.assertEqual(self.mod.restore_cache(directory,self.identity())['outcome'],'MISS')

    def test_stage_marker_checksum_failure_drives_failure_category(self):
        raw='#4 CANONICAL_STAGE {"stage":"checksum","durationMs":7,"outcome":"FAIL","errorCategory":"CHECKSUM_MISMATCH"}'
        diagnostic=self.mod.command_diagnostic(['docker','build'],1,1,'',raw)
        self.assertEqual(self.mod.BuildRefused('failed',diagnostic).category,'CHECKSUM_MISMATCH')

    def test_timeout_without_partial_output_is_classified_for_stop_loss(self):
        with patch.object(self.mod.subprocess,'run',side_effect=subprocess.TimeoutExpired(['docker','build'],600)):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.invoke(['docker','build'])
        self.assertEqual(caught.exception.category,'NETWORK_TIMEOUT')

    def test_copy_inputs_must_be_regular_files(self):
        (self.context/'entrypoint.sh').unlink();(self.context/'entrypoint.sh').mkdir()
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.preflight_context(self.context)
        self.assertEqual(caught.exception.category,'COPY_INPUT_MISSING')

    def test_last_failed_marker_classifies_checksum_after_recovered_network(self):
        raw='\n'.join(['#4 CANONICAL_STAGE {"stage":"network","durationMs":7,"outcome":"FAIL","errorCategory":"NETWORK_TIMEOUT"}',
                        '#4 CANONICAL_STAGE {"stage":"network","durationMs":9,"outcome":"PASS","errorCategory":null}',
                        '#4 CANONICAL_STAGE {"stage":"checksum","durationMs":2,"outcome":"FAIL","errorCategory":"CHECKSUM_MISMATCH"}'])
        diagnostic=self.mod.command_diagnostic(['docker','build'],1,1,'',raw)
        self.assertEqual(self.mod.BuildRefused('failed',diagnostic).category,'CHECKSUM_MISMATCH')

    def test_invalid_image_label_shape_is_refused(self):
        identity=self.identity()
        image=dict(Id='sha256:'+'a'*64,Os='linux',Architecture='amd64',Labels='invalid')
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_image(image,identity)

    def test_legacy_layer_bytes_must_match_config_diff_id(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        with tarfile.open(directory/'image.tar') as archive:
            entries=[(m.name,b'other' if m.name=='layer/layer.tar' else archive.extractfile(m).read()) for m in archive if m.isfile()]
        self.rewrite_archive(directory,receipt,entries)
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_archive_refusal_exposes_fixed_check_and_shape_without_raw_values(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        with tarfile.open(directory/'image.tar') as archive:
            entries=[(member.name,archive.extractfile(member).read()) for member in archive if member.isfile()]
        manifest=json.loads(entries[0][1]);manifest[0]['SYNTHETIC_PRIVATE_FIELD']='SYNTHETIC_PRIVATE_TOKEN'
        entries[0]=('manifest.json',json.dumps(manifest).encode());self.rewrite_archive(directory,receipt,entries)
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
        self.assertEqual(caught.exception.diagnostic['validationCheck'],'MANIFEST_SCHEMA')
        self.assertEqual(caught.exception.diagnostic['archiveShape']['manifestUnknownFieldCount'],1)
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))

    def test_export_archive_refusal_is_classified_as_export_stage(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        (directory/'image.tar').write_bytes(b'bad')
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity,stage='cache export')
        self.assertEqual(caught.exception.stage,'cache export')
        self.assertEqual(caught.exception.diagnostic['validationCheck'],'ARCHIVE_HASH')

    def test_archive_links_remain_refused_with_member_type_diagnostic(self):
        identity=self.identity();link=tarfile.TarInfo('linked');link.type=tarfile.LNKTYPE;link.linkname='manifest.json'
        directory,_=self.archive(identity,extra=link)
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
        self.assertEqual(caught.exception.diagnostic['validationCheck'],'TAR_MEMBER_TYPES')
        self.assertEqual(caught.exception.diagnostic['archiveShape']['linkCount'],1)

    def build_fixture(self):
        target=self.root/'infra/development/fuseki';target.parent.mkdir(parents=True)
        self.context.rename(target);self.context=target;self.mod.ROOT=self.root
        identity=self.identity();calls=[];built=[]
        def invoke(args,**kw):
            calls.append(args)
            if args[0]=='git':return subprocess.CompletedProcess(args,0,str(self.root/'.git'),'')
            if args[:2]==['docker','build']:
                built.append(args)
                return subprocess.CompletedProcess(args,0,'CANONICAL_STAGE {"stage":"checksum","durationMs":1,"outcome":"PASS","errorCategory":null}','')
            if args[:3]==['docker','image','inspect']:
                if not built:return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such image: '+identity['image'])
                value=dict(Id='sha256:'+'c'*64,Labels=self.mod.expected_labels(identity),Os='linux',Architecture='amd64')
                return subprocess.CompletedProcess(args,0,json.dumps(value),'')
            raise AssertionError('Unexpected external operation')
        return identity,calls,built,invoke

    def test_corrupt_restore_falls_back_to_one_canonical_build(self):
        identity,calls,built,invoke=self.build_fixture()
        cache=self.root/'corrupt';cache.mkdir();(cache/'image.tar').write_bytes(b'bad')
        with patch.object(self.mod,'invoke',side_effect=invoke):
            result=self.mod.build('G3-M3-001','fallback',restore_directory=cache)
        self.assertEqual(result['cacheOutcome'],'CACHE_INVALID')
        self.assertFalse(result['restored'])
        self.assertEqual(len(built),1)
        self.assertIn('--provenance=false',built[0])
        self.assertTrue(result['sourceChecksumVerified'])
        self.assertFalse(any(args[:2]==['docker','load'] for args in calls))

    def test_repeated_failure_prevents_expensive_build_in_new_invocation(self):
        identity,calls,built,invoke=self.build_fixture()
        failures=self.root/'failures'
        self.mod.save_failure_state(failures,identity,self.mod.BuildRefused('timeout',category='NETWORK_TIMEOUT'),'earlier','a'*40)
        with patch.object(self.mod,'invoke',side_effect=invoke),patch.object(self.mod.subprocess,'run',return_value=subprocess.CompletedProcess([],28,'','timeout')):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.build('G3-M3-001','blocked',failure_directory=failures)
        self.assertEqual(caught.exception.exit_code,2)
        self.assertFalse(built)
        self.assertFalse(any(args[0]=='docker' for args in calls))

    def test_final_gate_performs_build_after_prior_failure_instead_of_cached_pass(self):
        identity,calls,built,invoke=self.build_fixture()
        failures=self.root/'failures'
        self.mod.save_failure_state(failures,identity,self.mod.BuildRefused('timeout',category='NETWORK_TIMEOUT'),'earlier','a'*40)
        with patch.object(self.mod,'invoke',side_effect=invoke):
            result=self.mod.build('G3-M3-001','final',failure_directory=failures,final_gate=True)
        self.assertEqual(len(built),1)
        self.assertFalse(result['reused'])
        self.assertTrue((failures/'failure.json').is_file())

    def test_repeated_buildkit_failure_summary_does_not_duplicate_stage_duration(self):
        raw='#7 1.0 CANONICAL_STAGE {"stage":"network","durationMs":101,"outcome":"FAIL","errorCategory":"NETWORK_TIMEOUT"}'
        stages=self.mod.parse_stages(raw+'\n'+raw,'a'*64)
        self.assertEqual(len(stages),1)
        self.assertEqual(stages[0]['durationMs'],101)

    def test_mixed_source_failures_reproduce_terminal_category(self):
        responses=[subprocess.CompletedProcess([],22,'','http failure'),subprocess.CompletedProcess([],28,'','timeout')]
        with patch.object(self.mod.subprocess,'run',side_effect=responses):
            self.assertEqual(self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT'),('network','NETWORK_TIMEOUT'))

    def test_export_does_not_overwrite_nonempty_directory(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        valid=dict(Id=receipt['imageId'],Labels=self.mod.expected_labels(identity),Os='linux',Architecture='amd64')
        result=dict(imageId=receipt['imageId'],runId='run-200')
        with patch.object(self.mod,'inspect_image',return_value=valid):
            with self.assertRaises(self.mod.BuildRefused):self.mod.export_cache(directory,identity,result,head='a'*40)
        self.assertEqual((directory/'receipt.json').read_text(),json.dumps(receipt))

    def test_identity_stable_between_runs_and_tag_includes_helper_platform(self):
        first = self.identity()
        self.assertEqual(first, self.identity())
        self.assertEqual(first['image'], 'ontology-platform-fuseki:context-'+first['inputFingerprint'])
        self.assertEqual(first['cacheKey'], 'ontology-fuseki-image-v2-linux-amd64-'+first['inputFingerprint'])
        self.assertEqual(first['failureStateKey'], first['cacheKey']+'-failure-v1-'+first['envFingerprint'])
        self.assertNotEqual(first['contextSha256'], first['inputFingerprint'])
        with patch.object(self.mod, 'helper_digest', return_value='b'*64):
            self.assertNotEqual(first['cacheKey'], self.identity()['cacheKey'])
        self.assertNotEqual(first['cacheKey'], self.identity('linux/arm64')['cacheKey'])
        (self.context/'entrypoint.sh').write_text('changed\n')
        self.assertNotEqual(first['cacheKey'], self.identity()['cacheKey'])

    def test_environment_change_invalidates_failure_key_but_not_image_key(self):
        first = self.identity()
        with patch.object(self.mod, 'engine_identity', return_value={'platform':'linux/amd64','engineVersion':'30.0.0','buildxVersion':'v0.34.1'}):
            changed = self.identity()
        self.assertEqual(first['cacheKey'], changed['cacheKey'])
        self.assertNotEqual(first['failureStateKey'], changed['failureStateKey'])

    def test_valid_archive_is_checked_without_extracting_or_loading(self):
        identity = self.identity();directory, receipt = self.archive(identity)
        self.assertEqual(self.mod.validate_archive(directory, identity)['imageId'], receipt['imageId'])
        self.assertEqual(sorted(p.name for p in directory.iterdir()), ['image.tar','receipt.json'])

    def test_bad_archive_hash_is_refused_before_load(self):
        identity=self.identity();directory,_=self.archive(identity)
        with (directory/'image.tar').open('ab') as output:output.write(b'corruption')
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_unknown_receipt_fields_are_refused(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        receipt['privateEnv']='SYNTHETIC_SECRET';(directory/'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_wrong_platform_is_refused_even_with_matching_receipt(self):
        identity=self.identity();directory,_=self.archive(identity, mutate_config=lambda c:c.update(architecture='arm64'))
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_wrong_labels_are_refused_before_load(self):
        identity=self.identity();directory,_=self.archive(identity, mutate_config=lambda c:c['config']['Labels'].update({'io.ontology-platform.input-fingerprint':'f'*64}))
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_tar_traversal_link_special_and_unreferenced_members_are_refused(self):
        identity=self.identity()
        for name, kind in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('device',tarfile.CHRTYPE),('extra-tag.json',tarfile.REGTYPE)]:
            with self.subTest(name=name):
                member=tarfile.TarInfo(name);member.type=kind;member.linkname='/tmp/target'
                directory,_=self.archive(identity,extra=member)
                with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)
        self.assertFalse((self.root/'escape').exists())

    def test_receipt_and_archive_links_are_refused(self):
        identity=self.identity();directory,_=self.archive(identity)
        original=directory/'original';(directory/'receipt.json').rename(original)
        (directory/'receipt.json').symlink_to(original)
        with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_corrupt_cache_falls_back_without_loading(self):
        identity=self.identity();directory,_=self.archive(identity)
        (directory/'image.tar').write_bytes(b'broken')
        calls=[]
        with patch.object(self.mod,'invoke',side_effect=lambda args,**kw:calls.append(args)):
            result=self.mod.restore_cache(directory,identity)
        self.assertEqual(result['outcome'],'CACHE_INVALID')
        self.assertFalse(calls)

    def test_cache_miss_does_not_load(self):
        identity=self.identity()
        self.assertEqual(self.mod.restore_cache(self.root/'absent',identity)['outcome'],'MISS')

    def test_restore_checks_loaded_identity_and_records_producer(self):
        identity=self.identity();directory,receipt=self.archive(identity)
        absent=subprocess.CompletedProcess([],1,'','Error response from daemon: No such image: '+identity['image'])
        loaded={'Id':receipt['imageId'],'Os':'linux','Architecture':'amd64','Labels':{
            'org.opencontainers.image.source':self.mod.SOURCE,'io.ontology-platform.context-sha256':identity['contextSha256'],
            'io.ontology-platform.input-fingerprint':identity['inputFingerprint'],'io.ontology-platform.platform':identity['platform']}}
        results=[absent,subprocess.CompletedProcess([],0,'loaded',''),subprocess.CompletedProcess([],0,json.dumps(loaded),'')]
        with patch.object(self.mod,'invoke',side_effect=results):result=self.mod.restore_cache(directory,identity)
        self.assertEqual(result['outcome'],'HIT')
        self.assertEqual(result['producerRunId'],'producer-100')
        self.assertEqual(result['imageId'],receipt['imageId'])

    def test_existing_unknown_tag_is_not_overwritten_by_cache(self):
        identity=self.identity();directory,_=self.archive(identity)
        changed=subprocess.CompletedProcess([],0,json.dumps({'Id':'sha256:'+'b'*64,'Labels':{},'Os':'linux','Architecture':'amd64'}),'')
        with patch.object(self.mod,'invoke',return_value=changed) as invoke:
            with self.assertRaises(self.mod.BuildRefused):self.mod.restore_cache(directory,identity)
        self.assertEqual(invoke.call_count,1)

    def test_load_failure_is_hard_stop_not_cold_overwrite(self):
        identity=self.identity();directory,_=self.archive(identity)
        absent=subprocess.CompletedProcess([],1,'','Error response from daemon: No such image: '+identity['image'])
        with patch.object(self.mod,'invoke',side_effect=[absent,subprocess.CompletedProcess([],1,'','load failed')]):
            with self.assertRaises(self.mod.BuildRefused):self.mod.restore_cache(directory,identity)

    def test_missing_copy_input_has_specific_category_before_build(self):
        self.assertTrue(hasattr(self.mod, 'preflight_context'), 'COPY preflight interface is required')
        (self.context/'entrypoint.sh').unlink()
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.preflight_context(self.context)
        self.assertEqual(caught.exception.category,'COPY_INPUT_MISSING')

    def test_copy_cache_key_checksum_is_not_release_checksum_failure(self):
        diagnostic=self.mod.command_diagnostic(['docker','build'],1,0,'#2 [1/2] COPY entrypoint.sh /entry\n','#2 ERROR: failed to calculate checksum: not found')
        self.assertIn('COPY_INPUT_MISSING',diagnostic['errorCategories'])
        self.assertNotIn('CHECKSUM_MISMATCH',diagnostic['errorCategories'])

    def test_persisted_failure_short_reproduction_blocks_new_process(self):
        identity=self.identity();directory=self.root/'failures'
        diagnostic=self.mod.command_diagnostic(['docker','build'],1,1,'','TLS handshake timeout SYNTHETIC_SECRET')
        failure=self.mod.BuildRefused('build failed',diagnostic)
        self.mod.save_failure_state(directory,identity,failure,'run-100','a'*40)
        other=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(other)
        with patch.object(other,'short_reproduce',return_value=('network','NETWORK_TIMEOUT')) as probe:
            with self.assertRaises(other.BuildRefused) as caught:other.failure_gate(directory,identity,self.context)
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(probe.call_count,1)
        self.assertNotIn('SYNTHETIC_SECRET',next(directory.iterdir()).read_text())

    def test_changed_input_or_env_does_not_reuse_failure(self):
        identity=self.identity();directory=self.root/'failures'
        failure=self.mod.BuildRefused('build failed',self.mod.command_diagnostic(['docker','build'],1,1,'','connection refused'))
        self.mod.save_failure_state(directory,identity,failure,'run-100','a'*40)
        for key in ('inputFingerprint','envFingerprint'):
            changed=dict(identity);changed[key]='f'*64
            with patch.object(self.mod,'short_reproduce') as probe:self.mod.failure_gate(directory,changed,self.context)
            self.assertEqual(probe.call_count,0)

    def test_final_gate_runs_real_preflight_and_does_not_claim_cached_success(self):
        identity=self.identity();directory=self.root/'failures'
        failure=self.mod.BuildRefused('build failed',self.mod.command_diagnostic(['docker','build'],1,1,'','TLS handshake timeout'))
        self.mod.save_failure_state(directory,identity,failure,'run-100','a'*40)
        with patch.object(self.mod,'short_reproduce',return_value=('network','NETWORK_TIMEOUT')) as probe:
            result=self.mod.failure_gate(directory,identity,self.context,final_gate=True)
        self.assertIsNone(result)
        self.assertEqual(probe.call_count,0)
        self.assertTrue(list(directory.iterdir()))

    def test_short_network_probe_is_only_fixed_https_heads_and_total_bounded(self):
        self.identity();calls=[]
        def call(args,**kw):
            calls.append((args,kw));return subprocess.CompletedProcess(args,28,'','timeout')
        with patch.object(self.mod.subprocess,'run',side_effect=call):
            result=self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT')
        self.assertEqual(result,('network','NETWORK_TIMEOUT'))
        self.assertEqual(len(calls),2)
        for args,kw in calls:
            self.assertIn('--head',args);self.assertIn(args[-1],self.mod.OFFICIAL_URLS)
            self.assertLessEqual(kw['timeout'],6)
            self.assertEqual(args[args.index('--max-time')+1],'5')
            self.assertNotIn('--output',args)

    def test_cold_stage_markers_preserve_individual_durations_and_strip_raw_logs(self):
        identity=self.identity()
        raw='SYNTHETIC_SECRET\n#4 1.2 CANONICAL_STAGE {"stage":"checksum","durationMs":17,"outcome":"PASS","errorCategory":null}\n'
        self.assertEqual(self.mod.parse_stages(raw,identity['inputFingerprint']),[dict(stage='checksum',durationMs=17,outcome='PASS',errorCategory=None,inputFingerprint=identity['inputFingerprint'])])


if __name__=='__main__':unittest.main()
