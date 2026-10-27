"""A retained reader identity must include its real parser dependency and exact member set."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'acceptance/g3-compatibility.py'


class ReaderIdentityTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('compatibility_identity', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]):
            spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'snapshot_binary_set'), 'Reader identity does not yet freeze actual dependency binaries')
        return module

    def fixture(self, root):
        (root / 'OntologyPlatform.G2ContractTests.dll').write_bytes(b'synthetic entrypoint')
        (root / 'OntologyPlatform.Contracts.dll').write_bytes(b'synthetic strict parser')
        (root / 'runtime.json').write_text('{}')

    def test_parser_dependency_replacement_is_rejected(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            frozen = module.snapshot_binary_set(root)
            (root / 'OntologyPlatform.Contracts.dll').write_bytes(b'replaced parser')
            with self.assertRaises(RuntimeError):
                module.verify_binary_set(root, frozen)

    def test_new_or_missing_binary_member_is_rejected(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            frozen = module.snapshot_binary_set(root)
            module.verify_binary_set(root, frozen)
            (root / 'injected.dll').write_bytes(b'new member')
            with self.assertRaises(RuntimeError):
                module.verify_binary_set(root, frozen)
            (root / 'injected.dll').unlink()
            (root / 'runtime.json').unlink()
            with self.assertRaises(RuntimeError):
                module.verify_binary_set(root, frozen)

    def test_symlink_is_not_a_frozen_binary(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'linked.dll').symlink_to(root / 'OntologyPlatform.Contracts.dll')
            with self.assertRaises(ValueError):
                module.snapshot_binary_set(root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
