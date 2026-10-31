"""本任务独占新Synthetic环境，复用正式launcher，finally精确停止；不读旧runtime。"""
import os, sys, subprocess, importlib.util, json, time
from pathlib import Path
ROOT=Path.cwd()
TASK='G3-M5-REVIEW-FIX-001'
OUT=ROOT/'artifacts/review-fix'
os.environ['PLATFORM_TASK_ID']=TASK
os.environ['PLATFORM_EVIDENCE_DIR']='docs/evidence/'+TASK+'/runtime-logs'
spec=importlib.util.spec_from_file_location('shared',ROOT/'scripts/acceptance/g2-acceptance-runtime.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
process=None
receipt={'taskId':TASK,'status':'FAIL','launcherStopped':False}
try:
    # 固定入口占用只读拒绝，不停止其他环境。
    import urllib.error
    try:
        shared.OPENER.open('http://localhost:15100/health/live',timeout=1)
        raise RuntimeError('entrypoint_occupied')
    except urllib.error.HTTPError:
        raise RuntimeError('entrypoint_occupied') from None
    except (urllib.error.URLError,TimeoutError):
        pass
    if len(sys.argv)>1:
        path=Path(sys.argv[1]).resolve()
        assert path.is_relative_to(ROOT/'.tools/security')
    else:
        prepared=subprocess.check_output([sys.executable,'scripts/acceptance/g2-runtime.py','prepare'],text=True)
        path=ROOT/prepared.strip().splitlines()[-1]
    runtime=json.loads(path.read_text())
    assert runtime['resourceLifecycle']['taskId']==TASK
    receipt.update(runtimePath=str(path),volumePrefix=runtime['volumePrefix'])
    (OUT/'runtime-ownership.json').write_text(json.dumps(receipt,indent=2)+'\n')
    def launch(mode):
        return subprocess.Popen([sys.executable,'scripts/acceptance/g2-runtime.py',mode,'--runtime-file',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not Path(runtime['realmFile']).exists():
        process=launch('core')
        shared.wait_for('http://localhost:18080/realms/master/.well-known/openid-configuration')
        subprocess.run([sys.executable,'scripts/acceptance/g2-runtime.py','bootstrap','--runtime-file',str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        shared.stop(process)
    process=launch('full')
    shared.wait_for('http://localhost:15100/health/ready',{'X-Health-Key':runtime['healthKey']})
    env=os.environ.copy();env['PLATFORM_EVIDENCE_DIR']='docs/evidence/'+TASK+'/browser'
    script='browser-release-retest.mjs' if len(sys.argv)>1 else 'browser.mjs'
    result=subprocess.run(['node','docs/evidence/'+TASK+'/executed-harnesses/'+script,str(path)],env=env)
    receipt.update(status='PASS' if result.returncode==0 else 'FAIL',browserExitCode=result.returncode)
finally:
    shared.stop(process)
    receipt['launcherStopped']=process is None or process.poll() is not None
    (OUT/'runtime-closure.json').write_text(json.dumps(receipt,indent=2)+'\n')
raise SystemExit(0 if receipt['status']=='PASS' else 1)
