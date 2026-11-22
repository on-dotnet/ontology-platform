"""以 RF-02 同形的同步登记篡改验证窄 Oracle 资格消费者；不产生产品证据。"""
import copy
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/maintenance'))
import workflow_oracle_mapping_evidence as oracle
import workflow_oracle_mapping_formal_observer as observer


class OracleQualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {}
        self.archive = oracle.Originals(self.root,'s0',self.files)
        for name in oracle.drivers(ROOT,oracle.READY,oracle.PRODUCT_RUN):
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

    def test_current_plan_and_verify_reopen_test_streams_without_historical_s0_selection(self):
        """真实 plan/verify CLI 消费隔离的合成原件；夹具不贡献产品或实机测试资格。"""
        import workflow_m2_build as build
        root=self.root/'controlled-current'
        scripts=root/'scripts/maintenance'
        scripts.mkdir(parents=True)
        for name in ('workflow','workflow_execution','workflow_evidence','workflow_oracle_mapping_evidence',
                     'workflow_oracle_mapping_resources','workflow_m2_build','workflow_m2_evidence',
                     'execution_preflight','task_run_timeline','workflow_oracle_mapping_s2_contract','workflow_oracle_mapping_continuation'):
            shutil.copyfile(ROOT/'scripts/maintenance'/(name+'.py'),scripts/(name+'.py'))
        plan_file='workflow-oracle-s2-runtime-plan.json'
        shutil.copyfile(ROOT/'scripts/maintenance'/plan_file,scripts/plan_file)
        config=root/'docs/development'
        config.mkdir(parents=True)
        gates={name:dict(needs=needs,inputs=['backend/input.txt'],command=[],testsRequired=True)
               for name,needs in [('contract',[]),('backend',['contract']),('interaction',['backend'])]}
        (config/'verification-gates.json').write_text(json.dumps({'gates':gates}))
        (config/'local-validation-policy.md').write_text('Controlled engineering routing fixture.\n')
        (root/'.gitignore').write_text('artifacts/\n**/bin/\n')
        source=root/'backend/input.txt'
        source.parent.mkdir()
        source.write_text('before\n')
        run=oracle.PRODUCT_RUN
        scope='s2-s3-01-runtime-01'
        batch='s2-s3-01'
        env={k:v for k,v in os.environ.items() if k!='OMQ_PRODUCT_RUN'}
        def execute(args, expected=0, env=env):
            result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(expected,result.returncode,result.stderr+result.stdout)
            return (result.stdout,result.stderr)
        for args in (['init','-q'],['config','user.name','Fixture'],['config','user.email','fixture@localhost'],
                     ['add','.'],['commit','-qm','fixture']):
            execute(['git',*args])
        base=execute(['git','rev-parse','HEAD'])[0].strip()
        source.write_text('current\n')
        execute(['git','commit','-qam','current fixture'])
        head=execute(['git','rev-parse','HEAD'])[0].strip()
        area=root/'artifacts/workflow'/oracle.TASK
        selected=area/run/batch
        selected.mkdir(parents=True)
        index=dict(taskId=oracle.TASK,runId=run,scope=scope,batch=batch,measuredWorktree=str(root),
                   measuredCommit=head,tests={},buildFiles={})
        input_key=oracle.sha(json.dumps({'backend/input.txt':oracle.sha(source.read_bytes())},sort_keys=True).encode())
        for number,(name,(target,expression,minimum)) in enumerate(oracle.TESTS.items(),1):
            project=Path(build.TARGETS[target])
            marker=project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
            log=('Offline build closure fixture for '+target+'\n').encode()
            outputs={str(marker):oracle.sha(target.encode())}
            binding=oracle.encoded(dict(taskId=oracle.TASK,target=target,worktree=str(root),inputKey=input_key,
                                        outputs=outputs,logSha256=oracle.sha(log),status='PASS',exitCode=0))
            for suffix,data in [('-build-binding.json',binding),('-bound-build.txt',log)]:
                path=Path(target+suffix)
                digest=oracle.sha(data)
                (area/(path.stem+'-'+digest+path.suffix)).write_bytes(data)
                index['buildFiles'][path.name]=digest
            argv=['/usr/local/share/dotnet/dotnet',str(root/marker),'--filter',expression,'--minimum-expected-tests',
                  str(minimum),'--no-ansi','--progress','off','--results-directory',str(area/run/'test-results'/target)]
            key=oracle.digest_value(dict(inputKey=input_key,outputKey=oracle.sha(json.dumps(outputs,sort_keys=True).encode()),
                                         receiptSha256=oracle.sha(binding)))
            cid=format(number,'032x')
            index['tests'][name]=dict(commandId=cid)
            directory=area/'commands'/run/cid
            directory.mkdir(parents=True)
            receipt=dict(schemaVersion=2,taskId=oracle.TASK,runId=run,commandId=cid,parentId=None,stage='omq-test-'+name,
                         cwd=str(root),commandSummary=oracle.summary(argv),inputFingerprint=key,environmentFingerprint='a'*64,
                         deadlineSeconds=120,started=True,signal=None,exitCode=0,classification='SUCCESS',
                         startedAtUtc='2026-11-22T02:00:00Z',endedAtUtc='2026-11-22T02:00:01Z',elapsedSeconds=1)
            receipt['identity']=oracle.digest_value([key,receipt['environmentFingerprint'],receipt['commandSummary']['sha256'],
                                                    str(root),120,oracle.sha((scripts/'workflow_execution.py').read_bytes())])
            for stream,data in [('stdout',f'total: {minimum}\nfailed: 0\nsucceeded: {minimum}\nskipped: 0\n'.encode()),
                                ('stderr',b'')]:
                path=directory/(stream+'.txt')
                path.write_bytes(data)
                receipt[stream]=dict(path=str(path),sha256=oracle.sha(data),sizeBytes=len(data))
            (directory/'receipt.json').write_bytes(oracle.encoded(receipt))
        raw=oracle.encoded(index)
        digest=oracle.sha(raw)
        selection=selected/('engineering-selection-'+digest+'.json')
        selection.write_bytes(raw)
        prefix=[sys.executable,'-B','scripts/maintenance/workflow.py']
        output='artifacts/plan.json'
        execute([*prefix,'plan','--base',base,'--head',head,'--oracle-selection-sha',digest,'--output',output])
        plan=json.loads((root/output).read_bytes())
        execute([*prefix,'verify','--task',oracle.TASK,'--plan',output],2)
        receipt,=(area/'runs').glob('*/receipt.json')
        rows=json.loads(receipt.read_bytes())['checks']
        self.assertEqual(['contract','backend','interaction'],[item['gate'] for item in rows])
        for item in rows[:2]:
            self.assertEqual(('PASS',5,0),(item['status'],item['tests'],item['skipped']))
            proof=item['productProof']
            self.assertEqual((run,scope,batch,digest,'BLOCKED','NOT_QUALIFIED'),
                             tuple(proof[k] for k in ('runId','scope','batch','selectionSha256','oracleS0','AC03B')))
        self.assertEqual('FAIL',rows[-1]['status'])
        self.assertIn('OMQ_FORMAL_S2_S3_NOT_RUN',(root/rows[-1]['logPath']).read_text())
        self.assertFalse((root/'docs/evidence'/oracle.TASK/'implementation-01/s0/qualification.json').exists())
        cli=[sys.executable,'-B','scripts/maintenance/workflow_oracle_mapping_evidence.py','--task',oracle.TASK,
             '--run-id',run,'--gate','contract','--input-key',plan['inputKeys']['contract'],
             '--scope',scope,'--batch',batch,'--selection-sha',digest]
        for flag,value,reason in [('--run-id','implementation-01','OMQ_QUALIFICATION_ID'),
                                  ('--scope','s0','OMQ_CURRENT_ROUTE'),
                                  ('--input-key','f'*64,'OMQ_QUALIFICATION_ID'),
                                  ('--selection-sha','f'*64,'FileNotFoundError')]:
            with self.subTest(flag=flag):
                args=cli.copy()
                args[args.index(flag)+1]=value
                self.assertIn(reason,execute(args,1,{**env,'OMQ_PRODUCT_RUN':run})[1])
        # 旧计划也有同名 UI/交互槽，不能因此取得当前正式父的准入。
        parent='9'*32
        previous_plan=json.loads((ROOT/'scripts/maintenance/workflow-oracle-s2-access-plan.json').read_bytes())
        (area/run/('formal-run-s2-s3-oracle-'+parent+'.json')).write_bytes(oracle.encoded(dict(
            commandId=parent,taskId=oracle.TASK,runId=run,mode='s2-s3-oracle',exitCode=0,stageInputs={'plan':previous_plan})))
        wrong_parent=oracle.encoded({**index,'formalCommandId':parent})
        wrong_sha=oracle.sha(wrong_parent)
        (selected/('engineering-selection-'+wrong_sha+'.json')).write_bytes(wrong_parent)
        args=cli.copy()
        args[args.index('--gate')+1]='interaction'
        args[args.index('--input-key')+1]=plan['inputKeys']['interaction']
        args[args.index('--selection-sha')+1]=wrong_sha
        self.assertIn('OMQ_CURRENT_FORMAL_SCOPE',execute(args,1,{**env,'OMQ_PRODUCT_RUN':run})[1])
        selection.write_bytes(raw+b'\n')
        self.assertIn('OMQ_CURRENT_SELECTION_SHA',execute(cli,1,{**env,'OMQ_PRODUCT_RUN':run})[1])
        selection.write_bytes(raw)
        (area/'commands'/run/index['tests']['binding']['commandId']/'stdout.txt').unlink()
        self.assertIn('FileNotFoundError',execute(cli,1,{**env,'OMQ_PRODUCT_RUN':run})[1])

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

    def test_resume_case_command_rejects_mismatched_run_command_and_registered_fingerprint(self):
        # 隔离 Git 目录只提供 CLI 到命令消费者的前半段材料；缺少浏览器原件，任何分支都不能签产品 PASS。
        root=self.root
        scripts=root/'scripts/maintenance'
        modules=('workflow_oracle_mapping_evidence','workflow_execution','workflow_evidence','workflow_oracle_mapping_resources',
                 'workflow_m2_build','workflow_m2_evidence','execution_preflight','task_run_timeline',
                 'workflow_oracle_mapping_access_refresh','workflow_oracle_mapping_continuity')
        for name in modules:
            shutil.copyfile(ROOT/'scripts/maintenance'/(name+'.py'),scripts/(name+'.py'))
        for name in oracle.DRIVERS:
            shutil.copyfile(ROOT/name,root/name)
        (root/'.gitignore').write_text('artifacts/\n__pycache__/\n')
        source='backend/fixture.txt'
        (root/'backend').mkdir()
        (root/source).write_bytes(b'offline qualification fixture\n')
        def git(*args):
            return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True,timeout=10).stdout.strip()
        git('init','-q')
        git('add','.')
        git('-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-qm','offline case inputs')
        head=git('rev-parse','HEAD')
        run=oracle.PRODUCT_RUN
        env={**os.environ,'OMQ_PRODUCT_RUN':run}
        base=root/'artifacts/workflow'/oracle.TASK
        area=base/run
        area.mkdir(parents=True)
        cid='a'*32
        stage={'phase':'s0','mode':oracle.READY,'case':'expired'}
        host=copy.deepcopy(self.host)
        host['runId']=run
        # fixture.txt 是该仓库唯一构建输入；两个无执行内容的输出标记只用于输入绑定分支。
        import workflow_m2_build as build
        input_key=oracle.sha(json.dumps({source:oracle.sha((root/source).read_bytes())},sort_keys=True).encode())
        builds={}
        for target in ('api','agent'):
            project=Path(build.TARGETS[target])
            marker=project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
            output=b'offline marker only: '+target.encode()
            (root/marker).parent.mkdir(parents=True)
            (root/marker).write_bytes(output)
            log=b'offline marker prepared\n'
            (base/(target+'-bound-build.txt')).write_bytes(log)
            outputs={str(marker):oracle.sha(output)}
            raw=oracle.encoded(dict(taskId=oracle.TASK,target=target,worktree=str(root),status='PASS',exitCode=0,
                                    inputKey=input_key,outputs=outputs,logSha256=oracle.sha(log)))+b'\n'
            (base/(target+'-build-binding.json')).write_bytes(raw)
            builds[target]=dict(inputKey=input_key,outputKey=oracle.sha(json.dumps(outputs,sort_keys=True).encode()),receiptSha256=oracle.sha(raw))
        host.update(buildInputKey=builds['api']['inputKey'],buildOutputKey=builds['api']['outputKey'])
        dispatch=dict(taskId=oracle.TASK,runId=run,commandId=cid,testedCommit=head,mode=oracle.READY,case='expired',
                      reports=['offline-sentinel.json'],builds=builds,host=host,stageInputs=stage)
        path=area/('formal-run-'+oracle.READY+'-'+cid+'.json')
        path.write_bytes(oracle.encoded(dispatch))
        args=[oracle.NODE,oracle.DRIVER,'--task',oracle.TASK,'--run-id',run,'--mode',oracle.READY]
        key=oracle.digest_value(dict(taskId=oracle.TASK,runId=run,mode=oracle.READY,case='expired',drivers=oracle.drivers(root,oracle.READY,run),
                                     api=builds['api'],tests=builds['agent'],host={k:v for k,v in host.items() if k!='commandId'},stageInputs=stage))
        # 收据原件和登记一起变化后先经无损 restore，再让真正 CLI 消费这些字节。
        receipt=dict(schemaVersion=2,taskId=oracle.TASK,runId=run,commandId=cid,parentId=host['commandId'],stage='omq-browser-'+oracle.READY,
                     cwd=str(root),commandSummary=oracle.summary(args),inputFingerprint=key,started=True,signal=None,classification='EXIT_FAILURE',
                     exitCode=1,deadlineSeconds=180,startedAtUtc='2026-11-19T00:00:00Z',endedAtUtc='2026-11-19T00:00:01Z',elapsedSeconds=1,
                     environmentFingerprint='a'*64)
        policy=oracle.sha((root/'scripts/maintenance/workflow_execution.py').read_bytes())
        receipt['identity']=oracle.digest_value([key,receipt['environmentFingerprint'],receipt['commandSummary']['sha256'],str(root),180,policy])
        command=base/'commands'/run/cid
        command.mkdir(parents=True)
        for stream in ('stdout','stderr'):
            (command/(stream+'.txt')).write_bytes(b'')
            receipt[stream]=dict(sizeBytes=0,sha256=oracle.sha(b''))
        member=Path('docs/evidence')/oracle.TASK/run/'offline-case'/'receipt.json'
        (root/member).parent.mkdir(parents=True)
        def register(row):
            raw=oracle.encoded(row)+b'\n'
            (root/member).write_bytes(raw)
            entry=dict(path=str(member),originalPath=str(member),encoding='raw',sizeBytes=len(raw),sha256=oracle.sha(raw))
            recovered=oracle.restore(root,entry)
            self.assertEqual(raw,recovered)
            (command/'receipt.json').write_bytes(recovered)
            return entry['sha256']
        def refuse(run_id,command_id,reason):
            argv=[sys.executable,'-B','scripts/maintenance/workflow_oracle_mapping_evidence.py','--task',oracle.TASK,'--run-id',run_id,'--case-command',command_id]
            proc=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(0,proc.returncode)
            self.assertEqual('OMQ_QUALIFICATION_REJECTED '+reason,proc.stderr.strip())
            self.assertEqual('',proc.stdout)
        original=register(receipt)
        # 准确控制先经过真实 Git 驱动、构建、stageInputs、argv、双流与命令身份，才由故意无效的报告名拒绝。
        refuse(run,cid,'OMQ_REPORT_NAME')
        refuse(oracle.RESOURCE_RUN,cid,'OMQ_COMMAND_SCOPE')
        refuse(run,'b'*32,'OMQ_RUNTIME_DISPATCH')
        path.write_bytes(oracle.encoded({**dispatch,'runId':oracle.RESOURCE_RUN}))
        refuse(run,cid,'OMQ_RUNTIME_DISPATCH_SCOPE')
        path.write_bytes(oracle.encoded(dispatch))
        for change in ({'commandId':'b'*32},{'runId':oracle.RESOURCE_RUN},{'inputFingerprint':'0'*64}):
            with self.subTest(change=change):
                self.assertNotEqual(original,register({**receipt,**change}))
                refuse(run,cid,'OMQ_COMMAND_BINDING')

    def test_audit_must_cover_the_actual_browser_command(self):
        row=dict(startedAtUtc='2026-11-19T00:00:00Z',endedAtUtc='2026-11-19T00:00:01Z')
        audit=dict(taskId=oracle.TASK,runId=oracle.RUN,startUtc=row['startedAtUtc'],endUtc='2026-11-19T00:00:02Z',
                   sourceId=self.host['oracle']['containerId'])
        with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_WINDOW'):
            oracle.audit_observation(self.archive,audit,row,self.host,self.origin)


