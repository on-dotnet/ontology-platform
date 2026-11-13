#!/usr/bin/env python3
"""Doris任务专属消费者结构准入与有界适配器测试，不冒充完整生命周期验收。"""
import argparse
import json
from pathlib import Path
import re

TASK = 'G4-M2-DORIS-01'
ROOT = Path(__file__).resolve().parents[2]


def structural(root, task):
    """核对真实DI、应用、审计和测试入口，生产guard必须保留。"""
    if task != TASK:
        raise ValueError('DORIS_TASK_INVALID')
    paths = {
        'composition': 'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs',
        'dispatch': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionSourceDispatcher.cs',
        'application': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.cs',
        'commands': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Commands.cs',
        'adapter': 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/DorisSourceAdapter.cs',
        'audit': 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs',
        'tests': 'backend/tests/OntologyPlatform.ConnectionsTests/DorisFixtureSecurityTests.cs',
    }
    texts = {}
    for key, relative in paths.items():
        path = root / relative
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('DORIS_CONSUMER_MISSING')
        texts[key] = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
    for value in ('AddSingleton<IDorisSourceAdapter, DorisSourceAdapter>', 'AddHostedService<CatalogWorker>', '!builder.Environment.IsDevelopment()'):
        if value not in texts['composition']:
            raise ValueError('DORIS_COMPOSITION_OR_GUARD_MISSING')
    for value in ('"DORIS_READONLY"', 'DorisAdapterOptions.Validate', 'doris!.ProbeAsync', 'doris!.DiscoverAsync'):
        if value not in texts['dispatch']:
            raise ValueError('DORIS_DISPATCH_MISSING')
    if 'DemandSameCredentialScope' not in texts['commands']:
        raise ValueError('DORIS_SECRET_SCOPE_GUARD_MISSING')
    for action in ('intake', 'draft-test', 'test', 'create', 'rotate', 'patch', 'enable', 'discover', 'cancel', 'disable'):
        if '"' + action + '"' not in texts['application']:
            raise ValueError('DORIS_APPLICATION_CONSUMER_MISSING')
    for action in ('connection.secret.intake', 'connection.create', 'connection.probe.start', 'connection.probe.complete', 'connection.enable', 'connection.disable', 'connection.catalog.start', 'connection.catalog.finish', 'connection.catalog.cancel'):
        if '"' + action + '"' not in texts['audit']:
            raise ValueError('DORIS_AUDIT_MISSING')
    return dict(taskId=task, status='STRUCTURAL_READY', consumers=paths,
                lifecycle='NOT_RUN', interaction='NOT_RUN', production='NOT_AUTHORIZED')


def adapter(runtime, prepared):
    """已有本任务fixture上的短测试；不创建设施、不下载、不代替应用生命周期。"""
    import workflow_execution as execution
    import workflow_m2_build as build
    structural(ROOT, TASK)
    runtime = execution.ordinary(runtime)
    base = ROOT / 'artifacts/workflow' / TASK
    if not runtime.is_relative_to(base):
        raise ValueError('DORIS_RUNTIME_OUTSIDE_TASK')
    receipt = json.loads(execution.ordinary(prepared).read_text())
    if receipt.get('taskId') != TASK or receipt.get('worktree') != str(ROOT) or receipt.get('status') != 'DEPENDENCIES_READY':
        raise ValueError('DORIS_ENVIRONMENT_BINDING')
    binding = build.validate('connections', TASK)
    env = dict(receipt['environment'], G4_DORIS_TEST_RUNTIME=str(runtime), DOTNET_GCHeapHardLimit='0x40000000')
    result = execution.run([receipt['dotnet'], str(ROOT / 'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0/OntologyPlatform.ConnectionsTests.dll'),
                            '--filter', 'FullyQualifiedName~DorisFixtureSecurityTests|FullyQualifiedName~DorisAdapterTests|FullyQualifiedName~SourceDispatcherTests',
                            '--minimum-expected-tests', '23', '--results-directory', str(base / 'adapter-results'), '--no-ansi', '--progress', 'off'],
                           ROOT, task=TASK, stage='doris-adapter', environment=env, input_key=binding['inputKey'], timeout=25)
    # 复用现行MTP资格解析器，不新建旁路摘要规则。
    from workflow_m2_evidence import mtp
    tests = mtp(result.stdout + result.stderr, 23) if result.returncode == 0 else 0
    return dict(taskId=TASK, status='ADAPTER_CHECKS_PASSED' if result.returncode == 0 else 'FAIL', exitCode=result.returncode,
                tests=tests, buildBinding=binding, executionReceipt=result.receipt,
                lifecycle='NOT_RUN', interaction='NOT_RUN', production='NOT_AUTHORIZED')



def main():
    """每个入口明确声明验证层级，不返回全任务PASS。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'adapter', 'lifecycle'))
    parser.add_argument('--task', required=True, choices=(TASK,))
    parser.add_argument('--runtime')
    parser.add_argument('--prepared')
    args = parser.parse_args()
    try:
        if args.action in ('adapter', 'lifecycle') and (not args.runtime or not args.prepared):
            raise ValueError('DORIS_RUNTIME_AND_PREPARED_REQUIRED')
        if args.action == 'lifecycle':
            from workflow_doris_fixture import run
            result = run(args.prepared, args.runtime, ROOT / 'scripts/maintenance/workflow-doris.mjs')
        else:
            result = structural(ROOT, args.task) if args.action == 'preflight' else adapter(args.runtime, args.prepared)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['status'] in ('STRUCTURAL_READY', 'ADAPTER_CHECKS_PASSED', 'LIFECYCLE_CHECKS_PASSED') else 2
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps(dict(status='FAIL', reason=str(error))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
