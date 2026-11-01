/** 真实 OIDC/HTTP 补充验收；不启动服务，不保存凭据、SecretRef、原始响应或异常正文。 */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, lstat, realpath } from 'node:fs/promises';
import { resolve, relative, dirname, isAbsolute, sep } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

const help = `G4-M1 real HTTP acceptance
Usage: node scripts/acceptance/g4-m1-http.mjs --runtime-file PATH --evidence-dir PATH
Uses Master private runtime.json under this checkout .tools/security:
 taskId=G4-M1-RECOVERY-001, runId, publicOrigin=http://localhost:15100,
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
cross-org-secret requires private foreignSecretRef issued to org-demo/operator-ab.
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
Evidence under artifacts/g4-m1-recovery-001 or docs/evidence/G4-M1-RECOVERY-001 only.
Each invocation preserves a unique report. No screenshots, HAR, trace or storageState.
Exit 1=observed FAIL/runtime failure; 2=matrix still incomplete; 0=all 49 PASS.
Public HTTP cannot prove database rollback/fence/source I/O absence by itself;
untested parts remain NOT_RUN with explicit fixture requirements, never inferred PASS.`;
if (process.argv.includes('--help')) { process.stdout.write(help + '\n'); process.exit(0); }
const root = resolve(import.meta.dirname, '../..');
const groups = { C: 16, P: 14, E: 8, U: 6, R: 5 };
const matrix = Object.fromEntries(Object.entries(groups).flatMap(([prefix, count]) => Array.from({ length: count }, (_, n) => ['M1-' + prefix + String(n + 1).padStart(2, '0'), { status: 'NOT_RUN', observed: [], remaining: ['outside_executed_http_assertions'] }])));
const report = { schemaVersion: 1, taskId: 'G4-M1-RECOVERY-001', startedAtUtc: new Date().toISOString(), productExecution: false, matrix, checks: [], http: [], fixtures: {}, requirements: {
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
  demand(['artifacts/g4-m1-recovery-001', 'docs/evidence/G4-M1-RECOVERY-001'].some(base => resolve(root, base) === selected || inside(resolve(root, base), selected)), 'evidence_path_denied');
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
    identityStep('login_navigation'); await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fdata%2Fconnections');
    identityStep('username_input'); await page.locator('#username').fill(user.username);
    identityStep('password_input'); await page.locator('#password').fill(user.password);
    identityStep('login_submit'); await page.locator('#kc-login').click();
    identityStep('callback_navigation'); await page.waitForURL(url => url.origin === 'http://localhost:15100' && url.pathname === '/data/connections');
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
  if (['baseline','contracts'].includes(scenario)) {
    await step('authorization_priority', ['M1-C10','M1-C11'], async () => {
      const guest = await identity(null); const viewer = await identity('viewer-ab');
      const fakeId = '0'.repeat(32);
      const routes = [['GET','/api/v1/connections'], ['GET','/api/v1/connections/' + fakeId + '/catalogs'], ['POST','/api/v1/connections'], ['POST','/api/v1/connection-secrets'], ['POST','/api/v1/connections/' + fakeId + '/test'], ['POST','/api/v1/connections/' + fakeId + '/discoveries']];
      for (const [method,path] of routes) {
        const denied = await request(viewer, method, path, method === 'POST' ? '{' : undefined);
        status(denied, 403, 'authorization_denied');
        observe('M1-C10', 'six_server_policies_' + path.split('/').at(-1), true, { responseIndex: denied.index });
      }
      for (const actor of [guest, operator]) {
        const denied = await request(actor, 'POST', '/api/v1/connection-secrets', '{' + ' '.repeat(65537), { noCsrf: true });
        status(denied, actor === guest ? 401 : 403, actor === guest ? 'authentication_required' : 'csrf_rejected');
        observe('M1-C11', actor === guest ? 'authentication_before_oversize_and_json' : 'csrf_before_oversize_and_json', true, { responseIndex: denied.index });
      }
      const wrongOrigin = await request(operator, 'POST', '/api/v1/connections', '{', { headers: { Origin: 'http://localhost:15180' } }); status(wrongOrigin,403,'origin_rejected');
      const oversized = await request(operator, 'POST', '/api/v1/connection-secrets', '{' + ' '.repeat(65537)); status(oversized,413,'connection_profile_invalid');
      observe('M1-C11','origin_csrf_size_json_precedence_and_safe_problem', oversized.contentType?.startsWith('application/problem+json') && oversized.data.status === 413 && oversized.data.traceId === oversized.traceId);
    });
    await step('strict_create_contract', ['M1-C01','M1-C02','M1-C03','M1-C04'], async () => {
      const base = createBody('synthetic-unissued-reference');
      for (const [name, body] of [
        ['unknown_top_level',{ ...base, unexpected: true }], ['old_connectionProfile',{ ...base, connectionProfile: config }],
        ['old_secretInput',{ ...base, secretInput: 'synthetic-not-a-password' }], ['actor_context',{ ...base, actorContext: { roles:['platform.operator'] } }],
        ['unknown_command_action',{ ...base, command:{ ...base.command, action:'connection.arbitrary' } }],
      ]) { const result = await request(operator,'POST','/api/v1/connections',body); status(result,422,'connection_profile_invalid'); observe('M1-C01',name,true,{responseIndex:result.index}); }
      status(await request(operator,'POST','/api/v1/connections',base),422,'connection_secret_expired');
      observe('M1-C01','canonical_body_reaches_reference_validation_without_binding'); complete('M1-C01');
      status(await request(operator,'POST','/api/v1/connections',{schemaKind:'connection',payload:base}),422,'connection_profile_invalid'); observe('M1-C04','design_wrapper_rejected'); complete('M1-C04');
      for (const value of [null,true,false,'0',1,-1,0.5]) {
        status(await request(operator,'POST','/api/v1/connections',{...base,command:{...base.command,expectedRevision:value}}),422,'connection_profile_invalid');
      }
      observe('M1-C02','create_exact_integer_zero_only');
      for (const value of [null,true,'5432',0,65536,5432.5]) {
        const body = structuredClone(base); body.config.profile.port=value; status(await request(operator,'POST','/api/v1/connections',body),422,'connection_profile_invalid');
      }
      const profiles = [
        {type:'ORACLE',profile:{host:'pg-source',port:1521,serviceName:'fixture',username:'fixture_reader',tls:true,allowedOwners:['production']}},
        {type:'DORIS',profile:{feHost:'pg-source',queryPort:9030,catalog:'fixture',database:'fixture',username:'fixture_reader',tls:true}},
        {type:'TDENGINE',profile:{wsUrl:'wss://pg-source',database:'fixture',timePrecision:'MILLISECOND',timeZone:null}},
        {type:'WEB_API',profile:{baseOrigin:'https://pg-source',operationId:'synthetic_read',method:'GET',approvedPath:'/fixture',authentication:'NONE',pagination:'NONE',hostPolicyRef:'synthetic-policy'}},
      ];
      for (const value of profiles) {
        const body={...base,config:value,secretRef:value.type==='WEB_API'?null:base.secretRef};
        status(await request(operator,'POST','/api/v1/connections',body),422,'connector_not_enabled');
        status(await request(operator,'POST','/api/v1/connections',{...body,config:{...value,profile:{...value.profile,credentialRef:'synthetic-invalid'}}}),422,'connection_profile_invalid');
        if (value.type==='WEB_API') status(await request(operator,'POST','/api/v1/connections',{...body,secretRef:'synthetic-invalid'}),422,'connection_profile_invalid');
        observe('M1-C03',value.type+'_precise_profile_not_enabled');
      }
      for (const sslMode of ['Require','VerifyCA']) status(await request(operator,'POST','/api/v1/connections',{...base,config:{...config,profile:{...config.profile,sslMode}}}),422,'connection_tls_untrusted');
      status(await request(operator,'POST','/api/v1/connections',{...base,config:{...config,profile:{...config.profile,host:'unapproved-synthetic'}}}),403,'connection_network_forbidden');
      observe('M1-C03','postgres_verifyfull_and_exact_source_required'); complete('M1-C03');
    });
    await step('sql_and_reference_boundaries', ['M1-P06','M1-P07'], async () => {
      const issued=await intake(); const base=createBody(issued.ref);
      for (const text of ['production;SELECT 1','production UNION SELECT 1','WITH changed AS (DELETE FROM synthetic) SELECT 1','pg_sleep(1)','production"']) {
        status(await request(operator,'POST','/api/v1/connections/tests',{scopeSelection:scope,config:{...config,profile:{...config.profile,allowedSchemas:[text]}},secretRef:issued.ref,command:contextCommand(0)}),422,'connection_profile_invalid');
      }
      observe('M1-P06','sql_cte_function_multistatement_and_identifier_payloads_rejected');
      const otherActor=await identity('operator-a');
      status(await request(otherActor,'POST','/api/v1/connections',base),422,'connection_secret_expired'); observe('M1-P07','same_scope_different_actor_ref_rejected');
      status(await request(operator,'POST','/api/v1/connections',{...base,scopeSelection:{organizationId:'org-demo',siteIds:['site-b']}}),422,'connection_secret_expired'); observe('M1-P07','same_actor_different_scope_ref_rejected');
      status(await request(operator,'POST','/api/v1/connections',{...base,scopeSelection:{organizationId:'org-other',siteIds:['site-a']}}),403,'connection_scope_forbidden'); observe('M1-P07','forged_other_org_scope_denied_not_cross_org_identity_test');
      status(await request(operator,'POST','/api/v1/connection-secrets',{...issued.body,purpose:'ORACLE_READONLY',command:contextCommand(0)}),422,'connection_profile_invalid'); observe('M1-P07','wrong_purpose_intake_rejected');
    });
  }
  let id;
  if (['baseline','provision'].includes(scenario)) {
    let issued, creation, createRequest, initialProbe, firstCatalog;
    const created = await step('persistent_create_and_idempotency', ['M1-P10','M1-P11'], async () => {
      issued=await intake(); createRequest=createBody(issued.ref); creation=await request(operator,'POST','/api/v1/connections',createRequest);
      const value=status(creation,201); id=publicId(value.id); report.fixtures.connectionId=id;
      observe('M1-P10','created_only_draft_without_inherited_probe',value.state==='DRAFT' && value.configRevision===1 && value.lastProbeId===null && value.probeFresh===false); complete('M1-P10');
      const replay=await request(operator,'POST','/api/v1/connections',createRequest); status(replay,201);
      observe('M1-P11','exact_create_replay_same_response_and_etag',replay.raw===creation.raw && replay.etag===creation.etag);
      const conflict=await request(operator,'POST','/api/v1/connections',{...createRequest,displayName:createRequest.displayName+' changed'}); status(conflict,409,'connection_version_conflict');
      const stored=await current(id); observe('M1-P11','different_payload_does_not_change_entity',stored.data.configRevision===1 && stored.data.displayName===createRequest.displayName);
      const rows=await auditRows();
      observe('M1-P11','committed_create_audit_once_no_replay_or_conflict_audit',!!creation.traceId && rows.filter(row=>row.action==='connection.create' && row.traceId===creation.traceId).length===1 && !rows.some(row=>row.action==='connection.create' && [replay.traceId,conflict.traceId].includes(row.traceId)));
      complete('M1-P11');
      status(await request(operator,'POST','/api/v1/connections',{...createRequest,command:contextCommand(0)}),422,'connection_secret_expired');
      status(await request(operator,'POST','/api/v1/connection-secrets',issued.body),422,'connection_secret_expired'); observe('M1-P07','bound_ref_new_command_and_intake_replay_rejected');
      const projection=status(await request(auditor,'GET','/api/v1/connections/'+id),200);
      observe('M1-P08','auditor_redacted_config',projection.config.profile.host==='redacted' && projection.config.profile.database==='redacted' && projection.config.profile.username==='redacted' && JSON.stringify(projection.config.profile.allowedSchemas)==='["redacted"]');
      observe('M1-C12','connection_revision_etag_trace_correspond',creation.etag.startsWith('"1-') && rows.some(row=>row.traceId===creation.traceId && row.action==='connection.create' && row.organizationId==='org-demo'));
    });
    if (created) {
      await step('update_integer_and_etag_boundaries', ['M1-C02'], async () => {
        const before=await current(id);
        for (const revision of [null,true,false,'1',0,-1,1.5]) status(await mutate(id,'',{displayName:'Synthetic invalid revision',command:{...contextCommand(1),expectedRevision:revision}},before),422,'connection_profile_invalid');
        const patch={displayName:'Synthetic missing revision',command:contextCommand(before.data.configRevision)};
        status(await request(operator,'PATCH','/api/v1/connections/'+id,patch),428,'revision_required');
        for (const etag of ['*','W/'+before.etag,'"1"']) status(await request(operator,'PATCH','/api/v1/connections/'+id,patch,{headers:{'If-Match':etag}}),400,'invalid_revision');
        status(await mutate(id,'',{...patch,command:contextCommand(before.data.configRevision+1)},before),409,'connection_version_conflict');
        observe('M1-C02','update_positive_integer_strong_etag_and_revision_match_required');
        if (scenario==='baseline' && completedSteps.has('strict_create_contract')) complete('M1-C02');
      });
      await step('trusted_resource_scope', ['M1-C10'], async () => {
        const before=await current(id);
        status(await mutate(id,'',{scopeSelection:{organizationId:'org-demo',siteIds:['site-a','site-b']},command:contextCommand(before.data.configRevision)},before),200);
        const restricted=await identity('operator-a');
        status(await request(restricted,'GET','/api/v1/connections/'+id),403,'connection_scope_forbidden');
        status(await request(restricted,'POST','/api/v1/connections/'+id+'/test',{command:contextCommand(before.data.configRevision+1)},{headers:{'If-Match':before.etag}}),403,'connection_scope_forbidden');
        const expanded=await current(id);
        status(await mutate(id,'',{scopeSelection:scope,command:contextCommand(expanded.data.configRevision)},expanded),200);
        observe('M1-C10','server_stored_full_scope_checked_before_stale_cas');
        if (scenario==='baseline' && completedSteps.has('authorization_priority')) complete('M1-C10');
      });
      const probed=await step('real_probe_and_enable', ['M1-P01','M1-C09'], async () => {
        initialProbe=await probe(id); observe('M1-P01','real_verifyfull_five_stage_probe',successfulProbe(initialProbe.value)); complete('M1-P01');
        report.fixtures.probeId=initialProbe.value.probeId;
        const replay=await mutate(id,'test',initialProbe.body,initialProbe.before); status(replay,200);
        observe('M1-P11','probe_replay_same_persistent_id',replay.data.probeId===initialProbe.value.probeId && replay.data.completedAtUtc===initialProbe.value.completedAtUtc);
        const before=await current(id);
        observe('M1-C09','probe_success_does_not_activate_connection',before.data.state==='DRAFT' && before.data.probeFresh && initialProbe.value.status==='TEST_OK');
        const enabled=status(await mutate(id,'enable',{command:contextCommand(before.data.configRevision)},before),200);
        demand(enabled.state==='ACTIVE','enable_not_active');
      });
      if (probed) {
        await step('catalog_snapshot_and_new_oidc_session', ['M1-E01','M1-E02','M1-E05','M1-C09'], async () => {
          firstCatalog=await discover(id); report.fixtures.jobId=firstCatalog.job.jobId; report.fixtures.snapshotId=firstCatalog.snapshot.snapshotId;
          const objects=firstCatalog.snapshot.objects;
          observe('M1-E01','current_scope_and_source_role_only_production_heat_event',objects.length===1 && objects[0].schema==='production' && objects[0].name==='heat_event'); complete('M1-E01');
          const fields=Object.fromEntries(objects[0].fields.map(field=>[field.name,field]));
          observe('M1-E02','native_numeric_timestamp_timestamptz_jsonb_array_nullable',fields.tap_temp?.nativeType==='numeric(8,2)' && fields.tap_temp.precision===8 && fields.tap_temp.scale===2 && fields.tap_ts?.nativeType==='timestamp without time zone' && fields.event_time?.nativeType==='timestamp with time zone' && fields.payload?.nativeType==='jsonb' && fields.tags?.nativeType==='text[]' && fields.nullable?.nullable===true && fields.id?.nullable===false); complete('M1-E02');
          const secondSession=await identity('operator-ab');
          const read=status(await request(secondSession,'GET','/api/v1/connections/'+id+'/discoveries/'+firstCatalog.job.jobId),200);
          observe('M1-E05','durable_job_recovered_by_new_real_oidc_session',read.jobId===firstCatalog.job.jobId && read.snapshotId===firstCatalog.snapshot.snapshotId && read.status==='SUCCEEDED' && !!read.completedAtUtc); complete('M1-E05');
          observe('M1-C09','connection_probe_job_catalog_distinct_states',(await current(id)).data.state==='ACTIVE' && initialProbe.value.status==='TEST_OK' && firstCatalog.job.status==='SUCCEEDED' && firstCatalog.snapshot.status==='READY'); complete('M1-C09');
          const second=await discover(id); const old=status(await request(operator,'GET','/api/v1/catalogs/'+firstCatalog.snapshot.snapshotId),200);
          observe('M1-E03','same_content_fingerprint_stable_new_snapshot_old_projection_unchanged',firstCatalog.snapshot.snapshotId!==second.snapshot.snapshotId && firstCatalog.snapshot.schemaFingerprint===second.snapshot.schemaFingerprint && JSON.stringify(old)===JSON.stringify(firstCatalog.snapshot));
          observe('M1-E04','other_schemas_absent_from_actual_catalog',objects.every(item=>!['maintenance','otherplant'].includes(item.schema)));
          const audit=await auditRows();
          observe('M1-C12','probe_and_job_trace_match_committed_audit',audit.some(row=>row.action==='connection.probe.complete' && row.traceId===initialProbe.value.traceId && row.resource==='connection:'+id) && audit.some(row=>row.action==='connection.catalog.finish' && row.traceId===firstCatalog.job.traceId && row.resource==='connection:'+id));
          const actions=new Set(['connection.secret.intake','connection.create','connection.update','connection.secret.rotate','connection.probe.start','connection.probe.complete','connection.enable','connection.disable','connection.catalog.start','connection.catalog.finish','connection.catalog.cancel']);
          observe('M1-C13','observed_connection_audit_actions_in_fixed_allowlist',audit.filter(row=>row.action.startsWith('connection.')).every(row=>actions.has(row.action)));
        });
      }
      if (scenario==='baseline' && probed && firstCatalog) {
        await step('wrong_password_real_authentication', ['M1-P03'], async () => {
          const wrong='synthetic-wrong-'+randomUUID(); remember(wrong); const bad=await intake(wrong);
          const result=status(await request(operator,'POST','/api/v1/connections/tests',{scopeSelection:scope,config,secretRef:bad.ref,command:contextCommand(0)}),200);
          observe('M1-P03','real_auth_failure_after_network_and_tls',result.status==='TEST_FAILED' && result.stages.some(stage=>stage.name==='AUTH' && stage.status==='FAIL' && stage.diagnosticCode==='connection_auth_failed') && ['NETWORK','TLS'].every(name=>result.stages.some(stage=>stage.name===name && stage.status==='PASS')));
          matrix['M1-P03'].remaining=['Source-side bounded retry count is not exposed by public HTTP.'];
        });
        await step('concurrent_patch_and_rotation_invalidation', ['M1-C08','M1-P09','M1-P12'], async () => {
          const before=await current(id);
          const bodies=[0,1].map(index=>({displayName:'G4 synthetic concurrency '+index+' '+randomUUID().slice(0,8),command:contextCommand(before.data.configRevision)}));
          const raced=await Promise.all(bodies.map(body=>mutate(id,'',body,before)));
          observe('M1-P12','concurrent_patch_one_commit_one_409',raced.map(value=>value.status).sort().join(',')==='200,409');
          const winner=raced.findIndex(value=>value.status===200); const after=await current(id);
          demand(after.data.configRevision===before.data.configRevision+1 && after.data.displayName===bodies[winner].displayName,'concurrent_state_overwritten');
          const old=status(await request(operator,'GET','/api/v1/connections/'+id+'/probes/'+initialProbe.value.probeId),200);
          observe('M1-C08','configuration_change_invalidates_previous_probe',old.stale && !after.data.probeFresh && after.data.lastProbeId===null && after.data.state==='DRAFT');
          const newer=await probe(id); demand(successfulProbe(newer.value),'reprobe_failed');
          observe('M1-C08','new_probe_uses_changed_display_name_envelope_hash',newer.value.configHash!==initialProbe.value.configHash);
          const next=await intake(); const preRotate=await current(id);
          const rotated=status(await mutate(id,'rotate-secret',{secretRef:next.ref,command:contextCommand(preRotate.data.configRevision)},preRotate),200);
          const oldAfterRotate=status(await request(operator,'GET','/api/v1/connections/'+id+'/probes/'+newer.value.probeId),200);
          observe('M1-C08','secret_rotation_increments_version_and_invalidates_probe',rotated.secretVersion===preRotate.data.secretVersion+1 && rotated.lastProbeId===null && !rotated.probeFresh && rotated.state==='DRAFT' && oldAfterRotate.stale);
          matrix['M1-C08'].remaining=['Only displayName and SecretVersion changed; a valid SourceConfig profile change was not executed because the approved runnable profile is fixed.'];
          status(await request(operator,'POST','/api/v1/connections/tests',{scopeSelection:scope,config,secretRef:issued.ref,command:contextCommand(0)}),422,'connection_secret_expired');
          observe('M1-P09','previous_bound_ref_cannot_be_reused_after_rotation');
          const finalProbe=await probe(id); demand(successfulProbe(finalProbe.value) && finalProbe.value.secretVersion===rotated.secretVersion,'rotated_probe_failed');
          observe('M1-P09','new_probe_uses_current_secret_version');
          const enableBefore=await current(id); const enableResults=await Promise.all([0,1].map(()=>mutate(id,'enable',{command:contextCommand(enableBefore.data.configRevision)},enableBefore)));
          observe('M1-P12','concurrent_enable_one_commit_one_409',enableResults.map(value=>value.status).sort().join(',')==='200,409');
          const active=await current(id); demand(active.data.state==='ACTIVE' && active.data.configRevision===enableBefore.data.configRevision+1,'enable_state_overwritten');
          for (const action of ['enable','disable']) status(await mutate(id,action,{command:contextCommand(before.data.configRevision)},before),409,'connection_version_conflict');
          observe('M1-P12','old_etag_enable_disable_rejected');
        });
        await step('disable_and_current_authorization', ['M1-P12','M1-P14'], async () => {
          const before=await current(id); const results=await Promise.all([0,1].map(()=>mutate(id,'disable',{command:contextCommand(before.data.configRevision)},before)));
          observe('M1-P12','concurrent_disable_one_commit_one_409',results.map(value=>value.status).sort().join(',')==='200,409');
          const disabled=await current(id); demand(disabled.data.state==='DISABLED' && disabled.data.configRevision===before.data.configRevision+1,'disable_state_overwritten');
          if (matrix['M1-P12'].observed.includes('concurrent_patch_one_commit_one_409') && matrix['M1-P12'].observed.includes('concurrent_enable_one_commit_one_409')) complete('M1-P12');
          status(await mutate(id,'test',{command:contextCommand(disabled.data.configRevision)},disabled),409,'connection_disabled');
          status(await mutate(id,'discoveries',{command:contextCommand(disabled.data.configRevision)},disabled),409,'connection_probe_stale');
          status(await request(operator,'GET','/api/v1/connections/'+id+'/catalogs'),403,'catalog_access_forbidden');
          if (firstCatalog) status(await request(auditor,'GET','/api/v1/catalogs/'+firstCatalog.snapshot.snapshotId),403,'catalog_access_forbidden');
          observe('M1-P14','disabled_probe_discovery_and_history_requests_denied');
          report.fixtures.finalConnectionState='DISABLED';
        });
      } else { report.fixtures.finalConnectionState=(await current(id)).data.state; if (scenario==='baseline') report.fixtures.keepReason='dependent_source_or_catalog_phase_failed_preserve_for_short_reproduction'; }
    }
  } else if (scenario === 'cross-org-secret') {
    matrix['M1-P07'].remaining = ['Master binds foreign reference to a different organization/owner with unused/unexpired safe DB witness and confirms account restoration via a new login; expiry/replay/purpose/revocation cases require separate evidence.'];
    await step('credential_actual_cross_org_identity_and_reference', ['M1-P07'], async () => {
      const me = status(await request(operator, 'GET', '/api/v1/platform/me'), 200);
      demand(Array.isArray(me.roles) && me.roles.includes('platform.operator') && Array.isArray(me.scopes) && me.scopes.length > 0
        && me.scopes.every(value => value.organizationId === 'org-other') && me.scopes.some(value => value.siteId === 'site-a'), 'cross_org_actual_identity_not_confirmed');
      observe('M1-P07', 'actual_other_organization_oidc_operator_identity_confirmed', true,
        { identityLabel: 'operator-a', organizationId: 'org-other', selectedSiteId: 'site-a', canonicalOperatorRole: true });
      const rejected = await request(operator, 'POST', '/api/v1/connections', createBody(runtime.foreignSecretRef, { organizationId: 'org-other', siteIds: ['site-a'] }));
      status(rejected, 422, 'connection_secret_expired');
      observe('M1-P07', 'actual_cross_org_actor_foreign_reference_new_command_rejected', true, { responseIndex: rejected.index });
    });
  } else if (scenario === 'credential-lifecycle') {
    matrix['M1-P07'].remaining = ['HTTP 422 is shared by missing/used/expired/purpose/scope failures; Master must bind original unused expiry and revoked ciphertext-cleared witnesses, cross-org and other required cases. No business/source I/O absence is inferred.'];
    matrix['M1-P09'].remaining = ['Master independently confirms exact source password changes/restoration, old ciphertext clearing and Pooling=false source/build binding; HTTP observations alone do not inspect pools.'];
    await step('credential_supplied_reference_rejections', ['M1-P07'], async () => {
      for (const [label, ref] of [['expired', runtime.expiredSecretRef], ['revoked', runtime.revokedSecretRef]]) {
        const rejected = await request(operator, 'POST', '/api/v1/connections', createBody(ref));
        status(rejected, 422, 'connection_secret_expired');
        observe('M1-P07', 'master_supplied_' + label + '_ref_new_create_command_rejected', true, { responseIndex: rejected.index,
          ...(label === 'expired' ? { observedAfterProvidedExpiresAt: Date.now() >= Date.parse(runtime.expiredSecretExpiresAtUtc) } : {}) });
      }
    });
    await step('credential_real_source_rotation', ['M1-P07','M1-P09'], async () => {
      let needsRestore = false;
      try {
        phase = 'credential_original_create_probe';
        const original = await intake(); const created = status(await request(operator, 'POST', '/api/v1/connections', createBody(original.ref)), 201);
        id = publicId(created.id); report.fixtures.connectionId = id;
        const beforeChange = await probe(id);
        observe('M1-P09', 'original_password_real_probe_all_five_stages_pass', successfulProbe(beforeChange.value));
        phase = 'credential_rotation_handshake'; needsRestore = true; report.fixtures.sourceRestorationRequired = true; report.fixtures.sourceRestorationVerifiedByProbe = false;
        await credentialSignal('rotate', id);
        phase = 'credential_old_bound_password_after_source_change';
        const rejectedOld = await probe(id);
        const authRejected = value => value.status === 'TEST_FAILED' && ['NETWORK','TLS'].every(name => value.stages.some(stage => stage.name === name && stage.status === 'PASS'))
          && value.stages.some(stage => stage.name === 'AUTH' && stage.status === 'FAIL' && stage.diagnosticCode === 'connection_auth_failed')
          && ['READ_ONLY','METADATA'].every(name => value.stages.some(stage => stage.name === name && stage.status === 'NOT_RUN'));
        observe('M1-P09', 'old_bound_physical_password_auth_rejected_after_real_source_change', authRejected(rejectedOld.value));
        phase = 'credential_new_password_rotation';
        const next = await intake(rotationSecret); const beforeRotate = await current(id);
        const rotated = status(await mutate(id, 'rotate-secret', { secretRef: next.ref, command: contextCommand(beforeRotate.data.configRevision) }, beforeRotate), 200);
        const oldProbe = status(await request(operator, 'GET', '/api/v1/connections/' + id + '/probes/' + beforeChange.value.probeId), 200);
        observe('M1-P09', 'rotation_increments_secret_version_and_invalidates_old_probe', rotated.secretVersion === beforeRotate.data.secretVersion + 1 && rotated.lastProbeId === null && !rotated.probeFresh && rotated.state === 'DRAFT' && oldProbe.stale,
          { previousVersion: beforeRotate.data.secretVersion, currentVersion: rotated.secretVersion });
        const newProbe = await probe(id);
        observe('M1-P09', 'new_password_real_probe_all_stages_and_current_version', successfulProbe(newProbe.value) && newProbe.value.secretVersion === rotated.secretVersion);
        phase = 'credential_old_reference_rejections_after_rotation';
        for (const [label, ref] of [['previous_bound', original.ref], ['master_revoked', runtime.revokedSecretRef]]) {
          const rejected = await request(operator, 'POST', '/api/v1/connections/tests', { scopeSelection: scope, config, secretRef: ref, command: contextCommand(0) });
          status(rejected, 422, 'connection_secret_expired'); observe('M1-P07', label + '_ref_new_draft_probe_command_rejected', true, { responseIndex: rejected.index });
        }
        phase = 'credential_old_password_after_new_version_success';
        const oldValue = await intake(sourceSecret);
        const oldDraft = status(await request(operator, 'POST', '/api/v1/connections/tests', { scopeSelection: scope, config, secretRef: oldValue.ref, command: contextCommand(0) }), 200);
        observe('M1-P09', 'old_password_still_auth_rejected_after_new_version_success', authRejected(oldDraft));
      } finally {
        const interruptedPhase = phase;
        if (needsRestore) {
          await step('credential_restore_source_and_verify', ['M1-P09'], async () => {
            await credentialSignal('restore', id);
            const restored = await intake(sourceSecret);
            const draft = status(await request(operator, 'POST', '/api/v1/connections/tests', { scopeSelection: scope, config, secretRef: restored.ref, command: contextCommand(0) }), 200);
            observe('M1-P09', 'original_password_restored_real_draft_probe_all_stages_pass', successfulProbe(draft));
            report.fixtures.sourceRestorationVerifiedByProbe = true; report.fixtures.sourceRestorationRequired = false;
          });
        }
        if (id) await step('credential_disable_exact_created_connection', ['M1-P09'], async () => {
          const beforeDisable = await current(id);
          if (beforeDisable.data.state !== 'DISABLED') status(await mutate(id, 'disable', { command: contextCommand(beforeDisable.data.configRevision) }, beforeDisable), 200);
          const disabled = await current(id); demand(disabled.data.state === 'DISABLED', 'credential_cleanup_disable_failed'); report.fixtures.finalConnectionState = 'DISABLED';
        });
        phase = interruptedPhase;
      }
    });
  } else if (scenario!=='contracts') {
    id=publicId(runtime.httpConnectionId); report.fixtures.connectionId=id;
    await step('controlled_'+scenario, ['M1-P13','M1-E04','M1-E06','M1-E08'], async () => {
      if (scenario==='recover-job') {
        const job=await terminal(id,publicId(runtime.httpJobId));
        observe('M1-E06','existing_persistent_job_terminal_after_master_restart',['SUCCEEDED','FAILED','CANCELLED','PARTIAL'].includes(job.status),{terminalStatus:job.status});
      } else if (scenario==='source-unavailable' || scenario==='source-permission-limited') {
        const started=await startDiscovery(id); const job=await terminal(id,started.job.jobId);
        observe('M1-P13','actual_fault_discovery_not_empty_success',['FAILED','PARTIAL','CANCELLED'].includes(job.status) && job.snapshotId===null,{terminalStatus:job.status});
        if (scenario==='source-permission-limited') observe('M1-E04','permission_limited_is_partial_not_empty',job.status==='PARTIAL');
        status(await request(operator,'GET','/api/v1/connections/'+id+'/catalogs'),403,'catalog_access_forbidden');
        const failed=await probe(id); observe('M1-P13','source_fault_probe_not_test_ok',failed.value.status!=='TEST_OK');
      } else if (scenario==='catalog-cancel') {
        const start=await startDiscovery(id); const cancelled=status(await mutate(id,'discoveries/'+start.job.jobId+'/cancel',{command:contextCommand(start.before.data.configRevision)},start.before),200);
        const job=await terminal(id,start.job.jobId);
        if (job.status==='CANCELLED') observe('M1-E06','real_cancel_durable_terminal',!job.snapshotId && !!job.completedAtUtc);
        else matrix['M1-E06'].remaining=['Real job completed before cancel; establish a real source delay and rerun only this scenario.'];
        demand(['QUEUED','RUNNING','CANCELLED','SUCCEEDED','FAILED','PARTIAL'].includes(cancelled.status),'cancel_state_invalid');
      } else {
        const oldId=publicId(runtime.httpSnapshotId); const old=status(await request(operator,'GET','/api/v1/catalogs/'+oldId),200); const fresh=await discover(id);
        observe('M1-E08','actual_source_change_new_hash_and_old_stale',old.status==='STALE' && old.schemaFingerprint!==fresh.snapshot.schemaFingerprint && old.snapshotId!==fresh.snapshot.snapshotId);
        report.fixtures.snapshotId=fresh.snapshot.snapshotId;
      }
    });
  }
  // 逐项保留公开 HTTP 无法证明的部分；安全响应扫描从不代替日志/ZIP/Trace审查。
  if (!responseLeakFound && responseScanCount > 0) observe('M1-P08','executed_http_responses_scanned_in_memory_no_sensitive_values',true,{responseScanCount});
  matrix['M1-C11'].remaining=['Full priority/error taxonomy still needs all transport and fixture failure classes.'];
} catch (error) {
  report.failure = { phase, ...safeFailure(error, 'configuration_or_runtime_error') };
} finally {
  for (const context of contexts) await context.close().catch(()=>{});
  await browser?.close().catch(()=>{});
  report.completedAtUtc = new Date().toISOString();
  report.exitCode = report.failure || report.checks.some(check=>check.status==='FAIL') ? 1 : Object.values(matrix).some(item=>item.status!=='PASS') ? 2 : 0;
  if (output) await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
  process.stdout.write(JSON.stringify({taskId:report.taskId,scenario:report.scenario??null,status:report.exitCode===1?'FAIL':report.exitCode===2?'INCOMPLETE':'PASS',counts:Object.fromEntries(['PASS','FAIL','NOT_RUN'].map(state=>[state,Object.values(matrix).filter(item=>item.status===state).length])),failure:report.failure??null})+'\n');
  process.exitCode=report.exitCode;
}
