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


def read_log(path,sha):
    """V3归档只改后缀；仍核验原日志字节，双路径拒绝歧义。"""
    archived=path.with_suffix('.txt')
    require(not (path.exists() and archived.exists()),'PROOF_LOG_AMBIGUOUS')
    return read(path if path.exists() else archived,sha)


def mtp(raw,minimum):
    text=raw.decode();values=[]
    for names in [('total','总计'),('failed','失败'),('succeeded','成功'),('skipped','已跳过')]:
        matches=re.findall(r'(?:'+ '|'.join(names)+r'):\s*(\d+)',text,re.I)
        require(len(matches)==1,'MTP_SUMMARY');values.append(int(matches[0]))
    total,failed,success,skipped=values;require(total==success and total>=minimum and failed==skipped==0,'MTP_FAILED_OR_SKIPPED')
    return total


def closed(row,reference=None):
    require(row.get('status')=='PASS' and row.get('testStatus')=='PASS' and row.get('cleanupComplete') is True,'RUN_NOT_PASS')
    require(sorted(item['id'] for item in row['cleanup'])==row['cleanupExpected'] and all(item['afterAbsent'] is True for item in row['cleanup']),'CLEANUP_NOT_CLOSED')
    layers=build.driver_layers()
    expected=build.driver_inputs() if reference is None else reference
    require(set(row['driverInputs'])<=set(layers) and set(expected)<=set(layers),'ORIGINAL_DRIVER_DRIFT')
    execution=lambda values:{key:value for key,value in values.items() if layers[key]=='execution'}
    require(execution(row['driverInputs'])==execution(expected),'ORIGINAL_DRIVER_DRIFT')


def original(kind,path,current,driver_reference=None):
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
            if row.get('rawOriginalPath'):
                import base64
                envelope=json.loads(read(build.ROOT/row['rawOriginalPath']))
                original_raw=base64.b64decode(envelope['base64'],validate=True)
                require(build.sha(original_raw)==row['rawOriginalSha256']==envelope['sha256'] and len(original_raw)==envelope['byteLength'],'ORIGINAL_RAW_HASH')
                require(original_raw.rstrip(b'\n')+b'\n'==raw,'DISPLAY_MAPPING')
                raw=original_raw
            text=re.sub(r'\x1b\[[0-9;]*m','',raw.decode())
            matches=re.findall(r'Tests\s+(\d+) passed \((\d+)\)',text)
            require(len(matches)==1 and matches[0][0]==matches[0][1] and int(matches[0][0])>=119 and not re.search(r'\d+ (?:failed|skipped|todo|pending)',text),'VITEST_SUMMARY')
            return int(matches[0][0]),row
        return mtp(raw,29 if kind=='unit' else 16),row
    closed(row,driver_reference)
    if kind=='https':
        require(row['buildBinding']==current['connections'],'HTTPS_BUILD_DRIFT')
        require({item['category'] for item in row['tests']}=={'RealWebFixture','RealWebDnsRejection'},'HTTPS_CATEGORIES')
        total=0
        for item in row['tests']:
            require(item['exitCode']==0,'HTTPS_EXIT');total+=mtp(read_log(path.parent/(item['category']+'.log'),item['logSha256']),12 if item['category']=='RealWebFixture' else 1)
        return total,row
    if kind=='pg':
        require(row['exitCode']==0 and row['buildBinding']==current['connections'],'PG_BUILD_EXIT')
        return mtp(read_log(path.parent/'pg-test.log',row['logSha256']),1),row
    require(kind=='smoke' and row['browserExitCode']==0 and row['buildBinding']=={target:current[target] for target in ('api','web')},'SMOKE_BINDING_EXIT')
    report=json.loads(read(path.parent/'browser.json',row['browserSha256']))
    require(report['status']=='PASS' and report['taskId']==build.TASK and report['runId']==row['runId'] and report['skipped']==0 and len(report['checks'])==report['tests'] and set(report['checks'])==SMOKE_CHECKS,'SMOKE_CHECKS')
    require(row['secretAndBodyLeakScan']['platformDump'] and row['secretAndBodyLeakScan']['apiWebLogs'] and len(row['secretAndBodyLeakScan']['auditActions'])==11,'LEAK_AUDIT_CHECKS')
    return report['tests'],row


def validate_environment(task,prepares):
    require(prepares[0]['contentKey']==prepares[1]['contentKey'] and prepares[0]['workspaceKey']==prepares[1]['workspaceKey'] and prepares[0]['runDirectory']!=prepares[1]['runDirectory'],'PREPARE_PAIR')
    # 编译绑定覆盖当前锁/项目；额外核对批准工具本体，避免换机后只信历史ready。
    import workflow_environment as environment
    admission=environment.git_json(build.ROOT,environment.BASE,environment.ADMISSION)
    for tool in admission['files']:require(build.sha(Path(tool['path']).read_bytes())==tool['sha256'],'ENV_TOOL_DRIFT')
    import platform
    packages,projects,files=environment.locks(build.ROOT)
    approved={item['package']:item for item in environment.git_json(build.ROOT,environment.ARCHIVE_COMMIT,environment.ARCHIVES)['packages']}
    if task in ('G4-M2-DORIS-01', 'G4-M2-ORACLE-01'):
        approved['mysqlconnector/2.6.2'] = dict(package='mysqlconnector/2.6.2', archiveSha256='3d8758d29d2b19a5efa9f78cfac9cae824a870aaf88e2e3adc40bce3cddac748', contentHash='dlTc/tsBa42szdvpj4nrHvQVUb0gsMwR9HT6J0Zz2OSqfP0CdYlGw+qQPqCpbnO97idfvclSjKYtM6y5QaBQaQ==')
    if task == 'G4-M2-ORACLE-01':
        approved.update(environment.ORACLE_ARCHIVES)
    identity=environment.identities(dict(platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0],files=files,tools=admission['files'],sdk=environment.SDK_ARCHIVES,archives={key:value['archiveSha256'] for key,value in approved.items()}),build.ROOT)
    require(all(row['contentKey']==identity['contentKey'] and row['workspaceKey']==identity['workspaceKey'] for row in prepares),'ENV_IDENTITY_DRIFT')
    home=build.ROOT/'artifacts/workflow'/task/'environment'/identity['contentKey']
    environment.verify_assets(build.ROOT,home,projects,packages,approved)
    import workflow_web_cache as web
    rows,shims,links=web.inspect(build.ROOT,Path(admission['playwrightAndAjv']['store']),prepares[0]['node'],environment)
    marker=json.loads(environment.web_marker(build.ROOT,home,admission).read_text())
    require(marker['binding']==web.binding(build.ROOT,rows,shims,links,environment),'ENV_WEB_DRIFT')


