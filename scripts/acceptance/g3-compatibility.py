"""Run the pre-write compatibility binary against a genuine exported V2 release, without authentication access."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess

from evidence_paths import evidence_directory

ROOT = Path(__file__).resolve().parents[2]


def snapshot_binary_set(directory):
    """Freeze the entire entrypoint/dependency/configuration member set, refusing links."""
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Reader directory cannot be a symlink')
    members = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Reader member cannot be a symlink')
        if path.is_file():
            members.append({'path': path.relative_to(directory).as_posix(), 'sizeBytes': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    names = {item['path'] for item in members}
    if not {'OntologyPlatform.G2ContractTests.dll', 'OntologyPlatform.Contracts.dll'} <= names:
        raise RuntimeError('Reader entrypoint or actual strict parser dependency is missing')
    return members


def verify_binary_set(directory, frozen):
    """Reject changed, missing or injected members, including the real Contracts.dll parser."""
    if snapshot_binary_set(directory) != frozen:
        raise RuntimeError('Frozen reader binary set changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    artifact = ROOT / 'artifacts/g3-m1'
    directory = artifact / 'fallback-reader-v3'
    reader = directory / 'OntologyPlatform.G2ContractTests.dll'
    identity_path = artifact / 'fallback-reader-v3.identity.json'
    manifest = artifact / 'actual-v2-manifest.json'
    evidence = evidence_directory(ROOT, 'docs/evidence/G3-M1-001/runtime')
    evidence.mkdir(parents=True, exist_ok=True)
    if args.freeze:
        if identity_path.exists():
            identity = json.loads(identity_path.read_text())
            verify_binary_set(directory, identity['members'])
        else:
            identity = {'members': snapshot_binary_set(directory), 'scope': 'M1 pre-write retained compatible reader'}
        # Probe the unchanged directory before accepting its frozen identity; real artifact follows later.
        probe = subprocess.run(['dotnet', str(reader), '--filter', 'FullyQualifiedName~V2RoundtripRetainsExactAssessmentBinding',
                                '--output', 'Detailed', '--zero-tests-policy', 'strict', '--minimum-expected-tests', '1'],
                               cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        verify_binary_set(directory, identity['members'])
        (evidence / 'prewrite-reader.txt').write_text('\n'.join(line.rstrip() for line in probe.stdout.splitlines()) + '\n')
        if probe.returncode:
            raise RuntimeError('Pre-write binary probe failed')
        if not identity_path.exists():
            identity_path.write_text(json.dumps(identity, indent=2) + '\n')
        proof = {'status': 'PASS', 'freezeSha256': hashlib.sha256(identity_path.read_bytes()).hexdigest(),
                 'memberCount': len(identity['members']), 'preWriteProbeExitCode': probe.returncode}
        (evidence / 'prewrite-reader-identity.json').write_text(json.dumps({**proof, **identity}, indent=2) + '\n')
        print(json.dumps(proof))
        return 0
    if not reader.is_file() or not manifest.is_file() or not identity_path.is_file():
        raise RuntimeError('Pre-write frozen identity, reader or real V2 artifact missing')
    expected_identity = os.environ.get('G3_READER_IDENTITY_SHA')
    if not expected_identity or hashlib.sha256(identity_path.read_bytes()).hexdigest() != expected_identity:
        raise RuntimeError('Pre-write frozen identity hash is missing or changed')
    identity = json.loads(identity_path.read_text())
    verify_binary_set(directory, identity['members'])
    result = subprocess.run(['dotnet', str(reader), '--filter', 'FullyQualifiedName~CompatibilityBinaryReadsActualV2Manifest',
                             '--output', 'Detailed', '--zero-tests-policy', 'strict', '--minimum-expected-tests', '1'],
                            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    verify_binary_set(directory, identity['members'])
    (evidence / 'compatibility-binary.txt').write_text('\n'.join(line.rstrip() for line in result.stdout.splitlines()) + '\n')
    proof = {'status': 'PASS' if result.returncode == 0 else 'FAIL', 'exitCode': result.returncode,
             'freezeSha256': expected_identity, 'memberCount': len(identity['members']), 'readerUnchanged': True,
             'manifestSha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
             'scope': 'pre-write strict manifest reader binary; not a G2 application downgrade certification'}
    (evidence / 'compatibility-binary.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
    return 0 if proof['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
