#!/usr/bin/env python3
"""实际API DLL独立子进程的环境拒绝路径；不以其他配置异常代替G4拒绝。"""
import json
from pathlib import Path
import subprocess
import tempfile
import runtime as rt


def rejection_cases(m):
    """Production/Staging启用优先级都必须命中准确环境限制。"""
    dll = rt.ROOT / 'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll'
    rt.require(dll.is_file(), 'API_BUILD_REQUIRED')
    rt.prepare(m)
    runtime=rt.runtime_value(m)
    private=rt.private_dir(m['runId'])
    (private/'host-keyring').mkdir(mode=0o700)
    results = []
    for environment in ('Production', 'Staging'):
        for override in ('environment', 'command-line'):
            with tempfile.TemporaryDirectory(dir=private) as d:
                p = Path(d)
                rt.write_json(p/'appsettings.json',{'AllowedHosts':'localhost',
                    'ConnectionStrings':{'governance':'Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()},
                    'Security':{'Authority':'https://localhost:15180/realms/synthetic','ClientId':'synthetic','ClientSecret':(private/'keycloak-password').read_text(),
                        'PublicOrigin':'https://localhost:15100','KeyRingPath':str(private/'host-keyring'),'CertificatePath':runtime['certificatePath'],
                        'CertificatePassword':runtime['certificatePassword'],'HealthKey':runtime['healthKey']},
                    'Web':{'Origin':'http://127.0.0.1:15300'},'G4':{'Enabled':False},'Governance':{'ApplyMigrations':False}},private=True)
                env = rt.environment(m['runId'])
                env.update(ASPNETCORE_ENVIRONMENT=environment, DOTNET_ENVIRONMENT=environment, G4__Enabled='true' if override == 'environment' else 'false')
                args = ['/usr/local/share/dotnet/dotnet', str(dll), '--contentRoot', str(p)]
                if override == 'command-line': args += ['--G4:Enabled=true']
                raw,code,timed=rt.bounded_process(args,cwd=p,env=env,timeout=30)
                log=private/'logs'/('startup-'+environment+'-'+override+'.log')
                with open(log,'xb') as stream:
                    __import__('os').chmod(log,0o600);stream.write(raw)
                row = dict(environment=environment,override=override,exitCode=code,timedOut=timed,logSha256=rt.digest(raw),exactG4Rejection=not timed and code!=0 and 'M1只允许隔离开发环境。'.encode() in raw)
                rt.require(row['exactG4Rejection'],'ACCURATE_G4_REJECTION_REQUIRED')
                rt.write_json(rt.ARTIFACTS/m['runId']/('startup-'+environment+'-'+override+'.json'), row)
                results.append(row)
    return {'status': 'PASS_REJECTION_PATHS_ONLY', 'cases': results, 'developmentAndDisabled': 'PENDING_REAL_RUNTIME'}


GRAPH_PROBE = r'''using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OntologyPlatform.Api;
using OntologyPlatform.Modules.Connections;
/// <summary>只读取正式Host真实服务图、路由和选项；不运行后台服务或发起数据库连接。</summary>
public static class GraphProbe {
    /// <summary>使用本任务有效私有配置构造同一正式Host，逐例验证开关与缺省。</summary>
    public static void Main(string[] args) {
        var cases = new List<object>();
        foreach (var enabled in new[] {false,true}) foreach (bool? allow in new bool?[]{null,false,true}) {
            // 每例独立DI容器，防止单例选项缓存串扰。
            var app=PlatformApiHost.CreateApplication(new[]{"--contentRoot",args[0]},builder=>{
                builder.Environment.EnvironmentName="Development";
                var values=new Dictionary<string,string?>{{"G4:Enabled",enabled.ToString()},{"G4:ApplyMigrations","false"}};
                if(allow.HasValue)values["G4:AllowEmptyPublicSchema"]=allow.Value.ToString();
                builder.Configuration.AddInMemoryCollection(values);
            });
            try {
                // 读取生产DI中的真实服务与真实EndpointDataSource，不使用模拟handler。
                var worker=app.Services.GetServices<IHostedService>().Any(x=>x.GetType().Name=="CatalogWorker");
                var options=app.Services.GetService<PgAdapterOptions>();
                var routes=((IEndpointRouteBuilder)app).DataSources.SelectMany(x=>x.Endpoints).OfType<RouteEndpoint>().Any(x=>x.RoutePattern.RawText?.Contains("/connections")==true);
                if(worker!=enabled || (options!=null)!=enabled || routes!=enabled)throw new Exception("G4_GRAPH_BOUNDARY");
                if(enabled && !(options!.AllowedSchemas.SequenceEqual(allow==true?new[]{"production","public"}:new[]{"production"})))throw new Exception("G4_PUBLIC_DEFAULT_OR_OVERRIDE");
                cases.Add(new{enabled,allowEmptyPublicSchema=allow,workerRegistered=worker,adapterRegistered=options!=null,routesRegistered=routes,allowedSchemas=options?.AllowedSchemas,status="PASS"});
            } finally {app.DisposeAsync().AsTask().GetAwaiter().GetResult();}
        }
        Console.WriteLine(JsonSerializer.Serialize(cases));
    }
}
'''


def graph_cases(m):
    """编译临时无依赖工具；引用且逐字节核对I01已绑定正式API及SDK reference packs。"""
    import os
    import shutil
    rt.check_build(m)
    api=rt.ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0'
    output=rt.ARTIFACTS/m['runId']/'host-graph-tool'
    rt.require(not output.exists(),'EXISTING_GRAPH_TOOL')
    shutil.copytree(api,output)
    copied={str(p.relative_to(api)):rt.digest(p.read_bytes()) for p in api.rglob('*') if p.is_file()}
    rt.require(all(rt.digest((output/name).read_bytes())==sha for name,sha in copied.items()),'GRAPH_COPY_DRIFT')
    source=output/'GraphProbe.cs';source.write_text(GRAPH_PROBE)
    references={p.name:p for p in output.glob('*.dll')}
    for pack in ('Microsoft.NETCore.App.Ref','Microsoft.AspNetCore.App.Ref'):
        directory=Path('/usr/local/share/dotnet/packs')/pack/'10.0.13/ref/net10.0'
        rt.require(directory.is_dir(),'EXACT_REFERENCE_PACK_MISSING')
        references.update({p.name:p for p in directory.glob('*.dll')})
    response=output/'compile.rsp'
    response.write_text('\n'.join(['-noconfig','-nostdlib+','-nullable:enable','-target:exe','-out:'+str(output/'GraphProbe.dll'),*['-r:'+str(p) for p in references.values()],str(source)])+'\n')
    rt.execute(m,'compile-host-graph',['/usr/local/share/dotnet/dotnet','/usr/local/share/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll','@'+str(response)])
    private=rt.private_dir(m['runId']);r=rt.runtime_value(m)
    config=private/'graph-config';config.mkdir(mode=0o700)
    rt.write_json(config/'appsettings.json',{'ConnectionStrings':{'governance':'Host=127.0.0.1;Port=15432;Database=platform;Username=platform;Password='+(private/'platform-password').read_text()},
        'Security':{'Authority':'http://localhost:15180/realms/g2-synthetic','ClientId':'synthetic','ClientSecret':(private/'keycloak-password').read_text(),'PublicOrigin':'http://localhost:15100','KeyRingPath':str(private/'host-keyring'),'CertificatePath':r['certificatePath'],'CertificatePassword':r['certificatePassword'],'HealthKey':r['healthKey']},
        'Web':{'Origin':'http://127.0.0.1:15300'},'G4':{'KeyFile':str(private/'api/g4-key'),'SourceCaPath':str(private/'api/ca.crt')},'Governance':{'ApplyMigrations':False}},private=True)
    raw=rt.execute(m,'actual-host-graph',['/usr/local/share/dotnet/dotnet','exec','--runtimeconfig',str(output/'OntologyPlatform.Api.runtimeconfig.json'),'--depsfile',str(output/'OntologyPlatform.Api.deps.json'),str(output/'GraphProbe.dll'),str(config)],sensitive=True)
    rows=json.loads(raw.decode().splitlines()[-1]);rt.require(len(rows)==6 and all(x['status']=='PASS' for x in rows),'HOST_GRAPH_CASES')
    rt.write_json(rt.ARTIFACTS/m['runId']/'host-graph.json',{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'generatedSourceSha256':rt.digest(source.read_bytes()),'responseFileSha256':rt.digest(response.read_bytes()),'toolDllSha256':rt.digest((output/'GraphProbe.dll').read_bytes()),'copiedApiInputs':copied,'referenceInputs':{str(p):rt.digest(p.read_bytes()) for p in references.values()},'cases':rows})
    return rows
