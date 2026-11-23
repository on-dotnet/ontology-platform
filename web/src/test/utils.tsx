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

export function problemResponse(status: number, code: string): Response {
  return new Response(JSON.stringify({ type: 'about:blank', title: 'Backend title', status, code, detail: 'Backend detail' }), {
    status,
    headers: { 'Content-Type': 'application/problem+json' },
  });
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
