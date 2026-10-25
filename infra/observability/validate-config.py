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
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=600)
    result = {'argv': argv, 'startedAtUtc': start, 'exitCode': process.returncode,
              'stdout': process.stdout, 'stderr': process.stderr}
    (OUT / (label + '.result.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return process.returncode


def pull(resource):
    image = resource['image'] + ':' + resource['tag'] + '@' + resource['indexDigest']
    return capture(resource['name'] + '-pull', ['docker', 'pull', image])


def validate(resource):
    name = resource['name']
    if name == 'grafana':
        # Grafana无等价离线全量校验；必须统一AppHost真实启动并核对provisioning。
        return 0
    image = resource['image'] + ':' + resource['tag'] + '@' + resource['indexDigest']
    argv = ['docker', 'run', '--rm', '--network', 'none']
    for mount in resource['mounts']:
        argv += ['--mount', 'type=bind,src=' + str(ROOT / 'infra/observability' / mount['source']) + ',dst=' + mount['target'] + ',readonly']
    if name == 'alloy':
        argv += ['-e', 'LOKI_OTLP_ENDPOINT=http://loki:3100/otlp', '-e', 'TEMPO_OTLP_ENDPOINT=http://tempo:4318', '-e', 'PROMETHEUS_OTLP_ENDPOINT=http://prometheus:9090/api/v1/otlp']
        args = ['validate', '/etc/alloy/config.alloy']
    elif name == 'loki':
        args = ['-config.file=/etc/loki/loki.yaml', '-verify-config=true']
    elif name == 'tempo':
        args = ['-config.file=/etc/tempo/tempo.yaml', '-config.verify']
    else:
        argv += ['--entrypoint', '/bin/promtool']
        args = ['check', 'config', '/etc/prometheus/prometheus.yaml']
    return capture(name + '-validate', argv + [image] + args)


if __name__ == '__main__':
    if '--pull' in sys.argv:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            codes = list(executor.map(pull, RESOURCES))
        if any(codes):
            sys.exit(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        codes = list(executor.map(validate, RESOURCES))
    sys.exit(1 if any(codes) else 0)
