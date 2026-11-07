#!/usr/bin/env python3
"""G4-M2-WEB-01已批准缓存迁移：逐内容核验、路径重绑定、零安装。"""
import json
import os
from pathlib import Path
import shlex
import shutil
import hashlib
import subprocess
import re
import sys

TASK='G4-M2-WEB-01'


def require(value,code):
    if not value:raise ValueError('ENVIRONMENT_BLOCKED: '+code)


def shim_bytes(node,target):
    """仅生成准确Node和已核验包入口，不执行来源shim文本。"""
    return ('#!/bin/sh\nexec '+shlex.quote(str(node))+' '+shlex.quote(str(target))+' "$@"\n').encode()


def shim_target(path,root,node,allowed):
    """来源为已准备缓存，仅接受逐字节匹配的固定两参数shim。"""
    raw=path.read_bytes()
    for name,relative in allowed:
        if path.name==name and raw==shim_bytes(node,root/relative):
            require((root/relative).read_bytes().startswith(b'#!/usr/bin/env node'),'WEB_NON_NODE_BIN')
            return relative
    raise ValueError('ENVIRONMENT_BLOCKED: WEB_SHIM_DRIFT')


def workspace(root):
    """完整工作区项目身份精确匹配，不借用旧树绝对路径。"""
    state=json.loads((root/'node_modules/.pnpm-workspace-state-v1.json').read_text())
    expected={}
    for relative in ('','apps/web'):
        manifest=json.loads((root/relative/'package.json').read_text())
        expected[str(root/relative)]={k:manifest[k] for k in ('name','version') if k in manifest}
    require(state['projects']==expected and state.get('pnpmfiles')==[] and state.get('filteredInstall') is False,'WEB_WORKSPACE_SOURCE')
    return state


METADATA={'node_modules/.modules.yaml','node_modules/.pnpm/lock.yaml','node_modules/.pnpm-workspace-state-v1.json'}
CACHE_PREFIXES=('node_modules/.vitest-cache/','apps/web/node_modules/.vite/')


def topology(root,known,shims,metadata,allow_cache=False):
    """拒绝未核验普通文件；链接只能解析到已核验包成员及其内部目录。"""
    allowed_dirs=set()
    for relative in known:
        parent=Path(relative).parent
        while str(parent) not in ('.','node_modules','apps/web/node_modules'):
            allowed_dirs.add(str(parent));parent=parent.parent
    links={}
    for directory in (root/'node_modules',root/'apps/web/node_modules'):
        for path in directory.rglob('*'):
            relative=str(path.relative_to(root))
            if allow_cache and any(relative.startswith(prefix) or relative==prefix.rstrip('/') for prefix in CACHE_PREFIXES):
                require(not path.is_symlink(),'WEB_CACHE_LINK');continue
            if path.is_symlink():
                require(path.exists() and path.resolve().is_relative_to(root),'WEB_LINK_ESCAPE')
                target=str(path.resolve().relative_to(root))
                require(target in known or target in allowed_dirs or (relative=='node_modules/.pnpm/node_modules/@ontology-platform/web' and target=='apps/web'),'WEB_LINK_UNVERIFIED_TARGET')
                links[relative]=target
            elif path.is_file():
                require(relative in known or relative in shims or relative in metadata,'WEB_UNVERIFIED_FILE')
            else:require(path.is_dir(),'WEB_SPECIAL_FILE')
    return links


def package_directory(key,maximum=120):
    """复用锁定pnpm11.28.8的纯registry路径规则，包括peer suffix SHA256截短。"""
    require(re.fullmatch(r'[@a-zA-Z0-9_./+()=-]+',key) is not None and ':' not in key,'WEB_NON_REGISTRY_DEPENDENCY')
    name=key[:key.index('@',1)]
    filename=re.sub(r'[\\/:*?"<>|#]','+',key)
    if '(' in filename:
        filename=re.sub(r'\)\(|\(|\)','_',filename[:-1] if filename.endswith(')') else filename)
    if len(filename)>maximum or filename.lower()!=filename:
        filename=filename[:maximum-33]+'_'+hashlib.sha256(filename.encode()).hexdigest()[:32]
    return 'node_modules/.pnpm/'+filename+'/node_modules/'+name


