"""G4-M1准确派发/运行消费者前置检查，不将合同检查冒充产品验收。"""
from pathlib import Path
import re

CONTRACT_PATHS = (
    'docs/tasks/G4-M1-CONNECTION-001.md', 'docs/contracts/g4-m1-connections.md',
    'backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs',
    'backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionRules.cs',
    'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/IPgSourceAdapter.cs',
    'backend/tests/OntologyPlatform.G2ContractTests/G4WireContractTests.cs',
    'docs/evidence/G4-M1-CONNECTION-001/p1-review.md')
ACTIONS = ('secret.intake', 'create', 'update', 'secret.rotate', 'probe.start', 'probe.complete',
           'enable', 'disable', 'catalog.start', 'catalog.finish', 'catalog.cancel')


def check(root, phase, source_path, check_cli):
    """派发只查冻结输入；真实长入口必须另验runtime阶段所有消费者。"""
    checked = []
    for relative in CONTRACT_PATHS:
        path = source_path(root, relative)
        if not path.is_file():
            raise ValueError('G4_CONTRACT_MISSING: 冻结输入缺失')
        checked.append(relative)
    review = (Path(root)/CONTRACT_PATHS[-1]).read_text()
    if 'P1_CONTRACT_REVIEW_PASS' not in review:
        raise ValueError('G4_REVIEW_REQUIRED: 非作者合同未通过')
    if phase == 'runtime':
        audit = source_path(root, 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs').read_text()
        block = re.search(r'\bActions\s*=\s*new\([^;]*?\)\s*\{(.*?)\};', audit, re.S)
        if not block or any('"connection.'+action+'"' not in block[1] for action in ACTIONS):
            raise ValueError('G4_AUDIT_MISSING: 真实G4审计白名单遗漏')
        composition = source_path(root, 'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs').read_text()
        if any(name not in composition for name in ('ConnectionApplicationService','IPgSourceAdapter','ConnectionsDbContext','CatalogWorker')):
            raise ValueError('G4_DI_MISSING: G4组合入口不完整')
        runtime = source_path(root, 'scripts/acceptance/g4-m1-runtime.py')
        check_cli(['python3',str(runtime)], ['--runtime-file','--mode'])
        for relative in ('scripts/acceptance/g4-m1-browser.mjs','experiments/g4-m1/compose.m1.yaml'):
            source_path(root, relative)
            checked.append(relative)
    return dict(status='PASS', milestone='G4-M1', phase=phase, checkedPaths=checked,
                productRuntime='NOT_RUN', limitation='仅实际路径/合同或消费者检查；不得代替真实PG/OIDC/浏览器。')
