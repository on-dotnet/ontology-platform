"""重开 Doris Mapping/Query 已提交的产品验收原件。"""
from workflow_doris_mapping_query import BROWSER_SOURCES


def reopen_ac06(directory):
    """按签署清单恢复十四个原件的准确字节，再运行原有因果证明。"""
    import json
    import tempfile
    from pathlib import Path
    from doris_query_profile_witness import dependency_proof
    from workflow_evidence import restore,digest
    from workflow_m2_build import ROOT
    proof=json.loads((directory/'ac06-dependency-proof.json').read_bytes())
    envelopes=json.loads((directory/'lossless-originals.json').read_bytes())
    with tempfile.TemporaryDirectory(prefix='dmq-source-reopen-') as temporary:
        target=Path(temporary)
        for name,sha in proof['inputs'].items():
            if Path(name).name!=name or not name.endswith('.json'):raise ValueError('DMQ_PROOF_MEMBER')
            data=restore(ROOT,envelopes[name]) if name in envelopes else (directory/name).read_bytes()
            if digest(data)!=sha:raise ValueError('DMQ_PROOF_MEMBER_HASH')
            (target/name).write_bytes(data)
        return dependency_proof(target,proof['case'])


def measured_backend(root, commit):
    """重算原提交的完整构建投影，仅允许独立 QueryTests 原件读取测试与当前树有差异。"""
    import io
    import json
    import subprocess
    import tarfile
    from workflow_execution import sha
    from workflow_m2_evidence import require
    def projected(name):
        return (name.startswith(('backend/','Directory.')) or name in
                ('global.json','NuGet.Config','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','.node-version'))
    def listing(command):
        return {n for n in subprocess.check_output(command,cwd=root).decode().split('\0') if n and projected(n)}
    old=listing(['git','ls-tree','-rz','--name-only',commit])
    current=listing(['git','ls-files','--cached','--others','--exclude-standard','-z'])
    require(old==current,'DMQ_BACKEND_MEMBER_DRIFT')
    selection=['backend',*sorted(n for n in old if not n.startswith('backend/'))]
    raw=subprocess.check_output(['git','archive','--format=tar',commit,'--',*selection],cwd=root)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        hashes={f.name:sha(archive.extractfile(f).read()) for f in archive.getmembers() if f.isfile()}
    require(set(hashes)==old and {p for p,h in hashes.items() if sha((root/p).read_bytes())!=h}<=
            {'backend/tests/OntologyPlatform.QueryTests/G4QueryTests.cs'},'DMQ_PRODUCT_SOURCE_DRIFT')
    return sha(json.dumps(hashes,sort_keys=True).encode())


def measured_browser_sources(root, commit):
    """核对实测驱动原字节，源夹具仅允许与原提交产生完全相同的 Python 语法树。"""
    import ast
    import subprocess
    from workflow_execution import sha
    from workflow_m2_evidence import require
    result=[]
    for name in BROWSER_SOURCES:
        raw=(root/name).read_bytes()
        if name.endswith('/workflow_doris_s0_fixture.py'):
            previous=subprocess.check_output(['git','show',commit+':'+name],cwd=root)
            require(ast.dump(ast.parse(previous),include_attributes=False)==ast.dump(ast.parse(raw),include_attributes=False),
                    'DMQ_SOURCE_FIXTURE_SEMANTIC_DRIFT')
            raw=previous
        result.append(sha(raw))
    return result


