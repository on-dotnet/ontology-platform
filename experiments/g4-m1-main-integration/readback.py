#!/usr/bin/env python3
"""精确本轮PG的只读结构与行计数见证；不返回秘密列或原始业务行。"""
import json
import runtime as rt

PROJECTIONS = {
    'schema': "SELECT nspname FROM pg_namespace WHERE nspname IN ('connections','ontology','governance','public') ORDER BY 1;",
    'tables': "SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('connections','ontology','governance','production') ORDER BY 1,2;",
    'connections-history': 'SELECT "MigrationId","ProductVersion" FROM connections."__EFMigrationsHistory" ORDER BY 1;',
    'source-history': "SELECT count(*) FROM pg_namespace WHERE nspname='connections';",
    'source-activity': "SELECT state,wait_event_type,count(*) FROM pg_stat_activity WHERE usename='fixture_reader' GROUP BY state,wait_event_type ORDER BY 1,2;",
}


def query(m, ident, projection, *, source=False):
    """SQL只来自编译常量；本地socket合成管理员，不通过命令行暴露密码。"""
    rt.require(projection in PROJECTIONS, 'PROJECTION_ALLOWLIST')
    rt.inspect_owned(m, ident, 'pg-source' if source else 'platform-pg')
    user, database = ('postgres','fixture') if source else ('platform','platform')
    sql = 'BEGIN READ ONLY;\n' + PROJECTIONS[projection] + '\nCOMMIT;\n'
    raw = rt.docker(m, ['exec','-i',ident,'psql','-X','-q','-A','-t','-F','|','-v','ON_ERROR_STOP=1','-U',user,'-d',database],input_bytes=sql.encode())
    return dict(projection=projection,rows=raw.decode().splitlines(),sha256=rt.digest(raw),containerId=ident)


def snapshot(m, name, *, source=False):
    """固定安全投影落盘，元数据回读不是完整I06验收。"""
    r=rt.runtime_value(m);ident=r['containerIds']['pg-source' if source else 'platform-pg']
    result=[query(m,ident,p,source=source) for p in (('schema','tables','source-history','source-activity') if source else ('schema','tables','connections-history'))]
    rt.write_json(rt.ARTIFACTS/m['runId']/(name+'.json'),dict(taskId=rt.TASK,runId=m['runId'],testedCommit=m['_head'],projections=result))
    return result


# 复用已审安全投影与历史trace关联算法，调用及身份由本任务持有。
import datetime as dt
import re
import os
import subprocess
import time
from pathlib import Path
ACTIONS = ["connection.create", "connection.probe.start", "connection.probe.complete", "connection.catalog.start", "connection.catalog.finish", "connection.enable", "connection.disable"]
CLOCK_TOLERANCE = dt.timedelta(seconds=2)

class WitnessError(Exception):
    """仅携带固定安全错误码，不携带数据库或进程错误正文。"""

def require(condition: bool, code: str) -> None:
    """遇到证据缺口立即失败，不能把未知字段或空查询提升为通过。"""
    if not condition:
        raise WitnessError(code)

def identifier(value: object, length: int = 32) -> str:
    """只接受固定长度十六进制公开标识，禁止拼入任意 SQL。"""
    require(isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{length}}}", value) is not None, "invalid_public_identifier")
    return str(value)

def timestamp(value: object) -> dt.datetime:
    """严格读取带时区的公开时间，不输出失败输入。"""
    require(isinstance(value, str), "timestamp_missing")
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise WitnessError("timestamp_invalid") from error
    require(parsed.tzinfo is not None, "timestamp_timezone_missing")
    return parsed

def build_sql(fixtures: dict, traces: list[str]) -> str:
    """在数据库内只选择白名单元数据，绝不提取凭据、Actor、Session 或完整历史 JSON。"""
    connection, probe, job, snapshot = (identifier(fixtures[key]) for key in ["connectionId", "probeId", "jobId", "snapshotId"])
    trace_sql = ",".join("'" + identifier(value) + "'" for value in traces)
    action_sql = ",".join("'" + value + "'" for value in ACTIONS)
    # ReportJson/ViewJson 由 Web JSON 选项编码；下列 JSON 键必须保持 camelCase。
    return f'''BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SELECT json_build_object(
'connection',(SELECT json_build_object('id',"Id",'revision',"Revision",'configHash',"ConfigHash",'secretVersion',"SecretVersion",'updatedAtUtc',"UpdatedAtUtc") FROM connections."Connections" WHERE "Id"='{connection}'),
'probes',(SELECT coalesce(json_agg(p),'[]'::json) FROM (SELECT "Id" AS id,"ConnectionId" AS "connectionId","Revision" AS revision,"ConfigHash" AS "configHash","SecretVersion" AS "secretVersion","ExpiresAtUtc" AS "expiresAtUtc",
"ReportJson"::jsonb->>'probeId' AS "reportProbeId","ReportJson"::jsonb->>'connectionId' AS "reportConnectionId","ReportJson"::jsonb->>'configHash' AS "reportConfigHash",("ReportJson"::jsonb->>'secretVersion')::bigint AS "reportSecretVersion",
"ReportJson"::jsonb->>'traceId' AS "traceId","ReportJson"::jsonb->>'startedAtUtc' AS "startedAtUtc","ReportJson"::jsonb->>'completedAtUtc' AS "completedAtUtc","ReportJson"::jsonb->>'expiresAtUtc' AS "reportExpiresAtUtc"
FROM connections."ConnectionProbes" WHERE "ConnectionId"='{connection}' AND ("Id"='{probe}' OR "ReportJson"::jsonb->>'traceId' IN ({trace_sql})) ORDER BY "Id" LIMIT 17) p),
'job',(SELECT json_build_object('id',"Id",'connectionId',"ConnectionId",'revision',"Revision",'configHash',"ConfigHash",'secretVersion',"SecretVersion",'traceId',"TraceId",'createdAtUtc',"CreatedAtUtc",'completedAtUtc',"CompletedAtUtc",'snapshotId',"SnapshotId") FROM connections."CatalogJobs" WHERE "Id"='{job}' AND "ConnectionId"='{connection}'),
'snapshot',(SELECT json_build_object('id',"Id",'connectionId',"ConnectionId",'configHash',"ConfigHash",'secretVersion',"SecretVersion",'capturedAtUtc',"CapturedAtUtc",'viewSnapshotId',"ViewJson"::jsonb->>'snapshotId','viewConnectionId',"ViewJson"::jsonb->>'connectionId','viewRevision',("ViewJson"::jsonb->>'configRevision')::bigint,'viewSecretVersion',("ViewJson"::jsonb->>'secretVersion')::bigint,'viewCapturedAtUtc',"ViewJson"::jsonb->>'capturedAtUtc','schemaFingerprint',"ViewJson"::jsonb->>'schemaFingerprint') FROM connections."CatalogSnapshots" WHERE "Id"='{snapshot}' AND "ConnectionId"='{connection}'),
'audits',(SELECT coalesce(json_agg(a),'[]'::json) FROM (SELECT "Action" AS action,"Resource" AS resource,"Outcome" AS outcome,"TraceId" AS "traceId","OccurredAtUtc" AS "occurredAtUtc" FROM governance.audit_records WHERE "TraceId" IN ({trace_sql}) AND "Action" IN ({action_sql}) AND "Resource" IN ('connection:new','connection:{connection}') ORDER BY "OccurredAtUtc" LIMIT 65) a));
COMMIT;
'''

def validate_projection(value: object) -> None:
    """输出前检查标量值形状，只保留许可的元数据而不落未知正文。"""
    if isinstance(value, dict):
        for key, item in value.items():
            if item is None:
                continue
            if isinstance(item, (dict, list)):
                validate_projection(item)
            elif key.lower().endswith("id"):
                identifier(item)
            elif key.lower().endswith("hash") or key == "schemaFingerprint":
                identifier(item, 64)
            elif key.endswith("Utc"):
                timestamp(item)
            elif key in ["revision", "viewRevision", "secretVersion", "reportSecretVersion", "viewSecretVersion"]:
                require(type(item) is int and item >= 1, "projection_version_invalid")
            elif key == "action":
                require(item in ACTIONS, "projection_action_invalid")
            elif key == "resource":
                require(isinstance(item, str) and re.fullmatch(r"connection:(new|[a-f0-9]{32})", item) is not None, "projection_resource_invalid")
            elif key == "outcome":
                require(item in ["allowed", "denied", "failure"], "projection_outcome_invalid")
            else:
                raise WitnessError("projection_field_not_allowed")
    elif isinstance(value, list):
        for item in value:
            validate_projection(item)
    else:
        raise WitnessError("projection_shape_invalid")

