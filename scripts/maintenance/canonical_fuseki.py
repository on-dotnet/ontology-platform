#!/usr/bin/env python3
"""The single content-addressed Fuseki build entry for AppHost and acceptance.

A validated cache hit never calls docker build and therefore creates no history.
No mutable latest tag is produced. The local receipt records every invocation;
image labels record the first build owner. No environment/volume contents read.
"""
import argparse
import contextlib
import math
import tempfile
from collections import OrderedDict
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
BASE_IMAGE = 'eclipse-temurin:21.0.12.1_1-jre-jammy@'+BASE_DIGEST
OFFICIAL_URLS = ('https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz',
                 'https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz')
CONTEXT_FILES = frozenset(('.dockerignore','Dockerfile','entrypoint.sh','fetch-fuseki.sh','g2-config.ttl','g2-log4j2.properties'))
MAX_SOURCE_BYTES = 256 * 1024**2
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
                   ['docker','info'], ['docker','buildx','version'], ['docker','run'], ['docker','container','inspect']):
        if arguments[:len(prefix)] == prefix:
            result = prefix + ['[canonical arguments withheld]']
            if prefix == ['docker','image','inspect'] and re.fullmatch(REPOSITORY+r':context-'+HEX64, arguments[-1]):
                result.append(arguments[-1])
            return result
    if arguments and arguments[0]=='curl':return ['curl','[fixed Apache request arguments withheld]']
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
                stages.append(dict(value,inputFingerprint=fingerprint,executor='container'))
                seen.add(token)
        except (ValueError,TypeError):
            continue
    return stages


def ensure_image(context, task_id, run_id, expected=None, source_cache=None, before_cold=None):
    if not all(isinstance(value,str) and re.fullmatch(SAFE_ID,value) for value in (task_id,run_id)):
        raise BuildRefused('Invalid task/run identity')
    expected = expected or identity(context)
    preflight_context(context)
    start = time.monotonic()
    deadline=start+600
    value = inspect_image(expected)
    reused = value is not None
    stages=[]
    checksum_verified=False
    result_source=None
    probe=None
    container_checksum=False
    if not reused:
        if before_cold:probe=before_cold()
        with prepare_source(source_cache or ROOT/'artifacts/fuseki-sources',task_id,run_id,expected['inputFingerprint'],deadline) as source:
            stages.extend(source['stages'])
            validate_source_context(source['directory'])
            args=['docker','build','--provenance=false','--network=none','--platform',expected['platform'],'--progress','plain',
                  '--tag',expected['image'],'--build-context','fuseki_source='+str(source['directory'])]
            for key,wanted in dict(expected_labels(expected),**{'io.ontology-platform.task-id':task_id,'io.ontology-platform.run-id':run_id}).items():
                args.extend(['--label',key+'='+wanted])
            args.append(str(Path(context).resolve()))
            remaining=deadline-time.monotonic()
            if remaining<=0:raise BuildRefused('Canonical cold preparation budget exhausted',category='BUILD_BUDGET_EXHAUSTED')
            try:result=invoke(args,timeout=min(600,remaining))
            except BuildRefused as failure:
                failure.stages=stages+[stage_receipt('image preparation',start,'FAIL',expected['inputFingerprint'],failure.category)]
                raise
            stages.extend(parse_stages((result.stdout or '')+'\n'+(result.stderr or ''),expected['inputFingerprint']))
            if result.returncode:
                failure=BuildRefused('Canonical Fuseki build failed; raw output suppressed',failure_diagnostic(result,args))
                failure.stages=stages+[stage_receipt('image preparation',start,'FAIL',expected['inputFingerprint'],failure.category)]
                raise failure
            checksum_verified=source['verified']
            container_checksum=any(stage['stage']=='checksum' and stage['outcome']=='PASS' and stage.get('executor')=='container' for stage in stages)
            result_source=source['receipt']
            if context_digest(context)!=expected['contextSha256']:
                raise BuildRefused('Build context changed during build',category='CONTEXT_CHANGED')
            value=inspect_image(expected)
    if value is None:
        raise BuildRefused('Built image missing',category='IMAGE_IDENTITY_MISMATCH')
    if context_digest(context)!=expected['contextSha256']:
        raise BuildRefused('Build context changed during verification',category='CONTEXT_CHANGED')
    stages.append(stage_receipt('image preparation',start,'PASS',expected['inputFingerprint']))
    result=dict(expected,imageId=value['Id'],reused=reused,restored=False,taskId=task_id,runId=run_id,
                sourceChecksumVerified=checksum_verified,containerChecksumVerified=container_checksum,stages=stages)
    if result_source:result['source']=result_source
    if probe:result['failureProbe']=probe
    return result


