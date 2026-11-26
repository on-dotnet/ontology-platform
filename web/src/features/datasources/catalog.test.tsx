import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { components } from '@/api/schema';
import { meQueryKey, type UserInfo } from '@/features/auth/api';
import { jsonResponse, mockApi, problemResponse, renderApp, userWithRole } from '@/test/utils';

import { makeSource } from './test-fixtures';

const refreshedAt = '2026-04-08T10:20:30Z';
const nextRefreshedAt = '2026-04-08T10:25:30Z';
const ready: components['schemas']['CatalogInfo'] = { status: 'ready', refreshedAt, errorCode: null, tableCount: 2 };
const heat: components['schemas']['CatalogTableBrief'] = {
  schema: 'steel', name: 'heat', kind: 'table', columnCount: 2, comment: null,
  boundType: { id: '00000000-0000-4000-8000-000000000011', label: '炉次' },
};
const detail: components['schemas']['CatalogTable'] = {
  ...heat, refreshedAt,
  columns: [
    { name: 'heat_no', type: 'text', family: 'string', nullable: false, comment: '炉次号', position: 1 },
    { name: 'cast_no', type: 'integer', family: 'integer', nullable: true, comment: null, position: 2 },
  ],
  primaryKey: ['heat_no'],
  foreignKeys: [{ name: 'fk_heat_cast', columns: ['cast_no'], refSchema: 'mes', refTable: 'casting', refColumns: ['id'] }],
};
const panel = () => screen.findByRole('region', { name: '目录' });

afterEach(() => { vi.useRealTimers(); });

