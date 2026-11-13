#!/usr/bin/env python3
"""Oracle任务专属消费者结构准入与有界适配器测试，不冒充完整生命周期验收。"""
import argparse
import json
from pathlib import Path
import re

TASK = 'G4-M2-ORACLE-01'
ROOT = Path(__file__).resolve().parents[2]


def structural(root, task):
    """核对真实DI、应用、审计和测试入口，生产guard必须保留。"""
    if task != TASK:
        raise ValueError('ORACLE_TASK_INVALID')
    paths = {
        'composition': 'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs',
        'dispatch': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionSourceDispatcher.cs',
        'application': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.cs',
        'commands': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Commands.cs',
        'adapter': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/OracleSourceAdapter.cs',
        'audit': 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs',
        'tests': 'backend/tests/OntologyPlatform.ConnectionsTests/OracleAdapterTests.cs',
    }
    texts = {}
    for key, relative in paths.items():
        path = root / relative
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('ORACLE_CONSUMER_MISSING')
        texts[key] = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
    for value in ('AddSingleton<IOracleSourceAdapter, OracleSourceAdapter>', 'AddHostedService<CatalogWorker>', '!builder.Environment.IsDevelopment()'):
        if value not in texts['composition']:
            raise ValueError('ORACLE_COMPOSITION_OR_GUARD_MISSING')
    for value in ('"ORACLE_READONLY"', 'OracleAdapterOptions.Validate', 'oracle!.ProbeAsync', 'oracle!.DiscoverAsync'):
        if value not in texts['dispatch']:
            raise ValueError('ORACLE_DISPATCH_MISSING')
    if 'DemandSameCredentialScope' not in texts['commands']:
        raise ValueError('ORACLE_SECRET_SCOPE_GUARD_MISSING')
    for action in ('intake', 'draft-test', 'test', 'create', 'rotate', 'patch', 'enable', 'discover', 'cancel', 'disable'):
        if '"' + action + '"' not in texts['application']:
            raise ValueError('ORACLE_APPLICATION_CONSUMER_MISSING')
    for action in ('connection.secret.intake', 'connection.create', 'connection.probe.start', 'connection.probe.complete', 'connection.enable', 'connection.disable', 'connection.catalog.start', 'connection.catalog.finish', 'connection.catalog.cancel'):
        if '"' + action + '"' not in texts['audit']:
            raise ValueError('ORACLE_AUDIT_MISSING')
    return dict(taskId=task, status='STRUCTURAL_READY', consumers=paths,
                lifecycle='NOT_RUN', interaction='NOT_RUN', production='NOT_AUTHORIZED')


