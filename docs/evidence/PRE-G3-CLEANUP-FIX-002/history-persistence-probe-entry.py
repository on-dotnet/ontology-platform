from pathlib import Path
import subprocess,json,datetime,importlib.util,sys
sys.dont_write_bytecode=True
root=Path.cwd();e=root/'docs/evidence/PRE-G3-CLEANUP-FIX-002';plan=json.loads((e/'history-plan.json').read_text());expected=plan['historyBackend'];targets={o['target'] for o in plan['operations']}
def cli(*a):return subprocess.check_output(a,text=True).strip()
def vm():
 p=subprocess.run(['ps','-axo','pid,lstart,comm'],capture_output=True,text=True,check=True)
 return [line.strip() for line in p.stdout.splitlines() if line.split()[-1].endswith('/com.docker.virtualization')]
beforeVm=vm()
# Blank ref RPC is needed: Docker Desktop may answer cached metadata while VM sleeps.
refs=[x.split('/')[-1] for x in cli('docker','buildx','history','ls','--builder','desktop-linux','--format','{{.Ref}}').splitlines()]
afterVm=vm();network=json.loads(cli('docker','network','inspect','bridge','--format','{"Id":{{json .Id}},"Created":{{json .Created}}}'))
engine=cli('docker','info','--format','{{.ID}}');context=cli('docker','context','show');version=cli('docker','buildx','version')
assert engine==expected['engineId'] and context==expected['context'] and version==expected['buildxVersion']
proof=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),previousBridgeId=expected['bridgeId'],currentBridge=network,vmBeforeWake=beforeVm,vmAfterWake=afterVm,engineId=engine,context=context,buildxVersion=version,historyRefs=refs,removedRefs=sorted(targets),allRemovedRefsAbsent=not (targets&set(refs)),naturalFreshGenerationObserved=network['Id']!=expected['bridgeId'],explicitRestartOrConfigActions=False,policy='First RPC blank Ref; no single-ref record inspection, no rm/restart/update/config/prune. No record/env/BuildArgs content read.')
assert proof['naturalFreshGenerationObserved'] and afterVm,'Fresh natural generation not yet observed'
assert proof['allRemovedRefsAbsent'] and len(refs)==1,'Persistent history outcome differs'
proof['status']='PASS_PERSISTENT_ACROSS_OBSERVED_NATURAL_GENERATION'
(e/'history-persistent-check.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(status=proof['status'],bridge=network['Id'],vmBefore=len(beforeVm),vmAfter=len(afterVm),historyCount=len(refs),removedAbsent=len(targets))))
