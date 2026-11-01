#!/usr/bin/env python3
"""G4-M1恢复任务私有输入及阶段消费者；不会自动拉取镜像或启动容器。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M1-RECOVERY-001'
RUN = 'recovery-20261101-01'
PRIVATE = ROOT / '.tools/security/g4-m1-recovery-001-20261101-01'
ARTIFACTS = ROOT / 'artifacts/g4-m1-recovery-001'


def write_private(path, value):
    """独占0600写入；已有凭证绝不覆盖。"""
    data = json.dumps(value, indent=2) if isinstance(value, dict) else value
    with open(path, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        stream.write(data)


def environment():
    """仅输出无秘密的精确Compose输入；沿用既有依赖的只读位置。"""
    return dict(os.environ, G4_RUN_ID=RUN, G4_PRIVATE_DIR=str(PRIVATE),
        G4_PG_TEST_OUTPUT=str(ARTIFACTS/'pg-tests'), G4_API_OUTPUT=str(ARTIFACTS/'api'),
        G4_HOST_UID=str(os.getuid()), G4_HOST_GID=str(os.getgid()), G4_ROOT=str(ROOT),
        G4_SHARED_WEB_MODULES=str((ROOT/'apps/web/node_modules').resolve()),
        G4_SHARED_ROOT_MODULES=str((ROOT/'node_modules').resolve()), NEXT_TELEMETRY_DISABLED='1')


def compose():
    """只返回固定本任务Compose入口；调用者明确选择阶段。"""
    return ['docker', '--context', 'desktop-linux', 'compose', '-f',
        str(ROOT/'experiments/g4-m1/compose.m1.yaml'), '-f', str(ROOT/'experiments/g4-m1/compose.runtime.yaml')]


def validate_runtime(path):
    """私有输入限定准确当前树和任务，不接受任意配置或历史身份。"""
    if path.absolute() != PRIVATE/'runtime.json' or path.is_symlink():
        raise ValueError('EXACT_RUNTIME_REQUIRED')
    value = json.loads(path.read_text())
    if value['taskId'] != TASK or value['runId'] != RUN or value['publicOrigin'] != 'http://localhost:15100':
        raise ValueError('TASK_BINDING_REQUIRED')
    return value


def main():
    """分离私有准备、静态配置、已准入身份引导与API配置写入。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', type=Path, required=True)
    parser.add_argument('--mode', required=True, choices=('prepare', 'config', 'bootstrap', 'configure-api', 'snapshot'))
    args = parser.parse_args()
    if args.runtime_file.absolute() != PRIVATE/'runtime.json':
        raise ValueError('EXACT_RUNTIME_REQUIRED')
    if args.mode == 'prepare':
        if PRIVATE.is_symlink() or not PRIVATE.is_dir() or PRIVATE.stat().st_mode & 0o077:
            raise ValueError('PRIVATE_BOUNDARY_REQUIRED')
        for name in ('platform-password', 'keycloak-password'):
            write_private(PRIVATE/name, secrets.token_urlsafe(40))
        (PRIVATE/'api').mkdir(mode=0o700)
        with open(PRIVATE/'api/g4-key', 'xb') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(secrets.token_bytes(32))
        shutil.copyfile(PRIVATE/'ca.crt', PRIVATE/'api/ca.crt')
        os.chmod(PRIVATE/'api/ca.crt', 0o600)
        value = dict(taskId=TASK,runId=RUN,publicOrigin='http://localhost:15100',realmFile=str(PRIVATE/'realm.json'),
            sourceSecretFile=str(PRIVATE/'reader-password'),scope=dict(organizationId='org-demo',siteIds=['site-a']),
            browserChannel='msedge',scenario='baseline',certificatePath=str(PRIVATE/'api/keyring.pfx'),
            certificatePassword=secrets.token_urlsafe(40),healthKey=secrets.token_urlsafe(32))
        write_private(args.runtime_file, value)
        result = subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/acceptance/new-wave2-certificate.ps1'),
            '-RuntimeFile',str(args.runtime_file)],capture_output=True,text=True)
        if result.returncode: raise RuntimeError('PRIVATE_CERTIFICATE_FAILED')
        print(json.dumps(dict(taskId=TASK,status='PREPARED',containerExecution=False)))
        return
    runtime = validate_runtime(args.runtime_file)
    if args.mode == 'config':
        result = subprocess.run(compose()+['--profile','pg-test','config','--format','json'],env=environment(),capture_output=True,text=True)
        if result.returncode: raise RuntimeError('COMPOSE_CONFIG_FAILED')
        config=json.loads(result.stdout)
        for name,service in config['services'].items():
            if service['pull_policy']!='never' or service['platform']!='linux/arm64': raise ValueError('IMAGE_BOUNDARY')
        if sum(int(s['mem_limit']) for s in config['services'].values())>6*1024**3: raise ValueError('MEMORY_BOUNDARY')
        (ARTIFACTS/'runtime-compose-config.json').write_text(result.stdout)
        print(json.dumps(dict(status='CONFIG_ONLY',services=len(config['services']),containerExecution=False)))
    elif args.mode == 'bootstrap':
        env=environment();env['WAVE2_KEYCLOAK_ADMIN_PASSWORD']=(PRIVATE/'keycloak-password').read_text()
        result=subprocess.run(['python3',str(ROOT/'infra/security/bootstrap-keycloak.py'),'--profile','g2',
            '--keycloak-origin','http://localhost:15180','--public-origin',runtime['publicOrigin'],
            '--runtime-output',runtime['realmFile']],env=env,capture_output=True,text=True)
        (ARTIFACTS/'keycloak-bootstrap.txt').write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError('BOOTSTRAP_FAILED')
        print(json.dumps(dict(status='SYNTHETIC_REALM_CREATED',exitCode=result.returncode)))
    elif args.mode == 'configure-api':
        realm=json.loads(Path(runtime['realmFile']).read_text())
        if not realm['authority'].startswith('http://localhost:15180/realms/g2-'): raise ValueError('ISSUER_BOUNDARY')
        platform_password=(PRIVATE/'platform-password').read_text()
        config={'ConnectionStrings':{'governance':'Host=platform-pg;Database=platform;Username=platform;Password='+platform_password},
          'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],
          'PublicOrigin':runtime['publicOrigin'],'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx',
          'CertificatePassword':runtime['certificatePassword'],'HealthKey':runtime['healthKey']},
          'Web':{'Origin':'http://127.0.0.1:15300'},'G2':{'Enabled':False},
          'G4':{'Enabled':True,'ApplyMigrations':True,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/ca.crt'},
          'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},'Logging':{'LogLevel':{'Default':'Warning'}}}
        write_private(PRIVATE/'api/appsettings.json',config)
        print(json.dumps(dict(status='API_CONFIGURED',secretOutput='NONE')))
    elif args.mode == 'snapshot':
        ids=subprocess.check_output(['docker','--context','desktop-linux','ps','-aq','--filter','label=ontology.task-id='+TASK],text=True).split()
        data=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect',*ids],text=True)) if ids else []
        records=[]
        for item in data:
            if item['Config']['Labels'].get('ontology.task-id')!=TASK: raise ValueError('OWNERSHIP')
            records.append({k:item[k] for k in ('Id','Name','Image','State','HostConfig','Mounts','NetworkSettings')})
        (ARTIFACTS/'runtime-resources.json').write_text(json.dumps(records,indent=2)+'\n')
        print(json.dumps(dict(status='SNAPSHOT_ONLY',containers=len(records))))


if __name__ == '__main__':
    try: main()
    except Exception as failure:
        print(json.dumps(dict(status='FAILED',category=type(failure).__name__,details='SUPPRESSED')),file=sys.stderr)
        sys.exit(1)
