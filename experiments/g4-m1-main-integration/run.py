#!/usr/bin/env python3
"""G4-M1主线集成任务真实门禁入口；所有后续阶段由实际前置回执决定。"""
import argparse
import base64
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import sqlite3
import struct
import tarfile
import zipfile
import stat
import subprocess
import sys
import time
import runtime as rt
import consumer_check
import closeout

DOTNET='/usr/local/share/dotnet/dotnet'
NODE='/opt/homebrew/opt/node@24/bin/node'


def module(name):
    """只加载精确白名单中的任务实现；不调用旧任务main。"""
    rt.require(name+'.py' in rt.NAMES,'MODULE_ALLOWLIST')
    spec=importlib.util.spec_from_file_location(name,rt.HERE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def binding(m):
    return ['--run-id',m['runId'],'--expected-head',m['_head'],'--resource-manifest',m['_path']]


def locked_packages():
    """锁文件同名版本若出现矛盾也立即拒绝。"""
    packages={}
    for path in sorted((rt.ROOT/'backend').rglob('packages*.lock.json')):
        if path.name not in ('packages.lock.json','packages.osx-arm64.lock.json'):continue
        for entries in json.loads(path.read_text())['dependencies'].values():
            for name,value in entries.items():
                if 'resolved' in value and 'contentHash' in value:
                    key=name.lower()+'/'+value['resolved']
                    rt.require(key not in packages or packages[key]==value['contentHash'],'LOCK_HASH_CONFLICT')
                    packages[key]=value['contentHash']
    rt.require(packages,'EMPTY_LOCKS')
    return packages


def decode_package_index(blob):
    """只解码pnpm已审离线索引的MessagePack记录，不执行包内代码。"""
    position=0;records={}
    def take(n):
        nonlocal position
        value=blob[position:position+n];position+=n
        rt.require(len(value)==n,'INDEX_TRUNCATED')
        return value
    def number(n,signed=False):return int.from_bytes(take(n),'big',signed=signed)
    def read():
        tag=number(1)
        if tag in records:return {key:read() for key in records[tag]}
        if tag<128:return tag
        if tag>=224:return tag-256
        if 160<=tag<=191:return take(tag-160).decode()
        if 144<=tag<=159:return [read() for _ in range(tag-144)]
        if 128<=tag<=143:return {read():read() for _ in range(tag-128)}
        if tag in (192,194,195):return {192:None,194:False,195:True}[tag]
        if tag in (204,205,206,207):return number({204:1,205:2,206:4,207:8}[tag])
        if tag in (208,209,210,211):return number({208:1,209:2,210:4,211:8}[tag],True)
        if tag in (202,203):return struct.unpack('>f' if tag==202 else '>d',take(4 if tag==202 else 8))[0]
        if tag in (217,218,219):return take(number({217:1,218:2,219:4}[tag])).decode()
        if tag in (196,197,198):return take(number({196:1,197:2,198:4}[tag]))
        if tag in (220,221):return [read() for _ in range(number(2 if tag==220 else 4))]
        if tag in (222,223):return {read():read() for _ in range(number(2 if tag==222 else 4))}
        if tag==212:
            kind,ident=number(1),number(1);rt.require(kind==114,'INDEX_EXTENSION')
            keys=read();rt.require(isinstance(keys,list) and all(isinstance(x,str) for x in keys),'INDEX_RECORD_KEYS')
            records[ident]=keys;return {key:read() for key in keys}
        raise ValueError('INDEX_TAG')
    value=read();rt.require(position==len(blob),'INDEX_TRAILING_BYTES');return value


def verify_web_cache(web):
    """逐个已安装包绑定锁定store索引及文件SHA512；生成shim另行记录。"""
    store=Path('/Users/chasen/.codex/worktrees/g3-m3-master/ontology-platform/.tools/pnpm-store/v11/index.db')
    with sqlite3.connect('file:'+str(store)+'?mode=ro&immutable=1',uri=True) as db:
        indexed={key.split('\t')[-1]:(key,blob) for key,blob in db.execute('select key,data from package_index')}
    verified=[]
    for folder in sorted((web/'node_modules/.pnpm').iterdir()):
        modules=folder/'node_modules'
        if not modules.is_dir():continue
        candidates=[]
        for item in modules.iterdir():
            if item.is_symlink() or item.name=='.bin':continue
            candidates.extend(item.iterdir() if item.name.startswith('@') else [item])
        for package in candidates:
            if package.is_symlink() or not (package/'package.json').is_file():continue
            identity=json.loads((package/'package.json').read_text());key=identity['name']+'@'+identity['version']
            rt.require(key in indexed,'INDEX_PACKAGE_MISSING')
            store_key,blob=indexed[key];index=decode_package_index(blob)
            lock=(web/'pnpm-lock.yaml').read_text()
            pattern=r"^  '?"+re.escape(key)+r"'?:\n    resolution: \{integrity: "+re.escape(store_key.split('\t')[0])+r"[},]"
            rt.require(re.search(pattern,lock,re.MULTILINE),'STORE_LOCK_BINDING')
            rt.require(index['algo']=='sha512','INDEX_ALGORITHM')
            files=[]
            for name,entry in index['files'].items():
                path=package/name
                rt.require('..' not in Path(name).parts and not Path(name).is_absolute(),'INDEX_PATH')
                rt.require(path.is_file() and not path.is_symlink(),'INDEX_FILE_MISSING')
                actual=hashlib.sha512(path.read_bytes()).hexdigest()
                rt.require(actual==entry['digest'] and path.stat().st_size==entry['size'],'WEB_PACKAGE_FILE_DRIFT')
                files.append({'path':str(path.relative_to(web)),'sha512':actual})
            bins=identity.get('bin',{})
            if isinstance(bins,str):bins={identity['name'].split('/')[-1]:bins}
            declared=[]
            expected={x['path'] for x in files}
            for name,target in bins.items():
                resolved=(package/target).resolve()
                rt.require(resolved.is_relative_to(web) and str(resolved.relative_to(web)) in expected,'PACKAGE_BIN_UNBOUND')
                declared.append({'name':name,'path':str(resolved.relative_to(web))})
            verified.append({'package':key,'storeKey':store_key,'indexSha256':rt.digest(blob),'files':files,'bins':declared})
    rt.require(len(verified)>100,'INCOMPLETE_WEB_CACHE')
    return verified


SDK_ARCHIVES = {
    'Aspire.AppHost.Sdk':('13.6.3','cb8c5abad85fb542e2bb4807dd31a2ee4c22f56b7762e0258b74a803c1035ad0','eav786xkHaGl9QluDj4mDgTn4f8fdg+fFEx+vAb7YVWM5DYe0yEUJKqdj+PHxPkffLtKc+/CBgAvf7NbYT4Yfg=='),
    'MSTest.Sdk':('4.5.1','984c1fa3338a950aaee3afa8bdda314cd732af483e0dc8b4138ec51aa0327c2b','uWWZsmVXHQfTC3JLGz1fXF28WirAhh5JKBwYyVh4I/cjBKYNbO13ZvIh0NVEBa50no5FKmN+czZCivdQfPXNXQ==')}


def sdk_payload(name,m):
    """只从已校验不可变字节构造完整SDK文件集，避免重开共享归档。"""
    version,sha,content_hash=SDK_ARCHIVES[name]
    archive=Path('/Users/chasen/.nuget/packages')/name.lower()/version/(name.lower()+'.'+version+'.nupkg')
    raw=archive.read_bytes();rt.require(rt.digest(raw)==sha,'SDK_ARCHIVE_DRIFT')
    payload={};folded=set()
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        for item in package.infolist():
            relative=Path(item.filename)
            rt.require(not relative.is_absolute() and '..' not in relative.parts and stat.S_IFMT(item.external_attr>>16)!=stat.S_IFLNK,'SDK_ARCHIVE_PATH')
            if item.is_dir():continue
            rt.require(item.filename.casefold() not in folded,'SDK_DUPLICATE_MEMBER');folded.add(item.filename.casefold())
            payload[item.filename]=package.read(item)
    metadata={'version':2,'contentHash':content_hash,'source':str(rt.ARTIFACTS/m['runId']/'nuget-feed')}
    payload.update({archive.name:raw,archive.name+'.sha512':content_hash.encode(),'.nupkg.metadata':json.dumps(metadata,indent=2).encode()})
    target=Path(rt.environment(m['runId'])['NUGET_PACKAGES'])/name.lower()/version
    row={'name':name,'version':version,'archiveSha256':sha,'contentHash':content_hash,'files':[{'path':str((target/key).relative_to(rt.ROOT)),'sha256':rt.digest(data),'bytes':len(data)} for key,data in sorted(payload.items())]}
    return target,payload,row


def prepare_sdk_copies(m):
    """预存SDK精确归档与完整私有成员绑定；外网由OS拒绝。"""
    import xml.etree.ElementTree as ET
    observed=set()
    for project in (rt.ROOT/'backend').rglob('*.csproj'):
        tree=ET.parse(project).getroot();declared=tree.get('Sdk','')
        if '/' in declared:observed.add(tuple(declared.split('/',1)))
        for sdk in tree.findall('Sdk'):observed.add((sdk.attrib['Name'],sdk.attrib['Version']))
    rt.require(observed=={(name,value[0]) for name,value in SDK_ARCHIVES.items()},'SDK_DECLARATION_DRIFT')
    rows=[]
    for name in SDK_ARCHIVES:
        target,payload,row=sdk_payload(name,m);rt.require(not target.exists(),'EXISTING_SDK_COPY')
        for relative,data in payload.items():
            path=target/relative;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
        rt.require((target/'Sdk/Sdk.props').is_file(),'SDK_PROPS_MISSING');rows.append(row)
    rt.write_json(rt.ARTIFACTS/m['runId']/'sdk-copies.json',rows)
    return rows


def verify_sdk_copies(m):
    """期望集合来自固定SHA归档，ignored清单仅作回执；遗漏/增项/篡改均拒绝。"""
    receipt=json.loads((rt.ARTIFACTS/m['runId']/'sdk-copies.json').read_text());expected=[]
    for name in SDK_ARCHIVES:
        target,payload,row=sdk_payload(name,m);expected.append(row)
        rt.boundary(target,rt.ARTIFACTS/m['runId']/'nuget-packages',exists=True)
        actual=set()
        for path in target.rglob('*'):
            rt.require(not path.is_symlink(),'SDK_COPY_LINK')
            if path.is_file():actual.add(str(path.relative_to(target)))
            else:rt.require(path.is_dir(),'SDK_COPY_SPECIAL')
        rt.require(actual==set(payload),'SDK_COPY_MEMBER_SET')
        for relative,data in payload.items():
            path=rt.boundary(target/relative,target,exists=True)
            rt.require(path.read_bytes()==data,'SDK_COPY_DRIFT')
    rt.require(receipt==expected,'SDK_COPY_RECEIPT_DRIFT')


def restore_command(m):
    """OS边界先拒绝所有网络，再允许锁定本地恢复；SDK解析不能绕过。"""
    rt.require(sys.platform=='darwin' and Path('/usr/bin/sandbox-exec').is_file(),'OFFLINE_OS_BOUNDARY_UNAVAILABLE')
    return rt.offline_command([DOTNET,'restore',str(rt.ROOT/'backend/OntologyPlatform.slnx'),'--locked-mode','--configfile',str(rt.ARTIFACTS/m['runId']/'offline-nuget.config'),'-p:NuGetAudit=false','--disable-parallel','--disable-build-servers','-m:1','--verbosity','diagnostic'])


def recovery_environment(m):
    """诊断日志只继承显式工具环境，杜绝打印宿主秘密。"""
    env=rt.environment(m['runId'])
    return {k:v for k,v in env.items() if k.startswith(('DOTNET_','NUGET_','MSBUILD')) or k in ('PATH','LANG','LC_ALL','TMPDIR','TMP','TEMP')}


def recovery_command(m,command):
    """内核禁止网络及全局写入，只允许本Run和21项目obj写入。"""
    wrapped=rt.offline_command(command)
    writable=[rt.ARTIFACTS/rt.run_id(m['runId']),rt.run_temp(m['runId'])]+[rt.ROOT/Path(r['project']).parent/'obj' for r in lock_inventory()]
    for p in writable:rt.boundary(p,rt.ROOT)
    wrapped[2]+=' (deny file-write*) (allow file-write* (literal "/dev/null") '+ ' '.join('(subpath '+json.dumps(str(p))+')' for p in writable)+')'
    wrapped[2]+=' (deny file-read* (subpath "/Users/chasen/.nuget/packages"))'
    return wrapped


def sdk_resolution(m,tag):
    """真实SDK属性解析必须显示当前Run的两个私有SDK。"""
    verify_feed(m);verify_sdk_copies(m);rows=[]
    projects={'Aspire.AppHost.Sdk':'backend/src/AppHost/OntologyPlatform.AppHost.csproj','MSTest.Sdk':'backend/tests/OntologyPlatform.ConnectionsTests/OntologyPlatform.ConnectionsTests.csproj'}
    for name,project in projects.items():
        output=rt.ARTIFACTS/m['runId']/(tag+'-'+name.split('.')[0].lower()+'-imports.xml')
        rt.require(not output.exists(),'EXISTING_SDK_IMPORT_EVIDENCE')
        command=recovery_command(m,[DOTNET,'msbuild',str(rt.ROOT/project),'-nologo','-preprocess:'+str(output),'-nodeReuse:false'])
        raw=rt.execute(m,tag+'-'+name.split('.')[0].lower(),command,env=recovery_environment(m),timeout=60)
        target,_,_=sdk_payload(name,m);imports=output.read_text()
        expected=[str(target/'Sdk'/filename) for filename in ('Sdk.props','Sdk.targets')]
        rt.require(all(p in imports for p in expected),'SDK_RESOLVED_OUTSIDE_RUN')
        rt.require('/usr/local/share/dotnet/sdk/10.0.402/Sdks/Microsoft.NET.Sdk/Sdk/Sdk.props' in imports,'BUILTIN_SDK_DRIFT')
        rows.append({'name':name,'version':SDK_ARCHIVES[name][0],'resolvedSdkImports':expected,'preprocessSha256':rt.digest(output.read_bytes()),'preprocessPath':str(output)})
    return rows


def require_reviewer(m,stage):
    """独立审查原文及绑定由Master落盘，不由工具自授PASS。"""
    path=rt.ARTIFACTS/m['runId']/('review-'+stage+'.json')
    rt.require(path.is_file(),'REVIEW_REQUIRED_'+stage);v=json.loads(path.read_text())
    rt.require(v.get('status')=='PASS' and v.get('reviewer') not in (None,'','/root') and v.get('rawReview') and v.get('drivers')==m['drivers'] and v.get('testedCommit')==m['_head'],'REVIEW_BINDING_'+stage)
    rt.require(v.get('taskId')==rt.TASK and v.get('runId')==m['runId'] and v.get('manifestSha256')==m['_sha256'],'REVIEW_RUN_BINDING')
    if stage=='R2':
        expected={name:rt.digest((path.parent/name).read_bytes()) for name in ('gate-R2.json','restore-result.json','restore-provenance.json')}
        rt.require(v.get('evidenceHashes')==expected,'REVIEW_RESULT_BINDING')


def verify_empty_restore_cache(m):
    """完整恢复前只允许已逐字节检查的两个SDK，不消费预置普通包。"""
    packages=rt.boundary(rt.ARTIFACTS/rt.run_id(m['runId'])/'nuget-packages',rt.ARTIFACTS,exists=True)
    rt.require({p.name for p in packages.iterdir()}=={name.lower() for name in SDK_ARCHIVES},'PREPOPULATED_PACKAGE_CACHE')
    verify_sdk_copies(m)


def verify_restored_package(package,entry,archive,expected_sha):
    """恢复文件逐字节回绑已审归档，元数据不能替代实际payload。"""
    raw=archive.read_bytes();rt.require(rt.digest(raw)==expected_sha,'RESTORE_ARCHIVE_DRIFT')
    rt.require((package/archive.name).read_bytes()==raw,'RESTORED_NUPKG_DRIFT')
    metadata=json.loads((package/'.nupkg.metadata').read_text())
    rt.require(metadata['source']==str(archive.parent) and metadata['contentHash']==entry['sha512'],'PACKAGE_PROVENANCE')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members={str(Path(i.filename)).casefold():i for i in z.infolist() if not i.is_dir()}
        rt.require(all(not Path(i.filename).is_absolute() and '..' not in Path(i.filename).parts for i in z.infolist()),'RESTORED_ARCHIVE_PATH')
        rt.require(len(members)==sum(not i.is_dir() for i in z.infolist()),'RESTORED_ARCHIVE_CASE_COLLISION')
        for relative in entry['files']:
            item=rt.boundary(package/relative,package,exists=True)
            rt.require(item.is_file() and item.stat().st_nlink==1,'PACKAGE_FILE_BOUNDARY')
            if relative=='.nupkg.metadata':continue
            if relative==archive.name+'.sha512':expected=base64.b64encode(hashlib.sha512(raw).digest())
            else:
                rt.require(relative.casefold() in members,'RESTORED_MEMBER_UNBOUND');expected=z.read(members[relative.casefold()])
            rt.require(item.read_bytes()==expected,'RESTORED_PAYLOAD_DRIFT')
    actual=set()
    for p in package.rglob('*'):
        rt.require(not p.is_symlink(),'RESTORED_LINK')
        if p.is_file():actual.add(str(p.relative_to(package)))
    rt.require(actual==set(entry['files'])|{archive.name,'.nupkg.metadata'},'RESTORED_MEMBER_SET')


def verify_assets(m):
    """逐项目资产只接受本Run包目录、唯一源、唯一配置和完整锁内容。"""
    a=rt.ARTIFACTS/m['runId'];packages=a/'nuget-packages';feed=a/'nuget-feed';rows=[];all_packages=set();checked=set();approved=approved_archives();locks=locked_packages()
    for project in lock_inventory():
        path=rt.ROOT/Path(project['project']).parent/'obj/project.assets.json'
        rt.require(path.is_file(),'PROJECT_RESTORE_SKIPPED')
        v=json.loads(path.read_text());restore=v['project']['restore']
        rt.require(set(v['packageFolders']) in ({str(packages)},{str(packages)+'/'}),'ASSET_PACKAGE_SOURCE')
        rt.require(set(restore['sources'])=={str(feed)} and restore['configFilePaths']==[str(a/'offline-nuget.config')],'ASSET_CONFIG_SOURCE')
        rt.require(not restore.get('fallbackFolders') and not any(x.get('level')=='Error' for x in v.get('logs',[])),'ASSET_RESTORE_ERROR')
        actual={k.lower():x for k,x in v['libraries'].items() if x['type']=='package'}
        expected=set().union(*[set(x) for x in project['frameworks'].values()])
        rt.require(set(actual)==expected,'ASSET_LOCK_COVERAGE')
        for key,entry in actual.items():
            rt.require(entry['sha512']==locks[key],'ASSET_CONTENT_HASH')
            package=rt.boundary(packages/entry['path'],packages,exists=True)
            metadata=json.loads((package/'.nupkg.metadata').read_text())
            rt.require(metadata['source']==str(feed) and metadata['contentHash']==entry['sha512'],'PACKAGE_PROVENANCE')
            if key not in checked:
                name,version=key.split('/');verify_restored_package(package,entry,feed/(name+'.'+version+'.nupkg'),approved[key]['archiveSha256']);checked.add(key)
        all_packages.update(actual)
        rows.append({'project':project['project'],'assetsSha256':rt.digest(path.read_bytes()),'packages':sorted(actual),'restore':restore})
    rt.require(all_packages==set(locked_packages()),'SOLUTION_PACKAGE_COVERAGE')
    return rows


def strict_restore(m):
    """单次可见R2：原始双流、PID、环境和内核边界均绑定新T。"""
    import datetime,signal
    require_reviewer(m,'R1');verify_feed(m);verify_empty_restore_cache(m)
    a=rt.ARTIFACTS/m['runId'];before=sdk_resolution(m,'r2-sdk-before')
    incident=closeout.tool_tree(rt.ROOT/'.tools/dotnet-home')['fingerprint']
    command=recovery_command(m,restore_command(m)[3:]);env=recovery_environment(m)
    stdout=a/'restore-stdout.txt';stderr=a/'restore-stderr.txt'
    rt.require(not stdout.exists() and not stderr.exists(),'EXISTING_RESTORE')
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
    with stdout.open('xb') as out,stderr.open('xb') as err:
        process=subprocess.Popen(command,cwd=rt.ROOT,env=env,stdout=out,stderr=err,start_new_session=True)
        rt.write_json(a/'restore-start.json',{'pid':process.pid,'command':command,'environment':env,'testedCommit':m['_head'],'runId':m['runId'],'manifestSha256':m['_sha256'],'startedAtUtc':start})
        print(json.dumps({'stage':'R2_RESTORE_STARTED','pid':process.pid,'stdout':str(stdout),'stderr':str(stderr)}),flush=True)
        try:code=process.wait(timeout=600)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            finally:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            code=process.returncode
            rt.write_json(a/'restore-interrupted.json',{'pid':process.pid,'exitCode':code,'startedAtUtc':start,'elapsedSeconds':time.monotonic()-tick,'timingStatus':'OBSERVED','stdoutSha256':rt.digest(stdout.read_bytes()),'stderrSha256':rt.digest(stderr.read_bytes())})
            raise
    text=stdout.read_text(errors='replace')+'\n'+stderr.read_text(errors='replace')
    attempts=re.findall(r'(?im)^.*(?:\b(?:GET|POST|CACHE) https?://|NU1101|NU1301|Permission denied|Operation not permitted|网络不可达|无法加载.*服务索引).*$' ,text)
    same=closeout.tool_tree(rt.ROOT/'.tools/dotnet-home')['fingerprint']==incident
    row={'exitCode':code,'pid':process.pid,'startedAtUtc':start,'endedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsedSeconds':time.monotonic()-tick,'timingStatus':'OBSERVED','stdoutSha256':rt.digest(stdout.read_bytes()),'stderrSha256':rt.digest(stderr.read_bytes()),'networkOrRestoreDiagnostics':attempts,'incidentUnchanged':same,'osNetworkPolicy':'DENY_ALL','globalWritePolicy':'DENY_EXCEPT_RUN_AND_PROJECT_OBJ','historicalActualNetworkBytes':'NOT_VERIFIED','operatorStopRequested':(a/'restore-stop-request.json').exists()}
    rt.write_json(a/'restore-result.json',row)
    rt.require(code==0 and not attempts and same and not row['operatorStopRequested'],'STRICT_RESTORE_FAILED')
    assets=verify_assets(m);after=sdk_resolution(m,'r2-sdk-after');verify_feed(m);verify_sdk_copies(m)
    rt.write_json(a/'restore-provenance.json',{'sdkBefore':before,'sdkAfter':after,'assets':assets,'httpCacheFiles':[str(p.relative_to(a)) for p in (a/'nuget-http-cache').rglob('*') if p.is_file()]})
    return {'status':'PASS','scope':'OFFLINE_RESTORE_PASS_WITH_OS_NETWORK_DENY','projects':len(assets),'packages':len(locked_packages()),'exitCode':code,'networkObservationLimit':'Kernel denies network; diagnostic matching is finite, not a historical byte measurement'}


def approved_archives():
    """原提交中的已审归档身份，与当前完整锁集合逐项相等。"""
    path='docs/evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-02/all-platform-lock-content.json'
    raw=subprocess.check_output(['git','show','00c6f472c40bbe75d7b577a6144ca6046221a5d4:'+path],cwd=rt.ROOT)
    rows=json.loads(raw)['packages'];result={r['package']:r for r in rows}
    rt.require(len(result)==len(rows) and {k:v['contentHash'] for k,v in result.items()}==locked_packages(),'APPROVED_LOCK_COVERAGE')
    return result


def verify_feed(m):
    """拒绝空证据、额外源、包替换及链接；不回退共享缓存。"""
    import xml.etree.ElementTree as ET
    a=rt.boundary(rt.ARTIFACTS/rt.run_id(m['runId']),rt.ARTIFACTS,exists=True)
    feed=rt.boundary(a/'nuget-feed',a,exists=True);rows=approved_archives()
    expected={key.split('/')[0]+'.'+key.split('/')[1]+'.nupkg':row for key,row in rows.items()}
    rt.require({p.name for p in feed.iterdir()}==set(expected),'FEED_MEMBER_SET')
    for name,row in expected.items():
        p=rt.boundary(feed/name,feed,exists=True)
        rt.require(p.is_file() and p.stat().st_nlink==1 and rt.digest(p.read_bytes())==row['archiveSha256'],'FEED_ARCHIVE_DRIFT')
    receipt=json.loads((a/'nuget-archive-copies.json').read_text())
    rt.require(sorted(receipt,key=lambda r:r['package'])==sorted([{'package':k,'archiveSha256':v['archiveSha256']} for k,v in rows.items()],key=lambda r:r['package']),'FEED_RECEIPT_DRIFT')
    config=ET.parse(rt.boundary(a/'offline-nuget.config',a,exists=True)).getroot()
    expected_config=ET.fromstring('<configuration><packageSources><clear/><add key="approved-local" value="PLACEHOLDER"/></packageSources><packageSourceMapping><clear/><packageSource key="approved-local"><package pattern="*"/></packageSource></packageSourceMapping></configuration>')
    expected_config.find('packageSources/add').set('value',str(feed))
    def shape(node):return (node.tag,sorted(node.attrib.items()),(node.text or '').strip(),[shape(child) for child in node])
    rt.require(shape(config)==shape(expected_config),'OFFLINE_SOURCE_CONFIG')


def lock_inventory():
    """从solution项目及各TFM/RID锁生成完整覆盖，不以固定计数替代。"""
    import xml.etree.ElementTree as ET
    solution=rt.ROOT/'backend/OntologyPlatform.slnx';rows=[]
    for node in ET.parse(solution).iter('Project'):
        project=rt.boundary(solution.parent/node.attrib['Path'],rt.ROOT/'backend',exists=True)
        locks=[p for p in sorted(project.parent.glob('packages*.lock.json')) if p.name in ('packages.lock.json','packages.osx-arm64.lock.json')]
        rt.require(len(locks)==1,'PROJECT_LOCK_COVERAGE')
        lock=locks[0];value=json.loads(lock.read_text())
        rows.append({'project':str(project.relative_to(rt.ROOT)),'projectSha256':rt.digest(project.read_bytes()),'lock':str(lock.relative_to(rt.ROOT)),'lockSha256':rt.digest(lock.read_bytes()),'frameworks':{k:sorted(n.lower()+'/'+v['resolved'] for n,v in entries.items() if 'resolved' in v and 'contentHash' in v) for k,entries in value['dependencies'].items()}})
    rt.require(rows,'EMPTY_SOLUTION');return rows


def prepare_nuget(m):
    """每Run全新本地feed和SDK缓存；不触碰历史CLI事件目录。"""
    d=rt.ROOT/'.tools';d.mkdir(exist_ok=True)
    source=Path('/Users/chasen/.nuget/packages')
    packages=locked_packages()
    approved=approved_archives()
    rt.write_json(rt.ARTIFACTS/m['runId']/'lock-inventory.json',{'projects':lock_inventory(),'requiredPackages':sorted(packages),'approvedIntersection':sorted(set(packages)&set(approved)),'missing':sorted(set(packages)-set(approved)),'superset':sorted(set(approved)-set(packages))})
    # NuGet签名包GetContentHash不是完整ZIP的SHA512。使用SDK本身校验，保留两种散列。
    env=rt.environment(m['runId'])
    for key in ('DOTNET_CLI_HOME','NUGET_PACKAGES','NUGET_HTTP_CACHE_PATH','NUGET_SCRATCH','TMPDIR'):
        allowed=rt.run_temp(m['runId']) if key=='TMPDIR' else rt.ARTIFACTS/m['runId']
        target=rt.boundary(env[key],allowed);target.mkdir(parents=True,exist_ok=False)
    env['G4_PACKAGE_EXPECTATIONS']=json.dumps(packages)
    command=r'''[Reflection.Assembly]::LoadFrom('/usr/local/share/dotnet/sdk/10.0.402/NuGet.Packaging.dll') | Out-Null
$expected=$env:G4_PACKAGE_EXPECTATIONS | ConvertFrom-Json -AsHashtable
$rows=@(); foreach($entry in $expected.GetEnumerator()) {
 $parts=$entry.Key.Split('/'); $file='/Users/chasen/.nuget/packages/'+$entry.Key+'/'+$parts[0]+'.'+$parts[1]+'.nupkg'
 if(!(Test-Path -LiteralPath $file)){throw 'OFFLINE_PACKAGE_MISSING'}
 $reader=[NuGet.Packaging.PackageArchiveReader]::new($file)
 try {$actual=$reader.GetContentHash([Threading.CancellationToken]::None,$null)} finally {$reader.Dispose()}
 if($actual -cne $entry.Value){throw 'LOCKED_CONTENT_MISMATCH'}
 $rows+=@{package=$entry.Key;contentHash=$actual;archiveSha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
}; $rows | ConvertTo-Json -Depth 3'''
    verified_raw=rt.execute(m,'nuget-content-hash',rt.offline_command(['pwsh','-NoProfile','-Command',command]),env=env)
    verified_archives={row['package']:row['archiveSha256'] for row in json.loads(verified_raw)}
    rt.require(verified_archives=={key:row['archiveSha256'] for key,row in approved.items()},'GLOBAL_ARCHIVE_POLLUTION')
    rt.require(shutil.disk_usage(rt.ROOT).free>8*1024**3,'DISK_HEADROOM')
    feed=rt.boundary(rt.ARTIFACTS/m['runId']/'nuget-feed',rt.ARTIFACTS/m['runId'])
    rt.require(not feed.exists(),'EXISTING_TOOL_COPY');feed.mkdir()
    archive_rows=[]
    for key in packages:
        name,version=key.split('/');archive=source/key/(name+'.'+version+'.nupkg')
        target=feed/archive.name;shutil.copyfile(archive,target)
        rt.require(rt.digest(target.read_bytes())==verified_archives[key],'NUGET_COPY_DRIFT')
        archive_rows.append({'package':key,'archiveSha256':rt.digest(target.read_bytes())})
    rt.write_json(rt.ARTIFACTS/m['runId']/'nuget-archive-copies.json',archive_rows)
    prepare_sdk_copies(m)
    from xml.sax.saxutils import quoteattr
    config=rt.ARTIFACTS/m['runId']/'offline-nuget.config'
    rt.require(not config.exists(),'EXISTING_OFFLINE_CONFIG')
    config.write_text('<configuration><packageSources><clear/><add key="approved-local" value='+quoteattr(str(feed))+'/></packageSources><packageSourceMapping><clear/><packageSource key="approved-local"><package pattern="*"/></packageSource></packageSourceMapping></configuration>')
    verify_feed(m);verify_sdk_copies(m)


def relocate_workspace_state(state,source,target,manifests):
    """仅重定位两个已核验项目，丢弃旧缓存证明，由pnpm原强门禁重新验证。"""
    rt.require(set(manifests)=={'','/apps/web'} and state.get('projects')=={source+p:v for p,v in manifests.items()},'WORKSPACE_COPY_PROJECTS')
    rt.require(state.get('pnpmfiles')==[] and state.get('filteredInstall') is False and isinstance(state.get('settings'),dict),'WORKSPACE_COPY_HOOK_OR_PARTIAL')
    value=json.loads(json.dumps(state));value['projects']={target+p:v for p,v in manifests.items()}
    value['lastValidatedTimestamp']=0;value.pop('validation',None)
    return value


def prepare_tools(m):
    """已有锁定Web/Python制品独立复制，不运行install。"""
    d=rt.ROOT/'.tools';d.mkdir(exist_ok=True)
    rows=json.loads((rt.ARTIFACTS/'three-file-apply-20261103-01/private-cache-copy.json').read_text())['pyyamlFiles']
    source=Path('/Users/chasen/Developer/repos/ontology-platform/.tools/pythonlibs')
    rt.require(len(rows)==26 and not (d/'pythonlibs').exists(),'PYYAML_COPY_BOUNDARY')
    for row in rows:
        p=source/row['path'];rt.require(p.is_file() and not p.is_symlink() and rt.digest(p.read_bytes())==row['sha256'],'PYYAML_INPUT')
        dest=d/'pythonlibs'/row['path'];dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(p.read_bytes());dest.chmod(0o444)
    rt.execute(m,'pyyaml-import',['python3','-B','-c',"import yaml,pathlib; assert yaml.__version__=='6.0.3'; assert pathlib.Path(yaml.__file__).resolve().is_relative_to(pathlib.Path('.tools/pythonlibs').resolve()); print(yaml.__version__)"])
    web=Path('/Users/chasen/.codex/worktrees/g3-m5-review-fix/ontology-platform')
    for p in ('package.json','apps/web/package.json','pnpm-lock.yaml','pnpm-workspace.yaml'):
        rt.require((web/p).read_bytes()==(rt.ROOT/p).read_bytes(),'WEB_CACHE_LOCK_DRIFT')
    cache_rows=verify_web_cache(web)
    rt.write_json(rt.ARTIFACTS/m['runId']/'web-cache-files.json',cache_rows)
    for rel in ('node_modules','apps/web/node_modules','.tools/pnpm/package'):
        dest=rt.ROOT/rel;rt.require(not dest.exists(),'EXISTING_WEB_COPY')
        dest.parent.mkdir(parents=True,exist_ok=True)
        rt.execute(m,'copy-'+rel.replace('/','-').replace('.',''),['/bin/cp','-cR',str(web/rel),str(dest)])
    for row in cache_rows:
        for entry in row['files']:
            rt.require(hashlib.sha512((rt.ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha512'],'WEB_COPY_DRIFT')
    admission=json.loads((rt.ROOT/'docs/evidence/G4-M1-MAIN-INTEGRATION-001/p0/tools-admission.json').read_text())['pnpm']
    archive=Path(admission['archive'])
    rt.require('sha512-'+base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()==admission['integrity'],'PNPM_ARCHIVE')
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.isfile():
                rt.require('..' not in Path(member.name).parts and member.name.startswith('package/'),'PNPM_MEMBER')
                rt.require((d/'pnpm'/member.name).read_bytes()==tar.extractfile(member).read(),'PNPM_FILE_DRIFT')
    rebased=[]
    allowed_bins={(b['name'],b['path']) for row in cache_rows for b in row['bins']}
    for directory in (rt.ROOT/'node_modules',rt.ROOT/'apps/web/node_modules'):
        for path in directory.rglob('*'):
            if path.is_symlink():
                target=os.readlink(path)
                if target.startswith(str(web)):
                    path.unlink();path.symlink_to(target.replace(str(web),str(rt.ROOT),1))
                rt.require(path.resolve().is_relative_to(rt.ROOT) and path.exists(),'CACHE_LINK_ESCAPE')
            elif path.is_file() and '/.bin/' in str(path):
                raw=path.read_bytes()
                match=re.search(r'^# cmd-shim-target=(.+)$',raw.decode(),re.MULTILINE)
                rt.require(match,'SHIM_TARGET_MISSING')
                original=Path(match[1]).resolve()
                rt.require(original.is_relative_to(web),'SHIM_TARGET_ESCAPE')
                relative=str(original.relative_to(web))
                rt.require((path.name,relative) in allowed_bins,'SHIM_UNDECLARED_BIN')
                target=rt.ROOT/relative
                rt.require(target.read_bytes().startswith(b'#!/usr/bin/env node'),'SHIM_NON_NODE_BIN')
                after=('#!/bin/sh\nexec '+shlex.quote(NODE)+' '+shlex.quote(str(target))+' "$@"\n').encode()
                path.write_bytes(after);path.chmod(0o755)
                rebased.append({'path':str(path.relative_to(rt.ROOT)),'before':rt.digest(raw),'after':rt.digest(after),'target':relative,'method':'deterministic shim from integrity-bound package bin declaration'})
    state_path=rt.ROOT/'node_modules/.pnpm-workspace-state-v1.json'
    original=(web/'node_modules/.pnpm-workspace-state-v1.json').read_bytes()
    rt.require(state_path.read_bytes()==original,'WORKSPACE_COPY_STATE_DRIFT')
    manifests={}
    for rel in ('','/apps/web'):
        manifest=json.loads((rt.ROOT/(rel.lstrip('/')+'/package.json' if rel else 'package.json')).read_text())
        manifests[rel]={k:manifest[k] for k in ('name','version') if k in manifest}
    moved=relocate_workspace_state(json.loads(original),str(web),str(rt.ROOT),manifests)
    state_path.write_text(json.dumps(moved,ensure_ascii=False,indent=2)+'\n')
    workspace={'path':str(state_path.relative_to(rt.ROOT)),'beforeSha256':rt.digest(original),'afterSha256':rt.digest(state_path.read_bytes()),'method':'exact project root relocation; discard cached validation; force actual pnpm verifyDepsBeforeRun=error; no install'}
    rt.write_json(rt.ARTIFACTS/m['runId']/'tool-copies.json',{'pyyaml':rows,'shimRebases':rebased,'workspaceState':workspace,'download':0,'install':0})
    rt.execute(m,'pnpm-version',[NODE,str(d/'pnpm/package/bin/pnpm.cjs'),'--version'])
    rt.execute(m,'pnpm-workspace-validation',rt.offline_command([NODE,str(d/'pnpm/package/bin/pnpm.cjs'),'--config.verifyDepsBeforeRun=error','--dir','apps/web','run','lint','--help']),timeout=30)
    rt.write_json(rt.ARTIFACTS/m['runId']/'workspace-state-validated.json',{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'sha256':rt.digest(state_path.read_bytes()),'validatedBy':'actual unchanged pinned pnpm verifyDepsBeforeRun=error; eslint help is not lint PASS'})


def engineering(m):
    """真实原样完整入口；离线恢复先行，实际skip不被掩盖。"""
    require_gate(m,'R2')
    require_reviewer(m,'R2')
    verify_sdk_copies(m)
    rt.execute(m,'selftest',rt.offline_command(['pwsh','-NoProfile','-File','scripts/verify.ps1','-SelfTest'],loopback=True),timeout=1800)
    rt.execute(m,'task-tests',['python3','-B',str(rt.HERE/'tests.py')],timeout=120)
    solution=rt.ROOT/'backend/OntologyPlatform.slnx'
    rt.require(solution.is_file(),'SOLUTION')
    raw=rt.execute(m,'native-web',rt.offline_command(['pwsh','-NoProfile','-File','scripts/verify.ps1','-RunNative','-RunTests'],loopback=True),timeout=1800)
    text=raw.decode(errors='replace')
    skips=re.findall(r'(?:已跳过|Skipped)\s+([^\r\n]+)',text,re.IGNORECASE)
    cases=[]
    for project in sorted((rt.ROOT/'backend/tests').glob('*/*.csproj')):
        suffix=project.stem.removeprefix('OntologyPlatform.')
        dll=project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
        tag='baseline-'+suffix
        raw=rt.execute(m,tag,rt.offline_command([DOTNET,str(dll),'--minimum-expected-tests','1','--no-ansi','--output','Detailed','--results-directory',str(rt.ARTIFACTS/m['runId']/'test-results'/tag)],loopback=True),timeout=300)
        cases.append(rt.test_projection(m,tag,suffix,raw))
    rt.write_json(rt.ARTIFACTS/m['runId']/'build-inputs.json',{'testedCommit':m['_head'],'files':rt.build_fingerprint()})
    return {'status':'PARTIAL','nativeAndWebExitCode':0,'skipped':skips,'caseSummaries':{r['project']:r['summary'] for r in cases},'fixtureClosureRequired':True}


def contracts(m):
    """真实DLL导出及真实生成器的隔离再生；失败不修改生成物。"""
    rt.check_build(m)
    output=rt.ARTIFACTS/m['runId']/'g4-export.json'
    rt.require(not output.exists(),'EXISTING_EXPORT')
    rt.execute(m,'openapi-export',rt.offline_command([DOTNET,str(rt.ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll'),'--export-g4-openapi',str(output)],loopback=True),timeout=30)
    raw=rt.execute(m,'contract-chain',rt.offline_command([NODE,str(rt.HERE/'contract-check.mjs'),'--runtime-openapi',str(output),'--output',str(rt.ARTIFACTS/m['runId']/'regenerated')]),timeout=30)
    return json.loads(raw)


def consumer(m, name, *, scenario=None):
    """消费者先验证绑定，再开始本任务唯一输出，不接受自定义命令。"""
    rt.require(name in ('http','browser','fault','g3-compatibility'),'CONSUMER')
    rt.check_build(m)
    if scenario:rt.update_runtime(m,**({'scenario':scenario} if name=='browser' else {'httpScenario':scenario}))
    tag=name+'-'+(scenario or 'baseline')
    command=[NODE,str(rt.HERE/(name+'.mjs')),*binding(m),'--runtime-file',str(rt.private_dir(m['runId'])/'runtime.json')]
    command+=['--evidence-dir',str(rt.ARTIFACTS/m['runId']/tag)]
    raw=rt.execute(m,tag,command,timeout=900,sensitive=True,allowed_codes=(0,2) if name in ('http','browser') else (0,))
    receipt=json.loads((rt.ARTIFACTS/m['runId']/'commands'/(tag+'.json')).read_text())
    return {'consumer':name,'scenario':scenario or 'baseline','exitCode':receipt['exitCode'],'stdoutSha256':rt.digest(raw)}


def gate_path(m, gate):
    return rt.ARTIFACTS/m['runId']/('gate-'+gate+'.json')


def require_gate(m, gate, *, partial=False):
    path=gate_path(m,gate);rt.require(path.is_file(),'PREREQUISITE_'+gate)
    value=json.loads(path.read_text())
    closure=path.with_name('gate-'+gate+'-closure.json')
    if closure.is_file():value=json.loads(closure.read_text())
    rt.require(value['testedCommit']==m['_head'] and value['manifestSha256']==m['_sha256'],'GATE_INPUT_DRIFT')
    rt.require(value['result']['status'] in (('PASS','PARTIAL') if partial else ('PASS',)),'PREREQUISITE_NOT_PASS_'+gate)
    return value


def close_fixture_cases(m):
    """历史260与本轮全部跳过逐案取并集；原始Detailed日志重新解析防投影伪造。"""
    historical=rt.ROOT/'docs/evidence/G4-M1-MAIN-INTEGRATION-001/three-file-apply-20261103-01/skipped-cases.json'
    old=json.loads((rt.ROOT/'docs/evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-01/required-skip-closure-plan.json').read_text())
    rt.require(rt.digest(historical.read_bytes())==old['historicalSha256'],'HISTORICAL_CASE_BINDING')
    def identity(name):
        match=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_.]*)(.*)',name)
        rt.require(match,'TEST_CASE_NAME');return match[1].rsplit('.',1)[-1]+match[2]
    required={(r['project'],identity(r['case'])) for r in old['cases']};passed={};baselines=set();proofs=[];baseline_counts={}
    for path in sorted((rt.ARTIFACTS/m['runId']/'case-projections').glob('*.json')):
        value=json.loads(path.read_text());tag=value['command'];project=value['project']
        rt.require(value['taskId']==rt.TASK and value['runId']==m['runId'] and value['testedCommit']==m['_head'],'CASE_RUN_BINDING')
        receipt=rt.ARTIFACTS/m['runId']/'commands'/(tag+'.json');observed=json.loads(receipt.read_text())
        log=(rt.private_dir(m['runId'])/'logs' if observed['logVisibility']=='PRIVATE' else receipt.parent)/(tag+'.log')
        raw=log.read_bytes();parsed=rt.parse_test_cases(raw.decode(errors='replace'))
        rt.require(observed['testedCommit']==m['_head'] and observed['manifestSha256']==m['_sha256'] and observed['exitCode']==0 and rt.digest(raw)==value['rawLogSha256']==observed['logSha256'] and rt.digest(receipt.read_bytes())==value['commandReceiptSha256'],'CASE_LOG_BINDING')
        rt.require(parsed['cases']==value['cases'] and parsed['summary']==value['summary'],'CASE_PROJECTION_DRIFT')
        assembly=rt.ROOT/f'backend/tests/OntologyPlatform.{project}/bin/Debug/net10.0/OntologyPlatform.{project}.dll'
        rt.require(value['assemblySha256']==rt.digest(assembly.read_bytes()),'CASE_ASSEMBLY_DRIFT')
        if tag.startswith('baseline-'):
            baselines.add(project)
            for row in value['cases']:
                key=(project,identity(row['case']));baseline_counts[key]=baseline_counts.get(key,0)+1
        for row in value['cases']:
            key=(project,identity(row['case']))
            if tag.startswith('baseline-') and row['status']=='SKIP':required.add(key)
            if row['status']=='PASS' and sum(identity(other['case'])==key[1] for other in value['cases'])==1:passed.setdefault(key,[]).append({'command':tag,'projectionSha256':rt.digest(path.read_bytes()),'rawLogSha256':value['rawLogSha256'],'line':row['line']})
    expected={p.stem.removeprefix('OntologyPlatform.') for p in (rt.ROOT/'backend/tests').glob('*/*.csproj')}
    rt.require(baselines==expected,'BASELINE_PROJECT_SET')
    public={'pg-empty-public','pg-public-relation','pg-public-function','pg-public-type','pg-public-missing','pg-public-usage','pg-public-restored'}
    for key in sorted(required):
        rt.require(baseline_counts.get(key)==1,'AMBIGUOUS_OR_MISSING_BASELINE_CASE_REQUIRES_CLASS_EVIDENCE')
        witnesses=passed.get(key,[])
        if key==('ConnectionsTests','ExactPublicSchemaBoundaryUsesActualCatalog'):
            rt.require(public<={w['command'] for w in witnesses},'PUBLIC_SEVEN_SCENARIOS_REQUIRED')
        proofs.append({'project':key[0],'case':key[1],'applicability':'REQUIRED','status':'PASS' if witnesses else 'NOT_RUN','witnesses':witnesses})
    result={'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'historicalCases':len(old['cases']),'requiredCases':len(required),'closedCases':sum(bool(x['witnesses']) for x in proofs),'cases':proofs}
    rt.write_json(rt.ARTIFACTS/m['runId']/'fixture-case-closure.json',result)
    rt.require(result['closedCases']==result['requiredCases'],'APPLICABLE_CASES_NOT_CLOSED')
    return result


def main():
    """唯一参数合同；重复/任意TaskId和非法门禁均拒绝。"""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate',required=True,choices=('R2','PREFLIGHT','I01','I02','I03','I04','I05','I06','I07','I08'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--resource-manifest',required=True)
    args=parser.parse_args()
    rt.require(len(sys.argv)==9 and len(set(sys.argv[1::2]))==4,'EXACT_ARGUMENT_SET')
    m=rt.load_manifest(args.resource_manifest,args.run_id,args.expected_head)
    rt.require(not gate_path(m,args.gate).exists(),'EXISTING_GATE_RECEIPT')
    try:
        if args.gate=='R2':
            result=strict_restore(m)
        elif args.gate=='PREFLIGHT':
            require_gate(m,'R2');require_reviewer(m,'R2')
            rt.verify_engine(m)
            groups=consumer_check.check_all(m)
            prepare_tools(m)
            result={'status':'PASS','groups':groups,'resourcesStarted':False}
        elif args.gate=='I01':
            require_gate(m,'PREFLIGHT');result=engineering(m)
        elif args.gate=='I05':
            require_gate(m,'I01',partial=True);result=contracts(m)
        elif args.gate=='I03':
            require_gate(m,'I05');rt.check_build(m)
            result=module('startup-boundary').rejection_cases(m)
            result['hostGraph']=module('startup-boundary').graph_cases(m)
            result['status']='PARTIAL';result['rejectionPathsPassed']=True
        elif args.gate=='I02':
            v=require_gate(m,'I03',partial=True);rt.require(v['result'].get('rejectionPathsPassed'),'STARTUP_REJECTION_NOT_PASSED')
            rt.runtime_value(m)
            rt.start_group(m,'g3',modules=True)
            results=module('module-tests').run_modules(m)
            closeout.reclaim(m,'modules',apply=True)
            rt.require(all(x['status']=='PASS' for x in results),'MODULE_SKIP_NOT_CLOSED')
            rt.start_group(m,'g3');compat=consumer(m,'g3-compatibility')
            fixture_tests=module('module-tests').g3_fixture_tests(m)
            result={'status':'PASS','modules':results,'compatibility':compat,'securityAndManifest':fixture_tests}
        elif args.gate=='I04':
            require_gate(m,'I02')
            result=module('migration-boundary').verify_all(m)
        elif args.gate=='I06':
            require_gate(m,'I04');result=module('readback').lifecycle_and_faults(m)
            original=require_gate(m,'I01',partial=True);modules=require_gate(m,'I02')['result']['modules']
            rt.require(original['result']['nativeAndWebExitCode']==0 and all(x['status']=='PASS' for x in modules),'NATIVE_FIXTURE_CLOSURE')
            rt.require(sum(x['total'] for x in result['pgGroups'] if x['category']=='RealPgFixture')>=12 and any(x['category']=='RealPgWrongSanFixture' for x in result['pgGroups']) and any(x['category']=='RealPgPublicFixture' for x in result['pgGroups']),'PG_FIXTURE_CLOSURE')
            close_fixture_cases(m)
            for gate in ('I01','I03'):
                rt.write_json(gate_path(m,gate).with_name('gate-'+gate+'-closure.json'),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'manifestSha256':m['_sha256'],'result':{'status':'PASS','originalReceiptSha256':rt.digest(gate_path(m,gate).read_bytes()),'closureInputs':{'I02':rt.digest(gate_path(m,'I02').read_bytes()),'I04':rt.digest(gate_path(m,'I04').read_bytes()),'pgSecurity':rt.digest((rt.ARTIFACTS/m['runId']/'pg-security.json').read_bytes())},'historicalSkipsRetained':True}})
        elif args.gate=='I07':
            require_gate(m,'I06');result=module('readback').browser_faults(m)
        else:
            for gate in ('I01','I02','I03','I04','I05','I06','I07'):require_gate(m,gate)
            hygiene=closeout.verify_secret_hygiene(m)
            result=closeout.reclaim(m,'m1',apply=True)
            result['secretHygiene']=hygiene['status']
            rt.execute(m,'diff-main',['git','diff','--check',rt.MAIN,m['_head']])
            rt.execute(m,'diff-resume',['git','diff','--check','720c9cb72a22b9d905a1adade65c042de79a5ad0',m['_head']])
            result['status']='PARTIAL';result['independentReviewAndDelivery']='REQUIRED_AFTER_RUNTIME_CLOSEOUT'
        rt.write_json(gate_path(m,args.gate),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'manifestSha256':m['_sha256'],'result':result})
        print(json.dumps({'gate':args.gate,'result':result},ensure_ascii=False))
    except Exception as failure:
        rt.write_json(gate_path(m,args.gate),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'manifestSha256':m['_sha256'],'result':{'status':'BLOCKED_WITH_WITNESS','category':type(failure).__name__,'code':str(failure) if isinstance(failure,ValueError) else 'DETAILS_SUPPRESSED'}})
        raise


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError):
        print('BLOCKED_WITH_WITNESS',file=sys.stderr);raise SystemExit(2)
