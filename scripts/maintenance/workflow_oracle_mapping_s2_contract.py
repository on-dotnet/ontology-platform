"""Oracle S2/S3 的独立字面量预期；正式实时检查与原件重开共享此消费者。"""
import base64
import hashlib
import json
from workflow_oracle_mapping_resources import require

CAPABILITIES=('g4_resolve_entity','g4_read_observations','g4_traverse_relationships')
FROM='2026-01-01T00:00:00.000001Z'
TO='2026-02-01T00:00:00.000001Z'
ROOT_IRI='urn:ontology-platform:entity:094db4805030e6f0f5038180c180302762dc9eeb602ec313fb6f92642a44231e'
TARGET_IRI='urn:ontology-platform:entity:a8eebe02d606d917e21553b0a428294f990103f7e4c1d4726f69d20f7386d107'
RELATION='urn:synthetic:mapping:hasReading'
# 状态来自固定语义合同和独立字面量，不由被测返回生成。
RELATIONS={
 'near':('FOUND',0,None), 'negative':('FOUND',1,None),
 'null-parent':('FOUND',0,'mapping_relation_endpoint_unknown'), 'null-target':('FOUND',0,'mapping_relation_endpoint_unknown'),
 'touch':('FOUND',0,None), 'micro-overlap':('FOUND',1,None),
 'duplicate-target':('PARTIAL',0,'mapping_identity_overlap'), 'multiple-parents':('PARTIAL',0,'mapping_cardinality_conflict'),
 'fanout-10':('FOUND',10,None), 'fanout-11':('PARTIAL',0,'mapping_fanout_exceeded')}


def time_value(value):return dict(kind='UTC',lexical=value,fractionalDigits=6)

def require_root(root):
    interval={'from':time_value(FROM),'to':time_value(TO)}
    require(root['kind']=='entity' and root['entityIri']==ROOT_IRI and root['identity']==dict(organizationId='org-demo',siteId='site-a',
        sourceNamespace='query-fixture-v1',externalId='omq-entity-1',effectiveTime=interval) and root['validTime']==interval
        and root['typeIris']==['urn:synthetic:mapping:Asset'] and root['label'] is None,'S23_ROOT_IDENTITY')
    require(len(root['properties'])==1,'S23_ROOT_PROPERTIES')
    prop=root['properties'][0]
    require(prop['propertyIri']=='urn:synthetic:mapping:label' and prop['unit'] is None and prop['value']==dict(type='string',lexical='entity')
            and prop['eventTime']==time_value('2026-01-02T00:00:00.123456Z'),'S23_ROOT_VALUE')


def result_case(row,state):
    raw=row['raw'];data=json.loads(raw);name=row['name'];query=row['query']
    require(row['sha256']==hashlib.sha256(raw.encode()).hexdigest() and row['bytes']==len(raw.encode()) and row['httpStatus']==200,'S23_RESULT_BYTES')
    require(data['schemaVersion']=='g4.query-result.v1' and query['timeoutMs']==5000 and query['maxRows']==100 and query['depth']==1
            and query['capabilityId'] in CAPABILITIES and query['mappingReleaseIds']==[state['mappingReleaseId']],'S23_RESULT_QUERY')
    expected='FOUND';edges=None;candidates=0
    if name in RELATIONS:expected,edges,_=RELATIONS[name]
    elif name in ('missing','nano-before','nano-after'):expected='EMPTY'
    elif name in ('ambiguous','aba-selection-origin','normal-100-all'):expected='AMBIGUOUS';candidates=100 if name=='normal-100-all' else 2
    elif name in ('sentinel-101','source-acl'):expected='UNAVAILABLE'
    elif name in ('no-grant','revoke-execute','field-execute','expired-execute'):expected='UNAUTHORIZED'
    else:require(name in ('healthy-resolve','healthy-observations','healthy-relations','nano-start','nano-end','normal-100-selected','version-rebound','connection-rebound','aba-selection-current') or name.startswith(('mcp-','ui-')),'S23_CASE_UNKNOWN')
    require(data['status']==expected and len(data['candidates'])==candidates,'S23_RESULT_STATUS')
    evidence_closure(row,state,data,expected)
    if expected in ('EMPTY','UNAVAILABLE','UNAUTHORIZED','AMBIGUOUS'):
        require(not data['data'],'S23_RESULT_NO_DATA')
        if expected in ('UNAVAILABLE','UNAUTHORIZED'):require(not data['evidence'],'S23_RESULT_NO_EVIDENCE')
        if name=='sentinel-101':require(data['limited'] is True and data['subSources'] and all(s['status']!='EMPTY' for s in data['subSources']),'S23_SENTINEL')
        return expected
    roots=[r for r in data['data'] if r['kind']=='entity'];require(len(roots)==1,'S23_ROOT_COUNT');require_root(roots[0])
    relationships=[r for r in data['data'] if r['kind']=='relationship']
    observations=[r for r in data['data'] if r['kind']=='observation']
    if edges is None:edges=int(query['capabilityId']==CAPABILITIES[2])
    require(len(relationships)==edges and len({edge['target']['entityIri'] for edge in relationships})==edges,'S23_RELATION_COUNT')
    if expected=='PARTIAL':
        require(len(data['data'])==1 and len(data['evidence'])==1 and any(d['code']=='query_partial' for d in data['diagnostics'])
                and any(s['status']=='UNAVAILABLE' for s in data['subSources']),'S23_PARTIAL_TRUSTED_ROOT')
    for edge in relationships:
        require(edge['relationshipIri']==RELATION and edge['source']['entityIri']==ROOT_IRI and edge['entityIri']==ROOT_IRI,'S23_EDGE_IDENTITY')
        external='omq-target-2';start=FROM;finish=TO
        if name=='micro-overlap':start='2026-02-01T00:00:00.000000Z';finish='2026-03-01T00:00:00.000001Z'
        if name=='fanout-10':
            external=edge['target']['identity']['externalId']
            require(external in {'omq-target-2',*['s23-'+row['sourceCase']['token'][:10]+'-'+str(i) for i in range(1,10)]},'S23_FANOUT_IDENTITIES')
        expected_identity,expected_iri=identity(external,'omq-target-v1',start,finish)
        require(edge['target']['entityIri']==expected_iri and edge['target']['identity']==expected_identity
                and edge['target']['typeIris']==['urn:synthetic:mapping:Reading'],'S23_TARGET_IDENTITY')
        interval={'from':time_value('2026-02-01T00:00:00.000000Z' if name=='micro-overlap' else FROM),'to':time_value(TO)}
        # 源目标有效期改变会改变其IRI，完整时间交集仍由字面量独立判断。
        require(edge['validTime']==interval,'S23_EDGE_INTERVAL')
    if query['capabilityId']==CAPABILITIES[1]:
        require(len(observations)==1 and observations[0]['entityIri']==ROOT_IRI and observations[0]['propertyIri']=='urn:synthetic:mapping:label'
                and observations[0]['value']==dict(type='string',lexical='entity') and observations[0]['unit'] is None
                and observations[0]['observedAtUtc']=='2026-01-02T00:00:01.654321Z','S23_OBSERVATION')
    else:require(not observations,'S23_UNEXPECTED_OBSERVATION')
    expected_evidence=1+edges
    require(len(data['evidence'])==expected_evidence and len(data['subSources'])==(1 if query['capabilityId']==CAPABILITIES[0] else 2),'S23_EVIDENCE_COUNT')
    ids={e['evidenceId'] for e in data['evidence']}
    require(len(ids)==len(data['evidence']) and all(e.startswith(row['queryId']+':') for e in ids),'S23_EVIDENCE_IDS')
    used=set()
    for datum in data['data']:
        require(datum.get('evidenceIds') and len(set(datum['evidenceIds']))==len(datum['evidenceIds'])
                and set(datum['evidenceIds'])<=ids,'S23_DATA_EVIDENCE_CLOSURE')
        used.update(datum['evidenceIds'])
        for prop in datum.get('properties',[]):
            require(prop.get('evidenceIds') and set(prop['evidenceIds'])<=ids,'S23_PROPERTY_EVIDENCE_CLOSURE')
    require(used==ids,'S23_UNUSED_EVIDENCE')
    reads={e['sourceReadReceiptId'] for e in data['evidence']}
    require(all(any(s.get('sourceReadReceiptId')==read and s['status']=='SUCCESS' for s in data['subSources']) for read in reads),'S23_SOURCE_RECEIPT_CLOSURE')
    for evidence in data['evidence']:
        require(evidence['connectionId']==state['connectionId'] and evidence['mappingReleaseId']==state['mappingReleaseId']
                and evidence['sourceCatalogSnapshotId']==state['catalogSnapshotId'] and evidence['precision']=='ROW_KEY','S23_EVIDENCE_BINDING')
        encoded=evidence['sourceRecordRef'];require(encoded.startswith('key:'),'S23_RECORD_KIND')
        keys=json.loads(base64.b64decode(encoded[4:],validate=True))
        require(len(keys)==1 and keys[0]['field']=='ROW_ID' and keys[0]['value']['type']=='int64','S23_RECORD_KEY')
        allowed={'1','2',*[str(i) for i in range(71001,71010)]} if name=='fanout-10' else {'1','2'}
        require(keys[0]['value']['lexical'] in allowed,'S23_RECORD_VALUE')
    require(all(s['watermarkKind']=='UNKNOWN' and s.get('watermark') is None for s in data['subSources']),'S23_WATERMARK')
    return expected


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def identity(external,namespace,from_time=FROM,to_time=TO):
    value=dict(organizationId='org-demo',siteId='site-a',sourceNamespace=namespace,externalId=external)
    value['effectiveTime']={'from':time_value(from_time),'to':time_value(to_time)}
    return value,'urn:ontology-platform:entity:'+hashlib.sha256(canonical(value)).hexdigest()