def host_stage(stage,start,outcome,fingerprint,operation,category=None):
    return dict(stage_receipt(stage,start,outcome,fingerprint,category),executor='host',operation=operation)


def source_file_fd(directory_fd,name):
    flags=getattr(os,'O_NOFOLLOW',None)
    if flags is None:raise BuildRefused('Source nofollow support unavailable',category='SOURCE_PLATFORM_UNSUPPORTED')
    try:fd=os.open(name,os.O_RDONLY|flags|getattr(os,'O_NONBLOCK',0),dir_fd=directory_fd)
    except FileNotFoundError:return None
    except OSError:raise BuildRefused('Source cache file refused',category='SOURCE_CACHE_INVALID',stage='checksum') from None
    state=os.fstat(fd)
    if not stat.S_ISREG(state.st_mode) or state.st_nlink!=1 or not 0<state.st_size<=MAX_SOURCE_BYTES:
        os.close(fd)
        raise BuildRefused('Source cache type/size refused',category='SOURCE_CACHE_INVALID',stage='checksum')
    return fd


def source_digest_fd(fd,destination=None):
    before=os.fstat(fd)
    os.lseek(fd,0,os.SEEK_SET)
    digest=hashlib.sha512();size=0
    while chunk:=os.read(fd,1024*1024):
        size+=len(chunk)
        if size>MAX_SOURCE_BYTES:raise BuildRefused('Source exceeds approved size',category='SOURCE_SIZE_INVALID',stage='checksum')
        digest.update(chunk)
        if destination is not None:
            pending=memoryview(chunk)
            while pending:
                written=os.write(destination,pending)
                if written<=0:raise OSError('source write refused')
                pending=pending[written:]
    after=os.fstat(fd)
    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise BuildRefused('Source changed during read',category='SOURCE_CONTEXT_CHANGED',stage='checksum')
    if size!=before.st_size or digest.hexdigest()!=JENA_SHA512:
        raise BuildRefused('Source SHA512 verification refused',category='CHECKSUM_MISMATCH',stage='checksum')
    return size


def host_curl(url,output,seconds,connect,deadline,head=False):
    """Manual redirects can only target the two exact approved Apache URLs."""
    if url not in OFFICIAL_URLS:raise BuildRefused('Source URL refused',category='SOURCE_URL_REFUSED',stage='network')
    window=min(deadline,time.monotonic()+seconds)
    for redirect in range(4):
        remaining=window-time.monotonic()
        if remaining<=0:raise BuildRefused('Host source request timed out',category='NETWORK_TIMEOUT',stage='network')
        limit=min(seconds,max(1,math.ceil(remaining)))
        if not head:output.seek(0);output.truncate(0)
        args=['curl','-q','--fail','--silent','--show-error','--proto','=https','--proto-redir','=https','--max-redirs','3',
              '--connect-timeout',str(min(connect,limit)),'--max-time',str(limit),'--retry','0','--max-filesize',str(MAX_SOURCE_BYTES),
              '--write-out','%{stderr}\nCANONICAL_HTTP %{http_code} %{redirect_url}\n']
        if head:args.append('--head')
        args.append(url)
        begin=time.monotonic()
        try:result=subprocess.run(args,stdout=output,stderr=subprocess.PIPE,timeout=min(limit+(1 if head else 5),deadline-time.monotonic()))
        except subprocess.TimeoutExpired as failure:
            diagnostic=command_diagnostic(args,'TIMEOUT',time.monotonic()-begin,None,failure.stderr)
            raise BuildRefused('Host source request timed out',diagnostic,category='NETWORK_TIMEOUT',stage='network') from None
        except OSError:raise BuildRefused('Host curl unavailable',category='SOURCE_TOOL_UNAVAILABLE',stage='network') from None
        result.safe_diagnostic=command_diagnostic(args,result.returncode,time.monotonic()-begin,None,result.stderr)
        result.safe_diagnostic['timeoutSeconds']=limit
        if result.returncode:return result
        raw=result.stderr.decode('utf-8',errors='replace') if isinstance(result.stderr,bytes) else (result.stderr or '')
        matches=re.findall(r'^CANONICAL_HTTP ([0-9]{3}) ([^\r\n]*)$',raw,re.MULTILINE)
        if len(matches)!=1:raise BuildRefused('Source HTTP status protocol refused',result.safe_diagnostic,category='SOURCE_PROTOCOL_INVALID',stage='network')
        status=int(matches[0][0]);target=matches[0][1]
        if 300<=status<400:
            if redirect==3 or target not in OFFICIAL_URLS:
                raise BuildRefused('Source redirect refused',result.safe_diagnostic,category='SOURCE_REDIRECT_REFUSED',stage='network')
            url=target
            continue
        if target or not (200<=status<300 if head else status==200):
            raise BuildRefused('Source HTTP response refused',result.safe_diagnostic,category='SOURCE_PROTOCOL_INVALID',stage='network')
        return result
    raise BuildRefused('Source redirect budget refused',category='SOURCE_REDIRECT_REFUSED',stage='network')


