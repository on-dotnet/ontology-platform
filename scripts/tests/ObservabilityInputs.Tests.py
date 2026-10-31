"""真实观测入口的文件/Schema短门禁；不启动LGTM或代替产品遥测验收。"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/acceptance'))
spec=importlib.util.spec_from_file_location('observability',ROOT/'scripts/acceptance/g2-observability.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ObservationInputs(unittest.TestCase):
    def test_actual_entry_accepts_valid_trace_identity_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            value={'traces':[str(index)*32 for index in range(1,6)]}
            (root/'full-chain-identifiers.json').write_text(json.dumps(value))
            self.assertEqual(m.read_chain_identifiers(root),value)

    def test_missing_and_invalid_and_oversized_inputs_fail_before_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();path=root/'full-chain-identifiers.json'
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHAIN_IDS_MISSING'):m.read_chain_identifiers(root)
            for value in [{'traces':[]},{'traces':['0'*32]*5},{'traces':['wrong']*5},[]]:
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError,'EVIDENCE_CHAIN_IDS_INVALID'):m.read_chain_identifiers(root)
            path.write_text('x'*65537)
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHAIN_IDS_MISSING'):m.read_chain_identifiers(root)

    def test_linked_trace_file_is_refused_without_reading_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();other=root/'original';other.write_text('not-read')
            (root/'full-chain-identifiers.json').symlink_to(other)
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHAIN_IDS_MISSING'):m.read_chain_identifiers(root)
            self.assertEqual(other.read_text(),'not-read')

    def test_persisted_search_uses_actual_span_window_and_keeps_limit(self):
        payload={'resourceSpans':[{'spans':[{'spanId':'known','startTimeUnixNano':'1700000000000000000','endTimeUnixNano':'1700000001000000000'}]}]}
        value=m.worker_search_parameters(payload,'a'*32)
        self.assertEqual((value['start'],value['end']),(1699999940,1700000301))
        self.assertEqual(value['limit'],'20')
        self.assertEqual(m.VISIBILITY_BUDGET_SECONDS,90)

    def test_invalid_or_unbounded_span_windows_fail_closed(self):
        for payload in [{},{'spanId':'x','startTimeUnixNano':'bad','endTimeUnixNano':'1'},
                        {'spanId':'x','startTimeUnixNano':'1700000000000000000','endTimeUnixNano':'1699999999000000000'},
                        {'spanId':'x','startTimeUnixNano':'1700000000000000000','endTimeUnixNano':'1700003600000000000'}]:
            with self.assertRaisesRegex(ValueError,'TRACE_WINDOW_INVALID'):m.worker_search_parameters(payload,'a'*32)



if __name__=='__main__':unittest.main()
