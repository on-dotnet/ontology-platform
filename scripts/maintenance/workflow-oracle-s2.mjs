/** 本批 Oracle 双表真实场景；所有查询和状态变化使用正式服务及准确合成夹具。 */
import { randomUUID, createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve, basename } from "node:path";
import { execFileSync } from "node:child_process";
import * as omq from "./workflow-oracle-query-fixture.mjs";
const task = "G4-ORACLE-MAPPING-QUERY-001", runId = "product-resume-01";
const capabilities = ["g4_resolve_entity", "g4_read_observations", "g4_traverse_relationships"];
const relation = "urn:synthetic:mapping:hasReading";
const hash = raw => createHash("sha256").update(raw).digest("hex");

/** 独立 Python 消费者紧接健康结果检查；完整命令与源审计在父退出后再次资格。 */
export function consume(root, report, deadline) {
  return JSON.parse(execFileSync("python3", ["-B", "scripts/maintenance/workflow_oracle_mapping_s2_contract.py"],
    {cwd:root,input:JSON.stringify(report),encoding:"utf8",timeout:Math.min(10000,omq.stageRemaining(deadline)),stdio:["pipe","pipe","pipe"]}));
}

/** 精确模式、Task/Run与完整目录未通过时，不能开始任何业务动作。 */
export async function run(ctx) {
  const {root,state,shared,report,mode,actors,check,get,post,request,save,file} = ctx;
  if (!shared || !["s2-s3-01","s2-s3-01-access-01"].includes(shared.plan.planId) || state.taskId !== task || state.runId !== runId || state.batch !== "s2-s3-01"
      || !omq.s2Plan.stages.some(s => s.mode === mode)) throw new Error("ORACLE_S2_DISPATCH");
  const deadline=shared.stageDeadline;
  const call=(method,...args)=>omq.s2Call(root,method,args,deadline);
  const s=()=>omq.grantState(state);
  const grant=call("grants",s(),shared.executionId,mode==="s2-oracle-vocabulary");
  state.combinedGrantIds=grant.combinedGrantIds; report.currentGrants=grant; await save(state);
  check("oracle_combined_grant_closure",grant.grantCount===6&&grant.fieldCount===22&&grant.historyPreserved===true);
  report.scenarioReady=call("ready",s(),Object.values(actors).map(a=>({subjectId:a.me.subjectId,cookie:a.sessionCookie})),shared.executionId,mode);
  report.oracleCases=[];report.oracleWindows=[];
  const audit=async(name,action,expectedReads)=>{
    const start=new Date().toISOString();
    const result=await action();
    const end=new Date().toISOString();
    const observed=omq.platform(root,"q.audit_window(*json.load(sys.stdin))",[start,end,null],deadline);
    report.oracleWindows.push({name,startedAtUtc:start,finishedAtUtc:end,expectedReads,audit:observed});
    check("oracle_audit_"+name,observed.clientId===null&&observed.records.length===expectedReads);
    return result;
  };
  ctx={...ctx,call,audit};
  if(mode==="s2-oracle-vocabulary") await vocabulary(ctx);
  else if(mode==="s2-oracle-mapping") await audit("formal-mapping",()=>formalMapping(ctx),formalMappingReads(state));
  else {
    report.oracleBinding={connectionId:state.connectionId,catalogSnapshotId:state.catalog.snapshotId,mappingReleaseId:state.mappingReceipt.mappingReleaseId,activation:state.mappingCurrentReceipt??state.mappingReceipt};
    const caps=await get(actors.reader,"/api/v1/capabilities");
    const query=(cap=capabilities[2],filters={})=>({assetId:state.ontologyRelease.manifest.assetId,ontologyReleaseId:state.ontologyRelease.manifest.releaseId,
      mappingReleaseIds:[state.mappingReceipt.mappingReleaseId],capabilityId:cap,capabilityVersion:caps.find(c=>c.id===cap)?.version,
      relationshipIris:cap===capabilities[2]?[relation]:[],depth:1,maxRows:100,timeoutMs:5000,filters:{siteId:"site-a",entityExternalId:"omq-entity-1",...filters}});
    const record=async(name,response,q)=>{
      const row={name,sourceCase:report.activeSourceCase??null,query:q,queryId:response.queryId,httpStatus:response.status,raw:response.raw,bytes:Buffer.byteLength(response.raw),sha256:hash(response.raw)};
      row.evidenceProofs=[];
      for(const item of response.data.evidence) {
        const proof=await request(actors.reader,"GET","/api/v1/data/source-evidence/"+encodeURIComponent(item.evidenceId));
        row.evidenceProofs.push({evidenceId:item.evidenceId,httpStatus:proof.status,raw:proof.raw,sha256:hash(proof.raw)});
      }
      report.oracleCases.push(row);return row;
    };
    const execute=async(name,q=query(),actor=actors.reader,reads=q.capabilityId===capabilities[0]?1:2)=>{
      const key=randomUUID();
      return audit(name,async()=>record(name,await request({...actor,headers:{...actor.headers,"Idempotency-Key":key}},"POST","/api/v1/data/semantic-queries",q),q),reads);
    };
    ctx={...ctx,query,record,execute};
    if(mode==="s2-oracle-queries") await queries(ctx);
    else if(mode==="s2-oracle-relations") await relations(ctx);
    else if(mode==="s2-oracle-states") await states(ctx);
    else if(mode==="s2-oracle-versions") await versions(ctx);
    else if(mode==="s2-oracle-connection") await versions(ctx,true);
    else if(mode==="s2-oracle-access") await access(ctx);
    else if(mode==="s2-oracle-aba") await aba(ctx);
    else if(mode==="s2-oracle-reopen") await reopen(ctx);
    else if(mode==="s3") await mcp(ctx);
    else if(mode==="ui-s3"||mode==="ui-s1") await ui(ctx);
    else throw new Error("ORACLE_S2_MODE");
  }
  report.semanticQualification=consume(root,report,deadline);
  check("oracle_s23_semantics_qualified",report.semanticQualification.status==="SEMANTICS_QUALIFIED");
  report.status="PASS";report.scope="ORACLE_"+mode.toUpperCase().replaceAll("-","_");
}

