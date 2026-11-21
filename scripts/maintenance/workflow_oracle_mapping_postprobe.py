"""本次60a806准确失败的受限维护派生；只从已提交固定源生成，不改变旧维护或产品构建。"""
import json
import subprocess
import types
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_resume as resume
from workflow_oracle_mapping_resources import require

HEAD='6c5c6503ca97943978c8cf444a6a20622bdc815a'
ROOT=resume.ROOT
AREA=resume.AREA/'s2-s3-01'
DIRECTORY=AREA/'postprobe-runner-60a80687b58546afbd5abb19af3741c1'
BUILD_SHA='9f883c119ff59e418137182e2c2ea2addf592b3790deebc07df2ef6dca06487c'
TEST_NAME='postprobe-pg-fa19416f482b4647a74e6970cc33bc67'
TEST_SHA='8d638beed14473d27fd82449505710c70b9f90513e8e63bc4a94e2eb5ffe6b63'
TEST_INDEX='11d51ecc12c7f7c37c46d19570cd8389d5db4ff011c4dd45faa41a67f257e8c6'
RECOVERY_ATTEMPT='3cbe1105b4d849e1b0d84d4e89802427'
SEAL_SHA='50ec53a69c3f50860bde8f7e014172413889536a599d0dc0114f75b5553cdcac'
PROOF_SHA='2e47a33a305a101aa9675cf16eb56af36676f3bbab9abe8ea13eff7781464031'
PARENT='60a80687b58546afbd5abb19af3741c1'
FIXED={
 'query-c2195dd80e21477c9f75f44cf29e8ad0':'query-515cf74c1f53415785ff35c89ecd2fbb',
 'oracle-execution-2262397f3f0b4e4c884d201de49aea6e':'oracle-execution-4fe6a648f1b648a8a3dcb72c37ea7ecd',
 '1a396b17dc654ab09d72119870db69e0':'95b6542312d44761b6a57331436e07ea',
 '7e3085f4533143fb84b49adc83159998':PARENT,
 '5b786878c681a5a05c2cddd0079d654fd06d7d7ed05001cab1ca5822594c1f57':'2098ca90b8e43c1cd5ceb1077fa1f2adc2eb614cbb45748740fcdaa5e7784402',
 '9bc224697554422480d502c2d9b2262d':'521f417f797c4086ba3eebee0c2f7c30',
 'e8ffbaa43779ae60fc76c3e67d703365719f0a698cafa3e43c1f385d0078edf0':'e6c3fbc57d8767a60b87ec586fc205f37f7e328784f4347e37916c5d6ea621b5',
 'e080f26719734e7c84b9e941680ac565':'6ebb8589bd5642eea961f54ece75bcbf',
 'fad1a66d2ce94270afdf349400efa63f':'d677f407ae5e4e81a8ff7567b793d6de'}


def frozen(name,digest):
    """模板只能取准确已提交对象并核预置散列，外部文件不能提供可执行模板。"""
    raw=subprocess.check_output(['git','show',HEAD+':scripts/maintenance/'+name],cwd=ROOT)
    require(ex.sha(raw)==digest,'POSTPROBE_TEMPLATE');return raw.decode()


def replace(text,pairs):
    """限定白名单字符串必须实际出现；本轮目标、参数和模板都由代码固定。"""
    for left,right in pairs.items():
        require(left in text,'POSTPROBE_REPLACEMENT');text=text.replace(left,right)
    return text


def module(text,name,write=False):
    """准确派生源采用内容键保留，实测之后不得覆盖；loader执行前再核字节。"""
    path=AREA/(name+'-'+ex.sha(text.encode())+'.py')
    if write and not path.exists():path.write_text(text)
    require(path.is_file() and ex.ordinary(path).read_bytes()==text.encode(),'POSTPROBE_DERIVED_SOURCE')
    value=types.ModuleType(name);value.__file__=str(path);exec(compile(text,str(path),'exec'),value.__dict__);return value


def runner(write=False):
    text=frozen('workflow_oracle_preparation_runner.py','736d4ccff8d94f9c7d9a83f6bc52485c27aafbefc5b0e809b899a71d1b08e8c7')
    text=replace(text,{k:v for k,v in FIXED.items() if k in text})
    text=replace(text,{'451d26a9de8c77e9ec408d9b2208d2dcac4755e0':HEAD,
        'preparation-runner-dfe9e6c31322487c80499e9a1e9cd96c':DIRECTORY.name,'e87bdda008ad11071d34806bfa57a038fdc54c9923647f4b9e9db3950495d847':BUILD_SHA,
        's23-preparation-runner-build':'s23-postprobe-runner-build'})
    return module(text,'postprobe-runner-source',write)


def verified_runner():
    return runner().verified_runner()


