#!/usr/bin/env python3
"""任务级离线工具与.NET闭包准备；历史runtime/凭证从不复制。"""
import argparse
import base64
import hashlib
import io
import importlib.util
import types
import json
import os
from pathlib import Path
import platform
import re
import shutil
import shlex
import sqlite3
import struct
import stat
import subprocess
import tarfile
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import quoteattr

BASE='709d22ac11880539669d032550a056d7d761dda8'
ARCHIVE_COMMIT='00c6f472c40bbe75d7b577a6144ca6046221a5d4'
ADMISSION='docs/evidence/G4-M1-MAIN-INTEGRATION-001/p0/tools-admission.json'
ARCHIVES='docs/evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-02/all-platform-lock-content.json'
SDK_ARCHIVES={
    'Aspire.AppHost.Sdk':('13.6.3','cb8c5abad85fb542e2bb4807dd31a2ee4c22f56b7762e0258b74a803c1035ad0','eav786xkHaGl9QluDj4mDgTn4f8fdg+fFEx+vAb7YVWM5DYe0yEUJKqdj+PHxPkffLtKc+/CBgAvf7NbYT4Yfg=='),
    'MSTest.Sdk':('4.5.1','984c1fa3338a950aaee3afa8bdda314cd732af483e0dc8b4138ec51aa0327c2b','uWWZsmVXHQfTC3JLGz1fXF28WirAhh5JKBwYyVh4I/cjBKYNbO13ZvIh0NVEBa50no5FKmN+czZCivdQfPXNXQ==')}


def require(value,code):
    if not value:raise ValueError('ENVIRONMENT_BLOCKED: '+code)


def digest(data):return hashlib.sha256(data).hexdigest()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def ordinary(path):
    path=Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in [path,*path.parents]),'LINKED_PATH')
    require(not path.exists() or path.is_file() or path.is_dir(),'SPECIAL_PATH')
    return path


def materialize(path,data):
    """只更新调用者准确指定的私有文件，已匹配字节不重写。"""
    path=ordinary(path)
    if path.is_file() and path.read_bytes()==data:return False
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=ordinary(path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp'))
    with temporary.open('xb') as f:
        os.chmod(temporary,0o600);f.write(data)
    os.replace(temporary,path)
    return True


def archive_payload(raw):
    payload={};folded=set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            p=Path(info.filename)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in info.filename and stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK,'ARCHIVE_PATH')
            if info.is_dir():continue
            relative=str(p)
            require(relative.casefold() not in folded,'ARCHIVE_DUPLICATE')
            folded.add(relative.casefold());payload[relative]=z.read(info)
    return payload


def identities(inputs,root):
    content=digest(canonical(inputs))
    return dict(contentKey=content,workspaceKey=digest(canonical([content,str(root.resolve())])))


def git_json(root,commit,path):
    return json.loads(subprocess.check_output(['git','show',commit+':'+path],cwd=root))


def locks(root):
    """核验solution每个项目当前平台锁，并收集SDK resolver声明。"""
    packages={};projects=[];declared=set();inputs={}
    solution=root/'backend/OntologyPlatform.slnx'
    for node in ET.parse(solution).iter('Project'):
        project=ordinary(solution.parent/node.attrib['Path'])
        require(project.is_relative_to(root) and project.is_file(),'PROJECT_BOUNDARY')
        candidates=[p for p in project.parent.glob('packages*.lock.json') if p.name in ('packages.lock.json','packages.osx-arm64.lock.json')]
        require(len(candidates)==1,'PROJECT_LOCK_COVERAGE')
        lock=ordinary(candidates[0]);dependencies=json.loads(lock.read_text())['dependencies'];expected=set()
        for entries in dependencies.values():
            for name,row in entries.items():
                if 'resolved' not in row or 'contentHash' not in row:continue
                key=name.lower()+'/'+row['resolved']
                require(key not in packages or packages[key]==row['contentHash'],'LOCK_HASH_CONFLICT')
                packages[key]=row['contentHash'];expected.add(key)
        tree=ET.parse(project).getroot()
        sdk=tree.get('Sdk','')
        if '/' in sdk:declared.add(tuple(sdk.split('/',1)))
        for item in tree.findall('Sdk'):declared.add((item.attrib['Name'],item.attrib['Version']))
        projects.append(dict(path=str(project.relative_to(root)),packages=sorted(expected)))
        for p in (project,lock):inputs[str(p.relative_to(root))]=digest(p.read_bytes())
    require(declared=={(name,row[0]) for name,row in SDK_ARCHIVES.items()},'SDK_DECLARATION_DRIFT')
    for name in ('global.json','Directory.Build.props','Directory.Build.targets','Directory.Packages.props','NuGet.Config','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','apps/web/package.json','.node-version'):
        p=root/name
        if p.is_file():inputs[name]=digest(p.read_bytes())
    require(json.loads((root/'global.json').read_text())['sdk']['version']=='10.0.402','SDK_VERSION_DRIFT')
    require(packages and projects,'EMPTY_LOCKS')
    return packages,projects,inputs