def qualify(gate, input_key):
    """用冻结的命令输出重算本任务产品资格，支持从相同提交的干净检出复核。"""
    import json
    from pathlib import Path
    import workflow
    import workflow_execution as execution
    import workflow_m2_build as build
    from workflow_environment import locks
    from workflow_evidence import machine,restore
    from workflow_m2_evidence import mtp, require

    task, run = 'G4-DORIS-MAPPING-QUERY-001', 'implementation-01'
    current = build.ROOT/'docs/evidence'/task/'review-fix-01'
    if gate!='environment':
        return qualify_review_fix(gate,input_key,current)
    groups = {'environment': ['prepare'], 'contract': ['wire','pg-golden'],
              'backend': ['adapters','tls','query','semantic-batch','pg-golden','ac06'],
              'web': ['typecheck','lint','unit','build','ui-s3'],
              'interaction': ['s3','ui-s3','ui-s1','ac06']}
    require(gate in groups and workflow.input_key(build.ROOT,gate)==input_key,'DMQ_GATE_INPUT')
    public=build.ROOT/'docs/evidence'/task/run
    tests=0
    examined={}

    def read(relative):
        path=workflow.safe_file(root/relative)
        require(path.is_relative_to(root) and '..' not in Path(relative).parts,'DMQ_PROOF_PATH')
        raw=path.read_bytes()
        examined[relative]=execution.sha(raw)
        require(examined[relative]==index['files'][relative],'DMQ_ORIGINAL_DRIFT')
        return raw

    def record(relative):
        return json.loads(read(relative))

    backend_key=build.inputs('query')
    measured_commit='f5bdc7469a1038d56c7828f0e1222725fbb375ec'
    unchanged_product_key=measured_backend(build.ROOT,measured_commit) if gate in ('backend','contract','interaction','web') else None
    for label in groups[gate]:
        root=public/('s3-requalification' if label in ('query','pg-golden') else 's3')
        index=json.loads((root/'product-inputs.json').read_bytes())
        require(index['taskId']==task and index['runId']==run,'DMQ_GATE_IDENTITY')
        if label=='pg-golden':
            import subprocess
            mapping=json.loads((public/'historical-byte-mapping.json').read_bytes())
            require(mapping['sourceCommit']=='413d7363fa544ee9dbf780a9a2707b880af96ec8' and len(mapping['members'])==17,'DMQ_GOLDEN_HISTORY')
            for name,member in mapping['members'].items():
                require(name==member['originalPath'] and name.startswith(str(public.relative_to(build.ROOT))+'/') and
                        restore(build.ROOT,member)==subprocess.check_output(['git','show',mapping['sourceCommit']+':'+name],cwd=build.ROOT),
                        'DMQ_GOLDEN_HISTORICAL_BYTES')
        if label=='prepare':
            prep=record('prepare.json')
            import platform
            import workflow_environment as environment
            packages,projects,files=locks(build.ROOT)
            admission=environment.git_json(build.ROOT,environment.BASE,environment.ADMISSION)
            archives=environment.approved_archives(build.ROOT,task,packages)
            identity=environment.identities(dict(platform=platform.system()+'-'+platform.machine(),osVersion=platform.mac_ver()[0],
                files=files,tools=admission['files'],sdk=environment.SDK_ARCHIVES,archives={k:v['archiveSha256'] for k,v in archives.items()}),build.ROOT)
            require(identity['contentKey']==prep['contentKey'] and all(execution.sha(Path(t['path']).read_bytes())==t['sha256'] for t in admission['files']),'DMQ_PREPARE_CONTENT')
            require(prep['taskId']==task and prep['status']=='DEPENDENCIES_READY' and
                    prep['downloads']==prep['sdkDownloads']==prep['runtimeCredentialsCopied']==0 and
                    prep['packages']==len(packages) and prep['projects']==len(projects) and
                    prep['webDependencies']['download']==prep['webDependencies']['install']==0 and
                    index['environmentLockHash']==execution.sha(execution.encoded(files)),'DMQ_PREPARE')
            require(sorted(item['project'] for item in prep['assets'])==sorted(item['path'] for item in projects),'DMQ_PREPARE_ASSETS')
            tests+=len(projects)
            continue
        if label=='ac06':
            evidence=root.parent/'s2-equivalent'
            proof=(evidence/'ac06-dependency-proof.json').read_bytes()
            review=json.loads((evidence/'ac06-non-author-review.json').read_bytes())
            require(review['status']=='GO_S3' and review['proofSha256']==execution.sha(proof) and
                    review['caseId']==json.loads(proof)['case'] and reopen_ac06(evidence)==json.loads(proof),'DMQ_AC06_REOPEN')
            # 产品变化仅限工具传输；准确核对原取消快照中参与者及驱动的程序集。
            previous=record('ac06-snapshot.json')
            current=record('api-snapshot.json')
            witness=json.loads((evidence/'s1-host-s2-doris-overlap-69f7b494a29a4858ab2e9e3c35ba624e.json').read_bytes())
            require(previous['snapshotId']==witness['snapshotId'] and current['inputs']['inputKey']==unchanged_product_key,'DMQ_AC06_SNAPSHOTS')
            dlls=set(previous['files'])
            require(dlls==set(current['files']) and
                    {k for k in dlls if previous['files'][k]!=current['files'][k]}<={'OntologyPlatform.Modules.Agents.dll','OntologyPlatform.Modules.Agents.pdb'},
                    'DMQ_AC06_PARTICIPANT_DRIFT')
            tests+=1
            continue
        row=record(label+'/result.json')
        receipt=record(label+'/command.json')
        def stream(name):
            entry=index['streams'][label+'/'+name]
            relative=Path(entry['path']).relative_to(root.relative_to(build.ROOT))
            read(str(relative))
            return restore(build.ROOT,entry)
        stdout,stderr=stream('stdout'),stream('stderr')
        require(receipt['classification']=='SUCCESS' and receipt['exitCode']==0 and receipt['taskId']==task and receipt['runId']==run and
                all(receipt[stream]['sha256']==execution.sha(raw) for stream,raw in [('stdout',stdout),('stderr',stderr)]),'DMQ_COMMAND')
        if label in ('s3','ui-s1','ui-s3'):
            host=record(label+'/host.json')
            snapshot=record('api-snapshot.json')
            browser_argv=[record('prepare.json')['node'],'scripts/maintenance/workflow-m4-query.mjs','--task',task,'--run-id',run,'--mode',label]
            require(receipt['commandSummary']['sha256']==execution.sha(execution.encoded(browser_argv)) and
                    receipt['stage']=='dmq-s1-browser-'+label and json.loads(stdout)['checks']==len(row['checks']),'DMQ_BROWSER_COMMAND')
            require(row['mode']==label and row['status']=='PASS' and row['inputsUnchanged'] and
                    host['snapshotId']==row['inputBinding']['api']['snapshotId']==snapshot['snapshotId'] and
                    snapshot['inputs']['inputKey']==unchanged_product_key and host['status']=='EXITED' and host['exitCode']==0 and not host['exceeded'] and
                    host['browserCommand']==receipt['commandId'] and host['hostPeakBytes']['total']<=int(5.5*1024**3),'DMQ_BROWSER_HOST')
            computed=execution.sha(execution.encoded([snapshot['snapshotId'],label,measured_browser_sources(build.ROOT,measured_commit)]))
            require(receipt['inputFingerprint']==computed,'DMQ_BROWSER_DRIVER_DRIFT')
            checks={c['name'] for c in row['checks'] if c['status']=='PASS'}
            required={'s3':{'denied_tool_g4_resolve_entity','denied_tool_g4_read_observations','denied_tool_g4_traverse_relationships','mcp_exact_measurement','mcp_half_open_edges','fourth_tool_same_bytes_g4_traverse_relationships'},
                      'ui-s3':{'mapping_editor_active_doris_and_frozen_snapshot','ui_same_canonical_g4_resolve_entity','ui_same_canonical_g4_read_observations','ui_same_canonical_g4_traverse_relationships','s3_mobile_no_overflow'},
                      'ui-s1':{'current_owner_revocation_denied','revoked_result_cleared','restored_original_grant_same_bytes','browser_refresh_same_result','browser_refresh_no_business_query','late_old_subject_response_not_rendered','changed_subject_cannot_restore_previous_query'}}
            require(required[label]<=checks and all(c['status']=='PASS' for c in row['checks']),'DMQ_BROWSER_CASES')
            if label.startswith('ui-'):
                web=record('build/result.json')
                require(host['webExitCode'] in (0,143,-15) and host['webBuild']==row['inputBinding']['web'] and
                        host['webBuild']['inputHash']==execution.sha(execution.encoded(web['inputs'])) and
                        host['webBuild']['filesHash']==execution.sha(execution.encoded(web['files'])),'DMQ_BROWSER_WEB')
            tests+=len(row['checks'])
        elif label in ('unit','lint','typecheck','build'):
            from workflow_m4_query import web_source_inputs
            require(receipt['stage']=='query-web-'+label,'DMQ_WEB_STAGE')
            require(web_source_inputs(task)==row['inputs'],'DMQ_WEB_SOURCE_SET')
            require(row['taskId']==task and row['stage']==label and row['exitCode']==0 and row['commandId']==receipt['commandId'] and
                    all(execution.sha((build.ROOT/path).read_bytes())==value for path,value in row['inputs'].items()) and
                    execution.sha(execution.encoded(row['inputs']))==receipt['inputFingerprint'],'DMQ_WEB_INPUT')
            if label=='unit':
                entry=index['losslessOriginals']['unit/vitest-report.json']
                read(str(Path(entry['path']).relative_to(root.relative_to(build.ROOT))))
                original=restore(build.ROOT,entry)
                require(execution.sha(original)==row['reportSha256'],'DMQ_VITEST_HASH')
                tests+=machine(original,'vitest-json')
        else:
            from workflow_doris_s1 import S3_COMPAT_CASES
            fixed=dict(zip(('adapters','tls','query','wire'),S3_COMPAT_CASES,strict=True))
            if label in fixed:
                target,expression,minimum=fixed[label]
                stage='dmq-s3-compat-'+target
                results='s3-compat-results'
                require(row['target']==target and row['filter']==expression,'DMQ_TEST_SELECTION')
            else:
                target,method,minimum,stage,results={
                    'pg-golden':('query','OntologyPlatform.QueryTests.G4QueryTests.HistoricalPgReleaseAndResultKeepCanonicalBytes',2,'dmq-pg-golden','pg-golden-results'),
                    'semantic-batch':('semantic','OntologyPlatform.SemanticTests.VerifiedReadTests.VerifiedBatchRequiresActualComparedGraphsAndShacl',4,'dmq-verified-batch-sem','verified-batch-results')
                }[label]
                require(row['method']==method,'DMQ_METHOD')
                expression='FullyQualifiedName='+method
            built=record('builds/'+target+'.json')
            origin=Path(receipt['cwd'])
            project=Path(build.TARGETS[target])
            dll=origin/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
            argv=[built['command'][0],str(dll),'--filter',expression,'--minimum-expected-tests',str(minimum),'--no-ansi','--progress','off',
                  '--results-directory',str(origin/'artifacts/workflow'/task/run/results)]
            target_key=backend_key if target=='query' else unchanged_product_key
            require(receipt['stage']==stage and receipt['commandSummary']['sha256']==execution.sha(execution.encoded(argv)) and
                    built['taskId']==task and built['target']==target and built['status']=='PASS' and built['exitCode']==0 and
                    built['inputKey']==target_key and built['worktree']==str(origin) and str(dll.relative_to(origin)) in built['outputs'] and
                    row['input']==dict(inputKey=target_key,receiptSha256=examined['builds/'+target+'.json'],
                        outputKey=execution.sha(json.dumps(built['outputs'],sort_keys=True).encode())) and
                    row['exitCode']==0 and row['commandId']==receipt['commandId'] and receipt['inputFingerprint']==execution.sha(execution.encoded(row['input'])),
                    'DMQ_TEST_BUILD_COMMAND')
            count=mtp(stdout+stderr,minimum)
            require(count==row['passed'] and (label not in ('tls','pg-golden','semantic-batch') or count==minimum),'DMQ_MTP_COUNT')
            tests+=count
    return dict(status='PASS',executionMode='REUSED',qualificationMode='FRESH',taskId=task,runId=run,gate=gate,inputKey=input_key,
                tests=tests,skipped=0,originals=examined)



