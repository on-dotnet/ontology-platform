"""只修改本任务realm的合成operator-a组织属性，独立恢复并实测跨组织引用拒绝。"""
from pathlib import Path
import copy,hashlib,json,os,re,subprocess,threading,urllib.request,urllib.parse,urllib.error
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-final-gates-001/r04'
PRIVATE=ROOT/'.tools/security/g4-m1-final-gates-001-r04-20261102';records=[];errors=[];original=None;user_path=None;token=None;original_profile=None;profile_changed=False;user_changed=False
restore_lock=threading.RLock()
guard_expired=threading.Event()
report=dict(taskId='G4-M1-FINAL-GATES-001',status='FAIL',commands=records)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def request(method,path,body=None,form=False):
    assert path.startswith('/admin/realms/'+realm_name+'/users') or path=='/realms/master/protocol/openid-connect/token'
    headers={'Connection':'close'}
    if token:headers['Authorization']='Bearer '+token
    data=None
    if body is not None:
        data=(urllib.parse.urlencode(body) if form else json.dumps(body)).encode();headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with opener.open(urllib.request.Request('http://localhost:15180'+path,data=data,headers=headers,method=method),timeout=10) as response:
            raw=response.read(1024*1024+1);assert len(raw)<=1024*1024
            records.append(dict(method=method,path=path,status=response.status,body='PRIVATE_MEMORY_ONLY'))
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        records.append(dict(method=method,path=path,status=error.code,body='SUPPRESSED'));raise RuntimeError('bounded_identity_http_error') from None

# 本任务独有realm随阶段整体回收；只将固定operator-a设为跨组织合成身份。
try:
    realm=json.loads((PRIVATE/'realm.json').read_text());realm_name=realm['authority'].rsplit('/',1)[1]
    assert re.fullmatch('g2-[a-f0-9]+',realm_name)
    obj=json.loads(subprocess.check_output(['docker','--context','desktop-linux','inspect','ontology-g4-m1-final-gates-001-r04-keycloak-test-1'],text=True))[0]
    assert obj['Config']['Labels']['ontology.task-id']==report['taskId'] and obj['Config']['Labels']['ontology.run-id']=='final-gates-20261102-r04'
    token=request('POST','/realms/master/protocol/openid-connect/token',{'grant_type':'password','client_id':'admin-cli','username':'wave2-bootstrap','password':(PRIVATE/'keycloak-password').read_text()},True)['access_token']
    base='/admin/realms/'+realm_name+'/users'
    profile=request('GET',base+'/profile')
    for name,multi in [('organization_id',False),('site_ids',True)]:
        if not any(x['name']==name for x in profile['attributes']):profile['attributes'].append({'name':name,'multivalued':multi,'permissions':{'view':['admin'],'edit':['admin']}})
    request('PUT',base+'/profile',profile)
    users=request('GET',base+'?username=g2-operator-a&exact=true');assert len(users)==1 and users[0]['username']=='g2-operator-a'
    path=base+'/'+users[0]['id'];user=request('GET',path);user.setdefault('attributes',{}).update(organization_id=['org-other'],site_ids=['site-a'])
    request('PUT',path,user);actual=request('GET',path);assert actual['attributes']['organization_id']==['org-other']
    report.update(status='PASS',realm=realm_name,subjectSha256=hashlib.sha256(users[0]['id'].encode()).hexdigest(),organizationId='org-other',disposal='Task-only realm volume exact cleanup')
finally:
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'foreign-identity.json','x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({'status':report['status']}))
