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
STRESS = vm.OUTPUT / 's0-stress-fixture-active.json'
ENTITY_TIERS = (262144, 1048576, 4194304)
SHAPE = vm.OUTPUT / 's0-negative-shape-active.json'
STRESS_TABLES = [('dmq_entity', 'entity_id', ('E1',)), ('dmq_target', 'target_id', ('T1', 'T2', 'T3'))]
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


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def record(path, state):
    pending = path.with_suffix('.pending')
    durable = path == STRESS or path.name.startswith(('s0-stress-fixture-', 's2-sentinel-', 'overlap-profile-window-'))
    with pending.open('w') as out:
        out.write(json.dumps(state,indent=2)+'\n')
        if durable:
            out.flush()
            os.fsync(out.fileno())
    os.replace(pending,path)
    if durable: sync_directory(path.parent)


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
    password = (
        DIRECTORY / 'root.pass'
    ).read_bytes()
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
    password = (
        DIRECTORY / (account + '.pass')
    ).read_bytes()
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


def adjust_map_count(admission):
    """仅在唯一缺口为内核映射数并且 VM 空闲时，执行已获准的单项临时设置。"""
    vm.demand([k for k,ok in admission['s0Checks'].items() if not ok]==['mapCount'] and
              not admission['vm']['otherRunningCaps'] and not docker('kernel-idle','ps','-q'),'VM_KERNEL_ADJUSTMENT_SCOPE')
    nonce = secrets.token_hex(12)
    cid = docker('kernel-create','create','--pull=never','--privileged','--network=none','--read-only','--restart=no',
                 '--memory=64m','--memory-swap=64m','--cpus=.25','--pids-limit=16','--label','ontology.task='+vm.TASK,
                 '--label','ontology.run='+vm.RUN,'--label','ontology.attempt='+nonce,'--entrypoint=/usr/sbin/sysctl',
                 vm.IMAGES['be'],'-w','vm.max_map_count=2000000')
    path = vm.OUTPUT/('kernel-map-count-'+nonce+'.json')
    result = dict(admission=admission['attempt'],id=cid,before=admission['kernel']['maxMapCount'],target=2000000)
    record(path,result)
    fmt = '{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{len .Mounts}} {{.State.Status}}'
    vm.demand(docker('kernel-owner','inspect','-f',fmt,cid).split()==[cid,admission['images']['be']['id'],nonce,'0','created'],'VM_KERNEL_OWNER')
    result['readback'] = docker('kernel-adjust','start','-a',cid)
    vm.demand(result['readback']=='vm.max_map_count = 2000000' and
              docker('kernel-exit','inspect','-f','{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid)=='exited 0 false','VM_KERNEL_RESULT')
    docker('kernel-remove','rm',cid,cleanup=True)
    result['absentAfter'] = not docker('kernel-post','ps','--no-trunc','-aq','--filter','id='+cid)
    record(path,result)
    vm.demand(result['absentAfter'],'VM_KERNEL_CLEANUP')


def resume():
    """按已审索引恢复准确的两个源节点，复核资源和原卷后才允许启动。"""
    from workflow_m2_build import validate
    validate('connections',vm.TASK)
    reviewed = json.loads((vm.ROOT/'docs/evidence'/vm.TASK/vm.RUN/'s0-source-review.json').read_bytes())
    vm.demand(hashlib.sha256(INDEX.read_bytes()).hexdigest() in
              [v.get(INDEX.name) for v in reviewed.values() if isinstance(v,dict)],'REVIEWED_INDEX')
    state = json.loads(INDEX.read_bytes())
    admission = vm.collect()
    if admission['status']=='BLOCKED' and not admission['s0Checks']['mapCount']:
        adjust_map_count(admission)
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


def ready_source(fe, scratch=None):
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
    expected = ['dmq_entity','dmq_target']
    if scratch is not None:
        vm.demand(re.fullmatch('dmq_s0_[0-9a-f]{12}',scratch),'SHAPE_SCRATCH_NAME')
        expected.append(scratch)
    vm.demand(sql(fe,'reader','SHOW TABLES FROM fixture;').splitlines()==sorted(expected),'RESUME_FIXTURE')


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
    fe = state['services']['fe']['id']
    shape = None
    if method in ('driver-model-reject','driver-type-reject','driver-width-reject'):
        shape = json.loads(SHAPE.read_bytes())
        vm.demand(shape['phase']=='SWAPPED' and shape['method']==method and shape['services']==state['services'],'NEGATIVE_SHAPE_REQUIRED')
    else:
        vm.demand(not SHAPE.exists(),'SHAPE_ISOLATION')
    ready_source(fe,shape['scratch'] if shape else None)
    original = None
    if method=='driver-ac11':
        vm.demand(not STRESS.exists() and not (vm.OUTPUT/'s0-fixed-fixture-active.json').exists(),'AC11_ISOLATION')
        original = stress_original(fe,'dmq_entity','entity_id',('E1',))
        vm.demand(original=='7a7009c1fc43c542746436d44150f02f3e45cc2028fd375a142c03d5beccb34e' and
                  sql(fe,'reader','SELECT COUNT(*) FROM fixture.dmq_entity;')=='1','AC11_BASELINE')
    stress = None
    if method.startswith('driver-stress-'):
        vm.demand(not json.loads(STRESS.read_bytes()).get('entityTier'), 'S0_STRESS_BOUNDARY')
        stress = stress_binding(state)
    else:
        vm.demand(not STRESS.exists(),'STRESS_ISOLATION')
    env = dict(environment['environment'],DMQ_S0_SOURCE=str(DIRECTORY),DMQ_S0_EVIDENCE=str(vm.OUTPUT),
               DMQ_S0_BE_ID=state['services']['be']['id'],
               DOTNET_GCHeapHardLimit='0x18000000')
    test = {'driver-types':'RealDriverReadsFixedSource','driver-cancel':'ActiveBackendMustFinishInsideOriginalWindow',
            'driver-fixed-values':'FixedPlansReturnScopedValues','driver-fixed-entity':'FixedEntityCancellation',
            'driver-fixed-target':'FixedTargetCancellation','driver-stress-entity':'FixedEntityCancellation',
            'driver-stress-target':'FixedTargetCancellation','driver-ac11':'ControlledWriteBetweenSourceReads',
            'driver-model-reject':'FixedTargetRejectsUnsupportedShape','driver-type-reject':'FixedTargetRejectsUnsupportedShape',
            'driver-width-reject':'FixedTargetRejectsUnsupportedShape'}[method]
    key = execution.sha(execution.encoded([binding,hashlib.sha256(INDEX.read_bytes()).hexdigest(),test,
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),stress,shape]))
    result = execution.run([environment['dotnet'],str(vm.ROOT/'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0/OntologyPlatform.ConnectionsTests.dll'),
              '--filter','FullyQualifiedName=OntologyPlatform.ConnectionsTests.DorisMappingQueryTests.'+test,
              '--minimum-expected-tests','1','--results-directory',str(vm.OUTPUT/'driver-results'),'--no-ansi','--progress','off'],
              vm.ROOT,task=vm.TASK,run_id=vm.RUN,stage=method,input_key=key,environment=env,timeout=20)
    count = mtp(result.stdout+result.stderr,1) if result.returncode==0 else None
    receipt = dict(method=test,build=binding,stress=stress,shape=shape,command=result.receipt['commandId'],exitCode=result.returncode,passed=count)
    if original is not None:
        receipt['before'] = original
        receipt['after'] = stress_original(fe,'dmq_entity','entity_id',('E1',))
    record(vm.OUTPUT/(method+'-'+receipt['command']+'.json'),receipt)
    print(json.dumps(receipt))
    if original is not None: vm.demand(receipt['after']==original,'AC11_RESTORE')
    return result.returncode


def fixed_fixture(restore=False):
    """在两张原表内各补足至一百行。清理仅匹配本次新建的准确主键，最后核对逐行原字节。"""
    state=json.loads(INDEX.read_bytes())
    fe=state['services']['fe']['id']
    vm.demand(docker('fixed-fixture-owner','inspect','-f',
              '{{.Id}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Status}}',fe)
              ==' '.join([fe,vm.TASK,vm.RUN,'running']),'FIXED_FIXTURE_OWNER')
    ready_source(fe)
    vm.demand(not STRESS.exists(),'STRESS_ISOLATION')
    plan=[('dmq_entity','entity_id','E',['E1']),('dmq_target','target_id','T',['T1','T2','T3'])]
    pending=vm.OUTPUT/'s0-fixed-fixture-active.json'
    def snapshot(table,key):
        rows=sql(fe,'reader','SELECT * FROM fixture.'+table+' ORDER BY org_id,site_id,'+key+';')
        return hashlib.sha256(rows.encode()).hexdigest(),[line.split('\t') for line in rows.splitlines()]
    if restore:
        record_state=json.loads(pending.read_bytes())
        vm.demand(record_state['fe']==fe and record_state['run']==vm.RUN,'FIXED_FIXTURE_BINDING')
    else:
        vm.demand(not pending.exists(),'FIXED_FIXTURE_ALREADY_OPEN')
        record_state={'fe':fe,'run':vm.RUN,'attempt':secrets.token_hex(8),'tables':{}}
        for table,key,_,original in plan:
            digest,rows=snapshot(table,key)
            vm.demand([r[:3] for r in rows]==[['org-demo','site-a',v] for v in original],'FIXED_ORIGINAL_KEYS')
            record_state['tables'][table]={'before':digest}
        record(pending,record_state)
    for table,key,prefix,original in plan:
        keys=['DMQ_S0_'+prefix+format(i,'03d') for i in range(1,101-len(original))]
        entry=record_state['tables'][table]
        if restore:
            digest,rows=snapshot(table,key)
            if digest!=entry['before']:
                vm.demand(digest==entry.get('seeded') and len(rows)==100,'FIXED_DATA_DRIFT')
                # DELETE 只匹配本任务本次插入的完整复合键；保留所有正式夹具行。
                sql(fe,'root',"DELETE FROM fixture."+table+" WHERE org_id='org-demo' AND site_id='site-a' AND "+
                    key+" IN ("+','.join("'"+k+"'" for k in keys)+");")
            vm.demand(snapshot(table,key)[0]==entry['before'],'FIXED_RESTORE_CONTENT')
            entry['restored']=True
        else:
            payload="9.00,7.20,'K'" if table=='dmq_entity' else "8.000"
            dates="'2026-11-01','2026-12-01','2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456'"
            values=["('org-demo','site-a','"+k+"',"+payload+","+dates+")" for k in keys]
            sql(fe,'root','INSERT INTO fixture.'+table+' VALUES '+','.join(values)+';')
            digest,rows=snapshot(table,key)
            vm.demand(len(rows)==100 and all(r[:2]==['org-demo','site-a'] for r in rows)
                      and {r[2] for r in rows}==set(original+keys),'FIXED_BOUNDED_KEYS')
            entry.update(seeded=digest,inserted=len(keys))
        record(pending,record_state)
    result=vm.OUTPUT/('s0-fixed-fixture-'+record_state['attempt']+('-restored' if restore else '-seeded')+'.json')
    record(result,record_state)
    if restore: pending.unlink()
    print(result.relative_to(vm.ROOT))


def stress_resources(state, platform=False):
    """记录当前用量和容器历史高水位，在卷上独立预留本次短时写入的空间。"""
    live = docker('stress-live','ps','--no-trunc','-q').splitlines()
    if platform:
        from workflow_doris_s1 import HOST, live_stack
        approved=live_stack()
        vm.demand(json.loads(HOST.read_bytes())['status']=='EXITED' and set(live)==set(approved.values()),'STRESS_PLATFORM_IDLE')
        capacity=sum(int(docker('stress-quota','inspect','-f','{{.HostConfig.Memory}}',cid)) for cid in live)
        vm.demand(capacity==int(14.25*vm.GIB) and int(docker('stress-vm','info','-f','{{.MemTotal}}'))>=capacity+2*vm.GIB,'STRESS_PLATFORM_HEADROOM')
        active=docker('stress-drain','exec',approved['platform-pg'],'psql','-XwqAt','-U','postgres','-d','mapping','-c',
                      """SELECT (SELECT count(*) FROM connections."MappingJobs" WHERE "Status" IN ('QUEUED','RUNNING'))
                                   +(SELECT count(*) FROM semantic_query."Queries" WHERE "ExecutionStatus"='RUNNING');""")
        vm.demand(active=='0','STRESS_INFLIGHT_WORK')
    else:
        vm.demand(set(live)=={s['id'] for s in state['services'].values()},'STRESS_EXCLUSIVE_SOURCE')
    facts = {}
    for role,svc in state['services'].items():
        check = docker('stress-owner','inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task"}} {{index .Config.Labels "ontology.run"}} {{.State.Health.Status}} {{.HostConfig.Memory}}',svc['id']).split()
        cap = (4 if role=='fe' else 6)*vm.GIB
        vm.demand(check==[svc['id'],svc['image'],vm.TASK,vm.RUN,'healthy',str(cap)],'STRESS_OWNER_CAP')
        used,peak = map(int,docker('stress-memory','exec',svc['id'],'cat','/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory.peak').split())
        facts[role] = dict(currentBytes=used,cgroupPeakBytes=peak,capBytes=cap)
    volume = '/opt/apache-doris/be/storage'
    free = int(docker('stress-disk','exec',state['services']['be']['id'],'df','-Pk',volume).splitlines()[-1].split()[3])*1024
    facts['storageAvailableBytes'] = free
    return facts


def stress_original(fe,table,key,original):
    values = ','.join("'"+v+"'" for v in original)
    rows = sql(fe,'reader',f"SELECT * FROM fixture.{table} WHERE org_id='org-demo' AND site_id='site-a' AND {key} IN ({values}) ORDER BY org_id,site_id,{key};")
    vm.demand([r.split('\t')[:3] for r in rows.splitlines()]==[['org-demo','site-a',v] for v in original],'STRESS_ORIGINAL_KEYS')
    return hashlib.sha256(rows.encode()).hexdigest()


def stress_dimensions(table, original, entity_rows):
    if entity_rows is None:
        return 65536-len(original), 5
    vm.demand(entity_rows in ENTITY_TIERS, 'STRESS_ENTITY_TIER')
    return (entity_rows-len(original) if table == 'dmq_entity' else 0), 7


def stress_counts(fe,table,key,prefix,size,width=5):
    """计数仅承认本任务准确复合键、固定位数和序号区间；原行另行核对。"""
    vm.demand(re.fullmatch('DQ[0-9a-f]{12}',prefix) and width in (5,7)
              and 0<=size<(65536 if width==5 else max(ENTITY_TIERS)), 'STRESS_NAMESPACE')
    if not size:
        return [int(sql(fe,'reader',f'SELECT COUNT(*) FROM fixture.{table};')),0]
    scope = f"org_id='org-demo' AND site_id='site-a' AND {key} REGEXP '^{prefix}[0-9]{{{width}}}$' AND {key} BETWEEN '{prefix}{0:0{width}d}' AND '{prefix}{size-1:0{width}d}'"
    return list(map(int,sql(fe,'reader',f"SELECT COUNT(*),COUNT(IF({scope},1,NULL)) FROM fixture.{table};").split()))


def stress_binding(state):
    manifest = json.loads(STRESS.read_bytes())
    vm.demand(manifest['status']=='SEEDED' and manifest['source']==state['services'] and
              manifest['run']==vm.RUN,'STRESS_DRIVER_ADMISSION')
    fe = state['services']['fe']['id']
    counts = {}
    for table,key,original in STRESS_TABLES:
        count,width = stress_dimensions(table,original,manifest.get('entityTier'))
        counts[table] = count+len(original)
        vm.demand(manifest['tables'][table]['planned']==count and
                  stress_counts(fe,table,key,manifest['prefix'],count,width)==[counts[table],count] and
                  stress_original(fe,table,key,original)==manifest['tables'][table]['before'],'STRESS_DRIVER_DATA')
    result = dict(attempt=manifest['attempt'],manifestSha256=hashlib.sha256(STRESS.read_bytes()).hexdigest(),
                  rowsByTable=counts,purpose='cancellation_only')
    if 'entityTier' not in manifest: result['rowsPerTable']=65536
    return result


def tier_capacity(state):
    """实际六容器内存及 CPU 配额、命名卷使用量、源盘与宿主内存余量，只记录数值。"""
    import shutil
    from workflow_doris_s1 import live_stack
    ids = live_stack()
    memory,cpu = map(int,docker('tier-vm','info','-f','{{.MemTotal}} {{.NCPU}}').split())
    fmt = '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}={{.Destination}} {{end}}{{end}}'
    caps = cores = disk = 0
    for cid in ids.values():
        cap,nanos,*mounts = docker('tier-mount-caps','inspect','-f',fmt,cid).split()
        caps += int(cap)
        cores += int(nanos)
        persistent = []
        for mounted in mounts:
            name,destination = mounted.split('=',1)
            kind = docker('tier-vol-type','volume','inspect','-f','{{index .Options "type"}}',name)
            vm.demand(kind in ('','tmpfs'),'TIER_VOLUME_TYPE')
            if not kind: persistent.append(destination)
        if persistent:
            sizes = docker('tier-disk-usage','exec','-u','0',cid,'du','-sk',*persistent)
            disk += sum(int(row.split()[0])*1024 for row in sizes.splitlines())
    used = int(docker('tier-be-storage','exec',state['services']['be']['id'],'du','-sk','/opt/apache-doris/be/storage').split()[0])*1024
    host_disk = shutil.disk_usage(vm.ROOT).free
    host_pressure = int(re.search(r'free percentage:\s*(\d+)%',vm.host('memory_pressure','-Q')).group(1))
    host_memory = int(vm.host('sysctl','-n','hw.memsize'))
    vm.demand(caps==int(14.25*vm.GIB) and memory-caps>=2*vm.GIB and cores==9*10**9 and cpu>=12
              and host_disk>=12*vm.GIB and host_memory>=20*vm.GIB+int(5.5*vm.GIB)
              and host_pressure>0 and disk<4*vm.GIB,'TIER_RESOURCE_BUDGET')
    return dict(vmBytes=memory,vmCpus=cpu,containerCapBytes=caps,containerNanoCpus=cores,
                afterReserveBytes=memory-caps-2*vm.GIB,persistentVolumeBytes=disk,beStorageBytes=used,
                hostFreeBytes=host_disk,hostPhysicalBytes=host_memory,hostMemoryFreePercent=host_pressure)


def stress_fixture(restore=False, platform=False, batches=1, entity_rows=None, tied_event=False):
    """在唯一台账保护下临时扩充这两张合成表；与正式一百行门禁互斥。"""
    vm.demand(not tied_event or (platform and batches==1 and entity_rows==4194304 and not restore),'TIED_FIXTURE_SCOPE')
    vm.demand(batches in (1,8) and (batches==1 or platform),'STRESS_BATCH_BOUNDARY')
    vm.demand(entity_rows is None or (entity_rows in ENTITY_TIERS and platform and batches==1),'STRESS_TIER_SCOPE')
    state = json.loads(INDEX.read_bytes())
    vm.demand(not SHAPE.exists() and state['project']==PROJECT and state['runId']==vm.RUN and state['taskId']==vm.TASK and
              not (vm.OUTPUT/'s0-fixed-fixture-active.json').exists(),'STRESS_FIXTURE_SCOPE')
    resources = stress_resources(state,platform)
    fe = state['services']['fe']['id']
    ready_source(fe)
    if restore:
        manifest = json.loads(STRESS.read_bytes())
        vm.demand(manifest['source']==state['services'] and manifest['run']==vm.RUN and
                  manifest['prefix']=='DQ'+manifest['attempt'] and re.fullmatch('[0-9a-f]{12}',manifest['attempt']),'STRESS_RESTORE_OWNER')
    else:
        vm.demand(not STRESS.exists() and resources['storageAvailableBytes']>=2*vm.GIB and
                  all(resources[r]['capBytes']-resources[r]['currentBytes']>=vm.GIB//2 for r in ('fe','be')),'STRESS_CAPACITY_OR_PENDING')
        reviewed = json.loads((vm.ROOT/'docs/evidence'/vm.TASK/vm.RUN/'s0-fixed-plan-review.json').read_bytes())['hashes']
        baseline = vm.OUTPUT/'s0-fixed-fixture-0da9ac2fd127ad4f-restored.json'
        vm.demand(hashlib.sha256(baseline.read_bytes()).hexdigest()==reviewed[vm.RUN+'/'+baseline.name],'STRESS_REVIEWED_BASELINE')
        previous = json.loads(baseline.read_bytes())
        attempt = secrets.token_hex(6)
        manifest = dict(attempt=attempt,prefix='DQ'+attempt,run=vm.RUN,source=state['services'],status='INTENT',
                        beforeResources=resources,tables={},purpose='cancellation_only')
        if tied_event: manifest['temporaryEntityEventAt']='2026-11-17 12:00:00.123456'
        if entity_rows is not None:
            manifest.update(entityTier=entity_rows,tierCapacity=tier_capacity(state))
        for table,key,original in STRESS_TABLES:
            count,width = stress_dimensions(table,original,entity_rows)
            before = stress_original(fe,table,key,original)
            vm.demand(stress_counts(fe,table,key,manifest['prefix'],count,width)==[len(original),0] and
                      previous['tables'][table]['before']==before and previous['tables'][table]['restored'],'STRESS_BASELINE')
            manifest['tables'][table] = dict(before=before,planned=count)
        with STRESS.open('x') as out:
            json.dump(manifest,out,indent=2)
            out.flush()
            os.fsync(out.fileno())
        sync_directory(STRESS.parent)
    for table,key,original in STRESS_TABLES:
        entry = manifest['tables'][table]
        tier = manifest.get('entityTier')
        count,width = stress_dimensions(table,original,tier)
        prefix = manifest['prefix']
        vm.demand(entry['planned']==count and stress_original(fe,table,key,original)==entry['before'],'STRESS_PRIOR_ROWS')
        if restore:
            total,owned = stress_counts(fe,table,key,prefix,count,width)
            vm.demand(total==len(original)+owned,'STRESS_FOREIGN_ROWS')
            if owned and tier:
                # 从最初独占登记的准确键域生成三列主键，中断在批次落盘前也能恢复。
                for offset in range(0,count,65536):
                    n = min(65536,count-offset)
                    expected = (f"SELECT CONCAT('{prefix}',LPAD(CAST(number+{offset} AS STRING),{width},'0')) AS owned_key "
                                f'FROM numbers("number"="{n}")')
                    sql(fe,'root',f"DELETE FROM fixture.{table} USING ({expected}) owned WHERE "
                        f"{table}.org_id='org-demo' AND {table}.site_id='site-a' AND {table}.{key}=owned.owned_key;",limit=60)
            elif owned:
                for start in range(0,count,2048):
                    values = ','.join(f"'{prefix}{i:05d}'" for i in range(start,min(start+2048,count)))
                    sql(fe,'root',f"DELETE FROM fixture.{table} WHERE org_id='org-demo' AND site_id='site-a' AND {key} IN ({values});",limit=40)
            vm.demand(stress_counts(fe,table,key,prefix,count,width)==[len(original),0],'STRESS_RESTORE_COUNT')
            entry['after'] = stress_original(fe,table,key,original)
            vm.demand(entry['after']==entry['before'],'STRESS_RESTORE_BYTES')
        else:
            payload = "1.00,7.20,'K'" if key=='entity_id' else '1.000'
            event = "CONCAT('2026-11-17 12:00:00.',LPAD(CAST(MOD(number*8191,1000000) AS STRING),6,'0'))"
            if tied_event and table=='dmq_entity':
                event="'2026-11-17 12:00:00.123456'"
            size = 65536 if tier else (count if batches == 1 else 8192)
            entry['batches'] = []
            for offset in range(0, count, size):
                n = min(size, count-offset)
                insert = (f"INSERT INTO fixture.{table} SELECT 'org-demo','site-a',CONCAT('{prefix}',LPAD(CAST(number AS STRING),{width},'0')),"
                          f"{payload},'2026-11-01','2026-12-01',{event},'2026-11-17 12:00:01.123456' "
                          f'FROM (SELECT number+{offset} AS number FROM numbers("number"="{n}")) fixture_keys;')
                entry['batches'].append(dict(offset=offset, count=n, sha256=hashlib.sha256(insert.encode()).hexdigest()))
                record(STRESS,manifest)
                sql(fe,'root',insert,limit=60)
                vm.demand(stress_counts(fe,table,key,prefix,count,width)==[len(original)+offset+n,offset+n],'STRESS_SEED_COUNT')
                if (batches > 1 or tier) and (not tier or offset+n == count or offset % (4*size)==0):
                    facts = stress_resources(state,platform)
                    vm.demand(facts['storageAvailableBytes']>=2*vm.GIB and all(facts[r]['capBytes']-facts[r]['currentBytes']>=vm.GIB//2 for r in ('be','fe'))
                              and stress_original(fe,table,key,original)==entry['before'],'STRESS_BATCH_RESOURCES')
                    if tier:
                        used = int(docker('tier-growth','exec',state['services']['be']['id'],'du','-sk','/opt/apache-doris/be/storage').split()[0])*1024
                        baseline = manifest['tierCapacity']
                        vm.demand(baseline['persistentVolumeBytes']+max(0,used-baseline['beStorageBytes'])<4*vm.GIB,'TIER_DISK_GROWTH')
                        facts['beStorageBytes']=used
                    entry['batches'][-1]['resources']=facts
            if batches > 1 or tier:
                tablets = [int(row.split('\t')[0]) for row in sql(fe,'root',f'SHOW TABLETS FROM fixture.{table};').splitlines()]
                vm.demand(bool(tablets) and all(t>0 for t in tablets),'STRESS_TABLETS')
                ids=','.join(map(str,tablets))
                entry['rowsetSample'] = sql(fe,'root',f'SELECT TABLET_ID,COUNT(*),SUM(NUM_SEGMENTS) FROM information_schema.rowsets WHERE TABLET_ID IN ({ids}) GROUP BY TABLET_ID ORDER BY TABLET_ID;')
            entry['inserted'] = count
        record(STRESS,manifest)
    manifest['status'] = 'RESTORED' if restore else 'SEEDED'
    manifest[manifest['status'].lower()+'Resources'] = stress_resources(state,platform)
    if manifest.get('entityTier'):
        manifest[manifest['status'].lower()+'Capacity'] = tier_capacity(state)
    record(STRESS,manifest)
    path = vm.OUTPUT/('s0-stress-fixture-'+manifest['attempt']+'-'+manifest['status'].lower()+'.json')
    record(path,manifest)
    if restore:
        STRESS.unlink()
        sync_directory(STRESS.parent)
    print(path.relative_to(vm.ROOT),manifest['status'])


def shape_case(method,prepared,activation=False):
    """按 tablet 身份交换同名目标表，真实拒绝后交换回原件，只回收本次创建的空负例。"""
    state = json.loads(INDEX.read_bytes())
    vm.demand(not STRESS.exists() and not SHAPE.exists() and not (vm.OUTPUT/'s0-fixed-fixture-active.json').exists(),'SHAPE_FIXTURE_BUSY')
    stress_resources(state,platform=activation or method=='driver-width-reject')
    fe = state['services']['fe']['id']
    ready_source(fe)
    def tablet(name):
        rows = list(csv.DictReader(sql(fe,'root','SHOW TABLETS FROM fixture.'+name+';',True).splitlines(),delimiter='\t'))
        vm.demand(len(rows)==1 and rows[0]['TabletId'].isdigit(),'SHAPE_TABLET')
        return rows[0]['TabletId']
    def digest():
        return stress_original(fe,'dmq_target','target_id',('T1','T2','T3'))
    original = tablet('dmq_target')
    before = digest()
    vm.demand(before=='4fce66991c1a560ee3acc8de573c1077e5f669f68971ad08d55c06e50364191f' and
              sql(fe,'reader','SELECT COUNT(*) FROM fixture.dmq_target;')=='3','SHAPE_BASELINE')
    nonce = secrets.token_hex(6)
    scratch = 'dmq_s0_'+nonce
    ddl = fixture_tables()[1].replace('fixture.dmq_target','fixture.'+scratch)
    if method=='driver-model-reject':
        ddl = ddl.replace('UNIQUE KEY','DUPLICATE KEY').replace(', "enable_unique_key_merge_on_write"="true"','')
    elif method=='driver-width-reject':
        ddl = ddl.replace('target_id VARCHAR(32)','target_id VARCHAR(512)')
    else:
        vm.demand(method=='driver-type-reject','NEGATIVE_METHOD')
        ddl = ddl.replace('DECIMAL(12,3)','DOUBLE')
    change = dict(method=method,phase='INTENT',attempt=nonce,original=original,scratch=scratch,before=before,
                  expectedDdlSha256=hashlib.sha256(ddl.encode()).hexdigest(),services=state['services'])
    with SHAPE.open('x') as out:
        json.dump(change,out)
        out.flush()
        os.fsync(out.fileno())
    sql(fe,'root',ddl+';')
    variant = tablet(scratch)
    vm.demand(variant!=original and sql(fe,'root','SELECT COUNT(*) FROM fixture.'+scratch+';')=='0','SHAPE_VARIANT')
    change.update(variant=variant,phase='CREATED')
    record(SHAPE,change)
    swap = 'USE fixture; ALTER TABLE dmq_target REPLACE WITH TABLE '+scratch+' PROPERTIES("swap"="true");'
    try:
        sql(fe,'root',swap)
        vm.demand(tablet('dmq_target')==variant and tablet(scratch)==original,'SHAPE_SWAP')
        observed = sql(fe,'root','SHOW CREATE TABLE fixture.dmq_target;')
        key = re.findall(r'^(UNIQUE|DUPLICATE|AGGREGATE) KEY\(`org_id`, `site_id`, `target_id`\)$',observed,re.M)
        field = re.findall(r'^\s*`join_key` (decimal\(12,3\)|double) NULL,$',observed,re.M)
        width = re.findall(r'^\s*`target_id` varchar\((\d+)\) NOT NULL,$',observed,re.M)
        expected = {'driver-model-reject':(['DUPLICATE'],['decimal(12,3)'],['32']),
                    'driver-type-reject':(['UNIQUE'],['double'],['32']),
                    'driver-width-reject':(['UNIQUE'],['decimal(12,3)'],['512'])}[method]
        vm.demand((key,field,width)==expected,'SHAPE_CONTROL_CAUSE')
        change.update(phase='SWAPPED',actualDdlSha256=hashlib.sha256(observed.encode()).hexdigest(),
                      keyModel=key[0],keyColumns=['org_id','site_id','target_id'],nativeJoinKey=field[0],targetIdWidth=int(width[0]))
        record(SHAPE,change)
        if activation:
            from workflow_doris_s1 import browser_test
            browser_test('s2-doris-shape-reject',prepared)
            code = 0
            change['case'] = 'activation_after_approved_assessment'
        else:
            code = driver(prepared,method)
        change['exitCode'] = code
    finally:
        current = (tablet('dmq_target'),tablet(scratch))
        if current==(variant,original):
            sql(fe,'root',swap)
        vm.demand((tablet('dmq_target'),tablet(scratch))==(original,variant) and digest()==before and
                  sql(fe,'root','SELECT COUNT(*) FROM fixture.'+scratch+';')=='0','SHAPE_RESTORE')
        sql(fe,'root','DROP TABLE fixture.'+scratch+';')
        ready_source(fe)
        change.update(phase='RESTORED',after=digest(),restoredTablet=tablet('dmq_target'))
        record(vm.OUTPUT/('s0-shape-'+nonce+'-restored.json'),change)
        SHAPE.unlink()
    return code


def capabilities():
    vm.demand(not STRESS.exists(),'STRESS_ISOLATION')
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
    parser.add_argument('stage',choices=['create','resume','capabilities','driver-types','driver-cancel',
                        'stress-seed','stress-restore','s2-stress-seed','s2-stress-restore','driver-stress-entity','driver-stress-target','driver-ac11',
                        'driver-model-reject','driver-type-reject','driver-width-reject',
                        'fixed-seed','fixed-restore','driver-fixed-values','driver-fixed-entity','driver-fixed-target','stop'])
    parser.add_argument('--prepared',type=Path)
    args=parser.parse_args()
    stage=args.stage
    if stage.startswith('driver-'):
        if args.prepared is None: parser.error('--prepared required')
        if stage in ('driver-model-reject','driver-type-reject','driver-width-reject'):
            raise SystemExit(shape_case(stage,args.prepared))
        raise SystemExit(driver(args.prepared,stage))
    {'create':create, 'resume':resume, 'capabilities':capabilities, 'fixed-seed':fixed_fixture,
     'fixed-restore':lambda:fixed_fixture(True), 'stress-seed':stress_fixture,
     's2-stress-seed':lambda:stress_fixture(platform=True), 's2-stress-restore':lambda:stress_fixture(True,True), 'stress-restore':lambda:stress_fixture(True), 'stop':stop}[stage]()