def compare(projection: dict, posts: list[dict], fixtures: dict, report: dict) -> None:
    """按原 POST trace 和历史捕获版本关联，不用当前连接版本冒充旧任务输入。"""
    def check(name: str, condition: bool) -> None:
        report["checks"].append({"name": name, "status": "PASS" if condition else "FAIL"})
        require(condition, name)

    def by_trace(trace: str, route: str) -> dict:
        candidates = [item for item in posts if item["traceId"] == trace and item["route"] == route]
        require(len(candidates) == 1, "original_post_trace_not_unique")
        return candidates[0]

    def in_http_window(value: str, post: dict) -> bool:
        start = timestamp(post["startedAtUtc"])
        end = start + dt.timedelta(milliseconds=post["durationMs"])
        return start - CLOCK_TOLERANCE <= timestamp(value) <= end + CLOCK_TOLERANCE

    def audit(action: str, trace: str, resource: str, low: str, high: str) -> None:
        rows = [row for row in projection["audits"] if row["action"] == action and row["traceId"] == trace and row["resource"] == resource]
        check(action + "_unique_original_post_audit", len(rows) == 1)
        check(action + "_outcome_and_time", rows[0]["outcome"] == "allowed" and timestamp(low) - CLOCK_TOLERANCE <= timestamp(rows[0]["occurredAtUtc"]) <= timestamp(high) + CLOCK_TOLERANCE)

    connection, job, snapshot, probes = (projection[key] for key in ["connection", "job", "snapshot", "probes"])
    check("all_exact_rows_present_and_bounded", all(isinstance(item, dict) for item in [connection, job, snapshot]) and 0 < len(probes) < 17 and len(projection["audits"]) < 65)
    check("connection_job_snapshot_ids", connection["id"] == fixtures["connectionId"] == job["connectionId"] == snapshot["connectionId"] and job["id"] == fixtures["jobId"] and job["snapshotId"] == snapshot["id"] == fixtures["snapshotId"])
    job_post = by_trace(job["traceId"], "/api/v1/connections/{id}/discoveries")
    check("job_created_in_original_discover_post_window", in_http_window(job["createdAtUtc"], job_post))
    # 先匹配历史 hash/SecretVersion 与时间，再取最接近该任务的原始探针。
    candidates = [probe for probe in probes if probe["configHash"] == job["configHash"] and probe["secretVersion"] == job["secretVersion"] and timestamp(probe["completedAtUtc"]) <= timestamp(job["createdAtUtc"]) and probe["revision"] <= job["revision"]]
    check("historical_probe_candidate_exists", bool(candidates))
    candidates.sort(key=lambda item: timestamp(item["completedAtUtc"]))
    probe = candidates[-1]
    probe_post = by_trace(probe["traceId"], "/api/v1/connections/{id}/test")
    report["selectedHistoricalProbeId"] = probe["id"]
    report["fixtureProbeUsedAsHistoricalProbe"] = probe["id"] == fixtures["probeId"]
    check("probe_columns_match_camelcase_report", probe["id"] == probe["reportProbeId"] and probe["connectionId"] == probe["reportConnectionId"] == connection["id"] and probe["configHash"] == probe["reportConfigHash"] and probe["secretVersion"] == probe["reportSecretVersion"] and timestamp(probe["expiresAtUtc"]) == timestamp(probe["reportExpiresAtUtc"]))
    check("probe_original_post_window_and_order", in_http_window(probe["startedAtUtc"], probe_post) and in_http_window(probe["completedAtUtc"], probe_post) and timestamp(probe["startedAtUtc"]) <= timestamp(probe["completedAtUtc"]) < timestamp(probe["expiresAtUtc"]))
    check("snapshot_captured_job_revision_hash_secret", snapshot["viewRevision"] == job["revision"] and snapshot["configHash"] == job["configHash"] and snapshot["secretVersion"] == snapshot["viewSecretVersion"] == job["secretVersion"] and snapshot["id"] == snapshot["viewSnapshotId"] and snapshot["connectionId"] == snapshot["viewConnectionId"])
    check("job_snapshot_time_order", timestamp(job["createdAtUtc"]) <= timestamp(job["completedAtUtc"]) and timestamp(job["createdAtUtc"]) <= timestamp(snapshot["capturedAtUtc"]) <= timestamp(job["completedAtUtc"]) + CLOCK_TOLERANCE and timestamp(snapshot["capturedAtUtc"]) == timestamp(snapshot["viewCapturedAtUtc"]))
    check("current_connection_not_misused_as_historical_revision", connection["revision"] >= job["revision"] and connection["secretVersion"] >= job["secretVersion"] and timestamp(connection["updatedAtUtc"]) >= timestamp(job["createdAtUtc"]))
    latest = [item for item in probes if item["configHash"] == connection["configHash"] and item["secretVersion"] == connection["secretVersion"] and item["revision"] <= connection["revision"] and timestamp(item["completedAtUtc"]) <= timestamp(connection["updatedAtUtc"])]
    check("current_connection_has_separate_captured_probe", bool(latest))
    latest.sort(key=lambda item: timestamp(item["completedAtUtc"]))
    latest_probe = latest[-1]
    latest_post = by_trace(latest_probe["traceId"], "/api/v1/connections/{id}/test")
    check("current_probe_post_and_column_binding", latest_probe["id"] == latest_probe["reportProbeId"] and latest_probe["connectionId"] == latest_probe["reportConnectionId"] == connection["id"] and latest_probe["configHash"] == latest_probe["reportConfigHash"] and latest_probe["secretVersion"] == latest_probe["reportSecretVersion"] and in_http_window(latest_probe["startedAtUtc"], latest_post) and in_http_window(latest_probe["completedAtUtc"], latest_post))
    report["selectedCurrentConfigProbeId"] = latest_probe["id"]
    resource = "connection:" + connection["id"]
    audit("connection.probe.start", probe["traceId"], resource, probe["startedAtUtc"], probe["completedAtUtc"])
    audit("connection.probe.complete", probe["traceId"], resource, probe["completedAtUtc"], probe["completedAtUtc"])
    audit("connection.catalog.start", job["traceId"], resource, job["createdAtUtc"], job["createdAtUtc"])
    audit("connection.catalog.finish", job["traceId"], resource, job["completedAtUtc"], snapshot["capturedAtUtc"])
    creates = [item for item in posts if item["route"] == "/api/v1/connections"]
    require(bool(creates), "original_create_post_missing")
    original = min(creates, key=lambda item: item["index"])
    audit("connection.create", original["traceId"], "connection:new", original["startedAtUtc"], (timestamp(original["startedAtUtc"]) + dt.timedelta(milliseconds=original["durationMs"])).isoformat())
    disables = [item for item in posts if item["route"] == "/api/v1/connections/{id}/disable"]
    require(len(disables) == 1, "successful_disable_post_not_unique")
    check("current_connection_update_matches_disable_post", in_http_window(connection["updatedAtUtc"], disables[0]))
    audit("connection.disable", disables[0]["traceId"], resource, connection["updatedAtUtc"], connection["updatedAtUtc"])


def sql(m, text, *, source=False):
    """调用仅来自本任务固定SQL/严格公开标识；不提供任意SQL CLI。"""
    r=rt.runtime_value(m);service='pg-source' if source else 'platform-pg'
    ident=r['containerIds'][service];rt.inspect_owned(m,ident,service)
    user,database=('postgres','fixture') if source else ('platform','platform')
    return rt.docker(m,['exec','-i',ident,'psql','-X','-qAt','-U',user,'-d',database,'-v','ON_ERROR_STOP=1'],input_bytes=("SET statement_timeout='5s'; SET lock_timeout='2s';"+text).encode()).decode().strip()


def reports(m, name):
    """唯一消费者报告，不从其他Run或已有目录寻找成功结果。"""
    root=rt.ARTIFACTS/m['runId']/name
    found=list(root.rglob('report.json'))
    rt.require(len(found)==1,'REPORT_CARDINALITY')
    rt.boundary(found[0],root,exists=True)
    value=json.loads(found[0].read_text())
    rt.require(value['taskId']==rt.TASK and value['runId']==m['runId'] and not value.get('failure'),'REPORT_FAILURE_OR_IDENTITY')
    return value


def action(m, name, label):
    """真实OIDC/CSRF故障消费者，公开报告只允许本Run新目录。"""
    import run
    output=rt.ARTIFACTS/m['runId']/('fault-'+label)
    rt.execute(m,'fault-'+label,[run.NODE,str(rt.HERE/'fault.mjs'),*run.binding(m),'--runtime-file',str(rt.private_dir(m['runId'])/'runtime.json'),'--action',name,'--evidence-dir',str(output)],timeout=90,sensitive=True)
    files=list(output.glob('*.json'));rt.require(len(files)==1,'FAULT_REPORT_CARDINALITY')
    value=json.loads(files[0].read_text());rt.require(value['taskId']==rt.TASK and value['status']=='PASS','FAULT_FAILED')
    return value