def validate_source_context(directory):
    directory=Path(directory)
    dedicated_directory(directory)
    if {path.name for path in directory.iterdir()}!={'fuseki.tar.gz'}:
        raise BuildRefused('Named source context must contain exactly one archive',category='SOURCE_CONTEXT_INVALID',stage='extract/COPY')
    parent=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fd=None
    try:
        fd=source_file_fd(parent,'fuseki.tar.gz')
        if fd is None:raise BuildRefused('Named source archive missing',category='COPY_INPUT_MISSING')
        return source_digest_fd(fd)
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)


@contextlib.contextmanager
def prepare_source(cache,task_id,run_id,fingerprint,deadline=None):
    """Cache only verified official bytes; stage one private read-only named input."""
    if not all(isinstance(v,str) and re.fullmatch(SAFE_ID,v) for v in (task_id,run_id)) or not isinstance(fingerprint,str) or not re.fullmatch(HEX64,fingerprint):
        raise BuildRefused('Invalid source owner',category='SOURCE_IDENTITY_INVALID')
    deadline=deadline or time.monotonic()+600
    stages=[];parent=None;fd=None
    try:
        cache=dedicated_directory(cache)
        parent=os.open(cache,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        name=JENA_SHA512+'.tar.gz'
        started=time.monotonic()
        fd=source_file_fd(parent,name)
        downloaded=False
        outcome='HIT' if fd is not None else 'MISS'
        stages.append(host_stage('cache restore',started,outcome,fingerprint,'SOURCE_CACHE_VALIDATE'))
        if fd is None:
            with tempfile.TemporaryDirectory(prefix='source-download-',dir=cache) as temporary:
                part=Path(temporary)/'download.partial'
                opened=os.open(part,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(opened,'w+b') as stream:
                    for url in OFFICIAL_URLS:
                        started=time.monotonic()
                        try:result=host_curl(url,stream,180,15,deadline)
                        except BuildRefused as failure:
                            stages.append(host_stage('network',started,'FAIL',fingerprint,'SOURCE_DOWNLOAD',failure.category))
                            if failure.category=='NETWORK_TIMEOUT' and url!=OFFICIAL_URLS[-1]:continue
                            raise
                        category='NETWORK_TIMEOUT' if result.returncode==28 else 'DOWNLOAD_HTTP_FAILURE' if result.returncode==22 else 'NETWORK_CONNECT'
                        stages.append(host_stage('network',started,'PASS' if not result.returncode else 'FAIL',fingerprint,'SOURCE_DOWNLOAD',None if not result.returncode else category))
                        if not result.returncode:break
                        if result.returncode in (2,3,23,47,63):
                            raise BuildRefused('Source transfer limits/configuration refused',result.safe_diagnostic,
                                               category='SOURCE_SIZE_INVALID' if result.returncode==63 else 'SOURCE_TRANSFER_REFUSED',stage='network')
                        if url==OFFICIAL_URLS[-1]:raise BuildRefused('Both approved source requests failed',result.safe_diagnostic,category=category,stage='network')
                    stream.flush();os.fsync(stream.fileno())
                    started=time.monotonic()
                    try:source_digest_fd(stream.fileno())
                    except BuildRefused as failure:
                        stages.append(host_stage('checksum',started,'FAIL',fingerprint,'SOURCE_SHA512',failure.category));raise
                    stages.append(host_stage('checksum',started,'PASS',fingerprint,'SOURCE_SHA512'))
                    os.fchmod(stream.fileno(),0o400)
                try:os.link(part,name,dst_dir_fd=parent,follow_symlinks=False)
                except FileExistsError:pass
                part.unlink()
            fd=source_file_fd(parent,name)
            if fd is None:raise BuildRefused('Verified source publication missing',category='SOURCE_CACHE_INVALID')
            downloaded=True
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='fuseki-source-context-',dir=cache.parent) as temporary:
            directory=Path(temporary)
            destination=os.open(directory/'fuseki.tar.gz',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            try:size=source_digest_fd(fd,destination);os.fsync(destination)
            except BuildRefused as failure:
                stages.append(host_stage('checksum',started,'FAIL',fingerprint,'SOURCE_SHA512',failure.category));raise
            finally:os.close(destination)
            stages.append(host_stage('checksum',started,'PASS',fingerprint,'SOURCE_SHA512'))
            receipt=dict(cacheFile=str(cache/name),sha512=JENA_SHA512,sizeBytes=size,cacheOutcome=outcome,downloaded=downloaded,
                         taskId=task_id,runId=run_id,temporaryContextRemoved=False,reviewTrigger='G3-M3 stage closeout')
            source=dict(directory=directory,receipt=receipt,stages=stages,verified=True,downloaded=downloaded)
            validate_source_context(directory)
            try:
                yield source
                validate_source_context(directory)
            finally:receipt['temporaryContextRemoved']=True
    except BuildRefused as failure:
        failure.stages=getattr(failure,'stages',stages)
        raise
    except OSError:
        failure=BuildRefused('Source cache I/O refused',category='SOURCE_IO_REFUSED',stage='checksum')
        failure.stages=stages
        raise failure from None
    finally:
        if fd is not None:os.close(fd)
        if parent is not None:os.close(parent)


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
    def nonfinite(_):raise ValueError('Nonfinite JSON number')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)


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


def moby_json(value):
    """Match Go encoding/json maps and explicit structs, including HTML escaping."""
    if isinstance(value,dict):
        keys=value if isinstance(value,OrderedDict) else sorted(value)
        if any(not isinstance(key,str) for key in keys):raise ValueError()
        return b'{'+b','.join(moby_json(key)+b':'+moby_json(value[key]) for key in keys)+b'}'
    if isinstance(value,list):return b'['+b','.join(moby_json(item) for item in value)+b']'
    if value is not None and type(value) not in (str,bool,int):raise ValueError()
    if type(value) is int and not -(2**63)<=value<2**63:raise ValueError()
    return (json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)
            .replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            .replace('\u2028','\\u2028').replace('\u2029','\\u2029').encode('utf-8'))


