import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, renderApp } from '@/test/utils';

describe('settings: review mode', () => {
  it.each([
    ['single', '单人审核'],
    ['separate', '异人审核'],
  ] as const)('shows the %s review mode and explains both modes', async (reviewMode, label) => {
    mockApi({ 'GET /api/settings/platform': () => ({ reviewMode }) });
    renderApp('/settings');

    const card = (await screen.findByRole('heading', { name: '审核模式' })).closest('div.rounded-xl') as HTMLElement;
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(card).toHaveTextContent(`当前模式${label}`);
    const info = screen.getByRole('button', { name: '关于审核模式' });
    expect(info).toHaveAccessibleDescription(
      '单人审核时，审核人可以审核并合并自己提交的修改；异人审核时，提交人的变更集必须由其他审核人处理。由平台配置项 OP_REVIEW_MODE（single 或 separate）设置。',
    );
  });
});
