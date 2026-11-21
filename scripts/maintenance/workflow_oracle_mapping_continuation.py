"""本批唯一已资格前缀的有界后缀衔接；旧阶段不进入新父时间窗。"""
import ast
import json
import re
import subprocess
import uuid
from pathlib import Path

from workflow_oracle_mapping_resources import require
import workflow_execution as ex

PLAN_ID='s2-s3-01-access-01'
RUNTIME_PLAN='s2-s3-01-runtime-01'
REUSED_ACCESS={"commandId":"1afa8fd9ad624134a814126527f7a916","measuredCommit":"b9c55441d8d53b341e0424a746f5bef32950cf37","qualificationSha256":"13b3f88a56191dd16cfa4ec71a3393bb0a1798b5db7cbc74531ef6cdf41d4385","memberIndexSha256":"945280d40ddf750bea9fc4ecc6a3660b23b07871a4c1af2a203ec50fbac470ca"}
PREFIX=dict(commandId='edd1379b83c246329579075d16ccda58',measuredCommit='2a2ea74ff72c22860e4927318913eaece9d14f9f',mode='s2-oracle-relations',
    qualificationCommandId='a495b4d475404f95b726b8b46d6a3663',qualificationSha256='7bb9468c9ed44ae335936a60f3765456b44b125db64cfe05eb1f4e1782172d46',
    memberIndexSha256='91637b9ad1664efc70c8084ec999af10c62bdbca6efb3f885cf13b9366e29b8a')
RUNTIME_PREFIX_DRIVERS={
    'scripts/maintenance/workflow-m4-query.mjs':
        ('4dbd4e6b432d1b85c87abc7a002148bea7865c4dd1316b011315223ebc631542', '1393755557a0a13ca8500375d4ebf40d4782c3550fa5c486151f577fb65e29fe'),
    'scripts/maintenance/workflow-oracle-query-fixture.mjs':
        ('e45fa368dea6721212a138ae533ba979884d950fe0f06cc7f1c15fae34f3ecf2', 'a431cda70e1d0b090cce856c5512fc9fa3c2249689a2035622b3e3a1793b0202'),
    'scripts/maintenance/workflow-oracle-s2.mjs':
        ('e7ab33e1bd38429eb2bc1d7aa7071da3a39022fb4329b6c23404bf9757a546e9', '2b4042e16cfd0b386a185b1d65a9ae3c8e43e6086331a1505068ed002dc90850'),
    'scripts/maintenance/workflow_oracle_mapping_s2.py':
        ('314fae7820ad26533d2a2e651e271de731ae2983d2b91b224754a8afd2aa392b', '3e8d16b2e6630a49de08553520b110f2bb387520b5d9aa398c574796b861839b'),
    'scripts/maintenance/workflow_oracle_mapping_s2_contract.py':
        ('87601573a5b3ea57c6e7f46e96f048262f8eac94fddc76ed2dab7b6424afc8d2', '0109f016e550b5ae7711b07c969fa8b9d77db6996d3c2f5b9f14e7755b88f7b2'),
}
MODES=('s0-oracle-auth','s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-queries','s2-oracle-relations')
TASK='G4-ORACLE-MAPPING-QUERY-001'
RUN='product-resume-01'


BUILD_ORIGINALS={
 'api-build-binding.json':('b07a092a3010b825532b9872774a912e70a4e3b2af20e4defe8cecbecec2a0ea',17510),
 'api-bound-build.txt':('75e6aba04f38e63fd63a116fda5557c4ce5c6996433c815e12d605a3a4b6537d',2773),
 'agent-build-binding.json':('adf54273d9c111e75635d7dd8984a68d2366d7b469418e6f34e1b1fe0c0d6d2a',40373),
 'agent-bound-build.txt':('e75bf142869458a3b03c3c777c0b4b08753fcc0ba704ba2a4ec92193c874789e',2773)}


def historical_backend_input(root):
    """按原构建算法从冻结Git普通文件重算历史输入，不把当前输入说成未变。"""
    commit=PREFIX['measuredCommit']
    require(subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=root,capture_output=True).returncode==0,'S23_PREFIX_BUILD_ANCESTRY')
    items=[]
    for entry in subprocess.check_output(['git','ls-tree','-rz','--full-tree',commit],cwd=root).split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,kind,oid=metadata.decode().split();name=name.decode()
        if not(name.startswith('backend/') or name in ('global.json','NuGet.Config','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version') or name.startswith('Directory.')):continue
        if any(part in ('bin','obj','node_modules','.next') for part in Path(name).parts):continue
        require(kind=='blob' and mode in ('100644','100755'),'S23_PREFIX_BUILD_FILE');items.append((name,oid))
    data=subprocess.check_output(['git','cat-file','--batch'],cwd=root,input=''.join(oid+'\n' for _,oid in items).encode())
    rows={};offset=0
    for name,oid in items:
        end=data.index(b'\n',offset);header=data[offset:end].split()
        require(len(header)==3 and header[0].decode()==oid and header[1]==b'blob','S23_PREFIX_BUILD_BLOB')
        size=int(header[2]);offset=end+1;blob=data[offset:offset+size]
        require(len(blob)==size and data[offset+size:offset+size+1]==b'\n','S23_PREFIX_BUILD_BLOB_SIZE')
        rows[name]=ex.sha(blob);offset+=size+1
    require(offset==len(data),'S23_PREFIX_BUILD_TRAILING');result=ex.sha(json.dumps(rows,sort_keys=True).encode())
    require(len(rows)==414 and result=='53bddbec15779aa28ad25dc3082986027dbc6586f289add3326be2342d3d15ea','S23_PREFIX_BUILD_INPUT');return result


