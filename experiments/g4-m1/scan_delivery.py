"""在内存匹配真实合成秘密；只输出路径/类别/散列，不输出秘密值。"""
from pathlib import Path
import argparse,base64,hashlib,json,re,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001';PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01';TASK='G4-M1-RECOVERY-001'
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,value):
    with open(path,'x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--zip');args=parser.parse_args();patterns=set();findings=[];entries=[]
    assert PRIVATE.resolve()==PRIVATE and not PRIVATE.is_symlink() and PRIVATE.stat().st_mode&0o077==0
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                key=key.lower()
                if isinstance(item,str) and any(x in key for x in ('password','secret','token','healthkey')) and not any(x in key for x in ('file','path','expires','owner','version','configured','hash')) and len(item)>=8:patterns.add(item.encode())
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    for file in PRIVATE.rglob('*.json'):
        assert not file.is_symlink()
        try:walk(json.loads(file.read_text()))
        except (UnicodeError,ValueError):pass
    for name in ('reader-password','postgres-password','platform-password','keycloak-password','rotation-password','server.key','wrong-san.key','api/keyring.pfx','api/g4-key'):
        file=PRIVATE/name;assert not file.is_symlink();raw=file.read_bytes();assert raw;patterns.add(raw)
        if name.endswith('password'):patterns.add(raw.rstrip(b'\r\n'))
        if name.endswith('.key'):
            patterns.update(line for line in raw.splitlines() if len(line)>=32 and not line.startswith(b'-----'))
        if name.endswith('.pfx'):patterns.add(base64.b64encode(raw))
        if name.endswith('g4-key'):patterns.add(base64.b64encode(raw));patterns.add(raw.hex().encode())
    private_index=ART/'reference-hashes-for-zip-scan.json'
    docker=['docker','--context','desktop-linux'];commands=[]
    if args.zip:
        reference_hashes=set(json.loads(private_index.read_text())['hashes'])
    else:
        platform=json.loads(subprocess.check_output(docker+['inspect','ontology-g4-m1-recovery-001-platform-pg-1'],text=True,timeout=5))[0]
        assert platform['Config']['Labels']['ontology.task-id']==TASK and platform['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
        argv=docker+['exec','-i',platform['Id'],'psql','-U','platform','-d','platform','-qAt','-v','ON_ERROR_STOP=1'];result=subprocess.run(argv,input='SET statement_timeout=\'2s\';SELECT "Id" FROM connections."ConnectionSecrets";',capture_output=True,text=True,timeout=5)
        commands.append(dict(command=argv,operation='Read reference IDs only in memory; persist hashes only',exitCode=result.returncode));assert result.returncode==0
        references=result.stdout.splitlines();assert all(re.fullmatch('[a-f0-9]{32}',x) for x in references);reference_hashes={sha(x.encode()) for x in references};references=None
        write(private_index,dict(hashes=sorted(reference_hashes),scope='Only one-way hashes of synthetic references; no reference value.'))
    def scan(label,data):
        categories=[]
        if any(x in data for x in patterns):categories.append('known_synthetic_credential')
        if any(sha(x) in reference_hashes for x in re.findall(rb'(?<![a-f0-9])[a-f0-9]{32}(?![a-f0-9])',data)):categories.append('raw_secret_reference')
        if categories:findings.append(dict(path=label,categories=categories))
        entries.append(dict(path=label,bytes=len(data),sha256=sha(data)))
        return not categories
    if args.zip:
        package=Path(args.zip).resolve();assert package.is_relative_to(ROOT/'artifacts/reviews') and package.is_file() and not package.is_symlink()
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
            for item in archive.infolist():
                if not item.is_dir():scan(item.filename,archive.read(item))
        output=ART/'delivery-zip-sensitive-scan.json'
    else:
        own=subprocess.check_output(docker+['ps','-a','--filter','label=ontology.task-id='+TASK,'--format','{{.ID}}'],text=True,timeout=5).splitlines()
        for identity in own:
            obj=json.loads(subprocess.check_output(docker+['inspect',identity],text=True,timeout=5))[0];assert obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
            argv=docker+['logs',obj['Id']];x=subprocess.run(argv,capture_output=True,timeout=10);assert x.returncode==0;raw=x.stdout+x.stderr;label='runtime-log/'+obj['Name'].lstrip('/')
            commands.append(dict(command=argv,exitCode=x.returncode,bytes=len(raw)))
            if scan(label,raw):write(ART/(obj['Name'].lstrip('/')+'-log.raw.json'),dict(containerId=obj['Id'],command=argv,exitCode=x.returncode,rawBytes=len(raw),rawSha256=sha(raw),rawUtf8=raw.decode()))
        tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
        for relative in sorted(set(tracked)-{''}):
            if relative.startswith('docs/evidence/') and not relative.startswith('docs/evidence/'+TASK+'/'):continue
            file=ROOT/relative
            if file.is_symlink():continue
            assert file.is_file();scan(relative,file.read_bytes())
        diff=subprocess.check_output(['git','diff','59edb405dfb4acf4d4a259cffdc3551bafa90d2c','--'],cwd=ROOT);scan('Base-to-current-worktree.patch',diff)
        output=ART/'delivery-source-sensitive-scan.json'
    report=dict(taskId=TASK,status='FAIL' if findings else 'PASS',mode='ZIP' if args.zip else 'SOURCE_AND_REAL_RUNTIME_LOGS',knownPrivatePatternCount=len(patterns),referenceHashCount=len(reference_hashes),findings=findings,commands=commands,entries=entries,scope='Exact known synthetic passwords/keys/tokens and all persisted SecretRef IDs; HTTP reports include trace/audit observations. This is not a general-purpose secret or CVE scanner.')
    write(output,report);print(json.dumps(dict(status=report['status'],entries=len(entries),findingPaths=[x['path'] for x in findings])))
    if findings:raise SystemExit(1)
if __name__=='__main__':main()
