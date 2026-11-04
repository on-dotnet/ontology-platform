"""Registered, bounded two-variant SELECT diagnostic with exact finally release."""
import json,subprocess,sys,time
from pathlib import Path
W=Path("/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform")
sys.path.insert(0,str(W/'experiments/g4-m1-main-integration'))
import runtime as rt,run
A=rt.ARTIFACTS/'b-continue-20261104-20'
T='7bb08672c354fb97ed39ad4ad7492d2cbe297aad'
m=rt.load_manifest(A/'resource-manifest.json',A.name,T)
helper=A/'helpers/relay-nodelay-diagnostic.py'
query=A/'helpers/pg-latency-v3.fsx'
rt.require(rt.digest(helper.read_bytes())=="2224d2ec18621df2100b517d1599860af8d9396bd614863fe82851692684daca" and rt.digest(query.read_bytes())=="11882645385ffd28114de06041ad20ef0c02827fc2099c249ff60d3177171385",'DIAGNOSTIC_SOURCE_DRIFT')
module=run.module('module-tests')
output=A/'transport-ab-results.json'
rt.require(not output.exists(),'EXISTING_AB_RESULT')
for variant in ('original','nodelay'):
    d=A/('diagnostics/transport-'+variant)
    rt.require(d.is_dir() and not any(d.iterdir()),'VARIANT_DIRECTORY_NOT_EMPTY')
formal=rt.stop_ingress(m,'modules-agent')
rt.write_json(A/'diagnostics/formal-ingress-release.json',formal)
results=[]
for variant in ('original','nodelay'):
    d=A/('diagnostics/transport-'+variant)
    command=[sys.executable,'-B',str(helper),str(rt.HERE/'runtime.py'),'--ingress','modules-agent','--run-id',A.name,'--expected-head',T,'--resource-manifest',str(A/'resource-manifest.json'),'--evidence-dir',str(d),'--variant',variant]
    record=d/'ingress-modules-agent-process.json';process=None;release=None
    result={'scope':'DIAGNOSTIC_ONLY_NOT_FORMAL_GATE','variant':variant,'status':'FAIL','launcherSha256':rt.digest(Path(__file__).read_bytes()),'helperSha256':rt.digest(helper.read_bytes())}
    try:
        with (d/'ingress-modules-agent-process.log').open('xb') as stream:
            process=subprocess.Popen(command,cwd=rt.ROOT,env=rt.environment(A.name),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        birth=subprocess.check_output(['ps','-p',str(process.pid),'-o','lstart='],text=True).strip()
        rt.write_json(record,{'pid':process.pid,'birth':birth,'command':command,'taskId':rt.TASK,'runId':A.name,'testedCommit':T,'runtimeSha256':rt.digest((rt.HERE/'runtime.py').read_bytes()),'helperSha256':rt.digest(helper.read_bytes()),'launcherSha256':rt.digest(Path(__file__).read_bytes()),'scope':'DIAGNOSTIC_ONLY_NOT_FORMAL_GATE'})
        ready=d/'ingress-modules-agent-ready.json';deadline=time.monotonic()+30
        while not ready.exists():
            rt.require(process.poll() is None and time.monotonic()<deadline,'DIAGNOSTIC_START_FAILED');time.sleep(.1)
        value=json.loads(ready.read_text())
        rt.require(value['pid']==process.pid and value['taskId']==rt.TASK and value['runId']==A.name and value['testedCommit']==T and value['manifestSha256']==m['_sha256'],'DIAGNOSTIC_READY_BINDING')
        raw=rt.execute(m,'pg-latency-'+variant,rt.offline_command(['/usr/local/share/dotnet/dotnet','/usr/local/share/dotnet/sdk/10.0.402/FSharp/fsi.dll','--readline-','--exec',str(query)],loopback=True),timeout=60,sensitive=True)
        rows=[json.loads(line) for line in raw.decode().splitlines() if line.strip()]
        rt.require(len(rows)==4 and all(row['samples']==30 for row in rows),'DIAGNOSTIC_RESULTS')
        deadline=time.monotonic()+15
        while True:
            snapshot=module.module_ingress_snapshot((d/'ingress-modules-agent-events.jsonl').read_bytes(),process.pid)
            if snapshot['idle']:break
            rt.require(time.monotonic()<deadline,'DIAGNOSTIC_NOT_IDLE');time.sleep(.1)
        rt.require(snapshot['capacityRefusals']==0,'DIAGNOSTIC_CAPACITY_REFUSAL')
        result.update(status='OBSERVED',samples=rows,idle=snapshot,queryReceiptSha256=rt.digest((A/'commands'/('pg-latency-'+variant+'.json')).read_bytes()),variantInputsSha256=rt.digest((d/'variant-inputs.json').read_bytes()))
    except BaseException as error:
        result['errorType']=type(error).__name__
        raise
    finally:
        try:
            if record.exists():
                release=rt.stop_ingress(m,'modules-agent',evidence_directory=d)
                rt.require(release['status']=='PASS','DIAGNOSTIC_RELEASE_UNPROVEN')
                result['release']=release
                if process is not None:result['helperExitCode']=process.wait(timeout=5)
            elif process is not None:
                if process.poll() is None:process.terminate()
                result['unregisteredStartupExitCode']=process.wait(timeout=15)
                result['status']='FAIL'
        except BaseException as error:
            result['releaseErrorType']=type(error).__name__;result['status']='FAIL'
            raise
        finally:rt.write_json(d/'diagnostic-result.json',result)
    results.append(result)
rt.write_json(output,{'taskId':rt.TASK,'runId':A.name,'testedCommit':T,'scope':'DIAGNOSTIC_ONLY_NOT_FORMAL_GATE','results':results})
print(json.dumps({'diagnosticVariants':[{'variant':r['variant'],'samples':r['samples'],'release':r['release']['status'],'helperExitCode':r['helperExitCode']} for r in results]}))
