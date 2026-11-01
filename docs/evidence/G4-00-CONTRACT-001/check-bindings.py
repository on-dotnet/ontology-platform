"""Read-only G2/G4 design compatibility checks; not product execution."""
from pathlib import Path
import json, hashlib, re, subprocess
ROOT=Path(__file__).resolve().parents[3]
E=Path(__file__).resolve().parent
S=json.loads((E/'input-v1.1/contracts/g4-proposed-wire-contract.schema.json').read_text())
M=json.loads((ROOT/'docs/contracts/g2-models.json').read_text())['models']
K={x['properties']['schemaKind']['const']:x['properties']['payload'] for x in S['oneOf']}
def fields(n):return [f['name'][0].lower()+f['name'][1:] for f in M[n]['fields']]
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
q=K['G4QueryResultV1']; command=K['ConnectionCreateRequest']['properties']['command']
check('G2 eleven names preserved plus version',set(q['properties'])==set(fields('SemanticQueryResult'))|{'schemaVersion'})
check('all twelve G4 fields required',set(q['required'])==set(q['properties']))
check('G2 candidate seven fields match',set(q['properties']['candidates']['items']['properties'])==set(fields('EntityCandidate')))
check('command four required match',set(command['required'])==set(fields('CommandContext')))
check('create revision exactly zero',command['properties']['expectedRevision'].get('const')==0)
cs=(ROOT/'backend/src/Contracts/OntologyPlatform.Contracts/G2Models.g.cs').read_text()
for n in ('CommandContext','SemanticQueryResult','EntityCandidate','EvidenceRef','AssetVersionSnapshot','SemanticSubSource'):
 check(n+' strict generated DTO',bool(re.search(r'\[JsonUnmappedMemberHandling\(JsonUnmappedMemberHandling.Disallow\)\]\s*public sealed record '+n+r'\b',cs)))
route=(ROOT/'backend/src/Hosts/OntologyPlatform.Api/G2/SemanticEndpoints.cs').read_text()
check('old route and result retained','MapPost("/api/v1/semantic/queries"' in route and '.Produces<SemanticQueryResult>()' in route)
check('G4 route not implemented','/api/v1/data/semantic-queries' not in route)
bind=json.loads((E/'source-binding.json').read_text())
for x in bind['sources']:
 check('frozen-source:'+x['path'],hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()==x['sha256'])
changed=subprocess.check_output(['git','diff','--name-only',bind['baseSha']],cwd=ROOT,text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
allowed=('docs/contracts/g4-','docs/planning/g4-','docs/tasks/G4-00','docs/evidence/G4-00-CONTRACT-001/')
check('only owned paths changed',all(p.startswith(allowed) for p in changed+untracked))
print(json.dumps({'status':'PASS','scope':'STATIC_G2_G4_FIELD_AND_FROZEN_INPUT_BINDING','checks':checks,'count':len(checks),'g2Fields':fields('SemanticQueryResult'),'commandFields':fields('CommandContext'),'candidateFields':fields('EntityCandidate'),'runtime':'NOT_RUN'},ensure_ascii=False,indent=2))
