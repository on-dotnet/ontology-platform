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
import threading

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


def lifecycle_identity(runtime, profile):
    """Project only non-secret ownership; legacy private runtime files stay untouched."""
    value=runtime.get('resourceLifecycle')
    if value is None:
        value={'taskId':os.environ.get('PLATFORM_TASK_ID','DEVELOPMENT'), 'runId':runtime['volumePrefix']}
    task,run_id=value.get('taskId'),value.get('runId')
    prefix=runtime['volumePrefix']
    if not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',x) for x in (task,run_id)) or not re.fullmatch(r'(?:wave2|g2|g3-m1|g3-m2|g3-m3|g3-m4)-[a-z0-9-]{1,40}',prefix):
        raise ValueError('Invalid lifecycle identity')
    services=['postgres','keycloak','grafana','loki','tempo','prometheus','alloy']
    volumes=['postgres','grafana','loki','tempo','prometheus','alloy']
    if profile=='g2':
        services+=['fuseki','rustfs'];volumes+=['fuseki','rustfs']
    return dict(schemaVersion=1,project='on-dotnet/ontology-platform',taskId=task,runId=run_id,
                volumePrefix=prefix,profile=profile,expectedServices=services,
                expectedVolumes=[prefix+'-'+name+'-data' for name in volumes])


def lifecycle_write(meta, state, observations, **fields):
    """Atomically persist allowlisted metadata outside the private security runtime."""
    directory=ROOT
    for segment in ('artifacts','resource-lifecycle'):
        directory=directory/segment
        if directory.is_symlink():raise ValueError('Linked lifecycle artifact directory refused')
        directory.mkdir(exist_ok=True)
    path=directory/(meta['runId']+'.json')
    if path.is_symlink():raise ValueError('Linked lifecycle manifest refused')
    if path.exists():
        previous=json.loads(path.read_text())
        if any(previous.get(k)!=meta[k] for k in ('taskId','runId','volumePrefix')):
            raise ValueError('Lifecycle identity collision')
    value=dict(meta,state=state,observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),observations=observations,**fields)
    partial=directory/(meta['runId']+'.partial-'+secrets.token_hex(6))
    try:
        with partial.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2);stream.write('\n')
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def lifecycle_snapshot(meta):
    """Read only exact task/run labelled containers and known named volume metadata."""
    def query(args):
        return subprocess.run(['docker']+args,capture_output=True,text=True,timeout=5)
    try:
        listed=query(['container','ls','--all','--no-trunc','--filter','label=io.ontology-platform.task-id='+meta['taskId'],
                      '--filter','label=io.ontology-platform.run-id='+meta['runId'],'--format','{{.ID}}'])
        if listed.returncode:raise ValueError('Container metadata unavailable')
        containers=[]
        fmt='{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},"State":{{json .State.Status}},"TaskId":{{json (index .Config.Labels "io.ontology-platform.task-id")}},"RunId":{{json (index .Config.Labels "io.ontology-platform.run-id")}},"Service":{{json (index .Config.Labels "io.ontology-platform.service")}},"Mounts":{{json .Mounts}}}'
        for ident in listed.stdout.splitlines():
            if not re.fullmatch('[0-9a-f]{64}',ident):raise ValueError('Invalid container identity')
            result=query(['container','inspect','--format',fmt,ident])
            if result.returncode:raise ValueError('Container metadata unavailable')
            value=json.loads(result.stdout)
            if value['Id']!=ident or value['TaskId']!=meta['taskId'] or value['RunId']!=meta['runId'] or value['Service'] not in meta['expectedServices']:
                raise ValueError('Container ownership mismatch')
            value['Mounts']=[{k:mount[k] for k in ('Type','Name','Destination','RW') if k in mount} for mount in value['Mounts']]
            containers.append(value)
        volumes=[]
        fmt='{"Name":{{json .Name}},"Driver":{{json .Driver}},"CreatedAt":{{json .CreatedAt}},"Labels":{{json .Labels}}}'
        for name in meta['expectedVolumes']:
            result=query(['volume','inspect','--format',fmt,name])
            if result.returncode:
                # Only a specific absent-volume response is an observed absence.
                if result.returncode==1 and result.stderr.strip()=='Error response from daemon: get '+name+': no such volume':
                    volumes.append(dict(Name=name,status='ABSENT'));continue
                raise ValueError('Volume metadata unavailable')
            value=json.loads(result.stdout)
            if value['Name']!=name:raise ValueError('Volume identity mismatch')
            # Labels may contain user-supplied data: persist only ownership fields.
            labels=value.get('Labels') or {}
            value['Labels']={key:labels[key] for key in ('io.ontology-platform.task-id','io.ontology-platform.run-id','io.ontology-platform.service') if key in labels}
            value['references']=[c['Id'] for c in containers if any(m.get('Type')=='volume' and m.get('Name')==name for m in c['Mounts'])]
            volumes.append(value)
        return dict(status='OBSERVED',observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),containers=containers,volumes=volumes)
    except (OSError,subprocess.TimeoutExpired,ValueError,KeyError,TypeError):
        return dict(status='BLOCKED',reason='Exact Docker ownership metadata unavailable; no resource completion or deletion inferred',containers=[],volumes=[])


