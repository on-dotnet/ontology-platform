#!/usr/bin/env python3
"""G4-M1主线集成任务真实门禁入口；所有后续阶段由实际前置回执决定。"""
import argparse
import base64
import hashlib
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
    for path in (rt.ROOT/'backend').rglob('packages.lock.json'):
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


def prepare_tools(m):
    """已有锁定制品独立复制，不运行install、不链接共享可变源。"""
    d=rt.ROOT/'.tools';d.mkdir(exist_ok=True)
    source=Path('/Users/chasen/.nuget/packages')
    packages=locked_packages()
    # NuGet签名包GetContentHash不是完整ZIP的SHA512。使用SDK本身校验，保留两种散列。
    env=rt.environment();env['G4_PACKAGE_EXPECTATIONS']=json.dumps(packages)
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
    verified_raw=rt.execute(m,'nuget-content-hash',['pwsh','-NoProfile','-Command',command],env=env)
    verified_archives={row['package']:row['archiveSha256'] for row in json.loads(verified_raw)}
    rt.require(shutil.disk_usage(rt.ROOT).free>8*1024**3,'DISK_HEADROOM')
    rt.require(not (d/'nuget').exists(),'EXISTING_TOOL_COPY')
    (d/'nuget').mkdir()
    archive_rows=[]
    for key in packages:
        name,version=key.split('/');archive=source/key/(name+'.'+version+'.nupkg')
        target=d/'nuget'/archive.name;shutil.copyfile(archive,target)
        rt.require(rt.digest(target.read_bytes())==verified_archives[key],'NUGET_COPY_DRIFT')
        archive_rows.append({'package':key,'archiveSha256':rt.digest(target.read_bytes())})
    rt.write_json(rt.ARTIFACTS/m['runId']/'nuget-archive-copies.json',archive_rows)
    from xml.sax.saxutils import quoteattr
    config=rt.ARTIFACTS/m['runId']/'offline-nuget.config'
    rt.require(not config.exists(),'EXISTING_OFFLINE_CONFIG')
    config.write_text('<configuration><packageSources><clear/><add key="approved-local" value='+quoteattr(str(d/'nuget'))+'/></packageSources><packageSourceMapping><clear/><packageSource key="approved-local"><package pattern="*"/></packageSource></packageSourceMapping></configuration>')
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
    rt.write_json(rt.ARTIFACTS/m['runId']/'tool-copies.json',{'pyyaml':rows,'shimRebases':rebased,'download':0,'install':0})
    rt.execute(m,'pnpm-version',[NODE,str(d/'pnpm/package/bin/pnpm.cjs'),'--version'])


def engineering(m):
    """真实原样完整入口；离线恢复先行，实际skip不被掩盖。"""
    rt.execute(m,'selftest',['pwsh','-NoProfile','-File','scripts/verify.ps1','-SelfTest'],timeout=1800)
    rt.execute(m,'task-tests',['python3','-B',str(rt.HERE/'tests.py')],timeout=120)
    solution=rt.ROOT/'backend/OntologyPlatform.slnx'
    rt.require(solution.is_file(),'SOLUTION')
    rt.execute(m,'offline-restore',[DOTNET,'restore',str(solution),'--locked-mode','--configfile',str(rt.ARTIFACTS/m['runId']/'offline-nuget.config'),'-p:NuGetAudit=false','--disable-parallel'],timeout=600)
    raw=rt.execute(m,'native-web',['pwsh','-NoProfile','-File','scripts/verify.ps1','-RunNative','-RunTests'],timeout=1800)
    text=raw.decode(errors='replace')
    skips=re.findall(r'(?:已跳过|Skipped)\s+([^\r\n]+)',text)
    rt.write_json(rt.ARTIFACTS/m['runId']/'build-inputs.json',{'testedCommit':m['_head'],'files':rt.build_fingerprint()})
    return {'status':'PARTIAL' if skips else 'PASS','nativeAndWebExitCode':0,'skipped':skips,'fixtureClosureRequired':True}


def contracts(m):
    """真实DLL导出及真实生成器的隔离再生；失败不修改生成物。"""
    rt.check_build(m)
    output=rt.ARTIFACTS/m['runId']/'g4-export.json'
    rt.require(not output.exists(),'EXISTING_EXPORT')
    rt.execute(m,'openapi-export',[DOTNET,str(rt.ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll'),'--export-g4-openapi',str(output)])
    raw=rt.execute(m,'contract-chain',[NODE,str(rt.HERE/'contract-check.mjs'),'--runtime-openapi',str(output),'--output',str(rt.ARTIFACTS/m['runId']/'regenerated')])
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


def main():
    """唯一参数合同；重复/任意TaskId和非法门禁均拒绝。"""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate',required=True,choices=('PREFLIGHT','I01','I02','I03','I04','I05','I06','I07','I08'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--resource-manifest',required=True)
    args=parser.parse_args()
    rt.require(len(sys.argv)==9 and len(set(sys.argv[1::2]))==4,'EXACT_ARGUMENT_SET')
    m=rt.load_manifest(args.resource_manifest,args.run_id,args.expected_head)
    rt.require(not gate_path(m,args.gate).exists(),'EXISTING_GATE_RECEIPT')
    try:
        if args.gate=='PREFLIGHT':
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
            result={'status':'PASS','modules':results,'compatibility':compat}
        elif args.gate=='I04':
            require_gate(m,'I02')
            result=module('migration-boundary').verify_all(m)
        elif args.gate=='I06':
            require_gate(m,'I04');result=module('readback').lifecycle_and_faults(m)
            original=require_gate(m,'I01',partial=True);modules=require_gate(m,'I02')['result']['modules']
            rt.require(original['result']['nativeAndWebExitCode']==0 and all(x['status']=='PASS' for x in modules),'NATIVE_FIXTURE_CLOSURE')
            rt.require(sum(x['total'] for x in result['pgGroups'] if x['category']=='RealPgFixture')>=12 and any(x['category']=='RealPgWrongSanFixture' for x in result['pgGroups']) and any(x['category']=='RealPgPublicFixture' for x in result['pgGroups']),'PG_FIXTURE_CLOSURE')
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
