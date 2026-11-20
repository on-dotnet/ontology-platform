"""按本次正式 BFF 的新挑战、回调、服务器票据及同票 /me 核验四个冻结平台身份。"""

import copy
import hashlib
import json
import re
from pathlib import Path

TASK = 'G4-ORACLE-MAPPING-QUERY-001'
RUN = 's0-recovery-02'
BASE = '454d1a2f17581673cbbf44900a5fe241d603f5ef'
ISSUER = 'http://localhost:15743/realms/g2-180e1435711f03fa'
CLIENT = 'g2-180e1435711f03fa-bff'
ME = '/api/v1/platform/me'
LOGIN = 'http://localhost:15741/auth/login?returnUrl=%2Fapi%2Fv1%2Fplatform%2Fme'
KID = 'YDFz4TE4iNk_YhJPHaKPFznjrVccyduoMhlSVekbC1c'
MATERIAL = '1a7699986838eab6b51f7700ed353bb8d711b13af7f8852939826e9958fb7f75'
ARCHIVE = '87dd320d0bb8813bf44ffdc149e88298c249fcabc75c663e2e6c387f20a90409'
STORE = 'OntologyPlatform.Api.Security.PostgresTicketStore'
ROSTER = {
    'operator': ('g2-operator-ab', '5af20722-3900-4de9-b23a-7dcae3ca5927', 'platform.operator', ['site-a', 'site-b']),
    'auditor': ('g2-auditor-ab', '650199ae-8bd4-430a-885d-71cd69b6781e', 'platform.auditor', ['site-a', 'site-b']),
    'activator': ('g2-operator-a', 'bcf7f7f8-6af0-4f94-a28c-1220461ee62e', 'platform.operator', ['site-a']),
    'reader': ('g2-viewer-a', 'f902a743-7079-4e22-a643-a51deb027e89', 'platform.viewer', ['site-a']),
}
SUBJECTS = {item[1]: item for item in ROSTER.values()}
WORKERS = {
    'Microsoft.AspNetCore.Hosting.GenericWebHostService',
    'Microsoft.AspNetCore.DataProtection.Internal.DataProtectionHostedService',
    'OpenTelemetry.Extensions.Hosting.Implementation.TelemetryHostedService',
    'Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckPublisherHostedService',
    'Microsoft.Extensions.ServiceDiscovery.ServiceDiscoveryHostedService',
    'Yarp.ReverseProxy.Management.ProxyConfigManager',
}
EPHEMERAL_TABLES = {'governance.MappingAuthorizationEpochs', 'governance.server_sessions', 'governance.audit_records'}


def check(condition, code):
    if not condition:
        raise ValueError('OMQ_IDENTITY_' + code)


