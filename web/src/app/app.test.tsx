import { MutationObserver, type QueryClient } from '@tanstack/react-query';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import { jsonResponse, mockFetch, problemResponse, renderApp, testUser } from '@/test/utils';

function pathOf(request: Request): string {
  return new URL(request.url).pathname;
}

describe('app routing and session', () => {
  it('redirects to /login with the original path when /api/auth/me returns 401', async () => {
    mockFetch(() => problemResponse(401, 'auth.not_authenticated'));
    const { router } = renderApp('/documents');

    expect(await screen.findByRole('heading', { name: '登录', level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toEqual({ redirect: '/documents' });
  });

  it('renders the shell with the eight navigation items for a signed-in user', async () => {
    mockFetch(() => jsonResponse(testUser));
    renderApp('/');

    const nav = await screen.findByRole('navigation', { name: '主导航' });
    const links = within(nav).getAllByRole('link');
    expect(links).toHaveLength(8);
    expect(links.map((link) => link.textContent)).toEqual(['工作台', '资料', '审核', '本体', '数据', '探索', '版本', '设置']);
    expect(await screen.findByRole('heading', { level: 1, name: /王工/ })).toBeInTheDocument();
  });

  it('signs in and returns to the requested page', async () => {
    const user = userEvent.setup();
    let signedIn = false;
    mockFetch((request) => {
      if (pathOf(request) === '/api/auth/login') {
        signedIn = true;
        return jsonResponse(testUser);
      }
      return signedIn ? jsonResponse(testUser) : problemResponse(401, 'auth.not_authenticated');
    });
    const { router } = renderApp('/login?redirect=%2Freview');

    await user.type(await screen.findByRole('textbox', { name: '用户名' }), 'admin');
    await user.type(screen.getByLabelText(/^密码/), 'admin12345');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByRole('heading', { level: 1, name: '审核' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/review');
  });

  it('toggles the AI assistant with Ctrl+J', async () => {
    const user = userEvent.setup();
    mockFetch(() => jsonResponse(testUser));
    renderApp('/');
    await screen.findByRole('navigation', { name: '主导航' });

    await user.keyboard('{Control>}j{/Control}');
    expect(await screen.findByRole('complementary', { name: 'AI 助手' })).toBeInTheDocument();
    expect(screen.getByText('当前页面：工作台')).toBeInTheDocument();

    await user.keyboard('{Control>}j{/Control}');
    await vi.waitFor(() => expect(screen.queryByRole('complementary', { name: 'AI 助手' })).not.toBeInTheDocument());
  });
});

describe('signing out and ended sessions', () => {
  async function signOut() {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '账号菜单：王工' }));
    await user.click(await screen.findByRole('menuitem', { name: '退出登录' }));
  }

  it('signs out and shows the login page without a redirect target', async () => {
    const fetchMock = mockFetch((request) =>
      pathOf(request) === '/api/auth/logout' ? new Response(null, { status: 204 }) : jsonResponse(testUser),
    );
    const { router } = renderApp('/settings');

    await signOut();

    expect(await screen.findByRole('heading', { name: '登录', level: 1 })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({});
    expect(fetchMock.mock.calls.some(([input]) => input instanceof Request && pathOf(input) === '/api/auth/logout')).toBe(true);
  });

  it('treats 401 from logout as already signed out, without an error toast', async () => {
    mockFetch((request) =>
      pathOf(request) === '/api/auth/logout' ? problemResponse(401, 'auth.not_authenticated') : jsonResponse(testUser),
    );
    const { router } = renderApp('/settings');

    await signOut();

    expect(await screen.findByRole('heading', { name: '登录', level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toEqual({});
    expect(screen.queryAllByText('退出登录没有完成')).toHaveLength(0);
  });

  it('keeps the user signed in and explains when logout fails for another reason', async () => {
    mockFetch((request) =>
      pathOf(request) === '/api/auth/logout' ? problemResponse(403, 'auth.csrf_failed') : jsonResponse(testUser),
    );
    const { router } = renderApp('/settings');

    await signOut();

    // The toast text is also mirrored into a live region, so pick the toast's own error title.
    const matches = await screen.findAllByText('退出登录没有完成');
    expect(matches.some((element) => element.tagName === 'H2' && element.dataset.type === 'error')).toBe(true);
    expect(screen.getAllByText('页面已过期，请刷新页面后重试。').length).toBeGreaterThan(0);
    expect(router.state.location.pathname).toBe('/settings');
  });

  it.each([
    [
      'query',
      (queryClient: QueryClient) =>
        queryClient.fetchQuery({ queryKey: ['probe'], queryFn: () => unwrap(api.GET('/api/health')), retry: false }),
    ],
    [
      'mutation',
      (queryClient: QueryClient) =>
        new MutationObserver(queryClient, { mutationFn: () => unwrapEmpty(api.POST('/api/auth/logout')) }).mutate(),
    ],
  ])('sends the user to /login?redirect=… when a %s returns 401', async (_kind, request) => {
    let sessionEnded = false;
    mockFetch(() => (sessionEnded ? problemResponse(401, 'auth.not_authenticated') : jsonResponse(testUser)));
    const { router, queryClient } = renderApp('/documents?view=list');
    expect(await screen.findByRole('heading', { level: 1, name: '资料' })).toBeInTheDocument();

    sessionEnded = true;
    await expect(request(queryClient)).rejects.toMatchObject({ status: 401 });

    expect(await screen.findByRole('heading', { name: '登录', level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toEqual({ redirect: '/documents?view=list' });
  });
});
