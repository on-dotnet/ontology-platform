"""同一批正常关闭后的原件连续性：只读图资格及准确资源生命周期。"""
import copy
import json
from pathlib import Path

import workflow_execution as ex
from workflow_oracle_mapping_resources import require

TASK='G4-ORACLE-MAPPING-QUERY-001'
RUN='product-resume-01'
RECOVERY='s0-recovery-01'
AREA=Path('artifacts/workflow')/TASK/RUN
CLOSE=AREA/'s2-s3-01/closeout-bedd150f37914d5a8f9998b78bf66c43.json'
GRAPH=AREA/'s2-s3-01/graph-continuity-final-auth-01.json'
OLD_RELEASE='d60d10638030402c8fcf6254bc782529'
NEW_RELEASE='0272acbf10e9422abac7242328420e51'
NEW_MANIFEST='f990c65d09fb75f9e606fbfae66663556b4940b0d892391f0a53973caa5140cb'
FUSEKI='52f84c336a3ade30341a3e20fbda302677fd77ea5a71237b801e3dc5b508d9a6'
PG='79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545'
GENERATION=('2026-11-21T01:19:10.950405047Z',94067)
START=Path('artifacts/workflow')/TASK/RECOVERY/'start-53eb7c42e23540d08253eb13be080989.json'
APPEND='\n<urn:synthetic:mapping:Reading> a <http://www.w3.org/2002/07/owl#Class> .\n<urn:synthetic:mapping:hasReading> a <http://www.w3.org/2002/07/owl#ObjectProperty>; <http://www.w3.org/2000/01/rdf-schema#domain> <urn:synthetic:mapping:Asset>; <http://www.w3.org/2000/01/rdf-schema#range> <urn:synthetic:mapping:Reading> .\n'
BRANCH="""    if cid=='52f84c336a3ade30341a3e20fbda302677fd77ea5a71237b801e3dc5b508d9a6' and (started,pid)==('2026-11-21T01:19:10.950405047Z',94067) and row.get('productUse')=='BLOCKED' and row.get('reason')=='ORACLE_ADMISSION_TDB_CURRENT_SCAN':
        from workflow_oracle_mapping_continuity import graph_qualification
        graph_qualification(platform.ROOT,cid,started,pid)
        return row['attempt']
"""


def raw(root,path,archive=None):
    from workflow_oracle_mapping_continuation import _read
    return _read(root,path,archive)


def command(root,cid,run,argv,stage,key,timeout,archive=None):
    """所有引用均重开真实命令身份及原双流；绝不以账本的PASS代替。"""
    from workflow_oracle_mapping_evidence import Originals
    base=Path('artifacts/workflow')/TASK/'commands'/run/cid
    class Read(Originals):
        def __init__(self):self.root=root
        def raw(self,name):
            require(name in (cid+'-receipt.json',cid+'-stdout.txt',cid+'-stderr.txt'),'S23_CONTINUITY_COMMAND_FILE')
            return raw(root,base/name.removeprefix(cid+'-'),archive)
    row,out,err=Read().command(cid,argv,stage,key,None,root,command_run=run)
    require(row['classification']=='SUCCESS' and row['exitCode']==0 and row['deadlineSeconds']==timeout,'S23_CONTINUITY_COMMAND_FAILED')
    for stream in ('stdout','stderr'):require(row[stream]['path']==str(root/base/(stream+'.txt')),'S23_CONTINUITY_STREAM_PATH')
    return row,out,err


def scan_argv(kind):
    query='SELECT ?s ?p ?o WHERE { ?s ?p ?o }' if kind=='default' else 'SELECT ?g ?s ?p ?o WHERE { GRAPH ?g { ?s ?p ?o } }'
    return ['docker','--context','desktop-linux','exec',FUSEKI,'curl','--noproxy','*','--silent','--show-error','--fail','--max-time','20',
        '-H','Accept: application/sparql-results+json','--data-urlencode','query='+query,'http://127.0.0.1:3030/ontology/query']


