#!/usr/bin/env python3
"""Run actual migrated PostgreSQL, Jena and Governance atomicity/CAS integration tests."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('semantic_roundtrip', Path(__file__).with_name('semantic-roundtrip.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
raise SystemExit(module.main(postgres=True, label='draft-revision'))
