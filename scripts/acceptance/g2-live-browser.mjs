import { evidenceDirectory } from "./evidence-paths.mjs";
import { writeBrowserEntryReport } from "./browser-entry-report.mjs";
/** 真实OIDC/BFF纵向检查；不保存浏览器网络、Cookie、凭证或登录页面截图。 */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, relative, sep, isAbsolute } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
const root = resolve(import.meta.dirname, '../..');
const require = createRequire(resolve(root, 'apps/web/package.json'));
const { chromium } = require('@playwright/test');
const runtimePath = resolve(process.argv[2] ?? '');
const runtimeRelative = relative(resolve(root, '.tools/security'), runtimePath);
if (!runtimeRelative || runtimeRelative === '..' || runtimeRelative.startsWith('..' + sep) || isAbsolute(runtimeRelative)) throw new Error('runtime_path_denied');
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
  for (const [label, path] of [['proposal','/api/v1/release-proposals'], ['decision','/api/v1/approvals/synthetic/decisions'], ['activation','/api/v1/release-activations']]) {
    const response = await anonymous.request.post(origin + path, { data: '{', headers: { 'Content-Type': 'application/json' } });
    check('anonymous_publication_' + label + '_prebinding_401', response.status() === 401, response.status());
  }
  await anonymous.close();
  const operator = await identity('operator-ab');
  if (!process.argv.includes('--m2-api-only') && !process.argv.includes('--m3-api-only') && !process.argv.includes('--m4-api-only') && !process.argv.includes('--m4-impact-only')) {
    const smokeViewer = await identity('viewer-ab');
    const { runWorkspaceSmoke } = await import('./workspace-smoke.mjs');
    try {
      await runWorkspaceSmoke({ root, origin, operator, viewer: smokeViewer, command,
        faultCheck: process.argv.includes('--smoke-fault-check'), setPhase: value => { phase = value; } });
    } finally { await smokeViewer.context.close(); }
  }
  if (process.argv.includes('--workspace-smoke-only')) {
    await operator.context.close();
  } else if (process.argv.includes('--m4-impact-only')) {
    const viewer = await identity('viewer-ab');
    const single = await identity('viewer-a');
    const { runM4ImpactChecks } = await import('./g3-m4-impact-browser.mjs');
    await runM4ImpactChecks({ root, origin, operator, viewer, single, check, command, setPhase: value => { phase = value; } });
    for (const user of [operator, viewer, single]) await user.context.close();
  } else if (process.argv.includes('--m4-diff-only')) {
    const viewer = await identity('viewer-ab');
    const single = await identity('viewer-a');
    const { runM4DiffChecks } = await import('./g3-m4-diff-browser.mjs');
    await runM4DiffChecks({ root, origin, operator, viewer, single, check, command, setPhase: value => { phase = value; } });
    for (const user of [operator, viewer, single]) await user.context.close();
  } else if (process.argv.includes('--m4-api-only') || process.argv.includes('--m4-ui-only')) {
    const viewer = await identity('viewer-ab');
    const single = await identity('viewer-a');
    const audit = await identity('auditor-ab');
    const { runM4Checks } = await import('./g3-m4-browser.mjs');
    await runM4Checks({ root, origin, operator, audit, viewer, single, check, command,
      apiOnly: process.argv.includes('--m4-api-only'), uiOnly: process.argv.includes('--m4-ui-only'), setPhase: value => { phase = value; } });
    for (const user of [operator, viewer, single, audit]) await user.context.close();
  } else if (process.argv.includes('--m3-api-only') || process.argv.includes('--m3-ui-only')) {
    const viewer = await identity('viewer-ab');
    const single = await identity('viewer-a');
    const audit = await identity('auditor-ab');
    const { runM3Checks } = await import('./g3-m3-browser.mjs');
    await runM3Checks({ root, origin, operator, audit, viewer, single, check, command,
      apiOnly: process.argv.includes('--m3-api-only'), uiOnly: process.argv.includes('--m3-ui-only'), setPhase: value => { phase = value; } });
    for (const user of [operator, viewer, single, audit]) await user.context.close();
  } else if (process.argv.includes('--m2-api-only') || process.argv.includes('--m2-ui-only')) {
    const viewer = await identity('viewer-ab');
    const single = await identity('viewer-a');
    const { runM2Checks } = await import('./g3-m2-browser.mjs');
    await runM2Checks({ root, origin, operator, viewer, single, check, command, apiOnly: process.argv.includes('--m2-api-only'), uiOnly: process.argv.includes('--m2-ui-only'), setPhase: value => { phase = value; } });
    for (const user of [operator, viewer, single]) await user.context.close();
  } else {
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
  for (const [label, path] of [['proposal','/api/v1/release-proposals'], ['decision','/api/v1/approvals/synthetic/decisions'], ['activation','/api/v1/release-activations']]) {
    const response = await viewer.api.post(origin + path, { data: '{', headers: { 'Content-Type': 'application/json' } });
    check('viewer_publication_' + label + '_prebinding_403', response.status() === 403, response.status());
  }
  const audit = await identity('auditor-ab');
  const facts = await audit.api.get(origin + '/api/v1/platform/audit?limit=100');
  check('actual_auditor_reads_governance_audit', facts.status() === 200);
  const entries = await facts.json();
  check('publication_role_denials_have_committed_audit', entries.filter(value => value.action === 'authorization.denied' && value.outcome === 'denied').length >= 4);
  check('success_and_denial_audits_persisted', entries.some(value => value.action === 'ontology.create' && value.outcome === 'allowed') && entries.some(value => value.outcome === 'denied'));
  phase = 'real_ui_source_import';
  const page = operator.page;
  const uiErrors = [];
  page.on('pageerror', () => uiErrors.push('pageerror'));
  await page.goto(origin + '/ontologies');
  await page.getByRole('heading', { name: '本体资产与草稿', exact: true }).waitFor();
  const uiName = 'Synthetic live UI ' + randomUUID().slice(0,8);
  await page.getByRole('textbox', { name: '资产名称', exact: true }).fill(uiName);
  await page.getByLabel('额外授权厂区 site-b').check();
  for (const [key,file] of [['ontologyTurtle','ontology.ttl'],['shapesTurtle','shapes.ttl'],['vocabularyTurtle','vocabulary.ttl'],['dataTurtle','data.ttl']]) {
    await page.getByRole('combobox', { name: '选择源文档', exact: true }).selectOption(key);
    await page.getByLabel('载入' + file, { exact: true }).setInputFiles(resolve(root, 'samples/g2', file));
  }
  await page.getByRole('textbox', { name: '变更理由', exact: true }).fill('Synthetic real browser source acceptance');
  const createResult = page.waitForResponse(response => response.url() === origin + '/api/v1/ontology-drafts' && response.request().method() === 'POST');
  await page.getByRole('button', { name: '创建真实草稿', exact: true }).click();
  const uiCreatedResponse = await createResult;
  check('ui_four_real_file_import_create', uiCreatedResponse.status() === 200, uiCreatedResponse.status());
  const uiCreated = await uiCreatedResponse.json();
  check('ui_full_scope_and_source_exact', JSON.stringify(uiCreated.sources) === JSON.stringify(sources) && JSON.stringify(uiCreated.scope.siteIds) === JSON.stringify(['site-a','site-b']));
  // M2中间区域显式切换图/源码；先验证图可见，再回源码继续原有CAS和导出断言。
  await page.getByRole('button', { name: '图视图', exact: true }).click();
  await page.getByRole('heading', { name: 'RDF 结构投影', exact: true }).waitFor();
  await page.locator('.g2-graph canvas').first().waitFor();
  check('ui_explicit_graph_view_visible', await page.locator('.g2-graph canvas').first().isVisible());
  await page.getByRole('button', { name: '源码视图', exact: true }).click();
  phase = 'real_ui_structural_edit';
  await page.getByRole('combobox', { name: '结构操作', exact: true }).selectOption('add');
  const addedIri = 'urn:synthetic:live:Class:' + randomUUID();
  await page.getByRole('textbox', { name: '主体IRI', exact: true }).fill(addedIri);
  await page.getByRole('combobox', { name: '标准声明快捷填入', exact: true }).selectOption('http://www.w3.org/2002/07/owl#Class');
  const editResult = page.waitForResponse(response => response.url().endsWith('/' + uiCreated.draftId + '/edits') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '提交真实结构编辑', exact: true }).click();
  const editedResponse = await editResult;
  check('ui_real_structural_edit', editedResponse.status() === 200, editedResponse.status());
  const edited = await editedResponse.json();
  check('ui_projection_tracks_saved_revision', edited.revision === 2 && edited.projection.revision === edited.revision && edited.projection.nodes.some(node => node.id === addedIri));
  phase = 'real_ui_concurrent_cas';
  await page.getByRole('combobox', { name: '选择源文档', exact: true }).selectOption('ontologyTurtle');
  const localText = edited.sources.ontologyTurtle + '\n# Synthetic local pending\n';
  const editor = page.getByRole('textbox', { name: '本体 · OWL源码', exact: true });
  await editor.fill(localText);
  const remoteResponse = await operator.api.put(origin + '/api/v1/ontology-drafts/' + edited.draftId, { data: { name: edited.name, sources: { ...edited.sources, ontologyTurtle: edited.sources.ontologyTurtle + '\n# Synthetic concurrent remote\n' }, command: command(edited.revision) }, headers: { ...operator.headers, 'If-Match': '"' + edited.revision + '"' } });
  check('ui_concurrent_real_remote_save', remoteResponse.status() === 200, remoteResponse.status());
  let remote = await remoteResponse.json();
  const conflictResult = page.waitForResponse(response => response.url().endsWith('/' + edited.draftId) && response.request().method() === 'PUT');
  await page.getByRole('button', { name: '保存新修订', exact: true }).click();
  check('ui_stale_revision_real_409', (await conflictResult).status() === 409);
  await page.getByRole('alert').filter({ hasText: '版本冲突' }).waitFor();
  check('ui_409_preserves_local_text', await editor.inputValue() === localText);
  await page.getByRole('button', { name: '读取远端版本', exact: true }).click();
  await page.getByRole('heading', { name: '远端 revision ' + remote.revision + ' 与本地文本对比', exact: true }).waitFor();
  check('ui_remote_compare_preserves_local_text', await editor.inputValue() === localText);
  await page.getByRole('button', { name: '丢弃本地内容并载入此远端版本', exact: true }).click();
  check('ui_explicit_discard_loads_remote', await editor.inputValue() === remote.sources.ontologyTurtle);
  phase = 'real_ui_name_save';
  const renamedName = uiName + ' renamed';
  await page.getByRole('textbox', { name: '资产名称', exact: true }).fill(renamedName);
  const renameResult = page.waitForResponse(response => response.url() === origin + '/api/v1/ontology-drafts/' + remote.draftId && response.request().method() === 'PUT');
  await page.getByRole('button', { name: '保存新修订', exact: true }).click();
  const renameResponse = await renameResult;
  check('ui_name_save_real_put_200', renameResponse.status() === 200, renameResponse.status());
  const renamed = await renameResponse.json();
  check('ui_name_save_returns_new_name', renamed.name === renamedName && renamed.revision === remote.revision + 1);
  check('ui_name_save_preserves_source_and_hashes', JSON.stringify(renamed.sources) === JSON.stringify(remote.sources) && JSON.stringify(renamed.hashes) === JSON.stringify(remote.hashes));
  const renamedRead = await operator.api.get(origin + '/api/v1/ontology-drafts/' + remote.draftId);
  check('ui_name_save_persistent_get', renamedRead.status() === 200 && (await renamedRead.json()).name === renamedName);
  remote = renamed;
  phase = 'real_ui_shacl_and_diff';
  const validatedResult = page.waitForResponse(response => response.url().endsWith('/' + edited.draftId + '/validations') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '验证已保存修订', exact: true }).click();
  const validatedResponse = await validatedResult;
  check('ui_real_shacl_conforms', validatedResponse.status() === 200 && (await validatedResponse.json()).conforms === true);
  const diffResult = page.waitForResponse(response => response.url().includes('/' + edited.draftId + '/diff?'));
  await page.getByRole('button', { name: '读取真实 Diff', exact: true }).click();
  const diffResponse = await diffResult;
  const uiDiff = await diffResponse.json();
  check('ui_real_diff_revisions_and_triple', diffResponse.status() === 200 && uiDiff.baseRevision === 1 && uiDiff.targetRevision === remote.revision && uiDiff.addedTriples.some(triple => triple.subject.value === addedIri));
  phase = 'real_ui_export';
  const downloadResult = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出原始源', exact: true }).click();
  const downloaded = await downloadResult;
  check('ui_export_exact_server_source_bytes', (await readFile(await downloaded.path())).equals(Buffer.from(remote.sources.ontologyTurtle, 'utf8')));
  phase = 'real_ui_layouts';
  await mkdir(resolve(evidenceDirectory(root), 'screenshots'), { recursive: true });
  for (const width of [1440,1280,390]) {
    await page.setViewportSize({ width, height: 1000 });
    if (width === 390) await page.getByRole('button', { name: '图与校验', exact: true }).click();
    for (const theme of ['dark','light']) {
      if ((await page.evaluate(() => document.documentElement.dataset.theme ?? 'dark')) !== theme) await page.getByRole('button', { name: '切换深浅主题', exact: true }).click();
      const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, overflowing: [...document.querySelectorAll('body *')].filter(element => element.getBoundingClientRect().right > innerWidth + 1).slice(0,30).map(element => ({ tag: element.tagName, className: typeof element.className === 'string' ? element.className : '', width: Math.round(element.getBoundingClientRect().width), right: Math.round(element.getBoundingClientRect().right) })) }));
      if (layout.scrollWidth > layout.width) {
        layout.computed = await page.evaluate(() => [...document.querySelectorAll('.g2-inspector, .g2-inspector > section, .g2-inspector label, .g2-inspector select, .g2-graph, .g2-graph > div')].slice(0,35).map(element => {
          const style = getComputedStyle(element);
          return { tag: element.tagName, className: element.className, width: style.width, minWidth: style.minWidth, maxWidth: style.maxWidth, display: style.display, gridTemplateColumns: style.gridTemplateColumns, overflowWrap: style.overflowWrap, whiteSpace: style.whiteSpace, position: style.position, rectWidth: Math.round(element.getBoundingClientRect().width) };
        }));
        layout.g2Styles = await page.evaluate(() => {
          const result = [];
          function inspect(rules) { for (const rule of rules) { if (rule.selectorText?.includes('.g2-')) result.push(rule.cssText); if (rule.cssRules) inspect(rule.cssRules); } }
          for (const sheet of document.styleSheets) { try { inspect(sheet.cssRules); } catch { } }
          return result;
        });
        layout.cssAssets = [];
        for (const asset of await page.evaluate(() => [...document.querySelectorAll('link[rel=stylesheet]')].map(value => value.href))) {
          const body = await operator.api.get(asset);
          const bytes = await body.body();
          layout.cssAssets.push({ url: asset, status: body.status(), size: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
        }
        await writeFile(resolve(evidenceDirectory(root), 'live-layout-red.json'), JSON.stringify(layout,null,2) + '\n');
        await page.screenshot({ path: resolve(evidenceDirectory(root), 'screenshots/live-s1-' + width + '-' + theme + '-red.png'), fullPage: true, animations: 'disabled' });
      }
      check('ui_' + width + '_' + theme + '_no_horizontal_overflow', layout.scrollWidth <= layout.width);
      await page.screenshot({ path: resolve(evidenceDirectory(root), 'screenshots/live-s1-' + width + '-' + theme + '.png'), fullPage: true, animations: 'disabled' });
    }
  }
  check('ui_no_uncaught_hydration_errors', uiErrors.length === 0);
  if (process.argv.includes('--full')) {
    const { fullChain } = await import('./g2-full-chain.mjs');
    await fullChain({ root, origin, operator, audit, single, viewer, draft: remote, check, command, setPhase: value => { phase = value; } });
    if (process.argv.includes('--m1')) {
      const { runM1Checks } = await import('./g3-m1-browser.mjs');
      await runM1Checks({ root, origin, operator, audit, single, viewer, check, command, setPhase: value => { phase = value; } });
    }
  }
  if (process.argv.includes('--m2')) {
    const { runM2Checks } = await import('./g3-m2-browser.mjs');
    await runM2Checks({ root, origin, operator, audit, single, viewer, check, command, setPhase: value => { phase = value; } });
  }
  if (process.argv.includes('--m3')) {
    const { runM3Checks } = await import('./g3-m3-browser.mjs');
    await runM3Checks({ root, origin, operator, audit, single, viewer, check, command, setPhase: value => { phase = value; } });
  }
  if (process.argv.includes('--m4')) {
    const { runM4Checks } = await import('./g3-m4-browser.mjs');
    await runM4Checks({ root, origin, operator, audit, single, viewer, check, command, setPhase: value => { phase = value; } });
  }
  for (const user of [operator, single, viewer, audit]) await user.context.close();
  }
} catch (error) {
  failure = { phase, category: error?.name ?? 'Error', details: 'SUPPRESSED' };
} finally {
  await browser?.close();
  const checkpoint = process.argv.includes('--workspace-smoke-only') ? 'workspace-smoke' : process.argv.includes('--m4-impact-only') ? 'm4-impact-oidc' : process.argv.includes('--m4-diff-only') ? 'm4-diff-oidc' : process.argv.includes('--m4-api-only') ? 'm4-api-oidc' : process.argv.includes('--m4-ui-only') ? 'm4-ui-oidc' : process.argv.includes('--m4') ? 'm4-full-e2e' : process.argv.includes('--m3-api-only') ? 'm3-api-oidc' : process.argv.includes('--m3-ui-only') ? 'm3-ui-oidc' : process.argv.includes('--m3') ? 'm3-full-e2e' : process.argv.includes('--m2-api-only') ? 'm2-api-oidc' : process.argv.includes('--m2-ui-only') ? 'm2-ui-oidc' : process.argv.includes('--full') ? 'full-g2-e2e' : 'live-s1-http';
  const report = { stage: checkpoint, status: failure ? 'FAIL' : 'PASS', overallG2: 'PARTIAL', checks, failure, notRun: process.argv.includes('--full') ? (failure ? ['remaining steps after ' + phase, 'final sameHead CI'] : ['final sameHead CI', 'real model BLOCKED', 'Monaco PAUSED_BY_USER', 'Windows/Intel/production NOT_RUN']) : ['remaining full-chain gates','final regression and CI'] };
  await writeBrowserEntryReport(root, checkpoint, report);
  console.log(JSON.stringify({ stage: report.stage, status: report.status, passed: checks.filter(value => value.status === 'PASS').length, failure }));
  if (failure) process.exitCode = 1;
}
