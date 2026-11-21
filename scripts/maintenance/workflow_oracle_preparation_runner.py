"""本次准确失败行的一次性维护程序集；从冻结源码作白名单替换，不改产品构建。"""
import json
import subprocess
import uuid
from pathlib import Path
import workflow_execution as ex
import workflow_m2_build as build
import workflow_oracle_mapping_resume as resume
from workflow_oracle_mapping_resources import require

HEAD='451d26a9de8c77e9ec408d9b2208d2dcac4755e0'
ROOT=resume.ROOT
AREA=resume.AREA/'s2-s3-01'
DIRECTORY=AREA/'preparation-runner-dfe9e6c31322487c80499e9a1e9cd96c'
BACKEND='e8b537ed53b24faac246757d9de6592ae6a03ddeb96c81767f1b4373892d0877'
REPLACEMENTS={
 'G4OracleAccessMaintenance':'G4OraclePreparationMaintenance',
 'OracleAccessMaintenance':'OraclePreparationMaintenance',
 'OracleAccessFailureMaintenanceInIsolatedPostgres':'OraclePreparationFailureMaintenanceInIsolatedPostgres',
 'query-4b9f97e1bbdd45f7a39111c907447f65':'query-c2195dd80e21477c9f75f44cf29e8ad0',
 'oracle-execution-8db5f162e634422abf8b94caf509d2c9':'oracle-execution-2262397f3f0b4e4c884d201de49aea6e',
 'b4b07ea50d304927975cd5d052ff58e4':'1a396b17dc654ab09d72119870db69e0',
 '04f23ea8cfe34868a8500b80164d86fb':'7e3085f4533143fb84b49adc83159998',
 'e04b175fec4de4f9f6437e3841c14fd312f304dfa6849b3c6d98a2a491655a1c':'e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd',
 '3365a0ef157ed7b265d94f2ff0fd648bbfc3d79c64c8d875d144af7ef00ef5fd':'49f86dd4e0ec3ae0c1d1c0749a2f6764361d3c555a1e3938f77e24c1e8ff0d92',
 '25e9289fe30b97d2e03ed49723134713966a9949faf53fdc1c199af74ac56f5a':'5b786878c681a5a05c2cddd0079d654fd06d7d7ed05001cab1ca5822594c1f57',
 '5dda9b7f61a129ea975162da32706ae41433efad261039e09804ee8fe00c6c3f':'e8ffbaa43779ae60fc76c3e67d703365719f0a698cafa3e43c1f385d0078edf0',
 'eb5cfd622f3049238006b828e1a4ff52':'9bc224697554422480d502c2d9b2262d'}


def sources():
    """维护算法、入口与全部测试源码取同一准确Git提交；仅三份允许固定词法替换。"""
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',HEAD,'--','backend/tests/OntologyPlatform.QueryTests'],cwd=ROOT).decode().splitlines()
    names=[n for n in names if n.endswith('.cs')]
    core='backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4OracleAccessMaintenance.cs'
    entry='backend/src/Hosts/OntologyPlatform.Api/G4/OracleAccessMaintenance.cs'
    changed={core,entry,'backend/tests/OntologyPlatform.QueryTests/G4OracleAccessRecoveryTests.cs'}
    result={}
    for name in [*names,core,entry]:
        original=subprocess.check_output(['git','show',HEAD+':'+name],cwd=ROOT);text=original.decode()
        if name in changed:
            for left,right in REPLACEMENTS.items():text=text.replace(left,right)
        result[name]=dict(originalSha256=ex.sha(original),raw=text.encode())
    return result


