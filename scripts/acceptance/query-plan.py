#!/usr/bin/env python3
"""Run approved Query tests on disposable random-loopback PG, RustFS and Jena."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/G2-THIN-SLICE-001/QRY'
JENA = os.environ.get('G2_TEST_JENA_IMAGE', 'ontology-platform-g2-fuseki:6.2.0')
PG = 'postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6'
S3 = 'rustfs/rustfs:1.0.3@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='query-plan')
    parser.add_argument('--filter')
    parser.add_argument('--artifact-only', action='store_true')
    args = parser.parse_args()
    name = 'g2-query-' + secrets.token_hex(6)
    env = os.environ.copy()
    pg_secret = secrets.token_urlsafe(40)
    access = 'query' + secrets.token_hex(10)
    signing = secrets.token_urlsafe(40)
    env.update(POSTGRES_PASSWORD=pg_secret, POSTGRES_DB='governance', RUSTFS_ACCESS_KEY=access, RUSTFS_SECRET_KEY=signing)
    records = []
    code = 1
    connection = None
    names = []

    def run(command, required=True):
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout
        for sensitive in [pg_secret, access, signing, connection]:
            if sensitive:
                output = output.replace(sensitive, '[REDACTED]')
        records.append(dict(command=command, exitCode=result.returncode, output=output))
        print(output, end='', flush=True)
        if required and result.returncode:
            raise RuntimeError('Query command failed; see safe recorded result')
        return result

    def wait_url(url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            try:
                with opener.open(url, timeout=1):
                    return
            except OSError:
                time.sleep(.25)
        raise TimeoutError('Isolated service startup failed')

    with tempfile.TemporaryDirectory(prefix=name, dir='/private/tmp' if Path('/private/tmp').is_dir() else None) as directory:
        path = Path(directory)
        fixture = path / 'fixture'
        fixture.mkdir(mode=0o755)
        fixture.chmod(0o755)
        config = '''@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix ja: <http://jena.hpl.hp.com/2005/11/Assembler#> .
@prefix tdb2: <http://jena.apache.org/2016/tdb#> .
[] a fuseki:Server ; fuseki:services ( <#validation> <#ontology> ) .
'''
        for service, dataset in [('validation', 'memory'), ('ontology', 'tdb')]:
            config += f'''<#{service}> a fuseki:Service ; fuseki:name "{service}" ; fuseki:dataset <#{dataset}> ;
 fuseki:endpoint [ fuseki:operation fuseki:query ; fuseki:name "query" ] ;
 fuseki:endpoint [ fuseki:operation fuseki:gsp-rw ; fuseki:name "data" ] ;
 fuseki:endpoint [ fuseki:operation fuseki:shacl ; fuseki:name "shacl" ] .
'''
        config += '<#memory> a ja:MemoryDataset .\n<#tdb> a tdb2:DatasetTDB2 ; tdb2:location "/tmp/query-tdb" .\n'
        (fixture / 'config.ttl').write_text(config)
        (fixture / 'log4j2.properties').write_text('status=error\nrootLogger.level=OFF\n')
        for public_file in fixture.iterdir():
            public_file.chmod(0o644)
        try:
            modes = {'fixture': oct(fixture.stat().st_mode & 0o777), **{file.name: oct(file.stat().st_mode & 0o777) for file in fixture.iterdir()}}
            if modes != {'fixture': '0o755', 'config.ttl': '0o644', 'log4j2.properties': '0o644'}:
                raise RuntimeError('Public Jena fixture permission check failed')
            records.append(dict(check='public-jena-fixture-modes', exitCode=0, modes=modes))
            run(['docker', 'image', 'inspect', '--format', '{{.Id}}', JENA])
            run(['dotnet', 'restore', 'backend/tests/OntologyPlatform.QueryTests', '--locked-mode'])
            names.append(name + '-pg')
            run(['docker', 'run', '--detach', '--name', names[-1], '--memory', '256m', '--cpus', '1', '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_DB', '--tmpfs', '/var/lib/postgresql', PG])
            pgport = run(['docker', 'port', names[-1], '5432/tcp']).stdout.strip().rsplit(':', 1)[1]
            for _ in range(120):
                if subprocess.run(['docker', 'exec', names[-1], 'pg_isready', '-U', 'postgres', '-d', 'governance'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    break
                time.sleep(.25)
            else:
                raise TimeoutError('Isolated PostgreSQL startup failed')
            connection = f'Host=127.0.0.1;Port={pgport};Database=governance;Username=postgres;Password={pg_secret};Maximum Pool Size=12'
            env['G2_QRY_PG'] = connection
            env['ConnectionStrings__governance'] = connection
            names.append(name + '-s3')
            run(['docker', 'run', '--detach', '--name', names[-1], '--memory', '768m', '--cpus', '1', '--publish', '127.0.0.1::9000', '--env', 'RUSTFS_ACCESS_KEY', '--env', 'RUSTFS_SECRET_KEY', '--env', 'RUSTFS_CONSOLE_ENABLE=false', '--tmpfs', '/data:mode=1777', S3, '/data'])
            s3port = run(['docker', 'port', names[-1], '9000/tcp']).stdout.strip().rsplit(':', 1)[1]
            env['G2_QRY_S3'] = 'http://127.0.0.1:' + s3port
            wait_url(env['G2_QRY_S3'] + '/health/ready')
            names.append(name + '-jena')
            run(['docker', 'run', '--detach', '--name', names[-1], '--memory', '768m', '--cpus', '1', '--publish', '127.0.0.1::3030', '--mount', f'type=bind,src={fixture},dst=/fixture,readonly', '--entrypoint', 'java', JENA, '-Xmx384m', '-Dlog4j.configurationFile=/fixture/log4j2.properties', '-jar', '/opt/fuseki/fuseki-server.jar', '--config=/fixture/config.ttl'])
            jenaport = run(['docker', 'port', names[-1], '3030/tcp']).stdout.strip().rsplit(':', 1)[1]
            env['G2_QRY_JENA'] = 'http://127.0.0.1:' + jenaport
            env['G2_QRY_SAMPLES'] = str(ROOT / 'samples/g2')
            env['G2_QRY_TIMINGS'] = str(path / 'timings.jsonl')
            wait_url(env['G2_QRY_JENA'] + '/$/ping')
            run(['dotnet', 'build', 'backend/tests/OntologyPlatform.QueryTests', '--no-restore'])
            if not args.artifact_only:
                run(['dotnet', 'tool', 'restore'])
                for module in ['Governance', 'Ontology', 'Publishing']:
                    project = f'backend/src/Modules/{module}/OntologyPlatform.Modules.{module}'
                    run(['dotnet', 'tool', 'run', 'dotnet-ef', 'database', 'update', '--project', project, '--startup-project', project, '--no-build'])
            command = ['dotnet', 'test', '--project', 'backend/tests/OntologyPlatform.QueryTests', '--no-restore', '--no-build']
            if args.filter:
                command += ['--', '--filter', args.filter]
            code = run(command, False).returncode
        except Exception as failure:
            records.append(dict(status='FAIL', category=type(failure).__name__))
            print(type(failure).__name__, flush=True)
        finally:
            for container in reversed(names):
                run(['docker', 'rm', '--force', container], False)
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, capture_output=True).stdout.strip()
            source_files = [*ROOT.glob('backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/*.cs'), *ROOT.glob('backend/tests/OntologyPlatform.QueryTests/*.cs'), ROOT / 'backend/src/Hosts/OntologyPlatform.Api/G2/SemanticEndpoints.cs', ROOT / 'docs/contracts/g2-schemas.openapi.json', Path(__file__).resolve()]
            source_hashes = {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(source_files)}
            dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, text=True, capture_output=True).stdout)
            (EVIDENCE / (args.label + '.json')).write_text(json.dumps(dict(sourceSha=sha, workingTreeChanges=dirty, sourceHashes=source_hashes, exitCode=code, timings=[json.loads(line) for line in (path / 'timings.jsonl').read_text().splitlines()] if (path / 'timings.jsonl').exists() else [], records=records), ensure_ascii=False, indent=2) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