def direct_task_proof(directory, case):
    """重开原八项直接因果，按同一查询的工作实例、完整采样和终态 Profile 重算任务集合。"""
    import json
    from doris_query_cancel_witness import canonical_id, instant_ns, native_task_closes
    from doris_query_profile_witness import compare_tasks, dependency_proof

    def read(prefix, key=case):
        return json.loads((directory/(prefix+key+'.json')).read_bytes())

    shared = dependency_proof(directory, case)
    common = ('originalSevenChecks', 'exactSourceAndReference', 'fixedVersion', 'oneHeapPlan',
              'taskIdentities', 'cancellationOnly', 'actualHandshake', 'officialOutcome', 'fixtureRestored')
    checks = {name: shared['checks'][name] for name in common}
    witness = read('formal-cancel-')
    original = read('overlap-equivalent-')
    pipeline = read('overlap-pipeline-')
    native = read('overlap-native-events-')
    query = canonical_id(witness['sourceQueryId'])
    anchor = instant_ns(witness['beforeUnlockPgUtc'])
    committed = instant_ns(witness['cancelVisiblePgUtc'])
    samples = pipeline['samples']
    first = samples[0]
    drift = max(abs((s['beginNs']-first['beginNs'])-(s['beginMonoNs']-first['beginMonoNs']))+
                abs(s['endNs']-s['beginNs']-s['elapsedNs']) for s in samples)
    def event_time(name):
        rows=[e for e in original['events'] if e['event']==name]
        if len(rows)!=1:
            raise ValueError('RF_NATIVE_EVENT_'+name)
        return instant_ns(rows[0]['utc'])
    arrival, end = event_time('user_cancel_rpc'), event_time('context_end')
    def active(s):
        return [g for g in s['groups'] if g['query'] and canonical_id(g['query'])==query]
    def keys(groups):
        return {(canonical_id(t['instance']),t['task']) for g in groups if g['complete'] and g['closed']==0
                for t in g['tasks'] if not t['eos'] and t['state'] not in ('FINISHED','FINALIZED')}
    before = [s for s in samples if s['complete'] and len(active(s))==2 and s['endNs']+drift<=original['beforeCommitBoundNs']]
    snapshot = {'groups':active(before[-1])}
    wanted = keys(snapshot['groups'])
    instances, named = native_task_closes(native,snapshot['groups'],arrival,end)
    reference = read('overlap-profile-reference-',witness['stress']['attempt'])
    compared = compare_tasks(read('overlap-profile-'),reference,snapshot,instances)
    covered = named | {(canonical_id(t['instance']),t['index']) for t in compared
                       if (t['observedShortfall'] and t['soleMerge']) or t['nonEosScan']}
    empty = next((s for s in samples if s['complete'] and s['count']==0 and end<=s['beginNs']),None)
    audit = original['feAudit']
    deadline = anchor+250_000_000-drift
    checks.update(
        originalDirect=original['status']=='PASS' and all(original['checks'].values()) and shared['originalBrowser']=='PASS',
        fullPopulation=len(wanted)==3 and len(instances)==2 and drift==original['clockDriftUpperNs']<1_000_000 and
            any(s['complete'] and committed+drift<=s['beginNs']<=s['endNs']<=arrival-drift and keys(active(s))==wanted for s in samples),
        directTaskKeys=compared==original['profileComparisons'] and covered==wanted,
        termination=anchor<=committed<arrival<=end and empty is not None and empty['endNs']<=deadline and
            (empty['endNs']-anchor)/1e6==original['pipelineZeroUpperMs'] and
            audit['complete'] and audit['reader'] and audit['isSelect'] and audit['fixedEntity'] and
            arrival<=instant_ns(audit['endUtc'])<=instant_ns(audit['endExclusiveUpperUtc'])<=deadline and
            witness['feClockControl']['passed'] and 0<witness['feInactiveUpperMs']<=250)
    return dict(case=case,sourceQuery=shared['sourceQuery'],platformQuery=shared['platformQuery'],checks=checks,
                status='PASS' if all(checks.values()) else 'NO_GO',method='ORIGINAL_DIRECT_ALL_TASKS',
                timing=shared['timing'],inputs=shared['inputs'])


def session_scratch(output, name):
    """为既有票据探针独占一个新 Owner 临时文件；运行回执归属当前批次。"""
    import os
    import re
    from workflow_execution import ordinary
    if output.name!='review-fix-02' or not re.fullmatch(r'session-ready-[0-9a-f]{32}\.json',name):
        raise ValueError('RF02_SESSION_PATH')
    path=ordinary(output.parent/'implementation-01'/name)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    os.close(fd)
    return path


E1_RUN = 'review-fix-02'
E1_DRIVER_COMMIT = 'f2673f2c62537b5422f308b99cfb25da464eee35'
E1_EXPECTED = {'expired':'PREREQUISITE_STALE:grant_expired_or_missing','short':'PREREQUISITE_STALE:grant_ttl',
               'catalog':'PREREQUISITE_STALE:catalog','activation':'PREREQUISITE_STALE:activation','healthy':None}


def previous_profile_drivers(root, product):
    """核对原运行实际执行的完整旧代码。隔离批次专用分支在旧运行不可达。"""
    import ast
    import subprocess
    from pathlib import Path
    from workflow_execution import sha
    from workflow_m2_evidence import require

    class OldRun(ast.NodeTransformer):
        def visit_If(self, node):
            node=self.generic_visit(node)
            if ast.unparse(node.test)=="vm.EVIDENCE_RUN == 'review-fix-02'":
                return node.orelse
            return node

    result=[]
    for name in BROWSER_SOURCES:
        old=subprocess.check_output(['git','show',product+':'+name],cwd=root)
        now=(root/name).read_bytes()
        if now!=old:
            registered=subprocess.check_output(['git','show',E1_DRIVER_COMMIT+':'+name],cwd=root)
            require(now==registered,'RF_BROWSER_REGISTERED_REVISION')
            filename=Path(name).name
            if filename=='workflow_doris_vm.py':
                a=b"(RUN, 'review-fix-01', 'review-fix-02')"
                require(now.count(a)==1 and now.replace(a,b"(RUN, 'review-fix-01')")==old,'RF_OUTPUT_SCOPE')
            elif filename=='workflow-m4-query.mjs':
                a=b' && !(evidenceRun === "review-fix-02" && argument("mode") === "s2-doris-ready")'
                require(now.count(a)==1 and now.replace(a,b'')==old,'RF_OUTPUT_SCOPE')
            elif filename=='workflow_doris_s1.py':
                require(ast.dump(OldRun().visit(ast.parse(now)))==ast.dump(OldRun().visit(ast.parse(old))),'RF_OUTPUT_SCOPE')
            else:
                raise ValueError('RF_BROWSER_SOURCE_DRIFT')
        result.append(sha(old))
    return result


