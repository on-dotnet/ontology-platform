import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils';

import { useToast, type ToastAction } from './toast';

function ShowToast({ action, description }: { action?: ToastAction; description?: string }) {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.success('已删除“钢包”', description, action)}>
      show
    </button>
  );
}

async function showToast(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'show' }));
  // Base UI mirrors the text into a live region; the toast's own title is the heading.
  const title = (await screen.findAllByText('已删除“钢包”')).find((element) => element.tagName === 'H2');
  // Title → text column → toast.
  const toast = title?.parentElement?.parentElement;
  if (!toast) throw new Error('No toast shown');
  return toast;
}

describe('toast actions', () => {
  it('shows only the text and the close button without an action', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ShowToast description="可以在已删除列表里恢复。" />);

    const toast = await showToast(user);
    expect(toast).toHaveTextContent('可以在已删除列表里恢复。');
    // Base UI hides the close button from the accessibility tree until the toast is focused.
    expect(within(toast).getAllByRole('button', { hidden: true }).map((button) => button.getAttribute('aria-label') ?? button.textContent)).toEqual([
      '关闭',
    ]);
    expect(within(toast).queryByRole('link')).not.toBeInTheDocument();
  });

  it('runs a button action by click or keyboard and closes the toast', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(<ShowToast action={{ label: '撤销', onClick }} />);

    let toast = await showToast(user);
    await user.click(within(toast).getByRole('button', { name: '撤销' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('button', { name: '撤销' })).not.toBeInTheDocument());

    toast = await showToast(user);
    within(toast).getByRole('button', { name: '撤销' }).focus();
    await user.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByRole('button', { name: '撤销' })).not.toBeInTheDocument());
  });

  it('renders an action with an address as a link that runs the action on a plain click', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(<ShowToast action={{ label: '去审核', href: '/review/cs-manual', onClick }} />);

    const toast = await showToast(user);
    const link = within(toast).getByRole('link', { name: '去审核' });
    expect(link).toHaveAttribute('href', '/review/cs-manual');
    const clicked = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    link.dispatchEvent(clicked);
    // The caller navigates; the browser must not load the address itself.
    expect(clicked.defaultPrevented).toBe(true);
    expect(onClick).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('link', { name: '去审核' })).not.toBeInTheDocument());
  });

  it('leaves modified clicks to the browser, which opens the link in a new tab', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(<ShowToast action={{ label: '去审核', href: '#cs-manual', onClick }} />);

    const toast = await showToast(user);
    const clicked = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ctrlKey: true });
    within(toast).getByRole('link', { name: '去审核' }).dispatchEvent(clicked);
    expect(clicked.defaultPrevented).toBe(false);
    expect(onClick).not.toHaveBeenCalled();
  });
});
