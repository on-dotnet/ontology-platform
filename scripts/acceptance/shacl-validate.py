#!/usr/bin/env python3
"""Reproduce the real standard SHACL test group using the same isolated fixture."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('semantic_roundtrip', Path(__file__).with_name('semantic-roundtrip.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
raise SystemExit(module.main('*/ShaclTests/*', label='shacl-validate'))
