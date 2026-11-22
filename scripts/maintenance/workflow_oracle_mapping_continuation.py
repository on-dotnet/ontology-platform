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
        ('4dbd4e6b432d1b85c87abc7a002148bea7865c4dd1316b011315223ebc631542', 'e3ea8fe13eaf2a348bd69069b0e2f202463f5258de98d396de6539af6850894b'),
    'scripts/maintenance/workflow-oracle-query-fixture.mjs':
        ('e45fa368dea6721212a138ae533ba979884d950fe0f06cc7f1c15fae34f3ecf2', '10227b27e903e65e25bb292ec6dbb7b507c1f523f51b74a240a7aef89349b1d9'),
    'scripts/maintenance/workflow-oracle-s2.mjs':
        ('e7ab33e1bd38429eb2bc1d7aa7071da3a39022fb4329b6c23404bf9757a546e9', 'd1fe4a915ced5ff4d274bf21a80e62d56d85c31b81c234f29e45a4a3b323bf0a'),
    'scripts/maintenance/workflow_oracle_mapping_s2.py':
        ('314fae7820ad26533d2a2e651e271de731ae2983d2b91b224754a8afd2aa392b', 'e729fa216069acc87b3794aef689999a9a93cf984b484c406743ef67c274621f'),
    'scripts/maintenance/workflow_oracle_mapping_s2_contract.py':
        ('87601573a5b3ea57c6e7f46e96f048262f8eac94fddc76ed2dab7b6424afc8d2', 'e360d4047a3dd0fe50f3c6546fb1cd2581db5c52120dccfebe58fa1a18bef3d7'),
}
MODES=('s0-oracle-auth','s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-queries','s2-oracle-relations')
TASK='G4-ORACLE-MAPPING-QUERY-001'
RUN='product-resume-01'


BUILD_ORIGINALS={
 'api-build-binding.json':('b07a092a3010b825532b9872774a912e70a4e3b2af20e4defe8cecbecec2a0ea',17510),
 'api-bound-build.txt':('75e6aba04f38e63fd63a116fda5557c4ce5c6996433c815e12d605a3a4b6537d',2773),
 'agent-build-binding.json':('adf54273d9c111e75635d7dd8984a68d2366d7b469418e6f34e1b1fe0c0d6d2a',40373),
 'agent-bound-build.txt':('e75bf142869458a3b03c3c777c0b4b08753fcc0ba704ba2a4ec92193c874789e',2773)}


def historical_backend_input(root, commit=None):
    """按原构建算法从冻结Git普通文件重算历史输入，不把当前输入说成未变。"""
    commit=commit or PREFIX['measuredCommit']
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
    if commit==PREFIX['measuredCommit']:
        require(len(rows)==414 and result=='53bddbec15779aa28ad25dc3082986027dbc6586f289add3326be2342d3d15ea','S23_PREFIX_BUILD_INPUT')
    return result


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


# 归位窗 05ea 的 PG 原流。冻结三个完整条目（包括命令和检查），并保留原查询字节。
HISTORY_COMMAND = 'e93a6a64de354d7db5da065bd69fa5dd'
HISTORY_STDOUT = '9d82f180101effb003ee384816117116b6913e205b172ae4a31a6e095c5c55aa'
EXTENSION_FILE = Path('artifacts/workflow') / TASK / RUN / 's2-s3-01/diagnostic-activation-extension.json'


def normalized_receipt(value):
    stamp = value['activatedAtUtc']
    require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.]\d{1,7})?(?:Z|[+]00:00)', stamp),
            'S23_PREFIX_RECEIPT_TIME')
    return {**value, 'activatedAtUtc': stamp.removesuffix('+00:00').removesuffix('Z')+'Z'}


def check_activation_chain(binding, state, recorded_b, chain, *, history=None, extension=None):
    """当前 A3 或有证 A5；历史 A1、B2、A3 不得被新激活替换。"""
    old, current = binding['activation'], state['mappingReceipt']
    rows = chain['receipts'] or []
    count = 3 if extension is None else 5
    require(len(rows) == count, 'S23_PREFIX_ACTIVATION_COUNT')
    if extension is not None or 'total' in chain:
        require(chain['total']==count,'S23_PREFIX_TOTAL_ACTIVATIONS')
    if history is not None:
        require(rows[:3] == history and len(history) == 3, 'S23_PREFIX_IMMUTABLE_THREE')
    values = [row['receipt'] for row in rows]
    require(normalized_receipt(values[0]) == normalized_receipt(old)
            and normalized_receipt(values[1]) == normalized_receipt(recorded_b)
            and normalized_receipt(values[-1]) == normalized_receipt(current)
            and chain['current'] == [current['activationId'], current['activationRevision'], current['mappingReleaseId']],
            'S23_PREFIX_ACTIVATION_CHAIN')
    for revision, receipt in enumerate(values, 1):
        require(receipt['mappingId'] == old['mappingId'] and receipt['activationRevision'] == revision,
                'S23_PREFIX_REVISION')
        if revision > 1:
            require(receipt['previousReleaseId'] == values[revision-2]['mappingReleaseId'], 'S23_PREFIX_PREVIOUS')
        if revision % 2 == 0:
            require(receipt['kind'] == 'PUBLISH' and receipt['mappingReleaseId'] != old['mappingReleaseId'],
                    'S23_PREFIX_PUBLISH')
        elif revision > 1:
            require(receipt['kind'] == 'ROLLBACK' and receipt['mappingReleaseId'] == old['mappingReleaseId']
                    and receipt['manifestHash'] == old['manifestHash'], 'S23_PREFIX_ROLLBACK')
    require(all(len({r[key] for r in values}) == count and all(r[key] for r in values)
                for key in ('activationId', 'proposalId'))
            and all(len({row[key] for row in rows}) == count and all(row[key] for row in rows)
                    for key in ('command', 'check'))
            and all((row['connection'], row['catalog'], row['fingerprint']) ==
                    (binding['connectionId'], binding['catalogSnapshotId'], state['catalogFingerprint'])
                    for row in rows), 'S23_PREFIX_CHAIN_BINDING')
    if extension is not None:
        require(history and all(normalized_receipt(row['receipt']) == normalized_receipt(e['receipt'])
                and row['command'] == e['command'] for row,e in zip(rows[3:],extension,strict=True)),
                'S23_PREFIX_DIAGNOSTIC_RECEIPTS')