def frozen_build_context(root,dispatch,archive):
    """只有固定已资格五槽允许从原提交与冻结成员索引重开历史构建。"""
    if dispatch.get('commandId')!=PREFIX['commandId']:return None
    require(dispatch.get('taskId')==TASK and dispatch.get('runId')==RUN and dispatch.get('testedCommit')==PREFIX['measuredCommit']
        and dispatch.get('mode') in MODES and dispatch.get('case')=='healthy'
        and dispatch.get('batch',{}).get('stageInputs',{}).get('mode')=='s2-s3-oracle'
        and dispatch['batch']['stageInputs']['plan']['planId']=='s2-s3-01','S23_PREFIX_BUILD_SCOPE')
    frozen=_frozen_qualification(root,archive);base=Path('artifacts/workflow')/TASK;members={}
    for name,(digest,size) in BUILD_ORIGINALS.items():
        item=frozen['members'][name];require(item==dict(path=str(base/name),sha256=digest,sizeBytes=size),'S23_PREFIX_BUILD_ORIGINAL');members[name]=item
    return dict(measuredCommit=PREFIX['measuredCommit'],inputKey=historical_backend_input(root),members=members)


def _read(root,path,archive=None,label=None):
    relative=Path(path)
    require(not relative.is_absolute() and '..' not in relative.parts and relative.is_relative_to(Path('artifacts/workflow')/TASK),'S23_PREFIX_PATH')
    raw=ex.ordinary(root/relative).read_bytes()
    if archive is not None:
        key=label or 'prefix-'+ex.sha(str(relative).encode())+relative.suffix
        if key in archive.examined:require(archive.examined[key]==ex.sha(raw),'S23_PREFIX_MEMBER_CHANGED')
        archive.paths[key]=str(relative);archive.examined[key]=ex.sha(raw)
    return raw


def _frozen_qualification(root,archive=None):
    """消费既有资格命令本身的实际身份、双流和冻结输出，不接受自行填写的PASS摘要。"""
    import workflow_oracle_mapping_evidence as e
    cid=PREFIX['qualificationCommandId'];base=Path('artifacts/workflow')/TASK/'commands'/RUN/cid
    class Commands(e.Originals):
        def __init__(self):self.root=root
        def raw(self,name):
            require(name in (cid+'-receipt.json',cid+'-stdout.txt',cid+'-stderr.txt'),'S23_PREFIX_QUALIFIER_MEMBER')
            return _read(root,base/name.removeprefix(cid+'-'),archive)
    files=subprocess.check_output(['git','ls-tree','-r','--name-only',PREFIX['measuredCommit'],'--','scripts/maintenance'],cwd=root).decode().splitlines()
    inputs={name:ex.sha(e.git_original(root,PREFIX['measuredCommit'],name)) for name in files
            if Path(name).parent==Path('scripts/maintenance') and Path(name).match('workflow*.py')}
    argv=['python3','-B','scripts/maintenance/workflow_oracle_mapping_evidence.py','--task',TASK,'--run-id',RUN,
          '--case-command',PREFIX['commandId'],'--expected-mode',PREFIX['mode']]
    row,out,err=Commands().command(cid,argv,'s23-qualified-complete-prefix',ex.sha(ex.encoded(inputs)),None,root,command_run=RUN)
    require(row['classification']=='SUCCESS' and row['exitCode']==0 and row['deadlineSeconds']==120 and not err
            and ex.sha(out)==PREFIX['qualificationSha256'],'S23_PREFIX_QUALIFIER')
    for kind in ('stdout','stderr'):require(row[kind]['path']==str(root/base/(kind+'.txt')),'S23_PREFIX_QUALIFIER_PATH')
    value=json.loads(out)
    require(value['status']=='CASE_QUALIFIED' and value['commandId']==PREFIX['commandId'] and value['measuredCommit']==PREFIX['measuredCommit']
            and value['mode']==PREFIX['mode'] and value['qualifiedPredecessors']==sorted(MODES[:-1])
            and ex.sha(ex.encoded(value['members']))==PREFIX['memberIndexSha256'],'S23_PREFIX_FROZEN_RESULT')
    return value


def _program(raw,skip):
    return [ast.dump(node,include_attributes=False) for node in ast.parse(raw).body
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in skip]


