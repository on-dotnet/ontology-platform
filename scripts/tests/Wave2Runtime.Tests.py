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

# 新S3访问键须按运行时值和字段形式脱敏；普通公开诊断不可全部抹掉。
synthetic = dict(rustfsAccessKey='SYNTHETIC_ACCESS_ONLY', rustfsSecretKey='SYNTHETIC_SECRET_ONLY')
for line in ['RUSTFS_ACCESS_KEY=SYNTHETIC_ACCESS_ONLY', '{"rustfsAccessKey":"SYNTHETIC_ACCESS_ONLY"}', 'access key value SYNTHETIC_ACCESS_ONLY']:
    assert 'SYNTHETIC_ACCESS_ONLY' not in m.sanitize(line, list(m.secret_values(synthetic)))
for line in ['RUSTFS_ACCESS_KEY=other-synthetic-access', '{"rustfsAccessKey":"other-synthetic-access"}']:
    assert 'other-synthetic-access' not in m.sanitize(line, [])
for line in ['RustFS readiness: Healthy', 'capability=resolve_entity status=FOUND', 'public graph urn:ontology-platform:release:synthetic:ontology']:
    assert m.sanitize(line, list(m.secret_values(synthetic))) == line + '\n'
print('PASS: S3 access-key redaction and public diagnostic preservation')

# Bootstrap继承当前Python可执行文件，宿主没有python3别名也不会偷偷换解释器。
import sys
from unittest.mock import patch
synthetic_runtime = dict(keycloakPassword='SYNTHETIC_BOOTSTRAP_ONLY', realmFile='synthetic-realm.json')
with patch.object(m, 'load_runtime', return_value=(Path('synthetic-runtime.json'), synthetic_runtime)), \
        patch.object(m.subprocess, 'run') as child:
    child.return_value.returncode = 23
    assert m.bootstrap('synthetic-runtime.json', 'g2') == 23
    assert child.call_args.args[0][0] == sys.executable
    assert child.call_args.kwargs['env']['WAVE2_KEYCLOAK_ADMIN_PASSWORD'] == 'SYNTHETIC_BOOTSTRAP_ONLY'
print('PASS: current Python bootstrap and real child exit propagation')
