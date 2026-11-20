"""离线真实入口见证。合成平台/引擎边界不能产生产品或真实会话 PASS。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
import workflow_oracle_mapping_platform as platform
import workflow_oracle_mapping_resume as resume
from workflow_oracle_mapping_evidence import NODE

MODES=('s0-oracle-natural-cancel','s1','s1-reopen')
TEST_SOURCE=ROOT/'backend/tests/OntologyPlatform.AgentTests/G4QueryMcpTests.cs'


def boundary(state):
    """保留已序列化的 JS 输入，再进入原 ready_fixture；业务调用仅可抵达下列记录器。"""
    case=os.environ['OMQ_OFFLINE_CASE']
    events=[]
    payload={k:state[k] for k in ('taskId','runId','mode','connectionId')}
    def read_pg(sql,stage):
        events.append(stage)
        if stage=='ready-current-catalog':
            return json.dumps({} if case=='catalog' else state['catalog']),'1'*32
        if stage=='ready-current-grants':
            fields=['PRODUCTION/OMQ_ENTITY/'+str(i+1)+'/'+f['name'] for i,f in enumerate(state['catalog']['objects'][0]['fields'])]
            grants=[dict(Permission='data.query.'+p,ttl=1 if case=='ttl' else 400,SiteIds=['site-a'],OrganizationId='org-demo',
                         ObjectRefs=['PRODUCTION/OMQ_ENTITY'],FieldRefs=fields) for p in ('execute','result.read','evidence.read')]
            return json.dumps(grants),'2'*32
        if stage=='ready-activation':
            return json.dumps(dict(ActivationId='stale' if case=='activation' else 'activation-one',ActivationRevision=1)),'3'*32
        raise AssertionError('UNEXPECTED_PG')
    def sessions(actors,seconds):
        events.append('session')
        assert seconds==210 and len(actors)==4
        return {'observations':[]}
    def fixture():
        events.append('fixture')
        return {'counts':[2,1] if case=='rows' else [1,1]}
    def forbid(event,args):
        if event in ('subprocess.Popen','os.system','socket.connect','socket.bind','socket.getaddrinfo'):
            raise AssertionError('OFFLINE_EXTERNAL_ACCESS')
    sys.addaudithook(forbid)
    if case=='task':state['taskId']='OTHER'
    if case=='run':state['runId']='unexpected'
    if case=='opposite':state['runId']=platform.RUN if state['runId']==resume.PRODUCT else resume.PRODUCT
    try:
        with patch.object(platform,'read_pg',read_pg),patch.object(platform,'session_preflight',sessions),patch.object(platform,'fixture_state',fixture):
            return platform.ready_fixture(state)
    finally:
        Path(os.environ['OMQ_OFFLINE_TRACE']).write_text(json.dumps(dict(payload=payload,receivedRun=state['runId'],events=events)))


def probe_ready(mode,case='healthy',product=True):
    with tempfile.TemporaryDirectory() as work:
        root=Path(work)
        bridge=root/'scripts/maintenance/workflow_oracle_mapping_platform.py'
        bridge.parent.mkdir(parents=True)
        bridge.write_text("import importlib.util,sys\n"
            "current=sys.modules.pop(__name__)\n"
            f"sys.path.insert(0,{str(ROOT/'scripts/maintenance')!r})\n"
            f"s=importlib.util.spec_from_file_location('offline_oracle_boundary',{str(Path(__file__).resolve())!r})\n"
            "h=importlib.util.module_from_spec(s);s.loader.exec_module(h)\n"
            "current.ready_fixture=h.boundary\nsys.modules[__name__]=current\n")
        trace=root/'observed.json'
        env=dict(os.environ,OMQ_OFFLINE_CASE=case,OMQ_OFFLINE_TRACE=str(trace))
        env.pop('OMQ_PRODUCT_RUN',None)
        if product:env['OMQ_PRODUCT_RUN']=resume.PRODUCT
        node=NODE if Path(NODE).is_file() else 'node'
        run=subprocess.run([node,str(ROOT/'scripts/tests/WorkflowOracleReadyFixture.mjs'),str(root),mode],env=env,
                           cwd=ROOT,capture_output=True,check=True,timeout=8)
        return dict(result=json.loads(run.stdout),**json.loads(trace.read_bytes()))


def csharp_pattern():
    return re.search(r'Regex\.IsMatch\(report, @"([^"]+)"',TEST_SOURCE.read_text()).group(1)



class CapturedCommand(Exception):
    pass


def session_argv():
    """调用真实生产者，仅在引擎/构建边界截取 argv，绝不创建容器。"""
    holder={}
    binding={'inputKey':'1'*64,'outputKey':'2'*64,'receiptSha256':'3'*64}
    def take(command,root,**kw):
        holder.update(argv=command,inputFingerprint=kw['input_key'],parentId=kw['parent_id'])
        raise CapturedCommand()
    with patch.object(resume,'load',return_value={'sessionSnapshotId':'4'*64}), \
         patch.object(resume,'current_session_snapshot',return_value={'inputs':binding}), \
         patch.object(resume,'host_binding',return_value={'services':{'api-secondary':{'containerId':'7'*64}},'commandId':'8'*32}), \
         patch.object(resume.ex,'run',take):
        try:resume.verify_sessions([dict(subjectId=str(i),cookie='synthetic') for i in range(4)],210)
        except CapturedCommand:pass
    return holder


class EntryFixTests(unittest.TestCase):
    def test_actual_js_ready_dispatch_in_both_contexts(self):
        for product in (True,False):
            for mode in MODES:
                with self.subTest(product=product,mode=mode):
                    run=probe_ready(mode,product=product)
                    expected=resume.PRODUCT if product else platform.RUN
                    self.assertEqual((platform.TASK,expected,mode),(run['payload']['taskId'],run['payload']['runId'],run['payload']['mode']))
                    self.assertEqual({'status':'READY','runId':expected,'mode':mode},run['result'])
                    self.assertEqual(['ready-current-catalog','ready-current-grants','ready-activation','session','fixture'],run['events'])

    def test_scope_refusals_precede_any_external_boundary(self):
        for product in (True,False):
            for case in ('task','run','opposite'):
                with self.subTest(product=product,case=case):
                    run=probe_ready('s1',case,product)
                    self.assertEqual('ORACLE_ADMISSION_READY_SCOPE',run['result']['code'])
                    self.assertEqual([],run['events'])

    def test_stale_catalog_grant_activation_and_fixture_remain_rejected(self):
        for case,code in [('catalog','OMQ_READY_CATALOG_STALE'),('ttl','OMQ_READY_GRANT_TTL_SHORT'),('activation','OMQ_READY_ACTIVATION_STALE'),('rows','READY_SOURCE_ROWS')]:
            with self.subTest(case=case):
                run=probe_ready('s1',case)
                self.assertEqual('ORACLE_ADMISSION_'+code,run['result']['code'])

class SessionReportTests(unittest.TestCase):
    def test_real_runner_path_and_native_csharp_exclusive_output(self):
        # 真实 shell argv 中的路径；输入到 C# 既有表达式后只写独占合成测试目录。
        command=session_argv()['argv']
        runner=command[-1]
        directory=re.search(r'; d=(/tmp/omq-session-probe-[a-f0-9]{32});',runner).group(1)
        filename=re.search(r'export G4_BROWSER_REPORT="\$d/([^"/]+)"',runner).group(1)
        self.assertEqual('session-ready.json',filename)
        self.assertIn('G4_QUERY_RUNTIME_TEST='+platform.TASK+':'+platform.RUN,command)
        self.assertIn('mkdir -m 700 -- "$d"; trap',runner)
        self.assertIn('dotnet /session-tests/OntologyPlatform.AgentTests.dll --filter FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline',runner)
        nonce=directory.rsplit('-',1)[1]
        self.assertEqual(command,resume.session_invocation('7'*64,nonce))
        for bad in ('','a'*31,'A'*32,'a'*32+'/other'):
            with self.assertRaisesRegex(ValueError,'PRODUCT_SESSION_COMMAND'):
                resume.session_invocation('7'*64,bad)
        self.assertNotIn(directory,session_argv()['argv'][-1])
        report=directory+'/'+filename
        self.assertIn('new FileStream(report, FileMode.CreateNew, FileAccess.Write, FileShare.Read)',TEST_SOURCE.read_text())
        # PowerShell 用本机 .NET 的同一 Regex 语义及文件系统独占创建，避免将 Python 的近似表达式当成 C#。
        pwsh=shutil.which('pwsh')
        self.assertIsNotNone(pwsh,'PowerShell/.NET required for the Oracle session-report contract')
        with tempfile.TemporaryDirectory() as tmp:
            # 只合成 observations，不复制路径/打开策略。离线编译并执行真实消费者的 C# 写出分支。
            text=TEST_SOURCE.read_text()
            start=text.index('private static string? OracleSessionObservationFailure(')
            end=text.index('    /// <summary>通过标准Cookie格式',start)
            block=text[start:end].replace('private static','public static')
            self.assertIn('await WriteOracleSessionReportAsync(report, observations);',text[end:])
            source=Path(tmp)/'ReportProbe.cs'
            source.write_text('#nullable enable\nusing System; using System.IO; using System.Text.Json; using System.Threading.Tasks;\n'
                'public static class Assert { public static void IsTrue(bool value) { if(!value) throw new InvalidDataException("STRICT_PATH"); } }\n'
                'public static class OracleReportProbe {\n'+block+'\n}\n')
            script=Path(tmp)/'session-contract.ps1'
            script.write_text("""