def qualify_e1(public, prior_raw, prior_command, snapshot, node, agent_build):
    """以列明的五次正式执行重算 E1 资格；每个窗口绑定双方真实命令以及原 FE 审计。"""
    import datetime
    import json
    import re
    import subprocess
    from pathlib import Path
    from workflow_evidence import restore
    from workflow_execution import encoded,sha
    from workflow_m2_build import ROOT
    from workflow_m2_evidence import require
    from workflow_doris_s1 import readiness_budget

    folder=public.parent/E1_RUN
    index=json.loads((folder/'selected.json').read_bytes())
    task='G4-DORIS-MAPPING-QUERY-001'
    owner='implementation-01'
    mode='s2-doris-ready'
    require(index['revision']==E1_DRIVER_COMMIT and index['ownerRun']==owner and index['taskId']==task and index['runId']==E1_RUN
            and set(index['cases'])==set(E1_EXPECTED) and index['reuseProduct']=='9780c8f91cd084c1df11c604186d22d7f08f3023','RF02_SELECTION')
    require(subprocess.run(['git','merge-base','--is-ancestor',E1_DRIVER_COMMIT,'HEAD'],cwd=ROOT).returncode==0,'RF02_EXECUTION_REVISION')
    measured={}
    def data(name):
        entry=index['originals'][name]
        target=(folder.relative_to(ROOT)/'originals'/name).as_posix()
        require(Path(name).name==name and entry['originalPath']==target and entry['encoding'] in ('raw','base64')
                and entry['path']==target+('.raw.json' if entry['encoding']=='base64' else ''),'RF02_MEMBER')
        value=restore(ROOT,entry)
        measured[name]=sha(value)
        return value
    def read(name):return json.loads(data(name))
    def command(cid):
        require(re.fullmatch('[a-f0-9]{32}',cid) is not None,'RF02_COMMAND_ID')
        receipt=read(cid+'-receipt.json')
        require(receipt['schemaVersion']==2 and receipt['started'] is True and receipt['commandId']==cid and
                receipt['taskId']==task and receipt['runId']==E1_RUN and receipt['signal'] is None,'RF02_COMMAND_ID')
        streams=[]
        for stream in ('stdout','stderr'):
            raw=data(cid+'-'+stream+'.txt')
            require((sha(raw),len(raw))==(receipt[stream]['sha256'],receipt[stream]['sizeBytes']),'RF02_STREAM')
            streams.append(raw)
        return receipt,streams[0],streams[1]
    def summary(argv):
        return dict(argumentCount=len(argv)-1,executable=Path(argv[0]).name,sha256=sha(encoded(argv)))
    def millis(value):
        return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()*1000
    drivers={n:sha((ROOT/n).read_bytes()) for n in BROWSER_SOURCES}
    require(all(sha(subprocess.check_output(['git','show',E1_DRIVER_COMMIT+':'+n],cwd=ROOT))==h for n,h in drivers.items()),'RF02_DRIVER_REVISION')
    import ast
    import inspect
    dependency_paths=['scripts/maintenance/'+name for name in ('workflow_doris_fixture.py','workflow_execution.py','workflow_m2_build.py')]
    require(subprocess.run(['git','diff','--quiet',E1_DRIVER_COMMIT,'--',*dependency_paths],cwd=ROOT).returncode==0,'RF02_RUNTIME_DEPENDENCY')
    source_file='scripts/maintenance/workflow_doris_mapping_evidence.py'
    original_module=ast.parse(subprocess.check_output(['git','show',E1_DRIVER_COMMIT+':'+source_file],cwd=ROOT))
    scratch=next(n for n in original_module.body if isinstance(n,ast.FunctionDef) and n.name=='session_scratch')
    require(ast.dump(scratch)==ast.dump(ast.parse(inspect.getsource(session_scratch)).body[0]),'RF02_SESSION_HELPER')
    # 源端注册文件和所有 99 项 API 输出在原构建绑定中逐项核过；这里独立重算快照身份。
    identity={n:snapshot[n] for n in ('files','inputs','commandId','environment','taskId','resourceRun')}
    require(sha(encoded(identity))==snapshot['snapshotId'] and snapshot['commandId']==snapshot['inputs']['receiptSha256'] and
            snapshot['directory']==f"artifacts/workflow/{task}/review-fix-01/runtime-snapshots/{snapshot['snapshotId']}",'RF02_BUILD')
    # 历史反例只认证为原 Base 的原件。拒绝换过内容并重新登记的旧回执。
    history_path=(public.relative_to(ROOT)/'current-inputs.json').as_posix()
    history=json.loads(subprocess.check_output(['git','show','a363fbd53d3f2813539534f921f2b21004638eec:'+history_path],cwd=ROOT))
    for name,cid in history['readinessCommands'].items():
        for member in (name,cid+'-receipt.json'):
            actual=(public.relative_to(ROOT)/'originals'/member).as_posix()
            original=history['originals'][member]
            require(original['originalPath']==actual and sha(prior_raw(member))==original['sha256'],'RF02_HISTORICAL_ORIGINAL')
    oldaudit=json.loads(prior_raw('e1-audit-5a77f112b7c34a65bd2778629e657535.json'))
    oldrow,oldraw=prior_command(oldaudit['commandId'])
    oldout=json.loads(oldraw)
    oldargs,oldkey=e1_audit_identity(oldaudit['fe'],oldaudit['windows'])
    require(oldrow['exitCode']==0 and oldrow['inputFingerprint']==oldkey and oldrow['commandSummary']==summary(oldargs)
            and oldaudit['parserSha256']==sha(E1_AUDIT_PARSER.encode()) and sha(oldraw)==oldaudit['resultSha256'],'RF02_CONTROL_INPUT')
    baseline_api=json.loads(prior_raw('api-build-binding.json'))
    baseline_grants=json.loads(prior_raw('q-grant-renewal-f7316ae0c11a486a815ff1a60e44fe18.json'))
    execute_grant,=[g for g in baseline_grants['new'] if g['permission']=='data.query.execute']
    execution_policy=sha((ROOT/'scripts/maintenance/workflow_execution.py').read_bytes())
    windows={'positive-pressure-control':oldaudit['windows']['positive-pressure-control']}
    seen=set()
    for label,expected_error in E1_EXPECTED.items():
        entry=index['cases'][label]
        name=entry['report']
        require(re.fullmatch(r'browser-s2-doris-ready-[0-9]{13}\.json',name) and name not in windows and
                entry['dispatch']==label+'-'+name,'RF02_REPORT_ID')
        report=read(name)
        dispatch=read(entry['dispatch'])
        host=read(entry['host'])
        subject=report['inputBinding']['api']
        hid=subject['commandId']
        cid=entry['command']
        require(cid not in seen and hid not in seen and cid!=hid,'RF02_UNIQUE')
        seen.update((hid,cid))
        require(dispatch['case']==label and dispatch['report']==name and dispatch['revision']==E1_DRIVER_COMMIT and dispatch['driverSha256']==drivers,'RF02_DRIVER')
        stage=dict(readinessStage='baseline',expectedStale=label if label in ('catalog','activation') else None)
        require(dispatch['stageInputs']==host.get('stageInputs')==stage and 'stressInput' not in host,'RF02_STAGE')
        receipt,stdout,_=command(cid)
        argv=[node,'scripts/maintenance/workflow-m4-query.mjs','--task',task,'--run-id',owner,'--mode',mode]
        require(receipt['stage']=='dmq-s1-browser-'+mode and receipt['commandSummary']==summary(argv),'RF02_ARGV')
        require(receipt['inputFingerprint']==sha(encoded([snapshot['snapshotId'],mode,list(drivers.values()),stage])),'RF02_FINGERPRINT')
        require(receipt['cwd']==baseline_api['worktree'] and receipt['deadlineSeconds']==180 and
                receipt['identity']==sha(encoded([receipt['inputFingerprint'],receipt['environmentFingerprint'],receipt['commandSummary']['sha256'],
                                                  receipt['cwd'],180,execution_policy])),'RF02_COMMAND_IDENTITY')
        location=Path(receipt['cwd'])
        log=json.loads(stdout)
        require(report['inputsUnchanged'] is True and report['taskId']==task and report['runId']==owner and report['mode']==mode
                and report['inputBinding']['web'] is None and not report.get('bindingFailure') and not report.get('networkFailure'),'RF02_REPORT_INPUT')
        require(log['report']==str(location/'artifacts/workflow'/task/E1_RUN/name) and log['status']==report['status']
                and log['failure']==report.get('failure') and log['checks']==len(report['checks']),'RF02_REPORT_REF')
        require(entry['host']=='s1-host-'+mode+'-'+hid+'.json' and entry['events']=='service-events-'+hid+'.json' and
                subject['taskId']==host['taskId']==task and subject['runId']==host['runId']==owner and subject['stage']==host['stage']==mode and
                subject['status']=='READY' and host['status']=='EXITED' and host['commandId']==hid and subject['pid']==host['pid'] and
                subject['processStart']==host['processStart'] and subject['snapshotId']==host['snapshotId']==snapshot['snapshotId'] and
                host['exitCode']==0 and host['exceeded'] is False and 0<host['hostPeakBytes']['api']<=768*1024**2 and
                0<host['hostPeakBytes']['total']<=int(5.5*1024**3),'RF02_HOST')
        events=read(entry['events'])
        private=location/'.tools/security/g4-doris-mapping-query-001'
        host_args=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network-outbound (remote ip "*:*")) (allow network-outbound (remote ip "localhost:*"))',
            '/usr/bin/env','-i','PATH='+dispatch['hostPath'],'ASPNETCORE_ENVIRONMENT=Development',
            'ASPNETCORE_CONTENTROOT='+str(private/owner/'runtime/api'),'G4__SourceCaPath='+str(private/(owner+'-source')/'tls/ca.pem'),
            'ASPNETCORE_URLS=http://127.0.0.1:15641','DOTNET_GCHeapHardLimit=0x18000000','DOTNET_CLI_TELEMETRY_OPTOUT=1',
            'Logging__LogLevel__OntologyPlatform.Modules.SemanticQuery.G4QueryExecution=Information',
            snapshot['environment']['dotnet'],str(location/snapshot['directory']/'OntologyPlatform.Api.dll')]
        require([x['event'] for x in events]==['START','READY','END'] and all(x['taskId']==task and x['runId']==E1_RUN and x['stage']=='service'
                and x['commandId']==hid and x['commandSummary']==dict(executable='sandbox-exec',sha256=sha(encoded(host_args))) for x in events)
                and events[1]['pid']==host['pid'] and events[2]['exitCode']==host['exitCode'] and events[2]['classification']=='STOPPED','RF02_HOST_COMMAND')
        begin,end=millis(receipt['startedAtUtc']),millis(receipt['endedAtUtc'])
        require(millis(dispatch['startedUtc'])<=millis(events[0]['startedAtUtc'])<=begin<=millis(report['startedAtUtc'])<=
                millis(report['finishedAtUtc'])<=end<=millis(events[2]['endedAtUtc'])<=millis(dispatch['endedUtc']),'RF02_TIMELINE')
        windows[name]=[begin,end]
        if expected_error:
            require(receipt['exitCode']==dispatch['dispatchExit']==1 and receipt['classification']=='EXIT_FAILURE' and report['status']=='FAIL' and
                    host.get('browserCommand',cid)==cid and log['phase']=='scenario_ready' and report['failure']==dict(phase='scenario_ready',category='Error',code=expected_error),'RF02_REJECTION')
        else:
            ready=report['scenarioReady']
            require(receipt['exitCode']==dispatch['dispatchExit']==0 and receipt['classification']=='SUCCESS' and host['browserCommand']==cid
                    and report['status']=='PASS' and report['scope']=='PREREQUISITES_ONLY' and all(x['status']=='PASS' for x in report['checks'])
                    and ready==read('ready-'+hid+'.json') and (ready['status'],ready['stage'],ready['command'],ready['mode'],ready['snapshot'])==
                    ('READY','baseline',hid,mode,snapshot['snapshotId']) and ready['budgetSeconds']==readiness_budget('baseline') and
                    ready['fieldCount']==18 and ready['grantRequiredSeconds']==sum(ready['budgetSeconds'].values()),'RF02_HEALTHY')
            from workflow_m2_build import TARGETS
            from workflow_m2_evidence import mtp
            session,session_out,session_err=command(ready['sessionCommand'])
            project=Path(TARGETS['agent'])
            dll=location/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
            session_argv=[snapshot['environment']['dotnet'],str(dll),'--filter',
                          'FullyQualifiedName=OntologyPlatform.AgentTests.G4QueryMafRuntimeTests.BrowserSessionsCoverRegisteredExecutionDeadline',
                          '--minimum-expected-tests','1','--no-ansi','--progress','off','--results-directory',
                          str(location/'artifacts/workflow'/task/E1_RUN/'session-tests')]
            require(session['stage']=='dmq-current-sessions' and session['classification']=='SUCCESS' and session['exitCode']==0 and
                    session['deadlineSeconds']==20 and session['cwd']==str(location) and session['commandSummary']==summary(session_argv)
                    and session['inputFingerprint']==sha(encoded(agent_build)) and ready['sessionRequiredSeconds']==180 and
                    millis(report['startedAtUtc'])<=millis(session['startedAtUtc'])<millis(session['endedAtUtc'])<=millis(report['finishedAtUtc'])
                    and mtp(session_out+session_err,1)==1,'RF02_SESSION_COMMAND')
        if label in ('expired','short'):
            before=read('grant-before-'+label+'.json');after=read('grant-restored-'+label+'.json')
            orig,applied,restored=before['before'],before['applied'],after['restored']
            require(orig['id']==execute_grant['id'] and orig['rowHash']==execute_grant['recordHash'] and orig['expiry']==execute_grant['expiry']
                    and len(execute_grant['fields'])==18 and execute_grant['sites']==['site-a'],'RF02_GRANT_OWNER')
            left=millis(applied['expiry'])-begin
            require(orig['id']==applied['id']==restored['id'] and orig['rowHash']==restored['rowHash'] and orig['expiry']==restored['expiry'] and
                    orig['shapeHash']==applied['shapeHash']==restored['shapeHash'] and applied['rowHash']!=orig['rowHash'] and
                    (left<0 if label=='expired' else 0<left<=120000),'RF02_GRANT_STATE')
            for item,stage_name in ((before,label),(after,'restore-'+label)):
                change,_,_=command(item['command'])
                require(change['stage']=='rf02-grant-'+stage_name and change['exitCode']==0,'RF02_GRANT_CHANGE')
            require(millis(command(before['command'])[0]['endedAtUtc'])<=begin<end<=millis(command(after['command'])[0]['startedAtUtc']),'RF02_GRANT_WINDOW')
    audit=index['audit']
    require(audit['windows']==windows and audit['fe']==oldaudit['fe'] and audit['parserSha256']==oldaudit['parserSha256'],'RF02_AUDIT_WINDOW')
    argv,key=e1_audit_identity(audit['fe'],windows)
    row,stdout,_=command(audit['command'])
    require(row['stage']=='rf02-e1-audit' and row['commandSummary']==summary(argv) and row['inputFingerprint']==key and row['exitCode']==0,'RF02_AUDIT_ID')
    counter=json.loads(stdout)
    control=counter['windows']['positive-pressure-control']
    require(counter['inode']==oldout['inode'] and control==oldout['windows']['positive-pressure-control'] and control['mutations']==154 and control['fixedReads']==173 and
            set(counter['windows'])==set(windows) and counter['firstUtcMs']<min(v[0] for v in windows.values()) and
            counter['lastUtcMs']>max(v[1] for v in windows.values()) and all(v['mutations']==v['fixedReads']==0 for k,v in counter['windows'].items() if k!='positive-pressure-control'),'RF02_AUDIT_COUNTS')
    return {E1_RUN+'/'+name:value for name,value in measured.items()}


