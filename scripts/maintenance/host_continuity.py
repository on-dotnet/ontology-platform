#!/usr/bin/env python3
"""只读宿主持续运行预检及有界心跳；不修改全局电源策略，不保持显示器常亮。"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time

UTC = dt.timezone.utc


def now():
    """取得明确 UTC 的原始墙钟观测。"""
    return dt.datetime.now(UTC).isoformat()


def capture(command):
    """固定只读命令有超时和输出上限；错误不输出原系统日志。"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        if result.returncode or len(result.stdout.encode()) > 16 * 1024 * 1024:
            return None
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def policy_values(raw):
    """只提取 AC 段，不把电池策略或显示器防睡眠误判成主机保障。"""
    if raw is None:
        return None
    match = re.search(r'(?m)^AC Power:\s*\n((?:[ \t].*\n?)*)', raw)
    if not match:
        return None
    return {key: int(value) for key, value in re.findall(
        r'^\s*(sleep|displaysleep)\s+(\d+)\s*$', match[1], re.M)}


def assertion_values(raw):
    """只记录必要类别的计数，不采集其他进程名称或设备标识。"""
    if raw is None:
        return None
    keys = ('PreventUserIdleSystemSleep', 'PreventSystemSleep', 'PreventUserIdleDisplaySleep')
    return {key: int(value) for key, value in re.findall(
        r'^\s*(' + '|'.join(keys) + r')\s+(\d+)\s*$', raw, re.M)}


def display_state():
    """Apple只读CoreGraphics检查显示器睡眠；不抓屏、不采集显示器标识。"""
    try:
        import ctypes
        graphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        integer = ctypes.c_uint32
        graphics.CGGetOnlineDisplayList.argtypes = [integer, ctypes.POINTER(integer), ctypes.POINTER(integer)]
        graphics.CGGetOnlineDisplayList.restype = ctypes.c_int32
        for name in ('CGDisplayIsAsleep', 'CGDisplayIsBuiltin'):
            function = getattr(graphics, name)
            function.argtypes = [integer]
            function.restype = integer
        ids, count = (integer * 16)(), integer()
        if graphics.CGGetOnlineDisplayList(16, ids, ctypes.byref(count)) != 0 or count.value >= 16:
            return dict(status='NOT_VERIFIED')
        external = [ids[index] for index in range(count.value) if not graphics.CGDisplayIsBuiltin(ids[index])]
        return dict(status='OBSERVED', externalDisplayCount=len(external),
                    externalDisplaysAsleep=all(graphics.CGDisplayIsAsleep(item) for item in external) if external else None)
    except (OSError, AttributeError):
        return dict(status='NOT_VERIFIED')


def inspect(system=None, reader=capture):
    """跨平台只读判断策略；锁屏熄屏与整会话保证分别记录。"""
    system = system or platform.system()
    result = dict(schemaVersion=1, utc=now(), os=system, architecture=platform.machine(),
                  pid=os.getpid(), taskId='G3-M5-001', assurance='NOT_APPLICABLE',
                  lockDisplayTrial='NOT_VERIFIED', sessionContinuity='NOT_VERIFIED')
    if system != 'Darwin':
        return result
    policy = policy_values(reader(['pmset', '-g', 'custom']))
    batt = reader(['pmset', '-g', 'batt'])
    result.update(acPower=None if batt is None else "Now drawing from 'AC Power'" in batt,
                  policy=policy, assertions=assertion_values(reader(['pmset', '-g', 'assertions'])))
    locked = reader(['ioreg', '-n', 'Root', '-d1'])
    result['displays'] = display_state()
    result['screenLocked'] = None if locked is None or '"IOConsoleLocked"' not in locked else '"IOConsoleLocked" = Yes' in locked
    result['assurance'] = ('POLICY_READY' if result['acPower'] is True and policy is not None
                           and policy.get('sleep') == 0 and policy.get('displaysleep', 0) > 0
                           else 'BLOCKED_HOST_SLEEP_ASSURANCE')
    return result


def sleep_events(raw, start, end):
    """仅保存窗口内睡眠/唤醒类别及 UTC，不采集设备、应用或唤醒原因正文。"""
    if raw is None:
        return dict(status='NOT_VERIFIED', events=[], confirmedSleepMs=None)
    events, intervals, sleeping = [], [], None
    for line in raw.splitlines():
        match = re.match(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4})\s+(Sleep|Wake|DarkWake)\s+', line)
        if not match:
            continue
        stamp = dt.datetime.strptime(match[1], '%Y-%m-%d %H:%M:%S %z').astimezone(UTC)
        if stamp > end:
            continue
        kind = match[2]
        if kind == 'Sleep' and 'Entering Sleep' in line:
            sleeping = stamp if sleeping is None else sleeping
        elif kind in ('Wake', 'DarkWake') and sleeping is not None:
            low, high = max(start, sleeping), min(end, stamp)
            if high > low:
                intervals.append((low, high))
            sleeping = None
        if start <= stamp <= end:
            events.append(dict(utc=stamp.isoformat(), kind=kind,
                               idleSleep=kind == 'Sleep' and "'Idle Sleep'" in line))
    if sleeping is not None and end > max(start, sleeping):
        intervals.append((max(start, sleeping), end))
    total = round(sum((high-low).total_seconds()*1000 for low, high in intervals))
    return dict(status='OBSERVED_LOG_WINDOW', events=events, confirmedSleepMs=total,
                limitation='只计日志可确认的Sleep至Wake/DarkWake区间；无事件不证明未知窗口从未睡眠。')


