#!/usr/bin/env python3
"""短烟测身份与拓扑拒绝回归，不以模拟结果冒充产品验收。"""
import importlib.util
import json
from pathlib import Path
import tempfile
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

    def test_entry_exists(self):
        self.assertTrue(Path(SPEC.origin).is_file(),'short smoke adapter missing')

if __name__=='__main__': unittest.main()
