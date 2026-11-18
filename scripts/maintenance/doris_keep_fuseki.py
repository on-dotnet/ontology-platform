"""在准确原镜像与隔离卷上扫描 TDB2；独立预期来自平台 PG 的已发布源码/清单。"""
from contextlib import contextmanager
import hashlib
import json
import re
import subprocess
import time
from urllib.parse import quote

import doris_keep_preservation as keep
from doris_keep_drain import query


WITNESS = (
    'docs/evidence/G4-M4-QUERY-001/query-impl-01/browser-s1-1794657796193-result.json',
    'docs/evidence/G4-M5-INTEGRATION-001/integration-01/originals/integration-01/scenario-standard.json',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def published(platform):
    # 分别检查清单的原始字节和每份源码，返回值只在内存内用于隔离的参考图。
    sql = '''SELECT json_build_array("ReleaseId", "ManifestHash", "ManifestJson", "SourcesJson")::text
             FROM publishing."Releases" WHERE "Published" ORDER BY "ReleaseId";'''
    rows = {}
    for line in query(platform, 'BEGIN READ ONLY; ' + sql + ' ROLLBACK;'):
        key, digest, manifest_text, source_text = json.loads(line)
        manifest, sources = json.loads(manifest_text), json.loads(source_text)
        keep.require(re.fullmatch('[a-f0-9]{32}', key) and sha(manifest_text.encode()) == digest and
                     manifest['ReleaseId'] == key and key not in rows, 'PUBLISHED_MANIFEST')
        for role in ('Ontology', 'Vocabulary', 'Data', 'Shapes'):
            keep.require(sha(sources[role + 'Turtle'].encode()) == manifest['Hashes'][role + 'Hash'], 'PUBLISHED_SOURCE_HASH')
        for role in ('Ontology', 'Data'):
            keep.require(manifest[role + 'GraphIri'] == 'urn:ontology-platform:release:' + key + ':' + role.lower(),
                         'PUBLISHED_GRAPH_IDENTITY')
        rows[key] = (manifest, sources, digest)
    index = keep.PROJECTS.index(platform['project'])
    reference = keep.ROOT / WITNESS[index]
    evidence = json.loads(reference.read_text())
    if index == 0:
        key = evidence['snapshot']['ontologyReleaseId']
        keep.require(evidence['status'] == 'FOUND' and key in rows, 'M4_PUBLISHED_WITNESS')
    else:
        release = evidence['ontologyRelease']
        key = release['manifest']['releaseId']
        keep.require(key in rows and release['manifestHash'] == rows[key][2], 'M5_PUBLISHED_WITNESS')
    return rows, {'source': WITNESS[index], 'sha256': keep.digest(reference), 'releaseId': key}


def request(cid, url, accept, payload=None, method='GET', media=None):
    args = [*keep.DOCKER, 'exec', '-i', cid, 'curl', '--noproxy', '*', '--silent', '--fail',
            '--max-time', '20', '--max-filesize', str(32 * 1024**2), '-X', method, '-H', 'Accept: ' + accept]
    if payload is not None:
        args.extend(['-H', 'Content-Type: ' + media, '--data-binary', '@-'])
    result = subprocess.run([*args, 'http://127.0.0.1:3030/' + url], input=payload, capture_output=True, timeout=25)
    keep.require(result.returncode == 0, 'ISOLATED_HTTP_' + str(result.returncode))
    return result.stdout


@contextmanager
def original_reader(name, image):
    cid = keep.execute('create', '--network=none', '--pull=never', '--read-only', '--memory=896m', '--memory-swap=896m',
                       '--cpus=1', '--pids-limit=128', '--user=10001:10001', '--cap-drop=ALL',
                       '--security-opt=no-new-privileges', '--log-driver=none', '--tmpfs','/tmp:size=48m,mode=1777',
                       '--label', 'ontology.task-id='+keep.TASK, '--label','ontology.run-id='+keep.RUN,
                       '--label',keep.LABEL+'='+keep.ATTEMPT,*keep.mount(name, '/fuseki', False),
                       '--entrypoint=java',image,'-Xms96m','-Xmx480m','-Dlog4j.configurationFile=/opt/fuseki/g2-log4j2.properties',
                       '-jar','/opt/fuseki/fuseki-server.jar','--config=/opt/fuseki/g2-config.ttl')
    keep.assert_owner(cid)
    keep.record('created-isolated-tdb2-reader', cid)
    try:
        keep.start(cid)
        config = keep.execute('inspect','-f','{{.Image}} {{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{len .HostConfig.PortBindings}}',cid)
        keep.require(config.split() == [image,'none','true','0'], 'ISOLATED_TDB2_CONFIG')
        for _ in range(24):
            try:
                request(cid,'$/ping','text/plain')
                break
            except ValueError:
                if keep.execute('inspect','-f','{{.State.Running}}',cid) != 'true':
                    raise ValueError('TDB2_COPY_START_EXITED') from None
                time.sleep(0.5)
        else:
            raise ValueError('TDB2_COPY_START_TIMEOUT')
        yield cid
    finally:
        keep.assert_owner(cid)
        if keep.execute('inspect','-f','{{.State.Running}}',cid) == 'true':
            keep.execute('stop','--timeout=-1',cid,limit=35)
        observed = keep.helper_state(cid)
        keep.record('isolated-tdb2-reader-exit',cid,**observed)
        keep.require(observed['state']['Status']=='exited' and not observed['state']['OOMKilled'], 'TDB2_PROBE_STATE')
        keep.execute('rm',cid)
        keep.require(not keep.execute('ps','-aq','--no-trunc','--filter','id='+cid), 'TDB2_PROBE_NOT_REMOVED')
        keep.record('removed-isolated-tdb2-reader',cid)


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def fingerprint(values):
    return sha(('\n'.join(sorted(values))+'\n').encode())


def triples(cid, endpoint, graph):
    data = json.loads(request(cid,endpoint+'/data?graph='+quote(graph,safe=''),'application/rdf+json'))
    return {canonical([sub,pred,obj]) for sub,preds in data.items() for pred,objects in preds.items() for obj in objects}


def full_scan(cid):
    result = {}
    for name, sparql in [('default','SELECT ?s ?p ?o WHERE { ?s ?p ?o }'),
                         ('named','SELECT ?g ?s ?p ?o WHERE { GRAPH ?g { ?s ?p ?o } }')]:
        data = json.loads(request(cid,'ontology/query','application/sparql-results+json',sparql.encode(),'POST','application/sparql-query'))
        rows = data['results']['bindings']
        expected = {'s','p','o','g'} if name=='named' else {'s','p','o'}
        keep.require(set(data['head']['vars']) == expected and all(set(row)==expected for row in rows), 'TDB2_INCOMPLETE_ROW')
        result[name] = {'rows':len(rows),'sha256':fingerprint(map(canonical,rows))}
    return result


def verify_volume(row, platform, fact, archive):
    image = row['imageId']
    volume = row['project']+'_fuseki-data'
    keep.require(row['service']=='fuseki' and platform['project']==row['project'] and platform['service']=='platform-pg'
                 and archive.name==volume+'.tar' and str(archive.relative_to(keep.ROOT))==fact['privatePath'],'FUSEKI_SCOPE')
    releases, anchor = published(platform)
    with keep.scratch() as tmp, keep.helper(keep.mount(tmp,'/slot',False),write=True) as writer:
        keep.start(writer)
        keep.restore_empty(writer,archive,fact['sha256'])
        dirs = keep.execute('exec',writer,'find','/slot','-type','d','-name','Data-*','-printf','%P\n').splitlines()
        keep.require(dirs and all(re.fullmatch('databases/ontology/Data-[0-9]+',d) for d in dirs), 'UNRECOGNIZED_TDB2_DATABASE')
        with original_reader(tmp,image) as cid:
            scan = full_scan(cid)
            verified = []
            for key,(manifest,sources,digest) in releases.items():
                independent = {}
                for role, index in [('Ontology',0),('Vocabulary',2),('Data',3)]:
                    graph = 'urn:ontology-platform:keep-reference:'+key+':'+role.lower()
                    source = sources[role+'Turtle']
                    if source:
                        body = f'@base <https://ontology.invalid/source/{index}/> .\n'+source.lstrip('\ufeff')
                        request(cid,'validation/data?graph='+quote(graph,safe=''),'*/*',body.encode(),'PUT','text/turtle')
                        independent[role] = triples(cid,'validation',graph)
                    else:
                        independent[role] = set()
                for role in ('Ontology','Data'):
                    graph = manifest[role+'GraphIri']
                    actual = triples(cid,'ontology',graph)
                    expected = independent[role] | independent['Vocabulary'] if role=='Ontology' else independent[role]
                    keep.require(actual==expected,'PUBLISHED_GRAPH_CONTENT_MISMATCH')
                    verified.append({'graphIri':graph,'manifestHash':digest,'triples':len(actual),'rdfSha256':fingerprint(actual)})
            keep.require(verified and scan['named']['rows']>=sum(g['triples'] for g in verified), 'TDB2_GRAPH_COVERAGE')
        keep.require(keep.digest(archive)==fact['sha256'], 'SOURCE_ARCHIVE_CHANGED')
    return {'originalId':row['containerId'],'imageId':image,'archiveSha256':fact['sha256'],'isolatedReaderId':cid,
            'scope':'single configured persistent ontology dataset; validation dataset is memory-only','databaseGenerations':sorted(dirs),
            'fullRead':True,'scan':scan,'releaseAnchor':anchor,'publishedGraphsVerified':len(verified),'graphs':verified,
            'shutdownHook':'UNKNOWN','isolation':'network=none; zero host port bindings; restored scratch only','scratchRemoved':True}
