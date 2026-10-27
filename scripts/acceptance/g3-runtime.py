"""Launch only a fresh M1 stack, retaining the reviewed G2 protocol and secret-safe lifecycle."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys

os.environ.setdefault('PLATFORM_EVIDENCE_DIR', 'docs/evidence/G3-M1-001/runtime')
spec = importlib.util.spec_from_file_location('wave2_runtime', Path(__file__).with_name('wave2-runtime.py'))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'core', 'bootstrap', 'full'])
    parser.add_argument('--runtime-file')
    args = parser.parse_args()
    if args.mode == 'prepare':
        runtime.prepare('g2', 'g3-m1')
        return 0
    if not args.runtime_file:
        parser.error('--runtime-file required')
    path, value = runtime.load_runtime(args.runtime_file)
    if not value['volumePrefix'].startswith('g3-m1-') or path.parent.name != value['volumePrefix']:
        parser.error('Only this task fresh M1 runtime is allowed')
    if args.mode == 'bootstrap':
        return runtime.bootstrap(path, 'g2')
    return runtime.run(path, args.mode, 'g2', 'Release')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print('FAIL: ' + type(failure).__name__ + '; private details suppressed', file=sys.stderr)
        raise SystemExit(1)