param([string]$Report,[string]$Source)
$ErrorActionPreference = 'Stop'
Add-Type -Path $Source
$now=[DateTimeOffset]::UtcNow
$long=$now.AddMinutes(5)
$short=$now.AddSeconds(1)
$cutoff=$now.AddMinutes(2)
if ($null -ne [OracleReportProbe]::OracleSessionObservationFailure('actor','actor',$long,$long,$false,$cutoff)) { throw 'HEALTHY' }
foreach ($case in @(
    @('actor',$short,$long,$false,'OMQ_SESSION_TTL_INSUFFICIENT'), @('actor',$long,$short,$false,'OMQ_SESSION_TTL_INSUFFICIENT'),
    @('other',$short,$short,$false,'OMQ_SESSION_SUBJECT_MISMATCH'), @('actor',$short,$short,$true,'OMQ_SESSION_REVOKED'),
    @($null,$null,$short,$false,'OMQ_SESSION_TICKET_UNAVAILABLE')
)) {
    $code=[OracleReportProbe]::OracleSessionObservationFailure('actor',$case[0],$case[1],$case[2],$case[3],$cutoff)
    if($code -ne $case[4]) { throw 'MISCLASSIFIED_SESSION' }
}
$bad = @($Report.Replace('/omq-session-probe-','/omq-session-'), $Report.Replace('session-ready.json','ready.json'),
    $Report.Insert('/tmp/omq-session-probe-'.Length,'X'), $Report.Substring(0,'/tmp/omq-session-probe-'.Length)+'123/session-ready.json')