def record_links(row,state,data,expected):
    """逐个业务断言闭合源dataset、准确主键和源有效区间，禁止根／目标证据互换。"""
    links={}
    def dataset(target):
        ref=dict(snapshotId=state['catalogSnapshotId'],schema='CaseOwner' if target else 'PRODUCTION',name='OmqTarget' if target else 'OMQ_ENTITY',kind='TABLE')
        return 'dataset-'+hashlib.sha256(canonical(ref)).hexdigest()
    def bind(eids,key,target=False,start=FROM,end=TO):
        require(len(eids)==1,'S23_ONE_RECORD_PER_ENTITY')
        value=(dataset(target),key,start,end)
        for eid in eids:
            require(eid not in links or links[eid]==value,'S23_REFERENCE_COLLISION')
            links[eid]=value
    roots=[value for value in data['data'] if value['kind']=='entity']
    if roots:
        require(len(roots)==1,'S23_LINK_ROOT')
        bind(roots[0]['evidenceIds'],1)
        root_ids=set(roots[0]['evidenceIds'])
        require(all(set(prop['evidenceIds'])==root_ids for prop in roots[0]['properties']),'S23_PROPERTY_EXACT_ROOT_REFERENCE')
        for value in data['data']:
            if value['kind']=='observation':require(set(value['evidenceIds'])==root_ids,'S23_OBSERVATION_ROOT_REFERENCE')
            elif value['kind']=='relationship':
                require(value['source']['identity']==roots[0]['identity'] and value['source']['typeIris']==roots[0]['typeIris']
                    and root_ids<set(value['evidenceIds']),'S23_EDGE_SOURCE_REFERENCE')
                external=value['target']['identity']['externalId'];key=2
                if external!='omq-target-2':
                    require(row['name']=='fanout-10','S23_TARGET_EXTERNAL')
                    token=row['sourceCase']['token'];allowed={'s23-'+token[:10]+'-'+str(i):71000+i for i in range(1,10)}
                    require(external in allowed,'S23_TARGET_ROW');key=allowed[external]
                start='2026-02-01T00:00:00.000000Z' if row['name']=='micro-overlap' else FROM
                end='2026-03-01T00:00:00.000001Z' if row['name']=='micro-overlap' else TO
                bind([eid for eid in value['evidenceIds'] if eid not in root_ids],key,True,start,end)
    if expected=='AMBIGUOUS':
        token=row['sourceCase']['token'];expected_rows={ROOT_IRI:(1,FROM,TO,'omq-entity-1')}
        if row['name']=='normal-100-all':
            for i in range(1,100):
                external='s23-'+token[:10]+'-'+str(i);expected_rows[identity(external,'query-fixture-v1')[1]]=(71000+i,FROM,TO,external)
        else:
            end='2026-03-01T00:00:00.000001Z'
            expected_rows[identity('omq-entity-1','query-fixture-v1',TO,end)[1]]=(71001,TO,end,'omq-entity-1')
        for candidate in data['candidates']:
            require(candidate['entityIri'] in expected_rows,'S23_CANDIDATE_ROW_IDENTITY')
            key,start,end,external=expected_rows[candidate['entityIri']]
            require(candidate['externalId']==candidate['label']==external,'S23_CANDIDATE_EXTERNAL')
            bind(candidate['evidenceIds'],key,False,start,end)
    require(set(links)=={ref['evidenceId'] for ref in data['evidence']},'S23_EXACT_ROW_CLOSURE')
    for ref in data['evidence']:
        source,key,start,end=links[ref['evidenceId']]
        keys=json.loads(base64.b64decode(ref['sourceRecordRef'][4:],validate=True))
        require(ref['sourceDatasetRef']==source and keys==[dict(field='ROW_ID',value=dict(type='int64',lexical=str(key)))]
            and ref['validTime']==dict(fromUtc=start,toUtc=end),'S23_EXACT_SOURCE_RECORD')


