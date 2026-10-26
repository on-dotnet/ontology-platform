from pathlib import Path
import json, secrets, subprocess, time, urllib.request, urllib.error, urllib.parse
name='g2-shacl-poc-'+secrets.token_hex(5)
root=Path('/private/tmp')/name
root.mkdir()
config='''@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix ja: <http://jena.hpl.hp.com/2005/11/Assembler#> .
[] a fuseki:Server ; fuseki:services ( <#validation> ) .
<#validation> a fuseki:Service ; fuseki:name "validation" ;
 fuseki:dataset <#memory> ;
 fuseki:endpoint [ fuseki:operation fuseki:query ; fuseki:name "query" ] ;
 fuseki:endpoint [ fuseki:operation fuseki:gsp-rw ; fuseki:name "data" ] ;
 fuseki:endpoint [ fuseki:operation fuseki:shacl ; fuseki:name "shacl" ] .
<#memory> a ja:MemoryDataset .
'''
(root/'config.ttl').write_text(config)
records=[]
def run(args):
 p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 records.append({'command':args,'exitCode':p.returncode,'output':p.stdout})
 if p.returncode: raise RuntimeError(p.stdout)
 return p.stdout.strip()
def check(label,ok,detail=None):
 records.append({'check':label,'status':'PASS' if ok else 'FAIL','detail':detail})
 if not ok: raise AssertionError(label)
try:
 run(['docker','run','--detach','--name',name,'--publish','127.0.0.1::3030','--memory','512m','--cpus','1','--mount',f'type=bind,src={root},dst=/poc,readonly','--entrypoint','java','fuseki:8b85cd963ab3910a87ff4d69819a814fcc536d5f','-Xmx256m','-jar','/opt/fuseki/fuseki-server.jar','--config=/poc/config.ttl'])
 port=run(['docker','port',name,'3030/tcp']).rsplit(':',1)[1]
 origin='http://127.0.0.1:'+port
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def http(path,method='GET',body=None,accept='application/json'):
  req=urllib.request.Request(origin+path,data=body.encode() if body is not None else None,method=method,headers=({'Content-Type':'text/turtle; charset=utf-8','Accept':accept} if body is not None else {'Accept':accept}))
  with opener.open(req,timeout=10) as resp:return resp.status,resp.read().decode()
 for _ in range(40):
  try:
   http('/$/ping',accept='text/plain');break
  except (OSError,urllib.error.URLError): time.sleep(.5)
 else:raise TimeoutError('Fuseki startup')
 graph='urn:g2:poc:validation'
 path='/validation/data?graph='+urllib.parse.quote(graph,safe='')
 good='''@prefix ex: <urn:g2:poc:> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:heat a ex:Heat ; ex:key "炉次一"@zh ; ex:value "01"^^xsd:integer ; ex:unknown [ ex:note "保留"@zh ] .
'''
 shapes='''@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <urn:g2:poc:> .
ex:Shape a sh:NodeShape ; sh:targetClass ex:Heat ; sh:property [ sh:path ex:key ; sh:minCount 1 ; sh:message "缺业务键"@zh ] .
'''
 check('RIOT accepts UTF8 Turtle',http(path,'PUT',good)[0] in (200,201,204))
 status,report=http('/validation/shacl?graph='+urllib.parse.quote(graph,safe=''),'POST',shapes,'application/rdf+json')
 rdf=json.loads(report)
 checks=[v for predicates in rdf.values() for p,values in predicates.items() if p=='http://www.w3.org/ns/shacl#conforms' for v in values]
 check('real SHACL conforming standard RDF report',status==200 and checks[0]['value']=='true',rdf)
 status,export=http(path,accept='text/turtle')
 check('memory graph preserves typed lexical form', '01' in export,export)
 query='SELECT ?note WHERE { GRAPH <'+graph+'> { <urn:g2:poc:heat> <urn:g2:poc:unknown> ?b . ?b <urn:g2:poc:note> ?note } }'
 s,j=http('/validation/query?query='+urllib.parse.quote(query,safe=''),'GET')
 check('unknown blank-node assertion preserved',json.loads(j)['results']['bindings'][0]['note']['value']=='保留')
 bad='@prefix ex: <urn:g2:poc:> . ex:heat a ex:Heat .'
 http(path,'PUT',bad)
 status,report=http('/validation/shacl?graph='+urllib.parse.quote(graph,safe=''),'POST',shapes,'application/rdf+json')
 rdf=json.loads(report)
 check('nonconforming also HTTP200 and false',status==200 and any(v['value']=='false' for ps in rdf.values() for p,vs in ps.items() if p.endswith('#conforms') for v in vs),rdf)
 for suffix in ['focusNode','resultPath','resultMessage']:
  check('negative has '+suffix,any(p.endswith('#'+suffix) for ps in rdf.values() for p in ps))
 try:http(path,'PUT','this is not Turtle')
 except urllib.error.HTTPError as err:check('invalid Turtle rejected by RIOT',err.code==400)
 else:check('invalid Turtle rejected by RIOT',False)
 print('PASS: real Jena memory parsing/SHACL/lexical/report PoC')
except Exception as e:
 records.append({'status':'FAIL','category':type(e).__name__,'detail':str(e)})
 print('FAIL:',type(e).__name__,str(e))
 raise
finally:
 logs=subprocess.run(['docker','logs',name],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 records.append({'containerLog':logs.stdout})
 subprocess.run(['docker','rm','--force',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 (root/'result.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
 print('Evidence:',root)
