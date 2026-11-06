#!/usr/bin/env python3
"""本任务独立短烟测：真实OIDC/UI/只读PG探测与CSRF拒绝，绝不复用旧runtime。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import socket
import socketserver
import select
import threading
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


RELAY_NODE=r"""const net=require('node:net');
const port=Number(process.argv[1]),token=process.argv[2];
if(![15100,15180].includes(port)||!/^wf-relay-wf-[a-f0-9]{12}-[a-f0-9]{32}$/.test(token))process.exit(2);
process.stderr.write('PID '+process.pid+'\n');
const peer=port===15100?['127.0.0.1',15100]:['keycloak-test',8080];
const socket=net.connect({host:peer[0],port:peer[1]});
const finish=()=>{socket.destroy();process.exit(0);};
const timer=setTimeout(finish,45000);timer.unref();
socket.setTimeout(30000,finish);socket.on('error',finish);
process.stdout.on('error',finish);process.stdin.on('error',finish);
process.stdin.on('end',finish);socket.on('end',()=>{process.stdout.end();});
process.stdin.pipe(socket);socket.pipe(process.stdout);
"""
RELAY_STOP_NODE=r"""const fs=require('node:fs');
const pid=Number(process.argv[1]),token=process.argv[2];
if(!Number.isInteger(pid)||pid<1||!/^wf-relay-wf-[a-f0-9]{12}-[a-f0-9]{32}$/.test(token))process.exit(2);
function owned(){try{const a=fs.readFileSync('/proc/'+pid+'/cmdline').toString().split('\0');return a.includes(token)&&(a[0]==='node'||a[0].endsWith('/node'));}catch(e){if(e.code==='ENOENT')return false;throw e;}}
if(owned())process.kill(pid,'SIGTERM');
const deadline=Date.now()+2000;
const timer=setInterval(()=>{if(!owned()){clearInterval(timer);process.exit(0);}if(Date.now()>deadline){clearInterval(timer);process.exit(3);}},50);
"""


def relay_command(runtime, port, token):
    """只允许当前准确Web实例执行两个固定内部目标，不接受地址/脚本输入。"""
    require(runtime.get('taskId')==TASK and re.fullmatch('wf-[a-f0-9]{12}',runtime.get('runId','')),'RELAY_IDENTITY')
    require(port in (15100,15180),'RELAY_TARGET')
    require(re.fullmatch('wf-relay-'+runtime['runId']+'-[a-f0-9]{32}',token),'RELAY_TOKEN')
    ident=runtime['containerIds']['web'];require(re.fullmatch('[a-f0-9]{64}',ident),'RELAY_CONTAINER')
    return ['docker','--context',CONTEXT,'exec','-i',ident,'node','-e',RELAY_NODE,str(port),token]


class HostRelay:
    """内部网络专用stdio入口：仅loopback，两固定端口，16连接/45秒/总480秒。"""
    def __init__(self, root, runtime):
        self.root=root;self.runtime=runtime;self.servers=[];self.threads=[]
        self.stop=threading.Event();self.lock=threading.Lock();self.slots=threading.BoundedSemaphore(16)
        self.active={};self.failures=[];self.connections=0;self.timer=None

    def start(self):
        snapshot(self.root,self.runtime)
        owner=self
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=False
            daemon_threads=True
            block_on_close=False
            request_queue_size=32
            def handle_error(self, request, address):
                owner.failures.append('RELAY_HANDLER_FAILED')
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):owner.forward(self.request,self.server.server_address[1])
        try:
            for port in (15100,15180):
                server=Server(('127.0.0.1',port),Handler);self.servers.append(server)
                thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
                thread.start();self.threads.append(thread)
            self.timer=threading.Timer(480,self.expire);self.timer.daemon=True;self.timer.start()
            return self
        except Exception:
            self.close();raise

    def forward(self, client, port):
        if self.stop.is_set() or not self.slots.acquire(blocking=False):return
        process=None;pid=None;token='wf-relay-'+self.runtime['runId']+'-'+uuid.uuid4().hex
        try:
            process=subprocess.Popen(relay_command(self.runtime,port,token),cwd=self.root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0)
            client.settimeout(5)
            with self.lock:self.active[token]=(client,process);self.connections+=1
            ready,_,_=select.select([process.stderr],[],[],5)
            require(ready,'RELAY_PID_TIMEOUT')
            line=process.stderr.readline(80).decode();require(re.fullmatch(r'PID [1-9][0-9]*\n',line),'RELAY_PID')
            pid=int(line.split()[1]);deadline=time.monotonic()+45
            while not self.stop.is_set() and time.monotonic()<deadline:
                readable,_,_=select.select([client,process.stdout],[],[],.5)
                if client in readable:
                    data=client.recv(65536)
                    if not data:break
                    offset=0
                    while offset<len(data):
                        written=process.stdin.write(data[offset:]);require(written and written>0,'RELAY_PIPE_WRITE');offset+=written
                if process.stdout in readable:
                    data=os.read(process.stdout.fileno(),65536)
                    if not data:break
                    client.sendall(data)
        except (OSError,ValueError,subprocess.SubprocessError):
            # 单连接关闭/启动期拒绝只影响该连接，不打印流量或原始异常。
            pass
        finally:
            try:client.close()
            except OSError:pass
            if process:
                try:process.stdin.close()
                except OSError:pass
                if pid:
                    try:docker(self.root,'exec',self.runtime['containerIds']['web'],'node','-e',RELAY_STOP_NODE,str(pid),token,timeout=5)
                    except (OSError,ValueError,subprocess.SubprocessError):self.failures.append('RELAY_CHILD_RELEASE_NOT_VERIFIED')
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=2)
                for stream in (process.stdout,process.stderr):stream.close()
            with self.lock:self.active.pop(token,None)
            self.slots.release()

    def expire(self):
        self.failures.append('RELAY_LIFETIME_EXPIRED');self.close()

    def close(self):
        with self.lock:
            if self.stop.is_set():return {'connections':self.connections,'active':len(self.active),'failures':list(self.failures)}
            self.stop.set();active=list(self.active.values())
        if self.timer:self.timer.cancel()
        for server in self.servers:server.shutdown();server.server_close()
        for client,_ in active:
            try:client.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            with self.lock:
                if not self.active:break
            time.sleep(.05)
        with self.lock:
            if self.active:self.failures.append('RELAY_ACTIVE_AT_CLOSE')
        for thread in self.threads:thread.join(timeout=1)
        return {'connections':self.connections,'active':len(self.active),'failures':list(self.failures)}


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


def bounded_browser(args, root, timeout=180):
    """超时精确终止本次独立进程组，避免留下浏览器子进程。"""
    process=subprocess.Popen(args,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        stdout,_=process.communicate(timeout=timeout)
        return stdout,process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try: stdout,_=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);stdout,_=process.communicate(timeout=5)
        return stdout,124


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
    reader_password=(private/'reader-password').read_text()
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
""" % reader_password)
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
    for service,path in (('pg-source','/var/lib/postgresql'),('platform-pg','/var/lib/postgresql'),('keycloak-test','/opt/keycloak/data'),('api','/keyring')):
        raw=docker(root,'exec',runtime['containerIds'][service],'du','-sk',path,timeout=20).decode()
        sizes[service]=int(raw.split()[0])*1024
    require(sum(sizes.values())<3*1024**3,'VOLUME_STOP_THRESHOLD')
    return sizes


