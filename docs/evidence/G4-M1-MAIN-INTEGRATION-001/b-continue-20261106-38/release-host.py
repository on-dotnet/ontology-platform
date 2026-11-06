import hashlib,json,os,signal,subprocess,time
from pathlib import Path
A=Path(__file__).resolve().parent
record=json.loads((A/'host-monitor-process.json').read_text());pid=record['pid']
before=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=5)
actual_executable='/opt/homebrew/Cellar/python@3.13/3.13.17/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python'
expected=' '.join([actual_executable,*record['command'][1:]])
birth=subprocess.run(['ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True,timeout=5)
assert birth.returncode==0 and birth.stdout.strip()==json.loads((A/'host-monitor-live-identity.json').read_text())['birth'] and not birth.stderr
assert hashlib.sha256(Path(record['command'][2]).read_bytes()).hexdigest()==record['driverSha256']
assert before.returncode==0 and before.stdout.strip()==expected and not before.stderr
identity=hashlib.sha256(before.stdout.encode()).hexdigest()
os.kill(pid,signal.SIGTERM)
for _ in range(40):
 after=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=5)
 if after.returncode==1 and not after.stdout and not after.stderr:break
 time.sleep(.25)
assert after.returncode==1 and not after.stdout and not after.stderr
summary=A/'host-monitor.summary.json';assert summary.is_file()
value={'status':'PASS','executorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'before':{'pid':pid,'commandSha256':identity,'psExit':0,'birth':birth.stdout.strip(),'actualExecutable':actual_executable},'signal':'SIGTERM','after':{'psExit':after.returncode,'stdoutEmpty':True,'stderrEmpty':True},'summarySha256':hashlib.sha256(summary.read_bytes()).hexdigest()}
with (A/'host-monitor-released.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
print('EXACT_HOST_MONITOR_RELEASED')