def expected_graphs(default,named,frozen):
    """旧全集必须等冻结指纹；新增预期只来自明确词汇增量，不复制观察值。"""
    import doris_keep_fuseki as rdf
    require(not default and rdf.fingerprint(default)==frozen['scan']['default']['sha256'],'S23_GRAPH_DEFAULT')
    old=[r for r in named if r['g']['value'].startswith('urn:ontology-platform:release:'+OLD_RELEASE+':')]
    require(len(old)==frozen['scan']['named']['rows'] and rdf.fingerprint(map(rdf.canonical,old))==frozen['scan']['named']['sha256'],'S23_GRAPH_OLD_SET')
    expected=copy.deepcopy(old)
    for item in old:
        row=copy.deepcopy(item);row['g']['value']=row['g']['value'].replace(OLD_RELEASE,NEW_RELEASE);expected.append(row)
    root='urn:synthetic:mapping:';rdf_type='http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
    triples=[(root+'Reading',rdf_type,'http://www.w3.org/2002/07/owl#Class'),
        (root+'hasReading',rdf_type,'http://www.w3.org/2002/07/owl#ObjectProperty'),
        (root+'hasReading','http://www.w3.org/2000/01/rdf-schema#domain',root+'Asset'),
        (root+'hasReading','http://www.w3.org/2000/01/rdf-schema#range',root+'Reading')]
    for triple in triples:
        row={k:dict(type='uri',value=v) for k,v in zip(('s','p','o'),triple,strict=True)}
        row['g']=dict(type='uri',value='urn:ontology-platform:release:'+NEW_RELEASE+':ontology');expected.append(row)
    require(sorted(map(rdf.canonical,named))==sorted(map(rdf.canonical,expected)),'S23_GRAPH_EXPECTED_SET')
    return dict(defaultRows=0,namedRows=len(expected),namedSha256=rdf.fingerprint(map(rdf.canonical,expected)),oldRelease=OLD_RELEASE,newRelease=NEW_RELEASE)


def graph_qualification(root,cid,started,pid,archive=None,upper=None):
    """本次准确新进程消费正常发布后的全图；冻结恢复检查点及失败start均保持原样。"""
    from workflow_oracle_mapping_evidence import utc
    import workflow_oracle_mapping_recovery_components as components
    require(cid==FUSEKI and (started,pid)==GENERATION,'S23_GRAPH_GENERATION')
    proof=json.loads(raw(root,GRAPH,archive));start=json.loads(raw(root,START,archive))
    require((proof['taskId'],proof['runId'],proof['batch'])==(TASK,RUN,'s2-s3-01') and proof['startSha256']==ex.sha(raw(root,START,archive)), 'S23_GRAPH_SCOPE')
    require(start['id']==cid and (start['startedAt'],start['pid'])==(started,pid) and start['stage']==RUN and start['role']=='fuseki'
        and start['status']=='RUNNING' and start['productUse']=='BLOCKED' and start['reason']=='ORACLE_ADMISSION_TDB_CURRENT_SCAN','S23_GRAPH_START')
    scans={}
    for kind in ('default','named'):
        args=scan_argv(kind);ref=proof['scans'][kind]
        row,out,err=command(root,ref,RUN,args,'s23-graph-continuity-'+kind,ex.sha(ex.encoded(args)),25,archive)
        require(not err and utc(started)<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'S23_GRAPH_SCAN_ORDER')
        value=json.loads(out);fields={'s','p','o'}|({'g'} if kind=='named' else set())
        require(set(value['head']['vars'])==fields and all(set(item)==fields for item in value['results']['bindings']),'S23_GRAPH_FIELDS')
        scans[kind]=value['results']['bindings']
    # Published源检查由精确SELECT原件而非当前观察图导出。
    sql=proof['publicationSql'].encode();args=['docker','--context','desktop-linux','exec','-i','--user','postgres',PG,'psql','-XwqAt','-d','mapping','-v','ON_ERROR_STOP=1']
    require(sql==publication_sql(),'S23_GRAPH_PUBLICATION_SQL')
    body=sql
    row,out,err=command(root,proof['publicationCommandId'],RUN,args,'omq-current-published-graphs-pg-releases',ex.sha(body),25,archive)
    require(not err and utc(started)<=utc(row['startedAtUtc']) and (upper is None or utc(row['endedAtUtc'])<=upper),'S23_GRAPH_PUBLICATION_ORDER')
    publications=[json.loads(line) for line in out.decode().splitlines() if line.strip()]
    check_publications(publications)
    frozen_raw=raw(root,AREA/'s2-s3-01/frozen-graphs-second-open.json',archive)
    require(ex.sha(frozen_raw)=='393a597292cfba79d9b772bf7bac9a34d3e7d843bcf0c7e9ed3e97e9fd87c328','S23_GRAPH_FROZEN_ORIGINAL')
    frozen=json.loads(frozen_raw)
    result=expected_graphs(scans['default'],scans['named'],frozen)
    require(proof['expected']==result,'S23_GRAPH_PROOF_RESULT')
    return result