def dependency_edges(lock,layout,installed):
    """从importer、完整peer snapshot及hoist记录重建准确依赖边，拒绝丢失必需依赖。"""
    require(layout.get('virtualStoreDirMaxLength')==120,'WEB_STORE_LAYOUT')
    targets={key:package_directory(key) for key in lock['snapshots']}
    require(installed<=set(targets.values()),'WEB_UNREGISTERED_PACKAGE')
    edges={}
    def add(parent,name,key,optional=False):
        require(key in targets,'WEB_RESOLUTION_MISSING')
        target=targets[key]
        if optional and target not in installed:return
        require(target in installed,'WEB_DEPENDENCY_MISSING')
        link=parent+'/'+name
        if link!=target:edges[link]=target
    for relative,importer in lock['importers'].items():
        parent=('' if relative=='.' else relative+'/')+'node_modules'
        for kind in ('dependencies','devDependencies','optionalDependencies'):
            for name,row in importer.get(kind,{}).items():add(parent,name,name+'@'+row['version'],kind=='optionalDependencies')
    for key,row in lock['snapshots'].items():
        if targets[key] not in installed:continue
        parent='node_modules/.pnpm/'+targets[key].split('/')[2]+'/node_modules'
        for kind in ('dependencies','optionalDependencies'):
            for name,version in row.get(kind,{}).items():add(parent,name,name+'@'+version,kind=='optionalDependencies')
    for key,names in layout.get('hoistedDependencies',{}).items():
        if key=='apps/web':
            require(names=={'@ontology-platform/web':'private'},'WEB_WORKSPACE_HOIST')
            edges['node_modules/.pnpm/node_modules/@ontology-platform/web']='apps/web';continue
        for name,visibility in names.items():
            require(visibility=='private','WEB_PUBLIC_HOIST')
            require(key.split('@',1)[0]==name if not name.startswith('@') else key.startswith(name+'@'),'WEB_HOIST_ALIAS')
            add('node_modules/.pnpm/node_modules',name,key,True)
    return edges


def check_edges(expected,actual):
    """必须包含完整且唯一的锁依赖图，不能把错误链接固化为可信缓存。"""
    require(expected==actual,'WEB_DEPENDENCY_EDGE_DRIFT')


def inspect(root,store,node,adapter,allow_cache=False):
    """完整包内容、固定元数据、shim和规范化链接共同构成绑定。"""
    rows=adapter.verify_web_cache(root,store)
    allowed={(b['name'],b['path']) for row in rows for b in row['bins']}
    shims={}
    workspace(root)
    require((root/'node_modules/.pnpm/lock.yaml').read_bytes()==(root/'pnpm-lock.yaml').read_bytes(),'WEB_INSTALLED_LOCK_DRIFT')
    for directory in (root/'node_modules',root/'apps/web/node_modules'):
        adapter.ordinary(directory)
        for path in directory.rglob('*'):
            if path.is_file() and not path.is_symlink() and '/.bin/' in str(path):
                shims[str(path.relative_to(root))]=shim_target(path,root,node,allowed)
    known={file['path'] for row in rows for file in row['files']}
    links=topology(root,known,shims,METADATA,allow_cache)
    # parser来自prepare逐字节核验的私有批准包，不调用系统安装或网络。
    parser_path=Path(__file__).resolve().parents[2]/'.tools/pythonlibs'
    sys.path.insert(0,str(parser_path))
    try:
        import yaml
        lock=yaml.safe_load((root/'pnpm-lock.yaml').read_text())
        layout=yaml.safe_load((root/'node_modules/.modules.yaml').read_text())
    finally:sys.path.pop(0)
    installed={'/'.join(file['path'].split('/')[:4])+('/'+row['package'].rsplit('@',1)[0]) for row in rows for file in row['files'][:1]}
    check_edges(dependency_edges(lock,layout,installed),links)
    return rows,shims,links


def binding(root,rows,shims,links,adapter):
    """只排除pnpm会更新的时间戳；完整依赖拓扑每次重算。"""
    metadata={name:adapter.digest((root/name).read_bytes()) for name in METADATA if not name.endswith('state-v1.json')}
    return adapter.digest(adapter.canonical(dict(rows=rows,shims=shims,links=links,metadata=metadata)))


