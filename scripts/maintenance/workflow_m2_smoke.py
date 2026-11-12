#!/usr/bin/env python3
"""M2专属真实OIDC/API/UI消费者；复用受控工程设施函数，拒绝历史runtime。"""
import json
import os
from pathlib import Path
import secrets
import time
from workflow_execution import CONTEXT
import socket
import ipaddress
import workflow_m2_build as build
import workflow_smoke as shared
import workflow_m2_fixture as https

TASK=https.TASK
ROOT=https.ROOT
SERVICES=('web-source','platform-pg','keycloak-test','api','web')


def budget(runtime,private,evidence):
    """当前任务实际用量；受控tmpfs总容量低于3GiB停止线。"""
    data={}
    for service,path in [('platform-pg','/var/lib/postgresql'),('keycloak-test','/opt/keycloak/data'),('api','/keyring')]:
        data[service]=int(shared.docker(ROOT,'exec',runtime['containerIds'][service],'du','-sk',path).decode().split()[0])*1024
    local=sum(path.stat().st_size for directory in (private,evidence) for path in directory.rglob('*') if path.is_file())
    shared.require(sum(data.values())+local<3*1024**3 and local<1024**3,'M2_RESOURCE_STOP_THRESHOLD')
    return {'dataBytes':data,'privateAndOutputBytes':local,'dataStopBytes':3*1024**3,'outputStopBytes':1024**3}


def short_browser(private,node):
    """复用已验登录/API帮助函数和明确取消断言，不执行自然TTL阶段。"""
    source=(ROOT/'scripts/maintenance/workflow-m2-web.mjs').read_text()
    prefix=source[:source.index(" phase='csrf';")]
    csrf=source[source.index(" phase='csrf';"):source.index(" phase='negative_binding';")]
    cancel=source[source.index(" await mode('normal');let cancelRow="):source.index(" phase='natural_expiry';")]
    ending=source[source.index('}catch(error)'):]
    script=prefix+csrf+cancel+" console.log(JSON.stringify({status:'PASS',tests:checks.length,skipped:0,taskId:runtime.taskId,productAdmissionTaskId:'G4-M2-WEB-01',runId:runtime.runId,checks}));\n"+ending
    script=script.replace("const root=resolve(import.meta.dirname,'../..');",'const root='+json.dumps(str(ROOT))+';')
    script=script.replace('g4-m2-web-01', 'g4-eng-delivery-002').replace("runtime.taskId==='G4-M2-WEB-01'", "runtime.taskId==='G4-ENG-DELIVERY-002'")
    # 产品 HostPolicy 是被冻结的正式准入语义，不能随工程身份替换。
    script=script.replace("hostPolicyRef:'g4-eng-delivery-002'", "hostPolicyRef:'g4-m2-web-01'")
    path=private/'short-api.mjs';shared.private_write(path,script)
    from workflow_execution import run
    result=run(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))',node,str(path),str(private/'runtime.json')],ROOT,task='G4-ENG-DELIVERY-002',stage='short-api',timeout=90)
    return result.stdout,result.returncode


