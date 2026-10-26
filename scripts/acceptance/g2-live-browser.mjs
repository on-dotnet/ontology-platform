/** 真实OIDC/BFF纵向检查；不保存浏览器网络、Cookie、凭证或登录页面截图。 */
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, relative, sep } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
const root = resolve(import.meta.dirname, '../..');
const require = createRequire(resolve(root, 'apps/web/package.json'));
const { chromium } = require('@playwright/test');
const runtimePath = resolve(process.argv[2] ?? '');
if (relative(resolve(root, '.tools/security'), runtimePath).startsWith('..' + sep)) throw new Error('runtime_path_denied');
const runtime = JSON.parse(await readFile(runtimePath, 'utf8'));
const realm = JSON.parse(await readFile(runtime.realmFile, 'utf8'));
const origin = 'http://localhost:15100';
const checks = [];
let phase = 'browser_start';
let browser;
let failure = null;
function check(name, condition, observedStatus) {
  checks.push({ name, status: condition ? 'PASS' : 'FAIL', ...(observedStatus === undefined ? {} : { observedStatus }) });
  if (!condition) throw new Error('check_failed');
}
const command = revision => ({ commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision: revision, reason: 'Synthetic G2 live acceptance' });
async function identity(label) {
  phase = 'oidc_' + label;
  const context = await browser.newContext();
  const page = await context.newPage();
  const user = realm.identities['g2-' + label];
  await page.goto(origin + '/auth/login?returnUrl=%2F');
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#kc-login').click();
  await page.waitForURL(url => url.origin === origin && !url.pathname.startsWith('/signin-oidc'));
  const session = (await context.cookies()).find(cookie => cookie.name === '.OntologyPlatform.Session');
  check(label + '_real_http_only_session', session?.httpOnly === true && session.sameSite === 'Lax');
  const csrfResponse = await context.request.get(origin + '/auth/csrf');
  check(label + '_csrf', csrfResponse.status() === 200);
  const csrf = (await csrfResponse.json()).requestToken;
  return { context, page, api: context.request, headers: { Origin: origin, 'X-CSRF-TOKEN': csrf } };
}
try {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const anonymous = await browser.newContext();
  const denied = await anonymous.request.post(origin + '/api/v1/ontology-drafts', { data: '{', headers: { 'Content-Type': 'application/json' } });
  check('anonymous_authorization_before_malformed_binding', denied.status() === 401);
  await anonymous.close();
  const operator = await identity('operator-ab');
  phase = 'draft_create';
  const sources = {};
  for (const [key, file] of [['ontologyTurtle','ontology.ttl'],['shapesTurtle','shapes.ttl'],['vocabularyTurtle','vocabulary.ttl'],['dataTurtle','data.ttl']]) sources[key] = await readFile(resolve(root, 'samples/g2', file), 'utf8');
  const request = { name: 'Synthetic live source roundtrip', scope: { organizationId: 'org-demo', siteIds: ['site-a','site-b'] }, sources, baseReleaseId: null, command: command(0) };
  const noCsrf = await operator.api.post(origin + '/api/v1/ontology-drafts', { data: request, headers: { Origin: origin } });
  check('operator_missing_csrf_denied', noCsrf.status() === 403, noCsrf.status());
  const createdResponse = await operator.api.post(origin + '/api/v1/ontology-drafts', { data: request, headers: operator.headers });
  check('operator_real_draft_created', createdResponse.status() === 200, createdResponse.status());
  const draft = await createdResponse.json();
  check('persisted_initial_sources_exact', JSON.stringify(draft.sources) === JSON.stringify(sources) && draft.revision === 1);
  check('all_four_utf8_hashes_match', Object.entries(sources).every(([key,value]) => value === null || draft.hashes[key.replace('Turtle','Hash')] === createHash('sha256').update(value,'utf8').digest('hex')));
  phase = 'noop_and_cas';
  const saved = await operator.api.put(origin + '/api/v1/ontology-drafts/' + draft.draftId, { data: { name: draft.name, sources, command: command(draft.revision) }, headers: { ...operator.headers, 'If-Match': '"' + draft.revision + '"' } });
  check('real_noop_save', saved.status() === 200);
  const current = await saved.json();
  check('no_op_preserves_complete_source', JSON.stringify(current.sources) === JSON.stringify(sources));
  const readback = await operator.api.get(origin + '/api/v1/ontology-drafts/' + draft.draftId);
  check('persistent_readback', readback.status() === 200 && JSON.stringify((await readback.json()).sources) === JSON.stringify(sources));
  phase = 'shacl';
  const validation = await operator.api.post(origin + '/api/v1/ontology-drafts/' + draft.draftId + '/validations', { data: { revision: current.revision, hashes: current.hashes, command: command(current.revision) }, headers: operator.headers });
  check('live_jena_shacl', validation.status() === 200 && (await validation.json()).conforms === true);
  phase = 'cross_scope_and_role';
  const single = await identity('viewer-a');
  const forbidden = await single.api.get(origin + '/api/v1/ontology-drafts/' + draft.draftId);
  check('full_multisite_scope_required', forbidden.status() === 403);
  const viewer = await identity('viewer-ab');
  check('authorized_full_scope_read', (await viewer.api.get(origin + '/api/v1/ontology-drafts/' + draft.draftId)).status() === 200);
  const wrongRole = await viewer.api.post(origin + '/api/v1/ontology-drafts', { data: '{', headers: { 'Content-Type': 'application/json' } });
  check('role_authorization_before_malformed_binding', wrongRole.status() === 403);
  const audit = await identity('auditor-ab');
  const facts = await audit.api.get(origin + '/api/v1/platform/audit?limit=100');
  check('actual_auditor_reads_governance_audit', facts.status() === 200);
  const entries = await facts.json();
  check('success_and_denial_audits_persisted', entries.some(value => value.action === 'ontology.create' && value.outcome === 'allowed') && entries.some(value => value.outcome === 'denied'));
  for (const user of [operator, single, viewer, audit]) await user.context.close();
} catch (error) {
  failure = { phase, category: error?.name ?? 'Error', details: 'SUPPRESSED' };
} finally {
  await browser?.close();
  const report = { stage: 'S1_HTTP_REAL_OIDC', status: failure ? 'FAIL' : 'PASS', overallG2: 'PARTIAL', checks, failure, notRun: ['G2 UI source interaction','S2 publishing browser','S3 gateway MCP MAF SSE','final regression and CI'] };
  await writeFile(resolve(root, 'docs/evidence/G2-THIN-SLICE-001/master/live-s1-http.json'), JSON.stringify(report,null,2) + '\n');
  console.log(JSON.stringify({ stage: report.stage, status: report.status, passed: checks.filter(value => value.status === 'PASS').length, failure }));
  if (failure) process.exitCode = 1;
}
