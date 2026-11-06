#!/usr/bin/env python3
"""本任务独立短烟测：真实OIDC/UI/只读PG探测与CSRF拒绝，绝不复用旧runtime。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid

TASK='G4-ENG-WORKFLOW-001'
SERVICES=('pg-source','platform-pg','keycloak-test','api','web')
CONTEXT='desktop-linux'
IMAGES={
    'pg-source':'postgres@sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437',
    'platform-pg':'postgres@sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437',
    'keycloak-test':'quay.io/keycloak/keycloak@sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4',
    'api':'mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55',
    'web':'node@sha256:a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f'}
WEB_HELPER="""import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=process.env.G4_ROOT;
if(process.env.WORKFLOW_TASK!=='G4-ENG-WORKFLOW-001'||!/^wf-[0-9a-f]{12}$/.test(process.env.G4_RUN_ID))process.exit(2);
const server=net.createServer(client=>{
 const remote=net.connect({host:'keycloak-test',port:8080});
 const close=()=>{client.destroy();remote.destroy();};
 for(const socket of [client,remote]){socket.setTimeout(30000,close);socket.on('error',close);}
 client.pipe(remote);remote.pipe(client);
});
server.maxConnections=64;server.listen(15180,'127.0.0.1');
const dir=path.join(root,'apps/web');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'.next/required-server-files.json'),'utf8'));
process.env.__NEXT_PRIVATE_STANDALONE_CONFIG=JSON.stringify(manifest.config);
process.chdir(dir);
const require=createRequire(path.join(dir,'package.json'));
await require('next/dist/server/lib/start-server').startServer({dir,hostname:'0.0.0.0',port:15300,isDev:false,allowRetry:false,keepAliveTimeout:5000});
"""


def require(condition, code):
    if not condition: raise ValueError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def boundary(path, root, exists=False):
    path=Path(os.path.abspath(path));root=Path(root).resolve()
    require(path.is_relative_to(root),'PATH_OUTSIDE_TASK')
    require(not any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(root)),'LINKED_PATH')
    if exists: require(path.is_file(),'REQUIRED_FILE_MISSING: '+str(path.relative_to(root)))
    return path


def private_write(path, value):
    data=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream: stream.write(data)


def command(args, *, cwd, env=None, timeout=60):
    """捕获诊断但不回显可能含私有配置的原始输出。"""
    proc=subprocess.run(args,cwd=cwd,env=env,capture_output=True,timeout=timeout)
    require(proc.returncode==0,'COMMAND_FAILED: '+Path(args[0]).name+' exit='+str(proc.returncode))
    return proc.stdout


def docker(root, *args, timeout=60):
    return command(['docker','--context',CONTEXT,*args],cwd=root,timeout=timeout)


def engine(root):
    info=json.loads(docker(root,'info','--format','{{json .}}'))
    require(info['OSType']=='linux' and info['Architecture']=='aarch64','DOCKER_PLATFORM')
    return {'id':info['ID'],'version':info['ServerVersion'],'context':CONTEXT}


def validate_topology(runtime, rows, current_engine):
    """API重建、旧Web网络身份、他人容器、预算漂移均先拒绝。"""
    require(runtime.get('taskId')==TASK and re.fullmatch('wf-[0-9a-f]{12}',runtime.get('runId','')),'RUNTIME_IDENTITY')
    require(runtime['engine']==current_engine,'ENGINE_DRIFT')
    require(set(rows)==set(SERVICES) and set(runtime['containerIds'])==set(SERVICES),'SERVICE_SET')
    total=0
    for service,row in rows.items():
        require(row['Id']==runtime['containerIds'][service] and re.fullmatch('[0-9a-f]{64}',row['Id']),'CONTAINER_REPLACED')
        labels=row['Config']['Labels']
        require(labels.get('ontology.task-id')==TASK and labels.get('ontology.run-id')==runtime['runId'],'RESOURCE_OWNER')
        require(labels.get('com.docker.compose.service')==service,'SERVICE_OWNER')
        require(row['Config']['Image']==IMAGES[service] and row['Image']==runtime['imageIds'][service],'IMAGE_DRIFT')
        require(row['State']['Running'] and not row['State'].get('Paused'),'SERVICE_NOT_RUNNING')
        memory=row['HostConfig']['Memory'];require(0<memory<=1024**3,'RESOURCE_MEMORY');total+=memory
    require(total<=6*1024**3,'RESOURCE_BUDGET')
    require(rows['web']['HostConfig']['NetworkMode']=='container:'+rows['api']['Id'],'STALE_WEB_NETWORK')
    return True


def snapshot(root, runtime):
    rows={service:json.loads(docker(root,'inspect',ident))[0] for service,ident in runtime['containerIds'].items()}
    validate_topology(runtime,rows,engine(root))
    return {service:{'id':row['Id'],'imageId':row['Image'],'networkMode':row['HostConfig']['NetworkMode'],
                     'startedAt':row['State']['StartedAt']} for service,row in rows.items()}


def wait_http(url, headers=None, timeout=90):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with opener.open(urllib.request.Request(url,headers=headers or {}),timeout=3) as response:
                if response.status==200: return
        except (OSError,ValueError): pass
        time.sleep(.5)
    raise ValueError('LOCAL_HTTP_READINESS_TIMEOUT')


def fixture(root, private, run):
    """每Run独立无业务行fixture；不触碰编译目录或系统信任。"""
    for name in ('postgres-password','reader-password','platform-password','keycloak-password'):
        private_write(private/name,secrets.token_urlsafe(36))
    openssl=shutil.which('openssl');require(openssl is not None,'OPENSSL_MISSING')
    command([openssl,'req','-x509','-newkey','rsa:2048','-noenc','-sha256','-days','2','-subj','/CN=Workflow Synthetic CA','-addext','basicConstraints=critical,CA:TRUE','-keyout','ca.key','-out','ca.crt'],cwd=private)
    command([openssl,'req','-new','-newkey','rsa:2048','-noenc','-subj','/CN=pg-source','-keyout','server.key','-out','server.csr'],cwd=private)
    private_write(private/'server.ext','basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:pg-source\n')
    command([openssl,'x509','-req','-in','server.csr','-CA','ca.crt','-CAkey','ca.key','-set_serial','0x'+secrets.token_hex(16),'-days','2','-sha256','-extfile','server.ext','-out','server.crt'],cwd=private)
    password=(private/'reader-password').read_text()
    private_write(private/'init.sql',"""\\set ON_ERROR_STOP on
