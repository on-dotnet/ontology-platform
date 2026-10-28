"""Own only successful test container IDs; verify ownership and exact absence on cleanup."""
import datetime as dt
import json
import re
import subprocess
import time

PROJECT = 'on-dotnet/ontology-platform'
SAFE_ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'
CONTAINER_ID = r'[0-9a-f]{64}'
LABEL_PREFIX = 'io.ontology-platform.'
INSPECT_FORMAT = ('{"Id":{{json .Id}},"Name":{{json .Name}},'
                  '"Project":{{json (index .Config.Labels "io.ontology-platform.project")}},'
                  '"TaskId":{{json (index .Config.Labels "io.ontology-platform.task-id")}},'
                  '"RunId":{{json (index .Config.Labels "io.ontology-platform.run-id")}},'
                  '"Fixture":{{json (index .Config.Labels "io.ontology-platform.test-fixture")}}}')


class OwnedTestContainers:
    def __init__(self, task_id, run_id, records, runner=None):
        if not all(isinstance(value,str) and re.fullmatch(SAFE_ID,value) for value in (task_id,run_id)):
            raise ValueError('Invalid test resource task/run identity')
        self.task_id=task_id
        self.run_id=run_id
        self.records=records
        self.runner=runner or subprocess.run
        self.created=[]
        self.creation_failed=False

    def record(self,phase,**values):
        self.records.append(dict(resourceLifecycle=True,project=PROJECT,taskId=self.task_id,runId=self.run_id,
                                 observedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat(),phase=phase,**values))

    def prepare(self,args):
        if args[:2]!=['docker','run']:
            return args
        if '--name' not in args or not re.fullmatch(SAFE_ID,args[args.index('--name')+1]):
            raise ValueError('Controlled test container name required')
        if any(LABEL_PREFIX in value for value in args[2:]) or '--label-file' in args:
            raise ValueError('Caller cannot override resource ownership labels')
        labels={'project':PROJECT,'task-id':self.task_id,'run-id':self.run_id,'test-fixture':'true'}
        return args[:2]+[part for key,value in labels.items() for part in ('--label',LABEL_PREFIX+key+'='+value)]+args[2:]

    def observe(self,args,result):
        if args[:2]!=['docker','run']:
            return
        name=args[args.index('--name')+1]
        if result.returncode:
            self.creation_failed=True
            self.record('create',name=name,exitCode=result.returncode,status='FAIL',errorCategory='CREATE_FAILED')
            return
        ident=(result.stdout or '').strip().splitlines()[-1:]
        if len(ident)!=1 or not re.fullmatch(CONTAINER_ID,ident[0]) or any(item['Id']==ident[0] for item in self.created):
            self.creation_failed=True
            self.record('create',name=name,exitCode=0,status='BLOCKED',errorCategory='CREATE_ID_UNVERIFIED')
            raise RuntimeError('Created container identity unavailable; no deletion authorized')
        self.created.append({'Id':ident[0],'Name':'/'+name,'Project':PROJECT,'TaskId':self.task_id,
                             'RunId':self.run_id,'Fixture':'true'})
        self.record('create',name=name,containerId=ident[0],exitCode=0,status='PASS')

    def inspect(self,ident):
        result=self.runner(['docker','container','inspect','--format',INSPECT_FORMAT,ident],
                           capture_output=True,text=True,timeout=20)
        absent='Error response from daemon: No such container: '+ident
        if result.returncode==1 and not result.stdout.strip() and result.stderr.strip()==absent:
            return None,absent
        if result.returncode or len(result.stdout)>65536:
            raise RuntimeError('CONTAINER_INSPECT_UNVERIFIED')
        value=json.loads(result.stdout)
        if not isinstance(value,dict) or set(value)!={'Id','Name','Project','TaskId','RunId','Fixture'}:
            raise RuntimeError('CONTAINER_INSPECT_SCHEMA')
        return value,None

    def cleanup(self):
        passed=not self.creation_failed
        for expected in reversed(self.created):
            ident=expected['Id']
            try:
                value,diagnostic=self.inspect(ident)
                if value is None:
                    self.record('before',containerId=ident,absent=True,absenceDiagnostic=diagnostic,status='PASS')
                    continue
                if value!=expected:
                    self.record('before',containerId=ident,status='BLOCKED',errorCategory='OWNERSHIP_MISMATCH')
                    passed=False
                    continue
                self.record('before',containerId=ident,snapshot=value,status='PASS')
                args=['docker','container','rm','--force',ident]
                self.record('command',containerId=ident,command=args)
                start=time.monotonic()
                result=self.runner(args,capture_output=True,text=True,timeout=20)
                self.record('exit',containerId=ident,exitCode=result.returncode,durationMs=round((time.monotonic()-start)*1000))
                after,diagnostic=self.inspect(ident)
                absent=after is None
                self.record('after',containerId=ident,absent=absent,absenceDiagnostic=diagnostic,
                            status='PASS' if absent and result.returncode==0 else 'FAIL')
                if not absent or result.returncode:
                    passed=False
            except (OSError,ValueError,TypeError,RuntimeError,subprocess.SubprocessError) as failure:
                passed=False
                self.record('after',containerId=ident,status='BLOCKED',errorCategory=type(failure).__name__)
        return passed