def qualify_review_fix(gate, input_key, public):
    """重开本轮定向运行，按当前构建、驱动、真实命令与原件核定各受影响门禁。"""
    import datetime
    import json
    import subprocess
    from pathlib import Path
    import workflow
    import workflow_execution as execution
    import workflow_m2_build as build
    from workflow_evidence import restore, machine
    from workflow_m2_evidence import require, mtp
    from workflow_doris_s1 import S3_COMPAT_CASES
    from workflow_m4_query import web_source_inputs

    root, task, run = build.ROOT, 'G4-DORIS-MAPPING-QUERY-001', 'review-fix-01'
    expected = json.loads((public/'current-inputs.json').read_bytes())
    members = expected['originals']
    examined = {}
    require(expected['runId']==run and expected['taskId']==task and workflow.input_key(root,gate)==input_key,'RF_GATE_ID')
    product=expected['productInputCommit']
    require(len(product)==40 and subprocess.run(['git','merge-base','--is-ancestor',product,'HEAD'],cwd=root).returncode==0 and
            subprocess.run(['git','diff','--quiet',product,'HEAD','--','backend','apps/web'],cwd=root).returncode==0,'RF_PRODUCT_REVISION')
    def raw(name):
        entry=members[name]
        require(Path(name).name==name and entry['originalPath']==(public.relative_to(root)/'originals'/name).as_posix(),'RF_MEMBER_PATH')
        require(entry['encoding'] in ('raw','base64') and entry['path']==entry['originalPath']+('.raw.json' if entry['encoding']=='base64' else ''),'RF_ENVELOPE_PATH')
        data=restore(root,entry)
        examined[name]=execution.sha(data)
        return data
    def read(name): return json.loads(raw(name))
    def command(cid):
        row=read(cid+'-receipt.json')
        require(row['commandId']==cid and row['taskId']==task and row['runId']==run,'RF_COMMAND_ID')
        streams=[]
        for key in ('stdout','stderr'):
            data=raw(cid+'-'+key+'.txt')
            require(execution.sha(data)==row[key]['sha256'] and len(data)==row[key]['sizeBytes'],'RF_STREAM_ID')
            streams.append(data)
        return row, b''.join(streams)
    node=json.loads((public.parent/'implementation-01/s3/prepare.json').read_bytes())['node']
    current=build.inputs('query')
    def bound(target):
        name=target+'-build-binding.json'
        row=read(name)
        require(row['taskId']==task and row['target']==target and row['inputKey']==current and row['status']=='PASS' and row['exitCode']==0,'RF_BUILD_ID')
        return dict(inputKey=current,outputKey=execution.sha(json.dumps(row['outputs'],sort_keys=True).encode()),receiptSha256=examined[name])
    snapshot=read('s1-api-snapshot.json')
    require(snapshot['inputs']==bound('api') and snapshot['resourceRun']==run and snapshot['taskId']==task,'RF_API_BUILD')
    api=read('api-build-binding.json')
    for path,value in snapshot['files'].items():
        require(api['outputs']['backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/'+path]==value,'RF_SNAPSHOT_OUTPUT')
    driver=previous_profile_drivers(root,product)
    checks=0
    def test(label, target, stage, expression, minimum, folder):
        cid=expected['tests'][label]
        row,log=command(cid)
        binding=bound(target)
        project=Path(build.TARGETS[target])
        origin=Path(row['cwd'])
        dll=origin/project.parent/'bin/Debug/net10.0'/(project.stem+'.dll')
        argv=[snapshot['environment']['dotnet'],str(dll),'--filter',expression,'--minimum-expected-tests',str(minimum),'--no-ansi',
              '--progress','off','--results-directory',str(origin/'artifacts/workflow'/task/run/folder)]
        require(row['exitCode']==0 and row['stage']==stage and row['commandSummary']['sha256']==execution.sha(execution.encoded(argv)) and
                row['inputFingerprint']==execution.sha(execution.encoded(binding)),'RF_MTP_EXECUTION')
        return mtp(log,minimum)
    def browser(mode, equivalent=False):
        entry=expected['browsers'][mode]
        host=read(entry['host'])
        report=read(entry['report'])
        row,log=command(host['browserCommand'])
        base=[snapshot['snapshotId'],mode,driver,host['stageInputs']]
        if 'stressInput' in host:
            stamp=host['stressInput']
            require(execution.sha(raw('stress-input-'+stamp+'.json'))==stamp,'RF_STRESS_BINDING')
            base.append(stamp)
        require(report['inputBinding']['api']['commandId']==host['commandId'] and host['status']=='EXITED' and
                report['inputBinding']['api']['snapshotId']==host['snapshotId']==snapshot['snapshotId'] and host['exitCode']==0 and
                not host['exceeded'] and host['hostPeakBytes']['total']<=int(5.5*1024**3) and host['hostPeakBytes']['api']<=768*1024**2 and report['inputsUnchanged'] and report['mode']==mode and
                row['stage']=='dmq-s1-browser-'+mode and row['inputFingerprint']==execution.sha(execution.encoded(base)),'RF_BROWSER_INPUT')
        argv=[node,'scripts/maintenance/workflow-m4-query.mjs','--task',task,'--run-id','implementation-01','--mode',mode]
        require(row['commandSummary']['sha256']==execution.sha(execution.encoded(argv)) and
                report['taskId']==task and report['runId']=='implementation-01' and
                report.get('scenarioReady',{}).get('status')=='READY','RF_BROWSER_PREREQUISITE')
        if equivalent:
            case=expected['ac06']
            proof=read('ac06-direct-'+case+'.json')
            require(report['cancel']['key']==proof['case']==case and report['status']=='PASS' and row['exitCode']==0 and
                    all(c['status']=='PASS' for c in report['checks']),'RF_AC06_ORIGINAL_VERDICT')
            import tempfile
            with tempfile.TemporaryDirectory(prefix='dmq-rf-ac06-') as directory:
                location=Path(directory)
                for name, digest in proof['inputs'].items():
                    data=raw(name)
                    require(execution.sha(data)==digest,'RF_AC06_BYTES')
                    (location/name).write_bytes(data)
                require(direct_task_proof(location,case)==proof and proof['status']=='PASS','RF_AC06_DIRECT')
            review=json.loads((public/'non-author-product-review.json').read_bytes())
            require(review['case']==case and review['proofSha256']==examined['ac06-direct-'+case+'.json'] and
                    review['productInputCommit']==expected['productInputCommit'] and review['decision']=='NON_AUTHOR_PRODUCT_GO','RF_PRODUCT_REVIEW')
            return len(proof['checks'])
        require(row['exitCode']==0 and report['status']=='PASS' and all(c['status']=='PASS' for c in report['checks']),'RF_BROWSER_RESULT')
        required={'s3':{'mcp_exact_measurement','mcp_half_open_edges','fourth_tool_same_bytes_g4_traverse_relationships'},
                  'ui-s3':{'ui_same_canonical_g4_resolve_entity','ui_same_canonical_g4_read_observations','ui_same_canonical_g4_traverse_relationships','s3_mobile_no_overflow'},
                  'ui-s1':{'current_owner_revocation_denied','revoked_result_cleared','restored_original_grant_same_bytes','changed_subject_cannot_restore_previous_query'},
                  's2-doris-root-deadline':{'g2_reads_same_signed_release','healthy_formal_query','query_response_before_original_budget','cancel_response_before_original_budget','root_no_success_side_effect'}}
        require(required[mode]<={c['name'] for c in report['checks']},'RF_BROWSER_COVERAGE')
        if mode.startswith('ui-'):
            previous=read('web-build-binding.json')
            require(host['webExitCode'] in (0,143,-15) and previous['inputs']==web_source_inputs(task) and host['webBuild']==report['inputBinding']['web'] and
                    host['webBuild']['inputHash']==execution.sha(execution.encoded(previous['inputs'])) and
                    host['webBuild']['filesHash']==execution.sha(execution.encoded(previous['files'])),'RF_WEB_BUILD')
        if mode=='s2-doris-root-deadline':
            from urllib.parse import parse_qs,urlsplit
            events=read('root-dependencies-'+report['witnessId']+'.json')
            require(report['baseline']==report['after'] and report['after']['failedAdmissions']==report['after']['cancelAudits']==0
                    and report['after']['executeAudits']==1 and report['after']['status']=='COMPLETED' and not report['after']['cancel'],'RF_TRANSACTION')
            require([r['name'] for r in report['deadlineWitness']]==['query','cancel'],'RF_DEADLINE_PAIR')
            for probe in report['deadlineWitness']:
                phase=probe['name']
                batch=[r for r in events if r['phase']==phase]
                closed=[r for r in batch if r['kind']=='client_closed']
                require(len(closed)==1 and any(r['kind']=='PUT' and r['status'] in (200,201,204) for r in batch) and any(r['kind']=='POST' and r['status']==200 for r in batch) and
                        not any(r['kind']=='safety_release' for r in batch),'RF_ACTUAL_SHACL_CLEANUP')
                uri=closed[0]['path']
                graph=parse_qs(urlsplit(uri).query)['graph'][0]
                deadlines=[r['requestDeadline'] for r in host['cleanupUnknown'] if r['graph']==graph]
                require(len(deadlines)==1,'RF_DEADLINE_OWNER')
                end=datetime.datetime.fromisoformat(deadlines[0]).timestamp()*1000
                require(probe['budgetMs']=={'query':1200,'cancel':5000}[phase] and probe['code']=='semantic_timeout' and
                        probe['clientStartUtcMs']-1<=end-probe['budgetMs']<=closed[0]['utcNs']/1e6<=end and
                        probe['clientResponseUtcMs']<end and probe['elapsedMs']<probe['budgetMs'],'RF_ABSOLUTE_BUDGET')
            put={r['path'] for r in events if r['kind']=='PUT'}
            restored={r['path'] for r in events if r['phase']=='restore' and r['kind']=='GET' and r['status']==404}
            require(put and put<=restored,'RF_GRAPH_RESTORE')
        return len(report['checks'])
    if gate in ('backend','contract'):
        for target,expr,n in S3_COMPAT_CASES:
            if (target=='wire')==(gate=='contract'):
                checks+=test(expr,target,'dmq-s3-compat-'+target,expr,n,'s3-compat-results')
        checks+=test('golden','query','dmq-pg-golden','FullyQualifiedName=OntologyPlatform.QueryTests.G4QueryTests.HistoricalPgReleaseAndResultKeepCanonicalBytes',2,'pg-golden-results')
    if gate=='contract':
        historical=json.loads((public.parent/'implementation-01/historical-byte-mapping.json').read_bytes())
        require(historical['sourceCommit']=='413d7363fa544ee9dbf780a9a2707b880af96ec8' and len(historical['members'])==17,'RF_GOLDEN_HISTORY')
        for name,member in historical['members'].items():
            require(member['originalPath']==name and restore(root,member)==subprocess.check_output(['git','show',historical['sourceCommit']+':'+name],cwd=root),'RF_GOLDEN_BYTES')
    if gate=='backend':
        checks+=test('semantic-batch','semantic','dmq-verified-batch-sem','FullyQualifiedName=OntologyPlatform.SemanticTests.VerifiedReadTests.VerifiedBatchRequiresActualComparedGraphsAndShacl',4,'verified-batch-results')
        checks+=test('deadline','semantic','deadline-suite','FullyQualifiedName~SemanticDeadlineTests',8,'mtp')
        checks+=test('g3','semantic','g3-shared-budget','FullyQualifiedName~G3BoundaryTests.ParsingAcrossAllFourSourcesSharesOneFiveSecondBudget',1,'mtp')
    if gate in ('backend','interaction'):
        checks+=browser('s2-doris-root-deadline')
        checks+=browser('s2-doris-overlap',equivalent=True)
    if gate in ('interaction','web'):
        for mode in ('ui-s1','ui-s3') if gate=='web' else ('ui-s1','ui-s3','s3'):
            checks+=browser(mode)
    if gate=='interaction':
        examined.update(qualify_e1(public,raw,command,snapshot,node,bound('agent')))
        eng=read('e2-production-tests.json')
        for stage in ('rf-ef01-dispatch','rf-ef01-size'):
            row=eng[stage];receipt,output=command(row['commandId'])
            require(receipt['stage']==stage and receipt['exitCode']==0 and receipt['commandSummary']['sha256']==execution.sha(execution.encoded(row['command']))
                    and all(execution.sha((root/path).read_bytes())==sha for path,sha in row['inputs'].items()) and
                    receipt['inputFingerprint']==execution.sha(execution.encoded(row['inputs'])),'RF_E2_EXECUTION')
            require((b'Ran 4 tests' in output and b'OK' in output) if stage=='rf-ef01-dispatch' else b'1 tests, 0 failures' in output,'RF_E2_CASES')
        early=read('early-plan.json')['earlyMeasurements'][0]
        plan=read('early-members.json')
        require(early['head']=='79d6dc173476ce0166a13a34a309598f1e6da953' and early['exitCode']==0 and early['measurement']['sizeBytes']>0 and
                early['representativePaths']==[(public.relative_to(root)/'originals/old-runtime.json.raw.json').as_posix()] and
                plan['status']=='PASS' and plan['diffCheckExitCode']==0,'RF_E2_EARLY')
        publication=json.loads((public/'initial-publication.json').read_bytes())
        before=restore(root,publication['old-runtime'])
        require(publication['old-runtime']['encoding']=='base64' and not before.endswith(b'\n') and
                publication['resource-start']['encoding']=='raw' and restore(root,publication['resource-start']).endswith(b'\n'),'RF_E3_FIRST_WRITE')
        checks+=len(E1_EXPECTED)+4
    if gate=='web':
        for label in ('typecheck','lint','unit'):
            row=read('web-'+label+'-result.json')
            receipt,log=command(row['commandId'])
            require(receipt['exitCode']==row['exitCode']==0 and row['inputs']==web_source_inputs(task) and
                    receipt['inputFingerprint']==execution.sha(execution.encoded(row['inputs'])) and
                    row['stage']==label and row['taskId']==task,'RF_WEB_COMMAND')
            if label=='unit':
                report=raw('vitest-report.json')
                require(row['reportSha256']==execution.sha(report),'RF_WEB_TEST_BYTES')
                checks+=machine(report,'vitest-json')
            else: checks+=1
    require(checks>0,'RF_EMPTY_GATE')
    return dict(taskId=task,runId=E1_RUN,productEvidenceRun=run,gate=gate,inputKey=input_key,status='PASS',tests=checks,skipped=0,
                executionMode='REUSED',qualificationMode='FRESH',originals=examined)


