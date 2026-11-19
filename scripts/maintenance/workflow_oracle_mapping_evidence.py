"""G4 Oracle 当前执行原件的资格分发；预检、构建、命令和无损恢复走既有消费者。"""
import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from workflow_evidence import restore
from workflow_execution import encoded, ordinary, sha
from workflow_m2_evidence import require, mtp
from workflow_oracle_mapping_resources import TASK, RUN

ROOT = Path(__file__).resolve().parents[2]
DRIVER = 'scripts/maintenance/workflow-m4-query.mjs'
PLATFORM = 'scripts/maintenance/workflow_oracle_mapping_platform.py'
NODE = '/opt/homebrew/Cellar/node@24/24.22.1/bin/node'
DRIVERS = (DRIVER, 'scripts/maintenance/workflow-oracle-query-fixture.mjs', PLATFORM,
           'scripts/maintenance/workflow_oracle_mapping_formal_observer.py', 'scripts/maintenance/workflow_execution.py',
           'scripts/maintenance/workflow_m2_build.py', 'infra/oracle/config/mapping-observer.sql')
GATES = {'environment', 'contract', 'backend', 'web', 'interaction'}
READY = 's0-oracle-ready'
ERRORS = {'healthy': None, 'expired': 'OMQ_READY_GRANT_EXPIRED', 'short': 'OMQ_READY_GRANT_TTL_SHORT',
          'catalog': 'OMQ_READY_CATALOG_STALE', 'activation': 'OMQ_READY_ACTIVATION_STALE'}
BROWSER = {'provision', 'mapping', READY, 's0-oracle-natural', 's0-oracle-cancel', 's1', 's1-reopen', 's3', 'ui-s1', 'ui-s3'}
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


