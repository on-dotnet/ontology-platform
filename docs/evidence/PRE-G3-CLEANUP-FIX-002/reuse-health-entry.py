import urllib.request,json,datetime,subprocess
from pathlib import Path
root=Path.cwd();before=json.loads((root/'artifacts/maintenance/PRE-G3-CLEANUP-FIX-002/reuse-probe-before.json').read_text());result={}
for name in ('jena','rustfs','keycloak'):
 url=before['probes'][name]['path']
 try:
  with urllib.request.urlopen(url,timeout=8) as r:result[name]=dict(httpStatus=r.status,path=url)
 except Exception as e:result[name]=dict(status='NOT_READY',errorType=type(e).__name__)
command=before['probes']['postgres']['command'];p=subprocess.run(command,capture_output=True,text=True);result['postgres']=dict(command=command,exitCode=p.returncode)
r=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),prefix=before['prefix'],mode='existing-runtime/no-prepare/no-bootstrap',probes=result)
(root/'docs/evidence/PRE-G3-CLEANUP-FIX-002/reuse-probe-after.json').write_text(json.dumps(r,indent=2)+'\n');assert all(v.get('httpStatus')==200 or v.get('exitCode')==0 for v in result.values());print('4/4 retained environment health probes PASS after cleanup')
