/** 新双表模式在真实分发边界拒绝错误身份；不启动浏览器或外部服务。 */
import assert from "node:assert/strict";
import {test} from "node:test";
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
