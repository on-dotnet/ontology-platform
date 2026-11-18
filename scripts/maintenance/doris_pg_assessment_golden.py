"""从已停 M5 平台 PG 的隔离副本核验单行 assessment；复用现有准确 ID 工具。"""
import base64
import json
import shutil
import time

import doris_keep_pg_recovery as pg
import doris_keep_preservation as keep
from workflow_doris_s1 import HOST, OUT, PLATFORM, ROOT, live_stack, record
import workflow_doris_vm as vm
import workflow_execution as execution


ORIGINAL='b71ef14e5e484253c0b435332c4480fc071268f634c0b049d5d4aff57c383912'
VOLUME='ontology-g4-m5-integration-01_platform-data'
ASSESSMENT='ma-ace12515d7804af2870f2a434c167951'
HISTORY=ROOT/'docs/evidence/G4-M5-INTEGRATION-001/integration-01/originals/integration-01'
PROOF=OUT/'pg-historical-assessment.json'


def original_state():
    archived=json.loads((HISTORY/'platform-resources.json').read_bytes())
    historical=json.loads((ROOT/'docs/evidence'/vm.TASK/vm.RUN/'readmission-03.json').read_bytes())
    vm.demand(archived['taskId']=='G4-M5-INTEGRATION-001' and any(row['id']==ORIGINAL for row in archived['resources'])
              and pg.IMAGE in (HISTORY/'platform-resources.json').read_text(),'M5_PLATFORM_ORIGINAL')
    state=pg.engine_state(ORIGINAL)
    vm.demand(state['Status']=='exited' and state['ExitCode']==0 and not state['OOMKilled']
              and state['FinishedAt'] in json.dumps(historical),'M5_ORIGINAL_SHUTDOWN')
    fmt='{{.Id}} {{.Image}} {{index .Config.Labels "ontology.task-id"}} {{index .Config.Labels "com.docker.compose.service"}}'
    vm.demand(keep.execute('inspect','-f',fmt,ORIGINAL).split()==[ORIGINAL,pg.IMAGE,'G4-M5-INTEGRATION-001','platform-pg'],'M5_PLATFORM_OWNER')
    mounts=json.loads(keep.execute('inspect','-f','{{json .Mounts}}',ORIGINAL))
    vm.demand([(v['Name'],v['Destination']) for v in mounts if v['Type']=='volume']==[(VOLUME,'/var/lib/postgresql')]
              and not keep.execute('ps','-q','--filter','volume='+VOLUME),'M5_EXACT_VOLUME')
    return state['FinishedAt']


