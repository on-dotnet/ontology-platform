"""以 RF-02 同形的同步登记篡改验证窄 Oracle 资格消费者；不产生产品证据。"""
import copy
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/maintenance'))
import workflow_oracle_mapping_evidence as oracle


class OracleQualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {}
        self.archive = oracle.Originals(self.root,'s0',self.files)
        for name in oracle.DRIVERS:
            path = self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('fixture:'+name).encode())
        self.origin = Path('/managed/oracle-task')
        self.api = {k:c*64 for k,c in [('inputKey','1'),('outputKey','2'),('receiptSha256','3')]}
        self.agent = {**self.api,'receiptSha256':'4'*64}
        self.host = dict(taskId=oracle.TASK,runId=oracle.RUN,commandId='1'*32,snapshotId='a'*64,
                         buildInputKey=self.api['inputKey'],buildOutputKey=self.api['outputKey'],runtimeHelperSha256='4'*64,
                         composeSha256='5'*64,ports=dict(api=15741,secondary=15742,oidc=15743,web=15744),
                         oracle=dict(containerId='9'*64,imageId='sha256:'+'b'*64,networkId='1'*64),services={})
        for i,name in enumerate(('platform-pg','fuseki','rustfs','keycloak-test','api')):
            self.host['services'][name]=dict(containerId=str(i)*64,imageId='sha256:'+'a'*64,startedAt='2026-11-19T00:00:00Z',
                                             pid=100+i,mountSha256='c'*64,networks={'platform':'d'*64})

    def write(self, name, data):
        if not isinstance(data,bytes):
            data=oracle.encoded(data)+b'\n'
        p=self.archive.prefix/name
        real=self.root/p
        real.parent.mkdir(parents=True,exist_ok=True)
        real.write_bytes(data)
        self.files[name]=dict(path=str(p),originalPath=str(p),sha256=oracle.sha(data),sizeBytes=len(data),encoding='raw')

    def case(self, case):
        mode=oracle.READY
        stage=dict(phase='s0',mode=mode,case=case)
        argv,key,label=oracle.browser_invocation(self.root,mode,case,self.host,self.api,self.agent,stage)
        cid='a'*32
        entry=dict(commandId=cid,report=f'browser-{mode}-1790000000000.json',stageInputs=stage)
        before=copy.deepcopy(self.host)
        before['commandId']='2'*32
        after={**copy.deepcopy(before),'commandId':'3'*32}
        report=dict(taskId=oracle.TASK,runId=oracle.RUN,mode=mode,startedAtUtc='2026-11-19T00:00:01Z',
            finishedAtUtc='2026-11-19T00:00:02Z',inputsUnchanged=True,http=[{'status':200}],checks=[dict(name='real_check',status='PASS')],
            inputBinding=dict(api=before,web=None),outputBinding=dict(api=after,web=None),status='PASS')
        rejected=case!='healthy'
        if rejected:
            report.update(status='FAIL',failure=dict(phase='oracle_scenario_ready',category='Error',code=oracle.ERRORS[case]))
        log=oracle.encoded(dict(status=report['status'],phase='oracle_scenario_ready',failure=report.get('failure'),checks=1,
                                report=str(self.origin/'artifacts/workflow'/oracle.TASK/oracle.RUN/entry['report'])))+b'\n'
        receipt=dict(schemaVersion=2,taskId=oracle.TASK,runId=oracle.RUN,commandId=cid,parentId=self.host['commandId'],
             stage=label,cwd=str(self.origin),commandSummary=oracle.summary(argv),inputFingerprint=key,started=True,signal=None,
             classification='EXIT_FAILURE' if rejected else 'SUCCESS',exitCode=int(rejected),deadlineSeconds=180,
             startedAtUtc='2026-11-19T00:00:00Z',endedAtUtc='2026-11-19T00:00:03Z',elapsedSeconds=3,environmentFingerprint='a'*64)
        policy=oracle.sha((self.root/'scripts/maintenance/workflow_execution.py').read_bytes())
        receipt['identity']=oracle.digest_value([key,receipt['environmentFingerprint'],receipt['commandSummary']['sha256'],str(self.origin),180,policy])
        for stream,data in [('stdout',log),('stderr',b'')]:
            receipt[stream]=dict(sizeBytes=len(data),sha256=oracle.sha(data))
            self.write(cid+'-'+stream+'.txt',data)
        self.write(cid+'-receipt.json',receipt)
        self.write(entry['report'],report)
        def run():
            return oracle.browser_report(self.archive,entry,self.origin,mode,case,self.host,self.api,self.agent,stage)
        return entry,receipt,report,run

    def test_healthy_and_each_expected_rejection_require_the_same_closure(self):
        for case in oracle.ERRORS:
            with self.subTest(case=case):
                _,_,report,run=self.case(case)
                self.assertEqual(report,run()[0])

    def test_updating_registered_hash_does_not_authorize_changed_receipt(self):
        for case in ('healthy','expired','short'):
            for field,value in [('inputFingerprint','0'*64),('parentId','0'*32),('stage','other'),('taskId','G4-M2-ORACLE-01'),
                                ('runId','other'),('commandSummary',oracle.summary(['node','other'])),('identity','0'*64)]:
                with self.subTest(case=case,field=field):
                    entry,receipt,_,run=self.case(case)
                    receipt[field]=value
                    self.write(entry['commandId']+'-receipt.json',receipt)
                    with self.assertRaises(ValueError):
                        run()

    def test_changed_driver_build_stage_and_report_never_use_old_success(self):
        for case in ('healthy','short'):
            with self.subTest(case=case):
                entry,_,report,run=self.case(case)
                before=(self.root/oracle.DRIVER).read_bytes()
                (self.root/oracle.DRIVER).write_bytes(before+b'change')
                with self.assertRaises(ValueError): run()
                (self.root/oracle.DRIVER).write_bytes(before)
                entry['stageInputs']['newPhaseInput']='changed'
                with self.assertRaises(ValueError): run()
                del entry['stageInputs']['newPhaseInput']
                original=self.agent['outputKey']
                self.agent['outputKey']='f'*64
                with self.assertRaises(ValueError): run()
                self.agent['outputKey']=original
                for field,value in [('inputsUnchanged',False),('http',[]),('checks',[]),('finishedAtUtc','2026-11-19T00:00:04Z')]:
                    self.write(entry['report'],{**report,field:value})
                    with self.assertRaises(ValueError): run()
                altered=copy.deepcopy(report)
                altered['outputBinding']['api']['services']['api']['pid']+=1
                self.write(entry['report'],altered)
                with self.assertRaises(ValueError): run()

    def test_measured_observer_only_reuses_the_unchanged_audit_program(self):
        before=b"FLAG=1\ndef audit_window():\n return FLAG\ndef terminal():\n return 1\n"
        after=before.replace(b'terminal():\n return 1',b'terminal():\n return 2')
        self.assertEqual(oracle.audit_program(before),oracle.audit_program(after))
        self.assertNotEqual(oracle.audit_program(before),oracle.audit_program(after.replace(b'FLAG=1',b'FLAG=2')))
        with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_PROGRAM_SHADOW'):
            oracle.audit_program(after+b'def audit_window():\n return False\n')
        with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_PROGRAM_EFFECT'):
            oracle.audit_program(after+b'FLAG=3\n')

    def test_setup_cannot_inherit_a_changed_dispatch_or_grant_function(self):
        original=b"def ready_fixture(args): return 1\ndef grant_fixture(args): return 2\ndef browser_run(args): return 3\n"
        updated=original.replace(b'return 1',b'return 4')+b'def fixed_window_pair(): return 5\n'
        for mode in ('provision','mapping'):
            self.assertEqual(oracle.setup_platform_program(original,mode),oracle.setup_platform_program(updated,mode))
            for token in (b'return 2',b'return 3'):
                self.assertNotEqual(oracle.setup_platform_program(original,mode),
                                    oracle.setup_platform_program(updated.replace(token,b'return 7'),mode))
        with self.assertRaisesRegex(ValueError,'OMQ_SETUP_SCOPE'):
            oracle.setup_platform_program(updated,oracle.READY)

    def test_true_plan_and_verify_cli_dispatch_fail_closed_without_oracle_originals(self):
        # 最小受控 Git 库只选择 interaction 门禁，不启动后端、Docker 或浏览器。
        root=self.root/'controlled'
        scripts=root/'scripts/maintenance'
        scripts.mkdir(parents=True)
        for name in ('workflow','workflow_execution','workflow_evidence','workflow_oracle_mapping_evidence','workflow_oracle_mapping_resources',
                     'workflow_m2_build','workflow_m2_evidence','execution_preflight','task_run_timeline'):
            shutil.copyfile(ROOT/'scripts/maintenance'/(name+'.py'),scripts/(name+'.py'))
        policy=root/'docs/development'
        policy.mkdir(parents=True)
        (policy/'local-validation-policy.md').write_text('Controlled offline dispatch.\n')
        (policy/'verification-gates.json').write_text(json.dumps(dict(gates={'interaction':dict(needs=[],inputs=['trigger'],command=[],testsRequired=True)})))
        (root/'.gitignore').write_text('artifacts/\n')
        (root/'trigger').write_text('old')
        def cmd(args,expected=0):
            result=subprocess.run(args,cwd=root,capture_output=True,timeout=20)
            self.assertEqual(expected,result.returncode,result.stderr.decode())
            return result.stdout.decode().strip()
        cmd(['git','init','-q'])
        cmd(['git','config','user.name','Oracle offline fixture'])
        cmd(['git','config','user.email','oracle-fixture@localhost'])
        cmd(['git','add','.'])
        cmd(['git','commit','-qm','fixture'])
        base=cmd(['git','rev-parse','HEAD'])
        (root/'trigger').write_text('changed')
        cmd(['git','commit','-qam','select interaction'])
        output='artifacts/plan.json'
        (root/'artifacts').mkdir()
        prefix=[sys.executable,'-B','scripts/maintenance/workflow.py']
        cmd([*prefix,'plan','--base',base,'--head','HEAD','--output',output])
        cmd([*prefix,'verify','--task',oracle.TASK,'--plan',output],expected=2)
        receipt,=(root/'artifacts/workflow'/oracle.TASK/'runs').glob('*/receipt.json')
        result=json.loads(receipt.read_bytes())
        self.assertEqual('BLOCKED',result['status'])
        row,=result['checks']
        self.assertEqual('FAIL',row['status'])
        self.assertEqual(['python3','-B','scripts/maintenance/workflow_oracle_mapping_evidence.py','--task',oracle.TASK,
                          '--run-id',oracle.RUN,'--gate','interaction','--input-key',row['inputKey']],row['command'])
        self.assertIn('OMQ_ORIGINALS_NOT_RUN_s2',(root/row['logPath']).read_text())

    def test_audit_must_cover_the_actual_browser_command(self):
        row=dict(startedAtUtc='2026-11-19T00:00:00Z',endedAtUtc='2026-11-19T00:00:01Z')
        audit=dict(taskId=oracle.TASK,runId=oracle.RUN,startUtc=row['startedAtUtc'],endUtc='2026-11-19T00:00:02Z',
                   sourceId=self.host['oracle']['containerId'])
        with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_WINDOW'):
            oracle.audit_observation(self.archive,audit,row,self.host,self.origin)


if __name__=='__main__':
    unittest.main()
