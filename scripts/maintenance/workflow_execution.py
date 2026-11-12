#!/usr/bin/env python3
"""现有 FailureState 的公共子进程通道；私有双流和追加生命周期事实。"""
import contextlib
import contextvars
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import threading
import uuid
from types import SimpleNamespace
from execution_preflight import FailureState


CONTEXT=contextvars.ContextVar('workflow_context',default={})


def current_task(default='WORKFLOW'):
    return CONTEXT.get().get('task',os.environ.get('WORKFLOW_TASK_ID',default))


@contextlib.contextmanager
def cleanup_scope():
    token=CONTEXT.set({**CONTEXT.get(),'cleanup':True})
    try:yield
    finally:CONTEXT.reset(token)


@contextlib.contextmanager
def operation(root,task,stage,input_key,environment_key):
    """真实消费者入口的稳定失败身份不含随机资源ID；子命令保留父身份。"""
    root=ordinary(root);base=root/'artifacts/workflow'/task
    base.mkdir(parents=True,exist_ok=True)
    policy=sha(Path(__file__).read_bytes());key=sha(encoded([stage,input_key,environment_key,policy]))
    run_id=uuid.uuid4().hex;ident=uuid.uuid4().hex
    row=dict(schemaVersion=2,taskId=task,runId=run_id,commandId=ident,parentId=CONTEXT.get().get('parent_id'),stage=stage,inputFingerprint=input_key,environmentFingerprint=environment_key,startedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),classification='UNKNOWN')
    with FailureState(base/'failures'/(key+'.json'),key,'operation',policy) as guard:
        guard.allow('expensive')
        append(base/'command-events.jsonl',{**row,'event':'START'})
        token=CONTEXT.set(dict(task=task,run_id=run_id,parent_id=ident,input_key=input_key,environment_key=environment_key))
        start=time.monotonic();code=70
        try:
            yield row
            code=0;row['classification']='SUCCESS'
        except BaseException:
            row['classification']='INTERRUPTED' if isinstance(__import__('sys').exc_info()[1],KeyboardInterrupt) else 'EXIT_FAILURE'
            raise
        finally:
            CONTEXT.reset(token);guard.record('expensive',code)
            append(base/'command-events.jsonl',{**row,'event':'END','endedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsedSeconds':time.monotonic()-start,'exitCode':None,'operationOutcomeCode':code})


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def ordinary(path):
    path=Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('EXECUTION_LINKED_PATH')
    return path


def append(path,row):
    with ordinary(path).open('ab') as stream:
        os.chmod(path,0o600)
        stream.write(encoded(row)+b'\n');stream.flush();os.fsync(stream.fileno())


def capture(directory,name,raw):
    """原件仅写私有目录；公开归档必须另经内容检查。"""
    path=ordinary(directory/(name+'.txt'))
    with path.open('xb') as stream:
        os.chmod(path,0o600);stream.write(raw)
    return dict(path=str(path),sha256=sha(raw),sizeBytes=len(raw))


