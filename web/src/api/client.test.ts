import { describe, expect, it } from 'vitest';

import { fetchMe, login, logout } from '@/features/auth/api';
import i18n from '@/i18n';
import { errorMessage } from '@/i18n/error-message';
import { jsonResponse, mockFetch, problemResponse, requestAt, testUser } from '@/test/utils';

import { CSRF_HEADER } from './client';
import { ApiError, NETWORK_ERROR_CODE } from './errors';

describe('API client', () => {
  it('sends the op_csrf cookie value as X-CSRF-Token on write requests', async () => {
    document.cookie = 'op_csrf=token-123; path=/';
    const fetchMock = mockFetch(() => new Response(null, { status: 204 }));

    await logout();

    const request = requestAt(fetchMock, 0);
    expect(request.method).toBe('POST');
    expect(new URL(request.url).pathname).toBe('/api/auth/logout');
    expect(request.headers.get(CSRF_HEADER)).toBe('token-123');
    expect(request.credentials).toBe('same-origin');
  });

  it('does not add the CSRF header to read requests', async () => {
    document.cookie = 'op_csrf=token-123; path=/';
    const fetchMock = mockFetch(() => jsonResponse(testUser));

    await expect(fetchMe()).resolves.toEqual(testUser);
    expect(requestAt(fetchMock, 0).headers.get(CSRF_HEADER)).toBeNull();
  });

  it('turns problem+json responses into ApiError with the stable code', async () => {
    mockFetch(() => problemResponse(401, 'auth.invalid_credentials'));

    const error: unknown = await login({ username: 'admin', password: 'wrong' }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, code: 'auth.invalid_credentials' });
  });

  it('treats 401 from /api/auth/me as "not signed in"', async () => {
    mockFetch(() => problemResponse(401, 'auth.not_authenticated'));
    await expect(fetchMe()).resolves.toBeNull();
  });

  it('reports network failures with a client-side code', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')));
    await expect(fetchMe()).rejects.toMatchObject({ status: 0, code: NETWORK_ERROR_CODE });
  });
});

describe('errorMessage', () => {
  it('prefers the code, then the HTTP status, then a generic message', () => {
    expect(errorMessage(i18n, new ApiError({ status: 401, code: 'auth.invalid_credentials' }))).toBe(
      '用户名或密码不正确，请检查后重试。',
    );
    expect(errorMessage(i18n, new ApiError({ status: 503, code: 'db.unavailable' }))).toBe('平台服务暂时不可用，请稍后重试。');
    expect(errorMessage(i18n, new ApiError({ status: 418, code: 'unknown.code' }))).toBe(
      '操作没有完成，请稍后重试。如果问题持续出现，请联系平台管理员。',
    );
    expect(errorMessage(i18n, new Error('boom'))).toBe('操作没有完成，请稍后重试。如果问题持续出现，请联系平台管理员。');
  });
});
