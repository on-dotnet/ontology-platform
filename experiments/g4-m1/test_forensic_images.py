"""无需联网的取证下载拒绝与预算持久化回归。"""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import forensic_images as images


class Response(io.BytesIO):
    """固定响应，测试不得访问真实网络。"""
    status = 200
    headers = {}


class ForensicTests(unittest.TestCase):
    """检查下载前失败关闭、持久预算和真实内容身份。"""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.download = images.Download(self.root)

    def tearDown(self):
        self.download.lock.close()
        self.temp.cleanup()

    def test_unknown_host_never_connects(self):
        with patch.object(self.download.opener, 'open') as connect:
            with self.assertRaisesRegex(RuntimeError, 'HOST_REVIEW_REQUIRED'):
                self.download.get('https://unapproved.invalid/layer', 100)
            connect.assert_not_called()

    def test_http_downgrade_never_connects(self):
        with patch.object(self.download.opener, 'open') as connect:
            with self.assertRaisesRegex(RuntimeError, 'HOST_REVIEW_REQUIRED'):
                self.download.get('http://quay.io/layer', 100)
            connect.assert_not_called()

    def test_budget_rejects_before_connect(self):
        self.download.state['reservedBytes'] = images.LIMIT
        with patch.object(self.download.opener, 'open') as connect:
            with self.assertRaisesRegex(RuntimeError, 'DOWNLOAD_BUDGET_EXCEEDED'):
                self.download.get('https://quay.io/layer', 100)
            connect.assert_not_called()

    def test_failed_request_remains_reserved_across_restart(self):
        before = self.download.state['reservedBytes']
        with patch.object(self.download.opener, 'open', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError): self.download.get('https://quay.io/layer', 100)
        self.download.lock.close()
        self.download = images.Download(self.root)
        self.assertEqual(before + 100 + 1 + 65536, self.download.state['reservedBytes'])

    def test_actual_oversize_rejected(self):
        with patch.object(self.download.opener, 'open', return_value=Response(b'12345')):
            with self.assertRaisesRegex(RuntimeError, 'ACTUAL_SIZE_EXCEEDED'):
                self.download.get('https://quay.io/layer', 4)
        self.assertEqual(5, self.download.state['receivedBytes'])

    def test_exact_hash_accepted_wrong_hash_rejected(self):
        body = b'synthetic-layer'
        descriptor = dict(digest='sha256:' + hashlib.sha256(body).hexdigest(), size=len(body))
        with patch.object(self.download.opener, 'open', return_value=Response(body)):
            self.assertEqual(body, self.download.blob('https://quay.io/layer', descriptor, self.root/'oci', None, 'quay.io'))
        descriptor['digest'] = 'sha256:' + '0'*64
        with patch.object(self.download.opener, 'open', return_value=Response(body)):
            with self.assertRaisesRegex(RuntimeError, 'CONTENT_IDENTITY_MISMATCH'):
                self.download.blob('https://quay.io/layer', descriptor, self.root/'oci', None, 'quay.io')

    def test_auth_not_forwarded_to_other_allowed_host(self):
        with patch.object(self.download.opener, 'open', return_value=Response(b'x')) as connect:
            self.download.get('https://mcr.microsoft.com/layer', 1, 'synthetic-token', 'quay.io')
        self.assertNotIn('Authorization', connect.call_args.args[0].headers)


if __name__ == '__main__':
    unittest.main()
