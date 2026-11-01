"""执行已独立准入的固定G4恢复Compose阶段，保留实际命令/输入摘要/退出码。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recovery_runtime', ROOT/'scripts/acceptance/g4-m1-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
STAGES = {
    'keycloak-start': ['up', '-d', 'keycloak-test'],
    'platform-start': ['up', '-d', '--wait', '--wait-timeout', '60', 'platform-pg'],
    'api-web-start': ['up', '-d', 'api', 'web'],
    'status': ['ps', '--all', '--format', 'json'],
}
if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
    raise SystemExit('fixed stage required')
stage=sys.argv[1]
output=runtime.ARTIFACTS/(stage+'.json')
if output.exists(): raise SystemExit('preserve original attempt; review a new exact invocation')
cmd=runtime.compose()+STAGES[stage]
start=time.monotonic()
result=subprocess.run(cmd,env=runtime.environment(),capture_output=True,text=True,timeout=90)
inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
    ROOT/'experiments/g4-m1/compose.m1.yaml',ROOT/'experiments/g4-m1/compose.runtime.yaml',
    ROOT/'experiments/g4-m1/loopback-proxy.mjs',ROOT/'scripts/acceptance/g4-m1-runtime.py')}
output.write_text(json.dumps(dict(taskId=runtime.TASK,stage=stage,command=cmd,inputHashes=inputs,
    exitCode=result.returncode,elapsedSeconds=time.monotonic()-start,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
print(json.dumps(dict(stage=stage,exitCode=result.returncode)))
sys.exit(result.returncode)