def run(command,root,*,task=None,run_id=None,stage='command',parent_id=None,
        input_key=None,environment_key=None,identity_key=None,timeout=1800,environment=None,cleanup=False,diagnostic=False,stdin=None):
    """START 先持久化；真实退出码与超时分类分列，失败身份不含 RunId。"""
    context=CONTEXT.get();task=task or current_task()
    run_id=run_id or context.get('run_id');parent_id=parent_id or context.get('parent_id')
    cleanup=cleanup or context.get('cleanup',False)
    input_key=input_key or context.get('input_key');environment_key=environment_key or context.get('environment_key')
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}',task):raise ValueError('TASK_INVALID')
    if timeout<=0 or diagnostic and timeout>20:raise ValueError('DEADLINE_INVALID')
    root=ordinary(root)
    workspace=next((p for p in (root,*root.parents) if (p/'.git').exists()),root)
    base=ordinary(workspace/'artifacts/workflow'/task)
    run_id=run_id or uuid.uuid4().hex
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('RUN_INVALID')
    command_id=uuid.uuid4().hex
    directory=ordinary(base/'commands'/run_id/command_id);directory.mkdir(parents=True,mode=0o700)
    argv_hash=sha(encoded([str(arg) for arg in command]))
    if input_key is None:
        input_key=sha(encoded({str(p.relative_to(workspace)):sha(p.read_bytes()) for p in sorted((workspace/'scripts/maintenance').glob('workflow*.py'))}))
    if environment_key is None:
        environment_key=sha(encoded(dict(environment if environment is not None else os.environ)))
    policy=sha(Path(__file__).read_bytes())
    key=sha(encoded([input_key,environment_key,identity_key or argv_hash,str(root),timeout,policy]))
    guard=FailureState(base/'failures'/(key+'.json'),key,'command',policy)
    # 清理是收尾义务，不得被先前测试失败阻止。
    manager=contextlib.nullcontext() if cleanup else guard
    row=dict(schemaVersion=2,taskId=task,runId=run_id,stage=stage,commandId=command_id,parentId=parent_id,
             cwd=str(root),commandSummary=dict(executable=Path(command[0]).name,argumentCount=len(command)-1,sha256=argv_hash),
             inputFingerprint=input_key,environmentFingerprint=environment_key,identity=key,
             deadlineSeconds=timeout,started=False,exitCode=None,signal=None,classification='UNKNOWN',
             startedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    started=time.monotonic();child=None;out=b'';err=b'';cancelled=False;cost='short' if diagnostic else 'expensive'
    with manager:
        if not cleanup:
            try:guard.allow(cost)
            except ValueError:
                append(base/'command-events.jsonl',{**row,'event':'BLOCKED','classification':'UNCHANGED_FAILURE_BLOCKED'})
                raise
        append(base/'command-events.jsonl',{**row,'event':'START'})
        previous_handler=None
        if threading.current_thread() is threading.main_thread():
            previous_handler=signal.getsignal(signal.SIGTERM)
            def interrupted(signum,frame):raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM,interrupted)
        try:
            child=subprocess.Popen(command,cwd=root,env=environment,stdin=subprocess.PIPE if stdin is not None else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt')
            row['started']=True
            try:
                out,err=child.communicate(input=stdin,timeout=timeout)
                row['classification']='SUCCESS' if child.returncode==0 else 'EXIT_FAILURE'
            except (subprocess.TimeoutExpired,KeyboardInterrupt) as error:
                cancelled=isinstance(error,KeyboardInterrupt)
                row['classification']='CANCELLED' if cancelled else 'TIMEOUT'
                if os.name!='nt':os.killpg(child.pid,signal.SIGKILL)
                else:child.kill()
                out,err=child.communicate(timeout=10)
                row['processGroupTerminated']=True
                if os.name!='nt':
                    try:os.killpg(child.pid,0);row['processGroupTerminated']=False
                    except ProcessLookupError:pass
                if not row['processGroupTerminated']:row['classification']='TERMINATION_UNVERIFIED'
            row['exitCode']=child.returncode
            row['signal']=-child.returncode if child.returncode<0 else None
        except BaseException:
            row['classification']='INTERRUPTED' if child else 'START_FAILURE'
            if child and child.poll() is None:
                if os.name!='nt':os.killpg(child.pid,signal.SIGKILL)
                else:child.kill()
                out,err=child.communicate(timeout=10);row['exitCode']=child.returncode
            raise
        finally:
            if previous_handler is not None:signal.signal(signal.SIGTERM,previous_handler)
            row.update(endedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),elapsedSeconds=time.monotonic()-started,
                       stdout=capture(directory,'stdout',out),stderr=capture(directory,'stderr',err))
            if not cleanup:guard.record(cost,0 if row['classification']=='SUCCESS' else (row['exitCode'] or 70))
            append(base/'command-events.jsonl',{**row,'event':'END'})
            (directory/'receipt.json').write_bytes(encoded(row)+b'\n')
    if cancelled:raise KeyboardInterrupt()
    effective_code=0 if row['classification']=='SUCCESS' and row['exitCode']==0 else (124 if row['classification'] in ('TIMEOUT','CANCELLED') else (row['exitCode'] or 70))
    return SimpleNamespace(returncode=effective_code,
                           stdout=out,stderr=err,receipt=row)


