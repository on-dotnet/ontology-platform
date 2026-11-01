/** G4-M1 真实浏览器验收；私有凭据只驻留内存，不录制网络、会话或登录页面。 */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, realpath, lstat } from 'node:fs/promises';
import { resolve, relative, isAbsolute, sep, dirname } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

const help = `G4-M1 real browser acceptance (no service lifecycle operations)
Usage: node scripts/acceptance/g4-m1-browser.mjs --runtime-file PATH --evidence-dir PATH
Runtime JSON (private, under this checkout .tools/security):
{ "taskId":"G4-M1-RECOVERY-001", "runId":"synthetic-001",
  "publicOrigin":"http://localhost:15100", "realmFile":"ABS_PRIVATE_REALM_JSON",
  "sourceSecretFile":"ABS_PRIVATE_READER_PASSWORD", "browserChannel":"msedge",
  "scope":{"organizationId":"org-demo","siteIds":["site-a"]},
  "scenario":"baseline", "connectionId":null }
realmFile uses existing bootstrap shape: authority plus identities[g2-operator-ab,
g2-viewer-ab,g2-auditor-ab], each username/password. All auth origins must be loopback.
Source is fixed synthetic pg-source:5432/fixture/fixture_reader, VerifyFull, production.
Scenarios: baseline, layout-only, source-unavailable, source-timeout, catalog-cancel, source-permission-limited.
layout-only logs real resize geometry/hit testing and four stable viewport screenshots.
It does not run U01-U05 or change CSS, navigation state, animation duration or fixture data.
Fault scenarios require Master to establish actual fixture fault and supply connectionId.
source-timeout requires Master to pause only the task PG source for <=20s with finally
unpause; NETWORK must PASS, TLS must FAIL/source_unavailable after >=8s, and UI must
show failure plus an enabled retry action. Immediate connection refusal is not timeout.
Evidence must be below artifacts/g4-m1-recovery-001 or docs/evidence/G4-M1-RECOVERY-001.
Each run creates a unique directory. No passwords, SecretRef, CSRF, raw errors or URLs
are persisted. At most 4 masked screenshots per run; keep <=12 in final package.
Exit 0: all selected cases PASS; 1: FAIL; 2: NOT_RUN/incomplete. Static checks are not
product acceptance. U05 retains NOT_RUN until all required distinct states are observed.`;
if (process.argv.includes('--help')) { process.stdout.write(help + '\n'); process.exit(0); }
const root = resolve(import.meta.dirname, '../..');
const cases = Object.fromEntries(['U01','U02','U03','U04','U05','U06'].map(id => [`M1-${id}`, { status: 'NOT_RUN', observed: [], reason: 'not_executed' }]));
const report = { schemaVersion: 1, taskId: 'G4-M1-RECOVERY-001', startedAtUtc: new Date().toISOString(), cases, http: [], screenshots: [], productExecution: false };
const sensitive = new Set();
let browser, output, activeCase, phase = 'configuration';
const contexts = [];
let expectation;
/** 固定错误码取代异常正文，避免 Playwright 调用日志泄漏输入。 */
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
function requireTrue(condition, code) { if (!condition) { const error = new Error(); error.safeCode = code; throw error; } }
function note(name) { if (activeCase) cases[activeCase].observed.push(name); }
function command(revision) { return { commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Synthetic G4 recovery acceptance' }; }
function within(base, path) { const value = relative(base, path); return value !== '' && value !== '..' && !value.startsWith('..' + sep) && !isAbsolute(value); }
/** 私有文件必须真实落于当前树，且没有组或其他用户访问权限。 */
async function privateFile(path) {
  requireTrue(typeof path === 'string' && isAbsolute(path), 'private_path_required');
  const actual = await realpath(path);
  requireTrue(within(await realpath(resolve(root, '.tools/security')), actual), 'private_path_denied');
  const stat = await lstat(actual);
  requireTrue(stat.isFile() && (stat.mode & 0o077) === 0 && stat.size < 1024 * 1024, 'private_file_permissions_or_size');
  return readFile(actual, 'utf8');
}
function remember(value) { if (typeof value === 'string' && value.length >= 8) sensitive.add(value); }
function containsSecret(text) { return [...sensitive].some(value => text.includes(value)); }
/** 仅将状态码和固定路由模板写入证据，响应正文仅用于内存断言。 */
async function http(user, method, path, template, data, headers = {}) {
  const started = Date.now();
  const response = await user.api.fetch(user.origin + path, { method, data, headers: { ...headers, Connection: 'close' }, maxRedirects: 0, timeout: 20000 });
  report.http.push({ method, route: template, status: response.status(), durationMs: Date.now() - started });
  return response;
}
async function runCase(id, action) {
  activeCase = id; phase = id;
  try { await action(); cases[id].status = 'PASS'; delete cases[id].reason; }
  catch (error) { const failure = safeFailure(error, 'browser_or_transport_error'); cases[id].status = 'FAIL'; cases[id].reason = failure.code; cases[id].failure = failure; cases[id].phase = phase; }
  finally { activeCase = null; }
}
/** 输出根目录也拒绝符号链接；每次唯一目录保留先前失败。 */
async function evidenceDirectory(path) {
  const selected = resolve(path);
  requireTrue(['artifacts/g4-m1-recovery-001', 'docs/evidence/G4-M1-RECOVERY-001'].some(base => within(resolve(root, base), selected) || resolve(root, base) === selected), 'evidence_path_denied');
  for (let current = selected; current !== root; current = dirname(current)) {
    const stat = await lstat(current).catch(error => { if (error.code === 'ENOENT') return null; throw error; });
    requireTrue(!stat?.isSymbolicLink(), 'evidence_symlink_denied');
  }
  await mkdir(selected, { recursive: true });
  const directory = resolve(selected, 'browser-' + randomUUID());
  await mkdir(directory, { mode: 0o700 });
  return directory;
}
try {
  const args = process.argv.slice(2);
  requireTrue(args.length === 4 && args[0] === '--runtime-file' && args[2] === '--evidence-dir', 'arguments_invalid');
  output = await evidenceDirectory(args[3]);
  const runtime = JSON.parse(await privateFile(resolve(args[1])));
  requireTrue(runtime.taskId === report.taskId && /^[A-Za-z0-9_-]{1,80}$/.test(runtime.runId), 'runtime_identity_invalid');
  requireTrue(runtime.publicOrigin === 'http://localhost:15100', 'public_origin_denied');
  requireTrue(runtime.scope?.organizationId === 'org-demo' && JSON.stringify(runtime.scope.siteIds) === '["site-a"]', 'synthetic_scope_required');
  const scenario = runtime.scenario ?? 'baseline';
  requireTrue(['baseline', 'layout-only', 'source-unavailable', 'source-timeout', 'catalog-cancel', 'source-permission-limited'].includes(scenario), 'scenario_invalid');
  requireTrue(['baseline', 'layout-only'].includes(scenario) || /^[A-Za-z0-9_-]{1,100}$/.test(runtime.connectionId), 'fault_connection_required');
  requireTrue(!runtime.browserChannel || runtime.browserChannel === 'msedge', 'browser_channel_denied');
  const realm = JSON.parse(await privateFile(runtime.realmFile));
  const authority = new URL(realm.authority);
  requireTrue(authority.protocol === 'http:' && authority.hostname === 'localhost' && !authority.username && !authority.password, 'authority_origin_denied');
  const sourceSecret = (await privateFile(runtime.sourceSecretFile)).trimEnd();
  requireTrue(sourceSecret.length >= 8, 'source_secret_invalid');
  remember(sourceSecret); remember(realm.clientSecret);
  for (const value of Object.values(realm.identities ?? {})) remember(value.password);
  report.runId = runtime.runId; report.scenario = scenario;
  report.driverSha256 = createHash('sha256').update(await readFile(import.meta.filename)).digest('hex');
  const require = createRequire(resolve(root, 'apps/web/package.json'));
  const { chromium, expect } = require('@playwright/test'); expectation = expect;
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  report.productExecution = true;
  const allowedOrigins = new Set([runtime.publicOrigin, authority.origin]);
  async function context() {
    const result = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block', extraHTTPHeaders: { Connection: 'close' } });
    contexts.push(result);
    // 仅观察真实 DOM 状态变化；不延迟、替换或伪造服务端响应。
    await result.addInitScript(() => {
      window.__g4LoadingObserved = false; window.__g4PendingCategories = [];
      addEventListener('DOMContentLoaded', () => {
        const observe = () => {
          const categories = new Set(window.__g4PendingCategories);
          for (const node of document.querySelectorAll('[role=status]')) {
            const bounds = node.getBoundingClientRect(); const style = getComputedStyle(node);
            if (!node.getClientRects().length || bounds.bottom <= 0 || bounds.top >= innerHeight || style.display === 'none' || style.visibility !== 'visible') continue;
            const text = node.textContent?.trim() ?? '';
            if (/^正在读取/.test(text)) categories.add('READ_LOADING');
            if (/^正在测试|^测试中$/.test(text)) categories.add('PROBE_RUNNING');
            if (/^正在执行/.test(text)) categories.add('EXECUTION_RUNNING');
            if (/^正在(?:保存|录入|启用|禁用|轮换|刷新)/.test(text)) categories.add('MUTATION_RUNNING');
            if (/^目录发现：(?:运行中|等待执行)/.test(text)) categories.add('CATALOG_PENDING');
          }
          window.__g4PendingCategories = [...categories]; window.__g4LoadingObserved = categories.size > 0;
        };
        new MutationObserver(observe).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true }); observe();
      }, { once: true });
    });
    // 浏览器只访问当前合成应用和已配置的本地身份提供者。
    await result.route('**/*', route => allowedOrigins.has(new URL(route.request().url()).origin) ? route.continue() : route.abort());
    result.setDefaultTimeout(15000); return result;
  }
  async function identity(label) {
    const previousPhase = phase;
    const identityStep = stage => { phase = 'oidc_' + label + '_' + stage; };
    identityStep('user_lookup');
    const user = realm.identities['g2-' + label]; requireTrue(user?.username && user?.password, 'bootstrap_identity_missing');
    identityStep('context_create'); const session = await context();
    identityStep('page_create'); const page = await session.newPage();
    identityStep('login_navigation'); await page.goto(runtime.publicOrigin + '/auth/login?returnUrl=%2Fdata%2Fconnections');
    identityStep('username_input'); await page.locator('#username').fill(user.username);
    identityStep('password_input'); await page.locator('#password').fill(user.password);
    identityStep('login_submit'); await page.locator('#kc-login').click();
    identityStep('callback_navigation'); await page.waitForURL(url => url.origin === runtime.publicOrigin && url.pathname === '/data/connections');
    identityStep('cookie_check'); const cookie = (await session.cookies()).find(item => item.name === '.OntologyPlatform.Session');
    requireTrue(cookie?.httpOnly && cookie.sameSite === 'Lax', 'real_session_cookie_missing'); remember(cookie.value);
    const actor = { context: session, page, api: session.request, origin: runtime.publicOrigin };
    identityStep('csrf_request'); const csrf = await http(actor, 'GET', '/auth/csrf', '/auth/csrf'); requireTrue(csrf.status() === 200, 'csrf_issue_failed');
    identityStep('csrf_decode'); const token = (await csrf.json()).requestToken; requireTrue(typeof token === 'string', 'csrf_missing'); remember(token);
    actor.headers = { Origin: actor.origin, 'X-CSRF-TOKEN': token, Connection: 'close' };
    phase = previousPhase; return actor;
  }
  async function jsonResponse(response, expected) { requireTrue(response.status() === expected, 'unexpected_http_status'); return response.json(); }
  async function noLeak(page) {
    const visible = await page.locator('body').innerText();
    const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
    requireTrue(!containsSecret(visible) && !containsSecret(storage) && !containsSecret(page.url()), 'sensitive_browser_leak');
    requireTrue(!/secretRef|secretValue|X-CSRF-TOKEN/i.test(storage), 'sensitive_storage_key');
  }
  async function screenshot(page, name) {
    requireTrue(report.screenshots.length < 4, 'screenshot_budget'); await noLeak(page);
    requireTrue(new URL(page.url()).pathname.startsWith('/data/connections'), 'screenshot_route_denied');
    requireTrue((await page.locator('input[type=password]').evaluateAll(inputs => inputs.every(input => input.value === ''))), 'screenshot_secret_input');
    const file = name + '.png'; await page.screenshot({ path: resolve(output, file), fullPage: false, animations: 'disabled', mask: [page.locator('input[type=password]')] });
    report.screenshots.push(file);
  }
  /** 保留实际布局数值与命中布尔，不保存页面文字、URL或任意属性。 */
  async function layoutEvidence(page, theme, size, moment) {
    const evidence = await page.evaluate(() => {
      const rectangle = element => {
        if (!element) return null;
        const value = element.getBoundingClientRect();
        return Object.fromEntries(['x','y','width','height','left','right','top','bottom'].map(key => [key, Math.round(value[key] * 100) / 100]));
      };
      const navigation = document.querySelector('#platform-navigation');
      const selectors = {
        heading: '.connections-workspace h1',
        type_filter: '.connection-actions label:first-child select',
        state_filter: '.connection-actions label:nth-child(2) select',
        create_action: '.connection-heading a[href="/data/connections/new"]',
        first_connection_name: '.connection-scroll tbody tr:first-child td:first-child a',
      };
      const targets = Object.entries(selectors).map(([name, selector]) => {
        const all = document.querySelectorAll(selector); const element = all[0];
        const bounds = rectangle(element);
        if (!element || !bounds) return { name, count: all.length, bounds: null, hits: [], unobstructed: false };
        const actual = element.getBoundingClientRect();
        let left = Math.max(0, actual.left), right = Math.min(innerWidth, actual.right);
        let top = Math.max(0, actual.top), bottom = Math.min(innerHeight, actual.bottom);
        // 合法表格横向滚动只检查当前裁剪区，不把隐藏列当作页面遮挡。
        for (let parent = element.parentElement; parent; parent = parent.parentElement) {
          const style = getComputedStyle(parent); const box = parent.getBoundingClientRect();
          if (['auto','scroll','hidden','clip'].includes(style.overflowX)) { left = Math.max(left, box.left); right = Math.min(right, box.right); }
          if (['auto','scroll','hidden','clip'].includes(style.overflowY)) { top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom); }
        }
        const hits = right > left && bottom > top ? [0.2,0.5,0.8].map(ratio => {
          const x = left + (right - left) * ratio; const y = top + (bottom - top) / 2;
          const hit = document.elementFromPoint(x, y);
          return { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100, targetOrDescendant: !!hit && (hit === element || element.contains(hit)), hitTag: hit?.tagName ?? null };
        }) : [];
        return { name, count: all.length, bounds, hits, unobstructed: hits.length === 3 && hits.every(hit => hit.targetOrDescendant) };
      });
      return { viewport: { width: innerWidth, height: innerHeight }, scroll: { x: scrollX, y: scrollY }, documentWidth: document.documentElement.scrollWidth,
        sidebar: { count: document.querySelectorAll('#platform-navigation').length, bounds: rectangle(navigation), open: navigation?.classList.contains('is-open') ?? false, inert: navigation?.inert ?? false, transform: navigation ? getComputedStyle(navigation).transform : null },
        topbarCount: document.querySelectorAll('.topbar').length, targets };
    });
    report.layout ??= []; report.layout.push({ theme, size, moment, ...evidence }); return evidence;
  }
  /** 等待真实抽屉关闭和连续三帧几何稳定；不覆盖产品CSS或强行隐藏元素。 */
  async function settleLayout(page, narrow) {
    await page.evaluate(async () => {
      window.scrollTo(0, 0); await document.fonts.ready;
      window.__g4LayoutSample = null; window.__g4LayoutStableFrames = 0;
      await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
    });
    if (narrow) await page.waitForFunction(() => {
      const sidebar = document.querySelector('#platform-navigation');
      return sidebar && !sidebar.classList.contains('is-open') && sidebar.inert && sidebar.getBoundingClientRect().right <= 0;
    }, undefined, { polling: 'raf', timeout: 5000 });
    await page.waitForFunction(() => {
      const selected = ['#platform-navigation','.shell-body','.topbar','.connections-workspace','.connection-actions','.connection-scroll'];
      const sample = JSON.stringify(selected.map(selector => {
        const element = document.querySelector(selector); if (!element) return null;
        const value = element.getBoundingClientRect(); return [value.x,value.y,value.width,value.height];
      }));
      window.__g4LayoutStableFrames = sample === window.__g4LayoutSample ? window.__g4LayoutStableFrames + 1 : 0;
      window.__g4LayoutSample = sample;
      return window.__g4LayoutStableFrames >= 3;
    }, undefined, { polling: 'raf', timeout: 5000 });
  }
  /** 使用控件名或唯一语义定位；选择后仍验证实际值与可编辑状态。 */
  async function choose(control, value, step) {
    phase = step;
    await expectation(control).toHaveCount(1);
    await expectation(control).toBeEnabled();
    await control.selectOption(value);
    await expectation(control).toHaveValue(value);
  }
  async function clicked(page, label, path, method, status, options = {}) {
    phase = options.phase ?? label;
    if (options.observePending) await page.evaluate(() => { window.__g4PendingCategories = []; });
    const started = performance.now();
    let responseArrived = false; let pendingBeforeResponse = false; let pendingCategories = [];
    const [response] = await Promise.all([
      page.waitForResponse(value => new URL(value.url()).pathname === path && value.request().method() === method, { timeout: options.timeoutMs ?? 15000 }).then(value => { responseArrived = true; return value; }),
      (async () => {
        await page.getByRole('button', { name: label, exact: true }).click();
        if (options.observePending) {
          await page.waitForFunction(() => window.__g4PendingCategories?.includes('PROBE_RUNNING'), undefined, { polling: 'raf', timeout: 3000 });
          pendingBeforeResponse = !responseArrived;
          pendingCategories = await page.evaluate(() => window.__g4PendingCategories.filter(value => ['READ_LOADING','PROBE_RUNNING','EXECUTION_RUNNING','MUTATION_RUNNING','CATALOG_PENDING'].includes(value)));
        }
      })(),
    ]);
    report.http.push({ method, route: path.replace(/\/connections\/[^/]+/, '/connections/{id}'), status: response.status(), durationMs: Math.round(performance.now() - started),
      ...(options.observePending ? { pendingBeforeResponse, pendingCategories } : {}) });
    return jsonResponse(response, status);
  }
  const operator = await identity('operator-ab'); const page = operator.page;
  let connectionId = runtime.connectionId;
  const observedU05 = new Set();
  const connectionPath = () => '/api/v1/connections/' + connectionId;
  async function current() { const response = await http(operator, 'GET', connectionPath(), '/connections/{id}'); return { data: await jsonResponse(response, 200), etag: response.headers().etag }; }
  async function stages(probe) {
    requireTrue(probe.status === 'TEST_OK' && ['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].every(name => probe.stages.some(stage => stage.name === name && stage.status === 'PASS')), 'probe_stages_not_pass');
    await expectation(page.getByRole('region', { name: '连接测试报告' }).locator('ol li')).toHaveCount(5); observedU05.add('five_probe_stages');
  }
  async function discover(expectedStatus) {
    const job = await clicked(page, '发现目录', connectionPath() + '/discoveries', 'POST', 202);
    requireTrue(typeof job.jobId === 'string', 'durable_job_missing');
    await page.waitForURL(url => url.searchParams.get('job') === job.jobId); await page.reload();
    let result = job;
    for (let count = 0; count < 30 && ['QUEUED','RUNNING'].includes(result.status); count++) {
      await new Promise(done => setTimeout(done, 1000));
      result = await jsonResponse(await http(operator, 'GET', connectionPath() + '/discoveries/' + job.jobId, '/connections/{id}/discoveries/{jobId}'), 200);
    }
    requireTrue(result.status === expectedStatus, 'catalog_terminal_state_unexpected'); observedU05.add('job_refresh_recovery');
    return result;
  }
  if (scenario === 'baseline') {
    await runCase('M1-U02', async () => {
      const anonymous = await context(); const guest = { api: anonymous.request, origin: runtime.publicOrigin };
      requireTrue((await http(guest, 'GET', '/api/v1/connections', '/connections')).status() === 401, 'anonymous_read_not_401');
      requireTrue((await http(guest, 'POST', '/api/v1/connection-secrets', '/connection-secrets', '{', { 'Content-Type': 'application/json' })).status() === 401, 'anonymous_prebinding_not_401');
      note('anonymous_real_http_401');
      for (const label of ['viewer-ab', 'auditor-ab']) {
        const actor = await identity(label);
        requireTrue((await http(actor, 'POST', '/api/v1/connections', '/connections', '{', { ...actor.headers, 'Content-Type': 'application/json' })).status() === 403, 'role_write_not_403');
        note(label + '_real_http_403'); await actor.context.close();
      }
      requireTrue((await http(operator, 'POST', '/api/v1/connection-secrets', '/connection-secrets', '{', { Origin: operator.origin, 'Content-Type': 'application/json' })).status() === 403, 'missing_csrf_not_403');
      note('authenticated_csrf_denied_before_binding');
    });
    await runCase('M1-U03', async () => {
      await page.goto(operator.origin + '/data/connections/new');
      const profiles = {
        POSTGRESQL: { host: 'pg-source', port: '5432', database: 'fixture', username: 'fixture_reader', allowedSchemas: 'production' },
        ORACLE: { host: 'pg-source', port: '1521', serviceName: 'fixture', username: 'fixture_reader', allowedOwners: 'production' },
        DORIS: { feHost: 'pg-source', queryPort: '9030', catalog: 'fixture', database: 'fixture', username: 'fixture_reader' },
        TDENGINE: { wsUrl: 'wss://pg-source', database: 'fixture' },
        WEB_API: { baseOrigin: 'https://pg-source', operationId: 'fixture_read', approvedPath: '/fixture', hostPolicyRef: 'synthetic_policy' },
      };
      const fields = { POSTGRESQL: 'username', ORACLE: 'serviceName', DORIS: 'feHost', TDENGINE: 'wsUrl', WEB_API: 'baseOrigin' };
      for (const [type, field] of Object.entries(fields)) {
        await choose(page.getByRole('combobox', { name: /^数据源类型/ }), type, 'U03_' + type + '_select');
        phase = 'U03_' + type + '_field_presence';
        await expectation(page.locator('input[name=' + field + ']')).toBeVisible();
        phase = 'U03_' + type + '_invalid_name';
        await page.locator('input[name=displayName]').fill('');
        await page.getByRole('button', { name: '校验配置', exact: true }).click();
        await expectation(page.locator('input[name=displayName]')).toHaveAttribute('aria-invalid', 'true');
        phase = 'U03_' + type + '_valid_configuration';
        await page.locator('input[name=displayName]').fill('Synthetic ' + type);
        for (const [key, value] of Object.entries(profiles[type])) await page.locator('input[name=' + key + ']').fill(value);
        await page.getByRole('button', { name: '校验配置', exact: true }).click();
        await expectation(page.getByText('配置格式校验通过；连接结果以实际测试为准。')).toBeVisible();
        if (type !== 'POSTGRESQL') {
          phase = 'U03_' + type + '_unsupported_actions';
          await expectation(page.getByRole('button', { name: '测试草稿', exact: true })).toBeDisabled();
          await expectation(page.getByRole('button', { name: '保存为草稿', exact: true })).toBeDisabled();
          await expectation(page.getByText('配置可校验；此类型尚未支持连接测试与保存。')).toBeVisible();
        }
        phase = 'U03_' + type + '_negative_field';
        const negativeKey = type === 'POSTGRESQL' || type === 'ORACLE' ? 'port' : type === 'DORIS' ? 'queryPort' : type === 'TDENGINE' ? 'wsUrl' : 'baseOrigin';
        await page.locator('input[name=' + negativeKey + ']').fill(negativeKey.toLowerCase().includes('port') ? '65536' : 'not-a-url');
        await page.getByRole('button', { name: '校验配置', exact: true }).click();
        await expectation(page.locator('input[name=' + negativeKey + ']')).toHaveAttribute('aria-invalid', 'true');
        note(type + '_distinct_fields_positive_and_negative_format');
      }
    });
    await runCase('M1-U01', async () => {
      await page.goto(operator.origin + '/data/connections');
      await choose(page.getByRole('combobox', { name: /^类型/ }), 'ORACLE', 'U01_list_filter');
      await expectation(page.getByText('当前筛选下暂无连接。', { exact: false })).toBeVisible(); observedU05.add('empty_list');
      phase = 'U01_create_navigation';
      await page.getByRole('link', { name: '新建连接', exact: true }).click();
      await choose(page.getByRole('combobox', { name: /^数据源类型/ }), 'POSTGRESQL', 'U01_pg_type');
      phase = 'U01_pg_configuration';
      const name = 'G4 synthetic ' + runtime.runId + ' ' + randomUUID().slice(0, 8);
      await page.locator('input[name=displayName]').fill(name);
      for (const [field, value] of Object.entries({ host: 'pg-source', port: '5432', database: 'fixture', username: 'fixture_reader', allowedSchemas: 'production' })) await page.locator('input[name=' + field + ']').fill(value);
      await choose(page.locator('select[name=sslMode]'), 'VerifyFull', 'U01_verify_full');
      await choose(page.getByRole('combobox', { name: /^所属厂区/ }), 'org-demo/site-a', 'U01_scope');
      phase = 'U01_private_input_refresh';
      await page.getByLabel('重新输入密码', { exact: true }).fill(sourceSecret); await noLeak(page); await page.reload();
      await expectation(page.locator('input[name=displayName]')).toHaveValue(name);
      await expectation(page.getByLabel('重新输入密码', { exact: true })).toHaveValue('');
      await page.getByLabel('重新输入密码', { exact: true }).fill(sourceSecret);
      const receipt = await clicked(page, '安全录入凭据', '/api/v1/connection-secrets', 'POST', 201); remember(receipt.secretRef);
      await noLeak(page); await stages(await clicked(page, '测试草稿', '/api/v1/connections/tests', 'POST', 200));
      if (await page.evaluate(() => window.__g4LoadingObserved === true)) observedU05.add('actual_loading_dom');
      const created = await clicked(page, '保存为草稿', '/api/v1/connections', 'POST', 201);
      requireTrue(/^[A-Za-z0-9_-]{1,100}$/.test(created.id), 'connection_id_invalid');
      connectionId = created.id; report.connectionId = connectionId;
      requireTrue(created.state === 'DRAFT' && !containsSecret(JSON.stringify(created)), 'create_state_or_leak');
      await page.waitForURL(url => url.pathname === '/data/connections/' + connectionId); await page.reload();
      await expectation(page.getByRole('heading', { name, exact: true })).toBeVisible();
      await stages(await clicked(page, '重新测试', connectionPath() + '/test', 'POST', 200));
      await clicked(page, '明确启用连接', connectionPath() + '/enable', 'POST', 200);
      const job = await discover('SUCCEEDED'); requireTrue(job.snapshotId, 'snapshot_missing');
      await expectation(page.getByRole('heading', { name: '目录快照历史', exact: true })).toBeVisible();
      await page.locator('.catalog-history li button').first().click();
      await expectation(page.getByRole('region', { name: '目录快照详情' })).toContainText('heat_event');
      note('real_pg_draft_probe_create_enable_catalog_refresh');
      // 独立冲突用例失败仍保留，随后恢复权威详情完成主生命周期。
      await runCase('M1-U04', async () => {
        const before = await current(); const mine = name + ' local'; const theirs = name + ' server';
        await page.locator('input[name=displayName]').fill(mine);
        const updated = await http(operator, 'PATCH', connectionPath(), '/connections/{id}', { displayName: theirs, command: command(before.data.configRevision) }, { ...operator.headers, 'If-Match': before.etag });
        await jsonResponse(updated, 200);
        await clicked(page, '保存配置', connectionPath(), 'PATCH', 409);
        await expectation(page.getByRole('alert').filter({ hasText: '连接已被修改' })).toBeVisible();
        await expectation(page.locator('input[name=displayName]')).toHaveValue(mine);
        await page.getByRole('button', { name: '刷新详情', exact: true }).click();
        await expectation(page.getByRole('heading', { name: theirs, exact: true })).toBeVisible();
        await expectation(page.locator('input[name=displayName]')).toHaveValue(mine);
        await expectation(page.locator('.connection-comparison pre').first()).toContainText(theirs);
        await noLeak(page); note('real_409_latest_server_and_retained_nonsecret_edit');
      });
      activeCase = 'M1-U01'; await page.reload();
      await page.locator('input[name=displayName]').fill(name + ' edited');
      const changed = await clicked(page, '保存配置', connectionPath(), 'PATCH', 200);
      requireTrue(changed.state === 'DRAFT' && !changed.probeFresh, 'edit_did_not_invalidate_probe');
      await stages(await clicked(page, '重新测试', connectionPath() + '/test', 'POST', 200));
      await clicked(page, '明确启用连接', connectionPath() + '/enable', 'POST', 200);
      await page.getByRole('button', { name: '禁用连接', exact: true }).click();
      const disabled = await clicked(page, '确认禁用', connectionPath() + '/disable', 'POST', 200);
      requireTrue(disabled.state === 'DISABLED', 'disable_state'); await page.reload();
      await expectation(page.getByText('此连接已禁用，生命周期已终止。如需再次连接，请新建连接并重新测试。')).toBeVisible();
      await noLeak(page); note('edit_invalidates_probe_retest_enable_disable_refresh');
    });
  }
  if (['baseline', 'layout-only'].includes(scenario)) {
    await runCase('M1-U06', async () => {
      await page.goto(operator.origin + '/data/connections'); await expectation(page.getByRole('heading', { name: '数据源', exact: true })).toBeVisible();
      for (const theme of ['light', 'dark']) {
        phase = 'U06_' + theme + '_theme_toggle';
        if (await page.locator('html').getAttribute('data-theme') !== theme) await page.getByRole('button', { name: '切换深浅主题', exact: true }).click();
        await expectation(page.locator('html')).toHaveAttribute('data-theme', theme);
        for (const [width, height, size] of [[1440,1000,'wide'], [390,844,'narrow']]) {
          phase = 'U06_' + theme + '_' + size + '_viewport';
          await page.setViewportSize({ width, height });
          await layoutEvidence(page, theme, size, 'after_resize_before_settle');
          phase = 'U06_' + theme + '_' + size + '_layout_stability';
          await settleLayout(page, size === 'narrow');
          const geometry = await layoutEvidence(page, theme, size, 'stable_before_screenshot');
          requireTrue(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'page_horizontal_overflow');
          phase = 'U06_' + theme + '_' + size + '_create_action';
          await expectation(page.getByRole('link', { name: '新建连接', exact: true })).toBeVisible();
          phase = 'U06_' + theme + '_' + size + '_visible_copy';
          requireTrue(!/TODO|Mock|组件测试|研发提示|NOT_RUN/.test(await page.locator('main').innerText()), 'development_hint_visible');
          phase = 'U06_' + theme + '_' + size + '_screenshot';
          await screenshot(page, theme + '-' + size);
          phase = 'U06_' + theme + '_' + size + '_hit_testing';
          requireTrue(geometry.sidebar.count === 1 && geometry.topbarCount === 1, 'duplicate_shell_elements');
          requireTrue(geometry.targets.every(target => target.count === 1 && target.unobstructed), 'main_content_obstructed');
          if (size === 'narrow') requireTrue(geometry.sidebar.bounds.right <= 0 && !geometry.sidebar.open && geometry.sidebar.inert, 'closed_sidebar_overlaps_content');
          note(theme + '_' + size + '_stable_viewport_and_unobstructed_controls');
        }
      }
      note('screenshots_require_independent_visual_review');
    });
  } else {
    await runCase('M1-U05', async () => {
      await page.goto(operator.origin + '/data/connections/' + connectionId);
      await expectation(page.getByRole('button', { name: '刷新详情', exact: true })).toBeVisible();
      if (scenario === 'source-timeout') {
        const probe = await clicked(page, '重新测试', connectionPath() + '/test', 'POST', 200, { timeoutMs: 20000, observePending: true, phase: 'U05_source_timeout_probe' });
        const request = report.http.at(-1);
        const network = probe.stages.find(stage => stage.name === 'NETWORK');
        const tls = probe.stages.find(stage => stage.name === 'TLS');
        const elapsed = Date.parse(probe.completedAtUtc) - Date.parse(probe.startedAtUtc);
        // 仅固定分类、数值和布尔进入证据，既保留期限误分类又不复制响应正文。
        report.timeoutObservation = { clientDurationMs: request.durationMs, reportDurationMs: Number.isFinite(elapsed) ? elapsed : null,
          tlsDurationMs: Number.isFinite(tls?.durationMs) ? tls.durationMs : null, networkPassed: network?.status === 'PASS', tlsFailed: tls?.status === 'FAIL',
          probeStatus: ['TEST_FAILED','CANCELLED','TEST_OK','RUNNING'].includes(probe.status) ? probe.status : 'UNKNOWN',
          diagnosticCode: ['connection_source_unavailable','connection_cancelled','connection_tls_untrusted'].includes(tls?.diagnosticCode) ? tls.diagnosticCode : 'OTHER',
          pendingBeforeResponse: request.pendingBeforeResponse, pendingCategories: request.pendingCategories };
        requireTrue(request.pendingBeforeResponse && request.pendingCategories.includes('PROBE_RUNNING'), 'timeout_loading_not_observed_before_response');
        observedU05.add('actual_probe_pending_before_response');
        requireTrue(network?.status === 'PASS' && tls?.status === 'FAIL' && tls.durationMs >= 8000 && elapsed >= 8000 && request.durationMs >= 8000, 'timeout_duration_or_tcp_tls_stage_not_proven');
        requireTrue(probe.status === 'TEST_FAILED' && tls.diagnosticCode === 'connection_source_unavailable', 'timeout_terminal_classification_unexpected');
        phase = 'U05_source_timeout_visible_failure';
        await expectation(page.getByRole('region', { name: '连接测试报告' })).toContainText('测试失败');
        await expectation(page.getByText('源服务暂不可用，请检查服务后重试。')).toBeVisible();
        phase = 'U05_source_timeout_retry_action';
        await expectation(page.getByRole('button', { name: '重新测试', exact: true })).toBeVisible();
        await expectation(page.getByRole('button', { name: '重新测试', exact: true })).toBeEnabled();
        observedU05.add('real_tcp_connected_tls_timeout_at_least_eight_seconds');
        observedU05.add('timeout_failure_and_enabled_retry_action_no_second_paused_probe');
      } else if (scenario === 'source-unavailable') {
        const probe = await clicked(page, '重新测试', connectionPath() + '/test', 'POST', 200);
        requireTrue(probe.status === 'TEST_FAILED' && probe.stages.some(stage => stage.diagnosticCode === 'connection_source_unavailable'), 'source_fault_not_observed');
        await expectation(page.getByText('源服务暂不可用，请检查服务后重试。')).toBeVisible(); observedU05.add('source_unavailable_error');
      } else if (scenario === 'source-permission-limited') {
        await discover('PARTIAL');
        await expectation(page.getByText('发现未完整完成，不能将此结果视为没有对象。此前快照仅供历史参考。')).toBeVisible(); observedU05.add('partial_catalog');
      } else {
        const job = await clicked(page, '发现目录', connectionPath() + '/discoveries', 'POST', 202);
        if (await page.getByRole('button', { name: '取消发现', exact: true }).count() === 0) { note('job_completed_before_cancel_action'); return; }
        await clicked(page, '取消发现', connectionPath() + '/discoveries/' + job.jobId + '/cancel', 'POST', 200);
        await page.reload();
        const readback = await jsonResponse(await http(operator, 'GET', connectionPath() + '/discoveries/' + job.jobId, '/connections/{id}/discoveries/{jobId}'), 200);
        requireTrue(readback.status === 'CANCELLED', 'cancel_not_durable'); observedU05.add('cancelled_job_refresh');
      }
      await noLeak(page);
    });
  }
  cases['M1-U05'].observed.push(...observedU05);
  if (cases['M1-U05'].status !== 'FAIL') { cases['M1-U05'].status = 'NOT_RUN'; cases['M1-U05'].reason = 'aggregate_requires_loading_timeout_cancel_partial_and_refresh_evidence_across_controlled_runs'; }
} catch (error) {
  report.failure = { phase, ...safeFailure(error, 'configuration_or_runtime_error') };
} finally {
  for (const context of contexts) await context.close().catch(() => {});
  await browser?.close().catch(() => {});
  report.completedAtUtc = new Date().toISOString();
  report.exitCode = report.failure || Object.values(cases).some(item => item.status === 'FAIL') ? 1 : Object.values(cases).some(item => item.status === 'NOT_RUN') ? 2 : 0;
  if (output) await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  process.stdout.write(JSON.stringify({ taskId: report.taskId, scenario: report.scenario ?? null, status: report.exitCode === 1 ? 'FAIL' : report.exitCode === 2 ? 'INCOMPLETE' : 'PASS', caseStatuses: Object.fromEntries(Object.entries(cases).map(([key,value]) => [key,value.status])), failure: report.failure ?? null }) + '\n');
  process.exitCode = report.exitCode;
}
