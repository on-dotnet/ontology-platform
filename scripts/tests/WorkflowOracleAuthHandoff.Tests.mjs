/** 调用生产 browserRun 全函数及固定批分发，仅以受控服务边界替代外部I/O。 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile as readReal } from "node:fs/promises";
import { basename, resolve } from "node:path";
import * as crypto from "node:crypto";
process.env.OMQ_PRODUCT_RUN="product-resume-01";
const real=await import("../maintenance/workflow-oracle-query-fixture.mjs");
const text=await readReal(new URL("../maintenance/workflow-m4-query.mjs",import.meta.url),"utf8");
let body=text.slice(text.indexOf("async function browserRun("),text.indexOf("/** 只向任务事件文件"));
body=body.replaceAll('await import("node:child_process")','infra').replaceAll('await import("node:fs/promises")','files');
const AsyncFunction=Object.getPrototypeOf(async()=>{}).constructor;
const load=new AsyncFunction("real","infra","files","require","readFile","resolve","basename","oracleProgress","options",`
  const root="/controlled",task="G4-ORACLE-MAPPING-QUERY-001",runId="product-resume-01",evidenceRun=runId,
    privateName="private",moduleName="q",scenarioCode="",stateName="runtime-fixture.json",port=n=>({15441:15741,15443:15743})[n]??n;
  const oracle=true,doris=false,integration=false,twoTable=false,scenario=null,dorisReadRaces={};
  const omq=real;
  ${body}
  return browserRun;
`);

async function fixture(options={}) {
  const contexts=[],events=[],records=new Map();let hostCount=0,clock=0;
  const labels=["operator-ab","auditor-ab","operator-a","viewer-a","viewer-a"];
  const receipt={proposalId:"proposal-one",manifestHash:"hash",mappingId:"mapping-one",mappingReleaseId:"release-one",activationRevision:1,activationId:"active-one"};
  const release={manifestHash:"hash",manifest:{reviewReceipt:{proposalId:"proposal-one",bindingHash:"binding",submittedBy:real.originalSubject("operator-ab"),decidedBy:real.originalSubject("auditor-ab")},mapping:{entities:[{datasetRef:{snapshotId:"snapshot"}}]}}};
  const data={status:"FOUND",data:[{kind:"entity",identity:{siteId:"site-a",externalId:"omq-entity-1"},
    properties:[{propertyIri:"urn:synthetic:mapping:label",value:{type:"string",lexical:"entity"}}]}],
    evidence:[{evidenceId:"e1",precision:"ROW_KEY",sourceRecordRef:"row"}],
    subSources:[{status:"SUCCESS",sourceReadReceiptId:"r1",watermarkKind:"UNKNOWN",watermark:null}]};
  let state={taskId:"G4-ORACLE-MAPPING-QUERY-001",runId:"product-resume-01",scope:{organizationId:"org-demo",siteIds:["site-a"]},
    subjects:Object.fromEntries(["operator","auditor","activator","reader"].map((k,i)=>[k,real.originalSubject(labels[i])])),
    connectionId:"c".repeat(32),catalog:{snapshotId:"snapshot",schemaFingerprint:"d".repeat(64),objects:[{schema:"PRODUCTION",name:"OMQ_ENTITY",fields:"ROW_ID JOIN_KEY VAL ORG_ID SITE_ID EXT_ID LABEL FROM_TS TO_TS EVENT_TS OBSERVED_TS".split(" ").map((name,i)=>({name,ordinal:i+1}))}]},
    ontologyRelease:{manifest:{assetId:"asset",releaseId:"ontology"}},mappingDraft:{mappingId:"mapping-one"},mappingJob:{},mappingAssessment:{},
    mappingProposal:{},mappingApproved:{proposalId:"proposal-one",submittedBy:"operator",decision:{decidedBy:"auditor"}},mappingReceipt:receipt,mappingRelease:release};
  const qid="query-"+"a".repeat(32);
  const me=label=>({subjectId:real.originalSubject(label),displayName:"合成开发身份 "+label,roles:[label==="auditor-ab"?"platform.auditor":label==="viewer-a"?"platform.viewer":"platform.operator"],
    scopes:(label.endsWith("-ab")?["site-a","site-b"]:["site-a"]).map(siteId=>({organizationId:"org-demo",siteId}))});
  const browser={ version:()=>"130.0",close:async()=>events.push("browserClosed"),newContext:async()=>{
    const label=labels[contexts.length],id=contexts.length+1;
    const context={id,closed:false,route:async()=>{},setDefaultTimeout:()=>{},newPage:async()=>({goto:async()=>{},label,contextId:id}),
      cookies:async()=>[{name:".OntologyPlatform.Session",value:"private-cookie-"+id,httpOnly:true,sameSite:"Lax"}],
      close:async()=>{context.closed=true;events.push("contextClosed:"+id);},request:{fetch:async(url,args)=>{
        const path=new URL(url).pathname;let status=200,value;
        events.push({id,path,timeout:args.timeout});
        if(path===options.timeoutPath)throw Object.assign(new Error(),{name:"TimeoutError"});
        if(path==="/auth/csrf")value={requestToken:"csrf"};
        else if(path==="/api/v1/platform/me")value=me(label);
        else if(path==="/api/v1/capabilities")value=[{id:"g4_resolve_entity",version:"1"}];
        else if(path==="/api/v1/mapping-releases/release-one")value=release;
        else if(path==="/api/v1/mappings/mapping-one/active")value=receipt;
        else if(path==="/api/v1/mapping-proposals/proposal-one")value={status:"APPROVED",proposalId:"proposal-one",submittedBy:real.originalSubject("operator-ab"),
          decision:{decidedBy:real.originalSubject("auditor-ab"),decision:"APPROVE",bindingHash:"binding"},bindingHash:"binding",activation:receipt};
        else if(path==="/api/v1/data/semantic-queries") {
          if(label==="auditor-ab")value={status:"UNAUTHORIZED",data:[],evidence:[]};
          else if(args.data.maxRows===99){status=409;value={};}else value=data;
        } else if(path===`/api/v1/data/semantic-queries/${qid}/result`) {
          if(label==="auditor-ab"){status=404;value={};}else value=data;
        } else if(path==="/api/v1/data/source-evidence/e1")value={schemaVersion:"g4.source-evidence.v1",receipt:{queryId:qid,mappingReleaseId:"release-one",activationId:"active-one"}};
        else throw new Error("unexpected request "+path);
        return {status:()=>status,text:async()=>JSON.stringify(value),headers:()=>({"cache-control":"no-store","x-query-id":qid})};
      }}};
    contexts.push(context);return context;
  }};
  const observations=actors=>actors.map(a=>({subjectId:a.me.subjectId,sessionHash:String(a.context.id).repeat(64),ExpiresAtUtc:"2030-01-01T00:00:00Z",requiredUntilUtc:"2027-01-01T00:00:00Z"}));
  const omq={...real,checkBinding:()=>{},sameHost:()=>true,
    completeCurrentLogin:async(page,label)=>{
      events.push("login:"+label);if(options.authFail===label)throw Object.assign(new Error(),{safeCode:"ORACLE_LOGIN_CANCELLED"});
      const deadline=performance.now()+10000;
      return {deadline,observation:{label},finish:()=>{},remaining:()=>deadline-performance.now()};
    },authSessions:(_root,actors)=>({observations:observations(actors)}),batchGrants:()=>({}),
    ready:async({actors,mode})=>({capability:{id:"g4_resolve_entity",version:"1"},row:{session:{observations:observations(actors)},mode}}),
    witness:async()=>{events.push("A");if(options.aFail)throw Object.assign(new Error(),{safeCode:"A_FAILED"});},
  };
  const files={mkdir:async()=>{},writeFile:async(path,bytes)=>{records.set(basename(path),JSON.parse(bytes));if(basename(path)==="runtime-fixture.json")state=JSON.parse(bytes);}};
  const readFile=async()=>Buffer.from(JSON.stringify(state));
  const infra={execFileSync:()=>JSON.stringify({api:{commandId:String(++hostCount)},web:null})};
  const run=await load(omq,infra,files,()=>({chromium:{launch:async()=>browser}}),readFile,resolve,basename,e=>events.push(e),options);
  const shared={browser,contexts:[],executionId:"e".repeat(32),signal:new AbortController().signal};
  return {run,shared,events,contexts,records,browser};
}

test("actual browser driver passes auth into A, S1 and new-reader restore without early finally",async()=>{
  const f=await fixture();assert(await real.runAuthHandoffPlan(f.shared,f.run),JSON.stringify(f.shared.stages));
  assert.deepEqual(f.shared.stages.map(r=>r.mode),real.authPlan.stages.map(r=>r.mode));
  assert.equal(f.contexts.length,5);assert.equal(f.shared.actors.reader.context.id,5);
  assert(f.contexts[3].closed);assert(!f.contexts[0].closed);assert(!f.events.includes("browserClosed"));
  assert.equal(f.events.filter(e=>e==="A").length,1);
  const csrf=f.events.filter(e=>e.path==="/auth/csrf");assert.equal(csrf.length,5);assert(csrf.every(e=>e.timeout<=10000));
  const recovery=[...f.records.values()].find(r=>r.mode==="s1-reopen");
  assert.equal(recovery.status,"PASS");assert.equal(recovery.oraclePersistence.sessionHash,"5".repeat(64));
  assert(!recovery.http.some(r=>r.method==="POST"));
});

for(const options of [{authFail:"operator-ab"},{authFail:"viewer-a"},{aFail:true}])test("actual driver blocks downstream "+JSON.stringify(options),async()=>{
  const f=await fixture(options);assert.equal(await real.runAuthHandoffPlan(f.shared,f.run),false);
  assert(!f.shared.stages.some(r=>r.mode==="s1"));
  if(options.authFail)assert(!f.events.includes("A"));
});

test("cancel and stage timeout cannot append an unregistered phase",async()=>{
  const controller=new AbortController();controller.abort();
  await assert.rejects(real.runAuthHandoffPlan({signal:controller.signal},()=>assert.fail("dispatched")),{safeCode:"ORACLE_LOGIN_CANCELLED"});
  let now=0,calls=0;
  assert.equal(await real.runAuthHandoffPlan({},async()=>{calls++;now+=600001;return {status:"PASS"};},()=>now),false);
  assert.equal(calls,1);
});

for(const [path,phase] of [["/auth/csrf","oidc_csrf_operator-ab"],["/api/v1/platform/me","oidc_me_operator-ab"]])test("actual identity reports bounded network failure at "+path,async()=>{
  const f=await fixture({timeoutPath:path});assert.equal(await real.runAuthHandoffPlan(f.shared,f.run),false);
  assert.deepEqual(f.shared.stages[0].failure,{phase,category:"TimeoutError",code:"ORACLE_LOGIN_SUBMITTED_TIMEOUT"});
  assert(!f.events.includes("A"));
});
