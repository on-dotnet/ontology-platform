"""Oracle Mapping/Query 独立任务的准备与阶段前提。旧 M2 仍沿原入口。"""
import re
import subprocess

from execution_preflight import source_path
from workflow_environment import ORACLE_ARCHIVES, digest, materialize, ordinary
from workflow_oracle_mapping_resources import TASK, before_source, require


def structural(root, task, phase):
    """绑定本阶段实际 DI、调度、审计与运行脚本；静态前提不签发产品证据。"""
    require(task == TASK, 'TASK')
    shared = 'backend/src/Modules/'
    connections = shared+'Connections/OntologyPlatform.Modules.Connections/'
    query = shared+'SemanticQuery/OntologyPlatform.Modules.SemanticQuery/'
    consumers = {
        'backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs': ['AddSingleton<IOracleSourceAdapter, OracleSourceAdapter>', 'AddScoped<IG4SourceQueryReader>'],
        connections+'Application/ConnectionSourceDispatcher.cs': ['"ORACLE_READONLY"', 'oracle!.DiscoverAsync'],
        shared+'Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs': ['"connection.catalog.finish"', '"data.query.execute"', '"data.query.cancel"'],
        'backend/src/Hosts/OntologyPlatform.Api/G4/QueryEndpoints.cs': ['MapPost("/api/v1/data/semantic-queries/{queryId}/cancel"', 'G2EndpointGuard.TransportAsync'],
        query+'SemanticQueryModule.cs': ['AddHostedService<G4QueryWorker>'],
        query+'G4QueryResultStore.cs': ['CancelAsync(', 'AdmitAsync('],
        'scripts/maintenance/workflow_environment.py': ['prepare_inputs(root, task, approved)', 'verify_assets(root,home,projects,packages,approved)'],
    }
    if phase != 'contract':
        consumers[connections+'Adapters/OracleSourceAdapter.Mapping.cs'] = ['SET TRANSACTION READ ONLY', 'BeginTransactionAsync(']
        consumers['infra/oracle/config/mapping-query.sql'] = ['"PRODUCTION"."OMQ_ENTITY"', '"CaseOwner"."OmqTarget"']
    if phase in ('persistence', 'runtime'):
        consumers[query+'G4QueryResultStore.cs'].append('ConfirmOracleCleanupAsync(')
    require(phase in ('contract','source','persistence','runtime'), 'PHASE')
    binding = {}
    for path, tokens in consumers.items():
        data = source_path(root,path).read_bytes()
        code = re.sub(r'/\*.*?\*/|//[^\n]*','',data.decode(),flags=re.S)
        require(all(token in code for token in tokens), 'CONSUMER_MISSING_'+path)
        binding[path] = digest(data)
    return dict(taskId=task,phase=phase,status='STRUCTURAL_READY',consumers=binding,product='NOT_RUN')


def prepare_inputs(root, task, approved):
    """核当期资源后，从准确同仓任务的公共制品缓存绑定锁定包。"""
    structural(root, task, 'contract')
    before_source(root,task)
    source_branch = 'refs/heads/codex/g4-m2-oracle-01'
    listing = subprocess.check_output(['git','worktree','list','--porcelain','-z'], cwd=root).decode()
    candidates = []
    for block in listing.strip('\0').split('\0\0'):
        fields = dict(line.split(' ', 1) for line in block.split('\0') if ' ' in line)
        if fields.get('branch') == source_branch:
            candidates.append(ordinary(fields['worktree']))
    require(len(candidates) == 1, 'PUBLIC_ARCHIVE_SOURCE')
    source = candidates[0]/'artifacts/workflow/G4-M2-ORACLE-01/artifact-cache'
    target = root/'artifacts/workflow'/task/'artifact-cache'
    for key in sorted(set(ORACLE_ARCHIVES) | {'mysqlconnector/2.6.2'}):
        name, version = key.split('/')
        filename = name+'.'+version+'.nupkg'
        destination = ordinary(target/filename)
        archive = destination if destination.is_file() else ordinary(source/filename)
        require(archive.is_file(), 'PUBLIC_ARCHIVE_MISSING_'+key)
        data = archive.read_bytes()
        require(digest(data) == approved[key]['archiveSha256'], 'PUBLIC_ARCHIVE_DRIFT_'+key)
        materialize(destination, data)
