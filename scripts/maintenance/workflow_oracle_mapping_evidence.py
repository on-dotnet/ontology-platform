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


def drivers(root, mode):
    names = DRIVERS
    if mode in ('s0-oracle-natural', 's0-oracle-cancel', NATURAL_CANCEL):
        names += ('scripts/maintenance/workflow_oracle_mapping_formal_observer.py',)
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
    return _browser_invocation(mode,case,host,api_build,test_build,stage_inputs,drivers(root,mode))


def _browser_invocation(mode, case, host, api_build, test_build, stage_inputs, pinned):
    """供正式调用和独立重开共同推导命令。声明的 stageInputs 必须和实际选择吻合。"""
    require(mode in BROWSER and case in (ERRORS if mode == READY else ('healthy',)), 'OMQ_SCENARIO')
    require(stage_inputs['mode'] == mode and stage_inputs['case'] == case and stage_inputs['phase'] in ('s0', 's1', 's2', 's3'), 'OMQ_STAGE')
    require(stage_inputs['phase'] == ('s0' if mode.startswith('s0-') or mode in ('provision', 'mapping')
                                      else 's3' if mode in ('s3', 'ui-s3') else 's1'), 'OMQ_PHASE')
    require(host['buildInputKey'] == api_build['inputKey'] and host['buildOutputKey'] == api_build['outputKey'], 'OMQ_HOST_BUILD')
    for binding in (api_build, test_build):
        require(set(binding) == {'receiptSha256','inputKey','outputKey'} and all(HEX.fullmatch(v) for v in binding.values()), 'OMQ_BUILD_KEY')
    args = [NODE, DRIVER, '--task', TASK, '--run-id', RUN, '--mode', mode]
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

    def command(self, cid, argv, stage, input_key, parent_id, cwd):
        require(COMMAND.fullmatch(cid), 'OMQ_COMMAND_ID')
        row = self.read(cid+'-receipt.json')
        require(row['schemaVersion'] == 2 and row['commandId'] == cid and row['taskId'] == TASK and row['runId'] == RUN
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
    require(result['taskId'] == TASK and result['target'] == target and result['worktree'] == str(measured_worktree)
            and result['status'] == 'PASS' and result['exitCode'] == 0 and result['inputKey'] == build.inputs(target),
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
    current=drivers(archive.root,mode)
    original={}
    for name,digest in current.items():
        data=git_original(archive.root,measured,name)
        original[name]=sha(data)
        if digest!=original[name]:
            require(name==PLATFORM and mode in ('provision','mapping') and
                    setup_platform_program(data,mode)==setup_platform_program(ordinary(archive.root/name).read_bytes(),mode),
                    'OMQ_BROWSER_DRIVER_CHANGED')
    archive.browserIdentity=dict(measuredCommit=measured,measuredDrivers=original,candidateDrivers=current)
    return _browser_invocation(mode,case,host,api,tests,stage,original)


def browser_report(archive, entry, origin, mode, case, host, api_build, test_build, stage):
    """预期拒绝和健康场景使用相同命令、构建、驱动、宿主、窗口与非零检查门禁。"""
    measured=entry.get('measuredCommit')
    if measured:
        argv,key,label=measured_browser(archive,measured,mode,case,host,api_build,test_build,stage)
    else:
        argv,key,label=browser_invocation(archive.root,mode,case,host,api_build,test_build,stage)
    row, stdout, _ = archive.command(entry['commandId'], argv, label, key, host['commandId'], origin)
    require(row['deadlineSeconds']==180, 'OMQ_BROWSER_DEADLINE')
    name = entry['report']
    require(re.fullmatch('browser-'+re.escape(mode)+r'-[0-9]{13}\.json', name), 'OMQ_REPORT_NAME')
    report, result = archive.read(name), json.loads(stdout)
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
                {'oracle_current_original_subject_'+name for name in ('operator-ab','auditor-ab','operator-a','viewer-a')}
                <= {c['name'] for c in report['checks'] if c['status']=='PASS'},'OMQ_RESUME_NORMAL_OIDC')
    expected = ERRORS[case] if mode == READY else None
    if expected:
        require(row['exitCode'] == 1 and row['classification'] == 'EXIT_FAILURE' and report['status'] == 'FAIL'
                and report['failure']['code'] == expected and report['failure']['phase'] == 'oracle_scenario_ready', 'OMQ_EXPECTED_REJECTION')
    else:
        require(row['exitCode'] == 0 and row['classification'] == 'SUCCESS' and report['status'] == 'PASS'
                and all(check['status'] == 'PASS' for check in report['checks']), 'OMQ_HEALTHY')
    return report, row


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


def host_observation(archive, host, api_build, origin):
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
    records = audit_observation(archive,audit,row,host,origin,measured)
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
            readback = raw['terminalReadback']
            pg_id = host['services']['platform-pg']['containerId']
            args = ['docker','--context','desktop-linux','exec','-i','--user','postgres',pg_id,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
            sql = b'BEGIN READ ONLY;\n'+pg_query(key,entry['stageInputs']['readerSubjectId']).encode()+b'\nCOMMIT;'
            command,stdout,_ = archive.command(readback['commandId'],args,'omq-pg-formal-terminal-state',sha(sql),None,origin)
            require(command['exitCode']==0 and command['classification']=='SUCCESS' and command['deadlineSeconds']==15 and
                    utc(row['startedAtUtc'])<=utc(command['startedAtUtc'])<=utc(command['endedAtUtc'])<=utc(row['endedAtUtc']) and
                    json.loads(stdout)==readback['state'] and
                    [r for r in records if r['clientId']==proof['clientId']]==raw['audit']['records'],'OMQ_NATURAL_TERMINAL_ORIGINAL')
            require(report['scope']=='ORACLE_NATURAL_COMPLETION_BEFORE_PLATFORM_CANCEL' and
                    witness['cancel']['httpStatus']==200 and witness['cancel']['executionStatus']=='CANCELLED' and
                    witness['execute']['status'] in (409,503,504) and 0<=witness['execute']['elapsedMs']<=5000 and
                    proof.get('naturalCompletionBeforeCancel') is True and proof['formalCancelCommitted'] and
                    not proof['sameExecutionActiveAtCommit'] and not proof['nativeCancelCausedTermination'] and
                    0<=proof['naturalCleanupUpperMs']<=250 and proof['earliestCleanupMarginMs']>=0 and proof['successfulResults']==proof['successReceipts']==proof['successAudits']==0,
                    'OMQ_NATURAL_CANCEL_RACE')
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
        archive.persistenceWindow = {'startedAtUtc':row['startedAtUtc'],'endedAtUtc':row['endedAtUtc']}
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


def qualify(root, task, run_id, gate, input_key):
    import workflow
    require(task == TASK and run_id == RUN and gate in GATES and workflow.input_key(root,gate)==input_key, 'OMQ_QUALIFICATION_ID')
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
        elif name=='api-snapshot.json':
            path=self.area/'runtime-snapshots'/(host['snapshotId']+'.json')
        elif self.dispatch['mode']=='s1' and name==self.dispatch['reports'][0][:-5]+'-result.json':
            path=self.area/name
        elif name in self.dispatch['reports'] or name in (self.dispatch['file'],'formal-audit-'+self.dispatch['commandId']+'.json') or re.fullmatch(r'formal-witness-[a-f0-9-]{36}\.json',name):
            path=self.area/name
        else:
            raise ValueError('OMQ_RUNTIME_MEMBER_UNKNOWN')
        raw=ordinary(path).read_bytes()
        self.paths[name]=str(path.relative_to(self.root))
        self.examined[name]=sha(raw)
        return raw


def reopen_runtime_case(root,task,run,cid, *, expected_mode=None):
    require(task==TASK and run==RUN and COMMAND.fullmatch(cid),'OMQ_COMMAND_SCOPE')
    area=ordinary(root/'artifacts/workflow'/TASK/RUN)
    entries=list(area.glob('formal-run-*-'+cid+'.json'))
    require(len(entries)==1,'OMQ_RUNTIME_DISPATCH')
    dispatch=json.loads(ordinary(entries[0]).read_bytes())
    require(dispatch['taskId']==task and dispatch['runId']==run and dispatch['commandId']==cid and len(dispatch['reports'])==1
            and re.fullmatch('[0-9a-f]{40}',dispatch['testedCommit']),'OMQ_RUNTIME_DISPATCH_SCOPE')
    require(expected_mode is None or dispatch['mode']==expected_mode,'OMQ_UNEXPECTED_ORIGIN_MODE')
    dispatch['file']=entries[0].name
    archive=RuntimeOriginals(root,dispatch)
    source=archive.read(dispatch['file'])
    require(source['builds']['api']==build_binding(archive,'api',root) and source['builds']['agent']==build_binding(archive,'agent',root),
            'OMQ_DISPATCH_BUILDS')
    entry=dict(commandId=cid,report=dispatch['reports'][0],host=dispatch['file'],stageInputs=dispatch['stageInputs'],
               audit='formal-audit-'+cid+'.json')
    checks=reopen_browser(archive,entry,root,dispatch['mode'],dispatch['case'])
    persistence = {}
    if dispatch['mode'] in ('s1','s1-reopen'):
        persistence['persistence']=archive.persistence
        persistence['persistenceWindow']=archive.persistenceWindow
    if dispatch['mode']=='s1-reopen':
        prior = reopen_runtime_case(root,task,run,dispatch['stageInputs']['originCommandId'],expected_mode='s1')
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
    cli.add_argument('--case-command')
    args=cli.parse_args()
    try:
        if args.case_command:
            require(not args.gate and not args.input_key,'OMQ_QUALIFICATION_ARGUMENTS')
            result=reopen_runtime_case(ROOT,args.task,args.run_id,args.case_command)
        else:
            result=qualify(ROOT,args.task,args.run_id,args.gate,args.input_key)
        print(json.dumps(result))
    except (ValueError,KeyError,OSError,TypeError) as error:
        raise SystemExit('OMQ_QUALIFICATION_REJECTED '+(str(error) if isinstance(error,ValueError) else type(error).__name__))
