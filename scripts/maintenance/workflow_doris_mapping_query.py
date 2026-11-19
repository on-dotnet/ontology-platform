"""Doris 合成设施的固定建表输入与独立参考预期，供后续正式消费者使用。"""
from datetime import datetime, timezone


def s0_consumers(root, task, phase):
    """只核验本轮 S0 的实际执行器和定向消费者；后续运行阶段单独准入。"""
    from execution_preflight import source_path
    from workflow_m2_doris import source_consumers
    if task != 'G4-DORIS-MAPPING-QUERY-001' or phase not in ('source','runtime'):
        raise ValueError('DMQ_ONLY_S0_SOURCE_REGISTERED')
    paths = source_consumers(root)
    directory = 'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/'
    for relative, terms in (
        (directory+'DorisSourceAdapter.cs', ['ReadBranchAsync<T>', 'DorisReadSession.ReadAsync']),
        (directory+'DorisReadSession.cs', ['connection.ServerThread', 'KILL CONNECTION ', 'armed.ExecuteNonQueryAsync']),
        (directory+'DorisQueryReader.cs', ['FROM fixture.dmq_entity','FROM fixture.dmq_target','LIMIT 101','adapter.ReadBranchAsync']),
        (directory+'DorisMappingSourceValidator.cs', ['SHOW CREATE TABLE fixture.', 'RequireShape','enable_unique_key_merge_on_write']),
        ('backend/tests/OntologyPlatform.ConnectionsTests/DorisMappingQueryTests.cs',
         ['ReadBranchAsync', 'RealDriverReadsFixedSource', 'ActiveBackendMustFinishInsideOriginalWindow', 'backend_active_tasks',
          'FixedEntityCancellation','FixedTargetCancellation','ACTIVE_CANCELLATION_PRECONDITION_NOT_OBSERVED',
          'ControlledWriteBetweenSourceReads','FixedTargetRejectsUnsupportedShape'])):
        source = source_path(root,relative).read_text()
        if any(term not in source for term in terms):
            raise ValueError('DMQ_S0_CONSUMER_MISSING')
        paths[relative.split('/')[-1]] = relative
    if phase=='runtime':
        import json
        assurance = json.loads((root/'docs/evidence'/task/'implementation-01/s0-qualified-review.json').read_bytes())
        if assurance['status']!='S0_GO' or assurance['reviewDecision']!='GO_S1': raise ValueError('DMQ_S0_NOT_QUALIFIED')
        for name,path,terms in [
            ('mapping','backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingValidationService.cs',
             ['DorisMappingSourceValidator.ObserveAsync','CaptureSourceAsync','mapping_authorization_stale']),
            ('query','backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/QueryBindingReader.cs',
             ['DorisQueryReader.ReadEntityAsync','authority.CaptureAsync','DemandSameVersion']),
            ('composition',paths['composition'],['AddScoped<QueryBindingReader>','AddSingleton<IDorisSourceAdapter, DorisSourceAdapter>','MappingValidationService']),
            ('store','backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryResultStore.cs',['BindReceipts','SaveChangesAsync'])]:
            source=source_path(root,path).read_text()
            if any(term not in source for term in terms):raise ValueError('DMQ_S1_CONSUMER_MISSING_'+name)
            paths[name]=path
        return dict(taskId=task,phase='S1',status='STRUCTURAL_READY',consumers=paths,productLifecycle='NOT_RUN')
    return dict(taskId=task, phase='S0', status='STRUCTURAL_READY', consumers=paths,
                sourceCancellation='NOT_VERIFIED', productLifecycle='NOT_RUN')


# 两张表是同一目录输入，调用者必须完成全部建表和探针复位后才发正式 Discover。
def fixture_tables():
    """返回任务专用两表的 DDL；产品只读账号不参与执行。"""
    tables = []
    for name, identity, extra in (
        ('dmq_entity', 'entity_id', 'join_key DECIMAL(10,2) NULL, amount DECIMAL(20,2) NULL, unit_code VARCHAR(8) NOT NULL'),
        ('dmq_target', 'target_id', 'join_key DECIMAL(12,3) NULL'),
    ):
        tables.append(f'''CREATE TABLE fixture.{name} (
  org_id VARCHAR(32) NOT NULL, site_id VARCHAR(16) NOT NULL, {identity} VARCHAR(32) NOT NULL,
  {extra},
  valid_from DATETIMEV2(6) NOT NULL, valid_to DATETIMEV2(6) NOT NULL,
  event_at DATETIMEV2(6) NOT NULL, observed_at DATETIMEV2(6) NOT NULL
) UNIQUE KEY(org_id, site_id, {identity})
DISTRIBUTED BY HASH({identity}) BUCKETS 1
PROPERTIES ("replication_num"="1", "enable_unique_key_merge_on_write"="true")''')
    return tuple(tables)


REFERENCE_SQL = """SELECT t.target_id
FROM fixture.dmq_entity e JOIN fixture.dmq_target t
ON e.org_id=t.org_id AND e.site_id=t.site_id AND e.join_key=t.join_key
AND e.valid_from<t.valid_to AND t.valid_from<e.valid_to
WHERE e.org_id='org-demo' AND e.site_id='site-a' AND e.entity_id='E1'
ORDER BY t.target_id"""


def reference_targets(entity, targets):
    """对独立夹具元组按范围、精确数值和半开区间计算预期；不读产品输出。"""
    def coefficient(text):
        integer,_,fraction=text.partition('.')
        return int(integer+fraction), len(fraction)
    def equal(left,right):
        a,s=coefficient(left)
        b,t=coefficient(right)
        return a*10**t==b*10**s
    org, site, key, start, end = entity
    return sorted(identity for identity, target_org, target_site, target_key, first, last in targets
                  if (org, site) == (target_org, target_site) and key is not None and target_key is not None
                  and equal(key, target_key) and start < last and first < end)


def fixture_instant(local):
    """仅对夹具已明确登记的 Etc/UTC 无时区六位微秒值生成参考 UTC 词法。"""
    parsed = datetime.strptime(local, '%Y-%m-%d %H:%M:%S.%f')
    if parsed.strftime('%Y-%m-%d %H:%M:%S.%f') != local:
        raise ValueError('FIXTURE_DATETIMEV2_PRECISION')
    return parsed.replace(tzinfo=timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


BROWSER_SOURCES=tuple('scripts/maintenance/'+name for name in (
    'workflow_doris_s1.py','workflow-m4-query.mjs','workflow_doris_s0_fixture.py','workflow_doris_mapping_query.py',
    'doris_query_cancel_witness.py','doris_pipeline_observer.py','doris_query_profile_witness.py','doris_semantic_deadline_witness.py',
    'workflow_m5_integration.py','workflow_m4_query.py','workflow_doris_vm.py','workflow_m4_query_runtime.py'))
