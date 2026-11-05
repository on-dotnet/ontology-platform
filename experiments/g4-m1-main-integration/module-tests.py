#!/usr/bin/env python3
"""使用当前三容器设施直接执行正式模块程序集；不调用历史restore/main。"""
import json
import re
import zipfile
import collections
import os
import time
import subprocess
from pathlib import Path
import runtime as rt
import closeout

# 只复用已审断言常量，不执行历史main或restore入口。
SCHEMA_CHECK = "\nconst fs = require('fs');\nconst Ajv = require(process.argv[2]);\nconst bundle = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));\nconst allowed = new Set(['$schema','$ref','$defs','type','properties','required','additionalProperties','items','enum','oneOf','anyOf','allOf','not','description','format','minimum','maximum','minLength','maxLength','const','discriminator']);\nconst keywords = new Set();\nfunction scan(schema) {\n  if (typeof schema === 'boolean') return;\n  for (const [key, value] of Object.entries(schema)) {\n    if (!allowed.has(key)) throw new Error('Unsupported schema keyword: ' + key);\n    keywords.add(key);\n    if (key === '$defs' || key === 'properties') Object.values(value).forEach(scan);\n    if (['oneOf','anyOf','allOf'].includes(key)) value.forEach(scan);\n    if (['items','not','additionalProperties'].includes(key) && typeof value === 'object') scan(value);\n  }\n}\nscan(bundle.schema);\nconst ajv = new Ajv({validateSchema:false, allErrors:true, unknownFormats:'ignore', logger:false});\nconst validate = ajv.compile(bundle.schema);\nif (!validate(bundle.result)) throw new Error('Actual MCP payload failed output contract: ' + JSON.stringify(validate.errors));\nfor (const result of bundle.additionalResults || []) if (!validate(result)) throw new Error('Another actual MCP tool failed output contract');\nconst mutations = [\n  value => { delete value.status; },\n  value => { value.status = 'INVENTED'; },\n  value => { value.injectedActor = 'admin'; },\n  value => { value.snapshot = null; },\n  value => { value.evidence = null; },\n  value => { value.data[0].ontology = {classIris:[],objectPropertyIris:[],datatypePropertyIris:[],labels:[],supportedAxioms:[],diagnostics:[]}; }\n];\nfor (const mutate of mutations) {\n  const value = structuredClone(bundle.result);\n  mutate(value);\n  if (validate(value)) throw new Error('Invalid MCP payload unexpectedly passed output contract');\n}\nconsole.log(JSON.stringify({status:'PASS', validator:'repo-locked ajv6.15.0', scope:'observed common keyword subset; not full 2020-12 dialect certification', schemaKeywords:[...keywords].sort(), positive:1+(bundle.additionalResults||[]).length, negative:mutations.length, mediaTypes:bundle.mediaTypes}));\n"


def verify_ef(m):
    """执行前后核对已准入EF归档全部解包载荷，拒绝共享DLL被替换。"""
    archive=Path('/Users/chasen/.nuget/packages/dotnet-ef/10.0.13/dotnet-ef.10.0.13.nupkg')
    return verify_ef_payload(archive,m['tools'][str(archive)])


def verify_ef_payload(archive,expected_sha):
    """tools目录不得添加CLR可能额外消费的配置或共享链接。"""
    rt.require(rt.digest(archive.read_bytes())==expected_sha,'EF_ARCHIVE_DRIFT')
    files=[]
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if member.is_dir() or member.filename in ('_rels/.rels','[Content_Types].xml') or member.filename.startswith('package/services/metadata/core-properties/'):continue
            relative=Path(member.filename)
            rt.require(not relative.is_absolute() and '..' not in relative.parts,'EF_MEMBER_BOUNDARY')
            target=rt.boundary(archive.parent/relative,archive.parent,exists=True)
            rt.require(target.stat().st_nlink==1,'EF_HARDLINK')
            raw=target.read_bytes();rt.require(raw==package.read(member),'EF_PAYLOAD_DRIFT')
            files.append({'path':member.filename,'sha256':rt.digest(raw)})
    rt.require(len({r['path'].lower() for r in files})==len(files),'EF_DUPLICATE_MEMBER')
    actual=set()
    for path in (archive.parent/'tools').rglob('*'):
        rt.boundary(path,archive.parent,exists=True)
        if path.is_file():
            rt.require(path.stat().st_nlink==1,'EF_HARDLINK');actual.add(path.relative_to(archive.parent).as_posix())
        else:rt.require(path.is_dir(),'EF_SPECIAL_FILE')
    rt.require(actual=={r['path'] for r in files if r['path'].startswith('tools/')},'EF_EXTRA_RUNTIME_INPUT')
    return files


