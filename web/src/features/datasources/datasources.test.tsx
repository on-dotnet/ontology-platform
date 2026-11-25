import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { permissionsFor } from '@/features/auth/permissions';
import { mockApi, renderApp } from '@/test/utils';

// The M3 skeleton (spec 003, section 16): the pages exist and say they are coming; batches 2, 3,
// 5 and 6a replace these placeholders and their tests.
describe('M3 skeleton pages', () => {
  it('opens the data source list and one data source', async () => {
    mockApi({});
    const { router } = renderApp('/data');
    expect(await screen.findByRole('heading', { name: '数据连接即将推出' })).toBeInTheDocument();

    await router.navigate({ to: '/data/$dataSourceId', params: { dataSourceId: '00000000-0000-4000-8000-000000000009' } });
    expect(await screen.findByRole('heading', { name: '数据源详情即将推出' })).toBeInTheDocument();
  });

  it('opens the explore page', async () => {
    mockApi({});
    renderApp('/explore');
    expect(await screen.findByRole('heading', { name: '探索即将推出' })).toBeInTheDocument();
  });

  it('shows the access token and MCP cards in the settings', async () => {
    mockApi({ 'GET /api/settings/platform': () => ({ reviewMode: 'single' }) });
    renderApp('/settings');
    expect(await screen.findByRole('heading', { name: '访问令牌' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'MCP 接入' })).toBeInTheDocument();
  });
});

describe('M3 permissions', () => {
  it.each([
    ['admin', true, true],
    ['reviewer', false, true],
    ['editor', false, true],
    ['viewer', false, false],
  ] as const)('%s: manage data sources %s, browse catalogs and edit bindings %s', (role, admin, editor) => {
    const permissions = permissionsFor(role);
    expect(permissions.canManageDataSources).toBe(admin);
    expect(permissions.canBrowseCatalog).toBe(editor);
    expect(permissions.canEditBindings).toBe(editor);
    expect(permissions.canProposeViaMcp).toBe(editor);
  });

  it('grants nothing without a user', () => {
    expect(Object.values(permissionsFor(undefined)).some(Boolean)).toBe(false);
  });
});