E1_AUDIT_PARSER=r"""import datetime,hashlib,json,os,pathlib,re,sys
windows=json.loads(sys.argv[1]);states={k:dict(rows=0,mutations=0,fixedReads=0,firstOffset=None,lastOffset=None) for k in windows}
digests={k:hashlib.sha256() for k in windows};first=last=None
source=pathlib.Path('/opt/apache-doris/fe/log/fe.audit.log')
with source.open('rb') as stream:
 st=os.fstat(stream.fileno());limit=st.st_size;offset=0
 while offset<limit:
  raw=stream.readline();end=stream.tell()
  if not raw.endswith(b'\n') or end>limit:break
  m=re.search(rb'\|Timestamp=([0-9:. -]+)',raw)
  if m:
   stamp=datetime.datetime.fromisoformat(m[1].decode()).replace(tzinfo=datetime.timezone.utc).timestamp()*1000
   first=stamp if first is None else min(first,stamp);last=stamp if last is None else max(last,stamp)
   for k,(begin,final) in windows.items():
    if begin-5<=stamp<=final+5:
     row=states[k];row['rows']+=1;digests[k].update(raw)
     if row['firstOffset'] is None:row['firstOffset']=offset
     row['lastOffset']=end
     stmt=raw.partition(b'|Stmt=')[2].split(b'|')[0]
     if re.search(rb'\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE|LOAD)\b',stmt,re.I) and re.search(rb'dmq_(entity|target)',stmt,re.I):row['mutations']+=1
     if b'SET_VAR(enable_sql_cache=false)' in stmt and b'fixture.dmq_' in stmt:row['fixedReads']+=1
  offset=end
 assert source.stat().st_ino==st.st_ino and first<min(x[0] for x in windows.values()) and last>max(x[1] for x in windows.values())
for k,v in states.items():v['sha256']=digests[k].hexdigest()
print(json.dumps(dict(inode=st.st_ino,scannedBytes=offset,firstUtcMs=first,lastUtcMs=last,windows=states)))"""


