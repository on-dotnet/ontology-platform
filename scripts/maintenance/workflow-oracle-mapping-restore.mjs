/** 只恢复 d368 已知的 B 到捕获的历史 A；由 Master 在同一资源窗口单次调度。 */
import { createHash, randomUUID } from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { readFile, writeFile, rename } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import * as omq from "./workflow-oracle-query-fixture.mjs";
import { approveNewMappingProposal } from "./workflow-oracle-s2.mjs";

const task = "G4-ORACLE-MAPPING-QUERY-001", run = "product-resume-01", batch = "s2-s3-01";
const root = resolve(import.meta.dirname, "../.."), area = resolve(root, "artifacts/workflow", task, run);
const qid = "query-d368ac610c7745889890e1589653af8f", sourceCommand = "5b90bb8f66fb4ddd9bfeddbe5015133a";
const stdoutHash = "d1fba9b095bec4a31831c598e4bbf7bd043579d923e57efd3403a0dab74efc15";
const scope = { organizationId: "org-demo", siteIds: ["site-a"] };
const labels = {operator:"operator-ab", auditor:"auditor-ab", activator:"operator-a", reader:"viewer-a"};
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
function check(code, ok) { if (!ok) throw Object.assign(new Error(code), {safeCode:code}); }
const read = async path => JSON.parse(await readFile(path, "utf8"));
async function atomic(path, value) {
  const candidate = path + "." + randomUUID() + ".tmp";
  await writeFile(candidate, JSON.stringify(value, null, 2) + "\n", {flag:"wx", mode:0o600});
  await rename(candidate, path);
}

function sameReceipt(a, b) {
  if (!a || !b) return false;
  // 原 stdout 使用 UTC 偏移，Mapping 规范回执使用固定七位 UTC，保留 100ns 精度。
  const normalize = r => ({...r, activatedAtUtc:r.activatedAtUtc?.replace(/\+00:00$/u, "Z")});
  return isDeepStrictEqual(normalize(a), normalize(b));
}

