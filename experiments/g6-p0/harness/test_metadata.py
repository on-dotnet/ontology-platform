"""声明图审计负例：缺失传递节点、extra和精确约束不能伪装安装闭包。"""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location("audit_metadata",Path(__file__).resolve().parents[1]/"supply-chain/audit_metadata.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class MetadataTests(unittest.TestCase):
    def test_missing_node_and_extra(self):
        d={"nodes":{"a":{"requiresDist":["b[x]==1.0"]}},"selectedExtras":{}}
        r=module.audit(d)
        self.assertEqual(r["missingNodes"],["b"])
        self.assertEqual(r["unpropagatedExtras"],["b[x]"])
        self.assertEqual(r["graphEnumeration"],"INCOMPLETE")

    def test_exact_pin_conflict(self):
        d={"nodes":{"a":{"requiresDist":["b==1.0"]},"b":{"version":"2.0"}},"selectedExtras":{}}
        r=module.audit(d)
        self.assertEqual(r["exactPinMismatches"][0]["required"],"1.0")
        self.assertTrue(r["installClosure"].startswith("BLOCKED"))

    def test_unselected_extra_not_required(self):
        d={"nodes":{"a":{"requiresDist":["b; extra == 'unused'"]}},"selectedExtras":{}}
        r=module.audit(d)
        self.assertEqual(r["selectedDeclarationEdges"],0)
        self.assertEqual(r["graphEnumeration"],"PASS")