def prepare(profile="wave2", resource_prefix=None, task_id=None, run_id=None):
    """Prepare one new volume prefix, random passwords and shared encrypted PFX."""
    directory = ROOT / '.tools/security' / ((resource_prefix or profile) + '-' + secrets.token_hex(6))
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
    runtime['resourceLifecycle']={'taskId':task_id or os.environ.get('PLATFORM_TASK_ID','DEVELOPMENT'), 'runId':run_id or directory.name}
    meta=lifecycle_identity(runtime,profile)
    lifecycle_write(meta,'PREPARED',[])
    path = directory / 'runtime.json'
    private_json(path, runtime)
    subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT / 'scripts/acceptance/new-wave2-certificate.ps1'),
                    '-RuntimeFile', str(path)], check=True)
    print(str(path.relative_to(ROOT)))


def secret_values(value):
    """Enumerate only secret-bearing values already generated for this run."""
    if isinstance(value, dict):
        for key, child in value.items():
            if any(word in key.lower() for word in ('password', 'secret', 'healthkey', 'accesskey')) and isinstance(child, str):
                yield child
            yield from secret_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from secret_values(child)


def sanitize(line, sensitive):
    """Remove credentials and URL queries before any observable persistence."""
    if re.search(r'''(?i)["']?(password|client_secret|access_token|id_token|refresh_token|authorization|set-cookie|cookie|token|state|nonce|code|rustfs[_-]?access[_-]?key)["']?\s*[:=]''', line):
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
    meta=lifecycle_identity(runtime,profile)
    observations=[]
    lifecycle_write(meta,'STARTING',observations)
    env = os.environ.copy()
    env.update({'ResourceLifecycle__TaskId':meta['taskId'],'ResourceLifecycle__RunId':meta['runId']})
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
        try:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except OSError:
            lifecycle_write(meta,'START_FAILED',observations,reason='AppHost process could not start')
            raise
        stop=threading.Event()
        def record_snapshot():
            value=lifecycle_snapshot(meta)
            # Keep exact observed identities while bounding repetitive local evidence.
            meta['observedContainerIds']=sorted(set(meta.get('observedContainerIds',[]))|{c['Id'] for c in value['containers']})
            meta['observedVolumeNames']=sorted(set(meta.get('observedVolumeNames',[]))|{v['Name'] for v in value['volumes'] if v.get('status')!='ABSENT'})
            observations.append(value)
            del observations[:-64]
        def observe():
            while not stop.is_set():
                record_snapshot()
                lifecycle_write(meta,'RUNNING',observations)
                stop.wait(5)
        observer=threading.Thread(target=observe,name='resource-lifecycle',daemon=True)
        observer.start()
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
        except BaseException:
            process.terminate()
            result = process.wait(timeout=40)
            raise
        finally:
            stop.set()
            observer.join(timeout=240)
            if observer.is_alive():raise RuntimeError('Lifecycle observer did not finish')
            record_snapshot()
            lifecycle_write(meta,'EXITED',observations,exitCode=process.returncode if hasattr(process,'returncode') else result)
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
