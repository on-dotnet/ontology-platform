"""在任务独立平台上复用源码绑定、合成 OIDC 和只读运行快照。"""
import argparse
import json
import os
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


def local(stage,args,env=None,seconds=30):
    result = execution.run(args,ROOT,task=vm.TASK,run_id=vm.RUN,stage='dmq-s1-'+stage,environment=env,timeout=seconds)
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
BROWSER = ('provision','mapping','s1','s1-reopen','s1-key-negative','s1-current-catalog','s2-doris-mapping','s2-doris-queries','s2-doris-null','s2-doris-cancel','s2-doris-access','s2-doris-fanout','s2-doris-requalify')


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
    vm.demand(STRESS.exists()==(mode=='s2-doris-cancel'),'PRODUCT_STRESS_ISOLATION')
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
        report=local('browser-'+mode,[dep['node'],'scripts/maintenance/workflow-m4-query.mjs','--task',vm.TASK,'--run-id',vm.RUN,'--mode',mode],seconds=180)
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


def cancellation_case(prepared):
    from workflow_doris_s0_fixture import STRESS,stress_fixture
    vm.demand(not STRESS.exists(),'S2_SEPARATE_STRESS_REQUIRED')
    try:
        stress_fixture(platform=True)
        browser_test('s2-doris-cancel',prepared)
    finally:
        if STRESS.exists(): stress_fixture(restore=True,platform=True)


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
    parser.add_argument('stage',choices=['prepare','render','start','configure','freeze','pg-golden','s2-cancel-case','fanout','permission','s2-boundary','s2-restore','mapping-grants','query-grants','s2-mapping-grants','s2-query-grants',*BROWSER])
    parser.add_argument('--prepared')
    parser.add_argument('--permission',choices=[f'{v}-{k}' for v in ('revoke','restore') for k in ('execute','result','evidence')])
    parser.add_argument('--fanout', choices=['ten','eleven','restore'])
    args=parser.parse_args()
    if args.stage == 's2-doris-fanout':
        vm.demand(not (OUT/'s2-fanout-active.json').exists(), 'FANOUT_ALREADY_ACTIVE')
        try:
            browser_test(args.stage, args.prepared)
        finally:
            if (OUT/'s2-fanout-active.json').exists(): fanout_fixture('restore')
    elif args.stage in BROWSER: browser_test(args.stage,args.prepared)
    elif args.stage in ('s2-boundary','s2-restore'): relation_fixture(args.stage=='s2-restore')
    elif args.stage=='fanout': print(json.dumps(fanout_fixture(args.fanout)))
    elif args.stage=='permission': permission_case(args.permission)
    elif args.stage=='s2-cancel-case': cancellation_case(args.prepared)
    elif args.stage=='pg-golden': pg_golden(args.prepared)
    elif args.stage.endswith('-grants'): synthetic_grants(args.stage.split('-')[-2],args.stage.startswith('s2-'))
    else: {'prepare':prepare,'render':render,'start':start,'configure':configure,'freeze':freeze_api}[args.stage]()
