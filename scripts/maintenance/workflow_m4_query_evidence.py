"""M4原件解释层；只解析不可变报告，不执行产品或更换原构建身份。"""
import json
from datetime import datetime

TASK = 'G4-M4-QUERY-001'
RUN = 'query-impl-01'


def demand_causality(row, run_id=RUN):
    """UTC关联加同进程单调顺序证明源读取、两次激活、提交拒绝属于同一在途查询。"""
    def utc(value):
        if not isinstance(value, str): raise ValueError('QUERY_ABA_TIME_REQUIRED')
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.utcoffset() is None or result.utcoffset().total_seconds() != 0:
            raise ValueError('QUERY_ABA_UTC_REQUIRED')
        return result
    mapping = row.get('mappingId')
    if not isinstance(mapping, str) or not mapping or row.get('resourceRun') != run_id:
        raise ValueError('QUERY_ABA_RUN_MAPPING_REQUIRED')
    captured, b, a = [row[key] for key in ['capturedA', 'activatedB', 'activatedA']]
    if any(item.get('mappingId') != mapping for item in [captured, b, a]) or b.get('previousReleaseId') != captured['mappingReleaseId'] or a.get('previousReleaseId') != b['mappingReleaseId']:
        raise ValueError('QUERY_ABA_MAPPING_CHAIN')
    admitted, deadline = utc(row.get('admittedAtUtc')), utc(row.get('deadlineAtUtc'))
    if not 0 < (deadline-admitted).total_seconds() <= 5:
        raise ValueError('QUERY_ABA_DEADLINE_INVALID')
    events = row.get('events')
    phases = ['SOURCE_READ_COMPLETED', 'B_ACTIVATED', 'A_ACTIVATED', 'COMMIT_REJECTED']
    if not isinstance(events, list) or len(events) != len(phases): raise ValueError('QUERY_ABA_PHASES_REQUIRED')
    previous_utc, previous_mono = admitted, -1
    for index, (event, phase) in enumerate(zip(events, phases)):
        if not isinstance(event, dict) or event.get('phase') != phase or event.get('sequence') != index+1 or event.get('queryId') != row['queryId'] or event.get('mappingId') != mapping:
            raise ValueError('QUERY_ABA_EVENT_IDENTITY_ORDER')
        observed, monotonic = utc(event.get('utc')), event.get('monotonicMs')
        if type(monotonic) not in (int, float) or not previous_mono <= monotonic <= row['elapsedMs'] or not previous_utc <= observed < deadline:
            raise ValueError('QUERY_ABA_CAUSAL_ORDER')
        previous_utc, previous_mono = observed, monotonic


def demand_aba_original(raw, stage, task=TASK, run_id=RUN):
    """独立重开真实在途ABA原件，单纯MAF测试通过不能充当本项验收。"""
    import re
    if stage != 'query-real-aba-inflight-runtime': raise ValueError('QUERY_ABA_STAGE_INVALID')
    reports = []
    for line in raw.decode(errors='replace').splitlines():
        try: value = json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(value, dict) and value.get('case') == 'AC-05_INFLIGHT_ABA': reports.append(value)
    if len(reports) != 1: raise ValueError('QUERY_ABA_ORIGINAL_REQUIRED')
    row = reports[0]
    if row.get('taskId') != task or row.get('status') != 'PASS' or row.get('abaCompleted') is not True \
        or row.get('errorStatus') != 409 or row.get('errorCode') != 'query_binding_stale' \
        or not re.fullmatch(r'query-[0-9a-f]{32}', row.get('queryId', '')) or row.get('executionStatus') not in ['RUNNING','FAILED','CANCELLED'] \
        or row.get('resultHash', 'missing') is not None \
        or any(row.get(key) != 0 for key in ['ciphertextBytes','resultSize','committedReadReceipts','successfulQueryAudits']) \
        or not 0 < row.get('elapsedMs', 0) < 5000:
        raise ValueError('QUERY_ABA_ORIGINAL_INVALID')
    captured, b, a = (row.get(key, {}) for key in ['capturedA','activatedB','activatedA'])
    if any(not isinstance(item, dict) or not re.fullmatch(r'activation-[0-9a-f]{32}', item.get('activationId', ''))
           or not re.fullmatch(r'release-[0-9a-f]{32}', item.get('mappingReleaseId', '')) for item in [captured,b,a]) \
        or not isinstance(captured.get('activationRevision'), str) or not re.fullmatch(r'[1-9][0-9]*', captured['activationRevision']) \
        or any(type(item.get('activationRevision')) is not int or item['activationRevision'] <= 0 for item in [b,a]) \
        or captured.get('mappingReleaseId') != a.get('mappingReleaseId') \
        or captured.get('mappingReleaseId') == b.get('mappingReleaseId') \
        or len({captured.get('activationId'),b.get('activationId'),a.get('activationId')}) != 3 \
        or not int(captured.get('activationRevision', 0)) < b.get('activationRevision', 0) < a.get('activationRevision', 0):
        raise ValueError('QUERY_ABA_IDENTITY_INVALID')
    demand_causality(row, run_id)
    return row


