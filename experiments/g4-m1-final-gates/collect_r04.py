"""仅采集本任务当前R04的原始日志、只读审计/激活与资源身份，秘密在内存扫描。"""
import argparse,json,hashlib,subprocess,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];TASK='G4-M1-FINAL-GATES-001'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['r04','r04-final'],required=True);args=parser.parse_args()
    phase=args.phase;run='final-gates-20261102-'+phase;project='ontology-g4-m1-final-gates-001-'+phase;art=ROOT/'artifacts/g4-m1-final-gates-001'/phase;private=ROOT/('.tools/security/g4-m1-final-gates-001-'+phase+'-20261102')
    patterns=set()
    def walk(v):
        if isinstance(v,dict):
            for key,item in v.items():
                if isinstance(item,str) and len(item)>=8 and any(x in key.lower() for x in ('password','secret','token','healthkey')) and not any(x in key.lower() for x in ('file','path','version')):patterns.add(item.encode())
                walk(item)
        elif isinstance(v,list):
            for x in v:walk(x)
    for f in private.rglob('*.json'):walk(json.loads(f.read_text()))
    for name in ('reader-password','postgres-password','platform-password','keycloak-password','s3-access','s3-secret','api/g4-key','api/keyring.pfx','server.key','wrong-san.key'):
        b=(private/name).read_bytes();patterns.add(b);patterns.add(base64.b64encode(b))
    records=[];docker=['docker','--context','desktop-linux'];scan=[]
    for service in ('platform-pg','keycloak-test','api','web','fuseki','rustfs'):
        o=json.loads(subprocess.check_output(docker+['inspect',project+'-'+service+'-1'],text=True))[0];assert o['Config']['Labels']['ontology.task-id']==TASK and o['Config']['Labels']['ontology.run-id']==run
        image=json.loads(subprocess.check_output(docker+['image','inspect',o['Image']],text=True))[0];assert image['Architecture']=='arm64'
        records.append({'name':service,'id':o['Id'],'image':o['Image'],'descriptor':image['Descriptor'],'state':o['State'],'mounts':o['Mounts'],'memory':o['HostConfig']['Memory'],'labels':o['Config']['Labels']})
        x=subprocess.run(docker+['logs',o['Id']],capture_output=True,timeout=15);assert x.returncode==0;raw=x.stdout+x.stderr;assert not any(p in raw for p in patterns),'known_private_value_in_log'
        log={'containerId':o['Id'],'command':docker+['logs',o['Id']],'exitCode':0,'sha256':hashlib.sha256(raw).hexdigest(),'rawBytes':len(raw),'rawUtf8':raw.decode()};(art/(service+'-log.json')).write_text(json.dumps(log,indent=2)+'\n');scan.append({'name':service,'sha256':log['sha256'],'knownPrivateMatch':False})
    platform=next(x for x in records if x['name']=='platform-pg')
    sql='''SELECT json_build_object('audits',(SELECT json_agg(row_to_json(t)) FROM governance.audit_records t),'active',(SELECT json_agg(row_to_json(t)) FROM publishing."ActiveReleases" t),'activations',(SELECT json_agg(row_to_json(t)) FROM publishing."Activations" t),'releaseCount',(SELECT count(*) FROM publishing."Releases"),'connectionsCount',(SELECT count(*) FROM connections."Connections"));'''
    x=subprocess.run(docker+['exec','-i',platform['id'],'psql','-U','platform','-d','platform','-qAt','-v','ON_ERROR_STOP=1'],input='BEGIN READ ONLY;SET LOCAL statement_timeout=\'3s\';'+sql+'ROLLBACK;',text=True,capture_output=True,timeout=10);assert x.returncode==0
    data=json.loads(x.stdout);(art/'db-readback.json').write_text(json.dumps({'taskId':TASK,'runId':run,'containerId':platform['id'],'operation':'fixed read-only audit/activation query','exitCode':0,'data':data},indent=2)+'\n')
    (art/'runtime-witness.json').write_text(json.dumps({'taskId':TASK,'runId':run,'status':'PASS','resources':records,'logScan':scan,'knownPatternCount':len(patterns)},indent=2)+'\n');print(json.dumps({'status':'PASS','logs':len(scan),'audits':len(data['audits'])}))
if __name__=='__main__':main()