MODULE_PROJECTS=('SemanticTests','PublishingTests','QueryTests','AgentTests')


def module_project(suffix):
    """方法隔离只适用于已批准三服务组的四个正式程序集。"""
    rt.require(suffix in MODULE_PROJECTS,'MODULE_PROJECT_ALLOWLIST')
    return rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}'


def module_partition(cases,sources):
    """由同构建逐案例身份匹配唯一源码FQN；保留同方法全部参数及内部并发。"""
    expected=[row['case'] for row in cases]
    rt.require(expected and len(expected)==len(set(expected)),'SEMANTIC_CASE_AMBIGUOUS')
    grouped={}
    for case in expected:
        match=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)(?: \(.*\))?',case)
        rt.require(match,'SEMANTIC_CASE_NAME');grouped.setdefault(match[1],[]).append(case)
    plan=[]
    for method,names in sorted(grouped.items()):
        matches=[]
        for path,source in sources.items():
            declarations=re.findall(r'(?m)^    public (?:async )?(?:Task|void) '+re.escape(method)+r'\(',source)
            if not declarations:continue
            namespaces=re.findall(r'(?m)^namespace ([A-Za-z0-9_.]+);$',source)
            classes=re.findall(r'(?m)^public sealed class ([A-Za-z0-9_]+)$',source)
            rt.require(len(declarations)==len(namespaces)==len(classes)==1,'SEMANTIC_SOURCE_AMBIGUOUS')
            matches.append({'method':namespaces[0]+'.'+classes[0]+'.'+method,'source':path,'sourceSha256':rt.digest(source.encode()),'cases':sorted(names)})
        rt.require(len(matches)==1,'SEMANTIC_METHOD_MAPPING');plan.append(matches[0])
    return plan


def exact_cases(expected,actual):
    """案例多重集合逐项匹配，禁止用相同总数掩盖遗漏、重复或新增案例。"""
    rt.require(collections.Counter(expected)==collections.Counter(actual),'SEMANTIC_CASE_SET_DRIFT')


def module_ingress_snapshot(raw,pid):
    """同一日志快照计算占槽与退出；核验前已占槽但尚未建Exec也不能称为空闲。"""
    rows=[json.loads(line) for line in raw.splitlines()]
    rt.require(rows and any(r['event']=='ready' for r in rows) and all(row['pid']==pid for row in rows),'SEMANTIC_INGRESS_PID')
    opened={r['token'] for r in rows if r['event']=='reserved'}
    rt.require(all(r['token'] in opened for r in rows if r['event'] in ('connection','connection_closed','exec_created')),'SEMANTIC_RESERVATION_MISSING')
    closed={r['token'] for r in rows if r['event']=='connection_closed'}
    created={r['execId'] for r in rows if r['event']=='exec_created'}
    exited={r['execId'] for r in rows if r['event']=='exec_exited' and r['running'] is False and type(r['exitCode']) is int}
    return {'idle':opened<=closed and created<=exited,'connections':len(opened),'execs':len(created),'capacityRefusals':sum(r['event']=='refused_capacity' for r in rows),'eventsSha256':rt.digest(raw)}


