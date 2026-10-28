"""One-use continuation evidence, not a replacement for the permanent acceptance entry."""
import datetime,hashlib,importlib.util,json,os,subprocess,sys,uuid
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location('owned_g2',root/'scripts/acceptance/g2-acceptance-runtime.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
base=root/'docs/evidence/G3-M3-001/runtime/g3-m3-daa8b53191e9/a5c476bcb6d14b15ab3fae045405f838'
previous=json.loads((base/'acceptance.json').read_text())
assert all(g['status']=='PASS' and g['exitCode']==0 for g in previous['gates'][:5])
assert previous['gates'][5]['status']=='FAIL' and previous['gates'][5]['exitCode']==2
source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
changes=subprocess.check_output(['git','diff','--name-only',previous['sourceHead'],source],text=True).splitlines()
code=[p for p in changes if not p.startswith('docs/evidence/')]
assert set(code)=={'scripts/acceptance/g2-readiness-fault.py','scripts/acceptance/g3-acceptance-runtime.py','scripts/acceptance/performance-baseline.py','scripts/tests/G2Acceptance.Tests.py'}
runtime_file=root/'.tools/security/g3-m3-daa8b53191e9/runtime.json'
runtime=json.loads(runtime_file.read_text())
os.environ['PLATFORM_EVIDENCE_DIR']=str(base.relative_to(root))
run='resume-'+uuid.uuid4().hex
report={'status':'RUNNING','runId':run,'sourceHead':source,'previousRun':previous['runId'],'previousSource':previous['sourceHead'],'firstFiveGatesReused':previous['gates'][:5],'changedNonEvidenceInputs':code,'productLockBuildInputsChanged':False,'startedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'gates':[],'launcherStopped':False}
path=base/'continuation.json'; timeline=base/'continuation-timeline.jsonl'
process=None
try:
    process=subprocess.Popen([sys.executable,'scripts/acceptance/g3-runtime.py','full','--runtime-file',str(runtime_file),'--milestone','M3'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
    shared.wait_for('http://localhost:15100/health/ready',{'X-Health-Key':runtime['healthKey']})
    commands=[['scripts/acceptance/g2-readiness-fault.py','--runtime-file',str(runtime_file)],['scripts/acceptance/performance-baseline.py','--from-observed-run','--chain-report','m3-full-e2e.json']]
    for i,command in enumerate(commands):
        label='m3-resume-'+str(i)
        wrapped=[sys.executable,'scripts/maintenance/task_run_timeline.py','run','--path',str(timeline),'--task-id','G3-M3-001','--run-id',run,'--step-id',label,'--task-type','TEST','--input-fingerprint',hashlib.sha256(source.encode()).hexdigest(),'--command-label',Path(command[0]).stem]
        if i: wrapped+=['--depends-on','m3-resume-0']
        code=subprocess.run(wrapped+['--',sys.executable,*command]).returncode
        report['gates'].append({'name':Path(command[0]).name,'status':'PASS' if code==0 else 'FAIL','exitCode':code})
        if code: raise RuntimeError('Actual continuation gate failed')
    report['status']='PASS'
except Exception as error:
    report['status']='FAIL';report['failureCategory']=type(error).__name__
finally:
    shared.stop(process)
    report['launcherStopped']=process is not None and process.poll() is not None
    report['launcherExitCode']=None if process is None else process.returncode
    report['completedAtUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'runId':run,'launcherStopped':report['launcherStopped']}))
sys.exit(0 if report['status']=='PASS' and report['launcherStopped'] else 1)
