#!/usr/bin/env python3
"""M2离线缓存重绑定和消费者准入拒绝测试；不冒充产品测试。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class CacheTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('workflow_web_cache',ROOT/'scripts/maintenance/workflow_web_cache.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_rebound_shim_requires_exact_declared_target_and_node(self):
        m=self.load()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();target=root/'pkg/bin.js';target.parent.mkdir();target.write_text('#!/usr/bin/env node\n')
            shim=root/'modules/.bin/tool';shim.parent.mkdir(parents=True)
            shim.write_bytes(m.shim_bytes('/approved/node',target))
            self.assertEqual(m.shim_target(shim,root,'/approved/node',{('tool','pkg/bin.js')}),'pkg/bin.js')
            for payload in (b'#!/bin/sh\ncurl evil\n',m.shim_bytes('/other/node',target),m.shim_bytes('/approved/node',root/'outside.js')):
                shim.write_bytes(payload)
                with self.assertRaises(ValueError):m.shim_target(shim,root,'/approved/node',{('tool','pkg/bin.js')})

    def test_topology_rejects_unverified_files_and_internal_links(self):
        m=self.load()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();package=root/'node_modules/.pnpm/tool/node_modules/tool';package.mkdir(parents=True)
            file=package/'index.js';file.write_text('verified')
            known={str(file.relative_to(root))}
            m.topology(root,known,{},set())
            extra=root/'node_modules/rogue.js';extra.write_text('injected')
            with self.assertRaisesRegex(ValueError,'UNVERIFIED'):m.topology(root,known,{},set())
            extra.unlink();(root/'not-verified').write_text('injected')
            link=root/'node_modules/tool';link.symlink_to(root/'not-verified')
            with self.assertRaisesRegex(ValueError,'LINK'):m.topology(root,known,{},set())
            link.unlink();link.symlink_to(package)
            first=m.topology(root,known,{},set())
            link.unlink()
            self.assertNotEqual(first,m.topology(root,known,{},set()))

    def test_lock_edges_reject_wrong_approved_package_and_peer_version(self):
        m=self.load()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            lock={'importers':{'apps/web':{'dependencies':{'next':{'version':'1.0.0'}}}},'snapshots':{'next@1.0.0':{},'other@2.0.0':{}}}
            target='node_modules/.pnpm/next@1.0.0/node_modules/next'
            wrong='node_modules/.pnpm/other@2.0.0/node_modules/other'
            installed={target,wrong};layout={'hoistedDependencies':{},'virtualStoreDirMaxLength':120}
            edges=m.dependency_edges(lock,layout,installed)
            self.assertEqual(edges['apps/web/node_modules/next'],target)
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_EDGE'):
                m.check_edges(edges,{'apps/web/node_modules/next':wrong})
            m.check_edges(edges,{'apps/web/node_modules/next':target})

    def test_workspace_state_must_match_source_and_be_complete(self):
        m=self.load()
        import json
        with tempfile.TemporaryDirectory() as d:
            r=Path(d).resolve();(r/'apps/web').mkdir(parents=True);(r/'node_modules').mkdir()
            (r/'package.json').write_text('{"name":"root"}');(r/'apps/web/package.json').write_text('{"name":"web"}')
            state={'projects':{str(r):{'name':'root'},str(r/'apps/web'):{'name':'web'}},'pnpmfiles':[],'filteredInstall':False}
            path=r/'node_modules/.pnpm-workspace-state-v1.json';path.write_text(json.dumps(state));m.workspace(r)
            state['filteredInstall']=True;path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'WORKSPACE'):m.workspace(r)
            state['filteredInstall']=False
            state['projects']['/old']={'name':'extra'};path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'WORKSPACE'):m.workspace(r)

class AdmissionTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('m2',ROOT/'scripts/maintenance/workflow_m2_web.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_real_consumers_are_structural_only(self):
        result=self.load().structural(ROOT,'G4-M2-WEB-01')
        self.assertEqual(result['status'],'STRUCTURAL_READY')
        self.assertEqual(result['productSmoke'],'NOT_RUN')

    def test_wrong_task_and_missing_consumer_are_rejected(self):
        m=self.load()
        with self.assertRaisesRegex(ValueError,'TASK_ID'):m.structural(ROOT,'G3-M2-001')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'CONSUMER_MISSING'):m.structural(Path(d).resolve(),'G4-M2-WEB-01')

class CloseoutTests(unittest.TestCase):
    def test_driver_only_change_activates_product_qualification(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow
        for path in ('scripts/maintenance/workflow-m2-web.mjs','scripts/maintenance/workflow_m2_smoke.py','scripts/maintenance/workflow_m2_evidence.py'):
            plan=workflow.select_gates([path])
            self.assertEqual(plan['status'],'PLANNED')
            self.assertTrue({'environment','contract','backend','web','interaction'}<=set(plan['affected']))

    def test_cleanup_exception_cannot_leave_pass_and_missing_object_fails(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_build as build
        state={'status':'PASS','cleanup':[]}
        build.begin_cleanup(state,['container-id','network-id'])
        self.assertEqual(state['status'],'NOT_VERIFIED')
        state['cleanup'].append({'id':'container-id','afterAbsent':True})
        build.finish_cleanup(state)
        self.assertEqual(state['status'],'FAIL')
        state['cleanup'].append({'id':'network-id','afterAbsent':True})
        build.finish_cleanup(state)
        self.assertEqual(state['status'],'PASS')
        state['cleanup'][-1]['afterAbsent']=False
        build.finish_cleanup(state)
        self.assertEqual(state['status'],'FAIL')

    def test_failed_or_unbound_original_cannot_be_promoted(self):
        import json,sys
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_evidence as evidence
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/'docs/evidence/G4-M2-WEB-01/recovery/receipt.json';path.parent.mkdir(parents=True)
            row={'taskId':'G4-M2-WEB-01','status':'FAIL','testStatus':'PASS','cleanupComplete':True,'cleanup':[],'cleanupExpected':[],'driverInputs':{}}
            with patch.object(evidence.build,'ROOT',root),patch.object(evidence.build,'driver_inputs',return_value={}):
                path.write_text(json.dumps(row))
                with self.assertRaisesRegex(ValueError,'RUN_NOT_PASS'):evidence.original('https',path,{'connections':{}})
                row['status']='PASS';row['buildBinding']={'stale':'output'};path.write_text(json.dumps(row))
                with self.assertRaisesRegex(ValueError,'HTTPS_BUILD_DRIFT'):evidence.original('https',path,{'connections':{}})
                row['driverInputs']={'old':'driver'};path.write_text(json.dumps(row))
                with self.assertRaisesRegex(ValueError,'ORIGINAL_DRIVER_DRIFT'):evidence.original('https',path,{'connections':{}})

    def test_zero_or_skipped_original_mtp_is_not_success(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_evidence as evidence
        for raw in (b'total: 0 failed: 0 succeeded: 0 skipped: 0',b'total: 2 failed: 0 succeeded: 1 skipped: 1',b'total: 2 failed: 1 succeeded: 1 skipped: 0'):
            with self.assertRaises(ValueError):evidence.mtp(raw,1)
        self.assertEqual(evidence.mtp(b'total: 2 failed: 0 succeeded: 2 skipped: 0',1),2)

    def test_archived_text_requires_original_hash_and_unambiguous_path(self):
        import sys
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_evidence as evidence
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/'docs/evidence/G4-M2-WEB-01/pg-test.log';path.parent.mkdir(parents=True)
            raw=b'total: 1 failed: 0 succeeded: 1 skipped: 0\n';digest=evidence.build.sha(raw)
            with patch.object(evidence.build,'ROOT',root):
                archived=path.with_suffix('.txt');archived.write_bytes(raw)
                self.assertEqual(evidence.read_log(path,digest),raw)
                archived.write_bytes(raw+b'tampered')
                with self.assertRaisesRegex(ValueError,'PROOF_SHA'):evidence.read_log(path,digest)
                archived.write_bytes(raw);path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):evidence.read_log(path,digest)
                archived.unlink();self.assertEqual(evidence.read_log(path,digest),raw)

    def test_only_qualification_parser_excluded_from_execution_driver_identity(self):
        import sys
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_evidence as evidence
        current=evidence.build.driver_inputs();parser='scripts/maintenance/workflow_m2_evidence.py'
        original={**current,parser:'historical-parser'}
        row={'status':'PASS','testStatus':'PASS','cleanupComplete':True,'cleanup':[],'cleanupExpected':[],'driverInputs':original}
        evidence.closed(row)
        for path in {p for p in current if evidence.build.driver_layers()[p]=='execution'}:
            for changed in ({**original,path:'different'}, {k:v for k,v in original.items() if k!=path}):
                with self.assertRaisesRegex(ValueError,'ORIGINAL_DRIVER_DRIFT'):evidence.closed({**row,'driverInputs':changed})
        with self.assertRaisesRegex(ValueError,'ORIGINAL_DRIVER_DRIFT'):evidence.closed({**row,'driverInputs':{**original,'unknown-driver':'x'}})

    def test_product_executor_rejects_wrong_task_or_gate(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/maintenance'))
        import workflow_m2_evidence as evidence
        for task,gate in [('G3-M2-001','backend'),('G4-M2-WEB-01','other')]:
            with self.assertRaisesRegex(ValueError,'PRODUCT_TASK_GATE'):evidence.verify(task,gate,'x')

if __name__=='__main__':unittest.main()