def prepare(root,home,admission,projects,env,run_dir,node,adapter):
    """只允许本任务从两个明确批准的同仓库现存候选迁移。"""
    require(home.parents[1].name==TASK,'TASK_ID')
    marker=adapter.web_marker(root,home,admission)
    store=adapter.ordinary(admission['playwrightAndAjv']['store'])
    copied=0
    if marker.exists():
        saved=json.loads(marker.read_text());require(saved['root']==str(root),'WEB_OLD_ROOT')
        rows,shims,links=inspect(root,store,node,adapter)
        require(saved.get('binding')==binding(root,rows,shims,links,adapter),'WEB_TOPOLOGY_DRIFT')
        source_identity=saved['source']
    else:
        common=subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=root).decode().strip()
        candidates=[Path.home()/'.codex/worktrees'/name/'ontology-platform' for name in ('g4-eng-workflow-001','g4-eng-workflow-env')]
        source=None;rejected=[]
        for candidate in candidates:
            if not (candidate/'node_modules/.pnpm').is_dir():
                rejected.append(dict(root=str(candidate),reason='CACHE_MISSING'));continue
            candidate=adapter.ordinary(candidate)
            try:workspace(candidate)
            except (OSError,ValueError,KeyError):
                rejected.append(dict(root=str(candidate),reason='WORKSPACE_STATE_REJECTED'));continue
            source=candidate;break
        require(source is not None,'WEB_SOURCE_MISSING')
        require(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=source).decode().strip()==common,'WEB_SOURCE_REPOSITORY')
        for name in ('package.json','apps/web/package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version'):
            require(adapter.ordinary(source/name).read_bytes()==(root/name).read_bytes(),'WEB_LOCK_DRIFT')
        rows,shims,links=inspect(source,store,node,adapter,allow_cache=True)
        expected_binding=binding(source,rows,shims,links,adapter)
        source_identity=dict(root=str(source),rejectedCandidates=rejected,contentSha256=adapter.digest(adapter.canonical(rows)),shimsSha256=adapter.digest(adapter.canonical(shims)),linksSha256=adapter.digest(adapter.canonical(links)))
        for relative in ('node_modules','apps/web/node_modules'):
            require(not (root/relative).exists(),'WEB_EXISTING_UNBOUND_TREE')
        # 仅复制完整核验过的文件白名单，绝不迁移前任务测试缓存或任意额外模块。
        known={file['path'] for row in rows for file in row['files']}
        for relative in sorted(known|METADATA):
            dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(adapter.ordinary(source/relative),dest)
        copied=2
        for relative,target in links.items():
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.symlink_to(os.path.relpath(root/target,path.parent))
        for relative,target in shims.items():
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(shim_bytes(node,root/target));path.chmod(0o755)
        state=workspace(source)
        state['projects']={str(root)+key[len(str(source)):]:value for key,value in state['projects'].items()}
        state['lastValidatedTimestamp']=0;state.pop('validation',None)
        (root/'node_modules/.pnpm-workspace-state-v1.json').write_text(json.dumps(state,indent=2)+'\n')
        actual,actual_shims,actual_links=inspect(root,store,node,adapter)
        require(binding(root,actual,actual_shims,actual_links,adapter)==expected_binding,'WEB_COPY_CONTENT_DRIFT')
    command=adapter.offline([node,str(home/'pnpm/package/bin/pnpm.cjs'),'--config.verifyDepsBeforeRun=error','--dir','apps/web','run','lint','--help'],root,home,projects)
    command[2]+=' (allow file-write* (literal '+json.dumps(str(root/'node_modules/.pnpm-workspace-state-v1.json'))+'))'
    proc=subprocess.run(command,cwd=root,env=env,capture_output=True,timeout=60)
    adapter.materialize(run_dir/'web-dependency-check.log',proc.stdout+proc.stderr)
    require(proc.returncode==0,'PNPM_DEPENDENCY_STATE_FAILED')
    adapter.materialize(marker,adapter.canonical(dict(root=str(root),source=source_identity,binding=binding(root,rows,shims,links,adapter)))+b'\n')
    return dict(status='DEPENDENCIES_READY',packages=len(rows),materializedTrees=copied,download=0,install=0,restore=0,contentFiles=sum(len(row['files']) for row in rows),source=source_identity)