def output_path(value):
    """任务输出必须位于明确 ignored artifacts 边界且拒绝符号链接。"""
    root = Path(__file__).resolve().parents[2]
    target = Path(value).absolute()
    if '..' in target.parts:
        raise ValueError('输出拒绝父目录穿越')
    if not target.is_relative_to(root / 'artifacts') or any(p.is_symlink() for p in [target, *target.parents]):
        raise ValueError('输出必须位于本任务树 artifacts 普通目录')
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def save(path, value, append=False):
    """新证据不得覆写；心跳逐行持久化且不记录命令参数。"""
    with path.open('a' if append else 'x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def monitor(path, seconds, interval):
    """有界监测策略变化与锁屏心跳；不创建保活常驻进程或防显示器睡眠断言。"""
    start, tick = dt.datetime.now(UTC), time.monotonic()
    rows = []
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while True:
            row = inspect()
            row.update(sequence=len(rows), elapsedMs=round((time.monotonic()-tick)*1000))
            save(path, row, append=True)
            rows.append(row)
            if stopped or time.monotonic()-tick >= seconds:
                break
            time.sleep(min(interval, max(0, seconds-(time.monotonic()-tick))))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    end = dt.datetime.now(UTC)
    summary = dict(schemaVersion=1, taskId='G3-M5-001', ownerPid=os.getpid(),
                   startedAtUtc=start.isoformat(), endedAtUtc=end.isoformat(),
                   measuredElapsedMs=round((time.monotonic()-tick)*1000), heartbeatCount=len(rows),
                   lockedHeartbeatCount=sum(r.get('screenLocked') is True for r in rows),
                   policyContinuouslyReady=all(r['assurance']=='POLICY_READY' for r in rows),
                   maxHeartbeatGapMs=max((b['elapsedMs']-a['elapsedMs'] for a,b in zip(rows, rows[1:])), default=0),
                   displayOff='OBSERVED' if any(r.get('screenLocked') and r.get('displays',{}).get('externalDisplaysAsleep') is True for r in rows) else 'NOT_VERIFIED',
                   lockedDisplayOffHeartbeatCount=sum(r.get('screenLocked') is True and r.get('displays',{}).get('externalDisplaysAsleep') is True for r in rows),
                   sessionContinuity='NOT_VERIFIED', stoppedBySignal=stopped,
                   sleep=sleep_events(capture(['pmset','-g','log']) if platform.system()=='Darwin' else None,start,end))
    save(path.with_suffix('.summary.json'), summary)
    return summary


def fixture():
    """仅短生命周期准确 PID 断言正例和用户终止负例；finally 释放，不影响其他进程。"""
    if platform.system() != 'Darwin':
        return dict(status='NOT_APPLICABLE')
    outcomes = []
    for terminate in (False, True):
        child = subprocess.Popen(['/usr/bin/caffeinate','-i','-s','-t','2'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            observed = False
            deadline = time.monotonic()+1.5
            while time.monotonic()<deadline:
                raw = capture(['pmset','-g','assertions']) or ''
                blocks = re.findall(r'pid '+str(child.pid)+r'\(caffeinate\):[^\n]*',raw)
                owned = '\n'.join(blocks)
                if 'PreventUserIdleSystemSleep' in owned and 'PreventSystemSleep' in owned:
                    observed = True
                    break
                time.sleep(.05)
            alive_before_termination = child.poll() is None
            if terminate and alive_before_termination:
                child.terminate()
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        raw = capture(['pmset','-g','assertions'])
        released = raw is not None and re.search(r'pid '+str(child.pid)+r'\(caffeinate\):',raw) is None
        outcomes.append(dict(pid=child.pid, mode='terminated' if terminate else 'normal',
                             assertionObserved=observed, released=released, exitCode=child.returncode,
                             lifecycleValid=(child.returncode == -signal.SIGTERM and alive_before_termination) if terminate else child.returncode == 0))
    return dict(status='PASS' if all(x['assertionObserved'] and x['released'] and x['lifecycleValid'] for x in outcomes) else 'NOT_VERIFIED',
                flags=['-i','-s'], cases=outcomes, sessionAssurance='NOT_VERIFIED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    pre=sub.add_parser('preflight');pre.add_argument('--output')
    mon=sub.add_parser('monitor');mon.add_argument('--output',required=True)
    mon.add_argument('--seconds',type=int,default=600);mon.add_argument('--interval',type=int,default=5)
    sub.add_parser('fixture')
    cli=sub.add_parser('cli');cli.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        if args.mode=='cli':
            command=args.command[1:] if args.command[:1]==['--'] else args.command
            if not command:raise ValueError('需要真实CLI命令')
            if platform.system()=='Darwin':
                command=['/usr/bin/caffeinate','-is',*command]
            return subprocess.run(command,shell=False).returncode
        if args.mode=='monitor':
            if not 1<=args.seconds<=86400 or not 1<=args.interval<=60:raise ValueError('监测时长/间隔超出预算')
            target=output_path(args.output)
            if target.exists() or target.with_suffix('.summary.json').exists():raise ValueError('拒绝覆写已有心跳')
            result=monitor(target,args.seconds,args.interval)
        else:
            result=fixture() if args.mode=='fixture' else inspect()
            if args.mode=='preflight' and args.output:save(output_path(args.output),result)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        if result.get('assurance')=='BLOCKED_HOST_SLEEP_ASSURANCE' or result.get('status')=='NOT_VERIFIED':
            return 2
        if args.mode=='monitor' and (not result['policyContinuouslyReady'] or result['sleep']['status']=='NOT_VERIFIED'
                                    or result['sleep']['confirmedSleepMs'] != 0):
            return 2
        return 0
    except (ValueError,OSError,subprocess.SubprocessError):
        print('REFUSED: 宿主预检/输出边界不可核实，未修改电源设置',file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
