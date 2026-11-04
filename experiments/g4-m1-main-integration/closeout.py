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
