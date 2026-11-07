#!/usr/bin/env python3
"""准确任务的有界真实HTTPS测试；零拉取，精确ID记录及回收。"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import workflow_m2_build as build

TASK='G4-M2-WEB-01'
ROOT=Path(__file__).resolve().parents[2]
NODE='node@sha256:a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f'
DOTNET='mcr.microsoft.com/dotnet/aspnet@sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55'
ASSEMBLY=ROOT/'backend/tests/OntologyPlatform.ConnectionsTests/bin/Debug/net10.0'


def command(args,timeout=60):
    result=subprocess.run(args,capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError('FIXTURE_COMMAND_FAILED: '+args[0])
    return result.stdout.decode().strip()


def docker(*args,timeout=60):return command(['docker','--context','desktop-linux',*args],timeout)


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)


def certificate(private,name,hostname,ca):
    command(['openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',str(private/(name+'.key')),'-out',str(private/(name+'.csr')),'-subj','/CN='+hostname])
    extension=private/(name+'.ext');extension.write_text('subjectAltName=DNS:'+hostname+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
    command(['openssl','x509','-req','-in',str(private/(name+'.csr')),'-CA',str(private/(ca+'.crt')),'-CAkey',str(private/(ca+'.key')),'-set_serial',str(secrets.randbits(120)),'-out',str(private/(name+'.crt')),'-days','2','-extfile',str(extension)])


def prepare(private,run_id):
    """只在当前任务新建目录生成独立CA与合成密钥。"""
    for ca in ('ca','untrusted'):
        command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(private/(ca+'.key')),'-out',str(private/(ca+'.crt')),'-days','2','-subj','/CN='+run_id+'-'+ca,'-addext','basicConstraints=critical,CA:TRUE'])
    for name,host,ca in [('server','web-source','ca'),('wrong-san','wrong-source','ca'),('wrong-ca','web-source','untrusted')]:certificate(private,name,host,ca)
    (private/'api-key').write_text(secrets.token_hex(32));write(private/'control.json',{'mode':'normal'})
    write(private/'input.json',dict(TaskId=TASK,RunId=run_id,KeyPath='/fixture/api-key',RootCertificatePath='/fixture/ca.crt'))
    for path in private.iterdir():path.chmod(0o600)


def run(task):
    if task!=TASK:raise ValueError('TASK_ID')
    binding=build.validate('connections')
    # 准入真实消费者：程序集、源脚本及所有已缓存镜像必须存在。
    for image in (NODE,DOTNET):docker('image','inspect',image)
    if not (ASSEMBLY/'OntologyPlatform.ConnectionsTests.dll').is_file():raise ValueError('CONSUMER_MISSING')
    subnet=ipaddress.ip_network('172.30.240.0/24')
    for ident in docker('network','ls','-q').splitlines():
        info=json.loads(docker('network','inspect',ident))[0]
        for row in info.get('IPAM',{}).get('Config') or []:
            value=row.get('Subnet')
            if value and ipaddress.ip_network(value).version==4 and ipaddress.ip_network(value).overlaps(subnet):raise ValueError('SUBNET_IN_USE')
    run_id='m2-'+secrets.token_hex(6)
    private=ROOT/'.tools/security/g4-m2-web-01'/run_id;private.mkdir(parents=True,mode=0o700)
    output=ROOT/'artifacts/workflow'/TASK/run_id;output.mkdir(parents=True)
    state=dict(driverInputs=build.driver_inputs(),buildBinding=binding,taskId=TASK,runId=run_id,status='STARTING',containerIds=[],networkId=None,tests=[],privateRuntime=str(private),cleanup=[])
    receipt=output/'fixture-receipt.json'
    def save():write(receipt,state)
    save()
    prepare(private,run_id)
    labels=['--label','ontology.task='+TASK,'--label','ontology.run='+run_id]
    try:
        state['networkId']=docker('network','create','--internal','--subnet',str(subnet),*labels,run_id);save()
        source=docker('create','--pull=never','--name',run_id+'-source',*labels,'--network',state['networkId'],'--ip','172.30.240.10','--network-alias','web-source','--memory','256m','--cpus','0.5','--pids-limit','64','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','-e','TASK_ID='+TASK,'-e','RUN_ID='+run_id,'-v',str(private)+':/fixture:rw','-v',str(ROOT/'experiments/g4-m2-web-01/https-fixture.mjs')+':/fixture.mjs:ro',NODE,'node','/fixture.mjs')
        state['containerIds'].append(source);save();docker('start',source)
        for _ in range(60):
            if (private/'stats.json').exists():break
            time.sleep(.1)
        if not (private/'stats.json').exists():raise RuntimeError('SOURCE_NOT_READY')
        for category,minimum,negative in [('RealWebFixture',12,False),('RealWebDnsRejection',1,True)]:
            args=['create','--pull=never','--name',run_id+'-'+category.lower(),*labels,'--network',state['networkId'],'--memory','512m','--cpus','1','--pids-limit','96','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:size=64m','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','TESTINGPLATFORM_TELEMETRY_OPTOUT=1','-e','DOTNET_EnableDiagnostics=0','-e','DOTNET_PROCESSOR_COUNT=2','-e','G4_WEB_FIXTURE_INPUT=/fixture/input.json','-v',str(private)+':/fixture:rw','-v',str(ASSEMBLY)+':/app:ro','-v',str(output)+':/results:rw']
            if negative:args+=['--add-host','web-source:169.254.169.254','-e','G4_WEB_DNS_REJECTION=true']
            args += [DOTNET,'dotnet','/app/OntologyPlatform.ConnectionsTests.dll','--filter','TestCategory='+category,'--minimum-expected-tests',str(minimum),'--results-directory','/results/'+category,'--no-ansi','--progress','off']
            ident=docker(*args);state['containerIds'].append(ident);save()
            before=time.monotonic();docker('start',ident)
            while True:
                observation=json.loads(docker('inspect',ident))[0]['State']
                (output/(category+'.log')).write_text(docker('logs',ident)+'\n')
                if not observation['Running']:break
                if time.monotonic()-before>45:raise RuntimeError('REAL_TEST_TIMEOUT: '+category)
                time.sleep(1)
            exit_code=observation['ExitCode']
            log=docker('logs',ident);(output/(category+'.log')).write_text(log+'\n')
            state['tests'].append(dict(category=category,exitCode=exit_code,seconds=time.monotonic()-before,minimumExpected=minimum,logSha256=hashlib.sha256((log+'\n').encode()).hexdigest()));save()
            if exit_code:raise RuntimeError('REAL_TEST_FAILED: '+category)
        state['sourceStats']=json.loads((private/'stats.json').read_text())
        if build.validate('connections')!=binding:raise ValueError('BUILD_CHANGED')
        state['status']='PASS'
    except Exception as error:
        state['status']='FAIL';state['reason']=str(error)
    finally:
        build.begin_cleanup(state,[*state['containerIds'],*([state['networkId']] if state['networkId'] else [])]);save()
        for ident in reversed(state['containerIds']):
            before=json.loads(docker('inspect',ident))[0]
            (output/(ident[:12]+'.log')).write_text(docker('logs',ident)+'\n')
            if before['Config']['Labels'].get('ontology.task')!=TASK or before['Config']['Labels'].get('ontology.run')!=run_id:raise RuntimeError('CLEANUP_OWNERSHIP')
            result=docker('rm','-f',ident)
            after=docker('ps','-aq','--no-trunc','--filter','id='+ident)
            state['cleanup'].append(dict(id=ident,before=True,command='docker rm -f exact-id',result=result,afterAbsent=not after));save()
        if state['networkId']:
            ident=state['networkId'];docker('network','rm',ident)
            after=docker('network','ls','--no-trunc','-q','--filter','id='+ident)
            state['cleanup'].append(dict(id=ident,before=True,command='docker network rm exact-id',afterAbsent=not after))
        build.finish_cleanup(state)
        if state['driverInputs']!=build.driver_inputs():state['status']='FAIL'
        state['privateRuntimeDisposition']='KEEP: task-owned credentials excluded from ZIP; required until final lifecycle review'
        save()
    return dict(status=state['status'],receipt=str(receipt),runId=run_id)


def pg_regression(task):
    """新任务独立PG回归；只运行受影响的真实TLS/只读/原生类型与认证负例。"""
    import workflow_smoke as shared
    if task!=TASK:raise ValueError('TASK_ID')
    binding=build.validate('connections');run_id='m2-'+secrets.token_hex(6)
    private=ROOT/'.tools/security'/TASK.lower()/run_id;private.mkdir(parents=True,mode=0o700)
    output=ROOT/'artifacts/workflow'/TASK/run_id;output.mkdir(parents=True)
    shared.fixture(ROOT,private,run_id,task=TASK)
    sql=private/'init.sql';sql.write_text(sql.read_text().replace('tap_temp numeric(8,2));','tap_temp numeric(8,2), tap_ts timestamp, event_time timestamptz, payload jsonb, tags text[], nullable text);'))
    compose=private/'compose.json';config=shared.recipe(ROOT,private,run_id,compose,task=TASK)
    config['services']={'pg-source':config['services']['pg-source']};config['networks']={'source':config['networks']['source']};config['volumes']={'source-data':config['volumes']['source-data']};shared.replace_manifest(compose,config)
    write(private/'adapter-input.json',{'fixtureIdentity':TASK,'secretFile':'/run/secrets/reader-password','rootCertificatePath':'/run/secrets/ca.crt'})
    prefix=['docker','--context','desktop-linux','compose','-f',str(compose)]
    state=dict(driverInputs=build.driver_inputs(),taskId=TASK,runId=run_id,status='FAIL',buildBinding=binding,containers=[],cleanup=[])
    receipt=output/'pg-receipt.json';write(receipt,state)
    try:
        shared.command([*prefix,'create','--pull','never','pg-source'],cwd=ROOT)
        source=shared.command([*prefix,'ps','--all','-q','pg-source'],cwd=ROOT).decode().strip();state['containers'].append(source);write(receipt,state)
        docker('start',source)
        for _ in range(80):
            if json.loads(docker('inspect',source))[0]['State'].get('Health',{}).get('Status')=='healthy':break
            time.sleep(.25)
        network=config['networks']['source']['name']
        test=docker('create','--pull=never','--name',run_id+'-pg-test','--label','ontology.task-id='+TASK,'--label','ontology.run-id='+run_id,'--network',network,'--memory','512m','--cpus','1','--pids-limit','96','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:size=64m','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','TESTINGPLATFORM_TELEMETRY_OPTOUT=1','-e','DOTNET_PROCESSOR_COUNT=2','-e','G4_PG_ADAPTER_TEST_INPUT=/run/secrets/adapter-input.json','-v',str(private)+':/run/secrets:ro','-v',str(ASSEMBLY)+':/app:ro','-v',str(output)+':/results:rw',DOTNET,'dotnet','/app/OntologyPlatform.ConnectionsTests.dll','--filter','FullyQualifiedName~PgAdapterTests.RealFixturePreservesAuthorizedMetadata','--minimum-expected-tests','1','--results-directory','/results/test','--no-ansi','--progress','off')
        state['containers'].append(test);write(receipt,state);docker('start',test);code=int(docker('wait',test,timeout=40));log=docker('logs',test);(output/'pg-test.log').write_text(log+'\n')
        state.update(exitCode=code,logSha256=hashlib.sha256((log+'\n').encode()).hexdigest(),tests=1)
        if code==0 and build.validate('connections')==binding:state['status']='PASS'
    finally:
        build.begin_cleanup(state,[*state['containers'],*[item['name'] for collection in ('volumes','networks') for item in config[collection].values()]]);write(receipt,state)
        for ident in reversed(state['containers']):
            before=json.loads(docker('inspect',ident))[0]
            if before['Config']['Labels'].get('ontology.task-id')!=TASK or before['Config']['Labels'].get('ontology.run-id')!=run_id:raise ValueError('PG_CLEANUP_OWNER')
            (output/(ident[:12]+'.log')).write_text(docker('logs',ident)+'\n')
            docker('rm','-f',ident);after=docker('ps','-aq','--no-trunc','--filter','id='+ident)
            state['cleanup'].append(dict(kind='container',id=ident,before=True,command='docker rm -f exact-id',afterAbsent=not after));write(receipt,state)
        for kind,collection in [('volume','volumes'),('network','networks')]:
            for item in config[collection].values():
                name=item['name'];before=json.loads(docker(kind,'inspect',name))[0]
                if before['Labels'].get('ontology.task-id')!=TASK or before['Labels'].get('ontology.run-id')!=run_id:raise ValueError('PG_CLEANUP_OWNER')
                docker(kind,'rm',name);after=docker(kind,'ls','--format','{{.Name}}','--filter','name='+name).splitlines()
                state['cleanup'].append(dict(kind=kind,id=name,before=True,command='docker '+kind+' rm exact-id',afterAbsent=name not in after))
        build.finish_cleanup(state)
        if state['driverInputs']!=build.driver_inputs():state['status']='FAIL'
        write(receipt,state)
    return dict(status=state['status'],receipt=str(receipt))
