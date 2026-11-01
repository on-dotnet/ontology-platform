from pathlib import Path,PurePosixPath
import hashlib,json,tarfile,sys,collections
root=Path(__file__).resolve().parents[2];i=int(sys.argv[1]);folder=root/'artifacts/g4-m1-recovery-001/forensics'; image=folder/str(i)
sbom=folder/f'image-{i}.sbom.json';scan=json.loads(sbom.read_text()); receipt=json.loads((image/'receipt.json').read_text());assert scan['source']['image']['digest']==receipt['platformDigest']
manifest=scan['source']['image']['manifest'];files=[];total=0
for layer in manifest['layers']:
 blob=image/'blobs/sha256'/layer['digest'][7:]
 with tarfile.open(blob,'r|gz') as tar:
  for entry in tar:
   path=PurePosixPath(entry.name);name=path.name.lower()
   if path.is_absolute() or '..' in path.parts: continue
   candidate=(str(path).startswith(('usr/share/doc/','usr/share/licenses/','usr/share/common-licenses/','opt/keycloak/','usr/share/dotnet/','usr/local/')) and (name in ('copyright','license','license.txt','licence','copying','notice','notice.txt','third-party-notices.txt','thirdpartynotices.txt') or str(path).startswith('usr/share/common-licenses/')))
   if not candidate:continue
   record=dict(path=str(path),layerDigest=layer['digest'],size=entry.size,type='file' if entry.isfile() else 'link' if entry.issym() or entry.islnk() else 'other')
   if entry.isfile() and entry.size<=2*1024**2 and total+entry.size<=32*1024**2:
    data=tar.extractfile(entry).read();total+=len(data);record.update(sha256=hashlib.sha256(data).hexdigest(),text=data.decode('utf-8','replace'))
   elif entry.issym() or entry.islnk():record['linkTarget']=entry.linkname
   files.append(record)
packages=[{k:p.get(k) for k in ('type','namespace','name','version','purl','licenses','locations')} for p in scan['artifacts']]
out=root/'docs/evidence/G4-M1-RECOVERY-001/images';out.mkdir(exist_ok=True)
(out/f'{i}-sbom.json').write_bytes(sbom.read_bytes())
(out/f'{i}-licenses.json').write_text(json.dumps(dict(image=receipt,sourceSbomSha256=hashlib.sha256(sbom.read_bytes()).hexdigest(),packageCount=len(packages),unknownLicenseCount=sum(not p.get('licenses') for p in packages),packages=packages,licenseFiles=files,licenseTextBytes=total,coverage='Scanner inventory and bounded selected regular license files across original layers; layer order retained, symlinks indexed only; no container execution. No completeness or CVE-free assertion.'),indent=2)+'\n')
print(json.dumps(dict(image=i,packages=len(packages),unknown=sum(not p.get('licenses') for p in packages),files=len(files),textBytes=total)))