def wait_module_ingress_idle(m):
    """批次间等待准确进程的连接和远端Exec退出；不掐断测试连接或提升容量。"""
    a=rt.ARTIFACTS/m['runId'];phase=rt.runtime_value(m).get('modulePhase')
    rt.require(phase in rt.MODULE_PHASES.values(),'MODULE_PHASE')
    ready=json.loads((a/('ingress-'+phase+'-ready.json')).read_text())
    rt.require(ready['taskId']==rt.TASK and ready['runId']==m['runId'] and ready['testedCommit']==m['_head'] and ready['manifestSha256']==m['_sha256'],'SEMANTIC_INGRESS_BINDING')
    process=json.loads((a/('ingress-'+phase+'-process.json')).read_text())
    rt.require(process['pid']==ready['pid'] and process['taskId']==rt.TASK and process['runId']==m['runId'] and process['testedCommit']==m['_head'] and process['runtimeSha256']==ready['runtimeSha256']==m['drivers']['runtime.py'],'SEMANTIC_INGRESS_PROCESS_BINDING')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        os.kill(ready['pid'],0)
        rt.require(subprocess.check_output(['ps','-p',str(ready['pid']),'-o','lstart='],text=True).strip()==process['birth'],'SEMANTIC_INGRESS_PID_REUSED')
        raw=(a/('ingress-'+phase+'-events.jsonl')).read_bytes()
        try:snapshot=module_ingress_snapshot(raw,ready['pid'])
        except json.JSONDecodeError:time.sleep(.05);continue
        if snapshot['idle']:return snapshot
        time.sleep(.05)
    raise ValueError('SEMANTIC_INGRESS_NOT_IDLE')


def run_module_methods(m,env,suffix):
    """完整模块案例按方法隔离进程，保留方法内并发及参数；不修改正式断言。"""
    rt.require(rt.runtime_value(m).get('modulePhase')==rt.MODULE_PHASES[suffix],'MODULE_PROJECT_PHASE')
    project=module_project(suffix);a=rt.ARTIFACTS/m['runId'];baseline_path=a/'case-projections'/('baseline-'+suffix+'.json');baseline=json.loads(baseline_path.read_text())
    receipt=a/'commands'/('baseline-'+suffix+'.json');original=json.loads(receipt.read_text());raw=(a/'commands'/('baseline-'+suffix+'.log')).read_bytes()
    rt.require(baseline['testedCommit']==m['_head'] and original['manifestSha256']==m['_sha256'] and original['exitCode']==0,'SEMANTIC_BASELINE_BINDING')
    rt.require(rt.digest(raw)==original['logSha256']==baseline['rawLogSha256'] and rt.digest(receipt.read_bytes())==baseline['commandReceiptSha256'],'SEMANTIC_BASELINE_HASH')
    rt.require(rt.parse_test_cases(raw.decode())['cases']==baseline['cases'],'SEMANTIC_BASELINE_CASES')
    sources={p.relative_to(rt.ROOT).as_posix():p.read_bytes().decode('utf-8') for p in project.glob('*.cs')}
    plan=module_partition(baseline['cases'],sources)
    rt.require(baseline['project']==suffix and all(item['method'].startswith('OntologyPlatform.'+suffix+'.') for item in plan),'MODULE_METHOD_PROJECT_BINDING')
    dll=rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}/bin/Debug/net10.0/OntologyPlatform.{suffix}.dll'
    rt.require(rt.digest(dll.read_bytes())==baseline['assemblySha256'],'SEMANTIC_ASSEMBLY_DRIFT')
    rt.write_json(a/('module-method-plan-'+suffix+'.json'),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'project':suffix,'assemblySha256':baseline['assemblySha256'],'baselineSha256':rt.digest(baseline_path.read_bytes()),'methods':plan,'scope':'ALL_CASES_METHOD_PROCESS_ISOLATION'})
    observed=[];batches=[]
    for index,item in enumerate(plan,1):
        before=wait_module_ingress_idle(m);name='module-'+suffix+'-m'+str(index).zfill(3)
        command=['/usr/local/share/dotnet/dotnet',str(dll),'--filter','FullyQualifiedName='+item['method'],'--minimum-expected-tests','1','--no-ansi','--output','Detailed','--results-directory',str(a/'test-results'/name)]
        output=rt.execute(m,name,rt.offline_command(command,loopback=True),env=env,sensitive=True,timeout=90)
        parsed=rt.parse_test_cases(output.decode());actual=[row['case'] for row in parsed['cases']]
        exact_cases(item['cases'],actual)
        rt.require(parsed['summary']['SKIP']==0 and parsed['summary']['FAIL']==0,'MODULE_REQUIRED_FIXTURES_SKIPPED')
        after=wait_module_ingress_idle(m)
        rt.require(after['capacityRefusals']==before['capacityRefusals'],'SEMANTIC_FIXTURE_CAPACITY_REFUSAL')
        rt.test_projection(m,name,suffix,output);observed.extend(actual)
        batches.append({'command':name,'method':item['method'],'summary':parsed['summary'],'before':before,'after':after})
    exact_cases([row['case'] for row in baseline['cases']],observed)
    rt.write_json(a/('module-method-results-'+suffix+'.json'),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'project':suffix,'status':'PASS','scope':'ALL_CASES_METHOD_PROCESS_ISOLATION','total':len(observed),'batches':batches})
    return dict(project=suffix,total=len(observed),skipped=[],status='PASS',executionMode='METHOD_PROCESS_ISOLATION',methods=len(plan))