export async function restoreMapping(ctx) {
  const {oldA, oldB, chain, state, actors, report, get, post, command, persist} = ctx;
  const {operator, auditor, activator} = actors;
  const current = chain.receipts.at(-1)?.receipt, id = oldA.mappingId, path = "/api/v1/mappings/" + id;
  const diagnostic=ctx.diagnostic ?? null;
  const baseRevision=diagnostic ? 3 : 1;
  if (diagnostic) check("RESTORE_DIAGNOSTIC_PREFIX",chain.total===chain.receipts.length && diagnostic.history.length===3
    && isDeepStrictEqual(chain.receipts.slice(0,3),diagnostic.history) && sameReceipt(state.mappingReceipt,diagnostic.history[0].receipt)
    && sameReceipt(oldB,diagnostic.activatedB) && oldA.activationId==="activation-d2dcec9ef54c4f3bb96d60cab449580b"
    && (diagnostic.activatedA ? chain.total===5 && sameReceipt(current,diagnostic.activatedA) : chain.total===4));
  check("RESTORE_EXACT_HISTORY", sameReceipt(oldA, diagnostic ? diagnostic.history[2].receipt : state.mappingReceipt)
    && sameReceipt(oldA, chain.receipts[baseRevision-1]?.receipt) && sameReceipt(oldB, chain.receipts[baseRevision]?.receipt)
    && [baseRevision+1,baseRevision+2].includes(chain.receipts.length)
    && oldA.activationRevision===baseRevision && oldB.activationRevision===baseRevision+1 && oldB.previousReleaseId===oldA.mappingReleaseId
    && oldA.mappingReleaseId!==oldB.mappingReleaseId && oldB.mappingId===id
    && isDeepStrictEqual(chain.current,[current.activationId,current.activationRevision,current.mappingReleaseId])
    && chain.receipts.every(row => row.connection===state.connectionId && row.catalog===state.catalog.snapshotId
      && row.fingerprint===state.catalog.schemaFingerprint && row.command && row.check));
  const active = await get(activator,path+"/active");
  check("RESTORE_EXACT_ACTIVE",active.mappingId===id && active.activationRevision===current.activationRevision
    && active.mappingReleaseId===current.mappingReleaseId && active.manifestHash===current.manifestHash);
  const release = await get(operator,"/api/v1/mapping-releases/"+oldA.mappingReleaseId);
  check("RESTORE_RELEASE",release.manifestHash===oldA.manifestHash && release.manifest.mappingId===id
    && release.manifest.mappingReleaseId===oldA.mappingReleaseId && isDeepStrictEqual(release.manifest.scope,scope));
  const bProof = await get(operator,"/api/v1/mapping-proposals/"+oldB.proposalId);
  check("RESTORE_B_PROOF",sameReceipt(bProof.activation,oldB));
  let restored = current;
  if (chain.receipts.length===baseRevision+1) {
    await ctx.reserve(); // 首笔映射写前独占准确 Q 的一次归位；异常不自动重跑。
    const draft = await get(operator,path);
    check("RESTORE_DRAFT",draft.mappingId===id && draft.sourceConnectionId===state.connectionId && isDeepStrictEqual(draft.scope,scope));
    const target = {kind:"ROLLBACK",targetReleaseId:oldA.mappingReleaseId,manifestHash:oldA.manifestHash};
    let job = await post(operator,path+"/validate",{target,command:command(draft.revision)},202,'"mapping:'+draft.revision+'"');
    const jobId=job.jobId;
    check("RESTORE_JOB_ID",/^job-[a-f0-9]{32}$/u.test(jobId));
    while (["QUEUED","RUNNING"].includes(job.status)) {
      omq.stageRemaining(ctx.deadline);
      await new Promise(done=>setTimeout(done,150));
      job=await get(operator,"/api/v1/mapping-jobs/"+jobId);
      check("RESTORE_JOB_EXACT",job.jobId===jobId && job.mappingId===id && isDeepStrictEqual(job.target,target));
    }
    check("RESTORE_JOB_SUCCEEDED",job.jobId===jobId && job.mappingId===id && isDeepStrictEqual(job.target,target) && job.status==="SUCCEEDED" && /^ma-[a-f0-9]{32}$/u.test(job.assessmentId));
    const assessment=await get(operator,"/api/v1/mapping-assessments/"+job.assessmentId);
    const stages=["SCHEMA","IDENTITY","TIME_UNIT","SECURITY","EXECUTABILITY","RECONCILIATION","IMPACT"];
    check("RESTORE_ASSESSMENT",assessment.assessmentId===job.assessmentId && assessment.mappingId===id
      && assessment.binding.assessmentId===assessment.assessmentId && assessment.status==="READY_FOR_PROPOSAL"
      && isDeepStrictEqual(assessment.target,target) && isDeepStrictEqual(assessment.stages.map(row=>row.stage),stages)
      && assessment.stages.every(row=>row.status==="PASS")
      && assessment.binding.sourceConnectionId===state.connectionId && assessment.binding.sourceCatalogSnapshotId===state.catalog.snapshotId
      && assessment.binding.authorizationEpoch===report.grant.afterEpoch
      && isDeepStrictEqual(assessment.expectedActive,{releaseId:oldB.mappingReleaseId,activationRevision:oldB.activationRevision}));
    const proposal=await post(operator,path+"/proposals",{...target,schemaVersion:"g4.mapping.v1",scope:draft.scope,
      binding:assessment.binding,expectedActive:assessment.expectedActive,expiresAtUtc:assessment.expiresAtUtc,command:command()},201);
    check("RESTORE_PROPOSAL_BINDING",proposal.kind==="ROLLBACK" && proposal.targetReleaseId===target.targetReleaseId
      && proposal.manifestHash===target.manifestHash && isDeepStrictEqual(proposal.binding,assessment.binding)
      && isDeepStrictEqual(proposal.expectedActive,assessment.expectedActive) && isDeepStrictEqual(proposal.scope,scope));
    const approved=await approveNewMappingProposal({actors:{operator,auditor},check,post,command}, proposal);
    report.approved=approved;
    await persist();
    restored=await post(activator,"/api/v1/mapping-proposals/"+approved.proposalId+"/activate",
      {bindingHash:approved.bindingHash,expectedActive:approved.expectedActive,command:command(approved.proposalRevision)},200,'"proposal:'+approved.proposalRevision+'"');
  }
  check("RESTORE_A_RECEIPT",restored.kind==="ROLLBACK" && restored.mappingId===id && restored.activationRevision===oldB.activationRevision+1
    && restored.mappingReleaseId===oldA.mappingReleaseId && restored.manifestHash===oldA.manifestHash
    && restored.previousReleaseId===oldB.mappingReleaseId && new Set([oldA.activationId,oldB.activationId,restored.activationId]).size===3);
  const proposal=await get(operator,"/api/v1/mapping-proposals/"+restored.proposalId);
  const after=await get(activator,path+"/active");
  check("RESTORE_A_READBACK",sameReceipt(proposal.activation,restored) && proposal.kind==="ROLLBACK"
    && proposal.submittedBy===operator.me.subjectId && proposal.decision?.decidedBy===auditor.me.subjectId
    && after.mappingId===id && after.mappingReleaseId===oldA.mappingReleaseId && after.manifestHash===oldA.manifestHash
    && after.activationRevision===restored.activationRevision);
  report.currentReceipt=proposal.activation; report.currentActive=after;
  return proposal.activation;
}

