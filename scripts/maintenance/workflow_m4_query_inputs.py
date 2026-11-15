"""M4按程序集依赖的四层资格输入；未知实质路径拒绝覆盖声明。"""
from pathlib import Path
import xml.etree.ElementTree as ET
from workflow_execution import sha

PROJECTS = {'contract':'G2ContractTests','query-unit':'QueryTests','source-unit':'ConnectionsTests',
            'security-unit':'SecurityTests','agent-unit':'AgentTests','persistence':'QueryTests',
            'source':'ConnectionsTests','maf-binding':'AgentTests','aba-inflight':'AgentTests'}
INTERPRETERS = {'scripts/maintenance/workflow.py', 'scripts/maintenance/workflow_m4_query_evidence.py', 'scripts/maintenance/workflow_m4_query_inputs.py',
                'scripts/tests/WorkflowQuery.Tests.py', 'docs/development/verification-gates.json'}
ARCHIVE = {'scripts/create-review-package.ps1','scripts/maintenance/workflow_evidence.py',
           'scripts/tests/ReviewPackage.Tests.ps1','scripts/tests/WorkflowDelivery.Tests.py'}
DRIVERS = {'scripts/maintenance/workflow_m4_query.py','scripts/maintenance/workflow-m4-query.mjs',
           'scripts/maintenance/workflow_m4_query_runtime.py','scripts/maintenance/workflow_execution.py',
           'scripts/maintenance/workflow_environment.py','scripts/maintenance/workflow_web_cache.py'}


def layer(path):
    if path in INTERPRETERS: return 'interpretation'
    if path in ARCHIVE or path.startswith('docs/evidence/') or path.endswith('.md'): return 'archive'
    if path in DRIVERS or path.startswith('backend/tests/') or path.startswith('scripts/tests/'): return 'driver'
    if path.startswith(('backend/','apps/web/','docs/contracts/','infra/','samples/','.config/')) or '/' not in path: return 'execution'
    if path.startswith(('scripts/','.github/','.agents/','.codex/','tools/','experiments/')): return 'engineering'
    raise ValueError('QUERY_INPUT_UNCLASSIFIED:'+path)


def project_paths(root, project, all_paths):
    """实际ProjectReference递归闭包加目录所有新源码，嵌入合同和祖先构建配置保守完整绑定。"""
    pending=[root/project];seen=set(); selected=set()
    while pending:
        current=pending.pop().resolve()
        if current in seen: continue
        if not current.is_relative_to(root.resolve()) or not current.is_file(): raise ValueError('QUERY_PROJECT_UNKNOWN')
        seen.add(current)
        directory=str(current.parent.relative_to(root.resolve()))+'/'
        selected.update(path for path in all_paths if path.startswith(directory) and '/bin/' not in path and '/obj/' not in path)
        tree=ET.parse(current)
        for tag in ['EmbeddedResource','Content','None','Compile','Import']:
            for item in tree.iter(tag):
                include=item.get('Include') if tag!='Import' else item.get('Project')
                if not include: continue
                if any(char in include for char in '$*?;'): raise ValueError('QUERY_PROJECT_DYNAMIC_CONTENT')
                resource=(current.parent/include).resolve()
                if not resource.is_relative_to(root.resolve()): raise ValueError('QUERY_PROJECT_EXTERNAL_CONTENT')
                relative=str(resource.relative_to(root.resolve()))
                if relative not in all_paths: raise ValueError('QUERY_PROJECT_CONTENT_NOT_BOUND')
                selected.add(relative)
        for item in tree.iter('ProjectReference'):
            include=item.get('Include','')
            if '$' in include or '*' in include: raise ValueError('QUERY_PROJECT_DYNAMIC_REFERENCE')
            pending.append(current.parent/include)
    selected.update(path for path in all_paths if path.startswith(('docs/contracts/','.config/','samples/')) or '/' not in path or
                    Path(path).name in ('Directory.Build.props','Directory.Build.targets','Directory.Packages.props','NuGet.Config','global.json'))
    return selected


