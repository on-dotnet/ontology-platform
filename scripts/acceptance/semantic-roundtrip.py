#!/usr/bin/env python3
"""Run real SEM tests against bounded, disposable Fuseki; never use historical runtime or credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/G2-THIN-SLICE-001/SEM'
JENA = 'fuseki:8b85cd963ab3910a87ff4d69819a814fcc536d5f'
PG = 'postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6'


def main(test_filter=None, postgres=False, label='semantic-roundtrip'):
    name = 'g2-sem-' + secrets.token_hex(6)
    records = []
    env = os.environ.copy()
    secret = secrets.token_urlsafe(40)
    env['POSTGRES_PASSWORD'] = secret
    env['POSTGRES_DB'] = 'governance'
    connection = None
    code = 1

    def run(args, required=True):
        result = subprocess.run(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout
        if connection:
            output = output.replace(connection, '[CONNECTION]')
        output = output.replace(secret, '[REDACTED]')
        records.append(dict(command=args, exitCode=result.returncode, output=output))
        print(output, end='', flush=True)
        if required and result.returncode:
            raise RuntimeError('SEM command failed; see recorded exit code')
        return result

    with tempfile.TemporaryDirectory(prefix=name, dir='/private/tmp') as directory:
        path = Path(directory)
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
        config += '<#memory> a ja:MemoryDataset .\n<#tdb> a tdb2:DatasetTDB2 ; tdb2:location "/tmp/sem-tdb" .\n'
        (path / 'config.ttl').write_text(config)
        # Disable request, parser and query plaintext outlets, including failure paths.
        (path / 'log4j2.properties').write_text('status=error\nrootLogger.level=OFF\n')
        try:
            run(['docker', 'run', '--detach', '--name', name, '--publish', '127.0.0.1::3030', '--memory', '768m', '--cpus', '1',
                 '--mount', f'type=bind,src={path},dst=/fixture,readonly', '--entrypoint', 'java', JENA,
                 '-Xmx384m', '-Dlog4j.configurationFile=/fixture/log4j2.properties', '-jar', '/opt/fuseki/fuseki-server.jar', '--config=/fixture/config.ttl'])
            port = run(['docker', 'port', name, '3030/tcp']).stdout.strip().rsplit(':', 1)[1]
            origin = 'http://127.0.0.1:' + port
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(60):
                try:
                    with opener.open(origin + '/$/ping', timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            else:
                raise TimeoutError('Isolated Fuseki startup failed')
            env.update(G2_SEM_JENA_ORIGIN=origin, G2_SEM_SAMPLES=str(ROOT / 'samples/g2'))
            if postgres:
                run(['docker', 'run', '--detach', '--name', name + '-pg', '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_DB', '--memory', '512m', '--cpus', '1', '--tmpfs', '/var/lib/postgresql', PG])
                pgport = run(['docker', 'port', name + '-pg', '5432/tcp']).stdout.strip().rsplit(':', 1)[1]
                for _ in range(60):
                    if subprocess.run(['docker', 'exec', name + '-pg', 'pg_isready', '-U', 'postgres', '-d', 'governance'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                        break
                    time.sleep(.25)
                connection = f'Host=127.0.0.1;Port={pgport};Database=governance;Username=postgres;Password={secret}'
                env['ConnectionStrings__governance'] = connection
                env['G2_SEM_PG_CONNECTION'] = connection
                run(['dotnet', 'build', 'backend/tests/OntologyPlatform.SemanticTests', '--no-restore'])
                run(['dotnet', 'tool', 'restore'])
                for module in ['backend/src/Modules/Governance/OntologyPlatform.Modules.Governance', 'backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology']:
                    run(['dotnet', 'tool', 'run', 'dotnet-ef', 'database', 'update', '--project', module, '--startup-project', module, '--no-build'])
            command = ['dotnet', 'test', '--project', 'backend/tests/OntologyPlatform.SemanticTests', '--no-restore']
            if test_filter:
                command += ['--', '--filter', test_filter]
            result = run(command, required=False)
            code = result.returncode
            # Source/query logs are not collected; only bounded count/cleanup query evidence.
            query = 'SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }'
            with opener.open(urllib.request.Request(origin + '/validation/query?query=' + urllib.parse.quote(query), headers={'Accept': 'application/sparql-results+json'}), timeout=2) as response:
                count = json.loads(response.read())['results']['bindings'][0]['count']['value']
            records.append(dict(check='all temporary graph triples removed', count=int(count), status='PASS' if count == '0' else 'FAIL'))
            if count != '0':
                code = 1
        except Exception as error:
            code = 1
            records.append(dict(status='FAIL', category=type(error).__name__))
            raise
        finally:
            run(['docker', 'rm', '--force', name], required=False)
            if postgres:
                run(['docker', 'rm', '--force', name + '-pg'], required=False)
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / (label + '.json')).write_text(json.dumps(dict(exitCode=code, records=records), ensure_ascii=False, indent=2) + '\n')
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter')
    parser.add_argument('--label', default='semantic-roundtrip')
    parser.add_argument('--postgres', action='store_true')
    args = parser.parse_args()
    raise SystemExit(main(args.filter, args.postgres, args.label))
