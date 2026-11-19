"""在任务独立平台上复用源码绑定、合成 OIDC 和只读运行快照。"""
import argparse
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import signal
import threading
import socket
import subprocess
import sys
import time
import urllib.request

import canonical_fuseki
import workflow_doris_vm as vm
import workflow_execution as execution
import workflow_m2_build as build
import workflow_m4_query_runtime as snapshots
from workflow_doris_fixture import host_service, private
from workflow_doris_s0_fixture import DIRECTORY, INDEX, PROJECT, docker, record, sql, stress_resources


ROOT, OUT = vm.ROOT, vm.OUTPUT
HOME_DIR = DIRECTORY.parent/vm.RUN
RUNTIME = HOME_DIR/'runtime'
COMPOSE = OUT/'s1-platform-compose.json'
PLATFORM = OUT/'s1-platform-resources.json'
SNAPSHOT = OUT/'s1-api-snapshot.json'
PORTS = {'platform-pg':(15644,5432),'keycloak-test':(15643,8080),'fuseki':(15645,3030),'rustfs':(15646,9000)}
QUOTAS = {'platform-pg':(768,1),'keycloak-test':(1024,1),'fuseki':(2048,2),'rustfs':(512,1)}
FUSEKI_ID = 'sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c'


def local(stage,args,env=None,seconds=30,inputs=None):
    result = execution.run(args,ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-s1-'+stage,environment=env,timeout=seconds,input_key=inputs)
    vm.demand(result.returncode==0,'S1_'+stage.upper()+'_'+result.receipt['commandId'])
    return result


def admit_build():
    required = json.loads((ROOT/'docs/evidence'/vm.TASK/vm.RUN/'s0-qualified-review.json').read_bytes())
    vm.demand(required['status']=='S0_GO' and required['reviewDecision']=='GO_S1','S0_QUALIFICATION')
    return build.validate('api',vm.TASK)


def freeze_api():
    binding = admit_build()
    b = ROOT/'artifacts/workflow'/vm.TASK/'api-build-binding.json'
    candidate = json.loads(b.read_bytes())
    archive = OUT/('s1-api-build-'+binding['receiptSha256']+'.json')
    if not archive.exists():
        with archive.open('xb') as stream: stream.write(b.read_bytes())
    env = {'dotnet':candidate['command'][0],'platform':sys.platform}
    target = ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    if SNAPSHOT.exists():
        previous = json.loads(SNAPSHOT.read_bytes())
        snapshots.verify(ROOT,previous,task=vm.TASK,run_id=vm.EVIDENCE_RUN)
        if previous['inputs']==binding: return previous
    row = snapshots.freeze(ROOT,target,OUT/'runtime-snapshots',binding,binding['receiptSha256'],env,task=vm.TASK,run_id=vm.EVIDENCE_RUN)
    record(SNAPSHOT,row)
    return row


def prepare():
    os.umask(0o077)
    frozen = freeze_api()
    vm.demand(not COMPOSE.exists() and not HOME_DIR.exists(),'S1_PRESERVE_PRIVATE')
    HOME_DIR.mkdir(mode=0o700)
    pg = HOME_DIR/'platform-pg'
    for d in (pg,RUNTIME,RUNTIME/'api',RUNTIME/'keyring',RUNTIME/'query-keyring'):
        d.mkdir(mode=0o700)
    for name in ('keycloak-password','s3-access','s3-secret'):
        private(RUNTIME/name,secrets.token_urlsafe(40))
    private(pg/'password',secrets.token_urlsafe(40))
    private(pg/'pg_hba.conf','local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::0/0 scram-sha-256\n')
    private(pg/'certificate.cnf','[req]\ndistinguished_name=dn\nx509_extensions=extensions\nprompt=no\n[dn]\nCN=platform-pg\n[extensions]\nsubjectAltName=DNS:platform-pg,DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    local('platform-ca',['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','7','-config',str(pg/'certificate.cnf'),'-keyout',str(pg/'server.key'),'-out',str(pg/'server.crt')])
    private(RUNTIME/'api/g4-key',secrets.token_bytes(32))
    private(RUNTIME/'runtime.json',dict(taskId=vm.TASK,runId=vm.RUN,publicOrigin='http://localhost:15641',
            certificatePath=str(RUNTIME/'api/keyring.pfx'),certificatePassword=secrets.token_urlsafe(40),healthKey=secrets.token_urlsafe(32)))
    local('keyring',['pwsh','-NoProfile','-File','scripts/acceptance/new-wave2-certificate.ps1','-RuntimeFile',str(RUNTIME/'runtime.json')])
    render()
    print('S1_PRIVATE_AND_SNAPSHOT_READY',frozen['snapshotId'])


def render():
    vm.demand(not PLATFORM.exists(),'S1_ALREADY_CREATED')
    pg = HOME_DIR/'platform-pg'
    sys.path.insert(0,str(ROOT/'.tools/pythonlibs'))
    import yaml
    text = (ROOT/'experiments/g4-m3-mapping-001/compose.yaml').read_text()
    for old,new in [('${MAPPING_RUN_ID:?explicit run required}',vm.RUN),('${MAPPING_HOST_UID:-501}',str(os.getuid())),
                    ('${MAPPING_HOST_GID:-20}',str(os.getgid())),('${MAPPING_RUNTIME_PRIVATE_DIR:-/not-configured}',str(RUNTIME)),
                    ('${MAPPING_PRIVATE_DIR:?explicit private directory required}',str(pg)),('15680','15643')]:
        text = text.replace(old,new)
    template = yaml.safe_load(text)
    labels = {'ontology.task':vm.TASK,'ontology.run':vm.RUN}
    services = {k:template['services'][k] for k in PORTS}
    for name,service in services.items():
        ram,cores = QUOTAS[name]
        published,inside = PORTS[name]
        service.update(labels=labels,mem_limit=ram*1024**2,memswap_limit=ram*1024**2,cpus=cores,
                       ports=[f'127.0.0.1:{published}:{inside}'],networks=['platform-private','platform-entry'])
    for name in ('keycloak-test','rustfs'):
        services[name]['user']=f'{os.getuid()}:{os.getgid()}'
    canonical = canonical_fuseki.identity(ROOT/'infra/development/fuseki','linux/arm64')
    canonical_fuseki.validate_image(canonical_fuseki.inspect_image(canonical),canonical,FUSEKI_ID)
    services['fuseki']['image'] = canonical['image']
    volumes = {k:dict(template['volumes'][k],labels=labels) for k in ('platform-data','keycloak-data','rustfs-data','fuseki-data')}
    spec = dict(name=PROJECT,services=services,volumes=volumes,networks={'platform-private':dict(internal=True,labels=labels),'platform-entry':dict(labels=labels)})
    if COMPOSE.exists():
        prior=OUT/('s1-compose-'+execution.sha(COMPOSE.read_bytes())+'.json')
        if not prior.exists(): prior.write_bytes(COMPOSE.read_bytes())
    record(COMPOSE,spec)


def start():
    binding = admit_build()
    state = json.loads(INDEX.read_bytes())
    spec = json.loads(COMPOSE.read_bytes())
    vm.demand(not PLATFORM.exists() and spec['name']==PROJECT and set(spec['services'])==set(PORTS),'S1_PLATFORM_CREATE')
    source = stress_resources(state)
    memory,cores = map(int,docker('platform-capacity','info','-f','{{.MemTotal}} {{.NCPU}}').split())
    cap = int(14.25*vm.GIB)
    host = int(vm.host('sysctl','-n','hw.memsize'))
    vm.demand(memory>=cap+2*vm.GIB and cores>=9 and host>=20*vm.GIB+int(5.5*vm.GIB) and shutil.disk_usage(ROOT).free>=12*vm.GIB,'S1_CAPACITY')
    for port in range(15641,15648):
        with socket.socket() as probe: probe.bind(('127.0.0.1',port))
    inventory = dict(taskId=vm.TASK,runId=vm.RUN,capBytes=cap,vmBytes=memory,vmCpu=cores,hostBytes=host,
                     hostFree=vm.host('memory_pressure','-Q').splitlines()[-1],source=source,binding=binding,resources={},volumes={},networks={},images={},status='PREPARING')
    compose = ['compose','-p',PROJECT,'-f',str(COMPOSE)]
    for name,service in spec['services'].items():
        image = docker('platform-image','image','inspect','-f','{{.Id}} {{.Os}} {{.Architecture}}',service['image']).split()
        expected = FUSEKI_ID if name=='fuseki' else service['image'].split('@')[1]
        vm.demand(image==[expected,'linux','arm64'] and service['pull_policy']=='never','PLATFORM_IMAGE')
        vm.demand(not docker('platform-existing',*compose,'ps','-aq',name),'PLATFORM_ALREADY_EXISTS')
        inventory['images'][name] = expected
    for kind in ('volume','network'):
        existing = set(docker('platform-existing-'+kind,kind,'ls','--format','{{.Name}}').splitlines())
        vm.demand(all(PROJECT+'_'+name not in existing for name in spec[kind+'s']),'PLATFORM_NAME_COLLISION')
    record(PLATFORM,inventory)
    try:
        docker('platform-create',*compose,'create','--no-build','--pull','never',*PORTS,timeout=60)
    finally:
        for name in PORTS:
            cid=docker('platform-owner',*compose,'ps','--all','--quiet',name)
            if cid:
                check=docker('platform-id','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.NanoCpus}} {{.State.Status}}',cid).split()
                ram,cores=QUOTAS[name]
                vm.demand(check==[cid,inventory['images'][name],vm.TASK,vm.RUN,str(ram*1024**2),str(ram*1024**2),str(cores*10**9),'created'],'S1_EXACT_RESOURCE')
                inventory['resources'][name]=cid
        for kind in ('volume','network'):
            for name in spec[kind+'s']:
                handle=PROJECT+'_'+name
                actual=docker('platform-volume-network',kind,'inspect','-f','{{index .Labels "ontology.task"}} {{index .Labels "ontology.run"}}',handle)
                vm.demand(actual==vm.TASK+' '+vm.RUN,'S1_OBJECT_OWNER')
                inventory[kind+'s'][name]=handle
        record(PLATFORM,inventory)
    vm.demand(len(inventory['resources'])==4,'S1_CREATE_INCOMPLETE')
    for name,cid in inventory['resources'].items():
        docker('platform-start-'+name,'start',cid,timeout=30)
    inventory['status']='STARTED'
    record(PLATFORM,inventory)
    print('S1_PLATFORM_STARTED')


def configure():
    p=json.loads(PLATFORM.read_bytes())
    vm.demand(p['status']=='STARTED','S1_NOT_STARTED')
    for name,cid in p['resources'].items():
        vm.demand(docker('platform-config-owner','inspect','-f','{{.Id}} {{.State.Status}} {{.State.OOMKilled}}',cid)==cid+' running false','S1_SERVICE_STOPPED_'+name)
    origin='http://localhost:15643'
    duration=time.monotonic()+60
    while time.monotonic()<duration:
        try:
            with urllib.request.urlopen(origin+'/realms/master/.well-known/openid-configuration',timeout=2) as response:
                if response.status==200: break
        except OSError: time.sleep(.5)
    else: raise ValueError('S1_IDP_NOT_READY')
    env=dict(os.environ,WAVE2_KEYCLOAK_ADMIN_PASSWORD=(RUNTIME/'keycloak-password').read_text())
    if not (RUNTIME/'realm.json').exists():
        local('realm',['python3','-B','infra/security/bootstrap-keycloak.py','--profile','g2','--keycloak-origin',origin,'--public-origin','http://localhost:15641','--runtime-output',str(RUNTIME/'realm.json')],env,90)
    idp=json.loads((RUNTIME/'realm.json').read_bytes())
    identity=json.loads((RUNTIME/'runtime.json').read_bytes())
    pg=HOME_DIR/'platform-pg'
    vm.demand(idp['authority'].startswith(origin+'/realms/g2-'),'S1_IDP_ORIGIN')
    conf={'ConnectionStrings':{'governance':'Host=localhost;Port=15644;Database=mapping;Username=postgres;Password='+(pg/'password').read_text()+';SSL Mode=VerifyFull;Root Certificate='+str(pg/'server.crt')+';Timeout=5;Command Timeout=5'},
          'Security':{'Authority':idp['authority'],'ClientId':idp['clientId'],'ClientSecret':idp['clientSecret'],'PublicOrigin':identity['publicOrigin'],
                      'KeyRingPath':str(RUNTIME/'keyring'),'CertificatePath':identity['certificatePath'],'CertificatePassword':identity['certificatePassword'],'HealthKey':identity['healthKey']},
          'Web':{'Origin':'http://127.0.0.1:15642'},'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},
          'G2':{'Enabled':True,'ApplyMigrations':True},'G4':{'Enabled':True,'ApplyMigrations':True,'Mapping':{'Enabled':True},'QueryEnabled':True,'KeyFile':str(RUNTIME/'api/g4-key'),'QueryKeyRingPath':str(RUNTIME/'query-keyring'),'Doris':{'RootCertificatePath':str(DIRECTORY/'tls/ca.pem')}},
          'Semantics':{'ValidationOrigin':'http://127.0.0.1:15645/validation','PublishedOrigin':'http://127.0.0.1:15645/ontology'},
          'Publishing':{'S3Endpoint':'http://127.0.0.1:15646','AccessKey':(RUNTIME/'s3-access').read_text(),'SecretKey':(RUNTIME/'s3-secret').read_text(),'Bucket':'g4-doris-mapping-synthetic'},
          'Logging':{'LogLevel':{'Default':'Warning'}}}
    private(RUNTIME/'api/appsettings.json',conf)
    print('S1_CONFIGURED')


HOST = OUT/'s1-api-process.json'
BROWSER = ('s2-doris-ready','s2-doris-root-deadline','s3','ui-s1','ui-s3','s2-doris-authority-control','s2-doris-sentinel','s2-doris-overlap','provision','mapping','s1','s1-reopen','s1-key-negative','s1-current-catalog','s2-doris-mapping','s2-doris-queries','s2-doris-null','s2-doris-cancel','s2-doris-access','s2-doris-fanout','s2-doris-requalify','s2-doris-aba','s2-doris-admission-cancel','s2-doris-cancel-window','s2-doris-states','s2-doris-cardinality','s2-doris-identity','s2-doris-revoke-race','s2-doris-session-race','s2-doris-shape-prepare','s2-doris-shape-reject','s2-doris-shape-recover','s2-doris-cancel-profile','s2-doris-expiry','s2-doris-ddl-race','s2-doris-rotate-race','s2-doris-current-catalog','s2-doris-deadline','s2-doris-short-lock','s2-doris-disconnect','s2-doris-batch-binding')


def runtime_binding():
    row = json.loads(HOST.read_bytes())
    snapshot = json.loads(SNAPSHOT.read_bytes())
    snapshots.verify(ROOT,snapshot,task=vm.TASK,run_id=vm.EVIDENCE_RUN)
    pid = str(row['pid'])
    dll = ROOT/snapshot['directory']/'OntologyPlatform.Api.dll'
    vm.demand(row['taskId']==vm.TASK and row['runId']==vm.RUN and row['status']=='READY'
              and row['snapshotId']==snapshot['snapshotId'] and snapshot['inputs']==admit_build()
              and vm.host('ps','-p',pid,'-o','lstart=')==row['processStart']
              and vm.host('ps','-p',pid,'-o','command=')==snapshot['environment']['dotnet']+' '+str(dll),'S1_HOST_BINDING')
    return row


def web_binding():
    from workflow_m4_query import web_binding as bound_web
    return bound_web(vm.TASK,vm.RUN)


def s3_web_check(stage, prepared):
    from workflow_m4_query import web_check
    path=execution.ordinary(Path(prepared).absolute())
    vm.demand(path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'S3_PREPARE_PATH')
    dep=json.loads(path.read_bytes())
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'S3_ENVIRONMENT')
    return web_check(stage,task=vm.TASK,run_id=vm.EVIDENCE_RUN,env=dep['environment'],node=dep['node'])


def live_stack():
    state = json.loads(PLATFORM.read_bytes())
    source = json.loads(INDEX.read_bytes())
    services = dict(state['resources'],**{k:v['id'] for k,v in source['services'].items()})
    vm.demand(set(docker('six-cids','ps','-q','--no-trunc').splitlines())==set(services.values()),'S1_RESOURCE_PARTITION')
    for name,cid in services.items():
        check = docker('health','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}} {{.State.OOMKilled}} {{with (index .State "Health")}}{{.Status}}{{else}}none{{end}}',cid).split()
        vm.demand(check[:5]==[cid,vm.TASK,vm.RUN,'running','false'] and check[5] in ('healthy','none'),'S1_CONTAINER_'+name)
    return services


def browser_test(mode, prepared, readiness_stage='baseline', counterexample=None):
    """正式分发。仅期限见证运行一个可释放的本机 HTTP 观察点。"""
    if mode=='s2-doris-root-deadline':
        from doris_semantic_deadline_witness import validation_origin
        run_key=secrets.token_hex(16)
        with validation_origin(OUT,run_key) as origin:
            return run_browser(mode,prepared,readiness_stage,run_key,origin,counterexample)
    return run_browser(mode,prepared,readiness_stage,None,None,counterexample)


def run_browser(mode, prepared, readiness_stage, run_key, validation_url, counterexample):
    dependency_path=execution.ordinary(Path(prepared).absolute())
    vm.demand(dependency_path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'S1_ENVIRONMENT_PATH')
    dep=json.loads(dependency_path.read_bytes())
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'S1_ENVIRONMENT')
    from workflow_doris_s0_fixture import STRESS
    vm.demand(STRESS.exists()==(mode in ('s2-doris-overlap','s2-doris-cancel','s2-doris-admission-cancel','s2-doris-cancel-window')),'PRODUCT_STRESS_ISOLATION')
    live_stack()
    snapshot=freeze_api()
    dll=ROOT/snapshot['directory']/'OntologyPlatform.Api.dll'
    vm.demand(snapshot['environment']['dotnet']==dep['dotnet'],'S1_HOST_RUNTIME')
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        check.bind(('127.0.0.1',15641))
    identity=json.loads((RUNTIME/'runtime.json').read_bytes())
    context=execution.CONTEXT.set(dict(task=vm.TASK,run_id=vm.EVIDENCE_RUN))
    exceeded=threading.Event()
    finished=threading.Event()
    web_service=None
    env=dict(PATH=os.environ['PATH'],ASPNETCORE_ENVIRONMENT='Development',ASPNETCORE_CONTENTROOT=str(RUNTIME/'api'),
             G4__SourceCaPath=str(DIRECTORY/'tls/ca.pem'),ASPNETCORE_URLS='http://127.0.0.1:15641',DOTNET_GCHeapHardLimit='0x18000000',DOTNET_CLI_TELEMETRY_OPTOUT='1')
    env['Logging__LogLevel__OntologyPlatform.Modules.SemanticQuery.G4QueryExecution']='Debug' if mode in ('s2-doris-cancel-profile','s2-doris-cancel','s2-doris-overlap') else 'Information'
    if validation_url: env['Semantics__ValidationOrigin']=validation_url
    service=host_service([dep['dotnet'],str(dll)],env,ROOT,vm.TASK,exceeded)
    pid=service.process.pid
    evidence=OUT/('s1-host-'+mode+'-'+service.ident+'.json')
    row=dict(taskId=vm.TASK,runId=vm.RUN,stage=mode,status='STARTED',pid=pid,commandId=service.ident,snapshotId=snapshot['snapshotId'])
    peaks=dict(api=0,total=0)
    def monitor():
        while not finished.is_set():
            try:
                raw=vm.host('ps','-axo','pid=,ppid=,rss=')
                usage=[tuple(map(int,line.split())) for line in raw.splitlines()]
                children={os.getpid()}
                while True:
                    more={p for p,parent,_ in usage if parent in children}-children
                    if not more: break
                    children.update(more)
                peaks['api']=max(peaks['api'],max((rss*1024 for p,_,rss in usage if p==pid),default=0))
                peaks['total']=max(peaks['total'],sum(rss*1024 for p,_,rss in usage if p in children))
                if peaks['api']>768*1024**2 or peaks['total']>int(5.5*vm.GIB): exceeded.set()
            except (OSError,ValueError,subprocess.SubprocessError): exceeded.set()
            if exceeded.is_set():
                if service.process.poll() is None: os.killpg(pid,signal.SIGTERM)
                break
            finished.wait(.5)
    watcher=threading.Thread(target=monitor,daemon=True)
    watcher.start()
    record(evidence,row)
    try:
        row['processStart']=vm.host('ps','-p',str(pid),'-o','lstart=')
        probe=urllib.request.Request(identity['publicOrigin']+'/health/live',headers={'X-Health-Key':identity['healthKey']})
        stop=time.monotonic()+45
        while time.monotonic()<stop:
            vm.demand(service.process.poll() is None and not exceeded.is_set(),'S1_API_EXIT_'+service.ident)
            try:
                with urllib.request.urlopen(probe,timeout=2) as response:
                    if response.status==200: break
            except OSError: time.sleep(.25)
        else: raise ValueError('S1_API_READINESS_'+service.ident)
        row['status']='READY'
        record(HOST,row)
        service.ready()
        runtime_binding()
        if mode.startswith('ui-'):
            web_binding()
            with socket.socket() as check:
                check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                check.bind(('127.0.0.1',15642))
            web_service=host_service([dep['node'],'scripts/maintenance/workflow-m4-query.mjs','--task',vm.TASK,
                                      '--run-id',vm.RUN,'--mode','serve'],{'PATH':os.environ['PATH'],'G4_DORIS_EVIDENCE_RUN':vm.EVIDENCE_RUN},ROOT,vm.TASK,exceeded)
            row['webPid']=web_service.process.pid
            row['webCommandId']=web_service.ident
            row['webProcessStart']=vm.host('ps','-p',str(web_service.process.pid),'-o','lstart=')
            row['webBuild']=web_binding()
            record(evidence,row)
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                vm.demand(web_service.process.poll() is None and not exceeded.is_set(),'S3_WEB_EXIT_'+web_service.ident)
                try:
                    with socket.create_connection(('127.0.0.1',15642),timeout=.5): break
                except OSError: time.sleep(.1)
            else: raise ValueError('S3_WEB_READINESS')
            web_service.ready()
        # 浏览器实际消费的脚本与程序集进入输入指纹，重验保留前次失败且可区分修正。
        from workflow_doris_mapping_query import BROWSER_SOURCES
        runner_paths = [ROOT/name for name in BROWSER_SOURCES]
        components = [snapshot['snapshotId'], mode, [execution.sha(path.read_bytes()) for path in runner_paths]]
        if vm.EVIDENCE_RUN!=vm.RUN:
            row['stageInputs']=dict(readinessStage=readiness_stage,expectedStale=counterexample)
            components.append(row['stageInputs'])
        if STRESS.exists():
            data=STRESS.read_bytes()
            fingerprint=execution.sha(data)
            if vm.EVIDENCE_RUN!=vm.RUN:
                archive=OUT/('stress-input-'+fingerprint+'.json')
                if not archive.exists():
                    with archive.open('xb') as stream: stream.write(data)
                vm.demand(archive.read_bytes()==data,'STRESS_INPUT_DRIFT')
                row['stressInput']=fingerprint
            components.append(fingerprint)
        inputs = execution.sha(execution.encoded(components))
        report=local('browser-'+mode,[dep['node'],'scripts/maintenance/workflow-m4-query.mjs','--task',vm.TASK,'--run-id',vm.RUN,'--mode',mode],seconds=180,inputs=inputs,env=dict(os.environ,DMQ_READINESS_STAGE=readiness_stage,DMQ_ROOT_WITNESS=run_key or '',DMQ_STALE_EXPECTATION=counterexample or ''))
        vm.demand(not exceeded.is_set(),'S1_HOST_CAP')
        print(report.stdout.decode().strip())
        row['browserCommand']=report.receipt['commandId']
    finally:
        # 反向代理可持有 Web 长连接，两端均收到 TERM 后再等待各自退出。
        finished.set()
        watcher.join(6)
        if service.process.poll() is None: os.killpg(pid,signal.SIGTERM)
        if web_service is not None and web_service.process.poll() is None:
            os.killpg(web_service.process.pid,signal.SIGTERM)
        try: service.process.wait(timeout=12)
        finally:
            for thread in service.reader_threads: thread.join(2)
            service.finish()
            if web_service is not None:
                try: web_service.process.wait(timeout=15)
                finally:
                    for thread in web_service.reader_threads: thread.join(2)
                    web_service.finish()
                    row['webExitCode']=web_service.process.poll()
            # 只保存固定格式聚合数值与本任务 queryId，不导出任何其他应用日志。
            matches = re.findall(rb'DorisLeaseObservation query=(query-[0-9a-f]{32}) probes=(\d+) elapsedMs=([0-9.]+) maxReadMs=([0-9.]+) outcome=(closed|lease_changed|observation_failed)', bytes(service.out)+bytes(service.err))
            timings = re.findall(rb'QueryCancelPhase query=(query-[0-9a-f]{32}) phase=(owner|catalog|artifacts|graphs|verifiedBatch|sourceBinding|graphIndex|root|session|grants|transaction) elapsedMs=([0-9.]+)', bytes(service.out)+bytes(service.err))
            deadlines = re.findall(rb'TemporaryGraphCleanupUnconfirmed phase=([A-Za-z]+) graph=(urn:ontology-platform:temporary:[0-9a-f]{32}) cleanupDeadline=(\S+) requestDeadline=(\S+)',bytes(service.out)+bytes(service.err))
            row['cleanupUnknown'] = [dict(phase=p.decode(),graph=g.decode(),cleanupDeadline=c.decode(),requestDeadline=d.decode()) for p,g,c,d in deadlines]
            row['cancelPhases'] = [dict(queryId=q.decode(),phase=phase.decode(),ms=float(ms)) for q,phase,ms in timings]
            row['dorisObservations'] = [dict(queryId=q.decode(), probes=int(n), elapsedMs=float(t), maxReadMs=float(m), outcome=o.decode()) for q,n,t,m,o in matches]
            row.update(status='EXITED' if service.process.poll() is not None else 'STOP_UNKNOWN',hostPeakBytes=peaks,
                       exceeded=exceeded.is_set(),exitCode=service.process.poll())
            record(evidence,row)
            record(HOST,row)
            execution.CONTEXT.reset(context)


