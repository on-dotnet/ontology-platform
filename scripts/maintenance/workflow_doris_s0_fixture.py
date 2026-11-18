"""仅创建本次两节点源夹具，使用镜像自带的 MySQL 客户端核对源事实。"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

import workflow_doris_vm as vm
import workflow_execution as execution
from workflow_doris_fixture import private
from workflow_doris_mapping_query import fixture_tables, REFERENCE_SQL


PROJECT = 'ontology-g4-doris-mapping-query-001'
DIRECTORY = vm.ROOT / '.tools/security/g4-doris-mapping-query-001' / 'implementation-01-source'
INDEX = vm.OUTPUT / 's0-source-identities.json'
COMPOSE = ['compose', '-p', PROJECT, '-f', 'infra/doris/compose.yaml', '-f', 'infra/doris/compose.test.yaml',
           '-f', 'infra/doris/compose.mapping-query.yaml']
CLIENT = r'''set -eu
umask 077
file=$(mktemp /dev/shm/dmq-client.XXXXXXXX)
trap 'rm -f "$file"' EXIT
IFS= read -r password
printf '[client]\npassword=%s\n' "$password" > "$file"
unset password
mysql --defaults-file="$file" --protocol=TCP --host=localhost --port=9030 --user="$1" --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/run/doris-tls/ca.pem --connect-timeout=3 --skip-reconnect --batch --raw --unbuffered "$2"
'''


def docker(stage, *args, env=None, timeout=15, cleanup=False):
    proc = execution.run(['docker','--context','desktop-linux',*args],vm.ROOT,task=vm.TASK,run_id=vm.RUN,
                         stage='dmq-source-'+stage,timeout=timeout,environment=env,cleanup=cleanup)
    vm.demand(proc.returncode == 0,'DOCKER_' + stage.upper())
    return proc.stdout.decode().strip()


def record(path, state):
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(state,indent=2)+'\n')
    os.replace(pending,path)


def tls_files():
    os.umask(0o077)
    vm.demand(DIRECTORY.resolve() == DIRECTORY, 'PRIVATE_DIRECTORY_LINK')
    DIRECTORY.mkdir(mode=0o700)
    tls = DIRECTORY / 'tls'
    tls.mkdir(mode=0o700)
    for name in ('root','reader','store','admin'):
        private(DIRECTORY/(name+'.pass'),secrets.token_urlsafe(36))
    def openssl(*args):
        result = subprocess.run(['openssl',*map(str,args)],cwd=DIRECTORY,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12)
        vm.demand(result.returncode == 0,'SOURCE_TLS_GENERATION')
    openssl('req','-x509','-newkey','rsa:3072','-nodes','-days','7','-sha256','-subj','/CN=DMQ local source CA',
            '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign',
            '-keyout','ca.key','-out','tls/ca.pem')
    openssl('req','-new','-newkey','rsa:3072','-nodes','-subj','/CN=localhost','-keyout','server.key','-out','server.csr')
    private(DIRECTORY/'extensions.cnf','basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost\n')
    openssl('x509','-req','-in','server.csr','-CA','tls/ca.pem','-CAkey','ca.key','-CAcreateserial','-days','7',
            '-sha256','-extfile','extensions.cnf','-out','server.crt')
    openssl('verify','-CAfile','tls/ca.pem','-verify_hostname','localhost','-purpose','sslserver','server.crt')
    openssl('pkcs12','-export','-in','server.crt','-inkey','server.key','-certfile','tls/ca.pem','-name','server',
            '-passout','file:store.pass','-out','tls/server_certificate.p12')
    openssl('pkcs12','-export','-nokeys','-in','tls/ca.pem','-jdktrust','anyExtendedKeyUsage','-name','ca',
            '-passout','file:store.pass','-out','tls/ca_certificate.p12')
    password = (DIRECTORY/'root.pass').read_bytes()
    password_hash = '*' + hashlib.sha1(hashlib.sha1(password).digest()).hexdigest().upper()
    conf = (vm.ROOT/'infra/doris/config/fe.conf.example').read_text().replace('REPLACE_WITH_PRIVATE_DOUBLE_SHA1',password_hash)
    store = (DIRECTORY/'store.pass').read_text()
    private(DIRECTORY/'fe.conf',conf.replace('REPLACE_WITH_PRIVATE_STORE_PASSWORD',store))
    private(DIRECTORY/'be.conf',(vm.ROOT/'infra/doris/config/be.conf.example').read_bytes())


def compose_env():
    return dict(os.environ,DORIS_RUN_ID=vm.RUN,DORIS_FE_MEMORY='4g',DORIS_BE_MEMORY='6g',
                DORIS_FE_CONFIG=str(DIRECTORY/'fe.conf'),DORIS_BE_CONFIG=str(DIRECTORY/'be.conf'),
                DORIS_TLS_DIR=str(DIRECTORY/'tls'))


def sql(fe, account, query, headers=False, limit=15):
    vm.demand(account in ('root','reader'), 'SOURCE_ACCOUNT')
    ident = 'root' if account=='root' else 'fixture_reader'
    password = (DIRECTORY/(account+'.pass')).read_bytes()
    # 原始凭据仅经私有 stdin；错误文本可能回显 SQL，因此仅保存在私有运行目录。
    proc = subprocess.run(['docker','--context','desktop-linux','exec','-i',fe,'bash','-ec',CLIENT,'source',ident,'--column-names' if headers else '--skip-column-names'],
        input=password+b'\n'+query.encode()+b'\n',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=limit)
    if proc.returncode:
        private(DIRECTORY/('sql-error-'+secrets.token_hex(8)),proc.stderr)
        raise ValueError('SOURCE_SQL_' + str(proc.returncode))
    return proc.stdout.decode().strip()


def create():
    vm.demand(not INDEX.exists() and not DIRECTORY.exists(), 'SOURCE_ALREADY_REGISTERED')
    resource = vm.collect()
    vm.demand(resource['status']=='KERNEL_AND_VM_READY', 'VM_SOURCE_ADMISSION')
    vm.demand(resource['host']['physicalBytes'] >= 20*vm.GIB + resource['phaseEnvelope']['S0_FE_BE']['hostStageBudgetBytes']
              and resource['host']['diskAvailableBytes']>=12*vm.GIB,'HOST_STAGE_CAPACITY')
    for kind in ('container','volume','network'):
        args = ('ps','-aq') if kind=='container' else (kind,'ls','-q')
        vm.demand(not docker('existing-'+kind,*args,'--filter','label=com.docker.compose.project='+PROJECT),'SOURCE_PROJECT_EXISTS')
    tls_files()
    env=compose_env()
    rendered=json.loads(docker('render',*COMPOSE,'config','--format','json',env=env))
    vm.demand(rendered['name']==PROJECT and set(rendered['services'])=={'fe','be'},'SOURCE_PROJECT_RENDER')
    for kind in ('networks','volumes','services'):
        for name,row in rendered[kind].items():
            vm.demand(row['labels']=={'ontology.task':vm.TASK,'ontology.run':vm.RUN},'SOURCE_LABELS')
            if kind!='services':
                vm.demand(row['name']==PROJECT+'_'+name and not row.get('external'),'SOURCE_NEW_NAMESPACE')
    for name,service in rendered['services'].items():
        cap=(4 if name=='fe' else 6)*vm.GIB
        vm.demand(service['image']==vm.IMAGES[name] and service['pull_policy']=='never' and service['cap_drop']==['ALL']
                  and int(service['mem_limit'])==int(service['memswap_limit'])==cap and float(service['cpus'])==2
                  and service['pids_limit']==(512 if name=='fe' else 1024),'SOURCE_RESOURCE_LIMITS')
        for mount in service['volumes']:
            if mount['type']=='bind':
                vm.demand(Path(mount['source']).resolve().is_relative_to(DIRECTORY) and mount['read_only'],'SOURCE_BIND')
    fe_ports=rendered['services']['fe']['ports']
    vm.demand(len(fe_ports)==1 and fe_ports[0]['host_ip']=='127.0.0.1' and str(fe_ports[0]['published'])=='19030'
              and int(fe_ports[0]['target'])==9030 and not rendered['services']['be'].get('ports')
              and rendered['networks']['doris']['internal'] and set(rendered['services']['be']['networks'])=={'doris'},'SOURCE_NETWORK')
    state={'taskId':vm.TASK,'runId':vm.RUN,'project':PROJECT,'vmAdmission':resource['attempt'],'services':{},
           'networks':{},'volumes':{},'status':'CREATING','runtimePrivate':str(DIRECTORY.relative_to(vm.ROOT))}
    record(INDEX,state)
    try:
        docker('create',*COMPOSE,'create','--pull','never','--no-build',env=env,timeout=45)
    finally:
        for name in ('fe','be'):
            cid=docker('id-'+name,*COMPOSE,'ps','-aq',name,env=env)
            if cid:
                fmt='{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}}'
                full,image,task,run,status=docker('owner-'+name,'inspect','-f',fmt,cid).split()
                vm.demand(image==resource['images'][name]['id'] and task==vm.TASK and run==vm.RUN,'SOURCE_OWNER')
                state['services'][name]={'id':full,'image':image,'before':status}
                record(INDEX,state)
        for kind in ('network','volume'):
            fmt='{{.Id}}' if kind=='network' else '{{.Name}}'
            for name in rendered[kind+'s']:
                handle=PROJECT+'_'+name
                state[kind+'s'][name]=docker('owner-'+kind,kind,'inspect','-f',fmt,handle)
                record(INDEX,state)
    for name,entry in state['services'].items():
        vm.demand(entry['before']=='created','SERVICE_BEFORE_START')
        docker('start-'+name,'start',entry['id'])
        state['status']=name.upper()+'_STARTED'
        record(INDEX,state)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        health=[docker('health-'+key,'inspect','-f','{{.State.Status}} {{.State.Health.Status}} {{.State.OOMKilled}}',entry['id'])
                for key,entry in state['services'].items()]
        vm.demand(all(h.startswith('running ') and h.endswith(' false') for h in health),'SOURCE_START_FAILED')
        if health==['running healthy false']*2:
            state['status']='BOTH_HEALTHY'
            record(INDEX,state)
            return
        time.sleep(2)
    raise ValueError('SOURCE_START_DEADLINE')


def insert_entity(amount):
    return ("INSERT INTO fixture.dmq_entity VALUES "
            "('org-demo','site-a','E1',1.00,"+amount+",'K','2026-11-01','2026-12-01',"
            "'2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456');")


def resume():
    """按已审索引恢复准确的两个源节点，复核资源和原卷后才允许启动。"""
    from workflow_m2_build import validate
    validate('connections',vm.TASK)
    reviewed = json.loads((vm.ROOT/'docs/evidence'/vm.TASK/vm.RUN/'s0-source-review.json').read_bytes())
    vm.demand(hashlib.sha256(INDEX.read_bytes()).hexdigest() in
              [v.get(INDEX.name) for v in reviewed.values() if isinstance(v,dict)],'REVIEWED_INDEX')
    state = json.loads(INDEX.read_bytes())
    admission = vm.collect()
    vm.demand(admission['status']=='KERNEL_AND_VM_READY' and admission['host']['physicalBytes'] >=
              20*vm.GIB + admission['phaseEnvelope']['S0_FE_BE']['hostStageBudgetBytes'],'VM_SOURCE_ADMISSION')
    vm.demand(state['taskId']==vm.TASK and state['runId']==vm.RUN and state['project']==PROJECT and
              set(state['services'])=={'fe','be'} and DIRECTORY.resolve()==DIRECTORY,'RESUME_OWNER')
    path = vm.OUTPUT/('s0-resume-'+secrets.token_hex(6)+'.json')
    events = {'vmAttempt':admission['attempt'],'services':{},'started':[]}
    owner = '{{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{index .Config.Labels "com.docker.compose.project"}}'
    for role,s in state['services'].items():
        cap = (4 if role=='fe' else 6)*vm.GIB
        check = docker('resume-owner','inspect','-f','{{.Id}} {{.Image}} '+owner+' {{.State.Status}} {{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.NanoCpus}}',s['id'])
        vm.demand(check.split()==[s['id'],admission['images'][role]['id'],vm.TASK,vm.RUN,PROJECT,'exited',str(cap),str(cap),'2000000000'],'RESUME_ID_QUOTA')
        mounts = json.loads(docker('resume-mounts','inspect','-f','{{json .Mounts}}',s['id']))
        volumes = [m['Name'] for m in mounts if m['Type']=='volume']
        vm.demand(sorted(volumes)==sorted(state['volumes'][role+'-'+n] for n in ('data','log')),'RESUME_VOLUMES')
        bindings = [m for m in mounts if m['Type']!='volume']
        expected = {DIRECTORY/(role+'.conf')} | ({DIRECTORY/'tls'} if role=='fe' else set())
        vm.demand({Path(m['Source']).resolve() for m in bindings}==expected and
                  all(m['Type']=='bind' and not m['RW'] for m in bindings),'RESUME_BINDING')
        events['services'][role] = {'id':s['id'],'image':s['image'],'volumes':volumes,'from':'exited'}
    record(path,events)
    for role in ('fe','be'):
        cid = state['services'][role]['id']
        vm.demand(docker('resume-'+role,'start',cid)==cid,'RESUME_START')
        events['started'].append(cid)
        record(path,events)
        deadline = time.monotonic()+100
        while time.monotonic()<deadline:
            current=docker('resume-health','inspect','-f','{{.State.Status}} {{.State.Health.Status}}',cid)
            if current=='running healthy':break
            vm.demand(current=='running starting','RESUME_HEALTH')
            time.sleep(1)
        else: raise ValueError('RESUME_HEALTH_DEADLINE')
    ready_source(state['services']['fe']['id'])
    events['status']='BOTH_HEALTHY'
    record(path,events)
    print(path.relative_to(vm.ROOT),events['status'])


def ready_source(fe):
    """端口健康后仍须等固定 FE 接收到准确版本的 BE 心跳。"""
    for group in ('FRONTENDS','BACKENDS'):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            table=list(csv.DictReader(sql(fe,'root','SHOW '+group+';',True,limit=3).splitlines(),delimiter='\t'))
            vm.demand(len(table)==1,'RESUME_NODE_COUNT')
            version=table[0]['Version']
            if version and version not in ('NULL','\\N'):
                vm.demand(version=='doris-4.0.8-rc02-bc8ea1bac6d','RESUME_BUILD')
            if table[0]['Alive'].lower()=='true' and version=='doris-4.0.8-rc02-bc8ea1bac6d':
                break
            time.sleep(1)
        else: raise ValueError('RESUME_HEARTBEAT_DEADLINE')
    vm.demand(sql(fe,'reader','SHOW TABLES FROM fixture;').splitlines()==['dmq_entity','dmq_target'],'RESUME_FIXTURE')


def driver(prepared, method):
    """在当前输入绑定的程序集上仅运行一个 S0 源见证，保留 MTP 真实退出码。"""
    from workflow_m2_build import validate
    from workflow_m2_evidence import mtp
    from workflow_doris_mapping_query import s0_consumers
    s0_consumers(vm.ROOT,vm.TASK,'source')
    envfile = execution.ordinary(prepared)
    vm.demand(envfile.is_relative_to(vm.ROOT/'artifacts/workflow'/vm.TASK/'environment'),'PREPARE_OWNER')
    environment = json.loads(envfile.read_bytes())
    vm.demand(environment['status']=='DEPENDENCIES_READY' and environment['taskId']==vm.TASK and
              environment['worktree']==str(vm.ROOT),'PREPARE_RECEIPT')
    binding = validate('connections',vm.TASK)
    state = json.loads(INDEX.read_bytes())
    for service in state['services'].values():
        vm.demand(docker('driver-identity','inspect','-f','{{.Id}} {{.Image}} {{.State.Status}} {{.State.Health.Status}} {{index .Config.Labels "ontology.task"}}',service['id'])
                  ==' '.join([service['id'],service['image'],'running','healthy',vm.TASK]),'DRIVER_SOURCE_DRIFT')
    ready_source(state['services']['fe']['id'])
    env = dict(environment['environment'],DMQ_S0_SOURCE=str(DIRECTORY),DMQ_S0_EVIDENCE=str(vm.OUTPUT),
               DOTNET_GCHeapHardLimit='0x18000000')
    test = {'driver-types':'RealDriverReadsFixedSource','driver-cancel':'ActiveBackendMustFinishInsideOriginalWindow'}[method]
    key = execution.sha(execution.encoded([binding,hashlib.sha256(INDEX.read_bytes()).hexdigest(),test,
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()]))
    result = execution.run([environment['dotnet'],str(vm.ROOT/'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0/OntologyPlatform.ConnectionsTests.dll'),
              '--filter','FullyQualifiedName=OntologyPlatform.ConnectionsTests.DorisMappingQueryTests.'+test,
              '--minimum-expected-tests','1','--results-directory',str(vm.OUTPUT/'driver-results'),'--no-ansi','--progress','off'],
              vm.ROOT,task=vm.TASK,run_id=vm.RUN,stage=method,input_key=key,environment=env,timeout=20)
    count = mtp(result.stdout+result.stderr,1) if result.returncode==0 else None
    receipt = dict(method=test,build=binding,command=result.receipt['commandId'],exitCode=result.returncode,passed=count)
    record(vm.OUTPUT/(method+'-'+receipt['command']+'.json'),receipt)
    print(json.dumps(receipt))
    return result.returncode


def capabilities():
    state=json.loads(INDEX.read_text())
    vm.demand(state['status']=='BOTH_HEALTHY','REAL_SOURCE_NOT_READY')
    fe=state['services']['fe']['id']
    for name,s in state['services'].items():
        vm.demand(docker('owner','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{.State.Status}}',
                        s['id'])==f"{s['id']} {s['image']} {vm.TASK} running",'SOURCE_IDENTITY')
    path=vm.OUTPUT/('s0-native-source-'+secrets.token_hex(6)+'.json')
    fact={'taskId':vm.TASK,'sourceFeId':fe,'sourceBeId':state['services']['be']['id'],'origin':'FE-bundled MySQL 8.0.44 with VERIFY_IDENTITY',
          'formalDriver':'NOT_RUN','formalCancellation':'NOT_RUN','checks':{}}
    vm.demand(not path.exists(),'READ_NATIVE_PRIOR_RECEIPT')
    try:
        root=lambda q:sql(fe,'root',q)
        read=lambda q:sql(fe,'reader',q)
        first=root('SHOW BACKENDS;')
        if not first:
            root('ALTER SYSTEM ADD BACKEND "be:9050";')
        end=time.monotonic()+30
        while time.monotonic()<end:
            status=root('SHOW BACKENDS;').split('\t')
            if len(status)>10 and 'true' in status and any('4.0.8' in x for x in status):break
            time.sleep(1)
        else: raise ValueError('BE_REGISTRATION')
        fact['checks']['build']=next(x for x in status if '4.0.8' in x)
        fact['checks']['version']=root('SELECT VERSION();')
        root('CREATE DATABASE fixture;')
        for ddl in fixture_tables():root(ddl+';')
        # 管理凭据与只读凭据仅进入私有控制面，记录只包含结构与布尔结果。
        for who in ('admin','reader'):
            value=(DIRECTORY/(who+'.pass')).read_text()
            vm.demand(bool(re.fullmatch(r'[A-Za-z0-9_-]+',value)),'CREDENTIAL_FORMAT')
            if who=='reader':
                root("CREATE USER 'fixture_reader'@'%' IDENTIFIED BY '"+value+"';")
            else:
                root("SET PASSWORD FOR 'admin'@'%' = PASSWORD('"+value+"');")
        root("GRANT SELECT_PRIV ON internal.fixture.* TO 'fixture_reader'@'%';")
        fact['checks']['identity']=read('SELECT CURRENT_USER();')
        fact['checks']['ddl']={}
        for table,identity in (('dmq_entity','entity_id'),('dmq_target','target_id')):
            ddl=read('SHOW CREATE TABLE fixture.'+table+';')
            vm.demand(re.search(r'UNIQUE KEY\s*\(\s*`org_id`,\s*`site_id`,\s*`'+identity+r'`\s*\)',ddl,re.I)
                      and re.search(r'"enable_unique_key_merge_on_write"\s*=\s*"true"',ddl,re.I),'UNIQUE_MOW_KEY')
            fact['checks']['ddl'][table]={'sha256':hashlib.sha256(ddl.encode()).hexdigest(),'model':'UNIQUE','mow':True,
                                         'key':['org_id','site_id',identity]}
        types=read("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,ORDINAL_POSITION,NUMERIC_PRECISION,NUMERIC_SCALE "
                   "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='fixture' AND TABLE_NAME IN ('dmq_entity','dmq_target') ORDER BY TABLE_NAME,ORDINAL_POSITION;")
        fact['checks']['columns']=[line.split('\t') for line in types.splitlines()]
        vm.demand(len(fact['checks']['columns'])==18,'NATIVE_TYPE_ROWS')
        root(insert_entity('1.00'))
        root(insert_entity('9007199254740993.20'))
        for k,val in (('T1','1.000'),('T2','1.000'),('T3','1.010')):
            root("INSERT INTO fixture.dmq_target VALUES ('org-demo','site-a','"+k+"',"+val+
                 ",'2026-11-01','2026-12-01','2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456');")
        q="SELECT count(*),CAST(MAX(amount) AS STRING),CAST(MAX(event_at) AS STRING) FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id='E1';"
        expected='1\t9007199254740993.20\t2026-11-17 12:00:00.123456'
        actual=read(q)
        vm.demand(actual==expected,'NATIVE_LOGICAL_UPSERT')
        fact['checks']['upsert']={'logicalRows':1,'amount':actual.split('\t')[1],'eventAt':actual.split('\t')[2]}
        joined=read(REFERENCE_SQL+';').splitlines()
        vm.demand(joined==['T1','T2'],'NATIVE_RELATION')
        fact['checks']['join']=joined
        bounds=read("SELECT CAST(CAST('-9223372036854775808' AS BIGINT) AS STRING),CAST(CAST('9223372036854775807' AS BIGINT) AS STRING);")
        vm.demand(bounds=='-9223372036854775808\t9223372036854775807','NATIVE_BIGINT')
        fact['checks']['bigint']=bounds.split('\t')
        # 两次公开读取之间受控写入，随后复位；独立列明非静止窗口。
        root(insert_entity('9007199254740993.21'))
        try:
            second=read(q)
            vm.demand(second.split('\t')[1]=='9007199254740993.21','AC11_CHANGED_VALUE')
        finally:
            root(insert_entity('9007199254740993.20'))
        vm.demand(read(q)==expected,'FIXTURE_RESET')
        fact['checks']['twoReads']={'first':actual.split('\t')[1],'second':second.split('\t')[1],'resetVerified':True,
                                    'dataWatermark':None,'consistency':'UNKNOWN'}
        fact['status']='NATIVE_FIXTURE_VERIFIED'
    except Exception as err:
        fact.update(status='BLOCKED',reason=str(err) if isinstance(err,ValueError) else type(err).__name__)
        raise
    finally:record(path,fact)




def stop():
    """向本次两个服务的真实前台进程发送镜像 --grace 使用的 TERM，并保留数据和容器。"""
    state=json.loads(INDEX.read_text())
    vm.demand(state['taskId']==vm.TASK and state['project']==PROJECT and set(state['services'])=={'fe','be'},'STOP_SOURCE_OWNER')
    result={'taskId':vm.TASK,'runId':vm.RUN,'events':[]}
    path=vm.OUTPUT/('s0-source-stop-'+secrets.token_hex(6)+'.json')
    for name,role in (('be','doris_be'),('fe','java')):
        service=state['services'][name]
        cid=service['id']
        fmt='{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}}'
        ident=docker('stop-owner-'+name,'inspect','-f',fmt,cid).split()
        vm.demand(ident==[cid,service['image'],vm.TASK,vm.RUN,'running'],'STOP_SOURCE_IDENTITY')
        # --console 的运行方式未必写 PID 文件，严格只允许容器内一个匹配角色。
        cmd='set -eu; found=0; for f in /proc/[0-9]*/comm; do read -r r < "$f" || continue; if [ "$r" = "$1" ]; then found=$((found+1)); p=${f#/proc/}; p=${p%/comm}; fi; done; test "$found" = 1; kill -TERM "$p"'
        event={'service':name,'id':cid,'signal':'SIGTERM','before':ident[-1]}
        result['events'].append(event)
        record(path,result)
        started=time.monotonic()
        docker('term-'+name,'exec',cid,'sh','-ec',cmd,'stop',role,cleanup=True)
        event['waitExit']=docker('wait-'+name,'wait',cid,timeout=50,cleanup=True)
        status=json.loads(docker('after-'+name,'inspect','-f','{{json .State}}',cid))
        event.update(elapsedSeconds=time.monotonic()-started,after={k:status[k] for k in ('Status','ExitCode','OOMKilled','FinishedAt')})
        record(path,result)
        vm.demand(status['Status']=='exited' and not status['OOMKilled'] and not status['Error'] and status['ExitCode'] in (0,143),'SOURCE_EXIT')
    result['runningAfter']=docker('post-stop','ps','-q','--no-trunc').splitlines()
    result['retainedVolumes']={n:docker('retained','volume','inspect','-f','{{.Name}}',v) for n,v in state['volumes'].items()}
    result['status']='STOPPED_KEEP'
    record(path,result)
    print(path.relative_to(vm.ROOT),result['status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['create','resume','capabilities','driver-types','driver-cancel','stop'])
    parser.add_argument('--prepared',type=Path)
    args=parser.parse_args()
    stage=args.stage
    if stage.startswith('driver-'):
        if args.prepared is None: parser.error('--prepared required')
        raise SystemExit(driver(args.prepared,stage))
    {'create':create, 'resume':resume, 'capabilities':capabilities, 'stop':stop}[stage]()
