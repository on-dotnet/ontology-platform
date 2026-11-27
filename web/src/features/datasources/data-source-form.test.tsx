import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, problemResponse, renderApp, type RouteHandler } from '@/test/utils';

import { sourceKey } from './api';
import { initialForm, patchRequest } from './data-source-form';
import { makeSource } from './test-fixtures';

const collection = '/api/data-sources';
const testPath = `${collection}/test`;
const sampleWarning = '打开后，AI 建议绑定时会读取每列最多 5 个值并发送给模型服务；这些值会作为证据显示在审核页，所有登录用户都能看到';
const success = { ok: true, code: null, reason: null, warnings: [], serverVersion: '16.4' };
const newPassword = ' test-only value ';

async function openForm(mode: 'create' | 'edit', routes: Record<string, RouteHandler> = {}) {
  const source = makeSource();
  const api = mockApi({
    [`GET ${collection}`]: () => [source],
    [`GET ${collection}/:id`]: () => source,
    ...routes,
  });
  // These tests type whole connection settings; without the per-key pause they stay well inside
  // the time limit when the test host is busy.
  const user = userEvent.setup({ delay: null });
  const { queryClient } = renderApp(mode === 'create' ? '/data' : `/data/${source.id}`);
  if (mode === 'create') {
    await user.click(await screen.findByRole('button', { name: '新建数据源' }));
  } else {
    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '编辑' }));
  }
  const dialog = await screen.findByRole('dialog', { name: mode === 'create' ? '新建数据源' : '编辑数据源' });
  return { api, user, source, queryClient, dialog, form: within(dialog) };
}

