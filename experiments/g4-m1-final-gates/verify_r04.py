"""将R04真实HTTP、数据库只读回执、审计Trace及容器镜像身份逐项绑定。"""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-final-gates-001/r04-final'
reports=list((ART/'http').glob('http-*/report.json'));assert len(reports)==1
def wire_keys(value):
    # 持久化默认PascalCase与HTTP camelCase字段名不同；仅转换字段首字母，值与数组完整比较。
    if isinstance(value,dict):return {k[:1].lower()+k[1:]:wire_keys(v) for k,v in value.items()}
    if isinstance(value,list):return [wire_keys(v) for v in value]
    return value
raw=reports[0].read_bytes();r=json.loads(raw);assert r['exitCode']==0
w=json.loads((ART/'db-readback.json').read_text());db=w['data'];audits=db['audits'];checks=[]
def check(name,passed,facts=None):
    checks.append({'name':name,'status':'PASS' if passed else 'FAIL','facts':facts});assert passed,name
try:
    check('three_committed_activations',len(db['activations'])==3 and sorted(x['Revision'] for x in db['activations'])==[1,2,3])
    for i,activation in enumerate(r['activations']):
        matches=[x for x in audits if x['Id']==activation['auditId']]
        check('activation_audit_'+str(i),len(matches)==1 and matches[0]['TraceId']==activation['traceId'] and matches[0]['Action']==('release.rollback' if i==2 else 'release.activate') and matches[0]['Resource']==activation['releaseId'] and matches[0]['Outcome']=='allowed',{'auditId':activation['auditId'],'traceId':activation['traceId']})
        record=next(x for x in db['activations'] if x['ActivationId']==activation['activationId']);check('activation_persistence_'+str(i),wire_keys(json.loads(record['ResultJson']))==activation)
    check('active_matches_rollback',len(db['active'])==1 and db['active'][0]['Revision']==3 and db['active'][0]['ReleaseId']==r['activations'][0]['releaseId'])
    check('fault_active_full_identity',r['fault']['rejection']=='artifact_store_timeout' and len(r['fault']['afterActive'])==1 and all(r['fault']['beforeActive'][key]==r['fault']['afterActive'][0][key] for key in ['manifest','manifestHash','activationRevision']))
    for h in r['http']:
        trace=h.get('traceId');matches=[x for x in audits if x['TraceId']==trace]
        if h['httpStatus']==403:check('denied_audit_'+str(h['index']),bool(trace) and any(x['Outcome']=='denied' for x in matches),{'route':h['route'],'traceId':trace,'actions':[x['Action'] for x in matches]})
        if h['httpStatus']==503 and h['route']=='/api/v1/release-activations':check('fault_no_committed_activation',not any(x['Action'] in ('release.activate','release.rollback') for x in matches))
        expected=None
        if h['httpStatus']==200:
            if h['route']=='/api/v1/ontology-drafts' and h['method']=='POST':expected='ontology.create'
            elif h['route'].endswith('/assessments'):expected='ontology.assess'
            elif h['route']=='/api/v1/impact-reports':expected='ontology.impact.generate'
            elif h['route']=='/api/v1/release-proposals' and h['method']=='POST':expected='release.proposal.create'
            elif h['route'].endswith('/decisions'):expected='release.approval.decide'
            elif h['route']=='/api/v1/semantic/queries':expected='semantic.query'
            elif h['route'].startswith('/api/v1/evidence/'):expected='semantic.evidence.read'
            elif h['method']=='PUT':expected='ontology.save'
        if expected:check('positive_audit_'+str(h['index']),bool(trace) and any(x['Action']==expected and x['Outcome']=='allowed' for x in matches),{'action':expected,'traceId':trace})
    labels=[q['data'][0]['entity']['label'] for q in r['queries']]
    check('v1_faultv1_v2_rollbackv1_content',labels==['炉次heat-1','炉次heat-1','炉次heat-1-R04-v2','炉次heat-1'],labels)
    for i,q in enumerate(r['queries']):
        check('query_trace_'+str(i),any(h.get('traceId')==q['traceId'] and h['route']=='/api/v1/semantic/queries' and h['httpStatus']==200 for h in r['http']))
        evidence=r['evidence'][i];check('label_evidence_'+str(i),evidence['objectTerm']['value']==labels[i] and evidence['contentHash']==q['snapshot']['dataHash'] and evidence['releaseId']==q['snapshot']['releaseId'] and evidence['graphIri']==q['snapshot']['dataGraphIri'])
    witness=json.loads((ART/'runtime-witness.json').read_text());resources=witness['resources'];check('resource_budget',len(resources)==6 and sum(x['memory'] for x in resources)==4864*1024**2)
    expected={'fuseki':'715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c','rustfs':'9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b','platform-pg':'9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437','keycloak-test':'e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4','api':'3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55','web':'a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f'}
    for obj in resources:check('exact_image_'+obj['name'],obj['descriptor']['digest']=='sha256:'+expected[obj['name']])
finally:
    value={'taskId':'G4-M1-FINAL-GATES-001','status':'PASS' if checks and all(x['status']=='PASS' for x in checks) else 'FAIL','checks':checks,'reportSha256':hashlib.sha256(raw).hexdigest(),'dbSha256':hashlib.sha256((ART/'db-readback.json').read_bytes()).hexdigest(),'driverSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with open(ART/'bindings-final.json','x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':value['status'],'checks':len(checks)}))