def run(task,node):
    shared.require(task in (build.TASK,'G4-ENG-DELIVERY-002'),'M2_TASK')
    TASK=task
    binding={target:build.validate(target,task) for target in ('api','web')}
    for port in (15100,15180,15432):
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    for ident in https.docker('network','ls','-q').splitlines():
        info=json.loads(https.docker('network','inspect',ident))[0]
        for row in info.get('IPAM',{}).get('Config') or []:
            value=row.get('Subnet')
            if value and ipaddress.ip_network(value).version==4 and ipaddress.ip_network(value).overlaps(ipaddress.ip_network('172.30.240.0/24')):raise ValueError('SUBNET_IN_USE')
    run_id='m2-'+secrets.token_hex(6)
    private=ROOT/'.tools/security'/TASK.lower()/run_id;private.mkdir(parents=True,mode=0o700)
    evidence=ROOT/'artifacts/workflow'/TASK/'smoke'/run_id;evidence.mkdir(parents=True)
    runtime=shared.fixture(ROOT,private,run_id,task=TASK)
    web_private=private/'web-source';web_private.mkdir(mode=0o700);https.prepare(web_private,run_id)
    runtime.update(engine=shared.engine(ROOT),containerIds={},imageIds={},webFixture=str(web_private),sourceSecretFile=str(web_private/'api-key'))
    compose=private/'compose.json';config=shared.recipe(ROOT,private,run_id,compose,task=TASK)
    config['services'].pop('pg-source');config['volumes'].pop('source-data')
    # 无公开端口的唯一精确合成源，API只通过当前隔离source网络访问。
    config['networks']['source']['ipam']={'config':[{'subnet':'172.30.240.0/24'}]}
    config['services']['web-source']={
        'image':https.NODE,'pull_policy':'never','platform':'linux/arm64','mem_limit':256*1024**2,'cpus':.5,'pids_limit':64,'read_only':True,
        'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
        'labels':{'ontology.task-id':TASK,'ontology.run-id':run_id,'ontology.synthetic':'true'},
        'environment':{'TASK_ID':build.TASK,'RUN_ID':run_id},'command':['node','/fixture.mjs'],
        'networks':{'source':{'ipv4_address':'172.30.240.10'}},
        'volumes':[{'type':'bind','source':str(web_private),'target':'/fixture'}, {'type':'bind','source':str(ROOT/'experiments/g4-m2-web-01/https-fixture.mjs'),'target':'/fixture.mjs','read_only':True}]}
    config['services']['api']['volumes'].append({'type':'bind','source':str(web_private/'ca.crt'),'target':'/web-ca.crt','read_only':True})
    shared.replace_manifest(compose,config)
    prefix=['docker','--context',shared.CONTEXT,'compose','-f',str(compose)]
    for service in SERVICES:
        reference=https.NODE if service=='web-source' else shared.IMAGES[service]
        image=json.loads(shared.docker(ROOT,'image','inspect',reference))[0];shared.validate_image(image,reference)
        runtime['imageIds'][service]=image['Id']
    receipt=dict(environmentFingerprint=CONTEXT.get().get('environment_key'),driverInputs=build.driver_inputs(),taskId=TASK,runId=run_id,status='FAIL',buildBinding=binding,tests=0)
    shared.private_write(evidence/'resources.json',shared.resource_manifest(ROOT,runtime,config,private,'PLANNED'))
    relay=None
    try:
        shared.command([*prefix,'create','--pull','never',*SERVICES],cwd=ROOT,timeout=90)
        for service in SERVICES:runtime['containerIds'][service]=shared.command([*prefix,'ps','--all','--quiet',service],cwd=ROOT).decode().strip()
        shared.replace_manifest(evidence/'resources.json',shared.resource_manifest(ROOT,runtime,config,private,'CREATED'))
        shared.command([*prefix,'start',*SERVICES],cwd=ROOT,timeout=90)
        relay=shared.HostRelay(ROOT,runtime).start()
        shared.wait_http('http://localhost:15180/realms/master/.well-known/openid-configuration',timeout=120)
        env=dict(os.environ,WAVE2_KEYCLOAK_ADMIN_PASSWORD=(private/'keycloak-password').read_text())
        shared.command(['python3','-B',str(ROOT/'infra/security/bootstrap-keycloak.py'),'--profile','g2','--keycloak-origin','http://localhost:15180','--public-origin',runtime['publicOrigin'],'--runtime-output',runtime['realmFile']],cwd=ROOT,env=env)
        realm=json.loads(Path(runtime['realmFile']).read_text())
        api={'ConnectionStrings':{'governance':'Host=platform-pg;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()},
             'Security':{'Authority':realm['authority'],'ClientId':realm['clientId'],'ClientSecret':realm['clientSecret'],'PublicOrigin':runtime['publicOrigin'],'KeyRingPath':'/keyring','CertificatePath':'/private/api/keyring.pfx','CertificatePassword':runtime['certificatePassword'],'HealthKey':runtime['healthKey']},
             'Web':{'Origin':'http://127.0.0.1:15300'},'G2':{'Enabled':False},
             'G4':{'Enabled':True,'ApplyMigrations':True,'KeyFile':'/private/api/g4-key','SourceCaPath':'/private/api/ca.crt','AllowEmptyPublicSchema':True,'Web':{'TaskId':build.TASK,'RunId':run_id,'RootCertificatePath':'/web-ca.crt'}},
             'Governance':{'ApplyMigrations':True,'SeedDevelopmentResources':True},'Logging':{'LogLevel':{'Default':'Warning'}}}
        shared.private_write(private/'api/appsettings.json',api)
        shared.wait_http(runtime['publicOrigin']+'/health/live',headers={'X-Health-Key':runtime['healthKey']},timeout=60)
        shared.private_write(private/'runtime.json',runtime)
        before=shared.snapshot(ROOT,runtime)
        receipt['budgetBefore']=budget(runtime,private,evidence)
        args=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))',node,str(ROOT/'scripts/maintenance/workflow-m2-web.mjs'),str(private/'runtime.json')]
        stdout,code=short_browser(private,node) if task=='G4-ENG-DELIVERY-002' else shared.bounded_browser(args,ROOT,timeout=720)
        report=json.loads(stdout) if stdout.strip() else {'status':'FAIL','reason':'BROWSER_EMPTY','tests':0}
        shared.private_write(evidence/'browser.json',report);receipt.update(browserExitCode=code,tests=report.get('tests',0),browserSha256=shared.digest((evidence/'browser.json').read_bytes()))
        if task=='G4-ENG-DELIVERY-002':
            shared.require(report.get('taskId')==task and report.get('productAdmissionTaskId')==build.TASK and report.get('runId')==run_id and report.get('skipped')==0 and report.get('tests')==3 and len(report.get('checks',[]))==3 and set(report['checks'])=={'REAL_OIDC','AUTHENTICATED_CSRF_REJECTION','EXPLICIT_CANCEL_CLOSES_SOCKET'},'SHORT_REPORT_INVALID')
        shared.require(code==0 and report['status']=='PASS' and report['tests']>=(3 if task=='G4-ENG-DELIVERY-002' else 10),'M2_BROWSER_FAILED')
        shared.require(before==shared.snapshot(ROOT,runtime),'M2_TOPOLOGY_CHANGED')
        shared.require(binding=={target:build.validate(target,task) for target in ('api','web')},'M2_BUILD_CHANGED')
        dump=shared.docker(ROOT,'exec',runtime['containerIds']['platform-pg'],'pg_dump','-U','platform','-d','platform','--data-only')
        source_key=(web_private/'api-key').read_bytes().strip()
        shared.require(source_key not in dump and b'9007199254740993123456789' not in dump,'M2_PERSISTED_SOURCE_VALUE')
        actions=['connection.secret.intake','connection.create','connection.probe.start','connection.probe.complete','connection.enable','connection.disable','connection.catalog.start','connection.catalog.finish','connection.catalog.cancel','connection.secret.rotate','connection.update']
        actions=[a for a in actions[:9] if a!='connection.disable'] if task=='G4-ENG-DELIVERY-002' else actions
        shared.require(all(action.encode() in dump for action in actions),'M2_AUDIT_ACTION_MISSING')
        for service in ('api','web'):
            raw=shared.docker(ROOT,'logs',runtime['containerIds'][service]);shared.require(source_key not in raw and b'9007199254740993123456789' not in raw,'M2_LOG_SOURCE_VALUE')
        receipt['secretAndBodyLeakScan']={'platformDump':True,'apiWebLogs':True,'auditActions':actions,'rawDataSaved':True,'rawDataDisposition':'PRIVATE_ONLY: command stdout contains dump/log data; never publish command directory wholesale'}
        receipt['budgetAfter']=budget(runtime,private,evidence)
        receipt['status']='PASS'
    except (ValueError,OSError,Exception) as error:
        # 异常只保留类别/固定错误，不输出认证正文。
        receipt['reason']=str(error) if isinstance(error,ValueError) else type(error).__name__
    finally:
        from workflow_execution import cleanup_scope
        with cleanup_scope():
            if relay:receipt['relayCloseout']=relay.close()
            for service in SERVICES:
                if service not in runtime['containerIds']:
                    ident=shared.command([*prefix,'ps','--all','--quiet',service],cwd=ROOT).decode().strip()
                    if ident:runtime['containerIds'][service]=ident
            receipt['containerIds']=runtime['containerIds'];receipt['cleanup']=[]
            build.begin_cleanup(receipt,[*runtime['containerIds'].values(),*[item['name'] for collection in ('volumes','networks') for item in config[collection].values()]])
            shared.private_write(evidence/'receipt.json',receipt)
            for service,ident in runtime['containerIds'].items():
                info=json.loads(shared.docker(ROOT,'inspect',ident))[0]
                shared.require(info['Config']['Labels'].get('ontology.task-id')==TASK and info['Config']['Labels'].get('ontology.run-id')==run_id,'CLEANUP_OWNER')
                if service in ('api','web'): # 不保存原始日志，避免未来框架意外输出敏感载荷。
                    raw=shared.docker(ROOT,'logs',ident).decode();receipt[service+'LogSummary']={'bytes':len(raw),'sha256':shared.digest(raw.encode()),'exceptionTypes':sorted(set(__import__('re').findall(r'\b[A-Za-z]+Exception\b',raw)))}
                shared.docker(ROOT,'rm','-f',ident)
                after=shared.docker(ROOT,'ps','-aq','--no-trunc','--filter','id='+ident).decode().strip()
                receipt['cleanup'].append({'kind':'container','id':ident,'before':True,'command':'docker rm -f exact-id','afterAbsent':not after})
            for kind,collection in [('volume','volumes'),('network','networks')]:
                for value in config[collection].values():
                    name=value['name']
                    info=json.loads(shared.docker(ROOT,kind,'inspect',name))[0]
                    shared.require(info['Labels'].get('ontology.task-id')==TASK and info['Labels'].get('ontology.run-id')==run_id,'CLEANUP_OWNER')
                    shared.docker(ROOT,kind,'rm',name)
                    after=shared.docker(ROOT,kind,'ls','--format','{{.Name}}','--filter','name='+name).decode().splitlines()
                    receipt['cleanup'].append({'kind':kind,'id':name,'before':True,'command':'docker '+kind+' rm exact-id','afterAbsent':name not in after})
            build.finish_cleanup(receipt)
            if not build.execution_unchanged(receipt['driverInputs']) or receipt.get('relayCloseout',{}).get('failures'):receipt['status']='FAIL'
            if (web_private/'stats.json').exists():receipt['sourceStats']=json.loads((web_private/'stats.json').read_text())
            shared.replace_manifest(evidence/'receipt.json',receipt)
    return dict(status=receipt['status'],receipt=str(evidence/'receipt.json'),tests=receipt['tests'])
