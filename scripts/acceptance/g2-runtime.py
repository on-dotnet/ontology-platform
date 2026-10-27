#!/usr/bin/env python3
"""Run the genuine AppHost G2 profile with new private volumes and identities."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys

os.environ.setdefault('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G2-THIN-SLICE-001/master')
spec = importlib.util.spec_from_file_location('wave2_runtime', Path(__file__).with_name('wave2-runtime.py'))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def main():
    """Reuse the reviewed secret-safe launcher; never access historical runtime files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'core', 'bootstrap', 'full'])
    parser.add_argument('--runtime-file')
    args = parser.parse_args()
    if args.mode == 'prepare':
        runtime.prepare('g2')
        return 0
    if not args.runtime_file:
        parser.error('--runtime-file required')
    path, value = runtime.load_runtime(args.runtime_file)
    if not value['volumePrefix'].startswith('g2-') or path.parent.name != value['volumePrefix']:
        parser.error('G2 requires its own newly generated runtime directory')
    if args.mode == 'bootstrap':
        return runtime.bootstrap(path, 'g2')
    return runtime.run(path, args.mode, 'g2', 'Release')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as failure:
        print('FAILED: ' + type(failure).__name__ + '; details suppressed for secret safety', file=sys.stderr)
        sys.exit(1)