def timing_summary(path):
    """区间并集避免父子相加；缺 END 的 START 只标 UNKNOWN。"""
    events=[json.loads(line) for line in Path(path).read_text().splitlines()]
    starts={r['commandId']:r for r in events if r['event']=='START'}
    ends={r['commandId']:r for r in events if r['event']=='END'}
    intervals=sorted((dt.datetime.fromisoformat(starts[k]['startedAtUtc']).timestamp(),dt.datetime.fromisoformat(v['endedAtUtc']).timestamp()) for k,v in ends.items() if k in starts)
    union=0;left=right=None
    for start,end in intervals:
        if left is None:left,right=start,end
        elif start<=right:right=max(right,end)
        else:union+=right-left;left,right=start,end
    if left is not None:union+=right-left
    return dict(commandIntervalUnionSeconds=union,unknownCommands=sorted(set(starts)-set(ends)),blockedStarts=sum(r['event']=='BLOCKED' for r in events),modelReasoningSeconds='UNKNOWN',humanWaitSeconds='UNKNOWN')


class Service:
    """交互式常驻子进程的 start/readiness/stop；转发字节只留私有原件。"""
    def __init__(self,command,root,task,parent_id=None):
        self.root=ordinary(root);self.task=task;self.start=time.monotonic()
        self.ident=uuid.uuid4().hex;self.run_id=CONTEXT.get().get('run_id',uuid.uuid4().hex)
        self.base=self.root/'artifacts/workflow'/task
        self.directory=self.base/'commands'/self.run_id/self.ident;self.directory.mkdir(parents=True,mode=0o700)
        self.row=dict(schemaVersion=2,taskId=task,runId=self.run_id,commandId=self.ident,parentId=parent_id or CONTEXT.get().get('parent_id'),stage='service',startedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),classification='UNKNOWN',commandSummary=dict(executable=Path(command[0]).name,sha256=sha(encoded(command))))
        self.out=bytearray();self.err=bytearray()
        append(self.base/'command-events.jsonl',{**self.row,'event':'START'})
        try:self.process=subprocess.Popen(command,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0)
        except BaseException:
            append(self.base/'command-events.jsonl',{**self.row,'event':'END','classification':'START_FAILURE','endedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),'exitCode':None,'elapsedSeconds':time.monotonic()-self.start})
            raise

    def ready(self):
        append(self.base/'command-events.jsonl',{**self.row,'event':'READY','pid':self.process.pid})

    def finish(self):
        code=self.process.poll()
        append(self.base/'command-events.jsonl',{**self.row,'event':'END','endedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsedSeconds':time.monotonic()-self.start,'exitCode':code,'classification':'STOPPED' if code is not None else 'UNKNOWN','stdout':capture(self.directory,'stdout',bytes(self.out)),'stderr':capture(self.directory,'stderr',bytes(self.err))})


@contextlib.contextmanager
def waiting(root,task,stage):
    """同一事件协议登记有界等待，探测本身不冒充产品测试。"""
    base=ordinary(root)/'artifacts/workflow'/task;base.mkdir(parents=True,exist_ok=True)
    row=dict(schemaVersion=2,taskId=task,runId=CONTEXT.get().get('run_id',uuid.uuid4().hex),commandId=uuid.uuid4().hex,parentId=CONTEXT.get().get('parent_id'),stage=stage,startedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    start=time.monotonic();status='UNKNOWN';append(base/'command-events.jsonl',{**row,'event':'START'})
    try:
        yield
        status='READY'
    finally:append(base/'command-events.jsonl',{**row,'event':'END','classification':status,'endedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsedSeconds':time.monotonic()-start,'exitCode':None})
