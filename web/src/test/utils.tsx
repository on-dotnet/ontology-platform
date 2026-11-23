import { createMemoryHistory, RouterProvider } from '@tanstack/react-router';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { vi } from 'vitest';

import { createApp } from '@/app/create-app';
import { AppProviders } from '@/app/providers';
import { createQueryClient } from '@/app/query-client';
import type { UserInfo } from '@/features/auth/api';

export const testUser: UserInfo = {
  id: '00000000-0000-4000-8000-000000000001',
  username: 'admin',
  displayName: '王工',
  role: 'admin',
};

export function userWithRole(role: UserInfo['role']): UserInfo {
  return { ...testUser, username: role, displayName: `${role}-user`, role };
}

export function renderWithProviders(ui: ReactElement): RenderResult {
  const queryClient = createQueryClient();
  return render(<AppProviders queryClient={queryClient}>{ui}</AppProviders>);
}

/** Renders the full app (routes, guards, shell) at `path` with in-memory history. */
export function renderApp(path: string) {
  const { queryClient, router } = createApp(createMemoryHistory({ initialEntries: [path] }));
  const result = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...result, router, queryClient };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export function problemResponse(status: number, code: string, extra: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({ type: 'about:blank', title: 'Backend title', status, code, detail: 'Backend detail', ...extra }),
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

type Handler = (request: Request) => Response | Promise<Response>;

/** Replaces `fetch`; the handler receives the Request built by the API client. */
export function mockFetch(handler: Handler) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(input instanceof Request ? input : new Request(input, init))),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export function requestAt(fetchMock: ReturnType<typeof mockFetch>, index: number): Request {
  const input = fetchMock.mock.calls[index]?.[0];
  if (!(input instanceof Request)) throw new Error(`No Request recorded at call ${index}`);
  return input;
}

// --- path-aware API mock ------------------------------------------------------

export interface RecordedRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  /** Parsed JSON body; undefined for other bodies (e.g. multipart uploads). */
  body: unknown;
}

export interface RouteContext {
  request: Request;
  params: Record<string, string>;
  query: URLSearchParams;
  body: unknown;
}

/** Returns a Response, or data that is sent as JSON (undefined → 204). */
export type RouteHandler = (context: RouteContext) => unknown;

export const defaultAiStatus = { configured: true, reachable: true, model: 'gpt-test' };
export const emptyWorkbenchSummary = { pendingChangeSets: 0, entityTypes: 0, processingDocuments: 0, recentActivity: [] };

interface ApiOptions {
  /** Signed-in user; null answers /api/auth/me with 401. Defaults to `testUser`. */
  user?: UserInfo | null | (() => UserInfo | null);
}

/**
 * Builds a fetch handler from routes such as `'GET /api/change-sets/:id'`. App-wide endpoints
 * (session, AI status, workbench summary, ontologies) have defaults that routes can override.
 * Unmatched requests get a 404 problem so a missing route fails visibly.
 */
export function createApiHandler(routes: Record<string, RouteHandler> = {}, options: ApiOptions = {}) {
  const requests: RecordedRequest[] = [];
  const currentUser = () => (typeof options.user === 'function' ? options.user() : options.user === undefined ? testUser : options.user);
  const defaults: Record<string, RouteHandler> = {
    'GET /api/auth/me': () => currentUser() ?? problemResponse(401, 'auth.not_authenticated'),
    'GET /api/ai/status': () => defaultAiStatus,
    'GET /api/workbench/summary': () => emptyWorkbenchSummary,
    'GET /api/ontologies': () => [],
  };
  const compiled = Object.entries({ ...defaults, ...routes }).map(([key, handler]) => {
    const [method = 'GET', pattern = '/'] = key.split(' ');
    const names: string[] = [];
    const source = pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/:([A-Za-z]+)/g, (_match, name: string) => {
      names.push(name);
      return '([^/]+)';
    });
    return { method, regex: new RegExp(`^${source}$`), names, handler };
  });

  const handle = async (request: Request): Promise<Response> => {
    const url = new URL(request.url);
    let body: unknown;
    if ((request.headers.get('content-type') ?? '').includes('json')) {
      const text = await request.clone().text();
      body = text ? (JSON.parse(text) as unknown) : undefined;
    }
    requests.push({ method: request.method, path: url.pathname, query: url.searchParams, body });
    for (const route of compiled) {
      if (route.method !== request.method) continue;
      const match = route.regex.exec(url.pathname);
      if (!match) continue;
      const params = Object.fromEntries(route.names.map((name, index) => [name, decodeURIComponent(match[index + 1] ?? '')]));
      const result = await route.handler({ request, params, query: url.searchParams, body });
      if (result instanceof Response) return result;
      return result === undefined ? new Response(null, { status: 204 }) : jsonResponse(result);
    }
    return problemResponse(404, 'test.unmatched_route');
  };

  const calls = (method: string, path: string) => requests.filter((request) => request.method === method && request.path === path);
  return { handle, requests, calls };
}

/** `createApiHandler` installed as the global fetch. */
export function mockApi(routes: Record<string, RouteHandler> = {}, options: ApiOptions = {}) {
  const api = createApiHandler(routes, options);
  const fetchMock = mockFetch(api.handle);
  return { ...api, fetchMock };
}

/** Replaces object URLs and anchor clicks so file downloads can be asserted by file name. */
export function captureDownloads() {
  const created = vi.fn((_blob: Blob) => 'blob:test-download');
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: created });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
  const names: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    names.push(this.download);
  });
  return { names, created };
}