def moby_container_config(value):
    """Recreate the approved Moby container.Config struct; unknown fields refuse."""
    value={} if value is None else value
    fields=[('Hostname','',False),('Domainname','',False),('User','',False),('AttachStdin',False,False),
            ('AttachStdout',False,False),('AttachStderr',False,False),('ExposedPorts',None,True),('Tty',False,False),
            ('OpenStdin',False,False),('StdinOnce',False,False),('Env',None,False),('Cmd',None,False),
            ('Healthcheck',None,True),('ArgsEscaped',False,True),('Image','',False),('Volumes',None,False),
            ('WorkingDir','',False),('Entrypoint',None,False),('NetworkDisabled',False,True),('MacAddress','',True),
            ('OnBuild',None,False),('Labels',None,False),('StopSignal','',True),('StopTimeout',None,True),('Shell',None,True)]
    if not isinstance(value,dict) or set(value)-{key for key,_,_ in fields}:raise ValueError()
    result=OrderedDict()
    for key,default,optional in fields:
        item=value.get(key,default)
        if isinstance(default,(str,bool)):
            item=default if item is None else item
            if type(item) is not type(default):raise ValueError()
        elif key in ('Env','Cmd','Entrypoint','OnBuild','Shell'):
            if isinstance(item,str) and key in ('Cmd','Entrypoint'):item=[item]
            if item is not None and (not isinstance(item,list) or any(not isinstance(v,str) for v in item)):raise ValueError()
        elif key in ('ExposedPorts','Volumes','Labels'):
            if item is not None:
                if not isinstance(item,dict) or any(not isinstance(k,str) for k in item):raise ValueError()
                item=dict(item)
                for name,entry in item.items():
                    if key=='Labels':
                        item[name]='' if entry is None else entry
                        if not isinstance(item[name],str):raise ValueError()
                    else:
                        if entry not in ({},None):raise ValueError()
                        item[name]={}
        elif key=='StopTimeout':
            if item is not None and (type(item) is not int or not -(2**63)<=item<2**63):raise ValueError()
        elif key=='Healthcheck' and item is not None:
            order=('Test','Interval','Timeout','StartPeriod','StartInterval','Retries')
            if not isinstance(item,dict) or set(item)-set(order):raise ValueError()
            health=OrderedDict()
            for field in order:
                entry=item.get(field)
                if entry is None:continue
                if field=='Test':
                    if not isinstance(entry,list) or any(not isinstance(v,str) for v in entry):raise ValueError()
                elif type(entry) is not int or not 0<=entry<2**63:raise ValueError()
                if entry:health[field]=entry
            item=health
        if optional and (item is None or (key not in ('StopTimeout','Healthcheck') and not item)):continue
        result[key]=item
    return result


def moby_created(value):
    """Normalize Go RFC3339Nano precision without dropping nanoseconds."""
    if value is None:return None
    if not isinstance(value,str):raise ValueError()
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})',value)
    if not match:raise ValueError()
    dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    fraction=(match[2] or '').rstrip('0')
    zone='Z' if match[3] in ('Z','+00:00','-00:00') else match[3]
    return match[1]+('.'+fraction if fraction else '')+zone