START_FILE=EXTENSION_FILE.with_name('diagnostic-aba-start.json')
OUTCOME_FILE=EXTENSION_FILE.with_name('diagnostic-aba-outcome.json')


def diagnostic_parent_key(start_bytes):
    return ex.sha(ex.encoded([TASK,RUN,'s23-diagnostic-aba',ex.sha(start_bytes)]))


def diagnostic_bound_inputs(root, archive=None):
    """逐项重算 API、Agent 与实际宿主检查的输入；归档使用在开窗时冻结的准确公共原件。"""
    from workflow_oracle_mapping_evidence import Originals, build_binding, host_observation, stable_host
    import workflow_m4_query_runtime as snapshots
    raw=_read(root,START_FILE,archive); start=json.loads(raw); sources=start['sources']
    require((start['taskId'],start['runId'],start['batch'])==(TASK,RUN,'s2-s3-01')
            and re.fullmatch('[a-f0-9]{32}',start['executionId']) and re.fullmatch('[a-f0-9]{32}',start['windowId'])
            and re.fullmatch('[a-f0-9]{40}',start['measuredCommit']), 'S23_DIAGNOSTIC_START')
    files={'formal-api-inputs.json','formal-resources.json','formal-api-compose.json',
           *[t+s for t in ('api','agent') for s in ('-build-binding.json','-bound-build.txt')]}
    require(set(sources)==files,'S23_DIAGNOSTIC_BOUND_SOURCES')
    class Frozen(Originals):
        def __init__(self):
            self.root=root
            self.frozenPrefixBuild={'inputKey':historical_backend_input(root,start['measuredCommit'])}
        def raw(self,name):
            if name in sources:
                fingerprint=sources[name]
                require(re.fullmatch('[0-9a-f]{64}',fingerprint),'S23_DIAGNOSTIC_SOURCE_HASH')
                contents=_read(root,START_FILE.parent/('diagnostic-source-'+fingerprint+Path(name).suffix),archive)
                require(ex.sha(contents)==fingerprint,'S23_DIAGNOSTIC_SOURCE_CHANGED')
                return contents
            if name in ('api-snapshot.json','agent-snapshot.json'):
                inputs=self.read('formal-api-inputs.json');sid=inputs['snapshotId' if name=='api-snapshot.json' else 'sessionSnapshotId']
                require(re.fullmatch('[a-f0-9]{64}',sid),'S23_DIAGNOSTIC_SNAPSHOT_ID')
                return _read(root,START_FILE.parent.parent/'runtime-snapshots'/(sid+'.json'),archive)
            match=re.fullmatch(r'([a-f0-9]{32})-(receipt[.]json|std(?:out|err)[.]txt)',name)
            require(match,'S23_DIAGNOSTIC_HOST_MEMBER')
            from workflow_oracle_mapping_access_refresh import build_command_run
            return _read(root,START_FILE.parent.parent.parent/'commands'/build_command_run(match[1],RUN)/match[1]/match[2],archive)
    from workflow_oracle_mapping_access_refresh import BUILD_ORIGINS, snapshot_builds
    if start['host']['snapshotId'] in {s for _,_,s in BUILD_ORIGINS.values()}:
        snapshot_builds(root,start['host'],archive)
    frozen=Frozen()
    api=build_binding(frozen,'api',root);agent=build_binding(frozen,'agent',root)
    for target,expected in (('api',api),('agent',agent)):
        snap=frozen.read(target+'-snapshot.json')
        require(snap['inputs']==expected,'S23_DIAGNOSTIC_SNAPSHOT_INPUT')
        # 快照内容键、只读目录和每个文件持续有效，登记的索引同时冻结实际成员长度和散列。
        for relative,digest in snapshots.verify(root,snap,task=TASK,run_id=RUN).items():
            if archive is not None:
                alias='diagnostic-snapshot-'+ex.sha(relative.encode())
                archive.paths[alias]=relative;archive.examined[alias]=digest
        build=frozen.read(target+'-build-binding.json')
        from workflow_m2_build import TARGETS
        prefix=str(Path(TARGETS[target]).parent/'bin/Debug/net10.0')+'/'
        require(snap['files']=={n.removeprefix(prefix):v for n,v in build['outputs'].items() if n.startswith(prefix)},
                'S23_DIAGNOSTIC_SNAPSHOT_FILES')
    require(agent==start['agent'] and api==start['api'],'S23_DIAGNOSTIC_BUILD_KEYS')
    host_observation(frozen,start['host'],api,root,session_directory=root/frozen.read('agent-snapshot.json')['directory'])
    return start,raw,frozen,api,agent


