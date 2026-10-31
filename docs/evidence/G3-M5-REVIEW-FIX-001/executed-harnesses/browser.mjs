/** 本任务真实OIDC/API/React定向验收；仅新建Synthetic环境，不保存认证材料。 */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const root = process.cwd();
const require = createRequire(resolve(root, 'apps/web/package.json'));
const { chromium, expect } = require('@playwright/test');
const output = resolve(root, 'docs/evidence/G3-M5-REVIEW-FIX-001/browser');
await mkdir(output, { recursive: true });
const runtimePath = resolve(process.argv[2]);
const boundary = relative(resolve(root, '.tools/security'), runtimePath);
if (boundary.startsWith('..') || isAbsolute(boundary)) throw new Error('runtime_boundary');
const runtime = JSON.parse(await readFile(runtimePath, 'utf8'));
if (runtime.resourceLifecycle?.taskId !== 'G3-M5-REVIEW-FIX-001') throw new Error('runtime_owner');
const realm = JSON.parse(await readFile(runtime.realmFile, 'utf8'));
const origin = 'http://localhost:15100';
const checks = [], startedAtUtc = new Date().toISOString(), tick = performance.now();
let browser, phase = 'start', status = 'FAIL';
const identifiers = {};
const check = (name, condition) => { checks.push({ name, status: condition ? 'PASS' : 'FAIL' }); if (!condition) throw new Error(name); };
const command = revision => ({ commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Synthetic M5 review fix targeted acceptance' });
async function identity(label) {
  phase = 'identity_' + label;
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const user = realm.identities['g2-' + label];
  await page.goto(origin + '/auth/login?returnUrl=%2F');
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#kc-login').click();
  await page.waitForURL(url => url.origin === origin && !url.pathname.startsWith('/signin-oidc'));
  check(label + '_real_session', (await context.cookies()).some(cookie => cookie.name === '.OntologyPlatform.Session' && cookie.httpOnly));
  const csrfResponse = await context.request.get(origin + '/auth/csrf');
  check(label + '_csrf', csrfResponse.status() === 200);
  const csrf = (await csrfResponse.json()).requestToken;
  return { context, page, api: context.request, headers: { Origin: origin, 'X-CSRF-TOKEN': csrf } };
}
async function request(user, method, path, data, label, expected = 200) {
  const response = await user.api[method](origin + path, { headers: { ...user.headers,
    ...(data?.command ? { 'If-Match': '"' + data.command.expectedRevision + '"' } : {}) }, ...(data ? { data } : {}) });
  check(label + '_http_' + expected, response.status() === expected);
  return response.json();
}
async function verifyView(view, snapshot, kind) {
  await expect(view).toBeVisible();
  const text = await view.textContent();
  check(kind + '_current_profile_full_binding', text.includes(`当前平台支持策略 Profile：${snapshot.profileId} · v${snapshot.profileVersion} · ${snapshot.profileHash}`));
  check(kind + '_projection_separate', text.includes('只读投影协议版本：1') && !text.includes('只读投影协议版本：4'));
  check(kind + '_historical_disclaimer', text.includes(kind === 'RELEASE' ? '此策略不是当前选中历史 Release 发布时的策略快照。' : '此策略不是当前选中草稿修订保存时的策略快照。'));
  check(kind + '_version_hash_binding', text.includes(snapshot.version.id) && text.includes(snapshot.hashes.bundleHash)
    && text.includes(`revision ${snapshot.version.revision ?? '不适用'}`));
  check(kind + '_no_false_historical_v4', !/(?:发布时|保存时)(?:的)?(?:策略|Profile)[：: ]*v4/.test(text));
  check(kind + '_all_source_hashes', snapshot.sources.every(source => text.includes(source.sourceHash)));
}
try {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const operator = await identity('operator-ab'), viewer = await identity('viewer-ab');
  const audit = await identity('auditor-ab'), single = await identity('viewer-a');
  const { runWorkspaceSmoke } = await import(pathToFileURL(resolve(root, 'scripts/acceptance/workspace-smoke.mjs')));
  await runWorkspaceSmoke({ root, origin, operator, viewer, command, faultCheck: true, setPhase: value => { phase = value; } });
  const sources = {};
  for (const [key, file] of [['ontologyTurtle','ontology.ttl'],['shapesTurtle','shapes.ttl'],['vocabularyTurtle','vocabulary.ttl'],['dataTurtle','data.ttl']])
    sources[key] = await readFile(resolve(root, 'samples/g2', file), 'utf8');
  phase = 'prepare_real_publication';
  const first = await request(operator, 'post', '/api/v1/ontology-drafts', { name: 'Synthetic review fix ' + randomUUID().slice(0, 8),
    sources, baseReleaseId: null, scope: { organizationId: 'org-demo', siteIds: ['site-a','site-b'] }, command: command(0) }, 'create');
  const path = '/api/v1/ontology-drafts/' + first.draftId;
  identifiers.draftId = first.draftId;
  const assessment = await request(operator, 'post', path + '/assessments', { revision: first.revision, hashes: first.hashes, command: command(first.revision) }, 'assess');
  check('actual_assessment_eligible', assessment.publishEligible);
  const version = { kind: 'DRAFT', id: first.draftId, revision: first.revision };
  const impact = await request(operator, 'post', '/api/v1/impact-reports', { from: version, to: version, baselineKind: 'INITIAL', assessmentId: assessment.assessmentId, command: command(first.revision) }, 'impact');
  const proposal = await request(operator, 'post', '/api/v1/release-proposals', { kind: 'PUBLISH', draftId: first.draftId, draftRevision: first.revision,
    hashes: first.hashes, validationReportId: assessment.validationReportId, impactReportId: impact.reportId, impactHash: impact.canonicalHash,
    targetReleaseId: null, targetManifestHash: null, command: command(first.revision) }, 'proposal');
  const approved = await request(audit, 'post', '/api/v1/approvals/' + proposal.proposalId + '/decisions', { decision: 'approve', command: command(proposal.revision) }, 'independent_approval');
  check('distinct_approver', approved.approval.approvedBy !== approved.submittedBy);
  const receipt = await request(operator, 'post', '/api/v1/release-activations', { proposalId: proposal.proposalId, expectedActivationRevision: 0, expectedActiveReleaseId: null, command: command(approved.revision) }, 'activation');
  const releaseId = receipt.releaseId; identifiers.releaseId = releaseId;
  check('release_identity', typeof releaseId === 'string' && releaseId.length > 0);
  const releasedBefore = await request(viewer, 'get', '/api/v1/releases/' + releaseId, null, 'manifest_before');
  phase = 'historical_draft_ui';
  const page = operator.page;
  await page.goto(origin + '/ontologies');
  await page.getByRole('button').filter({ has: page.locator('strong', { hasText: first.name }) }).click();
  await expect(page.getByRole('textbox', { name: '本体 · OWL源码', exact: true })).toBeVisible();
  // 页面保留已读取修订1；服务端另存修订2，随后UI必须真实请求旧修订1。
  const current = await request(operator, 'put', path, { name: first.name, sources: { ...sources, ontologyTurtle: sources.ontologyTurtle + '\n# next revision after publication\n' }, command: command(first.revision) }, 'save_new_revision');
  check('draft_is_historical', current.revision > first.revision && current.hashes.bundleHash !== first.hashes.bundleHash);
  const auditBefore = await request(audit, 'get', '/api/v1/platform/audit?limit=100', null, 'audit_before_reads');
  const snapshotResponse = page.waitForResponse(response => response.url() === origin + path + '/expressions?revision=' + first.revision);
  await page.getByRole('button', { name: '高阶表达式', exact: true }).click();
  const draftResponse = await snapshotResponse;
  check('historical_draft_real_get', draftResponse.status() === 200);
  const oldSnapshot = await draftResponse.json();
  check('old_revision_current_policy', oldSnapshot.version.revision === first.revision && oldSnapshot.profileVersion === '4' && oldSnapshot.hashes.bundleHash === first.hashes.bundleHash);
  const draftView = page.getByRole('region', { name: '高阶表达式只读视图', exact: true });
  await verifyView(draftView, oldSnapshot, 'DRAFT');
  await draftView.scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, 'draft.png'), animations: 'disabled' });
  phase = 'fixed_release_ui';
  const releasePage = viewer.page;
  await releasePage.goto(origin + '/ontologies');
  await releasePage.getByText('读取固定正式Release高阶表达式', { exact: true }).click();
  await releasePage.getByRole('textbox', { name: '表达式Release ID', exact: true }).fill(releaseId);
  const releasedResponse = releasePage.waitForResponse(response => response.url() === origin + '/api/v1/releases/' + releaseId + '/expressions');
  await releasePage.getByRole('button', { name: '读取固定Release表达式', exact: true }).click();
  const response = await releasedResponse;
  check('release_real_get', response.status() === 200);
  const releaseSnapshot = await response.json();
  check('release_binding_current_policy', releaseSnapshot.version.id === releaseId && releaseSnapshot.version.revision === null && releaseSnapshot.profileVersion === '4' && releaseSnapshot.hashes.bundleHash === first.hashes.bundleHash);
  const releaseView = releasePage.getByRole('region', { name: '高阶表达式只读视图', exact: true });
  await verifyView(releaseView, releaseSnapshot, 'RELEASE');
  await releaseView.scrollIntoViewIfNeeded();
  await releasePage.screenshot({ path: resolve(output, 'release.png'), animations: 'disabled' });
  const auditAfter = await request(audit, 'get', '/api/v1/platform/audit?limit=100', null, 'audit_after_reads');
  // 审计查询自身会追加既有platform.audit.read；只排除该已核实动作，其他新增动作一律失败。
  const business = entries => entries.filter(entry => entry.action !== 'platform.audit.read');
  check('audit_window_not_truncated', auditBefore.length < 100 && auditAfter.length < 100);
  check('no_new_write_audit_from_expression_reads', JSON.stringify(business(auditBefore)) === JSON.stringify(business(auditAfter)));
  check('audit_reader_records_own_existing_action', auditAfter.filter(entry => entry.action === 'platform.audit.read').length > auditBefore.filter(entry => entry.action === 'platform.audit.read').length);
  const releasedAfter = await request(viewer, 'get', '/api/v1/releases/' + releaseId, null, 'manifest_after');
  check('release_manifest_unchanged', JSON.stringify(releasedBefore) === JSON.stringify(releasedAfter));
  await request(single, 'get', '/api/v1/releases/' + releaseId + '/expressions', null, 'release_scope_denied', 403);
  await request(single, 'get', path + '/expressions?revision=1', null, 'draft_scope_denied', 403);
  status = 'PASS';
} catch (error) {
  // 只保存断言名/阶段，不输出认证响应、源内容或浏览器上下文。
  checks.push({ name: 'execution_exception', status: 'FAIL', category: error?.name ?? 'Error' });
} finally {
  await browser?.close();
  const sourceSha256 = createHash('sha256').update(await readFile(resolve(root, 'apps/web/src/features/ontology/expression-tree.tsx'))).digest('hex');
  const report = { taskId: 'G3-M5-REVIEW-FIX-001', status, phase, startedAtUtc, endedAtUtc: new Date().toISOString(), durationMs: Math.round(performance.now()-tick), sourceSha256, identifiers, checks,
    limitation: '真实浏览器为当前v4合法发布后固定Release及旧草稿修订；v1/v2/v3历史发布策略场景以冻结合同/组件fixture和未变后端既有证据核实，非本轮真实v1-v3重建。' };
  await writeFile(resolve(output, 'result.json'), JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify({ status, phase, passed: checks.filter(c => c.status === 'PASS').length, failed: checks.filter(c => c.status === 'FAIL').length }));
}
process.exitCode = status === 'PASS' ? 0 : 1;