def maintenance(write=False):
    text=frozen('workflow_oracle_preparation_maintenance.py','2670f1d2c64b4b8f50a4f0f0eae6bd8f1f09e8ddd0c33fa9419d0096b8be87a3')
    text=replace(text,FIXED)
    parent=ROOT/'artifacts/workflow'/resume.TASK/'commands'/resume.PRODUCT/PARENT/'receipt.json'
    dispatch=resume.AREA/('formal-run-s2-s3-oracle-'+PARENT+'.json')
    text=replace(text,{'baa50ea0b1515612b6fbb28b0df6c6a0f42dd5c6da2815866c7a5c4c0258a0f2':'23df0a5560460b8a6b0e3ff24c2caca26f45dfdff60a0a924ea16a60a66d9e01',
        '7157305e4b5a50374c32c1cdd1fa45c441bf84789d2a633ee6348d66fb698085':'fba9d7d31278760340af6e3b18e3ede61f4d0b6047b6fc172bc5f0137f9115d6',
        'workflow_oracle_preparation_runner':'workflow_oracle_mapping_postprobe','preparation-':'postprobe-',
        'postprobe-pg-6b7675c651b84ffbb3d9d87683545f62':TEST_NAME,
        '1bd0437577fd7537b3b9c94593af1db56c2175959716c3f9b6200461177e0d68':TEST_SHA})
    value=module(text,'postprobe-maintenance-source',write)
    source=frozen('workflow_oracle_preparation_maintenance.cs.txt','3c0da10eb99d84b14598c1850c9d5349ef53794799869483e695446fc7efd501')
    target=Path(value.__file__).with_suffix('.cs.txt')
    if write and not target.exists():target.write_text(source)
    require(ex.ordinary(target).read_text()==source,'POSTPROBE_TEST_DRIVER')
    return value


def lifecycle(root,previous,current,proof=None,archive=None):
    """沿同构建API更替的原校验规则，绑定上一窗四边和本次准确恢复命令。"""
    source=frozen('workflow_oracle_mapping_preparation_refresh.py','1dca5ed4cd69e7a6e42bb10db5dfc28c477b5523d1575555518687f8969268ef')
    source=replace(source,{
        'import workflow_oracle_mapping_access_refresh as refresh':'import workflow_oracle_mapping_preparation_refresh as refresh',
        '7e3085f4533143fb84b49adc83159998':PARENT,
        '451d26a9de8c77e9ec408d9b2208d2dcac4755e0':HEAD,
        '7157305e4b5a50374c32c1cdd1fa45c441bf84789d2a633ee6348d66fb698085':'fba9d7d31278760340af6e3b18e3ede61f4d0b6047b6fc172bc5f0137f9115d6',
        '877fffa7f1588dc89c677576d1d9110e288ee367a28a3de5bccb8edb067d0047':'c45eee8041dc5018d765098f309473770407af3aad95b654f99f990b4e7384a1',
        '497193cefee9445eb708881f077be62c':'1957bc75f68345d1b5d5504f9545d5b0',
        'prefix-observation-85751d15c3ea4bf6aedc6222739960de.json':'prefix-observation-00617fe776d243ea83e7bd1d52606b10.json',
        'f88056757c79d612016b375a7776ba304aeae8caf26f309b56942c79e1f7cf4f':'6f1a386819e0e71f069d99a13c89f7777c9fb78920a1183b258c64de378bf7f9',
        'import workflow_oracle_preparation_maintenance as a':'from workflow_oracle_mapping_postprobe import maintenance; a=maintenance()',
        "root/'scripts/maintenance/workflow_oracle_preparation_maintenance.py'":"Path(a.__file__)",
        '2670f1d2c64b4b8f50a4f0f0eae6bd8f1f09e8ddd0c33fa9419d0096b8be87a3':'c63bc7ade8a045766248e6713181bfc369722df006a7b58f68e8f74d94386d0f',
        'import workflow_oracle_preparation_runner as runner':'import workflow_oracle_mapping_postprobe as runner',
        'e5c8e3028ca649fc8b8270c1df1eb474':RECOVERY_ATTEMPT,
        'fdd3d8ab116b2af85ed3d8cd28fc18907773073cfa46d94262ba5228a6e880ee':SEAL_SHA,
        'c2e9730c607a5bb45d19af398cc3eaf60372a64b2804bfee6145193f7aef4693':PROOF_SHA,
        'preparation-':'postprobe-','postprobe-pg-6b7675c651b84ffbb3d9d87683545f62':TEST_NAME,
        '1bd0437577fd7537b3b9c94593af1db56c2175959716c3f9b6200461177e0d68':TEST_SHA,
        '1ab6f16d7827560e75592c83eb7100b9a8feb97c48af048977de170f71fa7109':TEST_INDEX,
        'THREE_PRIOR_EDGES_AND_SAME_BUILD_API_RESTART':'FOUR_PRIOR_EDGES_AND_SAME_BUILD_API_RESTART'})
    verifier=types.ModuleType('postprobe_fixed_lifecycle')
    exec(compile(source,'postprobe_fixed_lifecycle','exec'),verifier.__dict__)
    return verifier.lifecycle(root,previous,current,proof,archive)
