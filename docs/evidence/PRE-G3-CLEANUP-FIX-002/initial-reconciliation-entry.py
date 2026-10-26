"""Initial T1 snapshot-only reconciliation; later history correction is authoritative.
This historical controller is not the final durable-history gate.
"""
from pathlib import Path
import json,collections,hashlib,datetime
root=Path.cwd();e=root/'docs/evidence/PRE-G3-CLEANUP-FIX-002'
def read(n):return json.loads((e/n).read_text())
p=read('apply-plan.json');rows=[json.loads(x) for x in (e/'apply-001.jsonl').read_text().splitlines()];ops=p['operations'];assert len(rows)==len(ops)*2
for i,o in enumerate(ops):
 b,a=rows[2*i:2*i+2];assert b['phase']=='before' and a['phase']=='after';assert all(r['type']==o['type'] and r['target']==o['target'] for r in [b,a]);assert a['exit']==0 and a['after']=={'absent':True}
done=rows[1::2];counts=dict(collections.Counter(r['type'] for r in done))
g0,g1=read('git-preapply.json'),read('git-after.json')
def refs(g):return dict(line.split(' ',1) for line in g['refs'].splitlines() if not line.startswith('refs/remotes/origin/HEAD '))
expected=refs(g0)
for o in ops:
 if o['type'].startswith('git-'):del expected[('refs/heads/' if o['type']=='git-local-branch' else 'refs/remotes/origin/')+o['target']]
assert refs(g1)==expected
wt0={x['worktree'] for x in g0['worktrees']};wt1={x['worktree'] for x in g1['worktrees']};removed={o['target'] for o in ops if o['type']=='worktree'};assert wt1==wt0-removed
assert all(not Path(o['target']).exists() and not Path(o['target']).is_symlink() for o in ops if o['type'] in ('cache','worktree'))
b,a,live=read('docker-preapply.json'),read('docker-after.json'),read('docker-after-live.json')
for key,field,kind in [('volumes','Name','docker-volume'),('images','Id','docker-image'),('buildHistory','Ref','docker-history'),('containers','Id','docker-container')]:
 trim=lambda x:x.split('/')[-1] if kind=='docker-history' else x
 old={trim(v[field]) for v in b[key]};gone={o['target'] for o in ops if o['type']==kind};actual={trim(v[field]) for v in live[key]};assert actual==old-gone,(key,actual,old-gone)
 if key!='containers':assert {trim(v[field]) for v in a[key]}==actual
original=read('docker-before.json');createdContainers={c['Id'] for c in b['containers']}-{c['Id'] for c in original['containers']};assert len(createdContainers)==9;assert {c['Id'] for c in live['containers']}==createdContainers;assert not a['containers']
for v in live['volumes']:
 old=next(x for x in b['volumes'] if x['Name']==v['Name']);assert old==v
assert all(x in wt1 for x in p['protectedWorktrees'])
network=lambda j:{name:(oid,driver) for oid,name,driver in [line.split('\t') for line in j['networks'].splitlines()]}
assert all(network(a)[k]==network(b)[k] for k in ('bridge','host','none'))
cacheIds=lambda j:{line.split()[0].rstrip('*') for line in j['buildxDu'].splitlines()[1:] if len(line.split())>=4 and len(line.split()[0].rstrip('*'))==25};assert cacheIds(a)==cacheIds(original)
volSize=lambda j:sum(v['Size'] for v in j['exactUsage']['volumes']);vRemoved=sum(v['Size'] for v in original['exactUsage']['volumes'] if v['Name'] in {o['target'] for o in ops if o['type']=='docker-volume'})
r=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='PASS_SCOPED_MAC_RESOURCE_ACCEPTANCE',operations=counts,exactCompleted=len(done),logSha256=hashlib.sha256((e/'apply-001.jsonl').read_bytes()).hexdigest(),noFailedEvents=True,noUnapprovedGitOrDockerDeletion=True,protectedTreesPreserved=sorted(wt1),cacheLogicalBytes=sum(x.get('logicalBytes',0) for x in done if x['type']=='cache'),gitBefore=g0['counts'],gitAfter=g1['counts'],dockerInitial=original['counts'],dockerPreApply=b['counts'],dockerAfterApplyLive=live['counts'],dockerFinal=a['counts'],probeCreatedContainers=sorted(createdContainers),probeShutdown='Normal trusted AppHost termination removed only its nine transient containers; named volumes retained.',volumesCandidateLogicalBytes=vRemoved,volumeEngineBefore=volSize(original),volumeEngineAfter=volSize(a),volumeEngineNetReduction=volSize(original)-volSize(a),imageLayersPreApply=b['exactUsage']['imageLayersSizeBytes'],imageLayersAfter=a['exactUsage']['imageLayersSizeBytes'],imageLayersNetReduction=b['exactUsage']['imageLayersSizeBytes']-a['exactUsage']['imageLayersSizeBytes'],oldStoppedContainerRwBytes=sum(x['SizeRw'] for x in original['exactUsage']['containers']),buildCacheIdsRetained=sorted(cacheIds(a)),defaultNetworksPreservedAcrossApplyAndShutdown=True,initialToPreApplyNetworkDrift={k:dict(initial=network(original)[k],preApply=network(b)[k],cause='NOT_VERIFIED; observed before Apply, no network mutation commands') for k in ('bridge','host','none') if network(original)[k]!=network(b)[k]},physicalDiskReclaimed='NOT_VERIFIED',oldZip='Pending exact hash deletion only after final committed ZIP independently reopens; final external delivery receipt records actual effect without Git self-reference.')
(e/'actual-reconciliation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['protectedTreesPreserved','probeCreatedContainers','buildCacheIdsRetained']}))
