#!/usr/bin/env python3
"""G4-M2-WEB-01专属消费者结构准入；结构READY绝非产品PASS。"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

TASK='G4-M2-WEB-01'
ROOT=Path(__file__).resolve().parents[2]


def require(value,code):
    if not value:raise ValueError('M2_ADMISSION_BLOCKED: '+code)


def structural(root,task):
    """绑定已存在应用/HTTP/审计/测试消费者，不冒用G3 M2或M1验收。"""
    require(task==TASK,'TASK_ID')
    relative={
        'routes':'backend/src/Hosts/OntologyPlatform.Api/G4/G4Endpoints.cs',
        'composition':'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs',
        'application':'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.cs',
        'audit':'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs',
        'contracts':'backend/tests/OntologyPlatform.G2ContractTests/G4WireContractTests.cs',
        'pgRegression':'backend/tests/OntologyPlatform.ConnectionsTests/PgAdapterTests.cs',
        'rejectionTests':'scripts/tests/WorkflowM2Web.Tests.py',
    }
    texts={}
    for key,name in relative.items():
        path=root/name
        require(path.is_file() and not any(p.is_symlink() for p in [path,*path.parents]),'CONSUMER_MISSING')
        texts[key]=re.sub(r'/\*.*?\*/|//[^\n]*','',path.read_text(),flags=re.S)
    require(len(re.findall(r'app\.Map(?:Get|Post|Patch)\(',texts['routes']))==16,'ROUTE_COUNT')
    require('AddScoped<ConnectionApplicationService>' in texts['composition'] and 'AddHostedService<CatalogWorker>' in texts['composition'],'DI_MISSING')
    for action in ('connection.secret.intake','connection.create','connection.probe.start','connection.probe.complete','connection.enable','connection.disable','connection.catalog.start','connection.catalog.finish','connection.catalog.cancel'):
        require('"'+action+'"' in texts['audit'],'AUDIT_MISSING')
    for action in ('intake','draft-test','test','create','rotate','patch','enable','discover','cancel','disable'):
        require('"'+action+'"' in texts['application'],'APPLICATION_CONSUMER_MISSING')
    return dict(taskId=task,status='STRUCTURAL_READY',consumers=relative,
                productSmoke='NOT_RUN',webImplementation='NOT_VERIFIED',
                limitation='仅结构准入；新Web运行测试、构建绑定、源设施及真实OIDC/UI烟测仍必须完成。')


def host(root,task):
    """不修改旧CLI的授权名单，复用现有只读宿主策略函数。"""
    require(task==TASK,'TASK_ID')
    spec=importlib.util.spec_from_file_location('host_continuity',root/'scripts/maintenance/host_continuity.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.inspect(task_id=task)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','host-preflight','fixture-test','pg-regression','smoke'])
    parser.add_argument('--task',required=True)
    args=parser.parse_args()
    try:
        if args.action in ('fixture-test','pg-regression','smoke'):
            structural(ROOT,args.task)
            require(host(ROOT,args.task).get('assurance')=='POLICY_READY','HOST_POLICY')
            if args.action=='fixture-test':
                from workflow_m2_fixture import run
                result=run(args.task)
            elif args.action=='pg-regression':
                from workflow_m2_fixture import pg_regression
                result=pg_regression(args.task)
            else:
                from workflow_m2_smoke import run
                import workflow_environment as environment
                import shutil
                result=run(args.task,shutil.which('node'))
        else:result=structural(ROOT,args.task) if args.action=='preflight' else host(ROOT,args.task)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('status') in ('STRUCTURAL_READY','PASS') or result.get('assurance')=='POLICY_READY' else 2
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps(dict(status='BLOCKED',reason=str(error))));return 2

if __name__=='__main__':raise SystemExit(main())
