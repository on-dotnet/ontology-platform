/** 真实 OIDC/HTTP 补充验收；不启动服务，不保存凭据、SecretRef、原始响应或异常正文。 */
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, lstat, realpath } from 'node:fs/promises';
import { resolve, relative, dirname, isAbsolute, sep } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

const help = `G4-M1 real HTTP acceptance
Usage: node scripts/acceptance/g4-m1-http.mjs --runtime-file PATH --evidence-dir PATH
Uses Master private runtime.json under this checkout .tools/security:
 taskId=G4-M1-MAIN-INTEGRATION-001, runId, publicOrigin=http://localhost:15100,
 realmFile, sourceSecretFile, scope={organizationId:org-demo,siteIds:[site-a]}.
Existing realm authority must be http://localhost:15180/realms/g2-* and contain
 g2-operator-ab, g2-operator-a, g2-viewer-ab, g2-auditor-ab identities.
Optional httpScenario: baseline(default), contracts, provision, source-unavailable,
 source-permission-limited, catalog-cancel, schema-change, recover-job, credential-lifecycle, cross-org-secret.
Fault scenarios require httpConnectionId; schema-change also httpSnapshotId;
 recover-job also httpJobId. These IDs are public synthetic objects, never secrets.
Master must establish actual source/DDL/restart/permission faults beforehand.
credential-lifecycle requires expiredSecretRef, expiredSecretExpiresAtUtc (original
intake receipt), revokedSecretRef and rotationSecretFile (0600, same real private
directory as sourceSecretFile, different password). Ref values never enter evidence.
Run this source password experiment alone, with no other active source probes/jobs.
After original-password success, stdout CREDENTIAL_ROTATION_READY carries only taskId,
runId and connectionId; Master changes only fixture_reader then sends exactly
SOURCE_PASSWORD_ROTATED followed by LF. Keep stdin open. In finally, stdout
CREDENTIAL_RESTORE_READY requests restoration; reply SOURCE_PASSWORD_RESTORED plus LF.
Both markers are <=64 bytes with 30s deadlines. Master must independently restore in
finally even if either marker fails. Marker acknowledgement is not source-state proof.
After restore acknowledgement the original-password draft probe must pass; the exact
created connection is disabled using a fresh revision/ETag even when earlier work fails.
cross-org-secret requires private foreignSecretRef issued to org-demo/operator-a and
foreignSecretOwnerSubjectId from that original intake identity; /me must keep this subject.
Master temporarily moves only g2-operator-a to org-other, then restores it independently
in finally and verifies a new login. The driver logs in only that actor, requires /me
canonical operator role and actual org-other/site-a scopes, then expects the foreign
reference create to return exactly 422/connection_secret_expired. No fabricated body
organization is accepted as identity evidence. Ref provenance remains Master evidence.
ExpiresAt and HTTP 422 cannot independently prove natural expiry/unused/revoked DB
state or absence of source I/O; Master supplies those witnesses. P07/P09 stay partial.
Source is fixed pg-source:5432/fixture/fixture_reader/production, TLS VerifyFull.
Baseline creates one connection then disables it; provision deliberately leaves an
ACTIVE connection for subsequent controlled faults and reports its public IDs.
Evidence under artifacts/g4-m1-main-integration-001 or docs/evidence/G4-M1-MAIN-INTEGRATION-001 only.
Each invocation preserves a unique report. No screenshots, HAR, trace or storageState.
Exit 1=observed FAIL/runtime failure; 2=matrix still incomplete; 0=all 49 PASS.
Public HTTP cannot prove database rollback/fence/source I/O absence by itself;
untested parts remain NOT_RUN with explicit fixture requirements, never inferred PASS.`;
if (process.argv.includes('--help')) { process.stdout.write(help + '\n'); process.exit(0); }
const root = resolve(import.meta.dirname, '../..');
const groups = { C: 16, P: 14, E: 8, U: 6, R: 5 };
const matrix = Object.fromEntries(Object.entries(groups).flatMap(([prefix, count]) => Array.from({ length: count }, (_, n) => ['M1-' + prefix + String(n + 1).padStart(2, '0'), { status: 'NOT_RUN', observed: [], remaining: ['outside_executed_http_assertions'] }])));
const report = { schemaVersion: 1, taskId: 'G4-M1-MAIN-INTEGRATION-001', startedAtUtc: new Date().toISOString(), productExecution: false, matrix, checks: [], http: [], fixtures: {}, requirements: {
  'M1-P07': ['Actual other-organization identity; natural 10-minute SecretRef expiry; controlled revoked-reference witness. Invalid purpose cannot be issued through public intake.'],
  'M1-P08': ['Master scans ordinary logs, Trace, ZIP and browser storage separately; this runner only scans actual HTTP responses in memory.'],
  'M1-P09': ['Change synthetic source password and prove old physical credentials cannot be reused; version increment alone does not prove pool eviction.'],
  'M1-P14': ['Correlate denied post-disable requests with source-side absence of I/O; HTTP rejection alone does not prove no adapter call.'],
  'M1-E03': ['Source DDL plus immutable stored snapshot witness, beyond repeated equal-content fingerprint.'],
  'M1-E06': ['Hold real catalog work; persist cancel and observe Npgsql cancellation. Kill exact task API during RUNNING; restart after 30-second lease and verify fence/attempt from private platform DB.'],
  'M1-E07': ['Inject failure only into Governance audit INSERT while Connections writes remain possible; verify transaction rollback through HTTP and private task DB. Do not replace with total DB outage.'],
  'M1-E08': ['Master applies authorized no-row DDL on production.heat_event and compares old/new immutable DB snapshots with actual projected STALE read.'],
  'M1-R04': ['Separate authorized G3 actual regression entry; this driver never writes G3 or publishes releases.'],
} };
const secrets = new Set(); const contexts = []; const completedSteps = new Set();
let cleanup;
let browser, output, phase = 'configuration', responseLeakFound = false, responseScanCount = 0;
/** 固定错误码进入证据；绝不输出 Playwright 错误 message/stack。 */
/** 只从异常内存文本提取固定网络代码；原 message/stack 永不进入证据。 */
function safeFailure(error, fallback) {
  const codes = new Set(['ECONNRESET','ECONNREFUSED','ECONNABORTED','ETIMEDOUT','EPIPE','ENOTFOUND','EAI_AGAIN','ENETUNREACH','EHOSTUNREACH','ERR_SOCKET_CLOSED',
    'net::ERR_CONNECTION_RESET','net::ERR_CONNECTION_REFUSED','net::ERR_CONNECTION_CLOSED','net::ERR_CONNECTION_ABORTED','net::ERR_CONNECTION_TIMED_OUT',
    'net::ERR_TIMED_OUT','net::ERR_EMPTY_RESPONSE','net::ERR_NETWORK_CHANGED','net::ERR_ABORTED','net::ERR_FAILED','net::ERR_INVALID_RESPONSE',
    'net::ERR_SOCKET_NOT_CONNECTED','net::ERR_HTTP_RESPONSE_CODE_FAILURE','net::ERR_HTTP2_PROTOCOL_ERROR','net::ERR_INTERNET_DISCONNECTED']);
  const candidates = typeof error?.message === 'string' ? error.message.match(/\b(?:net::[A-Z_]+|E[A-Z_]+)\b/g) ?? [] : [];
  const networkCode = [error?.code, ...candidates].find(value => codes.has(value));
  const category = networkCode ? 'network' : error?.name === 'TimeoutError' ? 'timeout' : error?.name === 'TypeError' ? 'type_error' : error?.name === 'SyntaxError' ? 'invalid_json' : 'runtime';
  const code = typeof error?.safeCode === 'string' && /^[a-z0-9_]{1,80}$/.test(error.safeCode) ? error.safeCode : category === 'timeout' ? 'browser_timeout' : fallback;
  return { code, category, ...(networkCode ? { networkCode } : {}) };
}
function demand(condition, code) { if (!condition) { const error = new Error(); error.safeCode = code; throw error; } }
function remember(value) { if (typeof value === 'string' && value.length >= 8) secrets.add(value); }
function leaked(text) { return [...secrets].some(secret => text.includes(secret)); }
/** 仅排除本次专用入口明确允许返回的引用；其他已知秘密始终检查。 */
function scanResponse(raw, allowedValue) {
  const clean = ![...secrets].filter(value => value !== allowedValue).some(value => raw.includes(value));
  if (!clean) {
    responseLeakFound = true;
    observe('M1-P08', 'sensitive_value_detected_in_actual_http_response', false);
  }
  responseScanCount++;
}
function inside(base, path) { const part = relative(base, path); return !!part && part !== '..' && !part.startsWith('..' + sep) && !isAbsolute(part); }
async function rejectSymlinks(path) {
  demand(inside(root, path), 'path_outside_checkout');
  for (let cursor = path; cursor !== root; cursor = dirname(cursor)) {
    const stat = await lstat(cursor).catch(error => { if (error.code === 'ENOENT') return null; throw error; });
    demand(!stat?.isSymbolicLink(), 'symlink_denied');
  }
}
async function privateText(path) {
  demand(typeof path === 'string' && isAbsolute(path) && inside(resolve(root, '.tools/security'), path), 'private_path_denied');
  await rejectSymlinks(path); const actual = await realpath(path); const stat = await lstat(actual);
  demand(inside(resolve(root, '.tools/security'), actual) && stat.isFile() && !(stat.mode & 0o077) && stat.size < 1048576, 'private_file_denied');
  return readFile(actual, 'utf8');
}
async function prepareEvidence(path) {
  const selected = resolve(path);
  demand(['artifacts/g4-m1-main-integration-001', 'docs/evidence/G4-M1-MAIN-INTEGRATION-001'].some(base => resolve(root, base) === selected || inside(resolve(root, base), selected)), 'evidence_path_denied');
  await rejectSymlinks(selected); await mkdir(selected, { recursive: true });
  const destination = resolve(selected, 'http-' + randomUUID()); await mkdir(destination, { mode: 0o700 }); return destination;
}
function contextCommand(revision) { return { commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Synthetic G4 recovery HTTP acceptance' }; }
function observe(id, name, condition = true, facts) {
  const check = { id, name, status: condition ? 'PASS' : 'FAIL', ...(facts ? { facts } : {}) };
  report.checks.push(check); matrix[id].observed.push(name);
  if (!condition) matrix[id].status = 'FAIL';
  demand(condition, 'assertion_failed');
}
function complete(id) { if (matrix[id].status !== 'FAIL') { matrix[id].status = 'PASS'; matrix[id].remaining = []; } }
async function step(name, ids, work) {
  phase = name;
  try { await work(); }
  catch (error) {
    report.checks.push({ name, phase, status: 'FAIL', ...safeFailure(error, 'runtime_or_transport_error') });
    // 一组前置失败不把尚未执行的其他矩阵项伪标为 FAIL；保留阶段失败和候选范围。
    report.checks.at(-1).candidateMatrixIds = ids;
    return false;
  }
  completedSteps.add(name); return true;
}
/** 固定双阶段标准输入协议；不调用 Docker、数据库或任意控制文件。 */
function credentialSignal(kind, connectionId) {
  const protocol = { rotate: ['CREDENTIAL_ROTATION_READY', 'SOURCE_PASSWORD_ROTATED\n'], restore: ['CREDENTIAL_RESTORE_READY', 'SOURCE_PASSWORD_RESTORED\n'] }[kind];
  demand(!!protocol, 'credential_handshake_kind_invalid');
  const receipt = { event: protocol[0], status: 'READY', readyAtUtc: new Date().toISOString() };
  report.credentialHandshakes ??= []; report.credentialHandshakes.push(receipt);
  return new Promise((resolve, reject) => {
    // 原始输入最多驻留 64 字节，所有终止路径均清除期限和监听。
    let pending = Buffer.alloc(0); let settled = false;
    const finish = code => {
      if (settled) return; settled = true; clearTimeout(timer);
      process.stdin.removeListener('data', onData); process.stdin.removeListener('end', onEnd); process.stdin.removeListener('error', onError); process.stdin.pause();
      if (code) { receipt.status = 'FAILED'; receipt.failureCode = code; const error = new Error(); error.safeCode = code; reject(error); }
      else { receipt.status = 'MARKER_ACKNOWLEDGED'; receipt.acknowledgedAtUtc = new Date().toISOString(); resolve(); }
    };
    const onData = chunk => {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      if (pending.length + bytes.length > 64) { finish('credential_marker_too_large'); return; }
      pending = Buffer.concat([pending, bytes]); const expected = Buffer.from(protocol[1]);
      if (pending.length > expected.length || !expected.subarray(0, pending.length).equals(pending)) { finish('credential_marker_invalid'); return; }
      if (pending.equals(expected)) finish();
    };
    const onEnd = () => finish('credential_stdin_closed'); const onError = () => finish('credential_stdin_error');
    const timer = setTimeout(() => finish('credential_marker_timeout'), 30000);
    process.stdin.on('data', onData); process.stdin.on('end', onEnd); process.stdin.on('error', onError);
    try {
      // 即使输入已关闭，恢复事件仍发给 Master；其独立 finally 是恢复保底。
      process.stdout.write(JSON.stringify({ event: protocol[0], taskId: report.taskId, runId: report.runId, connectionId }) + '\n');
      if (process.stdin.readableEnded || process.stdin.destroyed) finish('credential_stdin_closed'); else process.stdin.resume();
    } catch { finish('credential_transport_error'); }
  });
}
/** 路由来自脚本常量和已验证公开ID；请求/响应正文只用于内存判断。 */
function routeTemplate(path) {
  return path.split('?')[0].replace(/[a-f0-9]{32}/g, '{id}');
}
function publicId(value) { demand(typeof value === 'string' && /^[a-f0-9]{32}$/.test(value), 'public_id_invalid'); return value; }
async function request(actor, method, path, body, options = {}) {
  demand(path.startsWith('/api/v1/') || path === '/auth/csrf' || path === '/openapi/g4.json', 'route_denied');
  const headers = { ...(method === 'GET' ? {} : actor.headers), ...options.headers, Connection: 'close' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.noCsrf) delete headers['X-CSRF-TOKEN'];
  const began = Date.now();
  const response = await actor.api.fetch('http://localhost:15100' + path, { method, data: body, headers, timeout: 30000, maxRedirects: 0 });
  const status = response.status();
  const record = { index: report.http.length, phase, method, route: routeTemplate(path), httpStatus: status, startedAtUtc: new Date(began).toISOString(), durationMs: Date.now() - began };
  report.http.push(record);
  const raw = await response.text();
  demand(raw.length < 8 * 1024 * 1024, 'response_budget_exceeded');
  // 专用 intake 的引用和 CSRF 必须先加入内存敏感集合，且从不复制进报告。
  let data; try { data = JSON.parse(raw); } catch { data = null; }
  if (path === '/auth/csrf' && status === 200) remember(data?.requestToken);
  if (path === '/api/v1/connection-secrets' && status === 201) remember(data?.secretRef);
  const allowedValue = path === '/auth/csrf' && status === 200 ? data?.requestToken : path === '/api/v1/connection-secrets' && status === 201 ? data?.secretRef : undefined;
  scanResponse(raw, allowedValue);
  if (path === '/api/v1/connection-secrets' && status === 201) {
    demand(data && Object.keys(data).sort().join(',') === 'credentialVersion,expiresAtUtc,secretRef,usageLimit', 'intake_projection_invalid');
  }
  const trace = response.headers()['x-trace-id'];
  const safeTrace = typeof trace === 'string' && /^[A-Za-z0-9:_-]{1,64}$/.test(trace) && !leaked(trace) ? trace : undefined;
  if (safeTrace) record.traceId = safeTrace;
  if (path !== '/auth/csrf' && !(path === '/api/v1/connection-secrets' && status === 201)) record.responseSha256 = createHash('sha256').update(raw).digest('hex');
  // 仅保存固定枚举的安全投影，帮助定位失败，不保存完整返回正文。
  for (const key of ['state','status']) if (typeof data?.[key] === 'string' && ['DRAFT','ACTIVE','DISABLED','RUNNING','QUEUED','SUCCEEDED','FAILED','PARTIAL','CANCELLED','TEST_OK','TEST_FAILED','READY','STALE'].includes(data[key])) record[key === 'status' ? 'businessStatus' : key] = data[key];
  if (status >= 400) {
    const code = data?.code;
    demand(typeof code === 'string' && /^[a-z0-9_]{1,64}$/.test(code), 'problem_code_invalid');
    record.code = code;
    demand(!/pg-source|fixture_reader|heat_event|Npgsql|SELECT |Password=|StackTrace/i.test(raw), 'internal_detail_in_error');
  }
  return { status, data, raw, etag: response.headers().etag, traceId: safeTrace, index: record.index, contentType: response.headers()['content-type'] };
}
function status(result, expected, code) {
  report.http[result.index].expectedStatus = expected;
  if (code) report.http[result.index].expectedCode = code;
  demand(result.status === expected && (!code || result.data?.code === code), 'unexpected_http_status_or_code'); return result.data;
}
try {
  const args=process.argv.slice(2);demand(args.length===4 && args[0]==='--runtime-file' && args[2]==='--evidence-dir','arguments_invalid');
  output=await prepareEvidence(args[3]);const runtime=JSON.parse(await privateText(resolve(args[1])));
  demand(runtime.taskId===report.taskId && runtime.runId==='final-gates-20261102-r04-final','runtime_identity_invalid');
  const realm=JSON.parse(await privateText(runtime.realmFile));
  demand(/^http:\/\/localhost:15180\/realms\/g2-[a-f0-9]+$/.test(realm.authority),'issuer_denied');
  remember(realm.clientSecret);remember(runtime.certificatePassword);remember(runtime.healthKey);
  for(const value of Object.values(realm.identities))remember(value.password);
  report.runId=runtime.runId;report.driverSha256=createHash('sha256').update(await readFile(import.meta.filename)).digest('hex');
  const require=createRequire(resolve(root,'apps/web/package.json'));const {chromium}=require('@playwright/test');
  browser=await chromium.launch({channel:'msedge',headless:true});report.productExecution=true;
  async function identity(label) {
    const previousPhase = phase;
    const identityStep = stage => { phase = 'oidc_' + (label ?? 'anonymous') + '_' + stage; };
    identityStep('context_create');
    const context = await browser.newContext({ serviceWorkers: 'block', extraHTTPHeaders: { Connection: 'close' } }); contexts.push(context);
    await context.route('**/*', route => ['http://localhost:15100','http://localhost:15180'].includes(new URL(route.request().url()).origin) ? route.continue() : route.abort());
    context.setDefaultTimeout(15000);
    const actor = { api: context.request, headers: { Connection: 'close' }, context };
    if (!label) { phase = previousPhase; return actor; }
    identityStep('user_lookup'); const user = realm.identities['g2-' + label]; demand(user?.username && user?.password, 'identity_missing');
    identityStep('page_create'); const page = await context.newPage();
    identityStep('login_navigation'); await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fauth%2Fcsrf');
    identityStep('username_input'); await page.locator('#username').fill(user.username);
    identityStep('password_input'); await page.locator('#password').fill(user.password);
    identityStep('login_submit'); await page.locator('#kc-login').click();
    identityStep('callback_navigation'); await page.waitForURL(url => url.origin === 'http://localhost:15100' && url.pathname === '/auth/csrf');
    identityStep('cookie_check'); const cookie = (await context.cookies()).find(item => item.name === '.OntologyPlatform.Session');
    demand(cookie?.httpOnly && cookie.sameSite === 'Lax', 'oidc_session_missing'); remember(cookie.value);
    identityStep('csrf_request'); const csrf = status(await request(actor, 'GET', '/auth/csrf'), 200).requestToken;
    identityStep('csrf_decode'); demand(typeof csrf === 'string', 'csrf_missing'); actor.headers = { Origin: 'http://localhost:15100', 'X-CSRF-TOKEN': csrf, Connection: 'close' };
    identityStep('page_close'); await page.close(); phase = previousPhase; return actor;
  }

  const operator=await identity('operator-ab'),auditor=await identity('auditor-ab'),viewer=await identity('viewer-ab'),foreign=await identity('operator-a'),anonymous=await identity(null);
  const check=(name,condition=true,facts)=>observe('M1-R04',name,condition,facts);
  const get=async(actor,path)=>status(await request(actor,'GET',path),200);
  const post=async(actor,path,body)=>status(await request(actor,'POST',path,body,{headers:body.command?{'If-Match':'"'+body.command.expectedRevision+'"'}:{}}),200);
  const me=await get(foreign,'/api/v1/platform/me');check('real_cross_org_identity',me.roles.includes('platform.operator')&&me.scopes.every(x=>x.organizationId==='org-other'));
  status(await request(anonymous,'GET','/api/v1/ontology-drafts'),401);check('unauthenticated_denied');
  status(await request(operator,'GET','/api/v1/connections'),404);check('G4_disabled_route_absent');
  const scope={organizationId:'org-demo',siteIds:['site-a','site-b']};
  const sources={};report.sourceFiles=[];
  for(const [key,file] of Object.entries({ontologyTurtle:'ontology.ttl',shapesTurtle:'shapes.ttl',vocabularyTurtle:'vocabulary.ttl',dataTurtle:'data.ttl'})){
    sources[key]=await readFile(resolve(root,'samples/g2',file),'utf8');report.sourceFiles.push({path:'samples/g2/'+file,sha256:createHash('sha256').update(sources[key]).digest('hex')});
  }
  const create={name:'Synthetic final gates R04 '+randomUUID().slice(0,8),scope,sources,baseReleaseId:null,command:contextCommand(0)};
  phase='security';status(await request(operator,'POST','/api/v1/ontology-drafts',create,{noCsrf:true}),403);check('csrf_denied');
  status(await request(viewer,'POST','/api/v1/ontology-drafts',create),403);check('viewer_write_denied');
  phase='draft';let draft=await post(operator,'/api/v1/ontology-drafts',create);report.drafts=[draft];
  status(await request(foreign,'GET','/api/v1/ontology-drafts/'+draft.draftId),403);check('foreign_draft_denied');
  async function proposal(d){
    phase='assessment';const assessment=await post(operator,'/api/v1/ontology-drafts/'+d.draftId+'/assessments',{revision:d.revision,hashes:d.hashes,command:contextCommand(d.revision)});
    check('actual_assessment_publish_eligible',assessment.publishEligible && assessment.hashes.bundleHash===d.hashes.bundleHash);(report.assessments??=[]).push(assessment);
    const releases=await get(operator,'/api/v1/releases');const active=releases.filter(x=>x.isActive&&x.manifest.assetId===d.assetId);demand(active.length<=1,'multiple_active');
    const target={kind:'DRAFT',id:d.draftId,revision:d.revision};
    const impact=await post(operator,'/api/v1/impact-reports',{from:active.length?{kind:'RELEASE',id:active[0].manifest.releaseId,revision:null}:target,to:target,baselineKind:active.length?'VERSION_PAIR':'INITIAL',assessmentId:assessment.assessmentId,command:contextCommand(d.revision)});
    check('impact_bound',impact.publishEligible&&impact.targetSemantics.assessmentHash===assessment.assessmentHash);(report.impacts??=[]).push(impact);
    phase='proposal';let p=await post(operator,'/api/v1/release-proposals',{kind:'PUBLISH',draftId:d.draftId,draftRevision:d.revision,hashes:d.hashes,validationReportId:assessment.validationReportId,targetReleaseId:null,targetManifestHash:null,impactReportId:impact.reportId,impactHash:impact.canonicalHash,command:contextCommand(d.revision)});
    p=await approve(p);return p;
  }
  async function approve(p){
    phase='approval';const body={decision:'approve',command:contextCommand(p.revision)};
    status(await request(operator,'POST','/api/v1/approvals/'+p.proposalId+'/decisions',body,{headers:{'If-Match':'"'+p.revision+'"'}}),403);check('self_approval_denied');
    const approved=await post(auditor,'/api/v1/approvals/'+p.proposalId+'/decisions',body);(report.proposals??=[]).push(approved);return approved;
  }
  const activate=(p,revision,id)=>post(operator,'/api/v1/release-activations',{proposalId:p.proposalId,expectedActivationRevision:revision,expectedActiveReleaseId:id,command:contextCommand(p.revision)});
  phase='publish1';const p1=await proposal(draft);const a1=await activate(p1,0,null);report.activations=[a1];
  let releases=await get(operator,'/api/v1/releases');const r1=releases.find(x=>x.isActive&&x.manifest.assetId===draft.assetId);demand(r1,'release_one_missing');report.releases=[r1];
  const capabilities=await get(operator,'/api/v1/capabilities');const cap=capabilities.find(x=>x.id==='resolve_entity');demand(cap,'resolve_capability_missing');
  const plan={capabilityId:'resolve_entity',capabilityVersion:cap.version,assetId:draft.assetId,releaseId:null,entityType:null,entityIri:null,externalId:'heat-1',siteId:'site-a',relationshipIris:[],depth:5,maxRows:100,timeoutMs:5000};
  async function query(expected, expectedLabel){
    phase='query';const result=await post(operator,'/api/v1/semantic/queries',plan);(report.queries??=[]).push(result);
    check('actual_version_specific_entity',result.data[0]?.entity?.label===expectedLabel);
    check('Jena_result_bound',result.status==='FOUND' && JSON.stringify(result.snapshot)===JSON.stringify(expected.manifest.snapshot));
    demand(result.evidence.length>0,'evidence_missing');const evidence=await get(operator,'/api/v1/evidence/'+result.evidence.find(x=>x.predicateIri==='http://www.w3.org/2000/01/rdf-schema#label').evidenceId);(report.evidence??=[]).push(evidence);
    check('evidence_same_version',evidence.releaseId===expected.manifest.releaseId && evidence.contentHash===expected.manifest.hashes.dataHash && evidence.sourceObjectKey===expected.manifest.artifactObjects.at(-1).objectKey && evidence.graphIri===expected.manifest.dataGraphIri);
    status(await request(foreign,'POST','/api/v1/semantic/queries',plan),403);check('foreign_query_denied');
    status(await request(foreign,'GET','/api/v1/evidence/'+evidence.evidenceId),403);check('foreign_evidence_denied');return result;
  }
  await query(r1,'炉次heat-1');
  phase='revision2';draft=status(await request(operator,'PUT','/api/v1/ontology-drafts/'+draft.draftId,{name:draft.name,sources:{...sources,dataTurtle:sources.dataTurtle.replaceAll('炉次heat-1','炉次heat-1-R04-v2')},command:contextCommand(draft.revision)},{headers:{'If-Match':'"'+draft.revision+'"'}}),200);report.drafts.push(draft);
  const p2=await proposal(draft);
  phase='store_fault';const docker=['--context','desktop-linux'];const name='ontology-g4-m1-main-integration-001-r04-final-rustfs-1';
  const inspect=JSON.parse(execFileSync('docker',[...docker,'inspect',name,'--format','{{json .}}'],{encoding:'utf8'}));
  demand(inspect.Config.Labels['ontology.task-id']===report.taskId&&inspect.Config.Labels['ontology.run-id']===runtime.runId&&inspect.State.Running&&!inspect.State.Paused,'fault_ownership');
  const id=inspect.Id;report.fault={containerId:id,beforeActive:r1,commands:[]};
  try{
    execFileSync('docker',[...docker,'pause',id]);report.fault.commands.push({command:['docker',...docker,'pause',id],exitCode:0});
    const failed=await request(operator,'POST','/api/v1/release-activations',{proposalId:p2.proposalId,expectedActivationRevision:a1.activationRevision,expectedActiveReleaseId:r1.manifest.releaseId,command:contextCommand(p2.revision)},{headers:{'If-Match':'"'+p2.revision+'"'}});
    status(failed,503,'artifact_store_timeout');report.fault.rejection=failed.data.code;
  }finally{execFileSync('docker',[...docker,'unpause',id]);report.fault.commands.push({command:['docker',...docker,'unpause',id],exitCode:0});}
  releases=await get(operator,'/api/v1/releases');report.fault.afterActive=releases.filter(x=>x.isActive);check('fault_active_unchanged',releases.filter(x=>x.isActive).length===1&&releases.find(x=>x.isActive).manifest.releaseId===r1.manifest.releaseId && releases.find(x=>x.isActive).manifestHash===r1.manifestHash && releases.find(x=>x.isActive).activationRevision===a1.activationRevision);
  await query(r1,'炉次heat-1');
  phase='publish2';const a2=await activate(p2,a1.activationRevision,r1.manifest.releaseId);report.activations.push(a2);
  releases=await get(operator,'/api/v1/releases');const r2=releases.find(x=>x.isActive);report.releases.push(r2);check('second_release_distinct',r2.manifest.releaseId!==r1.manifest.releaseId&&r2.manifest.hashes.bundleHash!==r1.manifest.hashes.bundleHash && r2.manifest.hashes.dataHash!==r1.manifest.hashes.dataHash);await query(r2,'炉次heat-1-R04-v2');
  phase='rollback';const rollback=await approve(await post(operator,'/api/v1/release-proposals',{kind:'ROLLBACK',draftId:null,draftRevision:null,hashes:null,validationReportId:null,targetReleaseId:r1.manifest.releaseId,targetManifestHash:r1.manifestHash,command:contextCommand(0)}));
  report.activations.push(await activate(rollback,a2.activationRevision,r2.manifest.releaseId));
  releases=await get(operator,'/api/v1/releases');const rolled=releases.find(x=>x.isActive);check('rollback_exact_complete_manifest',rolled.manifest.releaseId===r1.manifest.releaseId&&JSON.stringify(rolled.manifest)===JSON.stringify(r1.manifest));await query(r1,'炉次heat-1');
  check('activation_revisions_contiguous',report.activations.map(x=>x.activationRevision).join(',')==='1,2,3');
  report.audit=await get(auditor,'/api/v1/platform/audit?limit=100');check('real_audit_present',report.audit.length>0);complete('M1-R04');
}catch(error){report.failure={phase,...safeFailure(error,'r04_runtime_error')};}
finally{
  for(const context of contexts)await context.close().catch(()=>{});await browser?.close().catch(()=>{});
  report.completedAtUtc=new Date().toISOString();report.exitCode=report.failure||matrix['M1-R04'].status!=='PASS'?1:0;
  if(output)await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
  process.stdout.write(JSON.stringify({status:report.exitCode?'FAIL':'PASS',scope:'R04',checks:report.checks.length,failure:report.failure??null,report:output?resolve(output,'report.json'):null})+'\n');process.exitCode=report.exitCode;
}