def diagnostic_command(root, cid, argv, stage, key, parent, archive):
    from workflow_oracle_mapping_evidence import Originals
    require(re.fullmatch('[a-f0-9]{32}', cid), 'S23_DIAGNOSTIC_COMMAND_ID')
    directory = Path('artifacts/workflow')/TASK/'commands'/RUN/cid

    class Streams(Originals):
        def __init__(self):
            self.root = root

        def raw(self, name):
            require(name in [cid+'-'+s for s in ('receipt.json','stdout.txt','stderr.txt')], 'S23_DIAGNOSTIC_STREAM')
            return _read(root, directory/name.removeprefix(cid+'-'), archive)

    row, out, err = Streams().command(cid, argv, stage, key, parent, root, command_run=RUN)
    require(all(row[name]['path'] == str(root/directory/(name+'.txt')) for name in ('stdout','stderr'))
            and (row['exitCode'] == 0 and row['classification'] == 'SUCCESS'
                 or row['exitCode'] != 0 and row['classification'] == 'EXIT_FAILURE'), 'S23_DIAGNOSTIC_EXIT')
    return row, out, err


def diagnostic_observation(original, parent, child, clocks, audit, associate):
    """父、子、宿主、实测输入、双流和 Q 已经重开。分别报告可得事实，不给缺证项资格。"""
    missing={}
    def measured(name,operation):
        try:
            return operation()
        except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
            # 仅输出固定字段及异常类别，不输出异常字符串或原始日志内容。
            missing[name]=dict(status='NOT_QUALIFIED',reason='S23_DIAGNOSTIC_'+name.upper(),errorType=type(error).__name__)
            return None
    def captured():
        receipt=original['capturedA']
        require(receipt['activationId']=='activation-d2dcec9ef54c4f3bb96d60cab449580b'
                and str(receipt['activationRevision'])=='3','S23_DIAGNOSTIC_A3')
        return dict(status='OBSERVED_A3',activationId=receipt['activationId'],activationRevision=3)

    a3=measured('capturedA',captured)
    clock_read=measured('clock',clocks)
    audit_read=measured('audit',audit)
    source=None
    if clock_read is not None and audit_read is not None:
        source=measured('sourceAssociation',lambda:associate(original,audit_read,clock_read))
    facts={k:original[k] for k in ('executionStatus','postStateStatus','postStateMissing','postErrorCode','postFence',
           'postLeaseOwnerHash','postLeaseUntilUtc','failedQueryAudits','successfulQueryAudits','queryAudits','committedReadReceipts',
           'resultHash','resultSize','ciphertextBytes') if k in original}
    return dict(queryId=original['queryId'],childCommandId=child['commandId'],parentCommandId=parent['commandId'],
                parentExit=parent['exitCode'],childExit=child['exitCode'],reportedStatus=original.get('status'),
                capturedA=a3 or missing['capturedA'],
                clockStatus='REOPENED' if clock_read is not None else 'NOT_QUALIFIED',
                auditStatus='REOPENED' if audit_read is not None else 'NOT_QUALIFIED',
                sourceAssociation={'status':source or 'NOT_QUALIFIED'},missing=missing,
                elapsedMs=original.get('elapsedMs'),admittedAtUtc=original.get('admittedAtUtc'),
                deadlineAtUtc=original.get('deadlineAtUtc'),phases=original.get('diagnosticPhases'),
                dropped=original.get('diagnosticPhasesDropped'),postState=facts)


