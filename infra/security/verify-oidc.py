#!/usr/bin/env python3
"""Exercise real isolated Keycloak/BFF HTTP flows; print only fixed safe checks.

This protocol driver does not replace the browser accessibility/SSR acceptance.
Passwords, callback URLs, tokens, Cookies and response bodies are never printed.
"""
import argparse
import copy
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Inspect every redirect before allowing an HTTP request to leave a host."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def validate_destination(address, approved):
    """Require an exact configured loopback origin, even for login form actions."""
    parsed = urllib.parse.urlsplit(address)
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '', '', ''))
    if (origin not in approved or parsed.username or parsed.password or parsed.fragment
            or parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')):
        raise ValueError('Unapproved protocol destination')


class LoginForm(HTMLParser):
    """Extract only the dedicated Keycloak password-login form action."""

    def __init__(self):
        super().__init__()
        self.actions = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'form' and values.get('id') == 'kc-form-login':
            self.actions.append(values.get('action'))

    def destination(self):
        if len(self.actions) != 1 or not self.actions[0]:
            raise ValueError('Expected one dedicated login form')
        return self.actions[0]


class ProtocolDriver:
    """Retain secrets in memory and produce only named, bounded result records."""

    def __init__(self, first, second, authority):
        self.first = first
        self.second = second
        self.approved = {first, second, urllib.parse.urlunsplit(urllib.parse.urlsplit(authority)[:2] + ('', '', ''))}
        for origin in self.approved:
            validate_destination(origin, self.approved)
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))
        self.current_check = 'initialization'
        self.records = []

    def request(self, address, form=None, headers=None):
        validate_destination(address, self.approved)
        payload = None if form is None else urllib.parse.urlencode(form).encode()
        request = urllib.request.Request(address, data=payload, headers=headers or {})
        if payload is not None:
            request.add_header('Content-Type', 'application/x-www-form-urlencoded')
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as failure:
            response = failure
        with response:
            return response.status, response.headers, response.read()

    def check(self, label, condition, status=None):
        self.current_check = label
        if not condition:
            raise AssertionError('Protocol assertion failed')
        self.records.append({'check': label, 'status': 'PASS', **({'httpStatus': status} if status is not None else {})})

    def follow_until_bff(self, address, form=None):
        """Follow OIDC protocol redirects, stopping before Next's public page."""
        for _ in range(15):
            status, headers, body = self.request(address, form)
            form = None
            if status not in (301, 302, 303, 307, 308):
                return status, headers, body
            address = urllib.parse.urljoin(address, headers.get('Location', ''))
            validate_destination(address, self.approved)
            parsed = urllib.parse.urlsplit(address)
            if parsed.path in ('/', '/signed-out') and address.startswith(self.first + '/'):
                return status, headers, body
        raise ValueError('OIDC redirect limit exceeded')

    def login(self, identity):
        self.current_check = 'oidc-login'
        status, headers, _ = self.request(self.first + '/auth/login?returnUrl=%2F')
        self.check('oidc-challenge', status == 302, status)
        destination = urllib.parse.urljoin(self.first, headers.get('Location', ''))
        validate_destination(destination, self.approved)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(destination).query)
        self.check('oidc-code-pkce-state-nonce', query.get('response_type') == ['code']
                   and query.get('code_challenge_method') == ['S256'] and bool(query.get('code_challenge'))
                   and bool(query.get('state')) and bool(query.get('nonce')))
        status, _, body = self.follow_until_bff(destination)
        self.check('keycloak-password-form', status == 200, status)
        parser = LoginForm()
        parser.feed(body.decode('utf-8'))
        action = urllib.parse.urljoin(destination, parser.destination())
        validate_destination(action, self.approved)
        status, _, _ = self.follow_until_bff(action, {'username': identity['username'], 'password': identity['password'], 'credentialId': ''})
        self.check('oidc-callback-completed', status == 302, status)
        session = [cookie for cookie in self.jar if cookie.name == '.OntologyPlatform.Session']
        self.check('httponly-lax-server-session-cookie', len(session) == 1
                   and (session[0].has_nonstandard_attr('httponly') or session[0].has_nonstandard_attr('HttpOnly'))
                   and session[0].get_nonstandard_attr('samesite', session[0].get_nonstandard_attr('SameSite', '')).lower() == 'lax')
        return copy.deepcopy(session[0])

    def json_request(self, origin, path, expected, label, form=None):
        self.current_check = label
        status, headers, body = self.request(origin + path, form)
        self.check(label, status == expected, status)
        self.check(label + '-no-store', headers.get('Cache-Control') == 'no-store')
        self.check(label + '-trace', bool(headers.get('X-Trace-Id')) and bool(headers.get('X-Correlation-Id')))
        if expected >= 400:
            self.check(label + '-problem', headers.get_content_type() == 'application/problem+json')
        return json.loads(body), headers

    def logout_and_replay(self, old_cookie):
        self.json_request(self.first, '/auth/logout', 403, 'csrf-missing-rejected', {})
        csrf, _ = self.json_request(self.first, '/auth/csrf', 200, 'antiforgery-issued')
        self.current_check = 'csrf-valid-logout'
        status, headers, _ = self.request(self.first + '/auth/logout', {'__RequestVerificationToken': csrf['requestToken']})
        self.check('csrf-valid-logout', status == 302, status)
        destination = urllib.parse.urljoin(self.first, headers.get('Location', ''))
        self.follow_until_bff(destination)
        self.jar.set_cookie(old_cookie)
        self.json_request(self.first, '/api/v1/platform/me', 401, 'logout-cookie-replay-first')
        self.jar.set_cookie(old_cookie)
        self.json_request(self.second, '/api/v1/platform/me', 401, 'logout-cookie-replay-second')


