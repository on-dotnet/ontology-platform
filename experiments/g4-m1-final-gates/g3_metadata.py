"""仅取固定RustFS官方index与ARM64清单，沿既有受限下载器累计预算。"""
from pathlib import Path
import importlib.util,json,hashlib,re,urllib.parse
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('forensics',ROOT/'experiments/g4-m1/forensic_images.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
out=ROOT/'artifacts/g4-m1-final-gates-001/g3-forensics'
d=f.Download(out/'metadata');d.state['taskId']='G4-M1-FINAL-GATES-001';d.save()
base='https://registry-1.docker.io/v2/rustfs/rustfs';digest='sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b';token=None
try:b=d.get(base+'/manifests/'+digest,128*1024)
except f.AuthenticationRequired as err:
 fields=dict(re.findall(r'(\w+)="([^"]*)"',str(err)));realm=fields.pop('realm');assert realm=='https://auth.docker.io/token'
 token=json.loads(d.get(realm+'?'+urllib.parse.urlencode(fields),16*1024))['token'];b=d.get(base+'/manifests/'+digest,128*1024,token,'registry-1.docker.io')
assert 'sha256:'+hashlib.sha256(b).hexdigest()==digest
(out/'rustfs-official-index.json').write_bytes(b)
descriptor=next(x for x in json.loads(b)['manifests'] if x.get('platform',{}).get('architecture')=='arm64' and x['platform']['os']=='linux')
m=d.get(base+'/manifests/'+descriptor['digest'],descriptor['size'],token,'registry-1.docker.io')
assert 'sha256:'+hashlib.sha256(m).hexdigest()==descriptor['digest']
(out/'rustfs-official-platform.json').write_bytes(m)
print(json.dumps(dict(indexDigest=digest,platformDigest=descriptor['digest'],configDigest=json.loads(m)['config']['digest'],receivedBytes=d.state['receivedBytes'],reservedBytes=d.state['reservedBytes'])))
