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
import uuid

SOURCE = 'https://github.com/on-dotnet/ontology-platform'
REPOSITORY = 'ontology-platform-fuseki'
ROOT = Path(__file__).resolve().parents[2]

class BuildRefused(Exception):
    """A build identity or Docker precondition failed; diagnostics never hold raw output."""
    def __init__(self, message, diagnostic=None):
        super().__init__(message)
        self.diagnostic = diagnostic


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
    """Persist only this entry's known argument grammar, never arbitrary env/args."""
    if arguments[:3]==['docker','image','inspect'] and re.fullmatch(REPOSITORY+r':context-[0-9a-f]{64}',arguments[-1]):
        return ['docker','image','inspect','--format','[Id/ownership Labels projection]',arguments[-1]]
    if arguments[:2]==['docker','build'] and len(arguments)==13 and arguments[2]=='--tag' and re.fullmatch(REPOSITORY+r':context-[0-9a-f]{64}',arguments[3]):
        labels=arguments[4:12]
        if all(labels[i]=='--label' for i in (0,2,4,6)) and all(re.fullmatch(r'(org.opencontainers.image.source=https://github.com/on-dotnet/ontology-platform|io.ontology-platform.context-sha256=[0-9a-f]{64}|io.ontology-platform.(task-id|run-id)=[A-Za-z0-9][A-Za-z0-9_.-]{0,99})',labels[i]) for i in (1,3,5,7)):
            return arguments[:-1]+['<repository>/infra/development/fuseki']
    if arguments[:2]==['git','-C'] and arguments[3:]==['rev-parse','--path-format=absolute','--git-common-dir']:
        return ['git','-C','<repository>']+arguments[3:]
    return [arguments[0] if arguments and arguments[0] in ('docker','git') else '[unknown executable]','[arguments withheld]']


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
    for category,pattern in (('NETWORK_TIMEOUT',r'timeout|timed out'),('PERMISSION_DENIED',r'permission denied|access denied'),
                             ('NETWORK_CONNECT',r'connection refused|no route to host|network is unreachable'),
                             ('CHECKSUM_MISMATCH',r'checksum.*(mismatch|failed)|FAILED.*checksum'),
                             ('DOWNLOAD_HTTP_FAILURE',r'curl:.*(?:error|returned)|HTTP[^\n]*(?:403|404|429|500|502|503)'),
                             ('BUILD_ERROR',r'ERROR|failed to solve')):
        if re.search(pattern,raw,re.I):categories.append(category)
    return dict(command=safe_command(arguments),exitCode=exit_code,timeoutSeconds=600,elapsedSeconds=round(elapsed,3),
                stdout=output_fingerprint(stdout),stderr=output_fingerprint(stderr),
                stageWindow=stages[-12:],errorCategories=categories or ['UNCLASSIFIED'])


def invoke(arguments):
    start=time.monotonic()
    try:
        result=subprocess.run(arguments, capture_output=True, text=True, timeout=600)
        result.safe_diagnostic=command_diagnostic(arguments,result.returncode,time.monotonic()-start,result.stdout,result.stderr)
        return result
    except subprocess.TimeoutExpired as ex:
        diagnostic=command_diagnostic(arguments,'TIMEOUT',time.monotonic()-start,ex.stdout,ex.stderr)
        raise BuildRefused('Docker unavailable or timed out; raw output suppressed',diagnostic) from None
    except OSError:
        diagnostic=command_diagnostic(arguments,'UNAVAILABLE',time.monotonic()-start)
        raise BuildRefused('Docker unavailable or timed out; raw output suppressed',diagnostic) from None


def failure_diagnostic(result, arguments):
    return getattr(result,'safe_diagnostic',None) or command_diagnostic(arguments,result.returncode,0,result.stdout,result.stderr)