def compatible_prefix(archive,measured,mode,stage):
    """仅五个准确已资格槽允许本次未执行权限段及父计划选择差异，其余执行内容仍逐字/AST相同。"""
    import workflow_oracle_mapping_evidence as e
    require(measured==PREFIX['measuredCommit'] and mode=='s2-s3-oracle' and stage['plan']['planId']=='s2-s3-01'
            and archive.dispatch['commandId']==PREFIX['commandId'] and archive.dispatch['mode'] in MODES,'S23_PREFIX_COMPAT_SCOPE')
    frozen=_frozen_qualification(archive.root)
    for name,digest in e.drivers(archive.root,mode).items():
        old=e.git_original(archive.root,measured,name);new=ex.ordinary(archive.root/name).read_bytes()
        require(ex.sha(old)==frozen['browserIdentity']['measuredDrivers'][name],'S23_PREFIX_ORIGINAL_DRIVER')
        if old==new:continue
        # 此五槽原件已有固定资格。仅接受复核登记的完整驱动字节对，未登记编辑仍走原严格比较。
        if (ex.sha(old),ex.sha(new))==RUNTIME_PREFIX_DRIVERS.get(name):
            continue
        left,right=old.decode(),new.decode()
        if name.endswith('/workflow-oracle-s2.mjs'):
            right=right.replace('!["s2-s3-01","s2-s3-01-access-01"].includes(shared.plan.planId)','shared.plan.planId !== "s2-s3-01"')
            for added, original in [('          ...(shared.plan.planId==="s2-s3-01-access-01"?{submit:omq.submitSystemLogin}:{}),\n          onProgress:event=>progress({...event,mode})});', '          onProgress:event=>progress({...event,mode})});'), ('await audit("current-catalog-mapping",()=>formalMapping(ctx),formalMappingReads(state));', 'await audit("current-catalog-mapping",()=>formalMapping(ctx),2);')]:
                require(right.count(added)==1,'S23_PREFIX_UNEXECUTED_SUFFIX')
                right=right.replace(added,original,1)
            # 五个历史槽在 ABA 之前。只接受逐字节登记的这一对 ABA 实现，其他入口仍全文核对。
            helper='/** 由当前审核者的正式 HTTP 客户端审批刚创建的 Mapping 提案，并核对同一提案的决定。 */'
            aba='/** B先由三角色正式准备；真正同query源读后A-B-A交给已有正式DI在途测试。 */'
            versions='/** 用正式Catalog命令产生新快照；只改变目录身份，旧绑定拒绝后正式重评发布。 */'
            if helper in right:
                require(right.count(helper)==right.count(aba)==right.count(versions)==1
                        and left.count(aba)==left.count(versions)==1 and helper not in left,'S23_PREFIX_ABA_BOUNDARY')
                previous=left[left.index(aba):left.index(versions)]
                candidate=right[right.index(helper):right.index(versions)]
                require(ex.sha(previous.encode())=='eb68e2914f6be6feac9c00e2e1202b954f657607ac1eebab0503fac5bc6664f5'
                        and ex.sha(candidate.encode())=='65027c49415997b0059d3efa08a7bc15731bf1f7bae7a754b91449a52bf964c6','S23_PREFIX_ABA_CHANGED')
                right=right.replace(candidate,previous,1)
            # 前五槽也没有进入权限测试函数；保留既有权限段边界。
            begin='/** 当前组合grant拒绝后既不执行业务SQL，也不恢复历史原值；每次恢复核原行。 */'
            end='/** B先由三角色正式准备；真正同query源读后A-B-A交给已有正式DI在途测试。 */'
            require(all(text.count(begin)==text.count(end)==1 for text in (left,right)),'S23_PREFIX_ACCESS_BOUNDARY')
            left=left[:left.index(begin)]+left[left.index(end):];right=right[:right.index(begin)]+right[right.index(end):]
        elif name.endswith('/workflow_oracle_mapping_platform_recovery.py'):
            start_patch="            from workflow_oracle_runtime_window import policy, published_graphs\n            if (window := policy()) is not None:\n                receipt['currentGraphs']=published_graphs(cid,started,int(pid),basis,close_sha=window['priorCloseSha256'])\n            else:\n                receipt['currentGraphs']=current_fuseki_graphs(cid,basis)"
            graph_patch="    if row.get('currentGraphs',{}).get('kind')=='s2-s3-01-runtime-01':\n        from workflow_oracle_runtime_window import published_graphs\n        require(row['stage']=='product-resume-01' and row['role']=='fuseki' and row['status']=='RUNNING' and\n                row['productUse']=='CURRENT_GRAPHS_VERIFIED' and\n                published_graphs(cid,started,pid,row['checkpoint'],row['currentGraphs']['commands'],close_sha=row['currentGraphs']['close'])==row['currentGraphs'],\n                'TDB_RUNTIME_GRAPHS')\n        return row['attempt']\n"
            require(right.count(start_patch)==right.count(graph_patch)==1,'S23_PREFIX_RUNTIME_GRAPH_SCOPE')
            right=right.replace(start_patch,"            receipt['currentGraphs']=current_fuseki_graphs(cid,basis)",1).replace(graph_patch,'',1)
            from workflow_oracle_mapping_continuity import BRANCH
            require(right.count(BRANCH)==1 and BRANCH not in left,'S23_PREFIX_GENERATION_BRANCH')
            right=right.replace(BRANCH,'',1)
            from workflow_oracle_mapping_repeat import BRANCH as REPEAT_BRANCH
            require(right.count(REPEAT_BRANCH)==1,'S23_PREFIX_REPEAT_BRANCH')
            right=right.replace(REPEAT_BRANCH,'',1)
            from workflow_oracle_mapping_acl_host import BRANCH as ACL_BRANCH
            require(right.count(ACL_BRANCH)==1,'S23_PREFIX_ACL_GRAPH_BRANCH')
            right=right.replace(ACL_BRANCH,'',1)
            close_admission='        # 产品收尾与同批开放采用相同的已核基线缓存扣减及40GiB上限。\n        from workflow_oracle_mapping_capacity import before_product_source as before_source\n'
            require(right.count(close_admission)==1 and close_admission not in left,'S23_PREFIX_CLOSE_ADMISSION')
            right=right.replace(close_admission,'',1)
            start=right.index('def start_owned(');end=right.index('def recover_fixed_row(',start)
            section=right[start:end]
            start_guard="    check_resources=platform.before_source\n    if product:\n        require(group=='replacement','TDB_PRODUCT_GROUP')\n        phase=product\n        from workflow_oracle_mapping_capacity import before_product_source\n        check_resources=before_product_source\n"
            require(section.count(start_guard)==1 and section.count('check_resources(')==2,'S23_PREFIX_START_ADMISSION')
            section=section.replace(start_guard,"    if product:\n        require(group=='replacement','TDB_PRODUCT_GROUP')\n        phase=product\n",1).replace('check_resources(','platform.before_source(')
            right=right[:start]+section+right[end:]
        elif name.endswith('/workflow_oracle_mapping_resume.py'):
            from workflow_oracle_mapping_capacity import ORIGINAL_CALL,PRODUCT_CALL
            require(right.count(PRODUCT_CALL)==1 and PRODUCT_CALL not in left,'S23_PREFIX_CAPACITY_BRANCH')
            right=right.replace(PRODUCT_CALL,ORIGINAL_CALL,1)
        elif name==e.DRIVER:
            right=right.replace('onProgress: event => oracleProgress({ ...event, mode }),\n          ...(shared?.plan?.planId === "s2-s3-01-access-01" ? { submit: omq.submitSystemLogin } : {}) });','onProgress: event => oracleProgress({ ...event, mode }) });')
            right=right.replace('(input.plan.planId === "s2-s3-01-access-01" ? omq.s2AccessPlan() : omq.s2Plan)','omq.s2Plan')
        elif name.endswith('/workflow-oracle-query-fixture.mjs'):
            # 旧plan不传submit；仅剔除准确新helper和未进入的选项分支，原认证逻辑仍全文比较。
            begin='/** 本批用户明确授权代填：仅四原账号、指定系统条目、已核验的本机正式表单。 */'
            end='export function currentProjection(label, me) {'
            require(right.count(begin)==right.count(end)==1,'S23_PREFIX_LOGIN_BOUNDARY')
            added=right[right.index(begin):right.index(end)]
            require(ex.sha(added.encode())=='f5d6637496e365a60993ff7f3f31e39b5ec2b3ca1dac32b50a2609195e88b894','S23_PREFIX_LOGIN_HELPER')
            right=right.replace(added,'',1).replace('    if (options.submit && submittedAt === undefined) {\n      const remaining = () => {\n        if (options.signal?.aborted || page.isClosed()) throw loginFailure("ORACLE_LOGIN_CANCELLED");\n        return loginRemaining(deadline, now);\n      };\n      remaining();\n      await options.submit(page, label, remaining);\n    }\n','')
            right=right.replace('export function s2AccessPlan() { return Object.freeze(JSON.parse(readFileSync(new URL("./workflow-oracle-s2-access-plan.json", import.meta.url), "utf8"))); }\n','')
            right=right.replace('"access_case", "runtime_case", "same_grant"','"access_case", "runtime_case"')
        elif name.endswith('/workflow_oracle_mapping_s2_contract.py'):
            right=right.replace("report['batch']['planId'] in ('s2-s3-01','s2-s3-01-access-01')","report['batch']['planId']=='s2-s3-01'")
            right=right.replace("    if mode=='s2-oracle-access' and report['batch']['planId']=='s2-s3-01-access-01':required[mode]=required[mode]|{'healthy-relations'}\n",'')
            right=right.replace("    if report['mode']=='s2-oracle-access' and report['batch']['planId']=='s2-s3-01-access-01':__import__('workflow_oracle_mapping_readiness').qualify(report)\n",'')
            right=right.replace("    if report['mode']=='s2-oracle-access' and report['batch']['planId']=='s2-s3-01-access-01':__import__('workflow_oracle_mapping_readiness').reopen(archive,report,host,origin)\n",'')
            row="    if report['batch']['planId']=='s2-s3-01-access-01':\n        if report['mode']=='s2-oracle-access':\n            from workflow_oracle_mapping_acl_observation import reopen\n            reopen(archive,report,host,origin)\n        if report['mode'] in ('s2-oracle-versions','s2-oracle-connection'):\n            require([w['expectedReads'] for w in report['oracleWindows'] if w['name']=='current-catalog-mapping']==[4],'S23_NEW_DOUBLE_TABLE_MAPPING_READS')\n"
            require(right.count(row)==1,'S23_PREFIX_SUFFIX_CONSUMER')
            right=right.replace(row,'',1)
            # 只有未执行的 ABA 模式调用新增的响应核对，其余消费者语法树逐节点相同。
            selection_call="    if mode=='s2-oracle-aba':current_selection_receipt(report)\n"
            selection_start='def current_selection_receipt(report):'
            if selection_start in right:
                require(right.count(selection_start)==right.count('def qualify(report):')==right.count(selection_call)==1,'S23_PREFIX_SELECTION_BOUNDARY')
                selection=right[right.index(selection_start):right.index('def qualify(report):')]
                require(ex.sha(selection.encode())=='9406565fd1fc216869377bf20511a62e1b10dcd14ed5e98600576b2e42c97f02','S23_PREFIX_SELECTION_CONSUMER')
                right=right.replace(selection,'',1).replace(selection_call,'',1)
            require(_program(left,{'frozen_plan'})==_program(right,{'frozen_plan'}),'S23_PREFIX_CONTRACT_CHANGED')
            continue
        else:require(False,'S23_PREFIX_DRIVER_CHANGED')
        require(left==right,'S23_PREFIX_EXECUTED_PATH_CHANGED')
    return True