def diagnostic_originals(root, record, archive, *, restore_target=False, observation_only=False):
    """按明确父、子、实测宿主、冻结快照、Q 及可选独立归位回执重开；失败状态原样保存。"""
    from workflow_oracle_mapping_evidence import DRIVER, NODE, stable_host, host_observation, utc
    from workflow_oracle_mapping_platform import HOST_FORMAT
    from workflow_oracle_mapping_s2 import runtime_invocation
    from workflow_oracle_mapping_continuity import PG
    require(set(record) == {'taskId','runId','batch','parentId','childId','queryId','measuredCommit','recovery'}
            and (record['taskId'],record['runId'],record['batch']) == (TASK,RUN,'s2-s3-01')
            and re.fullmatch('[a-f0-9]{32}',record['parentId']) and re.fullmatch('[a-f0-9]{32}',record['childId'])
            and re.fullmatch('query-[a-f0-9]{32}',record['queryId'])
            and re.fullmatch('[a-f0-9]{40}',record['measuredCommit'])
            and subprocess.run(['git','merge-base','--is-ancestor',record['measuredCommit'],'HEAD'],cwd=root).returncode==0,
            'S23_DIAGNOSTIC_SCOPE')
    parent,child,q = record['parentId'],record['childId'],record['queryId']
    base = EXTENSION_FILE.parent
    summary = json.loads(_read(root,base/('runtime-aba-'+child+'.json'),archive))
    require((summary['taskId'],summary['runId'],summary['case'],summary['commandId']) == (TASK,RUN,'aba',child),
            'S23_DIAGNOSTIC_CHILD')
    host, agent = summary['host'], summary['input']
    stable_host(host)
    require(set(agent)=={'inputKey','outputKey','receiptSha256'} and all(re.fullmatch('[0-9a-f]{64}',v) for v in agent.values())
            and host['services']['platform-pg']['containerId']==PG and
            host['oracle']['containerId']=='65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1',
            'S23_DIAGNOSTIC_HOST')
    start,start_raw,frozen,api,agent_binding=diagnostic_bound_inputs(root,archive)
    require(start['measuredCommit']==record['measuredCommit'] and agent==agent_binding
            and stable_host(start['host'])==stable_host(host),'S23_DIAGNOSTIC_START_BINDING')
    parent_args = [NODE,DRIVER,'--task',TASK,'--run-id',RUN,'--mode','s2-oracle-aba','--diagnostic-id',start['executionId']]
    parent_row,parent_out,_ = diagnostic_command(root,parent,parent_args,'s23-diagnostic-aba',
            diagnostic_parent_key(start_raw),start['host']['commandId'],archive)
    child_row,child_out,_ = diagnostic_command(root,child,runtime_invocation(host['services']['api-secondary']['containerId'],
            summary['nonce'],'aba'),'query-real-aba-inflight-runtime',ex.sha(ex.encoded(agent)),host['commandId'],archive)
    host_row=host_observation(frozen,host,api,root,session_directory=root/frozen.read('agent-snapshot.json')['directory'])
    require(host['commandId']!=start['host']['commandId'] and parent_row['deadlineSeconds']==900
            and child_row['deadlineSeconds']==25 and child_row['exitCode']==summary['exitCode']
            and utc(parent_row['startedAtUtc'])<=utc(host_row['startedAtUtc'])<=utc(host_row['endedAtUtc'])
            <=utc(child_row['startedAtUtc'])<=utc(child_row['endedAtUtc'])<=utc(parent_row['endedAtUtc'])
            and [json.loads(line) for line in parent_out.splitlines() if line.startswith(b'{"diagnosticAba":')]
                == [dict(diagnosticAba=dict(childCommandId=child,queryId=q))], 'S23_DIAGNOSTIC_PARENT_CHILD')
    parent_reports=[json.loads(line) for line in parent_out.splitlines() if line.startswith(b'{"diagnosticStages":')]
    require(len(parent_reports)==1,'S23_DIAGNOSTIC_PARENT_STAGES')
    stages=parent_reports[0]['diagnosticStages']
    require([stage['mode'] for stage in stages]==['s0-oracle-auth','s2-oracle-aba'] and stages[0]['status']=='PASS',
            'S23_DIAGNOSTIC_FOUR_ROLES')
    from workflow_oracle_mapping_identity_recovery import ROSTER
    observed_outcome=json.loads(_read(root,OUTCOME_FILE,archive))
    require(observed_outcome['exitCode']==parent_row['exitCode'] and (parent_row['exitCode']!=0 or
            child_row['exitCode']==0 and stages[-1]['status']=='PASS'), 'S23_DIAGNOSTIC_PARENT_OUTCOME')
    for idx,stage in enumerate(stages):
        name=Path(stage['report']).name
        require(re.fullmatch('browser-'+stage['mode']+'-[0-9]{13}[.]json',name) and
                stage['report']==str(root/base.parent/name),'S23_DIAGNOSTIC_STAGE_FILE')
        report_raw=_read(root,base.parent/name,archive);report=json.loads(report_raw)
        require(ex.sha(report_raw)==stage['reportSha256'] and report['batch']['executionId']==start['executionId']
                and report['batch']['index']==idx and (report['taskId'],report['runId'],report['mode'],report['status'])
                ==(TASK,RUN,stage['mode'],stage['status']) and report['inputsUnchanged'] is True
                and stable_host(report['inputBinding']['api'])==stable_host(host)
                and utc(parent_row['startedAtUtc'])<=utc(report['startedAtUtc'])<=utc(report['finishedAtUtc'])<=utc(parent_row['endedAtUtc']),
                'S23_DIAGNOSTIC_STAGE_ORIGINAL')
        from workflow_oracle_mapping_evidence import auth_projections, ticket_case
        present=[host_observation(frozen,report[k]['api'],api,root,session_directory=root/frozen.read('agent-snapshot.json')['directory'])
                 for k in ('inputBinding','outputBinding')]
        if idx==0:
            subjects=auth_projections(report)
            require(report['scope']=='ORACLE_FOUR_CURRENT_SESSIONS','S23_DIAGNOSTIC_AUTH_SCOPE')
            ticket_case(frozen,report,report['session'],subjects,start['host'],api,agent,root,*present)
        else:
            require(utc(report['startedAtUtc'])<=utc(child_row['startedAtUtc'])<=utc(child_row['endedAtUtc'])<=utc(report['finishedAtUtc']),
                    'S23_DIAGNOSTIC_CHILD_IN_ABA')
            subjects=[v[1] for v in ROSTER.values()]
            ticket_case(frozen,report,report['sessionBefore'],subjects,start['host'],api,agent,root,*present)
    originals=[json.loads(line) for line in child_out.splitlines() if line.startswith(b'{"taskId":')]
    require(len(originals)==1, 'S23_DIAGNOSTIC_ONE_Q')
    original=originals[0]
    require((original['taskId'],original['resourceRun'],original['case'],original['queryId'])==
            (TASK,RUN,'AC-05_INFLIGHT_ABA',q), 'S23_DIAGNOSTIC_Q')
    from workflow_oracle_mapping_evidence import audit_observation
    from workflow_oracle_mapping_s2_contract import reopen_source_clocks, source_associations
    def clocks():
        return reopen_source_clocks(frozen,summary,child_row,root)
    def audit():
        inflight,=[w for w in report['oracleWindows'] if w['name']=='inflight-activation-aba']
        source=inflight['audit']
        require(source['clientId'] is None,'S23_DIAGNOSTIC_UNFILTERED_SOURCE')
        audit_observation(frozen,source,dict(startedAtUtc=inflight['startedAtUtc'],endedAtUtc=inflight['finishedAtUtc']),
                          host,root,record['measuredCommit'])
        return source
    if observation_only:
        return diagnostic_observation(original,parent_row,child_row,clocks,audit,source_associations)
    require(original['status']==('PASS' if child_row['exitCode']==0 else 'FAIL')
            and original['capturedA']['activationId']=='activation-d2dcec9ef54c4f3bb96d60cab449580b'
            and str(original['capturedA']['activationRevision'])=='3', 'S23_DIAGNOSTIC_A3')
    clocks()
    audit()
    def command_from_phase(name):
        phases=[p for p in original['diagnosticPhases'] if p['phase']==name and p['edge']=='ENTER']
        require(len(phases)==1 and phases[0]['commandId'], 'S23_DIAGNOSTIC_ACTIVATION_COMMAND')
        return phases[0]['commandId']
    b=dict(receipt=original['activatedB'],command=command_from_phase('B_ACTIVATE'))
    if restore_target:
        require(original.get('activatedA') is not None or (child_row['exitCode']!=0 and original.get('abaCompleted') is False),
                'S23_DIAGNOSTIC_RESTORE_NOT_REQUIRED')
        history_raw=_read(root,base.parent.parent/'commands'/RUN/HISTORY_COMMAND/'stdout.txt',archive)
        require(ex.sha(history_raw)==HISTORY_STDOUT,'S23_PREFIX_HISTORY_ORIGINAL')
        return dict(sourceCommand=child,queryId=q,stdoutHash=ex.sha(child_out),history=json.loads(history_raw)['receipts'],
                    activatedB=b['receipt'],activatedA=original.get('activatedA'),parentId=parent,startSha256=ex.sha(start_raw))
    if record['recovery'] is None:
        a=dict(receipt=original['activatedA'],command=command_from_phase('A_ACTIVATE'))
    else:
        require(child_row['exitCode']!=0 and original.get('activatedA') is None,'S23_DIAGNOSTIC_RESTORE_ORIGIN')
        ref=record['recovery']
        require(set(ref)=={'operation','commandId','reportSha256'} and
                all(re.fullmatch('[a-f0-9]{32}',ref[k]) for k in ('operation','commandId')),'S23_DIAGNOSTIC_RESTORE_ID')
        path=base/('mapping-recovery-'+ref['operation']+'.json')
        raw=_read(root,path,archive); restored=json.loads(raw)
        require(ex.sha(raw)==ref['reportSha256'] and (restored['taskId'],restored['runId'],restored['batch'],
                restored['sourceCommand'],restored['queryId'],restored['executionId'],restored['status'],restored['stdoutHash'])
                ==(TASK,RUN,'s2-s3-01',child,q,ref['operation'],'PASS',ex.sha(child_out)), 'S23_DIAGNOSTIC_RESTORE_REPORT')
        from workflow_oracle_mapping_identity_recovery import ROSTER
        receipt,approved=restored['currentReceipt'],restored['approved']
        require(approved['status']=='APPROVED' and approved['proposalId']==receipt['proposalId'] and approved['kind']=='ROLLBACK'
                and approved['submittedBy']==ROSTER['operator'][1] and approved['decision']['decision']=='APPROVE'
                and approved['decision']['decidedBy']==ROSTER['auditor'][1]
                and all(restored['currentActive'][k]==receipt[k] for k in ('mappingId','mappingReleaseId','manifestHash','activationRevision'))
                and restored['currentActive']['usable'] is True,'S23_DIAGNOSTIC_RESTORE_APPROVAL')
        phase,=[p for p in restored['phases'] if p['method']=='POST' and p['path']=='/api/v1/mapping-proposals/'+receipt['proposalId']+'/activate']
        require(phase['status']==200 and phase['subjectId']==ROSTER['activator'][1] and utc(parent_row['endedAtUtc'])
                <=utc(phase['startedAtUtc'])<=utc(phase['finishedAtUtc'])<=utc(restored['finishedAtUtc']), 'S23_DIAGNOSTIC_RESTORE_ACTIVATE')
        window_id=restored['windowId']
        require(re.fullmatch('[a-f0-9]{32}',window_id),'S23_DIAGNOSTIC_RESTORE_WINDOW')
        argv=[NODE,'scripts/maintenance/workflow-oracle-mapping-restore.mjs',window_id,ref['operation'],'--diagnostic']
        restore_key=ex.sha(ex.encoded([ex.sha(start_raw),parent,child,q,window_id,ref['operation']]))
        check,out,_=diagnostic_command(root,ref['commandId'],argv,'normal-mapping-rollback',restore_key,None,archive)
        result=json.loads(out)
        require(check['deadlineSeconds']==800 and check['exitCode']==0 and
                utc(check['startedAtUtc'])<=utc(phase['startedAtUtc'])<=utc(restored['finishedAtUtc'])<=utc(check['endedAtUtc'])
                and result['status']=='PASS' and result['report']==str(root/path),'S23_DIAGNOSTIC_RESTORE_COMMAND')
        from workflow_oracle_mapping_continuity import command as reopen_pg
        sql=extension_sql(receipt['mappingId'])
        sql_key=ex.sha(b'BEGIN READ ONLY;\n'+sql+b'\nCOMMIT;')
        pg_argv=['docker','--context','desktop-linux','exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
        readings=[]
        for label in ('chainBeforeCommand','chainAfterCommand'):
            cmd,raw,err=reopen_pg(root,restored[label],RUN,pg_argv,'omq-pg-s23-recovery-activation',sql_key,15,archive)
            require(not err and utc(check['startedAtUtc'])<=utc(cmd['startedAtUtc'])<=utc(cmd['endedAtUtc'])
                    <=utc(check['endedAtUtc']), 'S23_DIAGNOSTIC_RESTORE_PG_WINDOW')
            readings.append(json.loads(raw))
        before,after=readings
        require(before['total']==len(before['receipts'])==4 and after['total']==len(after['receipts'])==5 and before['receipts']==after['receipts'][:4]
                and all(r['current']==[r['receipts'][-1]['receipt'][k] for k in ('activationId','activationRevision','mappingReleaseId')] for r in readings)
                and normalized_receipt(before['receipts'][-1]['receipt'])==normalized_receipt(b['receipt'])
                and normalized_receipt(after['receipts'][-1]['receipt'])==normalized_receipt(receipt),'S23_DIAGNOSTIC_RESTORE_PG')
        a=dict(receipt=receipt,command=phase['commandId'])
    return [b,a]


def register_diagnostic_activation(root,parent_id,child_id,query_id,measured_commit,recovery=None):
    from workflow_oracle_mapping_platform import save
    record=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',parentId=parent_id,childId=child_id,queryId=query_id,
                measuredCommit=measured_commit,recovery=recovery)
    index=DiagnosticIndex()
    observed=json.loads(_read(root,OUTCOME_FILE,index))
    require(all(observed[k]==record[k] for k in record if k!='recovery'),'S23_DIAGNOSTIC_SELECTED_OUTCOME')
    diagnostic_originals(root,record,index)
    original=dict(registration=record,members=index.members(root))
    save(root/EXTENSION_FILE,original)
    return ex.sha(_read(root,EXTENSION_FILE))


