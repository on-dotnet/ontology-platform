"""离线验证候选镜像层并收集原许可证；有界读取、不解包执行、不作完整合规声明。"""
from pathlib import Path,PurePosixPath
import json,hashlib,tarfile,io,zipfile
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'artifacts/g4-m1-final-gates-001/g3-forensics';OUT=ROOT/'docs/evidence/G4-M1-FINAL-GATES-001/images';OUT.mkdir(exist_ok=True)
for name in ['rustfs','fuseki']:
 files=[];jars=[];total=0;blobchecks=[]
 def license_name(n):
  lower=n.lower();return any(x in PurePosixPath(lower).name for x in ['license','licence','notice','copying','copyright']) or '/legal/' in lower or '/common-licenses/' in lower
 def add(path,data,source):
  global total
  if len(data)>2*1024**2 or total+len(data)>32*1024**2:raise RuntimeError('LICENSE_BUDGET')
  total+=len(data);files.append(dict(path=path,source=source,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),text=data.decode('utf8','replace')))
 def jar(data,path,source,depth=0):
  if depth>2:return
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   info=dict(path=path,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),coordinates=[],licensePaths=[])
   for m in z.infolist():
    if m.file_size>64*1024**2 or m.compress_size and m.file_size/m.compress_size>500:continue
    if license_name(m.filename) and m.file_size<2*1024**2:
     add(path+'!/'+m.filename,z.read(m),source);info['licensePaths'].append(m.filename)
    elif m.filename.endswith('pom.properties') and m.file_size<65536:
     info['coordinates'].append(z.read(m).decode('utf8','replace'))
    elif m.filename.endswith('.jar'):
     jar(z.read(m),path+'!/'+m.filename,source,depth+1)
   jars.append(info)
 with tarfile.open(BASE/(name+'.tar')) as outer:
  for m in outer.getmembers():
   if m.isfile() and m.name.startswith('blobs/sha256/'):
    with outer.extractfile(m) as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
    assert h==m.name.split('/')[-1];blobchecks.append(dict(digest='sha256:'+h,bytes=m.size))
  manifest=json.load(outer.extractfile('manifest.json'))[0]
  config=json.load(outer.extractfile(manifest['Config']));assert config['architecture']=='arm64' and config['os']=='linux'
  for layer in manifest['Layers']:
   with tarfile.open(fileobj=outer.extractfile(layer),mode='r|*') as inner:
    for entry in inner:
     path=PurePosixPath(entry.name)
     if path.is_absolute() or '..' in path.parts:raise RuntimeError('UNSAFE_LAYER_PATH')
     if not entry.isfile():continue
     if license_name(entry.name) and entry.size<=2*1024**2:
      add(entry.name,inner.extractfile(entry).read(),layer)
     elif entry.name.endswith(('.jar','.war')) and entry.size<128*1024**2:
      jar(inner.extractfile(entry).read(),entry.name,layer)
 scan=json.loads((BASE/(name+'-sbom.json')).read_text());packages=[{k:p.get(k) for k in ['type','name','version','purl','licenses']} for p in scan['artifacts']]
 result=dict(taskId='G4-M1-FINAL-GATES-001',image=name,platform='linux/arm64',config=manifest['Config'],verifiedBlobs=blobchecks,scannerDigest=scan['source']['image']['digest'],packages=packages,unknownLicenseCount=sum(not p['licenses'] for p in packages),licenseFiles=files,jars=jars,licenseTextBytes=total,coverage='PARTIAL: original layers, selected regular license files, JAR coordinates/notices; no guarantee of final filesystem completeness, Rust statically linked crates, CVE, signatures or distribution obligations.',containerExecution=False)
 (OUT/(name+'-licenses.json')).write_text(json.dumps(result,indent=2)+'\n')
 (OUT/(name+'-sbom.json')).write_bytes((BASE/(name+'-sbom.json')).read_bytes())
 print(json.dumps(dict(image=name,packages=len(packages),unknown=result['unknownLicenseCount'],licenseFiles=len(files),jars=len(jars),licenseTextBytes=total)),flush=True)
