"""隔离临时Git/假Docker拒绝回归；--real另建本任务空卷验证实际Apply，不接触项目数据。"""
import datetime as dt, hashlib, json, os, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path
ROOT=Path.cwd();E=ROOT/'docs/evidence/G3-M5-REVIEW-FIX-001';TASK='G3-M5-REVIEW-FIX-001'
SOURCE=(E/'executed-harnesses/cleanup.py').read_text();digest=lambda b:hashlib.sha256(b).hexdigest()
RESULT=[]
FAKE='''#!/usr/bin/env python3
import json,sys,os
from pathlib import Path
p=Path(os.environ['FAKE_DOCKER_STATE']);s=json.loads(p.read_text());a=sys.argv[3:]
if a[0]=='info':print(json.dumps({'ID':s['engine'],'ServerVersion':s['version']}))
elif a[:2]==['ps','-a']:print('ref' if s.get('references') else '')
elif a[:2]==['volume','inspect']:
 name=a[2]
 if name in s['volumes']:print(json.dumps([s['volumes'][name]]))
 else:
  print('[]');print('permission denied' if s.get('badPost') else 'Error response from daemon: get '+name+': no such volume',file=sys.stderr);sys.exit(1)
elif a[:2]==['volume','rm']:
 name=a[2];s['removed'].append(name);del s['volumes'][name];p.write_text(json.dumps(s));print(name)
else:sys.exit(3)
'''
def run_case(label,real=False):
 with tempfile.TemporaryDirectory(prefix='ontology-review-fix-cleanup-') as temp:
  root=Path(temp).resolve();e=root/'docs/evidence'/TASK;e.mkdir(parents=True)
  prefix='g2-rfix-fixture-'+uuid.uuid4().hex[:10] if real else 'g2-1c8100ef259a'
  names=[prefix+'-'+x+'-data' for x in ['alloy','fuseki','grafana','loki','postgres','prometheus','rustfs','tempo']]
  env=os.environ.copy();state={'engine':'fixture-engine','version':'29.9.2','volumes':{},'removed':[]}
  actualDocker=shutil.which('docker');context='desktop-linux';owned=[]
  try:
   if real:
    info=json.loads(subprocess.check_output([actualDocker,'--context',context,'info','--format','{{json .}}']))
    state.update(engine=info['ID'],version=info['ServerVersion'])
    for name in names:
     subprocess.run([actualDocker,'--context',context,'volume','create','--label','io.ontology-platform.task-id='+TASK,'--label','io.ontology-platform.test-fixture=true',name],check=True,stdout=subprocess.DEVNULL);owned.append(name)
     v=json.loads(subprocess.check_output([actualDocker,'--context',context,'volume','inspect',name]))[0]
     state['volumes'][name]={k:v.get(k) for k in ['Name','Driver','Scope','CreatedAt','Labels','Options']}
   else:
    state['volumes']={name:dict(Name=name,Driver='local',Scope='local',CreatedAt='2026-10-31T00:00:00Z',Labels=None,Options=None) for name in names}
    bindir=root/'bin';bindir.mkdir();(bindir/'docker').write_text(FAKE);(bindir/'docker').chmod(0o755)
    env['PATH']=str(bindir)+os.pathsep+env['PATH'];env['FAKE_DOCKER_STATE']=str(root/'state.json')
   plan={'taskId':TASK,'root':str(root),'expiresAtUtc':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),'backend':{'context':context,'engineId':state['engine'],'serverVersion':state['version']},'volumes':json.loads(json.dumps(state['volumes'])),'keep':{}}
   if label=='expired':plan['expiresAtUtc']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)).isoformat()
   if label=='version':state['version']='other'
   if label=='metadata':state['volumes'][names[0]]['CreatedAt']='replacement'
   if label=='referenced':state['references']=True
   if label=='bad_post':state['badPost']=True
   (root/'state.json').write_text(json.dumps(state))
   raw=(json.dumps(plan,indent=2)+'\n').encode();(e/'resource-plan.json').write_bytes(raw)
   (e/'runtime-closure.json').write_text(json.dumps({'status':'FAIL' if label=='unclosed' else 'PASS','launcherStopped':True,'volumePrefix':prefix}))
   subprocess.run(['git','init','-q',str(root)],check=True)
   subprocess.run(['git','-C',str(root),'add','docs'],check=True)
   subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic Fixture','-c','user.email=synthetic@example.invalid','commit','-qm','Synthetic cleanup proof'],check=True)
   commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
   script=root/'cleanup.py';script.write_text(SOURCE.replace('g2-1c8100ef259a',prefix))
   if label=='existing_log':(e/'resource-apply.json').write_text('protected')
   if label=='unwritable_log':(e/'resource-apply.json').mkdir()
   argv=[sys.executable,str(script),'--expected-plan-sha256','0'*64 if label=='hash' else digest(raw),'--proof-commit',commit]
   if label!='dry_run':argv.append('--apply')
   result=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True)
   state=json.loads((root/'state.json').read_text())
   success=label in ['safe_apply','dry_run','real_safe_apply']
   assert (result.returncode==0)==success,(label,result.stderr[-400:])
   if not real:
    expected=8 if label=='safe_apply' else 1 if label=='bad_post' else 0
    assert len(state['removed'])==expected
   if label=='bad_post':
    receipt=json.loads((e/'resource-apply.json').read_text());assert receipt['status']=='FAIL' and receipt['current']['state']=='VERIFIED_BEFORE_COMMAND' and any(x['command'][-3:-1]==['volume','rm'] for x in receipt['logs'])
   if real:
    for name in names:
     probe=subprocess.run([actualDocker,'--context',context,'volume','inspect',name],capture_output=True,text=True)
     assert probe.returncode==1 and json.loads(probe.stdout)==[] and probe.stderr.strip()=='Error response from daemon: get '+name+': no such volume'
    receipt=json.loads((e/'resource-apply.json').read_text());(E/'cleanup-real-fixture-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');owned=[]
   RESULT.append({'name':label,'status':'PASS','commandExitCode':result.returncode,'realDocker':real,'fixturePrefix':prefix if real else None})
  finally:
   # 仅清除此fixture精确创建且尚存在的空卷；不触碰任何项目卷。
   for name in owned:
    probe=subprocess.run([actualDocker,'--context',context,'volume','inspect',name],capture_output=True)
    if probe.returncode==0:subprocess.run([actualDocker,'--context',context,'volume','rm',name],check=True,stdout=subprocess.DEVNULL)
for label in ['dry_run','safe_apply','expired','hash','version','metadata','referenced','unclosed','existing_log','unwritable_log','bad_post']:run_case(label)
if '--real' in sys.argv:run_case('real_safe_apply',True)
report={'taskId':TASK,'executorSha256':digest(SOURCE.encode()),'status':'PASS','checks':RESULT,'fixtureRule':'真实fixture仅替换固定PREFIX为本任务唯一空卷组；其余执行器字节不变；假Docker只注入隔离临时进程PATH。'}
(E/'cleanup-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':'PASS','checks':len(RESULT)}))
