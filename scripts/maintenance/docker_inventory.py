#!/usr/bin/env python3
"""Read only allowlisted Docker identities, references and logical capacity.

Never inspect environment, build arguments, full container configs or volume bytes.
Unknown resources remain AMBIGUOUS until a reviewed exact-ID decision is supplied.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from cleanup_resources import run, read_json, safe_docker_snapshot, history_refs, Refused

LABELS = ('org.opencontainers.image.source','io.ontology-platform.task-id','io.ontology-platform.run-id',
          'io.ontology-platform.context-sha256','com.docker.compose.project','com.docker.compose.service')


def labels_template():
    return '{'+','.join(json.dumps(k)+':{{json (index .Labels '+json.dumps(k)+')}}' for k in LABELS)+'}'


def observe(decisions=None):
    decisions=decisions or {}
    containers=[]
    for ident in run(['docker','container','ls','--all','--no-trunc','--quiet']).stdout.splitlines():
        value=safe_docker_snapshot('docker-container',ident)
        value['Labels']=read_json(run(['docker','container','inspect','--format',labels_template().replace('.Labels','.Config.Labels'),ident]).stdout)
        containers.append(value)
    volumes=[]
    for name in run(['docker','volume','ls','--quiet']).stdout.splitlines():
        value=safe_docker_snapshot('docker-volume',name)
        value['Labels']=read_json(run(['docker','volume','inspect','--format',labels_template(),name]).stdout)
        value['references']=[c['Id'] for c in containers if any(m.get('Type')=='volume' and m.get('Name')==name for m in c['Mounts'])]
        volumes.append(value)
    images=[]
    for ident in sorted(set(run(['docker','image','ls','--all','--quiet','--no-trunc']).stdout.splitlines())):
        value=safe_docker_snapshot('docker-image',ident)
        template='{"RepoDigests":{{json .RepoDigests}},"Size":{{json .Size}},"Created":{{json .Created}},"Labels":'+labels_template().replace('.Labels','.Config.Labels')+'}'
        value.update(read_json(run(['docker','image','inspect','--format',template,ident]).stdout))
        value['references']=[c['Id'] for c in containers if c['Image']==ident]
        images.append(value)
    histories=[]
    for ref in history_refs():
        histories.append(safe_docker_snapshot('docker-history',ref))
    networks=[]
    for ident in run(['docker','network','ls','--no-trunc','--quiet']).stdout.splitlines():
        template='{"Id":{{json .Id}},"Name":{{json .Name}},"Driver":{{json .Driver}},"Containers":{{json .Containers}},"Labels":'+labels_template()+'}'
        networks.append(read_json(run(['docker','network','inspect','--format',template,ident]).stdout))
    backend={
        'context':run(['docker','context','show']).stdout.strip(),
        'engineId':run(['docker','info','--format','{{.ID}}']).stdout.strip(),
        'bridgeId':run(['docker','network','inspect','bridge','--format','{{.Id}}']).stdout.strip(),
        'buildxVersion':run(['docker','buildx','version']).stdout.strip(),
        'builder':run(['docker','buildx','inspect','desktop-linux']).stdout.strip(),
        'version':read_json(run(['docker','version','--format','{{json .}}']).stdout)}
    for kind,values,key in [('container',containers,'Id'),('volume',volumes,'Name'),('image',images,'Id'),('history',histories,'Ref'),('network',networks,'Id')]:
        for value in values:
            decision=decisions.get(kind+':'+value[key])
            if decision:
                if not all(decision.get(k) for k in ('classification','reason','releaseCondition')):
                    raise Refused('Every reviewed decision requires classification/reason/releaseCondition')
                value['decision']=decision
            else:
                value['decision']={'classification':'AMBIGUOUS','reason':'Exact owner/recovery classification has not been reviewed', 'releaseCondition':'Match exact ID to task runtime/manifest and prove recovery or retention before action'}
    return dict(schemaVersion=1,status='OBSERVED',observedAt=dt.datetime.now(dt.timezone.utc).isoformat(),backend=backend,
                containers=containers,volumes=volumes,images=images,history=histories,networks=networks,
                counts=dict(containers=len(containers),volumes=len(volumes),images=len(images),history=len(histories),networks=len(networks)),
                capacity=run(['docker','system','df','--format','{{json .}}']).stdout,
                detailedCapacity=run(['docker','system','df','-v']).stdout,
                physicalReclaimedBytes='NOT_VERIFIED',limitations='Read-only metadata; no volume contents or environment read. Shared image layers must not be summed. No physical APFS reclaim claim.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decisions',type=Path)
    args=parser.parse_args()
    try:
        decisions=read_json(args.decisions.read_text()) if args.decisions else None
        print(json.dumps(observe(decisions),ensure_ascii=False,indent=2))
        return 0
    except (Refused,OSError,ValueError,TypeError,KeyError) as ex:
        print('BLOCKED: '+(str(ex) if isinstance(ex,Refused) else type(ex).__name__),file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
