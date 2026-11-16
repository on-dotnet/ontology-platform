#!/usr/bin/env python3
"""M5消费者身份与前提失效反例；非真实DB验收。"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
class IntegrationTests(unittest.TestCase):
    def test_m5_does_not_change_m4_identity(self):
        import workflow_m4_query as old
        import workflow_m5_integration as new
        self.assertEqual(old.TASK,'G4-M4-QUERY-001')
        self.assertEqual(new.TASK,'G4-M5-INTEGRATION-001')
        self.assertNotEqual(old.PROFILE.project,new.PROFILE.project)
        self.assertNotEqual(old.PROFILE.private,new.PROFILE.private)
        self.assertFalse(set(old.PROFILE.ports.values())&set(new.PROFILE.ports.values()))
    def test_scenarios_have_separate_state_and_unknown_refuses(self):
        import workflow_m5_integration as new
        new.scenario('numeric');a=new.fixture_file()
        new.scenario('standard');b=new.fixture_file()
        self.assertNotEqual(a,b)
        with self.assertRaises(ValueError):new.scenario('../escape')
    def test_readiness_rejects_each_stale_fact(self):
        from workflow_m5_integration import demand_ready
        good={'api':True,'web':True,'build':True,'session':True,'connection':True,'grant':True,'activation':True,'fixture':True,'owner':True,'budget':True}
        self.assertEqual(demand_ready(good),'SCENARIO_READY')
        for key in good:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'PREREQUISITE_STALE:'+key):demand_ready({**good,key:False})
        with self.assertRaises(ValueError):demand_ready({})
if __name__=='__main__':unittest.main()