def frozen_member(root,item,archive=None,name=None):
    """冻结路径若被正式资源生命周期推进，仅从已有内容键副本取回相同原字节。"""
    path=Path(item['path'])
    if path.parent==Path('artifacts/workflow')/TASK and path.name in BUILD_ORIGINALS:
        digest,size=BUILD_ORIGINALS[path.name]
        require(item['sha256']==digest and item['sizeBytes']==size,'S23_PREFIX_BUILD_ORIGINAL')
        path=path.with_name(path.stem+'-'+digest+path.suffix);raw=_read(root,path,archive,name)
        require(len(raw)==size and ex.sha(raw)==digest,'S23_PREFIX_ORIGINAL_CHANGED');return raw
    runtime_originals={'formal-api-inputs.json':('2369e985350e0a7b0b38319f0e13823d126fcad73bbd1ef96ddec13ff2cfd63a',845),
        'formal-api-compose.json':('e08441297488c9c83ed537853df9ba18dd1131fbf1f32e6ec50dbfffb5c6ecff',6885)}
    if path.parent==Path('artifacts/workflow')/TASK/RUN and path.name in runtime_originals:
        digest,size=runtime_originals[path.name];require((item['sha256'],item['sizeBytes'])==(digest,size),'S23_PREFIX_RUNTIME_ORIGINAL')
        path=path.with_name(path.stem+'-'+digest+path.suffix)
    raw=_read(root,path)
    if len(raw)!=item['sizeBytes'] or ex.sha(raw)!=item['sha256']:
        require(path==Path('artifacts/workflow')/TASK/RUN/'formal-resources.json','S23_PREFIX_ORIGINAL_CHANGED')
        path=path.with_name('formal-resources-'+item['sha256']+'.json');raw=_read(root,path)
    require(len(raw)==item['sizeBytes'] and ex.sha(raw)==item['sha256'],'S23_PREFIX_ORIGINAL_CHANGED')
    return _read(root,path,archive,name)


