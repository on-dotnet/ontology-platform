"""只修改本任务realm的合成operator-a组织属性，独立恢复并实测跨组织引用拒绝。"""
from pathlib import Path
import copy,hashlib,json,os,re,subprocess,threading,urllib.request,urllib.parse,urllib.error
ROOT=Path(__file__).resolve().parents[2];ART=ROOT/'artifacts/g4-m1-recovery-001'
PRIVATE=ROOT/'.tools/security/g4-m1-recovery-001-20261101-01';records=[];errors=[];original=None;user_path=None;token=None;original_profile=None;profile_changed=False;user_changed=False
restore_lock=threading.RLock()
guard_expired=threading.Event()
report=dict(taskId='G4-M1-RECOVERY-001',status='FAIL',commands=records)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def request(method,path,body=None,form=False):
    assert path.startswith('/admin/realms/g2-05cf1b097c1a74bb/users') or path=='/realms/master/protocol/openid-connect/token'
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
def restore():
    global profile_changed,user_changed
    with restore_lock:
        if original is not None and user_changed:
            try:
                request('PUT',user_path,original)
                assert request('GET',user_path)['attributes']==original['attributes']
                report['userAttributesVerifiedBeforeProfileRestore']=True;user_changed=False
            except Exception as error:errors.append(dict(operation='restore_original_user',errorType=type(error).__name__))
        if original_profile is not None and profile_changed and not user_changed:
            try:
                request('PUT','/admin/realms/g2-05cf1b097c1a74bb/users/profile',original_profile)
                assert request('GET','/admin/realms/g2-05cf1b097c1a74bb/users/profile')==original_profile
                report['originalProfileRestored']=True;profile_changed=False
            except Exception as error:errors.append(dict(operation='restore_original_profile',errorType=type(error).__name__))
def guarded_mutation(kind,path,body):
    global user_changed,profile_changed
    with restore_lock:
        assert not guard_expired.is_set()
        if kind=='user':user_changed=True
        else:profile_changed=True
        request('PUT',path,body)
def expire_and_restore():
    guard_expired.set();restore()
