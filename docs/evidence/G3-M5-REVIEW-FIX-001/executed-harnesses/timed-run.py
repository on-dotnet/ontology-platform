import sys, subprocess, time, datetime, json, importlib.util
from pathlib import Path
root=Path.cwd(); out=root/'artifacts/review-fix'; label=sys.argv[1]; command=sys.argv[2:]
spec=importlib.util.spec_from_file_location('timeline', root/'scripts/maintenance/task_run_timeline.py');timeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(timeline)
spec=importlib.util.spec_from_file_location('preflight',root/'scripts/maintenance/execution_preflight.py'); preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)
start=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
with (out/(label+'.log')).open('x') as log:
 result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
end=datetime.datetime.now(datetime.timezone.utc).isoformat(); duration=round((time.monotonic()-tick)*1000)
row=dict(schemaVersion=1,taskId='G3-M5-REVIEW-FIX-001',runId='review-fix',stepId=label,taskType='TEST',inputFingerprint=preflight.product_input_fingerprint(root),startedAtUtc=start,endedAtUtc=end,durationMs=duration,outcome='PASS' if result.returncode==0 else 'FAIL',errorCategory=None if result.returncode==0 else 'COMMAND_FAILED',dependsOn=[],concurrencyGroup=label,attempt=1,exitCode=result.returncode,commandLabel=label)
row=timeline.complete(row,end,duration,result.returncode,row['errorCategory']);timeline.append(out/'timeline.jsonl',row,assign_attempt=True)
(out/(label+'.json')).write_text(json.dumps(dict(command=command,**row),indent=2)+'\n')
print(json.dumps(dict(label=label,exitCode=result.returncode,durationMs=duration,log=str(out/(label+'.log')))))
raise SystemExit(result.returncode)
