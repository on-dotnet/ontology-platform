"""用已执行编译命令的输入、流和保留的本机 DLL，重开两个限定恢复消费者。"""

import json
import re
from pathlib import Path

from workflow_execution import encoded, ordinary, sha

TASK = 'G4-ORACLE-MAPPING-QUERY-001'
BATCH = 's0-recovery-02'
BASE = '454d1a2f17581673cbbf44900a5fe241d603f5ef'
EXECUTED_ROOT = Path('/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform')
WORKFLOW = Path('artifacts/workflow') / TASK
BUILDS = WORKFLOW / BATCH
API = Path('backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0')
SDK = Path('/usr/local/share/dotnet')
CSC = SDK / 'sdk/10.0.402/Roslyn/bincore/csc.dll'
PACKS = ('Microsoft.NETCore.App.Ref', 'Microsoft.AspNetCore.App.Ref')
VERSIONS = ('10.0.402', '10.0.13')
# 该冻结工具链的目录次序、307 个引用名及其内容。验证命令输入仍逐项重算。
FRAMEWORK_CLOSURE = '1a917239d31a5dbc93ccbe552a579611f74f1ab66748e7be395a994bb89a024e'
CSC_SHA = 'b4240aecd35fedbae09710e3fdcebd491345eb141b6da1b240bb2b9c85badafd'
HOST_SHA = '11b517e7b00d0efa20e9b3ab6fe433f135d828a4c95c9c6ca7a9cf1328b6ada4'
KINDS = {'objects': ('workflow_oracle_mapping_object_recovery', 'ObjectRecovery.dll'),
         'identity': ('workflow_oracle_mapping_identity_recovery', 'RecoveryIdentity.dll')}
AUTH_ASSEMBLIES = ('OntologyPlatform.Api', 'Npgsql', 'Microsoft.AspNetCore.Authentication.OpenIdConnect',
                   'Microsoft.IdentityModel.Abstractions', 'Microsoft.IdentityModel.Logging',
                   'Microsoft.IdentityModel.Tokens', 'Microsoft.IdentityModel.Protocols',
                   'Microsoft.IdentityModel.Protocols.OpenIdConnect', 'Microsoft.IdentityModel.JsonWebTokens',
                   'System.IdentityModel.Tokens.Jwt')


def require(value, code):
    if not value:
        raise ValueError('RECOVERY_BUILD_' + code)


def digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def locations(build, kind, execution_root):
    root = Path(execution_root)
    require(root == EXECUTED_ROOT and kind in KINDS and build.get('kind') == kind, 'ROOT_OR_KIND')
    require(build.get('taskId') == TASK and build.get('runId') == BATCH and build.get('exitCode') == 0, 'RUN')
    name, dll = KINDS[kind]
    directory = Path(build['buildDir'])
    require(directory.parent == BUILDS and re.fullmatch('build-' + kind + '-[a-f0-9]{32}', directory.name)
            and build.get('dllName') == dll and re.fullmatch('[a-f0-9]{32}', build['commandId']), 'LOCATION')
    return root / directory, Path('scripts/maintenance') / (name + '.cs.txt'), name + '.cs', dll


