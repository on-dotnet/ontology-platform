#!/usr/bin/env python3
"""工程按影响计划的行为回归；隔离Git夹具不启动产品或下载。"""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'scripts/maintenance/workflow.py'
        if path.exists():
            spec = importlib.util.spec_from_file_location('workflow', path)
            cls.w = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.w)

    def test_entry_exists(self):
        self.assertTrue((ROOT / 'scripts/maintenance/workflow.py').is_file(), 'missing controlled workflow entry')

    def test_frontend_only_does_not_select_backend(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        plan = self.w.select_gates(['apps/web/src/components/connections/editor.tsx'])
        self.assertIn('web', plan['affected'])
        self.assertIn('interaction', plan['affected'])
        self.assertNotIn('backend', plan['affected'])
        self.assertNotIn('environment', plan['affected'])

    def test_driver_and_package_are_separate(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        browser = self.w.select_gates(['experiments/g4-m1-main-integration/browser.mjs'])
        self.assertIn('interaction', browser['affected'])
        self.assertNotIn('backend', browser['affected'])
        package = self.w.select_gates(['scripts/create-review-package.ps1'])
        self.assertIn('package', package['affected'])
        self.assertNotIn('backend', package['affected'])

    def test_shared_contract_propagates_and_unknown_refuses(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        plan = self.w.select_gates(['backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs'])
        self.assertTrue({'backend', 'web', 'interaction'} <= set(plan['affected']))
        self.assertEqual(self.w.select_gates(['new-unmapped-driver.py'])['status'], 'BLOCKED')
        self.assertEqual(self.w.select_gates(['docs/evidence/NEW/driver.py'])['status'], 'BLOCKED')

    def test_reuse_rejects_failure_skip_and_bad_hash(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'evidence.json'
            p.write_text('{}')
            row = dict(status='PASS', exitCode=0, tests=1, skipped=0, inputKey='key', environmentKey='env', policyKey='policy', evidenceSha256=self.w.digest(p.read_bytes()), sourceRun='T1', sourceCommit='a'*40, command=['python3','test.py'])
            self.assertTrue(self.w.reusable(row, 'key', 'env', 'policy', p))
            for change in ({'status':'FAIL'}, {'tests':0}, {'skipped':1}, {'evidenceSha256':'0'*64}, {'inputKey':'other'}, {'exitCode':1}):
                self.assertFalse(self.w.reusable(dict(row, **change), 'key', 'env', 'policy', p))
            p.unlink()
            self.assertFalse(self.w.reusable(row, 'key', 'env', 'policy', p))

    def test_content_keys_ignore_head_and_bind_transitive_files(self):
        if not hasattr(self, 'w'): self.skipTest('entry absent')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            subprocess.run(['git','init','-q',d],check=True)
            (root/'apps/web').mkdir(parents=True)
            (root/'apps/web/a.ts').write_text('one')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            first=self.w.input_key(root,'web')
            (root/'notes.md').write_text('unrelated')
            self.assertEqual(first,self.w.input_key(root,'web'))
            (root/'apps/web/a.ts').write_text('two')
            self.assertNotEqual(first,self.w.input_key(root,'web'))

    def test_json_evidence_does_not_invalidate_product(self):
        plan=self.w.select_gates(['docs/evidence/G4-ENG-WORKFLOW-001/summary.json'])
        self.assertNotIn('environment',plan['affected'])
        self.assertNotIn('backend',plan['affected'])
        self.assertIn('policy',plan['affected'])
        self.assertIn('environment',self.w.select_gates(['pnpm-lock.yaml'])['affected'])

    def test_zero_and_skipped_tests_refused(self):
        self.assertEqual(self.w.test_counts('Ran 0 tests in 0.000s\\nOK', 'python')[0],0)
        self.assertEqual(self.w.test_counts('Ran 4 tests in 0.001s\\nOK (skipped=1)', 'python'),(4,1))
        self.assertEqual(self.w.test_counts('Ran 7 tests in 0.001s\\nOK', 'python'),(7,0))

    def test_unknown_maintenance_never_claims_workflow_coverage(self):
        self.assertEqual(self.w.select_gates(['scripts/maintenance/new_runner.py'])['status'],'BLOCKED')

    def test_expected_fixture_rejection_does_not_hide_real_failure(self):
        summary='Ran 4 tests in 0.001s\nOK\n'
        expected='EXPECTED-REJECTION: FAIL: structured syntax invalid.yml (ParserError)\n'
        self.assertEqual(self.w.test_counts(expected+summary,'auto'),(4,0))
        for failure in ('FAIL: genuine failure\n','ERROR: genuine failure\n','FAILED (failures=1)\n'):
            self.assertEqual(self.w.test_counts(expected+failure+summary,'auto'),(0,0))
        self.assertEqual(self.w.test_counts(expected,'auto'),(0,0))

    def test_dependency_order(self):
        order=self.w.ordered(['interaction','web','backend','environment','contract'])
        self.assertLess(order.index('environment'),order.index('backend'))
        self.assertLess(order.index('backend'),order.index('interaction'))

    def test_full_identity_tracks_tests_without_default_full_schedule(self):
        self.assertIn('engineering-full',self.w.select_gates(['scripts/tests/StructuredFiles.Tests.ps1'])['affected'])
        paths=['scripts/tests/WorkflowEnvironment.Tests.py']
        self.assertNotIn('engineering-full',self.w.select_gates(paths)['affected'])
        self.assertTrue(self.w.matches(paths[0],self.w.input_patterns('engineering-full')))
        self.assertTrue(self.w.matches('scripts/maintenance/workflow_smoke.py',self.w.input_patterns('engineering-full')))

    def test_registry_edit_is_detected_despite_cached_definitions(self):
        raw=self.w.REGISTRY.read_bytes()
        key=self.w.input_key(ROOT,'engineering');policy=self.w.policy_key('engineering')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'registry.json';path.write_bytes(raw)
            with patch.object(self.w,'REGISTRY',path):
                self.assertTrue(self.w.inputs_stable(ROOT,'engineering',key,policy,self.w.digest(raw)))
                path.write_bytes(raw+b' ')
                self.assertFalse(self.w.inputs_stable(ROOT,'engineering',key,policy,self.w.digest(raw)))

    def test_failure_signature_ignores_time_and_temporary_path(self):
        first=b'FAIL: test_boundary (Tests)\n/tmp/run123/a.py\nRan 2 tests in 0.05s'
        second=b'FAIL: test_boundary (Tests)\n/tmp/run456/a.py\nRan 2 tests in 12.45s'
        self.assertEqual(self.w.error_signature(first,1),self.w.error_signature(second,1))
        self.assertNotEqual(self.w.error_signature(first,1),self.w.error_signature(b'FAIL: test_other (Tests)',1))

    def test_timeout_keeps_actual_exit_and_output(self):
        # 预期超时的失败状态只属于本例，不能污染仓库并阻断下一次自测。
        with tempfile.TemporaryDirectory() as directory:
            code,raw=self.w.execute_gate([sys.executable,'-u','-c','import time; print("started"); time.sleep(5)'],Path(directory).resolve(),0.05)
        self.assertEqual(code,124)
        self.assertIn(b'started',raw)

    def test_outer_verify_rejects_shorter_deadline_before_spawning_any_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory).resolve() / 'plan.json'
            plan.write_text(json.dumps(dict(affected=['engineering','engineering-full'])))
            command = [sys.executable, '-B', str(ROOT / 'scripts/maintenance/workflow.py'), 'verify', '--plan', str(plan)]
            with self.assertRaisesRegex(ValueError, 'VERIFY_OUTER_DEADLINE'):
                self.w.execute_gate(command, ROOT, timeout=230)
            self.assertEqual(3800, self.w.verification_deadline(['engineering','engineering-full']))

    def test_full_budget_counts_scratch_including_git_and_holds_host_margin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            prior = root / 'artifacts/workflow/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-01'
            prior.mkdir(parents=True)
            nonce = 'b' * 32
            path = prior / ('source-admission-' + nonce + '.json')
            gib = 1024**3
            allocations = dict(other=39*gib,newBuildEvidenceAndLogs=128*1024**2)
            witness = dict(taskId='G4-ORACLE-MAPPING-QUERY-001',runId='s0-recovery-01',phase='closed',expectedRunningRoles=[],
                           status='FORMAL_RESOURCE_READY',probeRemoved=True,attempt=nonce,endedUtc='2026-11-20T00:00:00Z',
                           platformDisk=dict(allocations=allocations,totalBytes=sum(allocations.values()),ceilingBytes=40*gib),
                           host=dict(diskBytes=20*gib,availableEstimate=12*gib),vm=dict(availableFs=20*gib))
            file = root / 'policy.json'
            file.write_text('{}')
            with patch.object(self.w, 'git', return_value=b'policy.json\0'), patch('shutil.disk_usage', return_value=type('Disk', (), {'free':20*gib})()):
                path.write_text(json.dumps(witness))
                budget = self.w.selftest_resources(root,path,root)
                self.assertGreater(budget['temporaryPeakBytes'], 32*1024**2)
                self.assertEqual(budget['projectedTaskBytes'],39*gib + budget['temporaryPeakBytes'])
                self.assertEqual(budget['hostJsonInputBytes'], 2)
                witness['host']['availableEstimate'] = 4*gib
                path.write_text(json.dumps(witness))
                with self.assertRaisesRegex(ValueError, 'SELFTEST_RESOURCE_HEADROOM'):
                    self.w.selftest_resources(root,path,root)
                witness['host']['availableEstimate'] = 12*gib
                allocations['other'] = 40*gib
                witness['platformDisk']['totalBytes'] = sum(allocations.values())
                path.write_text(json.dumps(witness))
                with self.assertRaisesRegex(ValueError, 'SELFTEST_RESOURCE_HEADROOM'):
                    self.w.selftest_resources(root,path,root)

    def test_immutable_reuse_reads_real_git_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            subprocess.run(['git','init','-q',d],check=True)
            subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','source'],cwd=root,check=True)
            source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            key=self.w.input_key(root,'engineering')
            folder=root/'docs/evidence/TEST';folder.mkdir(parents=True)
            log=folder/'run.log';log.write_text('Ran 2 tests in 0.01s\nOK\n')
            row=dict(gate='engineering',status='PASS',inputsUnchanged=True,exitCode=0,tests=2,skipped=0,inputKey=key,environmentKey='env',policyKey='policy',command=self.w.registry()['engineering']['command'],sourceCommit=source,sourceRun='T1',logPath='docs/evidence/TEST/run.log',evidenceSha256=self.w.digest(log.read_bytes()))
            (folder/'receipt.json').write_text(json.dumps(row))
            subprocess.run(['git','add','.'],cwd=root,check=True)
            subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','evidence'],cwd=root,check=True)
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            index={'engineering':{'commit':commit,'path':'docs/evidence/TEST/receipt.json'}}
            with patch.object(self.w,'ROOT',root):
                reused=self.w.load_reuse(index,'engineering',key,'env','policy')
                self.assertEqual(reused['executionMode'],'REUSED')
                self.assertNotIn('exitCode',reused)
                with self.assertRaisesRegex(ValueError,'REUSE_INELIGIBLE'):
                    self.w.load_reuse(index,'engineering','changed','env','policy')
                log.write_text('tampered working copy')
                self.assertEqual(self.w.load_reuse(index,'engineering',key,'env','policy')['evidenceCommit'],commit)

    def test_doc_executable_fixture_is_not_treated_as_prose(self):
        self.assertEqual(self.w.select_gates(['docs/evidence/OTHER/fixture.json'])['status'],'BLOCKED')
        self.assertEqual(self.w.select_gates(['docs/evidence/OTHER/driver.py'])['status'],'BLOCKED')

    def test_published_output_uses_existing_package_path_rules(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.w.write_gate_output(Path(d),'engineering',b'Ran 2 tests in 0.01s\nOK\n')
            self.assertEqual(output.read_bytes(),b'Ran 2 tests in 0.01s\nOK\n')
            self.w.validate_package_paths(ROOT,['docs/evidence/TEST/'+output.name])
            with self.assertRaisesRegex(ValueError,'PACKAGE_PATH_REJECTED'):
                self.w.validate_package_paths(ROOT,['docs/evidence/TEST/forbidden.log'])

    def test_package_estimate_requires_exact_commits(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'FULL_COMMIT_REQUIRED'):
                self.w.package_budget(Path(d),'main','HEAD','TASK-001')


    @contextlib.contextmanager
    def production_measurement(self, variant='identical', task='G4-M5-INTEGRATION-001', through_plan=False):
        """真实Git小夹具调用生产PowerShell，再由实际Python消费者解释；不启动产品。"""
        import shutil
        import os
        sys.path.insert(0, str(ROOT/'scripts/maintenance'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root).decode().strip()
            git('init', '-q'); git('config', 'user.name', 'EF01 Fixture'); git('config', 'user.email', 'fixture@example.invalid')
            (root/'.gitignore').write_text('artifacts/\n')
            (root/'scripts').mkdir(); shutil.copyfile(ROOT/'scripts/create-review-package.ps1', root/'scripts/create-review-package.ps1')
            content = '{"scope":"synthetic EF-01","status":"NOT_RUN"}\n'
            if variant == 'shared-source': (root/'a-shared.json').write_text(content)
            git('add', '.'); git('commit', '-qm', 'base'); base = git('rev-parse', 'HEAD')
            prefix = 'docs/evidence/'+task+'/'
            paths = [prefix+'entry-fix-02/reports/'+name+'.json' for name in ('a','b')]
            if task == 'G4-DORIS-MAPPING-QUERY-001':
                paths = [prefix+'implementation-01/s0-source-review.json', prefix+'implementation-01/s1/browser-s1-123.json']
            for index, name in enumerate(paths):
                p = root/name; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content if variant != 'different' or index == 0 else '{"scope":"different synthetic EF-01","status":"NOT_RUN"}\n')
            git('add', '.'); git('commit', '-qm', 'representatives'); head = git('rev-parse', 'HEAD')
            try:
                if through_plan:
                    with patch.object(self.w, 'ROOT', root):
                        result, = self.w.plan(base, head)['earlyMeasurements']
                else:
                    result = self.w.measure_committed_evidence(root, base, head, task)
                yield root, base, head, task, paths, result
            finally:
                if os.environ.get('WORKFLOW_EF01_EVIDENCE_DIR'):
                    target = Path(os.environ['WORKFLOW_EF01_EVIDENCE_DIR'])/(variant+'-'+head)
                    # 相同源码/秒内提交可生成同Head；不同测试仍保持各自实际执行原件。
                    import uuid
                    target = target.with_name(target.name+'-'+uuid.uuid4().hex[:8]); target.mkdir(parents=True, exist_ok=False)
                    shutil.copytree(root/'artifacts', target/'artifacts')
                    sources = paths + (['a-shared.json'] if variant == 'shared-source' else [])
                    (target/'fixture.json').write_text(json.dumps(dict(base=base, head=head, taskId=task, variant=variant,
                        producerSha256=self.w.digest((root/'scripts/create-review-package.ps1').read_bytes()),
                        consumerSha256=self.w.digest((ROOT/'scripts/maintenance/workflow.py').read_bytes()),
                        sources=[dict(gitPath=name, blobOid=git('rev-parse', head+':'+name), text=(root/name).read_text()) for name in sources]), indent=2)+'\n')

    def test_plan_dispatches_both_tasks_to_production_measurement(self):
        for task in ('G4-M5-INTEGRATION-001','G4-DORIS-MAPPING-QUERY-001'):
            with self.subTest(task=task), self.production_measurement(task=task, through_plan=True) as (root, base, head, _, paths, result):
                self.assertEqual(result['status'], 'MEASURED_NOT_READY_FOR_ACCEPTANCE')
                evidence = result['measurement']['representativeEvidence']
                self.assertEqual((evidence['taskId'],evidence['baseSha'],evidence['headSha']), (task,base,head))
                self.assertEqual({row['gitPath'] for row in evidence['sourceMembers']},set(paths))
                self.assertEqual(len(evidence['payloads']),1)
                self.assertFalse((root/'artifacts/reviews').exists())

    def test_production_measurement_accepts_identical_representative_json(self):
        for variant in ('different', 'identical', 'shared-source'):
            with self.subTest(variant=variant), self.production_measurement(variant) as (root, base, head, task, paths, result):
                self.assertEqual(result['status'], 'MEASURED_NOT_READY_FOR_ACCEPTANCE')
                description = result['measurement']['representativeEvidence']
                self.assertEqual({row['gitPath'] for row in description['sourceMembers']}, set(paths))
                self.assertEqual(len(description['payloads']), 2 if variant == 'different' else 1)
                if variant == 'shared-source': self.assertEqual(description['payloads'][0]['archivePath'], 'source/a-shared.json')
                self.assertFalse((root/'artifacts/reviews').exists())

    def test_real_producer_output_rejects_missing_conflicting_or_wrong_identity(self):
        from types import SimpleNamespace
        import workflow_execution
        with self.production_measurement() as (root, base, head, task, paths, result):
            for path in (root/'artifacts/workflow'/task/'package-measurements').glob('*.json'): path.unlink()
            cases = ['missing-mapping', 'missing-payload', 'missing-member', 'source-sha', 'source-length', 'source-blob',
                     'payload-sha', 'payload-length', 'duplicate-mapping', 'conflict-mapping', 'duplicate-payload',
                     'wrong-task', 'wrong-head', 'wrong-base', 'wrong-top-head', 'index-only', 'same-sha-other-path', 'path-case', 'old-protocol']
            for case in cases:
                measured = copy.deepcopy(result['measurement']); d = measured['representativeEvidence']
                if case == 'missing-mapping': d['sourceMembers'].pop()
                if case == 'missing-payload': d['payloads'] = []
                if case == 'missing-member': measured['members'].remove(d['payloads'][0]['archivePath'])
                if case == 'source-sha': d['sourceMembers'][0]['sha256'] = '0'*64
                if case == 'source-length': d['sourceMembers'][0]['sizeBytes'] += 1
                if case == 'source-blob': d['sourceMembers'][0]['blobOid'] = '0'*40
                if case == 'payload-sha': d['payloads'][0]['sha256'] = '0'*64
                if case == 'payload-length': d['payloads'][0]['sizeBytes'] += 1
                if case in ('duplicate-mapping', 'conflict-mapping'):
                    extra = copy.deepcopy(d['sourceMembers'][0])
                    if case == 'conflict-mapping': extra['archivePath'] = 'source/other.json'
                    d['sourceMembers'].append(extra)
                if case == 'duplicate-payload': d['payloads'].append(copy.deepcopy(d['payloads'][0]))
                if case == 'wrong-task': d['taskId'] = 'OTHER-TASK'
                if case == 'wrong-head': d['headSha'] = '0'*40
                if case == 'wrong-base': d['baseSha'] = '0'*40
                if case == 'wrong-top-head': measured['headSha'] = '0'*40
                if case == 'index-only': d['sourceMembers'][0]['archivePath'] = None
                if case == 'same-sha-other-path': d['payloads'][0]['archivePath'] = 'source/.gitignore'
                if case == 'path-case': d['sourceMembers'][0]['gitPath'] = paths[0].upper()
                if case == 'old-protocol': measured.pop('representativeEvidence')
                mutated = SimpleNamespace(returncode=0, stdout=json.dumps(measured).encode(), receipt=result['commandReceipt'])
                with self.subTest(case=case), patch.object(workflow_execution, 'run', return_value=mutated):
                    with self.assertRaisesRegex(ValueError, 'MEASUREMENT_|EARLY_REPRESENTATIVE_NOT_INCLUDED'):
                        self.w.measure_committed_evidence(root, base, head, task)
                self.assertFalse(list((root/'artifacts/workflow'/task/'package-measurements').glob('*.json')))

    def test_measurement_cache_reinterprets_original_and_invalidates_old_protocol(self):
        import workflow_execution
        with self.production_measurement() as (root, base, head, task, paths, result):
            directory = root/'artifacts/workflow'/task/'package-measurements'; cache = next(directory.glob('*.json'))
            damaged = copy.deepcopy(result); damaged['measurement']['representativeEvidence']['sourceMembers'] = []; damaged['status'] = 'PASS'
            cache.write_text(json.dumps(damaged))
            with patch.object(workflow_execution, 'run') as execute:
                current = self.w.measure_committed_evidence(root, base, head, task); execute.assert_not_called()
            self.assertEqual(current['status'], 'MEASURED_NOT_READY_FOR_ACCEPTANCE')
            self.assertEqual(len(current['measurement']['representativeEvidence']['sourceMembers']), 2)
            # 即使缓存中的原流散列同步变更，缺逻辑映射仍必须由协议校验拒绝。
            altered = copy.deepcopy(result['measurement']); altered['representativeEvidence']['sourceMembers'] = []
            stdout = directory/'tampered-stdout.txt'; stdout.write_text(json.dumps(altered))
            damaged['commandReceipt']['stdout'] = dict(path=str(stdout), sha256=self.w.digest(stdout.read_bytes()), sizeBytes=stdout.stat().st_size)
            cache.write_text(json.dumps(damaged))
            with self.assertRaisesRegex(ValueError, 'EARLY_REPRESENTATIVE_NOT_INCLUDED'):
                self.w.measure_committed_evidence(root, base, head, task)
            cache.unlink()
            old_key = self.w.digest(self.w.canonical([base, head, paths, self.w.digest((root/'scripts/create-review-package.ps1').read_bytes())]))
            old = directory/(old_key+'.json'); old.write_text('{"status":"PASS","legacyProtocol":true}')
            with patch.object(workflow_execution, 'run', wraps=workflow_execution.run) as execute:
                refreshed = self.w.measure_committed_evidence(root, base, head, task); execute.assert_called_once()
            self.assertEqual(refreshed['measurementProtocolVersion'], 1)
            self.assertEqual(old.read_text(), '{"status":"PASS","legacyProtocol":true}')

    def test_measurement_rejects_negative_growth_fields(self):
        from types import SimpleNamespace
        import workflow_execution
        with self.production_measurement() as (root, base, head, task, paths, result):
            for path in (root/'artifacts/workflow'/task/'package-measurements').glob('*.json'): path.unlink()
            original_git = self.w.git
            for change in ('double_negative', 'negative_metadata', 'negative_safety', 'missing_basis'):
                budget = dict(taskId=task, base=base, categories=[dict(remainingCount=1, reservedBytesEach=100, basis='observed maximum')], metadataReserveBytes=100, safetyReserveBytes=100)
                if change == 'double_negative': budget['categories'][0].update(remainingCount=-1, reservedBytesEach=-100)
                if change == 'negative_metadata': budget['metadataReserveBytes'] = -1
                if change == 'negative_safety': budget['safetyReserveBytes'] = -1
                if change == 'missing_basis': budget['categories'][0]['basis'] = ''
                def git(directory, *args):
                    if args[0] == 'ls-tree': return b'budget'
                    if args[0] == 'show': return json.dumps(budget).encode()
                    return original_git(directory, *args)
                measured = SimpleNamespace(returncode=0, stdout=json.dumps(result['measurement']).encode(), receipt=result['commandReceipt'])
                with self.subTest(change=change), patch.object(self.w, 'git', side_effect=git), patch.object(workflow_execution, 'run', return_value=measured):
                    with self.assertRaisesRegex(ValueError, 'MEASUREMENT_GROWTH_INVALID'):
                        self.w.measure_committed_evidence(root, base, head, task)

    def test_committed_plan_automatically_measures_new_report(self):
        w = self.w
        base, head = 'a'*40, 'b'*40
        report = 'docs/evidence/G4-M5-INTEGRATION-001/entry-fix-01/reports/first.json'
        def git(root, *args):
            if args[0] == 'rev-parse':
                return (base if args[-1].startswith(base) else head).encode()
            if args[0] == 'status':
                return b''
            return (report+'\0').encode()
        with patch.object(w, 'git', side_effect=git), patch.object(w.subprocess, 'run'), patch.object(w, 'measure_committed_evidence', return_value={'status':'MEASURED_NOT_READY_FOR_ACCEPTANCE'}) as measure, patch.object(w, 'input_key', return_value='input'):
            result = w.plan(base, head)
            measure.assert_called_once_with(w.ROOT, base, head, 'G4-M5-INTEGRATION-001')
            self.assertEqual(result['earlyMeasurements'][0]['status'], 'MEASURED_NOT_READY_FOR_ACCEPTANCE')

if __name__ == '__main__': unittest.main()
