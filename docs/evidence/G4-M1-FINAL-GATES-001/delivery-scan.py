"""Read-only known-secret scan for this task; no credential values enter results."""
import argparse,base64,hashlib,json,subprocess,zipfile
from pathlib import Path
ROOT=Path('/Users/chasen/.codex/worktrees/g4-m1-final-gates-001/ontology-platform');ART=ROOT/'artifacts/g4-m1-final-gates-001';TASK='G4-M1-FINAL-GATES-001'
p=argparse.ArgumentParser();p.add_argument('--zip',type=Path);args=p.parse_args();patterns=set();rows=[];findings=[]
def walk(v):
    if isinstance(v,dict):
        for k,x in v.items():
            low=k.lower()
            if isinstance(x,str) and len(x)>=8 and any(q in low for q in ('password','secret','token','healthkey')) and not any(q in low for q in ('file','path','expires','version','hash','purpose','status')):patterns.add(x.encode())
            walk(x)
    elif isinstance(v,list):
        for x in v:walk(x)
for name in ['g4-m1-final-gates-001-20261102-01','g4-m1-final-gates-001-r04-20261102','g4-m1-final-gates-001-public-20261102','g4-m1-final-gates-001-r04-final-20261102']:
    private=ROOT/'.tools/security'/name;assert private.is_dir() and not private.is_symlink() and private.stat().st_mode&0o077==0
    for f in private.rglob('*.json'):
        assert not f.is_symlink();walk(json.loads(f.read_text()))
    for rel in ['reader-password','postgres-password','platform-password','keycloak-password','s3-access','s3-secret','server.key','wrong-san.key','api/g4-key','api/keyring.pfx']:
        f=private/rel
        if not f.exists():continue
        assert not f.is_symlink();b=f.read_bytes();assert b;patterns.add(b);patterns.add(base64.b64encode(b))
        if rel.endswith('password') or rel.startswith('s3-'):patterns.add(b.strip())
        if rel.endswith('.key'):patterns.update(x for x in b.splitlines() if len(x)>=32 and not x.startswith(b'-----'))
        if rel=='api/g4-key':patterns.add(b.hex().encode())
def scan(path,raw):
    if any(v in raw for v in patterns):findings.append({'path':path,'category':'known_current_task_private_value'})
    rows.append({'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
if args.zip:
    z=args.zip.resolve();assert z.parent==ROOT/'artifacts/reviews' and z.is_file() and not z.is_symlink()
    with zipfile.ZipFile(z) as archive:
        assert archive.testzip() is None
        for item in archive.infolist():
            if not item.is_dir():scan(item.filename,archive.read(item))
    mode='ZIP';dest=ART/'delivery-zip-scan.json'
else:
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    for rel in sorted(set(paths)-{''}):
        if rel.startswith('docs/evidence/') and not rel.startswith('docs/evidence/'+TASK+'/'):continue
        f=ROOT/rel
        if f.is_symlink():continue
        scan(rel,f.read_bytes())
    scan('Base-to-current.patch',subprocess.check_output(['git','diff','1399364ad1367f3d1bfdee4d9901fdb33b48c15d','--'],cwd=ROOT))
    mode='SOURCE_CURRENT_EVIDENCE_AND_PATCH';dest=ART/'delivery-source-scan.json'
value={'taskId':TASK,'status':'FAIL' if findings else 'PASS','mode':mode,'knownPrivatePatternCount':len(patterns),'findings':findings,'entries':rows,'driverSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Known values from four current-task private directories; original C08 HTTP intake references scanned in-memory by its driver, not recovered after database deletion. Historical P08 browser/SecretRef coverage reused by unchanged inputs. Not a general-purpose secret or vulnerability scanner.'}
with dest.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'status':value['status'],'patterns':len(patterns),'entries':len(rows),'findingPaths':[x['path'] for x in findings]}));raise SystemExit(1 if findings else 0)