def e1_audit_identity(fe, windows):
    """按实际 FE、准确命令窗口以及登记的解析器重算审计命令和输入身份。"""
    import json
    from workflow_execution import encoded,sha
    argv=['docker','--context','desktop-linux','exec',fe,'python3','-c',E1_AUDIT_PARSER,json.dumps(windows,sort_keys=True)]
    return argv,sha(encoded([fe,windows,E1_AUDIT_PARSER]))


def audit_prerequisites():
    """只读现有 Doris FE 审计，按登记的真实浏览器窗口投影，不公开 SQL 正文。"""
    import datetime
    import json
    import workflow_execution as execution
    import workflow_doris_s1 as s
    from workflow_doris_s0_fixture import INDEX, record
    from workflow_m2_evidence import require
    require(s.vm.EVIDENCE_RUN=='review-fix-01','RF_AUDIT_RUN')
    fe=json.loads(INDEX.read_bytes())['services']['fe']['id']
    require(s.live_stack()['fe']==fe,'RF_AUDIT_OWNER')
    def milliseconds(timestamp):
        return datetime.datetime.fromisoformat(timestamp.replace('Z','+00:00')).timestamp()*1000
    windows={}
    for path in sorted(s.OUT.glob('browser-s2-doris-ready-*.json')):
        row=json.loads(path.read_bytes())
        if row.get('failure',{}).get('code') in ('PREREQUISITE_STALE:grant','PREREQUISITE_STALE:grant_expired_or_missing','PREREQUISITE_STALE:grant_ttl','PREREQUISITE_STALE:activation','PREREQUISITE_STALE:catalog'):
            windows[path.name]=[milliseconds(row['startedAtUtc']),milliseconds(row['finishedAtUtc'])]
    cases=sorted(s.OUT.glob('formal-cancel-*.json'),key=lambda f:f.stat().st_mtime)
    require(len(windows)>=4 and cases,'RF_AUDIT_CASES')
    positive=json.loads(cases[0].read_bytes())
    mid=milliseconds(positive['beforeUnlockPgUtc'])
    windows['positive-pressure-control']=[mid-120000,mid+90000]
    # 同一 FE 留存日志；每窗口保留参与计数的原行数、首末偏移及原字节摘要。
    parser=E1_AUDIT_PARSER
    args=['docker','--context','desktop-linux','exec',fe,'python3','-c',parser,json.dumps(windows,sort_keys=True)]
    result=execution.run(args,s.ROOT,task=s.vm.TASK,run_id=s.vm.EVIDENCE_RUN,stage='rf-prerequisite-audit',input_key=execution.sha(execution.encoded([fe,windows,parser])),timeout=20)
    require(result.returncode==0,'RF_AUDIT_SCAN_'+result.receipt['commandId'])
    counters=json.loads(result.stdout)['windows']
    require(all(v['mutations']==v['fixedReads']==0 for k,v in counters.items() if k!='positive-pressure-control') and
            counters['positive-pressure-control']['mutations']>0 and counters['positive-pressure-control']['fixedReads']>0,'RF_AUDIT_COVERAGE')
    row=dict(commandId=result.receipt['commandId'],fe=fe,windows=windows,parserSha256=execution.sha(parser.encode()),commandSha256=execution.sha(execution.encoded(args)),resultSha256=execution.sha(result.stdout))
    record(s.OUT/('e1-audit-'+row['commandId']+'.json'),row)
    return row