def run(arguments):
    """Consume only an explicitly supplied private runtime file, without echoing it."""
    runtime_path = Path(arguments.runtime_file).resolve()
    if '.tools/security/' not in runtime_path.as_posix() or (os.name != 'nt' and runtime_path.stat().st_mode & 0o077):
        raise ValueError('Expected a private ignored runtime configuration')
    runtime = json.loads(runtime_path.read_text())
    realm = json.loads(Path(runtime['realmFile']).read_text())
    records = []
    for label, site, readable in (('viewer-a', 'site-a', True), ('viewer-b', 'site-b', True),
                                   ('no-role-a', 'site-a', False), ('operator-a', 'site-a', True),
                                   ('auditor-a', 'site-a', False)):
        driver = ProtocolDriver(arguments.first_origin, arguments.second_origin, realm['authority'])
        try:
            driver.json_request(driver.first, '/api/v1/platform/me', 401, 'anonymous-denied')
            cookie = driver.login(realm['identities']['wave2-' + label])
            me, _ = driver.json_request(driver.first, '/api/v1/platform/me', 200, 'authenticated-identity')
            driver.check('minimal-identity-schema', set(me) == {'subjectId', 'displayName', 'roles', 'scopes'})
            driver.check('trusted-site-scope', me['scopes'] == [{'organizationId': 'org-demo', 'siteId': site}])
            twin, _ = driver.json_request(driver.second, '/api/v1/platform/me', 200, 'second-instance-cookie')
            driver.check('shared-identity', twin == me)
            resources, resource_headers = driver.json_request(driver.first, '/api/v1/platform/resources?siteId=' + site,
                                                              200 if readable else 403, 'resource-role-scope')
            if readable:
                driver.check('database-resource-scope', len(resources['items']) == 1
                             and resources['items'][0]['siteId'] == site and bool(resource_headers.get('X-Audit-Id')))
                other = 'site-b' if site == 'site-a' else 'site-a'
                driver.json_request(driver.first, '/api/v1/platform/resources?siteId=' + other, 403, 'cross-site-list-denied')
                driver.json_request(driver.first, '/api/v1/platform/resources/platform-' + other, 403, 'cross-site-row-denied')
                driver.json_request(driver.first, '/api/v1/platform/resources/unknown-synthetic-id', 404, 'unknown-resource')
            audit, _ = driver.json_request(driver.first, '/api/v1/platform/audit?limit=100',
                                           200 if label == 'auditor-a' else 403, 'audit-role')
            if label == 'auditor-a':
                driver.check('persisted-scoped-audit', bool(audit) and all(row['siteId'] == site and row['organizationId'] == 'org-demo' for row in audit))
                driver.json_request(driver.first, '/api/v1/platform/audit?limit=101', 400, 'audit-invalid-limit')
            driver.logout_and_replay(cookie)
            records.extend({'identity': label, **record} for record in driver.records)
        except Exception:
            records.extend({'identity': label, **record} for record in driver.records)
            records.append({'identity': label, 'check': driver.current_check, 'status': 'FAIL', 'details': 'SUPPRESSED'})
            print(json.dumps({'status': 'PARTIAL', 'checks': records}, ensure_ascii=False))
            return 1
    print(json.dumps({'status': 'PASS', 'checks': records, 'browserAcceptance': 'NOT_RUN', 'postgresRestart': 'NOT_RUN'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    parser.add_argument('--first-origin', default='http://localhost:15100')
    parser.add_argument('--second-origin', default='http://localhost:15101')
    arguments = parser.parse_args()
    try:
        sys.exit(run(arguments))
    except Exception as failure:
        print(json.dumps({'status': 'FAILED', 'category': type(failure).__name__, 'details': 'SUPPRESSED'}))
        sys.exit(1)