describe('data source catalog', () => {
  it('starts the first refresh, polls the detail every second, and stops at ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const source = makeSource();
    const busy = { ...source, catalog: { ...ready, refreshedAt: null, tableCount: 0, status: 'refreshing' as const } };
    let started = false;
    let finished = false;
    const endpoint = `/api/data-sources/${source.id}`;
    const api = mockApi({
      [`GET ${endpoint}`]: () => finished ? { ...source, catalog: ready } : started ? busy : source,
      [`POST ${endpoint}/catalog/refresh`]: () => {
        started = true;
        return jsonResponse(busy, 202);
      },
      [`GET ${endpoint}/catalog/schemas`]: () => [{ name: 'steel', tableCount: 2 }],
    }, { user: userWithRole('editor') });
    renderApp(`/data/${source.id}`);
    const region = await panel();
    const catalog = within(region);
    expect(catalog.getByText('还没有读取目录')).toBeVisible();
    fireEvent.click(catalog.getByRole('button', { name: '读取目录' }));
    const progress = await catalog.findByRole('status');
    expect(progress).toHaveTextContent('正在读取目录');
    expect(progress).toHaveAttribute('aria-live', 'polite');
    const skeleton = region.querySelector('[aria-busy="true"]');
    expect(skeleton).toBeInTheDocument();
    expect(progress.closest('[aria-busy="true"]')).toBeNull();
    expect(api.calls('POST', `${endpoint}/catalog/refresh`)).toHaveLength(1);
    const before = api.calls('GET', endpoint).length;
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(api.calls('GET', endpoint)).toHaveLength(before + 1);
    expect(catalog.queryByText('仍在读取')).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(9100));
    expect(progress).toHaveTextContent('仍在读取');
    expect(progress).toBeVisible();
    expect(skeleton).toHaveAttribute('aria-busy', 'true');
    expect(api.calls('GET', `${endpoint}/catalog/schemas`)).toHaveLength(0);
    finished = true;
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(await catalog.findByRole('treeitem', { name: 'steel' })).toBeVisible();
    const done = api.calls('GET', endpoint).length;
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(api.calls('GET', endpoint)).toHaveLength(done);
  });

  it('shows the localized failure and retries the refresh', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: { status: 'failed', refreshedAt: null, tableCount: 0, errorCode: 'datasource.connect_failed' } });
    const endpoint = `/api/data-sources/${source.id}`;
    let accepted = false;
    const api = mockApi({
      [`GET ${endpoint}`]: () => accepted ? { ...source, catalog: ready } : source,
      [`POST ${endpoint}/catalog/refresh`]: () => accepted
        ? jsonResponse({ ...source, catalog: { status: 'refreshing', refreshedAt: null, tableCount: 0, errorCode: null } }, 202)
        : problemResponse(409, 'datasource.credential_unreadable'),
      [`GET ${endpoint}/catalog/schemas`]: () => [{ name: 'steel', tableCount: 2 }],
    });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    expect(catalog.getByText('无法连接到数据源，请检查地址、账号和口令后重试。')).toBeVisible();
    expect(catalog.queryByRole('alert')).toBeNull();
    expect(api.requests.filter(({ path }) => path.includes('/catalog/'))).toEqual([]);
    await user.click(catalog.getByRole('button', { name: '重试' }));
    expect(await catalog.findByRole('alert')).toHaveTextContent('保存的口令无法读取，请重新填写口令。');
    expect(catalog.queryByText('无法连接到数据源，请检查地址、账号和口令后重试。')).toBeNull();
    expect(api.calls('POST', `${endpoint}/catalog/refresh`)).toHaveLength(1);
    accepted = true;
    await user.click(catalog.getByRole('button', { name: '重试' }));
    expect(await catalog.findByRole('treeitem', { name: 'steel' })).toBeVisible();
    expect(catalog.queryByRole('alert')).toBeNull();
    expect(api.calls('POST', `${endpoint}/catalog/refresh`)).toHaveLength(2);
  });

  it('shows a scope warning for an oversized catalog and an edit action for the admin', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: { ...ready, status: 'failed', errorCode: 'catalog.too_large' } });
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 2 }],
    });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    expect(catalog.getByText('表或列太多，请在数据源里填写模式范围后再读取。')).toBeVisible();
    expect(await catalog.findByRole('treeitem', { name: 'steel' })).toBeVisible();
    expect(catalog.queryByRole('status')).toBeNull();
    await user.click(catalog.getByRole('button', { name: '编辑数据源' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeVisible();
    expect(within(dialog).getByLabelText(/^口令/)).not.toBeRequired();
  });

  it('opens password repair for an unreadable credential reported by the refresh request', async () => {
    const user = userEvent.setup();
    const source = makeSource();
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/catalog/refresh': () => problemResponse(409, 'datasource.credential_unreadable'),
    });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    await user.click(catalog.getByRole('button', { name: '读取目录' }));
    expect(await catalog.findByRole('alert')).toHaveTextContent('保存的口令无法读取，请重新填写口令。');
    await user.click(catalog.getByRole('button', { name: '编辑数据源' }));
    const password = within(await screen.findByRole('dialog')).getByLabelText(/^口令/);
    expect(password).toBeRequired();
    expect(password).toHaveFocus();
    expect(password).not.toHaveAttribute('placeholder');
  });

  it.each(['redacted', 'full'] as const)('restricts the viewer detail page with a %s source response', async (response) => {
    const source = response === 'redacted' ? makeSource({ connection: null, catalog: null }) : makeSource({ catalog: ready });
    const api = mockApi({ 'GET /api/data-sources/:id': () => source }, { user: userWithRole('viewer') });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    expect(catalog.getByText('浏览数据源的目录需要编辑者以上角色')).toBeVisible();
    expect(catalog.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('button', { name: '测试连接' })).toBeNull();
    expect(screen.queryByRole('button', { name: '更多操作' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '连接信息' })).toBeNull();
    expect(api.requests.filter(({ path }) => path.includes('/catalog/'))).toEqual([]);
  });

  it.each(['next page', 'table detail', 'refresh'] as const)('hides the entire open catalog when %s returns 403', async (denied) => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: ready });
    const endpoint = `/api/data-sources/${source.id}`;
    const forbidden = () => problemResponse(403, 'auth.forbidden');
    const api = mockApi({
      [`GET ${endpoint}`]: () => source,
      [`GET ${endpoint}/catalog/schemas`]: () => [{ name: 'steel', tableCount: 3 }],
      [`GET ${endpoint}/catalog/tables`]: ({ query }) => query.get('cursor') === 'next' ? forbidden() : {
        items: [heat, { ...heat, name: 'slab' }], nextCursor: 'next',
      },
      [`GET ${endpoint}/catalog/tables/steel/heat`]: () => detail,
      [`GET ${endpoint}/catalog/tables/steel/slab`]: forbidden,
      [`POST ${endpoint}/catalog/refresh`]: forbidden,
    });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    await user.click(await catalog.findByRole('treeitem', { name: 'steel' }));
    await user.click(await catalog.findByRole('treeitem', { name: 'heat' }));
    expect(await catalog.findByText('heat_no')).toBeVisible();
    const meReads = api.calls('GET', '/api/auth/me').length;
    const sourceReads = api.calls('GET', endpoint).length;
    if (denied === 'table detail') await user.click(catalog.getByRole('treeitem', { name: 'slab' }));
    else await user.click(catalog.getByRole('button', { name: denied === 'next page' ? '加载更多表' : '读取目录' }));
    expect(await catalog.findByText('浏览数据源的目录需要编辑者以上角色')).toBeVisible();
    expect(catalog.queryByRole('tree')).toBeNull();
    expect(catalog.queryByRole('table')).toBeNull();
    expect(catalog.queryByRole('searchbox')).toBeNull();
    expect(catalog.queryByRole('button')).toBeNull();
    expect(catalog.queryByText('heat_no')).toBeNull();
    expect(catalog.queryByText('fk_heat_cast')).toBeNull();
    await waitFor(() => {
      expect(api.calls('GET', '/api/auth/me').length).toBeGreaterThan(meReads);
      expect(api.calls('GET', endpoint).length).toBeGreaterThan(sourceReads);
    });
  });

  it('keeps catalog access and retries a refresh rejected by CSRF validation', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: ready });
    let accepted = false;
    let refreshed = false;
    const api = mockApi({
      'GET /api/data-sources/:id': () => {
        refreshed = accepted;
        return refreshed ? { ...source, catalog: { ...ready, refreshedAt: nextRefreshedAt } } : source;
      },
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: refreshed ? 'mes' : 'steel', tableCount: 2 }],
      'POST /api/data-sources/:id/catalog/refresh': () => accepted
        ? jsonResponse({ ...source, catalog: { ...ready, status: 'refreshing' } }, 202)
        : problemResponse(403, 'auth.csrf_failed'),
    });
    renderApp(`/data/${source.id}`);
    const catalog = within(await panel());
    await catalog.findByRole('treeitem', { name: 'steel' });
    await user.click(catalog.getByRole('button', { name: '读取目录' }));
    expect(await catalog.findByRole('alert')).toHaveTextContent('页面已过期，请刷新页面后重试。');
    expect(catalog.getByRole('treeitem', { name: 'steel' })).toBeVisible();
    expect(catalog.queryByText('浏览数据源的目录需要编辑者以上角色')).toBeNull();
    accepted = true;
    await user.click(catalog.getByRole('button', { name: '重试' }));
    expect(await catalog.findByRole('treeitem', { name: 'mes' })).toBeVisible();
    expect(api.calls('POST', `/api/data-sources/${source.id}/catalog/refresh`)).toHaveLength(2);
  });

  it('reopens the catalog on the same page when the viewer regains editor access', async () => {
    const source = makeSource({ catalog: ready });
    let role: UserInfo['role'] = 'editor';
    let firstRead = true;
    mockApi({
      'GET /api/data-sources/:id': () => role === 'viewer' ? { ...source, connection: null, catalog: null } : source,
      'GET /api/data-sources/:id/catalog/schemas': () => {
        if (firstRead) {
          firstRead = false;
          role = 'viewer';
        }
        return role === 'viewer' ? problemResponse(403, 'auth.forbidden') : [{ name: 'mes', tableCount: 2 }];
      },
    }, { user: () => userWithRole(role) });
    const { queryClient } = renderApp(`/data/${source.id}`);
    await waitFor(() => {
      expect(queryClient.getQueryData<UserInfo>(meQueryKey)?.role).toBe('viewer');
      expect(screen.getByText('浏览数据源的目录需要编辑者以上角色')).toBeVisible();
      expect(screen.queryByText('db.example.test')).toBeNull();
    });
    role = 'editor';
    await act(() => queryClient.invalidateQueries({ queryKey: meQueryKey, exact: true }));
    expect(await screen.findByRole('treeitem', { name: 'mes' })).toBeVisible();
    expect(screen.getByRole('button', { name: '读取目录' })).toBeVisible();
  });

  it.each(['ready', 'refreshing', 'failed'] as const)('browses an archived snapshot when the last job is %s', async (status) => {
    const source = makeSource({ status: 'archived', catalog: { ...ready, status }, hasCredential: false });
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 2 }],
    });
    renderApp(`/data/${source.id}`);
    expect(await screen.findByRole('treeitem', { name: 'steel' })).toBeVisible();
    expect((await panel()).querySelector('[aria-busy="true"]')).toBeNull();
    expect(screen.queryByRole('button', { name: '读取目录' })).toBeNull();
    expect(screen.queryByRole('button', { name: '编辑数据源' })).toBeNull();
    expect(api.calls('POST', `/api/data-sources/${source.id}/catalog/refresh`)).toHaveLength(0);
  });

  it('does not wait or poll for a first refresh interrupted by archive', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const source = makeSource({
      status: 'archived', hasCredential: false, catalog: { ...ready, status: 'refreshing', refreshedAt: null, tableCount: 0 },
    });
    const api = mockApi({ 'GET /api/data-sources/:id': () => source });
    renderApp(`/data/${source.id}`);
    expect(await screen.findByRole('heading', { name: source.name })).toBeVisible();
    const endpoint = `/api/data-sources/${source.id}`;
    const before = api.calls('GET', endpoint).length;
    await act(() => vi.advanceTimersByTimeAsync(11_000));
    expect(screen.queryByText('仍在读取')).toBeNull();
    expect(api.calls('GET', endpoint)).toHaveLength(before);
    expect(api.requests.filter(({ path }) => path.includes('/catalog/'))).toEqual([]);
  });

  it('keeps the newer archive when the accepted refresh response arrives late', async () => {
    const user = userEvent.setup();
    const source = makeSource({ boundTypeCount: 0 });
    const archived = { ...source, status: 'archived', hasCredential: false, revision: source.revision + 2 };
    let deliver!: () => void;
    const delayed = new Promise<void>((resolve) => { deliver = resolve; });
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/catalog/refresh': async () => {
        await delayed;
        return jsonResponse({ ...source, revision: source.revision + 1, catalog: { ...ready, status: 'refreshing' } }, 202);
      },
      'POST /api/data-sources/:id/archive': () => archived,
    });
    const { queryClient } = renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '读取目录' }));
    expect(api.calls('POST', `/api/data-sources/${source.id}/catalog/refresh`)).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '归档' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '归档数据源' }));
    expect(await screen.findByText('已归档')).toBeVisible();
    await act(async () => {
      deliver();
      await waitFor(() => expect(queryClient.isMutating()).toBe(0));
    });
    expect(screen.getByText('已归档')).toBeVisible();
    expect(screen.queryByRole('button', { name: '更多操作' })).toBeNull();
    expect(screen.queryByRole('button', { name: '读取目录' })).toBeNull();
  });

  it('opens a schema and table by keyboard and shows the column and foreign-key metadata', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: ready });
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 1 }],
      'GET /api/data-sources/:id/catalog/tables': () => ({ items: [heat], nextCursor: null }),
      'GET /api/data-sources/:id/catalog/tables/steel/heat': () => detail,
    });
    renderApp(`/data/${source.id}`);
    const tree = await screen.findByRole('tree', { name: '模式与表' });
    expect(tree).toHaveAttribute('tabindex', '-1');
    const schema = within(tree).getByRole('treeitem', { name: 'steel' });
    expect(schema).toHaveAttribute('tabindex', '0');
    act(() => schema.focus());
    await user.keyboard('{ArrowRight}');
    expect(schema).toHaveAttribute('aria-expanded', 'true');
    const table = await within(tree).findByRole('treeitem', { name: 'heat' });
    expect(within(table).getByText('炉次')).toBeVisible();
    expect(table).toHaveAccessibleDescription('绑定的对象类型：炉次');
    await user.keyboard('{ArrowDown}');
    expect(table).toHaveFocus();
    expect(table).toHaveAttribute('tabindex', '0');
    expect(schema).toHaveAttribute('tabindex', '-1');
    await user.keyboard('{Enter}');
    const columns = await screen.findByRole('table', { name: '列' });
    const primaryRow = within(within(columns).getByRole('row', { name: /heat_no/ }));
    expect(primaryRow.getByText('主键')).toBeVisible();
    for (const name of ['text', '否', '炉次号']) expect(primaryRow.getByRole('cell', { name })).toBeVisible();
    const foreignRow = within(within(columns).getByRole('row', { name: /cast_no/ }));
    expect(foreignRow.getByText('外键')).toBeVisible();
    for (const name of ['integer', '是']) expect(foreignRow.getByRole('cell', { name })).toBeVisible();
    expect(screen.getByText('fk_heat_cast').closest('li')).toHaveTextContent('cast_no → mes.casting(id)');
    expect(screen.getByText('绑定的对象类型：炉次')).toBeVisible();
    expect(api.calls('GET', `/api/data-sources/${source.id}/catalog/tables`)[0]?.query.get('schema')).toBe('steel');
    await user.keyboard('{ArrowLeft}');
    expect(schema).toHaveFocus();
  });

  it('clears the selected table when switching schemas even when both have a table of the same name', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: ready });
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 1 }, { name: 'mes', tableCount: 1 }],
      'GET /api/data-sources/:id/catalog/tables': ({ query }) => ({
        items: [{ ...heat, schema: query.get('schema') }], nextCursor: null,
      }),
      'GET /api/data-sources/:id/catalog/tables/:schema/heat': ({ params }) => ({ ...detail, schema: params.schema }),
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('treeitem', { name: 'steel' }));
    await user.click(await screen.findByRole('treeitem', { name: 'heat' }));
    expect(await screen.findByRole('heading', { name: 'steel.heat' })).toBeVisible();
    await user.click(screen.getByRole('treeitem', { name: 'mes' }));
    expect(screen.queryByRole('heading', { name: 'steel.heat' })).toBeNull();
    const nextTable = await screen.findByRole('treeitem', { name: 'heat' });
    expect(nextTable).toHaveAttribute('aria-selected', 'false');
    await user.click(nextTable);
    expect(await screen.findByRole('heading', { name: 'mes.heat' })).toBeVisible();
  });

  it('searches across schemas and appends the next page with the same search term', async () => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: ready });
    const endpoint = `/api/data-sources/${source.id}/catalog/tables`;
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 1 }, { name: 'mes', tableCount: 1 }],
      [`GET ${endpoint}`]: ({ query }) => query.get('cursor') === 'page-two'
        ? { items: [{ ...heat, schema: 'mes', name: 'heat_history' }], nextCursor: null }
        : { items: [heat], nextCursor: 'page-two' },
    });
    renderApp(`/data/${source.id}`);
    const input = await screen.findByRole('searchbox', { name: '搜索表名' });
    await user.type(input, 'heat');
    await waitFor(() => expect(api.calls('GET', endpoint).at(-1)?.query.get('q')).toBe('heat'));
    await user.click(await screen.findByRole('button', { name: '加载更多表' }));
    expect(await screen.findByRole('treeitem', { name: 'heat_history' })).toBeVisible();
    expect(screen.getByRole('treeitem', { name: 'heat' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '加载更多表' })).toBeNull();
    const query = api.calls('GET', endpoint).at(-1)?.query;
    expect(query?.get('limit')).toBe('50');
    expect(query?.get('q')).toBe('heat');
    expect(query?.get('cursor')).toBe('page-two');
    expect(query?.has('schema')).toBe(false);
  });

  it('discards fresh client-side catalog entries when the server catalog is replaced', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const initialCatalog = { ...ready, tableCount: 1 };
    const source = makeSource({ catalog: initialCatalog });
    const busy = { ...source, catalog: { ...initialCatalog, status: 'refreshing' } };
    let started = false;
    let refreshed = false;
    mockApi({
      'GET /api/data-sources/:id': () => refreshed
        ? { ...source, catalog: { ...ready, refreshedAt: nextRefreshedAt, tableCount: 3 } }
        : started ? busy : source,
      'POST /api/data-sources/:id/catalog/refresh': () => {
        started = true;
        return jsonResponse(busy, 202);
      },
      'GET /api/data-sources/:id/catalog/schemas': () => refreshed
        ? [{ name: 'steel', tableCount: 2 }, { name: 'mes', tableCount: 1 }]
        : [{ name: 'steel', tableCount: 1 }],
      'GET /api/data-sources/:id/catalog/tables': () => ({
        items: refreshed ? [heat, { ...heat, name: 'casting' }] : [heat], nextCursor: null,
      }),
      'GET /api/data-sources/:id/catalog/tables/steel/heat': () => ({
        ...detail, refreshedAt: refreshed ? nextRefreshedAt : refreshedAt, comment: refreshed ? '新表注释' : '旧表注释',
      }),
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('treeitem', { name: 'steel' }));
    await user.click(await screen.findByRole('treeitem', { name: 'heat' }));
    expect(await screen.findByText('旧表注释')).toBeVisible();
    await user.click(screen.getByRole('button', { name: '读取目录' }));
    const region = await panel();
    const catalog = within(region);
    expect(await catalog.findByRole('status')).toHaveTextContent('正在读取目录');
    await act(() => vi.advanceTimersByTimeAsync(10_100));
    expect(catalog.getByText('仍在读取')).toBeVisible();
    expect(catalog.getByText('上次读取')).toBeVisible();
    expect(region.querySelector('time')).toHaveAttribute('datetime', refreshedAt);
    expect(catalog.getByRole('treeitem', { name: 'heat', selected: true })).toBeVisible();
    expect(catalog.getByText('旧表注释')).toBeVisible();
    refreshed = true;
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(await screen.findByRole('treeitem', { name: 'mes' })).toBeVisible();
    expect(region.querySelector('time')).toHaveAttribute('datetime', nextRefreshedAt);
    const schema = await screen.findByRole('treeitem', { name: 'steel', expanded: false });
    await user.click(schema);
    expect(await screen.findByRole('treeitem', { name: 'casting' })).toBeVisible();
    await user.click(screen.getByRole('treeitem', { name: 'heat' }));
    expect(await screen.findByText('新表注释')).toBeVisible();
    expect(screen.queryByText('旧表注释')).toBeNull();
  });
});
