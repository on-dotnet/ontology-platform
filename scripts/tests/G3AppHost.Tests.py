"""Exercise the actual Release AppHost guard before Build/Run can create resources."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / 'backend/src/AppHost/bin/Release/net10.0/OntologyPlatform.AppHost.dll'


class AppHostPrefixTests(unittest.TestCase):
    def probe(self, prefix):
        self.assertTrue(HOST.is_file(), 'Build the actual Release AppHost first')
        result = subprocess.run(['dotnet', str(HOST), '--Wave2:Enabled=true', '--Wave2:CoreOnly=false',
                                 '--DevelopmentInfrastructure:VolumePrefix=' + prefix, '--Wave2:NodePath='],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0, 'No probe may reach Build/Run')
        return result.stdout

    def test_current_and_legacy_prefixes_reach_next_required_configuration(self):
        for prefix in ('wave2-synthetic', 'g2-synthetic', 'g3-m1-synthetic', 'g3-m2-synthetic'):
            with self.subTest(prefix=prefix):
                self.assertIn('缺少Wave2配置：Wave2:NodePath', self.probe(prefix))

    def test_unapproved_or_unsafe_prefixes_stop_before_model_configuration(self):
        for prefix in ('g3-m3-synthetic', 'G3-m1-synthetic', '../g3-m1-synthetic',
                       'g3-m1-' + 'a' * 41, 'wave2-synthetic\n'):
            with self.subTest(prefix=prefix):
                output = self.probe(prefix)
                self.assertIn('纵向验收必须使用独立', output)
                self.assertNotIn('缺少Wave2配置：Wave2:NodePath', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
