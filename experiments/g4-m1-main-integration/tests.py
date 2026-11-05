#!/usr/bin/env python3
"""任务消费者和受控资源边界的真实正反回归。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARTIFACTS = ROOT / 'artifacts/g4-m1-main-integration-001'


class HostBoundaryTests(unittest.TestCase):
    """观测开始前必须拒绝目录越界、历史身份和已存在的证据。"""

    def test_runtime_real_cli_reaches_shared_binding_for_both_modes(self):
        """真实脚本入口解析两模式；非法Head须由共同绑定拒绝而不是旧解析器截断。"""
        command=[sys.executable,'-B',str(HERE/'runtime.py')]
        help_result=subprocess.run(command+['--help'],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(help_result.returncode,0)
        self.assertIn('--ingress',help_result.stdout)
        binding=['--run-id','b-continue-20261104-14','--expected-head','invalid','--resource-manifest',str(ARTIFACTS/'missing.json')]
        for mode in ([],['--ingress','modules'],['--ingress','g3'],['--ingress','m1'],*([ '--ingress', 'modules-'+phase] for phase in ('semantic','publishing','query','agent'))):
            with self.subTest(mode=mode):
                result=subprocess.run(command+mode+binding,cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,2)
                self.assertIn('REFUSED_RUNTIME_BOUNDARY',result.stderr)
                self.assertNotIn('unrecognized arguments',result.stderr)

    def test_runtime_file_dispatches_once_after_all_definitions(self):
        """子进程执行实际文件，只替换外部效果；两模式均须经过绑定且只派发一次。"""
        script='''import json,runpy,sys
path,*args=sys.argv[1:];sys.argv=[path,*args];events=[]
def trace(frame,event,arg):
 if event=='call' and frame.f_code.co_name=='cli' and frame.f_code.co_filename==path:
  g=frame.f_globals
  def load(*values):events.append(['binding',list(values)]);return {'runId':'fixture'}
  def verify(m):events.append(['verify',m])
  async def daemon(m,group):events.append(['ingress',m,group])
  assert 'ingress_daemon' in g
  g.update(load_manifest=load,verify_engine=verify,ingress_daemon=daemon);sys.settrace(None)
 return trace
sys.settrace(trace)
try:runpy.run_path(path,run_name='__main__')
finally:print('DISPATCH_EVENTS='+json.dumps(events))
'''
        command=[sys.executable,'-B','-c',script,str(HERE/'runtime.py')]
        binding=['--run-id','b-continue-20261104-14','--expected-head','a'*40,'--resource-manifest','fixture']
        for mode in ([],['--ingress','modules'],['--ingress','g3'],['--ingress','m1'],*([ '--ingress', 'modules-'+phase] for phase in ('semantic','publishing','query','agent'))):
            with self.subTest(mode=mode):
                result=subprocess.run(command+mode+binding,cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                events=json.loads(result.stdout.split('DISPATCH_EVENTS=')[1])
                self.assertEqual([row[0] for row in events],['binding','ingress' if mode else 'verify'])
                if mode:self.assertEqual(events[1][2],mode[1])
        for args in (binding+['--run-id','duplicate'],binding[:-2],['--ingress','foreign']+binding,binding+['--task-id','old']):
            with self.subTest(args=args):
                result=subprocess.run(command+args,cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,2)
                self.assertIn('DISPATCH_EVENTS=[]',result.stdout)

    def invoke(self, path, *args):
        """固定解释器和有界子进程，不运行默认长监测。"""
        return subprocess.run([sys.executable, '-B', str(HERE / 'host_continuity.py'),
                               'monitor', '--output', str(path), '--seconds', '1',
                               *args], cwd=ROOT, capture_output=True, text=True, timeout=5)

    def test_outside_and_traversal(self):
        """绝对树外路径和词法父目录穿越在观测前拒绝。"""
        for path in (ROOT / 'artifacts/foreign/monitor.jsonl', ARTIFACTS / '../escape.jsonl', ARTIFACTS):
            with self.subTest(path=str(path)):
                result = self.invoke(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('TASK_OUTPUT_BOUNDARY', result.stderr)

    def test_existing_output_and_summary(self):
        """现有原始证据与摘要均保持原字节。"""
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / 'monitor.jsonl'
            for occupied in (path, path.with_suffix('.summary.json')):
                occupied.write_text('preserved\n')
                result = self.invoke(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('EXISTING', result.stderr)
                self.assertEqual(occupied.read_text(), 'preserved\n')
                occupied.unlink()

    def test_symbolic_link_and_invalid_duration(self):
        """悬空摘要链接和超出预算的时长不能启动监测。"""
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / 'monitor.jsonl'
            path.with_suffix('.summary.json').symlink_to(Path(directory) / 'missing')
            result = self.invoke(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('EXISTING_OR_UNSAFE_SUMMARY', result.stderr)
            path.with_suffix('.summary.json').unlink()
            result = self.invoke(path, '--seconds', '14401')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('BOUND_OR_EXISTING_OUTPUT', result.stderr)

    def test_foreign_task_cli_is_not_accepted(self):
        """禁止用传入旧任务身份改写监测归属。"""
        result = self.invoke(ARTIFACTS / 'unused.jsonl', '--task-id', 'G4-M1-RECOVERY-001')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unrecognized arguments', result.stderr)


class RuntimeBoundaryTests(unittest.TestCase):
    """真实边界负例，不调用Docker或读取旧私有运行时。"""

    def test_g3_config_keeps_product_numeric_loopback_contract(self):
        """实际配置生成器只能为G3填写容器内固定回环地址，M1不能带G3配置。"""
        from unittest.mock import patch
        import runtime as rt
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            d=Path(directory);(d/'api').mkdir();(d/'realm.json').write_text(json.dumps({'authority':'http://localhost:15180/realms/g2-1234','clientId':'fixture','clientSecret':'fixture'}))
            for name in ('platform-password','s3-access','s3-secret'):(d/name).write_text('fixture')
            value={'realmFile':str(d/'realm.json'),'publicOrigin':'http://localhost:15100','certificatePassword':'fixture','healthKey':'fixture'}
            for group in ('g3','m1'):
                with patch.object(rt,'runtime_value',return_value=value),patch.object(rt,'private_dir',return_value=d):rt.configure_api({'runId':'fixture'},group)
                config=json.loads((d/'api/appsettings.json').read_text())
                if group=='g3':
                    self.assertEqual(config['Semantics'],{'ValidationOrigin':'http://127.0.0.1:15303/validation','PublishedOrigin':'http://127.0.0.1:15303/ontology'})
                    self.assertEqual(config['Publishing']['S3Endpoint'],'http://127.0.0.1:15900')
                else:self.assertNotIn('Semantics',config);self.assertNotIn('Publishing',config)


    def test_container_loopback_relay_group_and_lifecycle(self):
        """执行生成helper的真实启动段；错误组不能监听，断开/超时必须关闭双端。"""
        import runtime as rt
        prefix=rt.WEB_HELPER.split("const dir=path.join(root,'apps/web');")[0]
        prefix='\n'.join(line for line in prefix.splitlines() if not line.startswith('import ')).replace('__ROOT__',json.dumps(str(ROOT)))
        harness=r"""const vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
