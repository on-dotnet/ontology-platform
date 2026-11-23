import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, renderApp } from '@/test/utils';

import { aiHealth } from './api';

describe('AI status', () => {
  it('derives the health from configuration and reachability', () => {
    expect(aiHealth({ configured: false, reachable: null, model: null })).toBe('not_configured');
    expect(aiHealth({ configured: true, reachable: false, model: 'm' })).toBe('unreachable');
    expect(aiHealth({ configured: true, reachable: true, model: 'm' })).toBe('available');
    expect(aiHealth({ configured: true, reachable: null, model: 'm' })).toBe('unknown');
  });

  it('shows availability and the model name on the settings page', async () => {
    mockApi({ 'GET /api/ai/status': () => ({ configured: true, reachable: true, model: 'gpt-test-mini' }) });
    renderApp('/settings');

    const card = (await screen.findByRole('heading', { name: 'AI 服务' })).closest('.rounded-xl');
    expect(card).not.toBeNull();
    expect(await within(card as HTMLElement).findByText('可用')).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText('gpt-test-mini')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'AI 识别暂不可用' })).not.toBeInTheDocument();
  });

  it('explains the impact when the service is not configured', async () => {
    mockApi({ 'GET /api/ai/status': () => ({ configured: false, reachable: null, model: null }) });
    renderApp('/settings');

    const card = (await screen.findByRole('heading', { name: 'AI 服务' })).closest('.rounded-xl');
    expect(await within(card as HTMLElement).findByText('未配置')).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText('未设置')).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText('AI 服务尚未配置')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'AI 服务尚未配置' })).toBeInTheDocument();
  });
});
