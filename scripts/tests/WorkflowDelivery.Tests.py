#!/usr/bin/env python3
"""交付通道反例；真实短子进程不代表产品 E2E。"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
import workflow_m2_evidence as evidence
import workflow_m2_fixture as fixture

class DeliveryTests(unittest.TestCase):
    def test_original_rejects_conflicting_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            path=root/'docs/evidence/G4-M2-WEB-01/test/receipt.json'
            path.parent.mkdir(parents=True)
            raw=b'total: 29 failed: 0 succeeded: 29 skipped: 0\ntotal: 1 failed: 1 succeeded: 0 skipped: 0\n'
            (path.parent/'unit.txt').write_bytes(raw)
            path.write_text(json.dumps(dict(taskId=evidence.build.TASK,exitCode=0,buildBinding={},log='unit.txt',logSha256=hashlib.sha256(raw).hexdigest())))
            with patch.object(evidence.build,'ROOT',root):
                with self.assertRaises(ValueError):evidence.original('unit',path,{'connections':{}})

    def test_fixture_preserves_stdout_whitespace(self):
        self.assertEqual(fixture.command([sys.executable,'-c',"import sys;sys.stdout.write('  start\\n\\n')"]),'  start\n\n')

class RunnerTests(unittest.TestCase):
    def test_repeat_failure_is_blocked_across_runs(self):
        import workflow
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();counter=root/'count'
            command=[sys.executable,'-c',"from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_text(p.read_text()+'x' if p.exists() else 'x');sys.exit(7)",str(counter)]
            workflow.execute_gate(command,root,task='DELIVERY-TEST',run_id='one')
            with self.assertRaisesRegex(ValueError,'BLOCKED|SHORT_REPRO'):
                workflow.execute_gate(command,root,task='DELIVERY-TEST',run_id='two')
            self.assertEqual(counter.read_text(),'x')

    def test_unverified_termination_never_returns_zero(self):
        import os,signal
        import workflow_execution as execution
        if os.name=='nt':self.skipTest('POSIX process group scenario')
        real=execution.os.killpg
        def group(pid,sig):
            if sig:real(pid,sig)
        with tempfile.TemporaryDirectory() as directory,patch.object(execution.os,'killpg',side_effect=group):
            result=execution.run([sys.executable,'-c','import os,time;pid=os.fork();time.sleep(5) if pid==0 else None'],Path(directory).resolve(),task='DELIVERY-TEST',timeout=.05)
            self.assertNotEqual(result.returncode,0)
            self.assertNotEqual(result.receipt['classification'],'SUCCESS')

    def test_sigterm_interrupt_closes_child_and_records_end(self):
        import os,signal,subprocess,time
        if os.name=='nt':self.skipTest('POSIX cancellation scenario')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();marker=root/'child-pid'
            child="import os,time;from pathlib import Path;Path("+repr(str(marker))+").write_text(str(os.getpid()));time.sleep(10)"
            script="import sys;from pathlib import Path;sys.path.insert(0,"+repr(str(Path(__file__).resolve().parents[1]/'maintenance'))+");import workflow_execution as x;x.run("+repr([sys.executable,'-c',child])+",Path("+repr(str(root))+"),task='DELIVERY-TEST')"
            process=subprocess.Popen([sys.executable,'-B','-c',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try:
                for _ in range(200):
                    if marker.exists():break
                    time.sleep(.01)
                self.assertTrue(marker.exists())
                process.send_signal(signal.SIGTERM);process.communicate(timeout=5)
                self.assertNotEqual(process.returncode,0)
                rows=[json.loads(line) for line in (root/'artifacts/workflow/DELIVERY-TEST/command-events.jsonl').read_text().splitlines()]
                self.assertEqual(rows[-1]['event'],'END');self.assertEqual(rows[-1]['classification'],'CANCELLED')
                with self.assertRaises(ProcessLookupError):os.kill(int(marker.read_text()),0)
            finally:
                if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=5)

    def test_raw_streams_and_timeout(self):
        import workflow_execution as execution
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            row=execution.run([sys.executable,'-c',"import os;os.write(1,b'  start\\n\\n');os.write(2,b'err\\n')"],root,task='DELIVERY-TEST')
            self.assertEqual(row.stdout,b'  start\n\n');self.assertEqual(row.stderr,b'err\n')
            self.assertEqual(Path(row.receipt['stdout']['path']).read_bytes(),row.stdout)
            timeout=execution.run([sys.executable,'-c','import time;time.sleep(10)'],root,task='DELIVERY-TEST',timeout=.05)
            self.assertEqual(timeout.receipt['classification'],'TIMEOUT')
            self.assertNotEqual(timeout.returncode,0)
            self.assertNotEqual(timeout.receipt['exitCode'],124)

class ReportsTests(unittest.TestCase):
    def test_machine_vitest_rejects_failed_missing_unknown_and_counts(self):
        from workflow_evidence import machine
        row=dict(numTotalTestSuites=1,numPassedTestSuites=1,numFailedTestSuites=0,numPendingTestSuites=0,success=True,numTotalTests=1,numPassedTests=1,numFailedTests=0,numPendingTests=0,numTodoTests=0,testResults=[dict(status='passed',message='',assertionResults=[dict(status='passed')])])
        self.assertEqual(machine(json.dumps(row).encode(),'vitest-json'),1)
        for change in ({'success':False},{'numFailedTestSuites':1},{'testResults':[dict(status='failed',message='teardown failed',assertionResults=[dict(status='passed')])]}, {'numFailedTests':1},{'numTotalTests':2},{'testResults':[]}):
            with self.assertRaises(ValueError):machine(json.dumps({**row,**change}).encode(),'vitest-json')
        with self.assertRaises(ValueError):machine(b'{}','unknown')

    def test_trx_external_entities_and_depth_rejected(self):
        from workflow_evidence import machine
        for raw in (b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x/>',b'<x>'*65+b'</x>'*65):
            with self.assertRaises(ValueError):machine(raw,'trx')

    def test_historical_mtp_rejects_duplicate_missing_skip_zero(self):
        good=b'total: 29 failed: 0 succeeded: 29 skipped: 0'
        self.assertEqual(evidence.mtp(good,29),29)
        for raw in (good+good,good.replace(b'skipped: 0',b''),good.replace(b'skipped: 0',b'skipped: 1'),b'total: 0 failed: 0 succeeded: 0 skipped: 0'):
            with self.assertRaises(ValueError):evidence.mtp(raw,1)

class IntegrationTests(unittest.TestCase):
    def test_m2_dispatch_blocks_same_failure_before_consumer(self):
        import workflow_m2_web as web
        import workflow_execution as execution
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();counter=root/'count'
            def consumer(task):
                result=execution.run([sys.executable,'-c',"from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_text(p.read_text()+'x' if p.exists() else 'x');sys.exit(8)",str(counter)],root,task=task)
                return dict(status='FAIL' if result.returncode else 'PASS')
            with patch.object(web,'ROOT',root),patch.object(web,'structural',return_value={}),patch.object(web,'host',return_value={'assurance':'POLICY_READY'}),patch.object(web,'environment_identity',return_value={'synthetic':'protocol-test'}),patch.object(evidence.build,'inputs',return_value='stable-product'),patch.object(evidence.build,'driver_layers',return_value={'driver':'execution','parser':'qualification'}),patch.object(evidence.build,'driver_inputs',return_value={'driver':'stable','parser':'old'}) as inputs,patch.object(fixture,'run',side_effect=consumer):
                with self.assertRaisesRegex(ValueError,'EXECUTION_FAILED'):web.execute('fixture-test','DELIVERY-TEST')
                inputs.return_value={'driver':'stable','parser':'new-interpreter'}
                with self.assertRaisesRegex(ValueError,'SHORT_REPRO|BLOCKED'):web.execute('fixture-test','DELIVERY-TEST')
            self.assertEqual(counter.read_text(),'x')

    def test_cleanup_runs_after_failed_command(self):
        import workflow_execution as execution
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();command=[sys.executable,'-c','raise SystemExit(7)']
            execution.run(command,root,task='DELIVERY-TEST')
            with execution.cleanup_scope():
                result=execution.run(command,root,task='DELIVERY-TEST')
            self.assertEqual(result.returncode,7)

    def test_v3_raw_restore_and_rejections(self):
        import shutil
        from workflow_evidence import publish,restore
        source=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'scripts').mkdir()
            shutil.copyfile(source/'scripts/create-review-package.ps1',root/'scripts/create-review-package.ps1')
            for i,raw in enumerate((b'',b'  start\n\n',b'\x1b[31mcolor\x1b[0m',bytes([255,254,0]))):
                row=publish(root,'docs/evidence/DELIVERY-TEST/'+str(i)+'.txt',raw)
                self.assertEqual(restore(root,row),raw)
            for path,raw in [('docs/evidence/DELIVERY-TEST/denied.log',b'safe'),('docs/evidence/../../escape.txt',b'safe'),('docs/evidence/DELIVERY-TEST/secret.txt',b'-----BEGIN '+b'PRIVATE KEY-----')]:
                with self.assertRaises(ValueError):publish(root,path,raw)
            link=root/'docs/evidence/DELIVERY-TEST/link';link.symlink_to(root/'scripts')
            with self.assertRaises(ValueError):publish(root,'docs/evidence/DELIVERY-TEST/link/file.txt',b'safe')

    def test_nested_timing_union_and_unfinished_start(self):
        from workflow_execution import append,timing_summary
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'events.jsonl'
            for ident,start,end in [('parent',0,10),('child',2,4),('unknown',11,None)]:
                append(path,dict(commandId=ident,event='START',startedAtUtc='2026-11-12T00:00:%02d+00:00'%start))
                if end is not None:append(path,dict(commandId=ident,event='END',endedAtUtc='2026-11-12T00:00:%02d+00:00'%end))
            result=timing_summary(path)
            self.assertEqual(result['commandIntervalUnionSeconds'],10)
            self.assertEqual(result['unknownCommands'],['unknown'])

if __name__=='__main__':unittest.main()
