"""容器前路径/参数/登记/阶段漂移和同输入昂贵失败正反回归。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/maintenance/execution_preflight.py'
spec=importlib.util.spec_from_file_location('execution_preflight',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='m5-preflight-',dir=Path(tempfile.gettempdir()).resolve())
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def put(self,path,text):
        target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8');return target

    def fixture(self):
        self.put(m.AUDIT,'private static readonly HashSet<string> Actions = new(StringComparer.Ordinal) { "ontology.impact.generate" };')
        self.put(m.MODULE,'services.AddScoped<IG3ImpactService>();\nservices.AddScoped<IG3ExpressionService>();\nservices.AddSingleton<IG3ExpressionRuntime>();\n')
        self.put(m.LAUNCHERS[0],"[ValidateSet('M1','M2','M3','M4','M5')][string]$Milestone")
        self.put(m.LAUNCHERS[1],"parser.add_argument('--milestone',choices=['M1','M2','M3','M4','M5'])\n")
        self.put(m.LAUNCHERS[2],"parser.add_argument('--milestone',choices=['M1','M2','M3','M4','M5'])\nif args.milestone in ('M3','M4','M5'):\n    command.append('--m5')\n")

    def test_paths_existing_missing_case_traversal_and_symlink(self):
        self.put('backend/Actual.csproj','fixture\n')
        self.assertEqual(m.check_paths(self.root,['backend/Actual.csproj']),['backend/Actual.csproj'])
        for path in ['backend/actual.csproj','backend/Missing.csproj','../outside','backend\\Actual.csproj','/backend','C:/x']:
            with self.assertRaises(ValueError,msg=path):m.check_paths(self.root,[path])
        (self.root/'link').symlink_to(self.root/'backend',target_is_directory=True)
        with self.assertRaises(ValueError):m.check_paths(self.root,['link/Actual.csproj'])

    def test_actual_help_accepts_only_real_supported_options(self):
        target=self.put('cli.py',"import argparse\np=argparse.ArgumentParser();p.add_argument('--real');p.parse_args()\n")
        self.assertTrue(m.check_cli([sys.executable,str(target)],['--real']))
        with self.assertRaisesRegex(ValueError,'CLI_OPTION_MISSING'):m.check_cli([sys.executable,str(target)],['--hallucinated'])
        with self.assertRaisesRegex(ValueError,'CLI_MISSING'):m.check_cli(['MISSING_INTERPRETER_FIXTURE'],[])
        with mock.patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('withheld',10)):
            with self.assertRaisesRegex(ValueError,'CLI_UNAVAILABLE'):m.check_cli([sys.executable],[])

    def test_frozen_consumers_pass_and_missing_action_fails_before_request(self):
        self.fixture();self.assertEqual(m.check_consumers(self.root)['status'],'PASS')
        self.put(m.AUDIT,'private static readonly HashSet<string> Actions = new(StringComparer.Ordinal) { "ontology.save" }; // "ontology.impact.generate"')
        with self.assertRaisesRegex(ValueError,'AUDIT_ACTION_MISSING'):m.check_consumers(self.root)

    def test_missing_or_comment_only_di_is_rejected(self):
        self.fixture();path=self.root/m.MODULE
        path.write_text(path.read_text().replace('services.AddSingleton<IG3ExpressionRuntime>();','// services.AddSingleton<IG3ExpressionRuntime>();'))
        with self.assertRaisesRegex(ValueError,'DI_REGISTRATION_MISSING'):m.check_consumers(self.root)

    def test_phase_choices_only_fix_still_rejects_old_checkpoint_and_performance(self):
        self.fixture();path=self.root/m.LAUNCHERS[2]
        original=path.read_text()
        for old_guard in ["if args.milestone not in ('M2','M3','M4'): pass", "if args.milestone in ('M3','M4'): pass", "if args.milestone != 'M4': pass"]:
            path.write_text(original+'\n'+old_guard+'\n')
            with self.assertRaisesRegex(ValueError,'MILESTONE_GUARD_DRIFT'):m.check_consumers(self.root)
        path.write_text(original.replace("'--m5'","'--m4'"))
        with self.assertRaisesRegex(ValueError,'MILESTONE_DISPATCH_MISSING'):m.check_consumers(self.root)

    def test_python_and_powershell_choices_must_both_register_phase(self):
        self.fixture()
        for path in m.LAUNCHERS:
            original=(self.root/path).read_text()
            (self.root/path).write_text(original.replace(",'M5'",''))
            with self.assertRaisesRegex(ValueError,'MILESTONE_GUARD_DRIFT'):m.check_consumers(self.root)
            (self.root/path).write_text(original)

    def guard(self,hash='a'*64,version='b'*64):
        return m.FailureState(self.root/'state.json',hash,'semantic-tests',version)

    def test_identical_failure_requires_short_repro_then_blocks_expensive(self):
        with self.guard() as state:state.allow('expensive');state.record('expensive',17)
        with self.guard() as state:
            with self.assertRaisesRegex(ValueError,'SHORT_REPRO_REQUIRED'):state.allow('expensive')
            state.allow('short');state.record('short',17)
        with self.guard() as state:
            with self.assertRaisesRegex(ValueError,'UNCHANGED_FAILURE_BLOCKED'):state.allow('expensive')
        for changed in [self.guard(hash='c'*64),self.guard(version='d'*64)]:
            with changed as state:state.allow('expensive')
        with self.guard() as state:state.allow('short');state.record('short',0)
        with self.guard() as state:state.allow('expensive')

    def test_state_lock_symlink_corruption_and_preexisting_partial_are_retained(self):
        with self.guard() as state:
            with self.assertRaisesRegex(ValueError,'FAILURE_STATE_BUSY'):
                with self.guard():pass
        target=self.root/'state.json';target.write_text('{broken')
        with self.assertRaises(ValueError):
            with self.guard():pass
        self.assertFalse((self.root/'state.json.lock').exists())
        target.unlink();partial=self.root/'state.json.partial';partial.write_text('retained')
        with self.guard() as state:
            with self.assertRaises(FileExistsError):state.record('short',17)
        self.assertEqual(partial.read_text(),'retained')
        partial.unlink();target.symlink_to(self.put('outside','retained'))
        with self.assertRaisesRegex(ValueError,'FAILURE_STATE_LINKED'):self.guard()

    def test_real_guarded_failure_never_reexecutes_unchanged_expensive_input(self):
        state=self.root/'artifacts/state.json';marker=self.root/'runs.txt'
        invocation=[sys.executable,str(SCRIPT),'run','--state',str(state),'--input-hash','a'*64,
                    '--test-build-id','semantic-tests','--test-build-version','b'*64,'--cost','expensive',
                    '--',sys.executable,'-c',
                    'from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_text(p.read_text()+"x" if p.exists() else "x"); sys.exit(23)',
                    str(marker),'SYNTHETIC_PRIVATE_ARGUMENT_NOT_RECORDED']
        for expected in [23,2]:
            result=subprocess.run(invocation,cwd=self.root,capture_output=True,text=True)
            self.assertEqual(result.returncode,expected,result.stderr)
        self.assertEqual(marker.read_text(),'x')
        self.assertNotIn('SYNTHETIC_PRIVATE_ARGUMENT_NOT_RECORDED',state.read_text())
        short=list(invocation);short[short.index('expensive')]='short'
        self.assertEqual(subprocess.run(short,cwd=self.root,capture_output=True).returncode,23)
        self.assertEqual(subprocess.run(invocation,cwd=self.root,capture_output=True).returncode,2)
        self.assertEqual(marker.read_text(),'xx')
        changed=list(invocation);changed[changed.index('a'*64)]='c'*64
        self.assertEqual(subprocess.run(changed,cwd=self.root,capture_output=True).returncode,23)
        self.assertEqual(marker.read_text(),'xxx')

    def test_platform_participates_in_fingerprint_without_pmset(self):
        hashes=[]
        for system in ('Windows','Linux','Darwin'):
            with mock.patch.object(m.platform,'system',return_value=system),mock.patch.object(m.subprocess,'run',side_effect=AssertionError('No OS process expected')):
                hashes.append(self.guard().fingerprint)
        self.assertEqual(len(set(hashes)),3)


class ProductInputTests(unittest.TestCase):
    def test_document_change_reuses_input_but_product_change_invalidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
            (root/'.gitignore').write_text('artifacts/\n')
            (root/'source.py').write_text('product-v1\n')
            (root/'docs/tasks').mkdir(parents=True)
            note=root/'docs/tasks/note.md';note.write_text('one\n')
            original=m.product_input_fingerprint(root)
            note.write_text('two\n')
            self.assertEqual(original,m.product_input_fingerprint(root))
            (root/'source.py').write_text('product-v2\n')
            self.assertNotEqual(original,m.product_input_fingerprint(root))

if __name__=='__main__':unittest.main()
