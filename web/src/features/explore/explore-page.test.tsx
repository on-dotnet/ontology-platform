import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { components } from '@/api/schema';
import { ontologyKeys } from '@/features/ontologies/api';
import i18n from '@/i18n';
import { formatDateTime } from '@/lib/format';
import { ONTOLOGY_ID, ontologyFixture } from '@/test/fixtures';
import { problemResponse, renderApp } from '@/test/utils';

import { firstPage, heatRow, heatType, mockExplore, release, searchPath, typesPath } from './test-fixtures';

describe('explore published objects', () => {
  it('switches ontologies, searches bound types and explains unavailable types', async () => {
    const otherId = 'onto-copper';
    const other = { ...heatType, typeId: 'ingot', label: '铸锭' };
    const api = mockExplore({
      'GET /api/ontologies': () => [ontologyFixture(), ontologyFixture({ id: otherId, name: '铜冶金' })],
      [`GET ${typesPath}`]: () => ({
        release, items: [
          { ...heatType, typeId: 'broken', label: '旧表', problem: 'source_mismatch' },
          heatType, { ...heatType, typeId: 'archived', label: '归档表', problem: 'source_disabled' }, other,
        ],
      }),
      [`GET /api/ontologies/${otherId}/objects/types`]: () => ({ release: { id: 'c2', version: 2 }, items: [] }),
      [`POST ${searchPath}`]: ({ body }) => (body as components['schemas']['ObjectSearch']).typeId === 'heat'
        ? firstPage : { ...firstPage, typeId: 'ingot', items: [] },
    });
    const user = userEvent.setup();
    renderApp('/explore');
    expect(await screen.findByText('版本 v3')).toBeVisible();
    expect(screen.getByRole('button', { name: '关于“探索”' })).toHaveAccessibleDescription('这里显示的是已发布版本的数据');
    expect(screen.getByRole('button', { name: /旧表/ })).toBeDisabled();
    expect(screen.getByText('绑定的表或列已变更')).toBeVisible();
    expect(screen.getByRole('button', { name: /归档表/ })).toBeDisabled();
    expect(screen.getByText('数据源已停用或凭据不可用')).toBeVisible();
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    const search = screen.getByRole('searchbox', { name: '搜索对象类型' });
    await user.type(search, '铸');
    expect(screen.queryByRole('button', { name: '炉次' })).toBeNull();
    await user.click(screen.getByRole('button', { name: '铸锭' }));
    expect(await screen.findByText('这个类型还没有数据')).toBeVisible();
    expect(api.calls('POST', searchPath).map((r) => (r.body as components['schemas']['ObjectSearch']).typeId)).toEqual(['heat', 'ingot']);
    const selector = screen.getByRole('combobox', { name: '本体' });
    expect(selector).toHaveValue(ONTOLOGY_ID);
    await user.selectOptions(selector, otherId);
    expect(await screen.findByText('版本 v2')).toBeVisible();
    expect(screen.queryByText('版本 v3')).toBeNull();
    expect(screen.queryByText('这个类型还没有数据')).toBeNull();
  });

  it('shows human-readable keys first, only bound columns and lossless values', async () => {
    mockExplore({
      [`POST ${searchPath}`]: () => ({ ...firstPage, items: [{ ...heatRow, values: { ...heatRow.values, private: 'unbound-value' } }] }),
    });
    renderApp('/explore');
    const table = within(await screen.findByRole('table', { name: '炉次' }));
    const headers = table.getAllByRole('columnheader');
    expect(headers).toHaveLength(5);
    expect(headers[0]).toHaveTextContent('主键');
    for (const text of ['钢种', '重量', '数量', '已检验']) expect(table.getByRole('columnheader', { name: new RegExp(text) })).toBeVisible();
    expect(table.getAllByRole('cell')[0]).toHaveTextContent('H2401001 · A');
    expect(table.getByText('123.45000')).toBeVisible();
    expect(table.getByText('9007199254740993')).toBeVisible();
    expect(table.getByText('否')).toBeVisible();
    expect(table.getByText('已截断')).toBeVisible();
    expect(screen.queryByText('opaque-heat')).toBeNull();
    expect(screen.queryByText('unbound-value')).toBeNull();
  });

  it('localizes the column unit punctuation when the language changes', async () => {
    mockExplore();
    renderApp('/explore');
    expect(await screen.findByRole('columnheader', { name: '重量（t）' })).toBeVisible();
    await act(async () => { await i18n.changeLanguage('en'); });
    expect(screen.getByRole('columnheader', { name: '重量 (t)' })).toBeVisible();
    expect(screen.getByRole('columnheader', { name: '钢种' })).toBeVisible();
  });

  it('posts filters, removes their chips and clears an empty filtered result', async () => {
    const api = mockExplore({
      [`POST ${searchPath}`]: ({ body }) => (body as components['schemas']['ObjectSearch']).filters?.length
        ? { ...firstPage, items: [] } : firstPage,
    });
    const user = userEvent.setup();
    renderApp('/explore');
    const add = async () => {
      await user.click(await screen.findByRole('button', { name: '添加筛选' }));
      await user.selectOptions(screen.getByRole('combobox', { name: '选择属性' }), 'grade');
      const operator = screen.getByRole('combobox', { name: '选择运算符' });
      expect(within(operator).getAllByRole('option').map((opt) => (opt as HTMLOptionElement).value)).toEqual(['eq', 'in', 'isNull']);
      await user.selectOptions(operator, 'eq');
      await user.type(screen.getByRole('textbox', { name: '筛选值' }), 'Q999');
      await user.click(screen.getByRole('button', { name: '应用筛选' }));
      expect(await screen.findByText('没有符合条件的对象')).toBeVisible();
      expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({ typeId: 'heat', filters: [{ propertyId: 'grade', op: 'eq', value: 'Q999' }] });
    };
    await screen.findByRole('table', { name: '炉次' });
    await add();
    await user.click(screen.getByRole('button', { name: /移除.*Q999/ }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    await waitFor(() => expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({ filters: [] }));
    await add();
    const clear = () => screen.getByRole('button', { name: '清除筛选' });
    expect(clear()).toHaveClass('bg-primary');
    await user.click(screen.getByRole('button', { name: '添加筛选' }));
    expect(screen.getByRole('button', { name: '应用筛选' })).toHaveClass('bg-primary');
    expect(clear()).toHaveClass('bg-card', 'border-border');
    expect(clear()).not.toHaveClass('bg-primary');
    await user.click(screen.getByRole('button', { name: '取消' }));
    expect(clear()).toHaveClass('bg-primary');
    await user.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    expect(screen.queryByRole('button', { name: /移除.*Q999/ })).toBeNull();
  });

  it('shows calendar dates, preserves unzoned times and formats zoned times as absolute instants', async () => {
    const properties: components['schemas']['ObjectProperty'][] = [
      { propertyId: 'day', label: '生产日', datatype: 'date', unit: null, ops: ['eq'] },
      { propertyId: 'dateColumn', label: '日期列', datatype: 'dateTime', unit: null, ops: ['eq'] },
      { propertyId: 'time', label: '出炉时间', datatype: 'dateTime', unit: null, ops: ['eq'] },
      { propertyId: 'local', label: '现场时间', datatype: 'dateTime', unit: null, ops: ['eq'] },
      { propertyId: 'utc', label: 'UTC', datatype: 'dateTime', unit: null, ops: ['eq'] },
    ];
    const time = '2024-03-02T00:30:00+08:00';
    const local = '2024-03-10T02:30:45.123456';
    const utc = '2024-03-01T16:30:00Z';
    mockExplore({
      [`GET ${typesPath}`]: () => ({ release, items: [{ ...heatType, properties }] }),
      [`POST ${searchPath}`]: () => ({
        ...firstPage, items: [{ ...heatRow, values: { day: '2024-03-01', dateColumn: '2024-03-01', time, local, utc } }],
      }),
    });
    renderApp('/explore');
    const table = await screen.findByRole('table', { name: '炉次' });
    const dates = table.querySelectorAll('time[datetime="2024-03-01"]');
    expect(dates).toHaveLength(2);
    for (const date of dates) expect(date.textContent).toBe('2024年3月1日');
    expect(table.querySelector(`time[datetime="${local}"]`)?.textContent).toBe(local);
    const expected = formatDateTime(utc, 'zh-CN');
    for (const instant of [time, utc]) {
      expect(table.querySelector(`time[datetime="${instant}"]`)?.textContent).toBe(expected);
    }
  });

  it('sends the cursor, ends pagination at null and starts a changed sort on the first page', async () => {
    const api = mockExplore({
      [`POST ${searchPath}`]: ({ body }) => ({
        ...firstPage, nextCursor: (body as components['schemas']['ObjectSearch']).cursor ? null : 'next-opaque',
      }),
    });
    renderApp('/explore');
    fireEvent.click(await screen.findByRole('button', { name: '下一页' }));
    await waitFor(() => expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({ cursor: 'next-opaque' }));
    await screen.findByRole('table', { name: '炉次' });
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull();

    async function sortBy(label: string, sorts: components['schemas']['Sort'][]) {
      const table = within(await screen.findByRole('table', { name: '炉次' }));
      fireEvent.click(within(table.getByRole('columnheader', { name: new RegExp(label) })).getByRole('button'));
      await waitFor(() => expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({ cursor: null, sort: sorts }));
    }
    await sortBy('重量', [{ propertyId: 'weight', direction: 'asc' }]);
    await sortBy('钢种', [{ propertyId: 'weight', direction: 'asc' }, { propertyId: 'grade', direction: 'asc' }]);
    await sortBy('重量', [{ propertyId: 'weight', direction: 'desc' }, { propertyId: 'grade', direction: 'asc' }]);
    await sortBy('数量', [{ propertyId: 'weight', direction: 'desc' }, { propertyId: 'count', direction: 'asc' }]);
    await sortBy('重量', [{ propertyId: 'count', direction: 'asc' }]);
  });

  it('opens a detail from a data cell and returns to the same list page', async () => {
    const last = { ...heatRow, key: 'last', source: { ...heatRow.source, key: [{ column: 'heat_no', value: 'H99' }] } };
    const api = mockExplore({
      [`POST ${searchPath}`]: ({ body }) => (body as components['schemas']['ObjectSearch']).cursor
        ? { ...firstPage, items: [last] } : { ...firstPage, nextCursor: 'after-first' },
      [`GET /api/ontologies/${ONTOLOGY_ID}/objects/heat/last`]: () => ({ ...last, release, relations: [] }),
    });
    renderApp('/explore');
    fireEvent.click(await screen.findByRole('button', { name: '下一页' }));
    const row = await screen.findByRole('row', { name: /H99/ });
    fireEvent.click(within(row).getByRole('cell', { name: '123.45000' }));
    expect(await screen.findByRole('region', { name: '来源' })).toHaveTextContent('heat_no = H99');
    const trail = within(screen.getByRole('navigation', { name: '浏览路径' }));
    fireEvent.click(trail.getByRole('button', { name: '炉次' }));
    expect(await screen.findByRole('button', { name: 'H99' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull();
    expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({ cursor: 'after-first' });
  });

  it('keeps the selected object, filters and cursor while metadata refreshes in the background', async () => {
    const user = userEvent.setup();
    let delay = false;
    let fail = true;
    let finish!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const api = mockExplore({
      'GET /api/ontologies': async () => { if (delay) await pending; return [ontologyFixture()]; },
      [`GET ${typesPath}`]: async () => {
        if (delay) {
          await pending;
          if (fail) return problemResponse(502, 'query.source_unavailable');
        }
        return { release, items: [heatType] };
      },
      [`POST ${searchPath}`]: ({ body }) => ({
        ...firstPage, nextCursor: (body as components['schemas']['ObjectSearch']).cursor ? null : 'after-heat',
      }),
      [`GET /api/ontologies/${ONTOLOGY_ID}/objects/heat/opaque-heat`]: () => ({ ...heatRow, release, relations: [] }),
    });
    const { queryClient } = renderApp('/explore');
    await user.click(await screen.findByRole('button', { name: '添加筛选' }));
    await user.type(screen.getByRole('textbox', { name: '筛选值' }), 'Q235');
    await user.click(screen.getByRole('button', { name: '应用筛选' }));
    await user.click(await screen.findByRole('button', { name: '下一页' }));
    await user.click(await screen.findByRole('button', { name: 'H2401001 · A' }));
    expect(await screen.findByRole('region', { name: '来源' })).toBeVisible();
    delay = true;
    const refresh = Promise.all([
      queryClient.refetchQueries({ queryKey: ontologyKeys.list() }),
      queryClient.refetchQueries({ queryKey: ['explore', ONTOLOGY_ID, 'types'] }),
    ]);
    await waitFor(() => expect(api.calls('GET', typesPath)).toHaveLength(2));
    expect(screen.getByRole('region', { name: '来源' })).toBeVisible();
    await act(async () => { finish(); await refresh; });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接到数据源');
    fail = false;
    await user.click(within(alert).getByRole('button', { name: '重试' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(screen.getByRole('region', { name: '来源' })).toBeVisible();
    const trail = within(screen.getByRole('navigation', { name: '浏览路径' }));
    await user.click(trail.getByRole('button', { name: '炉次' }));
    expect(await screen.findByRole('button', { name: '回到第一页' })).toBeVisible();
    expect(screen.getByRole('button', { name: /移除筛选.*Q235/ })).toBeVisible();
    expect(api.calls('POST', searchPath).at(-1)?.body).toMatchObject({
      cursor: 'after-heat', filters: [{ propertyId: 'grade', op: 'eq', value: 'Q235' }],
    });
  });

  it.each(['', '   '])('opens an object whose text key %j has no visible characters', async (value) => {
    const row = { ...heatRow, source: { ...heatRow.source, key: [{ column: 'heat_no', value }] } };
    mockExplore({
      [`POST ${searchPath}`]: () => ({ ...firstPage, items: [row] }),
      [`GET /api/ontologies/${ONTOLOGY_ID}/objects/heat/opaque-heat`]: () => ({ ...row, release, relations: [] }),
    });
    renderApp('/explore');
    fireEvent.click(await screen.findByRole('button', { name: '空白值' }));
    expect(await screen.findByRole('region', { name: '来源' })).toHaveTextContent('heat_no = 空白值');
    expect(screen.getByRole('navigation', { name: '浏览路径' })).toHaveTextContent('空白值');
  });
});
