#!/usr/bin/env python3
"""Restore only the two committed public synthetic manifest byte fixtures; never normalize them."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    provenance = json.loads((root / "provenance.json").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    restored = []
    for version in (1, 2):
        name = f"real-v{version}-manifest.json"
        envelope_name = f"real-v{version}-manifest.base64.json"
        envelope_bytes = (root / envelope_name).read_bytes()
        envelope = json.loads(envelope_bytes)
        fact = next(row for row in provenance if row["originalFilename"] == name)
        if (envelope["encoding"] != "base64" or envelope["originalFilename"] != name
                or envelope["schemaVersion"] != 1 or len(envelope_bytes) != fact["envelopeSizeBytes"]
                or hashlib.sha256(envelope_bytes).hexdigest() != fact["envelopeSha256"]):
            raise ValueError("Manifest envelope provenance mismatch")
        raw = base64.b64decode(envelope["dataBase64"], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if (len(raw) != envelope["originalSizeBytes"] or digest != envelope["originalSha256"]
                or len(raw) != fact["originalSizeBytes"] or digest != fact["originalSha256"]):
            raise ValueError("Manifest raw byte provenance mismatch")
        target = args.output / name
        with target.open("xb") as stream:
            stream.write(raw)
        if target.read_bytes() != raw:
            raise ValueError("Restored manifest byte verification failed")
        restored.append(dict(path=str(target), sizeBytes=len(raw), sha256=digest))
    print(json.dumps(restored, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
