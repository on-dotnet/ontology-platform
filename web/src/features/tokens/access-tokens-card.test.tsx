import { onlineManager } from '@tanstack/react-query';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { components } from '@/api/schema';
import { jsonResponse, mockApi, problemResponse, renderWithProviders, testUser, userWithRole } from '@/test/utils';

import { AccessTokensCard } from './access-tokens-card';

const path = '/api/auth/tokens';
const active: components['schemas']['AccessToken'] = {
  id: '00000000-0000-4000-8000-000000000002',
  name: '排产助手',
  prefix: 'op_pat_abcdefgh',
  scopes: ['objects:read'],
  owner: { id: testUser.id, displayName: testUser.displayName },
  createdAt: '2025-01-02T08:00:00Z',
  expiresAt: '2099-04-02T08:00:00Z',
  lastUsedAt: null,
  revokedAt: null,
};

function openCreate(user: ReturnType<typeof userEvent.setup>) {
  return user.click(screen.getByRole('button', { name: '新建令牌' }));
}

describe('access tokens', () => {
  it('shows metadata and disables revocation for revoked and expired tokens', async () => {
    const revoked = { ...active, id: 'revoked', name: '已停用的助手', revokedAt: active.createdAt };
    const expired = { ...active, id: 'expired', name: '旧客户端', expiresAt: '2025-02-01T08:00:00Z', lastUsedAt: '2025-01-31T08:00:00Z' };
    const api = mockApi({ 'GET /api/auth/tokens': () => [active, revoked, expired] }, { user: userWithRole('viewer') });
    renderWithProviders(<AccessTokensCard />);

    const table = within(await screen.findByRole('table', { name: '访问令牌' }));
    expect(table.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      '名称', '前缀', '作用域', '创建时间', '过期时间', '最近使用', '操作',
    ]);
    const activeRow = within(table.getByRole('row', { name: /排产助手/ }));
    expect(activeRow.getByText('op_pat_abcdefgh')).toBeVisible();
    expect(activeRow.getByText('objects:read')).toBeVisible();
    expect(activeRow.getByText('从未使用')).toBeVisible();
    expect(activeRow.getAllByRole('time').map((time) => time.getAttribute('datetime'))).toEqual([active.createdAt, active.expiresAt]);
    expect(activeRow.getByRole('button', { name: '撤销' })).toBeEnabled();
    for (const [name, status] of [[/已停用的助手/, '已撤销'], [/旧客户端/, '已过期']] as const) {
      const row = table.getByRole('row', { name });
      expect(row).toHaveClass('text-muted-foreground');
      expect(within(row).getByText(status)).toBeVisible();
      expect(within(row).queryByRole('button', { name: '撤销' })).not.toBeInTheDocument();
    }
    expect(table.getByRole('row', { name: /旧客户端/ })).not.toHaveTextContent('从未使用');
    expect(within(table.getByRole('row', { name: /旧客户端/ })).getAllByRole('time').at(-1)).toHaveAttribute('datetime', expired.lastUsedAt);
    expect(screen.queryByRole('radio', { name: '全部令牌' })).not.toBeInTheDocument();
    expect(api.calls('GET', path).map(({ query }) => query.toString())).toEqual(['owner=me']);
  });

  it('requests all owners only in the admin all-tokens view', async () => {
    const user = userEvent.setup();
    const other = { ...active, id: 'other', name: '巡检助手', owner: { id: 'other-owner', displayName: '李工' } };
    const api = mockApi({ 'GET /api/auth/tokens': ({ query }) => query.get('owner') === 'all' ? [active, other] : [active] });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText(active.name);
    expect(screen.queryByRole('columnheader', { name: '主人' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: '全部令牌' }));
    expect(await screen.findByRole('columnheader', { name: '主人' })).toBeVisible();
    expect(within(screen.getByRole('row', { name: /巡检助手/ })).getByText('李工')).toBeVisible();
    await user.click(screen.getByRole('radio', { name: '我的令牌' }));
    expect(await screen.findByText(active.name)).toBeVisible();
    expect(screen.queryByText('李工')).not.toBeInTheDocument();
    expect(api.calls('GET', path).map(({ query }) => query.toString())).toEqual(['owner=me', 'owner=all']);
  });

  it('validates the viewer form, sends the selected scopes, and displays the secret only once', async () => {
    const user = userEvent.setup();
    const secret = 'example-only-once-secret';
    let created = false;
    const api = mockApi({
      'GET /api/auth/tokens': () => created ? [active] : [],
      'POST /api/auth/tokens': () => {
        created = true;
        return jsonResponse({ info: active, token: secret }, 201);
      },
    }, { user: userWithRole('viewer') });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText('暂无访问令牌');
    await openCreate(user);
    const form = within(screen.getByRole('dialog', { name: '新建令牌' }));
    expect(form.queryByText('changes:propose')).not.toBeInTheDocument();
    expect(form.getByRole('checkbox', { name: 'objects:read' })).toHaveAccessibleDescription('按本体查询业务对象。');
    expect(form.getByRole('combobox', { name: '有效期' })).toHaveValue('90');
    expect(form.getAllByRole('option').map((option) => option.textContent)).toEqual(['30 天', '90 天', '365 天']);
    const name = form.getByRole('textbox', { name: '名称' });
    expect(name).toHaveAttribute('maxlength', '100');
    await user.click(form.getByRole('button', { name: '创建令牌' }));
    expect(form.getByText('请输入令牌名称。')).toBeVisible();
    expect(form.getByText('请至少选择一个作用域。')).toBeVisible();
    expect(api.calls('POST', path)).toHaveLength(0);
    await user.type(name, '  排产助手  ');
    await user.click(form.getByRole('checkbox', { name: 'ontology:read' }));
    await user.click(form.getByRole('checkbox', { name: 'objects:read' }));
    await user.click(form.getByRole('button', { name: '创建令牌' }));

    const result = within(await screen.findByRole('dialog', { name: '保存访问令牌' }));
    expect(api.calls('POST', path).map(({ body }) => body)).toEqual([
      { name: '排产助手', scopes: ['ontology:read', 'objects:read'], expiresInDays: 90 },
    ]);
    expect(result.getByRole('status')).toHaveTextContent('令牌只显示这一次，请现在保存');
    expect(result.getByRole('status')).toHaveClass('bg-warning-soft');
    expect(result.getByText(secret)).toBeVisible();
    await user.click(result.getByRole('button', { name: '复制令牌' }));
    expect(await navigator.clipboard.readText()).toBe(secret);
    await user.click(result.getByRole('button', { name: '完成' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByRole('row', { name: /排产助手/ })).toBeVisible();
    expect(screen.queryByText(secret)).not.toBeInTheDocument();
    await openCreate(user);
    expect(screen.queryByText(secret)).not.toBeInTheDocument();
    expect(within(screen.getByRole('dialog')).getByRole('textbox', { name: '名称' })).toHaveValue('');
    expect(api.calls('GET', path).map(({ query }) => query.toString())).toEqual(['owner=me', 'owner=me']);
  });

  it.each([
    [409, 'token.limit_reached', '有效的访问令牌已达 10 个，请先撤销不用的令牌。'],
    [403, 'token.scope_not_allowed', '你的角色不能申请这个作用域。'],
  ] as const)('shows a localized creation error for %s', async (status, code, message) => {
    const user = userEvent.setup();
    const api = mockApi({
      'GET /api/auth/tokens': () => [],
      'POST /api/auth/tokens': () => problemResponse(status, code),
    }, { user: userWithRole('editor') });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText('暂无访问令牌');
    await openCreate(user);
    const form = within(screen.getByRole('dialog'));
    await user.type(form.getByRole('textbox', { name: '名称' }), '变更助手');
    await user.click(form.getByRole('checkbox', { name: 'changes:propose' }));
    await user.selectOptions(form.getByRole('combobox', { name: '有效期' }), '365');
    await user.click(form.getByRole('button', { name: '创建令牌' }));
    expect(await form.findByRole('alert')).toHaveTextContent(message);
    expect(api.calls('POST', path).map(({ body }) => body)).toEqual([
      { name: '变更助手', scopes: ['changes:propose'], expiresInDays: 365 },
    ]);
  });

  it('cancels without a request, then revokes the confirmed token and refreshes its row', async () => {
    const user = userEvent.setup();
    let revokedAt: string | null = null;
    const api = mockApi({
      'GET /api/auth/tokens': () => [{ ...active, revokedAt }],
      'DELETE /api/auth/tokens/:id': () => { revokedAt = active.createdAt; },
    });
    renderWithProviders(<AccessTokensCard />);
    await user.click(await screen.findByRole('button', { name: '撤销' }));
    const dialog = within(screen.getByRole('dialog', { name: '撤销令牌' }));
    expect(dialog.getByText('撤销后，使用“排产助手”的客户端将失去访问权限。此操作不可恢复。')).toBeVisible();
    await user.click(dialog.getByRole('button', { name: '取消' }));
    expect(api.requests.filter(({ method }) => method === 'DELETE')).toHaveLength(0);
    await user.click(await screen.findByRole('button', { name: '撤销' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '撤销令牌' }));
    const row = within(await screen.findByRole('row', { name: /排产助手.*已撤销/ }));
    expect(await screen.findByText('令牌已撤销')).toBeVisible();
    expect(row.queryByRole('button', { name: '撤销' })).not.toBeInTheDocument();
    expect(api.requests.filter(({ method }) => method === 'DELETE').map(({ path }) => path)).toEqual([
      '/api/auth/tokens/00000000-0000-4000-8000-000000000002',
    ]);
    expect(api.calls('GET', path)).toHaveLength(2);
  });

  it('explains a failed revocation in the confirmation dialog', async () => {
    const user = userEvent.setup();
    const api = mockApi({
      'GET /api/auth/tokens': () => [active],
      'DELETE /api/auth/tokens/:id': () => problemResponse(404, 'token.not_found'),
    });
    renderWithProviders(<AccessTokensCard />);
    await user.click(await screen.findByRole('button', { name: '撤销' }));
    const dialog = within(screen.getByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: '撤销令牌' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('访问令牌不存在，或不属于你。');
    // The token is gone already, so the list is fetched again.
    await waitFor(() => expect(api.calls('GET', path)).toHaveLength(2));
  });

  it('offers retry after a list error and shows the empty result', async () => {
    const user = userEvent.setup();
    let unavailable = true;
    mockApi({ 'GET /api/auth/tokens': () => unavailable ? problemResponse(400, 'http.400') : [] });
    renderWithProviders(<AccessTokensCard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('请求的内容不正确，请检查后重试。');
    unavailable = false;
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('暂无访问令牌')).toBeVisible();
    expect(screen.getByText('创建令牌后，脚本和外部智能体就能按作用域访问平台。')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('replaces the list skeleton with a permission message when the all-tokens request is refused', async () => {
    const user = userEvent.setup();
    let refuse!: (response: Response) => void;
    const allTokens = new Promise<Response>((resolve) => { refuse = resolve; });
    mockApi({ 'GET /api/auth/tokens': ({ query }) => query.get('owner') === 'all' ? allTokens : [active] });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText(active.name);
    await user.click(screen.getByRole('radio', { name: '全部令牌' }));
    expect(screen.getByText('正在加载…').closest('[role="status"]')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText(active.name)).not.toBeInTheDocument();
    refuse(problemResponse(403, 'auth.forbidden'));
    expect(await screen.findByRole('heading', { name: '没有访问权限' })).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('returns to personal tokens when the server reports loss of admin access', async () => {
    const user = userEvent.setup();
    let account = userWithRole('admin');
    const api = mockApi({
      'GET /api/auth/tokens': ({ query }) => {
        if (query.get('owner') === 'me') return [active];
        account = userWithRole('viewer');
        return problemResponse(403, 'auth.forbidden');
      },
    }, { user: () => account });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText(active.name);
    await user.click(screen.getByRole('radio', { name: '全部令牌' }));
    await waitFor(() => expect(screen.queryByRole('radio', { name: '全部令牌' })).not.toBeInTheDocument());
    expect(screen.getByText(active.name)).toBeVisible();
    expect(api.calls('GET', '/api/auth/me')).toHaveLength(2);
  });

  it('removes a disallowed scope from the form and the next request after a role change', async () => {
    const user = userEvent.setup();
    let account = userWithRole('editor');
    const api = mockApi({
      'GET /api/auth/tokens': () => [],
      'POST /api/auth/tokens': () => {
        if (account.role === 'viewer') return jsonResponse({ token: 'example-read-only', info: active }, 201);
        account = userWithRole('viewer');
        return problemResponse(403, 'token.scope_not_allowed');
      },
    }, { user: () => account });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText('暂无访问令牌');
    await openCreate(user);
    const form = within(screen.getByRole('dialog'));
    await user.type(form.getByRole('textbox', { name: '名称' }), active.name);
    await user.click(form.getByRole('checkbox', { name: 'changes:propose' }));
    await user.click(form.getByRole('checkbox', { name: 'objects:read' }));
    await user.click(form.getByRole('button', { name: '创建令牌' }));
    expect(await form.findByRole('alert')).toHaveTextContent('你的角色不能申请这个作用域。');
    await waitFor(() => expect(form.queryByRole('checkbox', { name: 'changes:propose' })).not.toBeInTheDocument());
    await user.click(form.getByRole('button', { name: '创建令牌' }));
    expect(await screen.findByText('example-read-only')).toBeVisible();
    expect(api.calls('POST', path).map(({ body }) => body)).toEqual([
      { name: active.name, scopes: ['changes:propose', 'objects:read'], expiresInDays: 90 },
      { name: active.name, scopes: ['objects:read'], expiresInDays: 90 },
    ]);
  });

  it('reports a network failure immediately when creating or revoking offline', async () => {
    const user = userEvent.setup();
    const offline = () => { throw new TypeError('offline'); };
    mockApi({ 'GET /api/auth/tokens': () => [active], 'POST /api/auth/tokens': offline, 'DELETE /api/auth/tokens/:id': offline });
    renderWithProviders(<AccessTokensCard />);
    await screen.findByText(active.name);
    onlineManager.setOnline(false);
    try {
      await openCreate(user);
      const form = within(screen.getByRole('dialog'));
      await user.type(form.getByRole('textbox', { name: '名称' }), '离线客户端');
      await user.click(form.getByRole('checkbox', { name: 'objects:read' }));
      await user.click(form.getByRole('button', { name: '创建令牌' }));
      expect(await form.findByRole('alert')).toHaveTextContent('无法连接到平台服务，请检查网络后重试。');
      await user.click(form.getByRole('button', { name: '取消' }));
      await user.click(await screen.findByRole('button', { name: '撤销' }));
      const confirmation = within(screen.getByRole('dialog', { name: '撤销令牌' }));
      await user.click(confirmation.getByRole('button', { name: '撤销令牌' }));
      expect(await confirmation.findByRole('alert')).toHaveTextContent('无法连接到平台服务，请检查网络后重试。');
      expect(confirmation.getByRole('button', { name: '取消' })).toBeEnabled();
    } finally {
      onlineManager.setOnline(true);
    }
  });
});