class DiagnosticIndex:
    """按准确定址记录逐件消费过的原件、摘要与长度；重新打开要求全集相同。"""
    def __init__(self):
        self.paths={}
        self.examined={}

    def members(self,root):
        return {path:dict(sha256=self.examined[key],sizeBytes=ex.ordinary(root/path).stat().st_size)
                for key,path in self.paths.items()}


def reopen_registered(root,raw_record,archive):
    saved=json.loads(raw_record);index=DiagnosticIndex()
    observed=json.loads(_read(root,OUTCOME_FILE,index))
    require(all(observed[k]==saved['registration'][k] for k in saved['registration'] if k!='recovery'),'S23_DIAGNOSTIC_SELECTED_OUTCOME')
    extension=diagnostic_originals(root,saved['registration'],index)
    require(index.members(root)==saved['members'],'S23_DIAGNOSTIC_FROZEN_MEMBERS')
    if archive is not None:
        for key,path in index.paths.items():
            require(key not in archive.paths or (archive.paths[key],archive.examined[key])==(path,index.examined[key]),'S23_DIAGNOSTIC_ALIAS')
            archive.paths[key]=path;archive.examined[key]=index.examined[key]
    return extension


def extension_sql(mapping_id):
    """五笔链逐行核实异人正式审批、成功检查及命令操作。原三笔查询原件仍用原 SQL 重开。"""
    original=activation_chain_sql(mapping_id)
    return original.replace(b"'current', json_build_array", b''''total', (SELECT count(*) FROM connections."MappingActivations" z WHERE z."MappingId"=v."MappingId"), 'current', json_build_array''').replace(b'AND p."DecidedBy"<>p."SubmittedBy"', b'''AND p."DecidedBy"<>p."SubmittedBy" AND p."Status"='APPROVED'
 AND ck."Status"='PASS' AND ck."BindingHash"=p."BindingHash" AND p."DecisionJson"::json->>'decision'='APPROVE'
 AND m."Operation"='activate:' || p."Id"''')