def publication_sql():
    return b'BEGIN READ ONLY;\nSELECT json_build_array("ReleaseId", "ManifestHash", "ManifestJson", "SourcesJson")::text FROM publishing."Releases" WHERE "Published" ORDER BY "ReleaseId";\nROLLBACK;'


def check_publications(rows):
    """核两份正式manifest、完整四源hash及唯一精确ontology追加。"""
    require(len(rows)==2 and {r[0] for r in rows}=={OLD_RELEASE,NEW_RELEASE},'S23_GRAPH_PUBLICATIONS')
    sources={}
    for release,digest,manifest_text,source_text in rows:
        manifest=json.loads(manifest_text);source=json.loads(source_text)
        require(ex.sha(manifest_text.encode())==digest and manifest['ReleaseId']==release,'S23_GRAPH_MANIFEST')
        require(digest==({NEW_RELEASE:NEW_MANIFEST,OLD_RELEASE:'ab3f11b9320448c60f5aa77a28bc1f96505dbdffd063c4e73fc1b80ef4e159ba'}[release]),'S23_GRAPH_QUALIFIED_RELEASE')
        require(set(source)=={role+'Turtle' for role in ('Ontology','Vocabulary','Shapes','Data')},'S23_GRAPH_SOURCE_FIELDS')
        for role in ('Ontology','Vocabulary','Shapes','Data'):
            require(ex.sha(source[role+'Turtle'].encode())==manifest['Hashes'][role+'Hash'],'S23_GRAPH_SOURCE_HASH')
        require(manifest['OntologyGraphIri']=='urn:ontology-platform:release:'+release+':ontology'
            and manifest['DataGraphIri']=='urn:ontology-platform:release:'+release+':data','S23_GRAPH_IRI')
        sources[release]=source
    expected=copy.deepcopy(sources[OLD_RELEASE]);expected['OntologyTurtle']+=APPEND
    require(sources[NEW_RELEASE]==expected,'S23_GRAPH_SOURCE_DELTA')


def lifecycle_spec(role,cid,kind,root):
    """受控消费者自行推导argv、阶段与预算，不接受账本自报命令。"""
    if kind=='stopped':args=['inspect','-f','{{json .State}}',cid];stage='omq-recovery-stopped-state';run=RECOVERY;seconds=45
    elif kind=='data-start':args=['start',cid];stage='omq-recovery-start-'+role;run=RECOVERY;seconds=50
    elif kind=='remove':args=['rm',cid];stage='resume-remove-stateless';run=RUN;seconds=30
    elif kind=='absent':args=['ps','-aq','--no-trunc','--filter','id='+cid];stage='entry-api-absent-'+role;run=RUN;seconds=30
    elif kind=='api-create':args=['compose','-f',str(root/AREA/'formal-api-compose.json'),'create','--no-build','--pull','never',role];stage='resume-create-'+role;run=RUN;seconds=30
    elif kind=='api-id':args=['compose','-f',str(root/AREA/'formal-api-compose.json'),'ps','--all','-q',role];stage='resume-id-'+role;run=RUN;seconds=30
    elif kind=='api-start':args=['start',cid];stage='resume-start-'+role;run=RUN;seconds=40
    else:raise ValueError('S23_CONTINUITY_KIND')
    argv=['docker','--context','desktop-linux',*args]
    key=ex.sha(ex.encoded(argv if run==RECOVERY else args))
    return run,argv,stage,key,seconds