def select(root, name, all_inputs, driver_source=None):
    paths=set(all_inputs)
    for path in paths: layer(path)
    if name in PROJECTS:
        project='backend/tests/OntologyPlatform.'+PROJECTS[name]+'/OntologyPlatform.'+PROJECTS[name]+'.csproj'
        selected=project_paths(root,project,paths)
    elif name.startswith('web-'):
        selected={path for path in paths if path.startswith('apps/web/') or '/' not in path or path=='docs/contracts/g4-connections.openapi.json'}
    else:
        selected=project_paths(root,'backend/src/Hosts/OntologyPlatform.Api/OntologyPlatform.Api.csproj',paths)
        if name.startswith('ui-'): selected.update(path for path in paths if path.startswith('apps/web/'))
    selected.update(path for path in DRIVERS if path in paths and (not name.startswith('web-') or path in {'scripts/maintenance/workflow_m4_query.py','scripts/maintenance/workflow_execution.py','scripts/maintenance/workflow_environment.py','scripts/maintenance/workflow_web_cache.py'}))
    # 当前M4真实源准备明确消费此冻结SQL，不能因属于历史目录而漏掉。
    selected.update(path for path in paths if path == 'experiments/g4-m3-mapping-001/fixture.sql' or path.startswith('infra/development/'))
    result={path:all_inputs[path] for path in sorted(selected) if layer(path) not in ('interpretation','archive')}
    driver='scripts/maintenance/workflow_m4_query.py'
    if driver in result: result[driver]=execution_driver_hash(driver_source if driver_source is not None else (root/driver).read_text(),name)
    return result


def build_inputs(root, project, all_inputs):
    path='backend/tests/'+project+'/'+project+'.csproj'
    return {name:all_inputs[name] for name in sorted(project_paths(root,path,set(all_inputs))) if layer(name) not in ('archive','interpretation')}


def qualification_change(original, current):
    """只解释/归档变化不更换原执行身份；其余差异必须真实重新执行。"""
    changed={path for path in original.keys()|current.keys() if original.get(path)!=current.get(path)}
    layers={layer(path) for path in changed}
    if layers & {'execution','driver','engineering'}: return 'EXECUTE'
    if 'interpretation' in layers: return 'REPARSE'
    return 'ARCHIVE' if changed else 'REUSED'


def demand_scope(original, current, selected):
    """未选工程路径的实质漂移必须说明依赖，不能从一个宽泛分类直接获得复用资格。"""
    changed={path for path in original.keys()|current.keys() if original.get(path)!=current.get(path)}
    for path in changed-set(selected):
        if layer(path)=='engineering': raise ValueError('QUERY_UNCLASSIFIED_ENGINEERING_DRIFT:'+path)


def execution_driver_hash(source, name):
    """同一模块先按顶层职责拆分身份；未知顶层执行语句仍在执行身份内。"""
    import ast
    from workflow_execution import encoded
    tree=ast.parse(source)
    excluded={'qualification_inputs','demand_build_inputs','demand_qualification','qualify','main'}
    nodes=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            omitted = node.name in excluded or (name.startswith('web-') and node.name not in {'prepared','web_check'})
            if omitted:
                # 排除函数体不能漏掉导入时执行的默认参数、装饰器及注解；未知副作用拒绝投影。
                defaults = [*node.args.defaults, *[value for value in node.args.kw_defaults if value is not None]]
                annotations = [node.returns, *[arg.annotation for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]]]
                annotations += [arg.annotation for arg in [node.args.vararg,node.args.kwarg] if arg is not None]
                if node.decorator_list or any(not isinstance(value,ast.Constant) for value in defaults) or any(value is not None for value in annotations):
                    raise ValueError('QUERY_INTERPRETER_IMPORT_SIDE_EFFECT_UNKNOWN')
                continue
        if isinstance(node,ast.ImportFrom) and node.module=='workflow_m4_query_evidence': continue
        if isinstance(node,ast.If) and ast.unparse(node.test)=="__name__ == '__main__'": continue
        nodes.append(ast.dump(node,include_attributes=False))
    return sha(encoded(nodes))


def project_original(root, original, name, all_inputs, driver_source):
    """原件未改写：用其原驱动字节和原全输入投影，只有执行闭包精确相等才可重核。"""
    if original.get('taskId') != 'G4-M4-QUERY-001' or original.get('runId') != 'query-impl-01' or original.get('name') != name or original.get('inputsUnchanged') is not True or original.get('status') != 'PASS' or original.get('exitCode') != 0:
        raise ValueError('QUERY_ORIGINAL_QUALIFICATION_IDENTITY')
    old=original.get('allInputs',original['inputs'])
    path='scripts/maintenance/workflow_m4_query.py'
    if old.get(path)!=sha(driver_source.encode()): raise ValueError('QUERY_ORIGINAL_DRIVER_HASH')
    projected=select(root,name,old,driver_source)
    current=select(root,name,all_inputs)
    demand_scope(old,all_inputs,current)
    if projected!=current: raise ValueError('QUERY_ORIGINAL_EXECUTION_CHANGED')
    return projected