def resource_manifest(root, runtime, config, private, phase):
    """创建前写准确期望名称，随后逐项观察；不存在与不可观察均不冒充删除。"""
    result={'taskId':TASK,'runId':runtime['runId'],'engine':runtime['engine'],'phase':phase,
            'containerIds':dict(runtime['containerIds']),'volumes':{},'networks':{},
            'decision':'KEEP_UNTIL_REVIEWED_CLOSEOUT','privateRuntime':str(private/'runtime.json'),
            'recipeSha256':digest((private/'compose.json').read_bytes())}
    for category,kind in (('volumes','volume'),('networks','network')):
        for name,item in config[category].items():
            row={'expectedName':item['name'],'observation':'NOT_VERIFIED'}
            if phase!='PLANNED':
                try:
                    actual=json.loads(docker(root,kind,'inspect',item['name']))[0]
                    labels=actual.get('Labels',{})
                    require(labels.get('ontology.task-id')==TASK and labels.get('ontology.run-id')==runtime['runId'],'RESOURCE_OWNER')
                    row.update(observation='OBSERVED',identity=actual['Name'] if kind=='volume' else actual['Id'])
                except (ValueError,OSError,subprocess.SubprocessError):
                    row['reason']='EXACT_OBJECT_NOT_OBSERVABLE'
            result[category][name]=row
    return result


