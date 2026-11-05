/** 直接调用也必须先验证冻结身份；校验失败不读取凭据、不启动浏览器。 */
import { execFileSync as verifyConsumerProcess } from 'node:child_process';
import { resolve as resolveConsumerPath } from 'node:path';
const consumerArgs = process.argv.slice(2);
const consumerBinding = {};
for (const key of ['run-id', 'expected-head', 'resource-manifest']) {
  const flag = '--' + key;
  const index = consumerArgs.indexOf(flag);
  if (index >= 0 && consumerArgs.lastIndexOf(flag) === index && index + 1 < consumerArgs.length) {
    consumerBinding[key] = consumerArgs[index + 1]; consumerArgs.splice(index, 2);
  }
}
if (!consumerArgs.includes('--help')) {
  const runtimeIndex = consumerArgs.indexOf('--runtime-file');
  const evidenceIndex = consumerArgs.indexOf('--evidence-dir');
  try {
    if (Object.keys(consumerBinding).length !== 3 || runtimeIndex < 0 || evidenceIndex < 0) throw new Error('binding');
    const check = [resolveConsumerPath(import.meta.dirname, 'consumer_check.py'), '--consumer', 'fault',
      '--run-id', consumerBinding['run-id'], '--expected-head', consumerBinding['expected-head'],
      '--resource-manifest', consumerBinding['resource-manifest'], '--runtime-file', consumerArgs[runtimeIndex + 1]];
    if (evidenceIndex >= 0) check.push('--evidence-dir', consumerArgs[evidenceIndex + 1]);
    verifyConsumerProcess('python3', ['-B', ...check], {stdio: 'pipe', timeout: 30000});
  } catch { console.error('REFUSED_CONSUMER_BOUNDARY'); process.exit(2); }
}
const outputIndex = consumerArgs.indexOf('--evidence-dir');
const faultEvidenceDirectory = outputIndex >= 0 ? consumerArgs[outputIndex + 1] : null;
if (outputIndex >= 0) consumerArgs.splice(outputIndex, 2);
process.argv = [...process.argv.slice(0, 2), ...consumerArgs];
/** 真实故障验收的固定HTTP操作；夹具变更由Master在准确任务数据库另行执行并恢复。 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { randomUUID, createHash } from 'node:crypto';
const root=path.resolve(import.meta.dirname,'../..');
const privateDir=path.join(root,'.tools/security/g4-m1-main-integration-001-'+consumerBinding['run-id']);
const allowed=['snapshot-read','audit-prepare','audit-fail','audit-retry','job-start','job-cancel','job-read','probe-refresh','audit-replay-failed','probe-client-cancel','intake-foreign','original-identity-check','disabled-denials','intake-lifecycle','intake-revocation','probe-denial','purpose-denial','catalog-cancel'];
if(process.argv.includes('--help')) {console.log('Usage: node experiments/g4-m1-main-integration/fault.mjs --run-id RUN --expected-head HEAD --resource-manifest PATH --evidence-dir NEW_PATH --runtime-file <private runtime> --action '+allowed.join('|'));process.exit(0);}
const args=process.argv.slice(2);
const report={taskId:'G4-M1-MAIN-INTEGRATION-001',runId:consumerBinding['run-id'],testedCommit:consumerBinding['expected-head'],startedUtc:new Date().toISOString(),checks:[],http:[],scope:'ONE_HTTP_ACTION_ONLY',databaseRollbackLeaseFenceEvidence:'NOT_RUN_BY_THIS_CONSUMER'};
let browser,context;
function demand(value,code){if(!value){const e=new Error();e.safeCode=code;throw e;}}
function privateJson(file){demand(fs.realpathSync(privateDir)===privateDir&&!fs.lstatSync(privateDir).isSymbolicLink()&&(fs.statSync(privateDir).mode&0o077)===0,'private_directory');demand(path.dirname(file)===privateDir&&!fs.lstatSync(file).isSymbolicLink()&&(fs.statSync(file).mode&0o077)===0,'private_boundary');return JSON.parse(fs.readFileSync(file,'utf8'));}
function writePrivate(file,value){fs.writeFileSync(file,JSON.stringify(value),{flag:'wx',mode:0o600});}
/** 固定取消握手；认证与全部消费者校验在加锁前完成。 */
function waitForCatalogControl(kind, connectionId, jobId) {
 const protocol={
  ready:{event:'CATALOG_CANCEL_READY',marker:'SOURCE_LOCKED\n',timeout:10000},
  started:{event:'CATALOG_JOB_STARTED',marker:'SOURCE_QUERY_WAITING\n',timeout:5000},
  cancelled:{event:'CATALOG_CANCEL_REQUESTED',marker:'SOURCE_QUERY_CANCELLED\n',timeout:5000},
 }[kind];
 demand(!!protocol,'cancel_control_kind');
 demand(/^[a-f0-9]{32}$/.test(connectionId),'cancel_control_connection');
 if(kind!=='ready')demand(/^[a-f0-9]{32}$/.test(jobId),'cancel_control_job');
 const receipt={event:protocol.event,status:'READY',readyAtUtc:new Date().toISOString()};
 (report.controlHandshakes??=[]).push(receipt);
 return new Promise((resolve,reject)=>{
  let pending=Buffer.alloc(0),settled=false;
  const finish=code=>{
   if(settled)return;settled=true;clearTimeout(timer);
   process.stdin.removeListener('data',onData);process.stdin.removeListener('end',onEnd);process.stdin.removeListener('error',onError);process.stdin.pause();
   if(code){receipt.status='FAILED';receipt.failureCode=code;const error=new Error();error.safeCode=code;reject(error);}
   else{receipt.status='MARKER_ACKNOWLEDGED';receipt.acknowledgedAtUtc=new Date().toISOString();resolve();}
  };
  const onData=chunk=>{
   const bytes=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);
   if(pending.length+bytes.length>64){finish('cancel_control_oversize');return;}
   pending=Buffer.concat([pending,bytes]);const expected=Buffer.from(protocol.marker);
   if(pending.length>expected.length||!expected.subarray(0,pending.length).equals(pending)){finish('cancel_control_marker');return;}
   if(pending.equals(expected))finish();
  };
  const onEnd=()=>finish('cancel_control_eof'),onError=()=>finish('cancel_control_transport');
  const timer=setTimeout(()=>finish('cancel_control_timeout'),protocol.timeout);
  process.stdin.on('data',onData);process.stdin.on('end',onEnd);process.stdin.on('error',onError);
  if(process.stdin.readableEnded||process.stdin.destroyed){finish('cancel_control_eof');return;}
  try{process.stdout.write(JSON.stringify({taskId:report.taskId,runId:report.runId,event:protocol.event,connectionId,...(kind==='ready'?{}:{jobId})})+'\n');process.stdin.resume();}
  catch{finish('cancel_control_transport');}
 });
}
const hash=value=>createHash('sha256').update(value).digest('hex');
const cmd=revision=>({commandId:randomUUID(),idempotencyKey:randomUUID(),expectedRevision:revision,reason:'Synthetic recovery fault acceptance'});
try{
 demand(args.length===4&&args[0]==='--runtime-file'&&args[2]==='--action'&&allowed.includes(args[3]),'arguments');
 const action=args[3];report.action=action;const runtime=privateJson(path.resolve(args[1]));
 demand(runtime.taskId===report.taskId&&runtime.runId===consumerBinding['run-id']&&runtime.publicOrigin==='http://localhost:15100','task_binding');
 const id=runtime.httpConnectionId;demand(/^[a-f0-9]{32}$/.test(id??''),'connection_id');report.connectionId=id;
 const realm=privateJson(runtime.realmFile);demand(/^http:\/\/localhost:15180\/realms\/g2-[a-f0-9]+$/.test(realm.authority),'issuer');
 const require=createRequire(path.join(root,'apps/web/package.json'));const{chromium}=require('@playwright/test');browser=await chromium.launch({channel:'msedge',headless:true});context=await browser.newContext({serviceWorkers:'block',extraHTTPHeaders:{Connection:'close'}});context.setDefaultTimeout(15000);
 await context.route('**/*',r=>['http://localhost:15100','http://localhost:15180'].includes(new URL(r.request().url()).origin)?r.continue():r.abort());
 const page=await context.newPage();await page.goto(runtime.publicOrigin+'/auth/login?returnUrl=%2Fdata%2Fconnections');const user=realm.identities[['intake-foreign','original-identity-check'].includes(action)?'g2-operator-a':'g2-operator-ab'];await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();await page.waitForURL(u=>u.origin===runtime.publicOrigin&&u.pathname==='/data/connections');await page.close();
 const csrfResponse=await context.request.get(runtime.publicOrigin+'/auth/csrf',{headers:{Connection:'close'},maxRedirects:0});demand(csrfResponse.status()===200,'csrf_status');const csrf=(await csrfResponse.json()).requestToken;demand(typeof csrf==='string','csrf_value');
 const headers={Connection:'close',Origin:runtime.publicOrigin,'X-CSRF-TOKEN':csrf};
 async function request(method,route,body,etag){
  demand((action==='purpose-denial'&&route==='/api/v1/connections')||route.startsWith('/api/v1/connections/')||route.startsWith('/api/v1/catalogs/')||route==='/api/v1/platform/me'||['intake-foreign','intake-lifecycle','intake-revocation'].includes(action)&&route==='/api/v1/connection-secrets','fixed_route');
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
 if(['intake-lifecycle','intake-revocation'].includes(action)){
  const secretFile=path.join(privateDir,'reader-password');demand(!fs.lstatSync(secretFile).isSymbolicLink()&&(fs.statSync(secretFile).mode&0o077)===0,'source_secret_boundary');
  const issue=async()=>{const x=await request('POST','/api/v1/connection-secrets',{secretValue:fs.readFileSync(secretFile,'utf8').trimEnd(),scopeSelection:{organizationId:'org-demo',siteIds:['site-a']},purpose:'POSTGRESQL_READONLY',command:cmd(0)});demand(x.status===201&&/^[a-f0-9]{32}$/.test(x.value.secretRef),'lifecycle_intake');return x.value;};
  if(action==='intake-revocation'){
   const fresh=await issue();writePrivate(path.join(privateDir,'fresh-revocation-ref.json'),fresh);report.checks.push({name:'fresh_unexpired_revocation_intake',status:'PASS'});
  }else{
  const expiring=await issue(),revoked=await issue(),purpose=await issue();
  writePrivate(path.join(privateDir,'lifecycle-refs.json'),{expiredSecretRef:expiring.secretRef,expiredSecretExpiresAtUtc:expiring.expiresAtUtc,revokedSecretRef:revoked.secretRef,purposeSecretRef:purpose.secretRef});
  report.checks.push({name:'two_actual_intake_receipts_kept_private',status:'PASS'});report.naturalExpiry=expiring.expiresAtUtc;
  }
 }else if(action==='purpose-denial'){
  const issued=privateJson(path.join(privateDir,'lifecycle-refs.json'));demand(/^[a-f0-9]{32}$/.test(issued.purposeSecretRef),'purpose_ref');
  const x=await request('POST','/api/v1/connections',{displayName:'Synthetic purpose rejection',scopeSelection:{organizationId:'org-demo',siteIds:['site-a']},config:{type:'POSTGRESQL',profile:{host:'pg-source',port:5432,database:'fixture',username:'fixture_reader',sslMode:'VerifyFull',allowedSchemas:['production']}},secretRef:issued.purposeSecretRef,command:cmd(0)});
  demand(x.status===422&&x.value.code==='connection_secret_expired','purpose_consumption_denied');report.checks.push({name:'actual_wrong_purpose_reference_not_consumed',status:'PASS'});
 }else if(action==='probe-denial'){
  demand(['connection_readonly_unverified','connection_auth_failed','connection_tls_untrusted','catalog_permission_limited'].includes(runtime.expectedProbeDiagnostic),'probe_expected_code');
  const x=await request('POST','/api/v1/connections/'+id+'/test',{command:cmd(current.value.configRevision)},current.etag);
  demand(x.status===200&&x.value.status==='TEST_FAILED'&&x.value.stages.some(s=>s.status==='FAIL'&&s.diagnosticCode===runtime.expectedProbeDiagnostic),'real_probe_denial');
  demand(/^[a-f0-9]{32}$/.test(x.value.probeId),'probe_id');report.probeId=x.value.probeId;report.stages=x.value.stages;report.checks.push({name:'exact_source_fault_diagnostic',status:'PASS'});
 }else if(action==='disabled-denials'){
  demand(current.value.state==='DISABLED','disabled_fixture_required');
  const probe=await request('POST','/api/v1/connections/'+id+'/test',{command:cmd(current.value.configRevision)},current.etag);demand(probe.status===409,'disabled_probe_denied');
  const discovery=await request('POST','/api/v1/connections/'+id+'/discoveries',{command:cmd(current.value.configRevision)},current.etag);demand(discovery.status===409,'disabled_discovery_denied');
  const history=await request('GET','/api/v1/connections/'+id+'/catalogs');demand(history.status===403,'disabled_history_denied');
  report.checks.push({name:'disabled_probe_discovery_and_history_denied',status:'PASS'});
 }else if(action==='original-identity-check'){
  const me=await request('GET','/api/v1/platform/me');const original=privateJson(path.join(privateDir,'cross-org-ref.json'));demand(me.status===200&&me.value.subjectId===original.subjectId&&me.value.scopes.every(x=>x.organizationId==='org-demo')&&me.value.scopes.some(x=>x.siteId==='site-a'),'original_identity_restored');report.originalSubjectSha256=hash(me.value.subjectId);report.checks.push({name:'same_subject_original_org_restored_new_oidc_login',status:'PASS'});
 }else if(action==='intake-foreign'){
  const me=await request('GET','/api/v1/platform/me');demand(me.status===200&&typeof me.value.subjectId==='string'&&me.value.scopes.every(x=>x.organizationId==='org-demo')&&me.value.scopes.some(x=>x.siteId==='site-a'),'original_subject_scope');
  const secretFile=path.join(privateDir,'reader-password');demand(!fs.lstatSync(secretFile).isSymbolicLink()&&(fs.statSync(secretFile).mode&0o077)===0,'private_secret_boundary');
  const issued=await request('POST','/api/v1/connection-secrets',{secretValue:fs.readFileSync(secretFile,'utf8').trimEnd(),scopeSelection:{organizationId:'org-demo',siteIds:['site-a']},purpose:'POSTGRESQL_READONLY',command:cmd(0)});
  demand(issued.status===201&&/^[a-f0-9]{32}$/.test(issued.value.secretRef),'foreign_intake');
  writePrivate(path.join(privateDir,'cross-org-ref.json'),{secretRef:issued.value.secretRef,subjectId:me.value.subjectId,expiresAtUtc:issued.value.expiresAtUtc,organizationId:'org-demo',siteIds:['site-a']});
  report.originalSubjectSha256=hash(me.value.subjectId);report.foreignRefSha256=hash(issued.value.secretRef);report.checks.push({name:'same_operator_a_original_org_actual_intake',status:'PASS'});
 }else if(action==='snapshot-read'){
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
 }else if(action==='catalog-cancel'){
  report.scope='CATALOG_CANCEL_HANDSHAKE_ONLY';
  await waitForCatalogControl('ready',id);
  const started=await request('POST','/api/v1/connections/'+id+'/discoveries',{command:cmd(current.value.configRevision)},current.etag);
  demand(started.status===202&&/^[a-f0-9]{32}$/.test(started.value.jobId)&&['QUEUED','RUNNING','SUCCEEDED','FAILED','PARTIAL','CANCELLED'].includes(started.value.status),'job_start');
  report.jobId=started.value.jobId;report.createdStatus=started.value.status;
  await waitForCatalogControl('started',id,report.jobId);
  const cancelled=await request('POST','/api/v1/connections/'+id+'/discoveries/'+report.jobId+'/cancel',{command:cmd(current.value.configRevision)},current.etag);
  demand(cancelled.status===200&&cancelled.value.jobId===report.jobId&&['QUEUED','RUNNING','SUCCEEDED','FAILED','PARTIAL','CANCELLED'].includes(cancelled.value.status),'job_cancel');
  demand(cancelled.value.snapshotId===null,'cancel_snapshot_absent');report.jobStatus=cancelled.value.status;report.snapshotId=null;
  await waitForCatalogControl('cancelled',id,report.jobId);
  report.checks.push({name:'warm_authenticated_start_cancel_with_source_witness_handshake',status:'PASS'});
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
finally{await context?.close().catch(()=>{});await browser?.close().catch(()=>{});report.completedUtc=new Date().toISOString();const dir=faultEvidenceDirectory;fs.mkdirSync(dir,{recursive:false});const file=path.join(dir,randomUUID()+'.json');fs.writeFileSync(file,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({taskId:report.taskId,runId:report.runId,scenario:report.action,action:report.action,status:report.status,evidence:path.relative(root,file),failure:report.failure}));}
