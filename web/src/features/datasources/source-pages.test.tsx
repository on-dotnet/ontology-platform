import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, problemResponse, renderApp, userWithRole } from '@/test/utils';

import { sourceKey } from './api';
import { makeSource } from './test-fixtures';

describe('data source list', () => {
  it.each(['editor', 'reviewer', 'admin'] as const)('opens binding suggestions for the linked ontology and types as %s', async (role) => {
    const user = userEvent.setup();
    const source = makeSource({ catalog: { status: 'ready', refreshedAt: null, tableCount: 1, errorCode: null } });
    const path = '/api/ontologies/onto-steel/binding-suggestions';
    const api = mockApi({
      'GET /api/data-sources': () => [source],
      'GET /api/data-sources/:id/catalog/schemas': () => [{ name: 'steel', tableCount: 1 }],
      [`POST ${path}`]: () => ({
        id: 'suggestion-1', ontologyId: 'onto-steel', dataSourceId: source.id, status: 'succeeded', step: null,
        proposed: 0, dropped: 0, changeSetId: null, samplesSent: false, errorCode: null,
        createdAt: source.createdAt, finishedAt: source.createdAt,
      }),
    }, { user: userWithRole(role) });
    const { router } = renderApp('/data?ontologyId=onto-steel&typeIds=type-heat,type-ladle&ontology=onto-other');
    const dialog = within(await screen.findByRole('dialog', { name: 'AI 建议绑定' }));
    await user.selectOptions(await dialog.findByRole('combobox', { name: '数据源' }), source.id);
    expect(await dialog.findByRole('checkbox', { name: 'steel' })).toBeChecked();
    expect(api.calls('POST', path)).toHaveLength(0);
    await user.click(dialog.getByRole('button', { name: '生成绑定建议' }));
    await waitFor(() => expect(api.calls('POST', path).map((call) => call.body)).toEqual([{
      dataSourceId: source.id, schemas: ['steel'], typeIds: ['type-heat', 'type-ladle'],
    }]));
    await user.click(dialog.getByRole('button', { name: '关闭' }));
    await waitFor(() => expect(router.state.location.searchStr).toBe('?ontology=onto-other'));
    expect(await screen.findByRole('link', { name: source.name })).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it.each([
    ['viewer', '?ontologyId=onto-steel&typeIds=type-heat,type-ladle'],
    ['editor', '?ontologyId=onto-steel'],
    ['editor', '?typeIds=type-heat'],
    ['editor', '?ontologyId=onto-steel&typeIds=,'],
  ] as const)('keeps the data list visible for %s with %s', async (role, search) => {
    const source = makeSource();
    mockApi({ 'GET /api/data-sources': () => [source] }, { user: userWithRole(role) });
    renderApp(`/data${search}`);
    expect(await screen.findByRole('link', { name: source.name })).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it.each(['editor', 'viewer'] as const)('shows the columns available to %s', async (role) => {
    const source = makeSource();
    mockApi({ 'GET /api/data-sources': () => [source] }, { user: userWithRole(role) });
    renderApp('/data');
    const row = within(await screen.findByRole('row', { name: new RegExp(source.name) }));
    expect(row.getByText('PostgreSQL')).toBeInTheDocument();
    expect(row.getByText('未测试')).toBeInTheDocument();
    expect(row.getByText('未知')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新建数据源' })).not.toBeInTheDocument();
    if (role === 'editor') {
      expect(row.getByText('db.example.test')).toBeInTheDocument();
      expect(row.getByText('steel')).toBeInTheDocument();
    } else {
      expect(screen.queryByText('db.example.test')).not.toBeInTheDocument();
      expect(screen.queryByText('steel')).not.toBeInTheDocument();
      expect(screen.queryByRole('columnheader', { name: '主机' })).not.toBeInTheDocument();
    }
  });

  it('shows test outcomes, archive precedence, refresh time and a known zero count', async () => {
    const at = '2026-11-21T09:12:00Z';
    const good = makeSource({
      lastTest: { at, ok: true, code: null, warnings: [] }, boundTypeCount: 0,
      catalog: { status: 'ready', refreshedAt: at, tableCount: 1, errorCode: null },
    });
    const failed = makeSource({ id: 'second', name: '二号库', lastTest: { at, ok: false, code: 'datasource.connect_failed', warnings: [] } });
    mockApi({ 'GET /api/data-sources': () => [good, failed, { ...good, id: 'third', name: '旧库', status: 'archived' }] });
    renderApp('/data');
    const row = await screen.findByRole('row', { name: /冶金样例/ });
    expect(within(row).getByText('正常')).toBeInTheDocument();
    expect(within(row).getByRole('cell', { name: '0' })).toBeInTheDocument();
    expect(row.querySelector('time')).toHaveAttribute('datetime', at);
    expect(screen.getByRole('row', { name: /二号库/ })).toHaveTextContent('失败');
    expect(screen.getByRole('row', { name: /旧库/ })).toHaveTextContent('已归档');
  });

  it.each([
    ['admin', '还没有数据源'],
    ['viewer', '还没有数据源，请管理员添加'],
  ] as const)('shows an actionable empty state for %s', async (role, title) => {
    mockApi({ 'GET /api/data-sources': () => [] }, { user: userWithRole(role) });
    renderApp('/data');
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: '新建数据源' })).toHaveLength(role === 'admin' ? 1 : 0);
  });

  it('retries the list from its error notice', async () => {
    const user = userEvent.setup();
    let failed = true;
    const api = mockApi({ 'GET /api/data-sources': () => failed ? problemResponse(422, 'validation.failed') : [makeSource()] });
    renderApp('/data');
    const notice = await screen.findByRole('alert');
    failed = false;
    await user.click(within(notice).getByRole('button', { name: '重试' }));
    expect(await screen.findByRole('link', { name: '冶金样例' })).toBeInTheDocument();
    expect(api.calls('GET', '/api/data-sources')).toHaveLength(2);
  });
});

describe('saved connection and archive', () => {
  it('displays credential metadata and the recorded failure without copying a saved password into the edit form', async () => {
    const user = userEvent.setup();
    const at = '2026-11-23T09:00:00Z';
    const source = makeSource({
      credentialUpdatedAt: at,
      lastTest: { at, ok: false, code: 'datasource.credential_unreadable', warnings: [] },
    });
    const unexpectedValue = 'fixture-value-never-for-display';
    mockApi({ 'GET /api/data-sources/:id': () => ({ ...source, password: unexpectedValue }) });
    renderApp(`/data/${source.id}`);
    expect(await screen.findByText('已保存')).toBeVisible();
    expect(screen.getByText('口令更新时间').nextElementSibling?.querySelector('time')).toHaveAttribute('datetime', at);
    expect(screen.getByText('保存的口令无法读取，请重新填写口令。')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(unexpectedValue);
    await user.click(screen.getByRole('button', { name: '重新填写口令' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByLabelText(/^口令/)).toHaveValue('');
    expect(dialog.getByLabelText(/^口令/)).toHaveFocus();
    expect(screen.queryByDisplayValue(unexpectedValue)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(unexpectedValue);
  });

  it('tests the saved settings as an editor and displays write privileges', async () => {
    const user = userEvent.setup();
    const source = makeSource();
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/test': () => ({ ok: true, serverVersion: '16.4', code: null, reason: null, warnings: ['account_can_write'] }),
    }, { user: userWithRole('editor') });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '测试连接' }));
    expect(await screen.findByText('连接成功')).toBeInTheDocument();
    expect(screen.getByText(/16\.4/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '注意' })).toHaveAccessibleDescription('该账号有写权限，建议换用只读账号');
    expect(api.calls('POST', `/api/data-sources/${source.id}/test`).map((call) => call.body)).toEqual([undefined]);
    expect(screen.queryByRole('button', { name: '更多操作' })).not.toBeInTheDocument();
  });

  it('replaces a local success with a newer recorded test and its timestamp', async () => {
    const user = userEvent.setup();
    let source = makeSource();
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/test': () => {
        source = { ...source, lastTest: { at: '2026-11-23T08:00:00Z', ok: true, code: null, warnings: [] } };
        return { ok: true, serverVersion: '16.4', code: null, reason: null, warnings: [] };
      },
    });
    const { queryClient } = renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '测试连接' }));
    expect(await screen.findByText(/服务器版本 16\.4/)).toBeVisible();
    const at = '2026-11-23T09:04:00Z';
    source = { ...source, lastTest: { at, ok: false, code: 'datasource.connect_failed', warnings: [] } };
    await act(() => queryClient.refetchQueries({ queryKey: sourceKey(source.id), exact: true }));
    expect(await screen.findByText(/无法连接到数据源/)).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('连接成功')).not.toBeInTheDocument();
    expect(screen.queryByText(/16\.4/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '最近一次测试' }).parentElement?.querySelector('time')).toHaveAttribute('datetime', at);
  });

  it('keeps a local failure reason separate from a concurrent recorded failure with the same code', async () => {
    const user = userEvent.setup();
    const source = makeSource();
    let tested = false;
    const at = '2026-11-23T09:04:00Z';
    mockApi({
      'GET /api/data-sources/:id': () => tested ? {
        ...source, lastTest: { at, ok: false, code: 'datasource.connect_failed', warnings: [] },
      } : source,
      'POST /api/data-sources/:id/test': () => {
        tested = true;
        return { ok: false, code: 'datasource.connect_failed', reason: 'auth_failed', warnings: [], serverVersion: null };
      },
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '测试连接' }));
    const feedback = await screen.findByRole('region', { name: '本次连接测试' });
    expect(within(feedback).getByRole('alert')).toHaveTextContent('认证失败，请检查用户名和口令。');
    expect(feedback.querySelector('time')).toBeNull();
    const history = screen.getByRole('region', { name: '最近一次测试' });
    expect(history.querySelector('time')).toHaveAttribute('datetime', at);
    expect(history).toHaveTextContent('失败');
    expect(history).not.toHaveTextContent('认证失败');
  });

  it('offers credential repair after a failed saved test', async () => {
    const user = userEvent.setup();
    const source = makeSource();
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/test': () => problemResponse(409, 'datasource.credential_unreadable'),
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '测试连接' }));
    const notice = await screen.findByRole('alert');
    expect(notice).toHaveTextContent('保存的口令无法读取，请重新填写口令。');
    await user.click(within(notice).getByRole('button', { name: '重新填写口令' }));
    const password = within(await screen.findByRole('dialog')).getByLabelText(/^口令/);
    expect(password).toHaveFocus();
    expect(password).toBeRequired();
    expect(password).not.toHaveAttribute('placeholder');
  });

  it.each([4, 0, null])('explains an archive conflict with a bound type count of %s', async (boundTypeCount) => {
    const user = userEvent.setup();
    const source = makeSource({ boundTypeCount });
    const api = mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/archive': () => problemResponse(409, 'datasource.in_use'),
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '归档' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText(/清除.*口令/)).toHaveTextContent(/旧版本.*名称/);
    expect(api.calls('POST', `/api/data-sources/${source.id}/archive`)).toHaveLength(0);
    await user.click(dialog.getByRole('button', { name: '归档数据源' }));
    const notice = await dialog.findByRole('alert');
    expect(notice).toHaveTextContent('还有数据绑定在使用这个数据源，不能归档。');
    if (boundTypeCount === null || boundTypeCount === 0) expect(notice).not.toHaveTextContent(/\d/);
    else expect(notice).toHaveTextContent('4 个对象类型');
    const confirm = dialog.getByRole('button', { name: '归档数据源' });
    expect(confirm).toBeDisabled();
    await user.click(confirm);
    expect(api.calls('POST', `/api/data-sources/${source.id}/archive`)).toHaveLength(1);
  });

  it('updates the detail and removes all actions after archive', async () => {
    const user = userEvent.setup();
    const source = makeSource({ boundTypeCount: 0 });
    mockApi({
      'GET /api/data-sources/:id': () => source,
      'POST /api/data-sources/:id/archive': () => ({ ...source, status: 'archived', hasCredential: false }),
    });
    renderApp(`/data/${source.id}`);
    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '归档' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '归档数据源' }));
    expect(await screen.findByText('已归档')).toBeInTheDocument();
    expect(screen.getByText('未保存')).toBeInTheDocument();
    for (const name of ['更多操作', '测试连接', '读取目录', '重新填写口令']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });
});
