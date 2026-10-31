#!/usr/bin/env python3
"""Record bounded task metadata and actual command intervals, never command arguments or output."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

FIELDS = {'schemaVersion', 'taskId', 'runId', 'stepId', 'taskType', 'inputFingerprint',
          'startedAtUtc', 'endedAtUtc', 'durationMs', 'outcome', 'errorCategory', 'dependsOn',
          'concurrencyGroup', 'attempt', 'exitCode', 'commandLabel'}
TYPES = {'PREFLIGHT', 'IMPLEMENTATION', 'BUILD', 'TEST', 'CI', 'REVIEW', 'CLEANUP', 'PACKAGE', 'WAIT', 'REWORK'}
OUTCOMES = {'PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'}
TIMING = {'VALID', 'CLOCK_DRIFT', 'NOT_RUN'}
IDENTITY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')


def utc(value):
    """Accept explicit UTC only; a local timestamp is not a recorded UTC observation."""
    if not isinstance(value, str) or not value.endswith(('Z', '+00:00')):
        raise ValueError('UTC timestamp required')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError('UTC timestamp required')
    return parsed


def timing_status(row):
    """旧记录保持原字节；仅推导其计时分类，不修写历史执行结果。"""
    if row['schemaVersion'] == 2:
        return row['timingStatus']
    if row['outcome'] == 'NOT_RUN':
        return 'NOT_RUN'
    return 'CLOCK_DRIFT' if row['errorCategory'] == 'CLOCK_DRIFT' else 'VALID'


def complete(row, ended_at_utc, duration_ms, exit_code, error_category=None):
    """统一记录真实退出与独立计时有效性；不钳制墙钟、不推定睡眠原因。"""
    finished = {**row, 'schemaVersion': 2, 'endedAtUtc': ended_at_utc,
                'durationMs': duration_ms, 'exitCode': exit_code,
                'outcome': 'PASS' if exit_code == 0 else 'FAIL',
                'errorCategory': error_category if error_category is not None else
                                 (None if exit_code == 0 else 'COMMAND_FAILED')}
    start, end = utc(finished['startedAtUtc']), utc(ended_at_utc)
    finished['timingStatus'] = ('CLOCK_DRIFT' if end < start or
        abs((end-start).total_seconds()*1000-duration_ms) > 1000 else 'VALID')
    return finished


def validate(rows):
    """Reject schema drift, invalid exits, duplicate identities and impossible dependency order."""
    known, attempts = {}, {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get('schemaVersion')) is not int or row['schemaVersion'] not in (1, 2) or set(row) != (FIELDS if row['schemaVersion'] == 1 else FIELDS | {'timingStatus'}):
            raise ValueError('Timeline schema mismatch')
        if not all(isinstance(row[key], str) and IDENTITY.fullmatch(row[key])
                   for key in ('taskId', 'runId', 'stepId', 'concurrencyGroup', 'commandLabel')):
            raise ValueError('Invalid controlled identity/label')
        if row['taskType'] not in TYPES or row['outcome'] not in OUTCOMES:
            raise ValueError('Invalid task type/outcome')
        if not isinstance(row['inputFingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', row['inputFingerprint']):
            raise ValueError('Input SHA256 required')
        if type(row['durationMs']) is not int or row['durationMs'] < 0:
            raise ValueError('Invalid measured duration')
        start, end = utc(row['startedAtUtc']), utc(row['endedAtUtc'])
        drift = end < start or abs((end-start).total_seconds()*1000-row['durationMs']) > 1000
        if row['schemaVersion'] == 1:
            if end < start or (row['errorCategory'] != 'CLOCK_DRIFT' and drift):
                raise ValueError('Clock and monotonic duration disagree')
        elif row['timingStatus'] not in TIMING:
            raise ValueError('Invalid timing status')
        elif row['outcome'] == 'NOT_RUN':
            if row['timingStatus'] != 'NOT_RUN':
                raise ValueError('Unexecuted step has no timing interval')
        elif row['timingStatus'] != ('CLOCK_DRIFT' if drift else 'VALID'):
            raise ValueError('Timing status must reflect measured clock difference')
        if row['schemaVersion'] == 2 and row['errorCategory'] == 'CLOCK_DRIFT':
            raise ValueError('Clock drift is timing metadata, not a command error')
        code = row['exitCode']
        if code is not None and type(code) is not int:
            raise ValueError('Invalid exit code')
        category = row['errorCategory']
        if category is not None and (not isinstance(category, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', category)):
            raise ValueError('Invalid controlled error category')
        if row['outcome'] == 'PASS' and (code != 0 or category is not None):
            raise ValueError('PASS requires actual exit zero without failure')
        if row['outcome'] == 'FAIL' and (code == 0 or code is None and category is None):
            raise ValueError('FAIL requires a failure exit or exception category')
        if row['outcome'] == 'BLOCKED' and code == 0:
            raise ValueError('BLOCKED is not exit-zero success')
        if row['outcome'] == 'NOT_RUN' and (code is not None or row['durationMs'] != 0 or start != end):
            raise ValueError('NOT_RUN has no executed interval')
        identity = (row['taskId'], row['runId'], row['stepId'])
        if identity in known:
            raise ValueError('Duplicate step identity')
        if not isinstance(row['dependsOn'], list) or len(set(row['dependsOn'])) != len(row['dependsOn']):
            raise ValueError('Invalid dependency list')
        for dependency in row['dependsOn']:
            key = (row['taskId'], row['runId'], dependency)
            if key not in known or (timing_status(known[key]) == 'VALID' and timing_status(row) == 'VALID'
                                    and utc(known[key]['endedAtUtc']) > start):
                raise ValueError('Unknown, cyclic or unfinished dependency')
        attempt_key = (row['taskId'], row['taskType'], row['commandLabel'], row['inputFingerprint'])
        expected = attempts.get(attempt_key, 0) + 1
        if type(row['attempt']) is not int or row['attempt'] != expected:
            raise ValueError('Attempt must reflect actual recorded rechecks')
        attempts[attempt_key] = expected
        known[identity] = row
    return rows


def summarize(rows, host_evidence=None):
    """Report span, union, cumulative runtime, overlap and only the observable dependency path."""
    validate(rows)
    executed = [row for row in rows if row['outcome'] != 'NOT_RUN']
    valid = [row for row in executed if timing_status(row) == 'VALID']
    drift_count = len(executed)-len(valid)
    intervals = sorted((utc(row['startedAtUtc']).timestamp()*1000, utc(row['endedAtUtc']).timestamp()*1000)
                       for row in valid)
    union, final = 0, None
    for start, end in intervals:
        union += max(0, end-max(start, final if final is not None else start))
        final = max(end, final if final is not None else end)
    cumulative = sum(row['durationMs'] for row in executed)
    valid_cumulative = sum(row['durationMs'] for row in valid)
    critical, counts, categories = {}, {}, {}
    for row in rows:
        key = (row['taskId'], row['runId'], row['stepId'])
        critical[key] = row['durationMs'] + max((critical[(row['taskId'], row['runId'], dep)] for dep in row['dependsOn']), default=0)
        counts[row['taskType']] = counts.get(row['taskType'], 0) + row['durationMs']
        if row['errorCategory']:
            categories[row['errorCategory']] = categories.get(row['errorCategory'], 0) + 1
    span = round(max((end for _, end in intervals), default=0)-min((start for start, _ in intervals), default=0))
    result = dict(schemaVersion=2, stepCount=len(rows), wallClockMs=span if not drift_count else None,
                validIntervalSpanMs=span, observedIntervalUnionMs=round(union),
                cumulativeTaskMs=cumulative, validIntervalCumulativeMs=valid_cumulative,
                overlapMs=max(0, valid_cumulative-round(union)), clockDriftCount=drift_count,
                timingStatus='CLOCK_DRIFT' if drift_count else 'VALID',
                confirmedSleepMs='UNKNOWN', nonSleepWallMs='UNKNOWN', humanWaitingTime='UNKNOWN',
                observableCriticalPathMs=max(critical.values(), default=0),
                recheckCount=sum(row['attempt'] > 1 for row in rows), taskTypeDurationMs=counts,
                failureCategories=categories, agentActiveTime='UNKNOWN', agentThinkingTime='UNKNOWN',
                limitations='UTC union/overlap use valid intervals only; critical path uses measured monotonic durations and declared dependencies. Sleep causality, chat, model cost and unobserved activity are not inferred.')
    if host_evidence is not None:
        result['hostSleepObservation'] = host_sleep_observation(host_evidence)
    return result


def host_sleep_observation(path):
    """有界读取独立宿主证据；只报告其窗口，不将漂移等价于睡眠或扣减异窗时间。"""
    path = ordinary(path)
    if not path.is_file() or path.stat().st_size > 1024*1024:
        raise ValueError('Bounded host evidence required')
    raw = path.read_bytes()
    value = json.loads(raw)
    start, end = utc(value['startedAtUtc']), utc(value['endedAtUtc'])
    sleep = value['sleep']
    if value['schemaVersion'] != 1 or end < start or not isinstance(sleep, dict):
        raise ValueError('Invalid host observation window')
    if sleep.get('status') != 'OBSERVED_LOG_WINDOW':
        return dict(status='NOT_VERIFIED', evidenceSha256=hashlib.sha256(raw).hexdigest())
    duration = sleep.get('confirmedSleepMs')
    if type(duration) is not int or duration < 0 or duration > (end-start).total_seconds()*1000:
        raise ValueError('Sleep duration outside observed host window')
    events = sleep.get('events')
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError('Bounded sleep event list required')
    for event in events:
        if set(event) != {'utc', 'kind', 'idleSleep'} or event['kind'] not in {'Sleep', 'Wake', 'DarkWake'} or type(event['idleSleep']) is not bool or not start <= utc(event['utc']) <= end:
            raise ValueError('Invalid observed sleep event')
    return dict(status='OBSERVED_LOG_WINDOW', evidenceSha256=hashlib.sha256(raw).hexdigest(),
                startedAtUtc=start.isoformat(), endedAtUtc=end.isoformat(), confirmedSleepMs=duration,
                nonSleepWindowMs=round((end-start).total_seconds()*1000)-duration,
                events=events, clockDriftCause='UNKNOWN',
                limitation='Independent host window; not subtracted from command timeline span.')


def ordinary(path):
    """Refuse symlink ancestors and files before opening or creating a timeline."""
    path = Path(path).absolute()
    if any(item.is_symlink() for item in [path, *path.parents]):
        raise ValueError('Linked timeline path refused')
    if path.exists() and (not path.is_file() or path.stat().st_size > 16*1024*1024):
        raise ValueError('Invalid or oversized timeline')
    return path


def read(path):
    path = ordinary(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('Truncated timeline line')
    return validate([json.loads(line) for line in raw.decode('utf-8').splitlines()])


def append(path, row, assign_attempt=False):
    """Serialize writers, validate the complete history and append exactly one durable JSON line."""
    path = ordinary(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(path)+'.lock')
    ordinary(lock)
    deadline = time.monotonic()+5
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError('Timeline writer lock busy or stale') from None
            time.sleep(.02)
    try:
        previous = read(path)
        if assign_attempt:
            row['attempt'] = 1 + sum(old['taskId'] == row['taskId'] and old['taskType'] == row['taskType']
                and old['commandLabel'] == row['commandLabel'] and old['inputFingerprint'] == row['inputFingerprint']
                for old in previous)
        validate(previous+[row])
        data = (json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n').encode()
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if os.write(fd, data) != len(data):
                raise ValueError('Incomplete timeline append')
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    summary = sub.add_parser('summary'); summary.add_argument('--path', required=True, type=Path)
    summary.add_argument('--host-evidence', type=Path)
    run = sub.add_parser('run')
    run.add_argument('--path', required=True, type=Path)
    for key in ('task-id', 'run-id', 'step-id', 'input-fingerprint', 'command-label'):
        run.add_argument('--'+key, required=True)
    run.add_argument('--task-type', required=True, choices=sorted(TYPES))
    run.add_argument('--concurrency-group', default='main')
    run.add_argument('--depends-on', action='append', default=[])
    run.add_argument('command', nargs=argparse.REMAINDER)
    ci = sub.add_parser('ci')
    ci.add_argument('--step-id', required=True)
    ci.add_argument('--task-type', required=True, choices=sorted(TYPES))
    ci.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.mode == 'ci':
            run_id, attempt, job = (os.environ.get(key, '') for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB'))
            if not re.fullmatch('[0-9]{1,20}', run_id) or not re.fullmatch('[0-9]{1,5}', attempt) or not IDENTITY.fullmatch(job):
                raise ValueError('Controlled CI identity required')
            args.path = Path.cwd()/'artifacts'/('task-timeline-'+job+'.jsonl')
            args.task_id, args.run_id = os.environ.get('TASK_TIMELINE_TASK_ID', 'ENGINEERING'), 'ci-'+run_id+'-'+attempt
            args.input_fingerprint = os.environ.get('TASK_TIMELINE_INPUT', '')
            if not args.input_fingerprint:
                head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
                if not re.fullmatch('[0-9a-f]{40}', head):
                    raise ValueError('Committed CI input required')
                args.input_fingerprint = hashlib.sha256(head.encode('ascii')).hexdigest()
            args.command_label, args.concurrency_group, args.depends_on = args.step_id, job, []
        if args.mode == 'summary':
            print(json.dumps(summarize(read(args.path), args.host_evidence), sort_keys=True)); return 0
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('An explicit command is required')
        rows = read(args.path)
        if args.mode == 'ci':
            previous = [row for row in rows if row['taskId'] == args.task_id and row['runId'] == args.run_id]
            args.depends_on = [previous[-1]['stepId']] if previous else []
        attempt = 1 + sum(row['taskId'] == args.task_id and row['taskType'] == args.task_type
                          and row['commandLabel'] == args.command_label and row['inputFingerprint'] == args.input_fingerprint for row in rows)
        start = dt.datetime.now(dt.timezone.utc); monotonic = time.monotonic()
        row = dict(schemaVersion=2, timingStatus='VALID', taskId=args.task_id, runId=args.run_id, stepId=args.step_id,
                   taskType=args.task_type, inputFingerprint=args.input_fingerprint,
                   startedAtUtc=start.isoformat(), endedAtUtc=start.isoformat(), durationMs=0,
                   outcome='PASS', errorCategory=None, dependsOn=args.depends_on,
                   concurrencyGroup=args.concurrency_group, attempt=attempt, exitCode=0, commandLabel=args.command_label)
        validate(rows+[row])
        code, category = None, None
        try:
            code = subprocess.run(command, shell=False).returncode
            category = None if code == 0 else 'COMMAND_FAILED'
        except OSError:
            code, category = 127, 'EXECUTABLE_UNAVAILABLE'
        except KeyboardInterrupt:
            code, category = 130, 'INTERRUPTED'
        finally:
            end = dt.datetime.now(dt.timezone.utc)
            elapsed = round((time.monotonic()-monotonic)*1000)
            row = complete(row, end.isoformat(), elapsed, code, category)
            append(args.path, row, assign_attempt=True)
        return code if code is not None and code >= 0 else 1
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        print('REFUSED: invalid timeline metadata or output boundary; values withheld', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
