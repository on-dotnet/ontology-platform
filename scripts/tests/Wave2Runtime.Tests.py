import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1] / 'acceptance/wave2-runtime.py'
s=importlib.util.spec_from_file_location('runtime',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for line in ['client_secret=synthetic-secret-value', 'http://localhost:15100/cb?code=synthetic-code&state=synthetic-state', 'Cookie: synthetic-cookie', 'login http://localhost:15888/login?t=synthetic-dashboard-token', '{"access_token":"synthetic-json-token"}', 'code = synthetic-spaced-code', 'state: synthetic-state', 'nonce=synthetic-nonce']:
    result=m.sanitize(line,['synthetic-secret-value'])
    assert 'synthetic-' not in result
try:m.load_runtime('/tmp/unapproved-runtime.json')
except ValueError:pass
else:raise AssertionError('outside runtime accepted')
print('PASS: eight output redaction negatives and runtime path boundary')