def doris_audit(dump, browser):
    """只在内存解析私有pg_dump；公开输出仅关联断言与数量，不复制记录或认证材料。"""
    escapes = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v', '\\': '\\'}
    def unescape(value):
        if value == r'\N':
            return None
        return re.sub(r'\\([bfnrtv\\]|[0-7]{1,3})', lambda match: escapes[match[1]] if match[1] in escapes else chr(int(match[1], 8)), value)
    tables = {}
    for table, columns, data in re.findall(r'COPY ([^\n]+?) \(([^\n]+)\) FROM stdin;\n(.*?)\n\\\.', dump.decode(), re.S):
        if table.startswith('connections.') or table == 'governance.audit_records':
            names = [name.strip().strip('"') for name in columns.split(',')]
            rows = []
            for line in data.splitlines():
                values = line.split('\t')
                require(len(values) == len(names), 'DORIS_DUMP_COLUMNS')
                rows.append(dict(zip(names, map(unescape, values))))
            tables[table] = rows
    require(browser.get('taskId') == 'G4-M2-DORIS-01' and browser.get('status') == 'PASS' and browser.get('skipped') == 0 and re.fullmatch('doris-[a-f0-9]{12}', browser.get('runId', '')), 'DORIS_BROWSER_IDENTITY')
    require(len(browser.get('checks', [])) == browser.get('tests') == 8 and 'SOURCE_REVOKE_PROBE_ENABLE_WORKER_HISTORY' in browser['checks'], 'DORIS_BROWSER_COVERAGE')
    require(len(browser.get('cancellations', [])) == 2 and {row['mutation'] for row in browser['cancellations']} == {'cancel', 'disable'}, 'DORIS_CANCEL_COVERAGE')
    audit = tables['governance.audit_records']
    jobs = tables['connections."CatalogJobs"']
    probes = tables['connections."ConnectionProbes"']
    commands = tables['connections."ConnectionCommands"']
    connections = tables['connections."Connections"']
    secrets = tables['connections."ConnectionSecrets"']
    def events(action, resource, trace=None):
        return [row for row in audit if row['Action'] == action and row['Resource'] == 'connection:' + resource and (trace is None or row['TraceId'] == trace)]
    require(len(jobs) == 5 and len(probes) == 5 and len(commands) >= 20 and len(secrets) == 7, 'DORIS_PERSISTED_COVERAGE')
    require(sorted(row['Status'] for row in jobs) == ['CANCELLED', 'CANCELLED', 'FAILED', 'SUCCEEDED', 'SUCCEEDED'], 'DORIS_JOB_COVERAGE')
    for row in jobs:
        actor = json.loads(row['ActorJson'])
        require(row['Status'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'), 'DORIS_JOB_NONTERMINAL')
        for action in ('connection.catalog.start', 'connection.catalog.finish'):
            require(len(events(action, row['ConnectionId'], actor['traceId'])) == 1, 'DORIS_JOB_AUDIT_ASSOCIATION')
        if row['Status'] == 'SUCCEEDED':
            require(any(snapshot['Id'] == row['SnapshotId'] and snapshot['ConnectionId'] == row['ConnectionId'] for snapshot in tables['connections."CatalogSnapshots"']), 'DORIS_JOB_SNAPSHOT_ASSOCIATION')
        else:
            require(row['SnapshotId'] is None, 'DORIS_FAILED_JOB_SNAPSHOT')
    for row in probes:
        actor = json.loads(row['ActorJson'])
        report = json.loads(row['ReportJson'])
        require(report['status'] in ('TEST_OK', 'TEST_FAILED', 'CANCELLED'), 'DORIS_PROBE_NONTERMINAL')
        for action in ('connection.probe.start', 'connection.probe.complete'):
            require(len(events(action, row['ConnectionId'] or ('new' if action.endswith('.start') else row['Id']), actor['traceId'])) == 1, 'DORIS_PROBE_AUDIT_ASSOCIATION')
        require(any(command['Id'] == row['CommandKey'] and json.loads(command['ReceiptJson']) == report for command in commands), 'DORIS_PROBE_RECEIPT_ASSOCIATION')
    for witness in browser['cancellations']:
        row = next(job for job in jobs if job['Id'] == witness['jobId'])
        require(row['Status'] == 'CANCELLED' and row['SnapshotId'] is None, 'DORIS_CANCEL_COMMIT')
        action = 'connection.catalog.cancel' if witness['mutation'] == 'cancel' else 'connection.disable'
        require(events(action, row['ConnectionId']), 'DORIS_CANCEL_AUDIT')
    require(len(connections) == 2 and all(row['State'] == 'DISABLED' for row in connections), 'DORIS_FINAL_CONNECTION_STATE')
    require(sum(row['Action'] == 'connection.create' for row in audit) == len(connections), 'DORIS_CREATE_AUDIT_COUNT')
    require(sum(row['Action'] == 'connection.secret.intake' for row in audit) == len(secrets), 'DORIS_INTAKE_REPLAY_DUPLICATE_AUDIT')
    require(all(row['OrganizationId'] == 'org-demo' and row['Outcome'] in ('allowed', 'denied', 'failure') for row in audit), 'DORIS_AUDIT_SCOPE')
    return dict(status='PASS', jobAssociations=len(jobs), probeAssociations=len(probes), finalConnections=len(connections), intakeAuditCount=len(secrets), exactCancellationAssociations=len(browser['cancellations']), limitation='Persisted transaction associations; failure-rollback atomicity requires separate shared transaction tests', raw='PRIVATE_ONLY')


def historical_qualification():
    """以冻结 Web Head 重核历史执行事实；不声称当前新驱动已执行全部长场景。"""
    import subprocess
    base='820855bc239d409b9931bf4e3ba669592afb2123'
    index_path='docs/evidence/G4-M2-WEB-01/recovery/product-proof-index.json'
    index=json.loads(subprocess.check_output(['git','show',base+':'+index_path],cwd=build.ROOT))
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',base,'scripts/maintenance'],cwd=build.ROOT).decode().splitlines()
    paths=[p for p in names if p.startswith('scripts/maintenance/workflow_m2_') and p.endswith('.py')]
    paths+=['scripts/maintenance/workflow-m2-web.mjs','scripts/maintenance/workflow_smoke.py','experiments/g4-m2-web-01/https-fixture.mjs']
    reference={p:build.sha(subprocess.check_output(['git','show',base+':'+p],cwd=build.ROOT)) for p in paths}
    results=[]
    for kind in ('unit','wire','ui','https','pg','smoke'):
        ref=index['proofs'][kind];raw=subprocess.check_output(['git','show',base+':'+ref['path']],cwd=build.ROOT)
        require(build.sha(raw)==ref['sha256'] and read(build.ROOT/ref['path'])==raw,'HISTORICAL_ORIGINAL_CHANGED')
        count,row=original(kind,build.ROOT/ref['path'],index['buildBindings'],reference)
        results.append(dict(kind=kind,tests=count,sourceCommit=base,path=ref['path'],sha256=ref['sha256'],qualification='PASS',executionMode='HISTORICAL_REQUALIFIED'))
    product_same=build.inputs('connections')==index['buildBindings']['connections']['inputKey']
    assertion='scripts/maintenance/workflow-m2-web.mjs'
    require(product_same and build.sha((build.ROOT/assertion).read_bytes())==reference[assertion],'TTL_SEMANTIC_INPUT_DRIFT')
    return dict(status='PASS',qualificationMode='FRESH',productExecutions=0,originals=results,
                naturalTtl=dict(executionMode='REUSED',scope='Natural expiry assertion and unchanged backend semantic inputs only',assertionDriverSha256=reference[assertion]),
                currentDriverCoverage='Historical orchestration is not current execution coverage; new runner requires fresh targeted TLS/cancellation proof',
                layers=build.driver_layers(),currentDriverInputs=build.driver_inputs())


def qualify_delivery(gate,input_key):
    """工程任务当前覆盖：新短运行、机器UI、warm环境和不可变长场景分列。"""
    task='G4-ENG-DELIVERY-002'
    index=json.loads((build.ROOT/'artifacts/workflow'/task/'product-gates.json').read_text())
    require(index['taskId']==task and index['gates'][gate]['inputKey']==input_key,'PRODUCT_INPUT_DRIFT')
    def proof(name):
        ref=index['proofs'][name];path=build.ROOT/ref['path']
        require(path.is_relative_to(build.ROOT/'docs/evidence'/task) and '..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'DELIVERY_PROOF_PATH')
        raw=path.read_bytes()
        if build.sha(raw)!=ref['sha256']:
            import base64
            envelope=json.loads(raw)
            require(envelope.get('encoding')=='base64','DELIVERY_PROOF_SHA')
            raw=base64.b64decode(envelope['base64'],validate=True)
            require(len(raw)==envelope['sizeBytes'] and build.sha(raw)==envelope['sha256'],'DELIVERY_ENVELOPE')
        require(build.sha(raw)==ref['sha256'],'DELIVERY_PROOF_SHA')
        return json.loads(raw),path,raw
    history=historical_qualification();counts={};refs=[]
    current={target:build.validate(target,task) for target in ('connections','api','web')}
    import workflow_m2_web as admission
    import workflow_execution as execution
    environment_key=execution.sha(execution.encoded(admission.environment_identity(task)))
    for name in ('https','pg','smoke'):
        row,path,_=proof(name)
        require(row['taskId']==task and row.get('environmentFingerprint')==environment_key,'DELIVERY_TASK_ENVIRONMENT');closed(row)
        if name=='https':
            require(row['buildBinding']==current['connections'],'DELIVERY_BUILD')
            require(len(row['tests'])==2 and {t['category'] for t in row['tests']}=={'RealWebFixture','RealWebDnsRejection'},'DELIVERY_CATEGORIES')
            counts[name]=0
            for test in row['tests']:
                require(test['exitCode']==0,'DELIVERY_EXIT');raw=execution.ordinary(path.parent/(test['category']+'.txt')).read_bytes()
                require(build.sha(raw)==test['logSha256'],'DELIVERY_LOG_SHA')
                counts[name]+=mtp(raw,12 if test['category']=='RealWebFixture' else 1)
            require({t['category'] for t in row['tests']}=={'RealWebFixture','RealWebDnsRejection'},'DELIVERY_CATEGORIES')
        elif name=='pg':
            require(row['exitCode']==0 and row['buildBinding']==current['connections'],'DELIVERY_PG')
            raw=execution.ordinary(path.parent/'pg-test.txt').read_bytes();require(build.sha(raw)==row['logSha256'],'DELIVERY_LOG_SHA');counts[name]=mtp(raw,1)
        else:
            report,report_path,report_raw=proof('browser')
            require(row['browserExitCode']==0 and row['buildBinding']=={k:current[k] for k in ('api','web')},'DELIVERY_SMOKE')
            require(build.sha(report_raw)==row['browserSha256'] and report['status']=='PASS' and report['taskId']==task and report['runId']==row['runId'] and report['productAdmissionTaskId']==build.TASK and report['skipped']==0 and report['tests']==len(report['checks'])==3 and set(report['checks'])=={'REAL_OIDC','AUTHENTICATED_CSRF_REJECTION','EXPLICIT_CANCEL_CLOSES_SOCKET'},'DELIVERY_SHORT_REPORT')
            counts[name]=3
        refs.append(index['proofs'][name])
    from workflow_evidence import machine
    report,path,ui_raw=proof('ui');counts['ui']=machine(ui_raw,'vitest-json',119)
    ui_execution,_,_=proof('uiExecution')
    require(ui_execution['exitCode']==0 and ui_execution['classification']=='SUCCESS' and ui_execution['inputKey']==build.inputs('web') and ui_execution['inputsUnchanged'] is True and ui_execution['reportSha256']==build.sha(ui_raw),'UI_EXECUTION_BINDING')
    preparations=[]
    for name in ('prepare1','prepare2'):
        row,_,_=proof(name)
        require(row['taskId']==task and row['status']=='DEPENDENCIES_READY' and row['worktree']==str(build.ROOT),'DELIVERY_PREPARE')
        require(all(row[key]==0 for key in ('downloads','sdkDownloads','materializedFiles','restoreCount','runtimeCredentialsCopied')) and row['webDependencies']['status']=='DEPENDENCIES_READY' and all(row['webDependencies'][key]==0 for key in ('materializedTrees','download','install','restore')),'DELIVERY_PREPARE_MUTATED')
        preparations.append(row)
    validate_environment(task,preparations)
    return dict(status='PASS',executionMode='REUSED',qualificationMode='FRESH',tests=sum(counts.values()),skipped=0,counts=counts,originalEvidence=refs,historicalQualification=history,limitation='Counts overlap between gates; current short runs are not a new natural TTL or full historical browser run')


def qualify_doris(gate, input_key):
    """Doris专属资格复用统一原件/测试解析器，不以接口存在或摘要自报计数放行。"""
    from workflow_evidence import restore, machine
    import workflow_execution as execution
    task = 'G4-M2-DORIS-01'
    required = {'environment': ['prepare1', 'prepare2'], 'contract': ['unit', 'wire'], 'backend': ['adapter', 'expired', 'pg', 'https', 'lifecycle'], 'web': ['ui', 'lifecycle'], 'interaction': ['lifecycle']}
    require(gate in required, 'DORIS_GATE')
    index = json.loads(execution.ordinary(build.ROOT / 'artifacts/workflow' / task / 'product-gates.json').read_text())
    require(index['taskId'] == task and index['gates'][gate]['inputKey'] == input_key, 'DORIS_GATE_INPUT')
    def raw(name):
        record = index['proofs'][name]
        path = execution.ordinary(build.ROOT / record['path'])
        require(path.is_relative_to(build.ROOT / 'docs/evidence' / task), 'DORIS_PROOF_BOUNDARY')
        return restore(build.ROOT, record)
    def document(name):
        return json.loads(raw(name))
    current = {target: build.validate(target, task) for target in ('api', 'web', 'connections', 'wire')}
    counts = {}
    for name in required[gate]:
        row = document(name)
        if name.startswith('prepare'):
            require(row['taskId'] == task and row['status'] == 'DEPENDENCIES_READY' and row['worktree'] == str(build.ROOT), 'DORIS_PREPARE')
            require(all(row[key] == 0 for key in ('downloads', 'sdkDownloads', 'materializedFiles', 'restoreCount', 'runtimeCredentialsCopied')), 'DORIS_PREPARE_MUTATED')
            counts[name] = 1
        elif name in ('unit', 'wire', 'adapter'):
            target = 'wire' if name == 'wire' else 'connections'
            require(row['exitCode'] == 0 and row['buildBinding'] == current[target], 'DORIS_TEST_BINDING')
            log = raw(name + 'Log')
            require(build.sha(log) == row['logSha256'], 'DORIS_TEST_LOG')
            counts[name] = mtp(log, {'unit': 29, 'wire': 16, 'adapter': 23}[name])
            require(counts[name] == row['tests'], 'DORIS_TEST_COUNT')
        elif name == 'ui':
            execution_row = document('uiExecution')
            require(execution_row['exitCode'] == 0 and execution_row['inputsUnchanged'] is True and execution_row['inputKey'] == build.inputs('web') and execution_row['reportSha256'] == build.sha(raw('ui')), 'DORIS_UI_BINDING')
            counts[name] = machine(raw('ui'), 'vitest-json', 120)
        elif name == 'expired':
            require(row['status'] == 'PASS' and row['buildBinding'] == current['connections'] and row['restoredOriginalBytes'] and row['restoredFeHealthy'], 'DORIS_TLS_RESTORE')
            require(row['presentedCertificate']['matchesGenerated'] and row['presentedCertificate']['opensslRejectedExpired'] and row['presentedCertificate']['observerExitCode'] != 0, 'DORIS_TLS_ACTUAL_LEAF')
            witness = document('expiredInputs')
            require(execution.sha(execution.encoded(witness['inputs'])) == witness['inputFingerprint'] and witness['inputs']['buildBinding'] == row['buildBinding'] and build.execution_unchanged(witness['inputs']['drivers']), 'DORIS_TLS_EXECUTION_INPUT')
            counts[name] = 0
            for part in ('expired-rejection', 'restored-product-probe'):
                require(witness['executionReceipts'][part]['inputFingerprint'] == witness['inputFingerprint'] and witness['executionReceipts'][part]['exitCode'] == 0 and witness['executionReceipts'][part]['stdout']['sha256'] == build.sha(raw(part)), 'DORIS_TLS_EXECUTED_KEY')
                require(row[part]['exitCode'] == 0 and build.sha(raw(part)) == row[part]['logSha256'], 'DORIS_TLS_LOG')
                counts[name] += mtp(raw(part), 1)
        elif name in ('pg', 'https'):
            closed(row)
            require(build.execution_unchanged(row['driverInputs']), 'DORIS_COMPAT_DRIVER_DRIFT')
            require(row['taskId'] == task and row['buildBinding'] == current['connections'], 'DORIS_COMPAT_BINDING')
            if name == 'pg':
                require(row['exitCode'] == 0 and build.sha(raw('pgLog')) == row['logSha256'], 'DORIS_PG_LOG')
                counts[name] = mtp(raw('pgLog'), 1)
            else:
                require({item['category'] for item in row['tests']} == {'RealWebFixture', 'RealWebDnsRejection'}, 'DORIS_WEB_CATEGORIES')
                counts[name] = 0
                for item in row['tests']:
                    log = raw(item['category'])
                    require(item['exitCode'] == 0 and build.sha(log) == item['logSha256'], 'DORIS_WEB_LOG')
                    counts[name] += mtp(log, 12 if item['category'] == 'RealWebFixture' else 1)
        else:
            require(row['taskId'] == task and row['status'] == 'LIFECYCLE_CHECKS_PASSED' and row['buildBindings'] == {target: current[target] for target in ('api', 'web')}, 'DORIS_LIFECYCLE_BINDING')
            require(row['browserExecution']['exitCode'] == 0 and row['browserExecution']['classification'] == 'SUCCESS', 'DORIS_BROWSER_EXIT')
            witness = document('lifecycleInputs')
            require(execution.sha(execution.encoded(witness['inputs'])) == witness['inputFingerprint'] == row['browserExecution']['inputFingerprint'], 'DORIS_EXECUTED_INPUT_FINGERPRINT')
            require(witness['inputs']['bindings'] == row['buildBindings'] and build.execution_unchanged(witness['inputs']['drivers']), 'DORIS_EXECUTION_DRIVER_DRIFT')
            require(witness['inputs']['compose'] == {str(p.relative_to(build.ROOT)): build.sha(p.read_bytes()) for p in sorted((build.ROOT / 'infra/doris').glob('*.yaml'))}, 'DORIS_COMPOSE_DRIFT')
            report = document('browser')
            original = raw('browserLog')
            require(build.sha(original) == row['browserExecution']['stdout']['sha256'] and json.loads(original) == report, 'DORIS_BROWSER_ORIGINAL')
            expected = {'REAL_OIDC', 'DORIS_INTAKE_REPLAY_PURPOSE_SCOPE', 'UI_INTAKE_CREATE_PROBE_ENABLE_DISCOVER', 'EXPLICIT_CANCEL_AND_DISABLE_TERMINATE_EXACT_SOURCE', 'SOURCE_REVOKE_PROBE_ENABLE_WORKER_HISTORY', 'EMPTY_SYNTHETIC_SCHEMA_RESTORE', 'ROTATE_SINGLE_USE_STALE_PROBE_TARGET_SCOPE', 'DISABLE_BLOCKS_PROBE_AND_HISTORY'}
            require(report['taskId'] == task and report['runId'] == row['runId'] and report['status'] == 'PASS' and report['skipped'] == 0 and report['tests'] == len(report['checks']) == len(expected) and set(report['checks']) == expected, 'DORIS_BROWSER_COVERAGE')
            require({w['mutation'] for w in report['cancellations']} == {'cancel', 'disable'} and all(w['observedBefore'] and w['absentAfter'] and type(w['sourceId']) == int for w in report['cancellations']), 'DORIS_SOURCE_TERMINATION')
            expected_ids = set(row['containers'].values()) | {service['pid'] for service in row['services']}
            require(expected_ids == {item['id'] for item in row['cleanup']} and all(item['afterAbsent'] for item in row['cleanup']), 'DORIS_LIFECYCLE_CLEANUP')
            require(0 < row['hostPeakRssBytes'] <= 4 * 1024**3 and row['auditAndSecretScan']['platformDump'] and row['auditAndSecretScan']['hostLogs'], 'DORIS_RESOURCE_OR_LEAK_SCAN')
            associations = document('audit')
            require(build.sha(raw('audit')) == row['auditAndSecretScan']['associationsSha256'] and associations['status'] == 'PASS' and associations['runId'] == row['runId'] and associations['jobAssociations'] == associations['probeAssociations'] == 5 and associations['exactCancellationAssociations'] == 2, 'DORIS_AUDIT_ASSOCIATIONS')
            counts[name] = report['tests']
    if gate == 'environment':
        first, second = document('prepare1'), document('prepare2')
        require(first['contentKey'] == second['contentKey'] and first['workspaceKey'] == second['workspaceKey'] and first['runDirectory'] != second['runDirectory'], 'DORIS_PREPARE_PAIR')
        validate_environment(task, [first, second])
    return dict(status='PASS', executionMode='REUSED', qualificationMode='FRESH', tests=sum(counts.values()), skipped=0, counts=counts, originalEvidence=[index['proofs'][name] for name in required[gate]], limitation='Counts overlap between gates; CI, other architectures, production and online revocation are not covered')


def oracle_audit(lifecycle_path, platform_path, api_path, output_path):
    """当前Oracle原始脱敏SQL投影、审计关联与内存秘密扫描；不保存私有dump。"""
    import subprocess
    import workflow_execution as execution
    task = 'G4-M2-ORACLE-01'
    base = build.ROOT / 'artifacts/workflow' / task
    paths = [execution.ordinary(path) for path in (lifecycle_path, platform_path, api_path, output_path)]
    require(all(path.is_relative_to(base) for path in paths) and not paths[3].exists(), 'ORACLE_AUDIT_PATH')
    lifecycle_path, platform_path, api_path, output_path = paths
    lifecycle = json.loads(lifecycle_path.read_text())
    browser_path = lifecycle_path.parent / lifecycle['stdout']
    report = json.loads(browser_path.read_text())
    require(build.sha(browser_path.read_bytes()) == lifecycle['stdoutSha256'] and report['status'] == 'PASS', 'ORACLE_AUDIT_LIFECYCLE')
    platform = json.loads(platform_path.read_text())
    api = json.loads(api_path.read_text())
    docker = ['docker', '--context', 'desktop-linux']
    ident = platform['containers']['platform-pg']['id']
    for resource in (platform, api):
        require(resource['taskId'] == task and resource['runId'] == report['runId'], 'ORACLE_AUDIT_IDENTITY')
    for identifier in (ident, api['containerId']):
        require(re.fullmatch('[a-f0-9]{64}', identifier), 'ORACLE_AUDIT_CONTAINER')
        row = json.loads(subprocess.check_output(docker + ['inspect', identifier], timeout=5))[0]
        require(row['Config']['Labels'].get('ontology.task') == task and row['Config']['Labels'].get('ontology.run') == report['runId'], 'ORACLE_AUDIT_CONTAINER')
    ids = [w['jobId'] for w in report['cancellations']]
    require(all(re.fullmatch('[a-f0-9]{32}', value) for value in [*ids, report['connectionId']]), 'ORACLE_AUDIT_IDS')
    selected = "SELECT DISTINCT \"ConnectionId\" FROM connections.\"CatalogJobs\" WHERE \"Id\" IN (" + ','.join("'" + value + "'" for value in ids) + ") UNION SELECT '" + report['connectionId'] + "'"
    sql = '''WITH selected AS (''' + selected + ''') SELECT json_build_object(
'jobs',(SELECT json_agg(json_build_object('id',"Id",'connectionId',"ConnectionId",'status',"Status",'snapshotId',"SnapshotId",'traceId',"ActorJson"::json->>'traceId','fence',"Fence")) FROM connections."CatalogJobs" WHERE "ConnectionId" IN (SELECT * FROM selected)),
'probes',(SELECT json_agg(json_build_object('id',"Id",'connectionId',"ConnectionId",'traceId',"ActorJson"::json->>'traceId')) FROM connections."ConnectionProbes" WHERE "ConnectionId" IN (SELECT * FROM selected)),
'audit',(SELECT json_agg(json_build_object('action',"Action",'resource',"Resource",'traceId',"TraceId")) FROM governance.audit_records WHERE "Resource" IN (SELECT 'connection:' || "ConnectionId" FROM selected)),
'connections',(SELECT json_agg(json_build_object('id',"Id",'state',"State")) FROM connections."Connections" WHERE "Id" IN (SELECT * FROM selected)));'''
    binding = dict(lifecycleSha256=build.sha(lifecycle_path.read_bytes()), browserSha256=lifecycle['stdoutSha256'], apiBuildBinding=build.validate('api', task), sqlSha256=build.sha(sql.encode()))
    result = execution.run(docker + ['exec', '-i', ident, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'platform', '-d', 'platform'], build.ROOT, task=task, run_id=report['runId'], stage='oracle-audit-projection', timeout=15, input_key=execution.sha(execution.encoded(binding)), stdin=sql.encode())
    require(result.returncode == 0, 'ORACLE_AUDIT_QUERY')
    projection = json.loads(result.stdout)
    jobs = projection['jobs']
    require(len(jobs) == 8 and len(projection['connections']) == 2 and all(row['state'] == 'DISABLED' for row in projection['connections']), 'ORACLE_PERSISTED_COVERAGE')
    for job in jobs:
        require(job['status'] in ('SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED') and (bool(job['snapshotId']) == (job['status'] == 'SUCCEEDED')), 'ORACLE_JOB_SNAPSHOT')
        for action in ('connection.catalog.start', 'connection.catalog.finish'):
            require(sum(a['action'] == action and a['resource'] == 'connection:' + job['connectionId'] and a['traceId'] == job['traceId'] for a in projection['audit']) == 1, 'ORACLE_JOB_AUDIT')
    for probe in projection['probes']:
        for action in ('connection.probe.start', 'connection.probe.complete'):
            require(sum(a['action'] == action and a['resource'] == 'connection:' + probe['connectionId'] and a['traceId'] == probe['traceId'] for a in projection['audit']) == 1, 'ORACLE_PROBE_AUDIT')
    for witness in [*report['cancellations'], report['logoutWitness']]:
        require(any(job['id'] == witness['jobId'] and job['status'] == 'CANCELLED' and not job['snapshotId'] for job in jobs), 'ORACLE_CANCEL_COMMIT')
    # 原dump与私有合成口令只在内存比对；公开投影不含actor/口令/密文/业务值。
    dump = subprocess.check_output(docker + ['exec', ident, 'pg_dump', '-U', 'platform', '-d', 'platform', '--data-only', '--no-owner', '--no-privileges'], timeout=20)
    logs = subprocess.check_output(docker + ['logs', api['containerId']], stderr=subprocess.STDOUT, timeout=10)
    private = platform_path.parent / 'private'
    secrets = [(private / relative).read_bytes().strip() for relative in ('adapter/reader-password', 'platform/platform-password', 'platform/keycloak-password')]
    require(all(len(value) > 16 and value not in dump and value not in logs and value not in result.stdout for value in secrets), 'ORACLE_SECRET_LEAK')
    projection_path = output_path.with_suffix('.projection.json')
    with projection_path.open('xb') as stream:
        stream.write(result.stdout)
    value = dict(taskId=task, runId=report['runId'], status='PASS', binding=binding, jobIds=sorted(job['id'] for job in jobs), jobAssociations=len(jobs), probeAssociations=len(projection['probes']), exactSourceCancellations=2, platformDumpSecretScan=True, apiLogsSecretScan=True, projection=projection_path.name, projectionSha256=build.sha(result.stdout), queryExecution=result.receipt)
    with output_path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    return value


def qualify_oracle(gate, input_key):
    """Oracle本机当前原件资格：解析实际日志/退出码/构建输入，未覆盖的外部验收不补PASS。"""
    import workflow_execution as execution
    task = 'G4-M2-ORACLE-01'
    base = build.ROOT / 'artifacts/workflow' / task
    manifest = json.loads((base / 'product-gates.json').read_text())
    require(manifest['taskId'] == task and gate in REQUIRED and manifest['gates'][gate]['inputKey'] == input_key, 'ORACLE_GATE_INPUT')
    current = {target: build.validate(target, task) for target in ('connections', 'wire', 'api', 'web')}
    def proof(kind):
        reference = manifest['proofs'][kind]
        path = execution.ordinary(build.ROOT / reference['path'])
        require(path.is_relative_to(base) and build.sha(path.read_bytes()) == reference['sha256'], 'ORACLE_PROOF_PATH_SHA')
        return path, json.loads(path.read_text())
    def log(path, row):
        target = execution.ordinary(path.parent / row['log'])
        require(target.is_relative_to(base), 'ORACLE_LOG_PATH')
        raw = target.read_bytes()
        receipt = row['execution']
        require(receipt['exitCode'] == 0 and receipt['classification'] == 'SUCCESS', 'ORACLE_ACTUAL_EXECUTION')
        require(receipt['stderr']['sizeBytes'] == 0 and build.sha(raw) == receipt['stdout']['sha256'], 'ORACLE_EXECUTED_LOG')
        return raw
    total = 0
    kinds = {'environment': ['prepare'], 'contract': ['wire', 'unit'], 'backend': ['unit', 'adapter', 'lifecycle', 'audit'], 'web': ['ui', 'lifecycle'], 'interaction': ['lifecycle', 'audit']}[gate]
    for kind in kinds:
        path, row = proof(kind)
        require(row.get('taskId') == task, 'ORACLE_PROOF_TASK')
        if kind == 'prepare':
            require(row['status'] == 'DEPENDENCIES_READY' and row['downloads'] == row['sdkDownloads'] == row['runtimeCredentialsCopied'] == 0, 'ORACLE_PREPARE')
            _, warm = proof('prepare2')
            require(warm['status'] == 'DEPENDENCIES_READY' and all(warm[key] == 0 for key in ('downloads', 'sdkDownloads', 'materializedFiles', 'restoreCount', 'runtimeCredentialsCopied')), 'ORACLE_WARM_PREPARE')
            validate_environment(task, [row, warm])
            total += 1
        elif kind in ('wire', 'unit', 'ui', 'adapter'):
            target = {'wire': 'wire', 'unit': 'connections', 'ui': 'web', 'adapter': 'connections'}[kind]
            require(row['buildBinding'] == current[target] and row['inputUnchanged'], 'ORACLE_BUILD_DRIFT')
            require(row['execution']['inputFingerprint'] == execution.sha(execution.encoded(row['buildBinding'])), 'ORACLE_TEST_INPUT')
            raw = log(path, row)
            if kind == 'adapter':
                require(row['actualExitCode'] == 0 and row['cleanupComplete'] and row['stage'] == 'PASS', 'ORACLE_ADAPTER_CLEANUP')
            else:
                require(row['exitCode'] == 0, 'ORACLE_LOCAL_EXIT')
            if kind == 'ui':
                text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode())
                matches = re.findall(r'Tests\s+(\d+) passed \((\d+)\)', text)
                require(len(matches) == 1 and matches[0] == ('122', '122') and not re.search(r'\d+ (?:failed|skipped|todo|pending)', text), 'ORACLE_UI_COUNT')
                total += 122
            else:
                total += mtp(raw, {'wire': 19, 'unit': 46, 'adapter': 5}[kind])
        elif kind == 'lifecycle':
            require(row['status'] == 'LIFECYCLE_CHECKS_PASSED' and row['exitCode'] == 0 and row['buildBindings'] == {target: current[target] for target in ('api', 'web')}, 'ORACLE_LIFECYCLE_BINDING')
            require(build.execution_unchanged(row['inputs']['drivers']), 'ORACLE_DRIVER_DRIFT')
            raw = execution.ordinary(path.parent / row['stdout']).read_bytes()
            require(build.sha(raw) == row['stdoutSha256'] == row['browserExecution']['stdout']['sha256'], 'ORACLE_BROWSER_ORIGINAL')
            report = json.loads(raw)
            expected = {'REAL_OIDC', 'ORACLE_INTAKE_REPLAY_PURPOSE_SCOPE', 'UI_INTAKE_CREATE_PROBE_ENABLE_DISCOVER', 'EXPLICIT_CANCEL_AND_DISABLE_TERMINATE_EXACT_SOURCE', 'INFLIGHT_PERMISSION_CHANGE_NO_SNAPSHOT', 'LEASE_FENCE_OLD_SOURCE_ENDED_NEW_ATTEMPT_SUCCEEDED', 'SOURCE_REVOKE_PROBE_ENABLE_WORKER_HISTORY', 'ROTATE_SINGLE_USE_STALE_PROBE_TARGET_SCOPE', 'AUDIT_FAILURE_ROLLS_BACK_ENABLE_PENDING_REPLAY_REJECTED', 'LOGOUT_TERMINATES_SOURCE_AND_FENCES_SNAPSHOT', 'DISABLE_BLOCKS_PROBE_AND_HISTORY'}
            require(report['status'] == 'PASS' and report['skipped'] == 0 and report['tests'] == len(expected) and set(report['checks']) == expected, 'ORACLE_BROWSER_CHECKS')
            require({item['mutation'] for item in report['cancellations']} == {'cancel', 'disable'}, 'ORACLE_CANCEL_MODES')
            for witness in [*report['cancellations'], report['logoutWitness']]:
                require(re.fullmatch(r'\d+:\d+', witness['sourceId']) and 0 < witness['endedAt'] - witness['cancelledAt'] < 5000 and 0 < witness['endedAt'] - witness['queuedAt'] < 7000, 'ORACLE_SOURCE_CANCELLATION')
            total += report['tests']
        else:
            lifecycle_path, lifecycle = proof('lifecycle')
            require(row['binding']['lifecycleSha256'] == build.sha(lifecycle_path.read_bytes()) and row['binding']['browserSha256'] == lifecycle['stdoutSha256'] and row['binding']['apiBuildBinding'] == current['api'], 'ORACLE_AUDIT_BINDING')
            projection_path = execution.ordinary(path.parent / row['projection'])
            require(projection_path.is_relative_to(base), 'ORACLE_AUDIT_PROJECTION_PATH')
            raw = projection_path.read_bytes()
            require(build.sha(raw) == row['projectionSha256'] == row['queryExecution']['stdout']['sha256'] and row['queryExecution']['classification'] == 'SUCCESS' and row['queryExecution']['exitCode'] == 0, 'ORACLE_AUDIT_QUERY_ORIGINAL')
            projection = json.loads(raw)
            require(sorted(job['id'] for job in projection['jobs']) == row['jobIds'], 'ORACLE_AUDIT_JOB_BINDING')
            for witness in [*lifecycle['report']['cancellations'], lifecycle['report']['logoutWitness']]:
                require(any(job['id'] == witness['jobId'] and job['status'] == 'CANCELLED' and not job['snapshotId'] for job in projection['jobs']), 'ORACLE_AUDIT_CANCEL_BINDING')
            require(row['status'] == 'PASS' and row['platformDumpSecretScan'] and row['apiLogsSecretScan'] and row['jobAssociations'] == len(projection['jobs']) == 8 and row['exactSourceCancellations'] == 2, 'ORACLE_AUDIT_ASSOCIATIONS')
            total += row['jobAssociations']
    return dict(status='PASS', taskId=task, gate=gate, inputKey=input_key, tests=total, skipped=0, qualificationMode='FRESH', scope='Current local Oracle development slice; production/CI/other platforms not executed')


def verify(task,gate,input_key):
    if task=='G4-M2-ORACLE-01':
        return qualify_oracle(gate,input_key)
    if task=='G4-M2-DORIS-01':
        return qualify_doris(gate,input_key)
    if task=='G4-ENG-DELIVERY-002':
        require(gate in REQUIRED,'PRODUCT_TASK_GATE')
        return qualify_delivery(gate,input_key)
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
    if prepares:validate_environment(task,prepares)

    return {'status':'PASS','gate':gate,'executionMode':'REUSED','qualification':'Original successful results, exact current inputs and original bytes revalidated; product not rerun','originalEvidence':evidence,'tests':tests,'skipped':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task',required=True);parser.add_argument('--gate',required=True);parser.add_argument('--input-key',required=True);args=parser.parse_args()
    try:print(json.dumps(verify(args.task,args.gate,args.input_key)))
    except (ValueError,KeyError,OSError) as error:print(json.dumps({'status':'BLOCKED','reason':str(error)}));raise SystemExit(2)
