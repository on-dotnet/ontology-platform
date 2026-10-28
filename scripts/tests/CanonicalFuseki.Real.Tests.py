#!/usr/bin/env python3
"""Explicit real Engine build/export/load/reuse regression; no resource deletion.

Creates only the canonical project image and dedicated ignored cache/receipts.
This local test is not evidence of two independent GitHub runners.
"""
import importlib.util
import json
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
