import createClient, { type Middleware } from 'openapi-fetch';

import { ApiError, NETWORK_ERROR_CODE, problemToError } from './errors';
import type { paths } from './schema';

export const CSRF_COOKIE = 'op_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(';')) {
    const cookie = part.trim();
    if (cookie.startsWith(prefix)) return decodeURIComponent(cookie.slice(prefix.length));
  }
  return undefined;
}

/** Double-submit CSRF: copy the readable `op_csrf` cookie into a header on every write request. */
const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (!UNSAFE_METHODS.has(request.method.toUpperCase())) return request;
    const token = readCookie(CSRF_COOKIE);
    if (token) request.headers.set(CSRF_HEADER, token);
    return request;
  },
};

/** Same-origin client; the browser sends the session cookie automatically. */
export const api = createClient<paths>({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin,
  credentials: 'same-origin',
  headers: { Accept: 'application/json, application/problem+json' },
  // Resolve fetch per call so tests (and future instrumentation) can replace it.
  fetch: (request: Request) => globalThis.fetch(request),
});
api.use(csrfMiddleware);

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

async function settle<T>(request: Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  try {
    return await request;
  } catch (cause) {
    throw new ApiError({ status: 0, code: NETWORK_ERROR_CODE, cause });
  }
}

/** Awaits an openapi-fetch call and returns its data, or throws an ApiError carrying the problem `code`. */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await settle(request);
  if (!response.ok || error !== undefined) throw problemToError(response.status, error);
  return data as T;
}

/** Like `unwrap` for responses without a body (204). */
export async function unwrapEmpty(request: Promise<FetchResult<unknown>>): Promise<void> {
  const { error, response } = await settle(request);
  if (!response.ok || error !== undefined) throw problemToError(response.status, error);
}
