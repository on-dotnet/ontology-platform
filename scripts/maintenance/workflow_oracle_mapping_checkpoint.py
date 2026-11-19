"""对本任务封闭的 PG、IdP、TDB2、对象、密钥和 Oracle 记录当前检查点；资源准入与调度仍属现有 recovery。"""
import json
import re
from pathlib import Path

import workflow_execution as ex
from workflow_oracle_mapping_platform import IMAGES
from workflow_oracle_mapping_resources import TASK, RUN, require

ROOT = Path(__file__).resolve().parents[2]
QUERY = 'query-18b5ee00b53e4e4eafc43cc4717bd293'
CONNECTION = 'a7913bb552eb4cd1a3f6eaf5b93cd619'
CID = re.compile('[0-9a-f]{64}')
SAFE_ID = re.compile('[A-Za-z0-9._:-]{1,160}')
SCHEMAS = ('agents', 'connections', 'governance', 'ontology', 'publishing', 'semantic_query')
CHECKPOINT_TABLES = {'connections.Connections', 'connections.CatalogSnapshots', 'connections.MappingReleases',
                     'connections.MappingActives', 'governance.MappingAuthorizationGrants', 'governance.audit_records',
                     'governance.server_sessions', 'publishing.Releases', 'publishing.ActiveReleases', 'semantic_query.Queries'}


def pg_sql(fixture, recovery_id):
    """PG 内逐行计算稳定投影，公开流中从来没有票据、密文、原语句或私有字段。"""
    current = fixture['mappingReceipt']
    release = fixture['ontologyRelease']['manifest']
    ident = {k: v for k, v in dict(reader=fixture['subjects']['reader'], asset=release['assetId'], release=release['releaseId'],
              mapping=current['mappingId'], active=current['activationId'], version=current['mappingReleaseId'],
              snapshot=fixture['catalog']['snapshotId'], recovery=recovery_id).items() if isinstance(v,str) and SAFE_ID.fullmatch(v)}
    require(len(ident)==8 and fixture['connectionId']==CONNECTION and fixture['scope']=={'siteIds':['site-a'],'organizationId':'org-demo'}
            and fixture['taskId']==TASK and fixture['runId']==RUN, 'CHECKPOINT_INPUT')
    schemas=','.join("'"+name+"'" for name in SCHEMAS)
    return rf"""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone TO 'UTC';
SET LOCAL statement_timeout TO '8s';
SELECT format('SELECT json_build_object(''kind'',''table'',''name'',%L,''count'',count(*),''sha256'',encode(sha256(convert_to(coalesce(string_agg(h,'''' ORDER BY h COLLATE "C"),''''),''UTF8'')),''hex'')) FROM (SELECT encode(sha256(convert_to(to_jsonb(r)::text,''UTF8'')),''hex'') h FROM %I.%I r) s',
 n.nspname||'.'||c.relname,n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE c.relkind IN ('r','p') AND n.nspname IN ({schemas}) ORDER BY n.nspname,c.relname
\gexec
SELECT json_build_object('kind','server','database',current_database(),'user',current_user,'readonly',current_setting('transaction_read_only'));
SELECT json_build_object('kind','release','id',r."ReleaseId",'asset',r."AssetId",'active',a."ReleaseId",'revision',a."Revision",
 'manifestHash',r."ManifestHash",'actualManifestHash',encode(sha256(convert_to(r."ManifestJson",'UTF8')),'hex'),
 'manifestObject',r."ManifestObjectJson"::jsonb,'objects',r."ManifestJson"::jsonb->'ArtifactObjects',
 'ontologyGraph',r."ManifestJson"::jsonb->>'OntologyGraphIri','dataGraph',r."ManifestJson"::jsonb->>'DataGraphIri')
 FROM publishing."Releases" r JOIN publishing."ActiveReleases" a ON a."AssetId"=r."AssetId"
 WHERE r."AssetId"='{ident['asset']}' AND r."ReleaseId"='{ident['release']}' AND r."OrganizationId"='org-demo';
SELECT json_build_object('kind','mapping','id',a."MappingId",'active',a."ActivationId",'version',a."ReleaseId",'revision',a."ActivationRevision",
 'hash',r."ContentHash",'actualHash',encode(sha256(r."CanonicalBytes"),'hex'),'source',binding->>'sourceConnectionId',
 'catalog',binding->>'sourceCatalogSnapshotId','ontology',binding->>'ontologyReleaseId','type',binding->>'sourceType')
 FROM connections."MappingActives" a JOIN connections."MappingReleases" r ON r."Id"=a."ReleaseId" AND r."MappingId"=a."MappingId"
 CROSS JOIN LATERAL (SELECT convert_from(r."CanonicalBytes",'UTF8')::jsonb->'binding' AS binding) b
 WHERE a."MappingId"='{ident['mapping']}' AND a."ActivationId"='{ident['active']}' AND a."ReleaseId"='{ident['version']}';
SELECT json_build_object('kind','catalog','snapshot',"Id",'connection',"ConnectionId",'schema',"ViewJson"::jsonb->>'schemaFingerprint')
 FROM connections."CatalogSnapshots" WHERE "Id"='{ident['snapshot']}' AND "ConnectionId"='{CONNECTION}';
SELECT json_build_object('kind','permission','permission',"Permission",'fields',cardinality("FieldRefs"),'site',"SiteIds",'org',"OrganizationId")
 FROM governance."MappingAuthorizationGrants" WHERE "ConnectionId"='{CONNECTION}' AND "SubjectId"='{ident['reader']}' AND "RevokedAtUtc" IS NULL
 AND "Permission" IN ('data.query.execute','data.query.result.read','data.query.evidence.read') ORDER BY "Permission";
SELECT json_build_object('kind','hold','state',q."ExecutionStatus",'cancel',q."CancelRequested",'fence',q."Fence",
 'released',q."LeaseOwner" IS NULL AND q."LeaseUntilUtc" IS NULL,'bytes',octet_length(q."ResultCiphertext"),'hash',q."ResultHash",
 'receipts',jsonb_array_length(convert_from(q."BindingBytes",'UTF8')::jsonb->'receipts'),
 'cancelAudit',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.cancel' AND "Outcome"='allowed' AND "Resource"=q."Id"),
 'recoverAudit',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.cleanup.recover' AND "Outcome"='allowed' AND "Resource"=q."Id"),
 'operationAudit',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.cleanup.recover' AND "Resource"=q."Id" AND "CorrelationId"='{ident['recovery']}'),
 'success',(SELECT count(*) FROM governance.audit_records WHERE "Action"='data.query.execute' AND "Outcome"='allowed' AND "Resource"=q."Id"))
 FROM semantic_query."Queries" q WHERE "Id"='{QUERY}' AND "SubjectId"='{ident['reader']}' AND "OrganizationId"='org-demo';
COMMIT;
""".encode()


