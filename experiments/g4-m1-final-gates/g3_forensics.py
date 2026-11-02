"""G3两精确本地候选镜像仅导出和离线SBOM取证，不执行镜像、不联网。"""
from pathlib import Path
import subprocess,json,os,time,hashlib,tarfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts/g4-m1-final-gates-001/g3-forensics';OUT.mkdir(exist_ok=True)
refs={'rustfs':'rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b','fuseki':'ontology-platform-fuseki:context-4fbf23514516632dcb651b5c05bf04e9992da52491607b6cf58de1f7348ff9ab'}
for name,ref in refs.items():
 archive=OUT/(name+'.tar');cmd=['docker','--context','desktop-linux','image','save','--platform','linux/arm64','--output',str(archive),ref]
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
 if run.returncode:raise RuntimeError('EXPORT_FAILED')
 env=dict(os.environ,DOCKER_SCOUT_OFFLINE='true',DOCKER_SCOUT_CACHE_DIR=str(OUT/'scout-cache'),DOCKER_SCOUT_NEW_VERSION_WARN='false')
 cmd=['docker','--context','desktop-linux','scout','sbom','--format','json','--platform','linux/arm64','--output',str(OUT/(name+'-sbom.json')),'archive://'+str(archive)]
 started=time.monotonic()
 with (OUT/(name+'-scan.txt')).open('wb') as log:
  try:rc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180).returncode
  except subprocess.TimeoutExpired:rc=124
 receipt=dict(taskId='G4-M1-FINAL-GATES-001',reference=ref,archiveBytes=archive.stat().st_size,archiveSha256=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),scanExitCode=rc,elapsedSeconds=time.monotonic()-started,offline=True,containerExecution=False,downloadBytes=0)
 (OUT/(name+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
