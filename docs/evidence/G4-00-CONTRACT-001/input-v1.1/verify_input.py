#!/usr/bin/env python3
"""G4-00 v1.1 input/UX/API cross-checks; stdlib only, no product runtime or network.

The full Draft 2020-12 JSON Schema validation is in verify_schema.py, which
requires an already-installed jsonschema package and never installs anything.
"""
import hashlib, json, pathlib, re, sys
ROOT=pathlib.Path(__file__).resolve().parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify():
    manifest=json.loads((ROOT/'MANIFEST.json').read_text('utf-8'))
    assert manifest['taskId']=='G4-00-CONTRACT-001'
    assert manifest['packageVersion']=='1.1'
    assert manifest['executionAuthorized'] is False
    assert manifest['reviewStatus']=='REQUEST_CHANGES_RESOLVED_DESIGN_ONLY'
    declared=manifest['members']
    all_files={x.relative_to(ROOT).as_posix() for x in ROOT.rglob('*') if x.is_file()}
    expected=set(declared)|{'MANIFEST.json','SHA256SUMS.txt'}
    assert all_files==expected, (sorted(all_files-expected),sorted(expected-all_files))
    for path,info in declared.items():
        f=ROOT/path
        assert f.is_file() and f.stat().st_size==info['bytes'],path
        assert digest(f)==info['sha256'],path
    lines=(ROOT/'SHA256SUMS.txt').read_text('utf-8').splitlines()
    assert lines==[f"{info['sha256']}  {p}" for p,info in sorted(declared.items())], 'SHA256SUMS differs from manifest'
    ux=(ROOT/'docs/03-G4-UX-STATE-MATRIX.md').read_text('utf-8')
    for i in range(1,14): assert re.search(rf'\bU{i:02d}\b',ux),f'missing UX U{i:02d}'
    acc=(ROOT/'docs/08-STAGES-ACCEPTANCE.md').read_text('utf-8')
    for i in range(1,71):assert re.search(rf'\bS-{i:02d}\b',acc),f'missing acceptance S-{i:02d}'
    for i in range(1,21):assert re.search(rf'\bC-{i:02d}\b',acc),f'missing contract C-{i:02d}'
    prd=(ROOT/'docs/02-G4-PRODUCT-PRD.md').read_text('utf-8')
    tech=(ROOT/'docs/04-CONNECTOR-MATRIX.md').read_text('utf-8')
    for name in ('PostgreSQL','Oracle','Doris','TDengine','Web API'):
        assert name in prd and name in tech, f'missing connector {name}'
    for name in ('FOUND','EMPTY','PARTIAL','UNAVAILABLE','UNAUTHORIZED','AMBIGUOUS'):
        assert name in ux and name in (ROOT/'docs/06-SECURITY-AND-QUERY.md').read_text('utf-8'), name
    for p in ROOT.rglob('*.json'):json.loads(p.read_text('utf-8'))
    positive=json.loads((ROOT/'samples/g4-design-positive-synthetic.json').read_text('utf-8'))
    negative=json.loads((ROOT/'samples/g4-design-negative-cases.json').read_text('utf-8'))
    regressions=json.loads((ROOT/'samples/g4-wire-contract-v11-negative-mutations.json').read_text('utf-8'))
    assert len(positive)==21 and len(negative)>=20 and len(regressions)==16
    semantic_negative=json.loads((ROOT/'samples/g4-wire-contract-v11-semantic-negative-cases.json').read_text('utf-8'))
    assert len(semantic_negative)==3
    connections=[x['payload'] for x in positive if x['schemaKind']=='ConnectionCreateRequest']
    assert {x['config']['type'] for x in connections}=={'POSTGRESQL','ORACLE','DORIS','TDENGINE','WEB_API'}
    assert len(connections)==6
    for con in connections:
        assert set(con)=={'displayName','scopeSelection','config','secretRef','command'}
        assert con['command']['expectedRevision']==0
        assert 'credentialRef' not in con['config']['profile']
        if con['config']['type']=='WEB_API' and con['config']['profile']['authentication']=='NONE':assert con['secretRef'] is None
        else:assert isinstance(con['secretRef'],str) and con['secretRef']
    query=[x['payload'] for x in positive if x['schemaKind']=='G4QueryResultV1']
    assert len(query)==6
    assert all(set(x)=={'schemaVersion','status','data','candidates','evidence','snapshot','subSources','validTime','observedAtUtc','traceId','limited','diagnostics'} for x in query)
    ambiguous=next(x for x in query if x['status']=='AMBIGUOUS')
    assert len(ambiguous['candidates'])==2 and not ambiguous['data']
    assert len({x['entityIri'] for x in ambiguous['candidates']})==2
    assert {x['siteId'] for x in ambiguous['candidates']}=={'SITE_A'}
    ids={x['evidenceId'] for x in ambiguous['evidence']}
    assert all(set(c['evidenceIds'])<=ids for c in ambiguous['candidates'])
    assert all(x['execution']=='NOT_RUN_DESIGN_ONLY' for x in negative)
    assert {x['schemaKind'] for x in positive}=={'ConnectionCreateRequest','MappingDraft','SemanticQuery','G4QueryResultV1','MappingListPage','MappingProposalView','MappingReleaseView','MappingRevisionDiffView','MappingAssessmentView'}
    docs=(ROOT/'docs/05-DATA-API-CONTRACT.md').read_text('utf-8')
    for path in ('GET /mappings/{id}','GET /mappings/{id}/revisions/{revision}',
                 'GET /mappings/{id}/diff','GET /mapping-proposals/{id}',
                 'GET /mapping-releases/{id}','GET /mappings/{id}/active'):
        assert path in docs,path
    assert '`PATCH /mappings/{id}`' in docs and '`PATCH /mappings/{id}`' in ux
    assert 'G4QueryResultV1' in docs and '/api/v1/data/semantic-queries' in docs
    assert 'AWAITING_SEPARATE_USER_EXECUTION_APPROVAL' in (ROOT/'docs/09-CODEX-EXECUTION-CONTRACT.md').read_text()
    print(json.dumps({'status':'PACKAGE_AND_CROSS_DOCUMENT_STRUCTURE_PASS','files':len(all_files),'payloadFiles':len(declared),'ux':13,'contractAcceptances':20,'futureProductAcceptances':70,'positiveSynthetic':len(positive),'negativeDesign':len(negative),'negativeSchemaRegressions':len(regressions),'negativeSemanticRegressions':len(semantic_negative),'runtime':'NOT_RUN','jsonSchemaSemanticValidation':'USE_verify_schema.py'},ensure_ascii=False))

if __name__=='__main__':
    try:verify()
    except Exception as e:
        print('VERIFY_FAILED:',str(e),file=sys.stderr);sys.exit(1)
