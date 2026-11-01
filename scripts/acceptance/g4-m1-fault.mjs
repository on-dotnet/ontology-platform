/** 真实故障验收的固定HTTP操作；夹具变更由Master在准确任务数据库另行执行并恢复。 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { randomUUID, createHash } from 'node:crypto';
const root=path.resolve(import.meta.dirname,'../..');
const privateDir=path.join(root,'.tools/security/g4-m1-recovery-001-20261101-01');
const allowed=['snapshot-read','audit-prepare','audit-fail','audit-retry','job-start','job-cancel','job-read','probe-refresh','audit-replay-failed','probe-client-cancel'];
if(process.argv.includes('--help')) {console.log('Usage: node g4-m1-fault.mjs --runtime-file <private runtime> --action '+allowed.join('|'));process.exit(0);}
const args=process.argv.slice(2);
const report={taskId:'G4-M1-RECOVERY-001',startedUtc:new Date().toISOString(),checks:[],http:[],scope:'ONE_HTTP_ACTION_ONLY',databaseRollbackLeaseFenceEvidence:'NOT_RUN_BY_THIS_CONSUMER'};
let browser,context;
function demand(value,code){if(!value){const e=new Error();e.safeCode=code;throw e;}}
function privateJson(file){demand(fs.realpathSync(privateDir)===privateDir&&!fs.lstatSync(privateDir).isSymbolicLink()&&(fs.statSync(privateDir).mode&0o077)===0,'private_directory');demand(path.dirname(file)===privateDir&&!fs.lstatSync(file).isSymbolicLink()&&(fs.statSync(file).mode&0o077)===0,'private_boundary');return JSON.parse(fs.readFileSync(file,'utf8'));}
function writePrivate(file,value){fs.writeFileSync(file,JSON.stringify(value),{flag:'wx',mode:0o600});}
const hash=value=>createHash('sha256').update(value).digest('hex');
const cmd=revision=>({commandId:randomUUID(),idempotencyKey:randomUUID(),expectedRevision:revision,reason:'Synthetic recovery fault acceptance'});
try{
 demand(args.length===4&&args[0]==='--runtime-file'&&args[2]==='--action'&&allowed.includes(args[3]),'arguments');
 const action=args[3];report.action=action;const runtime=privateJson(path.resolve(args[1]));
 demand(runtime.taskId===report.taskId&&runtime.runId==='recovery-20261101-01'&&runtime.publicOrigin==='http://localhost:15100','task_binding');
 const id=runtime.httpConnectionId;demand(/^[a-f0-9]{32}$/.test(id??''),'connection_id');report.connectionId=id;
 const realm=privateJson(runtime.realmFile);demand(/^http:\/\/localhost:15180\/realms\/g2-[a-f0-9]+$/.test(realm.authority),'issuer');
 const require=createRequire(path.join(root,'apps/web/package.json'));const{chromium}=require('@playwright/test');browser=await chromium.launch({channel:'msedge',headless:true});context=await browser.newContext({serviceWorkers:'block',extraHTTPHeaders:{Connection:'close'}});context.setDefaultTimeout(15000);
 await context.route('**/*',r=>['http://localhost:15100','http://localhost:15180'].includes(new URL(r.request().url()).origin)?r.continue():r.abort());
 const page=await context.newPage();await page.goto(runtime.publicOrigin+'/auth/login?returnUrl=%2Fdata%2Fconnections');const user=realm.identities['g2-operator-ab'];await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();await page.waitForURL(u=>u.origin===runtime.publicOrigin&&u.pathname==='/data/connections');await page.close();
 const csrfResponse=await context.request.get(runtime.publicOrigin+'/auth/csrf',{headers:{Connection:'close'},maxRedirects:0});demand(csrfResponse.status()===200,'csrf_status');const csrf=(await csrfResponse.json()).requestToken;demand(typeof csrf==='string','csrf_value');
 const headers={Connection:'close',Origin:runtime.publicOrigin,'X-CSRF-TOKEN':csrf};
 async function request(method,route,body,etag){
  demand(route.startsWith('/api/v1/connections/')||route.startsWith('/api/v1/catalogs/')||route==='/api/v1/platform/me','fixed_route');
  const start=Date.now();const response=await context.request.fetch(runtime.publicOrigin+route,{method,data:body,headers:{...headers,...(etag?{'If-Match':etag}:{})},maxRedirects:0,timeout:30000});const record={method,route:route.replace(/[a-f0-9]{32}/g,'{id}'),status:response.status(),durationMs:Date.now()-start};report.http.push(record);
  const raw=await response.text();demand(raw.length<8*1024*1024,'response_budget');let value=null;try{value=JSON.parse(raw);}catch{}
  record.jsonBody=!!value&&typeof value==='object';
  if(value?.code&&['connection_profile_invalid','connection_version_conflict','connection_secret_expired','catalog_access_forbidden','authentication_required','dependency_unavailable'].includes(value.code))record.code=value.code;
  demand(record.jsonBody||(['PATCH','POST'].includes(method)&&[500,503].includes(response.status())),'expected_json_response');
  return {status:response.status(),value,etag:response.headers().etag};
 }
 const current=await request('GET','/api/v1/connections/'+id);demand(current.status===200,'current_connection');
 const auditStage=runtime.auditStage??'start';demand(['start','complete'].includes(auditStage),'audit_stage');report.auditStage=auditStage;
 const pending=path.join(privateDir,'fault-audit-'+auditStage+'-command.json');
 if(action==='snapshot-read'){
  demand(/^[a-f0-9]{32}$/.test(runtime.httpSnapshotId??''),'snapshot_id');const x=await request('GET','/api/v1/catalogs/'+runtime.httpSnapshotId);demand(x.status===200,'snapshot_status');demand(x.value.snapshotId===runtime.httpSnapshotId&&['READY','STALE'].includes(x.value.status)&&/^[a-f0-9]{64}$/.test(x.value.schemaFingerprint)&&Array.isArray(x.value.objects),'snapshot_projection');report.snapshot={id:x.value.snapshotId,status:x.value.status,fingerprint:x.value.schemaFingerprint,containsRecoveryExtra:x.value.objects.some(o=>o.fields.some(f=>f.name==='recovery_extra'))};
 }else if(action.startsWith('audit-')){
  if(action==='audit-prepare'){
   const me=await request('GET','/api/v1/platform/me');demand(me.status===200&&typeof me.value.subjectId==='string'&&me.value.scopes.some(x=>x.organizationId==='org-demo'&&x.siteId==='site-a'),'identity');const body={command:cmd(current.value.configRevision)};
   const key=hash(JSON.stringify({subjectId:me.value.subjectId,organizationId:'org-demo',operation:'test',id,childId:null,idempotencyKey:body.command.idempotencyKey}));
   writePrivate(pending,{id,body,etag:current.etag,beforeRevision:current.value.configRevision,beforeName:current.value.displayName,beforeProbeId:current.value.lastProbeId,commandKey:key});report.commandKey=key;
  }else{
   const saved=privateJson(pending);demand(saved.id===id,'command_binding');const x=await request('POST','/api/v1/connections/'+id+'/test',saved.body,saved.etag);report.commandKey=saved.commandKey;if(x.status===200){demand(/^[a-f0-9]{32}$/.test(x.value.probeId),'probe_id');report.probeId=x.value.probeId;}
   const after=await request('GET','/api/v1/connections/'+id);demand(after.status===200,'after_connection');
   if(action==='audit-fail'){demand([500,503].includes(x.status),'fault_response');demand(after.value.configRevision===saved.beforeRevision&&after.value.displayName===saved.beforeName&&after.value.lastProbeId===saved.beforeProbeId&&after.etag===saved.etag,'http_rollback');report.checks.push({name:'http_state_unchanged_after_targeted_audit_fault',status:'PASS'});}
   else if(action==='audit-replay-failed'){demand(x.status===200&&x.value.status==='TEST_FAILED'&&after.value.lastProbeId===saved.beforeProbeId,'recovered_probe_failed');report.checks.push({name:'same_command_replays_recovered_failure_without_false_success',status:'PASS'});}
   else{demand(x.status===200&&x.value.status==='TEST_OK'&&Array.isArray(x.value.stages)&&x.value.stages.length===5&&['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].every(name=>x.value.stages.filter(s=>s.name===name&&s.status==='PASS').length===1)&&after.value.configRevision===saved.beforeRevision&&after.value.lastProbeId===x.value.probeId&&after.value.lastProbeId!==saved.beforeProbeId,'same_command_retry');report.checks.push({name:'same_command_succeeds_after_fault_removed',status:'PASS'});}
  }
 }else if(action==='probe-client-cancel'){
  const me=await request('GET','/api/v1/platform/me');demand(me.status===200&&typeof me.value.subjectId==='string'&&me.value.scopes.some(x=>x.organizationId==='org-demo'&&x.siteId==='site-a'),'identity');
  const body={command:cmd(current.value.configRevision)};
  report.commandKey=hash(JSON.stringify({subjectId:me.value.subjectId,organizationId:'org-demo',operation:'test',id,childId:null,idempotencyKey:body.command.idempotencyKey}));
  const cancelPage=await context.newPage();await cancelPage.goto(runtime.publicOrigin+'/health/live');
  const result=await cancelPage.evaluate(async input=>{
   const controller=new AbortController();const start=performance.now();const timer=setTimeout(()=>controller.abort(),1500);
   try {const response=await fetch(input.route,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-TOKEN':input.csrf,'If-Match':input.etag},body:JSON.stringify(input.body),signal:controller.signal});return {aborted:false,status:response.status,durationMs:performance.now()-start};}
   catch(error){return {aborted:error.name==='AbortError',durationMs:performance.now()-start};}
   finally{clearTimeout(timer);}
  },{route:'/api/v1/connections/'+id+'/test',csrf,etag:current.etag,body});
  demand(result.aborted&&result.durationMs>=1400&&result.durationMs<5000,'actual_browser_request_abort');report.clientCancellation=result;report.checks.push({name:'actual_request_aborted_during_source_wait',status:'PASS'});await cancelPage.close();
 }else if(action==='probe-refresh'){
  const x=await request('POST','/api/v1/connections/'+id+'/test',{command:cmd(current.value.configRevision)},current.etag);demand(x.status===200&&x.value.status==='TEST_OK'&&Array.isArray(x.value.stages)&&x.value.stages.length===5&&['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].every(name=>x.value.stages.filter(s=>s.name===name&&s.status==='PASS'&&s.durationMs>=0).length===1),'probe_refresh');report.checks.push({name:'real_five_stage_probe_refreshed',status:'PASS'});
 }else if(action==='job-start'){
  const x=await request('POST','/api/v1/connections/'+id+'/discoveries',{command:cmd(current.value.configRevision)},current.etag);demand(x.status===202,'job_start');demand(/^[a-f0-9]{32}$/.test(x.value.jobId)&&['QUEUED','RUNNING','SUCCEEDED','FAILED','PARTIAL','CANCELLED'].includes(x.value.status),'job_projection');report.jobId=x.value.jobId;report.jobStatus=x.value.status;
 }else{
  demand(/^[a-f0-9]{32}$/.test(runtime.httpJobId??''),'job_id');let x;
  if(action==='job-cancel')x=await request('POST','/api/v1/connections/'+id+'/discoveries/'+runtime.httpJobId+'/cancel',{command:cmd(current.value.configRevision)},current.etag);
  else x=await request('GET','/api/v1/connections/'+id+'/discoveries/'+runtime.httpJobId);
  demand(x.status===200&&x.value.jobId===runtime.httpJobId,'job_response');demand(/^[a-f0-9]{32}$/.test(x.value.jobId)&&['QUEUED','RUNNING','SUCCEEDED','FAILED','PARTIAL','CANCELLED'].includes(x.value.status),'job_projection');report.jobId=x.value.jobId;report.jobStatus=x.value.status;demand(x.value.snapshotId===null||/^[a-f0-9]{32}$/.test(x.value.snapshotId),'snapshot_projection');demand(x.value.diagnosticCode===null||['connection_source_unavailable','catalog_permission_limited','catalog_budget_exceeded','connection_cancelled','connection_readonly_unverified','connection_tls_untrusted','connection_auth_failed','connection_network_forbidden','catalog_access_forbidden'].includes(x.value.diagnosticCode),'diagnostic_projection');report.snapshotId=x.value.snapshotId;report.diagnosticCode=x.value.diagnosticCode;
 }
 report.status='PASS';
}catch(error){report.status='FAIL';report.failure={code:error.safeCode??'bounded_runtime_error',category:error.name==='TimeoutError'?'timeout':'runtime'};process.exitCode=1;}
finally{await context?.close().catch(()=>{});await browser?.close().catch(()=>{});report.completedUtc=new Date().toISOString();const dir=path.join(root,'artifacts/g4-m1-recovery-001/fault-http');fs.mkdirSync(dir,{recursive:true});const file=path.join(dir,randomUUID()+'.json');fs.writeFileSync(file,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({action:report.action,status:report.status,evidence:path.relative(root,file),failure:report.failure}));}