def module_environment(m):
    """同Run私有身份供每个全新模块fixture使用；不保留前项目的数据库状态。"""
    env=rt.environment(m['runId']);private=rt.private_dir(m['runId'])
    pg='Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()
    env.update(ConnectionStrings__governance=pg,RUSTFS_ACCESS_KEY=(private/'s3-access').read_text(),RUSTFS_SECRET_KEY=(private/'s3-secret').read_text())
    env.update(G2_SEM_JENA_ORIGIN='http://127.0.0.1:15303',G2_SEM_SAMPLES=str(rt.ROOT/'samples/g2'),G2_SEM_PG_CONNECTION=pg)
    for prefix in ('PUB','QRY','AI'):
        env.update({f'G2_{prefix}_PG':pg,f'G2_{prefix}_JENA':'http://127.0.0.1:15303',f'G2_{prefix}_S3':'http://127.0.0.1:15900',f'G2_{prefix}_SAMPLES':str(rt.ROOT/'samples/g2')})
    return env


def migrate_module_phase(m, env, phase):
    """每项目全新平台库运行原四模块正式迁移，命令及EF字节绑定独立phase。"""
    rt.require(phase in rt.MODULE_PHASES.values(),'MODULE_PHASE')
    r=rt.runtime_value(m);rt.require(r.get('modulePhase')==phase,'MODULE_PROJECT_PHASE')
    for service in ('platform-pg','fuseki','rustfs'):
        rt.require(rt.inspect_owned(m,r['containerIds'][service],service)['State']['Running'],'MODULE_RESOURCE_DOWN')
    ef=Path('/Users/chasen/.nuget/packages/dotnet-ef/10.0.13/tools/net8.0/any/dotnet-ef.dll')
    rt.require(ef.is_file(),'EXACT_EF_TOOL_MISSING');ef_before=verify_ef(m)
    for name in ('Governance','Ontology','Publishing','Agents'):
        project=rt.ROOT/f'backend/src/Modules/{name}/OntologyPlatform.Modules.{name}/OntologyPlatform.Modules.{name}.csproj'
        rt.require(project.is_file(),'MODULE_PROJECT_MISSING')
        command=['/usr/local/share/dotnet/dotnet',str(ef),'database','update','--project',str(project),'--startup-project',str(project),'--configuration','Debug','--no-build']
        rt.execute(m,phase+'-migrate-'+name,rt.offline_command(command,loopback=True),env=env,sensitive=True,timeout=90)
    rt.require(verify_ef(m)==ef_before,'EF_EXECUTED_INPUT_DRIFT')
    rt.write_json(rt.ARTIFACTS/m['runId']/('ef-tool-inputs-'+phase+'.json'),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'phase':phase,'files':ef_before})


def run_modules(m):
    """四项目分别拥有完整三服务寿命；全部案例、方法内并发和MCP后验不缩减。"""
    env=module_environment(m);schema=rt.ARTIFACTS/m['runId']/'agent-schema-result.json'
    rt.require(not schema.exists(),'EXISTING_SCHEMA_RESULT');env['G2_AI_SCHEMA_OUTPUT']=str(schema)
    results=[]
    for suffix in MODULE_PROJECTS:
        phase=rt.MODULE_PHASES[suffix]
        rt.start_group(m,'g3',modules=True,module_phase=phase)
        migrate_module_phase(m,env,phase)
        result=run_module_methods(m,env,suffix)
        rt.require(result['status']=='PASS','MODULE_REQUIRED_CASES')
        rt.resource_snapshot(m,'g3','resources-'+phase+'-completed')
        retired=closeout.reclaim(m,phase,apply=True)
        receipt=rt.ARTIFACTS/m['runId']/('cleanup-'+phase+'-result.json')
        rt.write_json(receipt,retired)
        rt.require(retired['status']=='PASS','MODULE_PHASE_NOT_RECLAIMED')
        result.update(fixturePhase=phase,cleanupReceiptSha256=rt.digest(receipt.read_bytes()))
        results.append(result)
    rt.require(schema.is_file(),'MCP_SCHEMA_OUTPUT_MISSING')
    rt.execute(m,'mcp-schema-positive-negative',['/opt/homebrew/opt/node@24/bin/node','-e',SCHEMA_CHECK,str(schema),str(rt.ROOT/'node_modules/.pnpm/ajv@6.15.0/node_modules/ajv')])
    return results