foreach ($value in $bad) {
    $denied=$false
    try { [OracleReportProbe]::WriteOracleSessionReportAsync($value,@('synthetic')).GetAwaiter().GetResult() }
    catch { $denied=$_.Exception.GetBaseException().Message -eq 'STRICT_PATH' }
    if (-not $denied) { throw 'INVALID_PATH_ACCEPTED' }
}
[OracleReportProbe]::WriteOracleSessionReportAsync($Report,@('synthetic')).GetAwaiter().GetResult()
$first=[IO.File]::ReadAllText($Report)
$denied=$false
try { [OracleReportProbe]::WriteOracleSessionReportAsync($Report,@('another')).GetAwaiter().GetResult() }
catch { $denied=$_.Exception.GetBaseException() -is [IO.IOException] }
if (-not $denied -or [IO.File]::ReadAllText($Report) -ne $first) { throw 'OVERWRITE_ALLOWED' }
""")
            os.mkdir(directory,0o700)
            try:
                result=subprocess.run([pwsh,'-NoProfile','-NonInteractive','-File',str(script),report,str(source)],
                                      capture_output=True,timeout=12)
                self.assertEqual(0,result.returncode,result.stderr.decode())
            finally:
                shutil.rmtree(directory)

    def test_only_closed_session_failure_reports_are_classified(self):
        for code in ('OMQ_SESSION_TTL_INSUFFICIENT','OMQ_SESSION_SUBJECT_MISMATCH','OMQ_SESSION_REVOKED','OMQ_SESSION_TICKET_UNAVAILABLE'):
            self.assertEqual(code,resume.session_failure_code(b'MTP output\n'+json.dumps({'code':code}).encode()+b'\n'))
        for value in ({'code':'OMQ_SESSION_TTL_INSUFFICIENT','unknown':1},{'code':'OTHER'},[],None):
            self.assertEqual('PRODUCT_SESSION_REJECTED',resume.session_failure_code(json.dumps(value).encode()))

    def test_registration_requires_current_compiled_bytes_command_and_readonly_mount(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root=Path(temporary).resolve()
            area=root/'artifacts/workflow'/platform.TASK/resume.PRODUCT
            output=root/'sample/bin'
            output.mkdir(parents=True)
            assembly=output/'OntologyPlatform.AgentTests.dll'
            assembly.write_bytes(b'offline-bound-output')
            (output/'example.deps.json').write_text('{}')
            (output/'example.runtimeconfig.json').write_text('{}')
            cmd='a'*32
            prefix=str(Path(platform.build.TARGETS['agent']).parent/'bin/Debug/net10.0')+'/'
            receipt=area.parent/'agent-build-binding.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps(dict(outputs={prefix+f.name:platform.ex.sha(f.read_bytes()) for f in output.iterdir()})))
            binding={'inputKey':'d'*64,'outputKey':'e'*64,'receiptSha256':platform.ex.sha(receipt.read_bytes())}
            snap=platform.snapshots.freeze(root,output,area/'runtime-snapshots',binding,cmd,{},task=platform.TASK,run_id=resume.PRODUCT)
            for attr,val in [('ROOT',root),('AREA',area),('BASE',area.parent/platform.RUN)]:
                stack.enter_context(patch.object(resume,attr,val))
            builder=stack.enter_context(patch.object(resume,'bound_build',return_value=(binding,dict(commandId=cmd))))
            scoped=dict(sessionSnapshotId=snap['snapshotId'])
            self.assertEqual(snap,resume.current_session_snapshot(scoped))
            mounted=str(root/snap['directory'])+':/session-tests'
            for target in (mounted+':rw',str(root/'old')+':/session-tests:ro'):
                with self.assertRaisesRegex(ValueError,'PRODUCT_SESSION_RECIPE'):
                    resume.verify_session_recipe({'services':{'api-secondary':{'volumes':[target]}}},snap)
            good={'services':{'api-secondary':{'volumes':[mounted+':ro']}}}
            resume.verify_session_recipe(good,snap)
            good['services']['api-secondary']['volumes'].append(str(root/'old')+':/session-tests/other:ro')
            with self.assertRaisesRegex(ValueError,'PRODUCT_SESSION_RECIPE'):
                resume.verify_session_recipe(good,snap)
            builder.return_value=(binding,dict(commandId='b'*32))
            with self.assertRaisesRegex(ValueError,'PRODUCT_SESSION_BUILD'):
                resume.current_session_snapshot(scoped)
            builder.return_value=(binding,dict(commandId=cmd))
            receipt.write_text(json.dumps(dict(outputs={prefix+assembly.name:'0'*64})))
            with self.assertRaisesRegex(ValueError,'PRODUCT_SESSION_BUILD'):
                resume.current_session_snapshot(scoped)


if __name__=='__main__':
    unittest.main()
