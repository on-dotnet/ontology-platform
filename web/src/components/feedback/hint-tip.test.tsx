import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test/utils';

import { InfoTip, WarnTip } from './hint-tip';

describe.each([
  ['InfoTip', InfoTip, '查看说明'],
  ['WarnTip', WarnTip, '注意'],
] as const)('%s', (_name, Tip, defaultLabel) => {
  it('is a labelled button that shows its bubble on hover and on keyboard focus', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Tip>变更集审核通过后才会进入本体。</Tip>);

    const trigger = screen.getByRole('button', { name: defaultLabel });
    expect(trigger).toHaveAccessibleDescription('变更集审核通过后才会进入本体。');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    await user.hover(trigger);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('变更集审核通过后才会进入本体。');

    await user.unhover(trigger);
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());

    await user.tab();
    expect(trigger).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('变更集审核通过后才会进入本体。');

    await user.tab();
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());
  });
});

it('uses a custom accessible label when given', () => {
  renderWithProviders(<InfoTip label="关于数据绑定">说明</InfoTip>);
  expect(screen.getByRole('button', { name: '关于数据绑定' })).toBeInTheDocument();
});
