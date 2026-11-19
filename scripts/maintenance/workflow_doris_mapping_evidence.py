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
    groups = {'environment': ['prepare'], 'contract': ['wire','pg-golden'],
              'backend': ['adapters','tls','query','semantic-batch','pg-golden','ac06'],
              'web': ['typecheck','lint','unit','build','ui-s3'],
              'interaction': ['s3','ui-s3','ui-s1','ac06']}
    require(gate in groups and workflow.input_key(build.ROOT,gate)==input_key,'DMQ_GATE_INPUT')
    root=build.ROOT/'docs/evidence'/task/run/'s3'
    index=json.loads((root/'product-inputs.json').read_bytes())
    require(index['taskId']==task and index['runId']==run,'DMQ_GATE_IDENTITY')
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
    for label in groups[gate]:
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
            require(previous['snapshotId']==witness['snapshotId'] and current['inputs']['inputKey']==backend_key,'DMQ_AC06_SNAPSHOTS')
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
                    snapshot['inputs']['inputKey']==backend_key and host['status']=='EXITED' and host['exitCode']==0 and not host['exceeded'] and
                    host['browserCommand']==receipt['commandId'] and host['hostPeakBytes']['total']<=int(5.5*1024**3),'DMQ_BROWSER_HOST')
            paths=BROWSER_SOURCES
            computed=execution.sha(execution.encoded([snapshot['snapshotId'],label,[execution.sha((build.ROOT/p).read_bytes()) for p in paths]]))
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
            require(receipt['stage']==stage and receipt['commandSummary']['sha256']==execution.sha(execution.encoded(argv)) and
                    built['taskId']==task and built['target']==target and built['status']=='PASS' and built['exitCode']==0 and
                    built['inputKey']==backend_key and built['worktree']==str(origin) and str(dll.relative_to(origin)) in built['outputs'] and
                    row['input']==dict(inputKey=backend_key,receiptSha256=examined['builds/'+target+'.json'],
                        outputKey=execution.sha(json.dumps(built['outputs'],sort_keys=True).encode())) and
                    row['exitCode']==0 and row['commandId']==receipt['commandId'] and receipt['inputFingerprint']==execution.sha(execution.encoded(row['input'])),
                    'DMQ_TEST_BUILD_COMMAND')
            count=mtp(stdout+stderr,minimum)
            require(count==row['passed'] and (label not in ('tls','pg-golden','semantic-batch') or count==minimum),'DMQ_MTP_COUNT')
            tests+=count
    return dict(status='PASS',executionMode='REUSED',qualificationMode='FRESH',taskId=task,runId=run,gate=gate,inputKey=input_key,
                tests=tests,skipped=0,originals=examined)


if __name__=='__main__':
    import argparse
    import json
    parser=argparse.ArgumentParser(description='重开本任务已提交的正式产品原件')
    parser.add_argument('--gate',required=True)
    parser.add_argument('--input-key',required=True)
    args=parser.parse_args()
    print(json.dumps(qualify(args.gate,args.input_key)))
