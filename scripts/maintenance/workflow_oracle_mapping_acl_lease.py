"""源 READ 撤权失败的单行修复，仅接受 685e 父窗及其已核实的准确原件。"""
import json
import os
import subprocess
from pathlib import Path

import workflow_execution as ex
import workflow_oracle_mapping_resume as resume
from workflow_oracle_mapping_postprobe import module, replace
from workflow_oracle_mapping_resources import require

ROOT = resume.ROOT
AREA = resume.AREA / 's2-s3-01'
HEAD = '095d2dd8ff957afa64f01fd938f18ffd357d8d5c'
PARENT = '685e33e9abd749168f6152789677859a'
QUERY = 'query-3e6bb50bdffe43feaa09736718b1dcb0'
DIRECTORY = AREA / ('lease-runner-' + PARENT)
BACKEND = '7cea75160944c1a12b91335cb3897ca9c30a6b299f300348ce6ed4382a45af3f'
BUILD_SHA = '98140e2316510e4a9ff5beb48f0881d4be0e754686fcb0fa57d83b1b9ffa6909'
TEST_NAME = 'acl-lease-pg-50c1dceed6854142b35198254d237664'
TEST_SHA = '6e8bdc7ed615d38d76067e549134d43c067b6518b158edf27fe970074ef62110'
CLOSE = AREA / 'closeout-70da4fc46f004170846f569dd421ec7a.json'
START = AREA / 'lease-3e6-startup.json'
TARGET = {
    'query-c2195dd80e21477c9f75f44cf29e8ad0': QUERY,
    'oracle-execution-2262397f3f0b4e4c884d201de49aea6e': 'oracle-execution-161cfdd65afd43b7b084b367a9588d8a',
    '1a396b17dc654ab09d72119870db69e0': '784c530b78e54b13945966d9ae4eca37',
    '7e3085f4533143fb84b49adc83159998': PARENT,
    'e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd': 'e04b175fec4de4f9f6437e3841c14fd312f304dfa6849b3c6d98a2a491655a1c',
    '49f86dd4e0ec3ae0c1d1c0749a2f6764361d3c555a1e3938f77e24c1e8ff0d92': '8fced87880bc598dc12652e9abf118810713a740dec02d0e225072f5831e736e',
    '5b786878c681a5a05c2cddd0079d654fd06d7d7ed05001cab1ca5822594c1f57': '94cced454818eaa4d88c6cf498bc159332a334352a92954c7da8d5fba7192a14',
    '9bc224697554422480d502c2d9b2262d': '4b8e81b0b1f1482ba5bf55aa167a6575',
    'e8ffbaa43779ae60fc76c3e67d703365719f0a698cafa3e43c1f385d0078edf0': '93e3800f00b74d5dfa1a9c6d7501a9f6e83358b217ac5aae59811197923fda77',
    'e080f26719734e7c84b9e941680ac565': '75de8de852b6435bad6defff146471e0',
    'fad1a66d2ce94270afdf349400efa63f': '92fa293202c54435a663c092fafd008c',
}


def template(name, digest):
    raw = subprocess.check_output(['git', 'show', HEAD + ':scripts/maintenance/' + name], cwd=ROOT)
    require(ex.sha(raw) == digest, 'SOURCE_ACL_LEASE_TEMPLATE')
    return raw.decode()


def runner(write=False):
    source = template('workflow_oracle_preparation_runner.py', '736d4ccff8d94f9c7d9a83f6bc52485c27aafbefc5b0e809b899a71d1b08e8c7')
    source = replace(source, {key: value for key, value in TARGET.items() if key in source})
    source = replace(source, {
        '451d26a9de8c77e9ec408d9b2208d2dcac4755e0': HEAD,
        'preparation-runner-dfe9e6c31322487c80499e9a1e9cd96c': DIRECTORY.name,
        'e8b537ed53b24faac246757d9de6592ae6a03ddeb96c81767f1b4373892d0877': BACKEND,
        'e87bdda008ad11071d34806bfa57a038fdc54c9923647f4b9e9db3950495d847': BUILD_SHA,
        's23-preparation-runner-build': 's23-source-acl-lease-runner-build',
    })
    return module(source, 'source-acl-lease-runner', write)


def compile_runner():
    require(not DIRECTORY.exists(), 'SOURCE_ACL_LEASE_BUILD_EXISTS')
    generated = DIRECTORY / 'generated'
    generated.mkdir(parents=True, mode=0o700)
    old = AREA / 'preparation-runner-dfe9e6c31322487c80499e9a1e9cd96c' / 'generated'
    for name, digest in {
        'SelfRegisteredExtensions.cs': 'b92a6a67737dc5a37317871707cfdb5b687861ec9baff41ea44b2a232cf14d1f',
        'MicrosoftTestingPlatformEntryPoint.cs': 'f051ec48a928f0a220cf43c8b4c19137a2248fb026b6d602bd51101fd0cecaca',
    }.items():
        raw = ex.ordinary(old / name).read_bytes()
        require(ex.sha(raw) == digest, 'SOURCE_ACL_LEASE_MTP_SOURCE')
        (generated / name).write_bytes(raw)
    return runner(True).compile_runner()


