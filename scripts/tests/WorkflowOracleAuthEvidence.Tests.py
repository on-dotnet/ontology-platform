"""经 Oracle 浏览器场景重开入口检查纯认证资格。离线夹具只含公开身份和伪散列。"""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/maintenance'))
import workflow_m2_build as builds
import workflow_oracle_mapping_evidence as e
import workflow_oracle_mapping_identity_recovery as identity
import workflow_oracle_mapping_resume as resume


def at(seconds):
    return (dt.datetime(2026,11,20,tzinfo=dt.timezone.utc)+dt.timedelta(seconds=seconds)).isoformat()


class MemoryOriginals(e.Originals):
    def __init__(self):
        self.root=ROOT
        self.files={}

    def raw(self,name):
        return self.files[name]

    def save(self,name,data):
        self.files[name]=e.encoded(data)

    def observed(self,cid,argv,key,stage,start,end,timeout,parent,run,out,err):
        source=ROOT/'artifacts/workflow'/e.TASK/'commands'/run/cid
        environment='e'*64
        row=dict(schemaVersion=2,commandId=cid,taskId=e.TASK,runId=run,stage=stage,parentId=parent,started=True,signal=None,
                 cwd=str(ROOT),commandSummary=e.summary(argv),inputFingerprint=key,deadlineSeconds=timeout,elapsedSeconds=end-start,
                 environmentFingerprint=environment,startedAtUtc=at(start),endedAtUtc=at(end),classification='SUCCESS',exitCode=0)
        row['identity']=e.digest_value([key,environment,row['commandSummary']['sha256'],str(ROOT),timeout,
                                       e.sha((ROOT/'scripts/maintenance/workflow_execution.py').read_bytes())])
        for stream,raw in [('stdout',out),('stderr',err)]:
            row[stream]=dict(path=str(source/(stream+'.txt')),sha256=e.sha(raw),sizeBytes=len(raw))
            self.files[cid+'-'+stream+'.txt']=raw
        self.save(cid+'-receipt.json',row)