class ProductResumeBindingTests(unittest.TestCase):
    def test_manifest_requires_both_exact_api_ids_and_all_approved_networks(self):
        labels=('api','api-secondary','platform-pg','keycloak-test','fuseki','rustfs','oracle')
        ids={r:str(i)*64 for i,r in enumerate(labels)}
        nets={k:c*64 for k,c in [('host-entry','c'),('platform-internal','d'),('source-internal','e')]}
        observed={}
        for name in labels[:-1]:
            connections={'platform-internal':nets['platform-internal']}
            if name in ('api','api-secondary','keycloak-test'):
                connections['host-entry']=nets['host-entry']
            if name in ('api','api-secondary'):
                connections['oracle']=nets['source-internal']
            observed[name]=dict(containerId=ids[name],networks=connections)
        h=dict(snapshotId='8'*64,services=observed,oracle=dict(containerId=ids['oracle'],networkId=nets['source-internal']),
               resourceManifestSha256='f'*64)
        m=dict(taskId=oracle.TASK,runId=oracle.PRODUCT_RUN,ids=ids,networks=nets,snapshotId='8'*64)
        oracle.verify_product_manifest(h,m,'f'*64)
        for change in (lambda x:x['ids'].update(api='a'*64),lambda x:x['networks'].update(**{'source-internal':'e'*63+'0'}),
                       lambda x:x.update(runId='implementation-01'),lambda x:x['ids'].pop('api-secondary')):
            copy_m=copy.deepcopy(m)
            change(copy_m)
            with self.assertRaises(ValueError):
                oracle.verify_product_manifest(h,copy_m,'f'*64)
        h['services']['platform-pg']['networks']['unapproved']='b'*64
        with self.assertRaisesRegex(ValueError,'OMQ_RESUME_SERVICE_NETWORKS'):
            oracle.verify_product_manifest(h,m,'f'*64)

    def test_legacy_audit_projection_keeps_physical_scope_and_source_sql(self):
        before=b'def audit_window():\n source = original()\n return issue(source,run=RUN)\n'
        after=(b'def audit_window(*,operation_run=RUN):\n source = original()\n if operation_run != RUN:\n'
               b'  source=alternative()\n return issue(source,run=operation_run)\n')
        self.assertEqual(oracle.audit_program(before),oracle.audit_program(after))
        self.assertNotEqual(oracle.audit_program(before),oracle.audit_program(after.replace(b'original()',b'other()')))
        self.assertNotEqual(oracle.audit_program(after,historical=False),oracle.audit_program(after.replace(b'alternative()',b'other()'),historical=False))

    def test_interactive_login_accepts_only_public_account_and_exact_realm(self):
        node=oracle.NODE if Path(oracle.NODE).is_file() else 'node'
        test=ROOT/'scripts/tests/WorkflowOracleNormalLogin.Tests.mjs'
        result=subprocess.run([node,'--test',str(test),str(test.with_name('WorkflowOracleAuthHandoff.Tests.mjs'))],cwd=ROOT,capture_output=True,timeout=6,
                              env=dict(os.environ,OMQ_PRODUCT_RUN='product-resume-01'))
        self.assertEqual(0,result.returncode,(result.stdout+result.stderr).decode())


