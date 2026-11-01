#!/usr/bin/env python3
"""Validate the entire G4-M1-RECOVERY-001 task input ZIP using Python stdlib only."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile


def verify(file_path: Path) -> None:
    with zipfile.ZipFile(file_path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        assert len(names) == len(set(names)), "duplicate archive entries"
        assert len({n.casefold() for n in names}) == len(names), "case collision"
        for name in names:
            components = PurePosixPath(name).parts
            assert not name.startswith('/') and components and '..' not in components and '\\' not in name, "unsafe path"
        assert archive.testzip() is None, "CRC failure"
        manifest = json.loads(archive.read('MANIFEST.json'))
        records = manifest['files']
        assert isinstance(records, list) and records
        assert set(names) == {x['path'] for x in records} | {'MANIFEST.json','SHA256SUMS.txt'}, "member set mismatch"
        checksum_lines = []
        for item in records:
            name = item['path']
            data = archive.read(name)
            h = hashlib.sha256(data).hexdigest()
            assert item['sizeBytes'] == len(data) and item['sha256'] == h, f"member hash mismatch: {name}"
            checksum_lines.append(f"{h}  {name}")
        assert archive.read('SHA256SUMS.txt').decode('utf-8') == '\n'.join(checksum_lines) + '\n', "SHA256SUMS mismatch"
        assert manifest['taskId'] == 'G4-M1-RECOVERY-001'
    print(json.dumps({'taskId':manifest['taskId'],'result':'PASS','payloadCount':len(records),'zipBytes':file_path.stat().st_size,'zipSha256':hashlib.sha256(file_path.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('usage: verify_package.py <absolute-path-to-zip>')
    verify(Path(sys.argv[1]))
