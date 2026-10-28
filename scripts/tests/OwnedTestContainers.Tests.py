"""Exercise real acceptance entrypoints and ownership protocol without Docker mutation."""
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/acceptance'))


def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts/acceptance'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class EntrypointSafetyTests(unittest.TestCase):
    def test_failed_creation_name_collision_never_deletes_preexisting_container(self):
        for name in ('semantic-roundtrip','release-faults','query-plan','mcp-agent','test-governance'):
            with self.subTest(entry=name),tempfile.TemporaryDirectory() as directory:
                module=load(name);module.EVIDENCE=Path(directory)/'evidence'
                if name=='test-governance':module.ROOT=Path(directory)
                calls=[]
                def command(args,**kwargs):
                    calls.append(args)
                    return subprocess.CompletedProcess(args,125 if args[:2]==['docker','run'] else 0,
                                                       'Name is already in use' if args[:2]==['docker','run'] else '', '')
                with contextlib.redirect_stdout(io.StringIO()),patch.object(sys,'argv',[name]),patch('subprocess.run',side_effect=command):
                    try:result=module.main()
                    except RuntimeError:result=1
                self.assertEqual(result,1)
                self.assertFalse(any(args[:2]==['docker','rm'] or args[:3]==['docker','container','rm'] for args in calls),
                                 'Creation failure must never authorize deletion by expected name')

    def test_all_entrypoints_propagate_cleanup_failure_after_successful_product_commands(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return b'{"results":{"bindings":[{"count":{"value":"0"}}]}}'
        class Opener:
            def open(self,*args,**kwargs):return Response()
        for name in ('semantic-roundtrip','release-faults','query-plan','mcp-agent','test-governance'):
            for cleanup_fails in (False,True):
                with self.subTest(entry=name,cleanupFails=cleanup_fails),tempfile.TemporaryDirectory() as directory:
                    module=load(name);module.EVIDENCE=Path(directory)/'evidence'
                    if name=='test-governance':module.ROOT=Path(directory)
                    live={};next_id=0
                    def command(args,**kwargs):
                        nonlocal next_id
                        if args[:2]==['docker','run']:
                            next_id+=1;ident=f'{next_id:064x}';container_name=args[args.index('--name')+1]
                            labels=dict(part.split('=',1) for at,part in enumerate(args) if at and args[at-1]=='--label')
                            live[ident]={'Id':ident,'Name':'/'+container_name,
                                'Project':labels['io.ontology-platform.project'],
                                'TaskId':labels['io.ontology-platform.task-id'],
                                'RunId':labels['io.ontology-platform.run-id'],'Fixture':'true'}
                            return subprocess.CompletedProcess(args,0,ident+'\n','')
                        if args[:3]==['docker','container','inspect']:
                            if cleanup_fails:return subprocess.CompletedProcess(args,1,'','permission denied')
                            ident=args[-1]
                            if ident in live:return subprocess.CompletedProcess(args,0,json.dumps(live[ident]),'')
                            return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such container: '+ident)
                        if args[:3]==['docker','container','rm']:
                            live.pop(args[-1],None)
                            return subprocess.CompletedProcess(args,0,args[-1]+'\n','')
                        if args[:2]==['docker','port']:return subprocess.CompletedProcess(args,0,'127.0.0.1:1234\n','')
                        return subprocess.CompletedProcess(args,0,'','')
                    with contextlib.redirect_stdout(io.StringIO()),patch.object(sys,'argv',[name]),patch('subprocess.run',side_effect=command), \
                         patch('subprocess.check_output',return_value='127.0.0.1:1234\n'), \
                         patch('urllib.request.build_opener',return_value=Opener()):
                        result=module.main()
                    self.assertEqual(result,1 if cleanup_fails else 0)
                    self.assertEqual(bool(live),cleanup_fails)
                    evidence=Path(directory)/'artifacts/governance-integration.json' if name=='test-governance' else next(module.EVIDENCE.glob('*.json'))
                    receipt=json.loads(evidence.read_text())
                    observed_exit=receipt[-1]['exitCode'] if isinstance(receipt,list) else receipt['exitCode']
                    self.assertEqual(observed_exit,result)


class OwnershipProtocolTests(unittest.TestCase):
    def setUp(self):
        self.module=load('owned_test_containers')
        self.records=[];self.commands=[];self.ids=['a'*64,'b'*64];self.live={}
        self.owner=self.module.OwnedTestContainers('G3-M3-001','fixture-123',self.records,self.fake_run)

    def fake_run(self,args,**kwargs):
        self.commands.append(args)
        ident=args[-1]
        if args[:3]==['docker','container','inspect']:
            if ident in self.live:return subprocess.CompletedProcess(args,0,json.dumps(self.live[ident]),'')
            return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such container: '+ident+'\n')
        if args[:3]==['docker','container','rm']:
            self.live.pop(ident,None)
            return subprocess.CompletedProcess(args,0,ident+'\n','')
        raise AssertionError('Unexpected process invocation')

    def create(self,index=0):
        ident=self.ids[index];name='fixture-'+str(index)
        args=self.owner.prepare(['docker','run','--detach','--name',name,'approved:tag'])
        self.live[ident]={'Id':ident,'Name':'/'+name,'Project':'on-dotnet/ontology-platform',
                          'TaskId':'G3-M3-001','RunId':'fixture-123','Fixture':'true'}
        self.owner.observe(args,subprocess.CompletedProcess(args,0,ident+'\n',''))
        return ident,args

    def test_created_id_is_removed_only_after_exact_labels_and_absence_is_verified(self):
        ident,args=self.create()
        self.assertIn('io.ontology-platform.task-id=G3-M3-001',args)
        self.assertIn('io.ontology-platform.run-id=fixture-123',args)
        self.assertTrue(self.owner.cleanup())
        self.assertFalse(self.live)
        self.assertEqual([r['phase'] for r in self.records],['create','before','command','exit','after'])
        self.assertEqual(self.records[-1]['absenceDiagnostic'],'Error response from daemon: No such container: '+ident)
        self.assertTrue(self.records[-1]['absent'])

    def test_failed_run_never_registers_or_deletes_a_returned_id(self):
        args=self.owner.prepare(['docker','run','--detach','--name','collision','approved:tag'])
        self.owner.observe(args,subprocess.CompletedProcess(args,125,'a'*64+'\n','collision'))
        self.assertFalse(self.owner.cleanup())
        self.assertEqual(self.commands,[])

    def test_foreign_labels_are_retained_and_other_owned_container_still_cleans(self):
        first,_=self.create();second,_=self.create(1)
        self.live[first]['TaskId']='OTHER'
        self.assertFalse(self.owner.cleanup())
        self.assertEqual(set(self.live),{first})
        self.assertFalse(any(c[:3]==['docker','container','rm'] and c[-1]==first for c in self.commands))
        self.assertTrue(any(r.get('containerId')==second and r.get('absent') for r in self.records))

    def test_inspect_permission_error_is_not_absence_and_does_not_remove(self):
        self.create()
        def denied(args,**kwargs):return subprocess.CompletedProcess(args,1,'','permission denied')
        self.owner.runner=denied
        self.assertFalse(self.owner.cleanup())
        self.assertTrue(self.live)
        self.assertFalse(any(r.get('absent') for r in self.records))

    def test_wrong_no_such_id_is_not_accepted(self):
        self.create()
        def wrong(args,**kwargs):return subprocess.CompletedProcess(args,1,'','Error response from daemon: No such container: '+'c'*64)
        self.owner.runner=wrong
        self.assertFalse(self.owner.cleanup())
        self.assertTrue(self.live)

    def test_malformed_success_id_does_not_authorize_name_cleanup(self):
        args=self.owner.prepare(['docker','run','--detach','--name','fixture','approved:tag'])
        with self.assertRaises(RuntimeError):self.owner.observe(args,subprocess.CompletedProcess(args,0,'not-an-id',''))
        self.assertFalse(self.owner.cleanup());self.assertEqual(self.commands,[])

    def test_cleanup_cli_exception_blocks_and_does_not_stop_other_safe_items(self):
        first,_=self.create();second,_=self.create(1);real=self.fake_run
        def interrupted(args,**kwargs):
            if args[-1]==first:raise subprocess.TimeoutExpired(args,20)
            return real(args,**kwargs)
        self.owner.runner=interrupted
        self.assertFalse(self.owner.cleanup())
        self.assertEqual(set(self.live),{first})
        self.assertTrue(any(r.get('containerId')==second and r.get('absent') for r in self.records))

    def test_rm_zero_with_remaining_container_is_failure(self):
        self.create();real=self.fake_run
        def no_effect(args,**kwargs):
            if args[:3]==['docker','container','rm']:return subprocess.CompletedProcess(args,0,'','')
            return real(args,**kwargs)
        self.owner.runner=no_effect
        self.assertFalse(self.owner.cleanup());self.assertTrue(self.live)

    def test_rm_failure_even_if_absent_does_not_become_pass(self):
        self.create();real=self.fake_run
        def nonzero(args,**kwargs):
            if args[:3]==['docker','container','rm']:
                self.live.clear();return subprocess.CompletedProcess(args,1,'','failure')
            return real(args,**kwargs)
        self.owner.runner=nonzero
        self.assertFalse(self.owner.cleanup())

    def test_preexisting_owner_label_and_invalid_identity_are_refused(self):
        with self.assertRaises(ValueError):self.module.OwnedTestContainers('OTHER\nunsafe','run',[])
        with self.assertRaises(ValueError):self.owner.prepare(['docker','run','--name','fixture','--label','io.ontology-platform.task-id=OTHER','image'])


if __name__=='__main__':unittest.main()