def historical_chain(root,archive=None):
    cid = '5b90bb8f66fb4ddd9bfeddbe5015133a'
    raw = _read(root, Path('artifacts/workflow')/TASK/'commands'/RUN/cid/'stdout.txt', archive)
    require(ex.sha(raw) == 'd1fba9b095bec4a31831c598e4bbf7bd043579d923e57efd3403a0dab74efc15', 'S23_PREFIX_ABA_STDOUT')
    original, = [json.loads(line) for line in raw.splitlines() if line.startswith(b'{"taskId":')]
    base = Path('artifacts/workflow')/TASK/'commands'/RUN
    history_raw = _read(root,base/HISTORY_COMMAND/'stdout.txt',archive)
    require(ex.sha(history_raw)==HISTORY_STDOUT,'S23_PREFIX_HISTORY_ORIGINAL')
    history = json.loads(history_raw)['receipts']
    return original['activatedB'],history


def prefix_activation(root, host, binding, state, command_id=None, archive=None, *, extension_hash=None):
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    recorded_b,history=historical_chain(root,archive)
    extension = None
    if extension_hash is not None:
        raw_record = _read(root,EXTENSION_FILE,archive)
        require(ex.sha(raw_record)==extension_hash,'S23_DIAGNOSTIC_REGISTRATION_HASH')
        extension = reopen_registered(root,raw_record,archive)
    # 已产生的历史命令沿原查询重开，当前采集始终在相同快照核未过滤总数。
    legacy=(command_id=='34de8c4335f94f97b6eac73f32fbf3e3')
    sql = (activation_chain_sql if legacy else extension_sql)(binding['activation']['mappingId'])
    if command_id is None:
        _, command_id = p.read_pg(sql,'s23-prefix-activation')
    require(re.fullmatch('[a-f0-9]{32}',command_id), 'S23_PREFIX_ACTIVATION_COMMAND')
    pg = host['services']['platform-pg']
    argv = ['docker','--context','desktop-linux','exec','-i','--user','postgres',pg['containerId'],
            'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    rec,out,err = c.command(root,command_id,RUN,argv,'omq-pg-s23-prefix-activation',
                            ex.sha(b'BEGIN READ ONLY;\n'+sql+b'\nCOMMIT;'),15,archive)
    require(not err and utc(pg['startedAt']) < utc(rec['startedAtUtc']), 'S23_PREFIX_ACTIVATION_GENERATION')
    chain=json.loads(out)
    require(legacy or 'total' in chain,'S23_PREFIX_TOTAL_ACTIVATIONS')
    check_activation_chain(binding,state,recorded_b,chain,history=history,extension=extension)
    return command_id