def moby_legacy_metadata(config):
    """Derive each official V1 identity/blob from the exact rootfs prefix and image."""
    diffs=config['rootfs']['diff_ids']
    if not 1<=len(diffs)<=125:raise ValueError()
    chain=''
    parent=''
    for index,diff in enumerate(diffs):
        chain=diff if not chain else 'sha256:'+hashlib.sha256((chain+' '+diff).encode()).hexdigest()
        final=index==len(diffs)-1
        source=config if final else {'created':'1970-01-01T00:00:00Z'}
        base=OrderedDict()
        for field in ('comment','created','container','container_config','docker_version','author','config','architecture','variant','os','Size'):
            item=source.get(field)
            if field=='created':base[field]=moby_created(item)
            elif field=='container_config':base[field]=moby_container_config(item)
            elif field=='config':
                if item is not None:base[field]=moby_container_config(item)
            elif field=='Size':
                if item is not None and (type(item) is not int or item<0):raise ValueError()
                if item:base[field]=item
            else:
                if item is not None and not isinstance(item,str):raise ValueError()
                if item:base[field]=item
        identity=dict(base,layer_id=chain)
        if parent:identity['parent']='sha256:'+parent
        identifier=hashlib.sha256(moby_json(identity)).hexdigest()
        stored=OrderedDict(id=identifier)
        if parent:stored['parent']=parent
        stored.update(base)
        # Moby assigns OS after CreateID; intermediate IDs deliberately omit OS.
        stored['os']=config['os']
        raw=moby_json(stored)
        if len(raw)>1024**2:raise ValueError()
        yield 'blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw
        parent=identifier


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
            if (not isinstance(manifest,list) or len(manifest)!=1 or not isinstance(manifest[0],dict) or
                not {'Config','RepoTags','Layers'} <= set(manifest[0]) <= {'Config','RepoTags','Layers','LayerSources'}):
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
            if 'LayerSources' in record:
                check='LAYER_SOURCES_SCHEMA'
                sources=record['LayerSources']
                if not isinstance(sources,dict):raise ValueError()
                shape['layerSourcesCount']=len(sources)
                shape['layerSourceDigestKeyCount']=sum(isinstance(key,str) and bool(re.fullmatch(r'sha256:'+HEX64,key)) for key in sources)
                known_fields={'mediaType','digest','size','annotations','platform','urls','data','artifactType'}
                shape['layerSourceKnownFields']=sorted({key for descriptor in sources.values() if isinstance(descriptor,dict) for key in descriptor if key in known_fields})
                shape['layerSourceUnknownFieldCount']=sum(len(set(descriptor)-known_fields) for descriptor in sources.values() if isinstance(descriptor,dict))
                check='LAYER_SOURCES_BINDING'
                diff_ids=config['rootfs']['diff_ids']
                if (config['rootfs']['type']!='layers' or not isinstance(diff_ids,list) or len(diff_ids)!=len(record['Layers']) or
                    any(not isinstance(key,str) or not re.fullmatch(r'sha256:'+HEX64,key) for key in diff_ids) or
                    len(set(diff_ids))!=len(diff_ids) or set(sources)!=set(diff_ids)):
                    raise ValueError()
                for layer,diff_id in zip(record['Layers'],diff_ids):
                    check='LAYER_SOURCES_SCHEMA'
                    descriptor=sources[diff_id]
                    if (not isinstance(descriptor,dict) or not {'mediaType','digest','size'} <= set(descriptor) <= {'mediaType','digest','size','annotations','platform'} or
                        descriptor['mediaType']!='application/vnd.oci.image.layer.v1.tar' or descriptor['digest']!=diff_id or
                        type(descriptor['size']) is not int or not 0 < descriptor['size'] <= MAX_ARCHIVE_BYTES):
                        raise ValueError()
                    check='LAYER_SOURCES_METADATA'
                    if ('annotations' in descriptor and descriptor['annotations']!={}) or ('annotations' in descriptor and not isinstance(descriptor['annotations'],dict)):
                        raise ValueError()
                    if 'platform' in descriptor:
                        platform=descriptor['platform']
                        if (not isinstance(platform,dict) or not {'os','architecture'} <= set(platform) <= {'os','architecture','variant'} or
                            normalized_platform(platform['os'],platform['architecture'])!=expected['platform'] or
                            ('variant' in platform and not (expected['platform']=='linux/arm64' and platform['variant']=='v8'))):
                            raise ValueError()
                    check='LAYER_SOURCES_BINDING'
                    if layer.startswith('blobs/') and layer!='blobs/sha256/'+diff_id[7:]:raise ValueError()
                    check='LAYER_SOURCES_CONTENT'
                    if members[layer].size!=descriptor['size']:raise ValueError()
                    digest=hashlib.sha256()
                    with archive.extractfile(members[layer]) as stream:
                        while chunk:=stream.read(1024*1024):digest.update(chunk)
                    if digest.hexdigest()!=diff_id[7:]:raise ValueError()
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
                    permitted={'io.containerd.image.name':'docker.io/library/'+expected['image'],
                               'org.opencontainers.image.ref.name':expected['image'].split(':',1)[1]}
                    # BuildKit's manifest descriptor annotation binds the config, not the root manifest ID.
                    if descriptor['mediaType'] in manifest_types:permitted['config.digest']=config_id
                    if not isinstance(annotations,dict) or set(annotations)-set(permitted):raise ValueError()
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
            unreferenced=[name for name,member in members.items() if member.isfile() and name not in allowed]
            shape['unreferencedFileCount']=len(unreferenced)
            shape['unreferencedSha256BlobCount']=sum(bool(re.fullmatch(r'blobs/sha256/'+HEX64,name)) for name in unreferenced)
            if unreferenced:
                # Only the complete deterministic Moby V1 set may authorize extras.
                if shape['format']!='OCI' or 'LayerSources' not in record or len(unreferenced)!=len(config['rootfs']['diff_ids']):raise ValueError()
                for name in unreferenced:
                    if not re.fullmatch(r'blobs/sha256/'+HEX64,name):raise ValueError()
                    item=strict_json(read(name))
                    if not isinstance(item,dict) or not {'id','created','container_config','os'} <= set(item):raise ValueError()
                shape['legacyMetadataCandidateCount']=len(unreferenced)
                check='V1_METADATA_DERIVATION'
                generated=list(moby_legacy_metadata(config))
                check='V1_METADATA_MEMBERS'
                if {name for name,_ in generated}!=set(unreferenced):raise ValueError()
                check='V1_METADATA_CONTENT'
                for name,raw in generated:
                    actual=read(name)
                    if actual!=raw or hashlib.sha256(actual).hexdigest()!=name.rsplit('/',1)[1]:raise ValueError()
                    allowed.add(name)
                shape['verifiedLegacyMetadataCount']=len(generated)
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