def drivers(root):
    return {name: sha(ordinary(root/name).read_bytes()) for name in DRIVERS}


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
    """供正式调用和独立重开共同推导命令。声明的 stageInputs 必须和实际选择吻合。"""
    require(mode in BROWSER and case in (ERRORS if mode == READY else ('healthy',)), 'OMQ_SCENARIO')
    require(stage_inputs['mode'] == mode and stage_inputs['case'] == case and stage_inputs['phase'] in ('s0', 's1', 's2', 's3'), 'OMQ_STAGE')
    require(stage_inputs['phase'] == ('s0' if mode.startswith('s0-') or mode in ('provision', 'mapping')
                                      else 's3' if mode in ('s3', 'ui-s3') else 's1'), 'OMQ_PHASE')
    require(host['buildInputKey'] == api_build['inputKey'] and host['buildOutputKey'] == api_build['outputKey'], 'OMQ_HOST_BUILD')
    for binding in (api_build, test_build):
        require(set(binding) == {'receiptSha256','inputKey','outputKey'} and all(HEX.fullmatch(v) for v in binding.values()), 'OMQ_BUILD_KEY')
    args = [NODE, DRIVER, '--task', TASK, '--run-id', RUN, '--mode', mode]
    components = dict(taskId=TASK, runId=RUN, mode=mode, case=case, drivers=drivers(root),
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


def browser_report(archive, entry, origin, mode, case, host, api_build, test_build, stage):
    """预期拒绝和健康场景使用相同命令、构建、驱动、宿主、窗口与非零检查门禁。"""
    argv, key, label = browser_invocation(archive.root, mode, case, host, api_build, test_build, stage)
    row, stdout, _ = archive.command(entry['commandId'], argv, label, key, host['commandId'], origin)
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
    require(report['inputBinding']['api']['commandId'] != report['outputBinding']['api']['commandId'], 'OMQ_HOST_PROBE_REUSE')
    expected = ERRORS[case] if mode == READY else None
    if expected:
        require(row['exitCode'] == 1 and row['classification'] == 'EXIT_FAILURE' and report['status'] == 'FAIL'
                and report['failure']['code'] == expected and report['failure']['phase'] == 'oracle_scenario_ready', 'OMQ_EXPECTED_REJECTION')
    else:
        require(row['exitCode'] == 0 and row['classification'] == 'SUCCESS' and report['status'] == 'PASS'
                and all(check['status'] == 'PASS' for check in report['checks']), 'OMQ_HEALTHY')
    return report, row


def host_observation(archive, host, api_build, origin):
    """重开准确容器安全字段、冻结程序集、只读挂载与原 Docker 命令。"""
    from workflow_oracle_mapping_platform import HOST_FORMAT, IMAGES
    from workflow_oracle_mapping_resources import SOURCE
    inputs = archive.read('formal-api-inputs.json')
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
        require(task == TASK and run == RUN and state == 'running' and int(pid) > 0, 'OMQ_HOST_OBSERVED')
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


def audit_observation(archive, audit, row, host, origin):
    """审计重新采用已登记的窄投影 SQL 与解析器；不能把其他窗口的零计数借给当前场景。"""
    from workflow_oracle_mapping_formal_observer import audit_invocation, parse_audit
    require((audit['taskId'],audit['runId'],audit['sourceId']) == (TASK,RUN,host['oracle']['containerId'])
            and utc(audit['startUtc']) == utc(row['startedAtUtc']) and utc(audit['endUtc']) == utc(row['endedAtUtc']), 'OMQ_AUDIT_WINDOW')
    call = audit_invocation(audit['sourceId'], audit['startUtc'], audit['endUtc'], audit['clientId'])
    command,stdout,_ = archive.command(audit['commandId'],call['argv'],'omq-audit-window',call['identity'],None,origin)
    records = parse_audit(stdout)
    require(command['exitCode'] == 0 and command['classification'] == 'SUCCESS' and utc(command['startedAtUtc']) >= utc(row['endedAtUtc'])
            and records == audit['records'] and len(records) == audit['sourceAuditCount'] and digest_value(records) == audit['recordsSha256'],
            'OMQ_AUDIT_OUTPUT')
    return records


def reopen_browser(archive, entry, origin, mode, case):
    api = build_binding(archive, 'api', origin)
    tests = build_binding(archive, 'agent', origin)
    host = archive.read(entry['host'])
    report,row = browser_report(archive, entry, origin, mode, case, host, api, tests, entry['stageInputs'])
    before = host_observation(archive, host, api, origin)
    inside = host_observation(archive, report['inputBinding']['api'], api, origin)
    after = host_observation(archive, report['outputBinding']['api'], api, origin)
    require(len({h['commandId'] for h in (before,inside,after)}) == 3 and
            utc(before['endedAtUtc']) <= utc(row['startedAtUtc']) <= utc(inside['startedAtUtc']) <= utc(inside['endedAtUtc'])
            <= utc(after['startedAtUtc']) <= utc(after['endedAtUtc']) <= utc(row['endedAtUtc']), 'OMQ_HOST_WINDOW')
    records = audit_observation(archive, archive.read(entry['audit']), row, host, origin)
    if mode == READY:
        require(not records, 'OMQ_PREREQUISITE_BUSINESS_READ')
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
        cases = [(READY,case) for case in ERRORS] if gate=='interaction' else [('ui-s1','healthy'),('ui-s3','healthy')]
        for mode,case in cases:
            entry = index['cases'][mode+'-'+case]
            tests += reopen_browser(archive,entry,origin,mode,case)
    require(tests > 0, 'OMQ_ZERO_CHECKS')
    return dict(taskId=task,runId=run_id,gate=gate,inputKey=input_key,status='PASS',tests=tests,skipped=0,
                qualificationMode='FRESH',executionMode='REUSED',scope='registered affected gate evidence',originals=archive.examined)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('task','run-id','gate','input-key'):
        cli.add_argument('--'+name,required=True)
    args=cli.parse_args()
    try:
        print(json.dumps(qualify(ROOT,args.task,args.run_id,args.gate,args.input_key)))
    except (ValueError,KeyError,OSError,TypeError) as error:
        raise SystemExit('OMQ_QUALIFICATION_REJECTED '+(str(error) if isinstance(error,ValueError) else type(error).__name__))