def run_diagnostic_aba():
    """在 Master 的现有受控资源窗消费一次诊断；四角色、180 秒 ABA 槽及其中 25 秒实机子命令分别计时。"""
    import os
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_resume as resume
    from workflow_oracle_runtime_window import policy, monitored
    from workflow_oracle_mapping_evidence import NODE, DRIVER
    window=policy();require(window is not None and not ex.ordinary(p.ROOT/START_FILE).exists(),'S23_DIAGNOSTIC_ALREADY_USED')
    admission=p.admission()
    pre=ex.run(['python3','-B','scripts/maintenance/execution_preflight.py','check','--milestone',TASK,'--phase','runtime'],
               p.ROOT,task=TASK,run_id=RUN,stage='s23-diagnostic-consumers',input_key=ex.sha(Path(__file__).read_bytes()),timeout=18)
    require(pre.returncode==0,'S23_DIAGNOSTIC_PREFLIGHT')
    prefix=prepare_prefix(p.ROOT,PREFIX,RUNTIME_PLAN)
    obs=json.loads(_read(p.ROOT,EXTENSION_FILE.parent/prefix['file']))
    require(obs['state']['mappingReceipt']['activationRevision']==3 and 'diagnosticExtensionSha256' not in obs,'S23_DIAGNOSTIC_EXPECTED_A3')
    require(subprocess.run(['git','diff','--quiet','HEAD','--','backend','scripts/maintenance'],cwd=p.ROOT).returncode==0,'S23_DIAGNOSTIC_DIRTY_INPUT')
    measured=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p.ROOT).decode().strip()
    host=p.runtime_binding(); agent=p.build.validate('agent',TASK);api=p.build.validate('api',TASK)
    require(agent['inputKey']==api['inputKey']==historical_backend_input(p.ROOT,measured),'S23_DIAGNOSTIC_MEASURED_BUILD')
    sources={}
    for name in ('formal-api-inputs.json','formal-resources.json','formal-api-compose.json',
                 'api-build-binding.json','agent-build-binding.json','api-bound-build.txt','agent-bound-build.txt'):
        path=(resume.AREA if name.startswith('formal-') else resume.AREA.parent)/name
        raw=ex.ordinary(path).read_bytes(); fingerprint=ex.sha(raw); sources[name]=fingerprint
        target=ex.ordinary(p.ROOT/START_FILE.parent/('diagnostic-source-'+fingerprint+Path(name).suffix))
        if not target.exists():
            with target.open('xb') as stream: stream.write(raw)
        require(ex.sha(target.read_bytes())==fingerprint,'S23_DIAGNOSTIC_FROZEN_INPUT')
    nonce=uuid.uuid4().hex
    start=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',executionId=nonce,windowId=window['id'],host=host,
               measuredCommit=measured,api=api,agent=agent,sources=sources,prefix=prefix,preflightCommand=pre.receipt['commandId'])
    argv=[NODE,DRIVER,'--task',TASK,'--run-id',RUN,'--mode','s2-oracle-aba','--diagnostic-id',nonce]
    with monitored(admission['attempt']):
        # 持久独占先于父启动；未知退出保留消耗，不派生盲重试。
        with ex.ordinary(p.ROOT/START_FILE).open('x') as stream: json.dump(start,stream)
        _,raw,_,_,_=diagnostic_bound_inputs(p.ROOT)
        result=ex.run(argv,p.ROOT,task=TASK,run_id=RUN,stage='s23-diagnostic-aba',input_key=diagnostic_parent_key(raw),
                      parent_id=host['commandId'],timeout=900,environment={**os.environ,'OMQ_ABA_DIAGNOSTIC':nonce,
                      'OMQ_PROGRESS_FILE':'s2-s3-'+nonce+'.jsonl'})
    markers=[json.loads(line)['diagnosticAba'] for line in result.stdout.splitlines() if line.startswith(b'{"diagnosticAba":')]
    require(len(markers)<=1,'S23_DIAGNOSTIC_AMBIGUOUS_RESULT')
    marker=markers[0] if markers else {}
    outcome=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',parentId=result.receipt['commandId'],measuredCommit=measured,
                 childId=marker.get('childCommandId'),queryId=marker.get('queryId'),exitCode=result.returncode)
    p.save(p.ROOT/OUTCOME_FILE,outcome)
    return outcome


