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
    require(task in (TASK,'G4-ENG-DELIVERY-002'),'TASK_ID')
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
    require(task in (TASK,'G4-ENG-DELIVERY-002'),'TASK_ID')
    spec=importlib.util.spec_from_file_location('host_continuity',root/'scripts/maintenance/host_continuity.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.inspect(task_id=task)


def environment_identity(task):
    """只读探针绑定真实 Engine/context、已批准镜像及工具内容，不拉取。"""
    import workflow_execution as execution
    import workflow_m2_fixture as fixture
    import workflow_smoke as shared
    import shutil
    tools={}
    for name in ('docker','python3'):
        path=Path(shutil.which(name)).resolve();tools[name]=execution.sha(path.read_bytes())
    def probe(args):
        result=execution.run(args,ROOT,task=task,stage='environment-probe',timeout=20,diagnostic=True)
        require(result.returncode==0,'ENVIRONMENT_PROBE_FAILED')
        return json.loads(result.stdout)
    info=probe(['docker','--context',shared.CONTEXT,'info','--format','{{json .}}'])
    images={}
    for image in sorted(set([fixture.NODE,fixture.DOTNET,*shared.IMAGES.values()])):
        row=probe(['docker','--context',shared.CONTEXT,'image','inspect',image])[0]
        images[image]={'id':row['Id'],'os':row['Os'],'architecture':row['Architecture']}
    return dict(platform=__import__('platform').platform(),tools=tools,engine=info['ID'],version=info['ServerVersion'],context=shared.CONTEXT,images=images)


def execute(action,task):
    """一般工程与 M2 使用同一操作/子命令协议；工程身份与产品准入身份分列。"""
    import workflow_execution as execution
    import workflow_m2_build as build
    structural(ROOT,task)
    require(host(ROOT,task).get('assurance')=='POLICY_READY','HOST_POLICY')
    key=execution.sha(execution.encoded(dict(product=build.inputs('connections'),drivers={p:h for p,h in build.driver_inputs().items() if build.driver_layers()[p]=='execution'},admission=TASK)))
    env=execution.sha(execution.encoded(environment_identity(task)))
    with execution.operation(ROOT,task,action,key,env):
        if action=='fixture-test':
            from workflow_m2_fixture import run
            result=run(task)
        elif action=='pg-regression':
            from workflow_m2_fixture import pg_regression
            result=pg_regression(task)
        else:
            from workflow_m2_smoke import run
            result=run(task,__import__('shutil').which('node'))
        require(result.get('status')=='PASS','EXECUTION_FAILED')
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','host-preflight','fixture-test','pg-regression','smoke'])
    parser.add_argument('--task',required=True)
    args=parser.parse_args()
    try:
        if args.action in ('fixture-test','pg-regression','smoke'):result=execute(args.action,args.task)
        else:result=structural(ROOT,args.task) if args.action=='preflight' else host(ROOT,args.task)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('status') in ('STRUCTURAL_READY','PASS') or result.get('assurance')=='POLICY_READY' else 2
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps(dict(status='BLOCKED',reason=str(error))));return 2

if __name__=='__main__':raise SystemExit(main())