guard=threading.Timer(60,expire_and_restore)
try:
    docker=['docker','--context','desktop-linux']
    for name in ['keycloak-test','platform-pg']:
        obj=json.loads(subprocess.check_output(docker+['inspect','ontology-g4-m1-recovery-001-'+name+'-1'],text=True,timeout=5))[0]
        assert obj['Config']['Labels']['ontology.task-id']=='G4-M1-RECOVERY-001' and obj['Config']['Labels']['ontology.run-id']=='recovery-20261101-01'
    realm=json.loads((PRIVATE/'realm.json').read_text());assert realm['authority']=='http://localhost:15180/realms/g2-05cf1b097c1a74bb'
    issued_file=PRIVATE/'cross-org-ref.json';assert not issued_file.is_symlink() and issued_file.stat().st_mode&0o077==0
    issued=json.loads(issued_file.read_text());assert re.fullmatch('[a-f0-9]{32}',issued['secretRef']) and re.fullmatch('[a-f0-9-]{36}',issued['subjectId'])
    sql='SELECT json_build_object(\'id\',"Id",\'owner\',"Owner",\'expiresAtUtc\',"ExpiresAtUtc",\'usedAtUtc\',"UsedAtUtc",\'organizationId\',"OrganizationId",\'serverNow\',now()) FROM connections."ConnectionSecrets" WHERE "Id"=\''+issued['secretRef']+'\' AND "Owner"=\''+issued['subjectId']+'\' AND "OrganizationId"=\'org-demo\' AND "SiteIds"=ARRAY[\'site-a\'] AND "UsedAtUtc" IS NULL AND "ExpiresAtUtc">now()+interval \'2 minutes\';'
    argv=docker+['exec','-i','ontology-g4-m1-recovery-001-platform-pg-1','psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt']
    x=subprocess.run(argv,input=sql,capture_output=True,text=True,timeout=5);assert x.returncode==0;foreign=json.loads(x.stdout);assert foreign.pop('owner')==issued['subjectId']
    runtime=json.loads((PRIVATE/'runtime.json').read_text());runtime.update(httpScenario='cross-org-secret',foreignSecretRef=foreign.pop('id'),foreignSecretOwnerSubjectId=issued['subjectId'])
    foreign['refSha256']=hashlib.sha256(runtime['foreignSecretRef'].encode()).hexdigest();foreign['ownerSha256']=hashlib.sha256(issued['subjectId'].encode()).hexdigest();report['foreignRefProvenance']=foreign
    records.append(dict(command=argv,sql='Exact private issuedRef and subjectId read; original query private-memory only',exitCode=x.returncode,stdout='PRIVATE_MEMORY_ONLY'))
    file=PRIVATE/'cross-org-secret-managed.json'
    with open(file,'x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(runtime,stream)
    token=request('POST','/realms/master/protocol/openid-connect/token',{'grant_type':'password','client_id':'admin-cli','username':'wave2-bootstrap','password':(PRIVATE/'keycloak-password').read_text()},form=True)['access_token']
    users=request('GET','/admin/realms/g2-05cf1b097c1a74bb/users?username=g2-operator-a&exact=true')
    assert len(users)==1 and users[0]['username']=='g2-operator-a' and re.fullmatch('[a-f0-9-]{36}',users[0]['id'])
    user_path='/admin/realms/g2-05cf1b097c1a74bb/users/'+users[0]['id']
    original_profile=request('GET','/admin/realms/g2-05cf1b097c1a74bb/users/profile')
    with open(PRIVATE/'cross-org-original-profile.json','x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(original_profile,stream)
    desired=copy.deepcopy(original_profile)
    assert not any(x['name'] in ('organization_id','site_ids') for x in desired['attributes'])
    desired['attributes'].extend([{'name':'organization_id','multivalued':False,'permissions':{'view':['admin'],'edit':['admin']}},{'name':'site_ids','multivalued':True,'permissions':{'view':['admin'],'edit':['admin']}}])
    guard.start()
    guarded_mutation('profile','/admin/realms/g2-05cf1b097c1a74bb/users/profile',desired)
    observed_profile=request('GET','/admin/realms/g2-05cf1b097c1a74bb/users/profile')
    assert [x for x in observed_profile['attributes'] if x['name'] not in ('organization_id','site_ids')]==original_profile['attributes']
    original=request('GET',user_path)
    if original.get('attributes',{}).get('organization_id')!=['org-demo'] or original.get('attributes',{}).get('site_ids')!=['site-a']:
        original.setdefault('attributes',{}).update(organization_id=['org-demo'],site_ids=['site-a'])
        report['originalAttributeSource']='repair_from_bootstrap_and_real_identity'
        guarded_mutation('user',user_path,original)
        assert request('GET',user_path)['attributes']==original['attributes']
    else:report['originalAttributeSource']='managed_original_attributes'
    with open(PRIVATE/'cross-org-original-user-managed.json','x',opener=lambda n,f:os.open(n,f,0o600)) as stream:json.dump(original,stream)
    changed=copy.deepcopy(original);changed['attributes']['organization_id']=['org-other'];guarded_mutation('user',user_path,changed)
    assert request('GET',user_path)['attributes']==changed['attributes']
    argv=['node','scripts/acceptance/g4-m1-http.mjs','--runtime-file',str(file),'--evidence-dir',str(ART/'http')]
    x=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=40)
    records.append(dict(command=argv,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==2
    report['status']='PASS'
finally:
    restore();guard.cancel()
    if report.get('userAttributesVerifiedBeforeProfileRestore') and report.get('originalProfileRestored'):
        argv=['node','scripts/acceptance/g4-m1-fault.mjs','--runtime-file',str(PRIVATE/'http-schema-change.json'),'--action','original-identity-check']
        try:
            x=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=25);records.append(dict(command=argv,exitCode=x.returncode,stdout=x.stdout,stderr=x.stderr));assert x.returncode==0
            report['originalIdentityNewLoginVerified']=True
        except Exception as error:errors.append(dict(operation='original_identity_new_login',errorType=type(error).__name__))
    report['cleanupErrors']=errors
    if errors:report['status']='FAIL'
    report['driverSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(ART/'cross-org-fault-profile-fixed.json','x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],originalIdentityRestored=report.get('originalIdentityNewLoginVerified'))))
if report['status']!='PASS':raise SystemExit(1)