def reopen_diagnostic_aba(root):
    """独立重开唯一父子原件及源审计；即使外层或五秒请求失败，仍返回实测分段与缺失资格。"""
    observed=json.loads(_read(root,OUTCOME_FILE))
    record={k:v for k,v in observed.items() if k!='exitCode'}
    index=DiagnosticIndex()
    facts=diagnostic_originals(root,{**record,'recovery':None},index,observation_only=True)
    return dict(**facts,members=index.members(root))


def diagnostic_recovery_target(root):
    """归位写前，从同一已登记诊断重开失败子命令，仅返回准确 B4 和原三笔。"""
    outcome=json.loads(_read(root,OUTCOME_FILE));record={k:v for k,v in outcome.items() if k!='exitCode'}
    require(type(outcome['exitCode']) is int,'S23_DIAGNOSTIC_RESTORE_PARENT_OUTCOME')
    return diagnostic_originals(root,{**record,'recovery':None},None,restore_target=True)


def run_diagnostic_restore():
    from workflow_oracle_mapping_evidence import NODE
    from workflow_oracle_runtime_window import policy, monitored
    import workflow_oracle_mapping_platform as p
    window=policy();require(window is not None,'S23_DIAGNOSTIC_RESTORE_WINDOW')
    target=diagnostic_recovery_target(p.ROOT)
    operation=uuid.uuid4().hex; window_id=window['id']
    args=[NODE,'scripts/maintenance/workflow-oracle-mapping-restore.mjs',window_id,operation,'--diagnostic']
    key=ex.sha(ex.encoded([target['startSha256'],target['parentId'],target['sourceCommand'],target['queryId'],window_id,operation]))
    admission=p.admission()
    with monitored(admission['attempt']):
        result=ex.run(args,p.ROOT,task=TASK,run_id=RUN,stage='normal-mapping-rollback',input_key=key,timeout=800)
    require(result.returncode==0,'S23_DIAGNOSTIC_RESTORE_FAILED_'+result.receipt['commandId'])
    path=EXTENSION_FILE.parent/('mapping-recovery-'+operation+'.json')
    return dict(operation=operation,commandId=result.receipt['commandId'],reportSha256=ex.sha(_read(p.ROOT,path)))


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
        revision=projection['mappingReceipt']['activationRevision']
        require(revision in (3,5),'S23_PREFIX_ACTIVATION_COUNT')
        if revision==5:
            observation['diagnosticExtensionSha256']=ex.sha(_read(root,EXTENSION_FILE))
        observation['activationChainCommand'] = prefix_activation(root,current,old,projection,
            extension_hash=observation.get('diagnosticExtensionSha256'))
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
        prefix_activation(root,obs['host'],query['oracleBinding'],obs['state'],chain,archive,
            extension_hash=obs.get('diagnosticExtensionSha256'))
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
