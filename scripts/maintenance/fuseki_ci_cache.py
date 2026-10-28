#!/usr/bin/env python3
"""Bound GitHub cache transport to canonical identities and existing repository storage."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MAX_ARCHIVE = 512 * 1024 * 1024
# A conservative project cap below the existing included repository allowance.
MAX_PROJECT_STORAGE = 1024 * 1024 * 1024
OUTPUT_FIELDS = {'cacheKey', 'failureStateKey', 'envFingerprint', 'inputFingerprint',
                 'contextSha256', 'platform', 'image', 'schemaVersion'}


def validate_identity(value):
    if not isinstance(value, dict) or set(value) != OUTPUT_FIELDS or value['schemaVersion'] != 2:
        raise ValueError('Canonical identity schema required')
    for key in ('envFingerprint', 'inputFingerprint', 'contextSha256'):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key]):
            raise ValueError('Canonical fingerprint required')
    if value['platform'] not in ('linux/amd64', 'linux/arm64'):
        raise ValueError('Approved platform required')
    key = 'ontology-fuseki-image-v2-' + value['platform'].replace('/', '-') + '-' + value['inputFingerprint']
    if value['cacheKey'] != key or value['failureStateKey'] != key+'-failure-v1-'+value['envFingerprint']:
        raise ValueError('Exact canonical key required')
    if value['image'] != 'ontology-platform-fuseki:context-'+value['inputFingerprint']:
        raise ValueError('Canonical tag required')
    return value


def budget(usage, size):
    if not isinstance(usage, dict) or type(usage.get('active_caches_size_in_bytes')) is not int:
        raise ValueError('Repository cache usage unavailable')
    used = usage['active_caches_size_in_bytes']
    if type(size) is not int or not 0 <= size <= MAX_ARCHIVE or not 0 <= used <= MAX_PROJECT_STORAGE-size:
        raise ValueError('Conservative existing-storage budget exceeded')
    return dict(status='PASS', existingBytes=used, proposedBytes=size, projectCapBytes=MAX_PROJECT_STORAGE,
                paidCapacityEnabled=False, permission='public metadata; no extra token permission')


def directory_size(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Dedicated ordinary directory required')
    total = 0
    for item in directory.rglob('*'):
        if item.is_symlink() or not item.is_file():
            raise ValueError('Cache links or nested directories refused')
        total += item.stat().st_size
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['identity', 'budget'])
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'identity':
            raw = subprocess.check_output([sys.executable, str(ROOT/'scripts/maintenance/canonical_fuseki.py'), '--identity'], cwd=ROOT, text=True)
            value = validate_identity(json.loads(raw))
            output = os.environ.get('GITHUB_OUTPUT')
            if output:
                with open(output, 'a', encoding='utf-8') as stream:
                    for key, item in value.items():
                        stream.write(key+'='+str(item)+'\n')
            print(json.dumps(value, sort_keys=True))
        else:
            if args.directory is None or os.environ.get('GITHUB_REPOSITORY') != 'on-dotnet/ontology-platform':
                raise ValueError('Exact repository and directory required')
            # The repository is PUBLIC. This deliberately sends no Authorization header or token.
            request=urllib.request.Request('https://api.github.com/repos/on-dotnet/ontology-platform/actions/cache/usage',
                headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
                         'User-Agent':'OntologyPlatform-cache-budget'})
            with urllib.request.urlopen(request,timeout=15) as response:
                raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:
                raise ValueError('Oversized metadata refused')
            print(json.dumps(budget(json.loads(raw), directory_size(args.directory)), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        print('BLOCKED: canonical identity or existing-storage budget unverified; no cache save authorized', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