class OracleSessionRestoreEvidenceTests(unittest.TestCase):
    """真实 S1 证据的离线反例：本人、新会话、GET 及零业务读取缺一不可。"""

    @staticmethod
    def fixture(mode):
        payload=b'{"status":"FOUND"}'
        query='query-'+'a'*32
        proof=dict(queryId=query,reportName='browser-s1-1790000000000.json',resultHash=oracle.sha(payload),
                   subjectId='original-q',sessionHash='a'*64)
        path='/api/v1/data/semantic-queries'
        http=[dict(method='GET',path=path+'/'+query+'/result',status=200,sha256=proof['resultHash'])]
        sessions=[dict(subjectId=subject,sessionHash=c*64) for subject,c in [('original-q','a'),('s1','b'),('s2','c'),('s3','d')]]
        audit=[]
        scope='S1_ORACLE_NEW_SESSION_RESULT_RESTORE'
        if mode=='s1':
            http += [dict(method='POST',path=path,status=200,sha256=proof['resultHash']) for _ in range(2)]
            audit=[dict(owner='PRODUCTION',table='OMQ_ENTITY',action='SELECT',code=0)]
            scope='S1_ORACLE_OIDC_QUERY_PERSISTENCE'
        return dict(mode=mode,scope=scope,oraclePersistence=proof,http=http,scenarioReady={'session':{'observations':sessions}}),dict(clientId=None,records=audit),{'readerSubjectId':'original-q'},payload

    def test_s1_fresh_and_replay_must_bind_bytes_and_the_single_read(self):
        report,audit,stage,payload=self.fixture('s1')
        self.assertEqual(report['oraclePersistence'],oracle.persistence_case(report,audit,stage,payload))
        for changed_audit,changed_payload in ((dict(audit,records=[]),payload),(dict(audit,records=audit['records']*2),payload),(audit,b'{}')):
            with self.assertRaises(ValueError):
                oracle.persistence_case(report,changed_audit,stage,changed_payload)
        report['http'].pop()
        with self.assertRaises(ValueError):
            oracle.persistence_case(report,audit,stage,payload)

    def test_legal_client_filter_cannot_count_reads_across_the_browser_window(self):
        client='1'*32
        start,end='2026-11-19T00:00:00Z','2026-11-19T00:00:01Z'
        scoped=observer.audit_invocation('a'*64,start,end,client)
        self.assertEqual(client,scoped['definition']['clientId'])
        self.assertIn("AND client_identifier='"+client+"'",scoped['body'])
        for mode in ('s1','s1-reopen'):
            with self.subTest(mode=mode):
                report,audit,stage,payload=self.fixture(mode)
                scoped_rows=[dict(row,clientId=client) for row in audit['records']]
                with self.assertRaisesRegex(ValueError,'OMQ_S1_AUDIT_CLIENT_FILTER'):
                    oracle.persistence_case(report,dict(clientId=client,records=scoped_rows),stage,payload)

    def test_reopen_rejects_other_subject_digest_and_source_reads(self):
        report,audit,stage,_=self.fixture('s1-reopen')
        self.assertEqual(report['oraclePersistence'],oracle.persistence_case(report,audit,stage))
        with self.assertRaises(ValueError):
            oracle.persistence_case(report,dict(audit,records=[{'action':'SELECT'}]),stage)
        with self.assertRaises(ValueError):
            oracle.persistence_case(report,audit,{'readerSubjectId':'other'})
        report['http'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):
            oracle.persistence_case(report,audit,stage)


