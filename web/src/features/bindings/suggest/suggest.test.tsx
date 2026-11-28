import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';

import type { components } from '@/api/schema';
import { makeSource } from '@/features/datasources/test-fixtures';
import { elementDetailFixture, elementFixture, impactFixture, ontologyFixture } from '@/test/fixtures';
import { jsonResponse, mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

type Suggestion = components['schemas']['BindingSuggestion'];
const title = 'AI 建议绑定';
const submit = '生成绑定建议';
const onto = ontologyFixture();
const source = makeSource({ catalog: { status: 'ready', refreshedAt: '2026-11-25T08:00:00Z', errorCode: null, tableCount: 2 } });
const postPath = `/api/ontologies/${onto.id}/binding-suggestions`;
const pollPath = '/api/binding-suggestions/req-1';
const allScope = { dataSourceId: source.id, schemas: ['steel', 'archive'] };

function suggestion(overrides: Partial<Suggestion> = {}): Suggestion {
  return { id: 'req-1', ontologyId: onto.id, dataSourceId: source.id, status: 'queued', step: null,
    proposed: 0, dropped: 0, droppedReasons: null, changeSetId: null, samplesSent: false, errorCode: null,
    createdAt: source.createdAt, finishedAt: null, ...overrides };
}

function server(routes: Record<string, RouteHandler> = {}, role: 'viewer' | 'editor' = 'editor') {
  return mockApi({
    'GET /api/ontologies': () => [onto],
    'GET /api/data-sources/:id': () => source,
    'GET /api/data-sources': () => [source],
    'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 1 }, { name: 'archive', tableCount: 1 }],
    [`POST ${postPath}`]: () => jsonResponse(suggestion({ status: 'succeeded' }), 202),
    ...routes,
  }, { user: userWithRole(role) });
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: title }));
  return within(await screen.findByRole('dialog', { name: title }));
}

async function openSource(user: ReturnType<typeof userEvent.setup>, search = '') {
  renderApp(`/data/${source.id}${search}`);
  return openDialog(user);
}

async function openDroppedResult(dropped: number, droppedReasons: Suggestion['droppedReasons']) {
  server({ [`POST ${postPath}`]: () => jsonResponse(suggestion({ status: 'succeeded', dropped, droppedReasons }), 202) });
  const user = userEvent.setup();
  const dialog = await openSource(user);
  await dialog.findByRole('checkbox', { name: 'steel' });
  await user.click(dialog.getByRole('button', { name: submit }));
  return dialog;
}

afterEach(() => { vi.useRealTimers(); });

