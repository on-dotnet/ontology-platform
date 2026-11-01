"""仅下载附件已绑定的一个Keycloak许可资产，复用取证总预算，不执行HTML。"""
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from forensic_images import Download, LIMIT

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'https://github.com/keycloak/keycloak/releases/download/26.8.1/third-party-notice-keycloak.html'
EXPECTED_SIZE = 7523238
EXPECTED_SHA = '14c17647c43f27315d148812a0be6b97b3cc9585463588ebbe67f7282cfe661d'


def main():
    folder = ROOT / 'artifacts/g4-m1-recovery-001/forensics'
    download = Download(folder)
    output = folder / 'keycloak-third-party-notice.html'
    if output.exists():
        data = output.read_bytes()
        if len(data) != EXPECTED_SIZE or hashlib.sha256(data).hexdigest() != EXPECTED_SHA:
            raise RuntimeError('EXISTING_NOTICE_IDENTITY_MISMATCH')
        print('VERIFIED_EXISTING_NOTICE'); return
    url = SOURCE
    for hop in range(2):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise RuntimeError('NOTICE_URL_REJECTED')
        if (hop == 0 and url != SOURCE) or (hop == 1 and parsed.hostname != 'release-assets.githubusercontent.com'):
            raise RuntimeError('NOTICE_HOST_REJECTED')
        reserve = 8*1024**2 + 65536
        if download.state['reservedBytes'] + reserve > LIMIT: raise RuntimeError('DOWNLOAD_BUDGET_EXCEEDED')
        download.disk(reserve)
        record = dict(host=parsed.hostname, asset='keycloak-26.8.1-third-party-notice', reservedBytes=reserve, receivedBytes=0, status='STARTED')
        download.state['reservedBytes'] += reserve; download.state['requests'].append(record); download.save()
        try: response = download.opener.open(urllib.request.Request(url, headers={'Accept-Encoding':'identity'}), timeout=20)
        except urllib.error.HTTPError as failure: response = failure
        record['httpStatus'] = response.status
        if hop == 0 and response.status == 302:
            url = urllib.parse.urljoin(url, response.headers['Location']); record['redirectHost'] = urllib.parse.urlsplit(url).hostname
            record['status'] = 'REDIRECT_BODY_NOT_READ'; response.close(); download.save(); continue
        if response.status != 200:
            response.close(); download.save(); raise RuntimeError('NOTICE_HTTP_REJECTED')
        data = bytearray(); started = time.monotonic()
        try:
            while True:
                if time.monotonic()-started > 120: raise RuntimeError('NOTICE_TIME_BUDGET')
                chunk = response.read(min(262144,EXPECTED_SIZE+1-len(data)))
                if not chunk: break
                data.extend(chunk); record['receivedBytes'] += len(chunk); download.state['receivedBytes'] += len(chunk)
                if len(data)>EXPECTED_SIZE: raise RuntimeError('NOTICE_SIZE_EXCEEDED')
        finally: response.close(); download.save()
        if len(data)!=EXPECTED_SIZE or hashlib.sha256(data).hexdigest()!=EXPECTED_SHA:
            raise RuntimeError('NOTICE_IDENTITY_MISMATCH')
        output.write_bytes(data); record['status']='VERIFIED_NOTICE'; download.save()
        result=dict(source=SOURCE,bytes=len(data),sha256=EXPECTED_SHA,bodyExecuted=False,linkedUrlsFollowed=False)
        (folder/'keycloak-notice-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return
    raise RuntimeError('NOTICE_REDIRECT_LIMIT')


if __name__ == '__main__':
    try: main()
    except Exception as failure:
        print(json.dumps(dict(status='REFUSED',category=type(failure).__name__,details='SUPPRESSED')))
        sys.exit(2)
