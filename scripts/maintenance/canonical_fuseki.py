#!/usr/bin/env python3
"""The single content-addressed Fuseki build entry for AppHost and acceptance.

A validated cache hit never calls docker build and therefore creates no history.
No mutable latest tag is produced. The local receipt records every invocation;
image labels record the first build owner. No environment/volume contents read.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tarfile
import stat
from pathlib import PurePosixPath
import uuid

SOURCE = 'https://github.com/on-dotnet/ontology-platform'
REPOSITORY = 'ontology-platform-fuseki'
ROOT = Path(__file__).resolve().parents[2]
JENA_VERSION = '6.2.0'
JENA_SHA512 = 'ba65f5867d2d4741b2ed9e2af5a0d4fbb447909894ab2a0c6bc4dac8997f4fe339c87b13c48d45d054977769f0f8bf763ea346b1f7792d5cdc458041bd43a132'
BASE_DIGEST = 'sha256:affcab5356e1270ac35d2361ee83135af2f03e8d580eca78a6d5d6fdbf048db0'
OFFICIAL_URLS = ('https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz',
                 'https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')
CONTEXT_FILES = frozenset(('.dockerignore','Dockerfile','entrypoint.sh','fetch-fuseki.sh','g2-config.ttl','g2-log4j2.properties'))
MAX_ARCHIVE_BYTES = 2 * 1024**3
HEX64 = r'[0-9a-f]{64}'
SAFE_ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'
STAGES = ('network','checksum','extract/COPY','image preparation','cache restore','cache export')

class BuildRefused(Exception):
    """A build identity or Docker precondition failed; diagnostics never hold raw output."""
    def __init__(self, message, diagnostic=None, category=None, stage=None, exit_code=1):
        super().__init__(message)
        self.diagnostic = diagnostic
        categories = (diagnostic or {}).get('errorCategories', [])
        self.category = category or (categories[0] if categories else 'PRECONDITION_REFUSED')
        self.stage = stage or category_stage(self.category)
        self.exit_code = exit_code


def context_digest(context):
    context = Path(context)
    if context.is_symlink() or not context.is_dir():
        raise BuildRefused('Canonical context must be an ordinary directory')
    digest = hashlib.sha256()
    for path in sorted(context.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise BuildRefused('Canonical context refuses links and special files')
        if path.is_file():
            relative = path.relative_to(context).as_posix()
            # macOS Finder metadata does not form part of Docker build inputs.
            if relative == '.DS_Store':
                raise BuildRefused('Remove untracked Finder metadata from the isolated build context')
            raw = path.read_bytes()
            digest.update(relative.encode() + b'\0' + str(len(raw)).encode() + b'\0' + raw)
    return digest.hexdigest()


def output_fingerprint(value):
    raw=value if isinstance(value,bytes) else (value or '').encode('utf-8',errors='replace')
    return dict(sizeBytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def safe_command(arguments):
    """Only fixed executable/operation labels survive; no caller values are logged."""
    for prefix in (['docker','image','inspect'], ['docker','build'], ['docker','load'], ['docker','save'],
                   ['docker','info'], ['docker','buildx','version']):
        if arguments[:len(prefix)] == prefix:
            result = prefix + ['[canonical arguments withheld]']
            if prefix == ['docker','image','inspect'] and re.fullmatch(REPOSITORY+r':context-'+HEX64, arguments[-1]):
                result.append(arguments[-1])
            return result
    if arguments[:2] == ['git','-C']:
        return ['git','-C','<repository>','[identity query]']
    return [arguments[0] if arguments and arguments[0] in ('docker','git') else '[unknown executable]', '[arguments withheld]']


def command_diagnostic(arguments, exit_code, elapsed, stdout=None, stderr=None):
    """Hash all output, but retain only static BuildKit phase/error categories."""
    def text(value):return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else (value or '')
    raw=text(stdout)+'\n'+text(stderr)
    stages=[]
    phase_patterns=(('LOAD_DEFINITION',r'\bload build definition\b'),('LOAD_METADATA',r'\bload metadata\b'),
                    ('LOAD_CONTEXT',r'\bload build context\b'),('LOAD_IGNORE',r'\bload \.dockerignore\b'),
                    ('FROM',r'\bFROM\b'),('RUN',r'\bRUN\b'),('COPY',r'\bCOPY\b'),
                    ('EXPORT',r'\bexporting to image\b'),('TAG',r'\bnaming to\b'),('ERROR',r'\bERROR\b'),
                    ('CANCELED',r'\bCANCELED\b'),('CACHED',r'\bCACHED\b'),('DONE',r'\bDONE\b'))
    for line in raw.splitlines():
        number=re.match(r'^#([0-9]{1,6})\s',line)
        if not number:continue
        for phase,pattern in phase_patterns:
            if re.search(pattern,line):
                value=dict(step=int(number[1]),phase=phase)
                if not stages or stages[-1]!=value:stages.append(value)
                break
    categories=[]
    for stage in reversed(parse_stages(raw,'')):
        if stage['outcome']=='FAIL' and stage['errorCategory'] not in categories:
            categories.append(stage['errorCategory'])
    if re.search(r'COPY',raw) and re.search(r'not found|not exist|failed to calculate checksum',raw,re.I):
        categories.append('COPY_INPUT_MISSING')
    for category,pattern in (('NETWORK_TIMEOUT',r'timeout|timed out'),('PERMISSION_DENIED',r'permission denied|access denied'),
                             ('NETWORK_CONNECT',r'connection refused|no route to host|network is unreachable'),
                             ('CHECKSUM_MISMATCH',r'checksum.*(mismatch|failed)|FAILED.*checksum'),
                             ('DOWNLOAD_HTTP_FAILURE',r'curl:.*(?:error|returned)|HTTP[^\n]*(?:403|404|429|500|502|503)'),
                             ('BUILD_ERROR',r'ERROR|failed to solve')):
        if re.search(pattern,raw,re.I) and not (category=='CHECKSUM_MISMATCH' and 'COPY_INPUT_MISSING' in categories):categories.append(category)
    return dict(command=safe_command(arguments),exitCode=exit_code,timeoutSeconds=600,elapsedSeconds=round(elapsed,3),
                stdout=output_fingerprint(stdout),stderr=output_fingerprint(stderr),
                stageWindow=stages[-12:],errorCategories=categories or ['UNCLASSIFIED'])


def invoke(arguments, timeout=600):
    start=time.monotonic()
    try:
        result=subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
        result.safe_diagnostic=command_diagnostic(arguments,result.returncode,time.monotonic()-start,result.stdout,result.stderr)
        return result
    except subprocess.TimeoutExpired as ex:
        diagnostic=command_diagnostic(arguments,'TIMEOUT',time.monotonic()-start,ex.stdout,ex.stderr)
        raise BuildRefused('Docker unavailable or timed out; raw output suppressed',diagnostic,category='NETWORK_TIMEOUT') from None
    except OSError:
        diagnostic=command_diagnostic(arguments,'UNAVAILABLE',time.monotonic()-start)
        raise BuildRefused('Docker unavailable or timed out; raw output suppressed',diagnostic) from None


def failure_diagnostic(result, arguments):
    return getattr(result,'safe_diagnostic',None) or command_diagnostic(arguments,result.returncode,0,result.stdout,result.stderr)


def failure_receipt(directory, task_id, run_id, digest, failure, elapsed, expected=None):
    """Publish one structured failure atomically; no raw output is written."""
    receipt=dict(schemaVersion=1,status='FAILED',taskId=task_id,runId=run_id,contextSha256=digest,
                 observedAt=dt.datetime.now(dt.timezone.utc).isoformat(),elapsedSeconds=round(elapsed,3),
                 reason=str(failure),ciContext={key:os.environ[key] for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT') if re.fullmatch(r'[0-9]{1,20}',os.environ.get(key,''))},failure=failure.diagnostic or dict(exitCode='PRECONDITION',errorCategories=['PRECONDITION_REFUSED']))
    if expected:
        receipt.update(inputFingerprint=expected['inputFingerprint'],envFingerprint=expected['envFingerprint'],
                       stages=getattr(failure,'stages',[stage_receipt(failure.stage,time.monotonic()-elapsed,'FAIL',expected['inputFingerprint'],failure.category)]))
    path=directory/(run_id+'-'+uuid.uuid4().hex+'.failed.json')
    partial=Path(str(path)+'.partial')
    try:
        with partial.open('x',encoding='utf-8') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        partial.replace(path)
        failure.receipt=receipt
    finally:
        partial.unlink(missing_ok=True)


def category_stage(category):
    if category.startswith(('NETWORK_', 'DOWNLOAD_')):
        return 'network'
    if category == 'CHECKSUM_MISMATCH':
        return 'checksum'
    if category.startswith(('COPY_', 'EXTRACT_', 'CONTEXT_')):
        return 'extract/COPY'
    return 'image preparation'


def normalized_platform(os_type, architecture):
    architecture = {'x86_64':'amd64', 'aarch64':'arm64'}.get(architecture, architecture)
    platform = str(os_type)+'/'+str(architecture)
    if platform not in ('linux/amd64','linux/arm64'):
        raise BuildRefused('Unsupported Engine platform', category='PLATFORM_MISMATCH')
    return platform


def engine_identity():
    info_args = ['docker','info','--format','{"os":{{json .OSType}},"arch":{{json .Architecture}},"version":{{json .ServerVersion}}}']
    info = invoke(info_args, timeout=15)
    version_args = ['docker','buildx','version']
    version = invoke(version_args, timeout=15)
    try:
        value = json.loads(info.stdout)
        if info.returncode or version.returncode:
            raise ValueError()
        # Keep exact Engine and Buildx versions, never runner IDs or raw config.
        engine = value['version']
        buildx = re.search(r'\bv[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][A-Za-z0-9._-]+)?',version.stdout)
        if not isinstance(engine,str) or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,80}', engine) or not buildx:
            raise ValueError()
        return dict(platform=normalized_platform(value['os'],value['arch']),engineVersion=engine,buildxVersion=buildx[0])
    except (ValueError,KeyError,TypeError):
        failed = info if info.returncode else version
        raise BuildRefused('Engine/Buildx identity unavailable',failure_diagnostic(failed, failed.args or info_args)) from None


def json_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def helper_digest():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def identity(context, platform=None):
    engine = engine_identity()
    platform = platform or engine['platform']
    if platform not in ('linux/amd64','linux/arm64'):
        raise BuildRefused('Unsupported requested platform',category='PLATFORM_MISMATCH')
    digest = context_digest(context)
    fingerprint = json_hash(dict(schemaVersion=2,contextSha256=digest,jenaVersion=JENA_VERSION,jenaSha512=JENA_SHA512,
                                 baseDigest=BASE_DIGEST,platform=platform,helperSha256=helper_digest()))
    env = json_hash(dict(schemaVersion=1,platform=platform,enginePlatform=engine['platform'],
                        engineVersion=engine['engineVersion'],buildxVersion=engine['buildxVersion']))
    key = 'ontology-fuseki-image-v2-'+platform.replace('/','-')+'-'+fingerprint
    return dict(schemaVersion=2,cacheKey=key,failureStateKey=key+'-failure-v1-'+env,envFingerprint=env,
                inputFingerprint=fingerprint,contextSha256=digest,platform=platform,image=REPOSITORY+':context-'+fingerprint)


def preflight_context(context):
    context_digest(context)
    actual = {path.name for path in Path(context).iterdir()}
    if CONTEXT_FILES - actual or any(not (Path(context)/name).is_file() for name in CONTEXT_FILES):
        raise BuildRefused('Canonical COPY input missing',category='COPY_INPUT_MISSING')
    if actual - CONTEXT_FILES:
        raise BuildRefused('Canonical context contains an unapproved input',category='CONTEXT_INPUT_INVALID')


def expected_labels(value):
    return {'org.opencontainers.image.source':SOURCE,'io.ontology-platform.context-sha256':value['contextSha256'],
            'io.ontology-platform.input-fingerprint':value['inputFingerprint'],'io.ontology-platform.platform':value['platform']}


def validate_image(value, expected, image_id=None):
    try:
        labels = value['Labels'] or {}
        if not isinstance(labels,dict):raise ValueError()
        if (not re.fullmatch(r'sha256:'+HEX64,value['Id']) or
            normalized_platform(value['Os'],value['Architecture']) != expected['platform'] or
            any(labels.get(key) != wanted for key,wanted in expected_labels(expected).items()) or
            (image_id is not None and value['Id'] != image_id)):
            raise ValueError()
        return value['Id']
    except (ValueError,KeyError,TypeError,BuildRefused):
        raise BuildRefused('Canonical image identity/platform/ownership mismatch',category='IMAGE_IDENTITY_MISMATCH') from None


def inspect_image(expected):
    args = ['docker','image','inspect','--format','{"Id":{{json .Id}},"Labels":{{json .Config.Labels}},"Os":{{json .Os}},"Architecture":{{json .Architecture}}}',expected['image']]
    result = invoke(args)
    if result.returncode == 1 and not result.stdout.strip() and result.stderr.strip() == 'Error response from daemon: No such image: '+expected['image']:
        return None
    if result.returncode:
        raise BuildRefused('Image inspection failed; refusing a build',failure_diagnostic(result,args))
    try:
        value = json.loads(result.stdout)
        try:
            validate_image(value,expected)
        except BuildRefused as failure:
            failure.diagnostic=failure_diagnostic(result,args)
            raise
        return value
    except (ValueError,KeyError,TypeError):
        raise BuildRefused('Invalid image inspection schema',failure_diagnostic(result,args)) from None


def stage_receipt(stage, start, outcome, fingerprint, category=None):
    return dict(stage=stage,durationMs=round((time.monotonic()-start)*1000),outcome=outcome,
                errorCategory=category,inputFingerprint=fingerprint)


def parse_stages(output, fingerprint):
    stages=[]
    seen=set()
    for line in (output or '').splitlines():
        marker='CANONICAL_STAGE '
        if marker not in line:
            continue
        try:
            value=json.loads(line.split(marker,1)[1])
            if (set(value) != {'stage','durationMs','outcome','errorCategory'} or value['stage'] not in STAGES or
                type(value['durationMs']) is not int or not 0 <= value['durationMs'] <= 600000 or
                value['outcome'] not in ('PASS','FAIL') or value['errorCategory'] not in (None,'NETWORK_TIMEOUT','NETWORK_CONNECT','DOWNLOAD_HTTP_FAILURE','CHECKSUM_MISMATCH','EXTRACT_FAILED')):
                continue
            token=json.dumps(value,sort_keys=True)
            if token not in seen:
                stages.append(dict(value,inputFingerprint=fingerprint))
                seen.add(token)
        except (ValueError,TypeError):
            continue
    return stages


def ensure_image(context, task_id, run_id, expected=None):
    if not all(isinstance(value,str) and re.fullmatch(SAFE_ID,value) for value in (task_id,run_id)):
        raise BuildRefused('Invalid task/run identity')
    expected = expected or identity(context)
    preflight_context(context)
    start = time.monotonic()
    value = inspect_image(expected)
    reused = value is not None
    stages=[]
    checksum_verified=False
    if not reused:
        args=['docker','build','--provenance=false','--platform',expected['platform'],'--progress','plain','--tag',expected['image']]
        for key,wanted in dict(expected_labels(expected),**{'io.ontology-platform.task-id':task_id,'io.ontology-platform.run-id':run_id}).items():
            args.extend(['--label',key+'='+wanted])
        args.append(str(Path(context).resolve()))
        result=invoke(args)
        stages.extend(parse_stages((result.stdout or '')+'\n'+(result.stderr or ''),expected['inputFingerprint']))
        if result.returncode:
            failure=BuildRefused('Canonical Fuseki build failed; raw output suppressed',failure_diagnostic(result,args))
            failure.stages=stages+[stage_receipt('image preparation',start,'FAIL',expected['inputFingerprint'],failure.category)]
            raise failure
        checksum_verified=any(stage['stage']=='checksum' and stage['outcome']=='PASS' for stage in stages)
        if context_digest(context)!=expected['contextSha256']:
            raise BuildRefused('Build context changed during build',category='CONTEXT_CHANGED')
        value=inspect_image(expected)
    if value is None:
        raise BuildRefused('Built image missing',category='IMAGE_IDENTITY_MISMATCH')
    if context_digest(context)!=expected['contextSha256']:
        raise BuildRefused('Build context changed during verification',category='CONTEXT_CHANGED')
    stages.append(stage_receipt('image preparation',start,'PASS',expected['inputFingerprint']))
    return dict(expected,imageId=value['Id'],reused=reused,restored=False,taskId=task_id,runId=run_id,
                sourceChecksumVerified=checksum_verified,stages=stages)


def regular_file(path, maximum):
    path=Path(path)
    for ancestor in (path,*path.parents):
        if ancestor.is_symlink():
            raise BuildRefused('Linked cache paths refused',category='CACHE_INVALID')
    mode=path.stat().st_mode
    if not stat.S_ISREG(mode) or not 0 < path.stat().st_size <= maximum:
        raise BuildRefused('Cache file type or size invalid',category='CACHE_INVALID')
    return path


def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_name(name):
    path=PurePosixPath(name)
    if not isinstance(name,str) or not name or any(ord(c)<32 or ord(c)==127 for c in name) or '\\' in name or path.is_absolute() or '..' in path.parts or name != path.as_posix():
        raise BuildRefused('Unsafe archive member path',category='CACHE_INVALID')
    return name


def validate_archive(directory, expected, stage='cache restore'):
    """Validate docker-save structures in place; emit only fixed refusal checks/counts."""
    check='DIRECTORY_SHAPE'
    shape=dict(format='UNKNOWN',memberCount=0,fileCount=0,directoryCount=0,linkCount=0,specialCount=0)
    try:
        directory=Path(directory)
        if directory.is_symlink() or not directory.is_dir() or {p.name for p in directory.iterdir()} != {'image.tar','receipt.json'}:
            raise ValueError()
        check='RECEIPT_SCHEMA'
        receipt=strict_json(regular_file(directory/'receipt.json',32768).read_bytes())
        fields={'schemaVersion','cacheKey','inputFingerprint','contextSha256','platform','image','imageId','archiveSha256',
                'archiveSizeBytes','producerRunId','producerHead','jenaSha512','baseDigest','sourceChecksumVerified'}
        if (set(receipt)!=fields or type(receipt['schemaVersion']) is not int or receipt['schemaVersion']!=2 or
            any(receipt[key]!=expected[key] for key in ('cacheKey','inputFingerprint','contextSha256','platform','image')) or
            receipt['jenaSha512']!=JENA_SHA512 or receipt['baseDigest']!=BASE_DIGEST or
            type(receipt['sourceChecksumVerified']) is not bool or type(receipt['archiveSizeBytes']) is not int or
            not re.fullmatch(SAFE_ID,receipt['producerRunId']) or not re.fullmatch(r'[0-9a-f]{40}',receipt['producerHead']) or
            not re.fullmatch(r'sha256:'+HEX64,receipt['imageId']) or not re.fullmatch(HEX64,receipt['archiveSha256'])):
            raise ValueError()
        check='ARCHIVE_FILE'
        path=regular_file(directory/'image.tar',MAX_ARCHIVE_BYTES)
        check='ARCHIVE_HASH'
        if path.stat().st_size!=receipt['archiveSizeBytes'] or file_hash(path)!=receipt['archiveSha256']:
            raise ValueError()
        check='TAR_STRUCTURE'
        with tarfile.open(path,'r:') as archive:
            members={}
            for member in archive:
                shape['memberCount']+=1
                shape['fileCount']+=int(member.isfile())
                shape['directoryCount']+=int(member.isdir())
                shape['linkCount']+=int(member.issym() or member.islnk())
                shape['specialCount']+=int(not (member.isfile() or member.isdir() or member.issym() or member.islnk()))
                check='TAR_MEMBER_PATHS'
                name=safe_member_name(member.name.rstrip('/') if member.isdir() else member.name)
                check='TAR_MEMBER_TYPES'
                if name in members or not (member.isfile() or member.isdir()) or member.size>MAX_ARCHIVE_BYTES or len(members)>=20000:
                    raise ValueError()
                members[name]=member
            def read(name, limit=1024*1024):
                member=members.get(safe_member_name(name))
                if member is None or not member.isfile() or member.size>limit:
                    raise ValueError()
                return archive.extractfile(member).read()
            check='MANIFEST_SCHEMA'
            manifest=strict_json(read('manifest.json'))
            if isinstance(manifest,list):
                shape['manifestRecordCount']=len(manifest)
                if len(manifest)==1 and isinstance(manifest[0],dict):
                    shape['manifestOptionalFields']=sorted(set(manifest[0]) & {'LayerSources'})
                    shape['manifestUnknownFieldCount']=len(set(manifest[0])-{'Config','RepoTags','Layers','LayerSources'})
            if not isinstance(manifest,list) or len(manifest)!=1 or set(manifest[0])!={'Config','RepoTags','Layers'}:
                raise ValueError()
            record=manifest[0]
            check='MANIFEST_TAGS_AND_LAYERS'
            if record['RepoTags']!=[expected['image']] or not isinstance(record['Layers'],list) or len(set(record['Layers']))!=len(record['Layers']):
                raise ValueError()
            check='CONFIG_IDENTITY'
            config_raw=read(record['Config'])
            config_id='sha256:'+hashlib.sha256(config_raw).hexdigest()
            config=strict_json(config_raw)
            validate_image(dict(Id=receipt['imageId'],Labels=config['config'].get('Labels'),Os=config['os'],Architecture=config['architecture']),expected)
            allowed={'manifest.json',record['Config'],*record['Layers']}
            check='LAYER_MEMBERS'
            for layer in record['Layers']:
                member=members.get(safe_member_name(layer))
                if not member or not member.isfile():
                    raise ValueError()
                parent=PurePosixPath(layer).parent.as_posix()
                if layer.endswith('/layer.tar'):
                    allowed.update({parent+'/VERSION',parent+'/json'})
            check='REPOSITORIES'
            if 'repositories' in members:
                repos=strict_json(read('repositories'))
                repository,tag=expected['image'].split(':',1)
                if set(repos)!={repository} or set(repos[repository])!={tag}:
                    raise ValueError()
                allowed.add('repositories')
            # New Engine image IDs identify the root OCI manifest, legacy IDs identify config.
            if 'index.json' in members or 'oci-layout' in members:
                shape['format']='OCI'
                check='OCI_LAYOUT'
                if strict_json(read('oci-layout'))!={'imageLayoutVersion':'1.0.0'}:
                    raise ValueError()
                check='OCI_INDEX'
                index=strict_json(read('index.json'))
                allowed.update({'index.json','oci-layout'})
                manifest_types=('application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json')
                index_types=('application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json')
                config_types=('application/vnd.oci.image.config.v1+json','application/vnd.docker.container.image.v1+json')
                layer_types=('application/vnd.oci.image.layer.v1.tar','application/vnd.oci.image.layer.v1.tar+gzip',
                             'application/vnd.oci.image.layer.v1.tar+zstd','application/vnd.docker.image.rootfs.diff.tar.gzip')
                def descriptor_blob(descriptor, kinds):
                    nonlocal check
                    check='OCI_DESCRIPTOR_SCHEMA'
                    if (not isinstance(descriptor,dict) or set(descriptor)-{'mediaType','digest','size','annotations','platform'} or
                        descriptor['mediaType'] not in kinds or not re.fullmatch(r'sha256:'+HEX64,descriptor['digest']) or
                        type(descriptor['size']) is not int or not 0 < descriptor['size'] <= MAX_ARCHIVE_BYTES):
                        raise ValueError()
                    check='OCI_DESCRIPTOR_ANNOTATIONS'
                    annotations=descriptor.get('annotations',{})
                    if not isinstance(annotations,dict) or set(annotations)-{'io.containerd.image.name','org.opencontainers.image.ref.name'}:
                        raise ValueError()
                    permitted={'io.containerd.image.name':'docker.io/library/'+expected['image'],
                               'org.opencontainers.image.ref.name':expected['image'].split(':',1)[1]}
                    if any(value!=permitted[key] for key,value in annotations.items()):raise ValueError()
                    check='OCI_DESCRIPTOR_PLATFORM'
                    if 'platform' in descriptor:
                        platform=descriptor['platform']
                        if (not isinstance(platform,dict) or set(platform)-{'os','architecture','variant'} or
                            normalized_platform(platform['os'],platform['architecture'])!=expected['platform'] or
                            ('variant' in platform and not (expected['platform']=='linux/arm64' and platform['variant']=='v8'))):
                            raise ValueError()
                    check='OCI_DESCRIPTOR_CONTENT'
                    name='blobs/sha256/'+descriptor['digest'][7:]
                    member=members.get(name)
                    if not member or not member.isfile() or member.size!=descriptor['size']:
                        raise ValueError()
                    digest=hashlib.sha256()
                    with archive.extractfile(member) as stream:
                        while chunk:=stream.read(1024*1024):digest.update(chunk)
                    if digest.hexdigest()!=descriptor['digest'][7:]:raise ValueError()
                    allowed.add(name)
                    return name
                def visit(descriptor, depth=0):
                    nonlocal check
                    check='OCI_MANIFEST_STRUCTURE'
                    if depth>4:raise ValueError()
                    name=descriptor_blob(descriptor,manifest_types+index_types)
                    check='OCI_MANIFEST_STRUCTURE'
                    item=strict_json(read(name))
                    if type(item['schemaVersion']) is not int or item['schemaVersion']!=2 or item.get('mediaType',descriptor['mediaType'])!=descriptor['mediaType']:
                        raise ValueError()
                    if descriptor['mediaType'] in index_types:
                        if not isinstance(item['manifests'],list) or len(item['manifests'])!=1:raise ValueError()
                        visit(item['manifests'][0],depth+1)
                    else:
                        config_name=descriptor_blob(item['config'],config_types)
                        check='OCI_CONFIG_BINDING'
                        if config_name!=record['Config'] or item['config']['digest']!=config_id:raise ValueError()
                        if not isinstance(item['layers'],list):raise ValueError()
                        layer_names=[descriptor_blob(layer,layer_types) for layer in item['layers']]
                        check='OCI_LAYER_BINDING'
                        if layer_names!=record['Layers']:raise ValueError()
                if (type(index['schemaVersion']) is not int or index['schemaVersion']!=2 or
                    index.get('mediaType','application/vnd.oci.image.index.v1+json') not in index_types or
                    not isinstance(index['manifests'],list) or len(index['manifests'])!=1):raise ValueError()
                check='OCI_ROOT_IDENTITY'
                root=index['manifests'][0]
                if receipt['imageId'] not in (config_id,root['digest']):raise ValueError()
                visit(root)
            else:
                shape['format']='DOCKER_LEGACY'
                check='LEGACY_CONFIG_IDENTITY'
                if config_id!=receipt['imageId']:raise ValueError()
                check='LEGACY_ROOTFS_SCHEMA'
                diff_ids=config['rootfs']['diff_ids']
                if config['rootfs']['type']!='layers' or not isinstance(diff_ids,list) or len(diff_ids)!=len(record['Layers']):raise ValueError()
                check='LEGACY_LAYER_CONTENT'
                for layer,diff_id in zip(record['Layers'],diff_ids):
                    if not isinstance(diff_id,str) or not re.fullmatch(r'sha256:'+HEX64,diff_id):raise ValueError()
                    digest=hashlib.sha256()
                    with archive.extractfile(members[layer]) as stream:
                        while chunk:=stream.read(1024*1024):digest.update(chunk)
                    if digest.hexdigest()!=diff_id[7:]:raise ValueError()
            check='UNREFERENCED_MEMBERS'
            if any(member.isfile() and name not in allowed for name,member in members.items()):
                raise ValueError()
        return receipt
    except (OSError,ValueError,KeyError,TypeError,AttributeError,tarfile.TarError,BuildRefused):
        diagnostic=dict(validationCheck=check,archiveShape=shape)
        raise BuildRefused('Cache archive validation refused',diagnostic,category='CACHE_INVALID',stage=stage) from None


def restore_cache(directory, expected):
    start=time.monotonic()
    directory=Path(directory)
    if (not directory.exists() and not directory.is_symlink()) or (directory.is_dir() and not directory.is_symlink() and not any(directory.iterdir())):
        return dict(outcome='MISS',stages=[stage_receipt('cache restore',start,'MISS',expected['inputFingerprint'])])
    try:
        receipt=validate_archive(directory,expected)
    except BuildRefused:
        return dict(outcome='CACHE_INVALID',stages=[stage_receipt('cache restore',start,'CACHE_INVALID',expected['inputFingerprint'],'CACHE_INVALID')])
    existing=inspect_image(expected)
    if existing is None:
        # After load starts, failures cannot safely fall back/overwrite a tag.
        args=['docker','load','--input',str(directory/'image.tar')]
        result=invoke(args)
        if result.returncode:
            raise BuildRefused('Docker cache load failed; inspect resources before retry',failure_diagnostic(result,args),category='CACHE_LOAD_FAILED',stage='cache restore')
        existing=inspect_image(expected)
    if existing is None:
        raise BuildRefused('Loaded cache image missing',category='CACHE_LOAD_FAILED',stage='cache restore')
    validate_image(existing,expected,receipt['imageId'])
    return dict(outcome='HIT',imageId=receipt['imageId'],producerRunId=receipt['producerRunId'],producerHead=receipt['producerHead'],
                sourceChecksumVerified=receipt['sourceChecksumVerified'],stages=[stage_receipt('cache restore',start,'PASS',expected['inputFingerprint'])])


def atomic_json(path, value):
    partial=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        with partial.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def dedicated_directory(directory):
    directory=Path(directory).absolute()
    for parent in (directory,*directory.parents):
        if parent.is_symlink():
            raise BuildRefused('Linked artifact directory refused')
    directory.mkdir(parents=True,exist_ok=True)
    if not directory.is_dir():
        raise BuildRefused('Artifact directory unavailable')
    return directory


def producer_head():
    result=invoke(['git','-C',str(ROOT),'rev-parse','HEAD'],timeout=15)
    if result.returncode or not re.fullmatch(r'[0-9a-f]{40}',result.stdout.strip()):
        raise BuildRefused('Committed producer Head unavailable')
    return result.stdout.strip()


def export_cache(directory, expected, result, head=None):
    start=time.monotonic()
    existing=inspect_image(expected)
    if existing is None:raise BuildRefused('Cannot export absent image')
    validate_image(existing,expected,result['imageId'])
    directory=dedicated_directory(directory)
    if any(directory.iterdir()):
        raise BuildRefused('Export requires an empty dedicated cache directory')
    args=['docker','save','--output',str(directory/'image.tar'),expected['image']]
    saved=invoke(args)
    if saved.returncode:
        raise BuildRefused('Docker cache export failed',failure_diagnostic(saved,args),stage='cache export')
    archive=regular_file(directory/'image.tar',MAX_ARCHIVE_BYTES)
    receipt=dict(schemaVersion=2,**{key:expected[key] for key in ('cacheKey','inputFingerprint','contextSha256','platform','image')},
                 imageId=result['imageId'],archiveSha256=file_hash(archive),archiveSizeBytes=archive.stat().st_size,
                 producerRunId=result['runId'],producerHead=head or producer_head(),jenaSha512=JENA_SHA512,baseDigest=BASE_DIGEST,
                 sourceChecksumVerified=result.get('sourceChecksumVerified',False))
    atomic_json(directory/'receipt.json',receipt)
    validate_archive(directory,expected,stage='cache export')
    return dict(outcome='EXPORTED',**receipt,stages=[stage_receipt('cache export',start,'PASS',expected['inputFingerprint'])])


FAILURE_FIELDS={'schemaVersion','inputFingerprint','envFingerprint','failureFingerprint','stage','category','producerRunId','producerHead','diagnostic','observedAtUtc'}


def save_failure_state(directory, expected, failure, run_id, head):
    directory=dedicated_directory(directory)
    diagnostic=failure.diagnostic or {}
    diagnostic={key:diagnostic.get(key,output_fingerprint(None)) for key in ('stdout','stderr')}
    state=dict(schemaVersion=1,inputFingerprint=expected['inputFingerprint'],envFingerprint=expected['envFingerprint'],
               stage=failure.stage,category=failure.category,producerRunId=run_id,producerHead=head,diagnostic=diagnostic,
               observedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    state['failureFingerprint']=json_hash({key:state[key] for key in ('inputFingerprint','envFingerprint','stage','category')})
    atomic_json(directory/'failure.json',state)


def short_reproduce(context, stage, category):
    """At most two fixed HTTPS HEAD requests (5s each); never download a package."""
    try:
        preflight_context(context)
    except BuildRefused as failure:
        return failure.stage,failure.category
    if stage!='network':
        return None
    failures=[]
    deadline=time.monotonic()+20
    for url in OFFICIAL_URLS:
        if time.monotonic()+6>deadline:break
        args=['curl','--head','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https',
              '--max-redirs','3','--connect-timeout','5','--max-time','5','--retry','0',url]
        try:
            result=subprocess.run(args,capture_output=True,text=True,timeout=6)
            if not result.returncode:return None
            failures.append('NETWORK_TIMEOUT' if result.returncode==28 else 'DOWNLOAD_HTTP_FAILURE' if result.returncode==22 else 'NETWORK_CONNECT')
        except subprocess.TimeoutExpired:
            failures.append('NETWORK_TIMEOUT')
        except OSError:
            return 'image preparation','PERMISSION_DENIED'
    if len(failures)==2:
        return 'network',failures[-1]
    return None


def failure_gate(directory, expected, context, final_gate=False):
    if final_gate:return
    path=Path(directory)/'failure.json'
    if not path.exists() and not path.is_symlink():return
    try:
        if {p.name for p in path.parent.iterdir()}!={'failure.json'}:raise ValueError()
        state=strict_json(regular_file(path,16384).read_bytes())
        if (set(state)!=FAILURE_FIELDS or type(state['schemaVersion']) is not int or state['schemaVersion']!=1 or
            any(not re.fullmatch(HEX64,state[key]) for key in ('inputFingerprint','envFingerprint','failureFingerprint')) or
            state['stage'] not in STAGES or not re.fullmatch(r'[A-Z][A-Z_]{0,60}',state['category']) or
            not re.fullmatch(SAFE_ID,state['producerRunId']) or not re.fullmatch(r'[0-9a-f]{40}',state['producerHead']) or
            set(state['diagnostic'])!={'stdout','stderr'}):raise ValueError()
        for value in state['diagnostic'].values():
            if set(value)!={'sizeBytes','sha256'} or type(value['sizeBytes']) is not int or value['sizeBytes']<0 or not re.fullmatch(HEX64,value['sha256']):raise ValueError()
        observed=dt.datetime.fromisoformat(state['observedAtUtc'])
        if observed.utcoffset()!=dt.timedelta(0):raise ValueError()
        if state['failureFingerprint']!=json_hash({key:state[key] for key in ('inputFingerprint','envFingerprint','stage','category')}):raise ValueError()
        if any(state[key]!=expected[key] for key in ('inputFingerprint','envFingerprint')):return
    except (OSError,ValueError,KeyError,TypeError,AttributeError,BuildRefused):
        raise BuildRefused('Failure-state schema refused',category='FAILURE_STATE_INVALID') from None
    if short_reproduce(context,state['stage'],state['category'])==(state['stage'],state['category']):
        raise BuildRefused('Repeated failure confirmed within short budget; expensive build blocked',category=state['category'],stage=state['stage'],exit_code=2)


def ordinary_directory(root, segments):
    path = root
    for segment in segments:
        path = path / segment
        if path.is_symlink():
            raise BuildRefused('Linked artifact directories refused')
        path.mkdir(exist_ok=True)
        if not path.is_dir():
            raise BuildRefused('Artifact directory unavailable')
    return path


def build(task_id, run_id, platform=None, restore_directory=None, export_directory=None, failure_directory=None, final_gate=False):
    if not all(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',value) for value in (task_id,run_id)):
        raise BuildRefused('Invalid task/run identity')
    directory=ordinary_directory(ROOT, ('artifacts','fuseki-builds'))
    start=time.monotonic()
    digest,lock,fd,owned=None,None,None,False
    expected=None
    if failure_directory and any(Path(failure_directory).resolve()==Path(value).resolve() for value in (restore_directory,export_directory) if value):
        raise BuildRefused('Failure state and image cache require separate directories')
    try:
        expected=identity(ROOT / 'infra/development/fuseki',platform)
        digest=expected['contextSha256']
        git=invoke(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'])
        if git.returncode!=0:
            raise BuildRefused('Shared Git identity unavailable',failure_diagnostic(git,git.args))
        # All managed worktrees share one lock, preventing duplicate first builds.
        shared=ordinary_directory(Path(git.stdout.strip()).parent, ('artifacts','fuseki-builds'))
        lock=shared/'canonical.lock'
        deadline=time.monotonic()+660
        while True:
            try:
                fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                owned=True
                break
            except FileExistsError:
                if time.monotonic()>=deadline:
                    raise BuildRefused('Canonical build lock active or stale; inspect exact lock owner before removal')
                time.sleep(.2)
        try:
            os.write(fd,json.dumps(dict(pid=os.getpid(),taskId=task_id,runId=run_id)).encode())
        finally:
            os.close(fd)
            fd=None
        context=ROOT / 'infra/development/fuseki'
        preflight_context(context)
        restored=restore_cache(restore_directory,expected) if restore_directory else dict(outcome='NOT_RUN',stages=[])
        if restored['outcome']!='HIT' and failure_directory:
            failure_gate(failure_directory,expected,context,final_gate)
        result=ensure_image(context,task_id,run_id,expected)
        result['cacheOutcome']=restored['outcome']
        result['stages']=restored['stages']+result['stages']
        result['restored']=restored['outcome']=='HIT'
        if result['restored']:
            result.update({key:restored[key] for key in ('producerRunId','producerHead','sourceChecksumVerified')})
        result['producerRunId']=result.get('producerRunId',run_id)
        result['currentGithubRunId']=os.environ.get('GITHUB_RUN_ID') if re.fullmatch(r'[0-9]{1,20}',os.environ.get('GITHUB_RUN_ID','')) else None
        result['runner']=os.environ.get('RUNNER_OS')+'-'+os.environ.get('RUNNER_ARCH') if all(re.fullmatch(r'[A-Za-z0-9_-]{1,30}',os.environ.get(key,'')) for key in ('RUNNER_OS','RUNNER_ARCH')) else 'local/UNKNOWN'
        if export_directory:
            exported=export_cache(export_directory,expected,result)
            result['exportOutcome']=exported['outcome']
            result['stages'].extend(exported['stages'])
        result['observedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
        receipt=directory/(run_id+'-'+uuid.uuid4().hex+'.json')
        with receipt.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2)
            stream.write('\n')
        return result
    except BuildRefused as ex:
        if expected and failure_directory and ex.exit_code!=2:
            save_failure_state(failure_directory,expected,ex,run_id,producer_head())
        failure_receipt(directory,task_id,run_id,digest,ex,time.monotonic()-start,expected)
        raise
    finally:
        if fd is not None:os.close(fd)
        if owned:lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id',default='DEVELOPMENT')
    parser.add_argument('--run-id',default='local-'+uuid.uuid4().hex)
    parser.add_argument('--image-only',action='store_true')
    parser.add_argument('--identity',action='store_true')
    parser.add_argument('--platform',choices=('linux/amd64','linux/arm64'))
    parser.add_argument('--restore-cache',type=Path)
    parser.add_argument('--export-cache',type=Path)
    parser.add_argument('--failure-state',type=Path)
    parser.add_argument('--final-gate',action='store_true')
    args=parser.parse_args()
    try:
        if args.identity:
            print(json.dumps(identity(ROOT/'infra/development/fuseki',args.platform),sort_keys=True))
            return 0
        result=build(args.task_id,args.run_id,args.platform,args.restore_cache,args.export_cache,args.failure_state,args.final_gate)
        print(result['image'] if args.image_only else json.dumps(result,sort_keys=True))
        return 0
    except (BuildRefused,OSError) as ex:
        if isinstance(ex,BuildRefused) and getattr(ex,'receipt',None) is not None:
            # Ephemeral CI runners must preserve this same allowlisted summary in
            # Actions logs even when ignored local receipts cannot be uploaded.
            print('CANONICAL_FAILURE_RECEIPT '+json.dumps(ex.receipt,sort_keys=True),file=sys.stderr)
        print('REFUSED: '+str(ex),file=sys.stderr)
        return getattr(ex,'exit_code',1)

if __name__=='__main__': sys.exit(main())
