"""仅为G4-M1恢复取证下载四个固定ARM64镜像；不执行容器或镜像内文件。"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 3 * 1024**3
DISK_LIMIT = 12 * 1024**3
# 首轮未知CDN一律暂停，非作者审核准确主机后才扩展此表。
HOSTS = {'registry-1.docker.io', 'auth.docker.io', 'quay.io', 'mcr.microsoft.com', 'production.cloudfront.docker.com'}
MEDIA = 'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁止urllib隐式跟随并把认证头交给另一主机。"""
    def redirect_request(self, *args, **kwargs):
        return None


class Download:
    """单写锁、持久预留预算、准确内容寻址的有限HTTP取证。"""
    def __init__(self, destination):
        self.root = destination.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / 'download.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.journal = self.root / 'budget.json'
        self.state = json.loads(self.journal.read_text()) if self.journal.exists() else dict(
            taskId='G4-M1-RECOVERY-001', reservedBytes=16 * 1024**2,
            receivedBytes=0, preflightMetadataReserveBytes=16 * 1024**2, requests=[])
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def save(self):
        temp = self.journal.with_suffix('.tmp')
        with temp.open('w') as output:
            json.dump(self.state, output, indent=2)
            output.write('\n'); output.flush(); os.fsync(output.fileno())
        temp.replace(self.journal)

    def disk(self, additional=0):
        size = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink())
        if size + additional > DISK_LIMIT or shutil.disk_usage(self.root).free < additional + 4 * 1024**3:
            raise RuntimeError('TASK_DISK_BUDGET_EXCEEDED')

    def get(self, url, maximum, token=None, registry=None):
        """请求前按最坏正文及64KiB协议开销预留，失败不退预算，不自动重试。"""
        for hop in range(5):
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.port not in (None, 443) or parsed.username or parsed.password:
                raise RuntimeError('HOST_REVIEW_REQUIRED:' + str(parsed.hostname))
            self.disk(maximum)
            reserve = maximum + 1 + 65536
            if self.state['reservedBytes'] + reserve > LIMIT:
                raise RuntimeError('DOWNLOAD_BUDGET_EXCEEDED')
            record = dict(host=parsed.hostname, reservedBytes=reserve, receivedBytes=0, status='STARTED')
            self.state['reservedBytes'] += reserve
            self.state['requests'].append(record); self.save()
            headers = {'Accept': MEDIA, 'Accept-Encoding': 'identity'}
            if token and parsed.hostname == registry:
                headers['Authorization'] = 'Bearer ' + token
            try:
                response = self.opener.open(urllib.request.Request(url, headers=headers), timeout=20)
            except urllib.error.HTTPError as failure:
                response = failure
            record['httpStatus'] = response.status
            if response.status in (301, 302, 303, 307, 308):
                next_url = urllib.parse.urljoin(url, response.headers['Location'])
                record['redirectHost'] = urllib.parse.urlsplit(next_url).hostname
                record['status'] = 'REDIRECT_BODY_NOT_READ'; self.save(); response.close()
                url = next_url
                continue
            if response.status == 401:
                challenge = response.headers.get('WWW-Authenticate', '')
                response.close(); record['status'] = 'AUTH_REQUIRED_BODY_NOT_READ'; self.save()
                raise AuthenticationRequired(challenge)
            if response.status != 200:
                response.close(); record['status'] = 'HTTP_REJECTED_BODY_NOT_READ'; self.save()
                raise RuntimeError('HTTP_STATUS_' + str(response.status))
            length = response.headers.get('Content-Length')
            if length and int(length) > maximum:
                response.close(); raise RuntimeError('DECLARED_SIZE_EXCEEDED')
            data = bytearray(); started = time.monotonic()
            try:
                while True:
                    if time.monotonic() - started > 180:
                        raise RuntimeError('RESPONSE_TIME_BUDGET')
                    block = response.read(min(1024**2, maximum + 1 - len(data)))
                    if not block: break
                    data.extend(block); record['receivedBytes'] += len(block)
                    self.state['receivedBytes'] += len(block)
                    if len(data) > maximum: raise RuntimeError('ACTUAL_SIZE_EXCEEDED')
                    self.disk(len(data))
            finally:
                response.close(); self.save()
            record['status'] = 'READ_COMPLETE'; self.save()
            return bytes(data)
        raise RuntimeError('REDIRECT_LIMIT')

    def blob(self, url, descriptor, directory, token, registry):
        digest = descriptor['digest']; size = descriptor['size']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or not isinstance(size, int) or size < 0:
            raise RuntimeError('INVALID_DESCRIPTOR')
        target = directory / 'blobs/sha256' / digest[7:]
        if target.exists():
            data = target.read_bytes()
        else:
            data = self.get(url, size, token, registry)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest[7:]:
            raise RuntimeError('CONTENT_IDENTITY_MISMATCH')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            self.disk(len(data)); target.write_bytes(data)
        return data