def lifecycle(runtime_path, prepared_path, output_path):
    """消费已隔离运行的本任务服务；没有准备入口就拒绝，不隐式创建或下载。"""
    import hashlib
    import workflow_execution as execution
    import workflow_m2_build as build
    from workflow_oracle_fixture import control
    runtime_path = execution.ordinary(runtime_path)
    prepared_path = execution.ordinary(prepared_path)
    output_path = execution.ordinary(output_path)
    if not runtime_path.is_relative_to(ROOT / '.tools/security/g4-m2-oracle-01') or not prepared_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK) or not output_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK):
        raise ValueError('ORACLE_EXECUTION_PATH')
    runtime = json.loads(runtime_path.read_text())
    prepared = json.loads(prepared_path.read_text())
    if runtime.get('taskId') != TASK or prepared.get('taskId') != TASK or runtime.get('worktree') != str(ROOT) or prepared.get('worktree') != str(ROOT):
        raise ValueError('ORACLE_EXECUTION_IDENTITY')
    if output_path.exists():
        raise ValueError('ORACLE_EVIDENCE_EXISTS')
    structural(ROOT, TASK)
    control(runtime['oracleSourceRecord'], 'active-reader')
    import time
    import urllib.request
    if runtime.get('publicOrigin') != 'http://localhost:15100':
        raise ValueError('ORACLE_ORIGIN')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(30):
        try:
            with opener.open(urllib.request.Request(runtime['publicOrigin'] + '/health/live', headers={'X-Health-Key': runtime['healthKey']}), timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(.2)
    else:
        raise ValueError('ORACLE_API_NOT_READY')
    bindings = {target: build.validate(target, TASK) for target in ('api', 'web')}
    inputs = dict(bindings=bindings, drivers=build.driver_inputs(), compose={str(path.relative_to(ROOT)): build.sha(path.read_bytes()) for path in sorted((ROOT / 'infra/oracle').glob('*.yaml'))})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = execution.sha(execution.encoded(inputs))
    with output_path.with_suffix('.inputs.json').open('x') as stream:
        stream.write(json.dumps(dict(inputs=inputs, inputFingerprint=fingerprint), indent=2) + '\n')
    result = execution.run([prepared['node'], str(ROOT / 'scripts/maintenance/workflow-oracle.mjs'), str(runtime_path)], ROOT, task=TASK, run_id=runtime['runId'], stage='oracle-lifecycle', timeout=240, input_key=fingerprint)
    report = json.loads(result.stdout)
    if result.returncode != 0 or report.get('status') != 'PASS' or report.get('taskId') != TASK or report.get('skipped') != 0:
        raise ValueError('ORACLE_LIFECYCLE_FAILED')
    if bindings != {target: build.validate(target, TASK) for target in bindings} or inputs['drivers'] != build.driver_inputs():
        raise ValueError('ORACLE_EXECUTION_DRIFT')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_suffix('.stdout.json')
    with raw_path.open('xb') as stream:
        stream.write(result.stdout)
    value = dict(taskId=TASK, runId=runtime['runId'], status='LIFECYCLE_CHECKS_PASSED', exitCode=result.returncode, browserExecution=result.receipt, buildBindings=bindings, inputs=inputs, stdout=raw_path.name, stdoutSha256=hashlib.sha256(result.stdout).hexdigest(), report=report, retainedServices='KEEP_FOR_SAME_TASK_REVIEW', cleanupComplete=False)
    with output_path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    return dict(taskId=TASK, status=value['status'], tests=report['tests'], cleanupComplete=False)


def adapter_tests(source_path, runtime_path, output_path):
    """已有源上的五项真实适配器验证，准确记录构建、退出码和临时容器清理。"""
    import os
    import subprocess
    import workflow_execution as execution
    import workflow_m2_build as build
    from workflow_oracle_fixture import load_source, control
    source_path = execution.ordinary(source_path)
    runtime_path = execution.ordinary(runtime_path)
    output_path = execution.ordinary(output_path)
    if not runtime_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK) or not output_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK) or output_path.exists():
        raise ValueError('ORACLE_ADAPTER_PATH')
    source = load_source(source_path)
    control(source_path, 'active-reader')
    runtime = json.loads(runtime_path.read_text())
    if runtime.get('taskId') != TASK or runtime.get('rootCertificatePath') != '/run/fixture/ca.pem' or runtime.get('walletDirectory') != '/run/fixture/client-wallet' or runtime.get('secretFile') != '/run/fixture/reader-password':
        raise ValueError('ORACLE_ADAPTER_RUNTIME')
    docker = ['docker', '--context', 'desktop-linux']
    running = subprocess.check_output(docker + ['ps', '-q', '--filter', 'label=ontology.task=' + TASK], timeout=5).decode().split()
    rows = json.loads(subprocess.check_output(docker + ['inspect', *running], timeout=5)) if running else []
    if any(row['HostConfig']['Memory'] <= 0 or row['HostConfig']['NanoCpus'] <= 0 for row in rows) or sum(row['HostConfig']['Memory'] for row in rows) + 512 * 1024**2 > 6 * 1024**3 or sum(row['HostConfig']['NanoCpus'] for row in rows) + 500_000_000 > 4_000_000_000:
        raise ValueError('ORACLE_TEST_BUDGET')
    binding = build.validate('connections', TASK)
    record = dict(taskId=TASK, runId=source['runId'], buildBinding=binding, stage='BEFORE_CREATE', cleanupComplete=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output_path.write_text(json.dumps(record, indent=2) + '\n')
    save()
    args = docker + ['create', '--pull=never', '--read-only', '--network', next(iter(source['networks'])), '--user', str(os.getuid()), '--memory=512m', '--memory-swap=512m', '--cpus=0.5', '--pids-limit=128', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--tmpfs', '/tmp:rw,nosuid,nodev,size=134217728', '--label=ontology.task=' + TASK, '--label=ontology.run=' + source['runId'], '--mount', 'type=bind,src=' + str(ROOT / 'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0') + ',dst=/app,readonly', '--mount', 'type=bind,src=' + str(runtime_path.parent) + ',dst=/run/fixture,readonly', '--env', 'G4_ORACLE_TEST_RUNTIME=/run/fixture/runtime.json', '--env', 'XDG_DATA_HOME=/tmp/data', '--env', 'TESTINGPLATFORM_TELEMETRY_OPTOUT=1', '--env', 'DOTNET_CLI_TELEMETRY_OPTOUT=1', '--ulimit', 'core=0', '--workdir', '/tmp', '--entrypoint', 'dotnet', 'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55', '/app/OntologyPlatform.ConnectionsTests.dll', '--filter', 'FullyQualifiedName~OracleFixtureSecurityTests', '--minimum-expected-tests', '5', '--results-directory', '/tmp/test-results', '--no-ansi', '--progress', 'off']
    ident = subprocess.check_output(args, timeout=20).decode().strip()
    record['containerId'] = ident
    save()
    try:
        result = execution.run(docker + ['start', '-a', ident], ROOT, task=TASK, run_id=source['runId'], stage='oracle-real-adapter', timeout=45, input_key=execution.sha(execution.encoded(binding)))
        record['execution'] = result.receipt
        state = json.loads(subprocess.check_output(docker + ['inspect', ident], timeout=5))[0]['State']
        record['actualExitCode'] = state['ExitCode']
        record['testPassed'] = result.returncode == state['ExitCode'] == 0 and not state['Running']
        record['inputUnchanged'] = build.validate('connections', TASK) == binding
        record['log'] = output_path.with_suffix('.log').name
        output_path.with_suffix('.log').write_bytes(result.stdout + result.stderr)
    finally:
        row = json.loads(subprocess.check_output(docker + ['inspect', ident], timeout=5))[0]
        record['beforeCleanup'] = row['State']['Status']
        if row['State']['Running']:
            subprocess.run(docker + ['stop', '--timeout', '5', ident], check=True, capture_output=True, timeout=10)
        subprocess.run(docker + ['rm', ident], check=True, capture_output=True, timeout=10)
        absent = subprocess.run(docker + ['inspect', ident], capture_output=True, timeout=5)
        record['cleanupComplete'] = absent.returncode == 1 and b'no such' in absent.stderr.lower()
        record['stage'] = 'PASS' if record.get('testPassed') and record.get('inputUnchanged') and record['cleanupComplete'] else 'FAIL'
        save()
    if record['stage'] != 'PASS':
        raise ValueError('ORACLE_ADAPTER_FAILED')
    return dict(taskId=TASK, status='PASS', cleanupComplete=True, tests=5)


def local_tests(target, prepared_path, output_path):
    """当前构建绑定的受影响合同、共享单元或Web组件测试，不启动源服务。"""
    import workflow_execution as execution
    import workflow_m2_build as build
    if target not in ('wire', 'connections', 'web'):
        raise ValueError('ORACLE_LOCAL_TARGET')
    output_path = execution.ordinary(output_path)
    prepared_path = execution.ordinary(prepared_path)
    if output_path.exists() or not output_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK) or not prepared_path.is_relative_to(ROOT / 'artifacts/workflow' / TASK):
        raise ValueError('ORACLE_LOCAL_PATH')
    prepared = json.loads(prepared_path.read_text())
    if prepared.get('taskId') != TASK or prepared.get('worktree') != str(ROOT):
        raise ValueError('ORACLE_LOCAL_IDENTITY')
    binding = build.validate(target, TASK)
    env = dict(prepared['environment'])
    cwd = ROOT
    if target == 'web':
        cwd = ROOT / 'apps/web'
        env['G4_TEST_TASK'] = TASK
        args = [prepared['node'], 'node_modules/vitest/vitest.mjs', 'run', 'src/features/connections/connections.test.ts']
    else:
        assembly = 'OntologyPlatform.G2ContractTests' if target == 'wire' else 'OntologyPlatform.ConnectionsTests'
        filter_value = 'FullyQualifiedName~G4WireContractTests' if target == 'wire' else 'TestCategory!~Real&TestCategory!~DorisFixture&TestCategory!~DorisExpiredCertificate'
        args = [prepared['dotnet'], str(ROOT / 'backend/tests' / assembly / 'bin/Debug/net10.0' / (assembly + '.dll')), '--filter', filter_value, '--minimum-expected-tests', '19' if target == 'wire' else '46', '--results-directory', str(output_path.with_suffix('')), '--no-ansi', '--progress', 'off']
    result = execution.run(['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)', *args], cwd, task=TASK, stage='oracle-local-' + target, environment=env, timeout=60, input_key=execution.sha(execution.encoded(binding)))
    value = dict(taskId=TASK, target=target, exitCode=result.returncode, buildBinding=binding, inputUnchanged=build.validate(target, TASK) == binding, execution=result.receipt, log=output_path.with_suffix('.log').name)
    output_path.with_suffix('.log').write_bytes(result.stdout + result.stderr)
    with output_path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    if result.returncode != 0 or not value['inputUnchanged']:
        raise ValueError('ORACLE_LOCAL_TEST_FAILED')
    return dict(taskId=TASK, target=target, status='PASS')


def main():
    """结构通过不等于实际运行通过，尚未完成的产品门禁保持NOT_RUN。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'lifecycle', 'adapter-tests', 'local-tests'))
    parser.add_argument('--task', required=True, choices=(TASK,))
    parser.add_argument('--target')
    parser.add_argument('--source')
    parser.add_argument('--runtime')
    parser.add_argument('--prepared')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        if args.action == 'preflight':
            value = structural(ROOT, args.task)
        elif args.action == 'lifecycle':
            value = lifecycle(args.runtime, args.prepared, args.output)
        elif args.action == 'local-tests':
            value = local_tests(args.target, args.prepared, args.output)
        else:
            value = adapter_tests(args.source, args.runtime, args.output)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps(dict(status='FAIL', reason=str(error))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
