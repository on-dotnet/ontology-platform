from pathlib import Path
import subprocess,json,datetime as dt,hashlib,importlib.util,sys
sys.dont_write_bytecode=True
root=Path.cwd();e=root/'docs/evidence/PRE-G3-CLEANUP-FIX-002'
s=importlib.util.spec_from_file_location('cleanup',root/'scripts/maintenance/cleanup_resources.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def cli(*a):return subprocess.check_output(a,text=True).strip()
def vm():
 p=subprocess.run(['ps','-axo','pid,lstart,comm'],capture_output=True,text=True,check=True)
 return [line.strip() for line in p.stdout.splitlines() if line.split()[-1].endswith('/com.docker.virtualization')]
beforeVm=vm();known='0c59496530c0d24e621a6aa825c4427b849ab3b171c78e53bd77b571df9d954a'
assert cli('docker','context','show')=='desktop-linux'
# BuildKit ref-only RPC, rather than possibly cached Docker metadata, is the
# first probe after natural idle; it does not pin any individual history Ref.
wakeRefs=cli('docker','buildx','history','ls','--builder','desktop-linux','--format','{{.Ref}}').splitlines()
engine=cli('docker','info','--format','{{.ID}}');assert engine=='7a8785bb-6b6e-4ae4-8065-996f4bf83016'
network=json.loads(cli('docker','network','inspect','bridge','--format','{"Id":{{json .Id}},"Created":{{json .Created}}}'))
assert network['Id']!=known, 'Natural fresh generation not observed; do not retry polluted server'
afterVm=vm();assert afterVm, 'VM process metadata unavailable'
backend=dict(context='desktop-linux',engineId=engine,bridgeId=network['Id'],buildxVersion=cli('docker','buildx','version'),buildkitVersion='v0.34.0',driver='docker',nodeName='desktop-linux')
assert backend['buildxVersion']=='github.com/docker/buildx v0.38.1 0dbe87f36ed472fe36b6796c3f70b4210a731fc5'
old=json.loads((e/'apply-plan.json').read_text());plan={k:v for k,v in old.items() if k!='operations'}
sha=cli('git','rev-parse','HEAD');assert cli('git','rev-parse','origin/main')==sha
now=dt.datetime.now(dt.timezone.utc);plan.update(expectedMainSha=sha,createdAt=now.isoformat(),expiresAt=(now+dt.timedelta(hours=4)).isoformat(),historyBackend=backend,operations=[])
for op in old['operations']:
 if op['type']!='docker-history':continue
 value=m.safe_docker_snapshot('docker-history',op['target']);assert m.digest(value)==op['fingerprint'], 'Historical approved metadata changed; stop and re-review'
 new=json.loads(json.dumps(op));new['ownershipEvidence']['commit']=sha;plan['operations'].append(new)
assert len(plan['operations'])==18
c=m.Cleaner(str(root),plan);c.history_backend()
out=root/'artifacts/maintenance/PRE-G3-CLEANUP-FIX-002';(out/'history-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
proof=dict(observedAt=now.isoformat(),previousBridge=known,currentBridge=network,vmBeforeDockerQuery=beforeVm,vmAfterDockerQuery=afterVm,initialRefOnlyWakeList=wakeRefs,backend=backend,engineIdUnchanged=True,naturalFreshGenerationObserved=True,activeRestartOrConfigCommands=False,scope='Only same original18 history IDs and original7field fingerprints. No Docker process/restart/config/network/cache mutation commands.',planSha256=hashlib.sha256((out/'history-plan.json').read_bytes()).hexdigest())
(e/'history-fresh-generation.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(operations=18,head=sha,bridge=network['Id'],vmBefore=len(beforeVm),vmAfter=len(afterVm),planSha256=proof['planSha256'])))
