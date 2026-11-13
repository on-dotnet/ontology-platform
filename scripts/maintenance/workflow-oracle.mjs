/** 本任务真实OIDC、Oracle凭据与UI生命周期；不输出秘密、响应正文或截图。 */
import {readFile, realpath} from 'node:fs/promises';
import {resolve, sep, dirname} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
const root = resolve(import.meta.dirname, '../..');
const checks = [];
let browser, phase = 'runtime';
const check = (value, code) => { if (!value) throw new Error(code); };
const command = (revision = 0) => ({commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Oracle合成验收'});
async function privateFile(path, base) {
  const absolute = resolve(path);
  check(absolute.startsWith(base + sep) && await realpath(absolute) === absolute, 'PRIVATE_PATH');
  return readFile(absolute, 'utf8');
}
try {
  const baseDir = resolve(root, '.tools/security/g4-m2-oracle-01');
  const file = resolve(process.argv[2]);
  const runtime = JSON.parse(await privateFile(file, baseDir));
  check(runtime.taskId === 'G4-M2-ORACLE-01' && /^oracle-[a-z0-9-]+$/.test(runtime.runId) && runtime.worktree === root, 'RUNTIME_IDENTITY');
  check(file === resolve(baseDir, runtime.runId, 'runtime.json'), 'RUNTIME_PATH');
  const fixture = mode => JSON.parse(execFileSync('python3', ['-B', resolve(root, 'scripts/maintenance/workflow_oracle_fixture.py'), 'control', '--runtime', runtime.oracleSourceRecord, '--mode', mode], {cwd: root, timeout: 20000, maxBuffer: 65536}).toString());
  const platform = (mode, job) => JSON.parse(execFileSync('python3', ['-B', resolve(root, 'scripts/maintenance/workflow_oracle_platform.py'), '--runtime', resolve(dirname(runtime.oracleSourceRecord), 'platform-resources.json'), '--mode', mode, ...(job ? ['--job', job] : [])], {cwd: root, timeout: 15000, maxBuffer: 65536}).toString());
  const origin = runtime.publicOrigin;
  check(origin === 'http://localhost:15100', 'ORIGIN');
  const realm = JSON.parse(await privateFile(runtime.realmFile, resolve(baseDir, runtime.runId)));
  const password = (await privateFile(runtime.sourceSecretFile, resolve(root, 'artifacts/workflow/G4-M2-ORACLE-01'))).trim();
  const {chromium} = createRequire(resolve(root, 'apps/web/package.json'))('@playwright/test');
  browser = await chromium.launch({channel: 'msedge', headless: true});
  const context = await browser.newContext({serviceWorkers: 'block', extraHTTPHeaders: {Connection: 'close'}});
  await context.route('**/*', route => new Set([origin, 'http://localhost:15180']).has(new URL(route.request().url()).origin) ? route.continue() : route.abort());
  context.setDefaultTimeout(12000);
  const page = await context.newPage();
  const user = realm.identities['g2-operator-ab'];
  phase = 'oidc';
  await page.goto(origin + '/auth/login?returnUrl=%2Fdata%2Fconnections');
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#kc-login').click();
  await page.waitForURL(url => url.origin === origin && url.pathname === '/data/connections');
  const cookie = (await context.cookies()).find(value => value.name === '.OntologyPlatform.Session');
  check(cookie?.httpOnly && cookie.sameSite === 'Lax', 'SESSION_COOKIE');
  checks.push('REAL_OIDC');
  async function get(path) {
    const response = await context.request.get(origin + path, {maxRedirects: 0});
    return {status: response.status(), data: await response.json(), etag: response.headers().etag};
  }
  async function send(path, body, revision, method = 'POST') {
    const csrf = await get('/auth/csrf');
    check(csrf.status === 200, 'CSRF');
    const headers = {Origin: origin, 'X-CSRF-TOKEN': csrf.data.requestToken};
    if (revision !== undefined) {
      const resource = path.match(/^\/api\/v1\/connections\/[^/]+/);
      check(resource, 'ETAG_RESOURCE');
      const current = await get(resource[0]);
      check(current.status === 200 && current.etag, 'ETAG');
      headers['If-Match'] = current.etag;
    }
    const response = await context.request.fetch(origin + path, {method, data: body, headers, maxRedirects: 0});
    return {status: response.status(), data: await response.json()};
  }
  const scope = {organizationId: 'org-demo', siteIds: ['site-a']};
  const config = {type: 'ORACLE', profile: {host: 'oracle-source', port: 2484, serviceName: 'FREEPDB1', username: 'FIXTURE_READER', allowedOwners: ['PRODUCTION', 'CaseOwner'], tls: true}};
  const path = id => '/api/v1/connections/' + id;
  async function intake(purpose = 'ORACLE_READONLY', selection = scope) {
    const body = {secretValue: password, scopeSelection: selection, purpose, command: command()};
    const response = await send('/api/v1/connection-secrets', body);
    check(response.status === 201, 'INTAKE');
    return {...response, body};
  }
  async function until(operation, code) {
    const end = Date.now() + 15000;
    while (Date.now() < end) { if (await operation()) return; await new Promise(resolve => setTimeout(resolve, 200)); }
    throw new Error(code);
  }
  phase = 'purpose_scope';
  const first = await intake();
  const replay = await send('/api/v1/connection-secrets', first.body);
  check(replay.status === 201 && replay.data.secretRef === first.data.secretRef, 'INTAKE_REPLAY');
  check((await send('/api/v1/connection-secrets', {...first.body, purpose: 'WEB_API_KEY'})).status === 409, 'PURPOSE_CONFLICT');
  for (const purpose of ['POSTGRESQL_READONLY', 'WEB_API_KEY']) {
    const wrong = await intake(purpose);
    check((await send('/api/v1/connections', {displayName: 'wrong-purpose', scopeSelection: scope, config, secretRef: wrong.data.secretRef, command: command()})).status === 422, 'CROSS_PURPOSE_CREATE');
    check((await send('/api/v1/connections/tests', {scopeSelection: scope, config, secretRef: wrong.data.secretRef, command: command()})).status === 422, 'CROSS_PURPOSE_DRAFT');
  }
  const otherScope = await intake('ORACLE_READONLY', {organizationId: 'org-demo', siteIds: ['site-b']});
  check((await send('/api/v1/connections', {displayName: 'wrong-scope', scopeSelection: scope, config, secretRef: otherScope.data.secretRef, command: command()})).status === 422, 'CROSS_SCOPE');
  checks.push('ORACLE_INTAKE_REPLAY_PURPOSE_SCOPE');
  phase = 'ui';
  await page.getByRole('link', {name: '新建连接', exact: true}).click();
  await page.getByRole('combobox', {name: /^数据源类型/}).selectOption('ORACLE');
  await page.locator('input[name=displayName]').fill('Oracle ' + runtime.runId);
  await page.getByRole('combobox', {name: /^所属厂区/}).selectOption('org-demo/site-a');
  await page.getByLabel('重新输入密码', {exact: true}).fill(password);
  async function click(label, expectedPath, status) {
    const [response] = await Promise.all([page.waitForResponse(value => new URL(value.url()).pathname === expectedPath && value.request().method() === 'POST'), page.getByRole('button', {name: label, exact: true}).click()]);
    check(response.status() === status, 'UI_RESPONSE_' + label);
    return response.json();
  }
  await click('安全录入凭据', '/api/v1/connection-secrets', 201);
  check((await page.getByLabel('重新输入密码', {exact: true}).inputValue()) === '', 'UI_SECRET_CLEARED');
  check((await click('测试草稿', '/api/v1/connections/tests', 200)).status === 'TEST_OK', 'DRAFT_TEST');
  let row = await click('保存为草稿', '/api/v1/connections', 201);
  check(row.state === 'DRAFT', 'CREATE_DRAFT');
  await page.waitForURL('**/data/connections/' + row.id);
  check((await click('重新测试', path(row.id) + '/test', 200)).status === 'TEST_OK', 'SAVED_TEST');
  row = await click('明确启用连接', path(row.id) + '/enable', 200);
  check(row.state === 'ACTIVE', 'ENABLE');
  const job = await click('发现目录', path(row.id) + '/discoveries', 202);
  let done;
  await until(async () => { done = (await get(path(row.id) + '/discoveries/' + job.jobId)).data; return done.status === 'SUCCEEDED'; }, 'DISCOVERY');
  const catalog = await get('/api/v1/catalogs/' + done.snapshotId);
  check(catalog.status === 200 && catalog.data.objects.length === 3 && catalog.data.objects.some(object => object.fields.some(field => field.oracleMetadata?.timeZoneKind === 'WITH_LOCAL_TIME_ZONE')), 'CATALOG');
  check(!(await page.locator('body').innerText()).includes(password), 'UI_SECRET_LEAK');
  checks.push('UI_INTAKE_CREATE_PROBE_ENABLE_DISCOVER');
  // UI断言已完成；关闭页面停止目录自动刷新，避免与待取消Worker混淆源连接身份。
  await page.close();
  phase = 'auditor_projection';
  const auditContext = await browser.newContext({serviceWorkers: 'block'});
  await auditContext.route('**/*', route => new Set([origin, 'http://localhost:15180']).has(new URL(route.request().url()).origin) ? route.continue() : route.abort());
  const auditPage = await auditContext.newPage();
  const auditUser = realm.identities['g2-auditor-a'];
  await auditPage.goto(origin + '/auth/login?returnUrl=%2Fdata%2Fconnections');
  await auditPage.locator('#username').fill(auditUser.username);
  await auditPage.locator('#password').fill(auditUser.password);
  await auditPage.locator('#kc-login').click();
  await auditPage.waitForURL(url => url.origin === origin && url.pathname === '/data/connections');
  for (const endpoint of [path(row.id), '/api/v1/connections']) {
    const response = await auditContext.request.get(origin + endpoint);
    check(response.status() === 200, 'AUDITOR_READ');
    const result = await response.json();
    const projected = endpoint === path(row.id) ? result : result.items.find(item => item.id === row.id);
    check(projected && ['host', 'serviceName', 'username'].every(key => projected.config.profile[key] === 'redacted') && JSON.stringify(projected.config.profile.allowedOwners) === JSON.stringify(['redacted']), 'AUDITOR_ORACLE_REDACTED');
  }
  const operatorConfig = (await get(path(row.id))).data.config;
  check(Object.entries(config.profile).every(([key, value]) => JSON.stringify(operatorConfig.profile[key]) === JSON.stringify(value)) && operatorConfig.type === config.type, 'OPERATOR_TARGET_UNCHANGED');
  await auditContext.close();
  await until(async () => fixture('active-reader').sourceIds.length === 0, 'READER_QUIET');
  phase = 'active_cancel';
  const cancellations = [];
  for (const mutation of ['cancel', 'disable']) {
    if (mutation === 'disable') {
      check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).data.status === 'TEST_OK', 'PRE_CANCEL_PROBE');
      row = (await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).data;
    }
    const before = fixture('active-reader').sourceIds;
    check(before.length === 0, 'READER_QUIET');
    fixture('delay-on');
    try {
      const queuedAt = performance.now();
      const queued = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
      check(queued.status === 202, 'CANCEL_QUEUE');
      let ids;
      await until(async () => { ids = fixture('active-reader').sourceIds.filter(id => !before.includes(id)); return ids.length === 1; }, 'CANCEL_SOURCE_STARTED');
      const sourceId = ids[0];
      const observedAt = performance.now();
      const endpoint = mutation === 'cancel' ? '/discoveries/' + queued.data.jobId + '/cancel' : '/disable';
      const cancelledAt = performance.now();
      const changed = await send(path(row.id) + endpoint, {command: command(row.configRevision)}, row.configRevision);
      check(changed.status === 200, 'CANCEL_COMMAND');
      if (mutation === 'disable') row = changed.data;
      await until(async () => !fixture('active-reader').allSourceIds.includes(sourceId), 'CANCEL_SOURCE_TERMINATED');
      const endedAt = performance.now();
      check(endedAt - cancelledAt < 5000 && endedAt - queuedAt < 7000, 'CANCEL_BEFORE_NATURAL_COMPLETION');
      await until(async () => (await get(path(row.id) + '/discoveries/' + queued.data.jobId)).data.status === 'CANCELLED', 'CANCEL_JOB_TERMINAL');
      cancellations.push({mutation, jobId: queued.data.jobId, sourceId, observedBefore: true, absentAfter: true, queuedAt, observedAt, cancelledAt, endedAt, naturalDelayMs: 10000});
    } finally { fixture('delay-off'); }
  }
  check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'DISABLED_NO_PROBE');
  // 已禁用连接不允许重启；为后续撤权验证建立一个新合成连接。
  const renewed = await intake();
  row = (await send('/api/v1/connections', {displayName: '撤权 ' + runtime.runId, scopeSelection: scope, config, secretRef: renewed.data.secretRef, command: command()})).data;
  check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).data.status === 'TEST_OK', 'RENEW_PROBE');
  row = (await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).data;
  const renewedJob = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
  check(renewedJob.status === 202, 'RENEW_DISCOVERY');
  await until(async () => { done = (await get(path(row.id) + '/discoveries/' + renewedJob.data.jobId)).data; return done.status === 'SUCCEEDED'; }, 'RENEW_CATALOG');
  checks.push('EXPLICIT_CANCEL_AND_DISABLE_TERMINATE_EXACT_SOURCE');
  phase = 'inflight_permission';
  fixture('delay-on');
  try {
    const pending = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
    check(pending.status === 202, 'INFLIGHT_QUEUE');
    await until(async () => fixture('active-reader').sourceIds.length === 1, 'INFLIGHT_SOURCE_STARTED');
    fixture('readonly-off');
    fixture('delay-off');
    await until(async () => { const state = (await get(path(row.id) + '/discoveries/' + pending.data.jobId)).data; return state.status === 'FAILED' && !state.snapshotId; }, 'INFLIGHT_PERMISSION_RECHECK');
  } finally { fixture('readonly-on'); fixture('delay-off'); }
  checks.push('INFLIGHT_PERMISSION_CHANGE_NO_SNAPSHOT');
  phase = 'lease_fence';
  fixture('delay-on');
  try {
    const pending = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
    check(pending.status === 202, 'FENCE_QUEUE');
    let oldSource;
    await until(async () => { const ids = fixture('active-reader').sourceIds; oldSource = ids[0]; return ids.length === 1; }, 'FENCE_SOURCE_STARTED');
    const before = platform('job-state', pending.data.jobId).job;
    platform('job-fence', pending.data.jobId);
    fixture('delay-off');
    await until(async () => !fixture('active-reader').allSourceIds.includes(oldSource), 'OLD_FENCE_SOURCE_ENDED');
    await until(async () => { const current = platform('job-state', pending.data.jobId).job; return current.status === 'SUCCEEDED' && current.snapshotId && current.fence >= before.fence + 2; }, 'FENCE_RECOVERY');
  } finally { fixture('delay-off'); }
  checks.push('LEASE_FENCE_OLD_SOURCE_ENDED_NEW_ATTEMPT_SUCCEEDED');
  phase = 'source_revoke';
  fixture('revoke-read');
  try {
    check((await get('/api/v1/catalogs/' + done.snapshotId)).status === 403, 'REVOKED_HISTORY');
    const rejectedJob = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
    check(rejectedJob.status === 202, 'REVOKED_JOB_QUEUED');
    await until(async () => { const rejected = (await get(path(row.id) + '/discoveries/' + rejectedJob.data.jobId)).data; return rejected.status === 'PARTIAL' && !rejected.snapshotId; }, 'REVOKED_WORKER');
    const rejectedProbe = await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision);
    check(rejectedProbe.status === 200 && rejectedProbe.data.status === 'TEST_FAILED', 'REVOKED_PROBE');
    check((await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'REVOKED_ENABLE');
  } finally { fixture('restore-read'); }
  checks.push('SOURCE_REVOKE_PROBE_ENABLE_WORKER_HISTORY');
  phase = 'rotate_edit';
  const next = await intake();
  const rotated = await send(path(row.id) + '/rotate-secret', {secretRef: next.data.secretRef, command: command(row.configRevision)}, row.configRevision);
  check(rotated.status === 200 && rotated.data.state === 'DRAFT' && !rotated.data.probeFresh, 'ROTATE');
  row = rotated.data;
  check((await send('/api/v1/connection-secrets', next.body)).status === 422, 'CONSUMED_INTAKE_REPLAY');
  check((await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'STALE_PROBE');
  for (const mutation of [{config: {...config, profile: {...config.profile, port: 2485}}}, {scopeSelection: {organizationId: 'org-demo', siteIds: ['site-b']}}])
    check((await send(path(row.id), {...mutation, command: command(row.configRevision)}, row.configRevision, 'PATCH')).status === 422, 'TARGET_SCOPE_REBIND');
  const edited = await send(path(row.id), {displayName: '已编辑 ' + runtime.runId, command: command(row.configRevision)}, row.configRevision, 'PATCH');
  check(edited.status === 200 && !edited.data.probeFresh, 'DISPLAY_EDIT');
  check((await send(path(row.id), {displayName: 'stale revision', command: command(row.configRevision)}, row.configRevision, 'PATCH')).status === 409, 'STALE_REVISION');
  row = edited.data;
  checks.push('ROTATE_SINGLE_USE_STALE_PROBE_TARGET_SCOPE');
  phase = 'audit_rollback';
  check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).data.status === 'TEST_OK', 'AUDIT_PRE_PROBE');
  const beforeEnable = await get(path(row.id));
  const enableBody = {command: command(row.configRevision)};
  try {
    platform('audit-on');
    const failed = await send(path(row.id) + '/enable', enableBody, row.configRevision);
    check([500, 503].includes(failed.status), 'AUDIT_FAILURE_REQUIRED');
    const afterFailure = await get(path(row.id));
    check(afterFailure.data.state === beforeEnable.data.state && afterFailure.etag === beforeEnable.etag && afterFailure.data.lastProbeId === beforeEnable.data.lastProbeId, 'AUDIT_TRANSACTION_ROLLBACK');
  } finally { platform('audit-off'); }
  const replayed = await send(path(row.id) + '/enable', enableBody, row.configRevision);
  check(replayed.status === 409, 'AUDIT_PENDING_COMMAND_NO_DUPLICATE_IO');
  const retried = await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision);
  check(retried.status === 200 && retried.data.state === 'ACTIVE', 'AUDIT_NEW_COMMAND_RECOVERY');
  row = retried.data;
  checks.push('AUDIT_FAILURE_ROLLS_BACK_ENABLE_PENDING_REPLAY_REJECTED');
  phase = 'logout_fence';
  let logoutWitness;
  fixture('delay-on');
  try {
    const queuedAt = performance.now();
    const pending = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
    check(pending.status === 202, 'LOGOUT_QUEUE');
    let sourceId;
    await until(async () => { const ids = fixture('active-reader').sourceIds; sourceId = ids[0]; return ids.length === 1; }, 'LOGOUT_SOURCE_STARTED');
    const csrf = await get('/auth/csrf');
    const cancelledAt = performance.now();
    const logout = await context.request.post(origin + '/auth/logout', {headers: {Origin: origin, 'X-CSRF-TOKEN': csrf.data.requestToken}, maxRedirects: 0});
    check(logout.status() === 302, 'LOGOUT');
    await until(async () => !fixture('active-reader').allSourceIds.includes(sourceId), 'LOGOUT_SOURCE_ENDED');
    const endedAt = performance.now();
    check(endedAt - queuedAt < 7000 && endedAt - cancelledAt < 5000, 'LOGOUT_BEFORE_NATURAL_COMPLETION');
    await until(async () => { const job = platform('job-state', pending.data.jobId).job; return job.status === 'CANCELLED' && !job.snapshotId; }, 'LOGOUT_NO_SNAPSHOT');
    logoutWitness = {jobId: pending.data.jobId, sourceId, queuedAt, cancelledAt, endedAt};
  } finally { fixture('delay-off'); }
  const relogin = await context.newPage();
  await relogin.goto(origin + '/auth/login?returnUrl=%2Fdata%2Fconnections');
  if (new URL(relogin.url()).origin !== origin) {
    await relogin.locator('#username').fill(user.username);
    await relogin.locator('#password').fill(user.password);
    await relogin.locator('#kc-login').click();
  }
  await relogin.waitForURL(url => url.origin === origin && url.pathname === '/data/connections');
  await relogin.close();
  checks.push('LOGOUT_TERMINATES_SOURCE_AND_FENCES_SNAPSHOT');
  phase = 'disable';
  const disabled = await send(path(row.id) + '/disable', {command: command(row.configRevision)}, row.configRevision);
  check(disabled.status === 200 && disabled.data.state === 'DISABLED', 'DISABLE');
  row = disabled.data;
  check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'DISABLED_TEST');
  check((await get(path(row.id) + '/catalogs')).status === 403, 'DISABLED_CATALOG');
  checks.push('DISABLE_BLOCKS_PROBE_AND_HISTORY');
  console.log(JSON.stringify({status: 'PASS', taskId: runtime.taskId, runId: runtime.runId, tests: checks.length, skipped: 0, checks, cancellations, logoutWitness, connectionId: row.id}));
} catch (error) {
  console.log(JSON.stringify({status: 'FAIL', phase, reason: error instanceof Error && /^[A-Z_]+$/.test(error.message) ? error.message : error?.name ?? 'Error', tests: checks.length, checks}));
  process.exitCode = 1;
} finally { if (browser) await browser.close(); }
