#!/usr/bin/env python3
"""Guard cross-session entry points and closeout sequence against policy drift."""
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[2]
class CloseoutGovernance(unittest.TestCase):
    def test_new_master_can_discover_efficiency_contract(self):
        for path in ('AGENTS.md', 'PLANS.md', 'docs/tasks/current-authorization.md'):
            text=(ROOT/path).read_text()
            for target in ('ai-development-efficiency.md', 'review-package-spec.md', 'resource-lifecycle.md'):
                self.assertIn(target, text, path+' must link '+target)
    def test_efficiency_contract_covers_all_ten_controls(self):
        text=(ROOT/'docs/development/ai-development-efficiency.md').read_text()
        for control in ('Preflight-first','先合同后并行','分层测试','持续集成','证据分层','交付冻结顺序','真实效率数据','阶段资源收尾','防跨会话丢规则','不以速度换安全'):
            self.assertIn(control,text)
        for status in ('UNKNOWN','NOT_RUN','NOT_VERIFIED'):
            self.assertIn(status,text)
    def test_active_rules_do_not_default_to_v2(self):
        for path in ('AGENTS.md','PLANS.md','docs/development/resource-lifecycle.md'):
            text=(ROOT/path).read_text()
            self.assertNotRegex(text,r'默认采用\[V2|复检的V2包')
            self.assertIn('V3',text)
    def test_m1_semantic_evidence_has_single_terminal_newline(self):
        data=(ROOT/'docs/evidence/G3-M1-001/SEM/g3-sem-selftest.txt').read_bytes()
        self.assertTrue(data.endswith(b'\n'))
        self.assertFalse(data.endswith(b'\n\n'))
if __name__=='__main__': unittest.main()