def g3_fixture_tests(m):
    """真实G3组补闭Security的PG/OIDC以及正式兼容二进制读取实际V2清单。"""
    import readback
    rt.check_build(m);private=rt.private_dir(m['runId']);env=rt.environment(m['runId'])
    env.update(G1_SEC_PG_CONNECTION='Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text(),G1_SEC_OIDC_RUNTIME=str(private/'runtime.json'))
    report=readback.reports(m,'g3-compatibility-baseline')
    manifests=[r['manifest'] for r in report['releases'] if r['manifest']['schemaVersion']==2]
    rt.require(manifests,'ACTUAL_V2_MANIFEST_MISSING')
    output=rt.ROOT/'backend/tests/OntologyPlatform.G2ContractTests/bin/Debug/actual-v2-manifest.json'
    rt.require(not output.exists(),'EXISTING_COMPATIBILITY_MANIFEST');rt.write_json(output,manifests[-1])
    actual_hash=rt.digest(output.read_bytes())
    rt.write_json(rt.ARTIFACTS/m['runId']/'actual-v2-input.json',{'path':str(output),'sha256':actual_hash,'sourceReportSha256':readback.report_sha(m,'g3-compatibility-baseline'),'releaseId':manifests[-1]['releaseId']})
    # 只管理本次刚创建的准确夹具；未知预存文件仍由上方拒绝，旧字节不覆盖。
    original=output.read_bytes();archive=rt.ARTIFACTS/m['runId']/'actual-v2-manifest.json'
    with archive.open('xb') as stream:stream.write(original)
    created=output.lstat()
    results=[]
    try:
        for suffix in ('SecurityTests','G2ContractTests'):
            name='g3-fixture-'+suffix;dll=rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}/bin/Debug/net10.0/OntologyPlatform.{suffix}.dll'
            raw=rt.execute(m,name,rt.offline_command(['/usr/local/share/dotnet/dotnet',str(dll),'--minimum-expected-tests','1','--no-ansi','--output','Detailed','--results-directory',str(rt.ARTIFACTS/m['runId']/'test-results'/name)],loopback=True),env=env,sensitive=True,timeout=300)
            projection=rt.test_projection(m,name,suffix,raw)
            rt.require(projection['summary']['SKIP']==0 and projection['summary']['FAIL']==0,'G3_REQUIRED_FIXTURES_SKIPPED');results.append(projection['summary'])
    finally:
        current=output.lstat()
        rt.require(not output.is_symlink() and current.st_nlink==1 and (current.st_dev,current.st_ino,current.st_mtime_ns)==(created.st_dev,created.st_ino,created.st_mtime_ns) and output.read_bytes()==original and archive.read_bytes()==original,'ACTUAL_V2_INPUT_DRIFT')
        rt.write_json(rt.ARTIFACTS/m['runId']/'actual-v2-retirement-before.json',{'path':str(output),'sha256':actual_hash,'archive':str(archive),'device':current.st_dev,'inode':current.st_ino,'operation':'unlink exact current-run generated fixture'})
        output.unlink()
        try:output.lstat()
        except FileNotFoundError as error:rt.require(error.errno==2,'ACTUAL_V2_ABSENCE')
        else:raise ValueError('ACTUAL_V2_REMAINS')
        rt.write_json(rt.ARTIFACTS/m['runId']/'actual-v2-retired.json',{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'path':str(output),'sha256':actual_hash,'archive':str(archive),'exitCode':0,'absence':'lstat ENOENT'})
    return results
