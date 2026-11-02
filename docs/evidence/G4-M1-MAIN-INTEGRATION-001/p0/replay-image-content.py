"""Replay the independent P0 read-only image checks; never starts or downloads images."""
import hashlib
import json
import pathlib
import subprocess
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
REPORT = json.loads((HERE / 'images-admission.json').read_text())
ROOT = pathlib.Path('/Users/chasen/.codex/worktrees/g4-m1-verify-recovery-001/ontology-platform')
FORENSICS = pathlib.Path('/Users/chasen/.codex/worktrees/g4-m1-recovery-001/ontology-platform/artifacts/g4-m1-recovery-001/forensics')
HISTORY = json.loads((ROOT / 'docs/evidence/G4-M1-RECOVERY-001/registry-manifests.json').read_text())

for row in REPORT['images']:
    command = row['commands'][0]['argv']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    blobs, objects = {}, {}
    with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
        for member in archive:
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            digest, parts = hashlib.sha256(), []
            while block := stream.read(1048576):
                digest.update(block)
                if member.size < 1000000:
                    parts.append(block)
            if member.name.startswith('blobs/sha256/'):
                assert member.name.endswith(digest.hexdigest())
                key = 'sha256:' + digest.hexdigest()
                blobs[key] = member.size
                if parts:
                    try:
                        objects[key] = json.loads(b''.join(parts))
                    except (ValueError, UnicodeDecodeError):
                        pass
    while process.stdout.read(1048576):
        pass
    stderr = process.stderr.read()
    assert process.wait() == 0 and not stderr
    inspected = json.loads(subprocess.check_output(row['commands'][1]['argv']))[0]
    chain = row['architectureManifestChain']
    manifest_id = 'sha256:' + chain['manifest']
    manifest = objects[manifest_id]
    config_id = manifest['config']['digest']
    assert config_id == 'sha256:' + chain['config']
    config = objects[config_id]
    assert config['architecture'] == 'arm64' and config['os'] == 'linux'
    assert blobs[config_id] == manifest['config']['size']
    assert config['rootfs']['diff_ids'] == inspected['RootFS']['Layers']
    for layer in manifest['layers']:
        assert blobs[layer['digest']] == layer['size']
    if row['name'] in ('postgres', 'keycloak', 'aspnet', 'node'):
        number = ('postgres', 'keycloak', 'aspnet', 'node').index(row['name'])
        raw_index = (FORENSICS / str(number) / 'official-index.json').read_bytes()
        assert hashlib.sha256(raw_index).hexdigest() == chain['index']
        index = json.loads(raw_index)
        assert any(item['digest'] == manifest_id and item['platform']['architecture'] == 'arm64' for item in index['manifests'])
        historical = next(item for item in HISTORY if item['sha256'] == chain['manifest'] and item['kind'] == 'arm64')
        assert historical['manifest'] == manifest
        for identity in (chain['manifest'], chain['config']):
            raw = (FORENSICS / str(number) / 'blobs/sha256' / identity).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == identity
    elif row['name'] == 'rustfs':
        index = objects['sha256:' + chain['index']]
        assert any(item['digest'] == manifest_id and item['platform']['architecture'] == 'arm64' for item in index['manifests'])
        for name, identity in [('index', chain['index']), ('platform', chain['manifest'])]:
            raw = (ROOT / 'docs/evidence/G4-M1-FINAL-GATES-001/images' / ('rustfs-official-' + name + '.json')).read_bytes()
            assert raw.endswith(b'\n') and hashlib.sha256(raw[:-1]).hexdigest() == identity
    license_report = row['licenseReport']
    assert hashlib.sha256(pathlib.Path(license_report['path']).read_bytes()).hexdigest() == license_report['sha256']
    print(json.dumps({'name': row['name'], 'contentAndArchivedManifest': 'VERIFIED', 'blobs': len(blobs), 'bytes': sum(blobs.values()), 'scope': 'Content replay only; canonical input recomputation remains in independent report; no full supplier-signature/CVE/license assertion'}), flush=True)
