/** 独占新签合成Ref的用途故障注入；准确单行恢复，禁止新增合法Provider。 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync,execFileSync} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {Worker} from 'node:worker_threads';
const root=path.resolve(import.meta.dirname,'../..'),privateDir=path.join(root,'.tools/security/g4-m1-recovery-001-20261101-01');
const report={taskId:'G4-M1-RECOVERY-001',status:'FAIL',commands:[],http:[],cleanupErrors:[]};
const docker=['--context','desktop-linux'],hash=v=>createHash('sha256').update(v).digest('hex');
function demand(value){if(!value)throw new Error('assertion_failed');}
function inspect(name){const v=JSON.parse(execFileSync('docker',[...docker,'inspect',name],{encoding:'utf8',timeout:5000}))[0];demand(v.Config.Labels['ontology.task-id']===report.taskId&&v.Config.Labels['ontology.run-id']==='recovery-20261101-01'&&v.State.Running&&!v.State.Paused);return v.Id;}
const platform=inspect('ontology-g4-m1-recovery-001-platform-pg-1'),source=inspect('ontology-g4-m1-recovery-001-pg-source-1');
let ref,changed=false,guard,expired=false,browser,injectedAt;
function db(sql,operation){const argv=[...docker,'exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt'];const x=spawnSync('docker',argv,{input:"SET lock_timeout='1s';SET statement_timeout='2s';"+sql,encoding:'utf8',timeout:4000});report.commands.push({command:['docker',...argv],operation,exitCode:x.status,sql:'SUPPRESSED_PRIVATE_REFERENCE',stderrBytes:Buffer.byteLength(x.stderr??'')});demand(x.status===0);return JSON.parse(x.stdout);}
function state(){return db('SELECT json_build_object(\'purpose\',"Purpose",\'ownerHash\',encode(sha256(convert_to("Owner",\'UTF8\')),\'hex\'),\'org\',"OrganizationId",\'unused\',"UsedAtUtc" IS NULL AND "ConnectionId" IS NULL,\'unexpired\',"ExpiresAtUtc">now(),\'cipherHash\',encode(sha256(convert_to("Ciphertext"||\':\'||"Nonce"||\':\'||"Tag",\'UTF8\')),\'hex\')) FROM connections."ConnectionSecrets" WHERE "Id"=\''+ref+'\';','safe_reference_projection');}
function restore(){if(!ref||!changed)return;const count=db('WITH changed AS (UPDATE connections."ConnectionSecrets" SET "Purpose"=\'POSTGRESQL_READONLY\' WHERE "Id"=\''+ref+'\' AND "Purpose"=\'RECOVERY_WRONG_PURPOSE\' AND "UsedAtUtc" IS NULL RETURNING 1) SELECT count(*) FROM changed;','restore_exact_reference_purpose');demand(count===0||count===1);const restored=state();demand(restored.purpose==='POSTGRESQL_READONLY'&&restored.unused&&restored.cipherHash===report.before.cipherHash);changed=false;}
function tcp(){const raw=execFileSync('docker',[...docker,'exec',source,'cat','/proc/net/snmp'],{encoding:'utf8',timeout:4000}).split('\n').filter(x=>x.startsWith('Tcp:'));const keys=raw[0].split(/\s+/),values=raw[1].split(/\s+/);return Number(values[keys.indexOf('PassiveOpens')]);}
try {
 demand(fs.realpathSync(privateDir)===privateDir&&(fs.statSync(privateDir).mode&0o077)===0);
 const runtime=JSON.parse(fs.readFileSync(path.join(privateDir,'runtime.json'),'utf8')),realm=JSON.parse(fs.readFileSync(runtime.realmFile,'utf8'));
 const {chromium}=createRequire(path.join(root,'apps/web/package.json'))('@playwright/test');browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({serviceWorkers:'block',extraHTTPHeaders:{Connection:'close'}});await context.route('**/*',r=>['http://localhost:15100','http://localhost:15180'].includes(new URL(r.request().url()).origin)?r.continue():r.abort());
 const page=await context.newPage();page.setDefaultTimeout(15000);await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fdata%2Fconnections');const user=realm.identities['g2-operator-ab'];await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();await page.waitForURL(u=>u.origin==='http://localhost:15100'&&u.pathname==='/data/connections');await page.close();
 const csrf=await context.request.get('http://localhost:15100/auth/csrf');demand(csrf.status()===200);const token=(await csrf.json()).requestToken;
 const headers={Origin:'http://localhost:15100','X-CSRF-TOKEN':token,Connection:'close'};
 async function request(route,body){const x=await context.request.post('http://localhost:15100'+route,{data:body,headers,timeout:6000,maxRedirects:0});report.http.push({route,status:x.status()});return {status:x.status(),value:await x.json()};}
 const command=()=>({commandId:randomUUID(),idempotencyKey:randomUUID(),expectedRevision:0,reason:'Synthetic wrong purpose consumption rejection'});
 const scope={organizationId:'org-demo',siteIds:['site-a']};const issued=await request('/api/v1/connection-secrets',{secretValue:fs.readFileSync(path.join(privateDir,'reader-password'),'utf8').trimEnd(),scopeSelection:scope,purpose:'POSTGRESQL_READONLY',command:command()});
 demand(issued.status===201&&/^[a-f0-9]{32}$/.test(issued.value.secretRef));ref=issued.value.secretRef;report.refSha256=hash(ref);report.before=state();demand(report.before.unused&&report.before.unexpired&&report.before.purpose==='POSTGRESQL_READONLY');
 const active=db('SELECT (SELECT count(*) FROM connections."CatalogJobs" WHERE "Status" IN (\'QUEUED\',\'RUNNING\'))+(SELECT count(*) FROM connections."ConnectionProbes" WHERE "ReportJson"::jsonb->>\'status\'=\'RUNNING\');','active_work_count');demand(active===0);
 const beforeTcp=tcp();changed=true;injectedAt=Date.now();
 const recoverySql='SET lock_timeout=\'1s\';SET statement_timeout=\'2s\';UPDATE connections."ConnectionSecrets" SET "Purpose"=\'POSTGRESQL_READONLY\' WHERE "Id"=\''+ref+'\' AND "Purpose"=\'RECOVERY_WRONG_PURPOSE\' AND "UsedAtUtc" IS NULL;';
 guard=new Worker(`const {workerData,parentPort}=require('node:worker_threads');const {spawnSync}=require('node:child_process');setTimeout(()=>{const x=spawnSync('docker',workerData.argv,{input:workerData.sql,encoding:'utf8',timeout:4000});parentPort.postMessage({expired:true,exitCode:x.status,stderrBytes:Buffer.byteLength(x.stderr??'')});},12000);`,{eval:true,workerData:{argv:[...docker,'exec','-i',platform,'psql','-U','platform','-d','platform','-v','ON_ERROR_STOP=1','-qAt'],sql:recoverySql}});
 guard.on('message',message=>{expired=true;report.watchdog=message;});guard.on('error',()=>{expired=true;report.cleanupErrors.push('watchdog_error');});
 const count=db('WITH changed AS (UPDATE connections."ConnectionSecrets" SET "Purpose"=\'RECOVERY_WRONG_PURPOSE\' WHERE "Id"=\''+ref+'\' AND "Purpose"=\'POSTGRESQL_READONLY\' AND "UsedAtUtc" IS NULL AND "ExpiresAtUtc">now() RETURNING 1) SELECT count(*) FROM changed;','change_exact_unused_reference_purpose');demand(count===1);
 report.injected={purpose:'RECOVERY_WRONG_PURPOSE',affectedRows:count};
 const response=await request('/api/v1/connections',{displayName:'Synthetic purpose rejection',scopeSelection:scope,config:{type:'POSTGRESQL',profile:{host:'pg-source',port:5432,database:'fixture',username:'fixture_reader',sslMode:'VerifyFull',allowedSchemas:['production']}},secretRef:ref,command:command()});
 demand(response.status===422&&response.value.code==='connection_secret_expired'&&!expired);report.rejectionCode=response.value.code;report.passiveOpenDelta=tcp()-beforeTcp;demand(report.passiveOpenDelta===0);
 report.afterRejected=state();demand(report.afterRejected.unused&&report.afterRejected.unexpired&&report.afterRejected.cipherHash===report.before.cipherHash&&report.afterRejected.ownerHash===report.before.ownerHash);
 restore();await guard.terminate();guard=null;demand(!expired&&Date.now()-injectedAt<12000);report.restored=state();demand(JSON.stringify(report.restored)===JSON.stringify(report.before));report.status='PASS';
}catch(error){report.failure={category:error.name};process.exitCode=1;}
finally{try{restore();}catch{report.cleanupErrors.push('finally_restore_failed');process.exitCode=1;}await guard?.terminate();await browser?.close();if(report.cleanupErrors.length||expired){report.status='FAIL';process.exitCode=1;}report.driverSha256=hash(fs.readFileSync(import.meta.filename));fs.writeFileSync(path.join(root,'artifacts/g4-m1-recovery-001/purpose-consumption-fault.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({status:report.status,cleanupErrors:report.cleanupErrors}));}
