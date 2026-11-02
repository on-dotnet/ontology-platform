"""默认冻结精确任务Docker清单；Apply仅按未过期白名单重验并删除。"""
from pathlib import Path
import argparse,datetime as dt,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-final-gates-001/r04-final'
TASK='G4-M1-FINAL-GATES-001';RUN='final-gates-20261102-r04-final';PROJECT='ontology-g4-m1-final-gates-001-r04-final'
DOCKER=['docker','--context','desktop-linux'];records=[]
IMAGES=['sha256:'+x for x in ['9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437','e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4','3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55','a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f']]
def command(args,allow_failure=False):
    start=dt.datetime.now(dt.timezone.utc);argv=DOCKER+args
    try:x=subprocess.run(argv,capture_output=True,text=True,timeout=30)
    except subprocess.TimeoutExpired:
        records.append(dict(command=argv,startedUtc=start.isoformat(),exitCode=None,timingStatus='TIMEOUT'));raise
    records.append(dict(command=argv,startedUtc=start.isoformat(),exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr))
    if not allow_failure:assert x.returncode==0
    return x
def lines(args):return [json.loads(x) for x in command(args+['--format','{{json .}}']).stdout.splitlines() if x]
def snapshot():
    containers=[json.loads(x) for x in command(['ps','-a','--no-trunc','--format','{"ID":{{json .ID}},"Names":{{json .Names}},"Image":{{json .Image}},"State":{{json .State}},"Status":{{json .Status}},"Labels":{{json .Labels}}}']).stdout.splitlines()]
    return dict(containers=containers,images=lines(['image','ls','--no-trunc','--digests']),volumes=lines(['volume','ls']),networks=lines(['network','ls','--no-trunc']))
def identity(kind,name):
    # 模板只取非秘密配置；容器Env/Args/挂载内文件从不进入输出。
    templates={
      'container':'{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"created":{{json .Created}},"labels":{{json .Config.Labels}},"running":{{json .State.Running}},"paused":{{json .State.Paused}},"memory":{{json .HostConfig.Memory}},"mounts":{{json .Mounts}}}',
      'volume':'{"name":{{json .Name}},"created":{{json .CreatedAt}},"driver":{{json .Driver}},"labels":{{json .Labels}},"options":{{json .Options}}}',
      'network':'{"id":{{json .Id}},"name":{{json .Name}},"created":{{json .Created}},"labels":{{json .Labels}},"internal":{{json .Internal}},"containers":{{json .Containers}}}',
      'image':'{"id":{{json .Id}},"created":{{json .Created}},"size":{{json .Size}},"tags":{{json .RepoTags}},"digests":{{json .RepoDigests}},"platform":{{json .Architecture}},"os":{{json .Os}},"descriptor":{{json .Descriptor}}}'}
    argv=['inspect'] if kind=='container' else [kind,'inspect']
    return json.loads(command(argv+[name,'--format',templates[kind]]).stdout)
