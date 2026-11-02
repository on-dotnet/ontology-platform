"""仅在新建精确PG合成夹具逐项注入public边界故障；不接收任意SQL/资源。"""
from pathlib import Path
import importlib.util,json,subprocess,time,hashlib,sys
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-final-gates-001/public';PRIVATE=ROOT/'.tools/security/g4-m1-final-gates-001-public-20261102';TASK='G4-M1-FINAL-GATES-001';RUN='final-gates-20261102-public';PROJECT='ontology-g4-m1-final-gates-001-public';D=['docker','--context','desktop-linux'];records=[]
def identity(service):
    o=json.loads(subprocess.check_output(D+['inspect',PROJECT+'-'+service+'-1'],text=True))[0]
    assert o['Config']['Labels']['ontology.task-id']==TASK and o['Config']['Labels']['ontology.run-id']==RUN
    return o['Id']
def sql(text):
    argv=D+['exec','-i',identity('pg-source'),'psql','-U','postgres','-d','fixture','-qAt','-v','ON_ERROR_STOP=1']
    x=subprocess.run(argv,input="SET statement_timeout='3s';"+text,capture_output=True,text=True,timeout=10);records.append({'operation':'controlled_public_fixture_sql','sql':text,'command':argv,'exitCode':x.returncode,'stdout':x.stdout,'stderr':x.stderr});assert x.returncode==0;return x.stdout.strip()
def state():
    return json.loads(sql("""SELECT json_build_object('publicExists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='public'),'relations',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),'functions',(SELECT count(*) FROM pg_proc c JOIN pg_namespace n ON n.oid=c.pronamespace WHERE n.nspname='public'),'types',(SELECT count(*) FROM pg_type c JOIN pg_namespace n ON n.oid=c.typnamespace WHERE n.nspname='public'),'usage',(SELECT has_schema_privilege('fixture_reader',oid,'USAGE') FROM pg_namespace WHERE nspname='public'),'create',(SELECT has_schema_privilege('fixture_reader',oid,'CREATE') FROM pg_namespace WHERE nspname='public'),'productionCatalog', (SELECT md5(string_agg(c.relname||':'||a.attname||':'||format_type(a.atttypid,a.atttypmod),',' ORDER BY c.relname,a.attnum)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='production' AND a.attnum>0 AND NOT a.attisdropped));"""))
def test(name,expected):
    before=state();argv=D+['exec','-e','G4_PUBLIC_EXPECTATION='+expected,identity('pg-adapter-test'),'dotnet','/tests/OntologyPlatform.ConnectionsTests.dll','--filter','FullyQualifiedName~ExactPublicSchemaBoundaryUsesActualCatalog','--minimum-expected-tests','1','--results-directory','/tmp/TestResults','--no-ansi','--output','Detailed']
    x=subprocess.run(argv,capture_output=True,text=True,timeout=40);row={'name':name,'expected':expected,'before':before,'command':argv,'exitCode':x.returncode,'stdout':x.stdout,'stderr':x.stderr};records.append(row);assert x.returncode==0 and '已跳过: 1' not in x.stdout;return before
ART.mkdir(exist_ok=True)
report={'taskId':TASK,'runId':RUN,'status':'FAIL','commands':records,'testedCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'driverSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
try:
    for attempt in range(20):
        ready=subprocess.run(D+['exec',identity('pg-source'),'pg_isready','-U','postgres','-d','fixture'],capture_output=True)
        if ready.returncode==0:break
        time.sleep(1)
    assert ready.returncode==0
    baseline=test('empty_public_baseline','PASS')
    for name,setup,restore in [('relation','CREATE TABLE public.g4_boundary (id integer);','DROP TABLE public.g4_boundary;'),('function','CREATE FUNCTION public.g4_boundary() RETURNS integer LANGUAGE SQL AS $$ SELECT 1 $$; REVOKE ALL ON FUNCTION public.g4_boundary() FROM PUBLIC;','DROP FUNCTION public.g4_boundary();'),('type',"CREATE TYPE public.g4_boundary AS ENUM ('synthetic');",'DROP TYPE public.g4_boundary;'),('missing','DROP SCHEMA public;','CREATE SCHEMA public AUTHORIZATION pg_database_owner; REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO PUBLIC;'),('usage','REVOKE USAGE ON SCHEMA public FROM PUBLIC,fixture_reader;','GRANT USAGE ON SCHEMA public TO PUBLIC;')]:
        sql(setup)
        try:test(name,'catalog_permission_limited' if name=='usage' else 'catalog_access_forbidden')
        finally:sql(restore)
        assert state()==baseline
    restored=test('empty_public_restored','PASS');assert restored==baseline
    report.update(status='PASS',baseline=baseline,restored=restored,states=7)
finally:
    try:report['sourceFinal']=state()
    except Exception as error:report['sourceFinalFailure']=type(error).__name__
    with open(ART/('public-faults-'+str(time.time_ns())+'.json'),'x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':report['status'],'states':report.get('states')}))