for(const group of ['g3','m1','foreign','',undefined]){
 const servers=[],connections=[],signals={};
 const socket=()=>({events:{},destroyed:false,on(k,f){this.events[k]=f;return this},setTimeout(ms,f){this.timeout=ms;this.expire=f;return this},destroy(){this.destroyed=true},pipe(other){this.peer=other;return other}});
 const net={createServer(callback){const s={callback,listen(port,host){this.address={port,host}},close(){this.closed=true},on(){return this}};servers.push(s);return s},connect(target){const s=socket();s.target=target;connections.push(s);return s}};
 const process={env:{G4_ROOT:input.root,G4_RUN_ID:'b-continue-20261104-23',G4_GROUP:group},exit(code){throw Error('EXIT_'+code)},on(k,f){signals[k]=f}};
 try{vm.runInNewContext(input.source,{net,process,setTimeout(){return {unref(){}}},Set});assert.ok(['g3','m1'].includes(group))}
 catch(e){if(['g3','m1'].includes(group))throw e;assert.equal(e.message,'EXIT_2');assert.equal(servers.length,0);continue}
 assert.deepEqual(servers.map(s=>s.address),group==='g3'?[{port:15180,host:'127.0.0.1'},{port:15303,host:'127.0.0.1'},{port:15900,host:'127.0.0.1'}]:[{port:15180,host:'127.0.0.1'}]);
 for(const [i,server]of servers.entries()){
  assert.equal(server.maxConnections,64);
  for(const trigger of ['clientError','upstreamError','clientClose','upstreamClose','clientTimeout','upstreamTimeout']){
   const c=socket();server.callback(c);const u=connections.at(-1);
   assert.deepEqual(JSON.parse(JSON.stringify(u.target)),[{host:'keycloak-test',port:8080},{host:'fuseki',port:3030},{host:'rustfs',port:9000}][i]);
   assert.equal(c.peer,u);assert.equal(u.peer,c);assert.equal(c.timeout,30000);assert.equal(u.timeout,30000);
   ({clientError:()=>c.events.error(),upstreamError:()=>u.events.error(),clientClose:()=>c.events.close(),upstreamClose:()=>u.events.close(),clientTimeout:()=>c.expire(),upstreamTimeout:()=>u.expire()})[trigger]();
   assert.ok(c.destroyed&&u.destroyed,trigger);
  }
 }
 const active=socket();servers[0].callback(active);const upstream=connections.at(-1);
 signals.SIGTERM();assert.ok(active.destroyed&&upstream.destroyed);assert.ok(servers.every(s=>s.closed));
}
console.log('group and bounded relay lifecycle PASS');"""
        result=subprocess.run(['/opt/homebrew/opt/node@24/bin/node','-e',harness],input=json.dumps({'source':prefix,'root':str(ROOT)}),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_g3_foreign_identity_restores_exact_user_and_profile_on_success_and_failure(self):
        """真实任务事务函数在正常、消费者失败和身份漂移时均复原原始输入。"""
        import copy
        from unittest.mock import patch
        import readback
        subject='11111111-1111-1111-1111-111111111111';base='/admin/realms/g2-0123456789abcdef'
        initial_profile={'attributes':[{'name':'username'}]}
        initial_user={'id':subject,'username':'g2-operator-a','attributes':{'organization_id':['org-demo'],'site_ids':['site-a'],'preserved':['value']}}
        for failure in (None,'work','unexpected_org','profile_put','user_restore','profile_restore','restore_readback'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
                state={'profile':copy.deepcopy(initial_profile),'user':copy.deepcopy(initial_user)};events=[];once=[]
                if failure=='unexpected_org':state['user']['attributes']['organization_id']=['foreign']
                original=copy.deepcopy(state['user'])
                def request(method,path,value=None):
                    events.append((method,path))
                    if path==base+'/users?username=g2-operator-a&exact=true':return [copy.deepcopy(state['user'])]
                    key='profile' if path==base+'/users/profile' else 'user'
                    self.assertIn(path,(base+'/users/profile',base+'/users/'+subject))
                    if method=='PUT':
                        if failure=='user_restore' and key=='user' and value['attributes']['organization_id']==['org-demo']:raise RuntimeError('synthetic_restore_failure')
                        if failure=='profile_restore' and key=='profile' and value==initial_profile:raise RuntimeError('synthetic_profile_restore_failure')
                        if failure=='restore_readback' and key=='user' and value['attributes']['organization_id']==['org-demo']:return None
                        state[key]=copy.deepcopy(value)
                        if failure=='profile_put' and key=='profile' and not once:once.append(True);raise RuntimeError('synthetic_profile_failure')
                        return None
                    return copy.deepcopy(state[key])
                def work():
                    self.assertEqual(state['user']['attributes']['organization_id'],['org-other'])
                    if failure=='work':raise RuntimeError('synthetic_work_failure')
                    return {'consumer':'PASS'}
                out=Path(directory);m={'runId':'fixture','_head':'a'*40}
                with patch.object(readback.rt,'private_dir',return_value=out),patch.object(readback.rt,'ARTIFACTS',out),patch.object(readback.rt,'write_json') as save:
                    if failure:
                        with self.assertRaises((ValueError,RuntimeError)):readback.g3_organization_trial(m,request,base,subject,work)
                    else:self.assertEqual(readback.g3_organization_trial(m,request,base,subject,work),{'consumer':'PASS'})
                    if failure!='profile_restore':self.assertEqual(state['profile'],initial_profile)
                    if failure not in ('user_restore','restore_readback'):self.assertEqual(state['user'],original)
                    self.assertTrue(any(call.args[0].name=='g3-identity-restore.json' and call.kwargs.get('private') for call in save.call_args_list))
                    self.assertEqual(save.call_args_list[-1].args[1]['restored'],failure not in ('user_restore','profile_restore','restore_readback'))
                    if failure in ('user_restore','profile_restore','restore_readback'):self.assertEqual(save.call_args_list[-1].args[1]['status'],'FAIL')


    def test_semantic_method_partition_preserves_parameter_rows_and_rejects_ambiguity(self):
        """同方法全部DataRow保留；源码歧义、缺项、非法案例和重复均失败关闭。"""
        import importlib.util
        spec=importlib.util.spec_from_file_location('method_partition',HERE/'module-tests.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source='namespace Fixture;\npublic sealed class Cases\n{\n    public async Task Check(string value)\n'
        cases=[{'case':'Check ("one")'},{'case':'Check ("two")'}]
        plan=module.module_partition(cases,{'Cases.cs':source})
        self.assertEqual(plan[0]['method'],'Fixture.Cases.Check')
        self.assertEqual(plan[0]['cases'],[r['case'] for r in cases])
        for rows,sources in ((cases,{}),(cases,{'a.cs':source,'b.cs':source}),(cases+cases,{'a.cs':source}),([{'case':'Check|Injected'}],{'a.cs':source})):
            with self.subTest(rows=rows,sources=list(sources)),self.assertRaises(ValueError):module.module_partition(rows,sources)
        for actual in (['one','one'],['one'],['one','two','extra']):
            with self.subTest(actual=actual),self.assertRaises(ValueError):module.exact_cases(['one','two'],actual)
        module.exact_cases(['one','two'],['two','one'])
        for suffix in ('SemanticTests','PublishingTests','QueryTests','AgentTests'):
            self.assertEqual(module.module_project(suffix),ROOT/('backend/tests/OntologyPlatform.'+suffix))
        for suffix in ('../SecurityTests','SecurityTests','ConnectionsTests','',None):
            with self.subTest(project=suffix),self.assertRaises(ValueError):module.module_project(suffix)

    def test_semantic_idle_counts_prevalidation_reservation_and_real_exec_exit(self):
        """核验前占槽和已断客户端的远端Exec均不能漏计，null退出码不是证明。"""
        import importlib.util
        spec=importlib.util.spec_from_file_location('method_idle',HERE/'module-tests.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        rows=[{'event':'ready','pid':123},{'event':'reserved','pid':123,'token':'one'}]
        def inspect():return module.module_ingress_snapshot(b'\n'.join(json.dumps(r).encode() for r in rows),123)
        self.assertFalse(inspect()['idle'])
        rows.extend([{'event':'exec_created','pid':123,'token':'one','execId':'id'},{'event':'connection_closed','pid':123,'token':'one'}])
        self.assertFalse(inspect()['idle'])
        rows.append({'event':'exec_exited','pid':123,'execId':'id','running':False,'exitCode':None})
        self.assertFalse(inspect()['idle']);rows[-1]['exitCode']=0
        self.assertTrue(inspect()['idle'])
        rows[-1]['pid']=456
        with self.assertRaises(ValueError):inspect()

    def test_run_identity(self):
        import runtime as rt
        self.assertEqual(rt.run_id('b-continue-20261104-01'), 'b-continue-20261104-01')
        for value in ('recovery-20261101-01', 'final-gates-20261102-r04-final', '../x', '', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rt.run_id(value)

    def test_ingress_routes_and_engine_frame_boundary(self):
        """入口仅接受冻结运行组，Docker帧不得混入未知流或无界长度。"""
        import runtime as rt
        self.assertEqual(rt.ingress_services('modules'),('platform-pg','fuseki','rustfs'))
        self.assertEqual(len(rt.ingress_services('g3')),6)
        for group in ('old','',None):
            with self.assertRaises(ValueError):rt.ingress_services(group)
        self.assertEqual(rt.engine_frame_header(bytes([1,0,0,0,0,0,0,7])),(1,7))
        for header in (b'',bytes([0,0,0,0,0,0,0,7]),bytes([1,1,0,0,0,0,0,7]),bytes([1,0,0,0,127,0,0,0])):
            with self.assertRaises(ValueError):rt.engine_frame_header(header)

    def test_ingress_exec_rejects_unregistered_targets_commands_and_identity(self):
        """错误目的地和旧Run在任何Engine写操作前拒绝；正例固定低权限。"""
        import runtime as rt
        engine=object.__new__(rt.TaskEngine);engine.m={'runId':'b-continue-20990101-99'}
        engine.allowed_targets={('127.0.0.1',5432)};engine.created_execs=set();calls=[]
        engine.owned=lambda *_:None
        engine.request=lambda method,path,body: calls.append(body) or {'Id':'a'*64}
        token='g4-relay-b-continue-20990101-99-'+'1'*32
        command=['perl','-e',rt.RELAY_PERL,'127.0.0.1','5432',token,'120']
        engine.create('b'*64,command)
        self.assertEqual(calls[0]['User'],'999:999');self.assertFalse(calls[0]['Privileged']);self.assertFalse(calls[0]['Tty'])
        for index,value in ((0,'sh'),(2,'arbitrary program'),(3,'192.0.2.1'),(3,'127.0.0.2'),(4,'9000'),(5,token.replace('20990101','20990102')),(6,'121')):
            changed=command.copy();changed[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):engine.create('b'*64,changed)
        self.assertEqual(len(calls),1)

    def test_ingress_m1_exact_networks_namespace_and_owner(self):
        """M1双internal网络与Web共享API正例；额外网络、旧身份和镜像串换拒绝。"""
        import copy
        import runtime as rt
        run='b-continue-20990101-99';m={'runId':run};engine=object.__new__(rt.TaskEngine);engine.m=m
        front='ontology-g4-main-'+run+'_front';source='ontology-g4-main-'+run+'_source'
        services=rt.ingress_services('m1');ids={s:str(i+1)*64 for i,s in enumerate(services)};rows=[]
        for i,service in enumerate(services):
            networks={front:{'NetworkID':'a'*64,'IPAddress':'172.18.0.'+str(i+2)}}
            if service=='api':networks[source]={'NetworkID':'b'*64,'IPAddress':'172.19.0.3'}
            if service=='web':networks={}
            rows.append({'Id':ids[service],'Image':rt.INGRESS_IMAGES[service],'ImageID':'sha256:'+'c'*64,'State':'running','Status':'Up',
                'Labels':{'ontology.task-id':rt.TASK,'ontology.run-id':run,'com.docker.compose.service':service},
                'HostConfig':{'NetworkMode':'container:'+ids['api'] if service=='web' else front},'NetworkSettings':{'Networks':networks}})
        routes,networks=rt.ingress_route_projection(m,engine,'m1',ids,rows)
        self.assertEqual(routes[-1]['providerId'],ids['api']);self.assertEqual(set(networks),{'a'*64,'b'*64})
        for mutation in ('old-run','wrong-image','extra-network','wrong-namespace','missing-id'):
            changed=copy.deepcopy(rows)
            if mutation=='old-run':changed[0]['Labels']['ontology.run-id']='b-continue-20990101-98'
            elif mutation=='wrong-image':changed[0]['Image']=rt.IMAGES['node']
            elif mutation=='extra-network':changed[2]['NetworkSettings']['Networks']['foreign']={'NetworkID':'d'*64,'IPAddress':'172.20.0.2'}
            elif mutation=='wrong-namespace':changed[3]['HostConfig']['NetworkMode']='container:'+'d'*64
            else:changed.pop()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):rt.ingress_route_projection(m,engine,'m1',ids,changed)

    def test_binding_rejects_image_and_tool_substitution(self):
        import runtime as rt
        report=json.loads((ROOT/'docs/evidence/G4-M1-MAIN-INTEGRATION-001/p0/tools-admission.json').read_text())
        baseline={'approvalSha256':rt.APPROVAL_SHA,'images':rt.IMAGES,'tools':{x['path']:x['sha256'] for x in report['files']}}
        rt.validate_admission(baseline)
        for key,value,code in [('images',{'postgres':'postgres:latest'},'IMAGE_ADMISSION'),('tools',{},'TOOL_ADMISSION'),('approvalSha256','0'*64,'APPROVAL_BINDING')]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,code):
                rt.validate_admission(dict(baseline,**{key:value}))

    def test_cli_rejects_old_identity_before_secret_read(self):
        for name in ('http.mjs', 'browser.mjs', 'fault.mjs', 'g3-compatibility.mjs'):
            result = subprocess.run(['/opt/homebrew/opt/node@24/bin/node',str(HERE/name),
                '--run-id','recovery-20261101-01','--expected-head','0'*40,
                '--resource-manifest',str(ARTIFACTS/'not-created.json'),
                '--runtime-file','/no-private-secret-read/runtime.json','--evidence-dir',str(ARTIFACTS/'never-created')], capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode,0,name)

    def test_download_and_existing_output_refused(self):
        import runtime as rt
        m={'runId':'b-continue-20990101-99'}
        for verb in ('install','pull','load'):
            with self.subTest(verb=verb), self.assertRaisesRegex(ValueError,'DOWNLOAD_OR_FORCE_REFUSED'):
                rt.execute(m,'negative-download',['not-executed',verb])

    def test_lexical_and_link_path_refused(self):
        import runtime as rt
        for path in (ARTIFACTS/'../escape',Path('/tmp/foreign')):
            with self.assertRaises(ValueError): rt.boundary(path,ARTIFACTS)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as d:
            link=Path(d)/'link'; link.symlink_to('/tmp')
            with self.assertRaises(ValueError): rt.boundary(link/'out',ARTIFACTS)

    def test_wrong_san_transition_binds_snapshot_variant_and_restores(self):
        """实际故障编排须把同一证书变体传给快照，测试失败也恢复server。"""
        from unittest.mock import patch
        from contextlib import ExitStack
        import runtime as rt,readback
        for fail in (False,True):
            events=[]
            def test(m,category,label,**kwargs):
                if category=='RealPgWrongSanFixture' and fail:raise ValueError('SYNTHETIC_TLS_TEST_FAILURE')
                return {'status':'PASS'}
            with ExitStack() as stack:
                stack.enter_context(patch.object(rt,'execute',side_effect=lambda m,n,c,**kw:events.append(('execute',n,kw['env'].get('G4_CERTIFICATE_VARIANT','server')))))
                stack.enter_context(patch.object(readback,'refresh_registry',side_effect=lambda m,n,**kw:events.append(('snapshot',n,kw.get('certificate_variant','server')))))
                stack.enter_context(patch.object(readback,'test_pg',side_effect=test));stack.enter_context(patch.object(readback,'sql',return_value='0'))
                for name in ('wait_pg','inspect_owned','docker','write_json'):stack.enter_context(patch.object(rt,name))
                stack.enter_context(patch.object(rt,'runtime_value',return_value={'containerIds':{'pg-adapter-test':'synthetic'}}))
                m={'runId':'b-continue-20261104-24','privateDirectory':str(ARTIFACTS/'synthetic')}
                if fail:
                    with self.assertRaisesRegex(ValueError,'SYNTHETIC_TLS_TEST_FAILURE'):readback.pg_security(m)
                else:readback.pg_security(m)
            self.assertIn(('execute','source-wrong-san','wrong-san'),events)
            self.assertIn(('snapshot','wrong-san','wrong-san'),events)
            self.assertIn(('execute','source-san-restore','server'),events)
            self.assertIn(('snapshot','san-restored','server'),events)

    def test_snapshot_uses_exact_certificate_variant_declaration(self):
        """真实挂载校验在匹配变体时通过、默认错配与任意变体时拒绝。"""
        from unittest.mock import patch
        from contextlib import ExitStack
        import runtime as rt,readback,closeout
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            d=Path(directory);run='b-continue-20261104-24'
            for n in ('server.crt','server.key','wrong-san.crt','wrong-san.key'):(d/n).write_text('synthetic')
            m={'runId':run,'privateDirectory':str(d)};seen=[]
            (d/run).mkdir();(d/run/'resources-m1-owned.json').write_text('{}\n')
            def configured(command,**kwargs):
                variant=kwargs['env'].get('G4_CERTIFICATE_VARIANT','server');seen.append(variant)
                declaration={'services':{'pg-source':{'volumes':[{'type':'bind','source':str(d/(variant+ext)),'target':'/cert'+ext,'read_only':True} for ext in ('.crt','.key')]}}}
                return subprocess.CompletedProcess(command,0,json.dumps(declaration).encode(),b'')
            actual={'Config':{'Labels':{'com.docker.compose.service':'pg-source'},'Image':rt.IMAGES['postgres']},'Image':'sha256:fixture','HostConfig':{'Memory':1024,'Privileged':False,'ReadonlyRootfs':True},'State':{'Running':True,'Paused':False},'Mounts':[{'Type':'bind','Source':str(d/('wrong-san'+ext)),'Destination':'/cert'+ext,'RW':False} for ext in ('.crt','.key')]}
            with ExitStack() as stack:
                stack.enter_context(patch.object(rt,'ARTIFACTS',d));stack.enter_context(patch.object(rt,'docker',return_value=b'fixture\n'));stack.enter_context(patch.object(rt,'verify_engine'))
                stack.enter_context(patch.object(rt.subprocess,'run',side_effect=configured));stack.enter_context(patch.object(rt,'inspect_owned',return_value=actual));stack.enter_context(patch.object(rt,'observed_volume_usage',return_value=0));stack.enter_context(patch.object(rt,'update_runtime'))
                stack.enter_context(patch.object(closeout,'inventory',return_value={}))
                readback.refresh_registry(m,'wrong-san',certificate_variant='wrong-san')
                result=json.loads((d/run/'resources-wrong-san.json').read_text())
                self.assertEqual(result['certificateVariant'],'wrong-san');self.assertEqual(len(result['containers'][0]['bindMappings']),2)
                self.assertEqual(result['composeConfigSha256'],rt.digest(configured([],env={'G4_CERTIFICATE_VARIANT':'wrong-san'}).stdout))
                with self.assertRaisesRegex(ValueError,'CERTIFICATE_VARIANT'):readback.refresh_registry(m,'invalid',certificate_variant='foreign')
                self.assertFalse((d/run/'resources-m1-before-invalid.json').exists())
                with self.assertRaisesRegex(ValueError,'ACTUAL_BIND_SOURCE'):rt.resource_snapshot(m,'m1','default-mismatch')
                for bad in ('foreign','../wrong-san',''):
                    with self.assertRaisesRegex(ValueError,'CERTIFICATE_VARIANT'):rt.resource_snapshot(m,'m1','invalid',certificate_variant=bad)
                with self.assertRaisesRegex(ValueError,'CERTIFICATE_VARIANT'):rt.resource_snapshot(m,'g3','invalid',certificate_variant='wrong-san')
            self.assertEqual(seen,['wrong-san','wrong-san','server'])

    def test_actual_bind_mounts_match_declared_native_or_desktop_path(self):
        """真实目录只接受逐项声明的原生或Docker Desktop路径及只读目标。"""
        import runtime as rt
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as d:
            source=Path(d)/'input';source.write_text('synthetic')
            declared=[{'type':'bind','source':str(source),'target':'/input','read_only':True}]
            actual={'Type':'bind','Source':str(source),'Destination':'/input','RW':False}
            for prefix in ('','/host_mnt'):
                row=dict(actual,Source=prefix+str(source))
                self.assertEqual(rt.validate_bind_mounts([row],declared)[0]['nativeSource'],str(source))
            for rows in ([],[actual,actual],[dict(actual,Source='/host_mnt/tmp/foreign')],
                         [dict(actual,Source='/host_mnt'+d+'/../input')],
                         [dict(actual,Source='/host_mnt/host_mnt'+str(source))],
                         [dict(actual,Destination='/other')],[dict(actual,RW=True)],
                         [actual,dict(actual,Destination='/extra')]):
                with self.subTest(rows=rows),self.assertRaises(ValueError):
                    rt.validate_bind_mounts(rows,declared)
            for declarations in ([dict(declared[0],read_only=False)],declared*2):
                with self.assertRaises(ValueError):rt.validate_bind_mounts([actual],declarations)
            source.unlink();source.symlink_to('/tmp')
            with self.assertRaisesRegex(ValueError,'SYMLINK'):
                rt.validate_bind_mounts([actual],declared)

    def test_deadline_terminates_process_group(self):
        import runtime as rt
        raw,code,timed_out=rt.bounded_process([sys.executable,'-c','import time; time.sleep(20)'],
            cwd=ROOT,env=rt.environment(),timeout=0.1)
        self.assertTrue(timed_out)
        self.assertIsNotNone(code)


class ExecutionRegressionTests(unittest.TestCase):
    def test_engine_stall_keeps_event_loop_and_cancel_responsive(self):
        """真实Unix对端不响应时，控制循环继续运行且取消准确释放连接。"""
        import asyncio
        import runtime as rt
        async def trial(directory):
            socket_path='engine.sock';accepted=[];closed=asyncio.Event()
            async def stalled(reader,writer):
                accepted.append(True)
                await reader.read();writer.close();await writer.wait_closed();closed.set()
            server=await asyncio.start_unix_server(stalled,socket_path)
            engine=object.__new__(rt.TaskEngine);engine.path=socket_path
            task=asyncio.create_task(engine.async_request('GET','/version'))
            ticks=0
            for _ in range(5):await asyncio.sleep(.01);ticks+=1
            self.assertTrue(accepted);self.assertEqual(ticks,5);self.assertFalse(task.done())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            await asyncio.wait_for(closed.wait(),1);server.close();await server.wait_closed()
        import os
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as d:
            previous=Path.cwd()
            try:os.chdir(d);asyncio.run(trial(d))
            finally:os.chdir(previous)

    def test_remote_half_close_still_accepts_upstream_bytes(self):
        """对端先关闭发送方向，客户端仍可发送完整上行数据再半关闭。"""
        import asyncio
        import runtime as rt
        async def trial():
            received=[];jobs=[]
            def frame(stream,data):return bytes([stream,0,0,0])+len(data).to_bytes(4,'big')+data
            async def peer(reader,writer):
                writer.write(frame(2,b'PIDS 123 124\nOUTPUT_EOF 0\n'));await writer.drain()
                received.append(await reader.read());writer.close();await writer.wait_closed()
            engine=await asyncio.start_server(peer,'127.0.0.1',0)
            async def bridge(reader,writer):
                er,ew=await asyncio.open_connection('127.0.0.1',engine.sockets[0].getsockname()[1])
                try:await rt.relay_copy(reader,writer,er,ew,lambda _:None)
                finally:ew.close();writer.close();await ew.wait_closed();await writer.wait_closed()
            server=await asyncio.start_server(lambda r,w:jobs.append(asyncio.create_task(bridge(r,w))),'127.0.0.1',0)
            try:
                reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
                self.assertEqual(await reader.read(),b'')
                payload=bytes(range(256))*1024;writer.write(payload);await writer.drain();writer.write_eof()
                await asyncio.gather(*jobs);self.assertEqual(received,[payload]);writer.close();await writer.wait_closed()
            finally:server.close();engine.close();await server.wait_closed();await engine.wait_closed()
        asyncio.run(asyncio.wait_for(trial(),5))

    def test_relay_binary_backpressure_and_half_close(self):
        """实际loopback双向字节流跨分片Docker帧，半关闭后仍可接收完整响应。"""
        import asyncio
        import runtime as rt
        payload=bytes(range(256))*8192
        async def trial():
            controls=[];jobs=[];observed=[]
            def frame(stream,data):return bytes([stream,0,0,0])+len(data).to_bytes(4,'big')+data
            async def peer(reader,writer):
                writer.write(frame(2,b'PIDS 123 124\n')+frame(1,b'greeting\0'));await writer.drain()
                data=await reader.read();observed.append(data)
                # Docker的stderr控制帧可以先于尚未读出的stdout尾帧抵达。
                writer.write(frame(2,('OUTPUT_EOF '+str(9+len(data)+10)+'\n').encode()))
                for i in range(0,len(data),32768):
                    packet=frame(1,data[i:i+32768])
                    if i==0:
                        for part in (packet[:2],packet[2:7],packet[7:]):writer.write(part);await writer.drain();await asyncio.sleep(.001)
                    else:writer.write(packet);await writer.drain()
                writer.write(frame(1,b'after-eof\0'));await writer.drain();writer.close();await writer.wait_closed()
            engine=await asyncio.start_server(peer,'127.0.0.1',0)
            async def bridge(reader,writer):
                er,ew=await asyncio.open_connection('127.0.0.1',engine.sockets[0].getsockname()[1])
                try:await rt.relay_copy(reader,writer,er,ew,controls.append)
                finally:ew.close();writer.close();await ew.wait_closed();await writer.wait_closed()
            def accepted(reader,writer):jobs.append(asyncio.create_task(bridge(reader,writer)))
            relay=await asyncio.start_server(accepted,'127.0.0.1',0)
            try:
                reader,writer=await asyncio.open_connection('127.0.0.1',relay.sockets[0].getsockname()[1])
                self.assertEqual(await reader.readexactly(9),b'greeting\0')
                writer.write(payload);await writer.drain();writer.write_eof()
                result=bytearray()
                while data:=await reader.read(16384):result.extend(data);await asyncio.sleep(.001)
                self.assertEqual(bytes(result),payload+b'after-eof\0');self.assertEqual(observed,[payload]);self.assertEqual(controls,[[123,124]])
                writer.close();await writer.wait_closed();await asyncio.gather(*jobs)
            finally:relay.close();engine.close();await relay.wait_closed();await engine.wait_closed()
        asyncio.run(asyncio.wait_for(trial(),10))

    def test_long_command_argument_is_not_a_path(self):
        import runtime as rt
        self.assertEqual(rt.command_file_inputs(['python3','-c','x'*10000]), {})

    def test_hook_ref_binding(self):
        import importlib.machinery, importlib.util
        loader=importlib.machinery.SourceFileLoader('task_hook',str(HERE/'hooks/pre-push'))
        spec=importlib.util.spec_from_loader(loader.name,loader);hook=importlib.util.module_from_spec(spec);loader.exec_module(hook)
        approval={'taskId':'G4-M1-MAIN-INTEGRATION-001','phase':'C_EXPLICIT_APPROVAL','origin':'fixture','head':'a'*40,'approvedMain':'b'*40}
        line='a'*40+' '+'a'*40+' refs/heads/main '+'b'*40
        hook.validate('origin','fixture',[line],approval)
        for lines in ([],[line,line],[line.replace('b'*40,'c'*40)],[line.replace('refs/heads/main','refs/heads/other')],[line.replace('a'*40,'0'*40)]):
            with self.subTest(lines=lines),self.assertRaises(ValueError):hook.validate('origin','fixture',lines,approval)


class ComposeBoundaryTests(unittest.TestCase):
    def test_api_init_declared_and_actual_state_are_required(self):
        """真实Compose及实际快照均拒绝API缺失/错误Init，覆盖恢复副本。"""
        import copy
        from unittest.mock import patch
        from contextlib import ExitStack
        import runtime as rt,consumer_check as cc
        rid='b-continue-20990101-98';m={'runId':rid,'privateDirectory':str(rt.private_dir(rid)),'images':rt.IMAGES}
        for group,profile in [('g3',None),('m1',None),('m1','lease')]:
            command=rt.compose_command(group)+(['--profile',profile] if profile else [])+['config','--format','json']
            result=subprocess.run(command,env=rt.compose_environment(m),capture_output=True,timeout=20);self.assertEqual(result.returncode,0,result.stderr)
            config=json.loads(result.stdout)
            for name in ('api','api-recovery'):
                if name not in config['services']:continue
                self.assertIs(config['services'][name].get('init'),True)
                for value in (None,False,'true',1):
                    bad=copy.deepcopy(config)
                    if value is None:bad['services'][name].pop('init')
                    else:bad['services'][name]['init']=value
                    with self.assertRaisesRegex(ValueError,'API_INIT_REQUIRED'):cc.check_compose(m,bad,group)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            for service in ('api','api-recovery'):
                for number,init in enumerate((None,False,'true',1,True)):
                    item={'Config':{'Labels':{'com.docker.compose.service':service},'Image':rt.IMAGES['aspnet']},'Image':'sha256:fixture','HostConfig':{'Memory':1024,'Privileged':False,'ReadonlyRootfs':True,'Init':init},'State':{'Running':True,'Paused':False},'Mounts':[]}
                    result=subprocess.CompletedProcess([],0,json.dumps({'services':{service:{'volumes':[]}}}).encode(),b'')
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(rt,'ARTIFACTS',Path(directory)));stack.enter_context(patch.object(rt,'docker',return_value=b'fixture\n'));stack.enter_context(patch.object(rt,'verify_engine'));stack.enter_context(patch.object(rt.subprocess,'run',return_value=result));stack.enter_context(patch.object(rt,'inspect_owned',return_value=item));stack.enter_context(patch.object(rt,'observed_volume_usage',return_value=0));stack.enter_context(patch.object(rt,'update_runtime'))
                        if init is True:
                            value=rt.resource_snapshot(m,'m1',service+str(number));self.assertIs(value['containers'][0]['init'],True)
                        else:
                            with self.assertRaisesRegex(ValueError,'ACTUAL_API_INIT_REQUIRED'):rt.resource_snapshot(m,'m1',service+str(number))

    def test_actual_config_positive_and_mutations(self):
        import copy
        import runtime as rt, consumer_check as cc
        m={'runId':'b-continue-20990101-98','privateDirectory':str(rt.private_dir('b-continue-20990101-98')),'images':rt.IMAGES}
        for group in ('m1','g3'):
            p=subprocess.run(rt.compose_command(group)+['config','--format','json'],env=rt.compose_environment(m),capture_output=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr.decode())
            config=json.loads(p.stdout);cc.check_compose(m,config,group)
            mutations=[('image','postgres:latest','COMPOSE_IMAGE'),('pull_policy','always','COMPOSE_IMAGE'),
                ('cap_add',['SYS_ADMIN'],'EXTRA_CAPABILITY'),('gpus','all','COMPOSE_PRIVILEGE'),
                ('mem_limit',7*1024**3,'MEMORY_BUDGET'),('network_mode','host','COMPOSE_NETWORK_MODE'),
                ('networks',{'default':{}},'UNDECLARED_NETWORK'),('ports',[{'host_ip':'0.0.0.0','target':5432,'published':'15432'}],'LOOPBACK_ONLY')]
            for key,value,code in mutations:
                bad=copy.deepcopy(config);bad['services']['platform-pg'][key]=value
                with self.subTest(group=group,key=key),self.assertRaisesRegex(ValueError,code):cc.check_compose(m,bad,group)
            for field,value,code in [('name','old-project','COMPOSE_PROJECT')]:
                bad=copy.deepcopy(config);bad[field]=value
                with self.assertRaisesRegex(ValueError,code):cc.check_compose(m,bad,group)
            bad=copy.deepcopy(config);bad['volumes']['platform-data']['driver_opts']['o']='size=65536m'
            with self.assertRaisesRegex(ValueError,'VOLUME_CAPACITY'):cc.check_compose(m,bad,group)
            if group=='g3':
                enlarged=copy.deepcopy(config)
                enlarged['services']['fuseki']['mem_limit']=2*1024**3
                enlarged['volumes']['fuseki-data']['driver_opts']['o']='size=1024m,mode=0700,uid=10001,gid=10001'
                self.assertEqual(cc.check_compose(m,enlarged,group)['memoryBytes'],5888*1024**2)
                for volume,size in (('fuseki-data',1025),('platform-data',1024),('rustfs-data',513),('keycloak-data',513)):
                    bad=copy.deepcopy(enlarged);bad['volumes'][volume]['driver_opts']['o']='size='+str(size)+'m'
                    with self.subTest(volume=volume),self.assertRaisesRegex(ValueError,'VOLUME_CAPACITY'):cc.check_compose(m,bad,group)
                bad=copy.deepcopy(enlarged);bad['services']['fuseki']['mem_limit']=1024**3
                with self.assertRaisesRegex(ValueError,'FUSEKI_MEMORY_CAPACITY'):cc.check_compose(m,bad,group)
                bad=copy.deepcopy(enlarged);bad['services']['platform-pg']['volumes'].append({'type':'volume','source':'fuseki-data','target':'/unexpected'})
                with self.assertRaisesRegex(ValueError,'FUSEKI_VOLUME_CONSUMER'):cc.check_compose(m,bad,group)
                edge=copy.deepcopy(enlarged);edge['services']['platform-pg']['mem_limit']=int(edge['services']['platform-pg']['mem_limit'])+256*1024**2
                self.assertEqual(cc.check_compose(m,edge,group)['memoryBytes'],6*1024**3)
                edge['services']['platform-pg']['mem_limit']+=1
                with self.assertRaisesRegex(ValueError,'MEMORY_BUDGET'):cc.check_compose(m,edge,group)
                bad=copy.deepcopy(enlarged);bad['volumes']['extra-data']=copy.deepcopy(bad['volumes']['platform-data']);bad['volumes']['extra-data']['name']=config['name']+'_extra-data'
                with self.assertRaisesRegex(ValueError,'TOTAL_VOLUME_CAPACITY'):cc.check_compose(m,bad,group)
            else:
                bad=copy.deepcopy(config);bad['volumes']['fuseki-data']=copy.deepcopy(bad['volumes']['platform-data']);bad['volumes']['fuseki-data']['name']=config['name']+'_fuseki-data';bad['volumes']['fuseki-data']['driver_opts']['o']='size=1024m'
                with self.assertRaisesRegex(ValueError,'VOLUME_CAPACITY'):cc.check_compose(m,bad,group)


class PushRaceTests(unittest.TestCase):
    def test_real_bare_push_races(self):
        import os
        with tempfile.TemporaryDirectory(prefix='g4-main-push-fixture-',dir=ARTIFACTS) as d:
            base=Path(d);repo=base/'author';bare=base/'remote.git';hooks=base/'hooks';hooks.mkdir()
            env=dict(os.environ,GIT_AUTHOR_NAME='Synthetic Fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',GIT_COMMITTER_NAME='Synthetic Fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
            def git(*args,cwd=None,ok=True,input=None):
                result=subprocess.run(['git',*map(str,args)],cwd=cwd or base,env=env,input=input,text=True,capture_output=True,timeout=15)
                if ok:self.assertEqual(result.returncode,0,result.stderr)
                return result
            git('init','--bare',bare);git('init',repo)
            tree=git('hash-object','-w','-t','tree','--stdin',cwd=repo,input='').stdout.strip()
            initial=git('commit-tree',tree,'-m','base',cwd=repo).stdout.strip()
            concurrent=git('commit-tree',tree,'-p',initial,'-m','concurrent',cwd=repo).stdout.strip()
            candidate=git('commit-tree',tree,'-p',concurrent,'-m','candidate',cwd=repo).stdout.strip()
            git('remote','add','origin',bare,cwd=repo)
            git('push','origin',initial+':refs/heads/main',concurrent+':refs/heads/fixture-concurrent',cwd=repo)
            approval={'taskId':'G4-M1-MAIN-INTEGRATION-001','phase':'C_EXPLICIT_APPROVAL','origin':str(bare),'head':candidate,'approvedMain':initial}
            wrapper="#!/usr/bin/env python3\nimport importlib.machinery,importlib.util,json,subprocess,sys\n"
            wrapper+="loader=importlib.machinery.SourceFileLoader('h',"+repr(str(HERE/'hooks/pre-push'))+");spec=importlib.util.spec_from_loader(loader.name,loader);h=importlib.util.module_from_spec(spec);loader.exec_module(h)\n"
            wrapper+="approval="+repr(approval)+"\nh.validate(sys.argv[1],sys.argv[2],sys.stdin.read().splitlines(),approval)\n"
            hook=hooks/'pre-push';hook.write_text(wrapper);hook.chmod(0o755)
            # 通告前服务器已前进：hook必须拒绝旧批准。
            git('--git-dir',bare,'update-ref','refs/heads/main',concurrent,initial)
            failed=git('-c','core.hooksPath='+str(hooks),'push','origin',candidate+':refs/heads/main',cwd=repo,ok=False)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('EXACT_UPDATE_REQUIRED',failed.stderr)
            self.assertEqual(git('--git-dir',bare,'rev-parse','main').stdout.strip(),concurrent)
            # 此回退只发生在自建无业务bare夹具，不触碰真实main。
            git('--git-dir',bare,'update-ref','refs/heads/main',initial,concurrent)
            race=wrapper+"subprocess.run(['git','--git-dir',"+repr(str(bare))+",'update-ref','refs/heads/main',"+repr(concurrent)+","+repr(initial)+"],check=True)\n"
            hook.write_text(race)
            failed=git('-c','core.hooksPath='+str(hooks),'push','origin',candidate+':refs/heads/main',cwd=repo,ok=False)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('incorrect old value provided',failed.stderr)
            self.assertIn('but expected '+initial,failed.stderr)
            self.assertEqual(git('--git-dir',bare,'rev-parse','main').stdout.strip(),concurrent)
            git('--git-dir',bare,'update-ref','refs/heads/main',initial,concurrent)
            hook.write_text(wrapper)
            git('-c','core.hooksPath='+str(hooks),'push','origin',candidate+':refs/heads/main',cwd=repo)
            self.assertEqual(git('--git-dir',bare,'rev-parse','main').stdout.strip(),candidate)


class RecoveryGuardTests(unittest.TestCase):
    def test_existing_log_rejected_before_command(self):
        import runtime as rt
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as d:
            directory=Path(d);commands=directory/'commands';commands.mkdir()
            (commands/'occupied.log').write_text('preserve')
            marker=directory/'must-not-exist'
            with self.assertRaisesRegex(ValueError,'EXISTING_OUTPUT'):
                rt.execute({'runId':directory.name},'occupied',[sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'])
            self.assertFalse(marker.exists())
            self.assertEqual((commands/'occupied.log').read_text(),'preserve')

    def test_guard_restores_after_parent_killed(self):
        import os,signal,time,selectors
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as d:
            directory=Path(d);fake=directory/'docker';state=directory/'state.json'
            ident='f'*64;run='b-continue-20990101-97'
            value={'Id':ident,'Config':{'Labels':{'ontology.task-id':'G4-M1-MAIN-INTEGRATION-001','ontology.run-id':run,'com.docker.compose.service':'pg-source'}},'State':{'Running':True,'Paused':False},'unpauseCalls':0}
            state.write_text(json.dumps(value))
            code="#!/usr/bin/env python3\nimport os,json,sys\nfrom pathlib import Path\np=Path(os.environ['GUARD_FIXTURE_STATE']);v=json.loads(p.read_text());a=sys.argv[3:]\nassert sys.argv[1:3]==['--context','desktop-linux'] and a[1]==v['Id']\nif a[0]=='inspect':print(json.dumps([v]))\nelif a[0] in ('pause','unpause'):\n v['State']['Paused']=a[0]=='pause';v['unpauseCalls']+=int(a[0]=='unpause');p.write_text(json.dumps(v))\nelse:sys.exit(2)\n"
            fake.write_text(code);fake.chmod(0o755)
            child_code="import sys,time;from pathlib import Path;sys.path.insert(0,"+repr(str(HERE))+");import runtime as r;r.ARTIFACTS=Path("+repr(str(directory))+");r.runtime_value=lambda m:{'containerIds':{'pg-source':"+repr(ident)+"}};guard=r.PauseGuard({'runId':"+repr(run)+"},'pg-source',1);guard.__enter__();print(guard.guard.pid,flush=True);time.sleep(60)"
            env=dict(os.environ,PATH=str(directory)+os.pathsep+os.environ['PATH'],GUARD_FIXTURE_STATE=str(state),PYTHONDONTWRITEBYTECODE='1')
            child=subprocess.Popen([sys.executable,'-B','-c',child_code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            guard_pid=None
            try:
                selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
                self.assertTrue(selector.select(4));guard_pid=int(child.stdout.readline());selector.close()
                self.assertTrue(json.loads(state.read_text())['State']['Paused'])
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
                deadline=time.monotonic()+4
                while json.loads(state.read_text())['State']['Paused'] and time.monotonic()<deadline:time.sleep(.05)
                after=json.loads(state.read_text());self.assertFalse(after['State']['Paused']);self.assertEqual(after['unpauseCalls'],1)
            finally:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
                if guard_pid:
                    try:os.kill(guard_pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                child.stdout.close();child.stderr.close()


class SourceIoWitnessTests(unittest.TestCase):
    def test_health_connections_are_separate_and_reader_drift_is_rejected(self):
        import readback
        from unittest.mock import patch
        positive=b'2026 [1] LOG: connection received: host=172.19.0.3 port=50123\n2026 [1] LOG: connection authorized: user=fixture_reader database=fixture SSL enabled\n'
        health=b'2026 [2] LOG: connection received: host=[local]\n2026 [2] LOG: connection authorized: user=postgres database=fixture application_name=pg_isready\n'
        with patch.object(readback,'sql',return_value='0'):
            result=readback.require_no_reader_io({},positive,positive+health)
            self.assertEqual(result['afterNetworkConnections'],1)
            with self.assertRaisesRegex(ValueError,'UNEXPECTED_SOURCE_NETWORK_IO'):
                readback.require_no_reader_io({},positive,positive+positive)
            for tcp_only in (b'2026 [3] LOG: connection received: host=172.19.0.4 port=55000\n', b'2026 [4] LOG: connection received: host=172.19.0.4 port=55001\n2026 [4] LOG: could not accept SSL connection\n'):
                with self.assertRaisesRegex(ValueError,'UNEXPECTED_SOURCE_NETWORK_IO'):
                    readback.require_no_reader_io({},positive,positive+tcp_only)
            with self.assertRaisesRegex(ValueError,'SOURCE_IO_POSITIVE_CONTROL_MISSING'):
                readback.require_no_reader_io({},health,health)
            with self.assertRaisesRegex(ValueError,'SOURCE_LOG_TRUNCATED'):
                readback.require_no_reader_io({},positive+health,positive)


class OfflineRestoreBoundaryTests(unittest.TestCase):
    def test_mac_platform_lock_is_included(self):
        import run
        packages=run.locked_packages()
        for name in ('aspire.hosting.apphost','aspire.hosting.postgresql','aspire.dashboard.sdk.osx-arm64','aspire.hosting.orchestration.osx-arm64'):
            self.assertIn(name+'/13.6.3',packages)

    def test_restore_denies_network_before_dotnet(self):
        import run
        command=run.restore_command({'runId':'b-continue-20261104-02'})
        self.assertEqual(command[:3],['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)'])
        self.assertIn('--locked-mode',command)
        self.assertIn('--disable-build-servers',command)
        self.assertIn('-m:1',command)
        import runtime
        self.assertEqual(runtime.environment()['DOTNET_GENERATE_ASPNET_CERTIFICATE'],'false')


class ToolCleanupBoundaryTests(unittest.TestCase):
    def test_exact_fingerprint_and_link_rejections(self):
        import closeout,os
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root=Path(directory);target=root/'copy';target.mkdir();file=target/'input';file.write_bytes(b'original')
            before=closeout.tool_tree(target);file.write_bytes(b'changed')
            self.assertNotEqual(before['fingerprint'],closeout.tool_tree(target)['fingerprint'])
            link=target/'escape';link.symlink_to('/private/tmp')
            with self.assertRaisesRegex(ValueError,'TOOL_LINK_ESCAPE'):closeout.tool_tree(target)
            link.unlink();os.link(file,target/'hardlink')
            with self.assertRaisesRegex(ValueError,'TOOL_HARDLINK'):closeout.tool_tree(target)
            (target/'hardlink').unlink();outside=root/'root-link';outside.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'SYMLINK'):closeout.tool_tree(outside)


class DurableCleanupTests(unittest.TestCase):
    def fixture(self):
        from contextlib import ExitStack
        from unittest.mock import patch
        import closeout,runtime
        stack=ExitStack();directory=stack.enter_context(tempfile.TemporaryDirectory(dir=ARTIFACTS));root=Path(directory)
        for path in ('copies','.tools/dotnet-home','artifacts/reviews'):(root/path).mkdir(parents=True)
        (root/'copies/input').write_bytes(b'regenerable');(root/'.tools/dotnet-home/cache').write_bytes(b'keep')
        (root/'artifacts/reviews/OntologyPlatform-Review-G4-M1-MAIN-INTEGRATION-001-test.zip').write_bytes(b'keep')
        stack.enter_context(patch.object(runtime,'ROOT',root));stack.enter_context(patch.object(runtime,'ARTIFACTS',root/'artifacts/g4-m1-main-integration-001'))
        stack.enter_context(patch.object(runtime,'git',side_effect=lambda *args:'1'*40 if args[0]=='rev-parse' else ''))
        stack.enter_context(patch.object(closeout,'TOOL_COPY_PATHS',('copies',)))
        stack.enter_context(patch('subprocess.check_output',return_value=b''))
        return stack,root

    def test_expired_plan_rejected_before_delete(self):
        import closeout,runtime,datetime
        with self.fixture()[0] as stack:
            root=runtime.ROOT;run='b-continue-20261104-01';closeout.freeze_tool_cleanup(run,'1'*40)
            path=runtime.ARTIFACTS/run/'cleanup-tools-plan.json';plan=json.loads(path.read_text());plan['expiresAtUtc']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=1)).isoformat();path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'CLEANUP_PLAN_EXPIRED'):closeout.apply_tool_cleanup(run,runtime.digest(path.read_bytes()))
            self.assertTrue((root/'copies/input').is_file())

    def test_partial_delete_failure_has_durable_before_after(self):
        import closeout,runtime,errno
        from unittest.mock import patch
        with self.fixture()[0] as stack:
            root=runtime.ROOT;run='b-continue-20261104-01';closeout.freeze_tool_cleanup(run,'1'*40)
            path=runtime.ARTIFACTS/run/'cleanup-tools-plan.json';journal=path.with_name('cleanup-tools-journal.jsonl')
            def failure(target):
                rows=[json.loads(line) for line in journal.read_text().splitlines()]
                self.assertEqual(rows[-1]['phase'],'BEFORE');self.assertEqual(rows[-1]['status'],'PENDING')
                (target/'input').unlink();raise PermissionError(errno.EACCES,'synthetic cleanup failure')
            failure.avoids_symlink_attacks=True
            with patch('shutil.rmtree',new=failure):
                with self.assertRaises(PermissionError):closeout.apply_tool_cleanup(run,runtime.digest(path.read_bytes()))
            result=json.loads(path.with_name('cleanup-tools-result.json').read_text())
            self.assertEqual(result['status'],'FAIL');self.assertEqual(result['commands'][0]['errorErrno'],errno.EACCES)
            self.assertEqual([json.loads(x)['phase'] for x in journal.read_text().splitlines()],['START','BEFORE','AFTER'])


class ModulePhaseTests(unittest.TestCase):
    """四项目设施寿命独立；跨phase错绑及不完整回收均不得进入下一项目。"""

    def test_exact_phase_routes_and_runtime_binding(self):
        import runtime
        from unittest.mock import patch
        expected={'SemanticTests':'modules-semantic','PublishingTests':'modules-publishing','QueryTests':'modules-query','AgentTests':'modules-agent'}
        self.assertEqual(runtime.MODULE_PHASES,expected)
        for phase in expected.values():
            self.assertEqual(runtime.ingress_services(phase),('platform-pg','fuseki','rustfs'))
            self.assertEqual(runtime.ingress_runtime_group({'group':'g3','modulePhase':phase},phase),'g3')
            with self.assertRaisesRegex(ValueError,'INGRESS_MODULE_PHASE'):
                runtime.ingress_runtime_group({'group':'g3','modulePhase':'other'},phase)
        with self.assertRaisesRegex(ValueError,'INGRESS_GROUP'):runtime.ingress_services('modules-foreign')
        with patch.object(runtime,'verify_engine') as verify:
            for kwargs in ({'modules':True},{'modules':True,'module_phase':'foreign'},{'module_phase':'modules-agent'}):
                with self.assertRaisesRegex(ValueError,'MODULE_PHASE'):runtime.start_group({},'g3',**kwargs)
            verify.assert_not_called()

    def test_four_full_lifecycles_and_failure_stop(self):
        import runtime,run
        from contextlib import ExitStack
        from unittest.mock import patch
        module=run.module('module-tests');totals={'SemanticTests':302,'PublishingTests':78,'QueryTests':49,'AgentTests':33}
        for failure in (None,'tests','cleanup'):
            with self.subTest(failure=failure),ExitStack() as stack:
                root=Path(stack.enter_context(tempfile.TemporaryDirectory(dir=ARTIFACTS)));rid='b-continue-20261104-20';(root/rid).mkdir();events=[];active=[]
                stack.enter_context(patch.object(runtime,'ARTIFACTS',root));stack.enter_context(patch.object(module,'module_environment',return_value={}))
                def start(m,group,**kw):
                    self.assertFalse(active);self.assertEqual(group,'g3');self.assertTrue(kw['modules']);active.append(kw['module_phase']);events.append(('start',active[0]))
                def migrate(m,env,phase):self.assertEqual(active,[phase]);events.append(('migrate',phase))
                def methods(m,env,project):
                    phase=runtime.MODULE_PHASES[project];self.assertEqual(active,[phase]);events.append(('tests',phase))
                    if failure=='tests' and project=='PublishingTests':raise ValueError('SYNTHETIC_TEST_FAILURE')
                    if project=='AgentTests':(root/rid/'agent-schema-result.json').write_text('{}')
                    return {'project':project,'status':'PASS','total':totals[project]}
                def cleanup(m,phase,apply=False):
                    self.assertTrue(apply);self.assertEqual(active,[phase]);events.append(('cleanup',phase))
                    if failure=='cleanup' and phase=='modules-publishing':raise ValueError('SYNTHETIC_CLEANUP_FAILURE')
                    active.clear();return {'status':'PASS'}
                def execute(m,name,*args,**kw):
                    self.assertEqual(name,'mcp-schema-positive-negative');self.assertFalse(active);self.assertEqual(len([e for e in events if e[0]=='cleanup']),4);events.append(('schema',name));return b''
                stack.enter_context(patch.object(runtime,'start_group',side_effect=start));stack.enter_context(patch.object(module,'migrate_module_phase',side_effect=migrate))
                stack.enter_context(patch.object(module,'run_module_methods',side_effect=methods));stack.enter_context(patch.object(runtime,'resource_snapshot',return_value={}))
                stack.enter_context(patch.object(module.closeout,'reclaim',side_effect=cleanup));stack.enter_context(patch.object(runtime,'execute',side_effect=execute))
                if failure:
                    with self.assertRaises(ValueError):module.run_modules({'runId':rid})
                    self.assertEqual([e[1] for e in events if e[0]=='start'],['modules-semantic','modules-publishing']);self.assertFalse(any(e[0]=='schema' for e in events))
                else:
                    result=module.run_modules({'runId':rid});self.assertEqual(sum(r['total'] for r in result),462)
                    self.assertEqual(events[:-1],[(action,phase) for phase in runtime.MODULE_PHASES.values() for action in ('start','migrate','tests','cleanup')])
                    for row in result:
                        phase=runtime.MODULE_PHASES[row['project']];path=root/rid/('cleanup-'+phase+'-result.json')
                        self.assertTrue(path.is_file());self.assertEqual(row['fixturePhase'],phase);self.assertEqual(row['cleanupReceiptSha256'],runtime.digest(path.read_bytes()))


class TransitionVolumeTests(unittest.TestCase):
    """切换时仅删准确可再生卷，缺席必须有真实诊断，资源计量拒绝遗漏。"""

    def test_orphan_volume_is_not_silently_omitted(self):
        import runtime
        from unittest.mock import patch
        m={'runId':'fixture'}
        with patch.object(runtime,'docker',return_value=b'volume-a\nvolume-b\n'):
            with self.assertRaisesRegex(ValueError,'UNOBSERVED_OWNED_VOLUME'):
                runtime.observed_volume_usage(m,{'volume-a':{'usedBytes':10}})
            self.assertEqual(runtime.observed_volume_usage(m,{'volume-a':{'usedBytes':10},'volume-b':{'usedBytes':20}}),30)
        with patch.object(runtime,'docker',return_value=b'volume-a\n'):
            with self.assertRaisesRegex(ValueError,'UNOBSERVED_OWNED_VOLUME'):
                runtime.observed_volume_usage(m,{'volume-a':{'usedBytes':10},'foreign':{'usedBytes':1}})

    def test_transition_exact_pair_and_failed_absence(self):
        import run,runtime,copy
        from unittest.mock import patch
        from contextlib import ExitStack
        module=run.module('migration-boundary');rid='b-continue-20261104-18';prefix='ontology-g4-main-'+rid+'_'
        m={'runId':rid};names=[prefix+'fuseki-data',prefix+'rustfs-data']
        before={k:{'owned':[],'keep':['foreign-'+k]} for k in ('container','network','volume')}
        before['volume']['owned']=[{'id':n,'created':'frozen'} for n in names+[prefix+'platform-data',prefix+'keycloak-data']]
        for failure in ('none','dryrun','version','owner','attached','absence','keep','remove','timeout','observe'):
            with self.subTest(failure=failure),ExitStack() as stack:
                directory=stack.enter_context(tempfile.TemporaryDirectory(dir=ARTIFACTS));root=Path(directory)
                stack.enter_context(patch.object(runtime,'ARTIFACTS',root));(root/rid).mkdir()
                state=copy.deepcopy(before);calls=[]
                def docker(manifest,args,**kw):
                    calls.append(args)
                    if args[:2]==['volume','inspect']:
                        name=args[2]
                        return json.dumps([{'Name':name,'CreatedAt':'changed' if failure=='version' else 'frozen','Labels':{'ontology.task-id':'foreign' if failure=='owner' else runtime.TASK,'ontology.run-id':rid}}]).encode()
                    if args[:2]==['ps','-aq']:return b'container' if failure=='attached' else b''
                    raise AssertionError(args)
                stack.enter_context(patch.object(runtime,'docker',side_effect=docker))
                def inventory(m):
                    if failure=='observe' and any(c[:2]==['volume','rm'] for c in calls):raise ValueError('SIMULATED_OBSERVATION_FAILURE')
                    return copy.deepcopy(state)
                stack.enter_context(patch.object(module.closeout,'inventory',side_effect=inventory))
                def command(cmd,**kw):
                    args=cmd[3:];calls.append(args)
                    if args[:2]==['volume','rm']:
                        if failure=='timeout':raise subprocess.TimeoutExpired(cmd,20,output=b'partial',stderr=b'timeout')
                        if failure=='remove':return subprocess.CompletedProcess(cmd,17,b'partial',b'synthetic failure')
                        state['volume']['owned']=[x for x in state['volume']['owned'] if x['id']!=args[2]]
                        if failure=='keep':state['network']['keep']=[]
                        return subprocess.CompletedProcess(cmd,0,args[2].encode(),b'')
                    self.assertEqual(args[:2],['volume','inspect'])
                    return subprocess.CompletedProcess(cmd,1,b'',b'permission denied' if failure=='absence' else b'Error response from daemon: get '+cmd[-1].encode()+b': no such volume')
                stack.enter_context(patch.object(module.subprocess,'run',side_effect=command))
                if failure=='dryrun':
                    self.assertEqual(module.retire_g3_volumes(m,before)['status'],'DRY_RUN')
                    self.assertFalse(any(c[:2]==['volume','rm'] for c in calls))
                elif failure=='none':
                    result=module.retire_g3_volumes(m,before,apply=True)
                    self.assertEqual(result['deleted'],names)
                    self.assertEqual([c for c in calls if c[:2]==['volume','rm']],[['volume','rm',n] for n in names])
                else:
                    with self.assertRaises(ValueError):module.retire_g3_volumes(m,before,apply=True)
                    if failure in ('version','owner','attached'):
                        self.assertFalse(any(c[:2]==['volume','rm'] for c in calls))
                    else:
                        self.assertTrue((root/rid/'migration-volume-retirement.json').exists())
                        rows=[json.loads(x) for x in (root/rid/'migration-volume-retirement-commands.jsonl').read_text().splitlines()]
                        self.assertEqual(rows[0]['phase'],'BEFORE')
                        if failure in ('remove','timeout'):
                            self.assertEqual([r['phase'] for r in rows],['BEFORE','COMMAND_EXIT','AFTER'])
                            self.assertEqual(rows[1]['exitCode'],17 if failure=='remove' else None)
                            self.assertIn('stderrSha256',rows[1])
                        if failure=='observe':
                            result=json.loads((root/rid/'migration-volume-retirement.json').read_text())
                            self.assertEqual(result['status'],'FAIL');self.assertEqual(result['afterObservationError'],'ValueError')


class CliHomeIsolationTests(unittest.TestCase):
    def test_actual_runs_never_reuse_kept_incident_home(self):
        import runtime
        first=runtime.environment('b-continue-20261104-01')['DOTNET_CLI_HOME']
        second=runtime.environment('b-continue-20261104-02')['DOTNET_CLI_HOME']
        self.assertEqual(first,str(ARTIFACTS/'b-continue-20261104-01/dotnet-cli-home'))
        self.assertNotEqual(first,second)
        for value in (first,second,runtime.environment()['DOTNET_CLI_HOME']):
            self.assertNotEqual(value,str(ROOT/'.tools/dotnet-home'))


class RecoveryIsolationTests(unittest.TestCase):
    def test_review_cannot_be_replayed_across_runs(self):
        import run,runtime
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            with patch.object(runtime,'ARTIFACTS',Path(directory)):
                m={'runId':'b-continue-20990101-95','_head':'1'*40,'_sha256':'2'*64,'drivers':{'run.py':'3'*64}}
                a=runtime.ARTIFACTS/m['runId'];a.mkdir()
                receipt={'status':'PASS','reviewer':'/root/reviewer','rawReview':'PASS source','drivers':m['drivers'],'testedCommit':m['_head'],'taskId':runtime.TASK,'runId':'b-continue-20990101-94','manifestSha256':m['_sha256']}
                (a/'review-R1.json').write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):run.require_reviewer(m,'R1')

    def test_caches_and_temp_are_private_for_each_run(self):
        """共享缓存或继承全局缓存注入必须不能污染另一Run。"""
        import runtime,os
        from unittest.mock import patch
        with patch.dict(os.environ,{'NUGET_HTTP_CACHE_PATH':'/tmp/foreign','TMPDIR':'/tmp/foreign','NUGET_PACKAGES':'/tmp/foreign'}):
            first=runtime.environment('b-continue-20261104-03')
            second=runtime.environment('b-continue-20261104-04')
        for key in ('DOTNET_CLI_HOME','NUGET_PACKAGES','NUGET_HTTP_CACHE_PATH','NUGET_SCRATCH'):
            with self.subTest(key=key):
                self.assertTrue(Path(first.get(key,"/missing")).is_relative_to(ARTIFACTS/'b-continue-20261104-03'))
                self.assertTrue(Path(second.get(key,"/missing")).is_relative_to(ARTIFACTS/'b-continue-20261104-04'))
                self.assertNotEqual(first[key],second[key])
        self.assertEqual(first['TMPDIR'],str(ROOT/'.tools/g4-m1-main-integration-001/b-continue-20261104-03/tmp'))
        self.assertNotEqual(first['TMPDIR'],second['TMPDIR'])

    def test_private_temp_preserves_formal_host_output_boundary_test(self):
        import runtime,shutil
        run_id='b-continue-20990101-93';directory=runtime.run_temp(run_id)
        self.assertFalse(directory.exists());directory.mkdir(parents=True)
        try:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/tests/HostContinuity.Tests.py'),'HostTests.test_output_rejects_source_and_symlink'],env=runtime.environment(run_id),capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr.decode())
        finally:shutil.rmtree(directory.parent)


class CaseProjectionTests(unittest.TestCase):
    def test_real_contract_nested_enum_mutations_are_all_rejected(self):
        script="""import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {compareDocument,schemaMutations} from './experiments/g4-m1-main-integration/contract-check.mjs';const doc=JSON.parse(readFileSync('docs/contracts/g4-connections.openapi.json'));const before=JSON.stringify(doc);compareDocument(doc,doc);const changes=schemaMutations(doc);assert.equal(changes.length,3);for(const changed of changes)assert.throws(()=>compareDocument(changed,doc),/OPENAPI_DRIFT/);assert.deepEqual(changes[1].components.schemas.ConnectionConfigPgConnectionConfig.properties.type.enum,['POSTGRESQL','INVALID_TEST_ENUM']);assert.equal(JSON.stringify(doc),before);console.log('actual frozen nested enum: positive + 3 negatives PASS');"""
        result=subprocess.run(['/opt/homebrew/opt/node@24/bin/node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_workspace_copy_relocation_forces_real_revalidation(self):
        import run,copy
        manifests={'':{'name':'ontology-platform'},'/apps/web':{'name':'@ontology-platform/web','version':'0.1.0'}}
        state={'projects':{'/old'+p:v for p,v in manifests.items()},'lastValidatedTimestamp':123,'validation':{'lockfile':'untrusted cached proof'},'settings':{},'pnpmfiles':[],'filteredInstall':False}
        moved=run.relocate_workspace_state(state,'/old','/new',manifests)
        self.assertEqual(set(moved['projects']),{'/new','/new/apps/web'})
        self.assertNotIn('validation',moved);self.assertEqual(moved['lastValidatedTimestamp'],0)
        self.assertIn('validation',state)
        for mutate in (lambda v:v['projects'].update({'/foreign':{'name':'foreign'}}),lambda v:v.update(pnpmfiles=['/foreign/hook.cjs']),lambda v:v['projects']['/old'].update(name='forged'),lambda v:v.update(filteredInstall=True)):
            bad=copy.deepcopy(state);mutate(bad)
            with self.assertRaises(ValueError):run.relocate_workspace_state(bad,'/old','/new',manifests)

    def test_ef_archive_rejects_additional_runtime_config_and_link(self):
        import run,runtime,zipfile,os
        module=run.module('module-tests')
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root=Path(directory);archive=root/'ef.nupkg';tool=root/'tools/ef.dll';tool.parent.mkdir();tool.write_bytes(b'locked payload')
            with zipfile.ZipFile(archive,'w') as z:z.writestr('tools/ef.dll',tool.read_bytes())
            expected=runtime.digest(archive.read_bytes())
            self.assertEqual(len(module.verify_ef_payload(archive,expected)),1)
            extra=tool.with_suffix('.runtimeconfig.dev.json');extra.write_text('{}')
            with self.assertRaisesRegex(ValueError,'EF_EXTRA_RUNTIME_INPUT'):module.verify_ef_payload(archive,expected)
            extra.unlink();extra.symlink_to(tool)
            with self.assertRaises(ValueError):module.verify_ef_payload(archive,expected)
            extra.unlink();os.link(tool,extra)
            with self.assertRaisesRegex(ValueError,'EF_HARDLINK'):module.verify_ef_payload(archive,expected)

    def test_ui_closure_rejects_keyword_only_and_unproven_timeout(self):
        import readback,copy
        expected={'baseline':['five_probe_stages','empty_list','job_refresh_recovery'],'source-unavailable':['source_unavailable_error'],'source-timeout':['actual_probe_pending_before_response','real_tcp_connected_tls_timeout_at_least_eight_seconds','timeout_failure_and_enabled_retry_action_no_second_paused_probe'],'source-permission-limited':['partial_catalog','job_refresh_recovery'],'catalog-cancel':['cancelled_job_refresh','cancelled_ui_and_enabled_discover_refresh_actions']}
        reports={k:{'scenario':k,'productExecution':True,'cases':{'M1-U05':{'status':'NOT_RUN','observed':v}}} for k,v in expected.items()}
        reports['source-timeout']['timeoutObservation']={'pendingBeforeResponse':True,'pendingCategories':['PROBE_RUNNING'],'clientDurationMs':9000,'reportDurationMs':9000,'tlsDurationMs':9000,'networkPassed':True,'tlsFailed':True,'probeStatus':'TEST_FAILED','diagnosticCode':'connection_source_unavailable'}
        reports['catalog-cancel']['cancelObservation']={'jobId':'a'*32,'createdStatus':'QUEUED','persistedStatus':'RUNNING','terminalStatus':'CANCELLED','completedAtPresent':True,'snapshotAbsent':True}
        source={'status':'PASS','source':{'jobId':'a'*32,'sourceLockHeldAtBackendDisappearance':True},'durable':{'status':'PASS','jobStatus':'CANCELLED','jobId':'a'*32,'snapshotId':None}}
        self.assertEqual(readback.validate_ui_closure(reports,source)['status'],'PASS')
        for mutate in (lambda x:x['baseline']['cases']['M1-U05'].update(observed=['partial timeout cancel']),lambda x:x['source-timeout']['timeoutObservation'].update(tlsDurationMs=1),lambda x:x['catalog-cancel']['cancelObservation'].update(jobId='b'*32),lambda x:x['source-unavailable'].update(productExecution=False)):
            altered=copy.deepcopy(reports);mutate(altered)
            with self.assertRaises(ValueError):readback.validate_ui_closure(altered,source)

    def test_parameterized_cases_and_count_mismatch(self):
        import runtime
        raw='passed Example ("insert") (12ms)\nskipped Other\n  total: 2\n  failed: 0\n  succeeded: 1\n  skipped: 1\n'
        self.assertTrue(hasattr(runtime,'parse_test_cases'),'per-case parser required')
        result=runtime.parse_test_cases(raw)
        self.assertEqual(result['cases'][0]['case'],'Example ("insert")')
        self.assertEqual(result['cases'][1]['status'],'SKIP')
        numeric=raw.replace('Example (\"insert\") (12ms)','Example (0) (12ms)').replace('skipped Other','skipped Other (4999)')
        cases=runtime.parse_test_cases(numeric)['cases']
        self.assertEqual([c['case'] for c in cases],['Example (0)','Other (4999)'])
        for duration in ('1s 118ms','1m 2s','1h 2m 3s','1秒 118毫秒'):
            sample='  passed Numeric (4999) ('+duration+')\n  passed Text ("1s 118ms") ('+duration+')\n  total: 2\n  failed: 0\n  succeeded: 2\n  skipped: 0\n'
            parsed=runtime.parse_test_cases(sample)
            self.assertEqual([r['case'] for r in parsed['cases']],['Numeric (4999)','Text ("1s 118ms")'])
        with self.assertRaises(ValueError):runtime.parse_test_cases(raw.replace('total: 2','total: 3'))
        with self.assertRaises(ValueError):runtime.parse_test_cases('  total: 1\n  failed: 0\n  succeeded: 1\n  skipped: 0\n')

    def test_i01_rejects_missing_offline_restore_before_execution(self):
        """缺少本Run离线恢复和独立放行时，不得启动昂贵SelfTest。"""
        import run
        try:
            run.engineering({'runId':'b-continue-20990101-98','_head':'0'*40,'_sha256':'0'*64})
        except Exception as failure:
            self.assertIsInstance(failure,ValueError)
            self.assertEqual(str(failure),'PREREQUISITE_R2')
        else:self.fail('I01 started without R2')


class OfflineFeedTests(unittest.TestCase):
    def test_unpacked_payload_tamper_is_rejected_with_unchanged_metadata(self):
        import run,runtime,zipfile,hashlib,base64
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root=Path(directory);archive=root/'fixture.1.0.0.nupkg';package=root/'package';package.mkdir()
            with zipfile.ZipFile(archive,'w') as z:z.writestr('lib//payload.dll',b'approved payload')
            raw=archive.read_bytes();(package/archive.name).write_bytes(raw)
            (package/'lib').mkdir();payload=package/'lib/payload.dll';payload.write_bytes(b'approved payload')
            (package/(archive.name+'.sha512')).write_bytes(base64.b64encode(hashlib.sha512(raw).digest()))
            (package/'.nupkg.metadata').write_text(json.dumps({'source':str(root),'contentHash':'metadata-unchanged'}))
            entry={'files':['lib/payload.dll',archive.name+'.sha512','.nupkg.metadata'],'sha512':'metadata-unchanged'}
            run.verify_restored_package(package,entry,archive,runtime.digest(raw))
            payload.write_bytes(b'polluted payload')
            with self.assertRaisesRegex(ValueError,'RESTORED_PAYLOAD_DRIFT'):
                run.verify_restored_package(package,entry,archive,runtime.digest(raw))

    def test_rid_archive_and_source_mutations_fail_closed(self):
        """使用真实文件验证缺包、改字节、异版、外部链接和额外源。"""
        import run,runtime,hashlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base=Path(directory);a=base/'b-continue-20990101-97';a.mkdir();feed=a/'nuget-feed';feed.mkdir()
            package=feed/'fixture.rid.1.0.0.nupkg';package.write_bytes(b'locked RID archive')
            rows=[{'package':'fixture.rid/1.0.0','archiveSha256':hashlib.sha256(package.read_bytes()).hexdigest()}]
            (a/'nuget-archive-copies.json').write_text(json.dumps(rows))
            config=a/'offline-nuget.config'
            config.write_text('<configuration><packageSources><clear/><add key="approved-local" value="'+str(feed)+'"/></packageSources><packageSourceMapping><clear/><packageSource key="approved-local"><package pattern="*"/></packageSource></packageSourceMapping></configuration>')
            m={'runId':a.name}
            with patch.object(runtime,'ARTIFACTS',base),patch.object(run,'approved_archives',create=True,return_value={row['package']:row for row in rows}):
                if not hasattr(run,'verify_feed'):self.fail('offline feed validation absent')
                run.verify_feed(m)
                original=package.read_bytes();package.unlink()
                with self.assertRaises(ValueError):run.verify_feed(m)
                package.write_bytes(b'polluted')
                with self.assertRaises(ValueError):run.verify_feed(m)
                package.unlink();package.symlink_to('/tmp/foreign')
                with self.assertRaises(ValueError):run.verify_feed(m)
                package.unlink();package.write_bytes(original)
                wrong=feed/'fixture.rid.2.0.0.nupkg';wrong.write_bytes(original)
                with self.assertRaises(ValueError):run.verify_feed(m)
                wrong.unlink();before=config.read_text();config.write_text(before.replace('</packageSources>','<add key="external" value="https://example.invalid"/></packageSources>'))
                with self.assertRaises(ValueError):run.verify_feed(m)
                config.write_text(before);(a/'nuget-archive-copies.json').write_text('[]')
                with self.assertRaises(ValueError):run.verify_feed(m)
                (a/'nuget-archive-copies.json').write_text(json.dumps(rows));run.verify_feed(m)


class SdkCopyMutationTests(unittest.TestCase):
    def test_actual_sdk_members_and_receipt_cannot_be_substituted(self):
        """对精确已审SDK归档的私有副本执行真实字节及路径负例。"""
        import run,runtime
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            with patch.object(runtime,'ARTIFACTS',Path(directory)):
                m={'runId':'b-continue-20990101-96'}
                run.prepare_sdk_copies(m);run.verify_sdk_copies(m)
                run.verify_empty_restore_cache(m)
                polluted=runtime.ARTIFACTS/m['runId']/'nuget-packages/polluted';polluted.mkdir()
                with self.assertRaisesRegex(ValueError,'PREPOPULATED_PACKAGE_CACHE'):run.verify_empty_restore_cache(m)
                polluted.rmdir()
                for name in run.SDK_ARCHIVES:
                    target,_,_=run.sdk_payload(name,m);p=target/'Sdk/Sdk.props';original=p.read_bytes()
                    try:
                        p.write_bytes(b'changed')
                        with self.assertRaises(ValueError):run.verify_sdk_copies(m)
                        p.unlink()
                        with self.assertRaises(ValueError):run.verify_sdk_copies(m)
                        p.symlink_to('/tmp/foreign')
                        with self.assertRaises(ValueError):run.verify_sdk_copies(m)
                    finally:
                        if p.exists() or p.is_symlink():p.unlink()
                        p.write_bytes(original)
                    wrong=target.with_name('0.0.0');target.rename(wrong)
                    try:
                        with self.assertRaises(ValueError):run.verify_sdk_copies(m)
                    finally:wrong.rename(target)
                receipt=runtime.ARTIFACTS/m['runId']/'sdk-copies.json';original=receipt.read_bytes()
                try:
                    receipt.write_text('[]')
                    with self.assertRaises(ValueError):run.verify_sdk_copies(m)
                finally:receipt.write_bytes(original)
                run.verify_sdk_copies(m)


class HandoffLifecycleTests(unittest.TestCase):
    def test_api_restart_rejoins_web_actual_namespace_and_checks_login_redirect(self):
        """API重启后旧Web命名空间不能继续作为OIDC依赖；错命名空间/issuer均拒绝。"""
        import run,runtime as rt,urllib.request,urllib.error
        from unittest.mock import patch
        from contextlib import ExitStack
        module=run.module('migration-boundary')
        for failure in (None,'namespace','issuer'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
                root=Path(directory);rid='b-continue-20990101-97';realm=root/'realm.json';realm.write_text(json.dumps({'authority':'http://localhost:15180/realms/g2-abc'}))
                m={'runId':rid,'_head':'a'*40};state={'api':'net:[10]','web':'net:[10]'}
                runtime={'containerIds':{'api':'api-id','web':'web-id'},'healthKey':'fixture','realmFile':str(realm)}
                def inspect(_m,ident,service):
                    return {'Id':ident,'Created':'fixed-created','HostConfig':{'NetworkMode':'container:api-id'},'State':{'Running':True,'StartedAt':'started-new-api'}}
                def docker(_m,args,**kwargs):
                    if args==['restart','api-id']:state['api']='net:[11]';return b'api-id'
                    if args==['restart','web-id']:
                        if failure!='namespace':state['web']=state['api']
                        return b'web-id'
                    if args[:1]==['exec']:return state['api' if args[1]=='api-id' else 'web'].encode()
                    self.fail(str(args))
                class Opener:
                    def open(self,request,timeout):
                        if state['api']!=state['web']:raise urllib.error.HTTPError(request.full_url,500,'unready',{},None)
                        issuer='http://localhost:15180/realms/'+('foreign' if failure=='issuer' else 'g2-abc')
                        raise urllib.error.HTTPError(request.full_url,302,'redirect',{'Location':issuer+'/protocol/openid-connect/auth?state=private'},None)
                with ExitStack() as stack:
                    stack.enter_context(patch.object(rt,'ARTIFACTS',root));stack.enter_context(patch.object(rt,'runtime_value',return_value=runtime));stack.enter_context(patch.object(rt,'inspect_owned',side_effect=inspect));stack.enter_context(patch.object(rt,'docker',side_effect=docker));stack.enter_context(patch.object(rt,'wait_http'));stack.enter_context(patch.object(rt,'execute',side_effect=lambda m,n,cmd,**kw:docker(m,cmd[3:])));stack.enter_context(patch.object(urllib.request,'build_opener',return_value=Opener()))
                    if failure:
                        with self.assertRaisesRegex(ValueError,'WEB_NETWORK_NAMESPACE|WEB_OIDC_REDIRECT'):module.restart(m)
                    else:
                        module.restart(m);self.assertEqual(state['web'],'net:[11]')
                        receipt=json.loads(next((root/rid).glob('migration-web-namespace-*.json')).read_text());self.assertEqual(receipt['loginStatus'],302);self.assertEqual(receipt['after']['api'],receipt['after']['web']);self.assertNotIn('state=private',json.dumps(receipt))

    def test_actual_manifest_is_losslessly_retired_on_success_or_test_failure(self):
        """当前合成输入用完必须原样归档并退休；未知预存/执行期间漂移绝不删除。"""
        import run,runtime as rt,readback
        from unittest.mock import patch
        from contextlib import ExitStack
        module=run.module('module-tests')
        for mode in ('pass','failure','unknown','drift'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
                root=Path(directory);rid='b-continue-20990101-96';a=root/'artifacts';private=root/'private';private.mkdir();(private/'platform-password').write_text('synthetic')
                output=root/'backend/tests/OntologyPlatform.G2ContractTests/bin/Debug/actual-v2-manifest.json';output.parent.mkdir(parents=True)
                if mode=='unknown':output.write_bytes(b'unknown prior output')
                captured=[]
                def execute(*args,**kwargs):
                    captured.append(output.read_bytes());self.assertEqual(json.loads(captured[0])['releaseId'],'current-release')
                    if mode=='failure':raise ValueError('FIXTURE_TEST_FAILED')
                    if mode=='drift':output.write_bytes(b'changed input')
                    return b'fixture output'
                with ExitStack() as stack:
                    for name,value in [('ROOT',root),('ARTIFACTS',a)]:stack.enter_context(patch.object(rt,name,value))
                    stack.enter_context(patch.object(rt,'private_dir',return_value=private));stack.enter_context(patch.object(rt,'environment',return_value={}));stack.enter_context(patch.object(rt,'check_build'));stack.enter_context(patch.object(rt,'execute',side_effect=execute));stack.enter_context(patch.object(rt,'test_projection',return_value={'summary':{'total':1,'PASS':1,'FAIL':0,'SKIP':0}}));stack.enter_context(patch.object(readback,'reports',return_value={'releases':[{'manifest':{'schemaVersion':2,'releaseId':'current-release'}}]}));stack.enter_context(patch.object(readback,'report_sha',return_value='b'*64))
                    m={'runId':rid,'_head':'a'*40}
                    if mode=='pass':module.g3_fixture_tests(m)
                    else:
                        with self.assertRaisesRegex(ValueError,{'failure':'FIXTURE_TEST_FAILED','unknown':'EXISTING_COMPATIBILITY_MANIFEST','drift':'ACTUAL_V2_INPUT_DRIFT'}[mode]):module.g3_fixture_tests(m)
                if mode in ('pass','failure'):
                    self.assertFalse(output.exists());self.assertEqual((a/rid/'actual-v2-manifest.json').read_bytes(),captured[0]);self.assertEqual(json.loads((a/rid/'actual-v2-retired.json').read_text())['absence'],'lstat ENOENT')
                elif mode=='unknown':self.assertEqual(output.read_bytes(),b'unknown prior output');self.assertFalse((a/rid/'actual-v2-manifest.json').exists())
                else:self.assertEqual(output.read_bytes(),b'changed input');self.assertEqual((a/rid/'actual-v2-manifest.json').read_bytes(),captured[0])


if __name__ == '__main__':
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
