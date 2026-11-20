/** 真实 ready() 经其现行 stdin bridge 调用 Python。只有外部事实由离线合成夹具提供。 */
import * as omq from "../maintenance/workflow-oracle-query-fixture.mjs";
import { readFile } from "node:fs/promises";
const [root,mode]=process.argv.slice(2);
const columns="ROW_ID JOIN_KEY VAL ORG_ID SITE_ID EXT_ID LABEL FROM_TS TO_TS EVENT_TS OBSERVED_TS".split(" ");
const connectionId="4".repeat(32),snapshotId="snapshot",schemaFingerprint="d".repeat(64);
const catalog={status:"READY",connectionId,snapshotId,schemaFingerprint,objects:[["PRODUCTION","OMQ_ENTITY"],["CaseOwner","OmqTarget"]].map(([schema,name])=>({
  schema,name,kind:"TABLE",fields:columns.map((name,i)=>({name,ordinal:i+1}))}))};
const roles=["operator","auditor","activator","reader"];
const subjects=Object.fromEntries(roles.map(role=>[role,"subject-"+role]));
const actors=roles.map(role=>({me:{subjectId:subjects[role]},sessionCookie:"synthetic-session-"+role}));
const mappingReceipt={mappingId:"mapping-one",mappingReleaseId:"release-one",activationRevision:1,activationId:"activation-one",manifestHash:"a".repeat(64)};
const binding={sourceConnectionId:connectionId,sourceCatalogSnapshotId:snapshotId,sourceCatalogFingerprint:schemaFingerprint,sourceType:"ORACLE",
  connectionRevision:1,secretVersion:1,adapterVersion:"oracle-mapping-v1",executorVersion:"oracle-mapping-validator-v1",canonicalVersion:"mapping-c14n-v1"};
const state={scope:{organizationId:"org-demo",siteIds:["site-a"]},subjects,connectionId,catalog,mappingDraft:{mappingId:mappingReceipt.mappingId},
  mappingRelease:{manifest:{binding}},mappingReceipt};
async function get(actor,path) {
  if(path==="/api/v1/connections/"+connectionId)return {state:"ACTIVE",configRevision:1,secretVersion:1};
  if(path==="/api/v1/catalogs/"+snapshotId)return catalog;
  if(path==="/api/v1/mappings/mapping-one/active")return mappingReceipt;
  if(path==="/api/v1/capabilities")return [{id:"g4_resolve_entity",version:"1"}];
  throw new Error("OFFLINE_UNEXPECTED_URL");
}
try {
  // 运行受测驱动真实的模式判断、阶段和 ready 调用。省去认证前序和就绪后的业务调用。
  const driver=await readFile(new URL("../maintenance/workflow-m4-query.mjs",import.meta.url),"utf8");
  const dispatch=driver.match(/^    (if \(oracle && \(mode\.startsWith\("s0-oracle-"\).*?\n\s+phase = "oracle_scenario_ready";\n\s+const current = await omq.ready\([^\n]*?\);)/m);
  if(!dispatch)throw new Error("OFFLINE_REAL_DISPATCH_MISSING");
  const AsyncFunction=Object.getPrototypeOf(async()=>{}).constructor;
  const invoke=new AsyncFunction("oracle","mode","omq","root","state","operator","auditor","activator","reader","get","check",
    'let phase; const shared = null; '+dispatch[1]+' return current; } throw new Error("OFFLINE_MODE_NOT_DISPATCHED");');
  const {row}=await invoke(true,mode,omq,root,state,...actors,get,(name,value)=>{if(!value)throw new Error(name);});
  console.log(JSON.stringify({status:row.status,runId:row.runId,mode}));
} catch(err) {
  const code=String(err.stderr??"").match(/(?:ValueError|AssertionError): ([A-Za-z0-9_]+)(?:\s|$)/)?.[1]??"READY_REJECTED";
  console.log(JSON.stringify({status:"REJECTED",code,mode}));
}
