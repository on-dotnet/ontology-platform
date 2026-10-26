#!/usr/bin/env python3
"""Reproduce G1 engineering/security, real OIDC and controlled audit/LGTM against a G2 profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/G2-THIN-SLICE-001/master'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', required=True)
    parser.add_argument('--runtime-only', action='store_true', help='Run actual OIDC and audit/LGTM only; engineering/native/containers explicitly NOT_RUN here')
    args = parser.parse_args()
    runtime = Path(args.runtime_file).resolve()
    if not runtime.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Only this checkout synthetic runtime is accepted')
    env = os.environ.copy()
    env['PLATFORM_EVIDENCE_DIR'] = 'docs/evidence/G2-THIN-SLICE-001/master'
    commands = []
    if not args.runtime_only:
        commands += [['pwsh','-NoProfile','-File','scripts/verify.ps1','-SelfTest'], ['dotnet','restore','backend/OntologyPlatform.slnx','--locked-mode'], ['pwsh','-NoProfile','-File','scripts/verify-web.ps1'], ['pwsh','-NoProfile','-File','scripts/verify.ps1','-RunNative','-RunTests','-SkipWeb'], ['python3','scripts/acceptance/test-governance.py']]
    commands += [['python3','infra/security/verify-oidc.py','--runtime-file',str(runtime),'--identity-prefix','g2'], ['python3','scripts/acceptance/verify-closeout-observability.py','--runtime-file',str(runtime),'--identity-prefix','g2']]
    records = []
    code = 0
    for index, command in enumerate(commands):
        result = subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True)
        # All invoked identity and runtime helpers already suppress secrets; keep their safe result only.
        output = '\n'.join(line.rstrip() for line in (result.stdout + result.stderr).splitlines()).rstrip() + '\n'
        log = EVIDENCE / ('g1-regression-' + str(index) + '.txt')
        log.write_text(output)
        records.append({'command':command,'exitCode':result.returncode,'output':str(log.relative_to(ROOT))})
        print(json.dumps({'step':index,'exitCode':result.returncode}),flush=True)
        if result.returncode:
            code = result.returncode
            break
    (EVIDENCE / 'g1-regression.json').write_text(json.dumps({'exitCode':code,'runtimeOnly':args.runtime_only,'notRun':['engineering/native/container suites in this invocation'] if args.runtime_only else [],'records':records},indent=2)+'\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