class AuthOriginalsTests(unittest.TestCase):
    def setUp(self):
        self.a=MemoryOriginals()
        self.patch(patch.object(e,'RUN',e.PRODUCT_RUN))
        self.cid='1'*32
        self.compile='2'*32
        self.nonce='3'*32
        self.parent='4'*32
        self.before='5'*32
        self.inside='6'*32
        self.after='7'*32
        self.secondary='a'*64
        self.host={'commandId':self.before,'services':{'api-secondary':{'containerId':self.secondary}}}
        self.tests=dict(receiptSha256='1'*64,inputKey='2'*64,outputKey='3'*64)
        self.report={'scope':'ORACLE_FOUR_CURRENT_SESSIONS','startedAtUtc':at(7),'finishedAtUtc':at(18),
                     'authIdentities':[],'http':[],'checks':[],'inputBinding':{'api':{'commandId':self.inside}},
                     'outputBinding':{'api':{'commandId':self.after}}}
        def add_check(name):
            self.report['checks'].append({'name':name,'status':'PASS'})
        for name in ('distinct_oidc_subjects','oracle_four_current_tickets'):add_check(name)
        self.obs=[]
        for i,(user,sub,role,sites) in enumerate(identity.ROSTER.values(),1):
            label=user.removeprefix('g2-')
            me=dict(subjectId=sub,displayName='合成开发身份 '+label,roles=[role],scopes=[dict(organizationId='org-demo',siteId=s) for s in sites])
            raw=json.dumps(me,ensure_ascii=True)
            h=e.sha(raw.encode())
            self.report['authIdentities'].append(dict(label=label,subjectId=sub,roles=me['roles'],scopes=me['scopes'],rawMe=raw,meSha256=h))
            for path,digest in [('/auth/csrf',str(i)*64),('/api/v1/platform/me',h)]:
                self.report['http'].append(dict(method='GET',path=path,status=200,elapsedMs=1,sha256=digest))
            for prefix in ('real_oidc_cookie_','oracle_current_original_subject_','oracle_current_role_sites_','oracle_synthetic_profile_shape_'):
                add_check(prefix+label)
            self.obs.append(dict(subjectId=sub,sessionHash=str(i)*64,ExpiresAtUtc=at(600),requiredUntilUtc=at(223),case='OMQ_BROWSER_SESSION_READY'))
        self.report['session']=dict(commandId=self.cid,nonce=self.nonce,observations=self.obs)
        self.build_args=['/dotnet/dotnet','build',builds.TARGETS['agent'],'--no-restore','--disable-build-servers','-m:1','-v:q']
        dll='OntologyPlatform.AgentTests.dll'
        prefix=str(Path(builds.TARGETS['agent']).parent/'bin/Debug/net10.0')+'/'
        files={dll:'a'*64}
        self.a.save('agent-build-binding.json',dict(outputs={prefix+dll:'a'*64},command=self.build_args))
        self.a.files['agent-bound-build.txt']=b'BUILD'
        self.snapshot=dict(files=files,inputs=self.tests,commandId=self.compile,environment={'toolEnvironment':'e'*64},taskId=e.TASK,resourceRun=e.PRODUCT_RUN)
        sid=e.digest_value(self.snapshot)
        self.directory=f'artifacts/workflow/{e.TASK}/{e.PRODUCT_RUN}/runtime-snapshots/{sid}'
        self.a.save('agent-snapshot.json',dict(self.snapshot,schemaVersion=2,snapshotId=sid,directory=self.directory))
        self.a.save('formal-api-inputs.json',{'sessionSnapshotId':sid})
        self.a.save('formal-api-compose.json',{'services':{'api-secondary':{'volumes':[str(ROOT/self.directory)+':/session-tests:ro']}}})
        self.a.observed(self.compile,['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*self.build_args],
                        self.tests['inputKey'],'command',0,1,180,None,'a'*32,b'BUILD',b'')
        self.store_session()
        self.times={self.before:(2,3),self.inside:(6,7),self.parent:(10,11),self.after:(16,17)}
        self.a.save('dispatch.json',{'host':self.host,'testedCommit':'e'*40})
        self.audit=dict(clientId=None,records=[])
        self.a.save('audit.json',self.audit)

    def patch(self,patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_actual_build_run_supports_exact_product_scope_and_rejects_other_named_runs(self):
        argv=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)',*self.build_args]
        for run in ('a'*32,e.PRODUCT_RUN,'implementation-01','other-task-01'):
            self.a.observed(self.compile,argv,self.tests['inputKey'],'command',0,1,180,None,run,b'BUILD',b'')
            with self.subTest(run=run):
                if run in ('a'*32,e.PRODUCT_RUN):
                    self.assertEqual(e.auth_test_snapshot(self.a,ROOT,self.tests)[0],ROOT/self.directory)
                else:
                    with self.assertRaisesRegex(ValueError,'OMQ_AUTH_BUILD_ARGV'):e.auth_test_snapshot(self.a,ROOT,self.tests)

    def store_session(self,**options):
        opts=dict(nonce=self.nonce,key=e.digest_value(self.tests),timeout=22,parent=self.parent,
                  out=e.encoded(self.obs)+b'\n',err=b'Total: 1\nFailed: 0\nSucceeded: 1\nSkipped: 0\n')
        opts.update(options)
        argv=resume.session_invocation(self.secondary,opts['nonce'],210)
        self.a.observed(self.cid,argv,opts['key'],'omq-session-real',12,14,opts['timeout'],opts['parent'],e.PRODUCT_RUN,opts['out'],opts['err'])

    def reopen(self,phase=None):
        def host_observed(archive,host,*args,**kw):
            if host['commandId']==self.parent:
                self.assertEqual(kw,dict(session_directory=ROOT/self.directory))
            begin,end=self.times[host['commandId']]
            return dict(commandId=host['commandId'],startedAtUtc=at(begin),endedAtUtc=at(end))
        self.a.save('audit.json',self.audit)
        entry={'host':'dispatch.json','stageInputs':phase or {},'audit':'audit.json'}
        with patch.object(e,'build_binding',return_value=self.tests),patch.object(e,'host_observation',side_effect=host_observed), \
             patch.object(e,'browser_report',return_value=(self.report,dict(startedAtUtc=at(5),endedAtUtc=at(19)))), \
             patch.object(e,'audit_observation',return_value=self.audit['records']):
            return e.reopen_browser(self.a,entry,ROOT,'s0-oracle-auth','healthy')

    def test_auth_reopens_four_actual_command_observations(self):
        self.assertEqual(self.reopen(),len(self.report['checks']))
        self.report['session']['observations']=copy.deepcopy(self.obs)
        self.report['session']['observations'][0]['sessionHash']='e'*64
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_TICKETS'):self.reopen()

    def test_wrong_nonce_fingerprint_deadline_parent_or_test_summary(self):
        for params,reason in (({'nonce':'a'*32},'OMQ_COMMAND_BINDING'),({'key':'0'*64},'OMQ_COMMAND_BINDING'),
                   ({'timeout':23},'OMQ_AUTH_SESSION_COMMAND'),({'parent':self.after},'OMQ_AUTH_SESSION_PARENT'),
                   ({'err':b'Total: 1\nFailed: 0\nSucceeded: 0\nSkipped: 1\n'},'MTP_FAILED_OR_SKIPPED')):
            with self.subTest(params=params):
                self.store_session(**params)
                with self.assertRaisesRegex(ValueError,reason):self.reopen()

    def test_substitution_with_reregistered_ticket_ttl_is_refused(self):
        for key,value,reason in [('requiredUntilUtc',at(220),'OMQ_AUTH_TTL'),('ExpiresAtUtc',at(223),'OMQ_AUTH_TTL'),
                                 ('case','INCORRECT','OMQ_AUTH_OBSERVATION')]:
            for obs in self.obs:obs[key]=value
            self.store_session()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,reason):self.reopen()
            for obs in self.obs:obs.update(requiredUntilUtc=at(223),ExpiresAtUtc=at(600),case='OMQ_BROWSER_SESSION_READY')

    def test_unfiltered_audit_and_reconstructed_http(self):
        self.audit['clientId']='a'*32
        with self.assertRaisesRegex(ValueError,'OMQ_AUDIT_UNFILTERED'):self.reopen()
        self.audit.update(clientId=None,records=[{'action':'SELECT'}])
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_SCOPE'):self.reopen()
        self.audit['records']=[]
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_SCOPE'):self.reopen({'fixtureBefore':{}})
        self.report['http'][0]['method']='POST'
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_HTTP'):self.reopen()
        self.report['http'][0]['method']='GET'
        ident=self.report['authIdentities'][0]
        ident['roles']=['platform.viewer']
        projected=json.loads(ident['rawMe']);projected['roles']=ident['roles']
        ident['rawMe']=json.dumps(projected)
        ident['meSha256']=self.report['http'][1]['sha256']=e.sha(ident['rawMe'].encode())
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_PROJECTION'):self.reopen()

    def test_wrong_assembly_mount_and_reregistered_build_artifacts(self):
        before=self.a.files.copy()
        spec=self.a.read('formal-api-compose.json')
        spec['services']['api-secondary']['volumes'].append('/other:/session-tests/x:ro')
        self.a.save('formal-api-compose.json',spec)
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_SESSION_RECIPE'):self.reopen()
        self.a.files=before
        self.a.files['agent-bound-build.txt']=b'substituted log'
        with self.assertRaisesRegex(ValueError,'OMQ_AUTH_AGENT_COMPILE'):self.reopen()

    def test_runtime_build_lookup_rejects_duplicate_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            host=dict(snapshotId='b'*64,composeSha256='c'*64,runtimeHelperSha256='d'*64)
            records=e.RuntimeOriginals(root,{'mode':'s0-oracle-auth','host':host})
            snapshots=records.area/'runtime-snapshots';snapshots.mkdir(parents=True)
            sid='e'*64
            (snapshots/(sid+'.json')).write_bytes(e.encoded(dict(commandId=self.compile)))
            (records.area/'formal-api-inputs.json').write_bytes(e.encoded(dict(snapshotId=host['snapshotId'],composeSha256=host['composeSha256'],
                                                                    relaySha256=host['runtimeHelperSha256'],sessionSnapshotId=sid)))
            for i in (1,2):
                p=records.area.parent/'commands'/(str(i)*32)/self.compile/'receipt.json'
                p.parent.mkdir(parents=True);p.write_bytes(b'{}')
                if i==1:self.assertEqual(records.read(self.compile+'-receipt.json'),{})
            with self.assertRaisesRegex(ValueError,'OMQ_AUTH_BUILD_ORIGINAL'):records.read(self.compile+'-receipt.json')


if __name__=='__main__':
    unittest.main()