def demand_build_inputs(build, inputs):
    """构建闭包必须完整相等；旧凭据漏掉嵌入合同也不能被新资格包装接受。"""
    from workflow_m4_query import ROOT
    from workflow_m4_query_inputs import build_inputs
    expected = build_inputs(ROOT,build['project'],inputs) if build.get('project') else {path:digest for path,digest in inputs.items()
                if path.startswith(('backend/', 'docs/contracts/')) or '/' not in path}
    if not expected or build.get('inputs') != expected:
        raise ValueError('QUERY_BUILD_INPUT_CLOSURE')


def demand_qualification(row, name, inputs, all_inputs=None, task=TASK, run_id=RUN):
    """先拒绝外任务、失败、漂移与零原件，随后才打开实际命令报告。"""
    if all_inputs is not None:
        from workflow_m4_query_inputs import demand_scope
        if not isinstance(row.get('allInputs'),dict): raise ValueError('QUERY_INPUT_CLASSIFICATION_MISSING')
        demand_scope(row['allInputs'],all_inputs,inputs)
    if row.get('taskId') != task or row.get('runId') != run_id or row.get('name') != name \
        or row.get('status') != 'PASS' or row.get('exitCode') != 0 or row.get('inputsUnchanged') is not True \
        or row.get('inputs') != inputs or not row.get('commands'):
        raise ValueError('QUERY_QUALIFICATION_INVALID')


