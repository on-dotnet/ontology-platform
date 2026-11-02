"""Default dry-run; remove only six frozen task-generated archive copies after exact revalidation."""
import argparse,datetime as dt,hashlib,json,subprocess
from pathlib import Path
ROOT=Path('/Users/chasen/.codex/worktrees/g4-m1-final-gates-001/ontology-platform');ART=ROOT/'artifacts/g4-m1-final-gates-001';PLAN=ART/'local-archive-cleanup-plan.json'
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--expected-plan-sha256');args=p.parse_args()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def validate(item):
    path=ROOT/item['path'];assert path.is_relative_to(ART) and path.is_file() and not path.is_symlink()
    for parent in path.parents:
        assert not parent.is_symlink()
        if parent==ROOT:break
    s=path.stat();assert [s.st_size,s.st_dev,s.st_ino,s.st_mtime_ns]==[item['bytes'],item['device'],item['inode'],item['mtimeNs']] and sha(path)==item['sha256'];return path
assert not PLAN.is_symlink();plan=json.loads(PLAN.read_text());assert plan['root']==str(ROOT) and plan['taskId']=='G4-M1-FINAL-GATES-001'
allowed={'artifacts/g4-m1-final-gates-001/image-'+str(i)+'.oci.tar' for i in range(4)}|{'artifacts/g4-m1-final-gates-001/g3-forensics/'+n+'.tar' for n in ('rustfs','fuseki')}
assert len(plan['files'])==6 and {v['path'] for v in plan['files']}==allowed
if not args.apply:print(json.dumps({'mode':'DRY_RUN','files':6,'planSha256':sha(PLAN),'deleted':0}));raise SystemExit(0)
assert args.expected_plan_sha256==sha(PLAN) and dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(plan['expiresUtc'])
assert ROOT.resolve()==ROOT
images=[json.loads((ART/('image-'+str(i)+'-restore.json')).read_text())['reference'] for i in range(4)]+['rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b','ontology-platform-fuseki:context-4fbf23514516632dcb651b5c05bf04e9992da52491607b6cf58de1f7348ff9ab']
expected=['9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437','e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4','3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55','a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f','9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b','715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c'];kept=[]
for ref,digest in zip(images,expected):
    obj=json.loads(subprocess.check_output(['docker','--context','desktop-linux','image','inspect',ref,'--format','{{json .}}'],text=True))
    assert obj['Descriptor']['digest']=='sha256:'+digest and obj['Architecture']=='arm64';kept.append({'reference':ref,'id':obj['Id'],'digest':obj['Descriptor']['digest']})
for item in plan['files']:validate(item)
receipt={'taskId':plan['taskId'],'status':'FAIL','planSha256':args.expected_plan_sha256,'driverSha256':sha(Path(__file__)),'keptImages':kept,'deleted':[],'beforeLogicalBytes':sum(x['bytes'] for x in plan['files']),'physicalReclaimedBytes':'NOT_MEASURED'}
try:
    for item in plan['files']:
        path=validate(item);path.unlink();assert not path.exists() and not path.is_symlink();receipt['deleted'].append({**item,'operation':'Path.unlink after fingerprint revalidation','exitCode':0,'absenceVerified':True})
    receipt['status']='PASS';receipt['afterCandidateCount']=0;receipt['deletedLogicalBytes']=sum(x['bytes'] for x in receipt['deleted'])
finally:
    receipt['completedUtc']=dt.datetime.now(dt.timezone.utc).isoformat()
    receipt['remaining']=[x['path'] for x in plan['files'] if (ROOT/x['path']).exists()]
    with (ART/'local-archive-cleanup-receipt.json').open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps({'status':receipt['status'],'deleted':len(receipt['deleted']),'logicalBytes':receipt.get('deletedLogicalBytes')}))
