"""只读当前准确任务容器中的合成状态与审计，不读取秘密表或业务行。"""
from pathlib import Path
import subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts/g4-m1-final-gates-001';TASK='G4-M1-FINAL-GATES-001'
reports=[json.loads(p.read_text()) for p in (OUT/'c08').glob('http-*/report.json')];report=next(r for r in reversed(reports) if r['exitCode']==0);connection=report['fixtures']['connectionId'];assert len(connection)==32 and all(x in '0123456789abcdef' for x in connection)
def query(service,user,database,sql):
 name='ontology-g4-m1-final-gates-001-'+service+'-1';i=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect',name],text=True))[0]
 assert i['Config']['Labels'].get('ontology.task-id')==TASK and i['Config']['Labels'].get('ontology.run-id')=='final-gates-20261102-01'
 cmd=['docker','--context','desktop-linux','exec','-i',i['Id'],'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U',user,'-d',database]
 p=subprocess.run(cmd,input='BEGIN READ ONLY;\n'+sql+';\nROLLBACK;\n',capture_output=True,text=True,timeout=15)
 assert p.returncode==0,'READBACK_FAILED'
 return dict(containerId=i['Id'],exitCode=p.returncode,sqlSha256=hashlib.sha256(sql.encode()).hexdigest(),result=json.loads(p.stdout.strip()))
source=query('pg-source','postgres','fixture',"""SELECT json_build_object('database',current_database(),'readerExists',EXISTS(SELECT 1 FROM pg_roles WHERE rolname='fixture_reader'),'publicObjects',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public')+(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')+(SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public'),'publicUsage',has_schema_privilege('fixture_reader','public','USAGE'),'publicCreate',has_schema_privilege('fixture_reader','public','CREATE'),'productionSelect',has_table_privilege('fixture_reader','production.heat_event','SELECT'),'databaseCreateTemp',has_database_privilege('fixture_reader','fixture','CREATE,TEMP'))""")
create_trace=next(x['traceId'] for x in report['http'] if x['route']=='/api/v1/connections' and x['method']=='POST' and x['status']==201);assert all(x in '0123456789abcdef' for x in create_trace)
state=query('platform-pg','platform','platform',f'''SELECT json_build_object('connection',(SELECT json_build_object('id',"Id",'revision',"Revision",'configHash',"ConfigHash",'state',"State",'lastProbeId',"LastProbeId",'secretVersion',"SecretVersion",'config',"ConfigJson"::json) FROM connections."Connections" WHERE "Id"='{connection}'),'probes',(SELECT json_agg(json_build_object('id',"Id",'revision',"Revision",'configHash',"ConfigHash",'secretVersion',"SecretVersion",'report',"ReportJson"::json)) FROM connections."ConnectionProbes" WHERE "ConnectionId"='{connection}'),'audits',(SELECT json_agg(json_build_object('action',"Action",'outcome',"Outcome",'traceId',"TraceId")) FROM governance.audit_records WHERE "Resource"='connection:{connection}' OR ("Action"='connection.create' AND "TraceId"='{create_trace}')))''')
facts=source['result'];assert facts['publicObjects']==0 and facts['publicUsage'] and not facts['publicCreate'] and facts['productionSelect'] and not facts['databaseCreateTemp']
s=state['result'];assert s['connection']['state']=='DISABLED' and s['connection']['lastProbeId'] is None and len(s['probes'])==3
from collections import Counter
counts=Counter(x['action'] for x in s['audits'] if x['outcome']=='allowed');assert counts['connection.update']==3 and counts['connection.create']==1 and counts['connection.disable']==1 and counts['connection.enable']==1 and counts['connection.probe.start']==3 and counts['connection.probe.complete']==3
for flow in report['flow']:
 if 'probeId' in flow:
  p=next(v for v in s['probes'] if v['id']==flow['probeId']);assert p['revision']==flow['revision'] and p['configHash']==flow['configHash'] and p['secretVersion']==flow['secretVersion']
receipt=dict(taskId=TASK,status='PASS',source=source,persistence=state,auditCounts=dict(counts),reportFlow=report['flow'])
(OUT/'c08-readback.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status='PASS',publicEmpty=True,probeCount=3,auditCounts=dict(counts))))