async function main() {
  const [windowId,executionId,...extra] = process.argv.slice(2);
  const isDiagnostic=extra.length===1 && extra[0]==="--diagnostic";
  check("RESTORE_CALLER",omq.productResume && root===process.cwd() && [windowId,executionId].every(v=>/^[a-f0-9]{32}$/u.test(v)) && (!extra.length || isDiagnostic));
  const windowFile=resolve(area,batch,"window-"+windowId+".json");
  const requireOpen=async()=>{
    const win=await read(windowFile);
    check("RESTORE_WINDOW",win.id===windowId && win.state==="OPEN" && win.taskId===task && win.runId===run
      && win.batch===batch && win.plan==="s2-s3-01-runtime-01" && [40,48].includes(win.ceiling/2**30));
  };
  await requireOpen();
  const diagnostic=isDiagnostic ? omq.platform(root,"__import__('workflow_oracle_mapping_continuation').diagnostic_recovery_target(q.ROOT)",[],performance.now()+60000) : null;
  const targetCommand=diagnostic?.sourceCommand ?? sourceCommand, targetQuery=diagnostic?.queryId ?? qid, targetHash=diagnostic?.stdoutHash ?? stdoutHash;
  const stdout=await readFile(resolve(area,"../commands",run,targetCommand,"stdout.txt"));
  check("RESTORE_ORIGINAL",(diagnostic || stdout.length===5349) && sha(stdout)===targetHash);
  const rows=stdout.toString().split("\n").filter(line=>line.startsWith('{"taskId":')).map(JSON.parse);
  check("RESTORE_Q",rows.length===1 && rows[0].queryId===targetQuery && (diagnostic?.activatedA || rows[0].abaCompleted===false));
  const statePath=resolve(area,"oracle-two-table.json"), state=await read(statePath);
  const captured=diagnostic ? diagnostic.history[2].receipt : state.mappingReceipt;
  check("RESTORE_STATE",state.taskId===task && state.runId===run && state.batch===batch && isDeepStrictEqual(state.scope,scope)
    && rows[0].capturedA.activationId===captured.activationId && rows[0].capturedA.mappingReleaseId===captured.mappingReleaseId);
  const reportFile=resolve(area,batch,"mapping-recovery-"+executionId+".json");
  const report={taskId:task,runId:run,batch,windowId,executionId,queryId:targetQuery,sourceCommand:targetCommand,stdoutHash:targetHash,status:"STARTED",phases:[]};
  await writeFile(reportFile,JSON.stringify(report)+"\n",{flag:"wx",mode:0o600});
  const persist=()=>atomic(reportFile,report);
  const authDeadline=performance.now()+600000;
  let deadline=authDeadline;
  const binding=()=>({api:omq.platform(root,"q.runtime_binding()",[],deadline)});
  const origin="http://localhost:"+omq.ports.api, issuer="http://localhost:"+omq.ports.oidc;
  const actors={};
  const contexts=[];
  let browser;
  const command=(expectedRevision=0)=>({commandId:randomUUID(),idempotencyKey:randomUUID(),expectedRevision,reason:diagnostic?"Approved diagnostic mapping rollback":"Approved d368 normal mapping rollback"});
  const request=async(actor,method,path,body,status=200,etag)=>{
    check("RESTORE_API_PATH",path.startsWith("/api/v1/mapping") && !path.includes("..") && !path.includes("?"));
    const phase={method,path,startedAtUtc:new Date().toISOString(),monotonicMs:performance.now(),
      subjectId:actor.me.subjectId,commandId:body?.command?.commandId??null};
    report.phases.push(phase);
    await persist();
    try {
      await requireOpen();
      const response=await actor.context.request.fetch(origin+path,{method,data:body,maxRedirects:0,
        headers:{...actor.headers,...(etag?{"If-Match":etag}:{})},timeout:Math.min(45000,omq.stageRemaining(deadline))});
      const raw=await response.text();
      phase.status=response.status(); phase.sha256=sha(raw);
      check("RESTORE_HTTP_"+phase.status,phase.status===status);
      return JSON.parse(raw);
    } finally { phase.finishedAtUtc=new Date().toISOString();phase.elapsedMs=performance.now()-phase.monotonicMs;await persist(); }
  };
  try {
    report.hostBefore=binding();omq.checkBinding(report.hostBefore);
    const require=createRequire(resolve(root,"apps/web/package.json"));
    browser=await require("@playwright/test").chromium.launch({channel:"msedge",headless:false,timeout:60000,
      args:["--disable-background-networking","--disable-component-update"]});
    const loginWindow={deadline:null,durationMs:600000,maxDeadline:authDeadline};
    for(const [role,label] of Object.entries(labels)){
      const context=await browser.newContext({serviceWorkers:"block"});contexts.push(context);
      await context.route("**/*",route=>[origin,issuer].includes(new URL(route.request().url()).origin)?route.continue():route.abort());
      const page=await context.newPage();
      await page.goto(origin+"/auth/login?returnUrl=%2Fapi%2Fv1%2Fplatform%2Fme",{timeout:Math.min(45000,omq.stageRemaining(authDeadline))});
      const login=await omq.completeCurrentLogin(page,label,{window:loginWindow,submit:omq.submitSystemLogin});
      const headers={Origin:origin};
      const meResponse=await context.request.get(origin+"/api/v1/platform/me",{maxRedirects:0,timeout:login.remaining()});
      check("RESTORE_ME_HTTP",meResponse.status()===200);
      const me=await meResponse.json();
      check("RESTORE_SUBJECT",omq.currentProjection(label,me) && me.subjectId===state.subjects[role]);
      const csrf=await context.request.get(origin+"/auth/csrf",{maxRedirects:0,timeout:login.remaining()});
      check("RESTORE_CSRF_HTTP",csrf.status()===200);headers["X-CSRF-TOKEN"]=(await csrf.json()).requestToken;
      login.remaining();login.finish("AUTHENTICATED");
      actors[role]={me,headers,context}; // 浏览器自行保管登录票据；仅 CSRF 请求头留在内存。
    }
    deadline=performance.now()+180000;
    await requireOpen();
    report.grant=omq.s2Call(root,"grants",[omq.grantState(state),executionId,true,"s2-s3-01-runtime-01"],deadline);
    check("RESTORE_GRANT_SCOPE",report.grant.historyPreserved===true && report.grant.grantCount===6 && report.grant.fieldCount===22
      && report.grant.workflowIds.length===9 && report.grant.remainingSeconds>=report.grant.requiredSeconds);
    state.combinedGrantIds=report.grant.combinedGrantIds;state.workflowGrantIds=report.grant.workflowIds;
    await atomic(statePath,state);
    const chainRead=()=>omq.platform(root,"q.read_pg(__import__('workflow_oracle_mapping_continuation')."+(diagnostic?"extension_sql":"activation_chain_sql")+"(json.load(sys.stdin)),'s23-recovery-activation')",state.mappingReceipt.mappingId,deadline);
    const [before,cmd]=chainRead();report.chainBeforeCommand=cmd;
    const adapted= {state,diagnostic,oldA:captured,oldB:rows[0].activatedB,chain:JSON.parse(before),actors,report,deadline,
      get:(a,p)=>request(a,"GET",p),post:(a,p,body,status,etag)=>request(a,"POST",p,body,status,etag),
      command,persist,reserve:()=>writeFile(resolve(area,batch,"mapping-recovery-"+targetQuery+".once"),JSON.stringify({windowId,executionId,qid:targetQuery})+"\n",{flag:"wx",mode:0o600})};
    const receipt=await restoreMapping(adapted);
    const [after,cmdAfter]=chainRead();report.chainAfterCommand=cmdAfter;
    const readback=JSON.parse(after);
    check("RESTORE_FINAL_CHAIN",readback.receipts.length===(diagnostic ? 5 : 3) && (!diagnostic || readback.total===5) && sameReceipt(readback.receipts.at(-1).receipt,receipt)
      && isDeepStrictEqual(readback.current,[receipt.activationId,receipt.activationRevision,receipt.mappingReleaseId]));
    state.mappingCurrentReceipt=receipt;await atomic(statePath,state);
    report.hostAfter=binding();omq.checkBinding(report.hostAfter);
    check("RESTORE_HOST",omq.sameHost(report.hostBefore,report.hostAfter));
    report.status="PASS";
  } catch(error){report.status="FAIL";report.failure=error.safeCode??error.name;process.exitCode=1;}
  finally{
    for(const context of contexts) await context.close().catch(()=>{});
    await browser?.close().catch(()=>{});
    report.finishedAtUtc=new Date().toISOString();await persist();
    console.log(JSON.stringify({status:report.status,report:reportFile}));
  }
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) await main();
