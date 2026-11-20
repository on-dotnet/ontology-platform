/** 新双表模式在真实分发边界拒绝错误身份；不启动浏览器或外部服务。 */
import assert from "node:assert/strict";
import {test} from "node:test";
process.env.OMQ_PRODUCT_RUN="product-resume-01";
const omq=await import("../maintenance/workflow-oracle-query-fixture.mjs");
const {run,formalMappingReads}=await import("../maintenance/workflow-oracle-s2.mjs");
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
