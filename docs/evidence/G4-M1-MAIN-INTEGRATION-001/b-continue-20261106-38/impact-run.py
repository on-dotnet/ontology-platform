"""Run38已批准的按影响验收；复用与新执行分别留证，不生成旧门禁的伪回执。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT/'experiments/g4-m1-main-integration'))
import runtime as rt
import run
import readback as rb
import closeout

RUN = 'b-continue-20261106-38'
A = rt.ARTIFACTS/RUN
OLD = rt.ARTIFACTS/'b-continue-20261106-37'
D = ROOT/'docs/evidence/G4-M1-MAIN-INTEGRATION-001'/RUN
T37 = '79d1d42f43e8e7da23e905da18a374037b6b22a3'
H37 = '5ec3e40097576c57b2d8bd224211e9d7f6c77ff4'
PRODUCT = {'apps/web/src/features/connections/catalog.tsx': 'c848454e65ace628e0ee4af1290e50d4868447ed4dd7f9608eb628a130893f5b',
           'apps/web/src/features/connections/connections.test.ts': '87712479050b9d2e575df345fb83e9a8a2f69778ab328705ec75917b9de126a8'}


def bound_helpers():
    """运行副本及所有补充驱动必须与本次已提交Git blob相同。"""
    rows = {}
    for name in ('impact-run.py', 'race-regression.mjs', 'observe-host-identity.py', 'release-host.py'):
        p = D/name
        blob = subprocess.check_output(['git','show','HEAD:'+str(p.relative_to(ROOT))])
        rt.require(p.read_bytes() == blob and (A/name).read_bytes() == blob, 'IMPACT_DRIVER_DRIFT')
        rows[name] = rt.digest(blob)
    return rows


def original(name):
    """固定已审归档提交为权威，防止两份可写副本同时改写后冒充旧通过。"""
    rel='docs/evidence/G4-M1-MAIN-INTEGRATION-001/'+OLD.name+'/'+name
    blob=subprocess.check_output(['git','show',H37+':'+rel])
    rt.require((OLD/name).read_bytes()==blob and (ROOT/rel).read_bytes()==blob,'REUSE_IMMUTABLE_BLOB_DRIFT')
    value=json.loads(blob)
    rt.require(value.get('testedCommit')==T37,'REUSE_TESTED_COMMIT')
    for key,expected in (('taskId',rt.TASK),('runId',OLD.name)):
        if key in value:rt.require(value[key]==expected,'REUSE_IDENTITY')
    return value,blob


def backend_binding():
    """既有构建不重新生成；准确1426项后端产物仍需逐字节相同。"""
    old,_ = original('build-inputs.json')
    rt.require(old['testedCommit'] == T37, 'REUSE_TESTED_COMMIT')
    expected = {k:v for k,v in old['files'].items() if k.startswith('backend/')}
    actual = {k:v for k,v in rt.build_fingerprint().items() if k.startswith('backend/')}
    rt.require(actual == expected and len(actual) == 1426, 'REUSE_BACKEND_BUILD_DRIFT')
    return actual


def qualification(head):
    """完整输入差异限制和原始证据散列，绝不把旧运行改写为本次执行。"""
    changes = rt.git('diff','--name-only',T37,head).splitlines()
    executable = [x for x in changes if not x.startswith('docs/evidence/') and x != 'docs/tasks/G4-M1-MAIN-INTEGRATION-001.md']
    rt.require(set(executable) == set(PRODUCT), 'IMPACT_SCOPE_DRIFT')
    for p,h in PRODUCT.items():
        rt.require(rt.digest((ROOT/p).read_bytes()) == h, 'PRODUCT_APPROVAL_DRIFT')
    old,_ = original('resource-manifest.json')
    rt.require(old['testedCommit'] == T37, 'REUSE_MANIFEST_HEAD')
    rt.require(old['drivers'] == {n:rt.digest((rt.HERE/n).read_bytes()) for n in rt.NAMES}, 'REUSE_DRIVER_DRIFT')
    sources = {}
    names = ['resource-manifest.json','build-inputs.json','fixture-case-closure.json',
             'review-engineering-interim.json','review-I02.json','review-I04.json','review-I06-and-fixture-closure.json']
    names += ['gate-'+g+'.json' for g in ('I01','I02','I03','I04','I05','I06')]
    names += ['gate-I01-closure.json','gate-I03-closure.json']
    for name in names:
        p = OLD/name
        value,raw=original(name)
        if name.startswith('review-'):rt.require(value['status']=='PASS','REUSE_REVIEW_NOT_PASSED')
        sources[name] = {'path':str(p),'sha256':rt.digest(raw),'bytes':len(raw),'archiveCommit':H37,
                         'gitBlob':rt.git('rev-parse',H37+':docs/evidence/G4-M1-MAIN-INTEGRATION-001/'+OLD.name+'/'+name)}
    for gate in ('I02','I04','I05','I06'):
        rt.require(json.loads((OLD/('gate-'+gate+'.json')).read_text())['result']['status']=='PASS','REUSE_NOT_PASSED')
    for gate in ('I01','I03'):
        rt.require(json.loads((OLD/('gate-'+gate+'-closure.json')).read_text())['result']['status']=='PASS','REUSE_CLOSURE_NOT_PASSED')
    return {'status':'REUSED_FROM_T37','execution':'NOT_REEXECUTED','sourceTestedCommit':T37,
            'sourceRunId':OLD.name,'testedCommit':head,'sourceChanges':executable,'sources':sources,
            'backendBuildFiles':backend_binding(),'taskDrivers':old['drivers'],
            'I01':'Backend/SelfTest reused; Web must be freshly executed',
            'I02':'G3 full stack and modules reused; HTTP/browser compatibility smoke must be freshly executed',
            'I03':'Startup/host graph and fixture closure reused','I04':'Migration/isolation reused',
            'I05':'Generator/contracts reused','I06':'Lifecycle/security and fixture closure reused',
            'I07':'NOT_REUSED; full canonical browser suite required',
            'approvalSha256':rt.digest((D/'IMPACT-ACCEPTANCE-APPROVAL.md').read_bytes())}


def initialize(head):
    """新Run独立清单/监测/工具副本；不执行restore或任何安装。"""
    reuse = qualification(head)
    m = json.loads((OLD/'resource-manifest.json').read_text())
    m.update(runId=RUN,testedCommit=head,privateDirectory=str(rt.private_dir(RUN)),temporaryDirectory=str(rt.run_temp(RUN)))
    rt.write_json(A/'resource-manifest.json',m)
    m = rt.load_manifest(A/'resource-manifest.json',RUN,head)
    rt.verify_engine(m)
    rt.run_temp(RUN).mkdir(parents=True)
    rt.write_json(A/'impact-reuse.json',reuse)
    rt.execute(m,'host-preflight',[sys.executable,'-B',str(rt.HERE/'host_continuity.py'),'preflight','--output',str(A/'host-preflight.json')])
    cmd = [sys.executable,'-B',str(rt.HERE/'host_continuity.py'),'monitor','--output',str(A/'host-monitor.jsonl'),'--seconds','14400','--interval','10']
    p = subprocess.Popen(cmd,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    rt.write_json(A/'host-monitor-process.json',{'taskId':rt.TASK,'runId':RUN,'testedCommit':head,'pid':p.pid,'command':cmd,'driverSha256':rt.digest((rt.HERE/'host_continuity.py').read_bytes())})
    subprocess.run([sys.executable,'-B',str(A/'observe-host-identity.py')],check=True)
    run.prepare_tools(m)
    return {'status':'PASS','reusedFrom':T37,'restore':'NOT_REEXECUTED','download':0}


def web(m):
    """已核验本地工具执行四项真实Web入口；OS拒绝非loopback联网。"""
    for command in ('lint','typecheck','test','build'):
        rt.execute(m,'impact-web-'+command,rt.offline_command([run.NODE,str(ROOT/'.tools/pnpm/package/bin/pnpm.cjs'),'--config.verifyDepsBeforeRun=error','--dir','apps/web','run',command],loopback=True),timeout=300)
    backend_binding()
    rt.write_json(A/'build-inputs.json',{'testedCommit':m['_head'],'files':rt.build_fingerprint(),
                  'backendSourceTestedCommit':T37,'webBuild':'FRESH','backendBuild':'BYTE_IDENTICAL_REUSED'})
    return {'status':'PASS','checks':['lint','typecheck','test','build'],'backendUnchanged':True}


def setup(m):
    """独立M1设施及真实HTTP兼容烟测，保留新建连接供I07故障组使用。"""
    rt.prepare(m)
    rt.start_group(m,'m1')
    run.consumer(m,'http',scenario='baseline')
    baseline = rb.reports(m,'http-baseline')
    lineage = rb.lineage(m,baseline)
    run.consumer(m,'http',scenario='provision')
    provision = rb.reports(m,'http-provision')['fixtures']
    rt.update_runtime(m,httpConnectionId=rb.identifier(provision['connectionId']),httpSnapshotId=rb.identifier(provision['snapshotId']))
    return {'status':'PASS','baselineReportSha256':rb.report_sha(m,'http-baseline'),'lineage':lineage['status'],
            'compatibilityScope':'real OIDC/CSRF/HTTP contract and authorization; unchanged full G3 coverage reused from T37'}


def race(m):
    """持有真实初读403时禁止提交；释放原响应并完成撤权重验后202可恢复。"""
    rt.check_build(m)
    rt.update_runtime(m,scenario='source-permission-limited',connectionId=rt.runtime_value(m)['httpConnectionId'])
    rb.action(m,'probe-refresh','race-precondition')
    query="SELECT json_build_object('select',has_table_privilege('fixture_reader','production.heat_event','SELECT'));"
    before=json.loads(rb.sql(m,query,source=True))
    rt.require(before=={'select':True},'RACE_ACL_INITIAL')
    after=None
    try:
        rb.sql(m,'REVOKE SELECT ON production.heat_event FROM fixture_reader;',source=True)
        rt.require(json.loads(rb.sql(m,query,source=True))=={'select':False},'RACE_FAULT_NOT_APPLIED')
        cmd=[run.NODE,str(A/'race-regression.mjs'),*run.binding(m),'--runtime-file',str(rt.private_dir(RUN)/'runtime.json'),'--evidence-dir',str(A/'race-regression')]
        rt.execute(m,'race-regression',cmd,timeout=90,sensitive=True,allowed_codes=(2,))
    finally:
        rb.sql(m,'GRANT SELECT ON production.heat_event TO fixture_reader;',source=True)
        after=json.loads(rb.sql(m,query,source=True))
        rt.write_json(A/'race-acl-restore.json',{'before':before,'after':after,'restored':after==before})
        rt.require(after==before,'RACE_RESTORE_FAILED')
    report=rb.reports(m,'race-regression')
    events={e['event'] for e in report['diagnosticEvents']}
    rt.require(not report.get('failure') and not any(v['status']=='FAIL' for v in report['cases'].values()),'RACE_BROWSER_FAILED')
    rt.require({'initial_catalog_command_blocked','released_actual_catalog','released_actual_discover_after_revalidation'}<=events,'RACE_SEQUENCE_NOT_OBSERVED')
    rt.require({'partial_catalog','job_refresh_recovery'}<=set(report['cases']['M1-U05']['observed']),'RACE_JOB_NOT_RECOVERED')
    rb.action(m,'probe-refresh','race-restored')
    return {'status':'PASS','scope':'real scheduled initial catalog403 exclusion, original202 job URL and PARTIAL reload recovery',
            'reportSha256':rb.report_sha(m,'race-regression'),'consumerExit':2,
            'consumerExitMeaning':'targeted scenario; other UI cases NOT_RUN here; canonical full I07 is separate','sourceAclRestored':True}


def main():
    rt.require(len(sys.argv)==2 and sys.argv[1] in ('init','web','setup','race','I07','cleanup'),'EXACT_IMPACT_PHASE')
    rt.require(ROOT==rt.ROOT and not rt.git('status','--porcelain'),'IMPACT_CWD_OR_DIRTY')
    helpers=bound_helpers();head=rt.git('rev-parse','HEAD');phase=sys.argv[1]
    output=A/('impact-'+phase+'.json');rt.require(not output.exists(),'EXISTING_IMPACT_RESULT')
    try:
        if phase=='init':result=initialize(head)
        else:
            m=rt.load_manifest(A/'resource-manifest.json',RUN,head)
            prerequisite={'web':'init','setup':'web','race':'setup','I07':'race','cleanup':'I07'}[phase]
            rt.require(json.loads((A/('impact-'+prerequisite+'.json')).read_text())['result']['status']=='PASS','IMPACT_PREREQUISITE')
            backend_binding()
            if phase in ('web','setup','race'):result=globals()[phase](m)
            elif phase=='I07':result=rb.browser_faults(m)
            else:
                hygiene=closeout.verify_secret_hygiene(m)
                result=closeout.reclaim(m,'m1',apply=True);result['secretHygiene']=hygiene['status']
        rt.require(bound_helpers()==helpers and not rt.git('status','--porcelain'),'IMPACT_INPUT_DRIFT')
    except Exception as error:
        rt.write_json(output,{'taskId':rt.TASK,'runId':RUN,'testedCommit':head,'helpers':helpers,
                     'result':{'status':'BLOCKED_WITH_WITNESS','category':type(error).__name__,'code':str(error) if isinstance(error,ValueError) else 'DETAILS_SUPPRESSED'}})
        raise
    rt.write_json(output,{'taskId':rt.TASK,'runId':RUN,'testedCommit':head,'helpers':helpers,'result':result})
    print(json.dumps({'phase':phase,'result':result},ensure_ascii=False))


if __name__=='__main__':
    main()
