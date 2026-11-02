/** 真实 OIDC/HTTP 补充验收；不启动服务，不保存凭据、SecretRef、原始响应或异常正文。 */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, lstat, realpath } from 'node:fs/promises';
import { resolve, relative, dirname, isAbsolute, sep } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

const help = `G4-M1 real HTTP acceptance
Usage: node scripts/acceptance/g4-m1-http.mjs --runtime-file PATH --evidence-dir PATH
Uses Master private runtime.json under this checkout .tools/security:
 taskId=G4-M1-FINAL-GATES-001, runId, publicOrigin=http://localhost:15100,
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
Evidence under artifacts/g4-m1-final-gates-001 or docs/evidence/G4-M1-FINAL-GATES-001 only.
Each invocation preserves a unique report. No screenshots, HAR, trace or storageState.
Exit 1=observed FAIL/runtime failure; 2=matrix still incomplete; 0=all 49 PASS.
Public HTTP cannot prove database rollback/fence/source I/O absence by itself;
untested parts remain NOT_RUN with explicit fixture requirements, never inferred PASS.`;
if (process.argv.includes('--help')) { process.stdout.write(help + '\n'); process.exit(0); }
const root = resolve(import.meta.dirname, '../..');
const groups = { C: 16, P: 14, E: 8, U: 6, R: 5 };
const matrix = Object.fromEntries(Object.entries(groups).flatMap(([prefix, count]) => Array.from({ length: count }, (_, n) => ['M1-' + prefix + String(n + 1).padStart(2, '0'), { status: 'NOT_RUN', observed: [], remaining: ['outside_executed_http_assertions'] }])));
const report = { schemaVersion: 1, taskId: 'G4-M1-FINAL-GATES-001', startedAtUtc: new Date().toISOString(), productExecution: false, matrix, checks: [], http: [], fixtures: {}, requirements: {
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
  demand(['artifacts/g4-m1-final-gates-001', 'docs/evidence/G4-M1-FINAL-GATES-001'].some(base => resolve(root, base) === selected || inside(resolve(root, base), selected)), 'evidence_path_denied');
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
  const record = { index: report.http.length, phase, method, route: routeTemplate(path), status, startedAtUtc: new Date(began).toISOString(), durationMs: Date.now() - began };
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
  for (const key of ['state','status']) if (typeof data?.[key] === 'string' && ['DRAFT','ACTIVE','DISABLED','RUNNING','QUEUED','SUCCEEDED','FAILED','PARTIAL','CANCELLED','TEST_OK','TEST_FAILED','READY','STALE'].includes(data[key])) record[key] = data[key];
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
  const args = process.argv.slice(2);
  demand(args.length === 4 && args[0] === '--runtime-file' && args[2] === '--evidence-dir', 'arguments_invalid');
  output = await prepareEvidence(args[3]);
  const runtime = JSON.parse(await privateText(resolve(args[1])));
  demand(runtime.taskId === report.taskId && /^[A-Za-z0-9_-]{1,80}$/.test(runtime.runId) && runtime.publicOrigin === 'http://localhost:15100', 'runtime_identity_invalid');
  demand(runtime.scope?.organizationId === 'org-demo' && JSON.stringify(runtime.scope.siteIds) === '["site-a"]', 'synthetic_scope_required');
  const scenario = runtime.httpScenario ?? 'baseline';
  demand(['baseline','contracts','provision','source-unavailable','source-permission-limited','catalog-cancel','schema-change','recover-job','credential-lifecycle','cross-org-secret'].includes(scenario), 'scenario_invalid');
  const realm = JSON.parse(await privateText(runtime.realmFile));
  const authority = new URL(realm.authority);
  demand(authority.origin === 'http://localhost:15180' && /^\/realms\/g2-[a-f0-9]+$/.test(authority.pathname) && !authority.search && !authority.hash && !authority.username && !authority.password, 'authority_denied');
  const sourceSecret = (await privateText(runtime.sourceSecretFile)).trimEnd(); demand(sourceSecret.length >= 8, 'source_secret_invalid');
  if (scenario === 'cross-org-secret') {
    demand(typeof runtime.foreignSecretRef === 'string' && /^[a-f0-9]{32}$/.test(runtime.foreignSecretRef), 'foreign_secret_ref_invalid'); remember(runtime.foreignSecretRef);
    demand(typeof runtime.foreignSecretOwnerSubjectId === 'string' && runtime.foreignSecretOwnerSubjectId.length > 0 && runtime.foreignSecretOwnerSubjectId.length <= 255, 'foreign_secret_owner_subject_invalid');
  }
  let rotationSecret;
  if (scenario === 'credential-lifecycle') {
    demand(typeof runtime.expiredSecretRef === 'string' && /^[a-f0-9]{32}$/.test(runtime.expiredSecretRef) && typeof runtime.revokedSecretRef === 'string' && /^[a-f0-9]{32}$/.test(runtime.revokedSecretRef) && runtime.expiredSecretRef !== runtime.revokedSecretRef, 'credential_fixture_refs_invalid');
    remember(runtime.expiredSecretRef); remember(runtime.revokedSecretRef);
    const expiry = Date.parse(runtime.expiredSecretExpiresAtUtc);
    demand(typeof runtime.expiredSecretExpiresAtUtc === 'string' && Number.isFinite(expiry) && expiry <= Date.now(), 'credential_fixture_expiry_not_elapsed');
    rotationSecret = (await privateText(runtime.rotationSecretFile)).trimEnd();
    demand(dirname(await realpath(runtime.rotationSecretFile)) === dirname(await realpath(runtime.sourceSecretFile)), 'rotation_secret_directory_denied');
    demand(((await lstat(runtime.rotationSecretFile)).mode & 0o777) === 0o600, 'rotation_secret_mode_invalid');
    demand(rotationSecret.length >= 8 && rotationSecret !== sourceSecret, 'rotation_secret_not_distinct'); remember(rotationSecret);
  }
  remember(sourceSecret); remember(realm.clientSecret); remember(runtime.certificatePassword); remember(runtime.healthKey);
  for (const value of Object.values(realm.identities ?? {})) remember(value.password);
  report.runId = runtime.runId; report.scenario = scenario;
  report.driverSha256 = createHash('sha256').update(await readFile(import.meta.filename)).digest('hex');
  const require = createRequire(resolve(root, 'apps/web/package.json')); const { chromium } = require('@playwright/test');
  browser = await chromium.launch({ channel: 'msedge', headless: true }); report.productExecution = true;
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
  phase = 'oidc_operator'; const operator = await identity(scenario === 'cross-org-secret' ? 'operator-a' : 'operator-ab');
  phase = 'oidc_auditor'; const auditor = ['credential-lifecycle','cross-org-secret'].includes(scenario) ? null : await identity('auditor-ab');
  const scope = runtime.scope;
  const config = { type: 'POSTGRESQL', profile: { host: 'pg-source', port: 5432, database: 'fixture', username: 'fixture_reader', sslMode: 'VerifyFull', allowedSchemas: ['production'] } };
  report.publicSourceConfigSha256 = createHash('sha256').update(JSON.stringify(config)).digest('hex');
  const createBody = (ref, selectedScope = scope) => ({ displayName: 'G4 synthetic HTTP ' + randomUUID().slice(0,8), scopeSelection: selectedScope, config: structuredClone(config), secretRef: ref, command: contextCommand(0) });
  async function intake(value = sourceSecret, selectedScope = scope) {
    const body = { secretValue: value, scopeSelection: selectedScope, purpose: 'POSTGRESQL_READONLY', command: contextCommand(0) };
    const result = await request(operator, 'POST', '/api/v1/connection-secrets', body);
    const receipt = status(result, 201); demand(typeof receipt.secretRef === 'string' && receipt.usageLimit === 1 && receipt.credentialVersion === 1, 'intake_receipt_invalid');
    return { ref: receipt.secretRef, body, receipt };
  }
  async function auditRows() { const rows = status(await request(auditor, 'GET', '/api/v1/platform/audit?limit=100'), 200); demand(Array.isArray(rows), 'audit_shape_invalid'); return rows; }
  async function current(id) { const result = await request(operator, 'GET', '/api/v1/connections/' + publicId(id)); status(result, 200); demand(/^"[1-9][0-9]*-[a-f0-9]{64}"$/.test(result.etag), 'etag_invalid'); return result; }
  async function mutate(id, action, body, before) { return request(operator, action === '' ? 'PATCH' : 'POST', '/api/v1/connections/' + publicId(id) + (action ? '/' + action : ''), body, { headers: { 'If-Match': before.etag } }); }
  async function probe(id) {
    const before = await current(id); const body = { command: contextCommand(before.data.configRevision) }; const response = await mutate(id, 'test', body, before); const value = status(response, 200);
    publicId(value.probeId); demand(value.connectionId === id, 'probe_connection_mismatch');
    return { response, value, body, before };
  }
  function successfulProbe(value) { return value.status === 'TEST_OK' && value.stages.length === 5 && ['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].every(name => value.stages.some(stage => stage.name === name && stage.status === 'PASS' && stage.durationMs >= 0)); }
  async function terminal(id, jobId) {
    for (let attempt = 0; attempt < 35; attempt++) {
      const value = status(await request(operator, 'GET', '/api/v1/connections/' + publicId(id) + '/discoveries/' + publicId(jobId)), 200);
      if (!['QUEUED','RUNNING'].includes(value.status)) return value;
      await new Promise(done => setTimeout(done, 1000));
    }
    demand(false, 'job_terminal_timeout');
  }
  async function startDiscovery(id) {
    const before = await current(id); const body = { command: contextCommand(before.data.configRevision) };
    const response = await mutate(id, 'discoveries', body, before); const job = status(response, 202); publicId(job.jobId);
    return { before, body, response, job };
  }
  async function discover(id) {
    const start = await startDiscovery(id); const job = await terminal(id, start.job.jobId); demand(job.status === 'SUCCEEDED', 'catalog_not_succeeded'); publicId(job.snapshotId);
    const snapshot = status(await request(operator, 'GET', '/api/v1/catalogs/' + job.snapshotId), 200); return { ...start, job, snapshot };
  }
  const created = status(await request(operator, 'POST', '/api/v1/connections', createBody((await intake()).ref)), 201);
  const id = publicId(created.id); report.fixtures.connectionId = id;
  cleanup = async () => { const before = await current(id); if (before.data.state !== 'DISABLED') status(await mutate(id, 'disable', {command:contextCommand(before.data.configRevision)}, before), 200); };
  const hash = value => value.etag.slice(1,-1).split('-').slice(1).join('-');
  const patch = (before, configValue, scopeSelection=null, displayName=null) => ({displayName, scopeSelection, config:configValue, command:contextCommand(before.data.configRevision)});
  const stale = async pid => status(await request(operator,'GET','/api/v1/connections/'+id+'/probes/'+pid),200).stale;
  phase='A_initial'; const a = await current(id); const pa = await probe(id);
  observe('M1-C08','A_exact_profile_and_five_stage_probe',JSON.stringify(a.data.config)===JSON.stringify(config) && successfulProbe(pa.value));
  report.flow = [{stage:'A',revision:a.data.configRevision,etag:a.etag,configHash:pa.value.configHash,probeId:pa.value.probeId,secretVersion:pa.value.secretVersion}];
  const bConfig = structuredClone(config); bConfig.profile.allowedSchemas=['production','public'];
  phase='B_patch'; const bBody=patch(a,bConfig); const bResponse=await mutate(id,'',bBody,a); status(bResponse,200); const b=await current(id);
  observe('M1-C08','B_persisted_revision_hash_and_probe_invalidated',JSON.stringify(b.data.config)===JSON.stringify(bConfig) && b.data.configRevision===a.data.configRevision+1 && hash(b)!==hash(a) && !b.data.probeFresh && b.data.lastProbeId===null && await stale(pa.value.probeId));
  report.flow.push({stage:'B',revision:b.data.configRevision,etag:b.etag,configHash:hash(b)});
  const replay=await mutate(id,'',bBody,a); status(replay,200); observe('M1-C08','B_same_command_replay_original_receipt',replay.raw===bResponse.raw && replay.etag===bResponse.etag);
  status(await mutate(id,'',patch(a,config),a),409,'connection_version_conflict'); observe('M1-C08','old_etag_rejected');
  status(await mutate(id,'',patch(b,null,{organizationId:'org-other',siteIds:['site-a']}),b),403,'connection_scope_forbidden'); observe('M1-C08','wrong_scope_rejected');
  const bad=structuredClone(bConfig);bad.profile.allowedSchemas.push('maintenance');status(await mutate(id,'',patch(b,bad),b),403,'connection_network_forbidden'); observe('M1-C08','third_schema_rejected');
  status(await mutate(id,'enable',{command:contextCommand(b.data.configRevision)},b),409,'connection_probe_stale'); observe('M1-C08','old_probe_cannot_enable_B');
  phase='B_display_name';status(await mutate(id,'',patch(b,null,null,'Synthetic final gates renamed'),b),200);const named=await current(id);
  observe('M1-C08','display_name_does_not_resurrect_probe',!named.data.probeFresh && await stale(pa.value.probeId));
  phase='B_reprobe';const pb=await probe(id);observe('M1-C08','B_new_probe_current_hash_secret_version',successfulProbe(pb.value) && pb.value.configHash===hash(named) && pb.value.configHash!==pa.value.configHash && pb.value.secretVersion===pa.value.secretVersion && pb.value.probeId!==pa.value.probeId);
  report.flow.push({stage:'B_reprobe',revision:named.data.configRevision,configHash:pb.value.configHash,probeId:pb.value.probeId,secretVersion:pb.value.secretVersion});
  const beforeEnable=await current(id);status(await mutate(id,'enable',{command:contextCommand(beforeEnable.data.configRevision)},beforeEnable),200);
  const catalog=await discover(id);observe('M1-C08','B_retested_enable_and_readable_catalog',catalog.snapshot.objects.length>0 && catalog.snapshot.objects.every(x=>x.schema==='production'));
  report.fixtures.snapshotId=catalog.snapshot.snapshotId;
  phase='return_A';const active=await current(id);status(await mutate(id,'',patch(active,config,null,a.data.displayName),active),200);const returned=await current(id);
  observe('M1-C08','return_A_hash_restored_but_both_old_probes_stale',hash(returned)===hash(a) && !returned.data.probeFresh && await stale(pa.value.probeId) && await stale(pb.value.probeId));
  status(await mutate(id,'enable',{command:contextCommand(returned.data.configRevision)},returned),409,'connection_probe_stale');observe('M1-C08','return_A_cannot_enable_old_A_probe');
  const pa2=await probe(id);observe('M1-C08','return_A_requires_new_successful_probe',successfulProbe(pa2.value) && pa2.value.probeId!==pa.value.probeId && pa2.value.configHash===pa.value.configHash);
  report.flow.push({stage:'return_A_reprobe',revision:returned.data.configRevision,configHash:pa2.value.configHash,probeId:pa2.value.probeId,secretVersion:pa2.value.secretVersion});
  const oldA=status(await request(operator,'GET','/api/v1/connections/'+id+'/probes/'+pa.value.probeId),200);const original={...oldA,stale:pa.value.stale};
  observe('M1-C08','original_probe_report_immutable_except_stale_projection',JSON.stringify(original)===JSON.stringify(pa.value));
  await cleanup();cleanup=null;observe('M1-C08','synthetic_connection_disabled',(await current(id)).data.state==='DISABLED');complete('M1-C08');
} catch(error) { report.failure={phase,...safeFailure(error,'configuration_or_runtime_error')}; }
finally {
  if(cleanup) try { await cleanup();report.cleanup='DISABLED'; } catch { report.cleanup='FAILED_REQUIRES_MASTER'; }
  for(const context of contexts) await context.close().catch(()=>{});
  await browser?.close().catch(()=>{});report.completedAtUtc=new Date().toISOString();
  report.exitCode=report.failure || report.checks.some(x=>x.status==='FAIL') || matrix['M1-C08'].status!=='PASS' ? 1 : 0;
  if(output) await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
  process.stdout.write(JSON.stringify({taskId:report.taskId,scope:'C08_ONLY',status:report.exitCode?'FAIL':'PASS',checks:report.checks.length,failure:report.failure??null,report:output?resolve(output,'report.json'):null})+'\n');process.exitCode=report.exitCode;
}
