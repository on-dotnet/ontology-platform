import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, renderWithProviders } from '@/test/utils';

import { McpAccessCard } from './mcp-access-card';

const endpoint = `${window.location.origin}/mcp`;

describe('MCP access card', () => {
  it('shows the endpoint and a client configuration instead of a placeholder', () => {
    mockApi({});
    renderWithProviders(<McpAccessCard />);

    expect(screen.getByRole('heading', { name: 'MCP 接入' })).toBeInTheDocument();
    expect(screen.queryByText('即将推出')).not.toBeInTheDocument();
    expect(screen.getByText(endpoint)).toBeVisible();

    const config = JSON.parse(screen.getByTestId('mcp-client-config').textContent ?? '') as unknown;
    expect(config).toEqual({
      mcpServers: {
        'ontology-platform': {
          type: 'http',
          url: endpoint,
          headers: { Authorization: 'Bearer <访问令牌>' },
        },
      },
    });
    expect(screen.getByText(/2026-07-28/)).toBeVisible();
    expect(screen.getByText('ontology:read')).toBeVisible();
    expect(screen.getByText('objects:read')).toBeVisible();
  });

  it('copies the endpoint and the configuration', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderWithProviders(<McpAccessCard />);

    await user.click(screen.getByRole('button', { name: '复制地址' }));
    expect(await navigator.clipboard.readText()).toBe(endpoint);

    await user.click(screen.getByRole('button', { name: '复制配置' }));
    expect(await navigator.clipboard.readText()).toBe(screen.getByTestId('mcp-client-config').textContent);
  });
});