describe('AI binding suggestions', () => {
  it.each([
    ['editor', 'ready', true], ['viewer', 'ready', false], ['editor', 'never', false],
    ['editor', 'refreshing', false], ['editor', 'failed', false],
  ] as const)('catalog entry for %s with status %s', async (role, status, visible) => {
    server({ 'GET /api/data-sources/:id': () => makeSource({ catalog: {
      status, refreshedAt: status === 'ready' ? source.createdAt : null, tableCount: 0, errorCode: null,
    } }) }, role);
    renderApp(`/data/${source.id}`);
    const catalog = within(await screen.findByRole('region', { name: '目录' }));
    if (visible) expect(await catalog.findByRole('button', { name: title })).toBeVisible();
    else expect(catalog.queryByRole('button', { name: title })).toBeNull();
  });

  it.each([false, true])('discloses model inputs for allowSamples=%s', async (allowSamples) => {
    server({ 'GET /api/data-sources/:id': () => ({ ...source, allowSamples }) });
    const dialog = await openSource(userEvent.setup());
    expect(await dialog.findByText(/表名、列名、类型和注释/)).toBeVisible();
    if (allowSamples) {
      expect(dialog.getByText(/每列最多 5 个样本值/)).toBeVisible();
      expect(dialog.getByText(/所有登录用户/).closest('[role="status"]')).toHaveTextContent(/证据.*审核页/);
    } else expect(dialog.queryByText(/样本/)).toBeNull();
  });

  it('submits all schemas by default and uses the current ontology', async () => {
    const other = ontologyFixture({ id: 'onto-other', name: '其他本体' });
    const api = server({ 'GET /api/ontologies': () => [other, onto] });
    const user = userEvent.setup();
    const dialog = await openSource(user, `?ontology=${onto.id}`);
    expect(await dialog.findByRole('checkbox', { name: 'steel' })).toBeChecked();
    expect(dialog.getByRole('checkbox', { name: 'archive' })).toBeChecked();
    await user.click(dialog.getByRole('button', { name: submit }));
    await waitFor(() => expect(api.calls('POST', postPath).map((call) => call.body)).toEqual([allScope]));
  });

  it('keeps selected tables across searches and sends just their schema and name', async () => {
    const api = server({ 'GET /api/data-sources/:id/catalog/tables': ({ query }) => ({
      items: ['heat', 'cast'].filter((name) => name.includes(query.get('q') ?? '')).map((name) =>
        ({ schema: 'steel', name, kind: 'table', comment: null, columnCount: 2, boundType: null })),
      nextCursor: null,
    }) });
    const user = userEvent.setup();
    const dialog = await openSource(user);
    await user.click(await dialog.findByRole('radio', { name: '按表' }));
    await user.click(await dialog.findByRole('checkbox', { name: 'steel.heat' }));
    await user.type(dialog.getByRole('searchbox'), 'cast');
    await waitFor(() => expect(api.calls('GET', `/api/data-sources/${source.id}/catalog/tables`).some(
      (call) => call.query.get('q') === 'cast')).toBe(true));
    await user.click(await dialog.findByRole('checkbox', { name: 'steel.cast' }));
    await user.click(dialog.getByRole('button', { name: submit }));
    await waitFor(() => expect(api.calls('POST', postPath).map((call) => call.body)).toEqual([{
      dataSourceId: source.id, tables: [{ schema: 'steel', name: 'heat' }, { schema: 'steel', name: 'cast' }],
    }]));
  });

  it('labels table search, settles rapid typing once, and blocks paging while it settles', async () => {
    const api = server({ 'GET /api/data-sources/:id/catalog/tables': () => ({
      items: [{ schema: 'steel', name: 'heat', kind: 'table', comment: null, columnCount: 2, boundType: null }],
      nextCursor: 'page-2',
    }) });
    const user = userEvent.setup();
    const dialog = await openSource(user);
    await user.click(await dialog.findByRole('radio', { name: '按表' }));
    const search = dialog.getByLabelText(i18n.t('bindings.suggest.searchTables'));
    expect(dialog.getByText(i18n.t('bindings.suggest.searchTables'))).toBeVisible();
    const next = await dialog.findByRole('button', { name: i18n.t('pagination.next') });
    expect(next).toBeEnabled();

    for (const value of ['h', 'he', 'hea', 'heat']) fireEvent.change(search, { target: { value } });
    expect(next).toBeDisabled();
    const searches = () => api.calls('GET', `/api/data-sources/${source.id}/catalog/tables`)
      .map((call) => call.query.get('q')).filter(Boolean);
    await waitFor(() => expect(searches()).toEqual(['heat']));
    expect(dialog.getByRole('button', { name: i18n.t('pagination.next') })).toBeEnabled();

    // A new search starts again from the first page; clearing it waits the same way.
    const calls = () => api.calls('GET', `/api/data-sources/${source.id}/catalog/tables`);
    fireEvent.click(dialog.getByRole('button', { name: i18n.t('pagination.next') }));
    await waitFor(() => expect(calls().at(-1)?.query.get('cursor')).toBe('page-2'));
    fireEvent.change(search, { target: { value: 'cast' } });
    await waitFor(() => expect(calls().at(-1)?.query.get('q')).toBe('cast'));
    expect(calls().at(-1)?.query.get('cursor')).toBeNull();
    expect(dialog.getByRole('button', { name: i18n.t('pagination.previous') })).toBeDisabled();
    const before = calls().length;
    for (const value of ['cas', 'c', '']) fireEvent.change(search, { target: { value } });
    expect(dialog.getByRole('button', { name: i18n.t('pagination.next') })).toBeDisabled();
    await waitFor(() => expect(dialog.getByRole('button', { name: i18n.t('pagination.next') })).toBeEnabled());
    expect(calls().slice(before).map((call) => call.query.get('q'))).not.toContain('cas');
    expect(calls().slice(before).map((call) => call.query.get('q'))).not.toContain('c');
    expect(dialog.getByRole('button', { name: i18n.t('pagination.previous') })).toBeDisabled();
  });

  it('offers ready active data sources and restricts suggestions to the unbound type', async () => {
    const heat = elementFixture({ id: 'el-heat', localName: 'Heat', labelZh: '炉次' });
    const api = server({
      'GET /api/ontologies/:id/elements': () => [heat],
      'GET /api/ontologies/:id/elements/:elementId': () => elementDetailFixture(heat),
      'GET /api/ontologies/:id/elements/:elementId/impact': () => impactFixture(heat.id),
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
      'GET /api/ontologies/:id/bindings': () => [{ typeId: heat.id, table: null, properties: [], relations: [], openChangeSetIds: [] }],
      'GET /api/data-sources': () => [source, makeSource({ id: 'never', name: '未读取的库' }),
        { ...source, id: 'old', name: '已归档的库', status: 'archived' }],
    });
    const user = userEvent.setup();
    renderApp(`/ontology?ontology=${onto.id}&view=list`);
    const elements = within(await screen.findByRole('table', { name: '本体元素' }));
    await user.click(await elements.findByRole('button', { name: '炉次' }));
    const dialog = await openDialog(user);
    const selector = await dialog.findByRole('combobox', { name: '数据源' });
    expect(within(selector).queryByRole('option', { name: '未读取的库' })).toBeNull();
    expect(within(selector).queryByRole('option', { name: '已归档的库' })).toBeNull();
    await user.selectOptions(selector, await within(selector).findByRole('option', { name: source.name }));
    await dialog.findByRole('checkbox', { name: 'steel' });
    await user.click(dialog.getByRole('button', { name: submit }));
    await waitFor(() => expect(api.calls('POST', postPath).map((call) => call.body)).toEqual([{ ...allScope, typeIds: [heat.id] }]));
  });

  it('polls the four-step progress every two seconds, then links to review and stops', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let next = suggestion({ status: 'running', step: 'match' });
    const api = server({
      [`POST ${postPath}`]: () => jsonResponse(suggestion({ status: 'running', step: 'catalog' }), 202),
      [`GET ${pollPath}`]: () => next,
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSource(user);
    await dialog.findByRole('checkbox', { name: 'steel' });
    await user.click(dialog.getByRole('button', { name: submit }));
    expect(await dialog.findByRole('listitem', { current: 'step' })).toHaveTextContent('读取目录');
    expect(api.calls('GET', pollPath)).toHaveLength(0);
    for (const [step, label] of [['match', '匹配类型与表'], ['columns', '匹配属性与关系'], ['changeset', '生成变更集']] as const) {
      next = suggestion({ status: 'running', step });
      await act(() => vi.advanceTimersByTimeAsync(2000));
      await waitFor(() => expect(dialog.getByRole('listitem', { current: 'step' })).toHaveTextContent(label));
    }
    next = suggestion({ status: 'succeeded', changeSetId: 'cs-binding', proposed: 3, dropped: 2 });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await dialog.findByText('已生成 3 项绑定建议，等待审核')).toBeVisible();
    expect(dialog.getByText('有 2 项无法采用，已忽略')).toBeVisible();
    expect(dialog.getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-binding');
    const polls = api.calls('GET', pollPath).length;
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api.calls('GET', pollPath)).toHaveLength(polls);
  });

  it('lists dropped reasons in descending order of count', async () => {
    const dialog = await openDroppedResult(3, { 'binding.type_mismatch': 1, 'suggestion.not_in_catalog': 2 });
    expect(await dialog.findByText('有 3 项无法采用，已忽略')).toBeVisible();
    expect(dialog.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '有 2 项引用了目录里没有的表或列', '有 1 项的属性类型与列类型不匹配',
    ]);
  });

  it('groups unknown dropped reasons without exposing their codes', async () => {
    const dialog = await openDroppedResult(5, {
      'suggestion.not_in_catalog': 2, 'binding.future_rule': 1, 'suggestion.future_check': 2,
    });
    expect(await dialog.findByText('有 5 项无法采用，已忽略')).toBeVisible();
    expect(dialog.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '其他原因（3 项）', '有 2 项引用了目录里没有的表或列',
    ]);
    expect(dialog.getByRole('status')).not.toHaveTextContent(/binding\.future_rule|suggestion\.future_check/);
  });

  it.each([null, {}])('shows only the dropped total and no review link for reasons %j', async (reasons) => {
    const dialog = await openDroppedResult(1, reasons);
    expect(await dialog.findByText('没有找到可以采用的绑定建议')).toBeVisible();
    expect(dialog.getByText('有 1 项无法采用，已忽略')).toBeVisible();
    expect(dialog.getByRole('status')).toHaveTextContent(/^没有找到可以采用的绑定建议\s*有 1 项无法采用，已忽略$/);
    expect(dialog.queryByRole('list')).toBeNull();
    expect(dialog.queryByRole('link', { name: '去审核' })).toBeNull();
  });

  it('explains a failed request, retries the same scope and can return to manual binding', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let attempt = 0;
    const failure = { status: 'failed', errorCode: 'ai.not_configured' } as const;
    const api = server({
      [`POST ${postPath}`]: () => jsonResponse(++attempt === 1 ? suggestion() : suggestion({ id: 'req-2', ...failure }), 202),
      [`GET ${pollPath}`]: () => suggestion(failure),
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSource(user);
    await user.click(await dialog.findByRole('checkbox', { name: 'archive' }));
    await user.click(dialog.getByRole('button', { name: submit }));
    await dialog.findByText('正在排队');
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await dialog.findByRole('alert')).toHaveTextContent('AI 绑定建议暂不可用，已有的绑定不受影响');
    expect(dialog.getByRole('alert')).toHaveTextContent(/管理员/);
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api.calls('GET', pollPath)).toHaveLength(1);
    await user.click(dialog.getByRole('button', { name: '重试' }));
    const body = { dataSourceId: source.id, schemas: ['steel'] };
    await waitFor(() => expect(api.calls('POST', postPath).map((call) => call.body)).toEqual([body, body]));
    await user.click(await dialog.findByRole('button', { name: '改为手工绑定' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: title })).toBeNull());
  });

  it('retries reading an accepted request after a poll error without submitting it again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let missing = true;
    const api = server({
      [`POST ${postPath}`]: () => jsonResponse(suggestion(), 202),
      [`GET ${pollPath}`]: () => missing ? problemResponse(404, 'binding_suggestion.not_found') : suggestion({ status: 'succeeded' }),
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSource(user);
    await dialog.findByRole('checkbox', { name: 'steel' });
    await user.click(dialog.getByRole('button', { name: submit }));
    await dialog.findByText('正在排队');
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await dialog.findByRole('alert')).toHaveTextContent('这次 AI 绑定建议不存在。');
    missing = false;
    await user.click(dialog.getByRole('button', { name: '重试' }));
    expect(await dialog.findByText('没有找到可以采用的绑定建议')).toBeVisible();
    expect(api.calls('GET', pollPath)).toHaveLength(2);
    expect(api.calls('POST', postPath)).toHaveLength(1);
  });

  it('blocks a scope over 200 tables and allows narrowing it to the limit', async () => {
    const api = server({ 'GET /api/data-sources/:id/catalog/schemas': () => [
      { name: 'steel', tableCount: 200 }, { name: 'archive', tableCount: 1 },
    ] });
    const user = userEvent.setup();
    const dialog = await openSource(user);
    expect(await dialog.findByRole('alert')).toHaveTextContent(/200 张表/);
    const start = dialog.getByRole('button', { name: submit });
    expect(start).toBeDisabled();
    await user.click(start);
    expect(api.calls('POST', postPath)).toHaveLength(0);
    await user.click(dialog.getByRole('checkbox', { name: 'archive' }));
    await user.click(start);
    await waitFor(() => expect(api.calls('POST', postPath)[0]?.body).toEqual({ dataSourceId: source.id, schemas: ['steel'] }));
  });

  it.each([
    [422, 'binding_suggestion.scope_too_large', /200 张表、4,000 列/],
    [422, 'binding_suggestion.scope_empty', /所选范围在目录里没有表/],
    [409, 'catalog.not_ready', /先读取目录/], [409, 'datasource.archived', /数据源已归档/],
    [404, 'datasource.not_found', /数据源不存在/],
  ] as const)('localizes HTTP %i %s inside the dialog', async (status, code, message) => {
    server({ [`POST ${postPath}`]: () => problemResponse(status, code) });
    const user = userEvent.setup();
    const dialog = await openSource(user);
    await dialog.findByRole('checkbox', { name: 'steel' });
    await user.click(dialog.getByRole('button', { name: submit }));
    expect(await dialog.findByRole('alert')).toHaveTextContent(message);
  });
});
