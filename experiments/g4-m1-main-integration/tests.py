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

    def test_run_identity(self):
        import runtime as rt
        self.assertEqual(rt.run_id('b-continue-20261104-01'), 'b-continue-20261104-01')
        for value in ('recovery-20261101-01', 'final-gates-20261102-r04-final', '../x', '', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rt.run_id(value)

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

    def test_deadline_terminates_process_group(self):
        import runtime as rt
        raw,code,timed_out=rt.bounded_process([sys.executable,'-c','import time; time.sleep(20)'],
            cwd=ROOT,env=rt.environment(),timeout=0.1)
        self.assertTrue(timed_out)
        self.assertIsNotNone(code)


class ExecutionRegressionTests(unittest.TestCase):
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
        for key in ('DOTNET_CLI_HOME','NUGET_PACKAGES','NUGET_HTTP_CACHE_PATH','NUGET_SCRATCH','TMPDIR'):
            with self.subTest(key=key):
                self.assertTrue(Path(first.get(key,"/missing")).is_relative_to(ARTIFACTS/'b-continue-20261104-03'))
                self.assertTrue(Path(second.get(key,"/missing")).is_relative_to(ARTIFACTS/'b-continue-20261104-04'))
                self.assertNotEqual(first[key],second[key])

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
            (package/'.nupkg.metadata').write_text('{}')
            entry={'files':['lib/payload.dll',archive.name+'.sha512'],'sha512':'metadata-unchanged'}
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


if __name__ == '__main__':
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