def lifecycle_command(root,cid,role,resource,kind,archive=None):
    run,argv,stage,key,seconds=lifecycle_spec(role,resource,kind,root)
    return command(root,cid,run,argv,stage,key,seconds,archive)


def find_command(root,role,resource,kind,lower,upper):
    from workflow_oracle_mapping_evidence import utc
    run,argv,stage,key,seconds=lifecycle_spec(role,resource,kind,root);matches=[]
    for path in (root/'artifacts/workflow'/TASK/'commands'/run).glob('*/receipt.json'):
        row=json.loads(ex.ordinary(path).read_bytes())
        if row.get('stage')==stage and row.get('inputFingerprint')==key and row.get('exitCode')==0 and lower<=utc(row['startedAtUtc'])<=utc(row['endedAtUtc'])<=upper:
            matches.append(row['commandId'])
    require(len(matches)==1,'S23_CONTINUITY_UNIQUE_'+role+'_'+kind)
    return matches[0]


def observed_oracle(root,host,archive=None):
    """原host完整Docker原件中的Oracle挂载及进程代次，不依赖精简host里的缺省字段。"""
    from workflow_oracle_mapping_platform import HOST_FORMAT
    from workflow_oracle_mapping_evidence import RuntimeOriginals
    selector=RuntimeOriginals(root,{'host':host})
    def matches(data):
        value=json.loads(data)
        return value.get('taskId')==TASK and value.get('runId')==RUN and value.get('snapshotId')==host['snapshotId'] and value.get('composeSha256')==host['composeSha256'] and value.get('relaySha256')==host['runtimeHelperSha256']
    path=selector.choose('formal-api-inputs*.json',matches)
    inputs=json.loads(raw(root,path.relative_to(root),archive))
    ids={k:v['containerId'] for k,v in host['services'].items()};roles=sorted(ids);source=host['oracle']['containerId']
    args=['docker','--context','desktop-linux','inspect','-f',HOST_FORMAT,*[ids[k] for k in roles],source]
    key=ex.sha(ex.encoded([inputs,ids,source,HOST_FORMAT]))
    row,out,err=command(root,host['commandId'],RUN,args,'omq-host-inspect',key,12,archive)
    values=out.decode().strip().splitlines();require(len(values)==len(roles)+1,'S23_CONTINUITY_HOST_ROWS')
    parts=values[-1].split('|');require(len(parts)==9,'S23_CONTINUITY_ORACLE_ROW')
    cid,image,task,run,state,pid,started,mounts,nets=parts
    require(cid==source and image==host['oracle']['imageId'] and (task,run,state)==(TASK,'implementation-01','running')
        and int(pid)>0 and list(dict(x.split('=') for x in nets.split()).values())==[host['oracle']['networkId']],'S23_CONTINUITY_ORACLE_OWNER')
    return row,dict(containerId=cid,pid=int(pid),startedAt=started,mounts=json.loads(mounts))