PROBE_SCRIPT = """for url in "$@"; do
    curl --head --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-redirs 3 --connect-timeout 5 --max-time 5 --retry 0 "$url" >/dev/null 2>/dev/null
    code=$?
    printf 'CANONICAL_PROBE_EXIT %s\\n' "$code"
    if [ "$code" -eq 0 ]; then exit 0; fi
done
exit 1
"""


def container_network_probe(task_id, run_id, platform=None):
    """Probe fixed origins in the already-local pinned base; never pull/build/delete."""
    started=time.monotonic()
    # Reserve one second for Python/process teardown within the public 20s bound.
    deadline=started+19
    run_id=run_id or 'probe-'+uuid.uuid4().hex
    if not all(isinstance(value,str) and re.fullmatch(SAFE_ID,value) for value in (task_id,run_id)):
        raise BuildRefused('Invalid probe owner',category='PROBE_IDENTITY_INVALID',exit_code=2)
    name='ontology-fuseki-probe-'+uuid.uuid4().hex
    receipt=dict(schemaVersion=1,scope='container',taskId=task_id,runId=run_id,containerName=name,
                 baseImage=BASE_IMAGE,platform=platform,runAttempted=False,autoRemoveRequested=True,
                 autoRemoval='NOT_RUN',sourceExitCodes=[],budgetSeconds=20,outcome='BLOCKED')

    def command(args, cap, reserve=0):
        timeout=min(cap,deadline-time.monotonic()-reserve)
        if timeout<=0:
            raise BuildRefused('Container probe deadline exhausted',category='PROBE_DOCKER_TIMEOUT',exit_code=2)
        begin=time.monotonic()
        try:
            result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
            result.safe_diagnostic=command_diagnostic(args,result.returncode,time.monotonic()-begin,result.stdout,result.stderr)
            result.safe_diagnostic['timeoutSeconds']=round(timeout,3)
            return result
        except subprocess.TimeoutExpired as failure:
            diagnostic=command_diagnostic(args,'TIMEOUT',time.monotonic()-begin,failure.stdout,failure.stderr)
            diagnostic['timeoutSeconds']=round(timeout,3)
            raise BuildRefused('Container probe Docker command timed out',diagnostic,category='PROBE_DOCKER_TIMEOUT',exit_code=2) from None
        except OSError:
            raise BuildRefused('Container probe Docker command unavailable',category='PROBE_DOCKER_UNAVAILABLE',exit_code=2) from None

    try:
        args=['docker','image','inspect','--format','{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"Os":{{json .Os}},"Architecture":{{json .Architecture}}}',BASE_IMAGE]
        base=command(args,3)
        if base.returncode:
            raise BuildRefused('Pinned probe base is not locally available',failure_diagnostic(base,args),category='PROBE_BASE_UNAVAILABLE',exit_code=2)
        try:
            image=strict_json(base.stdout)
            actual=normalized_platform(image['Os'],image['Architecture'])
            if (not re.fullmatch(r'sha256:'+HEX64,image['Id']) or not isinstance(image['RepoDigests'],list) or
                not any(value in ('eclipse-temurin@'+BASE_DIGEST,'docker.io/library/eclipse-temurin@'+BASE_DIGEST) for value in image['RepoDigests'])):
                raise ValueError()
        except (ValueError,TypeError,KeyError,BuildRefused):
            raise BuildRefused('Pinned probe base identity unavailable',failure_diagnostic(base,args),category='PROBE_BASE_IDENTITY_INVALID',exit_code=2) from None
        if platform is not None and platform!=actual:
            raise BuildRefused('Pinned probe base platform unavailable',category='PROBE_BASE_PLATFORM_MISMATCH',exit_code=2)
        platform=platform or actual
        receipt['platform']=platform
        receipt['baseImageId']=image['Id']
        args=['docker','run','--rm','--pull=never','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
              '--network=bridge','--name',name,'--platform',platform,
              '--label','io.ontology-platform.project=ontology-platform',
              '--label','io.ontology-platform.task-id='+task_id,'--label','io.ontology-platform.run-id='+run_id,
              '--entrypoint','/bin/sh',BASE_IMAGE,'-c',PROBE_SCRIPT,'canonical-probe',*OFFICIAL_URLS]
        receipt['runAttempted']=True
        pending=None
        try:
            result=command(args,14,reserve=3)
        except BuildRefused as failure:
            pending=failure
        # --rm is requested, but only an exact no-such-container result proves removal.
        inspect=['docker','container','inspect','--format','{{json .Id}}',name]
        try:
            removed=command(inspect,3)
            absent=removed.returncode==1 and not removed.stdout.strip() and removed.stderr.strip() in (
                'Error: No such container: '+name,'Error response from daemon: No such container: '+name)
            receipt['autoRemoval']='VERIFIED_REMOVED' if absent else 'CONTAINER_REMAINS' if removed.returncode==0 else 'NOT_VERIFIED'
        except BuildRefused as failure:
            receipt['autoRemoval']='NOT_VERIFIED'
            pending=pending or failure
        if pending:raise pending
        if receipt['autoRemoval']!='VERIFIED_REMOVED':
            raise BuildRefused('Probe auto-removal could not be verified; retain exact resource identity',category='PROBE_CLEANUP_UNVERIFIED',exit_code=2)
        if result.returncode not in (0,1):
            raise BuildRefused('Container probe Docker run failed',failure_diagnostic(result,args),category='PROBE_DOCKER_FAILURE',exit_code=2)
        lines=result.stdout.splitlines()
        if not 1<=len(lines)<=2 or any(not re.fullmatch(r'CANONICAL_PROBE_EXIT [0-9]{1,3}',line) for line in lines):
            raise BuildRefused('Container probe result schema refused',failure_diagnostic(result,args),category='PROBE_PROTOCOL_INVALID',exit_code=2)
        codes=[int(line.split(' ')[1]) for line in lines]
        if (any(code not in (0,5,6,7,22,28,35,47,52,55,56,60,77,92) for code in codes) or
            (result.returncode==0 and (codes[-1]!=0 or 0 in codes[:-1])) or
            (result.returncode==1 and (len(codes)!=2 or 0 in codes))):
            raise BuildRefused('Container probe source results refused',failure_diagnostic(result,args),category='PROBE_PROTOCOL_INVALID',exit_code=2)
        receipt['sourceExitCodes']=codes
        receipt['outcome']='RECOVERED' if result.returncode==0 else 'REPRODUCED'
        receipt['errorCategory']=None if result.returncode==0 else 'NETWORK_TIMEOUT' if codes[-1]==28 else 'DOWNLOAD_HTTP_FAILURE' if codes[-1]==22 else 'NETWORK_CONNECT'
        receipt['durationMs']=round((time.monotonic()-started)*1000)
        return receipt
    except BuildRefused as failure:
        receipt.update(durationMs=round((time.monotonic()-started)*1000),errorCategory=failure.category)
        failure.diagnostic=dict(failure.diagnostic or {},probe=receipt)
        raise


