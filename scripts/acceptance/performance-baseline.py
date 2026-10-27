#!/usr/bin/env python3
"""Run or summarize genuine full-chain latency observations; never invent a production SLO."""
import argparse
import datetime
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
from evidence_paths import evidence_directory
EVIDENCE = evidence_directory(ROOT, 'docs/evidence/G2-THIN-SLICE-001/master')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file', help='Run a new genuine browser publication/query/SSE/rollback chain')
    parser.add_argument('--from-observed-run', action='store_true', help='Summarize the existing actual full-chain observation; does not rerun the product')
    args = parser.parse_args()
    if bool(args.runtime_file) == args.from_observed_run:
        parser.error('Select a new --runtime-file run OR --from-observed-run explicitly')
    if args.runtime_file:
        code = subprocess.run([sys.executable,str(ROOT / 'scripts/acceptance/full-g2-e2e.py'),'--runtime-file',args.runtime_file],cwd=ROOT).returncode
        if code:
            return code
    actual = json.loads((EVIDENCE / 'performance-observations.json').read_text())
    chain = json.loads((EVIDENCE / 'full-g2-e2e.json').read_text())
    if chain['status'] != 'PASS':
        raise ValueError('A failed chain cannot certify performance coverage')
    grouped = {}
    for sample in actual['samples']:
        elapsed = sample['elapsedMs']
        if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Invalid actual duration')
        grouped.setdefault(sample['operation'],[]).append(elapsed)
    required = ['shacl','sparql','publication','sse']
    covered = {name:any(sample.get('category') == name for sample in actual['samples']) for name in required}
    report = {'status':'PASS' if all(covered.values()) else 'PARTIAL','scope':'Observed local synthetic engineering baseline; no production SLO or load certification','summarizedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'existing actual run summary' if args.from_observed_run else 'new actual run','environment':actual['environment'],'inputBytes':actual['sourceUtf8Bytes'],'coverage':covered,'operations':{name:{'count':len(values),'minMs':min(values),'medianMs':statistics.median(values),'maxMs':max(values),'p95NearestRankMs':sorted(values)[math.ceil(.95*len(values))-1]} for name,values in sorted(grouped.items())}}
    (EVIDENCE / 'performance-baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'actualSamples':len(actual['samples']),'coverage':covered}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
