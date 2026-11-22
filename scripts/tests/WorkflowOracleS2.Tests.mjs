/** 新双表模式在真实分发边界拒绝错误身份；不启动浏览器或外部服务。 */
import {createHash} from "node:crypto";
import assert from "node:assert/strict";
import {test} from "node:test";
import {execFileSync} from "node:child_process";
import {mkdtemp,rm,readFile,writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
process.env.OMQ_PRODUCT_RUN="product-resume-01";
const omq=await import("../maintenance/workflow-oracle-query-fixture.mjs");
const {run,formalMappingReads,approveNewMappingProposal}=await import("../maintenance/workflow-oracle-s2.mjs");
const names="ROW_ID JOIN_KEY VAL ORG_ID SITE_ID EXT_ID LABEL FROM_TS TO_TS EVENT_TS OBSERVED_TS".split(" ");
const catalog={status:"READY",connectionId:"connection",objects:[["PRODUCTION","OMQ_ENTITY"],["CaseOwner","OmqTarget"]].map(([schema,name])=>({schema,name,kind:"TABLE",fields:names.map((name,i)=>({name,ordinal:i+1}))}))};
test("combined projection is exact and does not widen historical projection",()=>{
  assert.equal(omq.projection(catalog,"connection").fields.length,11);
  const combined=omq.combinedProjection(catalog,"connection");assert.equal(combined.fields.length,22);
  assert.equal(combined.fields[21],"CaseOwner/OmqTarget/11/OBSERVED_TS");
  const bad=structuredClone(catalog);bad.objects[1].fields.pop();assert.throws(()=>omq.combinedProjection(bad,"connection"));
});
test("actual dispatcher rejects task/run/mode/plan before external calls",async()=>{
  const valid={root:"/not-used",mode:"s2-oracle-queries",state:{taskId:"G4-ORACLE-MAPPING-QUERY-001",runId:"product-resume-01",batch:"s2-s3-01"},shared:{plan:omq.s2Plan},report:{},actors:{}};
  for(const bad of [{...valid,mode:"s2-doris-queries"},{...valid,shared:{plan:omq.authPlan}},
    {...valid,state:{...valid.state,taskId:"other"}},{...valid,state:{...valid.state,runId:"implementation-01"}}])await assert.rejects(run(bad),/ORACLE_S2_DISPATCH/u);
});


test("formal mapping counts both validation and activation, rejecting interrupted local state",()=>{
  assert.equal(formalMappingReads({}),4);
  const names=["mappingDraft","mappingJob","mappingAssessment","mappingProposal","mappingApproved","mappingReceipt","mappingRelease"];
  const complete=Object.fromEntries(names.map(key=>[key,{}]));assert.equal(formalMappingReads(complete),0);
  for(const name of names)assert.throws(()=>formalMappingReads({...complete,[name]:null}),/ORACLE_S2_MAPPING_INTERRUPTED_PRESTATE/u);
  assert.throws(()=>formalMappingReads({mappingJob:{status:"RUNNING"}}),/ORACLE_S2_MAPPING_INTERRUPTED_PRESTATE/u);
});


test("new suffix dispatches exactly eleven bounded slots and stops on failure",async()=>{
  const plan=omq.s2AccessPlan(),visited=[],shared={plan};let time=0;
  assert(await omq.runAuthHandoffPlan(shared,async(mode,ctx)=>{visited.push(mode);assert.equal(ctx.stageDeadline-time,ctx.stageSpec.seconds*1000);time+=1;return {status:"PASS",mode};},()=>time));
  assert.deepEqual(visited,[omq.s2Plan.stages[0],...omq.s2Plan.stages.slice(5)].map(x=>x.mode));
  assert.equal(visited.length,11);assert.equal(plan.deadlineSeconds,2520);
  const failed=[];assert.equal(await omq.runAuthHandoffPlan({plan},async mode=>{failed.push(mode);return {status:mode==="s2-oracle-access"?"FAIL":"PASS"};}),false);
  assert.deepEqual(failed,["s0-oracle-auth","s2-oracle-access"]);
});

test("current auditor approves the exact new proposal using its normal HTTP decision endpoint",async()=>{
  const operator={me:{subjectId:"operator"}},auditor={me:{subjectId:"auditor"}};
  const proposal={kind:"ROLLBACK",proposalId:"proposal-"+"1".repeat(32),mappingId:"mapping",bindingHash:"a".repeat(64),
    proposalRevision:1,submittedBy:"operator",status:"PENDING",decision:null};
  const receipt={...proposal,proposalRevision:2,status:"APPROVED",
    decision:{decision:"APPROVE",decidedBy:"auditor",bindingHash:proposal.bindingHash}};
  const calls=[];
  const ctx={actors:{operator,auditor},command:revision=>({expectedRevision:revision}),
    check:(name,ok)=>assert.ok(ok,name),post:async(...args)=>{calls.push(args);return receipt;}};
  assert.equal(await approveNewMappingProposal(ctx,proposal),receipt);
  assert.deepEqual(calls,[[auditor,"/api/v1/mapping-proposals/"+proposal.proposalId+"/decisions",
    {decision:"APPROVE",bindingHash:proposal.bindingHash,command:{expectedRevision:1}},200,'"proposal:1"']]);
  for(const invalid of [{...proposal,status:"APPROVED"},{...proposal,submittedBy:"auditor"},{...proposal,decision:receipt.decision}])
    await assert.rejects(approveNewMappingProposal(ctx,invalid),/pending_distinct_reviewer/u);
  assert.equal(calls.length,1);
  for(const invalid of [{...receipt,proposalId:"proposal-"+"2".repeat(32)},
    {...receipt,decision:{...receipt.decision,decidedBy:"previous-auditor"}},
    {...receipt,decision:{...receipt.decision,bindingHash:"b".repeat(64)}}])
    await assert.rejects(approveNewMappingProposal({...ctx,post:async()=>invalid},proposal),/decision_current_reviewer/u);
});


test("ABA and connection dispatch the current reader's healthy seed, rejecting selection and old sessions",async()=>{
  const {aba,versions}=await import("../maintenance/workflow-oracle-s2.mjs");
  const digest=x=>createHash("sha256").update(x).digest("hex");
  const actor=role=>({me:{subjectId:role},sessionCookie:"fixture-"+role,headers:{}});
  const actors=Object.fromEntries(["operator","auditor","activator","reader"].map(r=>[r,actor(r)]));
  const q=(cap="g4_traverse_relationships",f={})=>({capabilityId:cap,relationshipIris:["urn:synthetic:mapping:hasReading"],filters:{entityExternalId:"omq-entity-1",siteId:"site-a",...f}});
  const historical={queryId:"query-"+"0".repeat(32)},state={latestQuery:historical,mappingDraft:{mappingId:"m"},mappingReceipt:{mappingReleaseId:"a"}};
  const seedId="query-"+"3".repeat(32), report={scenarioReady:{session:{observations:[{subjectId:"reader",sessionHash:"a".repeat(64)}]}},oracleBinding:{mappingReleaseId:"a"}};
  const row=(name,query,id)=>{const raw=JSON.stringify({status:name.endsWith("origin")?"AMBIGUOUS":"FOUND"});return {name,query,queryId:id,raw,sha256:digest(raw),httpStatus:200};};
  const calls=[],windows=[];
  const proposal={proposalId:"proposal-"+"1".repeat(32),kind:"PUBLISH",proposalRevision:1,mappingId:"m",status:"PENDING",submittedBy:"operator",bindingHash:"b".repeat(64)};
  const ctx={state,actors,report,query:q,shared:{executionId:"run"},file:"browser-s2-oracle-aba-1000000000000.json",
    check:(k,ok)=>assert.ok(ok,k),save:async()=>{},command:()=>({}),execute:async(n,query=q())=>row(n,query,n.endsWith("origin")?"query-"+"1".repeat(32):seedId),
    record:async(n,r,query)=>row(n,query,"query-"+"2".repeat(32)),get:async(a,p)=>p.endsWith("/active")?{mappingReleaseId:"a"}:{mapping:{identitySpecs:[{}]}},
    post:async(a,p)=>p.endsWith("/validate")?{status:"SUCCEEDED",assessmentId:"ma"}:p.endsWith("/decisions")?{...proposal,proposalRevision:2,status:"APPROVED",decision:{decision:"APPROVE",decidedBy:"auditor",bindingHash:proposal.bindingHash}}:proposal,
    request:async(a,m,p)=>({data:p.includes("assessments")?{status:"READY_FOR_PROPOSAL"}:{mappingId:"m"}}),
    audit:async(n,action,count)=>{windows.push([n,count]);return action();},call:(name,...args)=>{if(name==="runtime_case"){calls.push(args);throw Error("dispatch captured");}return {token:"fixture"};}};
  const receipt=(n,kind)=>({mappingId:"m",mappingReleaseId:"a",manifestHash:"f".repeat(64),activationRevision:n,
    activationId:"activation-"+String(n).repeat(32),proposalId:"proposal-"+String(n).repeat(32),kind,
    previousReleaseId:"b",auditId:"audit",outboxEventId:"event",activatedAtUtc:"2026-11-22T00:00:00.0000000Z"});
  const before=receipt(3,"ROLLBACK"),after=receipt(5,"ROLLBACK");
  state.mappingCurrentReceipt=before;
  const summary=({mappingId,mappingReleaseId,manifestHash,activationRevision})=>({mappingId,mappingReleaseId,manifestHash,activationRevision,usable:true});
  const previousGet=ctx.get, previousRequest=ctx.request, previousCall=ctx.call;
  let completed=false, proposalRead={kind:"ROLLBACK",proposalId:after.proposalId,activation:after};
  ctx.get=async(a,p)=>p.endsWith("/active")?summary(completed?after:before):p.includes("/mapping-proposals/")?proposalRead:previousGet(a,p);
  ctx.call=(name,...args)=>{
    if(name!=="runtime_case"||args[0]!=="aba") return previousCall(name,...args);
    calls.push(args);completed=true;
    return {original:{capturedA:{...before,activationRevision:"3"},activatedA:after}};
  };
  ctx.request=async(a,m,p,...args)=>p.endsWith("/result")?{raw:'{"status":"AMBIGUOUS"}'}:
    args[1]===409?{status:409,raw:'{"code":"query_binding_stale"}',data:{code:"query_binding_stale"}}:previousRequest(a,m,p,...args);
  await aba(ctx);
  assert.deepEqual(state.mappingCurrentReceipt,after);
  assert.equal(report.historySelection.rejection.status,409);
  await assert.rejects(versions(ctx,true),/dispatch captured/);
  assert.deepEqual(calls.map(([c,e])=>[c,e.queryId]),[["aba",seedId],["connection",seedId]]);
  assert.ok(windows.some(([n,k])=>n==="inflight-activation-aba"&&k===8));
  assert.deepEqual(state.latestQuery,historical);
  for(const seed of [{...state.runtimeQuery,sessionHash:"b".repeat(64)},{...state.runtimeQuery,queryId:historical.queryId},
    {...state.runtimeQuery,query:q("g4_resolve_entity",{entityIri:"selection"})}]){
    await assert.rejects(versions({...ctx,state:{...state,runtimeQuery:seed}},true),/runtime_seed/u);
  }
  assert.equal(calls.length,2);
  for(const invalid of [{proposalId:before.proposalId,activation:after},{proposalId:after.proposalId},
    ...[{activationId:before.activationId},{activationRevision:4},{manifestHash:before.activationId}].map(fields=>({
      proposalId:after.proposalId,activation:{...after,...fields}}))]){
    completed=false;state.mappingCurrentReceipt=before;proposalRead={kind:"ROLLBACK",...invalid};
    await assert.rejects(aba(ctx),/oracle_aba_/);
    assert.equal(state.mappingCurrentReceipt,before);
  }
});


test("runtime dispatch prepares all grants after auth and reopens ready before the first product call", async t => {
  const directory=await mkdtemp(join(tmpdir(),"omq-grants-"));
  t.after(()=>rm(directory,{recursive:true,force:true}));
  const bridge=(_,method,args)=>JSON.parse(execFileSync("python3",["-B","-c",
    "import json,runpy,sys; f=runpy.run_path('scripts/tests/WorkflowOracleS2.Tests.py')['grant_bridge']; print(json.dumps(f(sys.argv[1],sys.argv[2],json.load(sys.stdin))))",
    directory,method],{input:JSON.stringify(args),encoding:"utf8",stdio:["pipe","pipe","pipe"]}));
  const st=bridge(null,"state",[]), original=structuredClone(st);
  const actors=Object.fromEntries(Object.entries(st.subjects).map(([k,v])=>[k,{me:{subjectId:v},sessionCookie:"test"}]));
  const plan=omq.s2RuntimePlan();
  const prepare=async(state,executionId)=>{
    const shared={plan,executionId};
    const report={taskId:state.taskId,runId:state.runId,mode:"s2-oracle-aba",startedAtUtc:new Date().toISOString(),
      batch:{index:1,executionId,planId:plan.planId}};
    await assert.rejects(omq.runAuthHandoffPlan(shared,async(mode,ctx)=>{
      if (mode==="s0-oracle-auth") return {mode,status:"PASS"};
      await run({mode,root:".",state,actors,report,shared:ctx,save:async()=>{},
        check:(name,ok)=>assert.ok(ok,name),get:()=>{throw Error("after ready");}},bridge);
    }),error=>{
      if (!String(error).includes("after ready")) throw error;
      return true;
    });
    report.oracleWindows=[{startedAtUtc:new Date(Date.now()+1).toISOString()}];
    assert.equal(bridge(null,"consumer",[report]),true);
    return report;
  };
  const prepared=await prepare(st,"a".repeat(32));
  assert.equal(prepared.currentGrants.issued.length,15);
  assert.equal(prepared.currentGrants.requiredSeconds,1710);
  assert.equal(prepared.scenarioReady.afterEpoch,121);
  // 模拟事务提交成功后，调用者仍持旧的状态文件。
  const wrong=structuredClone(original);
  wrong.workflowGrantIds=[...prepared.currentGrants.workflowIds].reverse();
  await assert.rejects(prepare(wrong,"b".repeat(32)),/S2_PREPARE_REGISTERED_IDS/);
  const replay=await prepare(original,"b".repeat(32));
  assert.equal(replay.currentGrants.issued.length,0);
  assert.ok(replay.currentGrants.renewal.recovery.commandId);
  assert.deepEqual(replay.currentGrants.combinedGrantIds,prepared.currentGrants.combinedGrantIds);
  for(const change of [r=>r.scenarioReady.workflowIds.reverse(),r=>r.scenarioReady.afterEpoch++,
    r=>r.currentGrants.issued[0].id="wrong"]){
    const bad=structuredClone(prepared);change(bad);
    assert.throws(()=>bridge(null,"consumer",[bad]));
  }
  const bad=structuredClone(prepared), snap=bad.scenarioReady.beforeSnapshot;
  const folder=join(directory,"artifacts","workflow",st.taskId,"commands",st.runId,snap.commandId);
  const raw=JSON.parse(await readFile(join(folder,"stdout.txt"),"utf8"));
  raw.epoch++;snap.epoch=raw.epoch;bad.scenarioReady.beforeEpoch=raw.epoch;
  const altered=JSON.stringify(raw), receipt=JSON.parse(await readFile(join(folder,"receipt.json"),"utf8"));
  receipt.stdoutSha256=createHash("sha256").update(altered).digest("hex");
  await writeFile(join(folder,"stdout.txt"),altered);await writeFile(join(folder,"receipt.json"),JSON.stringify(receipt));
  assert.throws(()=>bridge(null,"consumer",[bad]),/S2_PREPARE_DELTA/);
});

test("runtime suffix executes ten slots and ends at the first failed S2 gate",async()=>{
  const plan=omq.s2RuntimePlan(), visited=[];
  assert.deepEqual(plan.stages,omq.s2AccessPlan().stages.filter(s=>s.mode!=="s2-oracle-access"));
  assert.equal(plan.deadlineSeconds,2340);
  assert.equal(await omq.runAuthHandoffPlan({plan},async mode=>{
    visited.push(mode);return {status:mode==="s2-oracle-reopen"?"FAIL":"PASS"};
  }),false);
  assert.deepEqual(visited,plan.stages.slice(0,7).map(s=>s.mode));
});
