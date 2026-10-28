"""Own one fresh authorized M1, M2 or M3 AppHost throughout genuine browser, semantic and operational acceptance."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('g2_acceptance', Path(__file__).with_name('g2-acceptance-runtime.py'))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def run_attempt():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file')
    parser.add_argument('--start-runtime', action='store_true')
    parser.add_argument('--milestone', choices=['M1', 'M2', 'M3'], default='M1')
    parser.add_argument('--api-only', action='store_true')
    parser.add_argument('--ui-only', action='store_true')
    parser.add_argument('--smoke-fault-check', action='store_true')
    args = parser.parse_args()
    if not args.runtime_file and not args.start_runtime:
        parser.error('Choose an owned runtime or explicitly start a new M1 stack')
    if args.api_only and args.ui_only:
        parser.error('Choose one integration checkpoint')
    if (args.api_only or args.ui_only) and args.milestone not in ('M2', 'M3'):
        parser.error('Integration checkpoints are authorized only for M2/M3')
    task_id = 'G3-' + args.milestone + '-001'
    task_evidence = 'docs/evidence/' + task_id + '/runtime'
    prefix = 'g3-' + args.milestone.lower() + '-'
    os.environ.setdefault('PLATFORM_EVIDENCE_DIR', task_evidence)
    if args.runtime_file:
        runtime_file = Path(args.runtime_file).resolve()
    else:
        prepared = subprocess.check_output([sys.executable, 'scripts/acceptance/g3-runtime.py', 'prepare', '--milestone', args.milestone], cwd=ROOT, text=True)
        runtime_file = (ROOT / prepared.strip().splitlines()[-1]).resolve()
    if not runtime_file.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Private runtime must belong to this checkout')
    runtime = json.loads(runtime_file.read_text())
    if not runtime['volumePrefix'].startswith(prefix) or runtime_file.parent.name != runtime['volumePrefix']:
        parser.error('Protected G2 or unrelated runtime refused')
    # 每次调用独占新目录，后续步骤不可能消费前一轮残留的成功文件。
    run_id = uuid.uuid4().hex
    from evidence_paths import evidence_directory
    base_evidence = evidence_directory(ROOT, task_evidence)
    if not base_evidence.is_relative_to((ROOT / task_evidence).resolve()):
        parser.error('Only this selected milestone runtime evidence root is accepted')
    os.environ['PLATFORM_EVIDENCE_DIR'] = str((base_evidence / runtime['volumePrefix'] / run_id).relative_to(ROOT.resolve()))
    evidence = evidence_directory(ROOT, task_evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    source_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    gate_names = ['full-g2-e2e.py', 'g3-compatibility.py', 'g1-regression.py', 'g2-observability.py',
                  'g2-trace-browser.mjs', 'g2-readiness-fault.py', 'performance-baseline.py']
    if args.api_only or args.ui_only:
        gate_names = gate_names[:1]
    acceptance = {'runId': run_id, 'sourceHead': source_head, 'volumePrefix': runtime['volumePrefix'],
                  'scope': 'API_ONLY' if args.api_only else 'UI_ONLY' if args.ui_only else 'FULL', 'milestone': args.milestone,
                  'evidenceDirectory': str(evidence.relative_to(ROOT.resolve())), 'status': 'RUNNING',
                  'startedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'gates': [{'name': name, 'status': 'NOT_RUN', 'exitCode': None} for name in gate_names]}

    def save_acceptance():
        (evidence / 'acceptance.json').write_text(json.dumps(acceptance, indent=2) + '\n')

    save_acceptance()
    # 只记录本轮归属元数据，绝不复制配置或认证值到证据。
    ownership = {'volumePrefix': runtime['volumePrefix'], 'runtimePath': str(runtime_file),
                 'runId': run_id, 'sourceHead': source_head, 'launcherOwned': args.start_runtime,
                 'scope': task_id + ' freshly generated Synthetic test environment; other tasks excluded',
                 'launcherStarted': False, 'launcherStopped': False}
    (evidence / 'owned-runtime.json').write_text(json.dumps(ownership, indent=2) + '\n')
    process = None
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

    def launch(mode):
        return subprocess.Popen([sys.executable, 'scripts/acceptance/g3-runtime.py', mode, '--runtime-file', str(runtime_file), '--milestone', args.milestone],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    try:
        if args.start_runtime:
            try:
                with shared.OPENER.open('http://localhost:15100/health/live', timeout=1):
                    raise RuntimeError('Public entrypoint is already occupied')
            except urllib.error.HTTPError:
                raise RuntimeError('Public entrypoint is already occupied') from None
            except (urllib.error.URLError, TimeoutError):
                pass
            if not Path(runtime['realmFile']).is_file():
                process = launch('core')
                shared.wait_for('http://localhost:18080/realms/master/.well-known/openid-configuration')
                subprocess.run([sys.executable, 'scripts/acceptance/g3-runtime.py', 'bootstrap', '--runtime-file', str(runtime_file), '--milestone', args.milestone], cwd=ROOT, check=True)
                shared.stop(process)
            process = launch('full')
            ownership['launcherStarted'] = True
        shared.wait_for('http://localhost:15100/health/ready', {'X-Health-Key': runtime['healthKey']})
        tools = json.loads(subprocess.check_output(['pwsh', '-NoProfile', '-File', 'scripts/bootstrap-web-tools.ps1'], cwd=ROOT, text=True))
        commands = [
            [sys.executable, 'scripts/acceptance/full-g2-e2e.py', '--runtime-file', str(runtime_file), '--m1'],
            [sys.executable, 'scripts/acceptance/g3-compatibility.py'],
            [sys.executable, 'scripts/acceptance/g1-regression.py', '--runtime-file', str(runtime_file), '--runtime-only'],
            [sys.executable, 'scripts/acceptance/g2-observability.py', '--runtime-file', str(runtime_file)],
            [tools['nodePath'], 'scripts/acceptance/g2-trace-browser.mjs', str(runtime_file)],
            [sys.executable, 'scripts/acceptance/g2-readiness-fault.py', '--runtime-file', str(runtime_file)],
            [sys.executable, 'scripts/acceptance/performance-baseline.py', '--from-observed-run'],
        ]
        if args.milestone == 'M2':
            commands[0].append('--m2-api-only' if args.api_only else '--m2-ui-only' if args.ui_only else '--m2')
        if args.milestone == 'M3':
            commands[0].append('--m3-api-only' if args.api_only else '--m3-ui-only' if args.ui_only else '--m3')
        if args.smoke_fault_check:
            commands[0].append('--smoke-fault-check')
        if args.api_only or args.ui_only:
            commands[0].remove('--m1')
            commands = commands[:1]
        for index, command in enumerate(commands):
            acceptance['gates'][index]['status'] = 'RUNNING'
            save_acceptance()
            result = subprocess.run(command, cwd=ROOT)
            acceptance['gates'][index].update(status='PASS' if result.returncode == 0 else 'FAIL', exitCode=result.returncode)
            save_acceptance()
            if result.returncode:
                acceptance['status'] = 'FAIL'
                return result.returncode
        acceptance['status'] = 'PASS'
        return 0
    except Exception as failure:
        acceptance['failureCategory'] = type(failure).__name__
        raise
    finally:
        try:
            shared.stop(process)
        except Exception as failure:
            acceptance['status'] = 'FAIL'
            acceptance['failureCategory'] = type(failure).__name__
            raise
        finally:
            for gate in acceptance['gates']:
                if gate['status'] == 'RUNNING':
                    gate.update(status='FAIL', failureCategory=acceptance.get('failureCategory', 'gate_interrupted'))
            ownership['launcherStopped'] = process is None or process.poll() is not None
            ownership['launcherExitCode'] = None if process is None else process.returncode
            (evidence / 'owned-runtime.json').write_text(json.dumps(ownership, indent=2) + '\n')
            if acceptance['status'] == 'RUNNING' or not ownership['launcherStopped']:
                acceptance['status'] = 'FAIL'
            acceptance['completedAtUtc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_acceptance()
            print(json.dumps({'status': acceptance['status'], 'runId': run_id,
                              'evidenceDirectory': acceptance['evidenceDirectory']}))
        if not ownership['launcherStopped']:
            raise RuntimeError('Owned launcher did not stop')


def main():
    before = os.environ.get('PLATFORM_EVIDENCE_DIR')
    try:
        return run_attempt()
    finally:
        if before is None:
            os.environ.pop('PLATFORM_EVIDENCE_DIR', None)
        else:
            os.environ['PLATFORM_EVIDENCE_DIR'] = before


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(json.dumps({'status': 'FAIL', 'category': type(failure).__name__, 'details': 'SUPPRESSED'}))
        raise SystemExit(1)