def lifecycle(root,previous,current,proof=None,archive=None):
    """准备时发现、重开时按固定引用核验全部允许变化的真实生命周期原件。"""
    from workflow_oracle_mapping_continuation import PREFIX,resumed_host
    from workflow_oracle_mapping_evidence import utc
    continuity=resumed_host(previous,current)
    oldrow,oldoracle=observed_oracle(root,previous,archive);newrow,neworacle=observed_oracle(root,current,archive)
    require(oldoracle['mounts']==neworacle['mounts'],'S23_CONTINUITY_ORACLE_MOUNTS')
    close=json.loads(raw(root,CLOSE,archive))
    require((close['taskId'],close['runId'],close['batch'],close['status'])==(TASK,RUN,'s2-s3-01','PASS') and close['remaining']==[],'S23_CONTINUITY_CLOSE')
    parent=json.loads(raw(root,Path('artifacts/workflow')/TASK/'commands'/RUN/PREFIX['commandId']/'receipt.json',archive))
    lower=utc(parent['endedAtUtc']);upper=utc(newrow['startedAtUtc'])
    require(utc(oldrow['endedAtUtc'])<=lower<upper,'S23_CONTINUITY_ORDER')
    manifests=[]
    for host in (previous,current):
        digest=host['resourceManifestSha256'];data=raw(root,AREA/('formal-resources-'+digest+'.json'),archive)
        require(ex.sha(data)==digest,'S23_CONTINUITY_MANIFEST_HASH');value=json.loads(data)
        require(value['ids']=={**{k:v['containerId'] for k,v in host['services'].items()},'oracle':host['oracle']['containerId']},'S23_CONTINUITY_MANIFEST_IDS')
        value['ids']={k:v for k,v in value['ids'].items() if k not in ('api','api-secondary')};manifests.append(value)
    require(manifests[0]==manifests[1],'S23_CONTINUITY_MANIFEST_DRIFT')
    references={} if proof is None else proof['commands'];consumed={}
    oldservices={**previous['services'],'oracle':oldoracle};newservices={**current['services'],'oracle':neworacle}
    require(close['ids']=={k:v['containerId'] for k,v in oldservices.items()},'S23_CONTINUITY_CLOSE_IDS')
    for role,old in oldservices.items():
        new=newservices[role];api=role in ('api','api-secondary')
        kinds=('remove','absent','api-create','api-id','api-start') if api else ('stopped','data-start')
        previous_end=lower
        for kind in kinds:
            resource=old['containerId'] if kind in ('remove','absent','stopped') else new['containerId']
            label=role+':'+kind
            cid=find_command(root,role,resource,kind,lower,upper) if proof is None else references[label]
            row,out,err=lifecycle_command(root,cid,role,resource,kind,archive)
            require(previous_end<=utc(row['startedAtUtc'])<=utc(row['endedAtUtc'])<=upper,'S23_CONTINUITY_COMMAND_ORDER')
            if kind=='stopped':
                state=json.loads(out);after={k:state[k] for k in ('Status','ExitCode','OOMKilled','FinishedAt')}
                require(after==close['data'][role]['after'] and after['Status']=='exited' and not after['OOMKilled'] and after['ExitCode'] in (0,143)
                    and not state['Error'] and utc(old['startedAt'])<utc(after['FinishedAt'])<utc(new['startedAt']),'S23_CONTINUITY_STOP_GENERATION')
            elif kind=='absent':require(not out.strip(),'S23_CONTINUITY_API_ABSENT')
            elif kind in ('remove','data-start','api-id','api-start'):require(out.decode().strip()==resource,'S23_CONTINUITY_ACTION_ID')
            if kind in ('data-start','api-start'):
                require(utc(row['startedAtUtc'])<=utc(new['startedAt'])<=utc(row['endedAtUtc']),'S23_CONTINUITY_START_GENERATION')
            consumed[label]=cid;previous_end=utc(row['endedAtUtc'])
    require(proof is None or references==consumed,'S23_CONTINUITY_EXTRA_COMMAND')
    graph=graph_qualification(root,newservices['fuseki']['containerId'],newservices['fuseki']['startedAt'],newservices['fuseki']['pid'],archive,upper)
    result=dict(continuity=continuity,commands=consumed,oracleMountSha256=ex.sha(ex.encoded(oldoracle['mounts'])),graphQualification=graph)
    require(proof is None or proof==result,'S23_CONTINUITY_PROOF_CHANGED')
    return result