/** 仅补原正式根所缺的Reading和关系词汇，保存原根；不重建连接或目录。 */
async function vocabulary(ctx) {
  const {state,actors:{operator,auditor},get,post,request,command,save,report,check}=ctx;
  const reusedRelease=Boolean(state.s2VocabularyStarted && state.ontologyRelease);
  const original=state.previousOntology??state;
  const currentReply=await request(operator,"GET","/api/v1/releases/"+original.ontologyRelease.manifest.releaseId),current=currentReply.data;
  check("original_g3_release_exact",current.manifestHash===original.ontologyRelease.manifestHash);
  const text=original.ontologyDraft.sources.ontologyTurtle;
  if(text.includes("urn:synthetic:mapping:Reading")&&text.includes("urn:synthetic:mapping:hasReading")) {
    report.vocabulary={status:"REUSED",releaseId:current.manifest.releaseId,manifestHash:current.manifestHash,draft:original.ontologyDraft,assessment:original.ontologyAssessment,impact:original.ontologyImpact,approved:original.ontologyApproved,releaseRaw:currentReply.raw};return;
  }
  state.previousOntology ??= Object.fromEntries(Object.entries(state).filter(([k])=>k.startsWith("ontology")));
  if(!state.s2VocabularyStarted) {
    for(const key of Object.keys(state))if(key.startsWith("ontology"))delete state[key];
    state.s2VocabularyStarted=true;await save(state);
  }
  if(!state.ontologyDraft) {
    const sources={...state.previousOntology.ontologyDraft.sources};
    sources.ontologyTurtle+='\n<urn:synthetic:mapping:Reading> a <http://www.w3.org/2002/07/owl#Class> .\n<urn:synthetic:mapping:hasReading> a <http://www.w3.org/2002/07/owl#ObjectProperty>; <http://www.w3.org/2000/01/rdf-schema#domain> <urn:synthetic:mapping:Asset>; <http://www.w3.org/2000/01/rdf-schema#range> <urn:synthetic:mapping:Reading> .\n';
    state.ontologyDraft=await post(operator,"/api/v1/ontology-drafts",{name:"Oracle 双表关系必要词汇",scope:state.scope,sources,baseReleaseId:null,command:command()});await save(state);
  }
      const draft = state.ontologyDraft;
      if (!state.ontologyAssessment) {
        report.phase = "g3_assessment";
        state.ontologyAssessment = await post(operator, `/api/v1/ontology-drafts/${draft.draftId}/assessments`, { revision: draft.revision, hashes: draft.hashes, command: command(draft.revision) });
        check("g3_assessment_eligible", state.ontologyAssessment.publishEligible); await save(state);
      }
      if (!state.ontologyImpact) {
        report.phase = "g3_impact";
        const target = { kind: "DRAFT", id: draft.draftId, revision: draft.revision };
        state.ontologyImpact = await post(operator, "/api/v1/impact-reports", { from: target, to: target, baselineKind: "INITIAL", assessmentId: state.ontologyAssessment.assessmentId, command: command(draft.revision) });
        check("g3_impact_eligible", state.ontologyImpact.publishEligible); await save(state);
      }
      if (!state.ontologyProposal) {
        report.phase = "g3_proposal";
        state.ontologyProposal = await post(operator, "/api/v1/release-proposals", { kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision, hashes: draft.hashes,
          validationReportId: state.ontologyAssessment.validationReportId, targetReleaseId: null, targetManifestHash: null,
          impactReportId: state.ontologyImpact.reportId, impactHash: state.ontologyImpact.canonicalHash, command: command(draft.revision) }); await save(state);
      }
      if (!state.ontologyApproved) {
        report.phase = "g3_independent_review";
        const p = state.ontologyProposal;
        state.ontologyApproved = await post(auditor, `/api/v1/approvals/${p.proposalId}/decisions`, { decision: "approve", command: command(p.revision) }); await save(state);
      }
      if (!state.ontologyRelease) {
        report.phase = "g3_activate";
        const p = state.ontologyApproved;
        const receipt = await post(operator, "/api/v1/release-activations", { proposalId: p.proposalId, expectedActivationRevision: 0, expectedActiveReleaseId: null, command: command(p.revision) });
        state.ontologyRelease = await get(operator, `/api/v1/releases/${receipt.releaseId}`); await save(state);
        check("g3_formal_original", state.ontologyRelease.manifest.schemaVersion === 2 && state.ontologyRelease.manifest.artifactObjects.length === 4);
      }

  const proof=await request(operator,"GET","/api/v1/releases/"+state.ontologyRelease.manifest.releaseId);
  report.vocabulary={status:reusedRelease?"REUSED":"FRESH",releaseId:state.ontologyRelease.manifest.releaseId,manifestHash:state.ontologyRelease.manifestHash,
    draft:state.ontologyDraft,assessment:state.ontologyAssessment,impact:state.ontologyImpact,approved:state.ontologyApproved,releaseRaw:proof.raw};
}

/** 首次验证与激活重评各读两表；完整已激活链只回读平台。中断态不猜测是否仍有源工作。 */
export function formalMappingReads(state) {
  const complete = ["mappingDraft", "mappingJob", "mappingAssessment", "mappingProposal", "mappingApproved", "mappingReceipt", "mappingRelease"];
  if (complete.every(key => Boolean(state[key]))) return 0;
  if (!Object.keys(state).some(key => key.startsWith("mapping"))) return 4;
  throw Object.assign(new Error("ORACLE_S2_MAPPING_INTERRUPTED_PRESTATE"), {safeCode:"ORACLE_S2_MAPPING_INTERRUPTED_PRESTATE"});
}