def prefix_result(root,archive=None):
    """先核冻结资格及所有引用，再按当前消费者重开五槽；只走上述精确兼容条件。"""
    import workflow_oracle_mapping_evidence as e
    frozen=_frozen_qualification(root,archive)
    for name,item in frozen['members'].items():
        frozen_member(root,item,archive,'prefix-'+name)
    checked={};members={};result=None
    for mode in MODES:
        result=e.reopen_runtime_case(root,TASK,RUN,PREFIX['commandId'],expected_mode=mode,_checked=checked)
        for name,item in result['members'].items():
            if name in members:require(members[name]==item,'S23_PREFIX_ORIGINAL_ALIAS')
            members[name]=item
            _read(root,item['path'],archive,'prefix-'+name)
    relocations=[dict(originalPath=item['path'],resolvedPath=members[name]['path'],sha256=item['sha256'],sizeBytes=item['sizeBytes'])
        for name,item in frozen['members'].items() if item['path']!=members[name]['path']]
    return {**result,'members':members,'frozenMemberRelocations':relocations},frozen


def _state_projection(state):
    return dict(connectionId=state['connectionId'],catalogSnapshotId=state['catalog']['snapshotId'],catalogFingerprint=state['catalog']['schemaFingerprint'],
        mappingReceipt=state.get('mappingCurrentReceipt') or state['mappingReceipt'],latestQuery={k:state['latestQuery'][k]
        for k in ('queryId','resultHash','reportName','actor','sessionHash')})


def _context(qualified,root):
    from workflow_oracle_mapping_evidence import stable_host
    reports={mode:next(name for name in qualified['members'] if name.startswith('browser-'+mode+'-') and name.endswith('.json')) for mode in ('s2-oracle-queries','s2-oracle-mapping')}
    query=json.loads(_read(root,qualified['members'][reports['s2-oracle-queries']]['path']))
    mapping=json.loads(_read(root,qualified['members'][reports['s2-oracle-mapping']]['path']))
    source=json.loads(_read(root,qualified['members']['formal-run-s2-s3-oracle-'+PREFIX['commandId']+'.json']['path']))
    return query,mapping,source['host']



def resumed_host(previous,current):
    """同批停止后再启动只允许进程代次及已登记无状态API身份变化；固定资源和构建仍完全一致。"""
    from workflow_oracle_mapping_evidence import stable_host
    import copy
    before=stable_host(previous);after=stable_host(current)
    normalized=[]
    for host in (before,after):
        value=copy.deepcopy(host);value.pop('resourceManifestSha256')
        for role,service in value['services'].items():
            service.pop('pid');service.pop('startedAt')
            if role in ('api','api-secondary'):service.pop('containerId')
        normalized.append(value)
    require(normalized[0]==normalized[1],'S23_PREFIX_FIXED_HOST_CHANGED')
    return dict(status='SAME_PERSISTENT_INPUTS_NEW_PROCESS_GENERATION',previousManifestSha256=before['resourceManifestSha256'],
        currentManifestSha256=after['resourceManifestSha256'],services={role:dict(previous={k:before['services'][role][k] for k in ('containerId','pid','startedAt')},
        current={k:after['services'][role][k] for k in ('containerId','pid','startedAt')}) for role in before['services']})


def qualified_access(root,archive=None):
    """按冻结索引逐件核验既有 access 原件，包括已迁移至内容键副本的正式资源、构建与日志。"""
    ref=REUSED_ACCESS;cid=ref['commandId'];base=Path('artifacts/workflow')/TASK/RUN
    raw=_read(root,base/'s2-s3-01'/('access-qualification-'+cid+'.json'),archive)
    require(ex.sha(raw)==ref['qualificationSha256'],'S23_ACCESS_QUALIFICATION_BYTES')
    proof=json.loads(raw);members=proof['members']
    require((proof['taskId'],proof['runId'],proof['commandId'],proof['measuredCommit'],proof['mode'],proof['status'],proof['checks'])
            ==(TASK,RUN,cid,ref['measuredCommit'],'s2-oracle-access','CASE_QUALIFIED',78)
            and len(members)==1236 and ex.sha(ex.encoded(members))==ref['memberIndexSha256'],'S23_ACCESS_QUALIFICATION_SCOPE')
    for name,member in members.items():
        path=Path(member['path'])
        mutable = ((path.parent==base and path.name in ('formal-resources.json','formal-api-inputs.json','formal-api-compose.json'))
                   or (path.parent==base.parent and (path.name in BUILD_ORIGINALS
                                                    or path.name in ('query-build-binding.json','query-bound-build.txt'))))
        if mutable:
            backup=path.with_name(path.stem+'-'+member['sha256']+path.suffix)
            if (root/backup).is_file():path=backup
        value=_read(root,path,archive,'reused-access-'+name)
        require(len(value)==member['sizeBytes'] and ex.sha(value)==member['sha256'],'S23_ACCESS_MEMBER_BYTES')
    return ref


def activation_chain_sql(mapping_id):
    """在同一只读快照核对当前行、不可变回执、命令与实际映射范围。"""
    require(re.fullmatch('mapping-[a-f0-9]{32}', mapping_id), 'S23_PREFIX_MAPPING_ID')
    return f'''SELECT json_build_object(
 'current', json_build_array(v."ActivationId",v."ActivationRevision",v."ReleaseId"),
 'receipts', (SELECT json_agg(json_build_object(
    'receipt', convert_from(a."CanonicalBytes",'UTF8')::json,
    'connection', a."BindingJson"::json->>'sourceConnectionId',
    'catalog', a."BindingJson"::json->>'sourceCatalogSnapshotId',
    'fingerprint', a."BindingJson"::json->>'sourceCatalogFingerprint',
    'check', a."CheckId", 'command', m."CommandId")
    ORDER BY a."ActivationRevision")
 FROM connections."MappingActivations" a
 JOIN connections."MappingActivationChecks" ck ON ck."Id"=a."CheckId" AND ck."ProposalId"=a."ProposalId"
 JOIN connections."MappingProposals" p ON p."Id"=a."ProposalId" AND p."ActivationId"=a."Id"
 JOIN connections."MappingCommands" m ON m."MappingId"=a."MappingId" AND m."ResponseBytes"=a."CanonicalBytes"
 WHERE a."MappingId"=v."MappingId" AND a."OrganizationId"=v."OrganizationId" AND a."SiteIds"=v."SiteIds"
 AND ck."MappingId"=a."MappingId" AND p."DecidedBy"<>p."SubmittedBy"
 AND a."ContentHash"=encode(sha256(a."CanonicalBytes"),'hex')))
 FROM connections."MappingActives" v WHERE v."MappingId"='{mapping_id}'
 AND v."OrganizationId"='org-demo' AND v."SiteIds"=ARRAY['site-a']::text[];'''.encode()


