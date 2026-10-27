"""Exercise actual evidence path selection, never write into historical task evidence."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class EvidenceBoundaryTests(unittest.TestCase):
    """A misplaced or escaped output must fail before creating a directory."""

    def choose(self, root, selected):
        path = Path(__file__).resolve().parents[1] / 'acceptance/evidence_paths.py'
        if not path.exists():
            self.fail('Missing bounded evidence selector; G3 runners cannot yet isolate outputs')
        spec = importlib.util.spec_from_file_location('evidence_paths', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {'PLATFORM_EVIDENCE_DIR': selected}):
            return module.evidence_directory(root, 'docs/evidence/OLD/master')

    def test_current_task_output_does_not_touch_old_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'docs/evidence/OLD/master'
            old.mkdir(parents=True)
            (old / 'original.txt').write_text('historical bytes')
            target = self.choose(root, 'docs/evidence/G3-M1-001/runtime')
            self.assertEqual(target, root.resolve() / 'docs/evidence/G3-M1-001/runtime')
            self.assertEqual((old / 'original.txt').read_text(), 'historical bytes')

    def test_outside_and_traversal_are_rejected_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for selected in ['../outside', 'artifacts/raw', 'docs/evidence/../../../outside']:
                with self.assertRaises(ValueError):
                    self.choose(root, selected)
            self.assertFalse((root / 'artifacts').exists())

    def test_existing_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            outside = Path(directory) / 'private'
            outside.mkdir()
            (root / 'docs/evidence').mkdir(parents=True)
            (root / 'docs/evidence/linked').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.choose(root, 'docs/evidence/linked/new')
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
