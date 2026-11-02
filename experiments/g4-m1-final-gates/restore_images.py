"""复验旧获审OCI每层后仅本地恢复四精确ARM64镜像；零网络、零容器执行。"""
from pathlib import Path
import hashlib,json,io,tarfile,subprocess
ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path('/Users/chasen/.codex/worktrees/g4-m1-recovery-001/ontology-platform/artifacts/g4-m1-recovery-001/forensics')
OUT=ROOT/'artifacts/g4-m1-final-gates-001'
CANDIDATES=ROOT/'docs/evidence/G4-M1-RECOVERY-001/input/evidence/image-candidates.json'
assert hashlib.sha256(CANDIDATES.read_bytes()).hexdigest()=='6f8cde18b311d9e4f1f7f3ef82375890910078d82cbc8ca2d2eeef9ee23143a7'
receipts=[]
for i,c in enumerate(json.loads(CANDIDATES.read_text())):
 directory=SOURCE/str(i)
 def blob(d):
  p=directory/'blobs/sha256'/d['digest'].removeprefix('sha256:')
  assert not p.is_symlink() and p.is_file()
  b=p.read_bytes();assert len(b)==d['size'] and 'sha256:'+hashlib.sha256(b).hexdigest()==d['digest']
  return b
 index=(directory/'official-index.json').read_bytes()
 assert 'sha256:'+hashlib.sha256(index).hexdigest()==c['indexDigest']
 expected=next(v for v in c['platforms'] if v['platform']['architecture']=='arm64')
 d=next(v for v in json.loads(index)['manifests'] if v['digest']==expected['digest'])
 assert d['platform']==expected['platform']
 manifest=json.loads(blob(d)); config=json.loads(blob(manifest['config']))
 assert config['architecture']=='arm64' and config['os']=='linux'
 descriptors=[d,manifest['config'],*manifest['layers']]
 for descriptor in descriptors:blob(descriptor)
 ref=c['reference'].rsplit(':',1)[0]+'@'+d['digest']
 d=dict(d,annotations={**d.get('annotations',{}),'io.containerd.image.name':ref,'org.opencontainers.image.ref.name':ref})
 archive=OUT/f'image-{i}.oci.tar'
 with tarfile.open(archive,'w') as tar:
  for name,data in [('oci-layout',b'{"imageLayoutVersion":"1.0.0"}'),('index.json',json.dumps(dict(schemaVersion=2,manifests=[d])).encode())]:
   item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
  for descriptor in descriptors:
   name='blobs/sha256/'+descriptor['digest'][7:];tar.add(directory/name,arcname=name,recursive=False)
 cmd=['docker','--context','desktop-linux','image','load','--platform','linux/arm64','--input',str(archive)]
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
 record=dict(taskId='G4-M1-FINAL-GATES-001',reference=ref,platformDigest=d['digest'],configDigest=manifest['config']['digest'],verifiedBlobCount=len(descriptors),downloadBytes=0,command=cmd,exitCode=run.returncode,stdout=run.stdout,stderr=run.stderr,containerExecution=False)
 assert run.returncode==0, 'LOAD_FAILED'
 actual=json.loads(subprocess.check_output(['docker','--context','desktop-linux','image','inspect',ref],text=True))[0]
 record['actual']={k:actual.get(k) for k in ['Id','RepoDigests','Os','Architecture','Descriptor']}
 assert actual['Architecture']=='arm64' and actual['Os']=='linux' and actual['Descriptor']['digest']==d['digest']
 (OUT/f'image-{i}-restore.json').write_text(json.dumps(record,indent=2)+'\n');receipts.append(record)
 print(json.dumps(dict(reference=ref,status='LOCAL_RESTORE_VERIFIED',downloadBytes=0)),flush=True)
(OUT/'images-restored.json').write_text(json.dumps(receipts,indent=2)+'\n')
