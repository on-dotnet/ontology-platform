#!/usr/bin/env python3
"""仅本任务平台库的固定审计故障与作业fence验证控制面。"""
import argparse
import json
import re
import subprocess
from pathlib import Path
import workflow_execution as execution

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M2-ORACLE-01'


def control(path, mode, job=None):
    """准确ID/标签/端口核对后，仅操作本任务已有平台库；不接受任意SQL。"""
    path = execution.ordinary(path)
    if not path.is_relative_to(ROOT / 'artifacts/workflow' / TASK) or mode not in ('audit-on', 'audit-off', 'job-fence', 'job-state'):
        raise ValueError('ORACLE_PLATFORM_BOUNDARY')
    source = json.loads(path.read_text())
    ident = source['containers']['platform-pg']['id']
    if source.get('taskId') != TASK or not re.fullmatch('[a-f0-9]{64}', ident):
        raise ValueError('ORACLE_PLATFORM_IDENTITY')
    docker = ['docker', '--context', 'desktop-linux']
    row = json.loads(subprocess.check_output(docker + ['inspect', ident], timeout=5))[0]
    if row['Id'] != ident or row['Config']['Labels'].get('ontology.task') != TASK or row['Config']['Labels'].get('ontology.run') != source['runId'] or not row['State']['Running']:
        raise ValueError('ORACLE_PLATFORM_IDENTITY')
    if row['HostConfig']['PortBindings'] != {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '15432'}]}:
        raise ValueError('ORACLE_PLATFORM_PORTS')
    if mode.startswith('job-') and not re.fullmatch('[a-f0-9]{32}', job or ''):
        raise ValueError('ORACLE_JOB_ID')
    statements = {
        'audit-on': '''BEGIN; CREATE FUNCTION governance.g4_oracle_audit_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW."Action" = 'connection.enable' THEN RAISE EXCEPTION 'G4_ORACLE_SYNTHETIC_AUDIT_FAILURE'; END IF; RETURN NEW; END $$;
CREATE TRIGGER g4_oracle_audit_fault BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.g4_oracle_audit_fault(); COMMIT;''',
        "audit-off": "BEGIN; DROP TRIGGER IF EXISTS g4_oracle_audit_fault ON governance.audit_records; DROP FUNCTION IF EXISTS governance.g4_oracle_audit_fault(); COMMIT; SELECT json_build_object('triggerAbsent',NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='g4_oracle_audit_fault' AND tgrelid='governance.audit_records'::regclass),'functionAbsent',NOT EXISTS(SELECT 1 FROM pg_proc WHERE proname='g4_oracle_audit_fault' AND pronamespace='governance'::regnamespace));",
        'job-fence': f'''UPDATE connections."CatalogJobs" SET "Fence"="Fence"+1, "LeaseUntil"=now()-interval '1 second' WHERE "Id"='{job}' AND "Status"='RUNNING';''',
        'job-state': f'''SELECT json_build_object('status',"Status",'snapshotId',"SnapshotId",'fence',"Fence") FROM connections."CatalogJobs" WHERE "Id"='{job}';'''
    }
    result = subprocess.run(docker + ['exec', '-i', ident, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'platform', '-d', 'platform'], input=statements[mode].encode(), capture_output=True, timeout=10)
    value = dict(taskId=TASK, runId=source['runId'], mode=mode, exitCode=result.returncode)
    if mode == 'audit-off' and result.returncode == 0:
        value['cleanup'] = json.loads(result.stdout)
        if not all(value['cleanup'].values()):
            raise ValueError('ORACLE_FAULT_CLEANUP_FAILED')
    if mode == 'job-state' and result.returncode == 0:
        value['job'] = json.loads(result.stdout)
    if result.returncode != 0:
        raise ValueError('ORACLE_PLATFORM_CONTROL_FAILED')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--mode', required=True, choices=('audit-on', 'audit-off', 'job-fence', 'job-state'))
    parser.add_argument('--job')
    args = parser.parse_args()
    try:
        print(json.dumps(control(args.runtime, args.mode, args.job)))
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        print(json.dumps(dict(taskId=TASK, status='FAIL', reason='ORACLE_PLATFORM_CONTROL_REFUSED')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
