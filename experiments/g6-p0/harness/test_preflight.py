"""真实发现失败和输入清单篡改必须在长入口前拒绝。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import preflight


class PreflightTests(unittest.TestCase):
    def test_real_import_failure_rejected(self):
        with tempfile.TemporaryDirectory(prefix="g6-p0-preflight-") as directory:
            path=Path(directory)
            (path/"test_broken.py").write_text("import g6_p0_intentionally_missing_module\n")
            with self.assertRaisesRegex(ValueError,"TEST_IMPORT_FAILED"):
                preflight.discover_count(path)
        self.assertFalse(path.exists())

    def test_zero_discovery_rejected(self):
        with tempfile.TemporaryDirectory(prefix="g6-p0-preflight-") as directory:
            path=Path(directory)
            with self.assertRaisesRegex(ValueError,"ZERO_TESTS"):
                preflight.discover_count(path)
        self.assertFalse(path.exists())

    def test_failed_suite_even_if_errors_not_reported(self):
        loader=unittest.TestLoader()
        loader.discover=lambda *a,**k:unittest.TestSuite([unittest.loader._FailedTest("bad",ImportError())])
        with patch.object(preflight.unittest,"TestLoader",return_value=loader):
            with self.assertRaisesRegex(ValueError,"TEST_IMPORT_FAILED"):preflight.discover_count("unused")

    def test_manifest_removal_and_empty_rejected(self):
        for raw in [b'{"files":[]}',b'{}',b'']:
            with self.assertRaisesRegex(ValueError,"MANIFEST_HASH_MISMATCH"):preflight.validate_manifest(raw)
