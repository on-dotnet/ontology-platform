import { evidenceDirectory } from "./evidence-paths.mjs";
import { postSemanticRead } from "./g3-read-backpressure.mjs";
/** 真实浏览器上下文中续接S1，验证异人发布、统一查询、原生MCP/SSE与版本回滚。 */
import { randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
/** 所有角色来自本轮真实OIDC；仅持久化合成标识、状态与耗时，不输出会话或正文。 */
export async function fullChain({ root, origin, operator, audit, single, viewer, draft, check, command, setPhase }) {
  const samples = [];
  const ids = {};
  const traces = [];
  const marks = [];
  const readBackpressureAttempts = [];
  /** 同源真实HTTP调用记录观察耗时，有限样本不是生产SLO。 */
  async function post(user, path, data, expected = 200) {
    const start = performance.now();
    const options = { data, headers: { ...user.headers, ...(data?.command ? { 'If-Match': '"' + data.command.expectedRevision + '"' } : {}) } };
    const response = path === '/api/v1/semantic/queries'
      ? await postSemanticRead(user.api, origin + path, options, fact => readBackpressureAttempts.push({ operation: path, ...fact }))
      : await user.api.post(origin + path, options);
    samples.push({ operation: path.replace(/[a-f0-9]{32}/g, '{id}'), category: path.endsWith('/validations') ? 'shacl' : path.endsWith('/semantic/queries') ? 'gateway' : path.endsWith('/release-activations') ? 'publication' : 'api', elapsedMs: performance.now() - start, status: response.status() });
    check('http_' + path.split('/').filter(Boolean).at(-1) + '_' + marks.length++, response.status() === expected, response.status());
    return response.json();
  }
  /** 每个实际UI命令均核对对应服务响应，再核对页面持久状态。 */
  async function clickResponse(page, button, path, predicate = () => true) {
    const waiting = page.waitForResponse(value => value.url() === origin + path && value.request().method() === 'POST');
    const start = performance.now();
    await button.click();
    const response = await waiting;
    samples.push({ operation: path.replace(/[a-f0-9]{32}/g, '{id}'), elapsedMs: performance.now() - start, status: response.status(), category: path.endsWith('/release-activations') ? 'publication' : path.endsWith('/semantic/queries') ? 'gateway' : 'api', transport: 'browser UI' });
    check('ui_command_' + marks.length++, response.status() === 200 && predicate(await response.json()), response.status());
    return response.json();
  }
  async function approveAndActivate(proposal, label) {
    setPhase(label + '_approval');
    await audit.page.goto(origin + '/releases');
    await audit.page.getByRole('textbox', { name: '审核操作理由', exact: true }).fill('Synthetic independent browser approval');
    const article = audit.page.locator('article').filter({ hasText: proposal.proposalId });
    const approved = await clickResponse(audit.page, article.getByRole('button', { name: '异人批准', exact: true }), '/api/v1/approvals/' + proposal.proposalId + '/decisions', value => value.status === 'APPROVED');
    check(label + '_distinct_subjects', approved.approval?.approvedBy !== approved.submittedBy && approved.approval?.decision === 'approve');
    setPhase(label + '_activation');
    await operator.page.goto(origin + '/releases');
    await operator.page.getByRole('textbox', { name: '审核操作理由', exact: true }).fill('Synthetic browser activation');
    const owned = operator.page.locator('article').filter({ hasText: proposal.proposalId });
    const receipt = await clickResponse(operator.page, owned.getByRole('button', { name: proposal.kind === 'ROLLBACK' ? '激活已批准回滚' : '激活已批准版本', exact: true }), '/api/v1/release-activations', value => Boolean(value.auditId && value.outboxEventId && value.manifestHash));
    traces.push(receipt.traceId);
    return receipt;
  }
  async function getRelease(id) {
    const response = await operator.api.get(origin + '/api/v1/releases/' + id);
    check('formal_release_read_' + marks.length++, response.status() === 200);
    return response.json();
  }
  try {
  const capsResponse = await operator.api.get(origin + '/api/v1/capabilities');
  check('actual_three_capability_registry', capsResponse.status() === 200);
  const caps = await capsResponse.json();
  check('executor_v4_and_exact_tools', caps.length === 3 && caps.every(value => value.executorId.endsWith('/4')) && caps.map(value => value.id).sort().join(',') === 'describe_ontology,resolve_entity,traverse_relationships');
  const plan = (capability, extras = {}) => ({ capabilityId: capability, capabilityVersion: caps.find(value => value.id === capability).version, assetId: draft.assetId, releaseId: null, entityType: null, entityIri: null, externalId: capability === 'describe_ontology' ? null : 'heat-1', siteId: capability === 'describe_ontology' ? null : 'site-a', relationshipIris: [], depth: 5, maxRows: 100, timeoutMs: 5000, ...extras });
  setPhase('s2_ui_proposal');
  // M1在原真实发布闭环前增加服务端评估，不能借旧校验报告绕过新资格门禁。
  await clickResponse(operator.page, operator.page.getByRole('button', { name: '评估发布资格', exact: true }),
    '/api/v1/ontology-drafts/' + draft.draftId + '/assessments',
    value => value.publishEligible && value.revision === draft.revision && value.stages.some(stage => stage.name === 'OWL_REASONING' && stage.status === 'NOT_RUN'));
  const proposal = await clickResponse(operator.page, operator.page.getByRole('button', { name: '提交异人发布审核', exact: true }), '/api/v1/release-proposals', value => value.status === 'PENDING' && value.draftRevision === draft.revision);
  ids.assetId = draft.assetId;
  await post(operator, '/api/v1/approvals/' + proposal.proposalId + '/decisions', { decision: 'approve', command: command(proposal.revision) }, 403);
  await post(operator, '/api/v1/release-activations', { proposalId: proposal.proposalId, expectedActivationRevision: 0, expectedActiveReleaseId: null, command: command(proposal.revision) }, 409);
  const first = await approveAndActivate(proposal, 'r1');
  ids.release1 = first.releaseId;
  const r1 = await getRelease(first.releaseId);
  check('m1_new_manifest_v2_assessment_bound', r1.manifest.schemaVersion === 2 && r1.manifest.semantics?.assessmentHash === proposal.semantics?.assessmentHash);
  check('r1_formal_immutable_graphs_sources', r1.isActive && r1.manifest.artifactObjects.length === 4 && r1.manifest.ontologyGraphIri.includes(first.releaseId) && r1.manifest.dataGraphIri.includes(first.releaseId));
  setPhase('performance_real_sparql');
  // 独立无Cookie的固定回环请求测量真正Jena SPARQL，不把Gateway耗时冒充解析器性能。
  for (let sample = 0; sample < 5; sample++) {
    const endpoint = new URL('http://localhost:13030/ontology/query');
    endpoint.searchParams.set('query', 'SELECT (COUNT(*) AS ?count) WHERE { GRAPH <' + r1.manifest.dataGraphIri + '> { ?s ?p ?o } }');
    const started = performance.now();
    const response = await fetch(endpoint, { headers: { Accept: 'application/sparql-results+json' }, signal: AbortSignal.timeout(5000) });
    const value = await response.json();
    samples.push({ operation: 'Jena SPARQL fixed formal data graph count', category: 'sparql', elapsedMs: performance.now() - started, status: response.status });
    check('real_sparql_observation_' + sample, response.ok && Number(value.results.bindings[0].count.value) > 0);
  }
  setPhase('s3_real_ui_query');
  const page = operator.page;
  await page.goto(origin + '/analysis');
  setPhase('s3_query_select_formal_release');
  await page.getByRole('combobox', { name: '查询正式版本', exact: true }).selectOption(first.releaseId);
  setPhase('s3_query_select_capability');
  await page.getByRole('combobox', { name: '受控语义能力', exact: true }).selectOption('resolve_entity');
  await page.getByRole('textbox', { name: '实体外部编号', exact: true }).fill('heat-1');
  setPhase('s3_query_select_site');
  await page.getByRole('combobox', { name: /^厂区/ }).selectOption('site-a');
  setPhase('s3_query_submit');
  const found = await clickResponse(page, page.getByRole('button', { name: '执行真实查询', exact: true }), '/api/v1/semantic/queries', value => value.status === 'FOUND' && value.snapshot.releaseId === first.releaseId && value.evidence.length > 0);
  await page.getByText('FOUND · 找到可信结果', { exact: true }).waitFor();
  traces.push(found.traceId);
  const evidenceResponse = page.waitForResponse(value => value.url().includes('/api/v1/evidence/') && value.request().method() === 'GET');
  await page.getByRole('button').filter({ hasText: found.evidence[0].evidenceId }).click();
  check('ui_evidence_reauthorized', (await evidenceResponse).status() === 200);
  await page.getByText('已由服务端重新读取证据 · Synthetic true', { exact: true }).waitFor();
  check('cross_scope_evidence_denied', (await single.api.get(origin + '/api/v1/evidence/' + encodeURIComponent(found.evidence[0].evidenceId))).status() === 403);
  // 同一真实浏览器页面切换计划，确认EMPTY与歧义不是失败伪装。
  await page.getByRole('textbox', { name: '实体外部编号', exact: true }).fill('missing-synthetic-' + randomUUID());
  await clickResponse(page, page.getByRole('button', { name: '执行真实查询', exact: true }), '/api/v1/semantic/queries', value => value.status === 'EMPTY');
  await page.getByRole('textbox', { name: '实体外部编号', exact: true }).fill('heat-1');
  await page.getByRole('combobox', { name: /^厂区/ }).selectOption('');
  await clickResponse(page, page.getByRole('button', { name: '执行真实查询', exact: true }), '/api/v1/semantic/queries', value => value.status === 'AMBIGUOUS' && value.candidates.length === 2);
  await page.getByRole('combobox', { name: /^厂区/ }).selectOption('site-a');
  setPhase('s3_native_mcp');
  let rpcId = 0;
  async function rpc(method, params, headers = viewer.headers) {
    const response = await viewer.api.post(origin + '/api/v1/mcp', { headers: { ...headers, Accept: 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-11-25' }, data: { jsonrpc: '2.0', id: ++rpcId, method, params } });
    check('real_mcp_http_' + method, response.status() === 200, response.status());
    const body = await response.text();
    const payload = response.headers()['content-type']?.includes('text/event-stream') ? JSON.parse(body.split('\n').find(line => line.startsWith('data:')).slice(5)) : JSON.parse(body);
    check('real_mcp_rpc_' + method, !payload.error && payload.id === rpcId);
    return payload.result;
  }
  await rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'g2-local-real-acceptance', version: '1.0' } });
  const tools = (await rpc('tools/list', {})).tools;
  check('mcp_exact_readonly_schemas', tools.length === 3 && tools.every(tool => !Object.hasOwn(tool.inputSchema.properties, 'actor') && tool.outputSchema));
  for (const capability of ['describe_ontology','resolve_entity','traverse_relationships']) {
    const result = await rpc('tools/call', { name: capability, arguments: { assetId: draft.assetId, depth: 5, maxRows: 100, timeoutMs: 5000, ...(capability === 'describe_ontology' ? {} : { externalId: capability === 'traverse_relationships' ? 'slab-1' : 'heat-1', siteId: 'site-a' }) } });
    check('mcp_formal_result_' + capability, !result.isError && result.structuredContent.snapshot.releaseId === first.releaseId && result.structuredContent.status === 'FOUND');
  }
  setPhase('s3_ui_maf_sse');
  await page.getByRole('textbox', { name: '运行说明', exact: true }).fill('Synthetic privacy marker G2_PROMPT_MUST_NOT_LEAK_' + randomUUID());
  await page.getByLabel('明确使用 deterministic harness', { exact: true }).check();
  const run = await clickResponse(page, page.getByRole('button', { name: '启动确定性工具运行', exact: true }), '/api/v1/execution-runs', value => value.snapshot.releaseId === first.releaseId && value.providerMode === 'deterministic');
  ids.runId = run.runId;
  traces.push(run.traceId);
  setPhase('s3_ui_wait_persisted_terminal');
  const eventsList = page.getByRole('list', { name: '真实持久运行事件', exact: true });
  const sseStart = performance.now();
  await eventsList.locator('li > strong').filter({ hasText: ' · run.completed' }).waitFor({ timeout: 40000 });
  samples.push({ operation: 'browser native SSE creation-to-observed-terminal', category: 'sse', elapsedMs: performance.now() - sseStart, status: 200, note: 'timer begins after create response; not before the HTTP command' });
  check('ui_real_native_sse_tool_delta_evidence_terminal', (await eventsList.innerText()).includes('tool.completed') && (await eventsList.innerText()).includes('message.delta') && (await eventsList.innerText()).includes('evidence.added'));
  setPhase('s3_native_sse_replay');
  const replay = await operator.api.get(origin + '/api/v1/execution-runs/' + run.runId + '/events', { headers: { Accept: 'text/event-stream' } });
  check('actual_yarp_native_sse_media_type', replay.status() === 200 && replay.headers()['content-type'].includes('text/event-stream'));
  const events = (await replay.text()).split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => JSON.parse(line.slice(5)));
  check('sse_persisted_monotonic_fixed_snapshot', events.length >= 7 && events.every((event,index) => event.seq === index+1 && event.snapshot.releaseId === first.releaseId) && events.at(-1).eventType === 'run.completed');
  const after = events[2];
  const resumed = await operator.api.get(origin + '/api/v1/execution-runs/' + run.runId + '/events', { headers: { Accept: 'text/event-stream', 'Last-Event-ID': after.eventId } });
  const resumedEvents = (await resumed.text()).split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => JSON.parse(line.slice(5)));
  check('actual_last_event_id_exact_resume', resumed.status() === 200 && JSON.stringify(resumedEvents) === JSON.stringify(events.slice(3)));
  setPhase('s3_disabled_provider');
  const disabled = await post(operator, '/api/v1/execution-runs', { prompt: 'Synthetic no model network', plan: plan('resolve_entity'), providerMode: 'disabled', command: command(0) });
  const disabledEvents = await operator.api.get(origin + '/api/v1/execution-runs/' + disabled.runId + '/events', { headers: { Accept: 'text/event-stream' } });
  check('disabled_model_durable_failure_no_tools', (await disabledEvents.text()).includes('provider_not_configured'));
  await page.screenshot({ path: resolve(evidenceDirectory(root),'screenshots/live-s3-run.png'), fullPage: true, animations: 'disabled' });
  setPhase('s2_r2_new_source_revision');
  const source2 = { ...draft.sources, ontologyTurtle: draft.sources.ontologyTurtle + '\n<urn:synthetic:live:SecondReleaseClass> a <http://www.w3.org/2002/07/owl#Class> .\n' };
  const save2 = await operator.api.put(origin + '/api/v1/ontology-drafts/' + draft.draftId, { headers: { ...operator.headers, 'If-Match': '"' + draft.revision + '"' }, data: { name: draft.name, sources: source2, command: command(draft.revision) } });
  check('r2_new_source_saved', save2.status() === 200);
  const draft2 = await save2.json();
  const valid2 = await post(operator, '/api/v1/ontology-drafts/' + draft.draftId + '/validations', { revision: draft2.revision, hashes: draft2.hashes, command: command(draft2.revision) });
  check('r2_real_shacl', valid2.conforms);
  const proposal2 = await post(operator, '/api/v1/release-proposals', { kind: 'PUBLISH', draftId: draft2.draftId, draftRevision: draft2.revision, hashes: draft2.hashes, validationReportId: valid2.reportId, targetReleaseId: null, targetManifestHash: null, command: command(draft2.revision) });
  const second = await approveAndActivate(proposal2, 'r2');
  ids.release2 = second.releaseId;
  const changed = await post(operator, '/api/v1/semantic/queries', plan('describe_ontology'));
  const historical = await post(operator, '/api/v1/semantic/queries', plan('describe_ontology', { releaseId: first.releaseId }));
  check('active_r2_and_history_r1_do_not_mix', changed.snapshot.releaseId === second.releaseId && changed.data[0].ontology.classIris.includes('urn:synthetic:live:SecondReleaseClass') && historical.snapshot.releaseId === first.releaseId && !historical.data[0].ontology.classIris.includes('urn:synthetic:live:SecondReleaseClass'));
  const oldRun = await operator.api.get(origin + '/api/v1/execution-runs/' + run.runId);
  check('existing_run_snapshot_retains_r1_after_r2', (await oldRun.json()).snapshot.releaseId === first.releaseId);
  setPhase('s2_ui_independent_rollback');
  await page.getByRole('textbox', { name: '审核操作理由', exact: true }).fill('Synthetic rollback independent proposal');
  const releaseArticle = page.locator('article').filter({ has: page.locator('strong').filter({ hasText: first.releaseId }) }).filter({ has: page.getByRole('button', { name: '提出回滚至此版本', exact: true }) });
  const rollbackProposal = await clickResponse(page, releaseArticle.getByRole('button', { name: '提出回滚至此版本', exact: true }), '/api/v1/release-proposals', value => value.kind === 'ROLLBACK' && value.targetReleaseId === first.releaseId);
  const rollback = await approveAndActivate(rollbackProposal, 'rollback');
  check('rollback_monotonic_activation_revision', rollback.releaseId === first.releaseId && rollback.activationRevision === second.activationRevision + 1);
  const restored = await post(operator, '/api/v1/semantic/queries', plan('describe_ontology'));
  check('rollback_query_matches_exact_r1', restored.snapshot.releaseId === first.releaseId && restored.snapshot.ontologyHash === historical.snapshot.ontologyHash && JSON.stringify(restored.data) === JSON.stringify(historical.data));
  const kept2 = await getRelease(second.releaseId);
  check('rollback_preserves_r2_history', !kept2.isActive && kept2.manifest.hashes.ontologyHash === changed.snapshot.ontologyHash);
  await page.screenshot({ path: resolve(evidenceDirectory(root),'screenshots/live-s2-rollback.png'), fullPage: true, animations: 'disabled' });
  } finally {
  if (['/analysis','/releases','/ontologies'].includes(new URL(operator.page.url()).pathname)) {
    await operator.page.screenshot({ path: resolve(evidenceDirectory(root),'screenshots/live-current-full-chain.png'), fullPage: true, animations: 'disabled' }).catch(() => {});
    const state = await operator.page.evaluate(() => ({ path: location.pathname, headings: [...document.querySelectorAll('h1,h2')].map(e=>e.textContent), alerts: [...document.querySelectorAll('[role=alert]')].map(e=>e.textContent), selects: [...document.querySelectorAll('select')].map(e=>({label:e.getAttribute('aria-label'), options:[...e.options].map(o=>({value:o.value,text:o.text})), value:e.value})) }));
    await writeFile(resolve(evidenceDirectory(root),'live-full-chain-ui-state.json'),JSON.stringify(state,null,2)+'\n');
  }
  await writeFile(resolve(evidenceDirectory(root),'full-chain-identifiers.json'), JSON.stringify({ ids, traces: traces.filter(Boolean), model: 'BLOCKED: no paid or real model calls authorized', oldRunConcurrencyScope: 'historical persisted Run checked across later activation; in-flight fencing races independently covered by native tests' },null,2)+'\n');
  await writeFile(resolve(evidenceDirectory(root),'performance-observations.json'), JSON.stringify({ environment: 'local macOS arm64, real isolated Docker/Aspire, headless Edge; no production SLO', sourceUtf8Bytes: Object.fromEntries(Object.entries(draft.sources).map(([key,value]) => [key,value===null?0:Buffer.byteLength(value)])), samples, readBackpressureAttempts },null,2)+'\n');
  }
  return ids;
}
