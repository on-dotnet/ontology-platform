"""Read-only, exact M1 post-cleanup reconciliation; no credentials or volume contents."""
import argparse,json,subprocess
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root.resolve();ev=root/'docs/evidence/G3-M1-001/master'
    plan=json.loads((ev/'cleanup-plan.json').read_text())
    before=json.loads((ev/'resources-before.json').read_text());pre=json.loads((ev/'resources-pre-apply.json').read_text());after=json.loads((ev/'resources-after.json').read_text())
    logs=[json.loads(line) for line in (ev/'cleanup-apply.jsonl.txt').read_text().splitlines()]
    targets={op['target']:op for op in plan['operations']}
    assert len(targets)==40 and all(op['type']=='docker-volume' and name.startswith('g3-m1-') for name,op in targets.items())
    first=[row for row in logs if row['phase']=='before'];last=[row for row in logs if row['phase']=='after']
    assert len(first)==len(last)==40 and {r['target'] for r in first}=={r['target'] for r in last}==set(targets)
    for row in first:
        op=targets[row['target']]
        assert row['command']==['docker','volume','rm',row['target']] and row['before']['references']==[]
        assert row['before']['Driver']==op['expectedDriver'] and row['before']['CreatedAt']==op['expectedCreatedAt']
    for row in last: assert row['exit']==0 and row['after']=={'absent':True} and row['command']==['docker','volume','rm',row['target']]
    def volumes(inventory): return {line.split('\t')[0] for line in inventory['docker']['queries']['volumes']['text'].splitlines() if line.strip()}
    protected_volumes=volumes(before);assert len(protected_volumes)==24
    assert volumes(pre)==protected_volumes|set(targets) and volumes(after)==protected_volumes
    protected_trees={row['path'] for row in before['worktrees'] if '/g3-m1-' not in row['path']}
    assert len(protected_trees)==6
    expected_trees=protected_trees|{str(root)}
    assert len(pre['worktrees'])==10 and {row['path'] for row in after['worktrees']}==expected_trees
    aliases={'refs/heads/main','refs/remotes/origin/main','refs/remotes/origin/HEAD'}
    old_refs={row['ref']:row['tip'] for row in before['refs'] if 'codex/g3-m1-' not in row['ref'] and row['ref'] not in aliases}
    after_refs={row['ref']:row['tip'] for row in after['refs']}
    assert all(after_refs.get(name)==tip for name,tip in old_refs.items())
    for row in pre['refs']:
        if any('codex/g3-m1-'+short in row['ref'] for short in ['sem','web','fix']): assert after_refs.get(row['ref'])==row['tip']
    native=json.loads((ev/'native-archive.json').read_text());artifacts=json.loads(native['afterArtifacts']['content'][0]['text'])['artifacts']
    archived={row['identityKey'] for row in artifacts if row['attachmentType']=='archived_worktree'}
    workers={str(Path('/Users/chasen/.codex/worktrees/g3-m1-'+short+'/ontology-platform')) for short in ['sem','web','fix']}
    assert archived==workers and all(not Path(path).exists() for path in workers)
    assert {row['identityKey'] for row in artifacts if row['attachmentType']=='worktree'}=={str(root)}
    assert all(item['cliExitCode'] is None and item['response']['isError'] is False for item in native['requests'])
    assert all(Path(path).exists() for path in expected_trees)
    live_volumes=set(subprocess.check_output(['docker','volume','ls','--quiet'],text=True).splitlines())
    assert protected_volumes<=live_volumes and not set(targets)&live_volumes
    live_worktrees=subprocess.check_output(['git','worktree','list','--porcelain'],cwd=root,text=True)
    live_paths={line[len('worktree '):] for line in live_worktrees.splitlines() if line.startswith('worktree ')}
    assert live_paths==expected_trees
    reader=json.loads((root/'docs/evidence/G3-M1-001/closeout-restoration/compatibility-binary.json').read_text())
    assert reader['status']=='PASS' and reader['exitCode']==0 and reader['memberCount']==126 and reader['readerUnchanged']
    ignored=json.loads((ev/'worker-ignored-prearchive.json').read_text())
    logical=sum(cache['logicalRegularBytes'] for worker in ignored['workers'] for cache in worker['ignored'])
    result={'status':'PASS','exactNamedVolumesRemoved':40,'nativeWorkerTreesArchived':3,'applyRows':len(logs),'worktrees':{'pre':10,'after':7},'namedVolumes':{'pre':64,'after':24},'refs':{'pre':len(pre['refs']),'after':len(after['refs']),'protectedHistoricalTipsUnchanged':True,'taskWorkerRefsKept':True},'protectedOldTrees':6,'protectedG2Volumes':24,'workerIgnoredLogicalRegularBytesWithoutHardlinkDedup':logical,'nativeApiCliExitCodes':None,'retainedReader':reader,'dockerVolumeReclaimedBytes':'NOT_MEASURED; log logicalBytes=0 is an unavailable-size placeholder','physicalSsdReclamation':'NOT_VERIFIED','oldG2ServicesRestarted':False}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
