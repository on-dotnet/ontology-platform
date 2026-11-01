"""Synthetic design counterexamples; not API/ACL runtime verification."""
from pathlib import Path
import json,copy
from jsonschema import Draft202012Validator,FormatChecker
E=Path(__file__).resolve().parent
original=json.loads((E/'input-v1.1/contracts/g4-proposed-wire-contract.schema.json').read_text())
reviewed=json.loads((E/'g4-reviewed-design.schema.json').read_text())
Draft202012Validator.check_schema(reviewed)
f=FormatChecker();assert {'date-time','uri'} <= f.checkers.keys()
v=Draft202012Validator(reviewed,format_checker=f);old=Draft202012Validator(original,format_checker=f)
pos=json.loads((E/'input-v1.1/samples/g4-design-positive-synthetic.json').read_text())
negative=json.loads((E/'input-v1.1/samples/g4-wire-contract-v11-negative-mutations.json').read_text())
assert all(v.is_valid(x) for x in pos)
assert all(not v.is_valid(x['payload']) for x in negative)
query=copy.deepcopy(next(x for x in pos if x['schemaKind']=='SemanticQuery'))
amb=next(x['payload'] for x in pos if x['schemaKind']=='G4QueryResultV1' and x['payload']['status']=='AMBIGUOUS')
candidates=amb['candidates'];rows=[]
def record(name,actual,expected):
 assert actual==expected,name
 rows.append({'caseId':name,'actual':actual,'expected':expected,'status':'PASS'})
def semantic(p,visible,version_ok=True):
 if not version_ok:return '409'
 selected=p['filters']['entityIri'];matches=[c for c in visible if c['entityIri']==selected]
 if not visible:return '403'
 if len(matches)!=1:return '422'
 c=matches[0]
 if c['siteId']!=p['filters']['siteId']:return '422'
 ext=p['filters'].get('entityExternalId')
 if ext is not None and ext!=c['externalId']:return '422'
 return 'ACCEPT'
for i,c in enumerate(candidates):
 x=copy.deepcopy(query);x['payload']['filters']={'entityIri':c['entityIri'],'siteId':c['siteId'],'entityExternalId':c['externalId']}
 record('original-rejects-selection-'+str(i),old.is_valid(x),False)
 record('reviewed-selection-schema-'+str(i),v.is_valid(x),True)
 record('reviewed-selection-semantic-'+str(i),semantic(x['payload'],candidates),'ACCEPT')
x=copy.deepcopy(x)
for name,modify in [('missing-site',lambda p:p.pop('siteId')),('null-site',lambda p:p.update(siteId=None)),('relative-iri',lambda p:p.update(entityIri='not-an-iri')),('empty-authority',lambda p:p.update(entityIri='https://')),('empty-urn',lambda p:p.update(entityIri='urn:')),('iri-space',lambda p:p.update(entityIri='https://db.example.invalid;SELECT 1')),('extra-sql',lambda p:p.update(sql='SELECT synthetic'))]:
 z=copy.deepcopy(x);modify(z['payload']['filters']);record(name,v.is_valid(z),False)
for name,field,value in [('wrong-site','siteId','SITE_B'),('wrong-entity','entityIri','urn:synthetic:unseen'),('wrong-external','entityExternalId','999')]:
 z=copy.deepcopy(x);z['payload']['filters'][field]=value
 record(name+'-schema',v.is_valid(z),True);record(name+'-semantic',semantic(z['payload'],candidates),'422')
record('revoked-candidate',semantic(x['payload'],[]),'403')
record('stale-version',semantic(x['payload'],candidates,False),'409')
draft=copy.deepcopy(next(x for x in pos if x['schemaKind']=='MappingDraft'))
for ui,wire in [('NEEDS_DECISION','NEEDS_REVIEW'),('PROPOSAL_READY','READY_FOR_PROPOSAL')]:
 draft['payload']['status']=ui;record('reject-workflow-'+ui,v.is_valid(draft),False)
 draft['payload']['status']=wire;record('accept-wire-'+wire,v.is_valid(draft),True)
# Admission boundary precedes constructing/querying a snapshot.
def admission(logged_in,asset_authorized):
 if not logged_in:return {'http':401,'bodyKind':'ProblemDetails','snapshotRead':False}
 if not asset_authorized:return {'http':403,'bodyKind':'ProblemDetails','snapshotRead':False}
 return {'http':200,'bodyKind':'G4QueryResultV1','snapshotRead':True}
record('anonymous-no-snapshot',admission(False,False),{'http':401,'bodyKind':'ProblemDetails','snapshotRead':False})
record('forbidden-no-snapshot',admission(True,False),{'http':403,'bodyKind':'ProblemDetails','snapshotRead':False})
record('authorized-snapshot',admission(True,True),{'http':200,'bodyKind':'G4QueryResultV1','snapshotRead':True})
print(json.dumps({'status':'PASS','scope':'REVIEW_AMENDMENT_SYNTHETIC_DESIGN_ONLY','originalPositivePreserved':21,'originalSchemaNegativePreserved':16,'cases':rows,'caseCount':len(rows),'productRuntime':'NOT_RUN','limitations':['semantic checks are synthetic expected contract behavior, not production guard tests','Datum and rollback schemas remain explicitly blocked for M4/M3 implementation']},ensure_ascii=False,indent=2))
