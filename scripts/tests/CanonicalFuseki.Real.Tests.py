#!/usr/bin/env python3
"""Explicit real Docker reuse regression. Creates only the canonical project image.

No mock, prune or old-resource deletion. The image is retained for AppHost and
acceptance; receipts remain under ignored artifacts/fuseki-builds with task/run.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('canonical',ROOT/'scripts/maintenance/canonical_fuseki.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def state():
    result={}
    for key,args in [('images',['image','ls','--all','--quiet','--no-trunc']),('history',['buildx','history','ls','--builder','desktop-linux','--format','{{.Ref}}'])]:
        value=subprocess.run(['docker']+args,capture_output=True,text=True)
        if value.returncode: raise RuntimeError('Real Docker '+key+' unavailable; NOT_RUN')
        result[key]=sorted(set(value.stdout.splitlines()))
    return result

before=state()
first=m.build('G3-M1-CLOSEOUT-002','real-reuse-1')
after_first=state()
second=m.build('G3-M1-CLOSEOUT-002','real-reuse-2')
after_second=state()
assert second['reused'] and first['imageId']==second['imageId']
assert after_first==after_second, 'Repeated unchanged source must not add image IDs or build history'
print(json.dumps(dict(status='PASS',checks=2,before=before,afterFirst=after_first,afterSecond=after_second,first=first,second=second,physicalReclaimedBytes='NOT_VERIFIED'),indent=2))