def check_activation_chain(binding, state, recorded_b, chain):
    """历史查询继续锚定旧 A。当前投影只能通过同一 Mapping 的连续三笔真实提交。"""
    old, current = binding['activation'], state['mappingReceipt']
    receipts = chain['receipts'] or []
    require(len(receipts) == 3, 'S23_PREFIX_ACTIVATION_COUNT')
    a, b, restored = [row['receipt'] for row in receipts]
    def receipt_bytes(value):
        # 正式 HTTP 和 CanonicalBytes 使用不同 UTC 后缀，保留原有七位小数精度。
        stamp = value['activatedAtUtc']
        require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.]\d{1,7})?(?:Z|[+]00:00)',stamp),
                'S23_PREFIX_RECEIPT_TIME')
        return {**value, 'activatedAtUtc': stamp.removesuffix('+00:00').removesuffix('Z')+'Z'}
    require(receipt_bytes(a) == receipt_bytes(old) and receipt_bytes(b) == receipt_bytes(recorded_b)
            and receipt_bytes(restored) == receipt_bytes(current)
            and len({row['activationId'] for row in (a,b,restored)}) == 3
            and len({row['proposalId'] for row in (a,b,restored)}) == 3
            and all(row['mappingId'] == old['mappingId'] for row in (b,restored))
            and [row['activationRevision'] for row in (b,restored)] ==
                [old['activationRevision']+1, old['activationRevision']+2]
            and b['previousReleaseId'] == old['mappingReleaseId'] != b['mappingReleaseId']
            and restored['previousReleaseId'] == b['mappingReleaseId']
            and restored['kind'] == 'ROLLBACK' and b['kind'] == 'PUBLISH'
            and restored['mappingReleaseId'] == old['mappingReleaseId']
            and restored['manifestHash'] == old['manifestHash']
            and chain['current'] == [current['activationId'],current['activationRevision'],current['mappingReleaseId']],
            'S23_PREFIX_ACTIVATION_CHAIN')
    require(all((row['connection'],row['catalog'],row['fingerprint']) ==
                (binding['connectionId'],binding['catalogSnapshotId'],state['catalogFingerprint'])
                for row in receipts) and all(len({row[key] for row in receipts}) == 3
                and all(row[key] for row in receipts) for key in ('command','check')), 'S23_PREFIX_CHAIN_BINDING')


def prefix_activation(root, host, binding, state, command_id=None, archive=None):
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    cid = '5b90bb8f66fb4ddd9bfeddbe5015133a'
    raw = _read(root, Path('artifacts/workflow')/TASK/'commands'/RUN/cid/'stdout.txt', archive)
    require(ex.sha(raw) == 'd1fba9b095bec4a31831c598e4bbf7bd043579d923e57efd3403a0dab74efc15', 'S23_PREFIX_ABA_STDOUT')
    original, = [json.loads(line) for line in raw.splitlines() if line.startswith(b'{"taskId":')]
    sql = activation_chain_sql(binding['activation']['mappingId'])
    if command_id is None:
        _, command_id = p.read_pg(sql,'s23-prefix-activation')
    require(re.fullmatch('[a-f0-9]{32}',command_id), 'S23_PREFIX_ACTIVATION_COMMAND')
    pg = host['services']['platform-pg']
    argv = ['docker','--context','desktop-linux','exec','-i','--user','postgres',pg['containerId'],
            'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    rec,out,err = c.command(root,command_id,RUN,argv,'omq-pg-s23-prefix-activation',
                            ex.sha(b'BEGIN READ ONLY;\n'+sql+b'\nCOMMIT;'),15,archive)
    require(not err and utc(pg['startedAt']) < utc(rec['startedAtUtc']), 'S23_PREFIX_ACTIVATION_GENERATION')
    check_activation_chain(binding,state,original['activatedB'],json.loads(out))
    return command_id


def prepare_prefix(root,descriptor,plan_id=PLAN_ID):
    """父命令启动前冻结当前基线及原query身份；不读取或移植任何旧会话材料。"""
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_s2 as s
    from workflow_oracle_mapping_evidence import stable_host
    require(descriptor==PREFIX,'S23_PREFIX_DESCRIPTOR');qualified,_=prefix_result(root)
    if plan_id==RUNTIME_PLAN:qualified_access(root)
    query,mapping,host=_context(qualified,root);state=json.loads((p.AREA.parent/RUN/'oracle-two-table.json').read_bytes())
    projection=_state_projection(state);old=query['oracleBinding'];latest=projection['latestQuery']
    require(projection['connectionId']==old['connectionId'] and projection['catalogSnapshotId']==old['catalogSnapshotId']
            and (plan_id==RUNTIME_PLAN or projection['mappingReceipt']==old['activation']) and latest['reportName'] in qualified['members'] and json.loads(_read(root,qualified['members'][latest['reportName']]['path']))==query
            and latest['queryId']==query['oracleCases'][2]['queryId'] and latest['resultHash']==query['oracleCases'][2]['sha256'],'S23_PREFIX_CURRENT_BINDING')
    from workflow_oracle_mapping_acl_host import lifecycle
    if plan_id==RUNTIME_PLAN:
        from workflow_oracle_runtime_window import runtime_continuity as lifecycle
    current=p.runtime_binding();continuity=lifecycle(root,host,current)
    snapshot=s.source_snapshot();require(snapshot['rows']==query['independentSource']['rows'] and snapshot['hashes']==query['independentSource']['hashes'],'S23_PREFIX_CURRENT_SOURCE')
    observation=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',planId=plan_id,qualifiedPrefix=PREFIX,state=projection,host=current,source=snapshot,hostContinuity=continuity)
    if plan_id == RUNTIME_PLAN:
        observation['activationChainCommand'] = prefix_activation(root,current,old,projection)
    name='prefix-observation-'+uuid.uuid4().hex+'.json';path=p.AREA.parent/RUN/'s2-s3-01'/name;p.save(path,observation)
    return dict(file=name,sha256=ex.sha(path.read_bytes()))