def failure_receipt(directory, task_id, run_id, digest, failure, elapsed):
    """Publish one structured failure atomically; no raw output is written."""
    receipt=dict(schemaVersion=1,status='FAILED',taskId=task_id,runId=run_id,contextSha256=digest,
                 observedAt=dt.datetime.now(dt.timezone.utc).isoformat(),elapsedSeconds=round(elapsed,3),
                 reason=str(failure),ciContext={key:os.environ[key] for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT') if re.fullmatch(r'[0-9]{1,20}',os.environ.get(key,''))},failure=failure.diagnostic or dict(exitCode='PRECONDITION',errorCategories=['PRECONDITION_REFUSED']))
    path=directory/(run_id+'-'+uuid.uuid4().hex+'.failed.json')
    partial=Path(str(path)+'.partial')
    try:
        with partial.open('x',encoding='utf-8') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        partial.replace(path)
        failure.receipt=receipt
    finally:
        partial.unlink(missing_ok=True)


def ensure_image(context, task_id, run_id):
    if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value) for value in (task_id, run_id)):
        raise BuildRefused('Invalid task/run identity')
    digest = context_digest(context)
    image = REPOSITORY + ':context-' + digest
    inspect = ['docker','image','inspect','--format','{"Id":{{json .Id}},"Labels":{{json .Config.Labels}}}',image]
    result = invoke(inspect)
    reused = result.returncode == 0
    if not reused:
        # Only the exact Docker missing-image diagnostic permits a build.
        if result.returncode != 1 or result.stdout.strip() or result.stderr.strip() != 'Error response from daemon: No such image: ' + image:
            raise BuildRefused('Image inspection failed; a socket/API failure cannot trigger a build',failure_diagnostic(result,inspect))
        args = ['docker','build','--tag',image,'--label','org.opencontainers.image.source='+SOURCE,
                '--label','io.ontology-platform.context-sha256='+digest,'--label','io.ontology-platform.task-id='+task_id,
                '--label','io.ontology-platform.run-id='+run_id,str(Path(context).resolve())]
        result = invoke(args)
        if result.returncode != 0:
            raise BuildRefused('Canonical Fuseki build failed; raw output suppressed',failure_diagnostic(result,args))
        if context_digest(context) != digest:
            raise BuildRefused('Build context changed during build',failure_diagnostic(result,args))
        result = invoke(inspect)
    if result.returncode != 0:
        raise BuildRefused('Built image cannot be verified',failure_diagnostic(result,inspect))
    try:
        value = json.loads(result.stdout)
        labels = value['Labels'] or {}
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',value['Id']) or labels.get('org.opencontainers.image.source') != SOURCE or labels.get('io.ontology-platform.context-sha256') != digest:
            raise BuildRefused('Canonical tag identity or ownership changed',failure_diagnostic(result,inspect))
    except (ValueError, KeyError, TypeError) as ex:
        raise BuildRefused('Invalid image inspection schema',failure_diagnostic(result,inspect)) from None
    if context_digest(context) != digest:
        raise BuildRefused('Build context changed during image verification',failure_diagnostic(result,inspect))
    return dict(image=image,imageId=value['Id'],contextSha256=digest,reused=reused,taskId=task_id,runId=run_id)


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


def build(task_id, run_id):
    if not all(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',value) for value in (task_id,run_id)):
        raise BuildRefused('Invalid task/run identity')
    directory=ordinary_directory(ROOT, ('artifacts','fuseki-builds'))
    start=time.monotonic()
    digest,lock,fd,owned=None,None,None,False
    try:
        digest=context_digest(ROOT / 'infra/development/fuseki')
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
        result=ensure_image(ROOT / 'infra/development/fuseki',task_id,run_id)
        result['observedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
        receipt=directory/(run_id+'-'+uuid.uuid4().hex+'.json')
        with receipt.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2)
            stream.write('\n')
        return result
    except BuildRefused as ex:
        failure_receipt(directory,task_id,run_id,digest,ex,time.monotonic()-start)
        raise
    finally:
        if fd is not None:os.close(fd)
        if owned:lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id',default='DEVELOPMENT')
    parser.add_argument('--run-id',default='local-'+uuid.uuid4().hex)
    parser.add_argument('--image-only',action='store_true')
    args=parser.parse_args()
    try:
        result=build(args.task_id,args.run_id)
        print(result['image'] if args.image_only else json.dumps(result,sort_keys=True))
        return 0
    except (BuildRefused,OSError) as ex:
        if isinstance(ex,BuildRefused) and getattr(ex,'receipt',None) is not None:
            # Ephemeral CI runners must preserve this same allowlisted summary in
            # Actions logs even when ignored local receipts cannot be uploaded.
            print('CANONICAL_FAILURE_RECEIPT '+json.dumps(ex.receipt,sort_keys=True),file=sys.stderr)
        print('REFUSED: '+str(ex),file=sys.stderr)
        return 1

if __name__=='__main__': sys.exit(main())
