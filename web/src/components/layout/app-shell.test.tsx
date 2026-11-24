import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { setBrowserFontSize } from '@/test/media';
import { mockApi, renderApp } from '@/test/utils';

describe('app shell breakpoint', () => {
  // With a 20px default font size, Tailwind's `lg` (64rem) is 1280px while the layout query says
  // desktop from 1024px: the sidebar must not depend on the CSS breakpoint in between (#8).
  it('keeps the navigation available between 1024px and 1280px at a 20px default font size', async () => {
    // The matchMedia stub then evaluates rem and em queries with a 20px default font size, as a
    // browser does for a user who enlarged it; px queries such as DESKTOP_QUERY are unaffected.
    setBrowserFontSize(20);
    vi.stubGlobal('innerWidth', 1100);
    mockApi();
    renderApp('/');

    const nav = await screen.findByRole('navigation', { name: '主导航' });
    const sidebar = nav.closest('aside');
    expect(sidebar).not.toBeNull();
    expect(sidebar?.className ?? '').not.toMatch(/(^|\s)hidden(\s|$)/);
    // Nor may a responsive Tailwind variant show or hide it: those breakpoints are in rem.
    expect(sidebar?.className ?? '').not.toMatch(/(^|\s)(sm|md|lg|xl|2xl):/);
    expect(within(nav).getAllByRole('link')).toHaveLength(8);
    expect(screen.getByRole('button', { name: '收起侧栏' })).toBeInTheDocument();
  });

  it('opens the navigation as a drawer below 1024px', async () => {
    const user = userEvent.setup();
    // As above: rem queries in the stub use a 20px default font size.
    setBrowserFontSize(20);
    vi.stubGlobal('innerWidth', 1000);
    mockApi();
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: '打开导航' }));
    const drawer = await screen.findByRole('dialog', { name: '主导航' });
    expect(within(within(drawer).getByRole('navigation', { name: '主导航' })).getAllByRole('link')).toHaveLength(8);
    cleanup();

    // Wide screens show the sidebar itself, with nothing hidden behind a drawer.
    vi.stubGlobal('innerWidth', 1440);
    renderApp('/');
    expect(await screen.findByRole('navigation', { name: '主导航' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开导航' })).not.toBeInTheDocument();
  });
});
