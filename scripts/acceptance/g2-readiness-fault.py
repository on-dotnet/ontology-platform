#!/usr/bin/env python3
"""Verify real protected readiness with bounded stalls in only this G2 runtime's containers."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file',required=True)
    args = parser.parse_args()
    path = Path(args.runtime_file).resolve()
    if not path.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Only current checkout private runtime accepted')
    runtime = json.loads(path.read_text())
    prefix = runtime['volumePrefix']
    if prefix.startswith(('g3-m3-', 'g3-m4-', 'g3-m5-')):
        if not re.fullmatch(r'g3-m[345]-[0-9a-f]{12}', prefix) or path.parent.name != prefix:
            parser.error('Only exactly owned M3/M4/M5 runtime accepted')
    elif not prefix.startswith(('g2-', 'g3-m1-', 'g3-m2-')):
        parser.error('Historical volumes forbidden')
    checks = []
    def probe(label,expected,authorized=True):
        start = time.monotonic()
        try:
            with OPENER.open(urllib.request.Request('http://localhost:15100/health/ready',headers={'X-Health-Key':runtime['healthKey']} if authorized else {}),timeout=8) as response:
                status = response.status
        except urllib.error.HTTPError as failure:
            status = failure.code
        except OSError:
            status = 0
        elapsed = (time.monotonic() - start) * 1000
        # Includes process scheduling and loopback HTTP overhead around the internal 2-second budget.
        passed = status == expected and elapsed < 3000
        checks.append({'check':label,'status':'PASS' if passed else 'FAIL','httpStatus':status,'elapsedMs':elapsed,'maximumObservedEnvelopeMs':3000,'internalBudgetMs':2000})
        print(json.dumps(checks[-1]),flush=True)
        if not passed:
            raise AssertionError('Actual readiness failed')
    try:
        probe('health_key_required',401,False)
        for attempt in range(90):
            try:
                probe('all_real_modules_dependencies_ready',200)
                break
            except (OSError,AssertionError):
                if attempt == 89:
                    raise
                checks.pop()
                time.sleep(1)
        for dependency,volume in [('jena','fuseki-data'),('rustfs','rustfs-data'),('governance_postgres','postgres-data')]:
            names = subprocess.check_output(['docker','ps','--filter','volume='+runtime['volumePrefix']+'-'+volume,'--format','{{.Names}}'],text=True).split()
            if len(names) != 1:
                raise ValueError('Expected one current G2 dependency container')
            paused = False
            try:
                subprocess.run(['docker','pause',names[0]],check=True,stdout=subprocess.DEVNULL)
                paused = True
                probe(dependency+'_stall_fails_closed',503)
            finally:
                if paused:
                    subprocess.run(['docker','unpause',names[0]],check=True,stdout=subprocess.DEVNULL)
            probe(dependency+'_recovered',200)
        return 0
    finally:
        from evidence_paths import evidence_directory
        target = evidence_directory(ROOT, 'docs/evidence/G2-THIN-SLICE-001/master') / 'readiness-real-faults.json'
        target.write_text(json.dumps({'scope':'actual own isolated AppHost/PG/Jena/RustFS, each paused only during a protected health request and unpaused in finally','checks':checks,'status':'PASS' if len(checks)==8 and all(check['status']=='PASS' for check in checks) else 'FAIL'},indent=2)+'\n')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(json.dumps({'status':'FAIL','category':type(failure).__name__,'details':'SUPPRESSED'}))
        raise SystemExit(1)
