"""Exercise transport boundaries; product cache correctness lives in canonical real tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ci_cache',ROOT/'scripts/maintenance/fuseki_ci_cache.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CacheTransportTests(unittest.TestCase):
    def identity(self):
        key='ontology-fuseki-image-v2-linux-amd64-'+'a'*64
        return dict(schemaVersion=2,cacheKey=key,failureStateKey=key+'-failure-v1-'+'b'*64,
            envFingerprint='b'*64,inputFingerprint='a'*64,contextSha256='c'*64,
            platform='linux/amd64',image='ontology-platform-fuseki:context-'+'a'*64)

    def test_only_exact_controlled_identity_becomes_action_output(self):
        m.validate_identity(self.identity())
        for key,value in [('cacheKey','prefix'),('failureStateKey','other'),('platform','linux/386'),
                          ('inputFingerprint','a'*64+'\nextra=unsafe'),('schemaVersion',1),('image','other')]:
            with self.assertRaises(ValueError):m.validate_identity({**self.identity(),key:value})

    def test_unknown_usage_and_paid_or_large_storage_are_blocked(self):
        self.assertEqual(m.budget(dict(active_caches_size_in_bytes=0),123)['status'],'PASS')
        for usage,size in [({},0),(dict(active_caches_size_in_bytes=True),0),
                           (dict(active_caches_size_in_bytes=-1),0),
                           (dict(active_caches_size_in_bytes=m.MAX_PROJECT_STORAGE),1),
                           (dict(active_caches_size_in_bytes=0),m.MAX_ARCHIVE+1)]:
            with self.assertRaises(ValueError):m.budget(usage,size)

    def test_directory_cannot_include_links(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'image.tar').write_bytes(b'123')
            self.assertEqual(m.directory_size(path),3)
            (path/'linked').symlink_to(path/'image.tar')
            with self.assertRaises(ValueError):m.directory_size(path)


if __name__=='__main__':unittest.main()
