"""Content-addressed Fuseki source and cache-hit regression tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('canonical', ROOT / 'scripts/maintenance/canonical_fuseki.py')

class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ontology-fuseki-')
        self.context = Path(self.tmp.name)
        (self.context / 'Dockerfile').write_text('FROM scratch\n')
        self.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(self.mod)
    def tearDown(self): self.tmp.cleanup()
    def test_content_identity_ignores_metadata_but_tracks_every_byte(self):
        first = self.mod.context_digest(self.context)
        (self.context / 'entrypoint.sh').write_text('echo test\n')
        self.assertNotEqual(self.mod.context_digest(self.context), first)
        self.assertEqual(self.mod.context_digest(self.context), self.mod.context_digest(self.context))
    def test_symlink_and_unknown_input_are_rejected(self):
        (self.context / 'other').symlink_to('/tmp')
        with self.assertRaises(self.mod.BuildRefused): self.mod.context_digest(self.context)
    def test_cache_hit_never_builds_and_records_image_identity(self):
        digest = self.mod.context_digest(self.context)
        image = 'sha256:' + 'a'*64
        data = {'Id': image, 'Labels': {'org.opencontainers.image.source': self.mod.SOURCE, 'io.ontology-platform.context-sha256': digest}}
        def run(args, **kwargs):
            self.assertEqual(args[:3], ['docker','image','inspect'])
            return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
        with patch.object(self.mod, 'invoke', side_effect=run) as cli:
            result = self.mod.ensure_image(self.context, 'TEST-001', 'fixture')
            self.assertTrue(result['reused'])
            self.assertEqual(result['imageId'], image)
            self.assertEqual(cli.call_count, 1)
    def test_changed_existing_tag_is_refused(self):
        with patch.object(self.mod, 'invoke', return_value=subprocess.CompletedProcess([],0,json.dumps({'Id':'sha256:'+'a'*64,'Labels':{}}),'')):
            with self.assertRaises(self.mod.BuildRefused): self.mod.ensure_image(self.context,'TEST-001','fixture')
    def test_socket_or_inspect_errors_do_not_trigger_build(self):
        with patch.object(self.mod, 'invoke', return_value=subprocess.CompletedProcess([],1,'','permission denied')) as cli:
            with self.assertRaises(self.mod.BuildRefused): self.mod.ensure_image(self.context,'TEST-001','fixture')
            self.assertEqual(cli.call_count,1)
    def test_both_apphost_profiles_and_acceptance_share_source(self):
        for name in ('G2Infrastructure.cs','DevelopmentInfrastructure.cs'):
            text = (ROOT/'backend/src/AppHost'/name).read_text()
            self.assertNotIn('AddDockerfile',text)
            self.assertIn('CanonicalFusekiImage.Add',text)
        text=(ROOT/'scripts/acceptance/g2-integration.ps1').read_text()
        self.assertIn('canonical_fuseki.py',text)
        self.assertNotIn('docker build',text)

if __name__ == '__main__': unittest.main()
