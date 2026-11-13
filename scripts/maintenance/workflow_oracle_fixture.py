#!/usr/bin/env python3
"""Oracle本任务固定控制面；不接受任意SQL、目标或跨任务runtime。"""
import argparse
import json
from pathlib import Path
import re
import subprocess

import workflow_execution as execution

ROOT = Path(__file__).resolve().parents[2]
TASK = 'G4-M2-ORACLE-01'
IMAGE = 'sha256:844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8'
COMMANDS = {
    'active-reader': "SELECT JSON_OBJECT('sid' VALUE SID, 'serial' VALUE SERIAL#, 'status' VALUE STATUS, 'event' VALUE EVENT) FROM V$SESSION WHERE USERNAME='FIXTURE_READER' AND MODULE='G4-M2-ORACLE-01';",
    'delay-on': 'UPDATE G4_CONTROL.DELAY_CONTROL SET SECONDS=10 WHERE ID=1;\nCOMMIT;',
    'delay-off': 'UPDATE G4_CONTROL.DELAY_CONTROL SET SECONDS=0 WHERE ID=1;\nCOMMIT;',
    'revoke-read': 'REVOKE READ ON "CaseOwner"."MixedCase" FROM FIXTURE_READER;',
    'restore-read': 'GRANT READ ON "CaseOwner"."MixedCase" TO FIXTURE_READER;',
    'readonly-off': 'ALTER USER FIXTURE_READER READ WRITE;',
    'readonly-on': 'ALTER USER FIXTURE_READER READ ONLY;',
    'column-on': 'GRANT UPDATE ("TextValue") ON "CaseOwner"."MixedCase" TO FIXTURE_READER;',
    'column-off': 'REVOKE UPDATE ON "CaseOwner"."MixedCase" FROM FIXTURE_READER;',
    'role-on': 'CREATE ROLE G4_NEGATIVE_ROLE;\nGRANT G4_NEGATIVE_ROLE TO FIXTURE_READER;',
    'role-off': 'REVOKE G4_NEGATIVE_ROLE FROM FIXTURE_READER;\nDROP ROLE G4_NEGATIVE_ROLE;',
}


def load_source(path):
    """先核验路径和任务身份，再允许Docker只读核对。"""
    path = execution.ordinary(path)
    if not path.is_relative_to(ROOT / 'artifacts/workflow' / TASK):
        raise ValueError('ORACLE_RUNTIME_BOUNDARY')
    value = json.loads(path.read_text())
    if value.get('taskId') != TASK or not re.fullmatch('[a-f0-9]{64}', value.get('containerId', '')) or not re.fullmatch('oracle-[a-z0-9-]+', value.get('runId', '')):
        raise ValueError('ORACLE_RUNTIME_IDENTITY')
    return value


def control(path, mode):
    """只对准确已运行合成源执行登记的权限/等待负例。"""
    if mode not in COMMANDS:
        raise ValueError('ORACLE_CONTROL_MODE')
    source = load_source(path)
    docker = ['docker', '--context', 'desktop-linux']
    row = json.loads(subprocess.check_output(docker + ['inspect', source['containerId']], timeout=5))[0]
    labels = row['Config']['Labels']
    if row['Id'] != source['containerId'] or row['Image'] != IMAGE or labels.get('ontology.task') != TASK or labels.get('ontology.run') != source['runId'] or not row['State']['Running']:
        raise ValueError('ORACLE_SOURCE_IDENTITY')
    if row['HostConfig']['PortBindings'] or not 0 < row['HostConfig']['Memory'] <= 4 * 1024**3 or not 0 < row['HostConfig']['NanoCpus'] <= 2_000_000_000 or row['HostConfig']['Privileged']:
        raise ValueError('ORACLE_SOURCE_BOUNDARY')
    networks = row['NetworkSettings']['Networks']
    if len(networks) != 1 or set(networks) != set(source['networks']):
        raise ValueError('ORACLE_SOURCE_NETWORK')
    network = json.loads(subprocess.check_output(docker + ['network', 'inspect', next(iter(networks))], timeout=5))[0]
    if not network['Internal'] or network['Labels'].get('ontology.task') != TASK:
        raise ValueError('ORACLE_SOURCE_NETWORK')
    if any(mount['Type'] == 'bind' and (mount['Source'].endswith('.sock') or mount['Destination'].endswith('.sock')) for mount in row['Mounts']):
        raise ValueError('ORACLE_SOURCE_SOCKET')
    text = 'SET ECHO OFF FEEDBACK OFF HEADING OFF PAGES 0 LINES 32767 TRIMSPOOL ON\nWHENEVER SQLERROR EXIT FAILURE ROLLBACK\nALTER SESSION SET CONTAINER=FREEPDB1;\n' + COMMANDS[mode] + '\nEXIT\n'
    result = subprocess.run(docker + ['exec', '-i', row['Id'], 'sqlplus', '-s', '/ as sysdba'], input=text.encode(), capture_output=True, timeout=15)
    # 固定控制SQL没有密码；对外只输出结构化状态，不输出任何源端正文。
    value = dict(taskId=TASK, runId=source['runId'], mode=mode, exitCode=result.returncode, status='CONTROL_APPLIED' if result.returncode == 0 else 'FAIL')
    if mode == 'active-reader' and result.returncode == 0:
        sessions = [json.loads(line) for line in result.stdout.decode().splitlines() if line.strip()]
        value['sessions'] = sessions
        value['allSourceIds'] = [str(row['sid']) + ':' + str(row['serial']) for row in sessions]
        value['sourceIds'] = [str(row['sid']) + ':' + str(row['serial']) for row in sessions if row['status'] == 'ACTIVE' and row['event'] == 'PL/SQL lock timer']
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('control',))
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--mode', required=True, choices=tuple(COMMANDS))
    args = parser.parse_args()
    try:
        value = control(args.runtime, args.mode)
        print(json.dumps(value))
        return 0 if value['exitCode'] == 0 else 2
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print(json.dumps(dict(taskId=TASK, status='FAIL', reason='ORACLE_CONTROL_REFUSED')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