def environment(home):
    """CLI第一次启动前隔离HOME策略与所有NuGet缓存；不继承配置注入。"""
    values={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','SystemRoot')}
    for name in ('cli-home','nuget-packages','http-cache','scratch','tmp','runs'):
        ordinary(home/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    values.update(DOTNET_ROOT='/usr/local/share/dotnet',DOTNET_CLI_HOME=str(home/'cli-home'),
        NUGET_PACKAGES=str(home/'nuget-packages'),NUGET_HTTP_CACHE_PATH=str(home/'http-cache'),
        NUGET_SCRATCH=str(home/'scratch'),TMPDIR=str(home/'tmp'),TMP=str(home/'tmp'),TEMP=str(home/'tmp'),
        DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
        DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true',DOTNET_GENERATE_ASPNET_CERTIFICATE='false',
        NUGET_CERT_REVOCATION_MODE='offline',DOTNET_CLI_USE_MSBUILD_SERVER='0',MSBUILDDISABLENODEREUSE='1',
        NEXT_TELEMETRY_DISABLED='1',PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1',PYTHONDONTWRITEBYTECODE='1')
    return values


def offline(command,root,home,projects):
    """Mac内核先拒绝全部网络和全局写；仅任务缓存与项目obj可写。"""
    require(platform.system()=='Darwin' and Path('/usr/bin/sandbox-exec').is_file(),'OS_NETWORK_BOUNDARY_UNAVAILABLE')
    writable=[home,*[root/Path(p['path']).parent/'obj' for p in projects]]
    profile='(version 1) (allow default) (deny network*) (deny file-write*) (allow file-write* (literal "/dev/null") '+ ' '.join('(subpath '+json.dumps(str(p))+')' for p in writable)+')'
    return ['/usr/bin/sandbox-exec','-p',profile,*command]


def run(command,root,home,projects,env,label,run_dir,timeout=180):
    """每次命令真实计时且保留有界日志；超时也是失败事实。"""
    from workflow_execution import run as execute
    started=time.monotonic()
    task=home.parent.parent.name
    proc=execute(offline(command,root,home,projects),root,task=task,run_id=run_dir.name,
                 stage=label,environment=env,timeout=timeout,input_key=home.name,
                 identity_key=digest(canonical([label,command])))
    raw=proc.stdout+proc.stderr;code=proc.returncode
    materialize(run_dir/(label+'.txt'),raw)
    row=dict(command=command,exitCode=proc.receipt['exitCode'],classification=proc.receipt['classification'],elapsedSeconds=time.monotonic()-started,outputSha256=digest(raw))
    materialize(run_dir/(label+'.json'),canonical(row)+b'\n')
    require(code==0,label+'_FAILED_'+str(code))
    return raw


def verify_assets(root,home,projects,packages,approved):
    """资产逐项目绑定本树/本缓存，所有实际包成员回绑已批准归档。"""
    rows=[];checked=set()
    for project in projects:
        path=ordinary(root/Path(project['path']).parent/'obj/project.assets.json')
        require(path.is_file(),'ASSETS_MISSING')
        value=json.loads(path.read_text());restore=value['project']['restore']
        require(restore['projectPath']==str(root/project['path']),'ASSET_OLD_WORKTREE')
        require({p.rstrip('/') for p in value['packageFolders']}=={str(home/'nuget-packages')},'ASSET_PACKAGE_PATH')
        require(set(restore['sources'])=={str(home/'feed')} and restore['configFilePaths']==[str(home/'offline-nuget.config')],'ASSET_CONFIG')
        require(not restore.get('fallbackFolders') and not any(x.get('level')=='Error' for x in value.get('logs',[])),'ASSET_ERRORS')
        actual={k.lower():v for k,v in value['libraries'].items() if v['type']=='package'}
        require(set(actual)==set(project['packages']),'ASSET_LOCK_COVERAGE')
        for key,entry in actual.items():
            require(entry['sha512']==packages[key],'ASSET_CONTENT_HASH')
            if key in checked:continue
            checked.add(key);name,version=key.split('/')
            target=ordinary(home/'nuget-packages'/entry['path'])
            require(target.is_relative_to(home/'nuget-packages'),'PACKAGE_BOUNDARY')
            archive=home/'feed'/(name+'.'+version+'.nupkg');raw=ordinary(archive).read_bytes()
            require(digest(raw)==approved[key]['archiveSha256'],'FEED_DRIFT')
            payload=archive_payload(raw)
            expected={k.casefold():v for k,v in payload.items()}
            expected[archive.name]=raw
            expected[archive.name+'.sha512']=base64.b64encode(hashlib.sha512(raw).digest())
            members=set()
            for p in target.rglob('*'):
                ordinary(p)
                if not p.is_file():continue
                rel=str(p.relative_to(target));members.add(rel)
                if rel=='.nupkg.metadata':
                    metadata=json.loads(p.read_text());require(metadata['contentHash']==entry['sha512'] and metadata['source']==str(home/'feed'),'PACKAGE_METADATA');continue
                require(rel.casefold() in expected and p.read_bytes()==expected[rel.casefold()],'PACKAGE_MEMBER_DRIFT_'+key+'_'+rel)
            require(members==set(entry['files'])|{archive.name,'.nupkg.metadata'},'PACKAGE_MEMBER_SET')
        rows.append(dict(project=project['path'],assetsSha256=digest(path.read_bytes())))
    require(checked==set(packages),'SOLUTION_CLOSURE')
    return rows


def decode_package_index(blob):
    """只解码pnpm已审离线索引的MessagePack记录，不执行包内代码。"""
    position=0;records={}
    def take(n):
        nonlocal position
        value=blob[position:position+n];position+=n
        require(len(value)==n,'INDEX_TRUNCATED')
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
            kind,ident=number(1),number(1);require(kind==114,'INDEX_EXTENSION')
            keys=read();require(isinstance(keys,list) and all(isinstance(x,str) for x in keys),'INDEX_RECORD_KEYS')
            records[ident]=keys;return {key:read() for key in keys}
        raise ValueError('INDEX_TAG')
    value=read();require(position==len(blob),'INDEX_TRAILING_BYTES');return value


def verify_web_cache(web,store):
    """逐个已安装包绑定锁定store索引及文件SHA512；生成shim另行记录。"""
    with sqlite3.connect('file:'+str(store)+'?mode=ro&immutable=1',uri=True) as db:
        indexed={key.split('\t')[-1]:(key,blob) for key,blob in db.execute('select key,data from package_index')}
    verified=[]
    ordinary(web/'node_modules/.pnpm')
    for folder in sorted((web/'node_modules/.pnpm').iterdir()):
        ordinary(folder)
        modules=folder/'node_modules'
        if not modules.is_dir():continue
        candidates=[]
        for item in modules.iterdir():
            if item.is_symlink() or item.name=='.bin':continue
            candidates.extend(item.iterdir() if item.name.startswith('@') else [item])
        for package in candidates:
            if package.is_symlink() or not (package/'package.json').is_file():continue
            identity=json.loads((package/'package.json').read_text());key=identity['name']+'@'+identity['version']
            require(key in indexed,'INDEX_PACKAGE_MISSING')
            store_key,blob=indexed[key];index=decode_package_index(blob)
            lock=(web/'pnpm-lock.yaml').read_text()
            pattern=r"^  '?"+re.escape(key)+r"'?:\n    resolution: \{integrity: "+re.escape(store_key.split('\t')[0])+r"[},]"
            require(re.search(pattern,lock,re.MULTILINE),'STORE_LOCK_BINDING')
            require(index['algo']=='sha512','INDEX_ALGORITHM')
            files=[]
            for name,entry in index['files'].items():
                path=ordinary(package/name)
                require('..' not in Path(name).parts and not Path(name).is_absolute(),'INDEX_PATH')
                require(path.is_file() and not path.is_symlink(),'INDEX_FILE_MISSING')
                actual=hashlib.sha512(path.read_bytes()).hexdigest()
                require(actual==entry['digest'] and path.stat().st_size==entry['size'],'WEB_PACKAGE_FILE_DRIFT')
                files.append({'path':str(path.relative_to(web)),'sha512':actual})
            actual_files={str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() and not p.is_symlink() and '/node_modules/.bin/' not in str(p)}
            require(actual_files==set(index['files']),'WEB_EXTRA_PACKAGE_FILE_'+key+'_'+','.join(sorted(actual_files-set(index['files']))))
            bins=identity.get('bin',{})
            if isinstance(bins,str):bins={identity['name'].split('/')[-1]:bins}
            declared=[]
            expected={x['path'] for x in files}
            for name,target in bins.items():
                resolved=(package/target).resolve()
                require(resolved.is_relative_to(web) and str(resolved.relative_to(web)) in expected,'PACKAGE_BIN_UNBOUND')
                declared.append({'name':name,'path':str(resolved.relative_to(web))})
            verified.append({'package':key,'storeKey':store_key,'indexSha256':digest(blob),'files':files,'bins':declared})
    require(len(verified)>100,'INCOMPLETE_WEB_CACHE')
    return verified


def web_marker(root,home,admission):
    """Web状态按自身输入持久化；后端锁/项目变化不清空已核验Web材料。"""
    files={name:digest(ordinary(root/name).read_bytes()) for name in ('package.json','apps/web/package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version')}
    node_files=[row for row in admission['files'] if '/node@24/' in row['path']]
    key=digest(canonical(dict(files=files,pnpm=admission['pnpm']['integrity'],node=node_files,
                              platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0])))
    return ordinary(home.parents[1]/'web-state'/(key+'.json'))


def prepare_web(root,home,admission,projects,env,run_dir,node):
    """逐文件确认已审内容后仅首次复制；所有链接、shim及pnpm工作区重绑定本树。"""
    source=Path(admission['webSource']['root'])
    store=ordinary(admission['playwrightAndAjv']['store'])
    for name in ('package.json','apps/web/package.json','pnpm-lock.yaml','pnpm-workspace.yaml'):
        require((source/name).read_bytes()==(root/name).read_bytes(),'WEB_LOCK_DRIFT')
    copied=0
    marker=web_marker(root,home,admission)
    legacy=[p for p in home.parent.glob('*/web-ready.json') if ordinary(p).is_file() and json.loads(p.read_text()).get('root')==str(root)]
    if marker.exists() or legacy:
        if marker.exists():require(json.loads(marker.read_text())['root']==str(root),'WEB_OLD_ROOT')
        rows=verify_web_cache(root,store)
    else:
        rows=verify_web_cache(source,store)
        for relative in ('node_modules','apps/web/node_modules'):
            dest=ordinary(root/relative)
            require(not dest.exists(),'WEB_EXISTING_UNBOUND_TREE')
            dest.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['/bin/cp','-cR',str(source/relative),str(dest)],check=True)
            copied+=1
        allowed_bins={(b['name'],b['path']) for row in rows for b in row['bins']}
        for directory in (root/'node_modules',root/'apps/web/node_modules'):
            for path in directory.rglob('*'):
                if path.is_symlink():
                    target=os.readlink(path)
                    if target.startswith(str(source)+'/'):
                        path.unlink();path.symlink_to(str(root)+target[len(str(source)):])
                    require(path.exists() and path.resolve().is_relative_to(root),'WEB_LINK_ESCAPE')
                elif path.is_file() and '/.bin/' in str(path):
                    match=re.search(r'^# cmd-shim-target=(.+)$',path.read_text(),re.MULTILINE)
                    require(match is not None,'WEB_SHIM_UNBOUND')
                    original=Path(match[1]).resolve();require(original.is_relative_to(source),'WEB_SHIM_ESCAPE')
                    relative=str(original.relative_to(source));require((path.name,relative) in allowed_bins,'WEB_UNDECLARED_BIN')
                    target=root/relative;require(target.read_bytes().startswith(b'#!/usr/bin/env node'),'WEB_NON_NODE_BIN')
                    path.write_text('#!/bin/sh\nexec '+shlex.quote(node)+' '+shlex.quote(str(target))+' "$@"\n');path.chmod(0o755)
        path=root/'node_modules/.pnpm-workspace-state-v1.json';state=json.loads(path.read_text())
        manifests={}
        for rel in ('','/apps/web'):
            manifest=json.loads((root/(rel.lstrip('/')+'/package.json' if rel else 'package.json')).read_text())
            manifests[rel]={k:manifest[k] for k in ('name','version') if k in manifest}
        require(state['projects']=={str(source)+p:v for p,v in manifests.items()},'WEB_WORKSPACE_SOURCE')
        require(state.get('pnpmfiles')==[] and state.get('filteredInstall') is False,'WEB_HOOK_OR_PARTIAL')
        state['projects']={str(root)+p:v for p,v in manifests.items()};state['lastValidatedTimestamp']=0;state.pop('validation',None)
        path.write_text(json.dumps(state,indent=2)+'\n')
        rows=verify_web_cache(root,store)
    # 每次检查路径敏感链接与实际pnpm依赖状态；第二次不会物化或restore。
    allowed_bins={(b['name'],b['path']) for row in rows for b in row['bins']}
    for directory in (root/'node_modules',root/'apps/web/node_modules'):
        for path in directory.rglob('*'):
            if path.is_symlink():require(path.exists() and path.resolve().is_relative_to(root),'WEB_LINK_ESCAPE')
            elif path.is_file() and '/.bin/' in str(path):
                original_shim=source/path.relative_to(root)
                match=re.search(r'^# cmd-shim-target=(.+)$',original_shim.read_text(),re.MULTILINE)
                require(match is not None,'WEB_SHIM_UNBOUND')
                original=Path(match[1]).resolve();require(original.is_relative_to(source),'WEB_SHIM_ESCAPE')
                relative=str(original.relative_to(source));require((path.name,relative) in allowed_bins,'WEB_UNDECLARED_BIN')
                expected=('#!/bin/sh\nexec '+shlex.quote(node)+' '+shlex.quote(str(root/relative))+' "$@"\n').encode()
                require(path.read_bytes()==expected,'WEB_SHIM_DRIFT')
    require(set(json.loads((root/'node_modules/.pnpm-workspace-state-v1.json').read_text())['projects'])=={str(root),str(root/'apps/web')},'WEB_OLD_WORKSPACE')
    # pnpm会更新本树工作区状态，仅允许此准确文件，仍拒绝全部网络。
    command=offline([node,str(home/'pnpm/package/bin/pnpm.cjs'),'--config.verifyDepsBeforeRun=error','--dir','apps/web','run','lint','--help'],root,home,projects)
    command[2]+=' (allow file-write* (literal '+json.dumps(str(root/'node_modules/.pnpm-workspace-state-v1.json'))+'))'
    proc=subprocess.run(command,cwd=root,env=env,capture_output=True,timeout=60)
    materialize(run_dir/'web-dependency-check.log',proc.stdout+proc.stderr)
    require(proc.returncode==0,'PNPM_DEPENDENCY_STATE_FAILED')
    materialize(marker,canonical(dict(root=str(root)))+b'\n')
    return dict(status='DEPENDENCIES_READY',packages=len(rows),materializedTrees=copied,download=0,install=0,restore=0,contentFiles=sum(len(row['files']) for row in rows))


def prepare(root,task):
    """同任务/同输入第二次仅核验，不复制、不restore；不做产品PASS声明。"""
    root=Path(root).resolve()
    require(re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}',task),'TASK_ID')
    require(platform.system()=='Darwin' and platform.machine()=='arm64','PLATFORM_NOT_RUN')
    packages,projects,input_files=locks(root)
    admission=git_json(root,BASE,ADMISSION)
    approved={p['package']:p for p in git_json(root,ARCHIVE_COMMIT,ARCHIVES)['packages']}
    require({k:v['contentHash'] for k,v in approved.items()}==packages,'APPROVED_CURRENT_LOCK_CLOSURE')
    for row in admission['files']:
        p=ordinary(row['path']);require(p.is_file() and digest(p.read_bytes())==row['sha256'],'APPROVED_TOOL_DRIFT')
    inputs=dict(platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0],files=input_files,tools=admission['files'],sdk=SDK_ARCHIVES,
                archives={k:v['archiveSha256'] for k,v in approved.items()})
    identity=identities(inputs,root)
    home=ordinary(root/'artifacts/workflow'/task/'environment'/identity['contentKey'])
    home.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=ordinary(home/'prepare.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    try:return prepare_locked(root,task,home,projects,packages,approved,admission,identity)
    finally:lock.unlink()


def prepare_locked(root,task,home,projects,packages,approved,admission,identity):
    env=environment(home);run_dir=home/'runs'/uuid.uuid4().hex;run_dir.mkdir(mode=0o700)
    materialized=0;source=Path.home()/'.nuget/packages';feed=home/'feed';feed.mkdir(exist_ok=True)
    # 所有批准归档在任何SDK启动前核验；不会读取凭证或旧任务私有runtime。
    raw_archives={}
    for key,row in approved.items():
        name,version=key.split('/');p=ordinary(source/key/(name+'.'+version+'.nupkg'))
        require(p.is_file(),'LOCKED_ARCHIVE_MISSING_'+key)
        raw=p.read_bytes();require(digest(raw)==row['archiveSha256'],'LOCKED_ARCHIVE_DRIFT_'+key)
        raw_archives[p.name]=raw
    sdk_payloads={}
    for name,(version,sha,content_hash) in SDK_ARCHIVES.items():
        archive=ordinary(source/name.lower()/version/(name.lower()+'.'+version+'.nupkg'))
        raw=archive.read_bytes();require(digest(raw)==sha,'SDK_ARCHIVE_DRIFT')
        payload=archive_payload(raw)
        payload.update({archive.name:raw,archive.name+'.sha512':content_hash.encode(),'.nupkg.metadata':canonical(dict(version=2,contentHash=content_hash,source=str(feed)))})
        sdk_payloads[name]=(version,payload)
    for name,raw in raw_archives.items():materialized+=materialize(feed/name,raw)
    require({p.name for p in feed.iterdir()}==set(raw_archives),'EXTRA_FEED_MEMBER')
    for name,(version,payload) in sdk_payloads.items():
        target=home/'nuget-packages'/name.lower()/version
        for relative,data in payload.items():materialized+=materialize(target/relative,data)
        require({str(p.relative_to(target)) for p in target.rglob('*') if ordinary(p).is_file()}==set(payload),'SDK_EXTRA_MEMBER')
    config=('<configuration><packageSources><clear/><add key="approved-local" value='+quoteattr(str(feed))+'/></packageSources><packageSourceMapping><clear/><packageSource key="approved-local"><package pattern="*"/></packageSource></packageSourceMapping></configuration>\n').encode()
    materialized+=materialize(home/'offline-nuget.config',config)
    materialized+=materialize(home/'cli-home/.nuget/NuGet/NuGet.Config',config)
    # pnpm工具来自批准tar；不复制node_modules/旧路径、也不运行install。
    pnpm=admission['pnpm'];raw=ordinary(pnpm['archive']).read_bytes()
    require('sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()==pnpm['integrity'],'PNPM_ARCHIVE_DRIFT')
    pnpm_files=set()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        for member in tar.getmembers():
            p=Path(member.name)
            require(not p.is_absolute() and '..' not in p.parts and p.parts[0]=='package' and (member.isfile() or member.isdir()),'PNPM_ARCHIVE_PATH')
            if member.isfile():
                require(member.name not in pnpm_files,'PNPM_DUPLICATE');pnpm_files.add(member.name)
                materialized+=materialize(home/'pnpm'/member.name,tar.extractfile(member).read())
    require({str(p.relative_to(home/'pnpm')) for p in (home/'pnpm').rglob('*') if ordinary(p).is_file()}==pnpm_files,'PNPM_EXTRA_MEMBER')
    python_rows=git_json(root,BASE,'docs/evidence/G4-M1-MAIN-INTEGRATION-001/three-file-apply-20261103-01/private-cache-copy.json')['pyyamlFiles']
    python_source=Path(admission['pyyaml']['sharedSource'])
    for row in python_rows:
        source_file=ordinary(python_source/row['path']);data=source_file.read_bytes()
        require(digest(data)==row['sha256'],'PYYAML_CONTENT_DRIFT')
        materialized+=materialize(root/'.tools/pythonlibs'/row['path'],data)
    require({str(p.relative_to(root/'.tools/pythonlibs')) for p in (root/'.tools/pythonlibs').rglob('*') if ordinary(p).is_file()}=={r['path'] for r in python_rows},'PYYAML_EXTRA_MEMBER')
    env['PYTHONPATH']=str(root/'.tools/pythonlibs')
    if (home/'ready.json').exists():verify_assets(root,home,projects,packages,approved)
    dotnet='/usr/local/share/dotnet/dotnet';node='/opt/homebrew/Cellar/node@24/24.22.1/bin/node'
    require(run([dotnet,'--version'],root,home,projects,env,'sdk-version',run_dir).decode().strip()=='10.0.402','SDK_VERSION')
    require(run([node,str(home/'pnpm/package/bin/pnpm.cjs'),'--version'],root,home,projects,env,'pnpm-version',run_dir).decode().strip()=='11.28.8','PNPM_VERSION')
    resolver={}
    for name,project in {'Aspire.AppHost.Sdk':'backend/src/AppHost/OntologyPlatform.AppHost.csproj','MSTest.Sdk':'backend/tests/OntologyPlatform.ConnectionsTests/OntologyPlatform.ConnectionsTests.csproj'}.items():
        output=run_dir/(name+'.xml')
        run([dotnet,'msbuild',str(root/project),'-nologo','-preprocess:'+str(output),'-nodeReuse:false'],root,home,projects,env,'resolver-'+name,run_dir)
        content=output.read_text();version=SDK_ARCHIVES[name][0]
        expected=[str(home/'nuget-packages'/name.lower()/version/'Sdk'/f) for f in ('Sdk.props','Sdk.targets')]
        require(all(p in content for p in expected),'SDK_RESOLVER_OUTSIDE_PRIVATE_CACHE')
        resolver[name]=expected
    previous=home/'ready.json';restores=0
    if previous.is_file():
        prior=json.loads(previous.read_text());require(prior['workspaceKey']==identity['workspaceKey'],'WORKSPACE_CHANGED')
        assets=verify_assets(root,home,projects,packages,approved)
    elif task in ('G4-M2-WEB-01','G4-ENG-DELIVERY-002','G4-M2-DORIS-01') and all((root/Path(p['path']).parent/'obj/project.assets.json').is_file() for p in projects):
        # 上次Web失败不使已成功的后端闭包失效；逐项目/包重新核验真实内容和绝对路径。
        assets=verify_assets(root,home,projects,packages,approved)
        require(any(json.loads(p.read_text()).get('exitCode')==0 and
                    digest((p.with_suffix('.txt') if p.with_suffix('.txt').exists() else p.with_suffix('.log')).read_bytes())==json.loads(p.read_text()).get('outputSha256')
                    for p in (home/'runs').glob('*/restore.json')),'BACKEND_REUSE_EVIDENCE_MISSING')
    else:
        failure=home/'restore-failure.json'
        require(not failure.exists(),'UNCHANGED_RESTORE_FAILURE_REQUIRES_SHORT_DIAGNOSIS')
        try:
            run([dotnet,'restore',str(root/'backend/OntologyPlatform.slnx'),'--locked-mode','--configfile',str(home/'offline-nuget.config'),'-p:NuGetAudit=false','--disable-parallel','--disable-build-servers','-m:1','--verbosity','minimal'],root,home,projects,env,'restore',run_dir,600)
            restores=1;assets=verify_assets(root,home,projects,packages,approved)
        except Exception:
            materialize(failure,canonical(dict(**identity,run=str(run_dir)))+b'\n');raise
    if task in ('G4-M2-WEB-01','G4-ENG-DELIVERY-002','G4-M2-DORIS-01'):
        spec=importlib.util.spec_from_file_location('workflow_web_cache',root/'scripts/maintenance/workflow_web_cache.py')
        web_adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(web_adapter)
        web=web_adapter.prepare(root,home,admission,projects,env,run_dir,node,types.SimpleNamespace(**globals()))
    else:
        web=prepare_web(root,home,admission,projects,env,run_dir,node)
    result=dict(schemaVersion=1,taskId=task,status='DEPENDENCIES_READY',**identity,worktree=str(root),
                environmentDirectory=str(home),environment=env,runDirectory=str(run_dir),packages=len(packages),projects=len(projects),
                downloads=0,sdkDownloads=0,materializedFiles=materialized,restoreCount=restores,assets=assets,sdkResolver=resolver,
                pnpmTool=str(home/'pnpm/package/bin/pnpm.cjs'),node=node,dotnet=dotnet,webDependencies=web,
                docker='NOT_RUN: prepare performs no service creation',smoke='NOT_RUN',runtimeCredentialsCopied=0)
    materialize(previous,canonical(dict(**identity))+b'\n')
    result['environmentFile']=str(home/'environment.json')
    materialize(home/'environment.json',canonical(env)+b'\n')
    materialize(run_dir/'receipt.json',canonical(result)+b'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--task',required=True)
    args=p.parse_args()
    try:
        result=prepare(args.root,args.task);print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='ENVIRONMENT_BLOCKED',reason=str(exc)),ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
