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
    result = execution.run(args,ROOT,task=vm.TASK,run_id=vm.RUN,stage='dmq-s1-'+stage,environment=env,timeout=seconds,input_key=inputs)
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
        snapshots.verify(ROOT,previous,task=vm.TASK,run_id=vm.RUN)
        if previous['inputs']==binding: return previous
    row = snapshots.freeze(ROOT,target,OUT/'runtime-snapshots',binding,binding['receiptSha256'],env,task=vm.TASK,run_id=vm.RUN)
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
BROWSER = ('provision','mapping','s1','s1-reopen','s1-key-negative','s1-current-catalog','s2-doris-mapping','s2-doris-queries','s2-doris-null','s2-doris-cancel','s2-doris-access','s2-doris-fanout','s2-doris-requalify','s2-doris-aba','s2-doris-admission-cancel','s2-doris-cancel-window','s2-doris-states','s2-doris-cardinality','s2-doris-identity','s2-doris-revoke-race','s2-doris-session-race','s2-doris-shape-prepare','s2-doris-shape-reject','s2-doris-shape-recover')


def runtime_binding():
    row = json.loads(HOST.read_bytes())
    snapshot = json.loads(SNAPSHOT.read_bytes())
    snapshots.verify(ROOT,snapshot,task=vm.TASK,run_id=vm.RUN)
    pid = str(row['pid'])
    dll = ROOT/snapshot['directory']/'OntologyPlatform.Api.dll'
    vm.demand(row['taskId']==vm.TASK and row['runId']==vm.RUN and row['status']=='READY'
              and row['snapshotId']==snapshot['snapshotId'] and snapshot['inputs']==admit_build()
              and vm.host('ps','-p',pid,'-o','lstart=')==row['processStart']
              and vm.host('ps','-p',pid,'-o','command=')==snapshot['environment']['dotnet']+' '+str(dll),'S1_HOST_BINDING')
    return row


def live_stack():
    state = json.loads(PLATFORM.read_bytes())
    source = json.loads(INDEX.read_bytes())
    services = dict(state['resources'],**{k:v['id'] for k,v in source['services'].items()})
    vm.demand(set(docker('six-cids','ps','-q','--no-trunc').splitlines())==set(services.values()),'S1_RESOURCE_PARTITION')
    for name,cid in services.items():
        check = docker('health','inspect','-f','{{.Id}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}} {{.State.OOMKilled}} {{with (index .State "Health")}}{{.Status}}{{else}}none{{end}}',cid).split()
        vm.demand(check[:5]==[cid,vm.TASK,vm.RUN,'running','false'] and check[5] in ('healthy','none'),'S1_CONTAINER_'+name)
    return services


