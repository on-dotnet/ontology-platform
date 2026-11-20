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
PREFIX=dict(commandId='edd1379b83c246329579075d16ccda58',measuredCommit='2a2ea74ff72c22860e4927318913eaece9d14f9f',mode='s2-oracle-relations',
    qualificationCommandId='a495b4d475404f95b726b8b46d6a3663',qualificationSha256='7bb9468c9ed44ae335936a60f3765456b44b125db64cfe05eb1f4e1782172d46',
    memberIndexSha256='91637b9ad1664efc70c8084ec999af10c62bdbca6efb3f885cf13b9366e29b8a')
MODES=('s0-oracle-auth','s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-queries','s2-oracle-relations')
TASK='G4-ORACLE-MAPPING-QUERY-001'
RUN='product-resume-01'


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
        left,right=old.decode(),new.decode()
        if name.endswith('/workflow-oracle-s2.mjs'):
            right=right.replace('!["s2-s3-01","s2-s3-01-access-01"].includes(shared.plan.planId)','shared.plan.planId !== "s2-s3-01"')
            # 未执行的权限测试函数是唯一产品场景差异；上下两个边界必须各唯一出现。
            begin='/** 当前组合grant拒绝后既不执行业务SQL，也不恢复历史原值；每次恢复核原行。 */'
            end='/** B先由三角色正式准备；真正同query源读后A-B-A交给已有正式DI在途测试。 */'
            require(all(text.count(begin)==text.count(end)==1 for text in (left,right)),'S23_PREFIX_ACCESS_BOUNDARY')
            left=left[:left.index(begin)]+left[left.index(end):];right=right[:right.index(begin)]+right[right.index(end):]
        elif name==e.DRIVER:
            right=right.replace('(input.plan.planId === "s2-s3-01-access-01" ? omq.s2AccessPlan() : omq.s2Plan)','omq.s2Plan')
        elif name.endswith('/workflow-oracle-query-fixture.mjs'):
            right=right.replace('export function s2AccessPlan() { return Object.freeze(JSON.parse(readFileSync(new URL("./workflow-oracle-s2-access-plan.json", import.meta.url), "utf8"))); }\n','')
            right=right.replace('"access_case", "runtime_case", "same_grant"','"access_case", "runtime_case"')
        elif name.endswith('/workflow_oracle_mapping_s2_contract.py'):
            right=right.replace("report['batch']['planId'] in ('s2-s3-01','s2-s3-01-access-01')","report['batch']['planId']=='s2-s3-01'")
            require(_program(left,{'frozen_plan'})==_program(right,{'frozen_plan'}),'S23_PREFIX_CONTRACT_CHANGED')
            continue
        else:require(False,'S23_PREFIX_DRIVER_CHANGED')
        require(left==right,'S23_PREFIX_EXECUTED_PATH_CHANGED')
    return True


def prefix_result(root,archive=None):
    """先核冻结资格及所有引用，再按当前消费者重开五槽；只走上述精确兼容条件。"""
    import workflow_oracle_mapping_evidence as e
    frozen=_frozen_qualification(root,archive)
    for name,item in frozen['members'].items():
        raw=_read(root,item['path'],archive,'prefix-'+name)
        require(len(raw)==item['sizeBytes'] and ex.sha(raw)==item['sha256'],'S23_PREFIX_ORIGINAL_CHANGED')
    checked={};members={};result=None
    for mode in MODES:
        result=e.reopen_runtime_case(root,TASK,RUN,PREFIX['commandId'],expected_mode=mode,_checked=checked)
        for name,item in result['members'].items():
            if name in members:require(members[name]==item,'S23_PREFIX_ORIGINAL_ALIAS')
            members[name]=item
            _read(root,item['path'],archive,'prefix-'+name)
    return {**result,'members':members},frozen


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
    return query,mapping,stable_host(source['host'])


