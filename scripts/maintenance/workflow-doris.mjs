/** 本任务真实OIDC、Doris凭据与UI生命周期；不输出秘密、响应正文或截图。 */
import {readFile, realpath} from 'node:fs/promises';
import {resolve, sep} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
const root = resolve(import.meta.dirname, '../..');
const checks = [];
let browser, phase = 'runtime';
const check = (value, code) => { if (!value) throw new Error(code); };
const command = (revision = 0) => ({commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Doris合成验收'});
async function privateFile(path, base) {
  const absolute = resolve(path);
  check(absolute.startsWith(base + sep) && await realpath(absolute) === absolute, 'PRIVATE_PATH');
  return readFile(absolute, 'utf8');
}
try {
  const baseDir = resolve(root, '.tools/security/g4-m2-doris-01');
  const file = resolve(process.argv[2]);
  const runtime = JSON.parse(await privateFile(file, baseDir));
  check(runtime.taskId === 'G4-M2-DORIS-01' && /^doris-[a-f0-9]{12}$/.test(runtime.runId) && runtime.worktree === root, 'RUNTIME_IDENTITY');
  check(file === resolve(baseDir, runtime.runId, 'runtime.json'), 'RUNTIME_PATH');
  const fixture = mode => JSON.parse(execFileSync('python3', ['-B', resolve(root, 'scripts/maintenance/workflow_doris_fixture.py'), 'control', '--runtime', file, '--mode', mode], {cwd: root, timeout: 20000, maxBuffer: 65536}).toString());
  const origin = runtime.publicOrigin;
  check(origin === 'http://localhost:15100', 'ORIGIN');
  const realm = JSON.parse(await privateFile(runtime.realmFile, resolve(baseDir, runtime.runId)));
  const password = (await privateFile(runtime.sourceSecretFile, resolve(root, 'artifacts/workflow/G4-M2-DORIS-01'))).trim();
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
  const config = {type: 'DORIS', profile: {feHost: 'localhost', queryPort: 19030, catalog: 'internal', database: 'fixture', username: 'fixture_reader', tls: true}};
  const path = id => '/api/v1/connections/' + id;
  async function intake(purpose = 'DORIS_READONLY', selection = scope) {
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
  const otherScope = await intake('DORIS_READONLY', {organizationId: 'org-demo', siteIds: ['site-b']});
  check((await send('/api/v1/connections', {displayName: 'wrong-scope', scopeSelection: scope, config, secretRef: otherScope.data.secretRef, command: command()})).status === 422, 'CROSS_SCOPE');
  checks.push('DORIS_INTAKE_REPLAY_PURPOSE_SCOPE');
  phase = 'ui';
  await page.getByRole('link', {name: '新建连接', exact: true}).click();
  await page.getByRole('combobox', {name: /^数据源类型/}).selectOption('DORIS');
  await page.locator('input[name=displayName]').fill('Doris ' + runtime.runId);
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
  check(catalog.status === 200 && catalog.data.objects.length === 1 && catalog.data.objects[0].fields.length === 2, 'CATALOG');
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
    check(projected && ['feHost', 'catalog', 'database', 'username'].every(key => projected.config.profile[key] === 'redacted'), 'AUDITOR_DORIS_REDACTED');
  }
  check(JSON.stringify((await get(path(row.id))).data.config) === JSON.stringify(config), 'OPERATOR_TARGET_UNCHANGED');
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
    fixture('pause');
    try {
      const queued = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
      check(queued.status === 202, 'CANCEL_QUEUE');
      let ids;
      await until(async () => { ids = fixture('active-reader').sourceIds.filter(id => !before.includes(id)); return ids.length === 1; }, 'CANCEL_SOURCE_STARTED');
      const sourceId = ids[0];
      const endpoint = mutation === 'cancel' ? '/discoveries/' + queued.data.jobId + '/cancel' : '/disable';
      const changed = await send(path(row.id) + endpoint, {command: command(row.configRevision)}, row.configRevision);
      check(changed.status === 200, 'CANCEL_COMMAND');
      if (mutation === 'disable') row = changed.data;
      await until(async () => !fixture('active-reader').sourceIds.includes(sourceId), 'CANCEL_SOURCE_TERMINATED');
      await until(async () => (await get(path(row.id) + '/discoveries/' + queued.data.jobId)).data.status === 'CANCELLED', 'CANCEL_JOB_TERMINAL');
      cancellations.push({mutation, jobId: queued.data.jobId, sourceId, observedBefore: true, absentAfter: true});
    } finally { fixture('unpause'); }
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
  phase = 'source_revoke';
  fixture('revoke');
  try {
    check((await get('/api/v1/catalogs/' + done.snapshotId)).status === 403, 'REVOKED_HISTORY');
    const rejectedJob = await send(path(row.id) + '/discoveries', {command: command(row.configRevision)}, row.configRevision);
    check(rejectedJob.status === 202, 'REVOKED_JOB_QUEUED');
    await until(async () => (await get(path(row.id) + '/discoveries/' + rejectedJob.data.jobId)).data.status === 'FAILED', 'REVOKED_WORKER');
    const rejectedProbe = await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision);
    check(rejectedProbe.status === 200 && rejectedProbe.data.status === 'TEST_FAILED', 'REVOKED_PROBE');
    check((await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'REVOKED_ENABLE');
  } finally { fixture('grant'); }
  checks.push('SOURCE_REVOKE_PROBE_ENABLE_WORKER_HISTORY');
  phase = 'metadata_restore';
  fixture('backup-schema');
  fixture('restore-schema');
  const restored = await get('/api/v1/catalogs/' + done.snapshotId);
  check(restored.status === 200 && restored.data.objects.length === 1 && restored.data.objects[0].fields.length === 2, 'RESTORED_METADATA_VISIBLE');
  checks.push('EMPTY_SYNTHETIC_SCHEMA_RESTORE');
  phase = 'rotate_edit';
  const next = await intake();
  const rotated = await send(path(row.id) + '/rotate-secret', {secretRef: next.data.secretRef, command: command(row.configRevision)}, row.configRevision);
  check(rotated.status === 200 && rotated.data.state === 'DRAFT' && !rotated.data.probeFresh, 'ROTATE');
  row = rotated.data;
  check((await send('/api/v1/connection-secrets', next.body)).status === 422, 'CONSUMED_INTAKE_REPLAY');
  check((await send(path(row.id) + '/enable', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'STALE_PROBE');
  for (const mutation of [{config: {...config, profile: {...config.profile, queryPort: 19031}}}, {scopeSelection: {organizationId: 'org-demo', siteIds: ['site-b']}}])
    check((await send(path(row.id), {...mutation, command: command(row.configRevision)}, row.configRevision, 'PATCH')).status === 422, 'TARGET_SCOPE_REBIND');
  const edited = await send(path(row.id), {displayName: '已编辑 ' + runtime.runId, command: command(row.configRevision)}, row.configRevision, 'PATCH');
  check(edited.status === 200 && !edited.data.probeFresh, 'DISPLAY_EDIT');
  check((await send(path(row.id), {displayName: 'stale revision', command: command(row.configRevision)}, row.configRevision, 'PATCH')).status === 409, 'STALE_REVISION');
  row = edited.data;
  checks.push('ROTATE_SINGLE_USE_STALE_PROBE_TARGET_SCOPE');
  phase = 'disable';
  const disabled = await send(path(row.id) + '/disable', {command: command(row.configRevision)}, row.configRevision);
  check(disabled.status === 200 && disabled.data.state === 'DISABLED', 'DISABLE');
  row = disabled.data;
  check((await send(path(row.id) + '/test', {command: command(row.configRevision)}, row.configRevision)).status === 409, 'DISABLED_TEST');
  check((await get(path(row.id) + '/catalogs')).status === 403, 'DISABLED_CATALOG');
  checks.push('DISABLE_BLOCKS_PROBE_AND_HISTORY');
  console.log(JSON.stringify({status: 'PASS', taskId: runtime.taskId, runId: runtime.runId, tests: checks.length, skipped: 0, checks, cancellations, connectionId: row.id}));
} catch (error) {
  console.log(JSON.stringify({status: 'FAIL', phase, reason: error instanceof Error && /^[A-Z_]+$/.test(error.message) ? error.message : error?.name ?? 'Error', tests: checks.length, checks}));
  process.exitCode = 1;
} finally { if (browser) await browser.close(); }
