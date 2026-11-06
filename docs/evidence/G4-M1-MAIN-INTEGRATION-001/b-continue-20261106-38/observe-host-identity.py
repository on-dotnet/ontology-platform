from pathlib import Path
import json,hashlib,subprocess
A=Path(__file__).resolve().parent;r=json.loads((A/'host-monitor-process.json').read_text());pid=str(r['pid'])
rows={}
for field in ['command','lstart']:
 p=subprocess.run(['ps','-p',pid,'-o',field+'='],capture_output=True,text=True,timeout=5);assert p.returncode==0 and not p.stderr;rows[field]=p.stdout.strip()
exe='/opt/homebrew/Cellar/python@3.13/3.13.17/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python'
assert rows['command']==' '.join([exe,*r['command'][1:]])
assert hashlib.sha256(Path(r['command'][2]).read_bytes()).hexdigest()==r['driverSha256']
value={'pid':r['pid'],'actualExecutable':exe,'executableSha256':hashlib.sha256(Path(exe).read_bytes()).hexdigest(),'birth':rows['lstart'],'actualCommand':rows['command'],'driverSha256':r['driverSha256'],'taskId':r['taskId'],'runId':r['runId'],'testedCommit':r['testedCommit'],'purpose':'Read-only identity freeze for later exact owned monitor release; no signal sent.','observerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with (A/'host-monitor-live-identity.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
print(json.dumps({'pid':r['pid'],'birth':rows['lstart'],'signalSent':False}))
