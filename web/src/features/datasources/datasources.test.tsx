import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { permissionsFor } from '@/features/auth/permissions';
import { mockApi, renderApp } from '@/test/utils';

import { makeSource } from './test-fixtures';

// The M3 skeleton (spec 003, section 16): the pages exist and say they are coming; batches 2, 3,
// 5 and 6a replace these placeholders and their tests.
describe('M3 skeleton pages', () => {
  it('opens the data source list and one data source', async () => {
    const user = userEvent.setup();
    const source = makeSource();
    mockApi({ 'GET /api/data-sources': () => [source], 'GET /api/data-sources/:id': () => source });
    renderApp('/data');
    const link = await screen.findByRole('link', { name: source.name });
    expect(link).toHaveAttribute('href', `/data/${source.id}`);
    expect(screen.getByRole('button', { name: '新建数据源' })).toBeInTheDocument();
    await user.click(screen.getByRole('cell', { name: 'db.example.test' }));
    expect(await screen.findByRole('heading', { level: 1, name: source.name })).toBeInTheDocument();
    expect(screen.getByText('reader')).toBeInTheDocument();
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
