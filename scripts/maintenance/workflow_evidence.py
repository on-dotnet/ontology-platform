#!/usr/bin/env python3
"""公开证据先复用 V3 内容/路径检查，必要时按既有 base64 映射无损保存。"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
from workflow_execution import ordinary


def digest(raw):return hashlib.sha256(raw).hexdigest()


def preflight(root,relative,raw):
    """base64 只用于工具传输；扫描恢复后的原字节，绝不绕过秘密检查。"""
    script=". ./scripts/create-review-package.ps1 -Library; try { $r=[Console]::In.ReadToEnd()|ConvertFrom-Json; Assert-ReviewPath $r.path; Assert-ReviewContent ([Convert]::FromBase64String($r.bytes)) 'command evidence' } catch { [Console]::Error.WriteLine('EVIDENCE_REJECTED'); exit 1 }"
    from workflow_execution import run,current_task
    result=run(['pwsh','-NoProfile','-Command',script],root,task=current_task('EVIDENCE-PREFLIGHT'),stdin=json.dumps(dict(path=relative,bytes=base64.b64encode(raw).decode())).encode(),timeout=20,diagnostic=True,stage='archive-preflight')
    if result.returncode:raise ValueError('EVIDENCE_REJECTED')


def publish(root,relative,raw):
    root=ordinary(root);target=ordinary(root/relative)
    if not target.is_relative_to(root/'docs/evidence') or '..' in Path(relative).parts:raise ValueError('EVIDENCE_BOUNDARY')
    preflight(root,relative,raw)
    try:
        text=raw.decode('utf-8')
        plain=bool(raw) and '\r' not in text and not text.endswith('\n\n') and '\x1b' not in text and '\x00' not in text and text.endswith('\n') and not any(line.rstrip()!=line for line in text.splitlines())
    except UnicodeDecodeError:plain=False
    record=dict(originalPath=relative,sha256=digest(raw),sizeBytes=len(raw))
    if not plain:
        target=target.with_suffix(target.suffix+'.raw.json')
        payload=json.dumps(dict(encoding='base64',**record,base64=base64.b64encode(raw).decode()),indent=2).encode()+b'\n'
        record['encoding']='base64'
    else:payload=raw;record['encoding']='raw'
    record['path']=str(target.relative_to(root))
    preflight(root,record['path'],payload)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(payload)
    if restore(root,record)!=raw:raise ValueError('EVIDENCE_RESTORE')
    return record


def restore(root,record):
    path=ordinary(Path(root)/record['path'])
    if not path.is_relative_to(ordinary(Path(root)/'docs/evidence')):raise ValueError('EVIDENCE_BOUNDARY')
    raw=path.read_bytes()
    if record['encoding']=='base64':
        envelope=json.loads(raw);raw=base64.b64decode(envelope['base64'],validate=True)
        if envelope['sha256']!=record['sha256']:raise ValueError('ENVELOPE_HASH')
    if len(raw)!=record['sizeBytes'] or digest(raw)!=record['sha256']:raise ValueError('EVIDENCE_HASH')
    return raw


def machine(raw,kind,minimum=1):
    """有界机器报告；未知格式、失败、跳过和计数矛盾关闭放行。"""
    if len(raw)>16*1024*1024:raise ValueError('REPORT_SIZE')
    if kind=='vitest-json':
        row=json.loads(raw)
        counts=[row.get(k) for k in ('numTotalTests','numPassedTests','numFailedTests','numPendingTests','numTodoTests')]
        if any(type(n)!=int for n in counts):raise ValueError('REPORT_COUNTS')
        total,passed,failed,pending,todo=counts
        assertions=[a for result in row.get('testResults',[]) for a in result.get('assertionResults',[])]
        suites=[row.get(k) for k in ('numTotalTestSuites','numPassedTestSuites','numFailedTestSuites','numPendingTestSuites')]
        if any(type(n)!=int or n<0 for n in suites):raise ValueError('REPORT_SUITE_COUNTS')
        valid=suites[0]==suites[1] and suites[2]==suites[3]==0 and all(result.get('status')=='passed' and not result.get('message') for result in row.get('testResults',[]))
        valid=valid and row.get('success') is True and total==passed==len(assertions) and failed==pending==todo==0 and all(a.get('status')=='passed' for a in assertions)
    else:raise ValueError('REPORT_FORMAT_UNKNOWN')
    if not valid or total<minimum:raise ValueError('REPORT_NOT_PASS')
    return total
