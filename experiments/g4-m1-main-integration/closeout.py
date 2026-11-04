#!/usr/bin/env python3
"""精确资源回收：默认DryRun，Apply只接受已登记当前Run的完整ID白名单。"""
import datetime
import json
import subprocess
import time
import runtime as rt


def inventory(m):
    """所有本Run对象和外部保留集分别取准确ID，不收集容器秘密配置。"""
    result={}
    for kind,argv in [('container',['ps','-aq','--no-trunc']),('network',['network','ls','-q','--no-trunc']),('volume',['volume','ls','-q'])]:
        all_ids=rt.docker(m,argv).decode().split()
        owned=[];keep=[]
        for ident in all_ids:
            args=['inspect',ident] if kind=='container' else [kind,'inspect',ident]
            item=json.loads(rt.docker(m,args))[0]
            labels=(item['Config'].get('Labels') or {}) if kind=='container' else item.get('Labels') or {}
            if labels.get('ontology.task-id')==rt.TASK and labels.get('ontology.run-id')==m['runId']:
                owned.append({'id':item.get('Id',item.get('Name')),'created':item.get('Created',item.get('CreatedAt'))})
            else:keep.append(ident)
        result[kind]={'owned':owned,'keep':sorted(keep)}
    return result


def reclaim(m, label, *, apply=False):
    """先冻结清单、重查身份/创建版本，再停止并删除；不调用prune或Compose down。"""
    rt.require(label in ('modules','g3','m1','failure'),'CLEANUP_GROUP')
    rt.verify_engine(m)
    before=inventory(m)
    registered=rt.ARTIFACTS/m['runId']/('resources-'+label+'-owned.json')
    rt.require(registered.is_file(),'CREATION_REGISTRY_REQUIRED')
    creation=json.loads(registered.read_text())
    rt.require(all(creation[k]['owned']==before[k]['owned'] for k in before),'UNREGISTERED_DELETE_REFUSED')
    plan={'taskId':rt.TASK,'runId':m['runId'],'observedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'resources':before}
    path=rt.ARTIFACTS/m['runId']/('cleanup-'+label+'-plan.json')
    rt.write_json(path,plan)
    if not apply:return plan
    rt.require(inventory(m)==before,'RESOURCE_DRIFT')
    commands=[]
    try:
        for row in before['container']['owned']:
            item=rt.inspect_owned(m,row['id'])
            if item['State']['Paused']:
                rt.docker(m,['unpause',row['id']]);commands.append({'command':['unpause',row['id']],'exitCode':0})
            rt.docker(m,['stop','--time','10',row['id']]);commands.append({'command':['stop','--time','10',row['id']],'exitCode':0})
            rt.docker(m,['rm',row['id']]);commands.append({'command':['rm',row['id']],'exitCode':0})
        for kind in ('network','volume'):
            for row in before[kind]['owned']:
                current=json.loads(rt.docker(m,[kind,'inspect',row['id']]))[0]
                rt.require(current['Labels'].get('ontology.task-id')==rt.TASK and current['Labels'].get('ontology.run-id')==m['runId'],'DELETE_OWNER')
                rt.require(current.get('Created',current.get('CreatedAt'))==row['created'],'DELETE_VERSION')
                rt.docker(m,[kind,'rm',row['id']]);commands.append({'command':[kind,'rm',row['id']],'exitCode':0})
        after=inventory(m)
        rt.require(all(not after[k]['owned'] and before[k]['keep']==after[k]['keep'] for k in before),'CLEANUP_OR_KEEP_DRIFT')
        diagnostics=[]
        for kind in before:
            for row in before[kind]['owned']:
                args=['inspect',row['id']] if kind=='container' else [kind,'inspect',row['id']]
                p=subprocess.run(['docker','--context','desktop-linux',*args],capture_output=True,timeout=20)
                expected=('No such object' if kind=='container' else ('not found' if kind=='network' else 'no such volume'))
                rt.require(p.returncode!=0 and expected.lower() in p.stderr.decode().lower(),'ABSENCE_DIAGNOSTIC')
                diagnostics.append({'kind':kind,'id':row['id'],'exitCode':p.returncode,'stderrSha256':rt.digest(p.stderr),'exactAbsent':True})
        rt.update_runtime(m,containerIds={},group=None)
        config=rt.private_dir(m['runId'])/'api/appsettings.json'
        if config.exists():config.rename(config.with_name('appsettings-closed-'+label+'.json'))
        return {'status':'PASS','deleted':sum(len(before[k]['owned']) for k in before),'absence':diagnostics,'keepVerified':True}
    finally:
        rt.write_json(rt.ARTIFACTS/m['runId']/('cleanup-'+label+'-commands.json'),{'before':before,'commands':commands,'after':inventory(m)})


def verify_secret_hygiene(m):
    """只用本Run已知秘密检查普通证据/源码及真实容器日志；不导出匹配字节。"""
    import base64
    private=rt.private_dir(m['runId']);patterns=set()
    for name in ('reader-password','postgres-password','platform-password','keycloak-password','s3-access','s3-secret','rotation-password','api/g4-key','server.key','wrong-san.key','api/keyring.pfx'):
        path=private/name
        if path.is_file():
            raw=path.read_bytes();patterns.add(raw.strip());patterns.add(base64.b64encode(raw));patterns.add(raw.hex().encode())
    def collect(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if isinstance(child,str) and any(x in key.lower() for x in ('password','clientsecret','healthkey','secretref','access_token','token')) and not child.startswith('/'):
                    patterns.add(child.encode())
                else:collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    for path in private.rglob('*.json'):
        try:collect(json.loads(path.read_text()))
        except (ValueError,UnicodeError):pass
    r=rt.runtime_value(m);source=r['containerIds']['platform-pg']
    rt.inspect_owned(m,source,'platform-pg')
    raw=rt.docker(m,['exec','-i',source,'psql','-U','platform','-d','platform','-qAt','-v','ON_ERROR_STOP=1'],input_bytes=b'BEGIN READ ONLY;SELECT "Id" FROM connections."ConnectionSecrets";COMMIT;')
    for line in raw.splitlines():
        if __import__('re').fullmatch(rb'[a-f0-9]{32}',line):patterns.add(line)
    patterns={p for p in patterns if len(p)>=16};findings=[];scanned=0
    def scan(name,data):
        nonlocal scanned
        scanned+=1
        if any(p in data for p in patterns):findings.append({'path':name,'category':'KNOWN_CURRENT_RUN_SECRET'})
    for name in rt.git('ls-files').splitlines():
        path=rt.ROOT/name
        if path.is_file() and path.stat().st_size<=20*1024**2:scan(name,path.read_bytes())
    for path in (rt.ARTIFACTS/m['runId']).rglob('*'):
        if path.is_file() and path.suffix in ('.json','.jsonl','.log','.txt','.md') and 'host-graph-tool' not in path.parts:
            scan(str(path.relative_to(rt.ROOT)),path.read_bytes())
    for service,ident in r['containerIds'].items():
        rt.inspect_owned(m,ident,service)
        raw=rt.execute(m,'scan-log-'+service,['docker','--context','desktop-linux','logs',ident],sensitive=True)
        scan('container/'+service,raw)
    result={'status':'FAIL' if findings else 'PASS','taskId':rt.TASK,'runId':m['runId'],'patterns':len(patterns),'scanned':scanned,'findings':findings,'scope':'known current synthetic secrets only; not general security/CVE certification'}
    rt.write_json(rt.ARTIFACTS/m['runId']/'secret-hygiene.json',result)
    rt.require(not findings,'SECRET_HYGIENE_FAILED')
    return result


TOOL_COPY_PATHS = (
    '.tools/nuget', '.tools/pythonlibs', '.tools/pnpm/package', 'node_modules',
    'apps/web/node_modules', '.tools/msbuild-sdks',
    'artifacts/g4-m1-main-integration-001/b-continue-20261104-02/sdk-boundary-fixture',
    'artifacts/g4-m1-main-integration-001/b-continue-20261104-02/sdk-boundary-fixture-v2',
    'artifacts/g4-m1-main-integration-001/b-continue-20261104-02/fresh-cli-home')


def tool_tree(path):
    """不跟随链接的精确副本清单；目录/链接元数据与实际文件SHA共同拒绝漂移。"""
    import os
    import stat
    rt.boundary(path,rt.ROOT,exists=True)
    rt.require(path.is_dir() and not path.is_symlink(),'TOOL_COPY_ROOT')
    rows=[];files=0;size=0;links=0
    def visit(current):
        nonlocal files,size,links
        info=current.lstat();relative=str(current.relative_to(path))
        row={'path':relative,'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino,'mtimeNs':info.st_mtime_ns}
        if stat.S_ISLNK(info.st_mode):
            rt.require(current.resolve().is_relative_to(rt.ROOT),'TOOL_LINK_ESCAPE')
            row['link']=os.readlink(current);links+=1
        elif stat.S_ISREG(info.st_mode):
            rt.require(info.st_nlink==1,'TOOL_HARDLINK')
            row.update(bytes=info.st_size,sha256=rt.digest(current.read_bytes()));files+=1;size+=info.st_size
        else:rt.require(stat.S_ISDIR(info.st_mode),'TOOL_SPECIAL_FILE')
        rows.append(row)
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(current.iterdir()):visit(child)
    visit(path)
    return {'files':files,'bytes':size,'links':links,'entries':len(rows),'fingerprint':rt.digest(json.dumps(rows,sort_keys=True).encode())}


def freeze_tool_cleanup(run, head):
    """只冻结本轮已登记副本；默认不删除，旧runtime/包/HTTP事件原件均保留。"""
    import subprocess
    rt.run_id(run);rt.require(run=='b-continue-20261104-01','EXACT_INCIDENT_RUN');rt.require(rt.git('rev-parse','HEAD')==head,'CLEANUP_HEAD')
    rt.require(not rt.git('status','--porcelain'),'CLEANUP_DIRTY_SOURCE')
    candidates=[]
    for relative in TOOL_COPY_PATHS:
        path=rt.ROOT/relative
        rt.require(not subprocess.check_output(['git','ls-files','--',relative],cwd=rt.ROOT),'TRACKED_TOOL_COPY')
        candidates.append({'path':relative,**tool_tree(path)})
    keeps={}
    for path in sorted((rt.ROOT/'artifacts/reviews').glob('OntologyPlatform-Review-G4-M1-MAIN-INTEGRATION-001-*.zip')):
        keeps[str(path.relative_to(rt.ROOT))]=rt.digest(path.read_bytes())
    rt.require(keeps,'HISTORICAL_PACKAGES_MISSING')
    incident_home=tool_tree(rt.ROOT/'.tools/dotnet-home')
    now=datetime.datetime.now(datetime.timezone.utc)
    plan={'createdAtUtc':now.isoformat(),'expiresAtUtc':(now+datetime.timedelta(minutes=15)).isoformat(),'taskId':rt.TASK,'runId':run,'root':str(rt.ROOT),'head':head,'sourceSha256':rt.digest(__import__('pathlib').Path(__file__).read_bytes()),'candidates':candidates,'keepPackages':keeps,'keepIncidentHome':incident_home,'mode':'DRY_RUN','globalCertificateStores':'KEEP_NOT_TOUCHED'}
    path=rt.ARTIFACTS/run/'cleanup-tools-plan.json';rt.write_json(path,plan);return plan


def apply_tool_cleanup(run, expected_plan_sha):
    """准确SHA白名单Apply，命令前复验与lstat ENOENT后验，禁止全局或宽泛清理。"""
    import errno
    import shutil
    import os
    rt.run_id(run);rt.require(run=='b-continue-20261104-01','EXACT_INCIDENT_RUN');path=rt.ARTIFACTS/run/'cleanup-tools-plan.json'
    rt.boundary(path,rt.ARTIFACTS/run,exists=True)
    rt.require(rt.digest(path.read_bytes())==expected_plan_sha,'CLEANUP_PLAN_DRIFT')
    plan=json.loads(path.read_text())
    rt.require(shutil.rmtree.avoids_symlink_attacks,'UNSAFE_RMTREE_IMPLEMENTATION')
    now=datetime.datetime.now(datetime.timezone.utc)
    rt.require(datetime.datetime.fromisoformat(plan['createdAtUtc'])<=now<=datetime.datetime.fromisoformat(plan['expiresAtUtc']),'CLEANUP_PLAN_EXPIRED')
    rt.require(plan['taskId']==rt.TASK and plan['runId']==run and plan['root']==str(rt.ROOT),'CLEANUP_PLAN_IDENTITY')
    rt.require(rt.git('rev-parse','HEAD')==plan['head'] and not rt.git('status','--porcelain'),'CLEANUP_INPUT_DRIFT')
    rt.require(rt.digest(__import__('pathlib').Path(__file__).read_bytes())==plan['sourceSha256'],'CLEANUP_EXECUTOR_DRIFT')
    rt.require([x['path'] for x in plan['candidates']]==list(TOOL_COPY_PATHS),'CLEANUP_PATH_SET')
    for row in plan['candidates']:
        rt.require(tool_tree(rt.ROOT/row['path'])=={k:v for k,v in row.items() if k!='path'},'CLEANUP_COPY_DRIFT')
    result={'taskId':rt.TASK,'runId':run,'head':plan['head'],'planSha256':expected_plan_sha,'status':'FAIL','commands':[]}
    output=rt.ARTIFACTS/run/'cleanup-tools-result.json';rt.require(not output.exists(),'EXISTING_CLEANUP_RECEIPT')
    journal=output.with_name('cleanup-tools-journal.jsonl')
    rt.require(not journal.exists() and not journal.is_symlink(),'EXISTING_CLEANUP_JOURNAL')
    with os.fdopen(os.open(journal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as stream:
        def persist(row):
            stream.write(json.dumps(row,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
        persist({'phase':'START','planSha256':expected_plan_sha,'head':plan['head']})
        try:
            for row in plan['candidates']:
                target=rt.ROOT/row['path'];before=tool_tree(target)
                rt.require(before=={k:v for k,v in row.items() if k!='path'},'CLEANUP_COPY_DRIFT')
                command={'operation':'shutil.rmtree exact frozen directory without following links','path':row['path'],'before':before,'status':'PENDING','exitCode':None}
                result['commands'].append(command);persist({'phase':'BEFORE',**command})
                try:
                    shutil.rmtree(target)
                    try:target.lstat()
                    except OSError as error:
                        rt.require(error.errno==errno.ENOENT,'CLEANUP_ABSENCE_DIAGNOSTIC');absent=error.errno
                    else:raise ValueError('TOOL_COPY_STILL_EXISTS')
                    command.update(status='PASS',exitCode=0,afterErrno=absent)
                except BaseException as error:
                    command.update(status='FAIL',exitCode=1,errorType=type(error).__name__,errorErrno=getattr(error,'errno',None),afterExists=target.exists())
                    persist({'phase':'AFTER',**command});raise
                persist({'phase':'AFTER',**command})
            for name,sha in plan['keepPackages'].items():rt.require(rt.digest((rt.ROOT/name).read_bytes())==sha,'KEEP_PACKAGE_DRIFT')
            rt.require(tool_tree(rt.ROOT/'.tools/dotnet-home')==plan['keepIncidentHome'],'KEEP_INCIDENT_HOME_DRIFT')
            rt.require(rt.git('rev-parse','HEAD')==plan['head'] and not rt.git('status','--porcelain'),'CLEANUP_SOURCE_DRIFT')
            result.update(status='PASS',keptPackages=len(plan['keepPackages']),incidentHomeKept=True,deletedFiles=sum(x['files'] for x in plan['candidates']),deletedLogicalBytes=sum(x['bytes'] for x in plan['candidates']),globalCertificateStores='NOT_TOUCHED')
            return result
        finally:rt.write_json(output,result)
