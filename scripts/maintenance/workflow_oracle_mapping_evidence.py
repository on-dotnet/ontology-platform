"""G4 Oracle 当前执行原件的资格分发；预检、构建、命令和无损恢复走既有消费者。"""
import argparse
import ast
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

from workflow_evidence import restore
from workflow_execution import encoded, ordinary, sha
from workflow_m2_evidence import require, mtp
from workflow_oracle_mapping_resources import TASK, RUN as RESOURCE_RUN

PRODUCT_RUN = 'product-resume-01'
RUN = os.environ.get('OMQ_PRODUCT_RUN',RESOURCE_RUN)
require('OMQ_PRODUCT_RUN' not in os.environ or RUN==PRODUCT_RUN,'OMQ_PRODUCT_RUN_SCOPE')

ROOT = Path(__file__).resolve().parents[2]
DRIVER = 'scripts/maintenance/workflow-m4-query.mjs'
PLATFORM = 'scripts/maintenance/workflow_oracle_mapping_platform.py'
NODE = '/opt/homebrew/Cellar/node@24/24.22.1/bin/node'
DRIVERS = (DRIVER, 'scripts/maintenance/workflow-oracle-query-fixture.mjs', PLATFORM,
           'scripts/maintenance/workflow_execution.py',
           'scripts/maintenance/workflow_m2_build.py', 'infra/oracle/config/mapping-observer.sql')
GATES = {'environment', 'contract', 'backend', 'web', 'interaction'}
READY = 's0-oracle-ready'
NATURAL_CANCEL = 's0-oracle-natural-cancel'
ERRORS = {'healthy': None, 'expired': 'OMQ_READY_GRANT_EXPIRED', 'short': 'OMQ_READY_GRANT_TTL_SHORT',
          'catalog': 'OMQ_READY_CATALOG_STALE', 'activation': 'OMQ_READY_ACTIVATION_STALE'}
BROWSER = {'provision', 'mapping', READY, 's0-oracle-natural', 's0-oracle-cancel', NATURAL_CANCEL, 's1', 's1-reopen', 's3', 'ui-s1', 'ui-s3'}
if RUN==PRODUCT_RUN:
    BROWSER.update(('s0-oracle-auth','auth-handoff-s1','reader-auth','s2-s3-oracle','s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-queries','s2-oracle-relations','s2-oracle-access','s2-oracle-aba','s2-oracle-connection','s2-oracle-versions','s2-oracle-states','s2-oracle-reopen'))
HEX = re.compile(r'[0-9a-f]{64}')
COMMAND = re.compile(r'[0-9a-f]{32}')
PUBLIC = Path('docs/evidence') / TASK / RUN


def digest_value(value):
    return sha(encoded(value))


def utc(text):
    value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    require(value.tzinfo is not None, 'OMQ_TIME_ZONE')
    return value.astimezone(dt.timezone.utc)


def summary(argv):
    return dict(executable=Path(argv[0]).name, argumentCount=len(argv)-1, sha256=digest_value(argv))


def batch_plan(root, mode="auth-handoff-s1", plan_id=None):
    if mode=="s2-s3-oracle":
        from workflow_oracle_mapping_s2_contract import frozen_plan
        return frozen_plan(root,plan_id or "s2-s3-01")
    require(mode=="auth-handoff-s1", "OMQ_BATCH_MODE")
    plan=json.loads(ordinary(root/'scripts/maintenance/workflow-oracle-auth-plan.json').read_bytes())
    expected=[('s0-oracle-auth','authentication',600),(NATURAL_CANCEL,'product',180),('mapping','product',180),
              ('s1','product',180),('reader-auth','authentication',180),('s1-reopen','product',180)]
    require(plan==dict(schemaVersion=1,planId='auth-handoff-01',mode='auth-handoff-s1',preSeconds=60,postSeconds=60,
                      submissionSeconds=40,requiredSessionSeconds=210,stages=[dict(mode=m,kind=k,seconds=s) for m,k,s in expected],
                      deadlineSeconds=60+600+4*180+180+60),'OMQ_BATCH_PLAN')
    return plan


def drivers(root, mode, run=None, plan_id=None):
    run = RUN if run is None else run
    names = DRIVERS
    if run==PRODUCT_RUN:
        names += ('scripts/maintenance/workflow_oracle_archive_requalification.py',
                  'scripts/maintenance/workflow_oracle_mapping_resume.py',
                  'scripts/maintenance/workflow_oracle_mapping_platform_recovery.py','scripts/maintenance/workflow_m4_query_runtime.py')
    if mode in ('s0-oracle-natural', 's0-oracle-cancel', NATURAL_CANCEL, 'auth-handoff-s1'):
        names += ('scripts/maintenance/workflow_oracle_mapping_formal_observer.py',)
    if mode=='auth-handoff-s1':
        names += ('scripts/maintenance/workflow-oracle-auth-plan.json',)
    if mode=='s2-s3-oracle' or mode.startswith('s2-oracle-') or mode in ('s3','ui-s1','ui-s3'):
        names += ('scripts/maintenance/workflow-oracle-s2-plan.json','scripts/maintenance/workflow-oracle-s2.mjs',
                  'scripts/maintenance/workflow_oracle_mapping_s2.py','scripts/maintenance/workflow_oracle_mapping_s2_contract.py',
                  'scripts/maintenance/workflow_oracle_mapping_formal_observer.py','scripts/maintenance/workflow_m4_query_evidence.py')
    if plan_id in ('s2-s3-01-access-01','s2-s3-01-runtime-01'):
        names+=('scripts/maintenance/workflow-oracle-s2-access-plan.json','scripts/maintenance/workflow_oracle_mapping_continuation.py','scripts/maintenance/workflow_oracle_mapping_continuity.py','scripts/maintenance/workflow_oracle_mapping_repeat.py','scripts/maintenance/workflow_oracle_mapping_access_refresh.py','scripts/maintenance/workflow_oracle_mapping_capacity.py','scripts/maintenance/workflow_oracle_mapping_readiness.py','scripts/maintenance/workflow_oracle_mapping_preparation_refresh.py','scripts/maintenance/workflow_oracle_mapping_postprobe.py','scripts/maintenance/workflow_oracle_preparation_runner.py','scripts/maintenance/workflow_oracle_preparation_maintenance.py')
    if plan_id in ('s2-s3-01-access-01','s2-s3-01-runtime-01'):
        names+=tuple('scripts/maintenance/workflow_oracle_mapping_'+part+'.py' for part in ('acl_host','acl_lease','acl_observation'))
    if plan_id=='s2-s3-01-runtime-01':names+=('scripts/maintenance/workflow-oracle-s2-runtime-plan.json','scripts/maintenance/workflow_oracle_runtime_window.py','scripts/maintenance/workflow-oracle-runtime-close-registry.json')
    return {name: sha(ordinary(root/name).read_bytes()) for name in names}


def stable_host(host):
    require(host['taskId'] == TASK and host['runId'] == RUN and COMMAND.fullmatch(host['commandId']), 'OMQ_HOST_OWNER')
    require(host['ports'] == dict(api=15741, secondary=15742, oidc=15743, web=15744), 'OMQ_HOST_PORTS')
    require(set(host['services']) in ({'api', 'platform-pg', 'fuseki', 'rustfs', 'keycloak-test'},
                                     {'api', 'api-secondary', 'platform-pg', 'fuseki', 'rustfs', 'keycloak-test'}), 'OMQ_HOST_SERVICES')
    for service in host['services'].values():
        require(HEX.fullmatch(service['containerId']) and re.fullmatch('sha256:[0-9a-f]{64}', service['imageId'])
                and service['pid'] > 0 and utc(service['startedAt']) and HEX.fullmatch(service['mountSha256'])
                and service['networks'], 'OMQ_HOST_IDENTITY')
    require(len({service['containerId'] for service in host['services'].values()}) == len(host['services']), 'OMQ_DUPLICATE_HOST')
    require(HEX.fullmatch(host['oracle']['containerId']) and HEX.fullmatch(host['oracle']['networkId'])
            and re.fullmatch('sha256:[0-9a-f]{64}', host['oracle']['imageId']), 'OMQ_SOURCE_IDENTITY')
    for name in ('snapshotId', 'buildInputKey', 'buildOutputKey', 'runtimeHelperSha256', 'composeSha256'):
        require(HEX.fullmatch(host[name]), 'OMQ_HOST_KEY')
    return {name: value for name, value in host.items() if name != 'commandId'}


def browser_invocation(root, mode, case, host, api_build, test_build, stage_inputs):
    return _browser_invocation(mode,case,host,api_build,test_build,stage_inputs,drivers(root,mode,plan_id=stage_inputs.get("plan",{}).get("planId")))


def _browser_invocation(mode, case, host, api_build, test_build, stage_inputs, pinned):
    """供正式调用和独立重开共同推导命令。声明的 stageInputs 必须和实际选择吻合。"""
    require(mode in BROWSER and case in (ERRORS if mode == READY else ('healthy',)), 'OMQ_SCENARIO')
    require(stage_inputs['mode'] == mode and stage_inputs['case'] == case and stage_inputs['phase'] in ('s0', 's1', 's2', 's3'), 'OMQ_STAGE')
    require(stage_inputs['phase'] == ('s0' if mode.startswith('s0-') or mode in ('provision', 'mapping', 'auth-handoff-s1', 'reader-auth')
                                      else 's2' if mode.startswith('s2-') else 's3' if mode in ('s3', 'ui-s3', 'ui-s1') else 's1'), 'OMQ_PHASE')
    require(host['buildInputKey'] == api_build['inputKey'] and host['buildOutputKey'] == api_build['outputKey'], 'OMQ_HOST_BUILD')
    for binding in (api_build, test_build):
        require(set(binding) == {'receiptSha256','inputKey','outputKey'} and all(HEX.fullmatch(v) for v in binding.values()), 'OMQ_BUILD_KEY')
    args = [NODE, DRIVER, '--task', TASK, '--run-id', RUN, '--mode', mode]
    if mode in ('auth-handoff-s1','s2-s3-oracle'):
        prefix='s2-s3' if mode=='s2-s3-oracle' else 'auth-handoff'
        require(stage_inputs['plan']==batch_plan(ROOT,mode,stage_inputs['plan']['planId']) and COMMAND.fullmatch(stage_inputs['executionId']) and
                stage_inputs['batchInput']==prefix+'-'+stage_inputs['executionId']+'.json','OMQ_BATCH_INPUT')
        args += ['--batch-input',stage_inputs['batchInput']]
    components = dict(taskId=TASK, runId=RUN, mode=mode, case=case, drivers=pinned,
                      api=api_build, tests=test_build, host=stable_host(host), stageInputs=stage_inputs)
    return args, digest_value(components), 'omq-browser-'+mode


