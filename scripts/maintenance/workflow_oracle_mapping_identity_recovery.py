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


def frozen_inputs(root, fixture_path=None):
    """以 Base 的已知源码/原件交叉证明四个不同主体、冻结 client 和唯一 RS256 签名键。"""
    root = Path(root)
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
        raw = path.read_bytes()
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
    """读取真实宿主逐行公开事件；上游另重开该准确宿主构建、命令双流和资源输入。"""
    check(hexid(attempt,32) and type(started_ms) is int and type(ended_ms) is int and
          0 <= ended_ms-started_ms <= 16*60*1000 and 2 <= len(events) <= 120, 'WINDOW')
    rows = {}
    operations = []
    flows = {}
    ready = False
    census = False
    previous = started_ms
    for event in events:
        check(set(event) == {'kind','attempt','utc','details'} and event['attempt'] == attempt
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
                  d['statePresent'] is True and d['noncePresent'] is True, 'CHALLENGE')
            flows[flow] = {'state':'challenge','utc':previous}
        elif kind == 'ticketOperation':
            check(flow in flows and d['action'] in ('Store','Renew','Remove') and hexid(d['rowRef'],64)
                  and isinstance(d['correlation'],str) and 1<=len(d['correlation'])<=64 and
                  type(d['epochBefore']) is int and type(d['epochAfter']) is int and
                  d['epochAfter']-d['epochBefore'] in ((0,) if d['action']=='Store' else (0,1)), 'TICKET_OPERATION')
            operations.append(d)
        elif kind == 'callback':
            stores = [o for o in operations if o['flow']==flow and o['action']=='Store']
            check(flow in flows and flows[flow]['state']=='challenge' and d['status']==302 and d['returnPath']==ME
                  and d['ticketStored'] is True and len(stores)==1 and stores[0]['correlation']==d['correlation']
                  and type(d['epochBefore']) is int and type(d['epochAfter']) is int and d['epochAfter']>=d['epochBefore'], 'CALLBACK')
            flows[flow].update(state='callback',correlation=d['correlation'])
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
            rows[sub] = {'flow':flow,'correlation':flows[flow]['correlation'],'sub':sub,'account':account,
                         'roles':[role],'org':'org-demo','sites':sites,'iat':d['iat'],'exp':d['exp']}
        else:
            raise ValueError('OMQ_IDENTITY_EVENT_KIND')
    check(census and ready and set(rows)==set(SUBJECTS) and len(flows)==4 and all(v['state']=='complete' for v in flows.values()),
          'FOUR_COMPLETED_SUBJECTS')
    check(len({v['correlation'] for v in rows.values()})==4,'CALLBACK_CORRELATIONS')
    return dict(status='FOUR_NORMAL_AUTHENTICATIONS_VERIFIED',attempt=attempt,subjects=rows,operations=operations)


def qualify_pg(before, after, events, details_before, details_after):
    """逐一绑定认证允许的写入；保持原行/审计、授权与跨存储引用的稳定投影。"""
    pre,post=before['stable'],after['stable']
    check(set(pre)==set(post) and all(pre[k]==post[k] for k in pre if k!='tables'),'PG_REFERENCES')
    check(set(pre['tables'])==set(post['tables']) and EPHEMERAL_TABLES<=set(post['tables'])
          and all(pre['tables'][k]==post['tables'][k] for k in pre['tables'] if k not in EPHEMERAL_TABLES),'PG_BUSINESS')
    rows=events['subjects']; ops=events['operations']
    sessions=details_before['sessions']; current=details_after['sessions']
    old=details_before['audit']; new=details_after['audit']
    check(set(sessions)<=set(current) and set(old)<=set(new) and all(old[k]==new[k] for k in old),'PG_OLD_RECORDS')
    created={o['rowRef'] for o in ops if o['action']=='Store'}
    changed={k for k in sessions if sessions[k]!=current[k]}
    updated={o['rowRef'] for o in ops if o['action'] in ('Renew','Remove') and o['epochAfter']>o['epochBefore']}
    check(len(created)==4 and set(current)-set(sessions)==created and changed==updated & set(sessions)
          and all(o['rowRef'] in current for o in ops), 'PG_SESSION_WRITES')
    epoch=details_before['epoch']
    check(type(epoch) is int and epoch>=0, 'PG_INITIAL_EPOCH')
    for op in ops:
        check(op['epochBefore']==epoch,'PG_EPOCH_BINDING')
        epoch=op['epochAfter']
    check(epoch==details_after['epoch'], 'PG_FINAL_EPOCH')
    login={r['correlation']:sub for sub,r in rows.items()}
    expected=sorted(('authentication.login',sub,c) for c,sub in login.items())
    for o in ops:
        if o['action']=='Remove' and o['epochAfter']>o['epochBefore']:
            subject=next(s for s,v in rows.items() if v['flow']==o['flow'])
            expected.append(('authentication.logout',subject,o['correlation']))
    additions=[new[k] for k in set(new)-set(old)]
    check(all(v['outcome']=='allowed' for v in additions) and sorted((v['action'],v['actor'],v['correlation']) for v in additions)==sorted(expected),'PG_AUDIT_WRITES')
    for stable,detail in ((pre,details_before),(post,details_after)):
        check(stable['tables']['governance.server_sessions']['count']==len(detail['sessions'])
              and stable['tables']['governance.audit_records']['count']==len(detail['audit']),'PG_COUNTERS')
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
    return results