def grant_fields(catalog,two_tables):
    tables={'dmq_entity':'org_id site_id entity_id join_key amount unit_code valid_from valid_to event_at observed_at'.split()}
    if two_tables: tables['dmq_target']='org_id site_id target_id join_key valid_from valid_to event_at observed_at'.split()
    objects=[]
    field_refs=[]
    for name,columns in tables.items():
        table=next(t for t in catalog['objects'] if t['schema']=='fixture' and t['name']==name and t['kind']=='TABLE')
        fields=sorted(table['fields'],key=lambda f:f['ordinal'])
        vm.demand([(f['ordinal'],f['name']) for f in fields]==list(enumerate(columns,1)),'DORIS_GRANT_FIELDS')
        base='fixture/'+name
        objects.append(base)
        field_refs.extend(f"{base}/{f['ordinal']}/{f['name']}" for f in fields)
    return objects,field_refs


def readiness_budget(stage):
    """授权覆盖装载、正式分支及恢复；短命浏览器会话在每次接续重新登录及核验。"""
    # 每批 INSERT / DELETE 最多 60 秒，两次读取各 15 秒；最大 64 批。
    fixture_seconds = {'baseline':0, 'staged':60, 'sentinel-running':0, 'sentinel':60, 'stress':64*(60+2*15), 'pressure-running':0}
    if stage not in fixture_seconds:
        raise ValueError('DORIS_PREREQUISITE_STAGE')
    restore = {'pressure-running':fixture_seconds['stress'],'sentinel-running':60}.get(stage,fixture_seconds[stage])
    return dict(load=fixture_seconds[stage], execute=180, restore=restore)


