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
