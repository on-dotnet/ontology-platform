"""Exercise secret destination and transport boundaries without real credentials."""
import importlib.util
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
