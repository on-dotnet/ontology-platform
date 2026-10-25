"""从官方来源直接归档版本、许可证和镜像索引，不读取认证材料。"""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/evidence/G1-WAVE2/OBS/dependencies'
COMPONENTS = [
    ('alloy', 'grafana/alloy', 'v1.21.2', 'grafana/alloy:v1.21.2', 'Apache-2.0'),
    ('loki', 'grafana/loki', 'v3.7.9', 'grafana/loki:3.7.9', 'AGPL-3.0-only'),
    ('tempo', 'grafana/tempo', 'v3.1.1', 'grafana/tempo:3.1.1', 'AGPL-3.0-only'),
    ('prometheus', 'prometheus/prometheus', 'v3.15.1', 'prom/prometheus:v3.15.1', 'Apache-2.0'),
    ('grafana', 'grafana/grafana', 'v13.2.4', 'grafana/grafana:13.2.4', 'AGPL-3.0-only'),
]


def inspect(component):
    name, repo, version, image, license_id = component
    directory = OUT / name
    directory.mkdir(parents=True, exist_ok=True)
    result = {'name': name, 'version': version, 'image': image, 'licenseSpdx': license_id,
              'observedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'fullImageCveScan': 'NOT_VERIFIED', 'fullImageSbom': 'NOT_VERIFIED',
              'signatureVerification': 'NOT_VERIFIED'}
    for label, url in [
        ('release', f'https://api.github.com/repos/{repo}/releases/tags/{version}'),
        ('license', f'https://raw.githubusercontent.com/{repo}/{version}/LICENSE'),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=40) as response:
                payload = response.read()
            # 不复制整份第三方许可或release正文；保留官方响应sha和必要事实。
            record = {'url': url, 'httpStatus': 200, 'sha256': hashlib.sha256(payload).hexdigest()}
            if label == 'release':
                data = json.loads(payload)
                record.update({k: data[k] for k in ['tag_name', 'html_url', 'published_at', 'prerelease', 'draft']})
            else:
                record['firstLines'] = payload.decode().splitlines()[:5]
            result[label] = record
            (directory / (label + '.json')).write_text(json.dumps(record, indent=2) + '\n')
        except Exception as error:
            result[label] = {'url': url, 'error': str(error)}
    for suffix, arguments in [
        ('index', ['docker', 'buildx', 'imagetools', 'inspect', image, '--raw']),
        ('digest', ['docker', 'buildx', 'imagetools', 'inspect', image, '--format', '{{.Manifest.Digest}}']),
    ]:
        process = subprocess.run(arguments, capture_output=True, text=True, timeout=180)
        # 此命令只输出公开镜像manifest，不请求或打印Docker认证配置。
        (directory / (suffix + '.output.json')).write_text(json.dumps({'stdout': process.stdout}, indent=2) + '\n')
        result[suffix + 'Command'] = {'argv': arguments, 'exitCode': process.returncode, 'stderr': process.stderr}
        if process.returncode:
            result['status'] = 'FAIL'
        elif suffix == 'index':
            result['arm64'] = [m for m in json.loads(process.stdout).get('manifests', []) if m.get('platform', {}).get('architecture') == 'arm64']
        else:
            result['indexDigest'] = process.stdout.strip()
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(inspect, COMPONENTS))
    (OUT / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