def reopen_prefix(root,stage,archive):
    """新父窗口只消费自己的阶段；历史前缀作为另一个父命令的完整资格引用。"""
    import workflow_oracle_mapping_s2 as s
    from workflow_oracle_mapping_evidence import stable_host,host_observation,build_binding,utc
    require(stage['plan']['planId'] in (PLAN_ID,RUNTIME_PLAN) and stage['plan']['qualifiedPrefix']==PREFIX,'S23_PREFIX_PLAN')
    qualified,_=prefix_result(root,archive);query,mapping,host=_context(qualified,root)
    ref=stage['qualifiedPrefix'];require(re.fullmatch('prefix-observation-[a-f0-9]{32}[.]json',ref['file']),'S23_PREFIX_OBSERVATION_NAME')
    path=Path('artifacts/workflow')/TASK/RUN/'s2-s3-01'/ref['file'];raw=_read(root,path,archive)
    require(ex.sha(raw)==ref['sha256'],'S23_PREFIX_OBSERVATION_HASH');obs=json.loads(raw)
    require((obs['taskId'],obs['runId'],obs['batch'],obs['planId'])==(TASK,RUN,'s2-s3-01',stage['plan']['planId']) and obs['qualifiedPrefix']==PREFIX
            and stable_host(obs['host'])==stable_host(archive.dispatch['host']),'S23_PREFIX_OBSERVATION_SCOPE')
    from workflow_oracle_mapping_acl_host import lifecycle
    if stage['plan']['planId']==RUNTIME_PLAN:
        from workflow_oracle_runtime_window import runtime_continuity as lifecycle
    lifecycle(root,host,obs['host'],obs['hostContinuity'],archive)
    host_observation(archive,obs['host'],build_binding(archive,'api',root),root)
    snapshot=obs['source'];require(snapshot['projectionVersion']==2 and snapshot['rows']==query['independentSource']['rows']
            and snapshot['hashes']==query['independentSource']['hashes'] and len(snapshot['commandIds'])==2,'S23_PREFIX_SOURCE')
    columns='ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,'+','.join("to_char("+c+",'YYYYMMDDHH24MISSFF6')" for c in s.COLUMNS[7:])
    for index,(cid,table) in enumerate(zip(snapshot['commandIds'],s.TABLES,strict=True)):
        sql='select json_array('+columns+' null on null returning varchar2(500)) from '+table+' order by ROW_ID;'
        argv=['docker','--context','desktop-linux','exec','-i',host['oracle']['containerId'],'sqlplus','-L','-s','/ as sysdba']
        row,out,err=archive.command(cid,argv,'s23-independent-source-snapshot',ex.sha(sql.encode()),None,root)
        require(row['classification']=='SUCCESS' and row['exitCode']==0 and [json.loads(x,parse_float=str) for x in out.decode().splitlines() if x.strip()]==snapshot['rows'][index],'S23_PREFIX_SOURCE_COMMAND')
    parent=archive.read(archive.dispatch['commandId']+'-receipt.json');previous=archive.read(PREFIX['commandId']+'-receipt.json')
    chain = obs.get('activationChainCommand')
    if stage['plan']['planId'] == RUNTIME_PLAN and archive.dispatch['commandId'] not in (
            '1080791aa97546f29c34fd915618ecef','c02e89f8d8f2481f90058606ccf71b29'):
        require(chain, 'S23_PREFIX_ACTIVATION_MISSING')
    if chain:
        prefix_activation(root,obs['host'],query['oracleBinding'],obs['state'],chain,archive)
    for cid in [obs['host']['commandId'],*snapshot['commandIds'],*([chain] if chain else [])]:
        sample=archive.read(cid+'-receipt.json')
        require(utc(previous['endedAtUtc'])<=utc(sample['startedAtUtc'])<=utc(sample['endedAtUtc'])<=utc(parent['startedAtUtc']),'S23_PREFIX_OBSERVATION_ORDER')
    binding=query['oracleBinding'];state=obs['state'];latest=state['latestQuery']
    require(state['connectionId']==binding['connectionId'] and state['catalogSnapshotId']==binding['catalogSnapshotId'] and (chain or state['mappingReceipt']==binding['activation'])
        and latest['queryId']==query['oracleCases'][2]['queryId'] and latest['resultHash']==query['oracleCases'][2]['sha256']
        and latest['reportName'] in qualified['members'] and json.loads(_read(root,qualified['members'][latest['reportName']]['path']))==query,'S23_PREFIX_QUERY_BINDING')
    reuse={'reusedAccess':qualified_access(root,archive)} if stage['plan']['planId']==RUNTIME_PLAN else {}
    return dict(**reuse,status='REUSED_QUALIFIED_PREFIX',commandId=PREFIX['commandId'],measuredCommit=PREFIX['measuredCommit'],modes=list(MODES),
        memberIndexSha256=ex.sha(ex.encoded(qualified['members'])),memberCount=len(qualified['members']),newAuthenticationRequired=True,scope='Separate old parent; no historical stages or source events included in current parent window')


def run_access_suffix():
    """按原十一槽计划执行，供其既有调用者使用。"""
    return _run_suffix(PLAN_ID)


def run_runtime_suffix():
    """按冻结的十槽计划执行，access 按准确原件单列。"""
    return _run_suffix(RUNTIME_PLAN)