def host_network_probe(task_id,run_id):
    """Match the current source executor with fixed-origin HEADs; never download."""
    started=time.monotonic();deadline=started+19
    receipt=dict(schemaVersion=1,scope='host',taskId=task_id,runId=run_id,budgetSeconds=20,sourceExitCodes=[],outcome='BLOCKED')
    try:
        with open(os.devnull,'wb') as output:
            for url in OFFICIAL_URLS:
                try:result=host_curl(url,output,5,5,deadline,head=True)
                except BuildRefused as failure:
                    if failure.category!='NETWORK_TIMEOUT':raise
                    receipt['sourceExitCodes'].append(28)
                    continue
                receipt['sourceExitCodes'].append(result.returncode)
                if result.returncode==0:
                    receipt.update(outcome='RECOVERED',errorCategory=None,durationMs=round((time.monotonic()-started)*1000));return receipt
                if result.returncode in (2,3,23,47,63):raise BuildRefused('Host source probe unavailable',result.safe_diagnostic,category='SOURCE_PROBE_UNAVAILABLE',exit_code=2)
        if len(receipt['sourceExitCodes'])!=2:raise BuildRefused('Host probe incomplete',category='SOURCE_PROBE_UNAVAILABLE',exit_code=2)
        code=receipt['sourceExitCodes'][-1]
        receipt.update(outcome='REPRODUCED',errorCategory='NETWORK_TIMEOUT' if code==28 else 'DOWNLOAD_HTTP_FAILURE' if code==22 else 'NETWORK_CONNECT',
                       durationMs=round((time.monotonic()-started)*1000))
        return receipt
    except BuildRefused as failure:
        failure.exit_code=2
        receipt.update(errorCategory=failure.category,durationMs=round((time.monotonic()-started)*1000))
        failure.diagnostic=dict(failure.diagnostic or {},probe=receipt)
        raise


