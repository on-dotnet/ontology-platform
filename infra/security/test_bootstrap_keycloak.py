"""Exercise secret destination and transport boundaries without real credentials."""
import importlib.util
import contextlib
import io
import json
import os
import sys
from unittest.mock import patch
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).with_name("bootstrap-keycloak.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapBoundaryTests(unittest.TestCase):
    """Use local fixtures only; never read developer credentials or token values."""

    def test_success_creates_private_runtime_file_without_printing_secrets(self):
        """Exercise actual helper HTTP and filesystem success using a local fixture."""
        class BootstrapHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.send_response(200 if self.path.endswith('/token') else 201)
                self.end_headers()
                if self.path.endswith('/token'):
                    self.wfile.write(b'{"access_token":"synthetic-admin-marker"}')

            def log_message(self, *_):
                pass

        runtime = Path(__file__).resolve().parents[2] / '.tools/security'
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=runtime) as directory, ThreadingHTTPServer(('127.0.0.1', 0), BootstrapHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            output = Path(directory) / 'realm.json'
            captured = io.StringIO()
            try:
                with patch.dict(os.environ, {'WAVE2_KEYCLOAK_ADMIN_PASSWORD': 'synthetic-unused'}), patch.object(sys, 'argv', [
                        'bootstrap-keycloak.py', '--keycloak-origin', f'http://127.0.0.1:{server.server_port}',
                        '--runtime-output', str(output)]), contextlib.redirect_stdout(captured):
                    bootstrap.main()
                private = json.loads(output.read_text())
                self.assertEqual(len(private['identities']), 5)
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(private['clientSecret'], captured.getvalue())
                self.assertTrue(all(identity['password'] not in captured.getvalue() for identity in private['identities'].values()))
                self.assertEqual(json.loads(captured.getvalue())['status'], 'CREATED')
            finally:
                server.shutdown()
                thread.join()

    def test_credential_response_redirect_is_never_followed(self):
        """A redirect must fail before credentials can reach another endpoint."""
        class RedirectHandler(BaseHTTPRequestHandler):
            reached_target = False

            def do_GET(self):
                if self.path == "/target":
                    type(self).reached_target = True
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")
                else:
                    self.send_response(302)
                    self.send_header("Location", "/target")
                    self.end_headers()

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(urllib.error.HTTPError):
                    bootstrap.request(f"http://127.0.0.1:{server.server_port}", "/start", token="synthetic-unused")
                self.assertFalse(RedirectHandler.reached_target)
            finally:
                server.shutdown()
                thread.join()

    def test_runtime_output_cannot_be_written_to_source_tree(self):
        """A caller typo must not put newly generated passwords in tracked paths."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                bootstrap.validate_runtime_output(Path(directory) / "source.json")

    def test_origin_rejects_path_query_fragment_and_credentials(self):
        """Only canonical loopback HTTP origins are supported by this dev helper."""
        for origin in ("http://localhost/path", "http://localhost?q=x", "http://localhost/#x", "http://user:pass@localhost", "https://localhost"):
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):
                    bootstrap.validate_origin(origin)
        bootstrap.validate_origin("http://localhost:18080")


if __name__ == "__main__":
    unittest.main()