def compile_runner():
    """只有新nonce目录可写；SDK及现有全部引用逐件绑定，原bin/快照不能被输出覆盖。"""
    require(build.inputs('api')==BACKEND and build.inputs('query')==BACKEND,'PREPARATION_BACKEND_CHANGED')
    require(DIRECTORY.is_dir() and not (DIRECTORY/'build.json').exists(),'PREPARATION_RUNNER_ONCE')
    prepared=ROOT/'artifacts/workflow'/resume.TASK/'environment/d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43/runs/3463d8ec1a64483989d9f2b531190dbb/receipt.json'
    prep=json.loads(ex.ordinary(prepared).read_bytes());sdk=Path(prep['dotnet']).parent
    bindings={n:build.validate(n,resume.TASK) for n in ('api','query','agent')}
    tests=ROOT/Path(build.TARGETS['query']).parent/'bin/Debug/net10.0'
    refs={p.name:p for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref') for p in sorted((sdk/'packs'/pack/'10.0.13/ref/net10.0').glob('*.dll'))}
    for p in sorted(tests.glob('*.dll')):
        if p.name!='OntologyPlatform.QueryTests.dll':refs.setdefault(p.name,p)
    items=sources();folder=DIRECTORY/('source-'+uuid.uuid4().hex);folder.mkdir(mode=0o700)
    files=[];manifest={}
    for name,row in items.items():
        p=folder/Path(name).name;p.write_bytes(row['raw']);files.append(p)
        manifest[name]=dict(originalSha256=row['originalSha256'],generatedSha256=ex.sha(row['raw']),sizeBytes=len(row['raw']))
    global_source='global using System; global using System.Collections.Generic; global using System.IO; global using System.Linq; global using System.Net.Http; global using System.Threading; global using System.Threading.Tasks; global using Microsoft.VisualStudio.TestTools.UnitTesting;'
    p=folder/'GlobalUsings.cs';p.write_text(global_source);files.append(p)
    p=folder/'PreparationRunner.cs';p.write_text(ENTRY);files.append(p)
    generated=sorted((DIRECTORY/'generated').glob('*.cs'));require(len(generated)==2,'PREPARATION_MTP_GENERATED');files+=generated
    dll=DIRECTORY/'OntologyPlatform.QueryTests.dll'
    args=[prep['dotnet'],str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-target:exe','-main:PreparationRunner','-deterministic+','-nostdlib+','-nullable:enable','-out:'+str(dll),*['-r:'+str(p) for p in refs.values()],*[str(p) for p in files]]
    inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):ex.sha(ex.ordinary(p).read_bytes()) for p in [Path(args[1]),*refs.values(),*files]}
    result=ex.run(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*args],ROOT,task=resume.TASK,run_id=resume.PRODUCT,
        stage='s23-preparation-runner-build',input_key=ex.sha(ex.encoded(inputs)),environment=prep['environment'],timeout=60)
    record=dict(taskId=resume.TASK,runId=resume.PRODUCT,sourceHead=HEAD,backendInput=BACKEND,commandId=result.receipt['commandId'],exitCode=result.returncode,
        sourceManifest=manifest,replacements=REPLACEMENTS,inputs=inputs,bindings=bindings,mtpGenerationCommand='0e68d60da1a24bf0a0fee07a96e72e72')
    if result.returncode:
        resume.platform.save(DIRECTORY/('build-failed-'+result.receipt['commandId']+'.json'),record)
        print((result.stdout+result.stderr).decode()[-8000:]);require(False,'PREPARATION_COMPILE')
    record['dll']=dict(path=str(dll.relative_to(ROOT)),sha256=ex.sha(dll.read_bytes()),sizeBytes=dll.stat().st_size)
    require(bindings=={n:build.validate(n,resume.TASK) for n in bindings},'PREPARATION_PRODUCT_BUILD_DRIFT')
    resume.platform.save(DIRECTORY/'build.json',record);return record


ENTRY='/// <summary>真实MTP与本条失败记录的独立维护入口，不创建HTTP服务。</summary>\ninternal static class PreparationRunner\n{\n    /// <summary>维护仅接受固定单参数，其余参数交由既有正式MTP解析和实际测试发现。</summary>\n    internal static async System.Threading.Tasks.Task<int> Main(string[] args)\n    {\n        if (args.Length == 1 && args[0] == "--recover-preparation")\n        {\n            await OntologyPlatform.Api.G4.OraclePreparationMaintenance.RunAsync();\n            return System.Environment.ExitCode;\n        }\n        return await OntologyPlatform.QueryTests.MicrosoftTestingPlatformApplication.RunAsync(args);\n    }\n}\n'


def verified_runner():
    """重开独立构建的全部准确输入和输出，产品绑定保持原样；不是以同名程序集推断身份。"""
    raw_build=ex.ordinary(DIRECTORY/'build.json').read_bytes()
    require(ex.sha(raw_build)=='e87bdda008ad11071d34806bfa57a038fdc54c9923647f4b9e9db3950495d847','PREPARATION_BUILD_ORIGINAL')
    record=json.loads(raw_build)
    require(record['exitCode']==0 and record['sourceHead']==HEAD and record['backendInput']==BACKEND,'PREPARATION_RUNNER_BUILD')
    for path,digest in record['inputs'].items():
        require(ex.sha(ex.ordinary(ROOT/Path(path)).read_bytes())==digest,'PREPARATION_RUNNER_INPUT')
    # 准确编译argv与原双流独立重开；生成来源命令只保留历史，不以缺失argv冒充已重开。
    from workflow_oracle_mapping_continuity import command
    paths=[ROOT/Path(name) for name in record['inputs']]
    compiler=paths[0];refs=[p for p in paths[1:] if p.suffix=='.dll'];files=[p for p in paths[1:] if p.suffix=='.cs']
    dotnet=compiler.parents[4]/'dotnet'
    args=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',str(dotnet),str(compiler),'-nologo','-target:exe','-main:PreparationRunner','-deterministic+','-nostdlib+','-nullable:enable','-out:'+str(ROOT/record['dll']['path']),*['-r:'+str(p) for p in refs],*[str(p) for p in files]]
    command(ROOT,record['commandId'],resume.PRODUCT,args,'s23-preparation-runner-build',ex.sha(ex.encoded(record['inputs'])),60)
    expected=sources()
    for name,item in expected.items():
        require(record['sourceManifest'][name]['originalSha256']==item['originalSha256'] and record['sourceManifest'][name]['generatedSha256']==ex.sha(item['raw']),'PREPARATION_SOURCE_DERIVATION')
    item=record['dll'];raw=ex.ordinary(ROOT/item['path']).read_bytes()
    require(ex.sha(raw)==item['sha256'] and len(raw)==item['sizeBytes'],'PREPARATION_RUNNER_OUTPUT')
    require(record['bindings']=={n:build.validate(n,resume.TASK) for n in record['bindings']},'PREPARATION_PRODUCT_BINDING')
    return record