def short_reproduce(context, stage, category, task_id='DEVELOPMENT', run_id=None, platform=None, probe_receipts=None, executor='host', source_cache=None):
    """Recheck current host source failures cheaply; preserve explicit legacy container probes."""
    try:
        preflight_context(context)
    except BuildRefused as failure:
        return failure.stage,failure.category
    if stage=='checksum' and source_cache is not None:
        started=time.monotonic();parent=None;fd=None
        receipt=dict(schemaVersion=1,scope='host',taskId=task_id,runId=run_id,operation='SOURCE_CACHE_VALIDATE',outcome='NOT_REPRODUCED',budgetSeconds=20)
        observed=None
        try:
            cache=Path(source_cache)
            if cache.is_symlink():raise BuildRefused('Source cache link refused',category='SOURCE_CACHE_INVALID',stage='checksum')
            if cache.is_dir():
                for path in (cache,*cache.parents):
                    if path.is_symlink():raise BuildRefused('Source cache ancestor refused',category='SOURCE_CACHE_INVALID',stage='checksum')
                parent=os.open(cache,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                fd=source_file_fd(parent,JENA_SHA512+'.tar.gz')
                if fd is not None:
                    source_digest_fd(fd)
                    receipt['outcome']='RECOVERED'
        except BuildRefused as failure:
            observed=(failure.stage,failure.category)
            receipt.update(outcome='REPRODUCED',errorCategory=failure.category)
        except OSError:
            raise BuildRefused('Source checksum probe unavailable',category='SOURCE_PROBE_UNAVAILABLE',exit_code=2) from None
        finally:
            if fd is not None:os.close(fd)
            if parent is not None:os.close(parent)
        receipt['durationMs']=round((time.monotonic()-started)*1000)
        if receipt['durationMs']>19000:raise BuildRefused('Source checksum probe budget exhausted',category='SOURCE_PROBE_UNAVAILABLE',exit_code=2)
        if probe_receipts is not None:probe_receipts.append(receipt)
        return observed
    if stage!='network':
        return None
    receipt=container_network_probe(task_id,run_id,platform) if executor=='container' else host_network_probe(task_id,run_id)
    if probe_receipts is not None:probe_receipts.append(receipt)
    if receipt['outcome']=='REPRODUCED':return 'network',receipt['errorCategory']
    return None


def failure_gate(directory, expected, context, final_gate=False, task_id='DEVELOPMENT', run_id=None, source_cache=None):
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
    probes=[]
    if short_reproduce(context,state['stage'],state['category'],task_id,run_id,expected['platform'],probes,source_cache=source_cache)==(state['stage'],state['category']):
        diagnostic={'probe':probes[-1]} if probes else None
        raise BuildRefused('Repeated failure confirmed within short budget; expensive build blocked',diagnostic,category=state['category'],stage=state['stage'],exit_code=2)
    return probes[-1] if probes else None


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
        def before_cold():return failure_gate(failure_directory,expected,context,final_gate,task_id,run_id,source_cache=shared.parent/'fuseki-sources')
        result=ensure_image(context,task_id,run_id,expected,source_cache=shared.parent/'fuseki-sources',
                            before_cold=before_cold if restored['outcome']!='HIT' and failure_directory else None)
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