class Originals:
    """RF-02 的准确成员、双流和运行身份条件，应用于 Oracle 独立目录。"""

    def __init__(self, root, group, index):
        require(group in {'admission','s0','s1','s2','s3'}, 'OMQ_ARCHIVE_STAGE')
        self.root, self.prefix, self.index = root, PUBLIC/group/'originals', index
        self.examined = {}

    def raw(self, name):
        require(Path(name).name == name and re.fullmatch(r'[A-Za-z0-9_.-]+', name), 'OMQ_ORIGINAL_NAME')
        item = self.index[name]
        original = (self.prefix/name).as_posix()
        require(item['originalPath'] == original and item['encoding'] in ('raw','base64')
                and item['path'] == original + ('.raw.json' if item['encoding'] == 'base64' else ''), 'OMQ_ORIGINAL_PATH')
        data = restore(self.root, item)
        self.examined[original] = sha(data)
        return data

    def read(self, name):
        return json.loads(self.raw(name))

    def command(self, cid, argv, stage, input_key, parent_id, cwd, *, command_run=None):
        require(COMMAND.fullmatch(cid), 'OMQ_COMMAND_ID')
        row = self.read(cid+'-receipt.json')
        require(row['schemaVersion'] == 2 and row['commandId'] == cid and row['taskId'] == TASK and row['runId'] == (command_run or RUN)
                and row['stage'] == stage and row['parentId'] == parent_id and row['started'] is True and row['signal'] is None
                and row['cwd'] == str(cwd) and row['commandSummary'] == summary(argv) and row['inputFingerprint'] == input_key,
                'OMQ_COMMAND_BINDING')
        policy = sha(ordinary(self.root/'scripts/maintenance/workflow_execution.py').read_bytes())
        require(row['deadlineSeconds'] > 0 and HEX.fullmatch(row['environmentFingerprint']) and
                row['identity'] == digest_value([input_key, row['environmentFingerprint'], summary(argv)['sha256'],
                                                 str(cwd), row['deadlineSeconds'], policy]), 'OMQ_COMMAND_IDENTITY')
        require(utc(row['startedAtUtc']) <= utc(row['endedAtUtc']) and row['elapsedSeconds'] >= 0, 'OMQ_COMMAND_TIMING')
        streams = []
        for key in ('stdout', 'stderr'):
            data = self.raw(cid+'-'+key+'.txt')
            require(row[key]['sha256'] == sha(data) and row[key]['sizeBytes'] == len(data), 'OMQ_COMMAND_STREAM')
            streams.append(data)
        return row, *streams


def build_binding(archive, target, measured_worktree):
    """从当前输入和实测输出原件重算构建关联，拒绝自报的三元组。"""
    import workflow_m2_build as build
    name = target+'-build-binding.json'
    raw = archive.raw(name)
    result = json.loads(raw)
    history=getattr(archive,'frozenPrefixBuild',None)
    expected_input=history['inputKey'] if history is not None and target in ('api','agent') else build.inputs(target)
    require(result['taskId'] == TASK and result['target'] == target and result['worktree'] == str(measured_worktree)
            and result['status'] == 'PASS' and result['exitCode'] == 0 and result['inputKey'] == expected_input,
            'OMQ_BUILD_BINDING')
    marker = str(Path(build.TARGETS[target]).parent/'bin/Debug/net10.0'/(Path(build.TARGETS[target]).stem+'.dll'))
    files = result['outputs']
    require(marker in files and all(HEX.fullmatch(value) for value in files.values()), 'OMQ_BUILD_OUTPUT')
    require(result['logSha256'] == sha(archive.raw(target+'-bound-build.txt')), 'OMQ_BUILD_LOG')
    return dict(inputKey=result['inputKey'], outputKey=sha(json.dumps(files,sort_keys=True).encode()), receiptSha256=sha(raw))


def setup_platform_program(data, mode):
    """仅 provision/mapping 未调用就绪夹具或 window-pair。保留其余代码与真实 browser CLI 分发。"""
    require(mode in ('provision','mapping'),'OMQ_SETUP_SCOPE')
    module=ast.parse(data)
    skip={'ready_fixture','ready_grants_sql','fixed_window_pair'}
    result=[]
    found=set()
    for node in module.body:
        if isinstance(node,ast.FunctionDef) and node.name in skip:
            require(node.name not in found and not node.decorator_list and not node.args.defaults,
                    'OMQ_SETUP_EXCLUDED_FUNCTION')
            found.add(node.name)
            continue
        if isinstance(node,ast.If):
            for child in ast.walk(node):
                if isinstance(child,ast.keyword) and child.arg=='choices' and isinstance(child.value,ast.Tuple):
                    child.value.elts=[item for item in child.value.elts if not (isinstance(item,ast.Constant) and item.value=='window-pair')]
                if isinstance(child,ast.Dict):
                    selected=[(key,value) for key,value in zip(child.keys,child.values,strict=True) if not (
                        isinstance(key,ast.Constant) and key.value=='window-pair' and isinstance(value,ast.Name) and value.id=='fixed_window_pair')]
                    child.keys=[k for k,_ in selected]
                    child.values=[v for _,v in selected]
        result.append(ast.dump(node,include_attributes=False))
    require('ready_fixture' in found,'OMQ_SETUP_ARCHITECTURE')
    return result


def measured_browser(archive, measured, mode, case, host, api, tests, stage):
    current=drivers(archive.root,mode,plan_id=stage.get("plan",{}).get("planId"))
    original={}
    for name,digest in current.items():
        data=git_original(archive.root,measured,name)
        original[name]=sha(data)
        if digest!=original[name]:
            if measured=='2a2ea74ff72c22860e4927318913eaece9d14f9f' and mode=='s2-s3-oracle' and stage['plan']['planId']=='s2-s3-01':
                from workflow_oracle_mapping_continuation import compatible_prefix
                if not getattr(archive,"prefixCompatibilityChecked",False):
                    compatible_prefix(archive,measured,mode,stage)
                    archive.prefixCompatibilityChecked=True
            else:
                require(name==PLATFORM and mode in ('provision','mapping') and
                        setup_platform_program(data,mode)==setup_platform_program(ordinary(archive.root/name).read_bytes(),mode),
                        'OMQ_BROWSER_DRIVER_CHANGED')
    archive.browserIdentity=dict(measuredCommit=measured,measuredDrivers=original,candidateDrivers=current)
    return _browser_invocation(mode,case,host,api,tests,stage,original)


def browser_report(archive, entry, origin, mode, case, host, api_build, test_build, stage):
    """预期拒绝和健康场景使用相同命令、构建、驱动、宿主、窗口与非零检查门禁。"""
    measured=entry.get('measuredCommit')
    batch=entry.get('batch')
    invocation_mode=batch['stageInputs']['mode'] if batch else mode
    invocation_stage=batch['stageInputs'] if batch else stage
    if measured:
        argv,key,label=measured_browser(archive,measured,invocation_mode,case,host,api_build,test_build,invocation_stage)
    else:
        argv,key,label=browser_invocation(archive.root,invocation_mode,case,host,api_build,test_build,invocation_stage)
    row, stdout, _ = archive.command(entry['commandId'], argv, label, key, host['commandId'], origin)
    require(row['deadlineSeconds']==(batch_plan(archive.root,invocation_mode,invocation_stage['plan']['planId'])['deadlineSeconds'] if batch else 180), 'OMQ_BROWSER_DEADLINE')
    name = entry['report']
    require(re.fullmatch('browser-'+re.escape(mode)+r'-[0-9]{13}\.json', name), 'OMQ_REPORT_NAME')
    report, result = archive.read(name), json.loads(stdout)
    if batch:
        parent=archive.read(batch['report'])
        require(result['report']==str(origin/'artifacts/workflow'/TASK/RUN/batch['report']),'OMQ_BATCH_OUTPUT_REPORT')
        validate_batch(archive,parent,result,row,invocation_stage,origin)
        matches=[r for r in parent['stages'] if r['mode']==mode and Path(r['report']).name==name]
        require(len(matches)==1,'OMQ_BATCH_STAGE_SELECTION')
        item=matches[0];spec=invocation_stage['plan']['stages'][item['index']]
        require(report['batch']==dict(executionId=invocation_stage['executionId'],planId=invocation_stage['plan']['planId'],index=item['index'],**spec)
                and report['stageInputs']==stage and item['startedAtUtc']==report['startedAtUtc'] and item['finishedAtUtc']==report['finishedAtUtc']
                and item['elapsedMs']==report['elapsedMs'] and 0<=report['elapsedMs']<=spec['seconds']*1000,'OMQ_BATCH_STAGE_IDENTITY')
    else:
        require(result['report'] == str(origin/'artifacts/workflow'/TASK/RUN/name)
                and result['status'] == report['status'] and result['failure'] == report.get('failure')
                and result['checks'] == len(report['checks']), 'OMQ_REPORT_OUTPUT')
    require(report['taskId'] == TASK and report['runId'] == RUN and report['mode'] == mode and report['inputsUnchanged'] is True
            and not report.get('bindingFailure') and not report.get('networkFailure') and not report.get('externalRequests')
            and report['http'] and report['checks'], 'OMQ_REPORT_INPUT')
    require(utc(row['startedAtUtc']) <= utc(report['startedAtUtc']) <= utc(report['finishedAtUtc']) <= utc(row['endedAtUtc']),
            'OMQ_REPORT_TIMELINE')
    for binding in (report['inputBinding'], report['outputBinding']):
        require(stable_host(binding['api']) == stable_host(host), 'OMQ_REPORT_HOST')
    require(report['inputBinding']['web'] == report['outputBinding']['web'] and
            (report['inputBinding']['web'] is not None) == mode.startswith('ui-'), 'OMQ_REPORT_WEB')
    require(report['inputBinding']['api']['commandId'] != report['outputBinding']['api']['commandId'], 'OMQ_HOST_PROBE_REUSE')
    if RUN==PRODUCT_RUN:
        require(report.get('browser',{}).get('authentication')=='INTERACTIVE_OIDC' and report['browser']['channel']=='msedge' and
                re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}',report['browser']['version']) and
                {'oracle_current_original_subject_'+name for name in (('viewer-a',) if mode=='reader-auth' else ('operator-ab','auditor-ab','operator-a','viewer-a'))}
                <= {c['name'] for c in report['checks'] if c['status']=='PASS'},'OMQ_RESUME_NORMAL_OIDC')
    expected = ERRORS[case] if mode == READY else None
    if expected:
        require(row['exitCode'] == 1 and row['classification'] == 'EXIT_FAILURE' and report['status'] == 'FAIL'
                and report['failure']['code'] == expected and report['failure']['phase'] == 'oracle_scenario_ready', 'OMQ_EXPECTED_REJECTION')
    else:
        require((batch is not None or row['exitCode'] == 0 and row['classification'] == 'SUCCESS') and report['status'] == 'PASS'
                and all(check['status'] == 'PASS' for check in report['checks']), 'OMQ_HEALTHY')
    return report, row