def prepare_prefix(root,descriptor):
    """父命令启动前冻结当前基线及原query身份；不读取或移植任何旧会话材料。"""
    import workflow_oracle_mapping_platform as p
    import workflow_oracle_mapping_s2 as s
    from workflow_oracle_mapping_evidence import stable_host
    require(descriptor==PREFIX,'S23_PREFIX_DESCRIPTOR');qualified,_=prefix_result(root)
    query,mapping,host=_context(qualified,root);state=json.loads((p.AREA.parent/RUN/'oracle-two-table.json').read_bytes())
    projection=_state_projection(state);old=query['oracleBinding'];latest=projection['latestQuery']
    require(projection['connectionId']==old['connectionId'] and projection['catalogSnapshotId']==old['catalogSnapshotId']
            and projection['mappingReceipt']==old['activation'] and latest['reportName'] in qualified['members'] and json.loads(_read(root,qualified['members'][latest['reportName']]['path']))==query
            and latest['queryId']==query['oracleCases'][2]['queryId'] and latest['resultHash']==query['oracleCases'][2]['sha256'],'S23_PREFIX_CURRENT_BINDING')
    current=p.runtime_binding();require(stable_host(current)==host,'S23_PREFIX_CURRENT_HOST')
    snapshot=s.source_snapshot();require(snapshot['rows']==query['independentSource']['rows'] and snapshot['hashes']==query['independentSource']['hashes'],'S23_PREFIX_CURRENT_SOURCE')
    observation=dict(taskId=TASK,runId=RUN,batch='s2-s3-01',planId=PLAN_ID,qualifiedPrefix=PREFIX,state=projection,host=current,source=snapshot)
    name='prefix-observation-'+uuid.uuid4().hex+'.json';path=p.AREA.parent/RUN/'s2-s3-01'/name;p.save(path,observation)
    return dict(file=name,sha256=ex.sha(path.read_bytes()))


def reopen_prefix(root,stage,archive):
    """新父窗口只消费自己的阶段；历史前缀作为另一个父命令的完整资格引用。"""
    import workflow_oracle_mapping_s2 as s
    from workflow_oracle_mapping_evidence import stable_host,host_observation,build_binding,utc
    require(stage['plan']['planId']==PLAN_ID and stage['plan']['qualifiedPrefix']==PREFIX,'S23_PREFIX_PLAN')
    qualified,_=prefix_result(root,archive);query,mapping,host=_context(qualified,root)
    ref=stage['qualifiedPrefix'];require(re.fullmatch('prefix-observation-[a-f0-9]{32}[.]json',ref['file']),'S23_PREFIX_OBSERVATION_NAME')
    path=Path('artifacts/workflow')/TASK/RUN/'s2-s3-01'/ref['file'];raw=_read(root,path,archive)
    require(ex.sha(raw)==ref['sha256'],'S23_PREFIX_OBSERVATION_HASH');obs=json.loads(raw)
    require((obs['taskId'],obs['runId'],obs['batch'],obs['planId'])==(TASK,RUN,'s2-s3-01',PLAN_ID) and obs['qualifiedPrefix']==PREFIX
            and stable_host(obs['host'])==host==stable_host(archive.dispatch['host']),'S23_PREFIX_OBSERVATION_SCOPE')
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
    for cid in [obs['host']['commandId'],*snapshot['commandIds']]:
        sample=archive.read(cid+'-receipt.json')
        require(utc(previous['endedAtUtc'])<=utc(sample['startedAtUtc'])<=utc(sample['endedAtUtc'])<=utc(parent['startedAtUtc']),'S23_PREFIX_OBSERVATION_ORDER')
    binding=query['oracleBinding'];state=obs['state'];latest=state['latestQuery']
    require(state['connectionId']==binding['connectionId'] and state['catalogSnapshotId']==binding['catalogSnapshotId'] and state['mappingReceipt']==binding['activation']
        and latest['queryId']==query['oracleCases'][2]['queryId'] and latest['resultHash']==query['oracleCases'][2]['sha256']
        and latest['reportName'] in qualified['members'] and json.loads(_read(root,qualified['members'][latest['reportName']]['path']))==query,'S23_PREFIX_QUERY_BINDING')
    return dict(status='REUSED_QUALIFIED_PREFIX',commandId=PREFIX['commandId'],measuredCommit=PREFIX['measuredCommit'],modes=list(MODES),
        memberIndexSha256=ex.sha(ex.encoded(qualified['members'])),memberCount=len(qualified['members']),newAuthenticationRequired=True,scope='Separate old parent; no historical stages or source events included in current parent window')


