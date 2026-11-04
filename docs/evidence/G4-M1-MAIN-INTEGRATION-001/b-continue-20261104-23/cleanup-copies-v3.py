"""One reviewed four-directory cleanup; default DryRun, never broad cleanup."""
import datetime as dt,json,os,shutil,subprocess,sys
from pathlib import Path
W=Path('/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform')
sys.path.insert(0,str(W/'experiments/g4-m1-main-integration'))
import runtime as rt,closeout
A=W/'artifacts/g4-m1-main-integration-001/b-continue-20261104-23'
PATHS=['.tools/pythonlibs','.tools/pnpm/package','node_modules','apps/web/node_modules']
KEEP=['.tools/dotnet-home']

def occupancy():
    results=[]
    for rel in PATHS:
        p=subprocess.run(['/usr/sbin/lsof','-nP','+D',str(W/rel)],capture_output=True,timeout=30)
        rt.require(p.returncode==1 and not p.stdout and not p.stderr,'COPY_IN_USE_OR_OBSERVATION_FAILED')
        results.append({'path':rel,'command':['/usr/sbin/lsof','-nP','+D',str(W/rel)],'exitCode':p.returncode,'stdoutSha256':rt.digest(p.stdout),'stderrSha256':rt.digest(p.stderr)})
    return results

def keep():return {p:closeout.tool_tree(W/p) for p in KEEP}
def snapshot():return [{'path':p,**closeout.tool_tree(W/p)} for p in PATHS]

if len(sys.argv)==1:
    now=dt.datetime.now(dt.timezone.utc)
    plan={'taskId':rt.TASK,'root':str(W),'createdAtUtc':now.isoformat(),'expiresAtUtc':(now+dt.timedelta(minutes=45)).isoformat(),'expectedHead':rt.git('rev-parse','HEAD'),'executorSha256':rt.digest(Path(__file__).read_bytes()),'candidates':snapshot(),'keep':keep(),'occupancy':occupancy(),'copyReceiptSha256':rt.digest((rt.ARTIFACTS/'b-continue-20261104-22/tool-copies.json').read_bytes())}
    rt.write_json(A/'cleanup-plan-v3.json',plan)
    print(json.dumps({'status':'DRY_RUN','planSha256':rt.digest((A/'cleanup-plan-v3.json').read_bytes())}))
else:
    rt.require(len(sys.argv)==3 and sys.argv[1]=='--apply','ARGS')
    path=A/'cleanup-plan-v3.json';rt.require(rt.digest(path.read_bytes())==sys.argv[2],'PLAN_DRIFT');plan=json.loads(path.read_text())
    rt.require(plan['taskId']==rt.TASK and plan['root']==str(W) and plan['expectedHead']==rt.git('rev-parse','HEAD'),'PLAN_IDENTITY')
    rt.require(dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(plan['expiresAtUtc']),'PLAN_EXPIRED')
    rt.require(plan['executorSha256']==rt.digest(Path(__file__).read_bytes()),'EXECUTOR_DRIFT')
    rt.require(snapshot()==plan['candidates'] and keep()==plan['keep'],'INPUT_DRIFT');observed=occupancy()
    journal=A/'cleanup-applied-v3.jsonl'
    def log(value):
        with journal.open('a') as f:f.write(json.dumps(value)+'\n');f.flush();os.fsync(f.fileno())
    rt.require(not journal.exists(),'EXISTING_JOURNAL');log({'phase':'BEFORE','planSha256':sys.argv[2],'occupancy':observed})
    for row in plan['candidates']:
        target=W/row['path'];rt.require({'path':row['path'],**closeout.tool_tree(target)}==row,'CANDIDATE_DRIFT')
        rt.require(not rt.git('ls-files','--',row['path']),'TRACKED_PATH')
        log({'phase':'COMMAND','path':row['path'],'operation':'shutil.rmtree','expectedFingerprint':row['fingerprint']})
        try:
            shutil.rmtree(target)
            try:target.lstat()
            except FileNotFoundError as error:rt.require(error.errno==2,'UNKNOWN_ABSENCE')
            else:raise ValueError('PATH_REMAINS')
            log({'phase':'AFTER','path':row['path'],'exitCode':0,'diagnostic':'lstat ENOENT'})
        except BaseException:
            log({'phase':'FAIL','path':row['path'],'exists':os.path.lexists(target)});raise
    rt.require(keep()==plan['keep'],'KEEP_DRIFT');log({'phase':'COMPLETE','keepVerified':True,'deleted':len(PATHS)})
    print('FOUR_OWN_COPIES_REMOVED')