/** 沿已有正式提案、异人审核和激活链构建精确双表定义。 */
async function formalMapping(ctx) {
  const {state,actors:{operator,auditor,activator,reader},get,post,request,command,save,report,check,shared}=ctx;
  const oracle=true,doris=false,twoTable=true;
      check("formal_prerequisites", Boolean(state.catalog && state.ontologyRelease));
      const sourceTable = name => oracle ? (name === "assets" ? "OMQ_ENTITY" : "OmqTarget") : doris ? (name === "assets" ? "dmq_entity" : "dmq_target") : state.numeric ? "numeric_" + name : name;
      const dataset = { snapshotId: state.catalog.snapshotId, schema: oracle ? "PRODUCTION" : doris ? "fixture" : "production", name: sourceTable("assets"), kind: "TABLE" };
      const table = state.catalog.objects.find(value => value.schema === dataset.schema && value.name === sourceTable("assets"));
      const field = input => {
        const name = oracle ? ({organization_id:"ORG_ID",site_id:"SITE_ID",asset_id:"EXT_ID",valid_from:"FROM_TS",valid_to:"TO_TS",label:"LABEL",event_at:"EVENT_TS",observed_at:"OBSERVED_TS",join_key:"JOIN_KEY"}[input] ?? input) : doris ? ({organization_id:"org_id",asset_id:"entity_id",label:"amount"}[input] ?? input) : input;
        return { datasetRef: dataset, name, ordinal: table.fields.find(value => value.name === name).ordinal };
      };
      const definition = { entities: [{ id: "asset", entityClassIri: "urn:synthetic:mapping:Asset", datasetRef: dataset,
        identitySpecId: "asset-identity", temporalSpecId: "asset-time", scopeFields: { organization: field("organization_id"), site: field("site_id") } }],
        identitySpecs: [{ id: "asset-identity", organizationFieldRef: field("organization_id"), siteFieldRef: field("site_id"), sourceNamespace: "query-fixture-v1",
          externalIdFieldRefs: [field("asset_id")], validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to") }],
        temporalSpecs: [{ id: "asset-time", eventTimeFieldRef: field("valid_from"), observedAtFieldRef: field("valid_from"),
          validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" }],
        properties: [{ id: "label", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" }],
        relations: [], conversions: [], unitSpecs: [] };
      if (oracle) {
        definition.temporalSpecs[0].eventTimeFieldRef = field("event_at");
        definition.temporalSpecs[0].observedAtFieldRef = field("observed_at");
        definition.temporalSpecs[0].timezonePolicy = {kind:"REGISTERED_ZONE", zoneId:"Etc/UTC"};
      }
      if (doris) {
        definition.properties[0] = { ...definition.properties[0], id: "amount", propertyIri:"urn:synthetic:mapping:amount", unitSpecId:"amount-k", conversionId:"amount-identity" };
        definition.unitSpecs = [{ id: "amount-k", sourceUnitIri: "urn:synthetic:m3:K-v1", targetUnitIri: "urn:synthetic:m3:K-v1",
          sourceUnitFieldRef: field("unit_code"), sourceUnitCode: "K", unitRegistryVersion: "1", evidenceKind: "SOURCE_FIELD" }];
        definition.conversions = [{ id: "amount-identity", registeredId: "identity", version: "1", parameters: {} }];
        definition.temporalSpecs[0].eventTimeFieldRef = field("event_at");
        definition.temporalSpecs[0].observedAtFieldRef = field("observed_at");
        definition.temporalSpecs[0].timezonePolicy = {kind:"REGISTERED_ZONE", zoneId:"Etc/UTC"};
      }
      if (twoTable) {
        const target = state.catalog.objects.find(t => t.name === "OmqTarget" && t.schema === "CaseOwner");
        const targetRef = { ...dataset, schema:"CaseOwner", name:"OmqTarget" };
        const col = input => { const name = ({org_id:"ORG_ID",site_id:"SITE_ID",target_id:"EXT_ID",valid_from:"FROM_TS",valid_to:"TO_TS",event_at:"EVENT_TS",observed_at:"OBSERVED_TS",join_key:"JOIN_KEY"})[input]; return {datasetRef:targetRef,name,ordinal:target.fields.find(f=>f.name===name).ordinal}; };
        definition.entities.push({id:"target",entityClassIri:"urn:synthetic:mapping:Reading",datasetRef:targetRef,
          identitySpecId:"target-key",temporalSpecId:"target-time",scopeFields:{organization:col("org_id"),site:col("site_id")}});
        definition.identitySpecs.push({id:"target-key",organizationFieldRef:col("org_id"),siteFieldRef:col("site_id"),sourceNamespace:"omq-target-v1",
          externalIdFieldRefs:[col("target_id")],validFromFieldRef:col("valid_from"),validToFieldRef:col("valid_to")});
        definition.temporalSpecs.push({id:"target-time",eventTimeFieldRef:col("event_at"),observedAtFieldRef:col("observed_at"),
          validFromFieldRef:col("valid_from"),validToFieldRef:col("valid_to"),timezonePolicy:{kind:"REGISTERED_ZONE",zoneId:"Etc/UTC"},precision:"MICROSECOND"});
        definition.relations=[{id:"targets",fromBindingId:"asset",toBindingId:"target",predicateIri:"urn:synthetic:mapping:hasReading",
          cardinality:"ONE_TO_MANY",temporalJoinPolicy:"HALF_OPEN_OVERLAP",joinFieldPairs:[{from:field("join_key"),to:col("join_key")}]}];
      }
      if (state.s3) {
      definition.properties.push({ id: "label2", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label2", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" });
      const ref = (table, name) => ({ datasetRef: { snapshotId: state.catalog.snapshotId, schema: "production", name: sourceTable(table), kind: "TABLE" },
        name, ordinal: state.catalog.objects.find(item => item.name === sourceTable(table)).fields.find(field => field.name === name).ordinal });
      definition.entities.push({ id: "reading", entityClassIri: "urn:synthetic:mapping:Reading", datasetRef: ref("readings", "reading_id").datasetRef,
        identitySpecId: "reading-identity", temporalSpecId: "reading-time", scopeFields: { organization: ref("readings", "organization_id"), site: ref("readings", "site_id") } });
      definition.identitySpecs.push({ id: "reading-identity", organizationFieldRef: ref("readings", "organization_id"), siteFieldRef: ref("readings", "site_id"), sourceNamespace: "readings",
        externalIdFieldRefs: [ref("readings", "reading_id")], validFromFieldRef: ref("readings", "valid_from"), validToFieldRef: ref("readings", "valid_to") });
      definition.temporalSpecs.push({ id: "reading-time", eventTimeFieldRef: ref("readings", "valid_from"), observedAtFieldRef: ref("readings", "observed_at"),
        validFromFieldRef: ref("readings", "valid_from"), validToFieldRef: ref("readings", "valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" });
      definition.properties.push({ id: "temperature", entityBindingId: "reading", propertyIri: "urn:synthetic:m3:reading", fieldRef: ref("readings", "temperature"), conversionId: "kelvin", unitSpecId: "temperature-unit", nullPolicy: "REJECT_NULL" },
        { id: "quality", entityBindingId: "reading", propertyIri: "urn:synthetic:mapping:quality", fieldRef: ref("readings", "attributes"), conversionId: "quality-json", unitSpecId: null, nullPolicy: "REJECT_NULL" });
      definition.unitSpecs = [{ id: "temperature-unit", sourceUnitIri: "urn:synthetic:m3:C-v1", targetUnitIri: "urn:synthetic:m3:K-v1", sourceUnitFieldRef: ref("readings", "unit_code"), sourceUnitCode: "Cel", unitRegistryVersion: "1", evidenceKind: "SOURCE_FIELD" }];
      definition.conversions = [{ id: "kelvin", registeredId: "celsius-to-kelvin", version: "1", parameters: {} }, { id: "quality-json", registeredId: "json-top-level-scalar", version: "1", parameters: { key: "quality", valueType: "STRING" } }];
      definition.relations = [{ id: "readings", fromBindingId: "asset", toBindingId: "reading", predicateIri: "urn:synthetic:mapping:hasReading", cardinality: "ONE_TO_MANY", temporalJoinPolicy: "HALF_OPEN_OVERLAP", joinFieldPairs: [{ from: ref("assets", state.numeric ? "numeric_key" : "asset_id"), to: ref("readings", state.numeric ? "numeric_key" : "asset_id") }] }];
      }
      if (!state.mappingDraft) {
        report.phase = "query_mapping_create";
        state.mappingCreate ??= { scope: state.scope, ontologyReleaseId: state.ontologyRelease.manifest.releaseId,
          ontologyManifestHash: state.ontologyRelease.manifestHash, sourceConnectionId: state.connectionId,
          sourceCatalogSnapshotId: state.catalog.snapshotId, mapping: definition, command: command() };
        await save(state);
        state.mappingDraft = await post(operator, "/api/v1/mappings", state.mappingCreate, 201); await save(state);
      }
      if (shared && state.mappingApproved) check("mapping_distinct_review_subject", state.mappingApproved.submittedBy !== state.mappingApproved.decision.decidedBy);
      const draft = state.mappingDraft, path = "/api/v1/mappings/" + draft.mappingId;
      if (!state.mappingJob) {
        report.phase = "query_mapping_validate";
        state.mappingValidation ??= { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) };
        await save(state);
        state.mappingJob = await post(operator, path + "/validate", state.mappingValidation, 202, `"mapping:${draft.revision}"`); await save(state);
      }
      if (!state.mappingAssessment) {
        report.phase = "query_mapping_wait";
        for (let attempt = 0; attempt < 60; attempt++) {
          const job = await get(operator, "/api/v1/mapping-jobs/" + state.mappingJob.jobId);
          if (job.status === "SUCCEEDED") { state.mappingAssessment = await get(operator, "/api/v1/mapping-assessments/" + job.assessmentId); break; }
          check("mapping_prerequisite_job_" + attempt, ["QUEUED", "RUNNING"].includes(job.status));
          await new Promise(done => setTimeout(done, 500));
        }
        check("mapping_prerequisite_ready", state.mappingAssessment?.status === "READY_FOR_PROPOSAL"); await save(state);
      }
      const assessment = state.mappingAssessment;
      if (!state.mappingProposal) {
        report.phase = "query_mapping_propose";
        state.mappingProposalCommand ??= { kind: "PUBLISH", schemaVersion: "g4.mapping.v1", scope: draft.scope,
          binding: assessment.binding, expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc,
          draftId: draft.draftId, draftRevision: draft.revision, command: command() }; await save(state);
        state.mappingProposal = await post(operator, path + "/proposals", state.mappingProposalCommand, 201); await save(state);
      }
      if (!state.mappingApproved) {
        report.phase = "query_mapping_independent_review";
        const proposal = state.mappingProposal;
        state.mappingDecision ??= { decision: "APPROVE", bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision) }; await save(state);
        state.mappingApproved = await post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, state.mappingDecision, 200, `"proposal:${proposal.proposalRevision}"`);
        check("mapping_distinct_review_subject", state.mappingApproved.submittedBy !== state.mappingApproved.decision.decidedBy); await save(state);
      }
      if (!state.mappingReceipt) {
        report.phase = "query_mapping_activate";
        const proposal = state.mappingApproved;
        state.mappingActivation ??= { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }; await save(state);
        state.mappingReceipt = await post(activator, `/api/v1/mapping-proposals/${proposal.proposalId}/activate`, state.mappingActivation, 200, `"proposal:${proposal.proposalRevision}"`); await save(state);
      }
      state.mappingRelease = await get(operator, "/api/v1/mapping-releases/" + state.mappingReceipt.mappingReleaseId); await save(state);
      check("query_mapping_original", state.mappingRelease.manifest.mapping.entities.length === (state.s3 || twoTable ? 2 : 1) && state.mappingRelease.manifest.mapping.entities[0].datasetRef.snapshotId === state.catalog.snapshotId);
      if (shared) {
        report.phase = "oracle_mapping_current_chain";
        const proposal = await request(auditor, "GET", "/api/v1/mapping-proposals/" + state.mappingApproved.proposalId);
        const currentRelease = await request(operator, "GET", "/api/v1/mapping-releases/" + state.mappingReceipt.mappingReleaseId);
        const active = await request(operator, "GET", "/api/v1/mappings/" + state.mappingReceipt.mappingId + "/active");
        const pr = proposal.data, rel = currentRelease.data, ar = active.data;
        check("oracle_current_mapping_independent_chain", pr.status === "APPROVED" && pr.submittedBy === operator.me.subjectId
          && pr.decision?.decidedBy === auditor.me.subjectId && pr.decision.decision === "APPROVE"
          && pr.bindingHash === pr.decision.bindingHash && pr.activation?.mappingReleaseId === state.mappingReceipt.mappingReleaseId
          && pr.activation.activationId === state.mappingReceipt.activationId && pr.activation.manifestHash === rel.manifestHash
          && ar.mappingReleaseId === pr.activation.mappingReleaseId && ar.activationRevision === pr.activation.activationRevision
          && rel.manifest.reviewReceipt.proposalId === pr.proposalId && rel.manifest.reviewReceipt.bindingHash === pr.bindingHash
          && rel.manifest.reviewReceipt.submittedBy === operator.me.subjectId && rel.manifest.reviewReceipt.decidedBy === auditor.me.subjectId);
        report.mappingQualification = { proposal: proposal.raw, release: currentRelease.raw, active: active.raw };
      }
      report.status = "PASS"; report.scope = oracle ? "ORACLE_FORMAL_TWO_TABLE_MAPPING" : "M4_QUERY_FIXED_MAPPING_PREREQUISITE_ONLY";

}

/** 独立源SQL先读固定标量，再按能力和纳秒窗口核健康/空结果。 */
async function queries(ctx) {
  const {call,report,check,execute,query,state,save,actors,root,shared}=ctx;
  const independent=call("source_snapshot");report.independentSource=independent;
  const decimal=value=>{const text=String(value),negative=text.startsWith("-"),[whole,fraction=""]=text.replace(/^-/u,"").split(".");return {coefficient:BigInt((negative?"-":"")+whole+fraction),scale:fraction.length};};
  const [parent,target]=independent.rows.map(rows=>rows[0]);
  check("independent_exact_number_coefficients",decimal(parent[2]).coefficient===9999999999999999999999999999n
    &&decimal(parent[2]).scale===6&&decimal(target[2]).coefficient===-9999999999999999999999999999n&&decimal(target[2]).scale===6);
  check("independent_source_times",parent[9]==="20260102000000123456"&&parent[10]==="20260102000001654321");
  let healthy;
  for(const [index,name] of ["healthy-resolve","healthy-observations","healthy-relations"].entries()) {
    const row=await execute(name,query(capabilities[index]));
    // 首个双表健康请求立即进入实际消费者；不把父命令尚未退出的语义检查称为完整原件资格。
    const result=JSON.parse(execFileSync("python3",["-B","-c",'import sys,json;sys.path.insert(0,"scripts/maintenance");from workflow_oracle_mapping_s2_contract import result_case; x=json.load(sys.stdin); print(json.dumps({"status":result_case(x[0],x[1])}))'],
      {cwd:root,input:JSON.stringify([row,report.oracleBinding]),encoding:"utf8",timeout:Math.min(5000,omq.stageRemaining(shared.stageDeadline)),stdio:["pipe","pipe","pipe"]}));
    check("immediate_real_consumer_"+name,result.status==="FOUND");
    if(index===2)healthy=row;
  }
  await execute("missing",query(capabilities[0],{entityExternalId:"absent-s23"}));
  const windows=[
    ["nano-before","2026-01-01T00:00:00.000000999Z","2026-01-01T00:00:00.000001000Z"],
    ["nano-start","2026-01-01T00:00:00.000000999Z","2026-01-01T00:00:00.000001001Z"],
    ["nano-end","2026-02-01T00:00:00.000000999Z","2026-02-01T00:00:00.000001001Z"],
    ["nano-after","2026-02-01T00:00:00.000001000Z","2026-02-01T00:00:00.000001001Z"]];
  for(const [name,validFrom,validTo]of windows)await execute(name,query(capabilities[0],{validFrom,validTo}));
  state.latestQuery={queryId:healthy.queryId,query:healthy.query,resultHash:healthy.sha256,raw:healthy.raw,actor:actors.reader.me.subjectId,
    sessionHash:report.scenarioReady.session.observations.find(r=>r.subjectId===actors.reader.me.subjectId).sessionHash,reportName:basename(ctx.file)};
  await save(state);
}

/** 对当前正式草稿重新评估；反例不能篡改assessment或把job失败当BLOCKED。 */
async function assess(ctx,name,issue) {
  const {state,actors:{operator},post,get,request,command,check,report,audit,shared}=ctx;
  return audit("mapping-"+name,async()=>{
    let job=await post(operator,"/api/v1/mappings/"+state.mappingDraft.mappingId+"/validate",
      {target:{kind:"PUBLISH",draftRevision:state.mappingDraft.revision},command:command(state.mappingDraft.revision)},202,'"mapping:'+state.mappingDraft.revision+'"');
    while(["QUEUED","RUNNING"].includes(job.status)) {
      omq.stageRemaining(shared.stageDeadline);await new Promise(done=>setTimeout(done,100));
      job=await get(operator,"/api/v1/mapping-jobs/"+job.jobId);
    }
    check("mapping_job_completed_"+name,job.status==="SUCCEEDED");
    const response=await request(operator,"GET","/api/v1/mapping-assessments/"+job.assessmentId),assessment=response.data;
    check("mapping_expected_"+name,assessment.status===(issue?"BLOCKED":"READY_FOR_PROPOSAL")&&(!issue||assessment.issues.some(i=>i.code===issue)));
    report.mappingCases??=[];report.mappingCases.push({name,job,assessment,raw:response.raw});return assessment;
  },2);
}

/** 关系变化依次注入、真实Query与Mapping、准确恢复；独立写者始终串行。 */
async function relations(ctx) {
  const specs=[["near",null],["negative",null],["null-parent","mapping_relation_endpoint_unknown"],["null-target","mapping_relation_endpoint_unknown"],
    ["touch",null],["micro-overlap",null],["duplicate-target","mapping_identity_overlap"],["multiple-parents","mapping_cardinality_conflict"],
    ["fanout-10",null],["fanout-11","mapping_fanout_exceeded"]];
  ctx.report.sourceCases=[];
  for(const [name,issue]of specs) {
    const changed=ctx.call("source_case",name);let restored;ctx.report.activeSourceCase={action:name,token:changed.token};
    try {await ctx.execute(name);await assess(ctx,name,issue);}
    finally {restored=ctx.call("source_case","restore",changed.token);ctx.report.sourceCases.push({name,changed,restored});delete ctx.report.activeSourceCase;}
    ctx.check("source_restored_"+name,JSON.stringify(restored.after.hashes)===JSON.stringify(changed.before.hashes));
  }
}

/** 100正常边界与唯一101反例分别记录；101不用于补跑Mapping长链。 */
async function states(ctx) {
  ctx.report.sourceCases=[];
  for(const action of ["ambiguous","normal-100","sentinel-101"]) {
    const changed=ctx.call("source_case",action);let restored;ctx.report.activeSourceCase={action,token:changed.token};
    try {
      if(action==="normal-100") {
        await ctx.execute("normal-100-selected",ctx.query(capabilities[0]));
        await ctx.execute("normal-100-all",ctx.query(capabilities[0],{entityExternalId:null}));
      } else await ctx.execute(action,ctx.query(capabilities[0],{entityExternalId:null}));
    } finally {restored=ctx.call("source_case","restore",changed.token);ctx.report.sourceCases.push({name:action,changed,restored});delete ctx.report.activeSourceCase;}
    ctx.check("source_restored_"+action,JSON.stringify(restored.after.hashes)===JSON.stringify(changed.before.hashes));
  }
}

/** 只用真正新reader会话恢复原query，逐个窗口实测零业务SELECT。 */
async function reopen(ctx) {
  const {state,actors:{reader,auditor},request,check,report,audit,call}=ctx;
  const previous=state.latestQuery;
  const session=report.scenarioReady.session.observations.find(r=>r.subjectId===reader.me.subjectId).sessionHash;
  check("s2_restore_new_reader",session!==previous.sessionHash&&reader.me.subjectId===previous.actor);
  report.oracleRestore={queryId:previous.queryId,originalHash:previous.resultHash,oldSessionHash:previous.sessionHash,newSessionHash:session,subjectId:reader.me.subjectId,originalReport:previous.reportName};
  await audit("new-reader-restore",async()=>{
    const current=await request(reader,"GET","/api/v1/data/semantic-queries/"+previous.queryId+"/result");
    check("s2_new_session_original_bytes",current.raw===previous.raw&&hash(current.raw)===previous.resultHash);
    report.oracleRestore.raw=current.raw;
    for(const item of current.data.evidence) {
      const proof=await request(reader,"GET","/api/v1/data/source-evidence/"+encodeURIComponent(item.evidenceId));
      check("s2_restored_receipt_same_query",proof.data.receipt.queryId===previous.queryId);
    }
    await request(auditor,"GET","/api/v1/data/semantic-queries/"+previous.queryId+"/result",undefined,404);
  },0);
  const mutation=call("permission_case",omq.grantState(state),"revoke","result");
  try {await audit("new-reader-revoked",()=>request(reader,"GET","/api/v1/data/semantic-queries/"+previous.queryId+"/result",undefined,403),0);}
  finally {report.restorePermission={changed:mutation,restored:call("permission_case",omq.grantState(state),"restore","result",mutation.token)};}
}

/** 同一key的MCP、HTTP与恢复工具必须返回同一query原字节，另核四工具拒绝。 */
async function mcp(ctx) {
  const {actors:{reader,auditor},rpcFor,request,query,record,audit,check,report}=ctx;
  const rpc=rpcFor(reader),denied=rpcFor(auditor),client={protocolVersion:"2025-11-25",capabilities:{},clientInfo:{name:"oracle-s23-review",version:"1"}};
  await rpc("initialize",client);await denied("initialize",client);
  const tools=(await rpc("tools/list",{})).tools.map(t=>t.name);
  const rejected=r=>r.isError===true&&!r.structuredContent&&r.content.length===1&&r.content[0].text==="semantic_tool_rejected";
  const canonical=(r,raw)=>!r.isError&&r.content.length===1&&r.content[0].text===raw&&JSON.stringify(r.structuredContent)===JSON.stringify(JSON.parse(raw));
  report.mcp=[];
  for(const cap of capabilities)await audit("mcp-"+cap,async()=>{
    check("mcp_registered_"+cap,tools.includes(cap)&&tools.includes("g4_query_result"));
    const q=query(cap),key=randomUUID(),args={query:q,idempotencyKey:key,selectionQueryId:null};
    const called=await rpc("tools/call",{name:cap,arguments:args});
    const http=await request({...reader,headers:{...reader.headers,"Idempotency-Key":key}},"POST","/api/v1/data/semantic-queries",q);
    check("mcp_http_same_query_bytes_"+cap,canonical(called,http.raw));
    const saved=await rpc("tools/call",{name:"g4_query_result",arguments:{queryId:http.queryId}});
    check("mcp_fourth_tool_original_"+cap,canonical(saved,http.raw));
    check("mcp_http_restore_original_"+cap,(await request(reader,"GET","/api/v1/data/semantic-queries/"+http.queryId+"/result")).raw===http.raw);
    const deniedExecution=await denied("tools/call",{name:cap,arguments:{...args,idempotencyKey:randomUUID()}});
    const deniedRestore=await denied("tools/call",{name:"g4_query_result",arguments:{queryId:http.queryId}});
    check("mcp_denied_execution_"+cap,rejected(deniedExecution));check("mcp_denied_restore_"+cap,rejected(deniedRestore));
    report.mcp.push({cap,queryId:http.queryId,called,saved,deniedExecution,deniedRestore});await record("mcp-"+cap,http,q);
  },cap===capabilities[0]?1:2);
}

/** Oracle页面使用viewer组合grant；当前组件真实提交、恢复、撤权和跨页身份切换。 */
async function ui(ctx) {
  const {state,actors:{operator,reader,auditor},origin,mode,check,query,record,audit,request,report,file,call,shared,progress}=ctx;
  const actor=reader;
  const region=()=>actor.page.getByRole("region",{name:"业务源查询结果",exact:true});
  if(mode==="ui-s3") {
    await operator.page.goto(origin+"/data/mappings/new");
    await operator.page.getByLabel("已启用的 PostgreSQL、Doris 或 Oracle 连接").selectOption(state.connectionId);
    await operator.page.getByLabel("完整目录快照").selectOption(state.catalog.snapshotId);
    check("oracle_mapping_editor_connection_catalog",await operator.page.getByLabel("完整目录快照").inputValue()===state.catalog.snapshotId);
  }
  await actor.page.goto(origin+"/analysis");
  await actor.page.getByRole("button",{name:"查询业务源",exact:true}).waitFor();
  for(const [label,value]of [["源查询本体资产",state.ontologyRelease.manifest.assetId],["源查询本体发布",state.ontologyRelease.manifest.releaseId],
    ["源查询映射发布",state.mappingReceipt.mappingReleaseId],["源查询外部号","omq-entity-1"]])await actor.page.getByLabel(label,{exact:true}).fill(value);
  await actor.page.getByLabel("源查询厂区",{exact:true}).selectOption("site-a");
  await actor.page.getByLabel("源查询最多返回项",{exact:true}).fill("100");
  let original;
  for(const cap of mode==="ui-s3"?capabilities:[capabilities[0]]) {
    await actor.page.getByLabel("业务源查询能力",{exact:true}).selectOption(cap);
    await actor.page.getByLabel("源查询关系路径",{exact:true}).fill(cap===capabilities[2]?relation:"");
    await audit("ui-execute-"+cap,async()=>{
      const pending=actor.page.waitForResponse(r=>r.url()===origin+"/api/v1/data/semantic-queries"&&r.request().method()==="POST");
      await actor.page.getByRole("button",{name:"查询业务源",exact:true}).click();
      const response=await pending,raw=await response.text(),queryId=response.headers()["x-query-id"];
      original={data:JSON.parse(raw),raw,status:response.status(),queryId};
      const q=response.request().postDataJSON();
      check("oracle_ui_actual_query_"+cap,q.capabilityId===cap&&q.mappingReleaseIds[0]===state.mappingReceipt.mappingReleaseId&&q.filters.entityExternalId==="omq-entity-1");
      await record(mode==="ui-s3"?"ui-"+cap:"ui-refresh",original,q);
      await region().getByRole("heading",{name:"FOUND · 找到可信结果",exact:true}).waitFor();
      check("oracle_ui_render_"+cap,(await region().innerText()).includes(cap===capabilities[2]?"hasReading":"entity"));
      check("oracle_ui_canonical_"+cap,(await request(actor,"GET","/api/v1/data/semantic-queries/"+queryId+"/result")).raw===raw);
      await region().screenshot({path:file.replace(".json","-"+cap+".png")});
    },cap===capabilities[0]?1:2);
  }
  if(mode==="ui-s1") {
    const {queryId,raw}=original,resultUrl=origin+"/api/v1/data/semantic-queries/"+queryId+"/result";
    check("oracle_ui_query_reference",new URL(actor.page.url()).searchParams.get("query")===queryId);
    await audit("ui-refresh-zero-read",async()=>{
      const response=actor.page.waitForResponse(r=>r.url()===resultUrl);
      await actor.page.reload();check("oracle_refresh_original_bytes",await(await response).text()===raw);
      await region().getByRole("heading",{name:"FOUND · 找到可信结果",exact:true}).waitFor();
    },0);
    check("oracle_ui_no_persistent_data",await actor.page.evaluate(async()=>localStorage.length===0&&sessionStorage.length===0&&(await indexedDB.databases()).length===0));
    const mutation=call("permission_case",omq.grantState(state),"revoke","result");
    try {await audit("ui-revoked-zero-read",async()=>{
      const response=actor.page.waitForResponse(r=>r.url()===resultUrl);
      await actor.page.getByRole("button",{name:"恢复查询结果",exact:true}).click();
      check("oracle_ui_revoked_403",(await response).status()===403);check("oracle_ui_revoked_clears",await region().count()===0);
    },0);}finally {report.uiPermission={changed:mutation,restored:call("permission_case",omq.grantState(state),"restore","result",mutation.token)};}
    await audit("ui-restored-zero-read",async()=>{
      const response=actor.page.waitForResponse(r=>r.url()===resultUrl);
      await actor.page.getByRole("button",{name:"恢复查询结果",exact:true}).click();
      check("oracle_ui_restored_original",await(await response).text()===raw);
    },0);
    await audit("ui-identity-late-zero-read",async()=>{
      let release,captured;
      const held=new Promise(done=>{release=done;}),ready=new Promise(done=>{captured=done;});
      await actor.page.route(resultUrl,async route=>{
        const response=await route.fetch();check("oracle_late_real_response",response.status()===200&&await response.text()===raw);
        captured();await held;await route.fulfill({response}).catch(()=>{});
      });
      let second;
      try {
        await actor.page.getByRole("button",{name:"恢复查询结果",exact:true}).click();await ready;
        second=await actor.context.newPage();await second.goto(origin+"/analysis");await second.bringToFront();
        await actor.page.waitForFunction(()=>!document.querySelector('[aria-label="业务源查询结果"]'));
        await second.getByRole("button",{name:"安全退出"}).click();await second.waitForURL(url=>url.origin===origin&&url.pathname==="/signed-out");
        await second.goto(origin+"/auth/login?returnUrl=%2Fapi%2Fv1%2Fplatform%2Fme");
        const lease=await omq.completeCurrentLogin(second,"auditor-ab",{window:{deadline:null,durationMs:180000,maxDeadline:shared.stageDeadline},signal:shared.signal,
          onProgress:event=>progress({...event,mode})});
        report.authentication??=[];report.authentication.push(lease.observation);
        actor.authDeadline=lease.deadline;
        actor.headers["X-CSRF-TOKEN"]=(await request(actor,"GET","/auth/csrf")).data.requestToken;
        const me=(await request(actor,"GET","/api/v1/platform/me")).data;
        check("oracle_ui_real_subject_changed",me.subjectId===auditor.me.subjectId&&omq.currentProjection("auditor-ab",me));
        lease.remaining();lease.finish("AUTHENTICATED");delete actor.authDeadline;
        release();await actor.page.unroute(resultUrl);await actor.page.bringToFront();
        await actor.page.waitForFunction(()=>!document.querySelector('[aria-label="恢复源查询引用"]')?.disabled);
        check("oracle_ui_late_old_subject_discarded",await region().count()===0);
        const denied=actor.page.waitForResponse(r=>r.url()===resultUrl);
        await actor.page.getByRole("button",{name:"恢复查询结果",exact:true}).click();
        check("oracle_ui_changed_subject_404",(await denied).status()===404);check("oracle_ui_rejection_cleared",await region().count()===0);
      } finally {release();await actor.page.unroute(resultUrl);await second?.close();}
    },0);
  }
  await actor.page.setViewportSize({width:390,height:844});
  await actor.page.waitForFunction(()=>document.querySelector("#platform-navigation")?.getBoundingClientRect().right<=0);
  check("oracle_ui_mobile_no_overflow",await actor.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await actor.page.getByRole("region",{name:"业务源查询",exact:true}).screenshot({path:file.replace(".json","-mobile.png")});
}

/** 当前组合grant拒绝后既不执行业务SQL，也不恢复历史原值；每次恢复核原行。 */
async function access(ctx) {
  const {actors:{reader,auditor,operator},state,execute,query,call,request,audit,check,report,command,root,shared}=ctx;
  // 当前API实例须先实际完成既有十秒连接探测；不作为Query冷启动或清理资格。
  if(shared.plan.planId==="s2-s3-01-access-01") {
  await audit("oracle-current-api-readiness",async()=>{
    const path="/api/v1/connections/"+state.connectionId, parts=[];
    const capture=async(method,url,body,etag)=>{
      const value=await request(operator,method,url,body,200,etag);
      parts.push({method,path:url,status:value.status,raw:value.raw,sha256:hash(value.raw),etag:value.etag});return value;
    };
    const before=await capture("GET",path);
    check("oracle_readiness_active",before.data.state==="ACTIVE");
    const result=await capture("POST",path+"/test",{command:command(before.data.configRevision)},before.etag);
    const after=await capture("GET",path);
    const probe=await capture("GET",path+"/probes/"+result.data.probeId);
    check("oracle_readiness_no_version_change",before.data.configRevision===after.data.configRevision&&before.data.secretVersion===after.data.secretVersion&&after.data.state==="ACTIVE");
    check("oracle_readiness_five_stages",probe.data.status==="TEST_OK"&&!probe.data.stale&&probe.data.stages.length===5&&probe.data.stages.every(s=>s.status==="PASS"));
    report.oracleReadiness={actor:operator.me.subjectId,api:report.inputBinding.api.services.api,http:parts,
      snapshot:omq.platform(root,"__import__('workflow_oracle_mapping_readiness').snapshot(*json.load(sys.stdin))",[probe.data.probeId],shared.stageDeadline)};
  },0);
  omq.platform(root,"__import__('workflow_oracle_mapping_readiness').qualify(json.load(sys.stdin))",report,shared.stageDeadline);
  }
  // 当前Reader改动须先用完整双表真实读取补证，保留历史latestQuery锚点。
  await execute("healthy-relations",query(capabilities[2]),reader,2);
  const q=query(capabilities[0]);
  await execute("no-grant",q,auditor,0);
  report.permissionCases=[];
  for(const action of ["revoke","field","expired"]) {
    const changed=call("permission_case",omq.grantState(state),action,"execute");let restored;
    try {
      if(action==="expired")report.naturalExpiry=call("await_expiry",omq.grantState(state),changed.token);
      await execute(action+"-execute",q,reader,0);
    }
    finally {restored=call("permission_case",omq.grantState(state),"restore","execute",changed.token);report.permissionCases.push({action,changed,restored});}
    check("oracle_grant_restored_"+action,call("same_grant",restored.after,changed.before));
  }
  const short=call("permission_case",omq.grantState(state),"short","execute");
  try {
    let refused=false;
    try {call("grants",omq.grantState(state),ctx.shared.executionId,false);}catch(error){refused=String(error.stderr).includes("S2_GRANT_TTL");}
    check("oracle_short_ttl_preflight_rejected",refused);
  }finally{report.shortTtl={changed:short,restored:call("permission_case",omq.grantState(state),"restore","execute",short.token)};}
  const acl=call("access_case","revoke-read");
  try {
    await execute("source-acl",q,reader,0);
    await audit("source-acl-restore-denied",()=>request(reader,"GET","/api/v1/data/semantic-queries/"+state.latestQuery.queryId+"/result",undefined,[403,503]),0);
  }finally{report.sourceAcl={changed:acl,restored:call("access_case","restore-read",acl.token)};}
  for(const kind of ["result","evidence"]) {
    const changed=call("permission_case",omq.grantState(state),"revoke",kind);
    try {await audit("denied-restore-"+kind,async()=>{
      const path=kind==="result"?"/api/v1/data/semantic-queries/"+state.latestQuery.queryId+"/result"
        :"/api/v1/data/source-evidence/"+encodeURIComponent(JSON.parse(state.latestQuery.raw).evidence[0].evidenceId);
      await request(reader,"GET",path,undefined,403);
    },0);}finally {report.permissionCases.push({kind,changed,restored:call("permission_case",omq.grantState(state),"restore",kind,changed.token)});}
  }
}

/** B先由三角色正式准备；真正同query源读后A-B-A交给已有正式DI在途测试。 */
async function aba(ctx) {
  const {state,actors:{operator,auditor,activator,reader},get,post,request,command,save,check,report,call,audit}=ctx;
  const changed=call("source_case","ambiguous");
  let selectionOrigin;report.activeSourceCase={action:"ambiguous",token:changed.token};
  try {selectionOrigin=await ctx.execute("aba-selection-origin",ctx.query(capabilities[0],{entityExternalId:null}));}
  finally {report.sourceCases=[{name:"ambiguous",changed,restored:call("source_case","restore",changed.token)}];delete report.activeSourceCase;}
  const selected={...selectionOrigin.query,filters:{...selectionOrigin.query.filters,entityIri:"urn:ontology-platform:entity:094db4805030e6f0f5038180c180302762dc9eeb602ec313fb6f92642a44231e",siteId:"site-a"}};
  const selectedRequest=()=>({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID(),"X-Selection-Query-Id":selectionOrigin.queryId}});
  await audit("aba-selection-current",async()=>ctx.record("aba-selection-current",await request(selectedRequest(),"POST","/api/v1/data/semantic-queries",selected),selected),1);
  report.historySelection={originQueryId:selectionOrigin.queryId,originHash:selectionOrigin.sha256,selected};
  const path="/api/v1/mappings/"+state.mappingDraft.mappingId;
  const baseline=await get(activator,path+"/active");
  check("oracle_aba_current_A",baseline.mappingReleaseId===state.mappingReceipt.mappingReleaseId);
  const current=await get(operator,path),mapping=structuredClone(current.mapping);
  mapping.identitySpecs[0].sourceNamespace="omq-aba-b-"+baseline.activationRevision;
  const draft=(await request(operator,"PATCH",path,{mapping,command:command(current.revision)},200,'"mapping:'+current.revision+'"')).data;
  state.mappingDraft=draft;await save(state);
  const assessment=await assess(ctx,"aba-b",null);
  const proposal=await post(operator,path+"/proposals",{kind:"PUBLISH",schemaVersion:"g4.mapping.v1",scope:draft.scope,binding:assessment.binding,
    expectedActive:assessment.expectedActive,expiresAtUtc:assessment.expiresAtUtc,draftId:draft.draftId,draftRevision:draft.revision,command:command()},201);
  const approved=await post(auditor,"/api/v1/mapping-proposals/"+proposal.proposalId+"/decisions",
    {decision:"APPROVE",bindingHash:proposal.bindingHash,command:command(proposal.proposalRevision)},200,'"proposal:'+proposal.proposalRevision+'"');
  check("oracle_aba_B_approved_distinct",approved.status==="APPROVED"&&approved.submittedBy!==approved.decision.decidedBy);
  const envelope={queryId:state.latestQuery.queryId,proposalId:approved.proposalId,
    roles:[[operator,"A"],[auditor,"B"],[activator,"C"],[reader,"Q"]].map(([actor,role])=>({role,subjectId:actor.me.subjectId,cookie:actor.sessionCookie}))};
  report.aba=await audit("inflight-activation-aba",()=>call("runtime_case", "aba",envelope),4);
  const active=await get(activator,path+"/active");
  check("oracle_aba_same_A_new_revision",active.mappingReleaseId===baseline.mappingReleaseId&&active.activationId!==baseline.activationId
    &&active.activationRevision===baseline.activationRevision+2);
  state.mappingCurrentReceipt=active;await save(state);
  await audit("aba-history-and-selection",async()=>{
    const restored=await request(reader,"GET","/api/v1/data/semantic-queries/"+selectionOrigin.queryId+"/result");
    check("oracle_aba_history_original_bytes",restored.raw===selectionOrigin.raw);
    const rejected=await request(selectedRequest(),"POST","/api/v1/data/semantic-queries",selected,409);
    check("oracle_aba_old_selection_stale",rejected.data.code==="query_binding_stale");
    report.historySelection.restoredRaw=restored.raw;report.historySelection.rejection={status:rejected.status,raw:rejected.raw};
  },0);
  report.abaDefinition={qualified:"same query after real source reads and before current-authorization transaction: formal mapping A→B→A",
    specification:"2026-11-20 clarification: one defined in-flight Mapping sequence; connection revision and historical recovery are separate AC05 cases"};
}

/** 用正式Catalog命令产生新快照；只改变目录身份，旧绑定拒绝后正式重评发布。 */
async function versions(ctx,connectionCase=false) {
  const {state,actors:{operator,reader},get,post,request,command,check,report,audit,save,query,record}=ctx;
  const path="/api/v1/connections/"+state.connectionId;
  const before=await request(operator,"GET",path);
  if(connectionCase) {
    const envelope={queryId:state.latestQuery.queryId,roles:[[ctx.actors.operator,"A"],[ctx.actors.auditor,"B"],[ctx.actors.activator,"C"],[reader,"Q"]]
      .map(([actor,role])=>({role,subjectId:actor.me.subjectId,cookie:actor.sessionCookie}))};
    report.connectionRuntime=await audit("inflight-connection-revision",()=>ctx.call("runtime_case","connection",envelope),2);
  }
  const oldQuery=query(capabilities[0]),oldCatalog=state.catalog;
  const denied=async name=>audit(name,async()=>{
    const response=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",oldQuery,409);
    check("oracle_old_binding_"+name,response.data.code==="query_binding_stale");
    report.versionRejections.push({name,status:response.status,raw:response.raw,sha256:hash(response.raw)});
  },0);
  report.versionRejections=[];
  const current=await request(operator,"GET",path);
  let job=await post(operator,path+"/discoveries",{command:command(current.data.configRevision)},202,current.etag);
  while(["QUEUED","RUNNING"].includes(job.status)) {
    omq.stageRemaining(ctx.shared.stageDeadline);await new Promise(done=>setTimeout(done,100));
    job=await get(operator,path+"/discoveries/"+job.jobId);
  }
  check("oracle_new_catalog_job",job.status==="SUCCEEDED");
  const catalog=await get(operator,"/api/v1/catalogs/"+job.snapshotId);
  check("oracle_catalog_new_identity_same_physical_fields",catalog.snapshotId!==oldCatalog.snapshotId&&catalog.schemaFingerprint===oldCatalog.schemaFingerprint
    &&JSON.stringify(catalog.objects)===JSON.stringify(oldCatalog.objects)&&catalog.configRevision===current.data.configRevision);
  check("oracle_catalog_connection_prestate",current.data.configRevision===before.data.configRevision+(connectionCase?2:0)
    &&current.data.secretVersion===before.data.secretVersion&&current.data.state==="ACTIVE");
  report.catalogVersion={before:oldCatalog,after:catalog,job,connectionBefore:before.data,connectionAfter:current.data};if(!connectionCase)await denied("catalog-new-snapshot");
  // 保存历史引用，创建当前目录下的正式双表映射；只更换本次任务自己的发布。
  state.versionHistory??=[];state.versionHistory.push({mapping:Object.fromEntries(Object.entries(state).filter(([key])=>key.startsWith("mapping"))),latestQuery:state.latestQuery,catalog:oldCatalog});
  for(const key of Object.keys(state))if(key.startsWith("mapping"))delete state[key];
  state.catalog=catalog;await save(state);
  await audit("current-catalog-mapping",()=>formalMapping(ctx),2);
  report.oracleBinding={connectionId:state.connectionId,catalogSnapshotId:catalog.snapshotId,mappingReleaseId:state.mappingReceipt.mappingReleaseId,activation:state.mappingReceipt};
  const capability=(await get(reader,"/api/v1/capabilities")).find(c=>c.id===capabilities[2]);
  const q={...oldQuery,mappingReleaseIds:[state.mappingReceipt.mappingReleaseId],capabilityId:capability.id,capabilityVersion:capability.version,relationshipIris:[relation]};
  const fresh=await audit("version-rebound-query",async()=>{
    const response=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",q);
    return record(connectionCase?"connection-rebound":"version-rebound",response,q);
  },2);
  state.latestQuery={queryId:fresh.queryId,query:q,resultHash:fresh.sha256,raw:fresh.raw,actor:reader.me.subjectId,
    sessionHash:report.scenarioReady.session.observations.find(r=>r.subjectId===reader.me.subjectId).sessionHash,reportName:basename(ctx.file)};
  report.trustSecret={status:"NOT_QUALIFIED",reason:"Read-only registry review found only secretVersion 1 in this task and no registered reversible replacement trust/secret version or rotation receipt. Old M2 rotation belongs to protected G4-M2-ORACLE-01 and cannot qualify this Mapping/Query chain."};
  await save(state);
}