def replace_manifest(path, value):
    """同目录原子更新回执；PLANNED内容保留准确名称，不删除原始运行证据。"""
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.next')
    private_write(pending,value);os.replace(pending,path)


def stop_owned(root, runtime):
    """逐对象停止已验证本Run容器；一项失败不阻止其余安全项。"""
    result={'stopped':[],'failures':[]}
    for service,ident in runtime['containerIds'].items():
        try:
            require(runtime['engine']==engine(root),'ENGINE_DRIFT_DURING_STOP')
            row=json.loads(docker(root,'inspect',ident))[0]
            require(row['Id']==ident and row['Config']['Labels'].get('ontology.task-id')==TASK and row['Config']['Labels'].get('ontology.run-id')==runtime['runId'],'STOP_OWNER')
            docker(root,'stop','--time','10',ident,timeout=20)
            after=json.loads(docker(root,'inspect',ident))[0]
            require(not after['State']['Running'],'STOP_POSTCONDITION')
            result['stopped'].append(ident)
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            result['failures'].append({'service':service,'id':ident,'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
    return result


def build_input_key(root):
    """只绑定受Git管理的产品构建与配方输入；不绑定HEAD、Run或过程证据。"""
    root=Path(root).resolve()
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
    fixed={'global.json','NuGet.Config','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version','.npmrc'}
    selected=[]
    for relative in sorted(set(paths)-{''}):
        if not (relative.startswith(('backend/','apps/web/','experiments/g4-m1-main-integration/compose.')) or relative in fixed or relative.startswith('Directory.')):continue
        # 无Git ignore的隔离测试也排除生成目录；生成状态独立由outputs绑定。
        if any(part in ('bin','obj','node_modules','.next') for part in Path(relative).parts):continue
        path=boundary(root/relative,root)
        selected.append([relative,digest(path.read_bytes()) if path.is_file() else 'MISSING'])
    require(selected,'BUILD_INPUT_EMPTY')
    return digest(json.dumps(selected,separators=(',',':')).encode())


def build_outputs(root):
    """绑定API运行目录及Next运行产物；不纳入可变cache/trace和调试报告。"""
    root=Path(root).resolve();result={}
    trees=(root/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0',root/'apps/web/.next')
    require((trees[0]/'OntologyPlatform.Api.dll').is_file() and (trees[1]/'required-server-files.json').is_file(),'BUILD_OUTPUT_MISSING')
    for tree in trees:
        for path in sorted(tree.rglob('*')):
            relative=path.relative_to(tree)
            if relative.parts[0] in ('cache','diagnostics','types') or path.name in ('trace','trace-build') or path.suffix=='.pdb':continue
            boundary(path,root)
            if path.is_file():result[str(path.relative_to(root))]=digest(path.read_bytes())
    return result


def validate_build(root):
    """烟测前后复核本树真实构建回执，拒绝旧源码或产物混用。"""
    root=Path(root).resolve()
    path=boundary(root/'artifacts/workflow'/TASK/'build-receipt.json',root,exists=True)
    receipt=json.loads(path.read_text())
    require(receipt.get('status')=='PASS' and receipt.get('worktree')==str(root),'BUILD_RECEIPT_IDENTITY')
    require(receipt.get('inputKey')==build_input_key(root),'BUILD_INPUT_DRIFT')
    require(receipt.get('outputs')==build_outputs(root),'BUILD_OUTPUT_DRIFT')
    return {'inputKey':receipt['inputKey'],'receiptSha256':digest(path.read_bytes()),'outputKey':digest(json.dumps(receipt['outputs'],sort_keys=True).encode())}


def validate_image(item, reference):
    """已批准的内容寻址导入镜像可无RepoDigests；仍要求精确ID/平台。"""
    require(item.get('Architecture')=='arm64' and item.get('Os')=='linux' and
            item.get('Id')==reference.split('@')[1],'IMAGE_ADMISSION')


def smoke(root, task, *, node=None):
    """新环境运行一次短真实路径；失败保留证据，finally只停本Run资源。"""
    root=Path(root).resolve();require(task==TASK,'TASK_NOT_AUTHORIZED')
    build_binding=validate_build(root)
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
        validate_image(item,image)
        runtime['imageIds'][service]=item['Id']
    compose=private/'compose.json';config=recipe(root,private,run,compose)
    prefix=['docker','--context',CONTEXT,'compose','-f',str(compose)]
    result={'taskId':TASK,'runId':run,'status':'FAIL','productExecution':False,'recipeSha256':digest(compose.read_bytes()),'resourceManifest':str(evidence/'resources.json')}
    result['buildBinding']=build_binding
    private_write(evidence/'resources.json',resource_manifest(root,runtime,config,private,'PLANNED'))
    start=time.monotonic();relay=None
    try:
        command([*prefix,'create','--pull','never',*SERVICES],cwd=root,timeout=120)
        for service in SERVICES:
            ident=command([*prefix,'ps','--all','--quiet',service],cwd=root).decode().strip()
            require(re.fullmatch('[0-9a-f]{64}',ident),'CREATED_ID_MISSING')
            runtime['containerIds'][service]=ident
        replace_manifest(evidence/'resources.json',resource_manifest(root,runtime,config,private,'CREATED'))
        command([*prefix,'start',*SERVICES],cwd=root,timeout=120)
        relay=HostRelay(root,runtime).start()
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
        stdout,code=bounded_browser(browser_command,root)
        result['browserExitCode']=code
        report=json.loads(stdout) if stdout.strip() else {'status':'FAIL','reason':'BROWSER_TIMEOUT_OR_EMPTY','tests':0}
        private_write(evidence/'browser.json',report)
        require(code==0 and report['status']=='PASS' and report['tests']==2,'SMOKE_ASSERTIONS')
        after=snapshot(root,runtime);require(after==runtime['beforeTopology'],'TOPOLOGY_CHANGED_DURING_SMOKE')
        require(validate_build(root)==build_binding,'BUILD_CHANGED_DURING_SMOKE')
        runtime_key=digest(json.dumps({'engine':runtime['engine'],'images':runtime['imageIds'],'recipe':result['recipeSha256'],'topology':after},sort_keys=True).encode())
        result.update(status='PASS',productExecution=True,checks=report,topology=after,runtimeKey=runtime_key,volumeBytesAfter=volume_observation(root,runtime))
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    finally:
        if relay:
            result['relayCloseout']=relay.close()
            if result['relayCloseout'] and result['relayCloseout']['failures']:result.update(status='FAIL',relay='CLOSEOUT_NOT_VERIFIED')
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
            stopped=stop_owned(root,runtime);result['stoppedContainerIds']=stopped['stopped']
            if stopped['failures']:result.update(status='FAIL',cleanup='STOP_FAILED_KEEP_EXACT_MANIFEST',stopFailures=stopped['failures'])
        replace_manifest(evidence/'resources.json',resource_manifest(root,runtime,config,private,'AFTER_STOP'))
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
