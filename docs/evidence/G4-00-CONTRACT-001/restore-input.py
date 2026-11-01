"""Reconstruct exact original input payload in a task-owned temporary directory."""
from pathlib import Path
import tempfile,shutil,json,base64,hashlib,subprocess,sys
E=Path(__file__).resolve().parent
side=json.loads((E/'input-original-bytes.json').read_text())
with tempfile.TemporaryDirectory(prefix='g4-00-input-restore-') as temp:
 root=Path(temp)/'input'
 source=E/'input-v1.1'
 assert not any(p.is_symlink() for p in source.rglob('*'))
 shutil.copytree(source,root)
 for n,entry in side['files'].items():
  p=Path(n);assert not p.is_absolute() and '..' not in p.parts
  b=base64.b64decode(entry['base64'],validate=True)
  assert len(b)==entry['bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256']
  (root/n).write_bytes(b)
 original_commit=side['originalArchiveCommit']
 for file in root.rglob('*'):
  if file.is_file():
   relative=file.relative_to(root).as_posix()
   original_blob=subprocess.check_output(['git','show',original_commit+':docs/evidence/G4-00-CONTRACT-001/input-v1.1/'+relative],cwd=E.parents[2])
   assert file.read_bytes()==original_blob,relative
 m=json.loads((root/'MANIFEST.json').read_text())
 assert len(list(p for p in root.rglob('*') if p.is_file()))==24
 for n,entry in m['members'].items():
  b=(root/n).read_bytes();assert len(b)==entry['bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256']
 for script in ['verify_input.py','verify_schema.py']:
  completed=subprocess.run([sys.executable,'-B',str(root/script)],capture_output=True,text=True)
  print(completed.stdout,end='');print(completed.stderr,end='',file=sys.stderr)
  assert completed.returncode==0,(script,completed.returncode)
 print(json.dumps({'status':'ORIGINAL_INPUT_RESTORED_AND_VERIFIED','files':24,'bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),'originalManifestSha256':hashlib.sha256((root/'MANIFEST.json').read_bytes()).hexdigest(),'archiveView':'EOF_NORMALIZED_DERIVATIVE','originalPayload':'EXACTLY_RESTORED','runtime':'NOT_RUN'}))
# TemporaryDirectory removes only this invocation's uniquely owned scratch tree.
