#!/usr/bin/env python3
"""解析原始M2测试回执/日志并重核运行输入；manifest不能自报PASS、测试数或退出码。"""
import argparse
import json
from pathlib import Path
import re
import workflow_m2_build as build

REQUIRED={'environment':['prepare1','prepare2'],'contract':['wire','unit'],'backend':['unit','https','pg','smoke'],'web':['ui','smoke'],'interaction':['https','smoke']}
SMOKE_CHECKS={'REAL_OIDC','AUTHENTICATED_CSRF_REJECTION','INTAKE_REPLAY_AND_PURPOSE_CONFLICT','PG_WEB_BIDIRECTIONAL_CREATE_AND_DRAFT_REJECTION','UNSUPPORTED_AUTH_PAGINATION_NO_IO','CROSS_SCOPE_BINDING_REJECT','UI_CREATE_TEST_ENABLE_DISCOVER','ROTATE_INVALIDATES_PROBE_AND_SINGLE_USE','TARGET_SCOPE_EDIT_NO_IO','UI_DISABLE_AND_NO_SUBSEQUENT_IO','DISABLE_CANCELS_TEST','DISABLE_CANCELS_ENABLE','DISABLE_CANCELS_CATALOGS','DISABLE_CANCELS_DISCOVERIES','EXPLICIT_CANCEL_CLOSES_SOCKET','AUTHORIZATION_VIEWER','AUTHORIZATION_SCOPE','AUTHORIZATION_OWNER','NATURAL_EXPIRY_NO_REACTIVATION_BOUND_SECRET_REMAINS_VALID'}


def require(value,code):
    if not value:raise ValueError(code)


def read(path,sha=None):
    path=Path(path)
    require(path.is_relative_to(build.ROOT/'docs/evidence'/build.TASK) and '..' not in path.parts and not any(p.is_symlink() for p in [path,*path.parents]),'PROOF_PATH')
    raw=path.read_bytes()
    if sha:require(build.sha(raw)==sha,'PROOF_SHA')
    return raw


def mtp(raw,minimum):
    text=raw.decode();values=[]
    for names in [('total','总计'),('failed','失败'),('succeeded','成功'),('skipped','已跳过')]:
        match=re.search(r'(?:'+ '|'.join(names)+r'):\s*(\d+)',text,re.I);require(match,'MTP_SUMMARY');values.append(int(match[1]))
    total,failed,success,skipped=values;require(total==success and total>=minimum and failed==skipped==0,'MTP_FAILED_OR_SKIPPED')
    return total


def closed(row):
    require(row.get('status')=='PASS' and row.get('testStatus')=='PASS' and row.get('cleanupComplete') is True,'RUN_NOT_PASS')
    require(sorted(item['id'] for item in row['cleanup'])==row['cleanupExpected'] and all(item['afterAbsent'] is True for item in row['cleanup']),'CLEANUP_NOT_CLOSED')
    require(row['driverInputs']==build.driver_inputs(),'ORIGINAL_DRIVER_DRIFT')


def original(kind,path,current):
    row=json.loads(read(path));require(row.get('taskId')==build.TASK,'PROOF_TASK')
    if kind in ('prepare1','prepare2'):
        require(row['status']=='DEPENDENCIES_READY' and row['worktree']==str(build.ROOT),'PREPARE_NOT_READY')
        require(all(row[key]==0 for key in ('downloads','sdkDownloads','materializedFiles','restoreCount','runtimeCredentialsCopied')),'PREPARE_MUTATED')
        require(row['webDependencies']['status']=='DEPENDENCIES_READY' and row['webDependencies']['materializedTrees']==row['webDependencies']['download']==row['webDependencies']['install']==row['webDependencies']['restore']==0,'WEB_PREPARE_MUTATED')
        return 1,row
    if kind in ('unit','wire','ui'):
        target={'unit':'connections','wire':'wire','ui':'web'}[kind]
        require(row['exitCode']==0 and row['buildBinding']==current[target],'LOCAL_TEST_BINDING')
        raw=read(path.parent/row['log'],row['logSha256'])
        if kind=='ui':
            match=re.search(r'Tests\s+(\d+) passed \((\d+)\)',raw.decode());require(match and match[1]==match[2] and int(match[1])>=119,'VITEST_SUMMARY');return int(match[1]),row
        return mtp(raw,29 if kind=='unit' else 16),row
    closed(row)
    if kind=='https':
        require(row['buildBinding']==current['connections'],'HTTPS_BUILD_DRIFT')
        require({item['category'] for item in row['tests']}=={'RealWebFixture','RealWebDnsRejection'},'HTTPS_CATEGORIES')
        total=0
        for item in row['tests']:
            require(item['exitCode']==0,'HTTPS_EXIT');total+=mtp(read(path.parent/(item['category']+'.log'),item['logSha256']),12 if item['category']=='RealWebFixture' else 1)
        return total,row
    if kind=='pg':
        require(row['exitCode']==0 and row['buildBinding']==current['connections'],'PG_BUILD_EXIT')
        return mtp(read(path.parent/'pg-test.log',row['logSha256']),1),row
    require(kind=='smoke' and row['browserExitCode']==0 and row['buildBinding']=={target:current[target] for target in ('api','web')},'SMOKE_BINDING_EXIT')
    report=json.loads(read(path.parent/'browser.json',row['browserSha256']))
    require(report['status']=='PASS' and report['taskId']==build.TASK and report['runId']==row['runId'] and report['skipped']==0 and len(report['checks'])==report['tests'] and set(report['checks'])==SMOKE_CHECKS,'SMOKE_CHECKS')
    require(row['secretAndBodyLeakScan']['platformDump'] and row['secretAndBodyLeakScan']['apiWebLogs'] and len(row['secretAndBodyLeakScan']['auditActions'])==11,'LEAK_AUDIT_CHECKS')
    return report['tests'],row