def lineage(m, baseline):
    """HTTP原始POST trace与安全数据库投影进行真实关联。"""
    fixtures={key:identifier(baseline['fixtures'][key]) for key in ('connectionId','probeId','jobId','snapshotId')}
    routes={'/api/v1/connections','/api/v1/connections/{id}/test','/api/v1/connections/{id}/discoveries','/api/v1/connections/{id}/disable'}
    posts=[{key:row[key] for key in ('index','route','traceId','startedAtUtc','durationMs')} for row in baseline['http'] if row.get('method')=='POST' and row.get('route') in routes and row.get('status') in (200,201,202,'TEST_OK','QUEUED')]
    rt.require(0<len(posts)<=32,'POST_SET')
    projection=json.loads(sql(m,build_sql(fixtures,[identifier(x['traceId']) for x in posts])))
    validate_projection(projection)
    report={'taskId':rt.TASK,'runId':m['runId'],'checks':[],'projection':projection}
    compare(projection,posts,fixtures,report)
    report['status']='PASS';rt.write_json(rt.ARTIFACTS/m['runId']/'http-db-lineage.json',report)
    return report


def test_pg(m, category, label, *, expectation=None):
    """已有实际程序集在精确第六容器运行；每组必须有测试且零skip。"""
    rt.require(category in ('RealPgFixture','RealPgWrongSanFixture','RealPgPublicFixture'),'PG_TEST_CATEGORY')
    r=rt.runtime_value(m);ident=r['containerIds']['pg-adapter-test'];rt.inspect_owned(m,ident,'pg-adapter-test')
    command=['docker','--context','desktop-linux','exec']
    if category=='RealPgWrongSanFixture':command+=['-e','G4_PG_WRONG_SAN_FIXTURE='+rt.TASK]
    if expectation:
        rt.require(expectation in ('PASS','catalog_access_forbidden','catalog_permission_limited'),'PG_PUBLIC_EXPECTATION')
        command+=['-e','G4_PUBLIC_EXPECTATION='+expectation]
    command += [ident,'dotnet','/tests/OntologyPlatform.ConnectionsTests.dll','--filter','TestCategory='+category,'--minimum-expected-tests','1','--results-directory','/tmp/TestResults','--no-ansi','--output','Detailed']
    raw=rt.execute(m,'pg-'+label,command,sensitive=True,timeout=180)
    text=raw.decode(errors='replace');match=re.search(r'(?:总计|total):\s*(\d+)',text,re.IGNORECASE)
    rt.require(match and int(match[1])>0,'PG_ZERO_TESTS')
    skips=re.search(r'(?:已跳过|skipped):\s*([1-9]\d*)',text,re.IGNORECASE)
    rt.require(not skips,'PG_FIXTURE_SKIPPED')
    return {'category':category,'label':label,'total':int(match[1]),'exitCode':0,'status':'PASS'}


def refresh_registry(m, label):
    """受控替换前后的创建清单保留版本；后续回收只使用最新精确ID。"""
    import closeout
    current=rt.ARTIFACTS/m['runId']/'resources-m1-owned.json'
    previous=current.with_name('resources-m1-before-'+label+'.json')
    rt.require(not previous.exists(),'EXISTING_RESOURCE_VERSION')
    os.rename(current,previous)
    rt.write_json(current,closeout.inventory(m))
    rt.resource_snapshot(m,'m1','resources-'+label)


def pg_security(m):
    """TLS、ACL和空public七状态；所有故障在finally恢复。"""
    rt.execute(m,'create-pg-test',rt.compose_command('m1')+['--profile','pg-test','up','-d','--no-build','--pull','never','pg-adapter-test'],env=rt.compose_environment(m),sensitive=True)
    refresh_registry(m,'pg-test-created')
    rows=[test_pg(m,'RealPgFixture','real-tls-acl')]
    baseline=sql(m,"BEGIN READ ONLY; SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'; COMMIT;",source=True)
    rt.require(baseline=='0','PUBLIC_BASELINE')
    rows.append(test_pg(m,'RealPgPublicFixture','empty-public',expectation='PASS'))
    faults=[('relation','CREATE TABLE public.g4_boundary (id integer);','DROP TABLE public.g4_boundary;','catalog_access_forbidden'),
        ('function','CREATE FUNCTION public.g4_boundary() RETURNS integer LANGUAGE SQL AS $$ SELECT 1 $$; REVOKE ALL ON FUNCTION public.g4_boundary() FROM PUBLIC;','DROP FUNCTION public.g4_boundary();','catalog_access_forbidden'),
        ('type',"CREATE TYPE public.g4_boundary AS ENUM ('synthetic');",'DROP TYPE public.g4_boundary;','catalog_access_forbidden'),
        ('missing','DROP SCHEMA public;','CREATE SCHEMA public AUTHORIZATION pg_database_owner; REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO PUBLIC;','catalog_access_forbidden'),
        ('usage','REVOKE USAGE ON SCHEMA public FROM PUBLIC,fixture_reader;','GRANT USAGE ON SCHEMA public TO PUBLIC;','catalog_permission_limited')]
    for name,setup,restore,expectation in faults:
        sql(m,setup,source=True)
        try:rows.append(test_pg(m,'RealPgPublicFixture','public-'+name,expectation=expectation))
        finally:sql(m,restore,source=True)
    rows.append(test_pg(m,'RealPgPublicFixture','public-restored',expectation='PASS'))
    env=rt.compose_environment(m);env['G4_CERTIFICATE_VARIANT']='wrong-san'
    try:
        rt.execute(m,'source-wrong-san',rt.compose_command('m1')+['up','-d','--no-build','--pull','never','pg-source'],env=env,sensitive=True)
        refresh_registry(m,'wrong-san');rt.wait_pg(m)
        rows.append(test_pg(m,'RealPgWrongSanFixture','wrong-san'))
    finally:
        rt.execute(m,'source-san-restore',rt.compose_command('m1')+['up','-d','--no-build','--pull','never','pg-source'],env=rt.compose_environment(m),sensitive=True)
        refresh_registry(m,'san-restored');rt.wait_pg(m)
    ident=rt.runtime_value(m)['containerIds']['pg-adapter-test'];rt.inspect_owned(m,ident,'pg-adapter-test')
    rt.docker(m,['stop','--time','5',ident]);rt.docker(m,['rm',ident]);refresh_registry(m,'pg-tests-closed')
    rt.write_json(rt.ARTIFACTS/m['runId']/'pg-security.json',{'status':'PASS','groups':rows})
    return rows


def audit_rollback(m):
    """真实审计写入触发故障；失败事务不得提前修改连接、探针或快照。"""
    result=[]
    for stage in ('start','complete'):
        rt.update_runtime(m,auditStage=stage)
        prepared=action(m,'audit-prepare','audit-'+stage+'-prepare')
        key=identifier(prepared['commandKey'],64)
        before=sql(m,"BEGIN READ ONLY; SELECT count(*) FROM connections.\"ConnectionProbes\" WHERE \"CommandKey\"='"+key+"'; COMMIT;")
        trigger="CREATE FUNCTION governance.g4_main_audit_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.\"Action\"='connection.probe."+stage+"' THEN RAISE EXCEPTION 'synthetic_audit_failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER g4_main_audit_fault BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.g4_main_audit_fault();"
        sql(m,trigger)
        try:
            failure=action(m,'audit-fail','audit-'+stage+'-fail')
            after=sql(m,"BEGIN READ ONLY; SELECT count(*) FROM connections.\"ConnectionProbes\" WHERE \"CommandKey\"='"+key+"'; COMMIT;")
            rt.require(before==after if stage=='start' else after=='1','AUDIT_DB_ROLLBACK')
        finally:
            sql(m,'DROP TRIGGER g4_main_audit_fault ON governance.audit_records; DROP FUNCTION governance.g4_main_audit_fault();')
        recovery=action(m,'audit-retry' if stage=='start' else 'audit-replay-failed','audit-'+stage+'-recovered')
        result.append({'stage':stage,'beforeCount':before,'afterCount':after,'httpFailure':failure,'recovery':recovery})
    rt.write_json(rt.ARTIFACTS/m['runId']/'audit-rollback.json',{'status':'PASS','cases':result})
    return result