class NaturalCancelEvidenceTests(unittest.TestCase):
    """离线反例只约束机器消费者；该组记录不能作为 Oracle 产品验收原件。"""

    @staticmethod
    def record():
        utc = lambda ms: f'2026-11-20T00:00:{ms//1000:02d}.{ms%1000:03d}Z'
        query, client, acquisition = 'query-'+'a'*32,'b'*32,'c'*32
        owner = 'oracle-execution-owner'
        def event(name,**values):
            return dict(name=name,query=query,execution=client,**values)
        begin = event('OracleBranchBegin',owner=owner,fence='1',utc=utc(105),workDeadlineUtc=utc(850),branchDeadlineUtc=utc(1100))
        session = event('OracleSourceSession',instance='1',sid='21',audsid='53',unified='75',con='3',utc=utc(111))
        def owned(phase,ms):
            return event('OracleSourceOwnership',phase=phase,utc=utc(ms),acquisition=acquisition)
        def native(action,ms):
            return event('OracleSourceEvent',action=action,utc=utc(ms))
        api = [begin,owned('ACQUIRED',108),session,native('EXECUTE',120),native('EOF',130),
               owned('READ_RETURNED',131),owned('ROLLED_BACK',158),owned('TX_DISPOSED',160),
               native('PHYSICAL_RELEASE',169),owned('PHYSICAL_DISPOSED',170),owned('CONFIRMED',171),
               event('OracleBranchRelease',confirmed='True',observedUtc=utc(172)),
               event('OracleCleanupCas',fence='1',released='True',observedUtc=utc(180))]
        def cleanup(trigger,when,deadline):
            return event('OracleSourceCleanup',trigger=trigger,utc=utc(when),acquisition=acquisition,
                         deadlineUtc=utc(deadline),remainingTicks=str((deadline-when)*10000))
        api.extend([cleanup('WORK_FAILURE',156,405),cleanup('PHYSICAL_DISPOSE',167,405),cleanup('FINAL',170,405)])
        commit = dict(name='OracleCancelCommit',query=query,originalFence='1',terminalFence='2',lowerUtc=utc(148),upperUtc=utc(151))
        original = dict(id=query,state='RUNNING',owner=owner,fence=1,cancel=False,deadline=utc(5000),observed=utc(104),
                        hash=None,bytes=None,receipts=0,cancelAudits=0,successAudits=0)
        terminal = dict(original,state='CANCELLED',owner=None,fence=2,cancel=True,cancelAudits=1,observed=utc(183))
        sql = 'aaaaaaaaaaaaa'
        active = dict(lo=utc(123),hi=utc(124),sid='21',serial='31',audsid='53',con='3',state='ACTIVE',sql=sql,
                      execution='4',start='20261120000000',previous='-',previousExecution='-')
        previous = dict(active,lo=utc(135),hi=utc(136),sql='-',execution='-',start='-',previous=sql,previousExecution='4')
        samples = [active,previous,dict(lo=utc(175),hi=utc(176),absent=True)]
        audit = dict(instance='1',session='75',owner='PRODUCTION',table='OMQ_ENTITY',action='SELECT',code=0,
                     clientId=client,auditExecution='12')
        clock = [dict(hostBefore=i,hostAfter=i,monoBefore=i,monoAfter=i,remote=i) for i in range(10)]
        return dict(queryId=query,sqlId=sql,clocks={k:clock for k in ('api','api-secondary','pg','source')},
                    logs={'api':api,'api-secondary':[commit]},platformStates=[original,terminal],
                    source={'events':samples},audit={'records':[audit]},cursorBefore={'0':[55,1,1,1,0]},
                    cursorAfter={'0':[55,2,2,2,0]},terminalReadback=dict(commandId='d'*32,state=dict(terminal)))

    def test_source_native_and_ownership_path_qualify_only_natural_race(self):
        for with_post in (True,False):
            with self.subTest(with_post=with_post):
                record=self.record()
                if with_post:
                    api=record['logs']['api']
                    api[:]=[e for e in api if e.get('trigger')!='WORK_FAILURE']
                    api[6].update(phase='COMMITTED',utc='2026-11-20T00:00:00.132Z')
                    api[7].update(utc='2026-11-20T00:00:00.133Z')
                    api[8:8]=[dict(api[7],phase='POST_STARTED',utc='2026-11-20T00:00:00.135Z'),
                              dict(api[7],phase='POST_RETURNED',utc='2026-11-20T00:00:00.151Z')]
                proof=observer.classify(record)
                self.assertTrue(proof['naturalCompletionBeforeCancel'])
                self.assertLessEqual(proof['naturalCleanupUpperMs'],250)
                self.assertFalse(proof['nativeCancelCausedTermination'])
                self.assertFalse(proof['sameExecutionActiveAtCommit'])

    def test_missing_or_conflicting_evidence_cannot_confirm_natural_race(self):
        def late_gone(r):
            r['source']['events'][-1].update(lo='2026-11-20T00:00:00.420Z',hi='2026-11-20T00:00:00.421Z')
        def late_read(r):
            r['logs']['api'][5].update(utc='2026-11-20T00:00:00.153Z')
        for case,mutate in {
            'no-independent-end':lambda r:r['source']['events'].pop(1),
            'only-absence':lambda r:r['source']['events'].__delitem__(slice(0,2)),
            'no-physical-return':lambda r:r['logs']['api'].pop(9),
            'wrong-acquisition':lambda r:r['logs']['api'][5].update(acquisition='2'*32),
            'unclosed-post':lambda r:r['logs']['api'].insert(8,dict(r['logs']['api'][7],phase='POST_STARTED')),
            'source-session':lambda r:r['source']['events'][1].update(serial='2'),
            'another-execution':lambda r:r['source']['events'][1].update(previousExecution='29'),
            'no-cas':lambda r:next(e for e in r['logs']['api'] if e['name']=='OracleCleanupCas').update(released='False'),
            'wrong-owner':lambda r:r['platformStates'][0].update(owner='other'),
            'wrong-fence':lambda r:next(e for e in r['logs']['api'] if e['name']=='OracleCleanupCas').update(fence='2'),
            'not-eof':lambda r:r['cursorAfter']['0'].__setitem__(2,1),
            'lost-readback':lambda r:r['terminalReadback'].update(commandId=''),
            'wrong-result':lambda r:r['terminalReadback']['state'].update(receipts=1),
            'late-release':late_gone,'late-read':late_read
        }.items():
            with self.subTest(case=case):
                record=self.record()
                mutate(record)
                self.assertFalse(observer.classify(record).get('naturalCompletionBeforeCancel'))

    def test_earlier_driver_cleanup_and_cross_execution_identity_remain_binding(self):
        def shift(e,offset_ms):
            base=observer.ns(e['utc'])
            when=observer.dt.datetime.fromtimestamp((base+offset_ms*1_000_000)/1e9,observer.ZONE)
            e.update(deadlineUtc=when.isoformat(timespec='microseconds'),remainingTicks=str(offset_ms*10000))
        def late_from_local_trigger(r):
            early=r['logs']['api'][-3]
            shift(early,22)
            shift(r['logs']['api'][-1],8)
        def ambiguous_dispatch(r):
            begin=r['logs']['api'][0]
            r['logs']['api'].append(dict(begin,name='OracleCancelDispatch',owner='other',cleanupRemainingMs='25'))
        for case,mutate in {
            'earlier-than-platform-250':late_from_local_trigger,
            'missing-final':lambda r:r['logs']['api'].pop(),
            'missing-physical':lambda r:r['logs']['api'].pop(-2),
            'no-first-failure':lambda r:r['logs']['api'].pop(-3),
            'unknown-trigger':lambda r:r['logs']['api'][-3].update(trigger='UNREGISTERED'),
            'expiry':lambda r:shift(r['logs']['api'][-1],0),
            'inconsistent-ticks':lambda r:r['logs']['api'][-1].update(remainingTicks='1'),
            'cross-acquisition':lambda r:r['logs']['api'][-1].update(acquisition='e'*32),
            'ignored-earliest':lambda r:shift(r['logs']['api'][-3],25),
            'dispatch-owner':ambiguous_dispatch,
        }.items():
            with self.subTest(case=case):
                record=self.record()
                mutate(record)
                self.assertFalse(observer.classify(record).get('naturalCompletionBeforeCancel'))
        record=self.record()
        record['logs']['api'][-1]['execution']='e'*32
        with self.assertRaisesRegex(ValueError,'MULTIPLE_BRANCH_IDENTITIES'):
            observer.classify(record)

    def test_old_witness_preserves_original_result_fields(self):
        record=self.record()
        record['logs']['api']=[ev for ev in record['logs']['api'] if ev['name']!='OracleSourceOwnership']
        proof=observer.classify(record)
        self.assertNotIn('naturalCompletionBeforeCancel',proof)
        self.assertNotIn('naturalCleanupUpperMs',proof)
        self.assertFalse(proof['nativeCancelCausedTermination'])


