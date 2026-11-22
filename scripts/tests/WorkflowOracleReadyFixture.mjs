/** 真实 ready() 经其现行 stdin bridge 调用 Python。只有外部事实由离线合成夹具提供。 */
import * as omq from "../maintenance/workflow-oracle-query-fixture.mjs";
import { readFile } from "node:fs/promises";
const [root,mode]=process.argv.slice(2);
// 从浏览器驱动读取实际 request 闭包，和 ready 夹具共用源码边界。
if (mode === "catalog-http") {
  const {createHash} = await import("node:crypto");
  const {readFileSync} = await import("node:fs");
  const input = JSON.parse(readFileSync(0, "utf8"));
  const driver = await readFile(new URL("../maintenance/workflow-m4-query.mjs", import.meta.url), "utf8");
  const start = driver.indexOf("  async function request(actor,");
  const end = driver.indexOf("  const get = async ", start);
  if (start < 0 || end <= start) throw new Error("REQUEST_IMPLEMENTATION_MISSING");
  const report = {http: [], checks: []};
  const responses = input.transport;
  const actor = {me: {subjectId: input.reader}, headers: {}, context: {request: {
    async fetch(url, options) {
      const reply = responses.shift();
      if (!reply || url !== "http://fixture.invalid"+reply.path || options.method !== reply.method) {
        throw new Error("UNEXPECTED_HTTP");
      }
      return {text: async () => reply.raw, status: () => reply.status,
              headers: () => ({"x-query-id": reply.queryId})};
    }
  }}};
  const startOf = (prefix) => {
    const lines = driver.split("\n").filter(line => line.startsWith("  const "+prefix+" = "));
    if (lines.length !== 1) throw new Error("REQUEST_CLOSURE_MISSING");
    return lines[0];
  };
  const factory = new Function("origin","omq","shared","report","oracleTwoTable","mode","realm","createHash",
    startOf("stageRemaining")+"\n"+startOf("check")+"\n"+startOf("secrets")+"\n"+
    driver.slice(start,end)+"\nreturn request;");
  const request = factory("http://fixture.invalid", omq, {stageDeadline:performance.now()+5000},
    report, true, "s2-oracle-aba", null, createHash);
  const endpoint = "/api/v1/data/semantic-queries";
  await request(actor,"GET",endpoint+"/"+input.old+"/result",undefined,410);
  const posted = await request(actor,"POST",endpoint,input.query);
  const restored = await request(actor,"GET",endpoint+"/"+posted.queryId+"/result");
  if (posted.raw !== restored.raw || responses.length) throw new Error("SEED_ORIGINALS");
  process.stdout.write(JSON.stringify(report.http));
  process.exit(0);
}
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