def browser_test(mode, prepared):
    dependency_path=execution.ordinary(Path(prepared).absolute())
    vm.demand(dependency_path.is_relative_to(ROOT/'artifacts/workflow'/vm.TASK/'environment'),'S1_ENVIRONMENT_PATH')
    dep=json.loads(dependency_path.read_bytes())
    vm.demand((dep['taskId'],dep['worktree'],dep['status'])==(vm.TASK,str(ROOT),'DEPENDENCIES_READY'),'S1_ENVIRONMENT')
    from workflow_doris_s0_fixture import STRESS
    vm.demand(STRESS.exists()==(mode in ('s2-doris-cancel','s2-doris-admission-cancel','s2-doris-cancel-window')),'PRODUCT_STRESS_ISOLATION')
    live_stack()
    snapshot=freeze_api()
    dll=ROOT/snapshot['directory']/'OntologyPlatform.Api.dll'
    vm.demand(snapshot['environment']['dotnet']==dep['dotnet'],'S1_HOST_RUNTIME')
    with socket.socket() as check: check.bind(('127.0.0.1',15641))
    identity=json.loads((RUNTIME/'runtime.json').read_bytes())
    context=execution.CONTEXT.set(dict(task=vm.TASK,run_id=vm.RUN))
    exceeded=threading.Event()
    finished=threading.Event()
    env=dict(PATH=os.environ['PATH'],ASPNETCORE_ENVIRONMENT='Development',ASPNETCORE_CONTENTROOT=str(RUNTIME/'api'),
             G4__SourceCaPath=str(DIRECTORY/'tls/ca.pem'),ASPNETCORE_URLS='http://127.0.0.1:15641',DOTNET_GCHeapHardLimit='0x18000000',DOTNET_CLI_TELEMETRY_OPTOUT='1')
    env['Logging__LogLevel__OntologyPlatform.Modules.SemanticQuery.G4QueryExecution']='Information'
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
        # 浏览器实际消费的脚本与程序集进入输入指纹，重验保留前次失败且可区分修正。
        runner_paths = [Path(__file__), ROOT/'scripts/maintenance/workflow-m4-query.mjs', ROOT/'scripts/maintenance/workflow_doris_s0_fixture.py',
                        ROOT/'scripts/maintenance/workflow_doris_mapping_query.py', ROOT/'scripts/maintenance/doris_query_cancel_witness.py']
        components = [snapshot['snapshotId'], mode, [execution.sha(path.read_bytes()) for path in runner_paths]]
        if STRESS.exists(): components.append(execution.sha(STRESS.read_bytes()))
        inputs = execution.sha(execution.encoded(components))
        report=local('browser-'+mode,[dep['node'],'scripts/maintenance/workflow-m4-query.mjs','--task',vm.TASK,'--run-id',vm.RUN,'--mode',mode],seconds=180,inputs=inputs)
        vm.demand(not exceeded.is_set(),'S1_HOST_CAP')
        print(report.stdout.decode().strip())
        row['browserCommand']=report.receipt['commandId']
    finally:
        finished.set()
        watcher.join(6)
        if service.process.poll() is None: os.killpg(pid,signal.SIGTERM)
        try: service.process.wait(timeout=12)
        finally:
            for thread in service.reader_threads: thread.join(2)
            service.finish()
            # 只保存固定格式聚合数值与本任务 queryId，不导出任何其他应用日志。
            matches = re.findall(rb'DorisLeaseObservation query=(query-[0-9a-f]{32}) probes=(\d+) elapsedMs=([0-9.]+) maxReadMs=([0-9.]+) outcome=(closed|lease_changed|observation_failed)', bytes(service.out)+bytes(service.err))
            row['dorisObservations'] = [dict(queryId=q.decode(), probes=int(n), elapsedMs=float(t), maxReadMs=float(m), outcome=o.decode()) for q,n,t,m,o in matches]
            row.update(status='EXITED' if service.process.poll() is not None else 'STOP_UNKNOWN',hostPeakBytes=peaks,
                       exceeded=exceeded.is_set(),exitCode=service.process.poll())
            record(evidence,row)
            record(HOST,row)
            execution.CONTEXT.reset(context)


def synthetic_grants(mode, two_tables=False):
    from workflow_m4_query import grant_transaction
    state=json.loads((OUT/('doris-two-table.json' if two_tables else 'runtime-fixture.json')).read_bytes())
    roles=state['subjects']
    vm.demand(state['taskId']==vm.TASK and state['runId']==vm.RUN and state['scope']==dict(organizationId='org-demo',siteIds=['site-a'])
              and set(roles)=={'operator','auditor','activator','reader'} and len(set(roles.values()))==4,'S1_GRANT_SCOPE')
    catalog=state['catalog']
    vm.demand(catalog['connectionId']==state['connectionId'] and catalog['status']=='READY','S1_GRANT_CATALOG')
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
    perms={'operator':['mapping.read','mapping.source.validate','mapping.edit','mapping.validate','mapping.submit'],
           'auditor':['mapping.read','mapping.source.validate','mapping.review','mapping.approve'],
           'activator':['mapping.read','mapping.source.validate','mapping.activate']} if mode=='mapping' else {
               'reader':['data.query.execute','data.query.result.read','data.query.evidence.read']}
    def id_for(subject,permission):
        return ('dmq-s2-' if two_tables else 'dmq-s1-')+execution.sha(execution.encoded([state['connectionId'],subject,permission]))[:32]
    sql,ids=grant_transaction(state,objects,field_refs,
                              [(roles[role],permissions) for role,permissions in perms.items()],id_for,vm.RUN)
    cid=live_stack()['platform-pg']
    result=execution.run(['docker','--context','desktop-linux','exec','-i',cid,'psql','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1','-qAt'],
                         ROOT,task=vm.TASK,run_id=vm.RUN,stage='dmq-'+mode+'-fixture-grants',stdin=sql,input_key=execution.sha(sql),timeout=18)
    vm.demand(result.returncode==0 and result.stdout.decode().strip()==str(len(ids)),'S1_GRANT_INSERT_'+result.receipt['commandId'])
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



