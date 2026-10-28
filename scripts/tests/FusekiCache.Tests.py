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
        source_dir=self.root/'prepared';source_dir.mkdir();(source_dir/'fuseki.tar.gz').write_bytes(b'fixture')
        self.prepared=patch.object(self.mod,'prepare_source',return_value=contextlib.nullcontext(dict(directory=source_dir,receipt={},stages=[],verified=True,downloaded=False)),create=True)
        self.source_valid=patch.object(self.mod,'validate_source_context',return_value=7,create=True)
        self.prepared.start();self.source_valid.start()

    def tearDown(self):
        self.source_valid.stop();self.prepared.stop();self.engine.stop()
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

    def layer_sources_archive(self, mutation=None):
        identity=self.identity();directory,receipt=self.archive(identity)
        with tarfile.open(directory/'image.tar') as archive:
            entries=[(m.name,archive.extractfile(m).read()) for m in archive if m.isfile()]
        record=json.loads(entries[0][1])[0]
        digest='sha256:'+hashlib.sha256(b'layer').hexdigest()
        descriptor=dict(mediaType='application/vnd.oci.image.layer.v1.tar',digest=digest,size=5)
        record['LayerSources']={digest:descriptor}
        if mutation:mutation(record,entries)
        entries[0]=('manifest.json',json.dumps([record]).encode())
        self.rewrite_archive(directory,receipt,entries)
        return identity,directory,receipt

    def test_docker_save_layer_sources_is_strictly_accepted_with_verified_content(self):
        identity,directory,receipt=self.layer_sources_archive()
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_layer_sources_checked_metadata_is_bound_to_declared_platform(self):
        def metadata(record,entries):
            descriptor=next(iter(record['LayerSources'].values()))
            descriptor.update(annotations={},platform={'os':'linux','architecture':'amd64'})
        identity,directory,receipt=self.layer_sources_archive(metadata)
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_layer_sources_rejects_unbound_keys_extra_layers_and_bad_shapes(self):
        def altered_key(record,entries):
            descriptor=next(iter(record['LayerSources'].values()))
            record['LayerSources']={'sha256:'+'f'*64:descriptor}
        def extra_key(record,entries):record['LayerSources']['sha256:'+'f'*64]=next(iter(record['LayerSources'].values()))
        cases=[lambda r,e:r.update(LayerSources=None),lambda r,e:r.update(LayerSources=[]),
               lambda r,e:r.update(LayerSources={}),altered_key,extra_key]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                identity,directory,_=self.layer_sources_archive(mutate)
                with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
                self.assertTrue(caught.exception.diagnostic['validationCheck'].startswith('LAYER_SOURCES'))

    def test_layer_sources_rejects_descriptor_tampering_and_external_metadata(self):
        changes=[{'digest':'sha256:'+'f'*64},{'size':6},{'size':True},{'mediaType':'application/octet-stream'},
                 {'urls':['https://SYNTHETIC_PRIVATE_TOKEN.example/layer']},{'urls':[]},{'SYNTHETIC_PRIVATE_FIELD':'SYNTHETIC_PRIVATE_TOKEN'},
                 {'annotations':{'foreign':'SYNTHETIC_PRIVATE_TOKEN'}},{'platform':{'os':'linux','architecture':'arm64'}},
                 {'platform':{'os':'linux','architecture':'amd64','os.version':'SYNTHETIC_PRIVATE_TOKEN'}}]
        for change in changes:
            with self.subTest(change=change):
                def mutate(record,entries):next(iter(record['LayerSources'].values())).update(change)
                identity,directory,_=self.layer_sources_archive(mutate)
                with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
                self.assertTrue(caught.exception.diagnostic['validationCheck'].startswith('LAYER_SOURCES'))
                self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))

    def test_layer_sources_rehashes_member_bytes_even_if_outer_archive_hash_is_updated(self):
        def tamper(record,entries):entries[-1]=(entries[-1][0],b'other')
        identity,directory,_=self.layer_sources_archive(tamper)
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
        self.assertEqual(caught.exception.diagnostic['validationCheck'],'LAYER_SOURCES_CONTENT')

    def test_layer_sources_coexists_with_verified_oci_manifest_binding(self):
        identity,directory,receipt=self.layer_sources_archive()
        with tarfile.open(directory/'image.tar') as archive:
            record=json.load(archive.extractfile('manifest.json'))[0]
            config_raw=archive.extractfile(record['Config']).read()
        config_name='blobs/sha256/'+hashlib.sha256(config_raw).hexdigest()
        diff_id=next(iter(record['LayerSources']))
        layer_name='blobs/sha256/'+diff_id[7:]
        record.update(Config=config_name,Layers=[layer_name])
        oci={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
             'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':receipt['imageId'],'size':len(config_raw)},
             'layers':[record['LayerSources'][diff_id]]}
        oci_raw=json.dumps(oci).encode();oci_digest=hashlib.sha256(oci_raw).hexdigest()
        descriptor={'mediaType':oci['mediaType'],'digest':'sha256:'+oci_digest,'size':len(oci_raw),
                    'annotations':{'io.containerd.image.name':'docker.io/library/'+identity['image'],
                                   'org.opencontainers.image.ref.name':identity['image'].split(':',1)[1]}}
        entries=[(config_name,config_raw),(layer_name,b'layer'),('blobs/sha256/'+oci_digest,oci_raw),
                 ('manifest.json',json.dumps([record]).encode()),('index.json',json.dumps({'schemaVersion':2,'manifests':[descriptor]}).encode()),
                 ('oci-layout',b'{"imageLayoutVersion":"1.0.0"}')]
        self.rewrite_archive(directory,receipt,entries)
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_layer_sources_does_not_authorize_extra_blob_members(self):
        def extra(record,entries):entries.append(('blobs/sha256/'+'f'*64,b'{}'))
        identity,directory,_=self.layer_sources_archive(extra)
        with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
        self.assertEqual(caught.exception.diagnostic['validationCheck'],'UNREFERENCED_MEMBERS')
        self.assertEqual(caught.exception.diagnostic['archiveShape']['unreferencedFileCount'],1)
        self.assertEqual(caught.exception.diagnostic['archiveShape']['unreferencedSha256BlobCount'],1)

    def moby_v1_archive(self, mutate=None):
        identity=self.identity();directory,receipt=self.archive(identity)
        with tarfile.open(directory/'image.tar') as archive:
            record=json.load(archive.extractfile('manifest.json'))[0]
            config=json.load(archive.extractfile(record['Config']))
        layers=[b'layer-one',b'layer-two']
        diffs=['sha256:'+hashlib.sha256(raw).hexdigest() for raw in layers]
        config.update(created='2026-10-28T10:00:00Z',rootfs={'type':'layers','diff_ids':diffs})
        config_raw=json.dumps(config,sort_keys=True).encode();receipt['imageId']='sha256:'+hashlib.sha256(config_raw).hexdigest()
        zero=dict(Hostname='',Domainname='',User='',AttachStdin=False,AttachStdout=False,AttachStderr=False,
                  Tty=False,OpenStdin=False,StdinOnce=False,Env=None,Cmd=None,Image='',Volumes=None,WorkingDir='',Entrypoint=None,OnBuild=None,Labels=None)
        config_go=dict(zero,Labels=dict(sorted(config['config']['Labels'].items())))
        def encode(value):
            return json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026').encode()
        metadata=[];parent='';chain=''
        for index,diff in enumerate(diffs):
            chain=diff if not chain else 'sha256:'+hashlib.sha256((chain+' '+diff).encode()).hexdigest()
            base=dict(created='1970-01-01T00:00:00Z',container_config=zero)
            if index==len(diffs)-1:base=dict(created=config['created'],container_config=zero,config=config_go,architecture='amd64',os='linux')
            id_input=dict(base,layer_id=chain)
            if parent:id_input['parent']='sha256:'+parent
            identifier=hashlib.sha256(encode(dict(sorted(id_input.items())))).hexdigest()
            item=dict(id=identifier)
            if parent:item['parent']=parent
            item.update(base);item['os']='linux'
            raw=encode(item)
            metadata.append(('blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw))
            parent=identifier
        if mutate:mutate(metadata)
        sources={diff:dict(mediaType='application/vnd.oci.image.layer.v1.tar',digest=diff,size=len(raw)) for diff,raw in zip(diffs,layers)}
        docker=dict(Config='blobs/sha256/'+receipt['imageId'][7:],RepoTags=[identity['image']],
                    Layers=['blobs/sha256/'+diff[7:] for diff in diffs],LayerSources=sources)
        oci=dict(schemaVersion=2,mediaType='application/vnd.oci.image.manifest.v1+json',
                 config=dict(mediaType='application/vnd.oci.image.config.v1+json',digest=receipt['imageId'],size=len(config_raw)),
                 layers=list(sources.values()))
        oci_raw=json.dumps(oci).encode();oci_digest='sha256:'+hashlib.sha256(oci_raw).hexdigest()
        entries=[(docker['Config'],config_raw),*[(name,raw) for name,raw in zip(docker['Layers'],layers)],
                 ('manifest.json',json.dumps([docker]).encode()),('blobs/sha256/'+oci_digest[7:],oci_raw),
                 ('oci-layout',b'{"imageLayoutVersion":"1.0.0"}'),
                 ('index.json',json.dumps(dict(schemaVersion=2,manifests=[dict(mediaType=oci['mediaType'],digest=oci_digest,size=len(oci_raw))])).encode()),
                 ('repositories',json.dumps({'ontology-platform-fuseki':{identity['image'].split(':',1)[1]:diffs[-1][7:]}}).encode()),*metadata]
        self.rewrite_archive(directory,receipt,entries)
        return identity,directory,receipt

    def test_moby_go_struct_json_defaults_map_sorting_and_html_escaping(self):
        actual=self.mod.moby_json(self.mod.moby_container_config({'User':'10001:10001','Env':[], 'Labels':{'z':'<&>','a':'中'}}))
        expected='{"Hostname":"","Domainname":"","User":"10001:10001","AttachStdin":false,"AttachStdout":false,"AttachStderr":false,"Tty":false,"OpenStdin":false,"StdinOnce":false,"Env":[],"Cmd":null,"Image":"","Volumes":null,"WorkingDir":"","Entrypoint":null,"OnBuild":null,"Labels":{"a":"中","z":"\\u003c\\u0026\\u003e"}}'
        self.assertEqual(actual,expected.encode())
        with self.assertRaises(ValueError):self.mod.moby_container_config({'SYNTHETIC_PRIVATE_FIELD':'ignored?'})

    def test_moby_rfc3339nano_preserves_submicrosecond_identity(self):
        self.assertEqual(self.mod.moby_created('2026-10-28T10:00:00.123456780+00:00'),'2026-10-28T10:00:00.12345678Z')
        self.assertNotEqual(self.mod.moby_created('2026-10-28T10:00:00.123456781Z'),self.mod.moby_created('2026-10-28T10:00:00.123456782Z'))
        for raw in ('{"value":NaN}','{"value":Infinity}','{"value":-Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):self.mod.strict_json(raw)

    def test_official_moby_oci_layer_sources_and_exact_v1_metadata_are_accepted(self):
        identity,directory,receipt=self.moby_v1_archive()
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_v1_metadata_tampering_is_not_authorized_by_rehashing_blob_and_archive(self):
        changes=[{'id':'f'*64},{'parent':'e'*64},{'os':'windows'},{'created':'2000-01-01T00:00:00Z'},
                 {'config':{'Labels':{'foreign':'SYNTHETIC_PRIVATE_TOKEN'}}},{'SYNTHETIC_PRIVATE_FIELD':'SYNTHETIC_PRIVATE_TOKEN'}]
        for change in changes:
            with self.subTest(change=change):
                def mutate(items):
                    value=json.loads(items[-1][1]);value.update(change);raw=json.dumps(value,separators=(',',':')).encode()
                    items[-1]=('blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw)
                identity,directory,_=self.moby_v1_archive(mutate)
                with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_v1_metadata_requires_every_exact_rootfs_prefix_without_extra_blob(self):
        for change in ('missing','extra','nonfinite','wrong-bytes','unknown'):
            with self.subTest(change=change):
                def mutate(items):
                    if change=='missing':items.pop()
                    elif change=='extra':items.append(('blobs/sha256/'+'f'*64,items[-1][1]))
                    elif change=='wrong-bytes':items[-1]=(items[-1][0],items[-1][1]+b' ')
                    elif change=='nonfinite':
                        raw=items[-1][1][:-1]+b',"Size":NaN}';items[-1]=('blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw)
                    else:items.append(('blobs/sha256/'+hashlib.sha256(b'{}').hexdigest(),b'{}'))
                identity,directory,_=self.moby_v1_archive(mutate)
                with self.assertRaises(self.mod.BuildRefused):self.mod.validate_archive(directory,identity)

    def test_real_engine_oci_manifest_id_is_valid_without_config_id_confusion(self):
        identity,directory,receipt=self.oci_archive()
        self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])

    def test_buildkit_config_digest_annotation_binds_exact_config_not_manifest_id(self):
        for mode in ('valid','manifest-id','unknown'):
            with self.subTest(mode=mode):
                identity,directory,receipt=self.oci_archive()
                with tarfile.open(directory/'image.tar') as archive:
                    entries=[(m.name,archive.extractfile(m).read()) for m in archive if m.isfile()]
                by_name=dict(entries);index=json.loads(by_name['index.json'])
                config=json.loads(by_name['manifest.json'])[0]['Config']
                digest='sha256:'+hashlib.sha256(by_name[config]).hexdigest()
                index['manifests'][0]['annotations']={'config.digest':digest if mode=='valid' else receipt['imageId']}
                if mode=='unknown':index['manifests'][0]['annotations']['unknown']='SYNTHETIC_PRIVATE_TOKEN'
                entries=[(name,json.dumps(index).encode() if name=='index.json' else raw) for name,raw in entries]
                self.rewrite_archive(directory,receipt,entries)
                if mode=='valid':self.assertEqual(self.mod.validate_archive(directory,identity)['imageId'],receipt['imageId'])
                else:
                    with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.validate_archive(directory,identity)
                    self.assertEqual(caught.exception.diagnostic['validationCheck'],'OCI_DESCRIPTOR_ANNOTATIONS')
                    self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))

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
        probe_calls,probe_run=self.host_transport()
        with patch.object(self.mod,'invoke',side_effect=invoke),patch.object(self.mod.subprocess,'run',side_effect=probe_run):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.build('G3-M3-001','blocked',failure_directory=failures)
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(caught.exception.category,'NETWORK_TIMEOUT')
        self.assertEqual(caught.exception.diagnostic['probe']['taskId'],'G3-M3-001')
        self.assertEqual(caught.exception.diagnostic['probe']['runId'],'blocked')
        self.assertEqual(caught.exception.diagnostic['probe']['scope'],'host')
        self.assertFalse(built)
        self.assertFalse(any(args[:2]==['docker','build'] for args in calls))

    def test_local_image_reuse_skips_source_and_known_failure_network_probes(self):
        identity,calls,built,invoke=self.build_fixture();failures=self.root/'failures'
        self.mod.save_failure_state(failures,identity,self.mod.BuildRefused('timeout',category='NETWORK_TIMEOUT'),'earlier','a'*40)
        def warm(args,**kw):
            if args[0]=='git':return invoke(args,**kw)
            self.assertEqual(args[:3],['docker','image','inspect'])
            return subprocess.CompletedProcess(args,0,json.dumps(dict(Id='sha256:'+'c'*64,Labels=self.mod.expected_labels(identity),Os='linux',Architecture='amd64')),'')
        with (patch.object(self.mod,'invoke',side_effect=warm),patch.object(self.mod,'prepare_source',side_effect=AssertionError('warm source access')),
             patch.object(self.mod,'failure_gate',side_effect=AssertionError('warm network probe'))):
            result=self.mod.build('G3-M3-001','warm',failure_directory=failures)
        self.assertTrue(result['reused']);self.assertFalse(result['sourceChecksumVerified'])
        self.assertNotIn('source',result);self.assertFalse(built)

    def test_identity_does_not_prepare_or_probe_official_source(self):
        self.build_fixture();output=io.StringIO()
        with (patch.object(self.mod,'prepare_source',side_effect=AssertionError('identity source access')),
             patch.object(self.mod.subprocess,'run',side_effect=AssertionError('identity network access')),
             patch.object(sys,'argv',['canonical','--identity']),contextlib.redirect_stdout(output)):
            self.assertEqual(self.mod.main(),0)
        self.assertEqual(json.loads(output.getvalue())['platform'],'linux/amd64')

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

    def host_transport(self,codes=(28,28)):
        calls=[];pending=list(codes)
        def run(args,**kw):
            calls.append((args,kw))
            self.assertEqual(args[0],'curl');self.assertIn('--head',args)
            code=pending.pop(0)
            return subprocess.CompletedProcess(args,code,None,b'\nCANONICAL_HTTP 200 \n' if code==0 else b'timeout')
        return calls,run

    def probe_transport(self, codes=(28,28), base_exit=0, run_exit=None, fault=None, output=None, remains=False, architecture='amd64'):
        calls=[]
        def run(args,**kw):
            calls.append((args,kw))
            if args[:3]==['docker','image','inspect']:
                if fault=='base-timeout':raise subprocess.TimeoutExpired(args,kw['timeout'])
                if fault=='unavailable':raise OSError('SYNTHETIC_PRIVATE_PATH')
                image=dict(Id='sha256:'+'b'*64,RepoDigests=['eclipse-temurin@'+self.mod.BASE_DIGEST],Os='linux',Architecture=architecture)
                return subprocess.CompletedProcess(args,base_exit,json.dumps(image) if not base_exit else '','missing base')
            if args[:2]==['docker','run']:
                if fault=='run-timeout':raise subprocess.TimeoutExpired(args,kw['timeout'],stderr='SYNTHETIC_PRIVATE_TOKEN')
                text=output if output is not None else ''.join('CANONICAL_PROBE_EXIT '+str(code)+'\n' for code in codes)
                return subprocess.CompletedProcess(args,run_exit if run_exit is not None else (0 if codes[-1]==0 else 1),text,'SYNTHETIC_PRIVATE_TOKEN')
            if args[:3]==['docker','container','inspect']:
                return subprocess.CompletedProcess(args,0 if remains else 1,'"sha256:'+('c'*64)+'"' if remains else '',
                                                   '' if remains else 'Error: No such container: '+args[-1])
            raise AssertionError('Only local Docker probe operations are permitted: '+str(args[:3]))
        return calls,run

    def test_mixed_source_failures_reproduce_terminal_category(self):
        calls,run=self.probe_transport(codes=(22,28))
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            self.assertEqual(self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container'),('network','NETWORK_TIMEOUT'))

    def test_actual_container_shell_head_protocol_handles_success_and_two_failures(self):
        binary=self.root/'probe-bin';binary.mkdir();curl=binary/'curl';calls=self.root/'probe-calls.jsonl'
        curl.write_text('#!/bin/sh\n'+
                       '{ printf "CALL\\n"; printf "%s\\n" "$@"; } >> "$PROBE_CALLS"\n'+
                       'last=; for arg do last=$arg; done\n'+
                       'case "$last" in *dlcdn.apache.org*) exit "$PROBE_PRIMARY_EXIT";; *archive.apache.org*) exit "$PROBE_FALLBACK_EXIT";; *) exit 99;; esac\n')
        curl.chmod(0o755)
        for codes,exit_code in [([0],0),([22,0],0),([28,28],1)]:
            with self.subTest(codes=codes):
                calls.unlink(missing_ok=True)
                result=subprocess.run(['/bin/sh','-c',self.mod.PROBE_SCRIPT,'canonical-probe',*self.mod.OFFICIAL_URLS],
                                      env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],PROBE_CALLS=str(calls),PROBE_PRIMARY_EXIT=str(codes[0]),PROBE_FALLBACK_EXIT=str(codes[-1])),
                                      capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,exit_code)
                self.assertEqual(result.stdout,''.join('CANONICAL_PROBE_EXIT '+str(code)+'\n' for code in codes))
                recorded=[part.splitlines() for part in calls.read_text().split('CALL\n')[1:]]
                self.assertEqual([args[-1] for args in recorded],list(self.mod.OFFICIAL_URLS[:len(codes)]))
                self.assertTrue(all('--head' in args and args[args.index('--max-time')+1]=='5' for args in recorded))

    def test_host_recovery_receipt_is_retained_before_one_build(self):
        identity,calls,built,invoke=self.build_fixture();failures=self.root/'failures'
        self.mod.save_failure_state(failures,identity,self.mod.BuildRefused('timeout',category='NETWORK_TIMEOUT'),'earlier','a'*40)
        probe_calls,probe_run=self.host_transport(codes=(0,))
        with patch.object(self.mod,'invoke',side_effect=invoke),patch.object(self.mod.subprocess,'run',side_effect=probe_run):
            result=self.mod.build('G3-M3-001','recovered',failure_directory=failures)
        self.assertEqual(len(built),1)
        self.assertEqual(result['failureProbe']['outcome'],'RECOVERED')
        self.assertEqual(result['failureProbe']['runId'],'recovered')
        self.assertEqual(result['failureProbe']['scope'],'host')

    def test_container_network_failure_cannot_be_recovered_by_host_head(self):
        calls,run=self.probe_transport();receipts=[]
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            result=self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',task_id='G3-M3-001',run_id='container-probe',platform='linux/amd64',probe_receipts=receipts,executor='container')
        self.assertEqual(result,('network','NETWORK_TIMEOUT'))
        self.assertTrue(all(args[0]=='docker' for args,kw in calls))
        self.assertEqual(receipts[0]['scope'],'container')
        self.assertEqual(receipts[0]['autoRemoval'],'VERIFIED_REMOVED')
        self.assertEqual(receipts[0]['sourceExitCodes'],[28,28])

    def test_container_probe_hardening_labels_base_and_total_deadline(self):
        calls,run=self.probe_transport();receipts=[]
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',task_id='G3-M3-001',run_id='probe-123',platform='linux/amd64',probe_receipts=receipts,executor='container')
        args=next(args for args,kw in calls if args[:2]==['docker','run'])
        for flag in ('--rm','--pull=never','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges'):self.assertIn(flag,args)
        self.assertIn('io.ontology-platform.task-id=G3-M3-001',args)
        self.assertIn('io.ontology-platform.run-id=probe-123',args)
        self.assertEqual(args[args.index('--platform')+1],'linux/amd64')
        self.assertEqual(args[args.index('--name')+1],receipts[0]['containerName'])
        self.assertIn('eclipse-temurin:21.0.12.1_1-jre-jammy@'+self.mod.BASE_DIGEST,args)
        self.assertEqual(args[-2:],list(self.mod.OFFICIAL_URLS))
        script=args[args.index('-c')+1]
        for option in ('--head','--connect-timeout 5','--max-time 5','--retry 0','--max-redirs 3'):self.assertIn(option,script)
        self.assertNotIn('--output',script)
        self.assertLessEqual(sum(kw['timeout'] for args,kw in calls),20)
        self.assertLessEqual(receipts[0]['durationMs'],20000)

    def test_container_probe_missing_base_never_pulls_or_builds(self):
        calls,run=self.probe_transport(base_exit=1)
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(caught.exception.category,'PROBE_BASE_UNAVAILABLE')
        self.assertEqual(len(calls),1)
        self.assertFalse(caught.exception.diagnostic['probe']['runAttempted'])

    def test_container_probe_docker_fault_is_blocked_instead_of_source_recovery(self):
        calls,run=self.probe_transport(run_exit=125,output='')
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(caught.exception.category,'PROBE_DOCKER_FAILURE')
        self.assertEqual(caught.exception.diagnostic['probe']['autoRemoval'],'VERIFIED_REMOVED')
        self.assertNotIn('SYNTHETIC_PRIVATE_TOKEN',json.dumps(caught.exception.diagnostic))

    def test_container_probe_cli_timeouts_and_unavailability_are_not_recovery(self):
        for fault in ('base-timeout','run-timeout','unavailable'):
            with self.subTest(fault=fault):
                calls,run=self.probe_transport(fault=fault)
                with patch.object(self.mod.subprocess,'run',side_effect=run):
                    with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
                self.assertEqual(caught.exception.exit_code,2)
                self.assertIn(caught.exception.category,('PROBE_DOCKER_TIMEOUT','PROBE_DOCKER_UNAVAILABLE'))
                self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(caught.exception.diagnostic))

    def test_container_probe_missing_curl_or_bad_protocol_cannot_mean_recovery(self):
        for codes,exit_code,output in [((127,127),1,None),((0,),0,''),((0,),0,'CANONICAL_PROBE_EXIT 0\nSYNTHETIC_PRIVATE_TOKEN')]:
            with self.subTest(codes=codes,exit_code=exit_code,output=output):
                calls,run=self.probe_transport(codes=codes,run_exit=exit_code,output=output)
                with patch.object(self.mod.subprocess,'run',side_effect=run):
                    with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
                self.assertEqual(caught.exception.exit_code,2)
                self.assertEqual(caught.exception.category,'PROBE_PROTOCOL_INVALID')

    def test_container_probe_requires_verified_auto_removal_even_after_head_success(self):
        calls,run=self.probe_transport(codes=(0,),remains=True)
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(caught.exception.category,'PROBE_CLEANUP_UNVERIFIED')
        self.assertEqual(caught.exception.diagnostic['probe']['autoRemoval'],'CONTAINER_REMAINS')
        self.assertFalse(any(args[:2]==['docker','rm'] for args,kw in calls))

    def test_container_probe_platform_mismatch_is_not_network_recovery(self):
        calls,run=self.probe_transport(architecture='arm64')
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            with self.assertRaises(self.mod.BuildRefused) as caught:self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',platform='linux/amd64',executor='container')
        self.assertEqual(caught.exception.exit_code,2)
        self.assertEqual(caught.exception.category,'PROBE_BASE_PLATFORM_MISMATCH')
        self.assertEqual(len(calls),1)

    def test_container_probe_success_is_actual_container_head_and_auto_removal(self):
        calls,run=self.probe_transport(codes=(22,0));receipts=[]
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            result=self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',probe_receipts=receipts,executor='container')
        self.assertIsNone(result)
        self.assertEqual(receipts[0]['outcome'],'RECOVERED')
        self.assertEqual(receipts[0]['autoRemoval'],'VERIFIED_REMOVED')
        self.assertEqual(receipts[0]['sourceExitCodes'],[22,0])

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
        calls,run=self.probe_transport()
        with patch.object(self.mod.subprocess,'run',side_effect=run):
            result=self.mod.short_reproduce(self.context,'network','NETWORK_TIMEOUT',executor='container')
        self.assertEqual(result,('network','NETWORK_TIMEOUT'))
        self.assertEqual([args[:2] for args,kw in calls],[['docker','image'],['docker','run'],['docker','container']])
        self.assertLessEqual(sum(kw['timeout'] for args,kw in calls),20)

    def test_cold_stage_markers_preserve_individual_durations_and_strip_raw_logs(self):
        identity=self.identity()
        raw='SYNTHETIC_SECRET\n#4 1.2 CANONICAL_STAGE {"stage":"checksum","durationMs":17,"outcome":"PASS","errorCategory":null}\n'
        self.assertEqual(self.mod.parse_stages(raw,identity['inputFingerprint']),[dict(stage='checksum',durationMs=17,outcome='PASS',errorCategory=None,inputFingerprint=identity['inputFingerprint'],executor='container')])


if __name__=='__main__':unittest.main()
