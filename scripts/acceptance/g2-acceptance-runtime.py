#!/usr/bin/env python3
"""Optionally launch isolated AppHost, then run every required real G2 runtime gate."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def stop(process):
    """Terminate only this helper's own launcher; preserve all named development volumes."""
    if process is not None and process.poll() is None:
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
        try:
            process.wait(timeout=55)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)


def wait_for(url, headers=None, seconds=120):
    """Read fixed local technical probes; never print headers, secrets or response bodies."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with OPENER.open(urllib.request.Request(url,headers=headers or {}),timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError,ValueError):
            pass
        time.sleep(.5)
    raise TimeoutError('Local G2 technical readiness not reached')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file')
    parser.add_argument('--start-runtime',action='store_true')
    args = parser.parse_args()
    if not args.runtime_file and not args.start_runtime:
        parser.error('Supply this checkout synthetic runtime or explicitly start a new one')
    if args.runtime_file:
        runtime_file = Path(args.runtime_file).resolve()
    else:
        prepared = subprocess.check_output([sys.executable,'scripts/acceptance/g2-runtime.py','prepare'],cwd=ROOT,text=True)
        runtime_file = (ROOT / prepared.strip().splitlines()[-1]).resolve()
    if not runtime_file.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Private runtime must belong to this checkout')
    runtime = json.loads(runtime_file.read_text())
    if not runtime['volumePrefix'].startswith('g2-'):
        parser.error('Historical profiles are forbidden')
    process = None
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    def launch(mode):
        return subprocess.Popen([sys.executable,'scripts/acceptance/g2-runtime.py',mode,'--runtime-file',str(runtime_file)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
    try:
        if args.start_runtime:
            # Fail before starting if another developer stack occupies the fixed public entrypoint.
            try:
                with OPENER.open('http://localhost:15100/health/live',timeout=1):
                    raise RuntimeError('Fixed public entrypoint already occupied')
            except urllib.error.HTTPError:
                raise RuntimeError('Fixed public entrypoint already occupied') from None
            except (urllib.error.URLError,TimeoutError):
                pass
            if not Path(runtime['realmFile']).is_file():
                process = launch('core')
                wait_for('http://localhost:18080/realms/master/.well-known/openid-configuration')
                subprocess.run([sys.executable,'scripts/acceptance/g2-runtime.py','bootstrap','--runtime-file',str(runtime_file)],cwd=ROOT,check=True)
                stop(process)
            process = launch('full')
        wait_for('http://localhost:15100/health/ready',{'X-Health-Key':runtime['healthKey']})
        tools = json.loads(subprocess.check_output(['pwsh','-NoProfile','-File','scripts/bootstrap-web-tools.ps1'],cwd=ROOT,text=True))
        # Keep the owned stack alive across all gates; a failed gate must stop acceptance.
        commands = [
            [sys.executable,'scripts/acceptance/full-g2-e2e.py','--runtime-file',str(runtime_file)],
            [sys.executable,'scripts/acceptance/g1-regression.py','--runtime-file',str(runtime_file),'--runtime-only'],
            [sys.executable,'scripts/acceptance/g2-observability.py','--runtime-file',str(runtime_file)],
            [tools['nodePath'],'scripts/acceptance/g2-trace-browser.mjs',str(runtime_file)],
            [sys.executable,'scripts/acceptance/g2-readiness-fault.py','--runtime-file',str(runtime_file)],
            [sys.executable,'scripts/acceptance/performance-baseline.py','--from-observed-run'],
        ]
        for command in commands:
            result = subprocess.run(command,cwd=ROOT)
            if result.returncode:
                return result.returncode
        return 0
    finally:
        stop(process)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(json.dumps({'status':'FAIL','category':type(failure).__name__,'details':'SUPPRESSED'}))
        raise SystemExit(1)
