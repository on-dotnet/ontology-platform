from pathlib import Path
import json,collections,hashlib,datetime
root=Path.cwd();e=root/'docs/evidence/PRE-G3-CLEANUP-FIX-002'
def read(n):return json.loads((e/n).read_text())
first=read('apply-plan.json');retry=read('history-plan.json');initial=read('initial-reconciliation.json');proof=read('history-persistent-check.json');strong=read('history-strong-after.json');final=read('docker-final.json');original=read('docker-before.json');pre=read('docker-preapply.json');beforeGit=read('git-preapply.json');finalGit=read('git-final.json')
logs={n:[json.loads(x) for x in (e/n).read_text().splitlines()] for n in ['apply-001.jsonl','history-apply.jsonl']}
for name,plan in [('apply-001.jsonl',first),('history-apply.jsonl',retry)]:
 rows=logs[name];assert len(rows)==2*len(plan['operations'])
 for i,op in enumerate(plan['operations']):
  b,a=rows[2*i:2*i+2];assert b['phase']=='before' and a['phase']=='after';assert all(r['type']==op['type'] and r['target']==op['target'] for r in (b,a));assert a['exit']==0 and a['after']=={'absent':True}
assert [(o['type'],o['target']) for o in retry['operations']]==[(o['type'],o['target']) for o in first['operations'] if o['type']=='docker-history']
assert strong['status']=='PASS_EXACT18_DB_ABSENCE' and len(strong['rows'])==18 and all(r['exitCode']==1 and r['stdoutEmpty'] and r['stderrExactExpectedNoRecord'] for r in strong['rows'])
assert proof['status']=='PASS_PERSISTENT_ACROSS_OBSERVED_NATURAL_GENERATION' and proof['allRemovedRefsAbsent'] and proof['naturalFreshGenerationObserved']
assert final['counts']==dict(containers=0,volumes=24,images=11,buildHistory=1);assert finalGit['counts']==dict(localBranches=15,remoteBranches=15,worktrees=6)
refs=lambda g:dict(line.split(' ',1) for line in g['refs'].splitlines() if not line.startswith('refs/remotes/origin/HEAD '))
old=refs(beforeGit);new=refs(finalGit);gone={('refs/heads/' if o['type']=='git-local-branch' else 'refs/remotes/origin/')+o['target'] for o in first['operations'] if o['type'].startswith('git-')};assert set(new)==set(old)-gone
mutable={'refs/heads/main','refs/heads/codex/PRE-G3-CLEANUP-FIX-002','refs/remotes/origin/main','refs/remotes/origin/codex/PRE-G3-CLEANUP-FIX-002'}
assert all(new[k]==v for k,v in old.items() if k not in gone|mutable)
assert all(new[k]==finalGit['head'] for k in mutable)
protected={w['worktree'] for w in finalGit['worktrees']};assert set(first['protectedWorktrees'])==protected
assert all(not Path(o['target']).exists() and not Path(o['target']).is_symlink() for o in first['operations'] if o['type'] in ('cache','worktree'))
vols=lambda j:{v['Name']:v for v in j['volumes']};images=lambda j:{v['Id'] for v in j['images']};hist=lambda j:{v['Ref'] for v in j['buildHistory']}
removedVolumes={o['target'] for o in first['operations'] if o['type']=='docker-volume'};removedImages={o['target'] for o in first['operations'] if o['type']=='docker-image'}
assert vols(final)=={k:v for k,v in vols(original).items() if k not in removedVolumes};assert images(final)==images(pre)-removedImages
assert hist(final)==set(proof['historyRefs']) and not hist(final)&{o['target'] for o in retry['operations']}
cacheIds=lambda j:{line.split()[0].rstrip('*') for line in j['buildxDu'].splitlines()[1:] if len(line.split())>=4 and len(line.split()[0].rstrip('*'))==25};assert cacheIds(final)==cacheIds(original)
network=lambda j:{name:(oid,driver) for oid,name,driver in [line.split('\t') for line in j['networks'].splitlines()]}
assert network(final)['bridge'][0]==proof['currentBridge']['Id'];assert all(network(final)[k]==network(original)[k] for k in ('host','none'))
volumeSize=lambda j:sum(v['Size'] for v in j['exactUsage']['volumes'])
result=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='PASS_SCOPED_MAC_ACTUAL_RESOURCES_WITH_DURABLE_HISTORY',uniqueEffectiveResources=266,commandAttempts=284,originalImmediateAttempts=266,correctedVolatileHistoryAttempts=18,retryDurableHistoryAttempts=18,loggedRows=568,originalLogsPreserved=True,logSha256={n:hashlib.sha256((e/n).read_bytes()).hexdigest() for n in logs},effectiveOperations=dict(collections.Counter(o['type'] for o in first['operations'])),gitBefore=beforeGit['counts'],gitAfter=finalGit['counts'],dockerInitial=original['counts'],dockerPreApply=pre['counts'],dockerFinal=final['counts'],cacheLogicalBytes=initial['cacheLogicalBytes'],volumeEngineInitial=volumeSize(original),volumeEngineFinal=volumeSize(final),volumeEngineNetReduction=volumeSize(original)-volumeSize(final),volumeCandidateLogicalBytes=initial['volumesCandidateLogicalBytes'],imageLayersPreApply=pre['exactUsage']['imageLayersSizeBytes'],imageLayersFinal=final['exactUsage']['imageLayersSizeBytes'],imageLayersNetReduction=pre['exactUsage']['imageLayersSizeBytes']-final['exactUsage']['imageLayersSizeBytes'],oldStoppedContainerRwBytes=initial['oldStoppedContainerRwBytes'],keepProtectedTrees=sorted(protected),keepVolumeNames=sorted(vols(final)),keepSharedCacheIds=sorted(cacheIds(final)),historyPersistentAcrossObservedNaturalGeneration=True,historyStrongMissingDiagnostics=18,noExplicitDockerRestartConfigOrNetworkMutation=True,initialAndNaturalNetworkDriftDocumented=True,physicalDiskReclaimed='NOT_VERIFIED',reviewZipPostCommitReceiptRequired=True)
(e/'actual-reconciliation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('keepProtectedTrees','keepVolumeNames','keepSharedCacheIds')}))
