"""对准确本任务只读角色执行有界权限故障并恢复原ACL。"""
from pathlib import Path
import subprocess,json,os,hashlib,time
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01'
records=[]
def db(sql):
 obj=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','ontology-g4-m1-recovery-001-pg-source-1'],text=True))[0]
 assert obj['Config']['Labels']['ontology.task-id']=='G4-M1-RECOVERY-001' and obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
 cmd=['docker','--context','desktop-linux','exec','-i',obj['Id'],'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt']
 x=subprocess.run(cmd,input="SET lock_timeout='2s'; SET statement_timeout='5s';"+sql,text=True,capture_output=True,timeout=10)
 records.append(dict(command=cmd,sql=sql,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==0
 return x.stdout.strip()
def run(cmd,deadline=90):
 x=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=deadline)
 records.append(dict(command=cmd,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr))
 return x
runtime=json.loads((PRIVATE/'runtime.json').read_text())
runtime.update(scenario='source-permission-limited',httpScenario='source-permission-limited',connectionId='1bf23f9d36bf4ceba09d745f04d8f743',httpConnectionId='1bf23f9d36bf4ceba09d745f04d8f743')
file=PRIVATE/'permission-fault.json'
if file.exists():
 assert not file.is_symlink() and file.stat().st_mode&0o077==0 and json.loads(file.read_text())==runtime
else:
 with open(file,'x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(runtime,stream)
assert run(['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(file),'--action','probe-refresh']).returncode==0
query="SELECT nspacl::text FROM pg_namespace WHERE nspname='production';"
before=db(query);assert db("SELECT has_schema_privilege('fixture_reader','production','USAGE');")=='t'
try:
 db('REVOKE USAGE ON SCHEMA production FROM fixture_reader;')
 assert db("SELECT has_schema_privilege('fixture_reader','production','USAGE');")=='f'
 browser=run(['node','scripts/acceptance/g4-m1-browser.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'browser')])
 http=run(['node','scripts/acceptance/g4-m1-http.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'http')])
finally:
 db('GRANT USAGE ON SCHEMA production TO fixture_reader;')
 after=db(query);assert before==after
 refresh=run(['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(file),'--action','probe-refresh'])
 result=dict(taskId='G4-M1-RECOVERY-001',status='PASS' if locals().get('browser') and browser.returncode==2 and http.returncode==2 and refresh.returncode==0 else 'FAIL',cleanup='PASS',beforeAcl=before,afterAcl=after,driverSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),commands=records)
 with open(ART/'permission-fault-fixed.json','x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print(json.dumps(dict(status=result['status'],cleanup=result['cleanup'])))