def run_access_suffix():
    """固定同批后缀的实际入口；原平台与审计依赖保持完整原字节，不替换或猴补其函数。"""
    import os
    import workflow_oracle_mapping_platform as p
    from workflow_oracle_mapping_evidence import browser_invocation,batch_plan
    require(p.product_run()==RUN,'S23_SUFFIX_RUN')
    root=p.ROOT;area=p.AREA.parent/RUN;mode='s2-s3-oracle';case='healthy'
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
    execution=uuid.uuid4().hex;stage['plan']=batch_plan(root,mode,PLAN_ID);stage['executionId']=execution
    stage['batchInput']='s2-s3-'+execution+'.json';stage['qualifiedPrefix']=prepare_prefix(root,stage['plan']['qualifiedPrefix'])
    p.save(area/stage['batchInput'],dict(executionId=execution,plan=stage['plan'],qualifiedPrefix=stage['qualifiedPrefix']))
    host=p.runtime_binding();api=p.build.validate('api',TASK);tests=p.build.validate('agent',TASK)
    argv,key,label=browser_invocation(root,mode,case,host,api,tests,stage)
    pattern='browser-'+mode+'-'+'[0-9]'*13+'.json';before=set(area.glob(pattern))
    environment={**os.environ,'OMQ_PROGRESS_FILE':'s2-s3-'+execution+'.jsonl'}
    result=ex.run(argv,root,task=TASK,run_id=RUN,stage=label,input_key=key,parent_id=host['commandId'],timeout=stage['plan']['deadlineSeconds'],environment=environment)
    after=set(area.glob(pattern))-before
    entry=dict(taskId=TASK,runId=RUN,mode=mode,case=case,stageInputs=stage,host=host,builds={'api':api,'agent':tests},
        commandId=result.receipt['commandId'],exitCode=result.returncode,resourceAttempt=resource['attempt'],preflightCommandId=pre.receipt['commandId'],
        reports=[path.name for path in sorted(after)],testedCommit=p.local('tested-head',['git','rev-parse','HEAD']))
    p.save(area/('formal-run-'+mode+'-'+result.receipt['commandId']+'.json'),entry)
    try:
        p.save(area/('formal-audit-'+result.receipt['commandId']+'.json'),p.audit_window(result.receipt['startedAtUtc'],result.receipt['endedAtUtc']))
        require(len(after)==1,'BATCH_REPORT_COUNT');batch=json.loads(next(iter(after)).read_bytes())
        for item in batch['stages']:
            require(re.fullmatch(r'browser-[a-z0-9-]+-[0-9]{13}[.]json',Path(item['report']).name),'BATCH_STAGE_NAME')
            p.save(area/('formal-audit-'+result.receipt['commandId']+'-'+item['mode']+'.json'),p.audit_window(item['startedAtUtc'],item['finishedAtUtc']))
    except Exception as error:
        p.save(area/('formal-audit-failure-'+result.receipt['commandId']+'.json'),dict(taskId=TASK,reason=str(error)))
        raise
    return dict(mode=mode,commandId=result.receipt['commandId'],exitCode=result.returncode,reports=entry['reports'],stageFailure=[json.loads(path.read_bytes()).get('failure') for path in after])
