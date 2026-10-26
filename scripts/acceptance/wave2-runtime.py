#!/usr/bin/env python3
"""Run only the new isolated AppHost Wave2 model with private runtime secrets.

Never print configuration or raw subprocess output. Every line is sanitized
before both terminal output and evidence persistence. This does not collect
existing system credentials or historical container/volume contents.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
# 默认保留历史入口；后续收口显式选择新证据目录，不覆盖历史事实。
EVIDENCE = (ROOT / os.environ.get('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G1-WAVE2/master')).resolve()
if not EVIDENCE.is_relative_to((ROOT / 'docs/evidence').resolve()):
    raise ValueError('Evidence must stay under repository docs/evidence')
EVIDENCE.mkdir(parents=True, exist_ok=True)



def private_json(path, value):
    """Create a new private file exclusively; never overwrite prior test secrets."""
    with open(path, 'x', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(value, stream)


def load_runtime(path):
    """Restrict secret persistence to this checkout's ignored security directory."""
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / '.tools/security').resolve()):
        raise ValueError('Runtime must be under this checkout .tools/security')
    return path, json.loads(path.read_text())


def prepare(profile="wave2"):
    """Prepare one new volume prefix, random passwords and shared encrypted PFX."""
    directory = ROOT / '.tools/security' / (profile + '-' + secrets.token_hex(6))
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    keyring = directory / 'keyring'
    keyring.mkdir(mode=0o700)
    runtime = dict(volumePrefix=directory.name, postgresPassword=secrets.token_urlsafe(40),
                   keycloakPassword=secrets.token_urlsafe(40), grafanaPassword=secrets.token_urlsafe(40),
                   certificatePassword=secrets.token_urlsafe(40), healthKey=secrets.token_urlsafe(40),
                   certificatePath=str(directory / 'keyring.pfx'), keyRingPath=str(keyring),
                   realmFile=str(directory / 'realm.json'))
    if profile == 'g2':
        runtime.update(rustfsAccessKey=secrets.token_hex(10), rustfsSecretKey=secrets.token_urlsafe(40))
    path = directory / 'runtime.json'
    private_json(path, runtime)
    subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT / 'scripts/acceptance/new-wave2-certificate.ps1'),
                    '-RuntimeFile', str(path)], check=True)
    print(str(path.relative_to(ROOT)))


def secret_values(value):
    """Enumerate only secret-bearing values already generated for this run."""
    if isinstance(value, dict):
        for key, child in value.items():
            if any(word in key.lower() for word in ('password', 'secret', 'healthkey')) and isinstance(child, str):
                yield child
            yield from secret_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from secret_values(child)


def sanitize(line, sensitive):
    """Remove credentials and URL queries before any observable persistence."""
    if re.search(r'''(?i)["']?(password|client_secret|access_token|id_token|refresh_token|authorization|set-cookie|cookie|token|state|nonce|code)["']?\s*[:=]''', line):
        return '[REDACTED: sensitive protocol field]\n'
    for value in sensitive:
        line = line.replace(value, '[REDACTED]')
    line = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[QUERY_REDACTED]', line)
    line = re.sub(r'(?i)(authorization|set-cookie|cookie)\s*:[^\r\n]*', r'\1: [REDACTED]', line)
    line = re.sub(r'(?i)(password|client_secret|access_token|id_token|refresh_token|token|state|code)=([^\s;,&]+)', r'\1=[REDACTED]', line)
    return line.rstrip() + '\n'


def run(path, mode, profile="wave2", configuration="Debug"):
    """Launch AppHost using process-local parameters; preserve named volumes on exit."""
    path, runtime = load_runtime(path)
    env = os.environ.copy()
    env.update({'Wave2__Enabled': 'true', 'Wave2__CoreOnly': str(mode == 'core').lower(),
                'DevelopmentInfrastructure__VolumePrefix': runtime['volumePrefix'],
                'Parameters__postgres-password': runtime['postgresPassword'],
                'Parameters__keycloak-admin-password': runtime['keycloakPassword'],
                'Parameters__grafana-admin-password': runtime['grafanaPassword']})
    if profile == 'g2':
        env.update({'G2__Enabled': 'true', 'Parameters__rustfs-access-key': runtime['rustfsAccessKey'],
                    'Parameters__rustfs-secret-key': runtime['rustfsSecretKey']})
    if mode == 'full':
        realm = json.loads(Path(runtime['realmFile']).read_text())
        runtime['realm'] = realm
        tools = json.loads(subprocess.check_output(['pwsh', '-NoProfile', '-File', str(ROOT / 'scripts/bootstrap-web-tools.ps1')], cwd=ROOT))
        env.update({'Wave2__Authority': realm['authority'], 'Wave2__ClientId': realm['clientId'],
                    'Parameters__bff-client-secret': realm['clientSecret'],
                    'Parameters__keyring-certificate-password': runtime['certificatePassword'],
                    'Parameters__api-health-key': runtime['healthKey'],
                    'Wave2__KeyRingPath': runtime['keyRingPath'], 'Wave2__CertificatePath': runtime['certificatePath'],
                    'Wave2__NodePath': tools['nodePath']})
    sensitive = sorted(set(secret_values(runtime)), key=len, reverse=True)
    evidence = EVIDENCE / 'runtime'
    evidence.mkdir(parents=True, exist_ok=True)
    log = evidence / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + mode + '.txt')
    command = ['dotnet', 'run', '--project', 'backend/src/AppHost', '--no-build', '--no-restore', '--configuration', configuration]
    with log.open('x', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for line in process.stdout:
                clean = sanitize(line, sensitive)
                stream.write(clean)
                stream.flush()
                print(clean, end='', flush=True)
            result = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            result = process.wait(timeout=40)
        stream.write('exitCode=' + str(result) + '\n')
    return result


def bootstrap(path, profile="wave2"):
    """Supply only the new bootstrap password to the reviewed SEC helper."""
    _, runtime = load_runtime(path)
    env = os.environ.copy()
    env['WAVE2_KEYCLOAK_ADMIN_PASSWORD'] = runtime['keycloakPassword']
    return subprocess.run(['python3', 'infra/security/bootstrap-keycloak.py', '--runtime-output', runtime['realmFile'], '--profile', profile], cwd=ROOT, env=env).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'core', 'bootstrap', 'full'])
    parser.add_argument('--runtime-file')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
        return 0
    if not args.runtime_file:
        parser.error('--runtime-file required')
    if args.mode == 'bootstrap':
        return bootstrap(args.runtime_file)
    return run(args.runtime_file, args.mode)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as failure:
        print('FAILED: ' + type(failure).__name__ + '; details suppressed for secret safety', file=sys.stderr)
        sys.exit(1)
