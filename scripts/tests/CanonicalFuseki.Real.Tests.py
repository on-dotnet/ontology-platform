#!/usr/bin/env python3
"""Explicit real Engine build/export/load/reuse regression; no resource deletion.

Creates only the canonical project image and dedicated ignored cache/receipts.
This local test is not evidence of two independent GitHub runners.
"""
import importlib.util
import json
import shutil
import tempfile
import time
from pathlib import Path
import subprocess
import sys
import uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('canonical',ROOT/'scripts/maintenance/canonical_fuseki.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def state():
    result={}
    for key,args in [('images',['image','ls','--all','--quiet','--no-trunc']),('history',['buildx','history','ls','--format','{{.Ref}}'])]:
        value=subprocess.run(['docker']+args,capture_output=True,text=True,timeout=20)
        if value.returncode:raise RuntimeError('Real Docker '+key+' unavailable; NOT_RUN')
        result[key]=sorted(set(value.stdout.splitlines()))
    return result

def source_failure_stop_loss():
    """Real file/hash/state repro in isolated Git; Docker only info/absent inspect."""
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='e0-a-source-stop-',dir='/private/tmp') as temporary:
        fixture=Path(temporary);context=fixture/'infra/development/fuseki';context.mkdir(parents=True)
        for name in m.CONTEXT_FILES:shutil.copyfile(ROOT/'infra/development/fuseki'/name,context/name)
        with (context/'Dockerfile').open('a') as stream:stream.write('# Synthetic isolated stop-loss input '+uuid.uuid4().hex+'\n')
        for args in (['init','-q','-b','fixture'],['add','infra'],['-c','user.name=E0 fixture','-c','user.email=e0@example.invalid',
                     '-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Synthetic source stop-loss fixture']):
            result=subprocess.run(['git','-C',str(fixture),*args],capture_output=True,text=True,timeout=15)
            assert result.returncode==0,'Isolated Git setup failed'
        cache=fixture/'artifacts/fuseki-sources';cache.mkdir(parents=True)
        (cache/(m.JENA_SHA512+'.tar.gz')).write_bytes(b'Synthetic bad cache bytes')
        wrapper=r'''import importlib.util,json,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('canonical',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=Path(sys.argv[2]);counts={'dockerBuilds':0,'downloads':0,'sourceHashChecks':0}
original=m.subprocess.run

def execute(args,**kw):
 if args[:2]==['docker','build']:counts['dockerBuilds']+=1
 if args and args[0]=='curl':counts['downloads']+=1
 return original(args,**kw)
m.subprocess.run=execute
hash_source=m.source_digest_fd

def verify(*args,**kw):
 counts['sourceHashChecks']+=1
 return hash_source(*args,**kw)
m.source_digest_fd=verify
started=time.monotonic()
try:
 m.build('G3-M3-001',sys.argv[3],failure_directory=m.ROOT/'failure-state')
 code=0;category=None
except m.BuildRefused as failure:
 code=failure.exit_code;category=failure.category
print(json.dumps(dict(exitCode=code,category=category,counts=counts,durationMs=round((time.monotonic()-started)*1000))))
sys.exit(code)
'''
        results=[]
        for label,exit_code in [('first-real-file-fail',1),('second-real-file-blocked',2)]:
            result=subprocess.run([sys.executable,'-c',wrapper,str(ROOT/'scripts/maintenance/canonical_fuseki.py'),str(fixture),label],
                                  capture_output=True,text=True,timeout=30)
            assert result.returncode==exit_code,'Unexpected isolated failure-gate exit'
            observed=json.loads(result.stdout)
            assert observed['category']=='CHECKSUM_MISMATCH'
            assert observed['counts']==dict(dockerBuilds=0,downloads=0,sourceHashChecks=1)
            assert observed['durationMs']<20000
            results.append(observed)
        return dict(status='PASS',checks=6,scope='isolated actual source file/hash + new-process persisted state',
                    results=results,durationMs=round((time.monotonic()-started)*1000),fixtureRemovedOnExit=True)


if '--source-failure-only' in sys.argv:
    print(json.dumps(source_failure_stop_loss(),indent=2));sys.exit(0)

run='e0-a-real-'+uuid.uuid4().hex
cache=ROOT/'artifacts'/run
before=state()
first=m.build('G3-M3-001',run+'-export',export_directory=cache,final_gate=True)
expected=m.identity(ROOT/'infra/development/fuseki')
receipt=m.validate_archive(cache,expected)
assert receipt['imageId']==first['imageId']
# Actual Engine roundtrip validates modern OCI IDs without removing any tag.
loaded=m.invoke(['docker','load','--input',str(cache/'image.tar')])
if loaded.returncode:raise RuntimeError('Real Docker cache load failed')
m.validate_image(m.inspect_image(expected),expected,receipt['imageId'])
after_first=state()
second=m.build('G3-M3-001',run+'-restore',restore_directory=cache,final_gate=True)
after_second=state()
assert second['restored'] and second['reused'] and second['cacheOutcome']=='HIT'
assert first['imageId']==second['imageId']
assert after_first==after_second,'Repeated unchanged input must not add image IDs or build history'
print(json.dumps(dict(status='PASS',checks=6,before=before,afterFirst=after_first,afterSecond=after_second,
                     first=first,second=second,cacheDirectory=str(cache.relative_to(ROOT)),actualDockerLoad=True,
                     crossRunner='NOT_RUN',physicalReclaimedBytes='NOT_VERIFIED'),indent=2))