def validate_batch(archive,parent,result,row,stage,origin):
    """真实父命令的固定计划、顺序、时间和原件逐一核对，阶段不是虚构子进程。"""
    plan=batch_plan(archive.root,stage['mode'],stage['plan']['planId'])
    require(stage['plan']==plan and parent['input']==dict(executionId=stage['executionId'],plan=plan,**({'qualifiedPrefix':stage['qualifiedPrefix']} if 'qualifiedPrefix' in plan else {}))
            and parent['taskId']==TASK and parent['runId']==PRODUCT_RUN and parent['mode']==plan['mode'],'OMQ_BATCH_PARENT')
    require(result==dict(status=parent['status'],report=str(origin/'artifacts/workflow'/TASK/RUN/Path(result['report']).name),stages=parent['stages'])
            and re.fullmatch('browser-'+plan['mode']+r'-[0-9]{13}\.json',Path(result['report']).name),'OMQ_BATCH_OUTPUT')
    require(row['classification'] in ('SUCCESS','EXIT_FAILURE') and row['exitCode']==(0 if parent['status']=='PASS' else 1)
            and 0<=row['elapsedSeconds']<=plan['deadlineSeconds'] and 0<=parent['preMs']<=60000 and 0<=parent['postMs']<=60000,
            'OMQ_BATCH_DEADLINE')
    previous=utc(parent['startedAtUtc'])
    require(utc(row['startedAtUtc'])<=previous<=utc(parent['finishedAtUtc'])<=utc(row['endedAtUtc']),'OMQ_BATCH_WINDOW')
    require(0<len(parent['stages'])<=len(plan['stages']),'OMQ_BATCH_COUNT')
    for index,item in enumerate(parent['stages']):
        spec=plan['stages'][index]
        require(item['index']==index and item['mode']==spec['mode'] and previous<=utc(item['startedAtUtc'])<=utc(item['finishedAtUtc'])
                <=utc(parent['finishedAtUtc']) and (index==len(parent['stages'])-1 or item['status']=='PASS'),'OMQ_BATCH_ORDER')
        name=Path(item['report']).name
        require(item['report']==str(origin/'artifacts/workflow'/TASK/RUN/name) and re.fullmatch('browser-'+spec['mode']+r'-[0-9]{13}\.json',name),'OMQ_BATCH_MEMBER')
        original=archive.read(name)
        require(item==dict(status=original['status'],phase=item['phase'],report=item['report'],checks=len(original['checks']),
                          failure=original.get('failure'),mode=original['mode'],index=index,reportSha256=sha(archive.raw(name)),startedAtUtc=original['startedAtUtc'],
                          finishedAtUtc=original['finishedAtUtc'],elapsedMs=original['elapsedMs']),'OMQ_BATCH_MEMBER_BINDING')
        require(original['batch']==dict(executionId=stage['executionId'],planId=plan['planId'],index=index,**spec),'OMQ_BATCH_MEMBER_PLAN')
        if item['status']=='PASS':
            require(0<=item['elapsedMs']<=spec['seconds']*1000 and all(c['status']=='PASS' for c in original['checks']),'OMQ_BATCH_STAGE_DEADLINE')
        previous=utc(item['finishedAtUtc'])
    if parent['status']=='PASS':
        require(len(parent['stages'])==len(plan['stages']) and all(r['status']=='PASS' for r in parent['stages']),'OMQ_BATCH_COMPLETE')
    else:
        require(parent.get('failure') or parent['stages'][-1]['status']=='FAIL','OMQ_BATCH_FAILURE')


def verify_product_manifest(host,manifest,manifest_hash):
    """七个准确身份和三张网络均须与观测一致，旧单 API 栈不能充当替代执行。"""
    ids = {**{n:r['containerId'] for n,r in host['services'].items()},'oracle':host['oracle']['containerId']}
    require(manifest_hash==host.get('resourceManifestSha256') and
            (manifest['taskId'],manifest['runId'],manifest['snapshotId'])==(TASK,PRODUCT_RUN,host['snapshotId']) and
            set(ids)=={'api','api-secondary','fuseki','platform-pg','keycloak-test','rustfs','oracle'} and
            ids==manifest['ids'] and len(set(ids.values()))==7,'OMQ_RESUME_MANIFEST')
    nets=manifest['networks']
    require(set(nets)=={'platform-internal','host-entry','source-internal'} and
            all(HEX.fullmatch(value) for value in nets.values()) and len(set(nets.values()))==3 and
            host['oracle']['networkId']==nets['source-internal'],'OMQ_RESUME_NETWORKS')
    for role,service in host['services'].items():
        expected = {'platform-internal'}
        if role in ('api','api-secondary','keycloak-test'):
            expected.add('host-entry')
        if role in ('api','api-secondary'):
            expected.add('source-internal')
        actual = list(service['networks'].values())
        require(len(expected)==len(actual) and {nets[k] for k in expected}==set(actual),'OMQ_RESUME_SERVICE_NETWORKS')


def host_observation(archive, host, api_build, origin, *, session_directory=None):
    """重开准确容器安全字段、冻结程序集、只读挂载与原 Docker 命令。"""
    from workflow_oracle_mapping_platform import HOST_FORMAT, IMAGES
    from workflow_oracle_mapping_resources import SOURCE
    inputs = archive.read('formal-api-inputs.json')
    manifest = None
    if host['runId']==PRODUCT_RUN:
        manifest = archive.read('formal-resources.json')
        verify_product_manifest(host,manifest,sha(archive.raw('formal-resources.json')))
        require(manifest['apiBuildId']==inputs['buildCommandId'] and manifest['buildOutputKey']==api_build['outputKey'],
                'OMQ_RESUME_MANIFEST_BUILD')
    snapshot = archive.read('api-snapshot.json')
    require(inputs['taskId'] == TASK and inputs['runId'] == RUN and inputs['build'] == api_build
            and inputs['snapshotId'] == snapshot['snapshotId'] == host['snapshotId']
            and inputs['relaySha256'] == host['runtimeHelperSha256']
            and inputs['composeSha256'] == host['composeSha256'] == sha(archive.raw('formal-api-compose.json')), 'OMQ_PLATFORM_INPUTS')
    identity = {k:snapshot[k] for k in ('files','inputs','commandId','environment','taskId','resourceRun')}
    require(snapshot['schemaVersion'] == 2 and snapshot['taskId'] == TASK and snapshot['resourceRun'] == RUN
            and snapshot['inputs'] == api_build and snapshot['commandId'] == inputs['buildCommandId']
            and digest_value(identity) == host['snapshotId']
            and snapshot['directory'] == f'artifacts/workflow/{TASK}/{RUN}/runtime-snapshots/{host["snapshotId"]}', 'OMQ_SNAPSHOT')
    api = archive.read('api-build-binding.json')
    prefix = 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/'
    require({k.removeprefix(prefix):v for k,v in api['outputs'].items() if k.startswith(prefix)} == snapshot['files'], 'OMQ_SNAPSHOT_FILES')
    ids = {name:service['containerId'] for name,service in host['services'].items()}
    roles = sorted(ids)
    source = host['oracle']['containerId']
    argv = ['docker','--context','desktop-linux','inspect','-f',HOST_FORMAT,*[ids[role] for role in roles],source]
    key = digest_value([inputs,ids,source,HOST_FORMAT])
    row,stdout,_ = archive.command(host['commandId'],argv,'omq-host-inspect',key,None,origin)
    require(row['classification'] == 'SUCCESS' and row['exitCode'] == 0 and row['deadlineSeconds'] == 12, 'OMQ_HOST_INSPECT')
    for role,line in zip([*roles,'oracle'],stdout.decode().strip().splitlines(),strict=True):
        cid,image,task,run,state,pid,started,raw_mounts,raw_networks = line.split('|')
        expected_run = RESOURCE_RUN if manifest and role not in ('api','api-secondary') else RUN
        require(task == TASK and run == expected_run and state == 'running' and int(pid) > 0, 'OMQ_HOST_OBSERVED')
        networks = dict(pair.split('=') for pair in raw_networks.split())
        if role == 'oracle':
            require(cid == source and image == SOURCE.split('@')[1] and list(networks.values()) == [host['oracle']['networkId']], 'OMQ_OBSERVED_ORACLE')
            continue
        mounts = json.loads(raw_mounts)
        require(host['services'][role] == dict(containerId=cid,imageId=IMAGES[role],startedAt=started,pid=int(pid),
                mountSha256=digest_value(mounts),networks=networks) and image == IMAGES[role], 'OMQ_OBSERVED_HOST')
        if role in ('api','api-secondary'):
            root_mount = [m for m in mounts if m['Destination'] == '/app']
            require(len(root_mount)==1 and root_mount[0]['RW'] is False and
                    root_mount[0]['Source'].removeprefix('/host_mnt') == str(origin/snapshot['directory'])
                    and not any(m['Destination'].startswith('/app/') for m in mounts), 'OMQ_OBSERVED_SNAPSHOT')
        if role=='api-secondary' and session_directory is not None:
            ticket_mount=[m for m in mounts if m['Destination']=='/session-tests' or m['Destination'].startswith('/session-tests/')]
            require(len(ticket_mount)==1 and ticket_mount[0]['Type']=='bind' and ticket_mount[0]['Destination']=='/session-tests'
                    and ticket_mount[0]['RW'] is False and ticket_mount[0]['Source'].removeprefix('/host_mnt')==str(session_directory),
                    'OMQ_AUTH_SESSION_LIVE_MOUNT')
    return row


OBSERVER = 'scripts/maintenance/workflow_oracle_mapping_formal_observer.py'
AUDIT_IMPORTS = ('scripts/maintenance/workflow_execution.py','scripts/maintenance/workflow_oracle_mapping_resources.py',
                 'scripts/maintenance/workflow_oracle_mapping_window.py')