def scenario_ready(state, stage, connection, active, actors):
    """同一正式分发入口在变更前核四角色会话、授权余量、绑定和已知夹具阶段。"""
    import datetime
    from workflow_m5_integration import demand_scoped_grants
    from workflow_doris_s0_fixture import STRESS, STRESS_TABLES, stress_original
    import uuid
    resources = live_stack()
    host = runtime_binding()
    window = readiness_budget(stage)
    seconds = sum(window.values())
    roles = state['subjects']
    vm.demand(set(roles)=={'operator','auditor','activator','reader'} and len(set(roles.values()))==4
              and [v['subjectId'] for v in actors]==[roles[k] for k in ('operator','auditor','activator','reader')], 'PREREQUISITE_STALE:subjects')
    vm.demand(state['scope']=={'organizationId':'org-demo','siteIds':['site-a']} and state['taskId']==vm.TASK and state['runId']==vm.RUN, 'PREREQUISITE_STALE:scope')
    expected = state.get('mappingCurrentReceipt') or state['mappingReceipt']
    binding = state['mappingRelease']['manifest']['binding']
    vm.demand(all(active.get(k)==expected[k] for k in ('mappingId','mappingReleaseId','manifestHash','activationRevision')), 'PREREQUISITE_STALE:activation')
    vm.demand(connection['state']=='ACTIVE' and connection['id']==state['connectionId']==binding['sourceConnectionId']
              and connection['configRevision']==binding['connectionRevision'] and connection['secretVersion']==binding['secretVersion'], 'PREREQUISITE_STALE:connection')
    cid=resources['platform-pg']
    def read(statement):
        return json.loads(docker('scenario-readiness','exec',cid,'psql','-XwqAt','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1','-c',statement))
    vm.demand(re.fullmatch('[a-f0-9]{32}',state['connectionId']) is not None,'PREREQUISITE_STALE:connection')
    current = read('SELECT "ViewJson" FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+state['connectionId']+'\' ORDER BY "CapturedAtUtc" DESC,"Id" DESC LIMIT 1;')
    mapping_id = expected['mappingId']
    vm.demand(re.fullmatch(r'mapping-[0-9a-f]{32}',mapping_id) is not None,'PREREQUISITE_STALE:activation')
    pointer = read(f"""SELECT to_jsonb(a) FROM connections."MappingActives" a WHERE "MappingId"='{mapping_id}'""")
    vm.demand(pointer['ActivationId']==expected['activationId'] and pointer['ActivationRevision']==active['activationRevision'],'PREREQUISITE_STALE:activation')
    catalog = state['catalog']
    vm.demand(current['status']=='READY' and current['snapshotId']==catalog['snapshotId']==binding['sourceCatalogSnapshotId']
              and current['schemaFingerprint']==catalog['schemaFingerprint']==binding['sourceCatalogFingerprint']
              and current['secretVersion']==binding['secretVersion'] and current['configRevision']==binding['connectionRevision'], 'PREREQUISITE_STALE:catalog')
    config_hash = read(f"""SELECT to_jsonb("ConfigHash") FROM connections."Connections" WHERE "Id"='{state['connectionId']}'""")
    vm.demand(config_hash==binding['configHash'],'PREREQUISITE_STALE:connection')
    objects,fields = grant_fields(current,True)
    vm.demand(len(fields)==18, 'PREREQUISITE_STALE:field_set')
    rows=read("""SELECT coalesce(json_agg(g),'[]') FROM (SELECT "SubjectId","OrganizationId","SiteIds","Permission","ConnectionId","ObjectRefs","FieldRefs","ExpiresAtUtc"
                     FROM governance."MappingAuthorizationGrants" WHERE "RevokedAtUtc" IS NULL AND ("ConnectionId" IS NULL OR "ConnectionId"='"""+state['connectionId']+"')) g;")
    now=datetime.datetime.now(datetime.timezone.utc)
    def eligible(required):
        return [r for r in rows if datetime.datetime.fromisoformat(r['ExpiresAtUtc'].replace('Z','+00:00'))>now+datetime.timedelta(seconds=required)]
    permissions={'operator':['mapping.read'],'reader':['data.query.execute','data.query.result.read','data.query.evidence.read']}
    for ttl in (0,seconds):
        try: demand_scoped_grants(eligible(ttl),state,objects,fields,permissions)
        except ValueError as error: raise ValueError('PREREQUISITE_STALE:'+('grant_ttl' if ttl else 'grant_expired_or_missing')) from error
    # Cookie 只经内存管道进入原有正式票据核验器，输出只含非秘密期限与会话散列。
    tested=build.validate('agent',vm.TASK)
    vm.demand(tested['inputKey']==admit_build()['inputKey'],'PREREQUISITE_STALE:session_build')
    dotnet=json.loads(SNAPSHOT.read_bytes())['environment']['dotnet']
    dll=ROOT/Path(build.TARGETS['agent']).parent/'bin/Debug/net10.0/OntologyPlatform.AgentTests.dll'
    session_file=OUT/('session-ready-'+uuid.uuid4().hex+'.json')
    env=dict(PATH=os.environ['PATH'],G4_BROWSER_PREFLIGHT='1',G4_QUERY_RUNTIME_TEST=vm.TASK+':'+vm.RUN,
             G4_DORIS_EVIDENCE_RUN=vm.EVIDENCE_RUN,G4_BROWSER_REPORT=str(session_file),DMQ_SESSION_SECONDS=str(window['execute']),
             ASPNETCORE_ENVIRONMENT='Development',DOTNET_CLI_TELEMETRY_OPTOUT='1')
    result=execution.run([dotnet,str(dll),'--filter','FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline','--minimum-expected-tests','1','--no-ansi','--progress','off','--results-directory',str(OUT/'session-tests')],
        ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-current-sessions',environment=env,stdin=execution.encoded(actors),input_key=execution.sha(execution.encoded(tested)),timeout=20)
    vm.demand(result.returncode==0 and len(json.loads(session_file.read_bytes()))==4,'PREREQUISITE_STALE:session')
    baseline=json.loads((OUT/'s0-fixed-fixture-0da9ac2fd127ad4f-restored.json').read_bytes())
    fe=resources['fe']
    pressure=json.loads(STRESS.read_bytes()) if STRESS.exists() else None
    vm.demand((pressure is not None)==(stage=='pressure-running'),'PREREQUISITE_STALE:fixture_stage')
    staged_counts = {}
    if stage=='sentinel-running':
        ledger=json.loads((OUT/'s2-sentinel-active.json').read_bytes())
        vm.demand(ledger['fe']==fe and ledger['runId']==vm.RUN and ledger['taskId']==vm.TASK and len(set(ledger['keys']))==100,'PREREQUISITE_STALE:sentinel')
        staged_counts['dmq_entity']=100
    for table,key,original in STRESS_TABLES:
        vm.demand(stress_original(fe,table,key,original)==baseline['tables'][table]['before'],'PREREQUISITE_STALE:fixture_bytes')
        expected_count=len(original)+(pressure['tables'][table]['planned'] if pressure else staged_counts.get(table,0))
        vm.demand(int(sql(fe,'reader',f'SELECT COUNT(*) FROM fixture.{table}'))==expected_count,'PREREQUISITE_STALE:fixture_count')
    qualified = dict(status='READY',stage=stage,budgetSeconds=window,grantRequiredSeconds=seconds,sessionRequiredSeconds=window['execute'],
                sessionCommand=result.receipt['commandId'],snapshot=host['snapshotId'],resourceIds=resources,fieldCount=len(fields),
                connectionId=connection['id'],secretVersion=connection['secretVersion'],catalog=current['snapshotId'],activation=expected['activationId'])
    qualified.update(command=host['commandId'],mode=host['stage'],observedAt=time.time(),validUntil=time.time()+window['execute'])
    record(OUT/('ready-'+host['commandId']+'.json'),qualified)
    return qualified


def nested_control(modes):
    """嵌套的变更必须属于当前正式运行及其已检查的前态，恢复独立可达。"""
    host=runtime_binding()
    receipt=json.loads((OUT/('ready-'+host['commandId']+'.json')).read_bytes())
    vm.demand(receipt['command']==host['commandId'] and receipt['snapshot']==host['snapshotId'] and
              receipt['mode'] in modes and time.time()<receipt['validUntil'],'PREREQUISITE_STALE:control')


def root_query_state(query_id, failed_key):
    """只读对账本轮正常提交和失败请求的准确行与审计。"""
    import uuid
    vm.demand(re.fullmatch('query-[a-f0-9]{32}',query_id) and str(uuid.UUID(failed_key))==failed_key,'ROOT_WITNESS_IDS')
    cid=json.loads(PLATFORM.read_bytes())['resources']['platform-pg']
    statement=f"""SELECT json_build_object('status',"ExecutionStatus",'cancel',"CancelRequested",'resultHash',"ResultHash",'resultSize',"ResultSize",
        'cancelAudits',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.cancel' AND "Outcome"='allowed' AND "Resource"='{query_id}'),
        'executeAudits',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.execute' AND "Outcome"='allowed' AND "Resource"='{query_id}'),
        'failedAdmissions',(SELECT count(*) FROM semantic_query."Queries" WHERE "IdempotencyKey"='{failed_key}'))
        FROM semantic_query."Queries" WHERE "Id"='{query_id}';"""
    return json.loads(docker('root-exact-state','exec',cid,'psql','-XwqAt','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1','-c',statement))


def synthetic_grants(mode, two_tables=False, renewal=False, ttl_seconds=14400):
    from workflow_m4_query import grant_transaction
    state=json.loads((OUT/('doris-two-table.json' if two_tables else 'runtime-fixture.json')).read_bytes())
    vm.demand(ttl_seconds==14400 or (ttl_seconds==120 and renewal and two_tables and mode=='query' and vm.EVIDENCE_RUN=='review-fix-01'),'RENEWAL_TTL_SCOPE')
    roles=state['subjects']
    vm.demand(state['taskId']==vm.TASK and state['runId']==vm.RUN and state['scope']==dict(organizationId='org-demo',siteIds=['site-a'])
              and set(roles)=={'operator','auditor','activator','reader'} and len(set(roles.values()))==4,'S1_GRANT_SCOPE')
    catalog=state['catalog']
    vm.demand(catalog['connectionId']==state['connectionId'] and catalog['status']=='READY','S1_GRANT_CATALOG')
    objects,field_refs = grant_fields(catalog,two_tables)
    perms={'operator':['mapping.read','mapping.source.validate','mapping.edit','mapping.validate','mapping.submit'],
           'auditor':['mapping.read','mapping.source.validate','mapping.review','mapping.approve'],
           'activator':['mapping.read','mapping.source.validate','mapping.activate']} if mode=='mapping' else {
               'reader':['data.query.execute','data.query.result.read','data.query.evidence.read']}
    if mode=='active-read': perms={'operator':['mapping.read']}
    def original_id(subject,permission):
        return ('dmq-s2-' if two_tables else 'dmq-s1-')+execution.sha(execution.encoded([state['connectionId'],subject,permission]))[:32]
    def id_for(subject,permission):
        previous_id = original_id(subject,permission)
        if not renewal: return previous_id
        return ('renew-20261119-' if vm.EVIDENCE_RUN == vm.RUN else vm.EVIDENCE_RUN+('-short-' if ttl_seconds==120 else '-'))+previous_id
    sql,ids=grant_transaction(state,objects,field_refs,
                              [(roles[role],permissions) for role,permissions in perms.items()],id_for,vm.EVIDENCE_RUN,ttl_seconds)
    cid=live_stack()['platform-pg']
    if renewal:
        vm.demand(mode in ('query','active-read') and two_tables and len(field_refs)==18,'RENEWAL_SCOPE')
        role,allowed=next(iter(perms.items()))
        original_ids=[original_id(roles[role],permission) for permission in allowed]
        def values(items): return ','.join("'"+v.replace("'","''")+"'" for v in items)
        def snapshot():
            statement=f"""SELECT json_agg(json_build_object('id',g."Id",'permission',g."Permission",'subject',g."SubjectId",
                    'connection',g."ConnectionId",'organization',g."OrganizationId",'sites',g."SiteIds",'objects',g."ObjectRefs",'fields',g."FieldRefs",
                    'expiry',g."ExpiresAtUtc",'revoked',g."RevokedAtUtc",'recordHash',md5(to_jsonb(g)::text),
                    'audit',a."Id",'issuedAt',a."OccurredAtUtc",'active',g."RevokedAtUtc" IS NULL AND g."ExpiresAtUtc">now(),
                    'intervalSeconds',extract(epoch from g."ExpiresAtUtc"-a."OccurredAtUtc")) ORDER BY g."Id")
                FROM governance."MappingAuthorizationGrants" g LEFT JOIN governance.audit_records a ON a."Resource"=g."Id"
                AND a."Action"='mapping.grant.change' AND a."Outcome"='allowed' AND a."Id"=md5(g."Id")
                WHERE g."Id" IN ({values([*ids,*original_ids])});"""
            return json.loads(docker('query-renewal-readback','exec',cid,'psql','-XwqAt','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1','-c',statement))
        before=snapshot()
        prior=[r for r in before if r['id'] in original_ids]
        def same_scope(row):
            source = mode=='query'
            return (row['subject']==roles[role] and row['organization']=='org-demo' and row['sites']==['site-a']
                    and row['connection']==(state['connectionId'] if source else None) and sorted(row['objects'])==sorted(objects if source else [])
                    and sorted(row['fields'])==sorted(field_refs if source else []) and row['permission'] in allowed and row['audit'])
        vm.demand(len(prior)==len(allowed) and all(not r['active'] and not r['revoked'] and same_scope(r) for r in prior),'RENEWAL_PREVIOUS_SCOPE')
    result=execution.run(['docker','--context','desktop-linux','exec','-i',cid,'psql','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1','-qAt'],
                         ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-'+mode+'-fixture-grants',stdin=sql,input_key=execution.sha(sql),timeout=18)
    vm.demand(result.returncode==0 and result.stdout.decode().strip()==str(len(ids)),'S1_GRANT_INSERT_'+result.receipt['commandId'])
    if renewal:
        after=snapshot()
        current=[r for r in after if r['id'] in ids]
        vm.demand(len(after)==2*len(allowed) and [r for r in after if r['id'] in original_ids]==prior and len(current)==len(allowed)
                  and all(same_scope(r) and r['active'] and r['intervalSeconds']==ttl_seconds for r in current),'RENEWAL_AFTER_SCOPE')
        record(OUT/('q-grant-renewal-'+result.receipt['commandId']+'.json'),dict(taskId=vm.TASK,runId=vm.RUN,status='CURRENT',ttlSeconds=ttl_seconds,permissions=allowed,
               old=prior,new=current,commandId=result.receipt['commandId']))
    print(json.dumps(dict(taskId=vm.TASK,mode=mode,grantCount=len(ids),commandId=result.receipt['commandId'])))


def source_scan_snapshot():
    fe=json.loads(INDEX.read_bytes())['services']['fe']['id']
    owner=docker('audit-owner','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}}',fe)
    vm.demand(owner==f'{fe} {vm.TASK} {vm.RUN}','S1_AUDIT_OWNER')
    # 只导出正式两种投影的 QueryId，若日志轮替或截断则拒绝复用此前的计数。
    program=r'''/SET_VAR\(enable_sql_cache=false\)/ && /fixture_reader/ && /org_id,site_id,(entity_id|target_id),join_key,/ && /FROM fixture.dmq_(entity|target)/ {
        for(i=1;i<=NF;i++) if($i ~ /^QueryId=/) {v=$i; sub(/^QueryId=/,"",v); print v}
    }'''
    path='/opt/apache-doris/fe/log/fe.audit.log'
    inode=docker('audit-file','exec',fe,'stat','-c','%i',path)
    marker='dmq_audit_fence_'+secrets.token_hex(12)
    vm.demand(sql(fe,'reader',f"SELECT '{marker}';")==marker,'S1_FE_FENCE')
    deadline=time.monotonic()+18
    while time.monotonic()<deadline:
        seen=docker('audit-fence','exec',fe,'awk','-v','marker='+marker,'index($0,marker) && /fixture_reader/ {n++} END {print n+0}',path)
        if seen=='1': break
        time.sleep(.35)
    else: raise ValueError('S1_AUDIT_FLUSH_TIMEOUT')
    ids=docker('business-query-ids','exec',fe,'awk','-F',r' *\| *',program,path).splitlines()
    import re
    vm.demand(bool(ids) and all(re.fullmatch('[a-f0-9-]{32,36}',qid) for qid in ids),'S1_AUDIT_FORMAT')
    return dict(containerId=fe,auditInode=inode,businessQueries=len(ids),queryIdsSha256=execution.sha(execution.encoded(ids)),auditFence=marker)



def expire_disposable_query(query_id,key,result_hash):
    """仅使本次新建、已读回且字节相符的合成查询到期；不改变任何历史查询或生产 TTL。"""
    import uuid
    vm.demand(runtime_binding()['stage']=='s2-doris-expiry' and re.fullmatch('query-[0-9a-f]{32}',query_id)
              and str(uuid.UUID(key))==key and re.fullmatch('[0-9a-f]{64}',result_hash),'TTL_FIXTURE_IDENTITY')
    state=json.loads((OUT/'doris-two-table.json').read_bytes())
    subject=state['subjects']['reader']
    vm.demand(re.fullmatch('[a-f0-9-]{32,36}',subject) and state['latestQuery']['queryId']!=query_id,'TTL_RETAIN_HISTORY')
    cid=live_stack()['platform-pg']
    query=f"""UPDATE semantic_query."Queries" SET "ExpiresAtUtc"=clock_timestamp()-interval '1 second'
        WHERE "Id"='{query_id}' AND "SubjectId"='{subject}' AND "OrganizationId"='org-demo'
        AND "IdempotencyKey"='{key}' AND "ResultHash"='{result_hash}' AND "ExecutionStatus"='COMPLETED'
        AND "CreatedAtUtc">now()-interval '90 seconds' AND "ExpiresAtUtc">now()+interval '23 hours'
        RETURNING "Id";"""
    result=execution.run(['docker','--context','desktop-linux','exec','-i',cid,'psql','-XwqAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','mapping'],
                         ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-disposable-query-expiry',stdin=query.encode(),
                         input_key=execution.sha(query.encode()),timeout=10)
    vm.demand(result.returncode==0 and result.stdout.decode().strip()==query_id,'TTL_FIXTURE_COUNT')
    print(json.dumps(dict(queryId=query_id,commandId=result.receipt['commandId'],expires='PAST')))


def permission_case(action, renewed=False):
    import re
    verb,kind=action.split('-')
    permission={'execute':'data.query.execute','result':'data.query.result.read','evidence':'data.query.evidence.read'}[kind]
    state=json.loads((OUT/'doris-two-table.json').read_bytes())
    subject=state['subjects']['reader']
    vm.demand(state['taskId']==vm.TASK and state['runId']==vm.RUN and state['scope']==dict(organizationId='org-demo',siteIds=['site-a'])
              and re.fullmatch('[a-f0-9-]{32,36}',subject) and re.fullmatch('[a-f0-9]{32}',state['connectionId']),'S2_GRANT_IDENTITY')
    digest=execution.sha(execution.encoded([state['connectionId'],subject,permission]))[:32]
    ids=[f'dmq-s1-{digest}',f'dmq-s2-{digest}']
    if renewed:
        vm.demand(kind=='result' and runtime_binding()['stage']=='ui-s1','S3_REVOKE_SCOPE')
        ids=[('renew-20261119-' if vm.EVIDENCE_RUN==vm.RUN else vm.EVIDENCE_RUN+'-')+ids[1]]
    pred='"Id" IN ('+','.join("'"+id+"'" for id in ids)+') AND "SubjectId"='+repr(subject)+' AND "Permission"='+repr(permission)
    active=OUT/('s2-grant-active-'+kind+'.json')
    cid=live_stack()['platform-pg']
    if verb=='revoke':
        nested_control({'s2-doris-access','s2-doris-revoke-race','ui-s1','s3'})
        vm.demand(not active.exists(),'GRANT_CONTROL_ALREADY_ACTIVE')
        import datetime
        stamp=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')
        row=dict(platform=cid,permission=permission,ids=ids,stamp=stamp)
        record(active,row)
        eligible='"RevokedAtUtc" IS NULL'
        change="'"+stamp+"'::timestamptz"
    else:
        row=json.loads(active.read_bytes())
        vm.demand(row['platform']==cid and ids==row['ids'] and permission==row['permission']
                  and re.fullmatch('[0-9T:+.-]{20,35}',row['stamp']),'GRANT_CONTROL_OWNERSHIP')
        eligible='"RevokedAtUtc"='+repr(row['stamp'])+'::timestamptz'
        change='NULL'
    # 同一事务锁定准确的两条本任务授权，状态或到期变化均阻断，保留原始失败凭据。
    query=f"""BEGIN; SET LOCAL statement_timeout='3s';
      DO $$ DECLARE total int; BEGIN
        UPDATE governance."MappingAuthorizationGrants" SET "RevokedAtUtc"={change} WHERE {pred} AND {eligible} AND "ExpiresAtUtc">now();
        GET DIAGNOSTICS total=ROW_COUNT; IF total<>{len(ids)} THEN RAISE EXCEPTION 'fixture-grant-count'; END IF;
      END $$;
      INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId")
        SELECT md5("Id"||clock_timestamp()::text),now(),'synthetic-query-fixture','mapping.grant.change',"Id",'allowed','dmq-permission','dmq-permission','org-demo',ARRAY['site-a'],NULL
        FROM governance."MappingAuthorizationGrants" WHERE {pred};
      COMMIT;"""
    result=execution.run(['docker','--context','desktop-linux','exec','-i',cid,'psql','-XwqAt','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1'],
                         ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-'+action,stdin=query.encode(),input_key=execution.sha(query.encode()),timeout=12)
    vm.demand(result.returncode==0,'GRANT_CONTROL_'+result.receipt['commandId'])
    row[verb+'CommandId']=result.receipt['commandId']
    if verb=='restore':
        record(OUT/('s2-grant-restored-'+kind+'-'+result.receipt['commandId']+'.json'),row)
        active.unlink()
    else: record(active,row)
    print(json.dumps(dict(action=action,count=len(ids),commandId=result.receipt['commandId'])))


def relation_fixture(restore=False):
    from workflow_doris_mapping_query import REFERENCE_SQL,reference_targets
    from workflow_doris_s0_fixture import stress_original
    state=json.loads((OUT/'doris-two-table.json').read_bytes())
    vm.demand(len(state['mappingRelease']['manifest']['mapping']['entities'])==2 and state['mappingReceipt']['activationId']
              and json.loads(HOST.read_bytes())['status']=='EXITED','S2_ACTIVATION_REQUIRED')
    fe=live_stack()['fe']
    active=OUT/'s2-boundary-active.json'
    where="org_id='org-demo' AND site_id='site-a'"
    old_ids=('T1','T2','T3')
    added=('T4','T5','T6')
    actual=sql(fe,'reader','SELECT target_id FROM fixture.dmq_target ORDER BY target_id;').splitlines()
    original=stress_original(fe,'dmq_target','target_id',old_ids)
    if restore:
        previous=json.loads(active.read_bytes())
        vm.demand(previous['fe']==fe and previous['before']==original and actual==list(old_ids+added),'S2_BOUNDARY_RESTORE_INPUT')
        sql(fe,'root',"DELETE FROM fixture.dmq_target WHERE "+where+" AND target_id IN ('T4','T5','T6');")
        vm.demand(sql(fe,'reader','SELECT target_id FROM fixture.dmq_target ORDER BY target_id;').splitlines()==list(old_ids)
                  and stress_original(fe,'dmq_target','target_id',old_ids)==original,'S2_BOUNDARY_RESTORE')
        previous.update(status='RESTORED',after=original)
        record(OUT/('s2-boundary-restored-'+secrets.token_hex(6)+'.json'),previous)
        active.unlink()
        print('S2_BOUNDARY_RESTORED')
        return
    vm.demand(not active.exists() and actual==list(old_ids),'S2_BASELINE')
    baseline=dict(fe=fe,activation=state['mappingReceipt']['activationId'],before=original,added=added,status='PREPARED')
    record(active,baseline)
    # T5 和 T6 与实体区间左右端点恰好相接；NULL 只属于独立的发布后查询与拒绝场景。
    sql(fe,'root',"""INSERT INTO fixture.dmq_target VALUES
        ('org-demo','site-a','T4',NULL,'2026-11-01','2026-12-01','2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456'),
        ('org-demo','site-a','T5',1.000,'2026-10-01','2026-11-01','2026-10-17 12:00:00.123456','2026-10-17 12:00:01.123456'),
        ('org-demo','site-a','T6',1.000,'2026-12-01','2027-01-01','2026-12-17 12:00:00.123456','2026-12-17 12:00:01.123456');""")
    entity=sql(fe,'reader',"SELECT org_id,site_id,join_key,valid_from,valid_to FROM fixture.dmq_entity WHERE "+where+" AND entity_id='E1';").split('\t')
    targets=[r.split('\t') for r in sql(fe,'reader',"SELECT target_id,org_id,site_id,join_key,valid_from,valid_to FROM fixture.dmq_target ORDER BY target_id;").splitlines()]
    for r in targets:
        if r[3]=='NULL': r[3]=None
    ref=reference_targets(entity,targets)
    server=sql(fe,'reader',REFERENCE_SQL+';').splitlines()
    vm.demand(len(targets)==6 and server==ref==['T1','T2'] and original==stress_original(fe,'dmq_target','target_id',old_ids),'S2_INDEPENDENT_TARGETS')
    baseline.update(status='ACTIVE_VERIFIED',referenceIds=server,coefficientIds=ref,rows=targets,scopeEntity=entity)
    record(active,baseline)
    record(OUT/('s2-boundary-reference-'+secrets.token_hex(6)+'.json'),baseline)
    print('S2_BOUNDARY_REFERENCE',','.join(server))


def scoped_state_fixture(action, collision=False):
    """受限正常数据的第二实体，以及源数据库既有单条 SELECT 许可的准确撤销与恢复。"""
    from workflow_doris_s0_fixture import STRESS, stress_original
    vm.demand(not STRESS.exists(), 'STATE_CASE_NOT_PRESSURE')
    fe=live_stack()['fe']
    path=OUT/'s2-source-states-active.json'
    scope="org_id='org-demo' AND site_id='site-a'"
    if action=='seed':
        vm.demand(not path.exists() and sql(fe,'reader','SELECT entity_id FROM fixture.dmq_entity ORDER BY entity_id;')=='E1','STATES_BASELINE')
        before=stress_original(fe,'dmq_entity','entity_id',['E1'])
        grants=execution.sha(sql(fe,'reader','SHOW GRANTS;').encode())
        row=dict(fe=fe,run=vm.RUN,scope=scope,original=before,grants=grants,attempt=secrets.token_hex(6),acl='original')
        record(path,row)
        join = '1.00' if collision else '2.00'
        sql(fe,'root',f"""INSERT INTO fixture.dmq_entity VALUES ('org-demo','site-a','E2',{join},1.00,'K','2026-11-01','2026-12-01','2026-11-17 12:00:00.123457','2026-11-17 12:00:01.123457');""")
        vm.demand(sql(fe,'reader','SELECT entity_id FROM fixture.dmq_entity ORDER BY entity_id;').splitlines()==['E1','E2'],'STATES_SEEDED')
        if collision:
            row['projectedIds'] = sql(fe,'reader',"SELECT join_key,COUNT(DISTINCT entity_id) FROM fixture.dmq_entity WHERE "+scope+" GROUP BY join_key;")
            vm.demand(row['projectedIds'].split()==['1.00','2'],'COLLIDING_KEYS_PRECONDITION')
            row['matchingParents'] = sql(fe,'reader',"SELECT t.target_id,COUNT(DISTINCT e.entity_id) FROM fixture.dmq_target t JOIN fixture.dmq_entity e ON t.org_id=e.org_id AND t.site_id=e.site_id AND t.join_key=e.join_key AND t.valid_from<e.valid_to AND t.valid_to>e.valid_from WHERE t.org_id='org-demo' AND t.site_id='site-a' GROUP BY t.target_id ORDER BY t.target_id;").splitlines()
            vm.demand(row['matchingParents']==['T1\t2','T2\t2'],'OVERLAPPING_PARENTS_PRECONDITION')
            record(path,row)
        return
    row=json.loads(path.read_bytes())
    vm.demand(row['fe']==fe and row['run']==vm.RUN and row['scope']==scope,'STATES_OWNER')
    existing=execution.sha(sql(fe,'reader','SHOW GRANTS;').encode())
    if action=='deny':
        vm.demand(existing==row['grants'] and row['acl']=='original','STATES_GRANT_CHANGED')
        row['acl']='revoking'
        record(path,row)
        sql(fe,'root',"REVOKE SELECT_PRIV ON internal.fixture.* FROM 'fixture_reader'@'%';")
        row['denied']=execution.sha(sql(fe,'reader','SHOW GRANTS;').encode())
        vm.demand(row['denied']!=row['grants'],'STATES_DENY')
        row['acl']='denied'
        record(path,row)
        return
    if row['acl']!='original' and existing!=row['grants']:
        vm.demand(row.get('denied')==existing,'STATES_GRANT_RESTORE_OWNER')
        sql(fe,'root',"GRANT SELECT_PRIV ON internal.fixture.* TO 'fixture_reader'@'%';")
    vm.demand(execution.sha(sql(fe,'reader','SHOW GRANTS;').encode())==row['grants'],'STATES_GRANTS_RESTORE')
    row['acl']='original'
    record(path,row)
    if action=='allow': return
    keys=sql(fe,'reader','SELECT entity_id FROM fixture.dmq_entity ORDER BY entity_id;').splitlines()
    vm.demand(keys in (['E1'],['E1','E2']) and stress_original(fe,'dmq_entity','entity_id',['E1'])==row['original'],'STATES_RESTORE_OWNER')
    if 'E2' in keys:
        sql(fe,'root',"DELETE FROM fixture.dmq_entity WHERE "+scope+" AND entity_id='E2';")
    vm.demand(sql(fe,'reader','SELECT entity_id FROM fixture.dmq_entity;')=='E1' and stress_original(fe,'dmq_entity','entity_id',['E1'])==row['original'],'STATES_RESTORE')
    row.update(status='RESTORED',after=row['original'])
    record(OUT/('s2-source-states-'+row['attempt']+'-restored.json'),row)
    path.unlink()


def fanout_fixture(action):
    """在已发布任务夹具中独立枚举十与十一条边，按准确复合键复原。"""
    from workflow_doris_mapping_query import REFERENCE_SQL
    from workflow_doris_s0_fixture import stress_original
    state = json.loads((OUT/'doris-two-table.json').read_bytes())
    vm.demand(state['taskId'] == vm.TASK and state['runId'] == vm.RUN and state['mappingReceipt']['activationId'], 'FANOUT_ACTIVATION')
    fe = live_stack()['fe']
    current = OUT/'s2-fanout-active.json'
    original = ['T1', 'T2', 'T3']
    added = ['Fan' + str(i) for i in range(1, 10)]
    scope = "org_id='org-demo' AND site_id='site-a'"
    def current_keys():
        return sql(fe, 'reader', 'SELECT target_id FROM fixture.dmq_target ORDER BY target_id;').splitlines()
    before = stress_original(fe, 'dmq_target', 'target_id', original)
    if action not in ('restore',): nested_control({'s2-doris-fanout'})
    if action == 'ten':
        vm.demand(not current.exists() and current_keys() == original, 'FANOUT_BASELINE')
        ledger = dict(taskId=vm.TASK, runId=vm.RUN, attempt=secrets.token_hex(6), fe=fe,
                      activation=state['mappingReceipt']['activationId'], before=before, added=added)
        record(current, ledger)
    else:
        ledger = json.loads(current.read_bytes())
        vm.demand(ledger['fe'] == fe and ledger['added'] == added and ledger['before'] == before
                  and ledger['activation'] == state['mappingReceipt']['activationId'], 'FANOUT_OWNER')
    if action == 'restore':
        keys = current_keys()
        vm.demand(set(original) <= set(keys) <= set(original + added), 'FANOUT_RESTORE_KEYS')
        owned = [key for key in added if key in keys]
        if owned:
            literals = ','.join(repr(key) for key in owned)
            sql(fe, 'root', f'DELETE FROM fixture.dmq_target WHERE {scope} AND target_id IN ({literals});')
        after = stress_original(fe, 'dmq_target', 'target_id', original)
        vm.demand(current_keys() == original and before == after, 'FANOUT_RESTORE')
        ledger.update(after=after, status='RESTORED', removed=owned)
        record(OUT/('s2-fanout-' + ledger['attempt'] + '-restored.json'), ledger)
        current.unlink()
        return ledger
    if action == 'eleven':
        vm.demand(current_keys() == sorted(original + added[:8]), 'FANOUT_TEN_REQUIRED')
    new_ids = added[:8] if action == 'ten' else added[8:]
    values = ','.join("('org-demo','site-a'," + repr(key) + ",1.000,'2026-11-01','2026-12-01','2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456')" for key in new_ids)
    sql(fe, 'root', 'INSERT INTO fixture.dmq_target VALUES ' + values + ';')
    expected = sorted(original[:2] + (added[:8] if action == 'ten' else added))
    independent = sql(fe, 'reader', REFERENCE_SQL + ';').splitlines()
    vm.demand(independent == expected and current_keys() == sorted(expected+['T3']), 'FANOUT_SQL_REFERENCE')
    ledger[action] = independent
    record(current, ledger)
    return dict(phase=action, expected=expected)



def sentinel_fixture(restore=False, renewed=False):
    """一次独立查询哨兵，只写入本次登记的 100 个复合键。"""
    from workflow_doris_s0_fixture import STRESS, STRESS_TABLES, stress_original, tier_capacity
    active = OUT/'s2-sentinel-active.json'
    done = OUT/('s2-sentinel-101-renewed-restored.json' if renewed else 's2-sentinel-101-restored.json')
    state = json.loads(INDEX.read_bytes())
    fe = live_stack()['fe']
    vm.demand(not STRESS.exists() and not done.exists(), 'SENTINEL_ONE_CASE')
    def hashes():
        return {table:stress_original(fe,table,key,original) for table,key,original in STRESS_TABLES}
    def order():
        return sql(fe,'reader','SELECT org_id,site_id,entity_id FROM fixture.dmq_entity ORDER BY event_at,entity_id,org_id,site_id;').splitlines()
    scope = 'org-demo\tsite-a\t'
    if not restore:
        vm.demand(not active.exists() and order()==[scope+'E1'],'SENTINEL_INITIAL_KEYS')
        vm.demand(sql(fe,'reader','SELECT COUNT(*) FROM fixture.dmq_target;')=='3','SENTINEL_TARGET_BASELINE')
        prefix = 'S'+secrets.token_hex(6)
        keys = [prefix+f'{i:03}' for i in range(100)]
        row = dict(taskId=vm.TASK,runId=vm.RUN,fe=fe,prefix=prefix,keys=keys,scope=['org-demo','site-a'],
                   original=hashes(),resources=tier_capacity(state),status='INTENT')
        record(active,row)
        values = ','.join("('org-demo','site-a','"+key+"',1.00,7.20,'K','2026-11-01','2026-12-01','2026-11-18','2026-11-18')" for key in keys)
        sql(fe,'root','INSERT INTO fixture.dmq_entity VALUES '+values+';')
        actual = order()
        vm.demand(actual==[scope+k for k in ['E1',*keys]] and hashes()==row['original'],'SENTINEL_101_KEYS')
        row.update(expectedPrefix=['E1',*keys[:-1]],sentinel=keys[-1],entityRows=101,targetRows=3,status='SEEDED')
        record(active,row)
        return
    row = json.loads(active.read_bytes())
    keys = row['keys']
    vm.demand(row['fe']==fe and row['taskId']==vm.TASK and row['runId']==vm.RUN and row['scope']==['org-demo','site-a']
              and re.fullmatch('S[0-9a-f]{12}',row['prefix']) and keys==[row['prefix']+f'{i:03}' for i in range(100)],'SENTINEL_OWNER')
    current = set(order())
    vm.demand(scope+'E1' in current and current<={scope+key for key in ['E1',*keys]} and hashes()==row['original'],'SENTINEL_RESTORE_OWNER')
    values = ','.join("'"+k+"'" for k in keys)
    sql(fe,'root',"DELETE FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id IN ("+values+");")
    row['after'] = hashes()
    vm.demand(order()==[scope+'E1'] and sql(fe,'reader','SELECT COUNT(*) FROM fixture.dmq_target;')=='3' and row['after']==row['original'],'SENTINEL_RESTORED')
    row.update(status='RESTORED',entityRowsAfter=1,targetRowsAfter=3)
    record(done,row)
    active.unlink()


def cancellation_case(prepared, admission=False):
    from workflow_doris_s0_fixture import STRESS,stress_fixture
    vm.demand(not STRESS.exists(),'S2_SEPARATE_STRESS_REQUIRED')
    browser_test('s2-doris-ready',prepared,'stress')
    try:
        stress_fixture(platform=True)
        browser_test('s2-doris-admission-cancel' if admission else 's2-doris-cancel',prepared,'pressure-running')
    finally:
        if STRESS.exists(): stress_fixture(restore=True,platform=True)


def graduated_cancel(prepared):
    """每级独立核资源、加载实体、实测固定 SELECT 并准确复原。满足自然窗口即停止扩容。"""
    import datetime
    from workflow_doris_s0_fixture import STRESS, ENTITY_TIERS, stress_fixture
    ledger = dict(taskId=vm.TASK,runId=vm.RUN,attempt=secrets.token_hex(6),stages=[],minimumWindowMs=160)
    path = OUT/('s2-entity-tiers-'+ledger['attempt']+'.json')
    record(path,ledger)
    for tier in ENTITY_TIERS:
        vm.demand(not STRESS.exists(),'S2_SEPARATE_STRESS_REQUIRED')
        stage = dict(entityRows=tier,targetRows=3)
        ledger['stages'].append(stage)
        record(path,ledger)
        browser_test('s2-doris-ready',prepared,'stress')
        try:
            stress_fixture(platform=True,entity_rows=tier)
            fixture = json.loads(STRESS.read_bytes())
            stage['fixture']=fixture['attempt']
            before = set(OUT.glob('browser-s2-doris-cancel-window-*.json'))
            browser_test('s2-doris-cancel-window',prepared,'pressure-running')
            new = set(OUT.glob('browser-s2-doris-cancel-window-*.json'))-before
            vm.demand(len(new)==1,'TIER_WITNESS_COUNT')
            report = new.pop()
            observed = json.loads(report.read_bytes())['naturalWindow']
            vm.demand(observed['stress']['attempt']==fixture['attempt'] and observed['stress']['rowsByTable']==
                      {'dmq_entity':tier,'dmq_target':3},'TIER_WITNESS_BINDING')
            events = observed['beEvents']
            start,end = [datetime.datetime.strptime(next(e['beUtc'] for e in events if e['kind']==kind),'%Y%m%d %H:%M:%S.%f')
                         for kind in ('registered','context_end')]
            stage.update(windowMs=(end-start).total_seconds()*1000,sourceQueryId=observed['sourceQueryId'],
                         naturalReport=report.name,queryId=observed['queryId'])
            vm.demand(stage['windowMs']>0,'TIER_WITNESS_CLOCK')
            if stage['windowMs']>=ledger['minimumWindowMs']:
                stage['formalAttempt']=True
                record(path,ledger)
                browser_test('s2-doris-cancel',prepared,'pressure-running')
                stage['formalBrowserPassed']=True
                break
        finally:
            if STRESS.exists():
                attempt=json.loads(STRESS.read_bytes())['attempt']
                stress_fixture(restore=True,platform=True)
                stage['restoration']='s0-stress-fixture-'+attempt+'-restored.json'
            record(path,ledger)
    ledger['status']='REVIEW_REQUIRED' if ledger['stages'][-1].get('formalBrowserPassed') else 'NO_GO_WINDOW'
    record(path,ledger)
    print(path.relative_to(ROOT),ledger['status'])


def ddl_race_fixture(action):
    """仅对登记的合成目标列作可逆改名，按原 tablet、DDL 及行摘要恢复。"""
    import csv
    import fcntl
    import hashlib
    from workflow_doris_s0_fixture import SHAPE, STRESS, ready_source, stress_original, sync_directory
    state = json.loads(INDEX.read_bytes())
    fe = state['services']['fe']['id']
    path = OUT/'s2-ddl-race-active.json'
    def ddl():
        return sql(fe,'root','SHOW CREATE TABLE fixture.dmq_target;')
    def tablet():
        rows = list(csv.DictReader(sql(fe,'root','SHOW TABLETS FROM fixture.dmq_target;',True).splitlines(),delimiter='\t'))
        vm.demand(len(rows)==1 and rows[0]['TabletId'].isdigit(),'DDL_TARGET_ID')
        return rows[0]['TabletId']
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()
    def rows_hash():
        return stress_original(fe,'dmq_target','target_id',('T1','T2','T3'))
    original_name = '`join_key`'
    changed_name = '`dmq_ac05_join_key`'
    if action=='arm':
        vm.demand(not any(p.exists() for p in (path,SHAPE,STRESS,OUT/'s0-fixed-fixture-active.json',OUT/'s2-fanout-active.json',OUT/'s2-source-states-active.json')),'DDL_FIXTURE_BUSY')
        stress_resources(state,platform=True)
        ready_source(fe)
        original = ddl()
        vm.demand(original.count(original_name)==1 and changed_name not in original,'DDL_BASELINE_COLUMN')
        baseline = rows_hash()
        vm.demand(baseline=='4fce66991c1a560ee3acc8de573c1077e5f669f68971ad08d55c06e50364191f','DDL_BASELINE_ROWS')
        row = dict(taskId=vm.TASK,runId=vm.RUN,attempt=secrets.token_hex(8),fe=fe,tablet=tablet(),
                   before=digest(original),changed=digest(original.replace(original_name,changed_name)),rows=baseline)
        with path.open('x') as handle:
            json.dump(row,handle)
            handle.flush()
            os.fsync(handle.fileno())
        sync_directory(path.parent)
        return
    with path.open() as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        vm.demand(path.exists() and os.path.samestat(path.stat(),os.fstat(guard.fileno())),'DDL_ATTEMPT_CLOSED')
        row = json.load(guard)
        vm.demand((row['taskId'],row['runId'],row['fe'],row['tablet'])==(vm.TASK,vm.RUN,fe,tablet()),'DDL_RESOURCE_DRIFT')
        current = digest(ddl())
        if action=='rename':
            host = json.loads(HOST.read_bytes())
            vm.demand(host['stage']=='s2-doris-ddl-race' and host['taskId']==vm.TASK and host['runId']==vm.RUN
                      and host['status']=='READY' and vm.host('ps','-p',str(host['pid']),'-o','lstart=')==host['processStart']
                      and current==row['before'],'DDL_RACE_STAGE')
            sql(fe,'root','ALTER TABLE fixture.dmq_target RENAME COLUMN join_key dmq_ac05_join_key;')
            vm.demand(digest(ddl())==row['changed'],'DDL_RENAME_POST')
            return
        vm.demand(action=='restore' and current in (row['before'],row['changed']),'DDL_UNKNOWN_SHAPE')
        if current==row['changed']:
            sql(fe,'root','ALTER TABLE fixture.dmq_target RENAME COLUMN dmq_ac05_join_key join_key;')
        vm.demand(digest(ddl())==row['before'] and tablet()==row['tablet'] and rows_hash()==row['rows'],'DDL_RESTORE_POST')
        row.update(status='RESTORED',observedChanged=current==row['changed'])
        record(OUT/('s2-ddl-race-'+row['attempt']+'-restored.json'),row)
        path.unlink()
        sync_directory(path.parent)



def runtime_race_test(case):
    """只接收当前合成 Cookie 的内存管道，按已绑定 AgentTests 运行一次已登记的正式在途竞争。"""
    from workflow_m2_evidence import mtp
    frozen = json.loads(SNAPSHOT.read_bytes())
    active = runtime_binding()
    stage, method = {
        'overlap': ('s2-doris-overlap', 'DorisSourceOverlapsVerifiedCancellation'),
        'aba': ('s2-doris-aba', 'DorisActivationRevisionRejectsInflightQuery'),
        'revoke': ('s2-doris-revoke-race', 'DorisRevocationRejectsInflightQuery'),
        'session': ('s2-doris-session-race', 'DorisExpiredSessionRejectsInflightQuery'),
        'ddl': ('s2-doris-ddl-race', 'DorisTableChangeRejectsInflightRows'),
        'rotate': ('s2-doris-rotate-race', 'DorisRotatedCredentialRejectsInflightQuery'),
        'deadline': ('s2-doris-deadline', 'DorisLockedCommitHonorsRealDeadline'),
        'lock': ('s2-doris-short-lock', 'DorisCommitRejectsPlatformLockTimeout'),
        'disconnect': ('s2-doris-disconnect', 'DorisDroppedConnectionDiscardsUnverifiedRows'),
        'batch': ('s2-doris-batch-binding', 'CancelRequiresSingleVerifiedReleaseBatch')
    }[case]
    vm.demand(active['stage'] == stage and active['snapshotId'] == frozen['snapshotId'], 'ABA_HOST_BINDING')
    binding = build.validate('agent', vm.TASK)
    vm.demand(binding['inputKey'] == build.validate('api', vm.TASK)['inputKey'], 'ABA_INPUT_BINDING')
    dotnet = frozen['environment']['dotnet']
    dll = ROOT / Path(build.TARGETS['agent']).parent / 'bin/Debug/net10.0/OntologyPlatform.AgentTests.dll'
    method = 'OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.' + method
    envelope = sys.stdin.buffer.read(65537)
    vm.demand(0 < len(envelope) <= 65536, 'ABA_SESSION_INPUT')
    env = dict(PATH=os.environ['PATH'], ASPNETCORE_ENVIRONMENT='Development', G4__SourceCaPath=str(DIRECTORY/'tls/ca.pem'),
               G4_DORIS_EVIDENCE_RUN=vm.EVIDENCE_RUN,G4_QUERY_RUNTIME_TEST=vm.TASK+':'+vm.RUN, DOTNET_GCHeapHardLimit='0x18000000', DOTNET_CLI_TELEMETRY_OPTOUT='1')
    result = execution.run([dotnet, str(dll), '--filter', 'FullyQualifiedName='+method, '--minimum-expected-tests', '1', '--no-ansi', '--progress', 'off', '--results-directory', str(OUT/'aba-results')],
                           ROOT, task=vm.TASK, run_id=vm.EVIDENCE_RUN, stage='dmq-inflight-'+case, environment=env,
                           input_key=execution.sha(execution.encoded(binding)), stdin=envelope, timeout=25)
    passed = mtp(result.stdout + result.stderr, 1) if not result.returncode else 0
    summary = dict(commandId=result.receipt['commandId'], input=binding, exitCode=result.returncode, passed=passed)
    record(OUT/(('s2-'+case+'-mtp-')+summary['commandId']+'.json'), summary)
    vm.demand(result.returncode == 0 and passed == 1, 'ABA_MTP_'+summary['commandId'])
    print(json.dumps(summary))


S3_COMPAT_CASES=[
    ('connections','(FullyQualifiedName~.PgAdapterTests.&FullyQualifiedName!~RealFixturePreservesAuthorizedMetadata)|FullyQualifiedName~.DorisAdapterTests.|FullyQualifiedName~.SourceDispatcherTests.|FullyQualifiedName~.G4QuerySourceTests.',20),
    ('connections','FullyQualifiedName~.DorisFixtureSecurityTests.BadAuthenticationAndCaCannotReadCatalog|FullyQualifiedName~.DorisFixtureSecurityTests.WrongSanIsRejectedByActualHandshake|FullyQualifiedName~.DorisMappingQueryTests.RealDriverReadsFixedSource',4),
    ('query','FullyQualifiedName~.G4QueryTests.',12),
    ('wire','FullyQualifiedName~.G4QueryWireTests.',6)]


def s3_compatibility(prepared):
    """在已就绪的本任务构建和源上复用 M2/M4 的准确测试；不启动历史栈。"""
    import tempfile
    from workflow_m2_evidence import mtp
    path=execution.ordinary(Path(prepared).absolute())
    vm.demand(path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'S3_COMPAT_ENV_PATH')
    dep=json.loads(path.read_bytes())
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'S3_COMPAT_PREPARE')
    live_stack()
    # 原 M2 测试只认识既有目录布局，三个精确私有链接在用例结束时随专用目录关闭。
    with tempfile.TemporaryDirectory(prefix='s3-m2-',dir=HOME_DIR) as temporary:
        layout=Path(temporary)
        (layout/'tls').mkdir(mode=0o700)
        (layout/'private').mkdir(mode=0o700)
        for link,source in [('private/reader.pass',DIRECTORY/'reader.pass'),('tls/ca.pem',DIRECTORY/'tls/ca.pem'),
                            ('tls/wrong-ca.pem',HOME_DIR/'platform-pg/server.crt')]:
            (layout/link).symlink_to(execution.ordinary(source))
        for target,expression,minimum in S3_COMPAT_CASES:
            binding=build.validate(target,vm.TASK)
            project=Path(build.TARGETS[target])
            dll=ROOT/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
            env=dict(dep['environment'],G4_DORIS_TEST_RUNTIME=str(layout),DMQ_S0_SOURCE=str(DIRECTORY))
            result=execution.run([dep['dotnet'],str(dll),'--filter',expression,'--minimum-expected-tests',str(minimum),'--no-ansi',
                                  '--progress','off','--results-directory',str(OUT/'s3-compat-results')],ROOT,task=vm.TASK,run_id=vm.EVIDENCE_RUN,
                                 stage='dmq-s3-compat-'+target,environment=env,input_key=execution.sha(execution.encoded(binding)),timeout=45)
            count=mtp(result.stdout+result.stderr,minimum) if result.returncode==0 else 0
            row=dict(target=target,filter=expression,input=binding,commandId=result.receipt['commandId'],exitCode=result.returncode,passed=count)
            record(OUT/('s3-compat-'+row['commandId']+'.json'),row)
            vm.demand(count>=minimum,'S3_COMPAT_'+row['commandId'])
            print(json.dumps(row))


def semantic_batch_regression(prepared):
    """复用本任务当前六项准确设施与已构建 MTP，只运行新请求内批次的四个反例及正例。"""
    from workflow_m2_evidence import mtp
    path = execution.ordinary(Path(prepared).absolute())
    vm.demand(path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'SEM_PREPARE_PATH')
    dep = json.loads(path.read_bytes())
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'SEM_PREPARE')
    live_stack()
    binding = build.validate('semantic',vm.TASK)
    dll = ROOT/Path(build.TARGETS['semantic']).parent/'bin/Debug/net10.0/OntologyPlatform.SemanticTests.dll'
    method = 'OntologyPlatform.SemanticTests.VerifiedReadTests.VerifiedBatchRequiresActualComparedGraphsAndShacl'
    env = dict(dep['environment'],G2_SEM_JENA_ORIGIN='http://127.0.0.1:15645',DOTNET_GCHeapHardLimit='0x18000000')
    result = execution.run([dep['dotnet'],str(dll),'--filter','FullyQualifiedName='+method,'--minimum-expected-tests','4',
                            '--no-ansi','--progress','off','--results-directory',str(OUT/'verified-batch-results')],ROOT,
                           task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-verified-batch-sem',environment=env,input_key=execution.sha(execution.encoded(binding)),timeout=25)
    count = mtp(result.stdout+result.stderr,4) if not result.returncode else 0
    row = dict(method=method,input=binding,commandId=result.receipt['commandId'],passed=count,exitCode=result.returncode)
    record(OUT/('verified-batch-sem-'+row['commandId']+'.json'),row)
    vm.demand(result.returncode==0 and count==4,'SEM_BATCH_MTP_'+row['commandId'])
    print(json.dumps(row))


def pg_golden(prepared):
    from workflow_m2_evidence import mtp
    path=execution.ordinary(Path(prepared).absolute())
    vm.demand(path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'PG_GOLDEN_ENV_PATH')
    dep=json.loads(path.read_bytes())
    binding=build.validate('query',vm.TASK)
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'PG_GOLDEN_PREPARE')
    dll=ROOT/'backend/tests/OntologyPlatform.QueryTests/bin/Debug/net10.0/OntologyPlatform.QueryTests.dll'
    method='OntologyPlatform.QueryTests.G4QueryTests.HistoricalPgReleaseAndResultKeepCanonicalBytes'
    result=execution.run([dep['dotnet'],str(dll),'--filter','FullyQualifiedName='+method,'--minimum-expected-tests','2',
                         '--no-ansi','--progress','off','--results-directory',str(OUT/'pg-golden-results')],ROOT,
                         task=vm.TASK,run_id=vm.EVIDENCE_RUN,stage='dmq-pg-golden',environment=dep['environment'],input_key=execution.sha(execution.encoded(binding)),timeout=25)
    passed=mtp(result.stdout+result.stderr,2) if not result.returncode else 0
    row=dict(method=method,input=binding,commandId=result.receipt['commandId'],passed=passed,exitCode=result.returncode)
    record(OUT/('pg-golden-test-'+row['commandId']+'.json'),row)
    vm.demand(passed==2 and result.returncode==0,'PG_GOLDEN_TEST_'+row['commandId'])
    print(json.dumps(row))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['s3-compat','s3-web-typecheck','s3-web-lint','s3-web-unit','s3-web-build','prepare','render','start','configure','freeze','pg-golden','semantic-batch','s2-activation-shape','s2-renew-query-grants','s2-renewed-sentinel','s2-overlap-case','overlap-test','s2-graduated-cancel','s2-cancel-case','s2-admission-case','state-fixture','expire-disposable','session-test','revoke-test','aba-test','ddl-test','rotate-test','deadline-test','lock-test','disconnect-test','batch-test','ddl-fixture','fanout','permission','s2-boundary','s2-restore','mapping-grants','query-grants','s2-mapping-grants','s2-query-grants',*BROWSER])
    parser.add_argument('--prepared')
    parser.add_argument('--stale-expectation',choices=['activation','catalog'])
    parser.add_argument('--profile-evidence',action='store_true')
    parser.add_argument('--tied-event',action='store_true')
    parser.add_argument('--ddl-action',choices=['arm','rename','restore'])
    parser.add_argument('--query-identity',nargs=3,metavar=('QUERY','KEY','HASH'))
    parser.add_argument('--permission',choices=[f'{v}-{k}' for v in ('revoke','restore') for k in ('execute','result','evidence')])
    parser.add_argument('--fanout', choices=['ten','eleven','restore'])
    parser.add_argument('--state-operation',choices=['seed','deny','allow','restore'])
    args=parser.parse_args()
    vm.demand(not args.tied_event or args.profile_evidence,'TIED_EVENTS_REQUIRE_PROFILE')
    vm.demand(not args.stale_expectation or args.stage=='s2-doris-ready','STALE_EXPECTATION_SCOPE')
    vm.demand(not args.profile_evidence or args.stage=='s2-overlap-case','PROFILE_STAGE_SCOPE')
    if args.stage.startswith('s3-web-'):
        raise SystemExit(s3_web_check(args.stage.removeprefix('s3-web-'),args.prepared))
    if args.stage == 's2-doris-fanout':
        vm.demand(not (OUT/'s2-fanout-active.json').exists(), 'FANOUT_ALREADY_ACTIVE')
        try:
            browser_test(args.stage, args.prepared)
        finally:
            if (OUT/'s2-fanout-active.json').exists(): fanout_fixture('restore')
    elif args.stage=='s2-renew-query-grants': synthetic_grants('query',True,renewal=True)
    elif args.stage in ('s2-doris-sentinel','s2-renewed-sentinel'):
        renewed=args.stage=='s2-renewed-sentinel'
        original=OUT/'s2-sentinel-101-restored.json'
        if renewed:
            reviewed=ROOT/'docs/evidence'/vm.TASK/vm.RUN/'s2-timing'/original.name
            vm.demand(reviewed.read_bytes()==original.read_bytes() and any(OUT.glob('q-grant-renewal-*.json')),'SENTINEL_RENEWED_PREREQUISITE')
        done=OUT/'s2-sentinel-101-renewed-restored.json' if renewed else original
        vm.demand(not (OUT/'s2-sentinel-active.json').exists() and not done.exists(),'SENTINEL_ONE_CASE')
        browser_test('s2-doris-authority-control',args.prepared,'sentinel')
        try:
            sentinel_fixture(renewed=renewed)
            browser_test('s2-doris-sentinel',args.prepared,'sentinel-running')
        finally:
            if (OUT/'s2-sentinel-active.json').exists(): sentinel_fixture(restore=True,renewed=renewed)
    elif args.stage=='s2-overlap-case':
        from workflow_doris_s0_fixture import STRESS, stress_fixture
        vm.demand(not STRESS.exists(),'OVERLAP_FIXTURE_IN_USE')
        browser_test('s2-doris-authority-control',args.prepared,'stress')
        try:
            stress_fixture(platform=True,entity_rows=4194304,tied_event=args.tied_event)
            if args.profile_evidence:
                from doris_query_profile_witness import reference
                reference(minimum_first_fragment_ms=50 if args.tied_event else None)
            browser_test('s2-doris-overlap',args.prepared,'pressure-running')
        finally:
            if STRESS.exists():
                try:
                    if args.profile_evidence:
                        from doris_query_profile_witness import recover_window
                        recover_window(OUT,json.loads(INDEX.read_bytes())['services']['fe']['id'],
                                       json.loads(STRESS.read_bytes())['attempt'])
                finally:
                    stress_fixture(restore=True,platform=True)
    elif args.stage=='expire-disposable': expire_disposable_query(*args.query_identity)
    elif args.stage=='state-fixture':
        if args.state_operation=='seed': browser_test('s2-doris-ready',args.prepared,'staged')
        scoped_state_fixture(args.state_operation)
    elif args.stage in ('s2-doris-states','s2-doris-cardinality'):
        vm.demand(not (OUT/'s2-source-states-active.json').exists(),'STATES_ALREADY_ACTIVE')
        browser_test('s2-doris-ready',args.prepared,'staged')
        try:
            scoped_state_fixture('seed',collision=args.stage=='s2-doris-cardinality')
            browser_test(args.stage,args.prepared)
            if args.stage=='s2-doris-cardinality': browser_test('s2-doris-identity',args.prepared)
        finally:
            if (OUT/'s2-source-states-active.json').exists(): scoped_state_fixture('restore')
    elif args.stage=='s2-doris-revoke-race':
        ledger=OUT/'s2-grant-active-execute.json'
        vm.demand(not ledger.exists(),'REVOKE_RACE_ALREADY_ACTIVE')
        try: browser_test(args.stage,args.prepared)
        finally:
            if ledger.exists(): permission_case('restore-execute')
    elif args.stage=='ddl-fixture':
        if args.ddl_action=='arm': browser_test('s2-doris-ready',args.prepared,'staged')
        ddl_race_fixture(args.ddl_action)
    elif args.stage=='s2-doris-ddl-race':
        browser_test('s2-doris-ready',args.prepared,'staged')
        ddl_race_fixture('arm')
        try: browser_test(args.stage,args.prepared)
        finally:
            if (OUT/'s2-ddl-race-active.json').exists(): ddl_race_fixture('restore')
    elif args.stage=='s3-compat': s3_compatibility(args.prepared)
    elif args.stage in BROWSER: browser_test(args.stage,args.prepared,counterexample=args.stale_expectation)
    elif args.stage in ('s2-boundary','s2-restore'):
        if args.stage=='s2-boundary': browser_test('s2-doris-ready',args.prepared,'staged')
        relation_fixture(args.stage=='s2-restore')
    elif args.stage in ('aba-test','revoke-test','session-test','ddl-test','rotate-test','deadline-test','lock-test','disconnect-test','batch-test'): runtime_race_test(args.stage.removesuffix('-test'))
    elif args.stage=='fanout': print(json.dumps(fanout_fixture(args.fanout)))
    elif args.stage=='permission': permission_case(args.permission)
    elif args.stage in ('s2-cancel-case','s2-admission-case'): cancellation_case(args.prepared,args.stage=='s2-admission-case')
    elif args.stage=='s2-activation-shape':
        from workflow_doris_s0_fixture import shape_case
        browser_test('s2-doris-shape-prepare',args.prepared)
        for method in ('driver-type-reject','driver-model-reject'):
            shape_case(method,args.prepared,activation=True)
            browser_test('s2-doris-shape-recover',args.prepared)
    elif args.stage=='s2-graduated-cancel': graduated_cancel(args.prepared)
    elif args.stage=='overlap-test': runtime_race_test('overlap')
    elif args.stage=='semantic-batch': semantic_batch_regression(args.prepared)
    elif args.stage=='pg-golden': pg_golden(args.prepared)
    elif args.stage.endswith('-grants'): synthetic_grants(args.stage.split('-')[-2],args.stage.startswith('s2-'))
    else: {'prepare':prepare,'render':render,'start':start,'configure':configure,'freeze':freeze_api}[args.stage]()