CREATE ROLE fixture_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD '%s';
REVOKE CREATE, TEMPORARY ON DATABASE fixture FROM PUBLIC;
GRANT CONNECT ON DATABASE fixture TO fixture_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA production AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA production FROM PUBLIC;
CREATE TABLE production.heat_event(id bigint PRIMARY KEY, tap_temp numeric(8,2));
GRANT USAGE ON SCHEMA production TO fixture_reader;
GRANT SELECT ON production.heat_event TO fixture_reader;
ALTER ROLE fixture_reader IN DATABASE fixture SET default_transaction_read_only = on;
""" % password)
    private_write(private/'pg_hba.conf','local all postgres trust\nlocal all all reject\nhostnossl all all all reject\nhostssl fixture fixture_reader all scram-sha-256\nhostssl all all all reject\n')
    api=private/'api';api.mkdir(mode=0o700)
    (api/'g4-key').write_bytes(secrets.token_bytes(32));(api/'g4-key').chmod(0o600)
    shutil.copyfile(private/'ca.crt',api/'ca.crt')
    runtime={'taskId':TASK,'runId':run,'worktree':str(root),'publicOrigin':'http://localhost:15100',
             'realmFile':str(private/'realm.json'),'sourceSecretFile':str(private/'reader-password'),
             'certificatePath':str(api/'keyring.pfx'),'certificatePassword':secrets.token_urlsafe(40),'healthKey':secrets.token_urlsafe(32)}
    private_write(private/'certificate-input.json',runtime)
    command(['pwsh','-NoProfile','-File',str(root/'scripts/acceptance/new-wave2-certificate.ps1'),'-RuntimeFile',str(private/'certificate-input.json')],cwd=root)
    for name in ('ca.key','server.csr','server.ext'): (private/name).unlink()
    for path in private.rglob('*'):
        if path.is_file():path.chmod(0o600)
    return runtime


def recipe(root, private, run, output):
    """从固定已审配方派生当前任务五服务；不改历史源、不继承历史身份。"""
    env=dict(os.environ,G4_RUN_ID=run,G4_PRIVATE_DIR=str(private),G4_ROOT=str(root),
        G4_HOST_UID=str(os.getuid()),G4_HOST_GID=str(os.getgid()),G4_HELPERS=str(private),
        G4_SHARED_WEB_MODULES=str(root/'apps/web/node_modules'),G4_SHARED_ROOT_MODULES=str(root/'node_modules'),
        G4_API_OUTPUT=str(root/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'),
        G4_PG_TEST_OUTPUT=str(root/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'))
    source=root/'experiments/g4-m1-main-integration/compose.m1.yaml'
    value=json.loads(command(['docker','--context',CONTEXT,'compose','-f',str(source),'config','--format','json'],cwd=root,env=env))
    value['name']='ontology-workflow-'+run
    value['services']={name:value['services'][name] for name in SERVICES}
    for service,item in value['services'].items():
        require(item['image']==IMAGES[service] and item['pull_policy']=='never','RECIPE_IMAGE')
        item['labels']['ontology.task-id']=TASK
        item['labels']['ontology.run-id']=run
        item['labels']['ontology.synthetic']='true'
        item.pop('profiles',None)
    value['services']['web']['environment']['WORKFLOW_TASK']=TASK
    for collection in ('volumes','networks'):
        for name,item in value[collection].items():
            item['name']='ontology-workflow-'+run+'_'+name
            item.setdefault('labels',{})['ontology.task-id']=TASK
            item['labels']['ontology.run-id']=run
    private_write(private/'loopback-proxy.mjs',WEB_HELPER)
    private_write(output,value)
    return value


def volume_observation(root, runtime):
    """实测本任务三个数据卷用量；达到3GiB立即停止，不声称硬配额。"""
    sizes={}
    for service,path in (('pg-source','/var/lib/postgresql'),('platform-pg','/var/lib/postgresql'),('keycloak-test','/opt/keycloak/data')):
        raw=docker(root,'exec',runtime['containerIds'][service],'du','-sk',path,timeout=20).decode()
        sizes[service]=int(raw.split()[0])*1024
    require(sum(sizes.values())<3*1024**3,'VOLUME_STOP_THRESHOLD')
    return sizes


def stop_owned(root, runtime):
    """只停止精确本Run容器；保留持久资源给审查后的白名单收尾。"""
    stopped=[]
    require(runtime['engine']==engine(root),'ENGINE_DRIFT_DURING_STOP')
    for service,ident in runtime['containerIds'].items():
        row=json.loads(docker(root,'inspect',ident))[0]
        require(row['Id']==ident and row['Config']['Labels'].get('ontology.task-id')==TASK and row['Config']['Labels'].get('ontology.run-id')==runtime['runId'],'STOP_OWNER')
        docker(root,'stop','--time','10',ident,timeout=20)
        after=json.loads(docker(root,'inspect',ident))[0]
        require(not after['State']['Running'],'STOP_POSTCONDITION')
        stopped.append(ident)
    return stopped


def smoke(root, task, *, node=None):
    """新环境运行一次短真实路径；失败保留证据，finally只停本Run资源。"""
    root=Path(root).resolve();require(task==TASK,'TASK_NOT_AUTHORIZED')
    for path in ('backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll','apps/web/.next/required-server-files.json','apps/web/node_modules/@playwright/test/package.json'):
        require((root/path).is_file(),'SMOKE_BUILD_INPUT_MISSING: '+path)
    node=node or shutil.which('node');require(node is not None,'NODE_MISSING')
    for port in (15100,15180,15432):
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1',port))
            except OSError: raise ValueError('SMOKE_PORT_IN_USE: '+str(port)) from None
    run='wf-'+uuid.uuid4().hex[:12]
    private=boundary(root/'.tools/security'/task.lower()/run,root)
    private.parent.mkdir(parents=True,exist_ok=True,mode=0o700);private.mkdir(mode=0o700)
    evidence=boundary(root/'artifacts/workflow'/task/'smoke'/run,root)
    evidence.mkdir(parents=True,mode=0o700)
    runtime=fixture(root,private,run)
    runtime.update(engine=engine(root),containerIds={},imageIds={})
    for service,image in IMAGES.items():
        item=json.loads(docker(root,'image','inspect',image))[0]
        require(item['Architecture']=='arm64' and image in item.get('RepoDigests',[]),'IMAGE_ADMISSION')
        runtime['imageIds'][service]=item['Id']
    compose=private/'compose.json';config=recipe(root,private,run,compose)
    prefix=['docker','--context',CONTEXT,'compose','-f',str(compose)]
    result={'taskId':TASK,'runId':run,'status':'FAIL','productExecution':False,'recipeSha256':digest(compose.read_bytes()),'resourceManifest':str(evidence/'resources.json')}
    start=time.monotonic()
    try:
        command([*prefix,'create','--pull','never',*SERVICES],cwd=root,timeout=120)
        for service in SERVICES:
            ident=command([*prefix,'ps','--all','--quiet',service],cwd=root).decode().strip()
            require(re.fullmatch('[0-9a-f]{64}',ident),'CREATED_ID_MISSING')
            runtime['containerIds'][service]=ident
        private_write(evidence/'resources.json',{'taskId':TASK,'runId':run,'engine':runtime['engine'],'containerIds':runtime['containerIds'],'volumes':{k:v['name'] for k,v in config['volumes'].items()},'decision':'KEEP_UNTIL_REVIEWED_CLOSEOUT','privateRuntime':str(private/'runtime.json')})
        command([*prefix,'start',*SERVICES],cwd=root,timeout=120)
        wait_http('http://localhost:15180/realms/master/.well-known/openid-configuration',timeout=180)
        env=dict(os.environ,WAVE2_KEYCLOAK_ADMIN_PASSWORD=(private/'keycloak-password').read_text())
        command(['python3','-B',str(root/'infra/security/bootstrap-keycloak.py'),'--profile','g2','--keycloak-origin','http://localhost:15180','--public-origin',runtime['publicOrigin'],'--runtime-output',runtime['realmFile']],cwd=root,env=env,timeout=60)
        realm=json.loads(Path(runtime['realmFile']).read_text())
        api={'ConnectionStrings':{'governance':'Host=platform-pg;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()},
             'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],'PublicOrigin':runtime['publicOrigin'],'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx','CertificatePassword':runtime['certificatePassword'],'HealthKey':runtime['healthKey']},
             'Web':{'Origin':'http://127.0.0.1:15300'},'G2':{'Enabled':False},
             'G4':{'Enabled':True,'ApplyMigrations':True,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/ca.crt','AllowEmptyPublicSchema':True},
             'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},'Logging':{'LogLevel':{'Default':'Warning'}}}
        private_write(private/'api/appsettings.json',api)
        wait_http(runtime['publicOrigin']+'/health/live',headers={'X-Health-Key':runtime['healthKey']},timeout=120)
        runtime['beforeTopology']=snapshot(root,runtime)
        result['volumeBytesBefore']=volume_observation(root,runtime)
        private_write(private/'runtime.json',runtime)
        browser_command=[node,str(root/'scripts/maintenance/workflow-smoke.mjs'),str(private/'runtime.json')]
        require(os.uname().sysname=='Darwin' and Path('/usr/bin/sandbox-exec').is_file(),'OFFLINE_OS_BOUNDARY_UNAVAILABLE')
        browser_command=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))',*browser_command]
        process=subprocess.run(browser_command,cwd=root,capture_output=True,timeout=180)
        private_write(evidence/'browser.json',json.loads(process.stdout))
        result['browserExitCode']=process.returncode
        report=json.loads(process.stdout);require(process.returncode==0 and report['status']=='PASS' and report['tests']==2,'SMOKE_ASSERTIONS')
        after=snapshot(root,runtime);require(after==runtime['beforeTopology'],'TOPOLOGY_CHANGED_DURING_SMOKE')
        result.update(status='PASS',productExecution=True,checks=report,topology=after,volumeBytesAfter=volume_observation(root,runtime))
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    finally:
        # create/start部分失败也只按当前项目和服务逐项找回准确ID，不漏掉自身已创建实例。
        for service in SERVICES:
            if service in runtime['containerIds']: continue
            try:
                ident=command([*prefix,'ps','--all','--quiet',service],cwd=root).decode().strip()
                if re.fullmatch('[0-9a-f]{64}',ident):
                    row=json.loads(docker(root,'inspect',ident))[0]
                    require(row['Config']['Labels'].get('ontology.task-id')==TASK and row['Config']['Labels'].get('ontology.run-id')==run,'PARTIAL_CREATE_OWNER')
                    runtime['containerIds'][service]=ident
            except (ValueError,OSError,subprocess.SubprocessError):
                result['resourceRecovery']='NOT_VERIFIED'
        result['containerIds']=runtime['containerIds']
        if runtime['containerIds']:
            try: result['stoppedContainerIds']=stop_owned(root,runtime)
            except (ValueError,OSError,subprocess.SubprocessError): result.update(status='FAIL',cleanup='STOP_FAILED_KEEP_EXACT_MANIFEST')
        result['elapsedSeconds']=time.monotonic()-start
        private_write(evidence/'receipt.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--task',required=True);parser.add_argument('--node')
    args=parser.parse_args()
    try:
        result=smoke(args.root,args.task,node=args.node);print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 2)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}));raise SystemExit(2)