def verified_runner():
    return runner(True).verified_runner()


def maintenance(write=False):
    source = template('workflow_oracle_preparation_maintenance.py', '2670f1d2c64b4b8f50a4f0f0eae6bd8f1f09e8ddd0c33fa9419d0096b8be87a3')
    source = replace(source, {key: value for key, value in TARGET.items() if key in source})
    source = replace(source, {
        'workflow_oracle_preparation_runner': 'workflow_oracle_mapping_acl_lease',
        'preparation-': 'acl-lease-',
        'APIS_REMOVED_DATA_GENERATIONS_UNCHANGED': 'APIS_ABSENT_ONLY_MAINTENANCE_DATABASES_RUNNING',
        'acl-lease-pg-6b7675c651b84ffbb3d9d87683545f62': TEST_NAME,
        '1bd0437577fd7537b3b9c94593af1db56c2175959716c3f9b6200461177e0d68': TEST_SHA,
        "ids=resume.manifest()['ids'];require(set(ids)==set(sealed['after']['rows'])":
            "ids=maintenance_ids();require(set(ids)==set(sealed['after']['rows'])",
        "ids=resume.manifest()['ids'];names=sorted(ids)": "ids=maintenance_ids();names=sorted(ids)",
    })
    # 旧封闭过程已用准确关闭原件独立复核，此代仅验证已停机后重启的两个数据库。
    m = module(source, 'source-acl-lease-maintenance', write)
    m.maintenance_ids = maintenance_ids
    m.verify_seal = lambda: verify_closed(m)
    driver = template('workflow_oracle_preparation_maintenance.cs.txt', '3c0da10eb99d84b14598c1850c9d5349ef53794799869483e695446fc7efd501')
    target = Path(m.__file__).with_suffix('.cs.txt')
    if write and not target.exists():
        target.write_text(driver)
    require(ex.ordinary(target).read_text() == driver, 'SOURCE_ACL_LEASE_PG_DRIVER')
    return m


def maintenance_ids():
    require(os.environ.get('OMQ_PRODUCT_RUN') == resume.PRODUCT, 'SOURCE_ACL_LEASE_RUN')
    require(ex.sha(ex.ordinary(CLOSE).read_bytes()) == '952094d4182ccac4ea312917b653c1d527674dc9157aa64902e20afd540ccd9e'
            and ex.sha(ex.ordinary(START).read_bytes()) == '5b3969da472c3b25318f9a962b5b3fea79172160e6c3393bdc0e61e8a99699bf', 'SOURCE_ACL_LEASE_LIFECYCLE')
    close, opened = resume.load(CLOSE), resume.load(START)
    ids = {k: v for k, v in close['ids'].items() if k not in resume.APIS}
    require(close['status'] == 'PASS' and not close['remaining'] and resume.manifest()['ids'] == ids
            and opened['status'] == 'MAINTENANCE_DATABASES_READY' and opened['queryId'] == QUERY
            and set(opened['services']) == resume.running_roles() == {'oracle', 'platform-pg'}, 'SOURCE_ACL_LEASE_HOST_SCOPE')
    for role, entry in opened['services'].items():
        require(entry['id'] == ids[role] and entry['status'] == 'RUNNING', 'SOURCE_ACL_LEASE_HOST_ID')
    return {k: ids[k] for k in opened['services']}


def seal():
    m = maintenance(True)
    require(not m.SEAL.exists(), 'SOURCE_ACL_LEASE_SEAL_EXISTS')
    ids = maintenance_ids()
    after = m.host_rows('seal-after', ids)
    old = resume.load(CLOSE)
    value = dict(taskId=resume.TASK, runId=resume.PRODUCT, batch='s2-s3-01', queryId=QUERY, parentCommandId=PARENT,
                 apis=old['apis'], closeSha256=ex.sha(CLOSE.read_bytes()), startupSha256=ex.sha(START.read_bytes()),
                 after=after, status='APIS_ABSENT_ONLY_MAINTENANCE_DATABASES_RUNNING')
    resume.platform.save(m.SEAL, value)
    verify_closed(m)


def verify_closed(m):
    ids = maintenance_ids()
    value = resume.load(m.SEAL)
    close = resume.load(CLOSE)
    require((value['taskId'], value['runId'], value['batch'], value['queryId'], value['parentCommandId']) ==
            (resume.TASK, resume.PRODUCT, 's2-s3-01', QUERY, PARENT) and value['apis'] == close['apis']
            and value['closeSha256'] == ex.sha(CLOSE.read_bytes()) and value['startupSha256'] == ex.sha(START.read_bytes()), 'SOURCE_ACL_LEASE_SEAL_TARGET')
    names = sorted(ids)
    argv = [*m.DOCKER, 'inspect', '-f', resume.platform.HOST_FORMAT, *[ids[n] for n in names]]
    receipt, body, _ = m.reopen_command(value['after']['commandId'], argv, 'seal-after')
    require(value['after']['rows'] == dict(zip(names, (line.split('|') for line in body.decode().strip().splitlines()), strict=True)),
            'SOURCE_ACL_LEASE_SEAL_OBSERVATION')
    return receipt