def capture():
    vm.demand(not PROOF.exists(),'GOLDEN_ALREADY_CAPTURED')
    stopped=original_state()
    live=live_stack()
    platform=live['platform-pg']
    cap=int(14.25*vm.GIB)
    mem,cpu=map(int,keep.execute('info','-f','{{.MemTotal}} {{.NCPU}}').split())
    vm.demand(mem>=cap+2*vm.GIB and cpu>=9 and shutil.disk_usage(ROOT).free>=12*vm.GIB and
              json.loads(HOST.read_bytes())['status']=='EXITED','GOLDEN_CAPACITY')
    conf=json.loads(PLATFORM.read_bytes())
    mounts=json.loads(keep.execute('inspect','-f','{{json .Mounts}}',platform))
    vm.demand([(v['Name'],v['Destination']) for v in mounts if v['Type']=='volume']==[(conf['volumes']['platform-data'],'/var/lib/postgresql')]
              and not json.loads(keep.execute('volume','inspect','-f','{{json .Options}}',conf['volumes']['platform-data'])),'S1_PLATFORM_DURABILITY')
    drain='''SELECT (SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid())
        +(SELECT count(*) FROM connections."MappingJobs" WHERE "Status" IN ('QUEUED','RUNNING'))
        +(SELECT count(*) FROM connections."MappingOutboxs" WHERE "DispatchedAtUtc" IS NULL);'''
    for _ in range(2):
        vm.demand(keep.execute('exec',platform,'psql','-XwqAt','-U','postgres','-d','mapping','-c',drain)=='0','S1_PLATFORM_INFLIGHT')
        time.sleep(.25)
    result=dict(taskId=vm.TASK,runId=vm.RUN,attempt=keep.ATTEMPT,sourceId=ORIGINAL,volume=VOLUME,image=pg.IMAGE,finishedAt=stopped,
                vmBytes=mem,vmCpus=cpu,peakContainerCount=6,peakCapBytes=cap,phase='S1_PG_GOLDEN')
    attempt=OUT/('pg-assessment-attempt-'+keep.ATTEMPT+'.json')
    record(attempt,result)
    try:
        result['releasedCurrentPlatformSlot']=pg.native_stop(platform)
        with keep.scratch(retain_between_mounts=True) as scratch:
            with keep.helper([*keep.mount(VOLUME,'/source'),*keep.mount(scratch,'/slot',False)],write=True,image=pg.IMAGE) as copier:
                keep.start(copier)
                vm.demand(sorted(keep.helper_state(copier)['volumes'])==sorted([[VOLUME,'/source',False],[scratch,'/slot',True]])
                          and pg.control(copier,'/source')=='shut down','PG_COLD_VOLUME')
                size=int(keep.execute('exec',copier,'du','-sb','/source').split()[0])
                vm.demand(0<size<2*vm.GIB and not keep.execute('exec',copier,'ls','-A','/slot'),'PG_GOLDEN_COPY_LIMIT')
                before=keep.volume_digest(copier,'/source')
                keep.execute('exec',copier,'cp','-a','/source/.','/slot',limit=60)
                vm.demand(keep.volume_digest(copier,'/slot')==before==keep.volume_digest(copier,'/source')
                          and pg.control(copier,'/slot')=='shut down','PG_GOLDEN_COPY_CHANGED')
                result.update(copyBytes=size,copySha256=before,copierId=copier)
            with pg.isolated_server(scratch,'query') as server:
                # 固定 ID、库及三列，避免在命令回执中持久化整库或未授权的行。
                sql="""BEGIN READ ONLY; SET LOCAL statement_timeout='3s';
                    SELECT json_build_object('id',"Id",'contentHash',"ContentHash",'hex',encode("CanonicalBytes",'hex'))
                    FROM connections."MappingAssessments" WHERE "Id"='ma-ace12515d7804af2870f2a434c167951';
                    COMMIT;"""
                row=json.loads(keep.execute('exec','--user=postgres',server,'psql','-XwqAt','-v','ON_ERROR_STOP=1','-U','postgres','-h','/tmp','-d','query','-c',sql,limit=8))
                raw=bytes.fromhex(row['hex'])
                public=json.loads((HISTORY/'scenario-standard.json').read_bytes())['mappingAssessment']
                vm.demand(row['id']==ASSESSMENT==public['assessmentId'] and execution.sha(raw)==row['contentHash']
                          and json.loads(raw)==public,'PG_HISTORICAL_BYTES')
                result.update(assessmentId=row['id'],contentHash=row['contentHash'],sizeBytes=len(raw),
                              canonicalBytesBase64=base64.b64encode(raw).decode('ascii'),isolatedServer=server,queryRows=1)
                pg.native_stop(server)
        vm.demand(original_state()==stopped,'OLD_M5_STATUS_CHANGED')
    finally:
        if pg.engine_state(platform)['Status']=='exited':
            vm.demand(keep.execute('start',platform)==platform,'S1_PLATFORM_RESUME')
            for _ in range(30):
                if keep.execute('exec',platform,'sh','-c','pg_isready -q -U postgres -d mapping && echo ready || echo pending')=='ready': break
                time.sleep(.3)
            else: raise ValueError('S1_PLATFORM_READY_TIMEOUT')
        for _ in range(30):
            health=keep.execute('inspect','-f','{{with (index .State "Health")}}{{.Status}}{{else}}none{{end}}',platform)
            if health in ('healthy','none'): break
            time.sleep(.5)
        vm.demand(live_stack()==live,'S1_RESTORE_TOPOLOGY')
        result['currentPlatformRestored']=True
        record(attempt,result)
    result['status']='EXACT_SINGLE_ROW_VERIFIED'
    record(PROOF,result)
    print(result['status'],result['contentHash'],result['sizeBytes'])


def postcheck():
    proof=json.loads(PROOF.read_bytes())
    journal=keep.BASE/(proof['attempt']+'-lifecycle.json')
    events=json.loads(journal.read_bytes())
    scratch=next(row['id'] for row in events if row['action']=='created-volume')
    current=live_stack()
    removed={}
    for cid in (proof['copierId'],proof['isolatedServer']):
        removed[cid]=not keep.execute('ps','-aq','--no-trunc','--filter','id='+cid)
    absent=not keep.execute('volume','ls','-q','--filter','name=^'+scratch+'$')
    fmt='{{.Id}} {{.State.Status}} {{.State.OOMKilled}} {{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'
    rows=[keep.execute('inspect','-f',fmt,cid).split() for cid in current.values()]
    vm.demand(all(removed.values()) and absent and all(row[1:3]==['running','false'] for row in rows)
              and sum(int(row[3]) for row in rows)==proof['peakCapBytes'] and original_state()==proof['finishedAt'],'PG_POSTCONDITION')
    import datetime
    row=dict(observedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),temporaryContainersAbsent=removed,
             temporaryVolume=scratch,temporaryVolumeAbsent=absent,currentServices=rows,originalM5FinishedAt=proof['finishedAt'],
             currentContainerCount=len(rows),capBytes=sum(int(row[3]) for row in rows),nanoCpus=sum(int(row[4]) for row in rows),
             lifecycleSha256=execution.sha(journal.read_bytes()))
    record(OUT/('pg-golden-postcheck-'+keep.ATTEMPT+'.json'),row)
    print('SIX_RESOURCES_RESTORED',row['currentContainerCount'],row['capBytes'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postcheck',action='store_true')
    if parser.parse_args().postcheck: postcheck()
    else: capture()
