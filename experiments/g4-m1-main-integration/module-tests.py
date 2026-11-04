#!/usr/bin/env python3
"""使用当前三容器设施直接执行正式模块程序集；不调用历史restore/main。"""
import json
import re
import runtime as rt

# 只复用已审断言常量，不执行历史main或restore入口。
SCHEMA_CHECK = "\nconst fs = require('fs');\nconst Ajv = require(process.argv[2]);\nconst bundle = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));\nconst allowed = new Set(['$schema','$ref','$defs','type','properties','required','additionalProperties','items','enum','oneOf','anyOf','allOf','not','description','format','minimum','maximum','minLength','maxLength','const','discriminator']);\nconst keywords = new Set();\nfunction scan(schema) {\n  if (typeof schema === 'boolean') return;\n  for (const [key, value] of Object.entries(schema)) {\n    if (!allowed.has(key)) throw new Error('Unsupported schema keyword: ' + key);\n    keywords.add(key);\n    if (key === '$defs' || key === 'properties') Object.values(value).forEach(scan);\n    if (['oneOf','anyOf','allOf'].includes(key)) value.forEach(scan);\n    if (['items','not','additionalProperties'].includes(key) && typeof value === 'object') scan(value);\n  }\n}\nscan(bundle.schema);\nconst ajv = new Ajv({validateSchema:false, allErrors:true, unknownFormats:'ignore', logger:false});\nconst validate = ajv.compile(bundle.schema);\nif (!validate(bundle.result)) throw new Error('Actual MCP payload failed output contract: ' + JSON.stringify(validate.errors));\nfor (const result of bundle.additionalResults || []) if (!validate(result)) throw new Error('Another actual MCP tool failed output contract');\nconst mutations = [\n  value => { delete value.status; },\n  value => { value.status = 'INVENTED'; },\n  value => { value.injectedActor = 'admin'; },\n  value => { value.snapshot = null; },\n  value => { value.evidence = null; },\n  value => { value.data[0].ontology = {classIris:[],objectPropertyIris:[],datatypePropertyIris:[],labels:[],supportedAxioms:[],diagnostics:[]}; }\n];\nfor (const mutate of mutations) {\n  const value = structuredClone(bundle.result);\n  mutate(value);\n  if (validate(value)) throw new Error('Invalid MCP payload unexpectedly passed output contract');\n}\nconsole.log(JSON.stringify({status:'PASS', validator:'repo-locked ajv6.15.0', scope:'observed common keyword subset; not full 2020-12 dialect certification', schemaKeywords:[...keywords].sort(), positive:1+(bundle.additionalResults||[]).length, negative:mutations.length, mediaTypes:bundle.mediaTypes}));\n"


def run_modules(m):
    """实际测试数与skip逐项留下，任何skip不提升为PASS。"""
    r=rt.runtime_value(m)
    for service in ('platform-pg','fuseki','rustfs'):
        rt.require(rt.inspect_owned(m,r['containerIds'][service],service)['State']['Running'],'MODULE_RESOURCE_DOWN')
    env=rt.environment()
    private=rt.private_dir(m['runId'])
    pg='Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()
    env.update(ConnectionStrings__governance=pg,RUSTFS_ACCESS_KEY=(private/'s3-access').read_text(),RUSTFS_SECRET_KEY=(private/'s3-secret').read_text())
    env.update(G2_SEM_JENA_ORIGIN='http://127.0.0.1:15303',G2_SEM_SAMPLES=str(rt.ROOT/'samples/g2'),G2_SEM_PG_CONNECTION=pg)
    for prefix in ('PUB','QRY','AI'):
        env.update({f'G2_{prefix}_PG':pg,f'G2_{prefix}_JENA':'http://127.0.0.1:15303',f'G2_{prefix}_S3':'http://127.0.0.1:15900',f'G2_{prefix}_SAMPLES':str(rt.ROOT/'samples/g2')})
    schema=rt.ARTIFACTS/m['runId']/'agent-schema-result.json'
    rt.require(not schema.exists(),'EXISTING_SCHEMA_RESULT')
    env['G2_AI_SCHEMA_OUTPUT']=str(schema)
    results=[]
    for suffix in ('SemanticTests','PublishingTests','QueryTests','AgentTests'):
        command=['/usr/local/share/dotnet/dotnet',str(rt.ROOT/f'backend/tests/OntologyPlatform.{suffix}/bin/Debug/net10.0/OntologyPlatform.{suffix}.dll'),'--minimum-expected-tests','1','--no-ansi','--output','Detailed']
        raw=rt.execute(m,'module-'+suffix,command,env=env,sensitive=True,timeout=300)
        text=raw.decode(errors='replace')
        match=re.search(r'(?:总计|total):\s*(\d+)',text,re.IGNORECASE)
        rt.require(match and int(match[1])>0,'ZERO_TESTS')
        skips=re.findall(r'(?:已跳过|Skipped) (.+)',text)
        count=re.search(r'(?:已跳过|skipped):\s*([1-9]\d*)',text,re.IGNORECASE)
        rt.require(not count,'MODULE_REQUIRED_FIXTURES_SKIPPED')
        results.append(dict(project=suffix,total=int(match[1]),skipped=skips,status='PARTIAL' if skips else 'PASS'))
    rt.require(schema.is_file(),'MCP_SCHEMA_OUTPUT_MISSING')
    rt.execute(m,'mcp-schema-positive-negative',['/opt/homebrew/opt/node@24/bin/node','-e',SCHEMA_CHECK,str(schema),str(rt.ROOT/'node_modules/.pnpm/ajv@6.15.0/node_modules/ajv')])
    return results
