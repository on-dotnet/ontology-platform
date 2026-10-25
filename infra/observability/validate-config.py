"""执行官方镜像一次性配置校验并直接保存公开输出；不启动服务编排。"""
import concurrent.futures
import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/evidence/G1-WAVE2/OBS/config-validation' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
RESOURCES = json.loads((ROOT / 'infra/observability/resources.json').read_text())['resources']


def capture(label, argv):
    OUT.mkdir(parents=True, exist_ok=True)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as error:
        # 超时也直接保留真实部分输出与明确退出码，不把没运行完冒充PASS。
        stdout = error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else (error.stdout or '')
        stderr = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else (error.stderr or '')
        process = subprocess.CompletedProcess(argv, 124, stdout, stderr + '\nTimed out after 600 seconds')
    result = {'argv': argv, 'startedAtUtc': start, 'exitCode': process.returncode,
              'stdout': process.stdout, 'stderr': process.stderr}
    (OUT / (label + '.result.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'label': label, 'exitCode': process.returncode, 'result': str(OUT / (label + '.result.json'))}), flush=True)
    return process.returncode


def pull(resource):
    image = resource['image'] + ':' + resource['tag'] + '@' + resource['indexDigest']
    return capture(resource['name'] + '-pull', ['docker', 'pull', image])


def validate(resource):
    name = resource['name']
    if name == 'grafana':
        # Grafana无等价离线全量校验；必须统一AppHost真实启动并核对provisioning。
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'grafana-validation-status.json').write_text(json.dumps({
            'status': 'NOT_RUN', 'exitCode': None, 'argv': None,
            'reason': 'No equivalent offline full provisioning validator; unified AppHost runtime required'
        }, indent=2) + '\n')
        return 0
    image = resource['image'] + ':' + resource['tag'] + '@' + resource['indexDigest']
    available = capture(name + '-platform', ['docker', 'image', 'inspect', image,
                         '--format', '{{json .Os}} {{json .Architecture}} {{json .Config.User}}'])
    if available:
        return available
    argv = ['docker', 'run', '--pull=never', '--rm', '--network', 'none']
    for mount in resource['mounts']:
        argv += ['--mount', 'type=bind,src=' + str(ROOT / 'infra/observability' / mount['source']) + ',dst=' + mount['target'] + ',readonly']
    if name == 'alloy':
        argv += ['-e', 'LOKI_OTLP_ENDPOINT=http://loki:3100/otlp', '-e', 'TEMPO_OTLP_ENDPOINT=http://tempo:4318', '-e', 'PROMETHEUS_OTLP_ENDPOINT=http://prometheus:9090/api/v1/otlp']
        args = ['validate', '/etc/alloy/config.alloy']
    elif name == 'loki':
        args = ['-config.file=/etc/loki/loki.yaml', '-verify-config=true']
    elif name == 'tempo':
        args = ['-config.file=/etc/tempo/tempo.yaml', '-config.verify=true']
    else:
        argv += ['--entrypoint', '/bin/promtool']
        args = ['check', 'config', '/etc/prometheus/prometheus.yaml']
    return capture(name + '-validate', argv + [image] + args)


if __name__ == '__main__':
    if '--pull' in sys.argv:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            codes = list(executor.map(pull, RESOURCES))
        pull_failed = any(codes)
    else:
        pull_failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        codes = list(executor.map(validate, RESOURCES))
    prometheus = next(resource for resource in RESOURCES if resource['name'] == 'prometheus')
    image = prometheus['image'] + ':' + prometheus['tag'] + '@' + prometheus['indexDigest']
    alert_code = capture('prometheus-alert-tests', ['docker', 'run', '--pull=never', '--rm', '--network', 'none',
                         '--mount', 'type=bind,src=' + str(ROOT / 'infra/observability/prometheus') + ',dst=/etc/prometheus,readonly',
                         '--entrypoint', '/bin/promtool', image, 'test', 'rules', '/etc/prometheus/alert-tests.yaml'])
    sys.exit(1 if pull_failed or any(codes) or alert_code else 0)