def static_identity(obj):return {k:v for k,v in obj.items() if k not in ('running','paused','containers')}
def owned(obj):assert obj['labels'].get('ontology.task-id')==TASK and obj['labels'].get('ontology.run-id')==RUN
def write(path,value):
    with open(path,'x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def original():
    data=json.loads((ART.parent/'resources-before.json').read_text())
    return {key:[{field:value} for value in data[key]] for key,field in [('containers','ID'),('images','ID'),('volumes','Name'),('networks','ID')]}
def preserved(before,after):
    for key,field in [('containers','ID'),('images','ID'),('volumes','Name'),('networks','ID')]:
        assert {x[field] for x in before[key]} <= {x[field] for x in after[key]},'preexisting_resource_missing_'+key
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--expected-plan-sha256');args=parser.parse_args()
    planpath=ART/'cleanup-plan-final.json';receipt=ART/'cleanup-receipt.json'
    version=json.loads(command(['version','--format','{{json .Server}}']).stdout);engine=json.loads(command(['info','--format','{"id":{{json .ID}},"architecture":{{json .Architecture}}}']).stdout)
    if not args.apply:
        before=snapshot();old=original();objects=[];drift=[];original_delta={}
        for key,field in [('containers','ID'),('images','ID'),('volumes','Name'),('networks','ID')]:
            missing={x[field] for x in old[key]}-{x[field] for x in before[key]}
            original_delta[key]=dict(missing=sorted(missing),added=sorted({x[field] for x in before[key]}-{x[field] for x in old[key]}))
            assert not missing, 'preexisting_resource_missing_'+key
        for kind,key,field in [('container','containers','ID'),('volume','volumes','Name'),('network','networks','ID')]:
            for item in before[key]:
                if kind=='container':name=item.get('Names','')
                else:name=item.get('Name','')
                if not name.startswith(PROJECT):continue
                obj=identity(kind,item[field]);owned(obj);assert not obj.get('paused',False)
                objects.append(dict(kind=kind,identity=item[field],expected=static_identity(obj)))
        protected={}
        for kind,key,field in [('container','containers','ID'),('image','images','ID'),('volume','volumes','Name'),('network','networks','ID')]:
            selected={x['identity'] for x in objects if x['kind']==kind};protected[key]=[x for x in before[key] if x[field] not in selected]
        now=dt.datetime.now(dt.timezone.utc)
        plan=dict(driverSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),taskId=TASK,runId=RUN,mode='DRY_RUN',createdUtc=now.isoformat(),expiresUtc=(now+dt.timedelta(hours=1)).isoformat(),engine=engine,serverVersion=version['Version'],before=before,original=old,originalIdentityDrift=drift,originalDelta=original_delta,protectedAtCloseout=protected,objects=objects,commands=records,scope='Only these owned temporary resources; all task worktrees and private inputs KEEP pending review.')
        write(planpath,plan);print(json.dumps(dict(mode='DRY_RUN',objects=len(objects),planSha256=hashlib.sha256(planpath.read_bytes()).hexdigest())));return
    assert not planpath.is_symlink() and hashlib.sha256(planpath.read_bytes()).hexdigest()==args.expected_plan_sha256
    plan=json.loads(planpath.read_text());assert plan['driverSha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest();assert plan['taskId']==TASK and plan['runId']==RUN and plan['engine']==engine and plan['serverVersion']==version['Version'] and dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(plan['expiresUtc'])
    result=dict(taskId=TASK,status='FAIL',planSha256=args.expected_plan_sha256,commands=records,deleted=[],before=snapshot(),originalIdentityDrift=plan['originalIdentityDrift']);preserved(plan['protectedAtCloseout'],result['before'])
    protected_now={}
    for kind,key,field in [('container','containers','ID'),('image','images','ID'),('volume','volumes','Name'),('network','networks','ID')]:
        selected={x['identity'] for x in plan['objects'] if x['kind']==kind};protected_now[key]=[x for x in result['before'][key] if x[field] not in selected]
    result['protectedAtApply']=protected_now;active_item=None
    try:
        # 全部对象先重验，再开始任何删除；卷/网络稍后必须无剩余引用。
        for item in plan['objects']:
            current=identity(item['kind'],item['identity']);assert static_identity(current)==item['expected']
            if item['kind']!='image':owned(current)
        items=sorted(plan['objects'],key=lambda x:({'container':0,'network':1,'volume':2,'image':3}[x['kind']],0 if x['kind']=='container' and x['expected']['name'].endswith('-web-1') else 1))
        for item in items:
            active_item=item;kind=item['kind'];key=item['identity'];current=identity(kind,key);assert static_identity(current)==item['expected']
            if kind=='container':
                assert not current['paused']
                if current['running']:command(['stop','--time','10',key])
                command(['rm',key])
            elif kind=='network':assert not current['containers'];command(['network','rm',key])
            elif kind=='volume':
                assert not command(['ps','-a','--filter','volume='+key,'--format','{{.ID}}']).stdout.strip();command(['volume','rm',key])
            else:
                remaining=snapshot()['containers']
                for container in remaining:assert json.loads(command(['inspect',container['ID'],'--format','{{json .Image}}']).stdout)!=key
                command(['image','rm',key])
            inspect_args=(['inspect',key] if kind=='container' else [kind,'inspect',key])+['--format','{{json .Name}}' if kind=='volume' else '{{json .Id}}']
            absent=command(inspect_args,True);assert absent.returncode!=0 and ('no such' in absent.stderr.lower() or 'not found' in absent.stderr.lower())
            result['deleted'].append(dict(kind=kind,identity=key,absenceVerified=True))
        result['after']=snapshot();preserved(plan['protectedAtCloseout'],result['after']);preserved(protected_now,result['after'])
        for item in plan['objects']:
            key,field={'container':('containers','ID'),'image':('images','ID'),'volume':('volumes','Name'),'network':('networks','ID')}[item['kind']]
            assert item['identity'] not in {x[field] for x in result['after'][key]}
        result['status']='PASS';result['closeoutProtectedResourcesPreserved']=True;result['originalBridgeIdentityPreservation']='UNCHANGED_THIS_TASK_ONLY'
    except Exception as error:
        result['failure']={'category':type(error).__name__,'object':None if active_item is None else {'kind':active_item['kind'],'identity':active_item['identity']}}
        raise
    finally:
        try:result['after']=snapshot()
        except Exception as error:result['afterUnavailable']={'category':type(error).__name__}
        deleted={(x['kind'],x['identity']) for x in result['deleted']}
        result['remainingDecisions']=[{'kind':x['kind'],'identity':x['identity'],'decision':'KEEP_PENDING_RECHECK','reason':'Deletion not completed; inspect failure and exact state before any retry.'} for x in plan['objects'] if (x['kind'],x['identity']) not in deleted]
        result['completedUtc']=dt.datetime.now(dt.timezone.utc).isoformat();write(receipt,result)
    print(json.dumps(dict(status=result['status'],deleted=len(result['deleted']))))
if __name__=='__main__':main()