def client_cancel(m):
    """真实TLS等待中的客户端取消，回读持久探针终态。"""
    with rt.PauseGuard(m,'pg-source',19):
        evidence=action(m,'probe-client-cancel','client-cancel')
        key=identifier(evidence['commandKey'],64)
        deadline=time.monotonic()+10
        while True:
            value=json.loads(sql(m,'BEGIN READ ONLY; SELECT json_build_object(\'status\',"ReportJson"::jsonb->>\'status\',\'stages\',"ReportJson"::jsonb->\'stages\') FROM connections."ConnectionProbes" WHERE "CommandKey"=\''+key+'\'; COMMIT;'))
            if value['status']!='RUNNING':break
            rt.require(time.monotonic()<deadline,'CLIENT_CANCEL_TIMEOUT');time.sleep(.2)
        rt.require(value['status']=='CANCELLED' and any(x['diagnosticCode']=='connection_cancelled' for x in value['stages']),'CLIENT_CANCEL_NOT_PERSISTED')
        rt.require(value['stages'][0]['name']=='NETWORK' and value['stages'][0]['status']=='PASS','NO_REAL_NETWORK_IO')
    result={'status':'PASS','http':evidence,'persistentProbe':value,'sourceRestored':True}
    rt.write_json(rt.ARTIFACTS/m['runId']/'client-cancel.json',result);return result


