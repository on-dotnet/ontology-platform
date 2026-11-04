#!/usr/bin/env python3
"""使用当前三容器设施直接执行正式模块程序集；不调用历史restore/main。"""
import json
import re
import zipfile
from pathlib import Path
import runtime as rt

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


def run_modules(m):
    """实际测试数与skip逐项留下，任何skip不提升为PASS。"""
    r=rt.runtime_value(m)
    for service in ('platform-pg','fuseki','rustfs'):
        rt.require(rt.inspect_owned(m,r['containerIds'][service],service)['State']['Running'],'MODULE_RESOURCE_DOWN')
    env=rt.environment(m['runId'])
    private=rt.private_dir(m['runId'])
    pg='Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()
    env.update(ConnectionStrings__governance=pg,RUSTFS_ACCESS_KEY=(private/'s3-access').read_text(),RUSTFS_SECRET_KEY=(private/'s3-secret').read_text())
    ef=Path('/Users/chasen/.nuget/packages/dotnet-ef/10.0.13/tools/net8.0/any/dotnet-ef.dll')
    rt.require(ef.is_file(),'EXACT_EF_TOOL_MISSING')
    ef_before=verify_ef(m)
    for name in ('Governance','Ontology','Publishing','Agents'):
        project=rt.ROOT/f'backend/src/Modules/{name}/OntologyPlatform.Modules.{name}/OntologyPlatform.Modules.{name}.csproj'
        rt.require(project.is_file(),'MODULE_PROJECT_MISSING')
        command=['/usr/local/share/dotnet/dotnet',str(ef),'database','update','--project',str(project),'--startup-project',str(project),'--configuration','Debug','--no-build']
        rt.execute(m,'module-migrate-'+name,rt.offline_command(command,loopback=True),env=env,sensitive=True,timeout=90)
    rt.require(verify_ef(m)==ef_before,'EF_EXECUTED_INPUT_DRIFT')
    rt.write_json(rt.ARTIFACTS/m['runId']/'ef-tool-inputs.json',{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'files':ef_before})
    env.update(G2_SEM_JENA_ORIGIN='http://127.0.0.1:15303',G2_SEM_SAMPLES=str(rt.ROOT/'samples/g2'),G2_SEM_PG_CONNECTION=pg)
    for prefix in ('PUB','QRY','AI'):
        env.update({f'G2_{prefix}_PG':pg,f'G2_{prefix}_JENA':'http://127.0.0.1:15303',f'G2_{prefix}_S3':'http://127.0.0.1:15900',f'G2_{prefix}_SAMPLES':str(rt.ROOT/'samples/g2')})
    schema=rt.ARTIFACTS/m['runId']/'agent-schema-result.json'
    rt.require(not schema.exists(),'EXISTING_SCHEMA_RESULT')
    env['G2_AI_SCHEMA_OUTPUT']=str(schema)
    results=[]
    for suffix in ('SemanticTests','PublishingTests','QueryTests','AgentTests'):
        command=['/usr/local/share/dotnet/dotnet',str(rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}/bin/Debug/net10.0/OntologyPlatform.{suffix}.dll'),'--minimum-expected-tests','1','--no-ansi','--output','Detailed']
        command+=['--results-directory',str(rt.ARTIFACTS/m['runId']/'test-results'/('module-'+suffix))]
        raw=rt.execute(m,'module-'+suffix,rt.offline_command(command,loopback=True),env=env,sensitive=True,timeout=300)
        projection=rt.test_projection(m,'module-'+suffix,suffix,raw)
        rt.require(projection['summary']['SKIP']==0 and projection['summary']['FAIL']==0,'MODULE_REQUIRED_FIXTURES_SKIPPED')
        results.append(dict(project=suffix,total=projection['summary']['total'],skipped=[],status='PASS'))
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
    results=[]
    for suffix in ('SecurityTests','G2ContractTests'):
        name='g3-fixture-'+suffix;dll=rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}/bin/Debug/net10.0/OntologyPlatform.{suffix}.dll'
        raw=rt.execute(m,name,rt.offline_command(['/usr/local/share/dotnet/dotnet',str(dll),'--minimum-expected-tests','1','--no-ansi','--output','Detailed','--results-directory',str(rt.ARTIFACTS/m['runId']/'test-results'/name)],loopback=True),env=env,sensitive=True,timeout=300)
        projection=rt.test_projection(m,name,suffix,raw)
        rt.require(projection['summary']['SKIP']==0 and projection['summary']['FAIL']==0,'G3_REQUIRED_FIXTURES_SKIPPED');results.append(projection['summary'])
    rt.require(rt.digest(output.read_bytes())==actual_hash,'ACTUAL_V2_INPUT_DRIFT')
    return results