def publish_original(root, run, source):
    """从本任务独立运行目录发布已选的机器原件，保持原字节及恢复身份。"""
    import re
    from pathlib import Path
    from workflow_execution import ordinary
    from workflow_evidence import publish
    task = 'G4-DORIS-MAPPING-QUERY-001'
    if not re.fullmatch(r'review-fix-[0-9]{2}', run):
        raise ValueError('DMQ_ARCHIVE_RUN')
    directory = root / 'artifacts/workflow' / task / run
    source = ordinary(Path(source).absolute())
    if source.parent != directory or not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.(json|txt)', source.name):
        raise ValueError('DMQ_ARCHIVE_SOURCE')
    if source.stat().st_size > 1024 * 1024:
        raise ValueError('DMQ_ARCHIVE_SIZE')
    relative = Path('docs/evidence') / task / run / 'originals' / source.name
    return publish(root, relative.as_posix(), source.read_bytes())


if __name__=='__main__':
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description='同一 Doris 任务的公开原件发布及资格重开')
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--gate')
    action.add_argument('--publish-original')
    parser.add_argument('--run')
    parser.add_argument('--input-key')
    args=parser.parse_args()
    if args.publish_original and args.run and not args.input_key:
        result = publish_original(Path(__file__).resolve().parents[2], args.run, args.publish_original)
    elif args.gate and args.input_key and not args.run:
        result = qualify(args.gate, args.input_key)
    else:
        parser.error('发布须提供 run，资格重开须提供 input-key。')
    print(json.dumps(result))
