"""Resolve diagnostic scope with case-sensitive Git refs; never certifies full CI."""
import json
import os
from pathlib import Path


def canonical_only(event_name, ref, event):
    if event_name not in ('push', 'pull_request', 'workflow_dispatch'):
        raise ValueError('Unsupported CI event')
    if not isinstance(event, dict):
        raise ValueError('Invalid CI event')
    if event_name == 'workflow_dispatch':
        value = event.get('inputs', {}).get('canonical_only', False)
        if type(value) is not bool and (not isinstance(value, str) or value not in ('false', 'true')):
            raise ValueError('Invalid diagnostic input')
        return value is True or value == 'true'
    if event_name == 'push' and ref == 'refs/heads/codex/g3-m3-master':
        message = (event.get('head_commit') or {}).get('message', '')
        if not isinstance(message, str):
            raise ValueError('Invalid head message')
        return '[canonical-diagnostic]' in message
    return False


def main():
    path = Path(os.environ['GITHUB_EVENT_PATH'])
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Event unavailable or oversized')
    result = canonical_only(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF'],
                            json.loads(path.read_text(encoding='utf-8')))
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
        stream.write('canonical_only=' + str(result).lower() + '\n')
    print('CANONICAL_DIAGNOSTIC_ONLY; product NOT_RUN; full required CI NOT_VERIFIED'
          if result else 'FULL_REQUIRED_CI')


if __name__ == '__main__':
    main()
