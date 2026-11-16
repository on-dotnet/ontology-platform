#!/usr/bin/env python3
"""M5薄消费者；复用既有PG执行能力，但Task/Run/私有目录/端口/场景均独立。"""
import argparse
from functools import partial
import importlib.util
import json
from pathlib import Path
import sys
from workflow_pg_profile import profile

ROOT=Path(__file__).resolve().parents[2]
TASK='G4-M5-INTEGRATION-001'
RUN='integration-01'
PROFILE=profile(TASK)
# 独立模块命名空间避免改变M4入口的默认身份；没有复制或动态改写源代码。
spec=importlib.util.spec_from_file_location('_m5_pg_consumer',ROOT/'scripts/maintenance/workflow_m4_query.py')
consumer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)
consumer.TASK=TASK
consumer.RUN=RUN
consumer.PROFILE=PROFILE
consumer.demand_aba_original=partial(consumer.demand_aba_original,task=TASK,run_id=RUN)
consumer.demand_qualification=partial(consumer.demand_qualification,task=TASK,run_id=RUN)


def no_legacy_qualification(*args,**kwargs):
    raise ValueError('INTEGRATION_USE_CURRENT_ACCEPTANCE_NOT_M4_QUALIFY')


consumer.qualify=no_legacy_qualification


def scenario(name):
    if name not in ('standard','numeric','safety','aba'):
        raise ValueError('INTEGRATION_SCENARIO_INVALID')
    consumer.SCENARIO=name


scenario('standard')


def __getattr__(name):
    return getattr(consumer,name)


def demand_ready(facts):
    """缺一项即失败；合成反例只检本判定器，不冒充真实场景ready。"""
    for key in ('api','web','build','session','connection','grant','activation','fixture','owner','budget'):
        if facts.get(key) is not True:raise ValueError('PREREQUISITE_STALE:'+key)
    return 'SCENARIO_READY'


def build_api():
    """第一次API启动前完成离线构建与本任务完整只读快照。"""
    from workflow_execution import sha,encoded
    from workflow_m4_query_runtime import freeze,verify
    output=ROOT/'artifacts/workflow'/TASK/RUN
    output.mkdir(parents=True,exist_ok=True)
    before=consumer.runtime_source_inputs()
    result=consumer.runtime_command('query-api-bound-build',['/usr/local/share/dotnet/dotnet','build','backend/src/Hosts/OntologyPlatform.Api',
        '--no-restore','--disable-build-servers','-m:1','-v:q'],timeout=180,offline=True)
    if before!=consumer.runtime_source_inputs():raise ValueError('INTEGRATION_BUILD_INPUT_DRIFT')
    snapshot=freeze(ROOT,ROOT/'backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0',output/'runtime-snapshots',
                    before,result.receipt['commandId'],consumer.runtime_environment_identity(),task=TASK,run_id=RUN)
    binaries=verify(ROOT,snapshot,task=TASK,run_id=RUN)
    (output/'runtime-snapshot-current.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    record=dict(taskId=TASK,runId=RUN,commandId=result.receipt['commandId'],inputs=before,binaries=binaries,inputHash=sha(encoded(before)))
    (output/'runtime-api-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return dict(status='BUILT_FROZEN',snapshotId=snapshot['snapshotId'],commandId=result.receipt['commandId'])


def prepare_runtime():
    """沿用现有配方生成新私有身份，首启挂已冻结快照；不启动旧任务。"""
    from workflow_m4_query_runtime import verify
    output=ROOT/'artifacts/workflow'/TASK/RUN
    snapshot=json.loads((output/'runtime-snapshot-current.json').read_text())
    binaries=verify(ROOT,snapshot,task=TASK,run_id=RUN)
    result=consumer.runtime_prepare()
    path=output/'runtime-compose.json';compose=json.loads(path.read_text())
    compose['services']['api']['volumes'][0]=str(ROOT/snapshot['directory'])+':/app:ro'
    path.write_text(json.dumps(compose,indent=2)+'\n')
    old=json.loads((output/'runtime-build-binding.json').read_text())
    binaries.update({p:h for p,h in old.items() if '/runtime-helper/' in p})
    (output/'runtime-build-binding.json').write_text(json.dumps(binaries,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['structural','host-preflight'])
    args=parser.parse_args()
    if args.command=='structural':print(json.dumps(consumer.structural(ROOT,TASK)))
    else:return consumer.host('preflight')
    return 0


if __name__=='__main__':sys.exit(main())