class AuthenticationRequired(Exception):
    """仅在内存传递公开registry认证挑战，不持久化token。"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--image', type=int, choices=range(4), required=True)
    args = parser.parse_args()
    # 输入来自获审附件，文件字节身份必须固定，不能替换为任意下载配置。
    data = args.input.read_bytes()
    if hashlib.sha256(data).hexdigest() != '6f8cde18b311d9e4f1f7f3ef82375890910078d82cbc8ca2d2eeef9ee23143a7':
        raise RuntimeError('UNAPPROVED_INPUT')
    candidate = json.loads(data)[args.image]
    name = candidate['reference'].rsplit(':', 1)[0]
    host, repository = ('registry-1.docker.io', 'library/' + name) if '/' not in name else name.split('/', 1)
    base = 'https://' + host + '/v2/' + repository
    download = Download(args.destination)
    token = None
    index_url = base + '/manifests/' + candidate['indexDigest']
    try:
        index = download.get(index_url, 128 * 1024)
    except AuthenticationRequired as failure:
        fields = dict(re.findall(r'(\w+)="([^"]*)"', str(failure)))
        realm = fields.pop('realm')
        if urllib.parse.urlsplit(realm).hostname not in ('auth.docker.io', 'quay.io', 'mcr.microsoft.com'):
            raise RuntimeError('AUTH_HOST_REJECTED')
        response = json.loads(download.get(realm + '?' + urllib.parse.urlencode(fields), 16 * 1024))
        token = response.get('token', response.get('access_token'))
        index = download.get(index_url, 128 * 1024, token, host)
    if 'sha256:' + hashlib.sha256(index).hexdigest() != candidate['indexDigest']:
        raise RuntimeError('INDEX_DIGEST_MISMATCH')
    expected = next(x for x in candidate['platforms'] if x['platform']['architecture'] == 'arm64')
    descriptor = next(x for x in json.loads(index)['manifests'] if x['digest'] == expected['digest'])
    if descriptor['platform'] != expected['platform']:
        raise RuntimeError('PLATFORM_MISMATCH')
    directory = download.root / str(args.image)
    manifest_raw = download.blob(base + '/manifests/' + descriptor['digest'], descriptor, directory, token, host)
    manifest = json.loads(manifest_raw)
    config = json.loads(download.blob(base + '/blobs/' + manifest['config']['digest'], manifest['config'], directory, token, host))
    if config['architecture'] != 'arm64' or config['os'] != 'linux':
        raise RuntimeError('CONFIG_PLATFORM_MISMATCH')
    for layer in manifest['layers']:
        download.blob(base + '/blobs/' + layer['digest'], layer, directory, token, host)
    # OCI入口只引用一个已核实ARM64官方manifest；不伪称裁剪后的index是官方index。
    (directory / 'index.json').write_text(json.dumps(dict(schemaVersion=2, manifests=[descriptor])) + '\n')
    (directory / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}\n')
    (directory / 'official-index.json').write_bytes(index)
    receipt = dict(reference=candidate['reference'], officialIndexDigest=candidate['indexDigest'],
        platformDigest=descriptor['digest'], configDigest=manifest['config']['digest'], platform=expected['platform'],
        layerBytes=sum(x['size'] for x in manifest['layers']), layers=len(manifest['layers']),
        budgetReservedBytes=download.state['reservedBytes'], receivedBytes=download.state['receivedBytes'],
        containerExecution=False, status='VERIFIED_OCI_LAYOUT')
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
