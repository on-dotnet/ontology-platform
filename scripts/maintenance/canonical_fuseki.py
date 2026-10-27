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
    """A build identity or Docker precondition failed."""


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


def invoke(arguments):
    try:
        return subprocess.run(arguments, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise BuildRefused('Docker unavailable or timed out; raw output suppressed') from ex


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
            raise BuildRefused('Image inspection failed; a socket/API failure cannot trigger a build')
        args = ['docker','build','--tag',image,'--label','org.opencontainers.image.source='+SOURCE,
                '--label','io.ontology-platform.context-sha256='+digest,'--label','io.ontology-platform.task-id='+task_id,
                '--label','io.ontology-platform.run-id='+run_id,str(Path(context).resolve())]
        result = invoke(args)
        if result.returncode != 0:
            raise BuildRefused('Canonical Fuseki build failed; raw output suppressed')
        if context_digest(context) != digest:
            raise BuildRefused('Build context changed during build')
        result = invoke(inspect)
    if result.returncode != 0:
        raise BuildRefused('Built image cannot be verified')
    try:
        value = json.loads(result.stdout)
        labels = value['Labels'] or {}
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',value['Id']) or labels.get('org.opencontainers.image.source') != SOURCE or labels.get('io.ontology-platform.context-sha256') != digest:
            raise BuildRefused('Canonical tag identity or ownership changed')
    except (ValueError, KeyError, TypeError) as ex:
        raise BuildRefused('Invalid image inspection schema') from ex
    if context_digest(context) != digest:
        raise BuildRefused('Build context changed during image verification')
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
    directory = ordinary_directory(ROOT, ('artifacts','fuseki-builds'))
    git = invoke(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'])
    if git.returncode != 0:
        raise BuildRefused('Shared Git identity unavailable')
    # All managed worktrees of this repository share one lock; separate trees
    # cannot race the first cache miss into duplicate Docker builds/history.
    shared = ordinary_directory(Path(git.stdout.strip()).parent, ('artifacts','fuseki-builds'))
    lock = shared / 'canonical.lock'
    # Cross-process exclusive creation serializes AppHost and CI entry calls.
    deadline = time.monotonic() + 660
    while True:
        try:
            fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise BuildRefused('Canonical build lock active or stale; inspect exact lock owner before removal')
            time.sleep(.2)
    try:
        os.write(fd,json.dumps(dict(pid=os.getpid(),taskId=task_id,runId=run_id)).encode())
        os.close(fd)
        result = ensure_image(ROOT / 'infra/development/fuseki', task_id,run_id)
        result['observedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
        receipt = directory / (run_id + '-' + uuid.uuid4().hex + '.json')
        with receipt.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2)
            stream.write('\n')
        return result
    finally:
        lock.unlink()


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
        print('REFUSED: '+str(ex),file=sys.stderr)
        return 1

if __name__=='__main__': sys.exit(main())
