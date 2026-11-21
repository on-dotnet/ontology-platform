import assert from "node:assert/strict";
import test from "node:test";
import { restoreMapping } from "../maintenance/workflow-oracle-mapping-restore.mjs";

function fixture(committed=false) {
  const operator={me:{subjectId:"operator"}},auditor={me:{subjectId:"auditor"}},activator={me:{subjectId:"activator"}};
  const scope={organizationId:"org-demo",siteIds:["site-a"]},id="m", connection="conn", catalog="cat", fingerprint="finger";
  const oldA={mappingId:id,activationId:"a1",mappingReleaseId:"A",activationRevision:1,manifestHash:"a".repeat(64),kind:"PUBLISH",proposalId:"pa"};
  const oldB={...oldA,activationId:"b",mappingReleaseId:"B",activationRevision:2,kind:"PUBLISH",proposalId:"pb",previousReleaseId:"A",manifestHash:"b".repeat(64)};
  const fresh={...oldA,activationId:"a3",activationRevision:3,kind:"ROLLBACK",previousReleaseId:"B",proposalId:"proposal-"+"e".repeat(32)};
  const target={kind:"ROLLBACK",targetReleaseId:"A",manifestHash:oldA.manifestHash};
  const job={jobId:"job-"+"1".repeat(32),status:"SUCCEEDED",assessmentId:"ma-"+"3".repeat(32),target,mappingId:id};
  const assessment={assessmentId:job.assessmentId,status:"READY_FOR_PROPOSAL",target,mappingId:id,expectedActive:{releaseId:"B",activationRevision:2},
    binding:{assessmentId:job.assessmentId,authorizationEpoch:121,sourceConnectionId:connection,sourceCatalogSnapshotId:catalog},
    stages:["SCHEMA","IDENTITY","TIME_UNIT","SECURITY","EXECUTABILITY","RECONCILIATION","IMPACT"].map(stage=>({stage,status:"PASS"})),expiresAtUtc:"unused"};
  const proposal={kind:"ROLLBACK",proposalId:fresh.proposalId,mappingId:id,status:"PENDING",submittedBy:"operator",proposalRevision:1,bindingHash:"1".repeat(64),
    ...target, binding:assessment.binding, scope, expectedActive:assessment.expectedActive};
  const approved={...proposal,status:"APPROVED",proposalRevision:2,decision:{decision:"APPROVE",decidedBy:"auditor",bindingHash:proposal.bindingHash}};
  const chain=(committed?[oldA,oldB,fresh]:[oldA,oldB]).map((receipt,i)=>({receipt,connection,catalog,fingerprint,command:"c"+i,check:"k"+i}));
  let current=chain.at(-1).receipt,reservations=0;
  const calls=[];
  const ctx={oldA,oldB,report:{grant:{afterEpoch:121}},actors:{operator,auditor,activator},deadline:performance.now()+1000,
    state:{mappingReceipt:oldA,connectionId:connection,catalog:{snapshotId:catalog,schemaFingerprint:fingerprint}},
    chain:{receipts:chain,current:[current.activationId,current.activationRevision,current.mappingReleaseId]},
    reserve:async()=>{assert.equal(reservations++,0)},persist:async()=>{},command:(revision=0)=>({expectedRevision:revision}),
    get:async(actor,path)=>{
      if(path.endsWith("/active"))return current;
      if(path==="/api/v1/mapping-releases/A")return {manifestHash:oldA.manifestHash,manifest:{mappingId:id,mappingReleaseId:"A",scope}};
      if(path==="/api/v1/mapping-proposals/pb")return {activation:oldB};
      if(path==="/api/v1/mappings/m")return {mappingId:id,sourceConnectionId:connection,scope,revision:4};
      if(path.endsWith(job.assessmentId))return assessment;
      if(path.endsWith(fresh.proposalId))return {...approved,activation:current};
      throw Error("unexpected GET "+path);
    },
    post:async(actor,path,body)=>{
      calls.push([actor.me.subjectId,path.split("/").pop()]);
      if(path.endsWith("/validate")){assert.deepEqual(body.target,target);return job;}
      if(path.endsWith("/proposals")){assert.deepEqual(body.expectedActive,assessment.expectedActive);return proposal;}
      if(path.endsWith("/decisions"))return approved;
      if(path.endsWith("/activate")){current=fresh;return fresh;}
      throw Error("unexpected POST "+path);
    }};
  return {ctx,calls,fresh,assessment};
}

test("current B verifies the original A and submits exactly one fresh rollback through the three specified roles",async()=>{
  const {ctx,calls,fresh}=fixture();
  assert.deepEqual(await restoreMapping(ctx),fresh);
  assert.deepEqual(calls,[["operator","validate"],["operator","proposals"],["auditor","decisions"],["activator","activate"]]);
});
test("committed A only reopens the original receipt",async()=>{
  const {ctx,calls,fresh}=fixture(true);
  assert.deepEqual(await restoreMapping(ctx),fresh);
  assert.deepEqual(calls,[]);
});
test("wrong B, stale assessment and non-passing stage cannot activate",async()=>{
  for(const change of ["wrongB","epoch","stage"]){
    const {ctx,calls,assessment}=fixture();
    if(change==="wrongB")ctx.chain.current=["other",2,"B"];
    if(change==="epoch")assessment.binding.authorizationEpoch--;
    if(change==="stage")assessment.stages[4].status="FAIL";
    await assert.rejects(restoreMapping(ctx),/RESTORE_(EXACT_HISTORY|ASSESSMENT)/);
    assert.deepEqual(calls,change==="wrongB"?[]:[["operator","validate"]]);
  }
});
