"""仅执行本任务8个已审准确卷白名单；默认DryRun，拒绝指纹/版本/引用/期限漂移。"""
import argparse, datetime as dt, hashlib, json, subprocess, os
from pathlib import Path
ROOT=Path.cwd();E=ROOT/'docs/evidence/G3-M5-REVIEW-FIX-001';TASK='G3-M5-REVIEW-FIX-001'
PREFIX='g2-1c8100ef259a'
NAMES={PREFIX+'-'+s+'-data' for s in ['alloy','fuseki','grafana','loki','postgres','prometheus','rustfs','tempo']}
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--expected-plan-sha256',required=True);p.add_argument('--proof-commit');args=p.parse_args()
raw=(E/'resource-plan.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==args.expected_plan_sha256
plan=json.loads(raw);assert plan['taskId']==TASK and plan['root']==str(ROOT.resolve()) and set(plan['volumes'])==NAMES
assert dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(plan['expiresAtUtc'])
context=plan['backend']['context'];assert context=='desktop-linux'
logs=[]
result={'taskId':TASK,'mode':'APPLY' if args.apply else 'DRY_RUN','status':'RUNNING','completed':[],'logs':logs}
output=E/('resource-apply.json' if args.apply else 'resource-dryrun.json')
# 在任何Docker删除之前以exclusive方式预占新回执；后续逐命令写入并fsync。
stream=output.open('x')
def persist():
    stream.seek(0);json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.truncate();stream.flush();os.fsync(stream.fileno())
persist()
def docker(*argv):
    command=['docker','--context',context,*argv];result=subprocess.run(command,capture_output=True,text=True)
    logs.append({'command':command,'exitCode':result.returncode,'utc':dt.datetime.now(dt.timezone.utc).isoformat()});persist()
    return result

def backend():
    result=docker('info','--format','{{json .}}');assert result.returncode==0
    info=json.loads(result.stdout);assert info['ID']==plan['backend']['engineId'] and info['ServerVersion']==plan['backend']['serverVersion']

def snapshot(name):
    result=docker('volume','inspect',name);assert result.returncode==0
    value=json.loads(result.stdout)[0]
    return {k:value.get(k) for k in ['Name','Driver','Scope','CreatedAt','Labels','Options']}

def verify(name, expected):
    backend();actual=snapshot(name);assert actual==expected
    result=docker('ps','-a','--filter','volume='+name,'--format','{{.ID}}');assert result.returncode==0 and not result.stdout.strip()
    return actual

try:
    backend()
    if args.apply:
        assert args.proof_commit and len(args.proof_commit)==40
        proof=subprocess.check_output(['git','show',args.proof_commit+':docs/evidence/'+TASK+'/resource-plan.json']);assert proof==raw
        closure=json.loads(subprocess.check_output(['git','show',args.proof_commit+':docs/evidence/'+TASK+'/runtime-closure.json']))
        assert closure['status']=='PASS' and closure['launcherStopped'] and closure['volumePrefix']==PREFIX
        subprocess.run(['git','merge-base','--is-ancestor',args.proof_commit,'HEAD'],check=True)
    for name,expected in plan['keep'].items():assert snapshot(name)==expected
    # 先检查全部对象，再逐对象删除前重复核对，禁止force/global prune。
    for name,expected in plan['volumes'].items():verify(name,expected)
    for name,expected in plan['volumes'].items():
        before=verify(name,expected)
        result['current']={'name':name,'before':before,'state':'VERIFIED_BEFORE_COMMAND'};persist()
        if args.apply:
            removed=docker('volume','rm',name);assert removed.returncode==0 and removed.stdout.strip()==name
            backend();post=docker('volume','inspect',name)
            assert post.returncode==1 and json.loads(post.stdout)==[] and post.stderr.strip()=='Error response from daemon: get '+name+': no such volume'
            result['completed'].append({'name':name,'before':before,'after':'STRONG_NO_SUCH_VOLUME','exitCode':removed.returncode})
        else:result['completed'].append({'name':name,'before':before,'action':'WOULD_DELETE'})
        persist()
    for name,expected in plan['keep'].items():assert snapshot(name)==expected
    result.update(status='PASS',keepUnchanged=True,physicalReclaimedBytes='UNKNOWN')
except BaseException:
    result['status']='FAIL'
    raise
finally:
    persist();stream.close()
print(json.dumps({'status':result['status'],'mode':result['mode'],'completed':len(result['completed'])}))