def hexid(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{'+str(size)+'}', value) is not None


def frozen_inputs(root, fixture_path=None, *, fixture_bytes=None):
    """以 Base 的已知源码/原件交叉证明四个不同主体、冻结 client 和唯一 RS256 签名键。"""
    root = Path(root)
    check(fixture_bytes is None or (isinstance(fixture_bytes,bytes) and fixture_path is None), 'FIXTURE_SOURCE')
    history = root/'docs/evidence'/TASK
    previous = history/'s0-recovery-01/originals'
    files = {
        'bootstrap': (root/'infra/security/bootstrap-keycloak.py', 'b397271399a40c63b9320cb133b58272d5198a86f278e564b382f2e08bec6c95'),
        'fixture': (Path(fixture_path) if fixture_path else root/'artifacts/workflow'/TASK/'implementation-01/runtime-fixture.json',
                    '5f5e12e5ddb269f145bd60f8f47b5ce9991ef51cbe5c84b56e5e9bee276a2a9f'),
        'ready': (history/'implementation-01/s0-blocked/originals/browser-s0-oracle-ready-1795104215090.json',
                  '05a65c1ffa9b0ad06900382df4b46aff062011485e8ca5ce491e3141aa1280ae'),
        'keys': (previous/'checkpoint-ca3d35a7e5f94e539cd24ec39b8f7c0b.json', 'abee065e0089abb5bef8881f62719e3de4e48d8ea9bd724f15f66afacb5ed5f2'),
        'archives': (previous/'archive-ledger.json', '270fca4d7f40f2fb1c1fee1ccf5e40bb00ac0509445e07d26f86287573315617'),
    }
    values = {}
    for key, (path, expected) in files.items():
        raw = fixture_bytes if key == 'fixture' and fixture_bytes is not None else path.read_bytes()
        check(hashlib.sha256(raw).hexdigest() == expected, 'FROZEN_'+key.upper())
        if key != 'bootstrap':
            values[key] = json.loads(raw)
    check(values['fixture']['subjects'] == {k: item[1] for k, item in ROSTER.items()}, 'FIXTURE_SUBJECTS')
    ready = values['ready']
    check(ready['taskId'] == TASK and ready['mode'] == 's0-oracle-ready' and ready['status'] == 'PASS'
          and ready['inputsUnchanged'] is True and [o['subjectId'] for o in ready['scenarioReady']['session']['observations']]
          == [v[1] for v in ROSTER.values()], 'READY_SUBJECTS')
    passed = {c['name'] for c in ready['checks'] if c['status'] == 'PASS'}
    check(all('real_oidc_cookie_'+v[0].removeprefix('g2-') in passed and 'current_subject_'+k in passed
              for k,v in ROSTER.items()), 'READY_ACCOUNTS')
    identity = values['keys']['observation']['stable']['oidc']
    signing = [k for k in identity['keys'] if k['use'] == 'sig']
    check(identity['issuer'] == ISSUER and identity['client'] == CLIENT and len(identity['keys']) == 2 and
          signing == [dict(kid=KID, alg='RS256', use='sig', kty='RSA', materialSha256=MATERIAL)], 'SIGNER')
    check(values['archives']['archives']['platform/keycloak-test.tar']['sha256'] == ARCHIVE, 'ARCHIVE')
    return {key: expected for key, (_, expected) in files.items()}


def epoch_details_sql():
    """单一只读快照返回稳定审计/票据摘要，绝不导出票据原件或实际会话引用。"""
    return b'''BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone TO 'UTC';
SET LOCAL statement_timeout TO '5s';
SELECT json_build_object('epoch',(SELECT "Revision" FROM governance."MappingAuthorizationEpochs" WHERE "OrganizationId"='org-demo'),
 'sessions',(SELECT coalesce(json_object_agg(encode(sha256(convert_to(s."Id",'UTF8')),'hex'),
   encode(sha256(convert_to(to_jsonb(s)::text,'UTF8')),'hex')),'{}'::json) FROM governance.server_sessions s),
 'audit',(SELECT coalesce(json_object_agg(a."Id",json_build_object('sha256',encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex'),
   'action',a."Action",'actor',a."Actor",'correlation',a."CorrelationId",'outcome',a."Outcome")),'{}'::json) FROM governance.audit_records a));
COMMIT;
'''


def qualify(events, attempt, started_ms, ended_ms):
    """严格四主体完成入口；无认证、部分认证和已写票但缺正式投影均不能通过。"""
    observed = qualify_partial(events, attempt, started_ms, ended_ms)
    check(observed['status']=='FOUR_NORMAL_AUTHENTICATIONS_VERIFIED','FOUR_COMPLETED_SUBJECTS')
    return observed


def qualify_partial(events, attempt, started_ms, ended_ms):
    """验证完整事件前缀。仅无票的孤立挑战可按等待收尾，残缺票据仍保留给 PG 核验。"""
    try:
        return _read_events(events, attempt, started_ms, ended_ms)
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('OMQ_IDENTITY_EVENT_SCHEMA') from exc


def _read_events(events, attempt, started_ms, ended_ms):
    check(hexid(attempt,32) and type(started_ms) is int and type(ended_ms) is int and
          0 <= ended_ms-started_ms <= 16*60*1000 and isinstance(events,list) and 2 <= len(events) <= 120, 'WINDOW')
    rows = {}
    operations = []
    flows = {}
    stored = {}
    correlations = set()
    epoch_windows = []
    ready = False
    census = False
    previous = started_ms
    for event in events:
        check(isinstance(event,dict) and set(event) == {'kind','attempt','utc','details'} and event['attempt'] == attempt
              and isinstance(event['details'],dict)
              and type(event['utc']) is int and previous <= event['utc'] <= ended_ms, 'EVENT_BINDING')
        previous = event['utc']
        d = event['details']
        kind = event['kind']
        if kind == 'census':
            check(not census and not ready and d['disabled'] is True and d['automatic'] is False and
                  d['signingKid'] == KID and d['material'] == MATERIAL and len(d['workers']) > 0
                  and 'Microsoft.AspNetCore.Hosting.GenericWebHostService' in d['workers']
                  and set(d['workers']) <= WORKERS and {ME,'/auth/login','/signin-oidc'} <= set(d['routes'])
                  and all(not s.startswith('/api/') or s.startswith('/api/v1/platform/') or s=='/api/{**reservedPath}'
                          for s in d['routes']), 'CENSUS')
            census = True
            continue
        if kind == 'ready':
            check(census and not ready and d == dict(login=LOGIN,issuer=ISSUER,client=CLIENT,noAutomaticKeys=True,
                  deniedBusinessRoutes=True,meWithoutSession=401,ticketStore=STORE),'READY')
            ready = True
            continue
        flow = d.get('flow')
        check(ready and hexid(flow,32), 'FLOW')
        if kind == 'challenge':
            check(flow not in flows and d['pkce']=='S256' and d['responseType']=='code' and
                  d['statePresent'] is True and d['noncePresent'] is True and
                  sum(v['state']!='complete' for v in flows.values())<12, 'CHALLENGE')
            flows[flow] = {'state':'challenge','utc':previous}
        elif kind == 'ticketOperation':
            check(flow in flows and d['action'] in ('Store','Renew','Remove') and hexid(d['rowRef'],64)
                  and isinstance(d['correlation'],str) and 1<=len(d['correlation'])<=64 and
                  type(d['epochBefore']) is int and type(d['epochAfter']) is int and
                  d['epochAfter']-d['epochBefore'] in ((0,) if d['action']=='Store' else (0,1)), 'TICKET_OPERATION')
            if d['action']=='Store':
                check(flows[flow]['state']=='challenge' and d['rowRef'] not in stored.values()
                      and d['correlation'] not in correlations,'DUPLICATE_STORE')
                stored[flow]=d['rowRef']
                correlations.add(d['correlation'])
                flows[flow].update(state='stored',correlation=d['correlation'])
            else:
                check(stored.get(flow)==d['rowRef'],'TICKET_FLOW_BINDING')
            operations.append(d)
        elif kind == 'callback':
            stores = [o for o in operations if o['flow']==flow and o['action']=='Store']
            check(flow in flows and flows[flow]['state']=='stored' and d['status']==302 and d['returnPath']==ME
                  and d['ticketStored'] is True and len(stores)==1 and stores[0]['correlation']==d['correlation']
                  and type(d['epochBefore']) is int and type(d['epochAfter']) is int
                  and d['epochBefore']<=stores[0]['epochBefore']<=stores[0]['epochAfter']<=d['epochAfter'], 'CALLBACK')
            flows[flow].update(state='callback',correlation=d['correlation'])
            epoch_windows.append([d['epochBefore'],d['epochAfter']])
        elif kind == 'me':
            check(flow in flows and flows[flow]['state']=='callback' and d['status']==200 and d['sub'] in SUBJECTS
                  and d['sub'] not in rows and d['issuer']==ISSUER and d['audience']==CLIENT and d['alg']=='RS256'
                  and d['kid']==KID and d['material']==MATERIAL and d['signatureVerified'] is True
                  and d['lifetimeVerified'] is True and type(d['iat']) is int and type(d['exp']) is int
                  and flows[flow]['utc']//1000 <= d['iat'] <= previous//1000 < d['exp']
                  and type(d['epochBefore']) is int and type(d['epochAfter']) is int and d['epochAfter']>=d['epochBefore'], 'CURRENT_IDENTITY')
            account, sub, role, sites = SUBJECTS[d['sub']]
            check((d['account'],d['roles'],d['org'],d['sites'])==(account,[role],'org-demo',sites),'PLATFORM_PROJECTION')
            flows[flow]['state']='complete'
            epoch_windows.append([d['epochBefore'],d['epochAfter']])
            rows[sub] = {'flow':flow,'correlation':flows[flow]['correlation'],'sub':sub,'account':account,
                         'roles':[role],'org':'org-demo','sites':sites,'iat':d['iat'],'exp':d['exp']}
        else:
            raise ValueError('OMQ_IDENTITY_EVENT_KIND')
    check(census and ready,'ENTRY_NOT_READY')
    pending={flow:v['state'] for flow,v in flows.items() if v['state']!='complete'}
    if set(rows)==set(SUBJECTS) and len(flows)==4 and not pending:
        status='FOUR_NORMAL_AUTHENTICATIONS_VERIFIED'
    elif len(rows)<4 and all(state=='challenge' for state in pending.values()):
        status='WAITING_FOR_USER_AUTH'
    else:
        status='BLOCKED'
    return dict(status=status,attempt=attempt,subjects=rows,operations=operations,pending=pending,epochWindows=epoch_windows)


def qualify_pg(before, after, events, details_before, details_after):
    """按实际 Store 数量逐次对账，零登录与部分登录仍必须保护原行、审计和业务引用。"""
    pre,post=before['stable'],after['stable']
    check(set(pre)==set(post) and all(pre[k]==post[k] for k in pre if k!='tables'),'PG_REFERENCES')
    check(set(pre['tables'])==set(post['tables']) and EPHEMERAL_TABLES<=set(post['tables'])
          and all(pre['tables'][k]==post['tables'][k] for k in pre['tables'] if k not in EPHEMERAL_TABLES),'PG_BUSINESS')
    rows=events['subjects']; ops=events['operations']
    sessions=details_before['sessions']; current=details_after['sessions']
    old=details_before['audit']; new=details_after['audit']
    check(set(sessions)<=set(current) and set(old)<=set(new) and all(old[k]==new[k] for k in old),'PG_OLD_RECORDS')
    stores=[o for o in ops if o['action']=='Store']
    created={o['rowRef'] for o in stores}
    changed={k for k in sessions if sessions[k]!=current[k]}
    updated={o['rowRef'] for o in ops if o['action'] in ('Renew','Remove') and o['epochAfter']>o['epochBefore']}
    check(len(created)==len(stores) and set(current)-set(sessions)==created and changed==updated & set(sessions)
          and all(o['rowRef'] in current for o in ops), 'PG_SESSION_WRITES')
    epoch=details_before['epoch']
    check(type(epoch) is int and epoch>=0, 'PG_INITIAL_EPOCH')
    for op in ops:
        check(op['epochBefore']==epoch,'PG_EPOCH_BINDING')
        epoch=op['epochAfter']
    check(epoch==details_after['epoch'], 'PG_FINAL_EPOCH')
    check(all(details_before['epoch']<=start<=end<=epoch for start,end in events['epochWindows']), 'PG_REQUEST_EPOCH')
    additions=[new[k] for k in set(new)-set(old)]
    logins=[v for v in additions if v['action']=='authentication.login']
    login={v['correlation']:v['actor'] for v in logins}
    check(len(logins)==len(login)==len(set(login.values())) and set(login)=={o['correlation'] for o in stores}
          and set(login.values())<=set(SUBJECTS) and all(login.get(r['correlation'])==sub for sub,r in rows.items()),
          'PG_LOGIN_BINDING')
    # 缺失 /me 的新票据仍要和同事务登录审计核对；这条审计本身不证明签名身份已完成。
    actors={o['flow']:login[o['correlation']] for o in stores}
    expected=[('authentication.login',subject,correlation) for correlation,subject in login.items()]
    expected.extend(('authentication.logout',actors[o['flow']],o['correlation']) for o in ops
                    if o['action']=='Remove' and o['epochAfter']>o['epochBefore'])
    check(all(v['outcome']=='allowed' for v in additions) and sorted((v['action'],v['actor'],v['correlation']) for v in additions)==sorted(expected),'PG_AUDIT_WRITES')
    for stable,detail in ((pre,details_before),(post,details_after)):
        check(stable['tables']['governance.server_sessions']['count']==len(detail['sessions'])
              and stable['tables']['governance.audit_records']['count']==len(detail['audit'])
              and stable['tables']['governance.MappingAuthorizationEpochs']['count']==1,'PG_COUNTERS')
        digests={'governance.server_sessions':list(detail['sessions'].values()),
                 'governance.audit_records':[row['sha256'] for row in detail['audit'].values()]}
        for table,hashes in digests.items():
            check(all(hexid(value,64) for value in hashes) and
                  hashlib.sha256(''.join(sorted(hashes)).encode('ascii')).hexdigest()==stable['tables'][table]['sha256'],
                  'PG_DETAIL_TABLE_DIGEST')
    expected_changes={'governance.MappingAuthorizationEpochs':epoch!=details_before['epoch'],
                      'governance.server_sessions':bool(created or changed),'governance.audit_records':bool(additions)}
    for name,modified in expected_changes.items():
        first,last=pre['tables'][name]['sha256'],post['tables'][name]['sha256']
        check(hexid(first,64) and hexid(last,64) and (first!=last)==modified,'PG_TABLE_DIGEST')
    return dict(status='AUTHENTICATION_WRITES_ACCOUNTED',epochBefore=details_before['epoch'],epochAfter=epoch,
                appendedSessionRows=len(created),appendedAuditRows=len(additions),businessTablesVerified=len(pre['tables'])-3)


def offline_tests():
    """用合成脱敏事件通过实际消费者一次，再逐项更改输入核过期、身份、签名和完成性拒绝。"""
    attempt='a'*32
    rows=[]
    def emit(kind,**data):
        rows.append(dict(kind=kind,attempt=attempt,utc=120000+len(rows),details=data))
    emit('census',workers=['Microsoft.AspNetCore.Hosting.GenericWebHostService'],routes=[ME,'/auth/login','/signin-oidc'],
         disabled=True,automatic=False,signingKid=KID,material=MATERIAL)
    emit('ready',login=LOGIN,issuer=ISSUER,client=CLIENT,noAutomaticKeys=True,deniedBusinessRoutes=True,meWithoutSession=401,ticketStore=STORE)
    for n,(account,sub,role,sites) in enumerate(ROSTER.values(),1):
        flow=format(n,'032x')
        emit('challenge',flow=flow,pkce='S256',responseType='code',statePresent=True,noncePresent=True)
        emit('ticketOperation',action='Store',flow=flow,rowRef=format(n,'064x'),correlation=flow,epochBefore=1,epochAfter=1)
        emit('callback',flow=flow,status=302,returnPath=ME,ticketStored=True,correlation=flow,epochBefore=1,epochAfter=1)
        emit('me',flow=flow,status=200,account=account,sub=sub,roles=[role],org='org-demo',sites=sites,issuer=ISSUER,
             audience=CLIENT,alg='RS256',kid=KID,material=MATERIAL,iat=120,exp=300,signatureVerified=True,lifetimeVerified=True,
             epochBefore=1,epochAfter=1)
    valid=qualify(rows,attempt,120000,121000)
    check(len(valid['subjects'])==4,'SELFTEST_HEALTH')
    trials={'expired':('exp',119),'wrong_subject':('sub','not-a-subject'),'wrong_issuer':('issuer','other'),
            'wrong_client':('audience','other'),'wrong_alg':('alg','none'),'wrong_signature':('signatureVerified',False),
            'encryption_key':('kid','other'),'stale_token':('iat',59),'wrong_role':('roles',['platform.operator'])}
    results=['healthy']
    for name,(field,value) in trials.items():
        mutated=copy.deepcopy(rows);mutated[-1]['details'][field]=value
        try:qualify(mutated,attempt,120000,121000)
        except ValueError:results.append(name);continue
        raise AssertionError(name)
    for name,subset in [('missing_subject',rows[:-4]),('only_jwks',rows[:2]),('unbound_callback',[v for v in rows if v['kind']!='callback'])]:
        try:qualify(subset,attempt,120000,121000)
        except ValueError:results.append(name);continue
        raise AssertionError(name)
    def observe(subset):
        return qualify_partial(subset,attempt,120000,121000)
    def pg_state(detail):
        def table(hashes):
            return dict(count=len(hashes),sha256=hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest())
        return {'stable':{'tables':{
            'governance.server_sessions':table(detail['sessions'].values()),
            'governance.audit_records':table([v['sha256'] for v in detail['audit'].values()]),
            'governance.MappingAuthorizationEpochs':table([format(detail['epoch'],'064x')]),
            'test.business':table([])}}}
    initial=dict(epoch=1,sessions={},audit={})
    details=copy.deepcopy(initial)
    def verify(observation,post_detail,post_state=None):
        return qualify_pg(pg_state(initial),pg_state(post_detail) if post_state is None else post_state,
                          observation,initial,post_detail)
    for n in range(5):
        prefix=rows[:2+4*n]
        observed=observe(prefix)
        state='FOUR_NORMAL_AUTHENTICATIONS_VERIFIED' if n==4 else 'WAITING_FOR_USER_AUTH'
        check(observed['status']==state and len(observed['subjects'])==n,'SELFTEST_PARTIAL')
        if n:
            op=prefix[-3]['details']
            details['sessions'][op['rowRef']]=format(n+20,'064x')
            details['audit'][str(n)]=dict(action='authentication.login',actor=prefix[-1]['details']['sub'],
                    correlation=op['correlation'],outcome='allowed',sha256=format(n+30,'064x'))
        writes=verify(observed,details)
        check(writes['appendedSessionRows']==writes['appendedAuditRows']==n and writes['epochAfter']==1,
              'SELFTEST_PARTIAL_PG')
        results.append('pg_and_identity_'+str(n))
        if n<4:
            check(observe(rows[:len(prefix)+1])['status']=='WAITING_FOR_USER_AUTH','SELFTEST_OPEN_CHALLENGE')
        if n==1:
            for cut in (1,2):
                incomplete=observe(prefix[:-cut])
                check(incomplete['status']=='BLOCKED' and verify(incomplete,details)['appendedSessionRows']==1,'SELFTEST_UNCONFIRMED')
            results.append('unconfirmed_store_or_callback')
            wrong=copy.deepcopy(details);wrong['audit']['1']['actor']=ROSTER['reader'][1]
            try:verify(observed,wrong)
            except ValueError:results.append('partial_wrong_audit_actor')
            else:raise AssertionError('partial_wrong_audit_actor')
            event=copy.deepcopy(prefix[-3]);event['utc']=120999
            for action in ('Renew','Remove'):
                event['details'].update(action=action,epochAfter=2,correlation='next-request')
                renewed=copy.deepcopy(details);renewed['epoch']=2
                renewed['sessions'][op['rowRef']]='f'*64
                if action=='Remove':
                    renewed['audit']['logout']=dict(action='authentication.logout',actor=ROSTER['operator'][1],
                                                    correlation='next-request',outcome='allowed',sha256='7'*64)
                writes=verify(observe(prefix+[event]),renewed)
                check(writes['epochAfter']==2 and writes['appendedAuditRows']==len(renewed['audit']),'SELFTEST_PG_EPOCH')
                results.append('partial_epoch_'+action.lower())
        if n==0:
            drift=pg_state(details);drift['stable']['tables']['test.business']['count']=1
            try:verify(observed,details,drift)
            except ValueError:results.append('zero_login_business_drift')
            else:raise AssertionError('zero_login_business_drift')
    # 已写但不在事件中的登录、越界 epoch、错误新增表摘要均必须拒绝。
    for name,observed,after in [
            ('unobserved_auth_write',observe(rows[:2]),details),
            ('unaccounted_epoch',valid,dict(details,epoch=2)),
            ('unaccounted_audit',valid,dict(details,audit={})),
            ('unaccounted_ticket',valid,dict(details,sessions={}))]:
        try:verify(observed,after)
        except ValueError:results.append(name)
        else:raise AssertionError(name)
    extra=copy.deepcopy(rows[2]);extra['utc']=120999;extra['details']['flow']='9'*32
    check(observe(rows+[extra])['status']=='BLOCKED','SELFTEST_EXTRA_FLOW')
    results.append('four_plus_extra_flow')
    too_many=rows[:2]
    for n in range(13):
        event=copy.deepcopy(extra);event['details']['flow']=format(n,'032x');too_many.append(event)
    bad_subject=copy.deepcopy(rows[:10]);bad_subject[-1]['details']['sub']=ROSTER['operator'][1]
    bad_signature=copy.deepcopy(rows[:6]);bad_signature[-1]['details']['signatureVerified']=False
    bad_role=copy.deepcopy(rows[:6]);bad_role[-1]['details']['roles']=['platform.viewer']
    bad_event=dict(kind='failed',utc=120999,attempt=attempt,details={'reason':'signature'})
    for name,cases in [('partial_duplicate_subject',bad_subject),('partial_wrong_signature',bad_signature),
                       ('partial_wrong_role',bad_role),('too_many_pending',too_many),('explicit_failure',rows[:2]+[bad_event])]:
        try:observe(cases)
        except ValueError:results.append(name)
        else:raise AssertionError(name)
    return results