def git_original(root, commit, name):
    require(re.fullmatch('[0-9a-f]{40}',commit) and subprocess.run(
        ['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=root,capture_output=True).returncode==0,'OMQ_MEASURED_ANCESTRY')
    row=subprocess.run(['git','show',commit+':'+name],cwd=root,capture_output=True)
    require(row.returncode==0,'OMQ_MEASURED_FILE')
    return row.stdout


def audit_program(data, *, historical=True):
    """审计段包含导入、常量、身份/登录/SQL、解析与真执行；后续定义不得覆盖或更改这些入口。"""
    module=ast.parse(data)
    stop=next((i for i,node in enumerate(module.body) if isinstance(node,ast.FunctionDef) and node.name=='audit_window'),None)
    require(stop is not None,'OMQ_AUDIT_PROGRAM')
    prefix=module.body[:stop+1]
    # 旧命令只调用默认物理 Run。按其确定实参折叠唯一的非默认资源分支，
    # SQL、解析、身份核验和外部命令的其余 AST 仍逐节点与实测版本相同。
    audit = prefix[-1]
    if historical and [arg.arg for arg in audit.args.kwonlyargs]==['operation_run']:
        require([ast.unparse(value) for value in audit.args.kw_defaults]==['RUN'],'OMQ_AUDIT_SCOPE_DEFAULT')
        audit.args.kwonlyargs=[]
        audit.args.kw_defaults=[]
        class HistoricalRun(ast.NodeTransformer):
            def visit_If(self,node):
                if ast.unparse(node.test)=='operation_run != RUN' and not node.orelse:
                    return None
                return self.generic_visit(node)
            def visit_Name(self,node):
                if node.id=='operation_run':
                    node.id='RUN'
                return node
        HistoricalRun().visit(audit)
    names={node.id for top in prefix for node in ast.walk(top) if isinstance(node,ast.Name)}
    names.update(node.name for node in prefix if isinstance(node,ast.FunctionDef))
    for node in module.body[stop+1:]:
        if isinstance(node,(ast.ClassDef,ast.FunctionDef)):
            require(node.name not in names and not node.decorator_list,'OMQ_AUDIT_PROGRAM_SHADOW')
        else:
            require(isinstance(node,ast.If) and ast.unparse(node.test)=="__name__ == '__main__'" and not node.orelse,
                    'OMQ_AUDIT_PROGRAM_EFFECT')
    return [ast.dump(node,include_attributes=False) for node in prefix]


def measured_audit_key(archive, call, commit):
    """还原运行时完整 observer 文件散列，当前窄审计程序、导入与已登记命令均须匹配。"""
    current=ordinary(archive.root/OBSERVER).read_bytes()
    measured=git_original(archive.root,commit,OBSERVER)
    historical = RUN==RESOURCE_RUN
    require(call['definition']['parserSha256']==sha(current) and
            audit_program(measured,historical=historical)==audit_program(current,historical=historical),
            'OMQ_AUDIT_PROGRAM_CHANGED')
    dependencies={}
    for path in AUDIT_IMPORTS if historical else (*AUDIT_IMPORTS,PLATFORM):
        data=git_original(archive.root,commit,path)
        require(data==ordinary(archive.root/path).read_bytes(),'OMQ_AUDIT_DEPENDENCY_CHANGED')
        dependencies[path]=sha(data)
    definition={**call['definition'],'parserSha256':sha(measured)}
    key=digest_value(definition)
    archive.auditIdentity=dict(measuredCommit=commit,originalProgramSha256=sha(measured),candidateProgramSha256=sha(current),
        auditProgramSha256=digest_value(audit_program(current,historical=historical)),dependencies=dependencies,commandInputFingerprint=key)
    return key


def audit_observation(archive, audit, row, host, origin, measured=None):
    """审计重新采用已登记的窄投影 SQL 与解析器；不能把其他窗口的零计数借给当前场景。"""
    require((audit['taskId'],audit['runId'],audit['sourceId']) == (TASK,RUN,host['oracle']['containerId'])
            and utc(audit['startUtc']) == utc(row['startedAtUtc']) and utc(audit['endUtc']) == utc(row['endedAtUtc']), 'OMQ_AUDIT_WINDOW')
    from workflow_oracle_mapping_formal_observer import audit_invocation, parse_audit, ns
    from workflow_oracle_mapping_resources import SOURCE
    call = audit_invocation(audit['sourceId'], audit['startUtc'], audit['endUtc'], audit['clientId'])
    source = host['oracle']['containerId']
    fmt = '{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.State.Status}}'
    identity,raw,_ = archive.command(audit['sourceIdentityCommand'],['docker','--context','desktop-linux','inspect','-f',fmt,source],
        'oracle-audit-source-identity',digest_value([source,SOURCE,TASK,RESOURCE_RUN]),None,origin)
    require(identity['exitCode']==0 and identity['classification']=='SUCCESS' and
            raw.decode().strip()=='|'.join([source,SOURCE.split('@')[1],TASK,RESOURCE_RUN,'running']), 'OMQ_AUDIT_SOURCE')
    key = measured_audit_key(archive,call,measured)
    command,stdout,_ = archive.command(audit['commandId'],call['argv'],'oracle-formal-audit-window',key,None,origin)
    records = parse_audit(stdout)
    require(command['exitCode'] == 0 and command['classification'] == 'SUCCESS' and utc(command['startedAtUtc']) >= utc(row['endedAtUtc'])
            and records == audit['records'] and len(records) == audit['sourceAuditCount'] and digest_value(records) == audit['recordsSha256'],
            'OMQ_AUDIT_OUTPUT')
    clocks = [line.strip()[6:] for line in stdout.decode().splitlines() if line.strip().startswith('CLOCK|')]
    require(audit['observerId']=='OMQ_OBSERVER' and len(clocks)==2 and clocks==audit['sourceClock'] and ns(clocks[0])<=ns(clocks[1])
            and all(utc(audit['startUtc']) <= utc(item['utc']) < utc(audit['endUtc'])
                    and (audit['clientId'] is None or audit['clientId']==item['clientId']) for item in records), 'OMQ_AUDIT_CLOCK')
    bounds = audit['errorBounds']
    earliest = ns(clocks[0])+bounds['lowerNs']+999
    latest = ns(clocks[1])+bounds['upperNs']
    require(ns(identity['endedAtUtc']) <= earliest+999 and earliest <= ns(command['startedAtUtc'])+999
            and ns(command['endedAtUtc']) <= latest+999 and bounds['lowerNs']<=bounds['upperNs'], 'OMQ_AUDIT_ERROR_BOUNDS')
    return records


def batch_audit_closure(archive, entry, row, host, origin, measured):
    """正式阶段入口消费父全窗及全部阶段原件，按完整事件和时钟误差拒绝遗漏或歧义。"""
    from workflow_oracle_mapping_formal_observer import ns
    parent = archive.read(entry['batch']['report'])
    plan = batch_plan(archive.root,entry['batch'].get('stageInputs',{}).get('mode','auth-handoff-s1'),entry['batch'].get('stageInputs',{}).get('plan',{}).get('planId'))
    planned = plan['stages'][:len(parent['stages'])] if plan['mode']=='s2-s3-oracle' else plan['stages']
    require([item['mode'] for item in parent['stages']] == [item['mode'] for item in planned],
            'OMQ_BATCH_AUDIT_STAGES')
    prefix = 'formal-audit-' + entry['commandId']
    parent_audit = archive.read(prefix + '.json')
    require(parent_audit['clientId'] is None, 'OMQ_BATCH_AUDIT_UNFILTERED')
    records = audit_observation(archive, parent_audit, row, host, origin, measured)
    observations = []
    previous = ns(row['startedAtUtc'])
    for item in parent['stages']:
        window = dict(startedAtUtc=item['startedAtUtc'], endedAtUtc=item['finishedAtUtc'])
        start, end = ns(window['startedAtUtc']), ns(window['endedAtUtc'])
        require(previous <= start < end <= ns(row['endedAtUtc']), 'OMQ_BATCH_AUDIT_ORDER')
        audit = archive.read(prefix + '-' + item['mode'] + '.json')
        require(audit['clientId'] is None, 'OMQ_BATCH_AUDIT_UNFILTERED')
        stage_records = audit_observation(archive, audit, window, host, origin, measured)
        observations.append((item['mode'], start, end, audit, stage_records))
        previous = end
    # 保守采用全部实测源/宿主偏差区间的包络，另计源时间戳微秒量化误差。
    # 任一事件可能跨阶段边界即拒绝；不通过平移窗口或删除间隙事件制造零读。
    audits = [parent_audit, *[item[3] for item in observations]]
    lower = min(audit['errorBounds']['lowerNs'] for audit in audits)
    upper = max(audit['errorBounds']['upperNs'] for audit in audits) + 999
    key_fields = ('instance', 'session', 'entry', 'statement', 'owner', 'table')
    def events(rows):
        result = {}
        for event in rows:
            key = tuple(event[field] for field in key_fields)
            require(key not in result, 'OMQ_BATCH_AUDIT_DUPLICATE')
            result[key] = event
        return result
    complete = events(records)
    union = {}
    stages = []
    for mode, start, end, audit, stage_records in observations:
        expected = {key: event for key, event in complete.items() if start <= ns(event['utc']) < end}
        actual = events(stage_records)
        require(actual == expected, 'OMQ_BATCH_AUDIT_EVENT_SET')
        for key, event in actual.items():
            instant = ns(event['utc'])
            require(start <= instant + lower and instant + upper < end, 'OMQ_BATCH_AUDIT_CLOCK_AMBIGUOUS')
            require(key not in union, 'OMQ_BATCH_AUDIT_DUPLICATE')
            union[key] = event
        stages.append(dict(mode=mode, startUtc=audit['startUtc'], endUtc=audit['endUtc'],
                           commandId=audit['commandId'], sourceAuditCount=len(actual), recordsSha256=digest_value(stage_records)))
    require(union == complete, 'OMQ_BATCH_AUDIT_GAP_OR_OMISSION')
    return dict(parentCommandId=entry['commandId'], auditCommandId=parent_audit['commandId'],
                startUtc=parent_audit['startUtc'], endUtc=parent_audit['endUtc'], sourceId=parent_audit['sourceId'],
                observerId=parent_audit['observerId'], clientId=None, eventKeyFields=list(key_fields),
                sourceClockError=dict(lowerNs=lower, upperNs=upper, timestampResolutionNs=1000),
                records=records, recordsSha256=digest_value(records), sourceAuditCount=len(records),
                stages=stages, gapReadCount=0, status='COMPLETE_EVENT_PARTITION')


def auth_test_snapshot(archive,origin,tests):
    """重开 AgentTests 的实际构建、双流、冻结文件清单及副实例的只读挂载配方。"""
    import workflow_m2_build as build
    snapshot=archive.read('agent-snapshot.json')
    inputs=archive.read('formal-api-inputs.json')
    build_row=archive.read('agent-build-binding.json')
    prefix=str(Path(build.TARGETS['agent']).parent/'bin/Debug/net10.0')+'/'
    files={p.removeprefix(prefix):digest for p,digest in build_row['outputs'].items() if p.startswith(prefix)}
    identity={k:snapshot[k] for k in ('files','inputs','commandId','environment','taskId','resourceRun')}
    sid=digest_value(identity)
    require(snapshot['schemaVersion']==2 and (snapshot['taskId'],snapshot['resourceRun'])==(TASK,PRODUCT_RUN)
            and snapshot['snapshotId']==sid==inputs['sessionSnapshotId'] and snapshot['inputs']==tests
            and snapshot['files']==files and 'OntologyPlatform.AgentTests.dll' in files
            and snapshot['directory']==f'artifacts/workflow/{TASK}/{PRODUCT_RUN}/runtime-snapshots/{sid}','OMQ_AUTH_SESSION_SNAPSHOT')
    directory=origin/snapshot['directory']
    spec=archive.read('formal-api-compose.json')['services']['api-secondary']['volumes']
    require([v for v in spec if v.split(':')[1]=='/session-tests' or v.split(':')[1].startswith('/session-tests/')]
            ==[str(directory)+':/session-tests:ro'],'OMQ_AUTH_SESSION_RECIPE')
    cid=snapshot['commandId']
    run=archive.read(cid+'-receipt.json')['runId']
    command=build_row['command']
    require((COMMAND.fullmatch(run) or RUN==PRODUCT_RUN and run==PRODUCT_RUN) and command[1:]==['build',build.TARGETS['agent'],'--no-restore','--disable-build-servers','-m:1','-v:q']
            and Path(command[0]).is_absolute() and Path(command[0]).name=='dotnet','OMQ_AUTH_BUILD_ARGV')
    argv=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*command]
    row,out,err=archive.command(cid,argv,'command',tests['inputKey'],None,origin,command_run=run)
    streams=origin/'artifacts/workflow'/TASK/'commands'/run/cid
    require(row['classification']=='SUCCESS' and row['exitCode']==0 and row['deadlineSeconds']==180
            and row['stdout']['path']==str(streams/'stdout.txt') and row['stderr']['path']==str(streams/'stderr.txt')
            and snapshot['environment']=={'toolEnvironment':row['environmentFingerprint']}
            and out+err==archive.raw('agent-bound-build.txt'),'OMQ_AUTH_AGENT_COMPILE')
    return directory,utc(row['endedAtUtc'])


def auth_projections(report):
    """核正式 /me 原始字节及四主体角色站点；只接受认证入口预期的八个只读请求。"""
    from workflow_oracle_mapping_identity_recovery import ROSTER
    requests=report['http']
    require(len(report['authIdentities'])==len(ROSTER)==4 and len(requests)==8,'OMQ_AUTH_HTTP_COUNT')
    checks={c['name'] for c in report['checks'] if c['status']=='PASS'}
    require({'distinct_oidc_subjects','oracle_four_current_tickets'}<=checks,'OMQ_AUTH_CHECKS')
    for i,((user,subject,role,sites),ident) in enumerate(zip(ROSTER.values(),report['authIdentities'],strict=True)):
        label=user.removeprefix('g2-')
        csrf,me=requests[2*i:2*i+2]
        for req,path in ((csrf,'/auth/csrf'),(me,'/api/v1/platform/me')):
            require(set(req)=={'method','path','status','elapsedMs','sha256'} and
                    (req['method'],req['path'],req['status'])==('GET',path,200) and
                    req['elapsedMs']>=0 and HEX.fullmatch(req['sha256']),'OMQ_AUTH_HTTP')
        require({name+label for name in ('real_oidc_cookie_','oracle_current_original_subject_','oracle_current_role_sites_',
                                         'oracle_synthetic_profile_shape_')}<=checks,'OMQ_AUTH_IDENTITY_CHECKS')
        require(set(ident)=={'label','subjectId','roles','scopes','meSha256','rawMe'} and
                ident['meSha256']==me['sha256']==sha(ident['rawMe'].encode()),'OMQ_AUTH_ME_BYTES')
        parsed=json.loads(ident['rawMe'])
        require(ident['label']==label and ident['subjectId']==subject and ident['roles']==[role]
                and parsed==dict(subjectId=subject,displayName='合成开发身份 '+label,roles=[role],scopes=ident['scopes'])
                and sorted(ident['scopes'],key=lambda s:s['siteId'])==[dict(organizationId='org-demo',siteId=site) for site in sites],
                'OMQ_AUTH_PROJECTION')
    return [item[1] for item in ROSTER.values()]


def auth_session_case(archive,report,audit,records,stage,host,api,tests,origin,inside,after):
    """独立消费认证的当前宿主、票据进程及完整源审计窗口。"""
    from workflow_oracle_mapping_resume import session_invocation
    require(RUN==PRODUCT_RUN and report['scope']=='ORACLE_FOUR_CURRENT_SESSIONS' and audit['clientId'] is None
            and not records and 'fixtureBefore' not in stage,'OMQ_AUTH_SCOPE')
    subjects=auth_projections(report)
    ticket_case(archive,report,report['session'],subjects,host,api,tests,origin,inside,after)


def ticket_case(archive,report,session,subjects,host,api,tests,origin,inside,after):
    from workflow_oracle_mapping_resume import session_invocation
    nonce=session['nonce']
    require(set(session)=={'nonce','commandId','observations'} and COMMAND.fullmatch(nonce),'OMQ_AUTH_SESSION_NONCE')
    directory,built=auth_test_snapshot(archive,origin,tests)
    cid=session['commandId']
    parent_id=archive.read(cid+'-receipt.json')['parentId']
    require(COMMAND.fullmatch(parent_id) and parent_id not in
            (host['commandId'],inside['commandId'],after['commandId']),'OMQ_AUTH_SESSION_PARENT')
    observed=host_observation(archive,{**host,'commandId':parent_id},api,origin,session_directory=directory)
    argv=session_invocation(host['services']['api-secondary']['containerId'],nonce,210)
    row,out,err=archive.command(cid,argv,'omq-session-real',digest_value(tests),parent_id,origin)
    begin,end=utc(row['startedAtUtc']),utc(row['endedAtUtc'])
    require(built<=utc(inside['startedAtUtc']) and utc(inside['endedAtUtc'])<=utc(observed['startedAtUtc']) and
            utc(report['startedAtUtc'])<=utc(observed['startedAtUtc'])<=utc(observed['endedAtUtc'])<=begin<=end<=utc(after['startedAtUtc'])
            and end<=utc(report['finishedAtUtc']) and row['deadlineSeconds']==22 and row['classification']=='SUCCESS'
            and row['exitCode']==0 and mtp(out+err,1)==1,'OMQ_AUTH_SESSION_COMMAND')
    observations=json.loads(out.splitlines()[-1])
    require(observations==session['observations'] and len(observations)==4 and
            [o['subjectId'] for o in observations]==subjects and len({o['sessionHash'] for o in observations})==4
            and len({o['requiredUntilUtc'] for o in observations})==1,'OMQ_AUTH_TICKETS')
    for item in observations:
        require(set(item)=={'case','subjectId','ExpiresAtUtc','requiredUntilUtc','sessionHash'} and
                item['case']=='OMQ_BROWSER_SESSION_READY' and HEX.fullmatch(item['sessionHash']),'OMQ_AUTH_OBSERVATION')
        required=utc(item['requiredUntilUtc'])
        require(begin<=required-dt.timedelta(seconds=210)<=end and utc(item['ExpiresAtUtc'])>required,'OMQ_AUTH_TTL')


def persistence_case(report, audit, stage, raw_result=None):
    """重开单表正例与新会话恢复的实际 HTTP、准确主体、原字节及整个浏览器命令读审计。"""
    require(audit['clientId'] is None,'OMQ_S1_AUDIT_CLIENT_FILTER')
    audit_rows = audit['records']
    proof = report['oraclePersistence']
    actor = stage['readerSubjectId']
    require(proof['subjectId']==actor and HEX.fullmatch(proof['resultHash']) and HEX.fullmatch(proof['sessionHash'])
            and re.fullmatch(r'browser-s1-[0-9]{13}\.json',proof['reportName'])
            and re.fullmatch(r'query-[a-f0-9]{32}',proof['queryId']), 'OMQ_S1_RESULT_IDENTITY')
    sessions = report['scenarioReady']['session']['observations']
    require(len(sessions)==len({s['subjectId'] for s in sessions})==4 and
            [s['sessionHash'] for s in sessions if s['subjectId']==actor]==[proof['sessionHash']], 'OMQ_S1_OWNER_SESSION')
    path = '/api/v1/data/semantic-queries/'+proof['queryId']+'/result'
    gets = [r for r in report['http'] if r['method']=='GET' and r['path']==path and r['status']==200]
    require(len(gets)==1 and gets[0]['sha256']==proof['resultHash'], 'OMQ_S1_HTTP_BYTES')
    if report['mode']=='s1':
        require(raw_result is not None and sha(raw_result)==proof['resultHash'] and len(audit_rows)==1 and
                (audit_rows[0]['owner'],audit_rows[0]['table'],audit_rows[0]['action'],audit_rows[0]['code'])==
                ('PRODUCTION','OMQ_ENTITY','SELECT',0), 'OMQ_S1_SOURCE_AND_BYTES')
        posts=[r for r in report['http'] if r['method']=='POST' and r['path']=='/api/v1/data/semantic-queries'
               and r['status']==200 and r['sha256']==proof['resultHash']]
        require(len(posts)==2 and json.loads(raw_result)['status']=='FOUND' and
                report['scope']=='S1_ORACLE_OIDC_QUERY_PERSISTENCE', 'OMQ_S1_FIRST_AND_REPLAY')
    else:
        require(report['mode']=='s1-reopen' and report['scope']=='S1_ORACLE_NEW_SESSION_RESULT_RESTORE' and not audit_rows
                and not any(r['method']=='POST' and r['path']=='/api/v1/data/semantic-queries' for r in report['http']),
                'OMQ_S1_RESTORE_REPLAYED')
    return proof


def mapping_case(report,stage):
    from workflow_oracle_mapping_identity_recovery import ROSTER
    proof=report['mappingQualification']
    require(set(proof)=={'proposal','release','active'},'OMQ_MAPPING_PROOF')
    proposal,release,active=(json.loads(proof[k]) for k in ('proposal','release','active'))
    for kind,path in [('proposal','/api/v1/mapping-proposals/'+proposal['proposalId']),
                      ('release','/api/v1/mapping-releases/'+stage['mappingReleaseId']),
                      ('active','/api/v1/mappings/'+proposal['mappingId']+'/active')]:
        require(any(r['method']=='GET' and r['path']==path and r['status']==200 and r['sha256']==sha(proof[kind].encode()) for r in report['http']),'OMQ_MAPPING_HTTP')
    review=release['manifest']['reviewReceipt'];activation=proposal['activation']
    require(report['scope']=='ORACLE_FORMAL_SINGLE_TABLE_MAPPING' and proposal['status']=='APPROVED'
            and proposal['submittedBy']==ROSTER['operator'][1] and proposal['decision']['decidedBy']==ROSTER['auditor'][1]
            and proposal['decision']['decision']=='APPROVE' and proposal['bindingHash']==proposal['decision']['bindingHash']==review['bindingHash']
            and review['proposalId']==proposal['proposalId']==activation['proposalId']
            and review['submittedBy']==proposal['submittedBy'] and review['decidedBy']==proposal['decision']['decidedBy']
            and activation['manifestHash']==release['manifestHash'] and activation['mappingReleaseId']==active['mappingReleaseId']==stage['mappingReleaseId']
            and activation['activationRevision']==active['activationRevision']==stage['activationRevision'],'OMQ_MAPPING_CHAIN')


def reopen_browser(archive, entry, origin, mode, case):
    api = build_binding(archive, 'api', origin)
    tests = build_binding(archive, 'agent', origin)
    stored = archive.read(entry['host'])
    host = stored['host'] if 'host' in stored else stored
    measured=stored.get('testedCommit') or entry['measuredCommit']
    entry={**entry,'measuredCommit':measured}
    report,row = browser_report(archive, entry, origin, mode, case, host, api, tests, entry['stageInputs'])
    before = host_observation(archive, host, api, origin)
    inside = host_observation(archive, report['inputBinding']['api'], api, origin)
    after = host_observation(archive, report['outputBinding']['api'], api, origin)
    require(len({h['commandId'] for h in (before,inside,after)}) == 3 and
            utc(before['endedAtUtc']) <= utc(row['startedAtUtc']) <= utc(inside['startedAtUtc']) <= utc(inside['endedAtUtc'])
            <= utc(after['startedAtUtc']) <= utc(after['endedAtUtc']) <= utc(row['endedAtUtc']), 'OMQ_HOST_WINDOW')
    audit = archive.read(entry['audit'])
    window=dict(startedAtUtc=report['startedAtUtc'],endedAtUtc=report['finishedAtUtc']) if entry.get('batch') else row
    require(audit['clientId'] is None, 'OMQ_AUDIT_UNFILTERED')
    records = audit_observation(archive,audit,window,host,origin,measured)
    if entry.get('batch'):
        archive.batchAudit = batch_audit_closure(archive,entry,row,host,origin,measured)
    if mode=='s0-oracle-auth':
        auth_session_case(archive,report,audit,records,entry['stageInputs'],host,api,tests,origin,inside,after)
    if entry.get('batch') and mode=='mapping':
        mapping_case(report,entry['stageInputs'])
    if entry.get('batch') and mode!='s0-oracle-auth':
        from workflow_oracle_mapping_identity_recovery import ROSTER
        subjects=[v[1] for v in ROSTER.values()]
        session=report['session'] if mode=='reader-auth' else report['sessionBefore']
        ticket_case(archive,report,session,subjects,host,api,tests,origin,inside,after)
        if mode in (NATURAL_CANCEL,'s1','s1-reopen'):
            ticket_case(archive,report,report['scenarioReady']['session'],subjects,host,api,tests,origin,inside,after)
        if mode=='reader-auth':
            require(not records and audit['clientId'] is None and report['scope']=='ORACLE_NEW_READER_AUTHENTICATED'
                    and len(report['authIdentities'])==1 and report['authIdentities'][0]['subjectId']==subjects[-1]
                    and any(c==dict(name='oracle_new_reader_context',status='PASS') for c in report['checks']), 'OMQ_READER_AUTH')
    if mode in ('s0-oracle-natural','s0-oracle-cancel',NATURAL_CANCEL):
        from workflow_oracle_mapping_formal_observer import classify
        witness = report['oracleWitness']
        key = witness['idempotencyKey']
        require(re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',key)
                and witness['output']=='formal-witness-'+key+'.json','OMQ_FORMAL_SOURCE_FILE')
        raw = archive.read(witness['output'])
        require(raw['idempotencyKey']==key and raw['taskId']==TASK and raw['runId']==RUN and raw['status']=='OBSERVED'
                and raw['sourceId']==host['oracle']['containerId'] and stable_host(raw['hostBefore'])==stable_host(host)
                and stable_host(raw['hostAfter'])==stable_host(host),'OMQ_FORMAL_SCOPE')
        proof = classify(raw)
        require(proof==raw['final'] and all(proof[k]==v for k,v in witness['final'].items()) and
                proof['queryId']==raw['queryId'] and proof['clientId'] and proof['slotReleased'] is True
                and proof['residualSourceWork']==0 and proof['allSourceWorkEnded'] is True and
                0<=proof['branchUpperMs']<=1000 and 0<=proof['totalUpperMs']<=5000, 'OMQ_FORMAL_BUDGET')
        require(any(item['clientId']==proof['clientId'] for item in records),'OMQ_FORMAL_SOURCE_AUDIT')
        if mode=='s0-oracle-natural':
            require(proof['naturalCompletion'] and proof['nativeErrorCode']==0 and not proof['formalCancelCommitted']
                    and not proof['nativeCancelCausedTermination'], 'OMQ_NATURAL_CONTROL')
        elif mode==NATURAL_CANCEL:
            from workflow_oracle_mapping_formal_observer import pg_query
            ack=raw['cancelResponseObserved']
            require(ack['status']=='CANCEL_OBSERVED' and ack['queryId']==proof['queryId'] and
                    ack['httpStatus']==witness['cancel']['httpStatus'] and
                    utc(window['startedAtUtc'])<=utc(raw['naturalReturnNotifiedUtc'])<utc(witness['cancel']['issuedUtc'])+dt.timedelta(milliseconds=1) and
                    utc(witness['cancel']['issuedUtc'])<=utc(witness['cancel']['observedUtc'])<=utc(ack['utc'])<=utc(window['endedAtUtc']),
                    'OMQ_NATURAL_CANCEL_HANDOFF')
            readback = raw['terminalReadback']
            pg_id = host['services']['platform-pg']['containerId']
            args = ['docker','--context','desktop-linux','exec','-i','--user','postgres',pg_id,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
            sql = b'BEGIN READ ONLY;\n'+pg_query(key,entry['stageInputs']['readerSubjectId']).encode()+b'\nCOMMIT;'
            command,stdout,_ = archive.command(readback['commandId'],args,'omq-pg-formal-terminal-state',sha(sql),None,origin)
            require(command['exitCode']==0 and command['classification']=='SUCCESS' and command['deadlineSeconds']==15 and
                    utc(ack['utc'])<=utc(command['startedAtUtc'])<=utc(command['endedAtUtc'])<=utc(window['endedAtUtc']) and
                    json.loads(stdout)==readback['state'] and
                    [r for r in records if r['clientId']==proof['clientId']]==raw['audit']['records'],'OMQ_NATURAL_TERMINAL_ORIGINAL')
            natural_race_case(report,proof)
        else:
            require(proof['formalCancelCommitted'] and proof['sameExecutionActiveAtCommit'] and
                    proof['nativeCancelCausedTermination'] and proof['nativeErrorCode']==1013 and
                    not proof['deadlineOrDisconnectBeforeCommit'] and 0<=proof['cleanupUpperMs']<=250 and
                    proof['successfulResults']==proof['successReceipts']==proof['successAudits']==0,'OMQ_CANCEL_CAUSE')
    if mode in ('s1','s1-reopen'):
        payload = None
        if mode=='s1':
            require(report['oraclePersistence']['reportName']==entry['report'],'OMQ_S1_ORIGINAL_REPORT')
            payload = archive.raw(entry['report'][:-5]+'-result.json')
        archive.persistence = persistence_case(report,audit,entry['stageInputs'],payload)
        archive.persistenceWindow = {'startedAtUtc':window['startedAtUtc'],'endedAtUtc':window['endedAtUtc']}
    if entry.get('batch',{}).get('stageInputs',{}).get('mode')=='s2-s3-oracle' and mode not in ('s0-oracle-auth','reader-auth'):
        from workflow_oracle_mapping_s2_contract import reopen_stage
        archive.s2Qualification=reopen_stage(archive,report,records,host,origin,measured,window)
    if mode.startswith('ui-'):
        wb=archive.read('web-build-binding.json')
        import workflow_m2_build as build
        web=report['inputBinding']['web']
        require(wb['taskId']==TASK and wb['target']=='web' and wb['status']=='PASS' and wb['exitCode']==0 and wb['inputKey']==build.inputs('web')
                and web['inputKey']==wb['inputKey'] and web['receiptSha256']==sha(archive.raw('web-build-binding.json'))
                and web['outputKey']==sha(json.dumps(wb['outputs'],sort_keys=True).encode()) and web['taskId']==TASK
                and web['runId']==RUN and web['buildId'] and wb['outputs'].get('apps/web/.next/BUILD_ID') in {sha(web['buildId'].encode()),sha((web['buildId']+'\n').encode())}, 'OMQ_BROWSER_WEB_BUILD')
    if mode == READY:
        require(archive.read(entry['audit'])['clientId'] is None and not records, 'OMQ_PREREQUISITE_BUSINESS_READ')
        if case == 'healthy':
            ready = report['scenarioReady']
            require({'oracle_ready_catalog_projection','oracle_ready_current_connection','oracle_ready_closed_versions',
                     'oracle_ready_current_activation','oracle_capability_registered','oracle_current_source_and_grants'}
                    <= {c['name'] for c in report['checks']} and ready['grantCount'] == 3 and ready['fieldCount'] == 11
                    and ready['requiredSeconds'] > 0 and ready['remainingSeconds'] >= ready['requiredSeconds'], 'OMQ_HEALTHY_PREREQUISITES')
    return len(report['checks'])


def natural_race_case(report, proof):
    """真实 AC03-A 消费者分别核验成功先赢与取消先赢，不能混用副作用条件。"""
    witness = report['oracleWitness']
    if proof.get('naturalSuccessWon') is True:
        rows = [r for r in report['http'] if r['method']=='POST' and
                r['path']=='/api/v1/data/semantic-queries/'+proof['queryId']+'/cancel']
        require(len(rows)==1 and rows[0]['status']==409 and rows[0].get('code')=='query_already_finished' and
                witness['cancel']['httpStatus']==409 and witness['cancel'].get('code')=='query_already_finished' and
                report['scope']=='ORACLE_NATURAL_SUCCESS_BEFORE_CANCEL' and witness['execute']['status']==200 and
                witness['execute']['queryStatus']=='FOUND' and 0<=witness['execute']['elapsedMs']<=5000 and
                proof['naturalCompletion'] and proof['nativeErrorCode']==0 and not proof['formalCancelCommitted'] and
                not proof['nativeCancelCausedTermination'] and not proof['sameExecutionActiveAtCommit'] and
                proof['successfulResults']==proof['successReceipts']==proof['successAudits']==1 and
                0<=proof['successCleanupUpperMs']<=250 and proof['earliestCleanupMarginMs']>=0,'OMQ_NATURAL_SUCCESS_RACE')
        return
    require(report['scope']=='ORACLE_NATURAL_COMPLETION_BEFORE_PLATFORM_CANCEL' and
            witness['cancel']['httpStatus']==200 and witness['cancel']['executionStatus']=='CANCELLED' and
            witness['execute']['status'] in (409,503,504) and 0<=witness['execute']['elapsedMs']<=5000 and
            proof.get('naturalCompletionBeforeCancel') is True and proof['formalCancelCommitted'] and
            not proof['sameExecutionActiveAtCommit'] and not proof['nativeCancelCausedTermination'] and
            0<=proof['naturalCleanupUpperMs']<=250 and proof['earliestCleanupMarginMs']>=0 and proof['successfulResults']==proof['successReceipts']==proof['successAudits']==0,
            'OMQ_NATURAL_CANCEL_RACE')


def environment_checks(archive, origin):
    import platform
    import workflow_environment as env
    prep = archive.read('prepare.json')
    packages, projects, files = env.locks(archive.root)
    admitted = env.git_json(archive.root,env.BASE,env.ADMISSION)
    permitted = env.approved_archives(archive.root,TASK,packages)
    identity = env.identities(dict(platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0],
        files=files,tools=admitted['files'],sdk=env.SDK_ARCHIVES,archives={k:v['archiveSha256'] for k,v in permitted.items()}),origin)
    require(prep['contentKey'] == identity['contentKey'] and prep['workspaceKey'] == identity['workspaceKey'] and
            prep['taskId'] == TASK and prep['worktree'] == str(origin) and prep['status'] == 'DEPENDENCIES_READY'
            and prep['downloads'] == prep['sdkDownloads'] == prep['runtimeCredentialsCopied'] == 0 and prep['node'] == NODE
            and prep['packages'] == len(packages) and prep['projects'] == len(projects)
            and prep['webDependencies']['download'] == prep['webDependencies']['install'] == 0, 'OMQ_DEPENDENCY_BINDING')
    require(all(sha(Path(t['path']).read_bytes()) == t['sha256'] for t in admitted['files']) and
            sorted(p['project'] for p in prep['assets']) == sorted(p['path'] for p in projects), 'OMQ_DEPENDENCY_ASSETS')
    return len(projects)


def test_invocation(origin, target, expression, minimum):
    import workflow_m2_build as build
    project=Path(build.TARGETS[target])
    return ['/usr/local/share/dotnet/dotnet',str(origin/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')),
            '--filter',expression,'--minimum-expected-tests',str(minimum),'--no-ansi','--progress','off',
            '--results-directory',str(origin/'artifacts/workflow'/TASK/RUN/'test-results'/target)]


TESTS = {
    'wire': ('wire','FullyQualifiedName~OntologyPlatform.G2ContractTests.G4WireContractTests', 2),
    'binding': ('connections','FullyQualifiedName~OntologyPlatform.ConnectionsTests.OracleMappingBindingTests',3),
    'deadline': ('query','FullyQualifiedName=OntologyPlatform.QueryTests.G4QueryRaceTests.OraclePhysicalCleanupCannotExtendOrConfirmAnExpiredWindow',1),
    'mcp-deadline': ('agent','FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMcpTests.G4RunReservationConsumesOriginalQueryDeadline',1),
}


def reopen_test(archive, entry, name, origin):
    target,expression,minimum = TESTS[name]
    binding = build_binding(archive,target,origin)
    argv = test_invocation(origin,target,expression,minimum)
    row,out,err = archive.command(entry['commandId'],argv,'omq-test-'+name,digest_value(binding),None,origin)
    require(row['exitCode']==0 and row['classification']=='SUCCESS', 'OMQ_TEST_EXIT')
    return mtp(out+err,minimum)


class CurrentTestOriginals(Originals):
    """按冻结选择的四组构建及命令身份重开私有原件，文件名均由消费者构造。"""

    def __init__(self,root,index):
        self.root,self.index,self.examined=root,index,{}
        self.area=root/'artifacts/workflow'/TASK

    def raw(self,name):
        cid,sep,member=name.partition('-')
        if COMMAND.fullmatch(cid) and member in ('receipt.json','stdout.txt','stderr.txt'):
            require(cid in {item['commandId'] for item in self.index['tests'].values()},'OMQ_TEST_COMMAND_SCOPE')
            path=self.area/'commands'/PRODUCT_RUN/cid/member
        else:
            require(name in {target+suffix for target,_,_ in TESTS.values()
                    for suffix in ('-build-binding.json','-bound-build.txt')},'OMQ_TEST_BUILD_SCOPE')
            digest=self.index['buildFiles'][name]
            require(HEX.fullmatch(digest),'OMQ_TEST_BUILD_SHA')
            original=Path(name)
            path=self.area/(original.stem+'-'+digest+original.suffix)
        data=ordinary(path).read_bytes()
        if not COMMAND.fullmatch(cid):
            require(sha(data)==digest,'OMQ_TEST_BUILD_BYTES')
        self.examined[str(path.relative_to(self.root))]=sha(data)
        return data


def record_current_tests(root,prior_sha=None,formal_parent=None):
    """只执行当前输入缺少的选择项；已冻结项须通过同一 reopen_test 才能复用。"""
    import workflow
    import workflow_execution as ex
    import workflow_m2_build as build
    require(RUN==PRODUCT_RUN,'OMQ_RECORD_PRODUCT_RUN')
    route=dict(taskId=TASK,runId=RUN,scope='s2-s3-01-runtime-01',batch='s2-s3-01')
    directory=root/'artifacts/workflow'/TASK/RUN/route['batch']
    prior=None
    if prior_sha:
        require(HEX.fullmatch(prior_sha),'OMQ_PRIOR_SELECTION')
        data=ordinary(directory/('engineering-selection-'+prior_sha+'.json')).read_bytes()
        require(sha(data)==prior_sha,'OMQ_PRIOR_SELECTION_SHA')
        prior=json.loads(data)
        require(all(prior[k]==v for k,v in route.items()) and prior['measuredWorktree']==str(root)
                and re.fullmatch('[0-9a-f]{40}',prior['measuredCommit']) and subprocess.run(
                    ['git','merge-base','--is-ancestor',prior['measuredCommit'],'HEAD'],cwd=root).returncode==0,'OMQ_PRIOR_SELECTION_SCOPE')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    require(not subprocess.check_output(['git','status','--porcelain','--','backend'],cwd=root),'OMQ_TEST_DIRTY_BACKEND')
    index=dict(**route,measuredWorktree=str(root),measuredCommit=commit,buildFiles={},tests={})
    archive=CurrentTestOriginals(root,index)
    for name,(target,expression,minimum) in TESTS.items():
        binding=build.validate(target,TASK)
        for suffix in ('-build-binding.json','-bound-build.txt'):
            path=archive.area/(target+suffix)
            data=ordinary(path).read_bytes()
            digest=sha(data)
            copy=ordinary(path.with_name(path.stem+'-'+digest+path.suffix))
            if not copy.exists():
                with copy.open('xb') as stream:
                    stream.write(data)
            require(sha(copy.read_bytes())==digest,'OMQ_BUILD_ARCHIVE')
            index['buildFiles'][path.name]=digest
        if prior and name in prior['tests'] and all(index['buildFiles'][target+k]==prior['buildFiles'][target+k]
                for k in ('-build-binding.json','-bound-build.txt')):
            entry=prior['tests'][name]
        else:
            result=ex.run(test_invocation(root,target,expression,minimum),root,task=TASK,run_id=RUN,
                stage='omq-test-'+name,input_key=digest_value(binding),timeout=120,
                environment=workflow.engineering_process_environment(TASK,route))
            entry=dict(commandId=result.receipt['commandId'])
        index['tests'][name]=entry
        reopen_test(archive,entry,name,root)
    if formal_parent is not None:
        require(COMMAND.fullmatch(formal_parent),'OMQ_FORMAL_PARENT')
        index['formalCommandId']=formal_parent
    data=encoded(index)
    digest=sha(data)
    selection=directory/('engineering-selection-'+digest+'.json')
    if not selection.exists():
        with selection.open('xb') as stream:
            stream.write(data)
    require(selection.read_bytes()==data,'OMQ_TEST_SELECTION_PERSISTENCE')
    return digest


def current_engineering(root,gate,input_key,scope,batch,selection_sha):
    """当前批次工程与产品原件沿同一登记门禁重开，源数据与命令不依赖历史 S0 选择表。"""
    import workflow
    require(RUN==PRODUCT_RUN and batch=='s2-s3-01' and scope=='s2-s3-01-runtime-01'
            and HEX.fullmatch(selection_sha or '') and workflow.input_key(root,gate)==input_key,'OMQ_CURRENT_ROUTE')
    path=root/'artifacts/workflow'/TASK/RUN/batch/('engineering-selection-'+selection_sha+'.json')
    raw=ordinary(path).read_bytes()
    require(sha(raw)==selection_sha,'OMQ_CURRENT_SELECTION_SHA')
    index=json.loads(raw)
    require((index['taskId'],index['runId'],index['scope'],index['batch'],index['measuredWorktree'])==
            (TASK,PRODUCT_RUN,scope,batch,str(root)) and re.fullmatch('[0-9a-f]{40}',index['measuredCommit'])
            and subprocess.run(['git','merge-base','--is-ancestor',index['measuredCommit'],'HEAD'],cwd=root).returncode==0,
            'OMQ_CURRENT_SELECTION_ID')
    require(set(index['tests'])<=set(TESTS),'OMQ_CURRENT_TEST_NAMES')
    archive=CurrentTestOriginals(root,index)
    if gate in ('contract','backend'):
        names=('wire','binding') if gate=='contract' else ('binding','deadline','mcp-deadline')
        tests=sum(reopen_test(archive,index['tests'][name],name,root) for name in names)
    elif gate in ('interaction','web'):
        parent=index.get('formalCommandId')
        require(COMMAND.fullmatch(parent or ''),'OMQ_FORMAL_S2_S3_NOT_RUN')
        modes=frozen_current_modes(root,scope,gate)
        tests=0
        for mode in modes:
            case=reopen_runtime_case(root,TASK,PRODUCT_RUN,parent,expected_mode=mode)
            require(case['status']=='CASE_QUALIFIED','OMQ_CURRENT_PRODUCT_CASE')
            tests+=case['checks']
            archive.examined.update({item['path']:item['sha256'] for item in case['members'].values()})
    else:
        require(False,'OMQ_CURRENT_ENVIRONMENT_ORIGINALS_NOT_RUN')
    require(tests>0,'OMQ_ZERO_CHECKS')
    return dict(taskId=TASK,runId=RUN,scope=scope,batch=batch,selectionSha256=selection_sha,gate=gate,
                inputKey=input_key,status='PASS',tests=tests,skipped=0,executionMode='REUSED',qualificationMode='FRESH',
                originals=archive.examined,oracleS0='BLOCKED',AC03B='NOT_QUALIFIED')


def frozen_current_modes(root,scope,gate):
    from workflow_oracle_mapping_s2_contract import frozen_plan
    modes=[item['mode'] for item in frozen_plan(root,scope)['stages']]
    return [mode for mode in modes if mode.startswith('ui-')==(gate=='web')]


def qualify(root, task, run_id, gate, input_key, scope=None, batch=None, selection_sha=None):
    import workflow
    require(task == TASK and run_id == RUN and gate in GATES and workflow.input_key(root,gate)==input_key, 'OMQ_QUALIFICATION_ID')
    if run_id==PRODUCT_RUN:
        return current_engineering(root,gate,input_key,scope,batch,selection_sha)
    require(scope is None and batch is None and selection_sha is None,'OMQ_HISTORICAL_SCOPE')
    # 一个不可变阶段选择表可被多个受影响门禁引用；每一行均从已公开原字节重新验证。
    group = {'environment':'admission','contract':'s0','backend':'s0','web':'s3','interaction':'s2'}[gate]
    selection = ordinary(root/PUBLIC/group/'qualification.json')
    require(selection.is_file(), 'OMQ_ORIGINALS_NOT_RUN_'+group)
    index = json.loads(selection.read_bytes())
    require(index['taskId']==TASK and index['runId']==RUN and index['group']==group and re.fullmatch('[0-9a-f]{40}',index['measuredCommit'])
            and subprocess.run(['git','merge-base','--is-ancestor',index['measuredCommit'],'HEAD'],cwd=root).returncode == 0,
            'OMQ_PRODUCT_ANCESTRY')
    archive = Originals(root,group,index['originals'])
    origin = Path(index['measuredWorktree'])
    require(origin.is_absolute() and '..' not in origin.parts, 'OMQ_WORKTREE')
    tests = 0
    if gate == 'environment':
        tests = environment_checks(archive,origin)
    elif gate in ('backend','contract'):
        for name in (('wire','binding') if gate=='contract' else ('binding','deadline','mcp-deadline')):
            tests += reopen_test(archive,index['tests'][name],name,origin)
    else:
        cases = ([(READY,case) for case in ERRORS]+[('s0-oracle-natural','healthy'),('s0-oracle-cancel','healthy')]) if gate=='interaction' else [('ui-s1','healthy'),('ui-s3','healthy')]
        for mode,case in cases:
            entry = index['cases'][mode+'-'+case]
            tests += reopen_browser(archive,entry,origin,mode,case)
    require(tests > 0, 'OMQ_ZERO_CHECKS')
    return dict(taskId=task,runId=run_id,gate=gate,inputKey=input_key,status='PASS',tests=tests,skipped=0,
                qualificationMode='FRESH',executionMode='REUSED',scope='registered affected gate evidence',originals=archive.examined)


class RuntimeOriginals(Originals):
    """首次归档前读取当前 Run 的同组原件。选择精确快照，拒绝被替换的构建或歧义别名。"""

    def __init__(self,root,dispatch):
        self.root, self.examined = root, {}
        self.area = root/'artifacts/workflow'/TASK/RUN
        self.dispatch = dispatch
        self.paths = {}
        self.frozenPrefixBuild=None
        if dispatch.get('commandId')=='edd1379b83c246329579075d16ccda58':
            from workflow_oracle_mapping_continuation import frozen_build_context
            self.frozenPrefixBuild=frozen_build_context(root,dispatch,self)

    def choose(self,pattern,matches):
        # 旧同任务快照若仍存在，只有原字节完全相同才可消除重名。
        candidates = [(p,ordinary(p).read_bytes()) for p in self.area.glob(pattern)]
        selected = [(p,data) for p,data in candidates if matches(data)]
        require(selected and len({sha(raw) for _,raw in selected})==1, 'OMQ_RUNTIME_ARTIFACT_MISSING')
        return selected[0][0]

    def raw(self,name):
        require(Path(name).name==name and re.fullmatch(r'[A-Za-z0-9_.-]+',name),'OMQ_RUNTIME_MEMBER')
        command = re.fullmatch('([a-f0-9]{32})-(receipt.json|stdout.txt|stderr.txt)',name)
        host=self.dispatch['host']
        if command:
            path=self.area.parent/'commands'/RUN/command[1]/command[2]
            if (self.dispatch['mode']=='s0-oracle-auth' or self.dispatch.get('batch')) and not path.is_file() and command[1]==self.read('agent-snapshot.json')['commandId']:
                candidates=list((self.area.parent/'commands').glob('*/'+command[1]+'/'+command[2]))
                require(len(candidates)==1 and COMMAND.fullmatch(candidates[0].parents[1].name),'OMQ_AUTH_BUILD_ORIGINAL')
                path=candidates[0]
        elif self.frozenPrefixBuild is not None and name in self.frozenPrefixBuild['members']:
            from workflow_oracle_mapping_continuation import frozen_member
            return frozen_member(self.root,self.frozenPrefixBuild['members'][name],self,name)
        elif name in ('api-build-binding.json','agent-build-binding.json','api-bound-build.txt','agent-bound-build.txt','web-build-binding.json'):
            path=self.area.parent/name
        elif name=='formal-resources.json' and self.dispatch['runId']==PRODUCT_RUN:
            path=self.choose('formal-resources*.json',lambda data: sha(data)==host['resourceManifestSha256'])
        elif name=='formal-api-inputs.json':
            def bound_inputs(data):
                entry=json.loads(data)
                return (entry.get('snapshotId')==host['snapshotId']
                        and entry.get('composeSha256')==host['composeSha256']
                        and entry.get('relaySha256')==host['runtimeHelperSha256'])
            path=self.choose('formal-api-inputs*.json',bound_inputs)
        elif name=='formal-api-compose.json':
            path=self.choose('formal-api-compose*.json',lambda data: sha(data)==host['composeSha256'])
        elif name=='agent-snapshot.json' and (self.dispatch['mode']=='s0-oracle-auth' or self.dispatch.get('batch')):
            snapshot=self.read('formal-api-inputs.json')['sessionSnapshotId']
            require(HEX.fullmatch(snapshot),'OMQ_AUTH_SESSION_SNAPSHOT_ID')
            path=self.area/'runtime-snapshots'/(snapshot+'.json')
        elif name=='api-snapshot.json':
            path=self.area/'runtime-snapshots'/(host['snapshotId']+'.json')
        elif self.dispatch.get('batch') and (name in self.dispatch['batchMembers'] or name in {
                'formal-audit-'+self.dispatch['commandId']+'-'+item['mode']+'.json'
                for item in self.dispatch['batch']['stageInputs']['plan']['stages']}):
            path=self.area/name
        elif self.dispatch['mode']=='s1' and name==self.dispatch['reports'][0][:-5]+'-result.json':
            path=self.area/name
        elif self.dispatch.get('batch') and self.dispatch['batch']['stageInputs']['mode']=='s2-s3-oracle' and re.fullmatch(
                r'(?:expiry|grant-plan|source-case|source-command|source-injected|source-restore|permission-case|permission-(?:revoke|field|expired|short|restore)|acl-case|acl-restored)-[a-f0-9]{32}[.]json',name):
            path=self.area/'s2-s3-01'/name
        elif self.dispatch.get('batch',{}).get('stageInputs',{}).get('plan',{}).get('qualifiedPrefix') and re.fullmatch(r'browser-s2-oracle-queries-[0-9]{13}[.]json',name):
            from workflow_oracle_mapping_continuation import prefix_result
            qualified=prefix_result(self.root,self)[0]
            require(name in qualified['members'],'OMQ_PREFIX_QUERY_MEMBER')
            path=self.root/qualified['members'][name]['path']
        elif name in self.dispatch['reports'] or name in (self.dispatch['file'],'formal-audit-'+self.dispatch['commandId']+'.json') or re.fullmatch(r'formal-witness-[a-f0-9-]{36}\.json',name):
            path=self.area/name
        else:
            raise ValueError('OMQ_RUNTIME_MEMBER_UNKNOWN')
        raw=ordinary(path).read_bytes()
        self.paths[name]=str(path.relative_to(self.root))
        self.examined[name]=sha(raw)
        return raw


def reopen_runtime_case(root,task,run,cid, *, expected_mode=None, _checked=None):
    require(task==TASK and run==RUN and COMMAND.fullmatch(cid),'OMQ_COMMAND_SCOPE')
    area=ordinary(root/'artifacts/workflow'/TASK/RUN)
    entries=list(area.glob('formal-run-*-'+cid+'.json'))
    require(len(entries)==1,'OMQ_RUNTIME_DISPATCH')
    dispatch=json.loads(ordinary(entries[0]).read_bytes())
    require(dispatch['taskId']==task and dispatch['runId']==run and dispatch['commandId']==cid and len(dispatch['reports'])==1
            and re.fullmatch('[0-9a-f]{40}',dispatch['testedCommit']),'OMQ_RUNTIME_DISPATCH_SCOPE')
    batch=None
    if dispatch['mode'] in ('auth-handoff-s1','s2-s3-oracle'):
        require(expected_mode in [x['mode'] for x in batch_plan(root,dispatch['mode'],dispatch['stageInputs']['plan']['planId'])['stages']],'OMQ_BATCH_EXPECTED_MODE')
        parent=json.loads(ordinary(area/dispatch['reports'][0]).read_bytes())
        matches=[r for r in parent['stages'] if r['mode']==expected_mode]
        require(len(matches)==1,'OMQ_BATCH_STAGE_NOT_RUN')
        name=Path(matches[0]['report']).name
        report=json.loads(ordinary(area/name).read_bytes())
        batch=dict(report=dispatch['reports'][0],stageInputs=dispatch['stageInputs'])
        dispatch={**dispatch,'batch':batch,'batchMembers':[dispatch['reports'][0],*[Path(r['report']).name for r in parent['stages']]],
                  'mode':expected_mode,'reports':[name],'stageInputs':report['stageInputs']}
    require(expected_mode is None or dispatch['mode']==expected_mode,'OMQ_UNEXPECTED_ORIGIN_MODE')
    dispatch['file']=entries[0].name
    archive=RuntimeOriginals(root,dispatch)
    source=archive.read(dispatch['file'])
    require(source['builds']['api']==build_binding(archive,'api',root) and source['builds']['agent']==build_binding(archive,'agent',root),
            'OMQ_DISPATCH_BUILDS')
    entry=dict(commandId=cid,report=dispatch['reports'][0],host=dispatch['file'],stageInputs=dispatch['stageInputs'],
               audit='formal-audit-'+cid+('-'+dispatch['mode'] if batch else '')+'.json',**({'batch':batch} if batch else {}))
    checks=reopen_browser(archive,entry,root,dispatch['mode'],dispatch['case'])
    persistence = {}
    if batch:
        checked={} if _checked is None else _checked
        checked[dispatch['mode']]=True
        prerequisites={'s0-oracle-auth':[],NATURAL_CANCEL:['s0-oracle-auth'],'mapping':[NATURAL_CANCEL],
                       's1':['mapping'],'reader-auth':['s1'],'s1-reopen':['reader-auth']}
        if batch['stageInputs']['mode']=='s2-s3-oracle':
            ordered=[item['mode'] for item in batch['stageInputs']['plan']['stages']]
            prerequisites={name:ordered[:index] for index,name in enumerate(ordered)}
        for required in prerequisites[dispatch['mode']]:
            if required not in checked:
                reopen_runtime_case(root,task,run,cid,expected_mode=required,_checked=checked)
        persistence['qualifiedPredecessors']=sorted(k for k in checked if k!=dispatch['mode'])
        persistence['batchAudit']=archive.batchAudit
        if batch['stageInputs']['plan'].get('qualifiedPrefix'):
            from workflow_oracle_mapping_continuation import reopen_prefix
            persistence['qualifiedPrefix']=reopen_prefix(root,batch['stageInputs'],archive)
    if hasattr(archive,'s2Qualification'):persistence['s2Qualification']=archive.s2Qualification
    if dispatch['mode'] in ('s1','s1-reopen'):
        persistence['persistence']=archive.persistence
        persistence['persistenceWindow']=archive.persistenceWindow
    if dispatch['mode']=='s1-reopen':
        prior = reopen_runtime_case(root,task,run,cid if batch else dispatch['stageInputs']['originCommandId'],expected_mode='s1')
        original = prior['persistence']
        require(all(original[k]==archive.persistence[k] for k in ('reportName','subjectId','resultHash','queryId')) and
                original['sessionHash']!=archive.persistence['sessionHash'] and
                utc(prior['persistenceWindow']['endedAtUtc'])<=utc(archive.persistenceWindow['startedAtUtc']),'OMQ_S1_RESTORE_ORIGIN')
        persistence['originCommandId']=prior['commandId']
        persistence['originMembers']=prior['members']
    return dict(taskId=task,runId=run,commandId=cid,measuredCommit=dispatch['testedCommit'],mode=dispatch['mode'],case=dispatch['case'],
                **persistence,
                **({'functional':{'AC03-A':'PASS'},'AC03-B':'NOT_QUALIFIED','cleanup250ms':'NOT_QUALIFIED','oracleS0':'BLOCKED'}
                   if dispatch['mode']==NATURAL_CANCEL else {}),
                status='CASE_QUALIFIED',checks=checks,scope='one measured scenario',executionMode='REUSED',qualificationMode='FRESH',auditIdentity=archive.auditIdentity,browserIdentity=archive.browserIdentity,members={n:dict(path=p,sha256=archive.examined[n],
                sizeBytes=ordinary(root/p).stat().st_size) for n,p in archive.paths.items()})


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('task','run-id'):
        cli.add_argument('--'+name,required=True)
    cli.add_argument('--gate')
    cli.add_argument('--input-key')
    for name in ('scope','batch','selection-sha'):
        cli.add_argument('--'+name)
    cli.add_argument('--case-command')
    cli.add_argument('--expected-mode',choices=sorted(BROWSER))
    args=cli.parse_args()
    try:
        if args.case_command:
            require(not args.gate and not args.input_key,'OMQ_QUALIFICATION_ARGUMENTS')
            result=reopen_runtime_case(ROOT,args.task,args.run_id,args.case_command,expected_mode=args.expected_mode)
        else:
            require(not args.expected_mode,'OMQ_QUALIFICATION_ARGUMENTS')
            result=qualify(ROOT,args.task,args.run_id,args.gate,args.input_key,args.scope,args.batch,args.selection_sha)
        print(json.dumps(result))
    except (ValueError,KeyError,OSError,TypeError) as error:
        raise SystemExit('OMQ_QUALIFICATION_REJECTED '+(str(error) if isinstance(error,ValueError) else type(error).__name__))
