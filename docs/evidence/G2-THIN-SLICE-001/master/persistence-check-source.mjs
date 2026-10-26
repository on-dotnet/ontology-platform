/** 本轮独立栈停止/重启后的真实持久化复验；凭证只在内存，不导出认证存储。 */
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const root=resolve(process.argv[2]);
const runtimePath=resolve(process.argv[3]);
const require=createRequire(resolve(root,'apps/web/package.json'));
const {chromium}=require('@playwright/test');
const runtime=JSON.parse(await readFile(runtimePath,'utf8'));
const realm=JSON.parse(await readFile(runtime.realmFile,'utf8'));
const prior=JSON.parse(await readFile(resolve(root,'docs/evidence/G2-THIN-SLICE-001/master/full-chain-identifiers.json'),'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const checks=[];
let report;
function check(name,value){checks.push({name,status:value?'PASS':'FAIL'});if(!value)throw new Error('check_failed');}
try{
 const context=await browser.newContext();const page=await context.newPage();
 await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fanalysis');
 await page.locator('#username').fill(realm.identities['g2-operator-ab'].username);
 await page.locator('#password').fill(realm.identities['g2-operator-ab'].password);
 await page.locator('#kc-login').click();
 await page.waitForURL(url=>url.origin==='http://localhost:15100'&&url.pathname==='/analysis');
 const first=await context.request.get('http://localhost:15100/api/v1/releases/'+prior.ids.release1);
 const second=await context.request.get('http://localhost:15100/api/v1/releases/'+prior.ids.release2);
 check('persisted_formal_releases_reauthorized',first.status()===200&&second.status()===200);
 const r1=await first.json(),r2=await second.json();
 check('rollback_pointer_and_history_survive_full_stack_restart',r1.isActive&&!r2.isActive);
 const runResponse=await context.request.get('http://localhost:15100/api/v1/execution-runs/'+prior.ids.runId);
 const run=await runResponse.json();
 check('persisted_owner_run_same_snapshot_and_trace',runResponse.status()===200&&run.status==='COMPLETED'&&run.snapshot.releaseId===prior.ids.release1&&run.traceId===prior.traces[2]);
 const eventsResponse=await context.request.get('http://localhost:15100/api/v1/execution-runs/'+prior.ids.runId+'/events',{headers:{Accept:'text/event-stream'}});
 const events=(await eventsResponse.text()).split(/\r?\n/).filter(line=>line.startsWith('data:')).map(line=>JSON.parse(line.slice(5)));
 check('persisted_native_events_replay_after_restart',eventsResponse.status()===200&&events.length===run.lastSeq&&events.every((event,index)=>event.seq===index+1&&event.snapshot.releaseId===prior.ids.release1)&&events.at(-1).eventType==='run.completed');
 const csrf=await(await context.request.get('http://localhost:15100/auth/csrf')).json();
 const caps=await(await context.request.get('http://localhost:15100/api/v1/capabilities')).json();
 const query=await context.request.post('http://localhost:15100/api/v1/semantic/queries',{headers:{Origin:'http://localhost:15100','X-CSRF-TOKEN':csrf.requestToken},data:{capabilityId:'describe_ontology',capabilityVersion:caps.find(value=>value.id==='describe_ontology').version,assetId:prior.ids.assetId,releaseId:null,entityType:null,entityIri:null,externalId:null,siteId:null,relationshipIris:[],depth:1,maxRows:100,timeoutMs:5000}});
 const result=await query.json();
 check('real_s3_and_jena_persisted_bytes_graphs_match_active_r1',query.status()===200&&result.status==='FOUND'&&result.snapshot.releaseId===prior.ids.release1&&result.snapshot.ontologyHash===r1.manifest.hashes.ontologyHash&&!result.data[0].ontology.classIris.includes('urn:synthetic:live:SecondReleaseClass'));
 const drafts=await(await context.request.get('http://localhost:15100/api/v1/ontology-drafts')).json();
 check('renamed_draft_survives_full_stack_restart',drafts.some(value=>value.assetId===prior.ids.assetId&&value.name.endsWith(' renamed')));
 report={status:'PASS',checks,scope:'own just-created cold profile stopped by fail-fast and restarted with its same named PG/Keycloak/Jena/RustFS volumes; actual OIDC and unchanged full-chain identifiers',sourceSha:'fac0490528e9cc110cf99f1a41cb003b31a7852f'};
}catch(error){report={status:'FAIL',checks,category:error.name,details:'SUPPRESSED'};process.exitCode=1;}
finally{await browser.close();await writeFile(resolve(root,'docs/evidence/G2-THIN-SLICE-001/master/persistence-after-full-restart.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,checks:checks.length}));}