def verify(task,gate,input_key):
    require(task==build.TASK and gate in REQUIRED,'PRODUCT_TASK_GATE')
    manifest=json.loads((build.ROOT/'artifacts/workflow'/task/'product-gates.json').read_text())
    require(manifest['taskId']==task and manifest['gates'][gate]['inputKey']==input_key,'PRODUCT_INPUT_DRIFT')
    current={target:build.validate(target) for target in ('connections','wire','api','web')}
    require(manifest['buildBindings']==current,'PRODUCT_BUILD_DRIFT')
    evidence=[];tests=0;prepares=[]
    for kind in REQUIRED[gate]:
        ref=manifest['proofs'][kind];path=build.ROOT/ref['path'];read(path,ref['sha256'])
        count,row=original(kind,path,current);tests+=count
        evidence.append({'kind':kind,'path':ref['path'],'sha256':ref['sha256'],'sourceRun':row.get('runId',row.get('runDirectory')),'tests':count})
        if kind.startswith('prepare'):prepares.append(row)
    if prepares:
        require(prepares[0]['contentKey']==prepares[1]['contentKey'] and prepares[0]['workspaceKey']==prepares[1]['workspaceKey'] and prepares[0]['runDirectory']!=prepares[1]['runDirectory'],'PREPARE_PAIR')
        # 编译绑定覆盖当前锁/项目；额外核对批准工具本体，避免换机后只信历史ready。
        import workflow_environment as environment
        admission=environment.git_json(build.ROOT,environment.BASE,environment.ADMISSION)
        for tool in admission['files']:require(build.sha(Path(tool['path']).read_bytes())==tool['sha256'],'ENV_TOOL_DRIFT')
        import platform
        packages,projects,files=environment.locks(build.ROOT)
        approved={item['package']:item for item in environment.git_json(build.ROOT,environment.ARCHIVE_COMMIT,environment.ARCHIVES)['packages']}
        identity=environment.identities(dict(platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0],files=files,tools=admission['files'],sdk=environment.SDK_ARCHIVES,archives={key:value['archiveSha256'] for key,value in approved.items()}),build.ROOT)
        require(all(row['contentKey']==identity['contentKey'] and row['workspaceKey']==identity['workspaceKey'] for row in prepares),'ENV_IDENTITY_DRIFT')
        home=build.ROOT/'artifacts/workflow'/task/'environment'/identity['contentKey']
        environment.verify_assets(build.ROOT,home,projects,packages,approved)
        import workflow_web_cache as web
        rows,shims,links=web.inspect(build.ROOT,Path(admission['playwrightAndAjv']['store']),prepares[0]['node'],environment)
        marker=json.loads(environment.web_marker(build.ROOT,home,admission).read_text())
        require(marker['binding']==web.binding(build.ROOT,rows,shims,links,environment),'ENV_WEB_DRIFT')

    return {'status':'PASS','gate':gate,'executionMode':'REUSED','qualification':'Original successful results, exact current inputs and original bytes revalidated; product not rerun','originalEvidence':evidence,'tests':tests,'skipped':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task',required=True);parser.add_argument('--gate',required=True);parser.add_argument('--input-key',required=True);args=parser.parse_args()
    try:print(json.dumps(verify(args.task,args.gate,args.input_key)))
    except (ValueError,KeyError,OSError) as error:print(json.dumps({'status':'BLOCKED','reason':str(error)}));raise SystemExit(2)