def collect_pg(pg_id, fixture, recovery_id, attempt):
    """Master 已准入原/替代阶段后调用；另外复核容器实例及镜像，在同一只读快照冻结行与交叉引用。"""
    require(CID.fullmatch(pg_id) and SAFE_ID.fullmatch(attempt), 'CHECKPOINT_PG_ID')
    def run(stage, args, input_bytes=None):
        args=['docker','--context','desktop-linux',*args]
        result=ex.run(args, ROOT, task=TASK, run_id=RUN, stage='omq-recovery-checkpoint-'+stage,
                      input_key=ex.sha(ex.encoded([pg_id,attempt,args,ex.sha(input_bytes or b''),ex.sha(Path(__file__).read_bytes())])),
                      stdin=input_bytes, timeout=35)
        require(result.returncode==0,'CHECKPOINT_PG_'+stage+'_'+result.receipt['commandId'])
        return result.stdout,result.receipt['commandId']
    observation,identity=run('identity',['inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.State.Status}}',pg_id])
    require(observation.decode().strip()=='|'.join((pg_id,IMAGES['platform-pg'],TASK,RUN,'running')),'CHECKPOINT_PG_OWNER')
    stdout,command=run('rows',['exec','-i','--user','postgres',pg_id,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1'],
                       pg_sql(fixture,recovery_id))
    rows=[json.loads(line) for line in stdout.splitlines() if line.strip()]
    def one(kind):
        matches=[r for r in rows if r['kind']==kind]
        require(len(matches)==1,'CHECKPOINT_PG_'+kind)
        return matches[0]
    tables={r['name']:dict(count=r['count'],sha256=r['sha256']) for r in rows if r['kind']=='table'}
    require(CHECKPOINT_TABLES<=set(tables) and all(CID.fullmatch(r['sha256']) and type(r['count']) is int and r['count']>=0 for r in tables.values()),
            'CHECKPOINT_PG_TABLES')
    require(one('server')==dict(kind='server',database='mapping',user='postgres',readonly='on'),'CHECKPOINT_PG_DATABASE')
    require(one('hold')==dict(kind='hold',state='CANCELLED',cancel=True,fence=2,released=True,bytes=0,hash=None,receipts=0,
                              cancelAudit=1,recoverAudit=1,operationAudit=1,success=0),'CHECKPOINT_PG_RECOVERY')
    r=one('release');m=one('mapping');c=one('catalog');f=fixture['ontologyRelease'];mr=fixture['mappingReceipt']
    require(r['id']==r['active']==f['manifest']['releaseId'] and r['manifestHash']==r['actualManifestHash']==f['manifestHash']
            and r['revision']==f['activationRevision'] and r['ontologyGraph']==f['manifest']['ontologyGraphIri']
            and r['dataGraph']==f['manifest']['dataGraphIri'],'CHECKPOINT_PG_RELEASE')
    require(m['hash']==m['actualHash']==mr['manifestHash'] and m['version']==mr['mappingReleaseId'] and m['revision']==mr['activationRevision']
            and m['source']==c['connection']==CONNECTION and m['catalog']==c['snapshot']==fixture['catalog']['snapshotId']
            and c['schema']==fixture['catalog']['schemaFingerprint'] and m['ontology']==r['id'] and m['type']=='ORACLE','CHECKPOINT_PG_ACTIVATION')
    perms=[r for r in rows if r['kind']=='permission']
    require(len(perms)==3 and {p['permission'] for p in perms}=={'data.query.execute','data.query.result.read','data.query.evidence.read'}
            and all(p['fields']==11 and p['site']==['site-a'] and p['org']=='org-demo' for p in perms),'CHECKPOINT_PG_GRANTS')
    objects=[{k[0].lower()+k[1:]:v for k,v in obj.items()} for obj in r['objects']]
    manifest={k[0].lower()+k[1:]:v for k,v in r['manifestObject'].items()}
    require(objects==f['manifest']['artifactObjects'] and manifest['hash']==r['manifestHash'] and all(
        CID.fullmatch(obj['hash']) and re.fullmatch(r'releases/[A-Za-z0-9-]+/[a-z0-9.-]+',obj['objectKey'])
        and 0<obj['sizeBytes']<=4*1024*1024 for obj in [*objects,manifest]),'CHECKPOINT_PG_OBJECTS')
    stable=dict(tables=tables,hold=one('hold'),catalog=c,mapping=m,permissions=perms,releaseId=r['id'],graphs=[r['ontologyGraph'],r['dataGraph']],
                objects=[*objects,manifest],shapesHash=f['manifest']['hashes']['shapesHash'])
    return dict(taskId=TASK,runId=RUN,attempt=attempt,containerId=pg_id,identityCommandId=identity,commandId=command,stable=stable,
                stableSha256=ex.sha(ex.encoded(stable)))


def verifier_inputs(fixture, pg, baseline):
    """只给验证器准确公开 ID、源基线与当前 PG 的图/对象引用。凭证在容器只读挂载内消费。"""
    stable=pg['stable']
    require(pg['taskId']==TASK and pg['runId']==RUN and pg['stableSha256']==ex.sha(ex.encoded(stable))
            and fixture['connectionId']==CONNECTION and set(fixture['subjects'])=={'reader','operator','auditor','activator'}
            and len(set(fixture['subjects'].values()))==4 and len(baseline)==2 and all(CID.fullmatch(h) for h in baseline),
            'CHECKPOINT_VERIFIER_INPUT')
    return dict(taskId=TASK,runId=RUN,connectionId=CONNECTION,reader=fixture['subjects']['reader'],subjects=fixture['subjects'],
                bucket='g4-oracle-mapping-synthetic',releaseId=stable['releaseId'],graphs=stable['graphs'],objects=stable['objects'],
                shapesHash=stable['shapesHash'],sourceRowHashes=baseline)


def verifier_source():
    """供 recovery 现有零下载 Roslyn/同快照依赖入口编译；载荷没有服务监听或业务 worker。"""
    return VERIFIER_PREAMBLE + STORAGE + SOURCE_KEYS + IDENTITY + VERIFIER_MAIN


VERIFIER_PREAMBLE = r'''
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Configuration;
using OntologyPlatform.Modules.Publishing;
using Npgsql;
using Oracle.ManagedDataAccess.Client;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Modules.SemanticQuery;

/// <summary>仅观测已经封闭的当前任务原栈或替代栈。所有认证材料留在进程私有内存。</summary>
internal static class Checkpoint
{
    private static readonly CancellationTokenSource Budget = new(TimeSpan.FromSeconds(100));
    private static CancellationToken Token => Budget.Token;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static string component = "input";
    private static JsonElement input;
    private static readonly Dictionary<string, object> stable = new();
    private static readonly Dictionary<string, object> proof = new();
    private static readonly HttpClient http = NewClient();
    private static readonly List<(string Kid, string Subject, long Issued, long Expiry, byte[] Digest, byte[] Signature)> witnesses = new();
    private static readonly IConfiguration Config=new ConfigurationBuilder().AddJsonFile("/private/api/appsettings.json",false,false).Build();
    private const string IssuerOrigin = "http://localhost:15743";
    private const string Rust = "http://rustfs:9000";
    private const string Fuseki = "http://fuseki:3030";
    private static string Str(JsonElement n, string k) => n.GetProperty(k).GetString()!;
    private static JsonElement Parse(byte[] data) => JsonSerializer.Deserialize<JsonElement>(data);
    private static string Sha(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    private static string TextHash(string s) => Sha(Encoding.UTF8.GetBytes(s));
    private static void Must(bool yes, string code) { if (!yes) throw new InvalidDataException(code); }
    private static string Escape(string s) => Uri.EscapeDataString(s);
    private static string Query(IDictionary<string,string> values) => string.Join("&",values.OrderBy(p=>Escape(p.Key),StringComparer.Ordinal).Select(p=>Escape(p.Key)+"="+Escape(p.Value)));
    private static HttpClient NewClient()
    {
        var handler=new SocketsHttpHandler{AllowAutoRedirect=false,UseProxy=false,UseCookies=true,ConnectTimeout=TimeSpan.FromSeconds(4)};
        handler.ConnectCallback=async (ctx,cancel)=>{
            var ep=ctx.DnsEndPoint;
            // 保留真实 issuer/Host 与 Cookie 源，TCP 始终只走当前阶段的隔离网。
            var target=(ep.Host,ep.Port) switch { ("localhost",15743)=>("127.0.0.1",15743),("fuseki",3030)=>("fuseki",3030),
                ("127.0.0.1",15746)=>("127.0.0.1",15746),_=>throw new InvalidDataException("http_target") };
            var socket=new Socket(SocketType.Stream,ProtocolType.Tcp);
            try { await socket.ConnectAsync(target.Item1,target.Item2,cancel);return new NetworkStream(socket,true); }
            catch { socket.Dispose();throw; }
        };
        return new HttpClient(handler){Timeout=TimeSpan.FromSeconds(6)};
    }
    private static async Task<(byte[] Body,HttpStatusCode Code,Uri? Location,string? Version)> Fetch(
        string url,HttpMethod? method=null,HttpContent? data=null,Dictionary<string,string>? headers=null,int limit=4*1024*1024)
    {
        using var req=new HttpRequestMessage(method??HttpMethod.Get,url){Content=data};
        if(headers!=null)foreach(var h in headers)req.Headers.TryAddWithoutValidation(h.Key,h.Value);
        using var res=await http.SendAsync(req,HttpCompletionOption.ResponseHeadersRead,Token);
        Must((int)res.StatusCode is >=200 and <400,"http_status_"+(int)res.StatusCode);
        await using var raw=await res.Content.ReadAsStreamAsync(Token);
        using var output=new MemoryStream();
        byte[] buf=new byte[16384];int n;
        while((n=await raw.ReadAsync(buf,Token))>0){Must(output.Length+n<=limit,"response_limit");output.Write(buf,0,n);}
        return(output.ToArray(),res.StatusCode,res.Headers.Location,res.Headers.TryGetValues("x-amz-version-id",out var ids)?ids.Single():null);
    }
'''

STORAGE = r'''
    private sealed class PublishingClient : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => name=="publishing-s3"?http:throw new InvalidDataException("publishing_client");
    }
    private static async Task PublishedObjects()
    {
        // 交由正式 RustFS 客户端签名，验证器不读签名口令。由已登记的固定回环 relay 接入当前专网。
        Must(Config["Publishing:Bucket"]==Str(input,"bucket")&&Config["Publishing:S3Endpoint"]=="http://127.0.0.1:15746","publishing_root");
        var store=new RustfsArtifactStore(new PublishingClient(),Config,TimeProvider.System);
        var objects=input.GetProperty("objects").EnumerateArray().ToArray();
        var rows=new List<object>();
        foreach(var element in objects){
            var obj=element.Deserialize<ArtifactObject>(Json)!;
            var data=await store.ReadVerifiedAsync(obj,Token);
            Must(data.LongLength==obj.SizeBytes&&Sha(data)==obj.Hash,"published_bytes");
            rows.Add(new{key=obj.ObjectKey,bytes=data.Length,sha256=obj.Hash});
        }
        Must(objects.Length>=4&&Str(objects[1],"hash")==Str(input,"shapesHash"),"shacl_bytes");
        stable["rustfs"]=new{bucket=Str(input,"bucket"),publishedObjects=rows,shapesSha256=Str(input,"shapesHash")};
    }
    private static async Task Graphs()
    {
        const string query="SELECT ?g ?s ?p ?o WHERE { { GRAPH ?g { ?s ?p ?o } } UNION { ?s ?p ?o } }";
        var raw=await Fetch(Fuseki+"/ontology/query?query="+Escape(query),headers:new(){{"Accept","application/sparql-results+json"}},limit:8*1024*1024);
        var rows=Parse(raw.Body).GetProperty("results").GetProperty("bindings").EnumerateArray().ToArray();
        var graphs=new SortedDictionary<string,List<string>>(StringComparer.Ordinal){{"",new()}};
        string Term(JsonElement term)=>JsonSerializer.Serialize(term.EnumerateObject().OrderBy(x=>x.Name,StringComparer.Ordinal)
            .Select(x=>new[]{x.Name,x.Value.GetString()!}).ToArray());
        foreach(var row in rows)
        {
            var g=row.TryGetProperty("g",out var graph)?Str(graph,"value"):"";
            if(!graphs.TryGetValue(g,out var values))graphs.Add(g,values=new());
            values.Add(string.Join("\n",new[]{"s","p","o"}.Select(k=>Term(row.GetProperty(k)))));
        }
        foreach(var graph in input.GetProperty("graphs").EnumerateArray())Must(graphs.TryGetValue(graph.GetString()!,out var v)&&v.Count>0,"release_graph");
        stable["tdb2"]=graphs.Select(x=>new{graph=x.Key,triples=x.Value.Count,sha256=TextHash(JsonSerializer.Serialize(x.Value.Order(StringComparer.Ordinal).ToArray()))}).ToArray();
    }
'''

SOURCE_KEYS = r'''
    private static async Task<string> Keys()
    {
        var cb=new NpgsqlConnectionStringBuilder(Config.GetConnectionString("governance"));
        Must(cb.Host=="platform-pg" && cb.Database=="mapping" && cb.Port==5432 && cb.SslMode==SslMode.VerifyFull,"pg_route");
        cb.Pooling=false;cb.CommandTimeout=5;cb.ApplicationName="omq-checkpoint-readonly";
        await using var db=new NpgsqlConnection(cb.ConnectionString);
        await db.OpenAsync(Token);
        await using var tx=await db.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead,Token);
        await using(var cmd=new NpgsqlCommand("SET TRANSACTION READ ONLY",db,tx))await cmd.ExecuteNonQueryAsync(Token);
        using var cert=X509CertificateLoader.LoadPkcs12FromFile("/private/api/keyring.pfx",Config["Security:CertificatePassword"],X509KeyStorageFlags.EphemeralKeySet);
        Must(cert.HasPrivateKey,"pfx");
        var bff=DataProtectionProvider.Create(new DirectoryInfo("/keyring"),s=>s.SetApplicationName("OntologyPlatform.PlatformBff.v1")
                .DisableAutomaticKeyGeneration().UnprotectKeysWithAnyCertificate(cert));
        var query=DataProtectionProvider.Create(new DirectoryInfo("/query-keyring"),s=>s.SetApplicationName("OntologyPlatform.G4-M4-QUERY-001").DisableAutomaticKeyGeneration());
        var expected=input.GetProperty("subjects").EnumerateObject().Select(x=>x.Value.GetString()!).ToHashSet();
        var observed=new HashSet<string>();int tickets=0;
        await using(var cmd=new NpgsqlCommand("SELECT \"ProtectedTicket\" FROM governance.server_sessions ORDER BY \"Id\" LIMIT 1001",db,tx))
        await using(var reader=await cmd.ExecuteReaderAsync(Token)){
            while(await reader.ReadAsync(Token)){
                Must(++tickets<=1000,"ticket_limit");
                var bytes=reader.GetFieldValue<byte[]>(0);
                var ticket=TicketSerializer.Default.Deserialize(bff.CreateProtector("OntologyPlatform.Governance.ServerTicket.v1").Unprotect(bytes));
                Must(ticket!=null,"ticket");
                var subject=ticket!.Principal.FindFirst("sub")?.Value ?? ticket.Principal.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value;
                Must(!string.IsNullOrEmpty(subject),"ticket_sub");observed.Add(subject!);
                if(expected.Contains(subject!)){
                    var original=ticket.Properties.GetTokenValue("id_token");
                    if(original!=null)CaptureSignature(original,subject!);
                }
            }
        }
        Must(expected.All(observed.Contains),"ticket_subjects");
        var results=new SortedDictionary<string,string>(StringComparer.Ordinal);
        await using(var cmd=new NpgsqlCommand("SELECT \"Id\",\"ResultHash\",\"ResultCiphertext\" FROM semantic_query.\"Queries\" WHERE octet_length(\"ResultCiphertext\")>0 ORDER BY \"Id\" LIMIT 101",db,tx))
        await using(var reader=await cmd.ExecuteReaderAsync(Token)){
            while(await reader.ReadAsync(Token)){
                var id=reader.GetString(0);var hash=reader.GetString(1);var plain=G4QueryResultStore.Unprotect(query,id,reader.GetFieldValue<byte[]>(2),hash);
                Must(Sha(plain)==hash&&results.Count<100,"query_result");results.Add(id,hash);CryptographicOperations.ZeroMemory(plain);
            }
        }
        Must(results.Count>0,"original_query_result");
        var sql="SELECT to_jsonb(s)::text FROM connections.\"ConnectionSecrets\" s JOIN connections.\"Connections\" c ON c.\"SecretId\"=s.\"Id\" AND c.\"SecretVersion\"=s.\"Version\" WHERE c.\"Id\"=@id AND c.\"State\"='ACTIVE'";
        string secret;
        await using(var cmd=new NpgsqlCommand(sql,db,tx)){
            cmd.Parameters.AddWithValue("id",Str(input,"connectionId"));
            var raw=(string?)await cmd.ExecuteScalarAsync(Token);Must(raw!=null,"encrypted_profile");
            var row=JsonSerializer.Deserialize<ConnectionSecretRecord>(raw!)!;
            using var cipher=new ConnectionSecretCipher("/private/api/g4-key");
            secret=cipher.Decrypt(row);
            Must(!string.IsNullOrEmpty(secret),"connection_cipher");
        }
        await tx.CommitAsync(Token);
        stable["keys"]=new{certSha256=Sha(cert.RawData),tickets,subjects=expected.Count,results,connectionSecretVerified=true};
        return secret;
    }

    private static async Task Source(string secret)
    {
        var options=new OracleAdapterOptions{RootCertificatePath="/run/fixture/ca.pem",WalletDirectory="/run/fixture/client-wallet"};
        var adapter=new OracleSourceAdapter(options);
        var profile=new OracleConnectionProfile{Host="oracle-source",Port=2484,ServiceName="FREEPDB1",Username="FIXTURE_READER",
            Tls=true,AllowedOwners=["PRODUCTION","CaseOwner"]};
        var stages=await adapter.ProbeAsync(profile,secret,Token);
        Must(stages.Length==5&&stages.All(s=>s.Status=="PASS"),"oracle_capabilities");
        var catalog=await adapter.DiscoverAsync(profile,secret,Token);
        string[] cols=["ROW_ID","JOIN_KEY","VAL","ORG_ID","SITE_ID","EXT_ID","LABEL","FROM_TS","TO_TS","EVENT_TS","OBSERVED_TS"];
        var tables=new[]{("PRODUCTION","OMQ_ENTITY"),("CaseOwner","OmqTarget")};
        Must(catalog.Length==2 && tables.All(t=>catalog.Any(o=>o.Schema==t.Item1 && o.Name==t.Item2 && o.Kind=="TABLE" &&
            o.Fields.OrderBy(f=>f.Ordinal).Select(f=>f.Name).SequenceEqual(cols))),"oracle_columns");
        var source=new OracleConnectionStringBuilder{UserID=profile.Username,Password=secret,Pooling=false,ConnectionTimeout=5,
            DataSource="(DESCRIPTION=(CONNECT_TIMEOUT=5)(TRANSPORT_CONNECT_TIMEOUT=5)(RETRY_COUNT=0)(ADDRESS=(PROTOCOL=TCPS)(HOST=oracle-source)(PORT=2484))(CONNECT_DATA=(SERVICE_NAME=FREEPDB1))(SECURITY=(SSL_SERVER_DN_MATCH=YES)))"};
        await using var conn=new OracleConnection(source.ConnectionString){WalletLocation=options.WalletDirectory,SSLServerDNMatch=true,Pipelining=false};
        await conn.OpenAsync(Token);
        string[] hashes=new string[2];
        await using(var cmd=conn.CreateCommand()){
            cmd.CommandTimeout=5;cmd.CommandText="ALTER SESSION SET READ_ONLY=TRUE";await cmd.ExecuteNonQueryAsync(Token);
            cmd.CommandText="select sys_context('USERENV','SESSION_USER')||'|'||sys_context('USERENV','NETWORK_PROTOCOL')||'|'||sys_context('USERENV','CON_NAME') from dual";
            Must(string.Equals((string?)await cmd.ExecuteScalarAsync(Token),"FIXTURE_READER|TCPS|FREEPDB1",StringComparison.OrdinalIgnoreCase),"tcps_identity");
        }
        for(int i=0;i<2;i++){
            var t=tables[i];await using var cmd=conn.CreateCommand();cmd.CommandTimeout=5;
            cmd.CommandText="select json_array(ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,"+
                string.Join(",",cols.Skip(7).Select(c=>"to_char("+c+",'YYYYMMDDHH24MISSFF6')"))+" returning varchar2(500)) from \""+t.Item1+"\".\""+t.Item2+"\" order by ROW_ID";
            await using var rr=await cmd.ExecuteReaderAsync(Token);
            Must(await rr.ReadAsync(Token),"oracle_missing_row");
            var r=JsonSerializer.Deserialize<JsonElement>(rr.GetString(0));
            Must(r.GetArrayLength()==11 && !await rr.ReadAsync(Token),"oracle_row_count");
            // 与原有 Python fixture_state(parse_float=str) 的准确数字词法按位兼容。
            var normalized=r.EnumerateArray().Select(v=>v.ValueKind==JsonValueKind.Number&&v.GetRawText().Any(x=>x=='.'||x=='E'||x=='e')
                ? (object)v.GetRawText():v).ToArray();
            hashes[i]=Sha(JsonSerializer.SerializeToUtf8Bytes(normalized));
        }
        Must(hashes.SequenceEqual(input.GetProperty("sourceRowHashes").EnumerateArray().Select(v=>v.GetString())),"oracle_baseline");
        stable["oracle"]=new{driverAssembly=typeof(OracleConnection).Assembly.GetName().FullName,driverSha256=Sha(File.ReadAllBytes(typeof(OracleConnection).Assembly.Location)),
            trust=adapter.TrustFingerprint,fields=cols,catalog=Sha(JsonSerializer.SerializeToUtf8Bytes(catalog)),counts=new[]{1,1},hashes,tcps=true,stages=stages.Select(s=>s.Name).ToArray()};
    }
'''


IDENTITY = r'''
    private static byte[] Un64(string s)=>Convert.FromBase64String(s.Replace('-','+').Replace('_','/')+new string('=',(4-s.Length%4)%4));
    private static void CaptureSignature(string original,string expectedSubject)
    {
        // 已保全票据内原签名仅在私有进程复核；不持有/重放 access token，也不请求签发新 token。
        var parts=original.Split('.');Must(parts.Length==3 && original.Length<=65536,"saved_signature");
        var header=Parse(Un64(parts[0]));var body=Parse(Un64(parts[1]));
        var issuer=Config["Security:Authority"];var client=Config["Security:ClientId"];
        var aud=body.GetProperty("aud");
        Must(Str(header,"alg")=="RS256" && Str(body,"iss")==issuer && Str(body,"sub")==expectedSubject
            && (aud.ValueKind==JsonValueKind.String?aud.GetString()==client:aud.EnumerateArray().Any(a=>a.GetString()==client)),"saved_identity");
        var issued=body.GetProperty("iat").GetInt64();var expiry=body.GetProperty("exp").GetInt64();
        Must(expiry>issued && issued<=DateTimeOffset.UtcNow.ToUnixTimeSeconds()+5,"original_validity");
        witnesses.Add((Str(header,"kid"),expectedSubject,issued,expiry,SHA256.HashData(Encoding.ASCII.GetBytes(parts[0]+"."+parts[1])),Un64(parts[2])));
    }
    private static async Task Identity()
    {
        // 只请求公开 discovery 和 JWKS；用已有票据的签名核验候选恢复的公钥。
        string issuer=Config["Security:Authority"]??"",client=Config["Security:ClientId"]??"";
        Must(Regex.IsMatch(issuer,@"\Ahttp://localhost:15743/realms/g2-[0-9a-f]{16}\z") && client==issuer.Split('/').Last()+"-bff","issuer_origin");
        var open=Parse((await Fetch(issuer+"/.well-known/openid-configuration")).Body);
        Must(Str(open,"issuer")==issuer && Str(open,"jwks_uri")==issuer+"/protocol/openid-connect/certs","issuer_keys");
        var jwks=Parse((await Fetch(Str(open,"jwks_uri"))).Body).GetProperty("keys").EnumerateArray().ToArray();
        Must(jwks.Length is >0 and <=32 && jwks.Select(j=>Str(j,"kid")).Distinct().Count()==jwks.Length,"jwks_cardinality");
        var publicSet=jwks.Select(j=>new{kid=Str(j,"kid"),alg=Str(j,"alg"),use=Str(j,"use"),kty=Str(j,"kty"),
            materialSha256=TextHash(JsonSerializer.Serialize(j.EnumerateObject().OrderBy(p=>p.Name,StringComparer.Ordinal).Select(p=>new[]{p.Name,p.Value.GetRawText()}).ToArray()))})
            .OrderBy(j=>j.kid,StringComparer.Ordinal).ToArray();
        foreach(var sample in witnesses){
            var key=jwks.Single(j=>Str(j,"kid")==sample.Kid && Str(j,"alg")=="RS256" && Str(j,"use")=="sig" && Str(j,"kty")=="RSA");
            using var rsa=RSA.Create();rsa.ImportParameters(new RSAParameters{Modulus=Un64(Str(key,"n")),Exponent=Un64(Str(key,"e"))});
            Must(rsa.KeySize>=2048 && rsa.VerifyHash(sample.Digest,sample.Signature,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1),"token_signature");
        }
        var expected=input.GetProperty("subjects").EnumerateObject().Select(x=>x.Value.GetString()!).ToHashSet();
        var actual=witnesses.Select(w=>w.Subject).ToHashSet();
        // 没有签名原件时公钥观察仍成立；状态单列，不能换算成验签成功。
        stable["oidc"]=new{issuer,client,keys=publicSet,originalIdTokensVerified=witnesses.Count,allFourOriginalSubjectsVerified=expected.SetEquals(actual)};
        proof["idToken"]=new{kind="retained_id_token_signature",signedSamples=witnesses.Count,signatureVerified=witnesses.Count>0,
            coveredSubjects=actual.Count,issuedByRestoredInstance=false,checkedAt=DateTimeOffset.UtcNow.ToString("O")};
    }
'''

VERIFIER_MAIN = r'''
    /// <summary>记录独立已观测分项；明确不把暂缺的恢复门禁换算成全部通过。</summary>
    public static async Task<int> Main()
    {
        try{
            input=JsonSerializer.Deserialize<JsonElement>(await Console.In.ReadToEndAsync(Token));
            Must(Str(input,"taskId")=="G4-ORACLE-MAPPING-QUERY-001" && Str(input,"runId")=="implementation-01"
                && Str(input,"connectionId")=="a7913bb552eb4cd1a3f6eaf5b93cd619","task");
            component="protected-pg";var secret=await Keys();
            component="source";await Source(secret);
            component="fuseki";await Graphs();
            component="rustfs";await PublishedObjects();
            component="keycloak";await Identity();
            Console.WriteLine(JsonSerializer.Serialize(new{status="CHECKPOINT_COMPONENTS_OBSERVED",stable,proof,unverified=new[]{
                "oidc_current_realm_directory_roles_client","rustfs_all_version_ids_and_delete_markers"}},Json));return 0;
        }catch(Exception e){
            var code=e is InvalidDataException && Regex.IsMatch(e.Message,@"\A[a-zA-Z0-9_-]{1,80}\z")?e.Message:e.GetType().Name;
            Console.WriteLine(JsonSerializer.Serialize(new{status="CHECKPOINT_INCOMPLETE",component,code,completed=stable.Keys.ToArray(),stable,proof},Json));
            return 2;
        }
    }
}
'''


def compare(before, after):
    """仅比较已观测的稳定分项；没有获得证据的版本清单和 IdP 后台目录仍单列。"""
    for event in (before,after):
        require(event['status']=='CHECKPOINT_COMPONENTS_OBSERVED' and set(event['stable'])=={'keys','oracle','tdb2','rustfs','oidc'}
                and event['unverified']==['oidc_current_realm_directory_roles_client','rustfs_all_version_ids_and_delete_markers'],
                'CHECKPOINT_VERIFIER_INCOMPLETE')
    require(before['stable']==after['stable'],'CHECKPOINT_RESTORE_DRIFT')
    missing=list(after['unverified'])
    if not all(e['proof']['idToken']['signatureVerified'] and e['stable']['oidc']['allFourOriginalSubjectsVerified'] for e in (before,after)):
        missing.append('retained_id_token_signatures_for_four_subjects')
    return dict(scope='restored stable references and bytes',status='PARTIAL',stableSha256=ex.sha(ex.encoded(after['stable'])),
                observedComponents=sorted(after['stable']),unverified=missing)
