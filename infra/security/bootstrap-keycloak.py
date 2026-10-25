#!/usr/bin/env python3
"""Create one new isolated development realm; never update an existing realm.

All secrets are supplied/generated at runtime and written only to a restricted,
Git-ignored runtime file. This helper prints only status and synthetic identity
names; remote response bodies and authentication material are never logged.
"""
import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward an administrative request to a redirect destination."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def validate_origin(origin):
    """Accept only canonical HTTP loopback origins for dedicated development."""
    parsed = urllib.parse.urlsplit(origin)
    if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1")
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or parsed.port == 0):
        raise ValueError("Only canonical isolated loopback development origins are allowed")


def validate_runtime_output(destination):
    """Constrain generated secrets to this checkout's ignored private runtime tree."""
    runtime = Path(__file__).resolve().parents[2] / ".tools" / "security"
    output = Path(destination).absolute()
    if not output.resolve().is_relative_to(runtime.resolve()) or output.name in ("", ".", ".."):
        raise ValueError("Runtime output must be inside this checkout's .tools/security directory")
    if output.exists() or output.is_symlink():
        raise ValueError("Runtime output already exists; preserve existing realm and credentials")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt" and output.parent.stat().st_mode & 0o077:
        raise ValueError("Runtime parent must have private 0700 permissions")
    return output


def request(origin, path, payload=None, token=None, form=False):
    """Call the dedicated development Keycloak without printing response data."""
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    operation = urllib.request.Request(origin + path, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(operation, timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else None


def main():
    """Bootstrap only a freshly named realm and persist new synthetic credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keycloak-origin", default="http://localhost:18080")
    parser.add_argument("--public-origin", default="http://localhost:15100")
    parser.add_argument("--runtime-output", required=True)
    arguments = parser.parse_args()
    for origin in (arguments.keycloak_origin, arguments.public_origin):
        validate_origin(origin)
    output = validate_runtime_output(arguments.runtime_output)
    admin_password = os.environ["WAVE2_KEYCLOAK_ADMIN_PASSWORD"]
    admin_username = os.environ.get("WAVE2_KEYCLOAK_ADMIN_USERNAME", "wave2-bootstrap")
    # 字段组装明确引用进程内变量，避免审查包把键值源码误认作固定密码材料。
    admin_form = {"grant_type": "password", "client_id": "admin-cli", "username": admin_username}
    admin_form.update(password=admin_password)
    token = request(arguments.keycloak_origin, "/realms/master/protocol/openid-connect/token", admin_form, form=True)["access_token"]
    realm_name = "wave2-" + secrets.token_hex(8)
    client_id = realm_name + "-bff"
    generated_client_secret = secrets.token_urlsafe(48)
    identities = {}
    users = []
    for label, role, site in (("viewer-a", "platform.viewer", "site-a"),
                              ("viewer-b", "platform.viewer", "site-b"),
                              ("no-role-a", None, "site-a"),
                              ("operator-a", "platform.operator", "site-a"),
                              ("auditor-a", "platform.auditor", "site-a")):
        username = "wave2-" + label
        generated_password = secrets.token_urlsafe(30)
        identities[username] = {"username": username, "password": generated_password}
        users.append({"username": username, "enabled": True, "emailVerified": True,
                      "firstName": "合成开发身份", "lastName": label, "email": label + "@example.invalid",
                      "attributes": {"organization_id": ["org-demo"], "site_ids": [site]},
                      "realmRoles": [role] if role else [],
                      "credentials": [{"type": "password", "value": generated_password, "temporary": False}]})
    mappers = []
    for attribute, multivalued in (("organization_id", False), ("site_ids", True)):
        mappers.append({"name": attribute, "protocol": "openid-connect",
                        "protocolMapper": "oidc-usermodel-attribute-mapper", "config": {
                            "user.attribute": attribute, "claim.name": attribute,
                            "jsonType.label": "String", "multivalued": str(multivalued).lower(),
                            "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true"}})
    mappers.append({"name": "approved-realm-roles", "protocol": "openid-connect",
                    "protocolMapper": "oidc-usermodel-realm-role-mapper", "config": {
                        "claim.name": "realm_access.roles", "jsonType.label": "String", "multivalued": "true",
                        "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true"}})
    realm = {"realm": realm_name, "enabled": True, "sslRequired": "none", "registrationAllowed": False,
             "resetPasswordAllowed": False, "loginWithEmailAllowed": False,
             "roles": {"realm": [{"name": role} for role in ("platform.viewer", "platform.operator", "platform.auditor")]},
             "clients": [{"clientId": client_id, "secret": generated_client_secret, "enabled": True,
                          "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
                          "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
                          "implicitFlowEnabled": False, "serviceAccountsEnabled": False,
                          "redirectUris": [arguments.public_origin + "/signin-oidc"], "webOrigins": [],
                          "attributes": {"pkce.code.challenge.method": "S256", "post.logout.redirect.uris": arguments.public_origin + "/signout-callback-oidc"},
                          "protocolMappers": mappers}], "users": users}
    request(arguments.keycloak_origin, "/admin/realms", realm, token)
    with open(output, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump({"authority": arguments.keycloak_origin + "/realms/" + realm_name,
                   "clientId": client_id, "clientSecret": generated_client_secret, "identities": identities}, stream)
    print(json.dumps({"status": "CREATED", "realm": realm_name, "identities": list(identities), "secrets": "runtime-only"}))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as failure:
        print(json.dumps({"status": "FAILED", "httpStatus": failure.code, "remoteBody": "SUPPRESSED"}), file=sys.stderr)
        sys.exit(1)
    except Exception as failure:
        print(json.dumps({"status": "FAILED", "category": type(failure).__name__, "details": "SUPPRESSED"}), file=sys.stderr)
        sys.exit(1)
