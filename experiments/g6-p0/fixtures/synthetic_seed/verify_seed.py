#!/usr/bin/env python3
"""Standard-library-only integrity verification of synthetic *design* seeds.
This does NOT execute Docling/LLM, evaluate quality, or constitute Gold.
"""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'seed-manifest.json').read_text(encoding='utf-8'))
assert manifest['kind'] == 'SYNTHETIC_SEED_NOT_GOLD'
assert len(manifest['documents']) == 9
for item in manifest['documents']:
    path = root / item['file']
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item['sha256'], item['file']
    doc = raw.decode('utf-8')
    for span in item['sourceSpans']:
        assert span['occurrences'] == doc.count(span['text']) == 1, (item['file'], span)
        a, b = span['startCodepoint'], span['endCodepoint']
        assert doc[a:b] == span['text'], (item['file'], span)
        assert a >= 0 and b <= len(doc)
    assert item['synthetic'] is True
    assert item['groundTruthStatus'] == 'SEED_EXPECTATION_NOT_EXPERT_GOLD'
print(f'SEED_INTEGRITY_PASS: {len(manifest["documents"])} synthetic files, SHA256 and source span checks passed. NO runtime/model/Gold evaluation performed.')