if __name__=='__main__':
    unittest.main()


class NaturalSuccessEvidenceTests(unittest.TestCase):
    """成功先赢仍必须提供完整 AC03-A 原件；离线反例不授予产品资格。"""
    @staticmethod
    def record():
        r=NaturalCancelEvidenceTests.record()
        r['logs']['api-secondary']=[]
        r['logs']['api']=[e for e in r['logs']['api'] if e['name']!='OracleCleanupCas' and e.get('trigger')!='WORK_FAILURE']
        for e in r['logs']['api']:
            if e.get('phase')=='ROLLED_BACK':e['phase']='COMMITTED'
        first,terminal=r['platformStates']
        first['leaseUntil']=first['deadline']
        terminal.update(state='COMPLETED',cancel=False,fence=1,hash='f'*64,bytes=200,receipts=1,successAudits=1,cancelAudits=0,leaseUntil=None)
        r['terminalReadback']['state']=dict(terminal)
        return r

    @staticmethod
    def report(proof):
        return dict(scope='ORACLE_NATURAL_SUCCESS_BEFORE_CANCEL',http=[dict(method='POST',
            path='/api/v1/data/semantic-queries/'+proof['queryId']+'/cancel',status=409,code='query_already_finished')],
            oracleWitness=dict(cancel=dict(httpStatus=409,code='query_already_finished'),execute=dict(status=200,queryStatus='FOUND',elapsedMs=230)))

    def test_actual_success_consumer_and_complete_source_proof_pass_without_b(self):
        proof=observer.classify(self.record())
        self.assertTrue(proof['naturalSuccessWon'])
        self.assertFalse(proof['nativeCancelCausedTermination'])
        self.assertFalse(proof['sameExecutionActiveAtCommit'])
        oracle.natural_race_case(self.report(proof),proof)

    def test_every_missing_ownership_or_cleanup_event_is_rejected(self):
        r=self.record()
        positions=[i for i,e in enumerate(r['logs']['api']) if e['name'] in ('OracleSourceOwnership','OracleSourceCleanup')]
        for i in positions:
            changed=copy.deepcopy(r);changed['logs']['api'].pop(i)
            with self.subTest(i=i):self.assertFalse(observer.classify(changed).get('naturalSuccessWon'))

    def test_wrong_identity_owner_fence_or_readback_rejected(self):
        changes=[lambda r:r['logs']['api'][0].update(owner='oracle-execution-other'),
            lambda r:r['logs']['api'][1].update(acquisition='e'*32),
            lambda r:r['logs']['api'][1].update(query='query-'+'e'*32),
            lambda r:r['terminalReadback']['state'].update(fence=2),
            lambda r:r['source']['events'][1].update(serial='99'),
            lambda r:r['source']['events'][1].update(previousExecution='99')]
        for i,change in enumerate(changes):
            r=self.record();change(r)
            with self.subTest(i=i):self.assertFalse(observer.classify(r).get('naturalSuccessWon'))

    def test_repeated_effects_wrong_terminal_or_uncleared_lease_rejected(self):
        for key,value in [('receipts',3),('successAudits',3),('cancelAudits',1),('fence',2),('state','FAILED'),
                          ('cancel',True),('owner','oracle-execution-other'),('leaseUntil','2026-11-20T00:00:05Z'),('hash',None),('bytes',0)]:
            r=self.record();r['platformStates'][-1][key]=value;r['terminalReadback']['state'][key]=value
            with self.subTest(key=key):self.assertFalse(observer.classify(r).get('naturalSuccessWon'))

    def test_residual_source_and_original_deadline_overrun_rejected(self):
        changes=[lambda r:r['source']['events'].pop(),
            lambda r:r['source']['events'][-1].update(lo='2026-11-20T00:00:00.420Z',hi='2026-11-20T00:00:00.421Z'),
            lambda r:r['logs']['api'][0].update(workDeadlineUtc='2026-11-20T00:00:00.125Z'),
            lambda r:r['logs']['api'][0].update(branchDeadlineUtc='2026-11-20T00:00:00.175Z')]
        for i,change in enumerate(changes):
            r=self.record();change(r)
            with self.subTest(i=i):self.assertFalse(observer.classify(r).get('naturalSuccessWon'))

    def test_unfinished_postcheck_is_rejected(self):
        r=self.record();event=next(e for e in r['logs']['api'] if e.get('phase')=='TX_DISPOSED')
        i=r['logs']['api'].index(event)+1
        r['logs']['api'].insert(i,dict(event,phase='POST_STARTED',utc='2026-11-20T00:00:00.161Z'))
        self.assertFalse(observer.classify(r).get('naturalSuccessWon'))
        r['logs']['api'].insert(i+1,dict(event,phase='POST_RETURNED',utc='2026-11-20T00:00:00.162Z'))
        self.assertTrue(observer.classify(r).get('naturalSuccessWon'))

    def test_unanchored_sample_early_release_and_cancelled_cleanup_are_rejected(self):
        def old_source(r):
            for e in r['source']['events'][:-1]:
                e.update(lo='2026-11-19T23:59:59.123Z',hi='2026-11-19T23:59:59.124Z')
        def cancelled(r):
            physical=next(e for e in r['logs']['api'] if e.get('trigger')=='PHYSICAL_DISPOSE')
            r['logs']['api'].append(dict(physical,trigger='WORK_CANCELLED'))
        def early_release(r):
            next(e for e in r['logs']['api'] if e.get('action')=='PHYSICAL_RELEASE')['utc']='2026-11-20T00:00:00.159Z'
        for change in (old_source,cancelled,early_release,lambda r:r['logs']['api'][2].update(utc='2025-01-01T00:00:00Z'),
                       lambda r:r['logs']['api'][0].update(owner=''),
                       lambda r:r['platformStates'][-1].update(observed='2026-11-20T00:00:00.160Z')):
            r=self.record();change(r)
            self.assertFalse(observer.classify(r).get('naturalSuccessWon'))

    def test_source_reappearance_after_release_is_rejected(self):
        r=self.record();active=dict(r['source']['events'][0],lo='2026-11-20T00:00:00.190Z',hi='2026-11-20T00:00:00.191Z')
        r['source']['events'] += [active,dict(absent=True,lo='2026-11-20T00:00:00.200Z',hi='2026-11-20T00:00:00.201Z')]
        self.assertFalse(observer.classify(r).get('naturalSuccessWon'))

    def test_natural_trigger_requires_exact_unique_acquisition_and_execution(self):
        r=self.record();api=r['logs']['api'];query=r['queryId']
        self.assertTrue(observer.natural_return_event(api,query))
        for field,value in [('query','query-'+'e'*32),('execution','e'*32),('acquisition','e'*32)]:
            changed=copy.deepcopy(api);next(e for e in changed if e.get('phase')=='READ_RETURNED')[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'FORMAL_NATURAL_RETURN_IDENTITY'):
                observer.natural_return_event(changed,query)
        self.assertFalse(observer.natural_return_event([e for e in api if e.get('phase')!='READ_RETURNED'],query))
        with self.assertRaisesRegex(ValueError,'FORMAL_NATURAL_RETURN_IDENTITY'):
            observer.natural_return_event(api+[next(e for e in api if e.get('phase')=='READ_RETURNED')],query)

    def test_actual_http_code_and_single_cancel_request_are_required(self):
        proof=observer.classify(self.record())
        for change in (lambda r:r['http'][0].update(code='other'),lambda r:r['http'].append(dict(r['http'][0])),
                       lambda r:r['oracleWitness']['cancel'].update(code='other'),lambda r:r['oracleWitness']['execute'].update(status=504)):
            report=self.report(proof);change(report)
            with self.assertRaisesRegex(ValueError,'OMQ_NATURAL_SUCCESS_RACE'):oracle.natural_race_case(report,proof)

    def test_cancel_winner_cannot_keep_success_effects(self):
        proof=observer.classify(NaturalCancelEvidenceTests.record())
        report=dict(scope='ORACLE_NATURAL_COMPLETION_BEFORE_PLATFORM_CANCEL',oracleWitness=dict(cancel=dict(httpStatus=200,executionStatus='CANCELLED'),
                    execute=dict(status=409,elapsedMs=230)))
        oracle.natural_race_case(report,proof)
        for field in ('successfulResults','successReceipts','successAudits'):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'OMQ_NATURAL_CANCEL_RACE'):
                oracle.natural_race_case(report,dict(proof,**{field:1}))


if __name__ == '__main__':
    unittest.main()
