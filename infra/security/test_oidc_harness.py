"""Offline boundary tests for the real OIDC acceptance driver."""
import importlib.util
import unittest
import http.cookiejar
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location('oidc_harness', Path(__file__).with_name('verify-oidc.py'))


class OidcDriverBoundaryTests(unittest.TestCase):
    """Keep credentials away from arbitrary redirect and form destinations."""

    def test_only_exact_approved_loopback_origins_can_receive_requests(self):
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        approved = {'http://localhost:15100', 'http://localhost:18080'}
        for address in ('http://evil.invalid/x', 'http://localhost:9999/x', 'http://user:pass@localhost:18080/x', 'file:///private/tmp/x'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                module.validate_destination(address, approved)
        module.validate_destination('http://localhost:18080/realms/test?state=synthetic', approved)

    def test_par_challenge_does_not_require_front_channel_secret_parameters(self):
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.challenge_transport({'client_id': ['test'], 'request_uri': ['urn:ietf:params:oauth:request_uri:synthetic']}), 'PAR')
        with self.assertRaises(ValueError):
            module.challenge_transport({'client_id': ['test']})

    def test_secure_cookie_localhost_exception_is_limited_to_approved_origins(self):
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        policy = module.LoopbackCookiePolicy({'http://localhost:18080'})
        cookie = http.cookiejar.Cookie(0, 'synthetic', 'unused', None, False, 'localhost.local', False, False, '/', True, True, None, True, None, None, {})
        self.assertTrue(policy.return_ok_secure(cookie, urllib.request.Request('http://localhost:18080/')))
        self.assertFalse(policy.return_ok_secure(cookie, urllib.request.Request('http://localhost:9999/')))
        self.assertFalse(policy.return_ok_secure(cookie, urllib.request.Request('http://evil.invalid/')))

    def test_login_parser_rejects_multiple_credential_forms(self):
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        form = module.LoginForm()
        form.feed('<form id="kc-form-login" action="/one"></form><form id="kc-form-login" action="/two"></form>')
        with self.assertRaises(ValueError):
            form.destination()


if __name__ == '__main__':
    unittest.main()
