#!/usr/bin/env python3
"""只读核对 G4 基线 HTTP 与持久连接、探针、任务、快照和审计的关联。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

TASK = "G4-M1-RECOVERY-001"
PROJECT = "ontology-g4-m1-recovery-001"
ROOT = Path(__file__).resolve().parents[2]
MODULE = "backend/src/Modules/Connections/OntologyPlatform.Modules.Connections"
SOURCES = [
    f"{MODULE}/Application/ConnectionApplicationService.cs",
    f"{MODULE}/Application/ConnectionApplicationService.Probes.cs",
    f"{MODULE}/Application/ConnectionApplicationService.Worker.cs",
    "backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs",
    "backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs",
]
ACTIONS = ["connection.create", "connection.probe.start", "connection.probe.complete",
           "connection.catalog.start", "connection.catalog.finish", "connection.enable", "connection.disable"]
CLOCK_TOLERANCE = dt.timedelta(seconds=2)


class WitnessError(Exception):
    """仅携带固定安全错误码，不携带数据库或进程错误正文。"""


def require(condition: bool, code: str) -> None:
    """遇到证据缺口立即失败，不能把未知字段或空查询提升为通过。"""
    if not condition:
        raise WitnessError(code)


def digest(data: bytes) -> str:
    """计算公开输入或安全投影的 SHA256。"""
    return hashlib.sha256(data).hexdigest()


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


def evidence_path(value: str, exists: bool) -> Path:
    """限制输入输出为当前树任务证据目录，拒绝私有运行配置和符号链接。"""
    path = Path(value).absolute()
    require(".." not in path.parts, "evidence_parent_traversal_denied")
    roots = [ROOT / "artifacts/g4-m1-recovery-001", ROOT / "docs/evidence" / TASK]
    require(any(path.is_relative_to(base) for base in roots), "evidence_path_outside_task")
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        require(not parent.is_symlink(), "evidence_symlink_denied")
    require(not exists or path.is_file(), "evidence_input_missing")
    return path


def execute(command: list[str], report: dict, sql: str | None = None) -> object:
    """仅执行固定 inspect/psql，期限和输出大小受限，错误原文不进入报告。"""
    record = {"command": command, "timeoutSeconds": 12, "startedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat()}
    if sql is not None:
        record.update(sql=sql, sqlSha256=digest(sql.encode()))
    report["commands"].append(record)
    try:
        result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=12, check=False)
    except subprocess.TimeoutExpired as error:
        record.update(exitCode=None, failure="command_timeout")
        raise WitnessError("command_timeout") from error
    record.update(exitCode=result.returncode, stdoutBytes=len(result.stdout.encode()), stderrBytes=len(result.stderr.encode()))
    require(result.returncode == 0, "command_failed")
    require(len(result.stdout.encode()) <= 524288, "projection_output_limit")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise WitnessError("projection_json_invalid") from error


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


def main() -> int:
    """Master 明确传入准确平台容器和公开报告，执行器只读取并生成唯一安全回执。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", required=True)
    parser.add_argument("--platform-container", required=True, help="准确 64 位 Docker ID，禁止名称或缩写")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-file", required=True, help="本树任务 evidence/artifacts 下的新 JSON 文件；拒绝覆盖")
    args = parser.parse_args()
    report = {"taskId": TASK, "caseId": "M1-C12", "status": "FAIL", "commands": [], "checks": [], "clockToleranceSeconds": 2, "sourceSha256": digest(Path(__file__).read_bytes()), "limitations": ["Only selected baseline lineage; no raw HTTP response reconstruction or secret/audit-detail reads."]}
    output = None
    try:
        output = evidence_path(args.output_file, False)
        require(output.parent.is_dir() and not output.exists(), "output_parent_or_exclusivity_invalid")
        baseline_path = evidence_path(args.baseline_report, True)
        require(baseline_path.stat().st_size <= 2097152, "baseline_size_limit")
        baseline_bytes = baseline_path.read_bytes()
        baseline = json.loads(baseline_bytes)
        require(baseline.get("taskId") == TASK and baseline.get("scenario") == "baseline" and baseline.get("productExecution") is True and baseline.get("exitCode") == 2 and not baseline.get("failure"), "baseline_not_successful_partial_product_run")
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id) is not None and baseline.get("runId") == args.run_id, "run_id_mismatch")
        container_id = identifier(args.platform_container, 64)
        fixtures = {key: identifier(baseline["fixtures"][key]) for key in ["connectionId", "probeId", "jobId", "snapshotId"]}
        # 旧报告 status 被业务枚举覆盖时，使用明确 expectedStatus 或成功状态；禁止选 GET 的新 trace。
        routes = {"/api/v1/connections", "/api/v1/connections/{id}/test", "/api/v1/connections/{id}/discoveries", "/api/v1/connections/{id}/disable"}
        posts = []
        for row in baseline["http"]:
            if row.get("method") == "POST" and row.get("route") in routes and (row.get("status") in [200, 201, 202, "TEST_OK", "QUEUED"]):
                posts.append({key: row[key] for key in ["index", "route", "traceId", "startedAtUtc", "durationMs"]})
        require(0 < len(posts) <= 32, "post_selection_count_invalid")
        for row in posts:
            identifier(row["traceId"]); timestamp(row["startedAtUtc"])
            require(type(row["index"]) is int and row["index"] >= 0, "http_index_invalid")
            require(type(row["durationMs"]) is int and 0 <= row["durationMs"] <= 30000, "http_duration_invalid")
        report.update(runId=args.run_id, baselineSha256=digest(baseline_bytes), fixtures=fixtures, originalPosts=posts,
                      sourceInputs={name: digest((ROOT / name).read_bytes()) for name in SOURCES})
        fmt = '{"id":{{json .Id}},"name":{{json .Name}},"taskId":{{json (index .Config.Labels "ontology.task-id")}},"runId":{{json (index .Config.Labels "ontology.run-id")}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"running":{{json .State.Running}},"paused":{{json .State.Paused}}}'
        identity = execute(["docker", "--context", "desktop-linux", "inspect", "--format", fmt, container_id], report)
        require(identity == {"id": container_id, "name": "/ontology-g4-m1-recovery-001-platform-pg-1", "taskId": TASK, "runId": args.run_id, "project": PROJECT, "service": "platform-pg", "running": True, "paused": False}, "platform_container_identity_mismatch")
        report["platformIdentity"] = identity
        sql = build_sql(fixtures, [row["traceId"] for row in posts])
        projection = execute(["docker", "--context", "desktop-linux", "exec", "-i", container_id, "psql", "-X", "-qAt", "-U", "platform", "-d", "platform", "-v", "ON_ERROR_STOP=1", "-f", "-"], report, sql)
        validate_projection(projection)
        report["projection"] = projection
        compare(projection, posts, fixtures, report)
        report["status"] = "PASS"
    except (WitnessError, OSError, ValueError, KeyError, TypeError) as error:
        report["failureCode"] = str(error) if isinstance(error, WitnessError) else "input_or_execution_shape_error"
    report["completedAtUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    if output is not None and output.parent.is_dir() and not output.exists():
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps({"taskId": TASK, "caseId": "M1-C12", "status": report["status"], "failureCode": report.get("failureCode")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
