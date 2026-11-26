import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { components } from '@/api/schema';
import { ONTOLOGY_ID } from '@/test/fixtures';
import { problemResponse, renderApp } from '@/test/utils';

import { firstPage, heatType, mockExplore, release, searchPath, typesPath } from './test-fixtures';

afterEach(() => { vi.useRealTimers(); });

describe('explore query states', () => {
  it('shows no ontology or an entirely unavailable type list without running a search', async () => {
    const api = mockExplore({ [`GET ${typesPath}`]: () => ({
      release, items: [{ ...heatType, problem: 'source_mismatch' }],
    }) });
    const view = renderApp('/explore');
    expect(await screen.findByText('当前没有可查询的对象类型')).toBeVisible();
    expect(api.calls('POST', searchPath)).toHaveLength(0);
    view.unmount();
    mockExplore({ 'GET /api/ontologies': () => [] });
    renderApp('/explore');
    expect(await screen.findByText('还没有可探索的本体')).toBeVisible();
  });

  it('replaces protected results with the role explanation on a forbidden response', async () => {
    mockExplore({ [`POST ${searchPath}`]: () => problemResponse(403, 'auth.forbidden') });
    renderApp('/explore');
    expect(await screen.findByText('没有访问权限')).toBeVisible();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText('Q235')).toBeNull();
  });
  it('opens the selected ontology release page when it has no release', async () => {
    const api = mockExplore({ [`GET ${typesPath}`]: () => problemResponse(409, 'query.no_release') });
    renderApp('/explore');
    expect(await screen.findByRole('heading', { name: '本体还没有发布版本' })).toBeVisible();
    expect(screen.getByRole('link', { name: '去发布' })).toHaveAttribute('href', `/releases?ontology=${ONTOLOGY_ID}`);
    expect(api.calls('POST', searchPath)).toHaveLength(0);
  });

  it.each(['editor', 'viewer'] as const)('shows the no-bindings action according to the %s role', async (role) => {
    const api = mockExplore({ [`GET ${typesPath}`]: () => ({ release, items: [] }) }, role);
    renderApp('/explore');
    expect(await screen.findByRole('heading', { name: '还没有绑定数据' })).toBeVisible();
    const link = screen.queryByRole('link', { name: '去绑定数据' });
    if (role === 'editor') {
      expect(link).toBeVisible();
      const target = new URL(link?.getAttribute('href') ?? '', window.location.origin);
      expect(target.pathname).toBe('/ontology');
      expect(target.searchParams.get('ontology')).toBe(ONTOLOGY_ID);
      expect(target.searchParams.get('view')).toBe('list');
    } else expect(link).toBeNull();
    expect(api.calls('POST', searchPath)).toHaveLength(0);
  });

  it('distinguishes a table with no rows from a filtered result', async () => {
    mockExplore({ [`POST ${searchPath}`]: () => ({ ...firstPage, items: [] }) });
    renderApp('/explore');
    expect(await screen.findByRole('heading', { name: '这个类型还没有数据' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '清除筛选' })).toBeNull();
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull();
  });

  it.each([
    [502, 'source_unavailable', '无法连接到数据源', '请联系管理员检查数据源连接'],
    [504, 'timeout', '查询超时', '请增加筛选条件后重试'],
    [409, 'source_mismatch', '绑定的表或列已变更', '请联系管理员检查目录和数据绑定'],
    [503, 'busy', '数据源正忙', '请稍后重试'],
    [409, 'source_disabled', '数据源不可用', '请联系管理员检查数据源状态和凭据'],
    [422, 'invalid_filter', '筛选条件无效', '请检查筛选属性、运算符和值'],
  ] as const)('localizes and retries %s query.%s in the results area', async (status, code, reason, suggestion) => {
    let failed = true;
    const api = mockExplore({ [`POST ${searchPath}`]: () => failed ? problemResponse(status, `query.${code}`) : firstPage });
    renderApp('/explore');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(reason);
    expect(alert).toHaveTextContent(suggestion);
    expect(alert).toHaveClass('bg-error-soft');
    expect(alert).not.toHaveTextContent('Backend detail');
    expect(screen.getByRole('button', { name: '添加筛选' })).toBeEnabled();
    failed = false;
    fireEvent.click(within(alert).getByRole('button', { name: '重试' }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    expect(api.calls('POST', searchPath)).toHaveLength(2);
  });

  it.each([
    ['release_changed', 409, '本体刚发布了新版本'],
    ['invalid_cursor', 422, '当前分页位置已失效'],
  ] as const)('restarts from the first page after query.%s', async (code, status, title) => {
    let active = release;
    const api = mockExplore({
      [`GET ${typesPath}`]: () => ({ release: active, items: [heatType] }),
      [`POST ${searchPath}`]: ({ body }) => {
        if ((body as components['schemas']['ObjectSearch']).cursor) {
          if (code === 'release_changed') active = { version: 4, id: 'new' };
          return problemResponse(status, `query.${code}`);
        }
        return { ...firstPage, release: active, nextCursor: 'c1' };
      },
    });
    renderApp('/explore');
    fireEvent.click(await screen.findByRole('button', { name: '下一页' }));
    const message = await screen.findByText(title);
    if (code === 'release_changed') expect(message.closest('[role="status"]')).toHaveClass('bg-warning-soft');
    else expect(message.closest('[role="alert"]')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查询' }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    await waitFor(() => expect(api.calls('POST', searchPath).map(({ body }) => (body as components['schemas']['ObjectSearch']).cursor)).toEqual([null, 'c1', null]));
    expect(screen.getByText(`版本 v${active.version}`)).toBeVisible();
  });

  it('offers cancellation after ten seconds and aborts the actual search request', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let signal: AbortSignal | undefined;
    const api = mockExplore({
      [`POST ${searchPath}`]: ({ request }) => {
        if (signal) return firstPage;
        signal = request.signal;
        return new Promise<Response>((_, reject) => request.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
      },
    });
    renderApp('/explore');
    await waitFor(() => expect(signal).toBeDefined());
    expect(screen.queryByText('仍在查询')).toBeNull();
    expect(screen.queryByRole('button', { name: '取消' })).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(10_001));
    expect(screen.getByText('仍在查询')).toBeVisible();
    expect(signal?.aborted).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(signal?.aborted).toBe(true);
    expect(await screen.findByText('查询已取消')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    expect(api.calls('POST', searchPath)).toHaveLength(2);
  });

  it('waits for confirmation if refreshed metadata discovers a new release during pagination', async () => {
    let active = release;
    const api = mockExplore({
      [`GET ${typesPath}`]: () => ({ release: active, items: [heatType] }),
      [`POST ${searchPath}`]: ({ body }) => ({
        ...firstPage, release: active, nextCursor: (body as components['schemas']['ObjectSearch']).cursor ? null : 'c1',
      }),
    });
    const { queryClient } = renderApp('/explore');
    fireEvent.click(await screen.findByRole('button', { name: '下一页' }));
    await screen.findByRole('button', { name: '回到第一页' });
    active = { version: 4, id: 'new' };
    await act(() => queryClient.refetchQueries({ queryKey: ['explore', ONTOLOGY_ID, 'types'] }));
    const warning = await screen.findByText('本体刚发布了新版本');
    expect(warning.closest('[role="status"]')).toHaveClass('bg-warning-soft');
    expect(api.calls('POST', searchPath)).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '重新查询' }));
    expect(await screen.findByRole('table', { name: '炉次' })).toBeVisible();
    expect(screen.getByText('版本 v4')).toBeVisible();
    expect(api.calls('POST', searchPath).map(({ body }) => (body as components['schemas']['ObjectSearch']).cursor)).toEqual([null, 'c1', null]);
  });

  it('starts a new ten-second wait when filters replace a pending search', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const signals: AbortSignal[] = [];
    mockExplore({ [`POST ${searchPath}`]: ({ request }) => {
      signals.push(request.signal);
      return new Promise<Response>((_, reject) => request.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
    } });
    renderApp('/explore');
    await waitFor(() => expect(signals).toHaveLength(1));
    await act(() => vi.advanceTimersByTimeAsync(7000));
    fireEvent.click(screen.getByRole('button', { name: '添加筛选' }));
    fireEvent.change(screen.getByRole('combobox', { name: '选择运算符' }), { target: { value: 'isNull' } });
    fireEvent.click(screen.getByRole('button', { name: '应用筛选' }));
    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0]?.aborted).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(screen.queryByText('仍在查询')).toBeNull();
    expect(screen.queryByRole('button', { name: '取消' })).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(6000));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(signals[1]?.aborted).toBe(true);
  });
});
