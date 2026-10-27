import subprocess,json,datetime,sys
from pathlib import Path
r=Path(sys.argv[1]);b=r/'docs/evidence/G3-M1-CLOSEOUT-002/master';plan=json.loads((b/'apply-plan-generation2.json').read_text());prior=json.loads((b/'docker-after-health.json').read_text());commands=[]
def query(args):
 p=subprocess.run(['docker']+args,capture_output=True,text=True);commands.append({'command':['docker']+args,'exitCode':p.returncode});return p

def success(args):
 p=query(args)
 if p.returncode:raise RuntimeError('Exact metadata unavailable')
 return p.stdout.strip()
def generation():return {'context':success(['context','show']),'engineId':success(['info','--format','{{.ID}}']),'bridgeId':success(['network','inspect','bridge','--format','{{.Id}}']),'buildxVersion':success(['buildx','version']),'builder':success(['buildx','inspect','desktop-linux'])}
start=generation();listed=success(['buildx','history','ls','--builder','desktop-linux','--format','{{.Ref}}']).splitlines();refs=[x.split('/')[-1] for x in listed];records=[]
fmt='{"Ref":{{printf "%q" .Ref}},"Name":{{printf "%q" .Name}},"Context":{{printf "%q" .Context}},"Dockerfile":{{printf "%q" .Dockerfile}},"VCSRepository":{{printf "%q" .VCSRepository}},"VCSRevision":{{printf "%q" .VCSRevision}},"Status":{{printf "%q" .Status}}}'
for op in plan['operations']:
 if op['type']!='docker-history':continue
 ref=op['target'];p=query(['buildx','history','inspect','--builder','desktop-linux','--format',fmt,ref]);strong=p.returncode==1 and not p.stdout and p.stderr.strip()=='ERROR: no record found for ref "'+ref+'"'
 records.append({'ref':ref,'listed':ref in refs,'inspectExitCode':p.returncode,'exactSupportedNoRecordDiagnostic':strong,'rawStderrSuppressed':True,'status':'PASS' if strong and ref not in refs else 'NOT_VERIFIED'})
end=generation();unchanged=start==end;natural=start['bridgeId']!=prior['bridgeId'];known=start['context']=='desktop-linux' and start['engineId']==plan['historyBackend']['engineId'] and start['buildxVersion']==plan['historyBackend']['buildxVersion'] and 'BuildKit version: v0.34.0' in start['builder'] and 'Driver:        docker' in start['builder'];passed=natural and unchanged and known and all(x['status']=='PASS' for x in records)
x={'observedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS' if passed else 'NOT_VERIFIED','priorObservedAt':prior['observedAt'],'priorGeneration':prior['bridgeId'],'observedNaturalGenerationChange':natural,'generationUnchangedDuringVerification':unchanged,'auditedBackendContractMatched':known,'generation':start,'records':records,'commands':commands,'scope':'Strong exact no-record in an actually different natural bridge generation; no restart/reset/upgrade/prune/database edits invoked. Time elapsed alone is not proof.'};(b/'history-natural-postverify.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps({'status':x['status'],'naturalGenerationChanged':natural,'generationStableDuringCheck':unchanged,'strongAbsence':sum(v['status']=='PASS' for v in records),'total':len(records),'priorGeneration':prior['bridgeId'],'actualGeneration':start['bridgeId']}))