class SourceSession:
    """本任务真实PG会话，锁持有有数据库超时，进程退出finally回滚。"""
    def __init__(self,m, *, source=True):
        import selectors
        self.selectors=selectors;self.m=m;self.source=source;self.process=None
    def __enter__(self):
        service='pg-source' if self.source else 'platform-pg'
        ident=rt.runtime_value(self.m)['containerIds'][service];rt.inspect_owned(self.m,ident,service)
        user,db=('postgres','fixture') if self.source else ('platform','platform')
        self.process=subprocess.Popen(['docker','--context','desktop-linux','exec','-i',ident,'psql','-X','-qAt','-U',user,'-d',db,'-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
        return self
    def read(self,timeout=4):
        selector=self.selectors.DefaultSelector();selector.register(self.process.stdout,self.selectors.EVENT_READ)
        try:
            rt.require(bool(selector.select(timeout)),'PG_SESSION_TIMEOUT')
            value=self.process.stdout.readline();rt.require(value,'PG_SESSION_EOF');return json.loads(value)
        finally:selector.close()
    def query(self,text):
        self.process.stdin.write(text+'\n');self.process.stdin.flush();return self.read()
    def __exit__(self,*exc):
        if self.process.poll() is None:
            try:self.process.stdin.write('ROLLBACK;\n\\q\n');self.process.stdin.flush();self.process.wait(timeout=5)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                os.killpg(self.process.pid,__import__('signal').SIGTERM);self.process.wait(timeout=5)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()


def catalog_cancel(m):
    """保持源锁直到真实worker连接消失，之后读取持久CANCELLED。"""
    action(m,'probe-refresh','cancel-probe-refresh')
    with SourceSession(m) as observer:
        observer.query("SET statement_timeout='2s'; SET idle_session_timeout='45s'; SET plan_cache_mode=force_generic_plan; PREPARE main_cancel_activity AS SELECT coalesce(json_agg(json_build_object('pid',pid,'wait',wait_event_type)),'[]') FROM pg_stat_activity WHERE usename='fixture_reader' AND backend_type='client backend'; EXECUTE main_cancel_activity;")
        observer.query("PREPARE main_cancel_lock(int) AS SELECT count(*) FROM pg_locks WHERE pid=$1 AND relation='pg_catalog.pg_attribute'::regclass AND mode='AccessExclusiveLock' AND granted; EXECUTE main_cancel_lock(-1);")
        with SourceSession(m) as lock:
            held=lock.query("SET statement_timeout='25s'; SET idle_in_transaction_session_timeout='25s'; SET lock_timeout='2s'; BEGIN; LOCK TABLE pg_catalog.pg_attribute IN ACCESS EXCLUSIVE MODE; SELECT json_build_object('pid',pg_backend_pid(),'held',true);")
            job=identifier(action(m,'job-start','cancel-job-start')['jobId']);rt.update_runtime(m,httpJobId=job)
            deadline=time.monotonic()+4;waiting=[]
            while not waiting:
                waiting=observer.query('EXECUTE main_cancel_activity;')
                if any(x['wait']=='Lock' for x in waiting):break
                rt.require(time.monotonic()<deadline,'WORKER_NOT_BLOCKED');time.sleep(.05)
            rt.require(any(x['wait']=='Lock' for x in waiting),'NO_SOURCE_LOCK_WAITER')
            cancelled=action(m,'job-cancel','cancel-job-request')
            deadline=time.monotonic()+5
            while True:
                after=observer.query('EXECUTE main_cancel_activity;')
                if not any(x['pid'] in {v['pid'] for v in waiting} for x in after):break
                rt.require(time.monotonic()<deadline,'SOURCE_BACKEND_NOT_CANCELLED');time.sleep(.05)
            rt.require(observer.query('EXECUTE main_cancel_lock('+str(int(held['pid']))+');')==1,'SOURCE_LOCK_RELEASED_TOO_EARLY')
        final=action(m,'job-read','cancel-job-final')
        rt.require(final['jobStatus']=='CANCELLED' and final['snapshotId'] is None,'JOB_CANCEL_NOT_DURABLE')
    result={'status':'PASS','jobId':job,'sourceBeforeCancel':waiting,'sourceAfterCancel':after,'sourceLockHeldAtBackendDisappearance':True,'http':cancelled,'final':final}
    rt.write_json(rt.ARTIFACTS/m['runId']/'catalog-cancel.json',result);return result


def run_interactive(m, consumer_name, scenario, callback, *, timeout=120):
    """真实浏览器/HTTP握手受固定事件约束，原始输出私有且有界。"""
    import run
    import selectors
    rt.require(consumer_name in ('http','browser'),'INTERACTIVE_CONSUMER')
    output=rt.ARTIFACTS/m['runId']/(consumer_name+'-'+scenario)
    command=[run.NODE,str(rt.HERE/(consumer_name+'.mjs')),*run.binding(m),'--runtime-file',str(rt.private_dir(m['runId'])/'runtime.json'),'--evidence-dir',str(output)]
    child=subprocess.Popen(command,cwd=rt.ROOT,env=rt.environment(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
    selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
    deadline=time.monotonic()+timeout;lines=[];started=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        while child.poll() is None:
            rt.require(time.monotonic()<deadline,'INTERACTIVE_DEADLINE')
            if not selector.select(.5):continue
            line=child.stdout.readline()
            if not line:break
            rt.require(len(line)<16384,'INTERACTIVE_OUTPUT_BUDGET');lines.append(line)
            value=json.loads(line)
            rt.require(value.get('taskId')==rt.TASK,'INTERACTIVE_TASK')
            if 'event' in value:
                rt.require(value.get('runId')==m['runId'],'INTERACTIVE_RUN')
                response=callback(value)
                rt.require(response in ('SOURCE_PASSWORD_ROTATED','SOURCE_PASSWORD_RESTORED','SOURCE_PAUSED','SOURCE_LOCKED','SOURCE_QUERY_WAITING'),'INTERACTIVE_ACK')
                child.stdin.write(response+'\n');child.stdin.flush()
        child.wait(timeout=5)
        rt.require(child.returncode in (0,2),'INTERACTIVE_CONSUMER_FAILED')
        return reports(m,consumer_name+'-'+scenario)
    finally:
        selector.close()
        if child.poll() is None:
            import signal
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
        import signal
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        raw=''.join(lines)+child.stderr.read()
        private=rt.private_dir(m['runId'])/'logs'/('interactive-'+consumer_name+'-'+scenario+'.log')
        with open(private,'x') as stream:os.chmod(private,0o600);stream.write(raw)
        for stream in (child.stdin,child.stdout,child.stderr):stream.close()
        rt.write_json(rt.ARTIFACTS/m['runId']/('interactive-'+consumer_name+'-'+scenario+'.json'),{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'command':command,'pid':child.pid,'startedAtUtc':started,'exitCode':child.returncode,'logSha256':rt.digest(raw.encode())})


def credential_lifecycle(m):
    """使用自然过期的原始签发回执，并实际轮换源密码后恢复。"""
    private=rt.private_dir(m['runId']);issued=json.loads((private/'lifecycle-refs.json').read_text())
    for key in ('expiredSecretRef','revokedSecretRef'):identifier(issued[key])
    expires=timestamp(issued['expiredSecretExpiresAtUtc'])
    rt.require(expires-dt.datetime.now(dt.timezone.utc)<dt.timedelta(minutes=11),'EXPIRY_BUDGET')
    while dt.datetime.now(dt.timezone.utc)<=expires:
        time.sleep(min(10,max(.1,(expires-dt.datetime.now(dt.timezone.utc)).total_seconds())))
    rt.update_runtime(m,httpScenario='credential-lifecycle',**issued,rotationSecretFile=str(private/'rotation-password'))
    def set_password(restore):
        path=private/('reader-password' if restore else 'rotation-password')
        rt.boundary(path,private,exists=True,private=True)
        value=path.read_text().strip();rt.require(re.fullmatch('[A-Za-z0-9_-]{30,100}',value),'SYNTHETIC_PASSWORD_FORMAT')
        sql(m,"ALTER ROLE fixture_reader PASSWORD '"+value+"';",source=True)
    # 独立恢复守护只读取本Run原密码；不把秘密放进argv、stdout或证据。
    script='''import sys,json,subprocess,time,pathlib
ident,task,run,private=sys.argv[1:];time.sleep(100)
base=['docker','--context','desktop-linux'];p=subprocess.run(base+['inspect',ident],capture_output=True,check=True,timeout=5);x=json.loads(p.stdout)[0]
assert x['Id']==ident and x['Config']['Labels']['ontology.task-id']==task and x['Config']['Labels']['ontology.run-id']==run
restored_password=(pathlib.Path(private)/'reader-password').read_text().strip();assert all(c.isalnum() or c in '_-' for c in restored_password)
subprocess.run(base+['exec','-i',ident,'psql','-U','postgres','-d','fixture','-v','ON_ERROR_STOP=1','-qAt'],input=("SET statement_timeout='5s';ALTER ROLE fixture_reader PASSWORD '"+restored_password+"';").encode(),capture_output=True,check=True,timeout=10)
'''
    source=rt.runtime_value(m)['containerIds']['pg-source']
    guard=subprocess.Popen([__import__('sys').executable,'-B','-c',script,source,rt.TASK,m['runId'],str(private)],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    changed=False
    def callback(value):
        nonlocal changed
        if value['event']=='CREDENTIAL_ROTATION_READY':
            rt.require(not changed,'DUPLICATE_ROTATE');set_password(False);changed=True;return 'SOURCE_PASSWORD_ROTATED'
        rt.require(value['event']=='CREDENTIAL_RESTORE_READY' and changed,'CREDENTIAL_HANDSHAKE')
        set_password(True);changed=False;return 'SOURCE_PASSWORD_RESTORED'
    try:
        report=run_interactive(m,'http','credential-lifecycle',callback,timeout=90)
        rt.require(report['fixtures']['sourceRestorationVerifiedByProbe'] and not changed,'SOURCE_PASSWORD_NOT_VERIFIED_RESTORED')
        return report
    finally:
        set_password(True)
        if guard.poll() is None:guard.terminate();guard.wait(timeout=5)
        rt.write_json(rt.ARTIFACTS/m['runId']/'credential-guard.json',{'pid':guard.pid,'exitCode':guard.returncode,'scriptSha256':rt.digest(script.encode()),'originalPasswordRestored':True})


def source_role_faults(m):
    """真实源角色与物理密码拒绝，逐例恢复后真实Probe复核。"""
    r=rt.runtime_value(m);private=rt.private_dir(m['runId'])
    faults=[('owner','ALTER TABLE production.heat_event OWNER TO fixture_reader;','ALTER TABLE production.heat_event OWNER TO postgres;','connection_readonly_unverified'),
        ('superuser','ALTER ROLE fixture_reader SUPERUSER;','ALTER ROLE fixture_reader NOSUPERUSER;','connection_readonly_unverified'),
        ('inherited-write','CREATE ROLE main_write_role NOLOGIN; GRANT UPDATE ON production.heat_event TO main_write_role; GRANT main_write_role TO fixture_reader; ALTER ROLE fixture_reader INHERIT;','ALTER ROLE fixture_reader NOINHERIT; REVOKE main_write_role FROM fixture_reader; REVOKE UPDATE ON production.heat_event FROM main_write_role; DROP ROLE main_write_role;','connection_readonly_unverified')]
    rows=[]
    for label,setup,restore,expected in faults:
        sql(m,setup,source=True)
        try:
            rt.update_runtime(m,expectedProbeDiagnostic=expected)
            result=action(m,'probe-denial','source-'+label)
            probe=identifier(result['probeId'])
            projection=json.loads(sql(m,'BEGIN READ ONLY; SELECT json_build_object(\'id\',"Id",\'status\',"ReportJson"::jsonb->>\'status\',\'stages\',"ReportJson"::jsonb->\'stages\') FROM connections."ConnectionProbes" WHERE "Id"=\''+probe+'\'; COMMIT;'))
            rt.require(projection['status']=='TEST_FAILED','ROLE_FAILURE_NOT_PERSISTED')
            rows.append({'name':label,'http':result,'persistent':projection})
        finally:sql(m,restore,source=True)
        action(m,'probe-refresh','source-'+label+'-restored')
    rt.write_json(rt.ARTIFACTS/m['runId']/'source-role-faults.json',{'status':'PASS','cases':rows});return rows


def source_network_connections(raw):
    """捕获TCP接入，包括TLS/认证前失败；排除已登记的Unix socket健康探针。"""
    rows=[]
    for line in raw.splitlines():
        if b'connection received:' not in line:continue
        match=re.search(rb'connection received: host=(\S+)',line)
        rt.require(match,'SOURCE_CONNECTION_LOG_FORMAT')
        if match[1]!=b'[local]':rows.append(line)
    return rows


def require_no_reader_io(m, before, after):
    """禁用池化、无活跃reader且无新增非Unix接入，覆盖TCP/TLS前置源IO。"""
    baseline=source_network_connections(before);observed=source_network_connections(after)
    rt.require(baseline,'SOURCE_IO_POSITIVE_CONTROL_MISSING')
    rt.require(after.startswith(before),'SOURCE_LOG_TRUNCATED')
    rt.require(observed==baseline,'UNEXPECTED_SOURCE_NETWORK_IO')
    rt.require(sql(m,"SELECT count(*) FROM pg_stat_activity WHERE usename='fixture_reader';",source=True)=='0','READER_SESSION_NOT_CLOSED')
    return {'beforeNetworkConnections':len(baseline),'afterNetworkConnections':len(observed),'scope':'all non-Unix connection received events, including TCP-only and TLS/auth rejection','pooling':False,'adapterPath':'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgSourceAdapter.cs','adapterSha256':rt.digest((rt.ROOT/'backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgSourceAdapter.cs').read_bytes())}


def lifecycle_and_faults(m):
    """真实TLS/ACL、HTTP、持久关联和安全故障串行验收。"""
    import run
    rt.check_build(m)
    groups=pg_security(m)
    run.consumer(m,'http',scenario='baseline');baseline=reports(m,'http-baseline')
    lineage_result=lineage(m,baseline)
    rt.update_runtime(m,httpConnectionId=identifier(baseline['fixtures']['connectionId']))
    source=rt.runtime_value(m)['containerIds']['pg-source']
    rt.require(sql(m,"SELECT count(*) FROM pg_stat_activity WHERE usename='fixture_reader';",source=True)=='0','ACTIVE_READER_BEFORE_DENIAL')
    before=rt.execute(m,'source-before-disabled',['docker','--context','desktop-linux','logs',source],sensitive=True)
    disabled=action(m,'disabled-denials','disabled-denials')
    after=rt.execute(m,'source-after-disabled',['docker','--context','desktop-linux','logs',source],sensitive=True)
    reader_io=require_no_reader_io(m,before,after)
    rt.write_json(rt.ARTIFACTS/m['runId']/'disabled-source-io.json',{'status':'PASS','sourceContainerId':source,'beforeSha256':rt.digest(before),'afterSha256':rt.digest(after),'readerIo':reader_io,'http':disabled})
    run.consumer(m,'http',scenario='provision');provision=reports(m,'http-provision')
    fixtures=provision['fixtures'];rt.update_runtime(m,httpConnectionId=identifier(fixtures['connectionId']),httpSnapshotId=identifier(fixtures['snapshotId']))
    action(m,'intake-lifecycle','intake-lifecycle')
    private=rt.private_dir(m['runId'])
    issued=json.loads((private/'lifecycle-refs.json').read_text());revoked=identifier(issued['revokedSecretRef'])
    count=sql(m,'WITH changed AS (UPDATE connections."ConnectionSecrets" SET "UsedAtUtc"=now() WHERE "Id"=\''+revoked+'\' AND "UsedAtUtc" IS NULL AND "ConnectionId" IS NULL RETURNING 1) SELECT count(*) FROM changed;')
    rt.require(count=='1','EXACT_SYNTHETIC_REVOCATION')
    import secrets,pg_fixture
    pg_fixture.private_file(private,'rotation-password',secrets.token_urlsafe(40))
    rt.write_json(rt.ARTIFACTS/m['runId']/'credential-revocation.json',{'taskId':rt.TASK,'runId':m['runId'],'referenceSha256':rt.digest(revoked.encode()),'affectedRows':1,'method':'consume exact unused synthetic reference; physical source password unchanged'})
    purpose=purpose_fault(m)
    roles=source_role_faults(m)
    audit=audit_rollback(m)
    cancel=client_cancel(m)
    catalog=catalog_cancel(m)
    lease=lease_fence(m)
    schema=schema_change(m)
    credentials=credential_lifecycle(m)
    cross_org=cross_org_secret(m)
    result={'status':'PASS','pgGroups':groups,'lineage':lineage_result['status'],'secretPurpose':purpose['status'],'sourceRoleFaults':len(roles),'auditRollbackCases':len(audit),'clientCancel':cancel['status'],'catalogCancel':catalog['status'],'leaseFence':lease['status'],'schemaImmutable':schema['status'],'credentialLifecycle':credentials['fixtures'],'crossOrganization':cross_org['status']}
    rt.write_json(rt.ARTIFACTS/m['runId']/'lifecycle-complete.json',result);return result


def browser_faults(m):
    """真实同构建浏览器闭环与故障组，未观测状态不提升为PASS。"""
    import run
    rt.check_build(m)
    rt.update_runtime(m,scenario='baseline')
    run.consumer(m,'browser',scenario='baseline');baseline=reports(m,'browser-baseline')
    rt.require(all(baseline['cases'][k]['status']=='PASS' for k in ('M1-U01','M1-U02','M1-U03','M1-U04','M1-U06')),'BROWSER_BASELINE_INCOMPLETE')
    run.consumer(m,'browser',scenario='layout-only');layout=reports(m,'browser-layout-only')
    r=rt.runtime_value(m);rt.update_runtime(m,connectionId=r['httpConnectionId'])
    source=r['containerIds']['pg-source']
    rt.docker(m,['stop','--time','5',source])
    try:run.consumer(m,'browser',scenario='source-unavailable')
    finally:
        rt.docker(m,['start',source]);rt.wait_pg(m);rt.require(rt.inspect_owned(m,source,'pg-source')['State']['Running'],'SOURCE_NOT_RESTORED')
    action(m,'probe-refresh','ui-probe-refresh')
    rt.update_runtime(m,scenario='source-timeout',sourcePauseHandshake=True)
    guard=None
    def paused(value):
        nonlocal guard
        rt.require(value['event']=='SOURCE_TIMEOUT_READY','TIMEOUT_HANDSHAKE')
        guard=rt.PauseGuard(m,'pg-source',19);guard.__enter__();return 'SOURCE_PAUSED'
    try:timeout_report=run_interactive(m,'browser','source-timeout',paused)
    finally:
        if guard:guard.__exit__()
        rt.update_runtime(m,sourcePauseHandshake=False)
    action(m,'probe-refresh','ui-timeout-restored')
    partial_sql='REVOKE SELECT ON production.heat_event FROM fixture_reader;'
    sql(m,partial_sql,source=True)
    try:run.consumer(m,'browser',scenario='source-permission-limited')
    finally:sql(m,'GRANT SELECT ON production.heat_event TO fixture_reader;',source=True)
    action(m,'probe-refresh','ui-permission-restored')
    cancelled=browser_cancel(m)
    observed=set()
    for name in ('baseline','source-unavailable','source-timeout','source-permission-limited','catalog-cancel'):
        observed.update(reports(m,'browser-'+name)['cases']['M1-U05']['observed'])
    rt.require(any('cancel' in x for x in observed) and any('timeout' in x for x in observed) and any('partial' in x for x in observed),'UI_FAULT_STATES_INCOMPLETE')
    result={'status':'PASS','baseline':{k:v['status'] for k,v in baseline['cases'].items()},'observedU05':sorted(observed),'sourceRestored':True,'catalogCancel':cancelled['status']}
    rt.write_json(rt.ARTIFACTS/m['runId']/'browser-complete.json',result);return result


def lease_fence(m):
    """真实双worker租约接管；旧worker恢复后不得重复快照或finish审计。"""
    connection=identifier(rt.runtime_value(m)['httpConnectionId']);replica=None
    def state(job):
        return json.loads(sql(m,'BEGIN READ ONLY; SELECT json_build_object(\'status\',"Status",\'fence\',"Fence",\'attempt\',"Attempt",\'expired\',"LeaseUntil"<now(),\'snapshot\',"SnapshotId") FROM connections."CatalogJobs" WHERE "Id"=\''+identifier(job)+'\'; COMMIT;'))
    def counts():
        return json.loads(sql(m,'BEGIN READ ONLY; SELECT json_build_object(\'snapshots\',(SELECT count(*) FROM connections."CatalogSnapshots" WHERE "ConnectionId"=\''+connection+'\'),\'audits\',(SELECT count(*) FROM governance.audit_records WHERE "Resource"=\'connection:'+connection+'\' AND "Action"=\'connection.catalog.finish\')); COMMIT;'))
    action(m,'probe-refresh','lease-probe')
    before=counts();result={'status':'FAIL','before':before}
    try:
        rt.execute(m,'lease-replica-create',rt.compose_command('m1')+['--profile','lease','create','--no-build','--pull','never','api-recovery'],env=rt.compose_environment(m),sensitive=True)
        refresh_registry(m,'lease-created');replica=rt.runtime_value(m)['containerIds']['api-recovery']
        info=rt.inspect_owned(m,replica,'api-recovery');rt.require(not info['State']['Running'] and not info['HostConfig']['PortBindings'],'LEASE_REPLICA_BOUNDARY')
        with SourceSession(m) as observer:
            observer.query("SET statement_timeout='2s'; SET idle_session_timeout='100s'; SET plan_cache_mode=force_generic_plan; PREPARE main_lease_activity AS SELECT coalesce(json_agg(json_build_object('pid',pid,'wait',wait_event_type)),'[]') FROM pg_stat_activity WHERE usename='fixture_reader'; EXECUTE main_lease_activity;")
            with SourceSession(m) as lock:
                held=lock.query("SET statement_timeout='55s'; SET idle_in_transaction_session_timeout='55s'; SET lock_timeout='2s'; BEGIN; LOCK TABLE pg_catalog.pg_attribute IN ACCESS EXCLUSIVE MODE; SELECT json_build_object('pid',pg_backend_pid(),'held',true);")
                job=identifier(action(m,'job-start','lease-job')['jobId']);rt.update_runtime(m,httpJobId=job)
                deadline=time.monotonic()+4
                while True:
                    first=state(job);waiting=observer.query('EXECUTE main_lease_activity;')
                    if first['status']=='RUNNING' and any(x['wait']=='Lock' for x in waiting):break
                    rt.require(time.monotonic()<deadline,'LEASE_FIRST_NOT_RUNNING');time.sleep(.05)
                rt.require(first['fence']==1 and first['attempt']==1,'LEASE_FIRST_FENCE')
                with rt.PauseGuard(m,'api',100):
                    deadline=time.monotonic()+36
                    while True:
                        expired=state(job)
                        if expired['expired']:break
                        rt.require(time.monotonic()<deadline and expired['fence']==1,'LEASE_NOT_EXPIRED');time.sleep(.2)
                    rt.docker(m,['start',replica]);rt.resource_snapshot(m,'m1','lease-two-workers')
                    deadline=time.monotonic()+10
                    while True:
                        takeover=state(job)
                        if takeover['fence']>=2:break
                        rt.require(time.monotonic()<deadline,'LEASE_NOT_TAKEN');time.sleep(.05)
                    rt.require(takeover['attempt']>=2,'LEASE_ATTEMPT')
                    lock.query("ROLLBACK; SELECT true;")
                    deadline=time.monotonic()+15
                    while True:
                        terminal=state(job)
                        if terminal['status'] not in ('QUEUED','RUNNING'):break
                        rt.require(time.monotonic()<deadline,'LEASE_TERMINAL_TIMEOUT');time.sleep(.1)
                    rt.require(terminal['status']=='SUCCEEDED' and terminal['snapshot'],'LEASE_RECOVERY_NOT_SUCCESS')
                    after=counts();rt.require(after=={'snapshots':before['snapshots']+1,'audits':before['audits']+1},'LEASE_DUPLICATE_WRITE')
                deadline=time.monotonic()+10
                while any(x['pid'] in {v['pid'] for v in waiting} for x in observer.query('EXECUTE main_lease_activity;')):
                    rt.require(time.monotonic()<deadline,'OLD_WORKER_IO_REMAINING');time.sleep(.1)
                # 至少跨过一个真实轮询周期，观察旧worker恢复不能再次提交。
                time.sleep(5.5)
                final=state(job);rt.require(final==terminal and counts()==after,'FENCE_FAILED_AFTER_OLD_WORKER_RESUMED')
                result.update(status='PASS',jobId=job,first=first,expired=expired,takeover=takeover,terminal=terminal,after=after,oldWorkerRecoveredWithoutDuplicate=True)
    finally:
        if replica:
            rt.inspect_owned(m,replica,'api-recovery');rt.docker(m,['stop','--time','5',replica]);rt.docker(m,['rm',replica]);refresh_registry(m,'lease-closed')
        rt.write_json(rt.ARTIFACTS/m['runId']/'lease-fence.json',result)
    return result


def cross_org_secret(m):
    """同一真实OIDC subject改变合成组织，再验证旧组织Ref不能消费，最后复原。"""
    import copy
    import urllib.parse
    import urllib.request
    import run
    action(m,'intake-foreign','cross-org-intake')
    private=rt.private_dir(m['runId']);r=rt.runtime_value(m);realm=json.loads(Path(r['realmFile']).read_text())
    name=realm['authority'].rsplit('/',1)[-1];rt.require(re.fullmatch('g2-[a-f0-9]+',name),'EXACT_SYNTHETIC_REALM')
    issued=json.loads((private/'cross-org-ref.json').read_text());ref=identifier(issued['secretRef']);subject=issued['subjectId']
    rt.require(re.fullmatch('[a-f0-9-]{36}',subject),'SUBJECT_ID')
    token=None
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def request(method,path,value=None,form=False):
        rt.require(path=='/realms/master/protocol/openid-connect/token' or path.startswith('/admin/realms/'+name+'/'),'ADMIN_REALM_BOUNDARY')
        data=(urllib.parse.urlencode(value).encode() if form else json.dumps(value).encode()) if value is not None else None
        headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'}
        if token:headers['Authorization']='Bearer '+token
        with opener.open(urllib.request.Request('http://localhost:15180'+path,data=data,headers=headers,method=method),timeout=8) as response:
            raw=response.read(1024*1024+1);rt.require(len(raw)<=1024*1024,'ADMIN_OUTPUT_LIMIT');return json.loads(raw) if raw else None
    token=request('POST','/realms/master/protocol/openid-connect/token',{'grant_type':'password','client_id':'admin-cli','username':'wave2-bootstrap','password':(private/'keycloak-password').read_text()},True)['access_token']
    prefix='/admin/realms/'+name
    users=request('GET',prefix+'/users?username=g2-operator-a&exact=true');rt.require(len(users)==1 and users[0]['id']==subject,'EXACT_SUBJECT')
    profile=request('GET',prefix+'/users/profile');desired=copy.deepcopy(profile)
    rt.require(not any(x['name'] in ('organization_id','site_ids') for x in desired['attributes']),'PROFILE_ALREADY_MANAGED')
    desired['attributes'].extend([{'name':'organization_id','multivalued':False,'permissions':{'view':['admin'],'edit':['admin']}},{'name':'site_ids','multivalued':True,'permissions':{'view':['admin'],'edit':['admin']}}])
    original=request('GET',prefix+'/users/'+subject)
    original.setdefault('attributes',{}).update(organization_id=['org-demo'],site_ids=['site-a'])
    restore_file=private/'cross-org-independent-restore.json'
    rt.write_json(restore_file,{'taskId':rt.TASK,'runId':m['runId'],'realm':name,'subject':subject,'profile':profile,'user':original,'token':token,'keycloakId':r['containerIds']['keycloak-test']},private=True)
    script=r'''import json,sys,pathlib,subprocess,time,urllib.request
path=pathlib.Path(sys.argv[1]);time.sleep(45);value=json.loads(path.read_text());assert not path.is_symlink() and path.stat().st_mode&0o077==0
ident=value['keycloakId'];p=subprocess.run(['docker','--context','desktop-linux','inspect',ident],capture_output=True,check=True,timeout=5);item=json.loads(p.stdout)[0]
assert item['Id']==ident and item['Config']['Labels']['ontology.task-id']==value['taskId'] and item['Config']['Labels']['ontology.run-id']==value['runId']
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
for suffix,body in [('users/'+value['subject'],value['user']),('users/profile',value['profile'])]:
 req=urllib.request.Request('http://localhost:15180/admin/realms/'+value['realm']+'/'+suffix,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+value['token'],'Content-Type':'application/json'},method='PUT')
 with opener.open(req,timeout=8) as response:assert response.status==204
'''
    guard=subprocess.Popen([__import__('sys').executable,'-B','-c',script,str(restore_file)],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    changed=False;result={'status':'FAIL','restoreGuardPid':guard.pid,'restoreGuardScriptSha256':rt.digest(script.encode())}
    try:
        request('PUT',prefix+'/users/profile',desired)
        # 签发动作已真实证明原claims；Keycloak unmanaged属性读取可能隐藏这两项。
        original.setdefault('attributes',{}).update(organization_id=['org-demo'],site_ids=['site-a'])
        changed_user=copy.deepcopy(original);changed_user['attributes']['organization_id']=['org-other']
        rt.write_json(private/'cross-org-restore.json',{'profile':profile,'user':original,'realm':name},private=True)
        request('PUT',prefix+'/users/'+subject,changed_user);changed=True
        rt.require(request('GET',prefix+'/users/'+subject)['attributes']['organization_id']==['org-other'],'ORG_CHANGE_NOT_OBSERVED')
        rt.update_runtime(m,httpScenario='cross-org-secret',foreignSecretRef=ref,foreignSecretOwnerSubjectId=subject)
        run.consumer(m,'http',scenario='cross-org-secret')
        observed=reports(m,'http-cross-org-secret')
        unused=sql(m,'BEGIN READ ONLY; SELECT count(*) FROM connections."ConnectionSecrets" WHERE "Id"=\''+ref+'\' AND "UsedAtUtc" IS NULL AND "OrganizationId"=\'org-demo\'; COMMIT;')
        rt.require(unused=='1','CROSS_ORG_SECRET_CONSUMED')
        result.update(status='PASS',originalReferenceUnused=True,subjectSha256=rt.digest(subject.encode()),referenceSha256=rt.digest(ref.encode()))
    finally:
        if original is not None:
            request('PUT',prefix+'/users/'+subject,original)
            rt.require(request('GET',prefix+'/users/'+subject)['attributes']==original['attributes'],'ORG_NOT_RESTORED')
        request('PUT',prefix+'/users/profile',profile)
        rt.require(request('GET',prefix+'/users/profile')==profile,'PROFILE_NOT_RESTORED')
        result['restored']=True
        if guard.poll() is None:guard.terminate();guard.wait(timeout=5)
        result['restoreGuardExitCode']=guard.returncode
        rt.write_json(rt.ARTIFACTS/m['runId']/'cross-org.json',result)
    action(m,'original-identity-check','cross-org-restored')
    return result


def browser_cancel(m):
    """浏览器发起/取消真实任务；独立观察源worker消失后才释放源锁。"""
    import threading
    rt.update_runtime(m,scenario='catalog-cancel',catalogCancelHandshake=True)
    action(m,'probe-refresh','ui-cancel-probe')
    observed={};watcher=None;held=None;job=None
    with SourceSession(m) as observer,SourceSession(m) as source_lock,SourceSession(m,source=False) as claim:
        observer.query("SET statement_timeout='2s'; SET idle_session_timeout='45s'; SET plan_cache_mode=force_generic_plan; PREPARE ui_cancel_activity AS SELECT coalesce(json_agg(json_build_object('pid',pid,'wait',wait_event_type)),'[]') FROM pg_stat_activity WHERE usename='fixture_reader'; EXECUTE ui_cancel_activity;")
        observer.query("PREPARE ui_cancel_lock(int) AS SELECT count(*) FROM pg_locks WHERE pid=$1 AND relation='pg_catalog.pg_shdepend'::regclass AND mode='AccessExclusiveLock' AND granted; EXECUTE ui_cancel_lock(-1);")
        def callback(value):
            nonlocal held,job,watcher
            if value['event']=='CATALOG_CANCEL_READY':
                claim.query("SET statement_timeout='10s'; SET idle_in_transaction_session_timeout='10s'; SET lock_timeout='2s'; BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('connection:catalog-claim',0)); END $$; SELECT true;")
                held=source_lock.query("SET statement_timeout='15s'; SET idle_in_transaction_session_timeout='15s'; SET lock_timeout='2s'; BEGIN; LOCK TABLE pg_catalog.pg_shdepend IN ACCESS EXCLUSIVE MODE; SELECT json_build_object('pid',pg_backend_pid(),'held',true);")
                return 'SOURCE_LOCKED'
            rt.require(value['event']=='CATALOG_JOB_STARTED','UI_CANCEL_EVENT')
            job=identifier(value['jobId']);rt.update_runtime(m,httpJobId=job)
            baseline=observer.query('EXECUTE ui_cancel_activity;');baseline_pids={x['pid'] for x in baseline}
            claim.query('ROLLBACK; SELECT true;')
            deadline=time.monotonic()+3
            while True:
                source=observer.query('EXECUTE ui_cancel_activity;')
                workers=[x for x in source if x['pid'] not in baseline_pids and x['wait']=='Lock']
                if len(workers)==1:break
                rt.require(time.monotonic()<deadline,'UI_CANCEL_WORKER_NOT_ISOLATED');time.sleep(.03)
            observed.update(before=source,workerPid=workers[0]['pid'],jobId=job)
            def watch():
                try:
                    deadline=time.monotonic()+5
                    while True:
                        after=observer.query('EXECUTE ui_cancel_activity;')
                        if not any(x['pid']==observed['workerPid'] for x in after):break
                        rt.require(time.monotonic()<deadline,'UI_CANCEL_SOURCE_NOT_CANCELLED');time.sleep(.03)
                    rt.require(observer.query('EXECUTE ui_cancel_lock('+str(int(held['pid']))+');')==1,'UI_SOURCE_LOCK_EARLY_RELEASE')
                    observed.update(after=after,sourceLockHeldAtBackendDisappearance=True)
                except Exception as error:observed['failure']=type(error).__name__
                finally:source_lock.query('ROLLBACK; SELECT true;')
            watcher=threading.Thread(target=watch,daemon=True);watcher.start()
            return 'SOURCE_QUERY_WAITING'
        try:
            report=run_interactive(m,'browser','catalog-cancel',callback,timeout=90)
            if watcher:watcher.join(timeout=7)
            rt.require(watcher is not None and not watcher.is_alive() and 'failure' not in observed and observed.get('sourceLockHeldAtBackendDisappearance'),'UI_SOURCE_CANCEL_WITNESS')
            rt.require(report['cancelObservation']['terminalStatus']=='CANCELLED' and report['cancelObservation']['snapshotAbsent'],'UI_CANCEL_TERMINAL')
        finally:rt.update_runtime(m,catalogCancelHandshake=False)
    final=action(m,'job-read','ui-cancel-final');rt.require(final['jobStatus']=='CANCELLED','UI_CANCEL_DURABLE')
    result={'status':'PASS','source':observed,'durable':final};rt.write_json(rt.ARTIFACTS/m['runId']/'browser-cancel-source.json',result);return result


def schema_change(m):
    """真实无业务行DDL与不可变旧Snapshot，再读投影必须STALE。"""
    import run
    r=rt.runtime_value(m);old=identifier(r['httpSnapshotId'])
    expression='SELECT md5("ViewJson") FROM connections."CatalogSnapshots" WHERE "Id"=\''+old+'\';'
    before=sql(m,'BEGIN READ ONLY; '+expression+' COMMIT;');rt.require(re.fullmatch('[a-f0-9]{32}',before),'SNAPSHOT_MISSING')
    sql(m,'ALTER TABLE production.heat_event ADD COLUMN recovery_extra integer;',source=True)
    try:
        run.consumer(m,'http',scenario='schema-change')
        report=reports(m,'http-schema-change')
        after=sql(m,'BEGIN READ ONLY; '+expression+' COMMIT;')
        rt.require(before==after,'OLD_SNAPSHOT_MUTATED')
        new=identifier(report['fixtures']['snapshotId']);rt.require(new!=old,'NEW_SNAPSHOT_REQUIRED')
        result={'status':'PASS','oldSnapshotId':old,'newSnapshotId':new,'oldViewBeforeHash':before,'oldViewAfterHash':after,'httpReportSha256':rt.digest(json.dumps(report).encode())}
    finally:sql(m,'ALTER TABLE production.heat_event DROP COLUMN recovery_extra;',source=True)
    rt.write_json(rt.ARTIFACTS/m['runId']/'schema-immutability.json',result);return result


def purpose_fault(m):
    """实际已签发未绑定Ref只变用途，真实HTTP拒绝且源IO和密文均不变。"""
    private=rt.private_dir(m['runId']);issued=json.loads((private/'lifecycle-refs.json').read_text());ref=identifier(issued['purposeSecretRef'])
    def state():
        return json.loads(sql(m,'BEGIN READ ONLY; SELECT json_build_object(\'purpose\',"Purpose",\'unused\',"UsedAtUtc" IS NULL AND "ConnectionId" IS NULL,\'unexpired\',"ExpiresAtUtc">now(),\'cipherHash\',md5("Ciphertext"||"Nonce"||"Tag")) FROM connections."ConnectionSecrets" WHERE "Id"=\''+ref+'\'; COMMIT;'))
    restore='UPDATE connections."ConnectionSecrets" SET "Purpose"=\'POSTGRESQL_READONLY\' WHERE "Id"=\''+ref+'\' AND "Purpose"=\'MAIN_WRONG_PURPOSE\' AND "UsedAtUtc" IS NULL;'
    before=state();rt.require(before['unused'] and before['unexpired'] and before['purpose']=='POSTGRESQL_READONLY','PURPOSE_BASELINE')
    # 故障持有期间独立子进程超时恢复；秘密Ref仅在私有文件/子进程stdin。
    platform=rt.runtime_value(m)['containerIds']['platform-pg']
    script=r'''import json,sys,pathlib,subprocess,time,re
private,ident,task,run=sys.argv[1:];time.sleep(20)
base=['docker','--context','desktop-linux'];item=json.loads(subprocess.check_output(base+['inspect',ident],timeout=5))[0]
assert item['Id']==ident and item['Config']['Labels']['ontology.task-id']==task and item['Config']['Labels']['ontology.run-id']==run
ref=json.loads((pathlib.Path(private)/'lifecycle-refs.json').read_text())['purposeSecretRef'];assert re.fullmatch('[a-f0-9]{32}',ref)
sql=f"""SET statement_timeout='5s';UPDATE connections."ConnectionSecrets" SET "Purpose"='POSTGRESQL_READONLY' WHERE "Id"='{ref}' AND "Purpose"='MAIN_WRONG_PURPOSE' AND "UsedAtUtc" IS NULL;"""
subprocess.run(base+['exec','-i',ident,'psql','-U','platform','-d','platform','-qAt','-v','ON_ERROR_STOP=1'],input=sql.encode(),capture_output=True,check=True,timeout=8)
'''
    # Guard只执行本驱动构造的固定SQL，从私有文件取得准确引用。
    guard=subprocess.Popen([__import__('sys').executable,'-B','-c',script,str(private),platform,rt.TASK,m['runId']],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    source=rt.runtime_value(m)['containerIds']['pg-source']
    rt.require(sql(m,"SELECT count(*) FROM pg_stat_activity WHERE usename='fixture_reader';",source=True)=='0','ACTIVE_READER_BEFORE_PURPOSE')
    logs_before=rt.execute(m,'source-before-purpose',['docker','--context','desktop-linux','logs',source],sensitive=True)
    result={'status':'FAIL','guardPid':guard.pid,'guardScriptSha256':rt.digest(script.encode())}
    try:
        count=sql(m,'WITH changed AS (UPDATE connections."ConnectionSecrets" SET "Purpose"=\'MAIN_WRONG_PURPOSE\' WHERE "Id"=\''+ref+'\' AND "UsedAtUtc" IS NULL AND "Purpose"=\'POSTGRESQL_READONLY\' RETURNING 1) SELECT count(*) FROM changed;')
        rt.require(count=='1','EXACT_PURPOSE_FAULT')
        http=action(m,'purpose-denial','purpose-denial')
        after=state();rt.require(after['unused'] and after['unexpired'] and after['cipherHash']==before['cipherHash'],'PURPOSE_ROW_CHANGED')
        logs_after=rt.execute(m,'source-after-purpose',['docker','--context','desktop-linux','logs',source],sensitive=True)
        reader_io=require_no_reader_io(m,logs_before,logs_after)
        result.update(status='PASS',before=before,after=after,http=http,sourceIoUnchanged=True,readerIo=reader_io)
    finally:
        sql(m,restore);rt.require(state()==before,'PURPOSE_NOT_RESTORED')
        if guard.poll() is None:guard.terminate();guard.wait(timeout=5)
        result['guardExitCode']=guard.returncode;result['restored']=True
        rt.write_json(rt.ARTIFACTS/m['runId']/'purpose-fault.json',result)
    return result