def evidence_closure(row,state,data,expected):
    """结果证据、完整来源回执、候选和真实主键分别核验，空数组不能绕过检查。"""
    import re
    from workflow_oracle_mapping_formal_observer import ns
    name=row['name'];proofs=row['evidenceProofs'];refs=data['evidence'];branches=data['subSources']
    record_links(row,state,data,expected)
    ids={item['evidenceId'] for item in refs}
    require(len(ids)==len(refs)==len(proofs) and {item['evidenceId'] for item in proofs}==ids,'S23_PROOF_SET')
    require(all(s['connectionId']==state['connectionId'] and s['watermarkKind']=='UNKNOWN' for s in branches),'S23_BRANCH_BINDING')
    require(data['snapshot']['mappingReleaseIds']==[state['mappingReleaseId']] and data['snapshot']['sourceCatalogSnapshotIds']==[state['catalogSnapshotId']]
            and data['snapshot']['capabilityId']==row['query']['capabilityId'] and data['snapshot']['capabilityVersion']==row['query']['capabilityVersion'],'S23_SNAPSHOT')
    if expected in ('EMPTY','UNAVAILABLE','UNAUTHORIZED'):require(not refs and not proofs,'S23_EMPTY_PROOFS')
    if expected=='AMBIGUOUS':
        count=100 if name=='normal-100-all' else 2
        require(len(refs)==len(data['candidates'])==count and len(branches)==1 and branches[0]['status']=='SUCCESS' and data['limited'] is False,'S23_CANDIDATE_COUNTS')
        token=row['sourceCase']['token'];require(re.fullmatch('[a-f0-9]{32}',token),'S23_CANDIDATE_TOKEN')
        expected_iris={ROOT_IRI}
        if count==2:expected_iris.add(identity('omq-entity-1','query-fixture-v1',TO,'2026-03-01T00:00:00.000001Z')[1])
        else:expected_iris.update(identity('s23-'+token[:10]+'-'+str(i),'query-fixture-v1')[1] for i in range(1,100))
        require({v['entityIri'] for v in data['candidates']}==expected_iris,'S23_CANDIDATE_IDENTITIES')
        require(all(v['organizationId']=='org-demo' and v['siteId']=='site-a' and v['entityTypeIris']==['urn:synthetic:mapping:Asset']
            and len(v['evidenceIds'])==1 and set(v['evidenceIds'])<=ids for v in data['candidates']),'S23_CANDIDATE_REFERENCES')
        require({e for v in data['candidates'] for e in v['evidenceIds']}==ids,'S23_CANDIDATE_CLOSURE')
    for ref in refs:
        require(ref['connectionId']==state['connectionId'] and ref['mappingReleaseId']==state['mappingReleaseId']
                and ref['sourceCatalogSnapshotId']==state['catalogSnapshotId'] and ref['scope']==dict(organizationId='org-demo',siteIds=['site-a'])
                and ref['precision']=='ROW_KEY' and ref['evidenceId'].startswith(row['queryId']+':'),'S23_REFERENCE_BINDING')
        item=next(p for p in proofs if p['evidenceId']==ref['evidenceId'])
        require(item['httpStatus']==200 and item['sha256']==hashlib.sha256(item['raw'].encode()).hexdigest(),'S23_PROOF_BYTES')
        proof=json.loads(item['raw']);receipt=proof['receipt']
        require(proof['schemaVersion']=='g4.source-evidence.v1' and proof['evidence']==ref and receipt['queryId']==row['queryId']
            and receipt['receiptId']==ref['sourceReadReceiptId'] and receipt['connectionId']==state['connectionId']
            and receipt['mappingReleaseId']==state['mappingReleaseId'] and receipt['originalCatalogSnapshotId']==receipt['currentCatalogSnapshotId']==state['catalogSnapshotId']
            and receipt['activationId']==state['activation']['activationId'] and receipt['activationRevision']==str(state['activation']['activationRevision']), 'S23_PROOF_BINDING')
        require(receipt['watermarkKind']=='UNKNOWN' and receipt['watermark'] is None and receipt['adapterVersion']=='oracle-query-v1'
            and receipt['status']=='SUCCESS' and 1<=receipt['rowCount']<=100 and receipt['limited'] is False
            and ref['observedAtUtc']==receipt['readCompletedAtUtc']
            and re.fullmatch('[a-f0-9]{64}',receipt['manifestHash']) and re.fullmatch('[a-f0-9]{64}',receipt['queryPlanHash'])
            and re.fullmatch('[a-f0-9]{64}',receipt['resultHash'] or '') and receipt['traceId']==data['traceId'],'S23_PROOF_CONTENT')
        require(0<=ns(receipt['readCompletedAtUtc'])-ns(receipt['readStartedAtUtc'])<=1_000_000_000
            and ns(receipt['readCompletedAtUtc'])<=ns(data['observedAtUtc']),'S23_PROOF_SOURCE_DEADLINE')
        require(any(b['sourceReadReceiptId']==receipt['receiptId'] and b['status']=='SUCCESS' and b['observedAtUtc']==receipt['readCompletedAtUtc'] for b in branches),'S23_PROOF_BRANCH')
        encoded=ref['sourceRecordRef'];require(encoded.startswith('key:'),'S23_PROOF_KEY_KIND')
        keys=json.loads(base64.b64decode(encoded[4:],validate=True))
        allowed={'1','2'}
        if name=='fanout-10':allowed.update(str(i) for i in range(71001,71010))
        elif name in ('ambiguous','aba-selection-origin','normal-100-all'):allowed.update(str(i) for i in range(71001,71100))
        require(len(keys)==1 and keys[0]['field']=='ROW_ID' and keys[0]['value']==dict(type='int64',lexical=keys[0]['value']['lexical'])
            and keys[0]['value']['lexical'] in allowed,'S23_PROOF_RECORD_KEY')