def permission_case(action):
    import re
    verb,kind=action.split('-')
    permission={'execute':'data.query.execute','result':'data.query.result.read','evidence':'data.query.evidence.read'}[kind]
    state=json.loads((OUT/'doris-two-table.json').read_bytes())
    subject=state['subjects']['reader']
    vm.demand(state['taskId']==vm.TASK and state['runId']==vm.RUN and state['scope']==dict(organizationId='org-demo',siteIds=['site-a'])
              and re.fullmatch('[a-f0-9-]{32,36}',subject) and re.fullmatch('[a-f0-9]{32}',state['connectionId']),'S2_GRANT_IDENTITY')
    digest=execution.sha(execution.encoded([state['connectionId'],subject,permission]))[:32]
    ids=[f'dmq-s1-{digest}',f'dmq-s2-{digest}']
    pred='"Id" IN ('+','.join("'"+id+"'" for id in ids)+') AND "SubjectId"='+repr(subject)+' AND "Permission"='+repr(permission)
    active=OUT/('s2-grant-active-'+kind+'.json')
    cid=live_stack()['platform-pg']
    if verb=='revoke':
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
        GET DIAGNOSTICS total=ROW_COUNT; IF total<>2 THEN RAISE EXCEPTION 'fixture-grant-count'; END IF;
      END $$;
      INSERT INTO governance.audit_records ("Id","OccurredAtUtc","Actor","Action","Resource","Outcome","TraceId","CorrelationId","OrganizationId","ScopeSiteIds","SiteId")
        SELECT md5("Id"||clock_timestamp()::text),now(),'synthetic-query-fixture','mapping.grant.change',"Id",'allowed','dmq-permission','dmq-permission','org-demo',ARRAY['site-a'],NULL
        FROM governance."MappingAuthorizationGrants" WHERE {pred};
      COMMIT;"""
    result=execution.run(['docker','--context','desktop-linux','exec','-i',cid,'psql','-XwqAt','-U','postgres','-d','mapping','-v','ON_ERROR_STOP=1'],
                         ROOT,task=vm.TASK,run_id=vm.RUN,stage='dmq-'+action,stdin=query.encode(),input_key=execution.sha(query.encode()),timeout=12)
    vm.demand(result.returncode==0,'GRANT_CONTROL_'+result.receipt['commandId'])
    row[verb+'CommandId']=result.receipt['commandId']
    if verb=='restore':
        record(OUT/('s2-grant-restored-'+kind+'-'+result.receipt['commandId']+'.json'),row)
        active.unlink()
    else: record(active,row)
    print(json.dumps(dict(action=action,count=2,commandId=result.receipt['commandId'])))


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


def cancellation_case(prepared, admission=False):
    from workflow_doris_s0_fixture import STRESS,stress_fixture
    vm.demand(not STRESS.exists(),'S2_SEPARATE_STRESS_REQUIRED')
    try:
        stress_fixture(platform=True)
        browser_test('s2-doris-admission-cancel' if admission else 's2-doris-cancel',prepared)
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
        try:
            stress_fixture(platform=True,entity_rows=tier)
            fixture = json.loads(STRESS.read_bytes())
            stage['fixture']=fixture['attempt']
            before = set(OUT.glob('browser-s2-doris-cancel-window-*.json'))
            browser_test('s2-doris-cancel-window',prepared)
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
                browser_test('s2-doris-cancel',prepared)
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


def runtime_race_test(case):
    """只接收当前合成 Cookie 的内存管道，按已绑定 AgentTests 运行一次已登记的正式在途竞争。"""
    from workflow_m2_evidence import mtp
    frozen = json.loads(SNAPSHOT.read_bytes())
    active = runtime_binding()
    stage, method = {
        'aba': ('s2-doris-aba', 'DorisActivationRevisionRejectsInflightQuery'),
        'revoke': ('s2-doris-revoke-race', 'DorisRevocationRejectsInflightQuery'),
        'session': ('s2-doris-session-race', 'DorisExpiredSessionRejectsInflightQuery')
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
               G4_QUERY_RUNTIME_TEST=vm.TASK+':'+vm.RUN, DOTNET_GCHeapHardLimit='0x18000000', DOTNET_CLI_TELEMETRY_OPTOUT='1')
    result = execution.run([dotnet, str(dll), '--filter', 'FullyQualifiedName='+method, '--minimum-expected-tests', '1', '--no-ansi', '--progress', 'off', '--results-directory', str(OUT/'aba-results')],
                           ROOT, task=vm.TASK, run_id=vm.RUN, stage='dmq-inflight-'+case, environment=env,
                           input_key=execution.sha(execution.encoded(binding)), stdin=envelope, timeout=25)
    passed = mtp(result.stdout + result.stderr, 1) if not result.returncode else 0
    summary = dict(commandId=result.receipt['commandId'], input=binding, exitCode=result.returncode, passed=passed)
    record(OUT/(('s2-'+case+'-mtp-')+summary['commandId']+'.json'), summary)
    vm.demand(result.returncode == 0 and passed == 1, 'ABA_MTP_'+summary['commandId'])
    print(json.dumps(summary))


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
                         task=vm.TASK,run_id=vm.RUN,stage='dmq-pg-golden',environment=dep['environment'],input_key=execution.sha(execution.encoded(binding)),timeout=25)
    passed=mtp(result.stdout+result.stderr,2) if not result.returncode else 0
    row=dict(method=method,input=binding,commandId=result.receipt['commandId'],passed=passed,exitCode=result.returncode)
    record(OUT/('pg-golden-test-'+row['commandId']+'.json'),row)
    vm.demand(passed==2 and result.returncode==0,'PG_GOLDEN_TEST_'+row['commandId'])
    print(json.dumps(row))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','render','start','configure','freeze','pg-golden','s2-activation-shape','s2-graduated-cancel','s2-cancel-case','s2-admission-case','state-fixture','session-test','revoke-test','aba-test','fanout','permission','s2-boundary','s2-restore','mapping-grants','query-grants','s2-mapping-grants','s2-query-grants',*BROWSER])
    parser.add_argument('--prepared')
    parser.add_argument('--permission',choices=[f'{v}-{k}' for v in ('revoke','restore') for k in ('execute','result','evidence')])
    parser.add_argument('--fanout', choices=['ten','eleven','restore'])
    parser.add_argument('--state-operation',choices=['seed','deny','allow','restore'])
    args=parser.parse_args()
    if args.stage == 's2-doris-fanout':
        vm.demand(not (OUT/'s2-fanout-active.json').exists(), 'FANOUT_ALREADY_ACTIVE')
        try:
            browser_test(args.stage, args.prepared)
        finally:
            if (OUT/'s2-fanout-active.json').exists(): fanout_fixture('restore')
    elif args.stage=='state-fixture': scoped_state_fixture(args.state_operation)
    elif args.stage in ('s2-doris-states','s2-doris-cardinality'):
        vm.demand(not (OUT/'s2-source-states-active.json').exists(),'STATES_ALREADY_ACTIVE')
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
    elif args.stage in BROWSER: browser_test(args.stage,args.prepared)
    elif args.stage in ('s2-boundary','s2-restore'): relation_fixture(args.stage=='s2-restore')
    elif args.stage in ('aba-test','revoke-test','session-test'): runtime_race_test(args.stage.removesuffix('-test'))
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
    elif args.stage=='pg-golden': pg_golden(args.prepared)
    elif args.stage.endswith('-grants'): synthetic_grants(args.stage.split('-')[-2],args.stage.startswith('s2-'))
    else: {'prepare':prepare,'render':render,'start':start,'configure':configure,'freeze':freeze_api}[args.stage]()