def _run_suffix(plan_id):
    """固定同批后缀的实际入口；原平台与审计依赖保持完整原字节，不替换或猴补其函数。"""
    import os
    import workflow_oracle_mapping_platform as p
    from workflow_oracle_mapping_evidence import browser_invocation,batch_plan
    require(p.product_run()==RUN,'S23_SUFFIX_RUN')
    root=p.ROOT;area=p.AREA.parent/RUN;mode='s2-s3-oracle';case='healthy'
    if plan_id == RUNTIME_PLAN:
        from workflow_oracle_runtime_window import policy, monitored
        require(policy() is not None, 'WINDOW_DECISION_REQUIRED')
    resource=p.admission()
    pre=ex.run(['python3','-B','scripts/maintenance/execution_preflight.py','check','--milestone',TASK,'--phase','runtime'],root,
        task=TASK,run_id=RUN,stage='omq-consumers-'+mode,input_key=ex.sha(Path(__file__).read_bytes()),timeout=18)
    require(pre.returncode==0,'FORMAL_CONSUMERS_'+pre.receipt['commandId'])
    statefile=area/'runtime-fixture.json';state=json.loads(statefile.read_bytes())
    stage=dict(phase='s2',mode=mode,case=case,prerequisiteSha256=ex.sha(statefile.read_bytes()))
    stage.update({k:state[k] for k in ('connectionId',) if k in state})
    if 'subjects'in state:stage['readerSubjectId']=state['subjects']['reader']
    if 'catalog'in state:stage['catalogSnapshotId']=state['catalog']['snapshotId'];stage['catalogFingerprint']=state['catalog']['schemaFingerprint']
    if 'mappingReceipt'in state:stage['activationRevision']=state['mappingReceipt']['activationRevision'];stage['mappingReleaseId']=state['mappingReceipt']['mappingReleaseId']
    execution=uuid.uuid4().hex;stage['plan']=batch_plan(root,mode,plan_id);stage['executionId']=execution
    stage['batchInput']='s2-s3-'+execution+'.json';stage['qualifiedPrefix']=prepare_prefix(root,stage['plan']['qualifiedPrefix'],plan_id)
    p.save(area/stage['batchInput'],dict(executionId=execution,plan=stage['plan'],qualifiedPrefix=stage['qualifiedPrefix']))
    host=p.runtime_binding();api=p.build.validate('api',TASK);tests=p.build.validate('agent',TASK)
    argv,key,label=browser_invocation(root,mode,case,host,api,tests,stage)
    pattern='browser-'+mode+'-'+'[0-9]'*13+'.json';before=set(area.glob(pattern))
    environment={**os.environ,'OMQ_PROGRESS_FILE':'s2-s3-'+execution+'.jsonl'}
    import contextlib
    events = p.AREA.parent/'command-events.jsonl'
    offset = events.stat().st_size
    result = None
    protection = None
    try:
        with monitored(resource['attempt']) if plan_id == RUNTIME_PLAN else contextlib.nullcontext():
            result=ex.run(argv,root,task=TASK,run_id=RUN,stage=label,input_key=key,parent_id=host['commandId'],timeout=stage['plan']['deadlineSeconds'],environment=environment)
    except (ValueError, KeyboardInterrupt, OSError, subprocess.SubprocessError) as error:
        if plan_id != RUNTIME_PLAN:
            raise
        protection = type(error).__name__ + ' ' + str(error)[:240]
        if result is None:
            with events.open('rb') as stream:
                stream.seek(offset)
                ended = [row for line in stream if (row:=json.loads(line)).get('event')=='END'
                         and row['inputFingerprint']==key and row['parentId']==host['commandId'] and row['stage']==label]
            if len(ended)!=1:
                p.save(area/('runtime-prestart-'+execution+'.json'),dict(reason=protection,executionId=execution))
                raise
            from types import SimpleNamespace
            receipt = json.loads((area.parent/'commands'/RUN/ended[0]['commandId']/'receipt.json').read_bytes())
            code = receipt['exitCode']
            result = SimpleNamespace(receipt=receipt,returncode=128-code if code is not None and code<0 else code or 70)
    after=set(area.glob(pattern))-before
    entry=dict(taskId=TASK,runId=RUN,mode=mode,case=case,stageInputs=stage,host=host,builds={'api':api,'agent':tests},
        commandId=result.receipt['commandId'],exitCode=result.returncode,resourceAttempt=resource['attempt'],preflightCommandId=pre.receipt['commandId'],
        reports=[path.name for path in sorted(after)],testedCommit=p.local('tested-head',['git','rev-parse','HEAD']))
    if protection:
        entry.update(protection=protection,parentExitCode=result.receipt['exitCode'])
        entry['exitCode']=result.returncode or 70
    p.save(area/('formal-run-'+mode+'-'+result.receipt['commandId']+'.json'),entry)
    try:
        p.save(area/('formal-audit-'+result.receipt['commandId']+'.json'),p.audit_window(result.receipt['startedAtUtc'],result.receipt['endedAtUtc']))
        require(len(after)==1,'BATCH_REPORT_COUNT');batch=json.loads(next(iter(after)).read_bytes())
        for item in batch['stages']:
            require(re.fullmatch(r'browser-[a-z0-9-]+-[0-9]{13}[.]json',Path(item['report']).name),'BATCH_STAGE_NAME')
            p.save(area/('formal-audit-'+result.receipt['commandId']+'-'+item['mode']+'.json'),p.audit_window(item['startedAtUtc'],item['finishedAtUtc']))
    except Exception as error:
        p.save(area/('formal-audit-failure-'+result.receipt['commandId']+'.json'),dict(taskId=TASK,reason=str(error)))
        if not entry['exitCode']:
            raise
    return dict(mode=mode,commandId=result.receipt['commandId'],exitCode=entry['exitCode'],reports=entry['reports'],stageFailure=[json.loads(path.read_bytes()).get('failure') for path in after])