def demand_connection_original(raw):
    """独立连接版本在途反例，恢复动作严格位于原Q拒绝之后。"""
    import re
    from workflow_oracle_mapping_formal_observer import ns
    rows=[]
    for line in raw.decode().splitlines():
        try:value=json.loads(line)
        except json.JSONDecodeError:continue
        if isinstance(value,dict) and value.get('case')=='CONNECTION_AFTER_READ':rows.append(value)
    require(len(rows)==1,'S23_CONNECTION_ORIGINAL_COUNT');row=rows[0]
    require(row['taskId']=='G4-ORACLE-MAPPING-QUERY-001' and row['resourceRun']=='product-resume-01' and row['status']=='PASS'
        and row['connectionId']=='a7913bb552eb4cd1a3f6eaf5b93cd619' and row['subjectId']=='f902a743-7079-4e22-a643-a51deb027e89'
        and re.fullmatch('query-[a-f0-9]{32}',row['queryId']) and re.fullmatch('[a-f0-9]{64}',row['leaseOwnerHash']) and row['fence']>0
        and row['newRevision']==row['oldRevision']+1 and row['restoredRevision']==row['newRevision']+1,'S23_CONNECTION_IDENTITY')
    require((row['errorStatus'],row['errorCode']) in ((409,'query_binding_stale'),(403,'query_forbidden'))
        and row['executionStatus'] in ('RUNNING','FAILED','CANCELLED') and row['resultHash'] is None
        and all(row[k]==0 for k in ('resultSize','ciphertextBytes','committedReadReceipts','successfulQueryAudits')),'S23_CONNECTION_NO_SUCCESS')
    require(0<row['elapsedMs']<5000 and 0<ns(row['deadlineAtUtc'])-ns(row['admittedAtUtc'])<=5_000_000_000,'S23_CONNECTION_DEADLINE')
    require(len(row['events'])==3,'S23_CONNECTION_EVENTS')
    previous=ns(row['admittedAtUtc']);mono=-1
    for index,(event,phase) in enumerate(zip(row['events'],['SOURCE_READ_COMPLETED','CONNECTION_PATCH_COMMITTED','COMMIT_REJECTED'])):
        require(event['phase']==phase and event['sequence']==index+1 and event['queryId']==row['queryId'] and event['connectionId']==row['connectionId']
            and previous<ns(event['utc'])<ns(row['deadlineAtUtc']) and mono<event['monotonicMs']<=row['elapsedMs'],'S23_CONNECTION_ORDER')
        previous=ns(event['utc']);mono=event['monotonicMs']
    require(previous<ns(row['restoredAtUtc']),'S23_CONNECTION_RESTORE_AFTER_REJECT')
    return row


def qualify(report):
    require(report['taskId']=='G4-ORACLE-MAPPING-QUERY-001' and report['runId']=='product-resume-01' and report['batch']['planId']=='s2-s3-01','S23_REPORT_OWNER')
    mode=report['mode'];rows=report.get('oracleCases',[])
    require(rows or mode in ('s2-oracle-vocabulary','s2-oracle-mapping','s2-oracle-reopen','s2-oracle-aba'),'S23_CASES_MISSING')
    names=[r['name'] for r in rows];require(len(names)==len(set(names)),'S23_CASE_DUPLICATE')
    required={
      's2-oracle-queries':{'healthy-resolve','healthy-observations','healthy-relations','missing','nano-before','nano-start','nano-end','nano-after'},
      's2-oracle-relations':set(RELATIONS), 's2-oracle-states':{'ambiguous','normal-100-selected','normal-100-all','sentinel-101'},
      's2-oracle-versions':{'version-rebound'},'s2-oracle-connection':{'connection-rebound'},
      's2-oracle-aba':{'aba-selection-origin','aba-selection-current'},
      's2-oracle-access':{'no-grant','revoke-execute','field-execute','expired-execute','source-acl'},
      's3':{'mcp-'+x for x in CAPABILITIES},'ui-s3':{'ui-'+x for x in CAPABILITIES},'ui-s1':{'ui-refresh'}}
    require(set(names)==required.get(mode,set()),'S23_CASE_SET')
    statuses=[result_case(row,report['oracleBinding']) for row in rows]
    return dict(status='SEMANTICS_QUALIFIED',mode=mode,cases=len(rows),statuses=statuses,scope='semantic original content; parent command and source audits qualify separately')



def frozen_plan(root):
    stages=[('s0-oracle-auth','authentication',600),*[(m,'product',180) for m in ['s2-oracle-vocabulary','s2-oracle-mapping',
        's2-oracle-queries','s2-oracle-relations','s2-oracle-access','s2-oracle-aba','s2-oracle-connection','s2-oracle-versions','s2-oracle-states']],('reader-auth','authentication',180),
        *[(m,'product',180) for m in ['s2-oracle-reopen','s3','ui-s3','ui-s1']]]
    expected=dict(schemaVersion=1,planId='s2-s3-01',mode='s2-s3-oracle',preSeconds=60,postSeconds=60,submissionSeconds=40,
        requiredSessionSeconds=210,stages=[dict(mode=m,kind=k,seconds=t) for m,k,t in stages],deadlineSeconds=120+sum(t for m,k,t in stages))
    plan=json.loads((root/'scripts/maintenance/workflow-oracle-s2-plan.json').read_bytes())
    require(plan==expected,'S23_FROZEN_PLAN')
    return plan


