from pathlib import Path
import datetime,hashlib,json,os,signal,subprocess,sys,time
root=Path(__file__).resolve().parents[2]
i=int(sys.argv[1]); short=len(sys.argv)>2 and sys.argv[2]=='short'; suffix='.short' if short else ''; maximum_seconds=20 if short else 180; folder=root/'artifacts/g4-m1-recovery-001/forensics'; image=folder/str(i)
assert (image/'receipt.json').is_file()
output=folder/f'image-{i}.sbom.json'; log=folder/f'image-{i}{suffix}.scout.txt'
env=os.environ.copy();env.update(DOCKER_SCOUT_OFFLINE='true',DOCKER_SCOUT_CACHE_DIR=str(folder/'scout-cache'),DOCKER_SCOUT_NEW_VERSION_WARN='false')
cmd=['docker','--context','desktop-linux','scout','sbom','--format','json','--platform','linux/arm64','--output',str(output),'oci-dir://'+str(i)]
started=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat(); status='RUNNING'; peak=0
with log.open('wb') as f:
 p=subprocess.Popen(cmd,cwd=folder,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 while p.poll() is None:
  size=sum(x.stat().st_size for x in folder.rglob('*') if x.is_file() and not x.is_symlink());peak=max(peak,size)
  if size>12*1024**3 or time.monotonic()-started>maximum_seconds:
   status='DISK_LIMIT' if size>12*1024**3 else 'TIMEOUT';os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   break
  time.sleep(1)
rc=p.returncode
receipt=dict(command=cmd,exitCode=rc,status='COMPLETED' if status=='RUNNING' else status,startedAtUtc=utc,elapsedSeconds=time.monotonic()-started,peakObservedTaskBytes=peak,offline=True,cacheDir=str(folder/'scout-cache'),image=json.loads((image/'receipt.json').read_text()))
if output.exists():receipt.update(sbomSha256=hashlib.sha256(output.read_bytes()).hexdigest(),sbomBytes=output.stat().st_size)
(folder/f'image-{i}{suffix}.scan-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));sys.exit(rc if rc else 0)