def qualify(gate, input_key):
    """当前输入重开实际非零测试和浏览器原件；缺适配证据保持阻断。"""
    import workflow
    from workflow_m4_query import ROOT, prepared, structural, qualification_inputs
    from workflow_execution import ordinary, sha
    from workflow_m2_evidence import mtp
    if gate not in ['environment', 'contract', 'backend', 'web', 'interaction'] or workflow.input_key(ROOT, gate) != input_key:
        raise ValueError('QUERY_QUALIFICATION_GATE_INVALID')
    prepared()
    structural(ROOT, TASK)
    required = {
        'environment': [], 'contract': ['contract'],
        'backend': ['query-unit', 'source-unit', 'security-unit', 'agent-unit', 'persistence', 'source', 'maf-binding', 'aba-inflight'],
        'web': ['web-typecheck', 'web-lint', 'web-unit', 'ui-s1', 'ui-s3'],
        'interaction': ['numeric', 's1', 's1-reopen', 's2-basic', 's2-runtime', 's2-race', 's2-aba', 's2-capacity', 's2-inflight', 's2-connection', 's3', 'aba-inflight'],
    }[gate]
    output = ROOT/'artifacts/workflow'/TASK/RUN
    all_inputs = qualification_inputs()
    originals = []
    count = 1 if gate == 'environment' else 0
    def read(reference):
        path = ordinary(ROOT/reference['path'])
        if not path.is_relative_to(ROOT/'artifacts/workflow'/TASK): raise ValueError('QUERY_QUALIFICATION_PATH')
        raw = path.read_bytes()
        if sha(raw) != reference['sha256']: raise ValueError('QUERY_QUALIFICATION_HASH')
        originals.append(reference)
        return raw
    for name in required:
        inputs=qualification_inputs(name)
        candidates = sorted((path for path in output.glob('qualification-'+name+'-*.json')
                             if json.loads(path.read_text()).get('name') == name), key=lambda path: path.stat().st_mtime)
        if not candidates: raise ValueError('QUERY_QUALIFICATION_MISSING_'+name)
        path = candidates[-1]
        row = json.loads(read(dict(path=str(path.relative_to(ROOT)), sha256=sha(path.read_bytes()))))
        if row.get('projection'):
            from workflow_m4_query_inputs import project_original
            proof=row['projection']
            original=json.loads(read(proof['original']))
            driver=read(proof['driver']).decode()
            projected=project_original(ROOT,original,name,all_inputs,driver)
            if row['inputs']!=projected or any(row.get(key)!=original.get(key) for key in ['taskId','runId','name','inputsUnchanged','commands','reports','build','exitCode','status']):
                raise ValueError('QUERY_PROJECTED_ORIGINAL_CHANGED')
        demand_qualification(row, name, inputs, all_inputs)
        if row.get('inputPolicyVersion') != 2: raise ValueError('QUERY_LEGACY_INPUT_PROJECTION_REQUIRES_PROOF')
        test_count = 0
        aba_originals = 0
        if name in ['contract','query-unit','source-unit','security-unit','agent-unit','persistence','source','maf-binding','aba-inflight'] and 'build' not in row:
            raise ValueError('QUERY_QUALIFICATION_BUILD_MISSING')
        if 'build' in row:
            from workflow_execution import encoded
            build = row['build']; receipt = build['receipt']
            demand_build_inputs(build, all_inputs)
            original = ROOT/'artifacts/workflow'/TASK/'commands'/RUN/receipt['commandId']/'receipt.json'
            if json.loads(original.read_text()) != receipt or receipt.get('exitCode') != 0 or receipt.get('stage') != 'query-build-'+build['project'] or receipt.get('inputFingerprint') != sha(encoded(build['inputs'])) or not build['binaries']:
                raise ValueError('QUERY_QUALIFICATION_BUILD')
            if any(all_inputs.get(path) != digest for path,digest in build['inputs'].items()): raise ValueError('QUERY_QUALIFICATION_BUILD_INPUT')
            read(dict(path=str(original.relative_to(ROOT)),sha256=sha(original.read_bytes())))
            for stream in ['stdout','stderr']: read(receipt[stream])
        for reference in row['commands']:
            command = json.loads(read(reference))
            if command.get('taskId') != TASK or command.get('runId') != RUN or command.get('exitCode') != 0 or command.get('classification') != 'SUCCESS' or not command.get('started'):
                raise ValueError('QUERY_QUALIFICATION_COMMAND')
            raw = b''.join(read(command[key]) for key in ['stdout', 'stderr'])
            if name == 'aba-inflight' and command['stage'] == 'query-real-aba-inflight-runtime':
                demand_aba_original(raw, command['stage'])
                aba_originals += 1
            if command['stage'].startswith(('query-unit-', 'query-contract-tests', 'query-real-')):
                test_count += mtp(raw, 1)
        if row['reports']:
            for reference in row['reports']:
                report = json.loads(read(reference))
                if report.get('taskId') != TASK or report.get('runId') != RUN or report.get('mode') != name or report.get('status') != 'PASS' or report.get('inputsUnchanged') is not True or not report.get('http') or not report.get('checks') or any(check.get('status') != 'PASS' for check in report['checks']):
                    raise ValueError('QUERY_QUALIFICATION_BROWSER')
                test_count += len(report['checks'])
        elif name.startswith('web-'):
            stage = name.removeprefix('web-')
            rows = [json.loads(path.read_text()) for path in output.glob('web-'+stage+'-*/result.json')]
            matching = [web for web in rows if any(json.loads(read(ref))['commandId'] == web['commandId'] for ref in row['commands'])]
            if len(matching) != 1 or matching[0]['exitCode'] != 0: raise ValueError('QUERY_QUALIFICATION_WEB')
            web = matching[0]
            if any(sha((ROOT/path).read_bytes()) != digest for path, digest in web['inputs'].items()): raise ValueError('QUERY_QUALIFICATION_WEB_INPUT')
            if stage == 'unit':
                from workflow_evidence import machine
                test_count += machine(read(dict(path=web['report'], sha256=web['reportSha256'])), 'vitest-json')
            else: test_count += 1
        if name == 'aba-inflight' and aba_originals != 1: raise ValueError('QUERY_ABA_ORIGINAL_REQUIRED')
        if test_count <= 0: raise ValueError('QUERY_QUALIFICATION_ZERO_TESTS')
        count += test_count
    return dict(taskId=TASK, runId=RUN, gate=gate, status='PASS', executionMode='REUSED', qualificationMode='FRESH', tests=count, skipped=0, originals=originals)