def build_manifest(build, kind, executionRoot):
    """仅发布引用名称/散列与准确命令元数据；不读任何签名配置或备份私有材料。"""
    execution_root = Path(executionRoot)
    dest, source, snapshot, dll = locations(build, kind, execution_root)
    local_record = json.loads(ordinary(dest / 'receipt.json').read_bytes())
    require(build == local_record, 'LOCAL_BUILD_RECEIPT')
    binding_file = ordinary(execution_root / WORKFLOW / 'api-build-binding.json')
    binding_bytes = binding_file.read_bytes()
    api_binding = json.loads(binding_bytes)
    require(sha(binding_bytes) == build['apiBinding'] and api_binding['taskId'] == TASK
            and api_binding['target'] == 'api' and api_binding['exitCode'] == 0, 'LOCAL_API_BINDING')
    ready_files = list((execution_root / WORKFLOW / 'environment').glob('*/runs/*/receipt.json'))
    # 原编译器从既有 prepare receipt 读取环境；按原命令的环境摘要定位，包括重复的合格 prepare。
    raw_rc = ordinary(execution_root / WORKFLOW / 'commands' / BATCH / build['commandId'] / 'receipt.json')
    command = json.loads(raw_rc.read_bytes())
    environments = [json.loads(ordinary(f).read_bytes()) for f in ready_files]
    require(any(row.get('dotnet') == str(SDK / 'dotnet') and
                sha(encoded(row['environment'])) == command['environmentFingerprint'] for row in environments),
            'PREPARED_ENVIRONMENT')
    sdk_refs = []
    for pack in PACKS:
        for file in sorted((SDK / 'packs' / pack / VERSIONS[1] / 'ref/net10.0').glob('*.dll')):
            sdk_refs.append([file.relative_to(SDK).as_posix(), sha(file.read_bytes())])
    require(sha(encoded(sdk_refs)) == FRAMEWORK_CLOSURE and sha(CSC.read_bytes()) == CSC_SHA
            and sha((SDK / 'dotnet').read_bytes()) == HOST_SHA, 'SDK_CLOSURE')
    refs = []
    for name in AUTH_ASSEMBLIES if kind == 'identity' else ():
        rel = (API / (name + '.dll')).as_posix()
        actual = sha(ordinary(execution_root / rel).read_bytes())
        require(api_binding['outputs'].get(rel) == actual, 'AUTH_REFERENCE')
        refs.append([rel, actual])
    source_bytes = ordinary(execution_root / source).read_bytes()
    require(sha(source_bytes) == build['sourceSha256'] and source_bytes == ordinary(dest / snapshot).read_bytes(),
            'COMPILER_SOURCE_SNAPSHOT')
    output = ordinary(dest / dll)
    require(output.is_file() and sha(output.read_bytes()) == build['dllSha256'], 'LOCAL_DLL')
    return dict(schemaVersion=1, kind=kind, taskId=TASK, runId=BATCH, base=BASE, executionRoot=str(execution_root),
                commandId=build['commandId'], buildDir=build['buildDir'], schema='retained-compiler-inputs',
                sourceSha256=sha(source_bytes), sdkVersion=VERSIONS[0], frameworkVersion=VERSIONS[1],
                compilerSha256=CSC_SHA, dotnetSha256=HOST_SHA, sdkRefs=sdk_refs, apiRefs=refs,
                apiOutputs=api_binding['outputs'], apiBindingSha256=sha(binding_bytes),
                apiBuildLogSha256=api_binding['logSha256'], apiInputKey=api_binding['inputKey'],
                environmentFingerprint=command['environmentFingerprint'], outputBytes=output.stat().st_size,
                outputSha256=build['dllSha256'])