describe('data source dialog', () => {
  it('creates a source with explicit sample consent and tests only its connection parameters', async () => {
    const saved = makeSource({ name: '质检库' });
    let created = false;
    let finishRefresh: (() => void) | undefined;
    const { form, user, api, dialog } = await openForm('create', {
      [`POST ${collection}`]: () => { created = true; return saved; },
      [`GET ${collection}`]: () => created
        ? new Promise((resolve) => { finishRefresh = () => resolve([saved]); })
        : [makeSource()],
      [`GET ${collection}/:id`]: () => saved,
      [`POST ${testPath}`]: () => ({ ...success, warnings: ['account_can_write'] }),
    });
    expect(dialog).toHaveAccessibleDescription('平台对数据源只读；绑定并发布后，绑定列的数据对平台的所有登录用户可见');
    const kind = form.getByRole('combobox', { name: '类型' });
    expect(within(kind).getAllByRole('option')).toHaveLength(1);
    expect(kind).toHaveDisplayValue('PostgreSQL');
    expect(form.getByRole('spinbutton', { name: '端口' })).toHaveValue(5432);
    const ssl = form.getByRole('combobox', { name: 'SSL 模式' });
    expect(ssl).toHaveValue('prefer');
    expect(within(ssl).getAllByRole('option').map((option) => option.getAttribute('value')))
      .toEqual(['disable', 'prefer', 'require', 'verify-full']);
    const samples = form.getByRole('switch', { name: '允许把样本值发给模型' });
    expect(samples).not.toBeChecked();
    expect(form.queryByText(sampleWarning)).not.toBeInTheDocument();
    await user.click(samples);
    expect(form.getByRole('status')).toHaveTextContent(sampleWarning);
    expect(form.getByRole('status')).toHaveClass('bg-warning-soft');
    await user.type(form.getByRole('textbox', { name: '主机' }), ' reports.example.test ');
    await user.type(form.getByRole('textbox', { name: '数据库' }), ' quality ');
    await user.type(form.getByRole('textbox', { name: '用户名' }), ' reports_reader ');
    const password = form.getByLabelText(/^口令/);
    expect(password).toHaveAttribute('type', 'password');
    await user.type(password, newPassword);
    await user.selectOptions(ssl, 'verify-full');
    await user.type(form.getByRole('textbox', { name: '模式名 1' }), ' mes ');
    await user.click(form.getByRole('button', { name: '添加模式' }));
    await user.type(form.getByRole('textbox', { name: '模式名 2' }), ' archive,2025 ');
    await user.click(form.getByRole('button', { name: '添加模式' }));
    await user.type(form.getByRole('textbox', { name: '模式名 3' }), '   ');
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(await form.findByText(/连接成功/)).toBeInTheDocument();
    const warning = form.getByRole('button', { name: '注意' });
    expect(warning).toHaveAccessibleDescription('该账号有写权限，建议换用只读账号');
    await user.click(warning);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('该账号有写权限，建议换用只读账号');
    expect(form.getByText(/16\.4/)).toBeInTheDocument();
    expect(screen.queryAllByDisplayValue(newPassword.trim())).toEqual([password]);
    expect(document.body).not.toHaveTextContent(newPassword.trim());
    const connection = {
      kind: 'postgresql', host: 'reports.example.test', port: 5432, database: 'quality',
      username: 'reports_reader', password: newPassword, sslMode: 'verify-full', schemas: ['mes', 'archive,2025'],
    };
    expect(api.calls('POST', testPath).map((r) => r.body)).toEqual([connection]);
    await user.type(form.getByRole('textbox', { name: '名称' }), saved.name);
    const save = form.getByRole('button', { name: '保存数据源' });
    await user.click(save);
    await waitFor(() => expect(finishRefresh).toBeTypeOf('function'));
    expect(save).toBeDisabled();
    await user.click(save);
    finishRefresh?.();
    expect(await screen.findByRole('heading', { name: saved.name })).toBeInTheDocument();
    expect(screen.queryAllByDisplayValue(newPassword.trim())).toHaveLength(0);
    expect(document.body).not.toHaveTextContent(newPassword.trim());
    expect(api.calls('POST', collection).map((r) => r.body)).toEqual([{ ...connection, name: saved.name, allowSamples: true }]);
    expect(api.calls('POST', `${collection}/${saved.id}/test`)).toHaveLength(0);
    // A long walk through the whole form; slow when the gate runs everything at once.
  }, 15_000);

  it.each(['unchanged', 'untested', 'consent changed', 'test failed'] as const)(
    'records a saved test only for a successful, unchanged draft (%s)', async (scenario) => {
      const saved = makeSource({ id: 'new-source', name: '新库' });
      const savedTestPath = `${collection}/${saved.id}/test`;
      let current = saved;
      const { form, user, api } = await openForm('create', {
        [`POST ${collection}`]: () => saved,
        [`POST ${testPath}`]: () => scenario === 'test failed'
          ? { ...success, ok: false, code: 'datasource.connect_failed', reason: 'timeout' }
          : success,
        [`POST ${savedTestPath}`]: () => {
          current = { ...saved, lastTest: { at: saved.createdAt, ok: true, code: null, warnings: [] } };
          return success;
        },
        [`GET ${collection}/:id`]: () => current,
      });
      await user.type(form.getByRole('textbox', { name: '名称' }), saved.name);
      await user.type(form.getByRole('textbox', { name: '主机' }), 'db.test');
      await user.type(form.getByRole('textbox', { name: '数据库' }), 'db');
      await user.type(form.getByRole('textbox', { name: '用户名' }), 'reader');
      await user.type(form.getByLabelText(/^口令/), newPassword);
      if (scenario !== 'untested') {
        await user.click(form.getByRole('button', { name: '测试连接' }));
        if (scenario === 'test failed') expect(await form.findByRole('alert')).toHaveTextContent('连接超时');
        else expect(await form.findByText(/连接成功/)).toBeVisible();
      }
      if (scenario === 'consent changed') await user.click(form.getByRole('switch', { name: '允许把样本值发给模型' }));
      await user.click(form.getByRole('button', { name: '保存数据源' }));
      await screen.findByRole('heading', { name: saved.name });
      expect(api.calls('POST', savedTestPath)).toHaveLength(scenario === 'unchanged' ? 1 : 0);
      const history = within(await screen.findByRole('region', { name: '最近一次测试' }));
      expect(await history.findByText(scenario === 'unchanged' ? '正常' : '未测试')).toBeVisible();
    },
  );

  it('saves the selected and manually entered schemas and tests the new source once', async () => {
    const saved = makeSource({ id: 'new-schema-source', name: '质检库' });
    const savedTestPath = `${collection}/${saved.id}/test`;
    const { form, user, api } = await openForm('create', {
      [`POST ${testPath}`]: () => ({ ...success, schemas: [' quality ', 'archive', 'mes'] }),
      [`POST ${collection}`]: () => saved,
      [`POST ${savedTestPath}`]: () => success,
      [`GET ${collection}/:id`]: () => saved,
    });
    await user.type(form.getByRole('textbox', { name: '名称' }), saved.name);
    await user.type(form.getByRole('textbox', { name: '主机' }), 'db.test');
    await user.type(form.getByRole('textbox', { name: '数据库' }), 'db');
    await user.type(form.getByRole('textbox', { name: '用户名' }), 'reader');
    await user.type(form.getByLabelText(/^口令/), newPassword);
    await user.type(form.getByRole('textbox', { name: '模式名 1' }), ' mes ');
    await user.click(form.getByRole('button', { name: '测试连接' }));

    const mes = await form.findByRole('checkbox', { name: 'mes' });
    expect(mes).toBeChecked();
    await user.click(mes);
    expect(form.queryByDisplayValue(' mes ')).not.toBeInTheDocument();
    await user.click(form.getByRole('button', { name: '添加模式' }));
    await user.type(form.getByRole('textbox', { name: '模式名 1' }), 'legacy');
    await user.click(form.getByRole('checkbox', { name: 'archive' }));
    await user.click(form.getByRole('checkbox', { name: 'quality' }));
    expect(form.getByRole('textbox', { name: '模式名 2' })).toHaveValue('archive');
    expect(form.getByRole('textbox', { name: '模式名 3' })).toHaveValue(' quality ');
    await user.click(form.getByRole('checkbox', { name: 'archive' }));
    expect(form.queryByDisplayValue('archive')).not.toBeInTheDocument();
    expect(form.getByRole('checkbox', { name: 'archive' })).not.toBeChecked();
    expect(form.getByText(/连接成功/)).toBeVisible();
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    await screen.findByRole('heading', { name: saved.name });
    expect(api.calls('POST', collection).map((call) => call.body))
      .toEqual([expect.objectContaining({ schemas: ['legacy', ' quality '] })]);
    expect(api.calls('POST', savedTestPath)).toHaveLength(1);
  });

  it('keeps the picker and enforces the 50-row scope when editing', async () => {
    const source = makeSource();
    const names = Array.from({ length: 50 }, (_, index) => `schema_${index}`);
    const full = { ...source, connection: { ...source.connection, schemas: names } };
    const { form, user } = await openForm('edit', {
      [`GET ${collection}/:id`]: () => full,
      [`POST ${testPath}`]: () => ({ ...success, schemas: [...names, 'extra'] }),
    });
    await user.click(form.getByRole('button', { name: '测试连接' }));
    await user.click(await form.findByRole('button', { name: '下一页' }));
    expect(form.getByRole('checkbox', { name: 'extra' })).toBeDisabled();
    await user.click(form.getByRole('button', { name: '上一页' }));
    const first = form.getByRole('checkbox', { name: 'schema_0' });
    expect(first).toBeChecked();
    await user.click(first);
    await user.click(form.getByRole('button', { name: '下一页' }));
    const extra = form.getByRole('checkbox', { name: 'extra' });
    expect(extra).toBeEnabled();
    await user.click(extra);
    expect(form.getByRole('textbox', { name: '模式名 50' })).toHaveValue('extra');
    expect(form.getByRole('button', { name: '添加模式' })).toBeDisabled();
    expect(form.getByText(/连接成功/)).toBeVisible();
  });

  it.each([{ schemas: null }, { schemas: [] }])('keeps manual scope entry with $schemas', async ({ schemas }) => {
    const { form, user } = await openForm('edit', {
      [`POST ${testPath}`]: () => ({ ...success, schemas }),
    });
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(await form.findByText(/连接成功/)).toBeVisible();
    expect(form.queryByRole('checkbox')).not.toBeInTheDocument();
    await user.click(form.getByRole('button', { name: '添加模式' }));
    await user.type(form.getByRole('textbox', { name: '模式名 2' }), 'manual');
    expect(form.getByText(/连接成功/)).toBeVisible();
  });

  it('validates on blur and blocks invalid requests with a summary', async () => {
    const { form, user, api } = await openForm('create');
    const port = form.getByRole('spinbutton', { name: '端口' });
    await user.clear(port);
    await user.type(port, '65536');
    await user.tab();
    expect(port).toHaveAccessibleDescription('请输入 1 到 65535 之间的整数。');
    await user.type(form.getByRole('textbox', { name: '数据库' }), '   ');
    await user.type(form.getByRole('textbox', { name: '用户名' }), '   ');
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(form.getByRole('alert')).toHaveTextContent('请检查标出的字段后重试。');
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    expect(form.getByRole('textbox', { name: '名称' })).toHaveAccessibleDescription('请填写名称。');
    expect(form.getByRole('textbox', { name: '数据库' })).toHaveAccessibleDescription('请填写数据库。');
    expect(form.getByRole('textbox', { name: '用户名' })).toHaveAccessibleDescription('请填写用户名。');
    expect(form.getByLabelText(/^口令/)).toHaveAccessibleDescription('请填写口令。');
    expect(api.calls('POST', testPath)).toHaveLength(0);
    expect(api.calls('POST', collection)).toHaveLength(0);
  });

  it('uses the stored credential and diffs edits against the revision opened by the user', async () => {
    let current = makeSource();
    const { form, user, api, source, queryClient } = await openForm('edit', {
      [`GET ${collection}/:id`]: () => current,
      [`POST ${testPath}`]: () => success,
      [`PATCH ${collection}/:id`]: () => problemResponse(409, 'datasource.stale'),
    });
    const password = form.getByLabelText(/^口令/);
    expect(password).toHaveValue('');
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('placeholder', '已保存，留空表示不修改');
    expect(password).not.toBeRequired();
    const name = form.getByRole('textbox', { name: '名称' });
    await user.clear(name);
    await user.type(name, '用户修改');
    for (const label of ['数据库', '用户名', '模式名 1']) {
      await user.type(form.getByRole('textbox', { name: label }), ' ');
    }
    current = makeSource({
      name: '后台修改', revision: 9,
      connection: { host: 'elsewhere.example.test', port: 1234, database: 'new', username: 'new', sslMode: 'require', schemas: [] },
    });
    await act(() => queryClient.refetchQueries({ queryKey: sourceKey(source.id), exact: true }));
    await screen.findByText('后台修改', { selector: 'h1' });
    expect(name).toHaveValue('用户修改');
    expect(form.getByRole('textbox', { name: '主机' })).toHaveValue('db.example.test');
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(await form.findByText(/连接成功/)).toBeInTheDocument();
    expect(api.calls('POST', testPath).map((r) => r.body)).toEqual([{
      kind: 'postgresql', dataSourceId: source.id, host: 'db.example.test', port: 5432,
      database: 'steel', username: 'reader', sslMode: 'prefer', schemas: ['steel'],
    }]);
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    expect(await form.findByRole('alert')).toHaveTextContent('数据源已被其他人修改，请刷新后再改。');
    expect(name).toHaveValue('用户修改');
    expect(api.calls('PATCH', `${collection}/${source.id}`).map((r) => r.body)).toEqual([{ name: '用户修改', revision: 3 }]);
  });

  it('preserves untouched legacy connection fields and sends an explicit whitespace correction', () => {
    const source = makeSource({
      connection: { host: ' db ', port: 5432, database: ' steel ', username: ' reader ', sslMode: 'prefer', schemas: [' mes '] },
    });
    const form = { ...initialForm(source), name: '新名称' };
    expect(patchRequest(form, source)).toEqual({ revision: 3, name: '新名称' });
    expect(patchRequest({ ...form, database: 'steel', schemas: [{ id: 0, name: 'mes' }] }, source)).toEqual({
      revision: 3, name: '新名称', database: 'steel', schemas: ['mes'],
    });
  });

  it('requires a password for a changed host before testing or saving', async () => {
    const { form, user, api, source } = await openForm('edit', {
      [`POST ${testPath}`]: () => success,
      [`PATCH ${collection}/:id`]: () => makeSource({ revision: 4 }),
    });
    const host = form.getByRole('textbox', { name: '主机' });
    const password = form.getByLabelText(/^口令/);
    await user.clear(host);
    await user.type(host, ' DB.EXAMPLE.TEST ');
    expect(password).not.toBeRequired();
    await user.clear(host);
    await user.type(host, 'other.example.test');
    expect(password).toBeRequired();
    expect(password).not.toHaveAttribute('placeholder');
    expect(password).toHaveAccessibleDescription(/请重新填写口令/);
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(password).toHaveAttribute('aria-invalid', 'true');
    expect(password).toHaveFocus();
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    expect(api.calls('POST', testPath)).toHaveLength(0);
    expect(api.calls('PATCH', `${collection}/${source.id}`)).toHaveLength(0);
    await user.type(password, newPassword);
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls('PATCH', `${collection}/${source.id}`).map((r) => r.body))
      .toEqual([{ host: 'other.example.test', password: newPassword, revision: source.revision }]);
  });

  it('restores the optional password when port, username or SSL mode is restored', async () => {
    const { form, user } = await openForm('edit');
    const password = form.getByLabelText(/^口令/);
    const port = form.getByRole('spinbutton', { name: '端口' });
    const username = form.getByRole('textbox', { name: '用户名' });
    const sslMode = form.getByRole('combobox', { name: 'SSL 模式' });
    await user.clear(port);
    await user.type(port, '5433');
    expect(password).toBeRequired();
    await user.clear(port);
    await user.type(port, '5432');
    expect(password).not.toBeRequired();
    await user.clear(username);
    await user.type(username, 'Reader');
    expect(password).toBeRequired();
    await user.clear(username);
    await user.type(username, 'reader');
    expect(password).not.toBeRequired();
    await user.selectOptions(sslMode, 'require');
    expect(password).toBeRequired();
    await user.selectOptions(sslMode, 'prefer');
    expect(password).not.toBeRequired();
  });

  it.each(['测试连接', '保存数据源'])('shows a server password requirement on the field after %s', async (action) => {
    const rejected = () => problemResponse(422, 'datasource.password_required');
    const { form, user } = await openForm('edit', {
      [`POST ${testPath}`]: rejected,
      [`PATCH ${collection}/:id`]: rejected,
    });
    const password = form.getByLabelText(/^口令/);
    await user.click(form.getByRole('button', { name: action }));
    await waitFor(() => expect(password).toHaveAttribute('aria-invalid', 'true'));
    expect(password).toHaveAccessibleDescription(/请重新填写口令/);
  });

  it.each(['lastTest', 'catalog'] as const)('requires a replacement password when %s records an unreadable credential', async (origin) => {
    const code = 'datasource.credential_unreadable';
    const source = makeSource(origin === 'lastTest'
      ? { lastTest: { at: '2026-11-23T09:00:00Z', ok: false, code, warnings: [] } }
      : { catalog: { status: 'failed', errorCode: code, refreshedAt: null, tableCount: 0 } });
    const { form, user, api } = await openForm('edit', {
      [`GET ${collection}/:id`]: () => source,
      [`PATCH ${collection}/:id`]: () => makeSource({ revision: source.revision + 1 }),
    });
    const password = form.getByLabelText(/^口令/);
    expect(password).toBeRequired();
    expect(password).toHaveValue('');
    expect(password).not.toHaveAttribute('placeholder');
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(password).toHaveAccessibleDescription('请填写口令。');
    expect(api.calls('POST', testPath)).toHaveLength(0);
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    expect(password).toHaveFocus();
    expect(api.calls('PATCH', `${collection}/${source.id}`)).toHaveLength(0);
    await user.type(password, newPassword);
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls('PATCH', `${collection}/${source.id}`).map((r) => r.body))
      .toEqual([{ password: newPassword, revision: source.revision }]);
  });

  it('reopens a successfully saved edit with the new name and fresh connection feedback', async () => {
    let current = makeSource();
    const { form, user, api, source } = await openForm('edit', {
      [`GET ${collection}/:id`]: () => current,
      [`POST ${testPath}`]: () => success,
      [`PATCH ${collection}/:id`]: () => {
        current = { ...current, name: '用户修改', revision: current.revision + 1 };
        return current;
      },
    });
    const name = form.getByRole('textbox', { name: '名称' });
    await user.clear(name);
    await user.type(name, '用户修改');
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(await form.findByText(/连接成功/)).toBeVisible();
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls('PATCH', `${collection}/${source.id}`).map((r) => r.body)).toEqual([{ name: '用户修改', revision: 3 }]);
    await user.click(screen.getByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '编辑' }));
    const reopened = within(await screen.findByRole('dialog', { name: '编辑数据源' }));
    expect(reopened.getByRole('textbox', { name: '名称' })).toHaveValue('用户修改');
    expect(reopened.queryByText(/连接成功/)).not.toBeInTheDocument();
    expect(reopened.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('uses a replacement credential, clears the schema scope, and keeps the draft on a stale save', async () => {
    const { form, user, api, source } = await openForm('edit', {
      [`POST ${testPath}`]: () => problemResponse(422, 'datasource.platform_database', { detail: newPassword }),
      [`PATCH ${collection}/:id`]: () => problemResponse(409, 'datasource.stale', { detail: newPassword }),
    });
    await user.type(form.getByLabelText(/^口令/), newPassword);
    const host = form.getByRole('textbox', { name: '主机' });
    await user.clear(host);
    await user.type(host, 'staging.example.test');
    await user.click(form.getByRole('button', { name: '移除模式 1' }));
    await user.click(form.getByRole('button', { name: '测试连接' }));
    expect(await form.findByRole('alert')).toHaveTextContent('不能把平台自己的数据库作为数据源。');
    expect(api.calls('POST', testPath).map((r) => r.body)).toEqual([{
      kind: 'postgresql', host: 'staging.example.test', port: 5432, database: 'steel', username: 'reader',
      sslMode: 'prefer', schemas: [], password: newPassword,
    }]);
    await user.click(form.getByRole('button', { name: '保存数据源' }));
    expect(await form.findByText('数据源已被其他人修改，请刷新后再改。')).toBeInTheDocument();
    expect(api.calls('PATCH', `${collection}/${source.id}`).map((r) => r.body))
      .toEqual([{ revision: 3, host: 'staging.example.test', schemas: [], password: newPassword }]);
    expect(document.body).not.toHaveTextContent(newPassword.trim());
    expect(form.getByLabelText(/^口令/)).toHaveAttribute('type', 'password');
  });

  it.each([
    ['unreachable', /无法连接到主机/],
    ['auth_failed', /认证失败/],
    ['database_missing', /数据库不存在/],
    ['ssl', /SSL 连接失败/],
    ['timeout', /连接超时/],
  ] as const)(
    'shows the reason for a %s test failure inside the dialog',
    async (reason, expected) => {
      const { form, user } = await openForm('edit', {
        [`POST ${testPath}`]: () => ({ ok: false, code: 'datasource.connect_failed', reason, warnings: [], serverVersion: null }),
      });
      await user.click(form.getByRole('button', { name: '测试连接' }));
      expect(await form.findByRole('alert')).toHaveTextContent(expected);
      expect(form.getByRole('alert')).toHaveClass('bg-error-soft');
    },
  );
});
