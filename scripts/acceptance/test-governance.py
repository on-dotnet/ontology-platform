#!/usr/bin/env python3
"""Mandatory real PostgreSQL ticket integration check using a disposable test container.

This is a bounded test fixture, not a second development orchestration model.
Secrets are generated in memory and output is sanitized before persistence.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
from owned_test_containers import OwnedTestContainers

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('wave2_runtime', ROOT / 'scripts/acceptance/wave2-runtime.py')
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


def main(configuration="Debug", test_filter=None):
    name = 'wave2-governance-test-' + secrets.token_hex(6)
    database_password = secrets.token_urlsafe(40)
    env = os.environ.copy()
    env.update(POSTGRES_PASSWORD=database_password, POSTGRES_DB='governance')
    identity_name = name + '-keycloak'
    identity_password = secrets.token_urlsafe(40)
    env['KC_BOOTSTRAP_ADMIN_PASSWORD'] = identity_password
    code = 1
    record = []
    owned = OwnedTestContainers(os.environ.get('PLATFORM_TASK_ID', 'DEVELOPMENT'), name, record)

    def command(args, required=True):
        args = owned.prepare(args)
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        owned.observe(args, result)
        output = ''.join(RUNTIME.sanitize(line, [value for value in (database_password, identity_password, env.get('G1_SEC_PG_CONNECTION')) if value]) for line in result.stdout.splitlines())
        # 空值不能进入脱敏替换列表，连接值已包含密码但仍整体隐藏。
        record.append(dict(command=args, exitCode=result.returncode, output=output))
        print(output, end='')
        if required and result.returncode:
            raise RuntimeError('Integration command failed')
        return result

    try:
        # 固定M0已经批准的PG摘要，主机只能通过回环随机端口访问。
        command(['docker', 'run', '--detach', '--name', name, '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_DB',
                 '--publish', '127.0.0.1::5432', '--tmpfs', '/var/lib/postgresql',
                 'postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6'])
        port = subprocess.check_output(['docker', 'port', name, '5432/tcp'], text=True).strip().rsplit(':', 1)[1]
        for _ in range(60):
            if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres', '-d', 'governance'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(1)
        else:
            raise TimeoutError('PostgreSQL not ready')
        env['G1_SEC_PG_CONNECTION'] = f'Host=127.0.0.1;Port={port};Database=governance;Username=postgres;Password={database_password}'
        env['ConnectionStrings__governance'] = env['G1_SEC_PG_CONNECTION']
        command(['dotnet', 'tool', 'restore'])
        module = 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance'
        command(['dotnet', 'tool', 'run', 'dotnet-ef', 'database', 'update', '--project', module, '--startup-project', module, '--configuration', configuration, '--no-build'])
        # 临时身份服务只用于真实PAR测试，独立容器、随机密码、不访问开发栈。
        command(['docker', 'run', '--detach', '--name', identity_name,
                 '--env', 'KC_BOOTSTRAP_ADMIN_PASSWORD', '--env', 'KC_BOOTSTRAP_ADMIN_USERNAME=wave2-bootstrap',
                 '--publish', '127.0.0.1::8080',
                 'quay.io/keycloak/keycloak:26.8.1@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b', 'start-dev'])
        identity_port = subprocess.check_output(['docker', 'port', identity_name, '8080/tcp'], text=True).strip().rsplit(':', 1)[1]
        authority_origin = 'http://localhost:' + identity_port
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            try:
                with opener.open(authority_origin + '/realms/master/.well-known/openid-configuration', timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise TimeoutError('Keycloak not ready')
        private = ROOT / '.tools/security' / name
        private.mkdir(parents=True, mode=0o700)
        private.chmod(0o700)
        env['WAVE2_KEYCLOAK_ADMIN_PASSWORD'] = identity_password
        realm_file = private / 'realm.json'
        command(['python3', 'infra/security/bootstrap-keycloak.py', '--keycloak-origin', authority_origin,
                 '--runtime-output', str(realm_file)])
        runtime_file = private / 'runtime.json'
        RUNTIME.private_json(runtime_file, {'realmFile': str(realm_file)})
        env['G1_SEC_OIDC_RUNTIME'] = str(runtime_file)
        test = ['dotnet', 'test', '--project', 'backend/tests/OntologyPlatform.SecurityTests', '--configuration', configuration, '--no-build', '--no-restore']
        if test_filter:
            test.extend(['--filter', test_filter])
        command(test)
        code = 0
    except Exception as failure:
        record.append(dict(status='FAIL', category=type(failure).__name__, details='suppressed'))
        print('FAIL: real governance integration; details retained only after sanitization')
        code = 1
    finally:
        if not owned.cleanup():
            code = 1
        target = ROOT / 'artifacts/governance-integration.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        record.append(dict(check='integration-exit', exitCode=code))
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    if code == 0:
        print('PASS: selected real PostgreSQL/Keycloak integration filter; count is in actual test output.' if test_filter else 'PASS: real PostgreSQL tickets/revocation/expiry/audit and real Keycloak PAR security integration.')
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', choices=['Debug', 'Release'], default='Debug')
    parser.add_argument('--filter')
    args = parser.parse_args()
    sys.exit(main(args.configuration, args.filter))