def validate(build, kind, *, root, executed_root, frozen, command_bytes, manifest, binary=None):
    """Git 重开源码、清单与双流；本机按准确 buildDir 取 DLL。缺少该原件时拒绝完整资格。"""
    root, executed_root = Path(root), Path(executed_root)
    dest, source, snapshot, dll = locations(build, kind, executed_root)
    schema = dict(schemaVersion=1, kind=kind, taskId=TASK, runId=BATCH, base=BASE, executionRoot=str(executed_root),
                  commandId=build['commandId'], buildDir=build['buildDir'], schema='retained-compiler-inputs',
                  sdkVersion=VERSIONS[0], frameworkVersion=VERSIONS[1], compilerSha256=CSC_SHA, dotnetSha256=HOST_SHA)
    require(all(manifest.get(k) == v for k,v in schema.items()), 'MANIFEST_IDENTITY')
    source_sha = sha(ordinary(root / source).read_bytes())
    require(manifest['sourceSha256'] == source_sha == build['sourceSha256'], 'SOURCE_INPUT')
    baseline = [b for b in frozen('recovery-cli-binding.json')['testedBuilds'] if b['target']=='api' and b['exitCode']==0]
    require(len(baseline)==1, 'API_BASELINE')
    previous = baseline[0]
    api_outputs = manifest['apiOutputs']
    # 上批测量的 output 是编译日志散列。各产物散列由单独冻结的 API 绑定原件登记。
    require(build['apiSource'] == previous['head'] and manifest['apiBindingSha256'] == build['apiBinding'] == previous['binding']
            and manifest['apiBuildLogSha256'] == build['apiOutput'] == previous['output']
            and manifest['apiInputKey'] == previous['inputKey'], 'API_OUTPUTS')
    framework = manifest['sdkRefs']
    require(isinstance(framework,list) and len(framework)==307 and sha(encoded(framework)) == FRAMEWORK_CLOSURE, 'FRAMEWORK_REFS')
    api_refs = [[str(API / (name + '.dll')), api_outputs[str(API / (name + '.dll'))]]
                for name in (AUTH_ASSEMBLIES if kind=='identity' else ())]
    require(manifest['apiRefs'] == api_refs, 'API_REFS')
    refs = [(SDK / p, h) for p,h in framework] + [(executed_root / p, h) for p,h in api_refs]
    argv = ['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',str(SDK / 'dotnet'),str(CSC),
            '-nologo','-target:exe','-nostdlib+','-nullable:enable','-out:'+str(dest / dll),
            *['-r:'+str(p) for p,h in refs],str(dest / snapshot)]
    argv_sha = sha(encoded(argv))
    fp = sha(encoded(dict(source=source_sha, refs=[h for _,h in refs], compiler=CSC_SHA)))
    cmd = json.loads(command_bytes(build['commandId'], 'receipt.json'))
    env_key = manifest['environmentFingerprint']
    identity = sha(encoded([fp, env_key, argv_sha, str(executed_root), 50,
                            sha(ordinary(root / 'scripts/maintenance/workflow_execution.py').read_bytes())]))
    require(cmd['schemaVersion']==2 and cmd['taskId']==TASK and cmd['runId']==BATCH and cmd['commandId']==build['commandId']
            and cmd['stage']=='compile-'+kind and cmd['cwd']==str(executed_root) and cmd['deadlineSeconds']==50
            and cmd['started'] is True and cmd['exitCode']==0 and cmd['signal'] is None and cmd['classification']=='SUCCESS'
            and cmd['commandSummary']==dict(executable='sandbox-exec',argumentCount=len(argv)-1,sha256=argv_sha)
            and fp==build['inputFingerprint']==cmd['inputFingerprint'] and digest(env_key)
            and cmd['environmentFingerprint']==env_key and cmd['identity']==identity, 'ACTUAL_COMPILER_COMMAND')
    for name in ('stdout','stderr'):
        stream = command_bytes(build['commandId'], name+'.txt')
        require(cmd[name]['sizeBytes']==len(stream) and cmd[name]['sha256']==sha(stream), 'COMPILER_STREAMS')
    require((dest / dll).is_file(), 'LOCAL_DLL_NOT_AVAILABLE')
    path = ordinary(dest / dll)
    observed = path.read_bytes()
    if binary is not None:
        require(binary == observed if isinstance(binary, bytes) else Path(binary) == path, 'BINARY_SOURCE')
    require(len(observed)==manifest['outputBytes'] and sha(observed)==manifest['outputSha256']==build['dllSha256'], 'RETAINED_OUTPUT')
    # 同机或可读取原实测工作树时，只通过原目录验证对应的小编译回执与源快照。
    require(json.loads(ordinary(dest/'receipt.json').read_bytes())==build and sha(ordinary(dest/snapshot).read_bytes())==source_sha,
            'RETAINED_BUILD_INPUT')
    require(manifest == build_manifest(build, kind, executed_root), 'LOCAL_MANIFEST')
    return dict(status='RETAINED_DRIVER_QUALIFIED',commandId=cmd['commandId'],inputFingerprint=fp,
                sourceSha256=source_sha,outputSha256=sha(observed),outputBytes=len(observed),
                manifestSha256=sha(encoded(manifest)),binaryEvidence='LOCAL_RETAINED_BUILD_OUTPUT')