def reopen_mutations(archive,report,host,origin):
    """按准确平台／源容器重开组合授权与可逆反例的双流，不接受摘要布尔值。"""
    import re
    import workflow_execution as ex
    import workflow_oracle_mapping_s2 as fixture
    from workflow_m4_query import grant_transaction
    from workflow_oracle_mapping_identity_recovery import ROSTER
    from workflow_oracle_mapping_evidence import sha
    state=dict(connectionId='a7913bb552eb4cd1a3f6eaf5b93cd619',scope=dict(organizationId='org-demo',siteIds=['site-a']),subjects={k:v[1] for k,v in ROSTER.items()})
    pg=['docker','--context','desktop-linux','exec','-i','--user','postgres',host['services']['platform-pg']['containerId'],'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    native=['docker','--context','desktop-linux','exec','-i',host['oracle']['containerId'],'sqlplus','-L','-s','/ as sysdba']
    def command(cid,args,stage,body):
        row,out,err=archive.command(cid,args,stage,sha(body),None,origin)
        require(row['exitCode']==0 and row['classification']=='SUCCESS','S23_MUTATION_COMMAND')
        return out.decode().strip()
    def snapshot(snapshot):
        body=b'BEGIN READ ONLY;\n'+fixture.grant_snapshot_sql(state)+b'\nCOMMIT;'
        actual=json.loads(command(snapshot['commandId'],pg,'omq-pg-s23-grant-snapshot',body))
        require(actual=={k:v for k,v in snapshot.items() if k!='commandId'},'S23_GRANT_SNAPSHOT_ORIGINAL')
        return actual
    grants=report['currentGrants']
    catalog_sql=(f'''SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"='{state['connectionId']}' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;''').encode()
    require(json.loads(command(grants['catalogCommand'],pg,'omq-pg-s23-current-catalog',b'BEGIN READ ONLY;\n'+catalog_sql+b'\nCOMMIT;'))==grants['catalogSnapshot'],'S23_GRANT_CATALOG_ORIGINAL')
    before=snapshot(grants['beforeSnapshot']);after=snapshot(grants['afterSnapshot'])
    require(all(row in after['rows'] for row in before['rows']) and grants['beforeEpoch']==before['epoch'] and grants['afterEpoch']==after['epoch']
        and grants['beforeRowsSha256']==sha(ex.encoded(before['rows'])) and grants['afterRowsSha256']==sha(ex.encoded(after['rows'])),'S23_GRANT_HISTORY_ORIGINAL')
    require(grants['rows']==[next(r for r in after['rows'] if r['Id']==grants['combinedGrantIds'][role+':'+op]) for role,op in fixture.SCOPED],'S23_GRANT_ROW_ORIGINAL')
    require(all(210<=fixture.ttl(row,after['clock'])<=14400 for row in grants['rows']) and len(grants['workflowIds'])==9,'S23_GRANT_ACTUAL_TTL')
    require(all(any(row['Id']==ident and fixture.covers(row,state,role,op,False) and row['RevokedAtUtc'] is None and fixture.ttl(row,after['clock'])>=210 for row in after['rows'])
        for ident,(role,op) in zip(grants['workflowIds'],fixture.WORKFLOW,strict=True)),'S23_WORKFLOW_ORIGINAL')
    if grants['issued']:
        plan=archive.read('grant-plan-'+grants['executionId']+'.json')
        require(plan['taskId']==report['taskId'] and plan['runId']==report['runId'] and plan['batch']=='s2-s3-01' and plan['before']==grants['beforeSnapshot']
            and plan['connectionId']==state['connectionId'] and plan['objects']==fixture.OBJECTS and plan['fields']==fixture.FIELDS and plan['planned']==grants['issued'],'S23_GRANT_PLAN_ORIGINAL')
        items=plan['planned'];lookup={(state['subjects'][item['role']],item['operation']):item['id'] for item in items}
        require(len(lookup)==len(items) and all((item['role'],item['operation']) in (fixture.SCOPED if item['kind']=='COMBINED' else fixture.WORKFLOW) for item in items),'S23_ISSUANCE_SCOPE')
        pairs=[(state['subjects'][role],[item['operation'] for item in items if item['role']==role]) for role in state['subjects']]
        body,ids=grant_transaction(state,fixture.OBJECTS,fixture.FIELDS,pairs,lambda who,op:lookup[(who,op)],report['runId'])
        require(command(grants['grantCommand'],pg,'omq-pg-s23-append-approved-grants',body).splitlines()[-1]==str(len(items))
            and after['epoch']==before['epoch']+len(items) and all(any(a['Resource']==ident and a['issued']==1 for a in after['audit']) for ident in ids),'S23_GRANT_ISSUANCE_ORIGINAL')
    else:require(grants['grantCommand'] is None and before['rows']==after['rows'] and before['epoch']==after['epoch'],'S23_GRANT_REUSE_ORIGINAL')
    def source_snapshot(value):
        columns="ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,"+','.join("to_char("+c+",'YYYYMMDDHH24MISSFF6')" for c in fixture.COLUMNS[7:])
        actual=[]
        require(len(value['commandIds'])==2,'S23_SOURCE_SNAPSHOT_COMMANDS')
        for cid,table in zip(value['commandIds'],fixture.TABLES,strict=True):
            version=value.get('projectionVersion',1)
            require(type(version) is int and version in (1,2) and all(type(row) is list and len(row)==11 for group in value['rows'] for row in group),'S23_SOURCE_PROJECTION')
            sql='select json_array('+columns+(' null on null' if version==2 else '')+' returning varchar2(500)) from '+table+' order by ROW_ID;'
            raw=command(cid,native,'s23-independent-source-snapshot',sql.encode())
            actual.append([json.loads(line,parse_float=str) for line in raw.splitlines() if line.strip()])
        require(value['rows']==actual and value['hashes']==[sha(ex.encoded(rows)) for rows in actual],'S23_SOURCE_SNAPSHOT_ORIGINAL')
    if 'independentSource' in report:
        source_snapshot(report['independentSource'])
        rows=report['independentSource']['rows'];require([len(v) for v in rows]==[1,1]
            and [r[0][2] for r in rows]==['9999999999999999999999.999999','-9999999999999999999999.999999'],'S23_EXACT_SOURCE_NUMBER')
    names=[row['name'] for row in report.get('sourceCases',[])]
    expected=list(RELATIONS) if report['mode']=='s2-oracle-relations' else ['ambiguous','normal-100','sentinel-101'] if report['mode']=='s2-oracle-states' else ['ambiguous'] if report['mode']=='s2-oracle-aba' else []
    require(names==expected,'S23_SOURCE_CASE_CLOSURE')
    for case in report.get('sourceCases',[]):
        changed,restored=case['changed'],case['restored'];token=changed['token'];require(re.fullmatch('[a-f0-9]{32}',token),'S23_SOURCE_TOKEN')
        plan=archive.read('source-case-'+token+'.json')
        require(plan['taskId']==report['taskId'] and plan['runId']==report['runId'] and plan['batch']=='s2-s3-01' and plan['token']==token
            and plan['status']=='PREPARED' and plan['sourceId']==host['oracle']['containerId'] and plan['action']==case['name'],'S23_SOURCE_PLAN')
        require(archive.read('source-injected-'+token+'.json')==changed and archive.read('source-restore-'+token+'.json')==restored,'S23_SOURCE_LEDGER_ORIGINAL')
        baseline=[[[1,1,'9999999999999999999999.999999','org-demo','site-a','omq-entity-1','entity','20260101000000000001','20260201000000000001','20260102000000123456','20260102000001654321']],
            [[2,1,'-9999999999999999999999.999999','org-demo','site-a','omq-target-2','target','20260101000000000001','20260201000000000001','20260103000000123456','20260103000001654321']]]
        require(plan['before']['rows']==baseline,'S23_SOURCE_LITERAL_BASELINE')
        require(changed['before']==plan['before'] and changed['expectedRows']==plan['expectedRows'] and changed['after']['rows']==plan['expectedRows']
            and plan['expectedRows']==fixture.expected_case(case['name'],plan['before']['rows'],token),'S23_SOURCE_EXPECTED')
        for snap in (changed['before'],changed['after'],restored['before'],restored['after']):source_snapshot(snap)
        require(restored['after']['rows']==changed['before']['rows'] and restored['token']==token and restored['status']=='RESTORED','S23_SOURCE_RESTORED')
        body=fixture.source_transaction(changed['before']['rows'],changed['after']['rows']).encode()
        require(plan['sqlSha256']==sha(body),'S23_SOURCE_SQL_HASH')
        command(changed['commandId'],native,'s23-source-'+case['name'],body)
        if restored['commandId']:
            command(restored['commandId'],native,'s23-source-restore',fixture.source_transaction(restored['before']['rows'],restored['after']['rows']).encode())
        else:require(restored['before']==restored['after'],'S23_SOURCE_NOOP_RESTORE')
        for result in report['oracleCases']:
            if result.get('sourceCase',{}):
                if result['sourceCase']['token']==token:require(result['sourceCase']['action']==case['name'],'S23_SOURCE_RESULT_LINK')
    mutations=list(report.get('permissionCases',[]))
    for key in ('shortTtl','restorePermission','uiPermission'):
        if key in report:mutations.append(report[key])
    for pair in mutations:
        changed,restored=pair['changed'],pair['restored'];token=changed['token'];plan=archive.read('permission-case-'+token+'.json')
        require(plan['taskId']==report['taskId'] and plan['runId']==report['runId'] and plan['batch']=='s2-s3-01' and plan['token']==token
            and plan['before']==changed['before'] and fixture.same_grant(plan['after'],changed['after']) and plan['id']==changed['id']==restored['id']
            and fixture.same_grant(restored['after'],changed['before']) and restored['action']=='restore','S23_PERMISSION_PLAN')
        expected_after=dict(changed['before'])
        if changed['action']=='field':expected_after['FieldRefs']=fixture.FIELDS[:-1]
        elif changed['action']=='revoke':expected_after['RevokedAtUtc']=changed['after']['RevokedAtUtc'];require(expected_after['RevokedAtUtc'] is not None,'S23_REVOKE_TIMESTAMP')
        elif changed['action'] in ('expired','short'):
            expected_after['ExpiresAtUtc']=changed['after']['ExpiresAtUtc']
            left=fixture.ttl(changed['after'],changed['beforeSnapshot']['clock'])
            require(abs(left-(5 if changed['action']=='expired' else 30))<0.00001,'S23_PERMISSION_EXACT_TTL')
        else:require(False,'S23_PERMISSION_ACTION')
        require(fixture.same_grant(expected_after,changed['after']),'S23_PERMISSION_SINGLE_CHANGE')
        require(changed['id'] in grants['combinedGrantIds'].values() and changed['before']['SubjectId']==ROSTER['reader'][1],'S23_PERMISSION_SCOPE')
        for entry in (changed,restored):
            prior=snapshot(entry['beforeSnapshot']);current=snapshot(entry['afterSnapshot'])
            require(any(fixture.same_grant(row,entry['before']) for row in prior['rows']) and any(fixture.same_grant(row,entry['after']) for row in current['rows']),'S23_PERMISSION_SNAPSHOTS')
            if entry['commandId']:
                audit_ids=re.findall(r"VALUES \('([a-f0-9]{32})',now\(\)",entry['sql'])
                require(len(audit_ids)==1 and entry['sql']==fixture.permission_sql(entry['id'],entry['before'],plan['before'] if entry['action']=='restore' else plan['after'],entry['action'],entry['token'],audit_ids[0]),'S23_PERMISSION_SQL_SCOPE')
                raw=command(entry['commandId'],pg,'omq-pg-s23-permission-'+entry['action'],entry['sql'].encode())
                require(fixture.same_grant(json.loads(raw.splitlines()[-1]),entry['after']) and current['epoch']==prior['epoch']+1,'S23_PERMISSION_READBACK')
            else:require(fixture.same_grant(entry['before'],entry['after']) and current==prior,'S23_PERMISSION_NOOP')
    if report['mode']=='s2-oracle-access':
        require(len(report['permissionCases'])==5 and 'shortTtl' in report and 'sourceAcl' in report,'S23_ACCESS_CASE_CLOSURE')
        expiry=report['naturalExpiry'];entry=next(pair['changed'] for pair in report['permissionCases'] if pair.get('action')=='expired')
        require(archive.read('expiry-'+expiry['token']+'.json')==expiry and expiry['token']==entry['token'] and expiry['before']==entry['afterSnapshot']
            and fixture.ttl(entry['after'],expiry['before']['clock'])>0 and expiry['status']=='NATURALLY_EXPIRED' and expiry['observations'],'S23_NATURAL_EXPIRY_PRESTATE')
        for observation in expiry['observations']:
            snapshot(observation)
            require(any(fixture.same_grant(row,entry['after']) for row in observation['rows']) and observation['epoch']==expiry['before']['epoch'],'S23_NATURAL_EXPIRY_UNCHANGED')
        require(fixture.ttl(entry['after'],expiry['observations'][-1]['clock'])<=0,'S23_NATURAL_EXPIRY_OBSERVED')
        pair=report['sourceAcl'];changed,restored=pair['changed'],pair['restored'];token=changed['token']
        acl_sql="SELECT json_array(OWNER,TABLE_NAME,PRIVILEGE,GRANTABLE) FROM DBA_TAB_PRIVS WHERE GRANTEE='FIXTURE_READER' AND (OWNER,TABLE_NAME) IN (('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget')) ORDER BY OWNER,TABLE_NAME,PRIVILEGE;"
        healthy=[['CaseOwner','OmqTarget','READ','NO'],['PRODUCTION','OMQ_ENTITY','READ','NO']]
        for snap,expected in [(changed['before'],healthy),(changed['after'],healthy[1:]),(restored['before'],healthy[1:]),(restored['after'],healthy)]:
            actual=[json.loads(line) for line in command(snap['commandId'],native,'s23-source-acl',acl_sql.encode()).splitlines() if line.strip()]
            require(snap['sourceId']==host['oracle']['containerId'] and actual==snap['rows']==expected,'S23_ACL_EXACT_ROWS')
        require(archive.read('acl-case-'+token+'.json')['before']==changed['before'] and archive.read('acl-restored-'+token+'.json')==restored,'S23_ACL_LEDGER')
        command(changed['commandId'],native,'s23-revoke-read',b'REVOKE READ ON "CaseOwner"."OmqTarget" FROM FIXTURE_READER;')
        command(restored['commandId'],native,'s23-restore-read',b'GRANT READ ON "CaseOwner"."OmqTarget" TO FIXTURE_READER;')
    return dict(grants=6,sourceCases=len(names),permissionCases=len(mutations))


def reopen_stage(archive,report,records,host,origin,measured,window):
    """真实消费者重开每个独立窗口的完整源审计，拒绝子摘要、重复/间隙读取及未绑定HTTP字节。"""
    from workflow_oracle_mapping_evidence import audit_observation,utc,sha
    from workflow_oracle_mapping_formal_observer import ns
    from workflow_oracle_mapping_s2 import OBJECTS,FIELDS,SCOPED
    from workflow_oracle_mapping_identity_recovery import ROSTER
    result=qualify(report)
    ledger=reopen_mutations(archive,report,host,origin)
    grants=report['currentGrants'];require(grants['taskId']==report['taskId'] and grants['runId']==report['runId'] and grants['batch']=='s2-s3-01'
        and grants['fieldCount']==22 and grants['grantCount']==6 and len(grants['rows'])==6 and grants['requiredSeconds']==210
        and grants['remainingSeconds']>=210 and grants['historyPreserved'] is True,'S23_GRANT_SCOPE')
    for role,op in SCOPED:
        ident=grants['combinedGrantIds'][role+':'+op]
        rows=[row for row in grants['rows'] if row['Id']==ident]
        require(len(rows)==1 and rows[0]['SubjectId']==ROSTER[role][1] and rows[0]['Permission']==op
                and rows[0]['ConnectionId']=='a7913bb552eb4cd1a3f6eaf5b93cd619' and rows[0]['OrganizationId']=='org-demo'
                and rows[0]['SiteIds']==['site-a'] and rows[0]['ObjectRefs']==OBJECTS and rows[0]['FieldRefs']==FIELDS
                and rows[0]['RevokedAtUtc'] is None,'S23_GRANT_SINGLE_COMPLETE')
    for row in report.get('oracleCases',[]):
        # UI的HTTP流来自实际Playwright响应；驱动本身及原报告散列已由父消费者核。
        from urllib.parse import quote
        for item in row['evidenceProofs']:
            require(any(h['method']=='GET' and h['path']=='/api/v1/data/source-evidence/'+quote(item['evidenceId'],safe='') and h['status']==200 and h['sha256']==item['sha256'] for h in report['http']),'S23_HTTP_EVIDENCE_ORIGINAL')
        if not row['name'].startswith('ui-'):
            require(any(h['method']=='POST' and h['path']=='/api/v1/data/semantic-queries' and h['status']==200 and h['sha256']==row['sha256']
                for h in report['http']),'S23_HTTP_RESULT_ORIGINAL')
    keys=('instance','session','entry','statement','owner','table')
    complete={tuple(row[k] for k in keys):row for row in records};require(len(complete)==len(records),'S23_STAGE_DUPLICATE')
    union={};previous=ns(window['startedAtUtc'])
    for item in report['oracleWindows']:
        start,end=ns(item['startedAtUtc']),ns(item['finishedAtUtc'])
        require(previous<=start<end<=ns(window['endedAtUtc']) and item['audit']['clientId'] is None,'S23_WINDOW_ORDER')
        raw=audit_observation(archive,item['audit'],dict(startedAtUtc=item['startedAtUtc'],endedAtUtc=item['finishedAtUtc']),host,origin,measured)
        current={tuple(row[k] for k in keys):row for row in raw}
        expected={key:row for key,row in complete.items() if start<=ns(row['utc'])<end}
        require(len(current)==len(raw)==item['expectedReads'] and current==expected,'S23_WINDOW_EVENTS')
        for key,row in current.items():
            instant=ns(row['utc']);bounds=item['audit']['errorBounds']
            require(start<=instant+bounds['lowerNs'] and instant+bounds['upperNs']+999<end and key not in union,'S23_WINDOW_CLOCK_OR_DUPLICATE')
            union[key]=row
        previous=end
    require(union==complete,'S23_STAGE_AUDIT_GAP')
    if report['mode'] in ('s2-oracle-mapping','s2-oracle-versions','s2-oracle-connection'):
        proof=report['mappingQualification'];proposal,release,active=[json.loads(proof[k]) for k in ('proposal','release','active')]
        require(proposal['status']=='APPROVED' and proposal['submittedBy']==ROSTER['operator'][1] and proposal['decision']['decidedBy']==ROSTER['auditor'][1]
            and proposal['decision']['decision']=='APPROVE' and proposal['activation']['mappingReleaseId']==active['mappingReleaseId']==release['manifest']['mappingReleaseId']
            and proposal['activation']['manifestHash']==release['manifestHash'] and len(release['manifest']['mapping']['entities'])==2,'S23_MAPPING_CHAIN')
        for kind,path in [('proposal','/api/v1/mapping-proposals/'+proposal['proposalId']),('release','/api/v1/mapping-releases/'+active['mappingReleaseId']),
                          ('active','/api/v1/mappings/'+active['mappingId']+'/active')]:
            require(any(h['method']=='GET' and h['path']==path and h['sha256']==sha(proof[kind].encode()) for h in report['http']),'S23_MAPPING_HTTP')
    if report['mode']=='s2-oracle-reopen':
        saved=report['oracleRestore'];require(saved['oldSessionHash']!=saved['newSessionHash'] and saved['originalHash']==sha(saved['raw'].encode())
            and saved['subjectId']==ROSTER['reader'][1] and not records,'S23_RESTORE_ORIGINAL')
        previous=archive.read(saved['originalReport']);prior=next(row for row in previous['oracleCases'] if row['queryId']==saved['queryId'])
        require(prior['raw']==saved['raw'] and prior['sha256']==saved['originalHash']
            and next(v for v in previous['scenarioReady']['session']['observations'] if v['subjectId']==ROSTER['reader'][1])['sessionHash']==saved['oldSessionHash'],'S23_RESTORE_EXACT_PRIOR_STAGE')
    expected_mapping=list(RELATIONS) if report['mode']=='s2-oracle-relations' else ['aba-b'] if report['mode']=='s2-oracle-aba' else []
    require([row['name'] for row in report.get('mappingCases',[])]==expected_mapping,'S23_MAPPING_CASE_SET')
    for case in report.get('mappingCases',[]):
        assessment=case['assessment'];issue=RELATIONS[case['name']][2] if case['name'] in RELATIONS else None
        require(case['job']['status']=='SUCCEEDED' and assessment['assessmentId']==case['job']['assessmentId']
            and assessment['status']==('BLOCKED' if issue else 'READY_FOR_PROPOSAL') and (issue is None or any(i['code']==issue for i in assessment['issues']))
            and json.loads(case['raw'])==assessment,'S23_MAPPING_SEMANTIC_EXPECTATION')
        require(any(h['method']=='GET' and h['path']=='/api/v1/mapping-assessments/'+assessment['assessmentId'] and h['status']==200 and h['sha256']==sha(case['raw'].encode()) for h in report['http']),'S23_MAPPING_ASSESSMENT_ORIGINAL')
    if report['mode'] in ('s2-oracle-versions','s2-oracle-connection'):
        versions=report['catalogVersion'];before,after=versions['before'],versions['after'];connection=versions['connectionAfter']
        require(before['snapshotId']!=after['snapshotId'] and before['schemaFingerprint']==after['schemaFingerprint'] and before['objects']==after['objects']
            and after['configRevision']==connection['configRevision'] and connection['state']=='ACTIVE'
            and connection['secretVersion']==versions['connectionBefore']['secretVersion'],'S23_CATALOG_VERSION_ORIGINAL')
        delta=0 if report['mode']=='s2-oracle-versions' else 2
        require(connection['configRevision']==versions['connectionBefore']['configRevision']+delta,'S23_CATALOG_SINGLE_CAUSE')
        if delta==0:require(len(report['versionRejections'])==1 and report['versionRejections'][0]['status']==409 and json.loads(report['versionRejections'][0]['raw'])['code']=='query_binding_stale','S23_CATALOG_OLD_BINDING_REJECTED')
    if report['mode']=='s2-oracle-vocabulary':
        vocab=report['vocabulary']
        require(vocab['status'] in ('FRESH','REUSED'),'S23_VOCABULARY_CURRENT_PATH')
        release=json.loads(vocab['releaseRaw'])
        require(release['manifestHash']==vocab['manifestHash'] and release['manifest']['releaseId']==vocab['releaseId']
            and vocab['assessment']['publishEligible'] and vocab['impact']['publishEligible'] and vocab['approved']['status']=='APPROVED'
            and vocab['approved']['submittedBy']==ROSTER['operator'][1] and 'urn:synthetic:mapping:Reading' in vocab['draft']['sources']['ontologyTurtle']
            and 'urn:synthetic:mapping:hasReading' in vocab['draft']['sources']['ontologyTurtle'],'S23_VOCABULARY_FORMAL')
        require(any(h['method']=='GET' and h['path']=='/api/v1/releases/'+vocab['releaseId'] and h['sha256']==sha(vocab['releaseRaw'].encode()) for h in report['http']),'S23_VOCABULARY_HTTP')
    if report['mode']=='s3':
        require([v['cap'] for v in report['mcp']]==list(CAPABILITIES),'S23_MCP_CAPABILITIES')
        for item in report['mcp']:
            original=next(v for v in report['oracleCases'] if v['name']=='mcp-'+item['cap']);require(item['queryId']==original['queryId'],'S23_MCP_QUERY')
            for kind in ('called','saved'):
                value=item[kind];require(not value.get('isError',False) and len(value['content'])==1 and value['content'][0]['text']==original['raw']
                    and value['structuredContent']==json.loads(original['raw']),'S23_MCP_CANONICAL')
            for kind in ('deniedExecution','deniedRestore'):
                value=item[kind];require(value['isError'] is True and not value.get('structuredContent') and len(value['content'])==1 and value['content'][0]['text']=='semantic_tool_rejected','S23_MCP_DENIED')
    if report['mode'] in ('ui-s3','ui-s1'):
        checks={v['name'] for v in report['checks'] if v['status']=='PASS'}
        required={'oracle_mapping_editor_connection_catalog'} if report['mode']=='ui-s3' else {'oracle_refresh_original_bytes','oracle_ui_revoked_403','oracle_ui_revoked_clears',
            'oracle_ui_real_subject_changed','oracle_ui_late_old_subject_discarded','oracle_ui_changed_subject_404','oracle_ui_rejection_cleared','oracle_ui_no_persistent_data'}
        require(required<=checks,'S23_UI_ACTUAL_COMPONENT_CHECKS')
    if report['mode'] in ('s2-oracle-aba','s2-oracle-connection'):
        from workflow_oracle_mapping_s2 import runtime_invocation
        from workflow_m4_query_evidence import demand_aba_original
        case='aba' if report['mode']=='s2-oracle-aba' else 'connection'
        summary=report['aba' if case=='aba' else 'connectionRuntime']
        from workflow_oracle_mapping_evidence import stable_host,host_observation
        require(stable_host(summary['host'])==stable_host(host) and summary['input']==archive.read('agent-snapshot.json')['inputs'],'S23_RUNTIME_CURRENT_HOST_INPUT')
        # 重开运行器紧前真实宿主检查，避免仅使用自报的parentId。
        host_observation(archive,summary['host'],archive.read('api-snapshot.json')['inputs'],origin,session_directory=origin/archive.read('agent-snapshot.json')['directory'])
        args=runtime_invocation(summary['host']['services']['api-secondary']['containerId'],summary['nonce'],case)
        row,stdout,_=archive.command(summary['commandId'],args,'query-real-'+case+'-inflight-runtime',
            sha(__import__('workflow_execution').encoded(summary['input'])),summary['host']['commandId'],origin)
        require(row['deadlineSeconds']==25 and ns(window['startedAtUtc'])<=ns(row['startedAtUtc'])<ns(row['endedAtUtc'])<=ns(window['endedAtUtc']),'S23_RUNTIME_STAGE_WINDOW')
        original=demand_aba_original(stdout,'query-real-aba-inflight-runtime',report['taskId'],report['runId']) if case=='aba' else demand_connection_original(stdout)
        require(row['exitCode']==0 and row['classification']=='SUCCESS' and summary['original']==original,'S23_RUNTIME_ORIGINAL')
        if case=='aba':
            import re
            require(original['connectionId']=='a7913bb552eb4cd1a3f6eaf5b93cd619' and original['capturedA']['connectionId']==original['connectionId']
                and original['subjectId']==ROSTER['reader'][1] and re.fullmatch('[a-f0-9]{64}',original['leaseOwnerHash']) and original['fence']>0,'S23_ABA_CAPTURE')
            previous=ns(original['admittedAtUtc']);mono=-1
            for event in original['events']:
                require(event['connectionId']==original['connectionId'] and previous<ns(event['utc']) and mono<event['monotonicMs'],'S23_ABA_STRICT_ORDER')
                previous=ns(event['utc']);mono=event['monotonicMs']
            history=report['historySelection'];old=next(r for r in report['oracleCases'] if r['name']=='aba-selection-origin')
            require(history['originQueryId']==old['queryId'] and history['originHash']==old['sha256'] and history['restoredRaw']==old['raw']
                and history['rejection']['status']==409 and json.loads(history['rejection']['raw'])['code']=='query_binding_stale','S23_ABA_HISTORY_SELECTION')
    return dict(**result,mutationOriginals=ledger,sourceAuditCount=len(records),auditWindows=len(report['oracleWindows']),completeEventPartition=True)


if __name__=='__main__':
    import sys
    print(json.dumps(qualify(json.load(sys.stdin))))
