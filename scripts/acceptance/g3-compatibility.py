"""Run the pre-write compatibility binary against a genuine exported V2 release, without authentication access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from evidence_paths import evidence_directory

ROOT = Path(__file__).resolve().parents[2]


def main():
    artifact = ROOT / 'artifacts/g3-m1'
    reader = artifact / 'fallback-reader/OntologyPlatform.G2ContractTests.dll'
    manifest = artifact / 'actual-v2-manifest.json'
    if not reader.is_file() or not manifest.is_file():
        raise RuntimeError('Pre-write reader binary or real V2 artifact missing')
    before = hashlib.sha256(reader.read_bytes()).hexdigest()
    result = subprocess.run(['dotnet', str(reader), '--filter', 'FullyQualifiedName~CompatibilityBinaryReadsActualV2Manifest',
                             '--output', 'Detailed'], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    after = hashlib.sha256(reader.read_bytes()).hexdigest()
    evidence = evidence_directory(ROOT, 'docs/evidence/G3-M1-001/runtime')
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'compatibility-binary.txt').write_text('\n'.join(line.rstrip() for line in result.stdout.splitlines()) + '\n')
    proof = {'status': 'PASS' if result.returncode == 0 and before == after else 'FAIL', 'exitCode': result.returncode,
             'readerSha256': before, 'readerUnchanged': before == after,
             'manifestSha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
             'scope': 'pre-write strict manifest reader binary; not a G2 application downgrade certification'}
    (evidence / 'compatibility-binary.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
    return 0 if proof['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
