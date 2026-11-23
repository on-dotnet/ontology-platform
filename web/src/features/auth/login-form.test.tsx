import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockFetch, problemResponse, renderWithProviders, requestAt, testUser } from '@/test/utils';

import { LoginForm } from './login-form';

describe('LoginForm', () => {
  it('shows the localized message for a 401 problem response, not the backend text', async () => {
    const user = userEvent.setup();
    mockFetch(() => problemResponse(401, 'auth.invalid_credentials'));
    const onSuccess = vi.fn();
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    await user.type(screen.getByRole('textbox', { name: '用户名' }), 'admin');
    await user.type(screen.getByLabelText(/^密码/), 'wrong-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('用户名或密码不正确，请检查后重试。');
    expect(alert).not.toHaveTextContent('Backend');
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('falls back to the HTTP status message for an unknown error code', async () => {
    const user = userEvent.setup();
    mockFetch(() => problemResponse(400, 'auth.something_new'));
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);

    await user.type(screen.getByRole('textbox', { name: '用户名' }), 'admin');
    await user.type(screen.getByLabelText(/^密码/), 'x');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('请求的内容不正确，请检查后重试。');
  });

  it('validates required fields before sending anything', async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch(() => jsonResponse(testUser));
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(screen.getByRole('alert')).toHaveTextContent('请填写用户名和密码后再登录。');
    expect(screen.getByText('请输入用户名')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '用户名' })).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('stays quiet when focus leaves a field the user never typed in', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);

    // The username field is auto-focused; tabbing away without typing must not show an error.
    await user.tab();
    await user.tab();
    expect(screen.queryByText('请输入用户名')).not.toBeInTheDocument();

    // Typing and then clearing a field does show the error on blur.
    const password = screen.getByLabelText(/^密码/);
    await user.type(password, 'x');
    await user.clear(password);
    await user.tab();
    expect(screen.getByText('请输入密码')).toBeInTheDocument();
  });

  it('posts the credentials and reports the signed-in user', async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch(() => jsonResponse(testUser));
    const onSuccess = vi.fn();
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    await user.type(screen.getByRole('textbox', { name: '用户名' }), ' admin ');
    await user.type(screen.getByLabelText(/^密码/), 'admin12345');
    await user.click(screen.getByRole('button', { name: '显示密码' }));
    expect(screen.getByLabelText(/^密码/)).toHaveAttribute('type', 'text');
    await user.click(screen.getByRole('button', { name: '登录' }));

    await vi.waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(onSuccess.mock.calls[0]?.[0]).toEqual(testUser);
    const request = requestAt(fetchMock, 0);
    expect(new URL(request.url).pathname).toBe('/api/auth/login');
    expect(await request.json()).toEqual({ username: 'admin', password: 'admin12345' });
  });
});
