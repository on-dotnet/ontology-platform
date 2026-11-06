#!/usr/bin/env python3
"""短烟测身份与拓扑拒绝回归，不以模拟结果冒充产品验收。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import subprocess
import socket
import threading
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('workflow_smoke',ROOT/'scripts/maintenance/workflow_smoke.py')

class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(cls.smoke)

    def topology(self):
        engine={'id':'engine','version':'1','context':'desktop-linux'}
        ids={name:str(i+1)*64 for i,name in enumerate(self.smoke.SERVICES)}
        runtime={'taskId':self.smoke.TASK,'runId':'wf-0123456789ab','engine':engine,'containerIds':ids,'imageIds':{name:'sha256:'+ident for name,ident in ids.items()}}
        rows={name:{'Id':ident,'Config':{'Labels':{'ontology.task-id':self.smoke.TASK,'ontology.run-id':runtime['runId'],'com.docker.compose.service':name},'Image':self.smoke.IMAGES[name]},'Image':runtime['imageIds'][name],'State':{'Running':True,'Paused':False},'HostConfig':{'Memory':768*1024**2,'NetworkMode':'container:'+ids['api'] if name=='web' else 'front'}} for name,ident in ids.items()}
        return runtime,rows,engine

    def test_loaded_approved_image_identity_without_repo_alias(self):
        ref=self.smoke.IMAGES['pg-source']
        self.smoke.validate_image({'Architecture':'arm64','Os':'linux','Id':ref.split('@')[1],'RepoDigests':[]},ref)
        with self.assertRaises(ValueError):
            self.smoke.validate_image({'Architecture':'arm64','Os':'linux','Id':'sha256:'+'0'*64},ref)

    def test_valid_current_topology(self):
        self.assertTrue(self.smoke.validate_topology(*self.topology()))

    def test_old_runtime_refused(self):
        runtime,rows,engine=self.topology();runtime['taskId']='G4-M1-MAIN-INTEGRATION-001'
        with self.assertRaisesRegex(ValueError,'RUNTIME_IDENTITY'):
            self.smoke.validate_topology(runtime,rows,engine)

    def test_recreated_api_refused_before_browser(self):
        runtime,rows,engine=self.topology();rows['api']['Id']='f'*64
        with self.assertRaisesRegex(ValueError,'CONTAINER_REPLACED'):
            self.smoke.validate_topology(runtime,rows,engine)

    def test_old_web_namespace_refused(self):
        runtime,rows,engine=self.topology();rows['web']['HostConfig']['NetworkMode']='container:'+'f'*64
        with self.assertRaisesRegex(ValueError,'STALE_WEB_NETWORK'):
            self.smoke.validate_topology(runtime,rows,engine)

    def test_owner_and_engine_drift_refused(self):
        runtime,rows,engine=self.topology();rows['pg-source']['Config']['Labels']['ontology.run-id']='wf-ffffffffffff'
        with self.assertRaisesRegex(ValueError,'RESOURCE_OWNER'):
            self.smoke.validate_topology(runtime,rows,engine)
        runtime,rows,engine=self.topology()
        with self.assertRaisesRegex(ValueError,'ENGINE_DRIFT'):
            self.smoke.validate_topology(runtime,rows,dict(engine,id='other'))

    def test_fixture_path_cannot_be_old_tree_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'private').mkdir();(root/'link').symlink_to(root/'private')
            with self.assertRaisesRegex(ValueError,'PATH_OUTSIDE_TASK'):
                self.smoke.boundary(root.parent/'old-runtime.json',root)
            with self.assertRaisesRegex(ValueError,'LINKED_PATH'):
                self.smoke.boundary(root/'link/runtime.json',root)

    def test_browser_timeout_has_real_exit_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            raw,code=self.smoke.bounded_browser([sys.executable,'-c','import time; time.sleep(10)'],Path(directory),timeout=.1)
            self.assertEqual(code,124)
            raw,code=self.smoke.bounded_browser([sys.executable,'-c','print("safe"); raise SystemExit(7)'],Path(directory),timeout=3)
            self.assertEqual(code,7)
            self.assertEqual(raw.strip(),b'safe')

    def test_stop_failure_does_not_skip_other_owned_instances(self):
        runtime,rows,identity=self.topology();calls=[]
        def fake_docker(root,*args,**kwargs):
            if args[0]=='inspect':
                row=next(v for v in rows.values() if v['Id']==args[1]);return json.dumps([row]).encode()
            if args[0]=='stop':
                calls.append(args[-1])
                if args[-1]==runtime['containerIds']['pg-source']:raise ValueError('STOP_FAILED')
                next(v for v in rows.values() if v['Id']==args[-1])['State']['Running']=False
                return b''
            self.fail('unexpected external action')
        with patch.object(self.smoke,'engine',return_value=identity),patch.object(self.smoke,'docker',side_effect=fake_docker):
            result=self.smoke.stop_owned(ROOT,runtime)
        self.assertEqual(set(calls),set(runtime['containerIds'].values()))
        self.assertEqual(len(result['stopped']),4)
        self.assertEqual(len(result['failures']),1)

    def test_build_binding_rejects_changed_source_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'backend/src').mkdir(parents=True);(root/'backend/src/a.cs').write_text('source')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            api=root/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0';api.mkdir(parents=True)
            web=root/'apps/web/.next';web.mkdir(parents=True)
            (api/'OntologyPlatform.Api.dll').write_bytes(b'assembly');(web/'required-server-files.json').write_text('{}')
            receipt=root/'artifacts/workflow/G4-ENG-WORKFLOW-001/build-receipt.json';receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({'status':'PASS','worktree':str(root),'inputKey':self.smoke.build_input_key(root),'outputs':self.smoke.build_outputs(root)}))
            self.smoke.validate_build(root)
            (api/'OntologyPlatform.Api.dll').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BUILD_OUTPUT_DRIFT'):self.smoke.validate_build(root)
            (api/'OntologyPlatform.Api.dll').write_bytes(b'assembly');(root/'backend/src/a.cs').write_text('changed source')
            with self.assertRaisesRegex(ValueError,'BUILD_INPUT_DRIFT'):self.smoke.validate_build(root)

    def test_planned_resources_exist_before_external_creation(self):
        runtime,_,_=self.topology()
        with tempfile.TemporaryDirectory() as directory:
            private=Path(directory);(private/'compose.json').write_text('{}')
            config={'volumes':{'data':{'name':'ontology-workflow-wf-0123456789ab_data'}},'networks':{'front':{'name':'ontology-workflow-wf-0123456789ab_front'}}}
            with patch.object(self.smoke,'docker',side_effect=AssertionError('no external creation or inspection')):
                manifest=self.smoke.resource_manifest(ROOT,runtime,config,private,'PLANNED')
            self.assertEqual(manifest['volumes']['data']['expectedName'],config['volumes']['data']['name'])
            self.assertEqual(manifest['networks']['front']['observation'],'NOT_VERIFIED')
            self.assertEqual(manifest['engine'],runtime['engine'])

    def test_relay_only_accepts_fixed_current_task_targets(self):
        runtime,_,_=self.topology()
        token='wf-relay-'+runtime['runId']+'-'+'a'*32
        command=self.smoke.relay_command(runtime,15180,token)
        self.assertEqual(command[:5],['docker','--context','desktop-linux','exec','-i'])
        self.assertEqual(command[5],runtime['containerIds']['web'])
        with self.assertRaisesRegex(ValueError,'RELAY_TARGET'):
            self.smoke.relay_command(runtime,80,token)
        runtime['taskId']='OTHER'
        with self.assertRaisesRegex(ValueError,'RELAY_IDENTITY'):
            self.smoke.relay_command(runtime,15180,token)

    def test_relay_real_duplex_stream_releases_own_process(self):
        runtime,_,_=self.topology();relay=self.smoke.HostRelay(ROOT,runtime)
        actual_popen=subprocess.Popen;children=[]
        script="import os,sys; print('PID '+str(os.getpid()),file=sys.stderr,flush=True);\nwhile True:\n data=os.read(0,65536)\n if not data:break\n os.write(1,data)"
        def local_transport(args,**kwargs):
            child=actual_popen([sys.executable,'-c',script],**kwargs);children.append(child);return child
        left,right=socket.socketpair()
        with patch.object(self.smoke.subprocess,'Popen',side_effect=local_transport),patch.object(self.smoke,'docker',return_value=b''):
            thread=threading.Thread(target=relay.forward,args=(right,15100));thread.start()
            left.settimeout(5);left.sendall(b'opaque test request');self.assertEqual(left.recv(64),b'opaque test request')
            left.close();thread.join(timeout=5)
        self.assertFalse(thread.is_alive());self.assertFalse(relay.active)
        self.assertTrue(all(child.poll() is not None for child in children))

    def test_entry_exists(self):
        self.assertTrue(Path(SPEC.origin).is_file(),'short smoke adapter missing')

if __name__=='__main__': unittest.main()
